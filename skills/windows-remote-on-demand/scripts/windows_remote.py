#!/usr/bin/env python3
"""Run PowerShell and transfer files through the verified Windows SSH connection."""

import argparse
import base64
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import uuid


DEFAULT_CONFIG = Path.home() / ".ssh/windows_remote.conf"
HOST = "windows-remote"
INFO_SCRIPT = r"""
$os = Get-CimInstance Win32_OperatingSystem
$system = Get-CimInstance Win32_ComputerSystem
[ordered]@{
    computer = $env:COMPUTERNAME
    username = $env:USERNAME
    home = $env:USERPROFILE
    powershell = $PSVersionTable.PSVersion.ToString()
    os = $os.Caption
    cpu = @(Get-CimInstance Win32_Processor | ForEach-Object { $_.Name })
    memoryBytes = [long]$system.TotalPhysicalMemory
    drives = @(Get-CimInstance Win32_LogicalDisk -Filter 'DriveType=3' | ForEach-Object {
        [ordered]@{drive=$_.DeviceID;label=$_.VolumeName;sizeBytes=[long]$_.Size;freeBytes=[long]$_.FreeSpace}
    })
    gpu = @(Get-CimInstance Win32_VideoController | Select-Object Name, DriverVersion)
} | ConvertTo-Json -Depth 5
"""


def ps_literal(value):
    return "'" + str(value).replace("'", "''") + "'"


def wrapped_script(script):
    return (
        "$ErrorActionPreference='Stop'; $ProgressPreference='SilentlyContinue'; "
        "[Console]::OutputEncoding=[Text.UTF8Encoding]::new($false); "
        "$OutputEncoding=[Console]::OutputEncoding; $global:LASTEXITCODE=0;\n"
        "try {\n" + script + "\n"
        "$windowsRemoteExit=$LASTEXITCODE; exit $windowsRemoteExit\n"
        "} catch { [Console]::Error.WriteLine(($_ | Out-String)); exit 1 }\n"
    )


def encoded_command(script):
    payload = base64.b64encode(script.encode("utf-16le")).decode("ascii")
    return "powershell.exe -NoLogo -NoProfile -NonInteractive -EncodedCommand " + payload


def execute(command, timeout, input_text=None):
    return subprocess.run(
        command, input=input_text, capture_output=True, text=True,
        encoding="utf-8", errors="replace", timeout=timeout,
    )


def ssh(config, command, timeout):
    return execute(["ssh", "-F", str(config), HOST, command], timeout)


def batch_quote(value):
    text = str(value)
    if any(char in text for char in ("\n", "\r", "\x00")):
        raise ValueError("File paths must not contain line breaks or NUL bytes")
    return '"' + text.replace("\\", "\\\\").replace('"', '\\"') + '"'


def remote_path(value):
    normalized = value.replace("\\", "/")
    if len(normalized) >= 2 and normalized[0].isalpha() and normalized[1] == ":":
        if not normalized[2:].startswith("/"):
            raise ValueError("Use an absolute Windows path, for example D:/RemoteWork/file.bin")
        # Windows SFTP treats C:/... as relative to the login directory.
        return "/" + normalized
    return normalized


def sftp(config, operation, source, target, timeout):
    batch = operation + " " + batch_quote(source) + " " + batch_quote(target) + "\n"
    return execute(["sftp", "-F", str(config), "-b", "-", HOST], timeout, batch)


def run_powershell(config, script, timeout):
    source = wrapped_script(script)
    command = encoded_command(source)
    if len(command) <= 7000:
        return ssh(config, command, timeout)

    # cmd.exe has a short command-line limit. Stage larger scripts via SFTP.
    name = "windows-remote-" + uuid.uuid4().hex + ".ps1"
    prepare = (
        "$d=Join-Path $env:LOCALAPPDATA 'WindowsRemote\\Scripts'; "
        "New-Item -ItemType Directory -Force -Path $d | Out-Null; "
        "(Join-Path $d " + ps_literal(name) + ") | ConvertTo-Json -Compress"
    )
    result = ssh(config, encoded_command(wrapped_script(prepare)), timeout)
    if result.returncode:
        return result
    destination = json.loads(result.stdout)
    with tempfile.TemporaryDirectory(prefix="windows-remote-") as temp:
        local = Path(temp) / name
        # Windows PowerShell 5.1 needs a BOM to identify UTF-8 source text.
        local.write_text(source, encoding="utf-8-sig")
        sent = sftp(config, "put", local, remote_path(destination), timeout)
        if sent.returncode:
            return sent
    invoke = "& powershell.exe -NoLogo -NoProfile -NonInteractive -ExecutionPolicy Bypass -File " + ps_literal(destination)
    return ssh(config, encoded_command(wrapped_script(invoke)), timeout)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--timeout", type=float, default=60, help="Local wait limit in seconds; no automatic retries")
    sub = parser.add_subparsers(dest="action", required=True)
    sub.add_parser("info", help="Read Windows system, CPU, RAM, disks, and graphics adapters")
    run = sub.add_parser("run", help="Run PowerShell synchronously; long-running jobs need a separate task manager")
    source = run.add_mutually_exclusive_group(required=True)
    source.add_argument("--command", help="PowerShell source code")
    source.add_argument("--file", type=Path, help="Local UTF-8 PowerShell script")
    put = sub.add_parser("put", help="Upload one file with SFTP; the destination directory must exist")
    put.add_argument("local", type=Path)
    put.add_argument("remote", help="Windows path, for example D:/RemoteWork/input.bin")
    get = sub.add_parser("get", help="Download one file with SFTP")
    get.add_argument("remote")
    get.add_argument("local", type=Path)
    args = parser.parse_args()
    args.config = args.config.expanduser().resolve()
    if not args.config.is_file():
        parser.error("Verified SSH configuration is missing: " + str(args.config))
    if args.timeout <= 0:
        parser.error("--timeout must be positive")
    try:
        if args.action == "info":
            result = run_powershell(args.config, INFO_SCRIPT, args.timeout)
        elif args.action == "run":
            script = args.command if args.command is not None else args.file.expanduser().read_text(encoding="utf-8-sig")
            result = run_powershell(args.config, script, args.timeout)
        elif args.action == "put":
            local = args.local.expanduser().resolve()
            if not local.is_file():
                parser.error("Local source file does not exist: " + str(local))
            result = sftp(args.config, "put", local, remote_path(args.remote), args.timeout)
        else:
            local = args.local.expanduser().resolve()
            local.parent.mkdir(parents=True, exist_ok=True)
            result = sftp(args.config, "get", remote_path(args.remote), local, args.timeout)
    except subprocess.TimeoutExpired:
        print("Local wait timed out. Remote task state is unknown; check it before resubmitting.", file=sys.stderr)
        return 124
    except (OSError, ValueError) as error:
        print(str(error), file=sys.stderr)
        return 2
    sys.stdout.write(result.stdout)
    sys.stderr.write(result.stderr)
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
