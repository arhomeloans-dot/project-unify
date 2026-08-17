$tok = [Environment]::GetEnvironmentVariable("HF_TOKEN","User")
if ([string]::IsNullOrEmpty($tok)) { $tok = $env:HF_TOKEN }
$hdr = @{ Authorization = "Bearer $tok" }

Write-Host "========================================================"
Write-Host "HF ROUTER - AVAILABLE MODELS"
Write-Host "========================================================"

try {
    $models = Invoke-RestMethod -Uri "https://router.huggingface.co/v1/models" -Headers $hdr -TimeoutSec 20
    $all = $models.data
    Write-Host ("Router reachable. Total models served: {0}" -f $all.Count)
    Write-Host ""
    Write-Host "--- Matching 'kimi' or 'moonshot' ---"
    $all | Where-Object { $_.id -match '(?i)kimi|moonshot' } | ForEach-Object { Write-Host ("  {0}" -f $_.id) }
    Write-Host ""
    Write-Host "--- Matching 'glm' or 'zai' ---"
    $all | Where-Object { $_.id -match '(?i)glm|zai' } | ForEach-Object { Write-Host ("  {0}" -f $_.id) }
} catch {
    Write-Host "Router query FAILED - $($_.Exception.Message)"
    Write-Host ""
    Write-Host "Falling back to Hub search..."
    foreach ($q in @("Kimi","GLM")) {
        Write-Host "--- Hub search: $q ---"
        try {
            $r = Invoke-RestMethod -Uri "https://huggingface.co/api/models?search=$q&sort=downloads&direction=-1&limit=10" -Headers $hdr -TimeoutSec 20
            $r | ForEach-Object { Write-Host ("  {0}" -f $_.id) }
        } catch {
            Write-Host "  failed: $($_.Exception.Message)"
        }
    }
}
