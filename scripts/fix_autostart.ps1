$TaskName = "ProjectUnifyDaemon"
$Dir      = "$PSScriptRoot\.."
$Python   = "$PythonDir\pythonw.exe"
if (-not (Test-Path $Python)) { $Python = "$PythonDir\python.exe" }

Write-Host "========================================================"
Write-Host "AUTO-START CONFIGURATION"
Write-Host "========================================================"

Write-Host ""
Write-Host "Current task configuration:"
$t = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
if ($t) {
    Write-Host ("  Trigger  : {0}" -f ($t.Triggers | ForEach-Object { $_.CimClass.CimClassName }))
    Write-Host ("  RunAs    : {0}" -f $t.Principal.UserId)
    Write-Host ("  LogonType: {0}" -f $t.Principal.LogonType)
} else {
    Write-Host "  (task not found - will create)"
}

Write-Host ""
Write-Host "Re-registering with AtLogOn trigger..."

$me       = "$env:USERDOMAIN\$env:USERNAME"
$trigger  = New-ScheduledTaskTrigger -AtLogOn -User $me
$action   = New-ScheduledTaskAction -Execute $Python -Argument "$Dir\project_unify_daemon.py" -WorkingDirectory $Dir
$principal= New-ScheduledTaskPrincipal -UserId $me -LogonType Interactive -RunLevel Limited
$settings = New-ScheduledTaskSettingsSet -MultipleInstances IgnoreNew `
                                         -ExecutionTimeLimit ([timespan]::Zero) `
                                         -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1) `
                                         -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries

Register-ScheduledTask -TaskName $TaskName -Trigger $trigger -Action $action `
                       -Principal $principal -Settings $settings -Force | Out-Null

Write-Host "  DONE"
Write-Host ""

$t = Get-ScheduledTask -TaskName $TaskName
Write-Host "New configuration:"
Write-Host ("  Trigger  : {0}" -f ($t.Triggers | ForEach-Object { $_.CimClass.CimClassName }))
Write-Host ("  RunAs    : {0}" -f $t.Principal.UserId)
Write-Host ("  Restart  : up to 3 times, 1 min apart, on failure")

Write-Host ""
Write-Host "HF_TOKEN check (must be User-scope for the task to see it):"
$tok = [Environment]::GetEnvironmentVariable("HF_TOKEN","User")
if ([string]::IsNullOrEmpty($tok)) {
    Write-Host "  NOT SET at User scope - Tier 3 would fail after reboot."
    Write-Host "  Fix with:"
    Write-Host '    [Environment]::SetEnvironmentVariable("HF_TOKEN","<your-token>","User")'
} else {
    Write-Host ("  OK - persists across reboot ({0}...)" -f $tok.Substring(0,[Math]::Min(12,$tok.Length)))
}

Write-Host ""
Write-Host "========================================================"
Write-Host "Ready to reboot. After restart, verify with:"
Write-Host "  cd $Dir; .\test_tiers.ps1"
Write-Host "========================================================"
