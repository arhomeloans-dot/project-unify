# Deploying a new node

Repeatable path for each machine in the mesh.

## Prerequisites

- Windows 10/11, Python 3.11+
- Ollama installed and running (`http://127.0.0.1:11434`)
- Optional: HuggingFace token for Tier 3

## 1. Models

```powershell
ollama pull gemma2:9b
ollama pull llama3.1
ollama list          # confirm both present
```

If `/api/generate` returns `llama-server binary not found`, the Ollama install
is incomplete — reinstall it. Pulling models again won't fix it.

## 2. Dependencies

```powershell
pip install requests
```

## 3. Token (optional, Tier 3 only)

```powershell
[Environment]::SetEnvironmentVariable("HF_TOKEN","hf_xxx","User")
```

Must be **User scope** — a session variable won't survive reboot or reach a
scheduled task. Verify with `.\scripts\check_hf.ps1`.

## 4. Start and verify

```powershell
.\scripts\start_daemon.ps1
.\tests\test_tiers.ps1
```

Expect three `SUCCESS` lines with `failover_events: 0`. If Tiers 1–2 fail but
Tier 3 works, Ollama isn't running. If the reverse, check the token.

## 5. Auto-start

```powershell
.\scripts\fix_autostart.ps1
```

Registers an at-logon task with 3 retries. Reboot, log in, re-run
`test_tiers.ps1` — the daemon should already be healthy without manual start.

**Headless nodes:** at-logon won't fire on a machine nobody logs into. That
needs a service account with stored credentials (or NSSM), which is a separate
setup.

## 6. Dashboard

Open `dashboard/orion_dashboard.html` in a browser. It polls
`http://127.0.0.1:11435/metrics` every 3 seconds.

## 7. Calibrate

Follow `TUNING.md`. Do not assume another node's timeouts transfer — GPU
throughput varies widely.

## Wiring the agents

```python
import requests

def route_document(doc_id, task_type, content):
    r = requests.post("http://127.0.0.1:11435/infer", json={
        "doc_id": doc_id, "task_type": task_type, "content": content
    }, timeout=200)
    return r.json()
```

Client timeout must exceed the slowest tier's read timeout plus the full
failover chain, or you'll abort work the daemon is still doing. See
`src/hos_integration.py`.
