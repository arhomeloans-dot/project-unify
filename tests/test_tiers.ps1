$ErrorActionPreference = "Continue"

Write-Host "========================================================"
Write-Host "PROJECT UNIFY - TIER ROUTING TEST"
Write-Host "========================================================"

try {
    $h = Invoke-RestMethod -Uri "http://127.0.0.1:11435/health" -TimeoutSec 3
    Write-Host "Daemon: HEALTHY"
} catch {
    Write-Host "Daemon: NOT RUNNING. Run .\start_daemon.ps1 first."
    exit 1
}
Write-Host ""

$tests = @(
  @{ id="t1_classify";  task="classify";         text="Invoice from Acme Corp dated 2026-08-15 for consulting services." },
  @{ id="t2_reconcile"; task="reconcile";        text="Primary ledger 10,234 records. Secondary ledger 10,198 records. Variance 36 records. Identify likely cause." },
  @{ id="t3_judicial";  task="judicial";         text="Determine whether the settlement terms conflict with the governing precedent and state the controlling rule." }
)

$n = 1
foreach ($t in $tests) {
    Write-Host ("[{0}/{1}] {2}  (task={3})" -f $n, $tests.Count, $t.id, $t.task)
    $body = @{ doc_id = $t.id; task_type = $t.task; content = $t.text } | ConvertTo-Json
    try {
        $r = Invoke-RestMethod -Uri "http://127.0.0.1:11435/infer" -Method POST -Body $body -ContentType "application/json" -TimeoutSec 200
        $flow = $r.failover_chain -join " -> "
        Write-Host ("    complexity : {0:F3}" -f $r.complexity)
        Write-Host ("    tier       : {0}" -f $r.actual_tier)
        Write-Host ("    chain      : {0}" -f $flow)
        Write-Host ("    latency    : {0:F0} ms" -f $r.latency_ms)
        if ($r.success) { Write-Host "    result     : SUCCESS" } else { Write-Host "    result     : FAILED (http $($r.http_status))" }
    } catch {
        Write-Host "    result     : REQUEST ERROR - $($_.Exception.Message)"
    }
    Write-Host ""
    $n++
}

Write-Host "========================================================"
Write-Host "METRICS"
Write-Host "========================================================"
try {
    $m = Invoke-RestMethod -Uri "http://127.0.0.1:11435/metrics" -TimeoutSec 5
    Write-Host ("total_requests : {0}" -f $m.total_requests)
    Write-Host ("failover_events: {0}" -f $m.failover_events)
    Write-Host ("avg_latency_ms : {0}" -f $m.performance.avg_latency_ms)
    Write-Host "routing_breakdown:"
    $m.routing_breakdown.PSObject.Properties | ForEach-Object { Write-Host ("  {0,-12} {1}" -f $_.Name, $_.Value) }
} catch {
    Write-Host "Could not fetch metrics: $($_.Exception.Message)"
}
