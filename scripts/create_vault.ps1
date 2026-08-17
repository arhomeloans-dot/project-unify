<#
  Creates an AES-256 encrypted secrets vault.
  You type the secrets and the passphrase locally. Neither is ever transmitted,
  logged, or written to disk in plaintext. Only the encrypted .vault file is
  safe to upload to Google Drive or anywhere else.
#>

$ErrorActionPreference = "Stop"
$OutFile = Join-Path $PSScriptRoot "project-unify-secrets.vault"

Write-Host "========================================================"
Write-Host " PROJECT UNIFY - CREATE ENCRYPTED SECRETS VAULT"
Write-Host "========================================================"
Write-Host ""
Write-Host "Nothing you type here is shown on screen or sent anywhere."
Write-Host "Press Enter to skip any secret you don't have."
Write-Host ""

function Read-Secret([string]$Label) {
    $sec = Read-Host -Prompt $Label -AsSecureString
    $bstr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($sec)
    try   { [Runtime.InteropServices.Marshal]::PtrToStringBSTR($bstr) }
    finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr) }
}

$hf   = Read-Secret "HF_TOKEN          "
$ant  = Read-Secret "ANTHROPIC_API_KEY "
$note = Read-Host   "Notes (optional, not secret)"

$payload = [ordered]@{
    created           = (Get-Date).ToString("o")
    machine           = $env:COMPUTERNAME
    HF_TOKEN          = $hf
    ANTHROPIC_API_KEY = $ant
    notes             = $note
} | ConvertTo-Json

Write-Host ""
Write-Host "Choose a passphrase. Write it down somewhere safe -"
Write-Host "there is no recovery if you lose it."
Write-Host ""
$p1 = Read-Secret "Passphrase        "
$p2 = Read-Secret "Confirm passphrase"
if ($p1 -ne $p2)      { Write-Host ""; Write-Host "Passphrases do not match. Nothing written."; exit 1 }
if ($p1.Length -lt 12){ Write-Host ""; Write-Host "Use at least 12 characters. Nothing written."; exit 1 }

# PBKDF2-SHA256 (200k iterations) -> AES-256-CBC
$salt = [byte[]]::new(16); [System.Security.Cryptography.RandomNumberGenerator]::Fill($salt)
$kdf  = [System.Security.Cryptography.Rfc2898DeriveBytes]::new(
            $p1, $salt, 200000, [System.Security.Cryptography.HashAlgorithmName]::SHA256)
$key  = $kdf.GetBytes(32)

$aes = [System.Security.Cryptography.Aes]::Create()
$aes.KeySize = 256; $aes.Mode = "CBC"; $aes.Padding = "PKCS7"
$aes.Key = $key; $aes.GenerateIV()

$plain  = [Text.Encoding]::UTF8.GetBytes($payload)
$cipher = $aes.CreateEncryptor().TransformFinalBlock($plain, 0, $plain.Length)

# wipe key material from memory
[Array]::Clear($key,0,$key.Length); [Array]::Clear($plain,0,$plain.Length)
$aes.Dispose(); $kdf.Dispose()

$blob = [Convert]::ToBase64String($salt + $aes.IV + $cipher)

@"
-----BEGIN PROJECT UNIFY VAULT-----
Cipher: AES-256-CBC
KDF: PBKDF2-HMAC-SHA256, 200000 iterations
Layout: base64( salt[16] || iv[16] || ciphertext )
Created: $((Get-Date).ToString("o"))
Decrypt with: open_vault.ps1

$blob
-----END PROJECT UNIFY VAULT-----
"@ | Set-Content -Path $OutFile -Encoding UTF8

Write-Host ""
Write-Host "========================================================"
Write-Host "VAULT CREATED"
Write-Host "========================================================"
Write-Host "  $OutFile"
Write-Host ""
Write-Host "This file is safe to store in Google Drive."
Write-Host "Without the passphrase it is unreadable."
