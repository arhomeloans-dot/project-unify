# Scripts

| Script | Purpose |
|---|---|
| `start_daemon.ps1` | Frees port 11435, launches the daemon detached, waits for `/health` |
| `fix_autostart.ps1` | Registers the at-logon scheduled task with retry |
| `check_hf.ps1` | Tier 3 diagnostic: token scope, DNS, HTTPS, auth |
| `find_hf_models.ps1` | Lists model IDs your token can actually reach |
| `create_vault.ps1` | Creates the AES-256 encrypted secrets vault |
| `open_vault.ps1` | Decrypts the vault |
