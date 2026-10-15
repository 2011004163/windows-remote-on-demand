#Requires -Version 5.1
# Run as administrator on the Windows target. All addresses and keys are supplied by you.
param(
    [Parameter(Mandatory)][string]$ControllerIp,
    [Parameter(Mandatory)][string]$WindowsIp,
    [Parameter(Mandatory)][string]$PublicKeyFile
)
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$macIp = $ControllerIp
$windowsIp = $WindowsIp
$plainKey = [IO.File]::ReadAllText((Resolve-Path -LiteralPath $PublicKeyFile)).Trim()
if ($plainKey -notmatch '^ssh-ed25519 [A-Za-z0-9+/]+={0,3}(?: [^\r\n]*)?$') {throw 'Supply one plain Ed25519 PUBLIC key line.'}
$keyBody = $plainKey.Split(' ')[1]
$publicKey = 'from="' + $macIp + '" ssh-ed25519 ' + $keyBody + ' windows-remote-client'
$identity = [Security.Principal.WindowsIdentity]::GetCurrent()
$principal = New-Object Security.Principal.WindowsPrincipal($identity)
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    throw 'Run this PowerShell script as administrator.'
}
$tailscale = Join-Path $env:ProgramFiles 'Tailscale\tailscale.exe'
if (-not (Test-Path -LiteralPath $tailscale)) { throw 'Tailscale is not installed.' }
$tsText = & $tailscale status --json
if ($LASTEXITCODE -ne 0) { throw 'Cannot read Tailscale status.' }
$ts = ($tsText -join "`n") | ConvertFrom-Json
if ($ts.BackendState -ne 'Running' -or $windowsIp -notin $ts.TailscaleIPs) {
    throw 'The Windows Tailscale address must match the WindowsIp parameter.'
}

$stamp = Get-Date -Format 'yyyyMMdd-HHmmss-fff'
$logRoot = Join-Path $env:LOCALAPPDATA 'WindowsRemote\SSH-Setup'
$backup = Join-Path $logRoot $stamp
New-Item -ItemType Directory -Path $backup -Force | Out-Null
$transcriptStarted = $false
try {
    Start-Transcript -Path (Join-Path $backup 'setup.log') -Force | Out-Null
    $transcriptStarted = $true
    $ruleName = 'OpenSSH-Server-In-TCP'
    $ruleBefore = Get-NetFirewallRule -Name $ruleName -ErrorAction SilentlyContinue
    $serviceBefore = Get-Service -Name sshd -ErrorAction SilentlyContinue
    $capability = Get-WindowsCapability -Online -Name 'OpenSSH.Server~~~~0.0.1.0'
    $keysPath = Join-Path $env:ProgramData 'ssh\administrators_authorized_keys'
    $state = [ordered]@{
        computer = $env:COMPUTERNAME
        identity = $identity.Name
        capabilityBefore = [string]$capability.State
        serviceBefore = if ($serviceBefore) { [string]$serviceBefore.Status } else { $null }
        serviceStartupBefore = if ($serviceBefore) { [string]$serviceBefore.StartType } else { $null }
        firewallRuleExisted = [bool]$ruleBefore
        keysExisted = Test-Path -LiteralPath $keysPath
        macIp = $macIp
    }
    if ($ruleBefore) {
        $ruleBefore | Export-Clixml -Path (Join-Path $backup 'firewall-rule.xml')
        $ruleBefore | Get-NetFirewallAddressFilter | Export-Clixml -Path (Join-Path $backup 'firewall-addresses.xml')
    }
    if ($state.keysExisted) {
        Copy-Item -LiteralPath $keysPath -Destination (Join-Path $backup 'administrators_authorized_keys')
        (Get-Acl -LiteralPath $keysPath).Sddl | Set-Content -LiteralPath (Join-Path $backup 'authorized-keys-acl.txt')
    }
    $state | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath (Join-Path $backup 'before.json') -Encoding UTF8

    Write-Host '[1/4] Installing the Windows OpenSSH Server feature if needed...'
    if ($capability.State -ne 'Installed') {
        $installed = Add-WindowsCapability -Online -Name 'OpenSSH.Server~~~~0.0.1.0'
        if ($installed.RestartNeeded) { throw 'Windows requests a restart. Restart and run this package again.' }
    }

    Write-Host '[2/4] Adding the dedicated Mac public key...'
    New-Item -ItemType Directory -Path (Split-Path $keysPath) -Force | Out-Null
    $oldKeys = if (Test-Path -LiteralPath $keysPath) { [IO.File]::ReadAllText($keysPath) } else { '' }
    if (-not $oldKeys.Contains($keyBody)) {
        $newKeys = $oldKeys.TrimEnd([char[]]"`r`n")
        if ($newKeys.Length -gt 0) { $newKeys += "`r`n" }
        $newKeys += $publicKey + "`r`n"
        [IO.File]::WriteAllText($keysPath, $newKeys, [Text.UTF8Encoding]::new($false))
    }
    $acl = [Security.AccessControl.FileSecurity]::new()
    $adminSid = [Security.Principal.SecurityIdentifier]::new('S-1-5-32-544')
    $systemSid = [Security.Principal.SecurityIdentifier]::new('S-1-5-18')
    $acl.SetOwner($adminSid)
    $acl.SetAccessRuleProtection($true, $false)
    foreach ($sid in @($adminSid, $systemSid)) {
        $acl.AddAccessRule([Security.AccessControl.FileSystemAccessRule]::new(
            $sid, [Security.AccessControl.FileSystemRights]::FullControl,
            [Security.AccessControl.AccessControlType]::Allow))
    }
    Set-Acl -LiteralPath $keysPath -AclObject $acl

    Write-Host '[3/4] Allowing SSH from the Mac Tailscale address in the default firewall rule...'
    if (Get-NetFirewallRule -Name $ruleName -ErrorAction SilentlyContinue) {
        Set-NetFirewallRule -Name $ruleName -Enabled True -Profile Any -RemoteAddress $macIp
    } else {
        New-NetFirewallRule -Name $ruleName -DisplayName 'OpenSSH Server (Mac via Tailscale)' `
            -Enabled True -Direction Inbound -Action Allow -Protocol TCP -LocalPort 22 `
            -Profile Any -RemoteAddress $macIp | Out-Null
    }

    Write-Host '[4/4] Starting SSH and enabling automatic startup...'
    Set-Service -Name sshd -StartupType Automatic
    Start-Service -Name sshd
    $sshd = Join-Path $env:WINDIR 'System32\OpenSSH\sshd.exe'
    & $sshd -t
    if ($LASTEXITCODE -ne 0) { throw 'Existing sshd_config failed validation; see the log.' }
    if (-not (Get-NetTCPConnection -LocalPort 22 -State Listen -ErrorAction SilentlyContinue)) {
        throw 'The sshd service is not listening on TCP port 22.'
    }
    $hostKey = Join-Path $env:ProgramData 'ssh\ssh_host_ed25519_key.pub'
    $keygen = Join-Path $env:WINDIR 'System32\OpenSSH\ssh-keygen.exe'
    $fingerprint = & $keygen -lf $hostKey
    if ($LASTEXITCODE -ne 0) { throw 'Cannot read the SSH host key fingerprint.' }
    $report = [ordered]@{
        checkedAt = (Get-Date).ToString('o')
        computer = $env:COMPUTERNAME
        username = $env:USERNAME
        identity = $identity.Name
        tailscaleIp = $windowsIp
        sshd = [string](Get-Service sshd).Status
        hostKeyFingerprint = ($fingerprint -join ' ')
        publicKeyInstalled = 'windows-remote-client'
        backup = $backup
        verification = 'Local setup only; Mac SSH authentication still needs verification.'
    }
    $reportPath = Join-Path $logRoot 'windows-ssh-connection.json'
    $report | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath $reportPath -Encoding UTF8
    Write-Host ''
    Write-Host 'SSH_READY' -ForegroundColor Green
    Write-Host "USERNAME=$env:USERNAME"
    Write-Host "HOST_KEY=$($report.hostKeyFingerprint)"
    Write-Host "BACKUP=$backup"
    Write-Host 'Sending the connection report to the Mac...'
    & $tailscale file cp $reportPath ($macIp + ':')
    if ($LASTEXITCODE -ne 0) {
        Write-Warning 'Report transfer failed. Send the USERNAME and HOST_KEY lines to the Mac agent.'
    }
} catch {
    Write-Host ''
    Write-Host ('SETUP_FAILED: ' + $_.Exception.Message) -ForegroundColor Red
    Write-Host "Logs and original settings: $backup"
    exit 1
} finally {
    if ($transcriptStarted) { Stop-Transcript | Out-Null }
}
