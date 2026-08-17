# Changelog

## [1.0.0] — 2026-08-17

First fully operational release. All three tiers verified end-to-end, surviving
reboot with auto-start.

### Changed — tier restructure
- Tier 2 is now **local Llama3.1** (was HuggingFace); Tier 3 is **HuggingFace**
  (was Claude API). Removes the paid-API dependency from the mid tier.

### Fixed
- **Tier 3 endpoint.** `api-inference.huggingface.co` was retired by HuggingFace
  and no longer resolves. Migrated to `router.huggingface.co/v1/chat/completions`
  with the OpenAI-compatible message schema. This was the root cause of every
  Tier 3 failure since the project began.
- **Metrics keys** still referenced `tier2_kimi` / `tier3_claude`, raising
  `KeyError` on routing. Now match the live tier names.
- **Tier 1 failover target** pointed at `tier2_kimi` instead of `tier2_llama`.
- **Single-threaded server** died on client disconnect
  (`ConnectionAbortedError`). Now `ThreadingHTTPServer` with connection-abort
  handling.
- **CORS** headers added so the dashboard can read `/metrics` from `file://`.
- **Dashboard** tier keys and labels updated; `localhost` → `127.0.0.1`.
- **Auto-start** changed from at-startup to at-logon, so the task inherits
  User-scope environment variables. Added 3× retry.

### Timeouts
- Tier 1: 30s → 60s → **90s** (cold start measured 72s)
- Tier 2: **120s**
- Tier 3: 30s → **60s**

### Security
- Setup scripts containing live API tokens excluded from this repository.
  Tokens are read from environment variables only. See `.env.example`.
