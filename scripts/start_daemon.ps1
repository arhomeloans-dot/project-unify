$ErrorActionPreference = "Stop"
$Dir    = "$PSScriptRoot\.."
$Python = "$PythonDir\pythonw.exe"
if (-not (Test-Path $Python)) { $Python = "$PythonDir\python.exe" }

Write-Host "Stopping any existing daemon..."
Get-CimInstance Win32_Process -Filter "Name like 'python%'" |
    Where-Object { $_.CommandLine -like "*project_unify_daemon.py*" } |
    ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
Start-Sleep -Seconds 3

# Verify the port is actually free before starting
$busy = Get-NetTCPConnection -LocalPort 11435 -State Listen -ErrorAction SilentlyContinue
if ($busy) {
    Write-Host "WARNING: port 11435 still in use by PID $($busy.OwningProcess) - stopping it"
    Stop-Process -Id $busy.OwningProcess -Force -ErrorAction SilentlyContinue
    Start-Sleep -Seconds 3
}

Remove-Item "$Dir\__pycache__" -Recurse -Force -ErrorAction SilentlyContinue

Write-Host "Starting daemon (detached)..."
Start-Process -FilePath $Python `
              -ArgumentList "$Dir\project_unify_daemon.py" `
              -WorkingDirectory $Dir `
              -WindowStyle Hidden

Write-Host "Waiting for daemon to come up..."
$ok = $false
foreach ($i in 1..45) {
    Start-Sleep -Seconds 1
    try {
        $h = Invoke-RestMethod -Uri "http://127.0.0.1:11435/health" -TimeoutSec 2
        Write-Host "DAEMON UP - status: $($h.status)"
        $ok = $true
        break
    } catch { }
}
if (-not $ok) {
    Write-Host "DAEMON DID NOT START - last 20 log lines:"
    Get-Content "$Dir\project_unify_daemon.log" -Tail 20
    exit 1
}
Write-Host ""
Write-Host "Daemon runs in the background. You can close this window."
