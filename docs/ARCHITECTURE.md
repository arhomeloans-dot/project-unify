# Architecture

```
        ┌─────────────────────────────────────────────┐
Scribe ─┤                                             │
Librar.─┤   Project Unify daemon   127.0.0.1:11435    │
Archiv.─┤   POST /infer  GET /metrics  GET /health    │
        └──────────────────┬──────────────────────────┘
                           │ complexity score 0.0–1.0
              ┌────────────┼─────────────┐
              ▼            ▼             ▼
        < 0.80        0.80–0.95       ≥ 0.95
         TIER 1         TIER 2         TIER 3
       Gemma2:9b      Llama3.1      Kimi-K3 → GLM 5.2
       (Ollama)       (Ollama)      (HF router)
        $0.00          $0.00        ~$0.00015/doc
           └──── on timeout ──►└──── on timeout ──►┘
```

## Complexity scoring

```
complexity = min(task_weight + min(len(content)/1000, 0.3), 1.0)
```

| `task_type` | Base weight | Typical destination |
|---|---|---|
| `classify` | 0.30 | Tier 1 |
| `summarize` | 0.30 | Tier 1 |
| `extract_entities` | 0.40 | Tier 1 |
| `reconcile` | 0.70 | Tier 2 (with length) |
| `judicial` | 0.99 | Tier 3 |

Length contributes up to +0.30, so a long `reconcile` reaches Tier 2 and a
`judicial` task always lands on Tier 3. Unknown task types default to 0.50.

## Failover

Escalation is one-directional and triggers on **timeout (504)** or **any
non-200**. Each hop is appended to `failover_chain`, returned with the response,
so you can always see the path a document actually took:

```
tier1_local → tier2_llama → tier3_kimi → tier3_glm
```

GLM 5.2 is the terminal tier; if it fails, the error is returned and
`performance.errors` increments. A clean run shows a single-element chain and
`failover_events: 0` — that's the target state.

## Confidence

Fixed per tier, reflecting model capability, not per-response certainty:
Tier 1 `0.75`, Tier 2 `0.85`, Tier 3 Kimi `0.90` / GLM `0.88`. Zero on failure.
Treat these as routing metadata, not calibrated probabilities.

## Timeouts

`(connect, read)` seconds, in `TIMEOUT_CONFIG`:

| Tier | Connect | Read |
|---|---|---|
| `tier1_local` | 3 | 90 |
| `tier2_llama` | 3 | 120 |
| `tier3_kimi` | 10 | 60 |
| `tier3_glm` | 10 | 60 |

Local tiers get short connect (Ollama is on the same box) and long read (GPU
generation is slow). Remote tiers invert that.

## Concurrency

`ThreadingHTTPServer` with `daemon_threads = True`. Metrics are mutated under a
`threading.Lock`. Note that Ollama itself serializes GPU work, so parallel local
requests queue at the GPU regardless of daemon concurrency.

## State

Metrics are **in-memory only** — they reset when the daemon restarts. Durable
history (e.g. CockroachDB) is a future addition; the dashboard reads live
values.
