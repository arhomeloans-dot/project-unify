Write-Host "========================================================"
Write-Host "HUGGINGFACE TIER 3 DIAGNOSTIC"
Write-Host "========================================================"

$tok = [Environment]::GetEnvironmentVariable("HF_TOKEN","User")
if ([string]::IsNullOrEmpty($tok)) { $tok = $env:HF_TOKEN }
if ([string]::IsNullOrEmpty($tok)) {
    Write-Host "1. HF_TOKEN : NOT SET"
} else {
    Write-Host ("1. HF_TOKEN : SET ({0}...)" -f $tok.Substring(0,[Math]::Min(12,$tok.Length)))
}

Write-Host ""
Write-Host "2. DNS resolution:"
try {
    $ips = [System.Net.Dns]::GetHostAddresses("api-inference.huggingface.co")
    Write-Host ("   OK -> {0}" -f ($ips -join ", "))
} catch {
    Write-Host "   FAILED - $($_.Exception.Message)"
}

Write-Host ""
Write-Host "3. HTTPS reachability (router.huggingface.co):"
try {
    $r = Invoke-WebRequest -Uri "https://huggingface.co" -Method HEAD -TimeoutSec 10
    Write-Host ("   OK - HTTP {0}" -f $r.StatusCode)
} catch {
    Write-Host "   FAILED - $($_.Exception.Message)"
}

Write-Host ""
Write-Host "4. Token validity (whoami):"
if (-not [string]::IsNullOrEmpty($tok)) {
    try {
        $who = Invoke-RestMethod -Uri "https://huggingface.co/api/whoami-v2" -Headers @{ Authorization = "Bearer $tok" } -TimeoutSec 10
        Write-Host ("   OK - authenticated as: {0}" -f $who.name)
    } catch {
        Write-Host "   FAILED - $($_.Exception.Message)"
    }
} else {
    Write-Host "   SKIPPED - no token"
}
