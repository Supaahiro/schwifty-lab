# PowerShell Code Signing Toolkit

A self-contained toolkit for signing PowerShell scripts (`.ps1`, `.psm1`, `.psd1`) with an
Authenticode certificate issued by a **local Certificate Authority (CA)**.

---

## Repository layout

```
codesign/
├── code-sign.ps1              # unified signing tool  (start here)
├── README.md                  # this file
└── pki/
    ├── code-sign.cmd          # generates key + CSR + cert + PFX  (run once)
    └── code-sign.conf         # OpenSSL config for the code-signing cert
```

> **Not included:** the local CA itself (`ca.crt` / `ca.key`).
> You must bring your own CA or create one with standard OpenSSL / ADCS commands.

---

## Part 1 — Generating the code-signing certificate

### Prerequisites

| Requirement | Notes |
|---|---|
| [OpenSSL](https://slproweb.com/products/Win32OpenSSL.html) on `PATH` | `openssl version` must work |
| Local CA files | `ca.crt` and `ca.key` copied into the `pki/` folder |

### What the batch file does (4 steps)

```
[1/4]  openssl genrsa        →  code-sign.key   (4096-bit RSA private key)
[2/4]  openssl req           →  code-sign.csr   (certificate signing request)
[3/4]  openssl x509 -req     →  code-sign.crt   (cert signed by your CA, valid 5 years)
[4/4]  openssl pkcs12 -export→  code-sign.pfx   (PFX bundle: cert + key + CA chain)
```

### Running it

1. Copy `ca.crt` and `ca.key` into `pki/`.
2. Open a command prompt and `cd` into `pki/`.
3. Run:

   ```cmd
   code-sign.cmd
   ```

4. When prompted at step 4, **set a strong password** for the PFX file.
   You will need this password every time you run `code-sign.ps1`.

5. Keep the generated files according to this table:

   | File | Keep? | Notes |
   |---|---|---|
   | `code-sign.key` | Yes — **secret** | Never commit; store in a vault |
   | `code-sign.csr` | Optional | Can be discarded after signing |
   | `code-sign.crt` | Yes | The public certificate |
   | `code-sign.pfx` | Yes — **secret** | Used by the signing script |

### What makes this a code-signing certificate?

`code-sign.conf` sets the critical X.509 extensions required by Windows Authenticode:

```ini
keyUsage         = critical, digitalSignature
extendedKeyUsage = critical, codeSigning    # OID 1.3.6.1.5.5.7.3.3
```

Without the `codeSigning` EKU the certificate will be **rejected** by
`Set-AuthenticodeSignature`.

### Making Windows trust your local CA

For the signature status to show **"Valid"** (not "UnknownError") in PowerShell,
the signing CA must be trusted on the target machine:

```powershell
# Run once as Administrator on every machine that will run the signed scripts
Import-Certificate -FilePath .\pki\ca.crt -CertStoreLocation Cert:\LocalMachine\Root
```

---

## Part 2 — Signing scripts with `code-sign.ps1`

### Parameter reference

| Parameter | Type | Required | Description |
|---|---|---|---|
| `-CertificatePath` | string | Yes | Path to the `.pfx` file |
| `-CertificatePassword` | SecureString | No | PFX password; prompted if omitted |
| `-SourcePath` | string | Yes | Script file **or** directory |
| `-DestinationPath` | string | No | Enables Copy mode |
| `-Recurse` | switch | No | Recurse into sub-directories |
| `-Extensions` | string[] | No | Default: `.ps1 .psm1 .psd1` |
| `-ExcludeDirectory` | string[] | No | Default: `.git .vs bin obj node_modules` |
| `-TimestampServer` | string | No | RFC 3161 URL (recommended) |

Supports `-WhatIf` and `-Verbose` (standard PowerShell common parameters).

### Examples

```powershell
# Sign a single script in-place (password prompted)
.\code-sign.ps1 `
    -CertificatePath .\pki\code-sign.pfx `
    -SourcePath      .\Deploy.ps1
```

```powershell
# Sign all scripts in .\src recursively, writing signed copies to .\out
.\code-sign.ps1 `
    -CertificatePath .\pki\code-sign.pfx `
    -SourcePath      .\src `
    -DestinationPath .\out `
    -Recurse
```

```powershell
# Add a timestamp so signatures survive certificate expiry (production recommended)
.\code-sign.ps1 `
    -CertificatePath .\pki\code-sign.pfx `
    -SourcePath      .\src `
    -Recurse `
    -TimestampServer http://timestamp.digicert.com
```

```powershell
# Automation: password from an environment variable (CI/CD)
$pwd = ConvertTo-SecureString $env:PFX_PASSWORD -AsPlainText -Force
.\code-sign.ps1 `
    -CertificatePath     .\pki\code-sign.pfx `
    -CertificatePassword $pwd `
    -SourcePath          .\src `
    -Recurse
```

```powershell
# Dry run: see what would be signed without modifying any file
.\code-sign.ps1 `
    -CertificatePath .\pki\code-sign.pfx `
    -SourcePath      .\src `
    -Recurse `
    -WhatIf
```

### Verifying a signature

```powershell
Get-AuthenticodeSignature .\Deploy.ps1 | Select-Object Status, StatusMessage, SignerCertificate
```

---

## Security considerations

### PFX file and password

- The PFX file contains the private key and must be treated like a password.
  **Never commit it to source control.**  Add `*.pfx` and `*.key` to `.gitignore`.
- Always set a strong PFX export password.  Weak passwords make the private key
  trivially recoverable from the `.pfx` file.
- In CI/CD pipelines, inject the PFX as a base64-encoded secret and decode it at
  runtime; avoid writing the raw file to disk any longer than necessary.

### Certificate store import

`code-sign.ps1` imports the certificate into `Cert:\CurrentUser\My`.
This makes the private key available to any process running as the same user.
On shared machines consider:
- Using a dedicated service account for signing.
- Removing the certificate from the store after signing (`Remove-Item Cert:\CurrentUser\My\<thumbprint>`).

### Timestamp server

Without a timestamp, a signature becomes **untrusted the moment the certificate
expires**.  Always use `-TimestampServer` in production to get an RFC 3161
counter-signature that embeds the signing time independently of certificate validity.

### Execution policy

Signing a script does **not** bypass execution policy; it satisfies the
`AllSigned` or `RemoteSigned` policies.  The CA must still be trusted in
`Cert:\LocalMachine\Root` for the signature to be accepted.

### Key length and algorithm

The toolkit uses 4096-bit RSA keys and SHA-256 hashing, which meet current
best-practice minimums.  Avoid MD5 or SHA-1 — they are rejected by modern
Windows versions for Authenticode.
