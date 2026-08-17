# Tuning a node

Every machine has different GPU throughput, so thresholds and timeouts must be
calibrated per node. This is the "slide-scale gauge" the Orion dashboard exists
to inform.

## 1. Measure before you tune

```powershell
.\tests\test_tiers.ps1
```

Run it twice — once cold (right after boot) and once warm. The gap is large:
the reference RTX 3050 measured **72s cold vs 37s warm** on Tier 1.

## 2. Set timeouts from observed latency

Rule of thumb: **timeout ≈ 1.75 × warm latency**, and always above your cold
number. Too tight and you pay the full timeout *before* redoing the work on the
next tier — the worst of both.

Edit `TIMEOUT_CONFIG` in `src/project_unify_daemon.py`.

## 3. Set thresholds from cost vs. speed

```python
COMPLEXITY_THRESHOLD_T2 = 0.80   # Tier 1 → Tier 2
COMPLEXITY_THRESHOLD_T3 = 0.95   # Tier 2 → Tier 3
```

The tradeoff is not the usual one. On the reference machine the **paid tier is
~10× faster** than local (6s vs 37–82s). So:

- **Cost-first** (default): raise thresholds, keep work local, accept ~60s/doc.
- **Throughput-first**: lower `THRESHOLD_T3` toward ~0.60. A 10× speedup for
  ~$0.00015/doc is cheap if volume is bursty or a human is waiting.
- **Quality-first**: lower thresholds for `reconcile`/`judicial` only, by
  raising those task weights instead of moving the global thresholds.

At ~$0.00015/doc, 10,000 documents through Tier 3 costs about **$1.50**. Weigh
that against ~7 hours of local GPU time for the same batch.

## 4. Per-task tuning

Often better than moving global thresholds — adjust the weights in
`estimate_complexity()`. Raising `reconcile` from 0.70 to 0.85 pushes
reconciliation to Tier 2 regardless of length, without affecting classification.

## 5. Watch the failover rate

`failover_events` in `/metrics` is the health signal. A rising count means a
tier is under-provisioned for its workload — every failover is a full wasted
timeout. Target zero in steady state.
