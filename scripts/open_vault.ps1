<# Decrypts project-unify-secrets.vault. Passphrase is never echoed or stored. #>
$ErrorActionPreference = "Stop"
$InFile = Join-Path $PSScriptRoot "project-unify-secrets.vault"
if (-not (Test-Path $InFile)) { Write-Host "No vault found at $InFile"; exit 1 }

function Read-Secret([string]$Label) {
    $sec = Read-Host -Prompt $Label -AsSecureString
    $bstr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($sec)
    try   { [Runtime.InteropServices.Marshal]::PtrToStringBSTR($bstr) }
    finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr) }
}

$lines = Get-Content $InFile | Where-Object { $_ -notmatch '^-----|^Cipher:|^KDF:|^Layout:|^Created:|^Decrypt|^\s*$' }
$raw   = [Convert]::FromBase64String(($lines -join ""))

$salt = $raw[0..15]; $iv = $raw[16..31]; $cipher = $raw[32..($raw.Length-1)]
$pass = Read-Secret "Passphrase"

try {
    $kdf = [System.Security.Cryptography.Rfc2898DeriveBytes]::new(
               $pass, $salt, 200000, [System.Security.Cryptography.HashAlgorithmName]::SHA256)
    $aes = [System.Security.Cryptography.Aes]::Create()
    $aes.KeySize = 256; $aes.Mode = "CBC"; $aes.Padding = "PKCS7"
    $aes.Key = $kdf.GetBytes(32); $aes.IV = $iv
    $plain = $aes.CreateDecryptor().TransformFinalBlock($cipher, 0, $cipher.Length)
    Write-Host ""
    Write-Host ([Text.Encoding]::UTF8.GetString($plain))
} catch {
    Write-Host ""
    Write-Host "Decryption failed - wrong passphrase or corrupted file."
    exit 1
}
