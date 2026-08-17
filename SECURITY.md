# Security

## Secrets never live in this repository

All credentials are read from environment variables at runtime:

```python
HUGGINGFACE_TOKEN = os.environ.get("HF_TOKEN", "")
```

Set them at **User scope** so they survive reboot and are visible to the
scheduled task:

```powershell
[Environment]::SetEnvironmentVariable("HF_TOKEN","hf_xxx","User")
```

`.gitignore` excludes `.env` and `*.token`. Setup scripts from the original
deployment that contained inline tokens are excluded entirely — their sanitized
form uses `{{HF_TOKEN}}` placeholders.

## Policy: regenerate, don't store

**Do not back up the HuggingFace token anywhere.** It takes about 90 seconds to
issue a new one, and every stored copy is another place it can leak from. If a
node loses its token, or you suspect exposure, revoke and reissue — do not go
looking for a saved copy.

This applies to any credential that is cheap to regenerate and carries no
irreplaceable state. Reserve encrypted storage for secrets that genuinely cannot
be reissued.

## Encrypted vault (for secrets that *can't* be reissued)

Not needed for API tokens (see the policy above). If you ever hold a secret that
cannot simply be regenerated, use these rather than a plaintext note:

```powershell
.\scripts\create_vault.ps1    # prompts for secrets + passphrase, writes .vault
.\scripts\open_vault.ps1      # prompts for passphrase, prints secrets
```

- **AES-256-CBC**, key derived by **PBKDF2-HMAC-SHA256, 200,000 iterations**
- Random 16-byte salt and IV per vault
- Secrets and passphrase are entered locally via `SecureString`, never echoed,
  never written to disk in plaintext, never transmitted
- The `.vault` file is safe to store in cloud storage; without the passphrase it
  is not readable
- **There is no recovery if the passphrase is lost**

## Rotate anything that has been exposed

A token that has appeared in a chat window, a plaintext file, a screenshot, or a
git commit should be considered compromised — encrypting it afterward does not
un-expose it. Rotate first, then vault the new value.

- HuggingFace: https://huggingface.co/settings/tokens — create a **Fine-grained**
  token with **"Make calls to Inference Providers"** ticked. A Read token
  authenticates but cannot run models (403); a Write token works but can also
  delete your repositories.
- Anthropic: https://console.anthropic.com/settings/keys

If a token ever reaches a git commit, rotating it is the only real fix —
rewriting history does not reliably remove it from clones, forks, or caches.
