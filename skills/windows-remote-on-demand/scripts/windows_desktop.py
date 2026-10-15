#!/usr/bin/env python3
"""Use Windows-MCP on demand without registering permanent tools in an AI client."""
import argparse
import base64
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request

import windows_remote as remote

REPO = Path(__file__).resolve().parent
CONFIG = Path.home() / '.config/windows-remote/desktop.json'
STATE = Path.home() / '.local/state/windows-remote'
ROOT = 'D:/RemoteWork/Tools/Windows-MCP'
TASK = 'WindowsRemote-OnDemand'
PORT = 18409


def emit(value):
    print(json.dumps(value, ensure_ascii=False, indent=2))


def checked(result):
    if result.returncode:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip() or 'Remote command failed')
    return result.stdout


def ps(script, timeout=25):
    return checked(remote.run_powershell(remote.DEFAULT_CONFIG, script, timeout))


def load():
    if not CONFIG.is_file():
        raise RuntimeError('Desktop access is not installed; run setup first')
    return json.loads(CONFIG.read_text())


def manage(action, extra=''):
    return json.loads(ps('Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass -Force; & ' + remote.ps_literal(ROOT + '/desktop-manage.ps1') + ' -Action ' + action + extra))


def control(operation):
    return subprocess.run(['ssh', '-F', str(remote.DEFAULT_CONFIG), '-S', str(STATE / 'ssh.sock'), '-O', operation, remote.HOST], capture_output=True, text=True, timeout=12)


def request(config, method, params=None):
    body = {'jsonrpc': '2.0', 'id': 1, 'method': method}
    if params is not None:
        body['params'] = params
    req = urllib.request.Request(
        'http://127.0.0.1:' + str(PORT) + '/mcp',
        data=json.dumps(body).encode(),
        headers={'Authorization': 'Bearer ' + config['auth_key'], 'Content-Type': 'application/json', 'Accept': 'application/json, text/event-stream'},
    )
    # Ignore proxy environment variables for this loopback-only SSH tunnel.
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(req, timeout=75) as response:
        text = response.read().decode('utf-8')
        if 'text/event-stream' in response.headers.get('Content-Type', ''):
            messages = [json.loads(line[5:].strip()) for line in text.splitlines() if line.startswith('data:')]
            data = next((m for m in messages if m.get('id') == 1), None)
        else:
            data = json.loads(text)
    if data is None:
        raise RuntimeError('MCP returned no response; the call outcome is unknown. Do not automatically repeat it.')
    if 'error' in data:
        raise RuntimeError(json.dumps(data['error'], ensure_ascii=False))
    return data.get('result', {})


def initialize(config):
    return request(config, 'initialize', {'protocolVersion': '2025-03-26', 'capabilities': {}, 'clientInfo': {'name': 'Windows-Remote-OnDemand', 'version': '1.0'}})


def setup():
    CONFIG.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    if CONFIG.exists():
        config = load()
    else:
        config = {'auth_key': secrets.token_urlsafe(36), 'port': PORT, 'root': ROOT, 'task': TASK}
        descriptor = os.open(CONFIG, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, 'w') as stream:
            json.dump(config, stream)
    ps("$d=" + remote.ps_literal(ROOT) + "; New-Item -ItemType Directory -Force -Path $d | Out-Null; "
       "$i=[Security.Principal.WindowsIdentity]::GetCurrent(); $a=New-Object Security.AccessControl.DirectorySecurity; "
       "$a.SetAccessRuleProtection($true,$false); $a.SetOwner($i.User); "
       "foreach($s in @($i.User,(New-Object Security.Principal.SecurityIdentifier('S-1-5-18')))){ "
       "$r=New-Object Security.AccessControl.FileSystemAccessRule($s,'FullControl','ContainerInherit,ObjectInherit','None','Allow'); $a.AddAccessRule($r) }; Set-Acl -LiteralPath $d -AclObject $a")
    source = REPO / 'windows'
    with tempfile.TemporaryDirectory(prefix='windows-desktop-') as directory:
        temp = Path(directory)
        for name in ['desktop-runner.ps1', 'desktop-manage.ps1']:
            path = temp / name
            path.write_text((source / name).read_text(), encoding='utf-8-sig')
            checked(remote.sftp(remote.DEFAULT_CONFIG, 'put', path, remote.remote_path(ROOT + '/' + name), 30))
        config_file = temp / 'config.toml'
        config_file.write_text('[server]\ntransport = "streamable-http"\nhost = "127.0.0.1"\nport = ' + str(PORT) + '\nauth_key = "' + config['auth_key'] + '"\nstateless_http = true\n', encoding='utf-8')
        checked(remote.sftp(remote.DEFAULT_CONFIG, 'put', config_file, remote.remote_path(ROOT + '/config.toml'), 30))
    return manage('Install', " -RuntimeRoot (Join-Path $env:LOCALAPPDATA 'WindowsRemote\\WindowsMCP')")


def stop():
    try:
        result = manage('Stop')
    finally:
        if STATE.exists():
            control('exit')
    if result['taskState'] == 4:
        time.sleep(0.5)
        result = manage('Status')
    tunnel = STATE.exists() and control('check').returncode == 0
    return {'windows': result, 'tunnelRunning': tunnel, 'stopped': result['process'] is None and result['taskState'] != 4 and not tunnel}


def start():
    config = load()
    STATE.mkdir(parents=True, exist_ok=True, mode=0o700)
    result = manage('Start')
    try:
        if control('check').returncode:
            # A multiplexed master exits after 300 seconds without forwarding activity.
            command = ['ssh', '-F', str(remote.DEFAULT_CONFIG), '-M', '-S', str(STATE / 'ssh.sock'), '-f', '-N', '-o', 'ControlPersist=300', '-o', 'ExitOnForwardFailure=yes', '-L', f'127.0.0.1:{PORT}:127.0.0.1:{PORT}', remote.HOST]
            checked(subprocess.run(command, capture_output=True, text=True, timeout=15))
        deadline = time.monotonic() + 40
        last = None
        while time.monotonic() < deadline:
            try:
                server = initialize(config)
                return {'ready': True, 'server': server.get('serverInfo'), 'windows': manage('Status')}
            except (urllib.error.URLError, OSError) as error:
                last = error
                time.sleep(0.5)
        raise RuntimeError('Desktop server did not become ready: ' + str(last))
    except Exception:
        stop()
        raise


def save_images(result, output):
    def visit(item):
        if isinstance(item, list):
            for value in item:
                visit(value)
        elif isinstance(item, dict) and item.get('type') == 'image' and 'data' in item:
            output.mkdir(parents=True, exist_ok=True)
            suffix = '.png' if item.get('mimeType') == 'image/png' else '.jpg'
            path = output / (time.strftime('%Y%m%d-%H%M%S') + '-' + secrets.token_hex(3) + suffix)
            path.write_bytes(base64.b64decode(item.pop('data'), validate=True))
            item['type'] = 'image_saved'
            item['path'] = str(path.resolve())
        elif isinstance(item, dict):
            for value in item.values():
                visit(value)
    visit(result)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='action', required=True)
    for action in ['setup', 'start', 'status', 'stop', 'tools']:
        sub.add_parser(action)
    describe = sub.add_parser('describe')
    describe.add_argument('tool')
    call = sub.add_parser('call')
    call.add_argument('tool')
    arguments = call.add_mutually_exclusive_group()
    arguments.add_argument('--args', default='{}', help='JSON object of tool arguments')
    arguments.add_argument('--args-file', type=Path, help='UTF-8 JSON object')
    call.add_argument('--output', type=Path, default=Path.cwd() / 'outputs/windows-desktop')
    args = parser.parse_args()
    try:
        if args.action == 'setup':
            result = setup()
        elif args.action == 'start':
            result = start()
        elif args.action == 'stop':
            result = stop()
        elif args.action == 'status':
            result = {'windows': manage('Status'), 'tunnelRunning': STATE.exists() and control('check').returncode == 0}
        else:
            config = load()
            if control('check').returncode:
                raise RuntimeError('Desktop tunnel is stopped; run start explicitly')
            manage('Touch')
            initialize(config)
            if args.action in ['tools', 'describe']:
                tools = request(config, 'tools/list').get('tools', [])
                if args.action == 'tools':
                    result = {'tools': [t['name'] for t in tools]}
                else:
                    result = next((t for t in tools if t['name'] == args.tool), None)
                    if result is None:
                        raise ValueError('Unknown desktop tool: ' + args.tool)
            else:
                arguments = json.loads(args.args_file.read_text(encoding='utf-8') if args.args_file else args.args)
                if not isinstance(arguments, dict):
                    raise ValueError('Tool arguments must be a JSON object')
                result = save_images(request(config, 'tools/call', {'name': args.tool, 'arguments': arguments}), args.output)
        emit(result)
        return 1 if isinstance(result, dict) and (result.get('isError') or result.get('stopped') is False) else 0
    except (OSError, ValueError, RuntimeError, subprocess.TimeoutExpired) as error:
        emit({'error': str(error), 'automaticRetry': False})
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
