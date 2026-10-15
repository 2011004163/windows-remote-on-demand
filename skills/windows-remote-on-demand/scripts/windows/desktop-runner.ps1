# Runs only inside the logged-in Windows user's session, on explicit demand.
$ErrorActionPreference = 'Stop'
$root = $PSScriptRoot
$settings = Get-Content -LiteralPath (Join-Path $root 'runtime.json') -Raw | ConvertFrom-Json
$exe = Join-Path $settings.runtimeRoot 'venv\Scripts\windows-mcp.exe'
$lease = Join-Path $root 'lease'
$env:ANONYMIZED_TELEMETRY = 'false'
$env:POSTHOG_API_KEY = ''
$tools = 'Snapshot,Screenshot,Click,Type,Scroll,Move,Shortcut,Wait,WaitFor,Clipboard,ControlStatus,DisplayInventory'
$arguments = 'serve --config "' + (Join-Path $root 'config.toml') + '" --tools ' + $tools + ' --stateless-http'
$process = $null
try {
    Set-Content -LiteralPath $lease -Value ([DateTime]::UtcNow.ToString('o')) -Encoding Ascii
    $process = Start-Process -FilePath $exe -ArgumentList $arguments -WindowStyle Hidden -WorkingDirectory $root -RedirectStandardOutput (Join-Path $root 'stdout.log') -RedirectStandardError (Join-Path $root 'stderr.log') -PassThru
    [ordered]@{pid=$process.Id;startedUtc=$process.StartTime.ToUniversalTime().ToString('o');runnerPid=$PID;sessionId=(Get-Process -Id $PID).SessionId} | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $root 'process.json') -Encoding UTF8
    while (-not $process.HasExited) {
        if (([DateTime]::UtcNow - (Get-Item -LiteralPath $lease).LastWriteTimeUtc).TotalSeconds -gt 300) { break }
        Start-Sleep -Seconds 3
        $process.Refresh()
    }
} finally {
    if ($process) {
        $process.Refresh()
        if (-not $process.HasExited) { & "$env:SystemRoot\System32\taskkill.exe" /PID $process.Id /T /F | Out-Null }
    }
}
