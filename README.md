# Project Unify

Complexity-based LLM router. One HTTP endpoint decides, per document, whether a
task is cheap enough to run on a local model or hard enough to justify a paid
API call — then fails over automatically if a tier stalls.

Built for the HOS three-agent pipeline (Scribe / AssistantLibrarian / Archivist),
but the interface is generic: `POST /infer` with a document, get back the answer
plus the full routing record.

## Why

Running every document through a frontier API is expensive. Running every
document through a 9B local model is slow and sometimes not good enough.
Project Unify scores each request 0.0–1.0 and sends it to the cheapest tier
that can plausibly handle it, escalating only on timeout or failure.

Measured on an RTX 3050 (see `docs/TUNING.md` for how to calibrate your own):

| Tier | Model | Where | Typical latency | Cost/doc |
|------|-------|-------|-----------------|----------|
| 1 | Gemma2:9b | Local (Ollama) | 35–52s warm, ~72s cold | $0.00 |
| 2 | Llama3.1 | Local (Ollama) | 62–82s | $0.00 |
| 3 | Kimi-K3 → GLM 5.2 | HuggingFace router | ~6s | ~$0.00015 |

Note the inversion: the paid tier is roughly **10× faster** than the local
tiers. Cost and speed pull in opposite directions here, which is exactly why the
thresholds are tunable per machine.

## Quick start

```powershell
# 1. Prerequisites: Python 3.11+, Ollama running, models pulled
ollama pull gemma2:9b
ollama pull llama3.1

# 2. Tier 3 token (optional — tiers 1 and 2 work without it)
[Environment]::SetEnvironmentVariable("HF_TOKEN","hf_xxx","User")

# 3. Start
.\scripts\start_daemon.ps1

# 4. Verify all three tiers
.\tests\test_tiers.ps1
```

Then `.\scripts\fix_autostart.ps1` to register it to launch at logon.

## API

**`POST /infer`**

```json
{ "doc_id": "scribe_001", "task_type": "classify", "content": "..." }
```

Returns the result plus a full routing record — complexity score, tier chosen,
failover chain, latency, cost, confidence:

```json
{
  "doc_id": "scribe_001",
  "complexity": 0.364,
  "initial_tier": "tier1_local",
  "actual_tier": "tier1_local",
  "failover_chain": ["tier1_local"],
  "latency_ms": 37056,
  "cost_usd": 0.0,
  "confidence": 0.75,
  "success": true
}
```

`task_type` is one of `classify`, `summarize`, `extract_entities`, `reconcile`,
`judicial` — each carries a base complexity weight. See `docs/ARCHITECTURE.md`.

**`GET /metrics`** — cumulative routing breakdown, cost, latency, failover count.
**`GET /health`** — liveness check.

## Docs

- [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) — how routing and failover work
- [`docs/DEPLOYMENT.md`](docs/DEPLOYMENT.md) — standing up a new node
- [`docs/TUNING.md`](docs/TUNING.md) — calibrating thresholds per machine
- [`docs/TROUBLESHOOTING.md`](docs/TROUBLESHOOTING.md) — **read this first when something breaks**
- [`SECURITY.md`](SECURITY.md) — credential handling and the encrypted vault

## Repo layout

```
src/       daemon + HOS integration layer
scripts/   start, auto-start registration, diagnostics
tests/     end-to-end tier routing test
dashboard/ Orion real-time metrics dashboard (open in browser)
docs/
```

## License

MIT
