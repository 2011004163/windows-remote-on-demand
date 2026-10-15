param(
    [ValidateSet('Install','Start','Touch','Stop','Status')][string]$Action = 'Status',
    [string]$RuntimeRoot
)
$ErrorActionPreference = 'Stop'
$root = $PSScriptRoot
$name = 'WindowsRemote-OnDemand'
$marker = 'Windows remote desktop: on-demand only, no login trigger'
$scheduler = New-Object -ComObject 'Schedule.Service'
$scheduler.Connect()
$folder = $scheduler.GetFolder('\')
$task = $null
try { $task = $folder.GetTask($name) } catch { }
if ($task -and $task.Definition.RegistrationInfo.Description -ne $marker) { throw 'An unrelated scheduled task has the same name; it was preserved.' }

if ($Action -eq 'Install') {
    if (-not (Test-Path -LiteralPath (Join-Path $RuntimeRoot 'venv\Scripts\windows-mcp.exe'))) { throw 'The existing Windows-MCP installation was not found.' }
    [ordered]@{runtimeRoot=$RuntimeRoot;idleSeconds=300;version='0.8.8'} | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $root 'runtime.json') -Encoding UTF8
    $definition = $scheduler.NewTask(0)
    $definition.RegistrationInfo.Description = $marker
    $definition.Principal.UserId = [Security.Principal.WindowsIdentity]::GetCurrent().User.Value
    $definition.Principal.LogonType = 3 # TASK_LOGON_INTERACTIVE_TOKEN
    $definition.Principal.RunLevel = 0
    $definition.Settings.Enabled = $true
    $definition.Settings.AllowDemandStart = $true
    $definition.Settings.DisallowStartIfOnBatteries = $false
    $definition.Settings.StopIfGoingOnBatteries = $false
    $definition.Settings.ExecutionTimeLimit = 'PT24H'
    $definition.Settings.MultipleInstances = 2 # ignore a duplicate start request
    $entry = $definition.Actions.Create(0)
    $entry.Path = Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0\powershell.exe'
    $entry.Arguments = '-NoLogo -NoProfile -NonInteractive -ExecutionPolicy Bypass -WindowStyle Hidden -File "' + (Join-Path $root 'desktop-runner.ps1') + '"'
    $entry.WorkingDirectory = $root
    # There are deliberately no triggers: installation does not start the task.
    $task = $folder.RegisterTaskDefinition($name, $definition, 6, $definition.Principal.UserId, $null, 3, $null)
}
if ($Action -eq 'Start') {
    if (-not $task) { throw 'Run the Mac desktop setup command first.' }
    Set-Content -LiteralPath (Join-Path $root 'lease') -Value ([DateTime]::UtcNow.ToString('o')) -Encoding Ascii
    if ($task.State -ne 4) { $null = $task.Run($null) }
}
if ($Action -eq 'Touch') {
    if (-not $task -or $task.State -ne 4) { throw 'The desktop service is not running; start it explicitly.' }
    Set-Content -LiteralPath (Join-Path $root 'lease') -Value ([DateTime]::UtcNow.ToString('o')) -Encoding Ascii
}
if ($Action -eq 'Stop') {
    $statePath = Join-Path $root 'process.json'
    $runtimePath = Join-Path $root 'runtime.json'
    if ((Test-Path -LiteralPath $statePath) -and (Test-Path -LiteralPath $runtimePath)) {
        $state = Get-Content -LiteralPath $statePath -Raw | ConvertFrom-Json
        $runtime = Get-Content -LiteralPath $runtimePath -Raw | ConvertFrom-Json
        $process = Get-Process -Id $state.pid -ErrorAction SilentlyContinue
        if ($process -and $process.Path.StartsWith((Join-Path $runtime.runtimeRoot 'venv'), [StringComparison]::OrdinalIgnoreCase) -and $process.StartTime.ToUniversalTime().ToString('o') -eq $state.startedUtc) {
            & "$env:SystemRoot\System32\taskkill.exe" /PID $process.Id /T /F | Out-Null
        }
    }
    if ($task -and $task.State -eq 4) { $task.Stop(0) }
}
$processState = $null
if (Test-Path -LiteralPath (Join-Path $root 'process.json')) {
    $prior = Get-Content -LiteralPath (Join-Path $root 'process.json') -Raw | ConvertFrom-Json
    $p = Get-Process -Id $prior.pid -ErrorAction SilentlyContinue
    if ($p -and $p.StartTime.ToUniversalTime().ToString('o') -eq $prior.startedUtc) { $processState=$prior }
}
[ordered]@{taskName=$name;installed=($null -ne $task);taskState=$(if($task){$task.State}else{0});loginTriggerCount=$(if($task){$task.Definition.Triggers.Count}else{0});process=$processState;root=$root;idleSeconds=300} | ConvertTo-Json -Depth 5 -Compress
