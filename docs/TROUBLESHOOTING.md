# Troubleshooting

Field notes from the initial deployment. Every entry below cost real debugging
time — read the symptom table before diagnosing from scratch.

## Symptom → cause quick table

| Symptom | Almost certainly |
|---|---|
| Tier 3 fails in **0 ms**, every time | Dead endpoint or bad hostname — not a timeout (see #1) |
| PowerShell: "actively refused it", but daemon is up | IPv6 `localhost` vs IPv4 bind (see #2) |
| Daemon "not running" after you closed the window | Not launched detached (see #3) |
| Works interactively, Tier 3 breaks after reboot | Token set per-session, not User-scope (see #4) |
| Code edited but old behavior persists | Stale `__pycache__`, or old process still holding the port (see #5) |
| Tier 1 times out then succeeds on Tier 2 | Timeout ceiling too close to real latency (see #6) |
| Dashboard gauges all read zero | Tier-name mismatch or CORS (see #7) |
| Tier 3 returns **403** in ~300 ms | Token is the wrong *type* — lacks Inference permission (see #8) |

---

## 1. Tier 3 fails instantly at 0 ms

**Symptom**
```
Tier 3 (Kimi) failed (exception: HTTPSConnectionPool(host='api-inference.huggingfac...
latency=0.0ms | status=500
```

**Cause.** HuggingFace retired `api-inference.huggingface.co`. The hostname no
longer resolves at all, so the request died at DNS before any network I/O.

**The tell:** *0 ms is not a timeout.* A timeout burns its full read window
(30s, 60s). A 0 ms failure means the request never left the machine — DNS,
hostname, or malformed URL. Anything that fails instantly is local.

This one was misdiagnosed repeatedly as an auth problem. It cost an Anthropic
API key purchase and two token re-issues before anyone checked DNS.

**Fix.** Inference now goes through the Inference Providers router with an
OpenAI-compatible schema:

```python
HUGGINGFACE_API_URL = "https://router.huggingface.co/v1/chat/completions"

payload = {
    "model": "moonshotai/Kimi-K3",
    "messages": [{"role": "user", "content": prompt}],
    "max_tokens": 512,
}
# response: data["choices"][0]["message"]["content"]
```

The old `{"inputs": prompt}` shape and `[0]["generated_text"]` parse are both dead.

**Verify:** `.\scripts\check_hf.ps1` then `.\scripts\find_hf_models.ps1`. The
second lists every model your token can actually reach — model IDs must match
exactly.

---

## 2. "No connection could be made because the target machine actively refused it"

**Symptom.** The daemon is provably running and healthy, but PowerShell can't
reach it. Python's `requests` to the same URL works fine.

**Cause.** The daemon binds `0.0.0.0` — IPv4 only. PowerShell resolves
`localhost` to IPv6 `::1` first and gets refused. `requests` silently falls back
to IPv4; `Invoke-RestMethod` does not.

**Fix.** Use `127.0.0.1`, never `localhost`, in any PowerShell client:

```powershell
Invoke-RestMethod -Uri "http://127.0.0.1:11435/health"
```

This bit us for hours and masqueraded as "the daemon keeps crashing."

---

## 3. Daemon dies when you close the terminal

**Cause.** Run in the foreground, it's a child of that shell.

**Fix.** `.\scripts\start_daemon.ps1` launches it detached via `pythonw.exe`,
frees port 11435 first, and polls `/health` until it confirms the daemon is up.

Related: the original server was single-threaded `HTTPServer`, so one client
disconnecting mid-request raised `ConnectionAbortedError` and wedged it. Now
`ThreadingHTTPServer` with `handle_one_request` swallowing
`ConnectionAborted/Reset/BrokenPipe`.

---

## 4. Tier 3 works now, breaks after reboot

**Cause.** `$env:HF_TOKEN = "..."` lives only in that PowerShell session. A
detached or scheduled process never sees it.

**Fix.** Set it at User scope:

```powershell
[Environment]::SetEnvironmentVariable("HF_TOKEN","hf_xxx","User")
```

Also: an **at-startup** scheduled task fires before login and won't inherit
User-scope variables (and often won't run at all without stored credentials).
`.\scripts\fix_autostart.ps1` registers it **at logon** instead.

---

## 5. Code changes don't take effect

**Cause.** Python caches compiled bytecode, and killing by process name can miss
the instance holding the port — the new process then dies on bind while the old
one keeps serving stale code.

**Fix.** `start_daemon.ps1` handles both: clears `__pycache__`, and checks
`Get-NetTCPConnection -LocalPort 11435` to kill whatever actually owns the port.

**The tell:** if the log shows no new startup banner after a restart, the new
process died on bind. The old one is still running.

---

## 6. Tier 1 times out, then Tier 2 succeeds

Not a bug — a mis-set ceiling. If Tier 1 finishes at 52s against a 60s timeout,
any slow or cold run blows through, wastes the full 60s, *then* starts over on
Tier 2. Cold start after reboot measured **72s** vs 37s warm.

Set each timeout ~1.75× observed warm latency. Current values in
`TIMEOUT_CONFIG`: Tier 1 90s, Tier 2 120s, Tier 3 60s. See `TUNING.md`.

---

## 7. Orion dashboard shows all zeros

Two independent causes:

1. **Tier-name mismatch.** The dashboard's keys must match
   `routing_breakdown` exactly: `tier1_local`, `tier2_llama`, `tier3_kimi`,
   `tier3_glm`. Renaming tiers in the daemon without updating the dashboard
   yields silent zeros.
2. **CORS.** Opened from `file://`, the browser blocks the fetch unless the
   daemon sends `Access-Control-Allow-Origin`. It now does, on every response,
   plus an `OPTIONS` preflight handler.

---

## General debugging principles

- **0 ms = local failure. Full-timeout = remote failure.** The latency number
  tells you which side of the network to look at before you read the message.
- **Test from the same machine and runtime as the client.** A sandbox or
  container on a different host cannot reach `127.0.0.1:11435` — a connection
  error there says nothing about the daemon's health.
- **Verify identifiers against the live API, don't assume.** `Kimi-K3` and
  `GLM-5.2` were assumed wrong and turned out correct; the endpoint was wrong.
  `find_hf_models.ps1` exists so nobody guesses again.

---

## 8. Tier 3 returns HTTP 403 in ~300 ms

**Symptom**
```
Tier 3 (Kimi) failed (http_error: {"error":"This authentication method does not
have sufficient permissions to call Inference Providers on behalf of user ...
latency=315ms | status=403
```

**Cause.** The token is valid but was created with the wrong *type*. A
HuggingFace **Read** token can browse and download models but is not permitted
to **run** them through Inference Providers.

**The tell:** a fast, non-zero latency with a 4xx status means you reached the
provider and were refused — an authorization problem, not a connectivity or
endpoint problem. Contrast with #1 (0 ms = never left the machine).

**Fix.** Create a **Fine-grained** token with this permission ticked:

> ☑ Make calls to Inference Providers

A **Write** token also works but grants far more than needed (it can delete
repositories). Prefer fine-grained — least privilege.

**Important:** token permissions **cannot be inspected after creation** —
HuggingFace displays the value once and never reveals its scopes again. If a
node throws 403s, do not try to audit the existing token. Issue a new
fine-grained one and swap it in.

**Verify:** `.\scripts\check_hf.ps1` will still report the token as valid (it
authenticates fine — `whoami` works with any token type). Only an actual
inference call exposes the missing permission. Use `.\tests\test_tiers.ps1`.
