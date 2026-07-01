<#
.SYNOPSIS
    Signs PowerShell scripts with an Authenticode certificate loaded from a PFX file.

.DESCRIPTION
    Invoke-ScriptSigning consolidates single-file and batch signing into one tool.

    Two target modes:
      - Single file  : -SourcePath points to a .ps1 / .psm1 / .psd1 file.
      - Directory    : -SourcePath points to a folder; use -Recurse for sub-folders.

    Two signing modes:
      - In-place     : files are signed where they are (default).
      - Copy mode    : files are copied from -SourcePath to -DestinationPath first,
                       then signed in the destination tree.

    The certificate must be a valid, unexpired code-signing certificate that includes
    a private key.  Its password is requested interactively when not supplied via
    -CertificatePassword (recommended for interactive use; avoid plain-text passwords
    in scripts or CI pipelines - use a SecureString from a vault instead).

    Compatible with PowerShell 5.1 and later.

.PARAMETER CertificatePath
    Path to the PFX/P12 file that contains the code-signing certificate and private key.

.PARAMETER CertificatePassword
    Password for the PFX file as a SecureString.
    When omitted the user is prompted interactively.

.PARAMETER SourcePath
    Path to the script file or directory to sign.

.PARAMETER DestinationPath
    When specified, switches to Copy mode: files are copied from SourcePath to this
    path before signing.  Must not overlap with SourcePath.

.PARAMETER Recurse
    Search sub-directories when SourcePath is a directory.

.PARAMETER Extensions
    File extensions to process.  Defaults to .ps1, .psm1, .psd1, .exe, .dll.

.PARAMETER ExcludeDirectory
    Directory names to skip during traversal.
    Defaults to: .git  .vs  bin  obj  node_modules

.PARAMETER TimestampServer
    RFC 3161 timestamp server URL.  Enables long-term signature validity after
    certificate expiry (recommended for production).
    Example: http://timestamp.digicert.com

.EXAMPLE
    # Sign a single file in-place (password prompted)
    .\Invoke-ScriptSigning.ps1 -CertificatePath .\pki\code-sign.pfx -SourcePath .\Deploy.ps1

.EXAMPLE
    # Sign all scripts in .\src recursively, writing signed copies to .\out
    .\Invoke-ScriptSigning.ps1 `
        -CertificatePath  .\pki\code-sign.pfx `
        -SourcePath       .\src `
        -DestinationPath  .\out `
        -Recurse

.EXAMPLE
    # Automation: supply password from a SecureString (e.g. from a secrets vault)
    $pwd = ConvertTo-SecureString $env:PFX_PASSWORD -AsPlainText -Force
    .\Invoke-ScriptSigning.ps1 `
        -CertificatePath     .\pki\code-sign.pfx `
        -CertificatePassword $pwd `
        -SourcePath          .\src `
        -Recurse `
        -TimestampServer     http://timestamp.digicert.com

.EXAMPLE
    # Dry run: preview what would be signed without touching any file
    .\Invoke-ScriptSigning.ps1 -CertificatePath .\pki\code-sign.pfx -SourcePath .\src -Recurse -WhatIf
#>
[CmdletBinding(SupportsShouldProcess, DefaultParameterSetName = 'InPlace')]
[Diagnostics.CodeAnalysis.SuppressMessageAttribute("PSUseDeclaredVarsMoreThanAssignment", "", Justification = "Backward compatibility with Powershell 5.1.")]
[Diagnostics.CodeAnalysis.SuppressMessageAttribute("PSAvoidAssignmentToAutomaticVariable", "", Justification = "Backward compatibility with Powershell 5.1.")]
[Diagnostics.CodeAnalysis.SuppressMessageAttribute("PSUseDeclaredVarsMoreThanAssignments", "", Justification = "Backward compatibility with Powershell 5.1.")]
param(
    [Parameter(Mandatory)]
    [string] $CertificatePath,

    [Parameter()]
    [System.Security.SecureString] $CertificatePassword,

    [Parameter(Mandatory)]
    [string] $SourcePath,

    [Parameter(ParameterSetName = 'CopyMode')]
    [string] $DestinationPath,

    [Parameter()]
    [switch] $Recurse,

    [Parameter()]
    [string[]] $Extensions = @('.ps1', '.psm1', '.psd1', '.exe', '.dll'),

    [Parameter()]
    [string[]] $ExcludeDirectory = @('.git', '.vs', 'bin', 'obj', 'node_modules'),

    [Parameter()]
    [string] $TimestampServer
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

# PS 5.1 compatibility: $IsLinux / $IsMacOS / $IsWindows were introduced in PS 6.
# Declare them as constants when absent so the rest of the script can reference
# them unconditionally on any version.
if (-not (Test-Path variable:IsLinux))  { $IsLinux   = $false }
if (-not (Test-Path variable:IsMacOS))  { $IsMacOS   = $false }
if (-not (Test-Path variable:IsWindows)){ $IsWindows  = $true  }

# On non-Windows platforms, ensure the OpenAuthenticode module is available.
if ($IsLinux -or $IsMacOS) {
    $moduleName = 'OpenAuthenticode'
    if (-not (Get-Module -ListAvailable -Name $moduleName)) {
        Write-Output "Installing required module '$moduleName' from PSGallery..."
        Install-Module -Name $moduleName -Scope CurrentUser -Force
    }
}

# ─────────────────────────────────────────────────────────────────────────────
# Internal helpers
# ─────────────────────────────────────────────────────────────────────────────

function Resolve-FullPath {
<#
.SYNOPSIS
    Resolves a path string to its absolute form, throwing a descriptive error on failure.

.PARAMETER Path
    The path string to resolve.

.PARAMETER Label
    A human-readable label for the parameter (used in the error message).

.OUTPUTS
    System.String. The absolute path.
#>
    param(
        [string] $Path,
        [string] $Label
    )
    try { return [IO.Path]::GetFullPath($Path) }
    catch { throw "$Label is not a valid path: '$Path'" }
}

function Import-SigningCertificate {
<#
.SYNOPSIS
    Loads a PFX certificate and validates it for Authenticode code signing.

.DESCRIPTION
    On Windows the certificate is imported into the current user's personal store
    (Cert:\CurrentUser\My) so that Set-AuthenticodeSignature can access the private key.
    On Linux/macOS, Get-PfxCertificate is used instead (requires the OpenAuthenticode module).

    Validation checks performed:
      - Private key is present.
      - Certificate has not expired.
      - Enhanced Key Usage includes the Code Signing OID (1.3.6.1.5.5.7.3.3).

.PARAMETER PfxPath
    Absolute path to the PFX/P12 file.

.PARAMETER Password
    Password for the PFX file as a SecureString.

.OUTPUTS
    System.Security.Cryptography.X509Certificates.X509Certificate2
#>
    [OutputType([System.Security.Cryptography.X509Certificates.X509Certificate2])]
    param(
        [string]                       $PfxPath,
        [System.Security.SecureString] $Password
    )

    try {
        if ($IsLinux -or $IsMacOS) {
            $cert = Get-PfxCertificate `
                -FilePath $PfxPath `
                -Password $Password
        }
        else {
            $cert = Import-PfxCertificate `
                -FilePath          $PfxPath `
                -CertStoreLocation Cert:\CurrentUser\My `
                -Password          $Password
        }
    }
    catch {
        throw "Failed to import PFX '$PfxPath': $($_.Exception.Message)"
    }

    if (-not $cert.HasPrivateKey) {
        throw "Certificate '$($cert.Subject)' does not contain a private key."
    }

    if ($cert.NotAfter -lt (Get-Date)) {
        throw "Certificate '$($cert.Subject)' expired on $($cert.NotAfter.ToString('yyyy-MM-dd'))."
    }

    $codeSignOid = '1.3.6.1.5.5.7.3.3'
    $eku = $cert.Extensions |
        Where-Object { $_ -is [System.Security.Cryptography.X509Certificates.X509EnhancedKeyUsageExtension] }

    if (-not $eku) {
        throw "Certificate '$($cert.Subject)' has no Enhanced Key Usage extension. A code-signing certificate is required."
    }

    $hasCodeSign = $eku.EnhancedKeyUsages | Where-Object { $_.Value -eq $codeSignOid }
    if (-not $hasCodeSign) {
        throw "Certificate '$($cert.Subject)' does not carry the Code Signing EKU (OID $codeSignOid)."
    }

    return $cert
}

function Get-TargetFilesSet {
<#
.SYNOPSIS
    Returns the list of files inside a directory that match the given extensions,
    optionally skipping excluded sub-directories.

.PARAMETER Directory
    Root directory to search.

.PARAMETER Extensions
    Array of file extensions to include (e.g. '.ps1', '.psm1').

.PARAMETER ExcludeDirectory
    Directory names to skip during traversal.

.PARAMETER Recurse
    When present, descends into sub-directories.

.OUTPUTS
    System.Collections.Generic.List[System.IO.FileInfo]
#>
    param(
        [string]   $Directory,
        [string[]] $Extensions,
        [string[]] $ExcludeDirectory,
        [switch]   $Recurse
    )

    $results = New-Object 'System.Collections.Generic.List[System.IO.FileInfo]'

    $items = Get-ChildItem -Path $Directory -File -Recurse:$Recurse.IsPresent
    foreach ($file in $items) {
        if ($Recurse) {
            # Build path segments relative to the root to detect excluded dirs.
            $relative = $file.FullName.Substring($Directory.Length)
            $parts = $relative.Split(
                [char[]]@([IO.Path]::DirectorySeparatorChar, [IO.Path]::AltDirectorySeparatorChar),
                [System.StringSplitOptions]::RemoveEmptyEntries
            )
            # The last element is the filename itself; check intermediate segments only.
            # Note: Select-Object -SkipLast is PS 7+ only; use array slicing instead.
            $dirParts = if ($parts.Count -gt 1) { $parts[0..($parts.Count - 2)] } else { @() }
            if ($dirParts | Where-Object { $ExcludeDirectory -contains $_ }) { continue }
        }

        if ($Extensions -contains $file.Extension) {
            [void] $results.Add($file)
        }
    }

    return , $results
}

function Convert-SignatureResult {
<#
.SYNOPSIS
    Builds a normalised signature-result object for the Linux/macOS code path.

.DESCRIPTION
    On Linux/macOS, Set-OpenAuthenticodeSignature throws on failure and returns
    nothing on success.  This function produces a Status/StatusMessage object
    that mirrors the shape returned by Set-AuthenticodeSignature on Windows,
    allowing Invoke-FileSign to use a single result-checking code path.

.PARAMETER ErrorMessage
    When provided, the result Status is set to 'UnknownError'.
    When omitted (or empty), Status is set to 'Valid'.

.OUTPUTS
    PSCustomObject with Status and StatusMessage properties.
#>
    param(
        [string] $ErrorMessage
    )

    if ($ErrorMessage) {
        return [PSCustomObject]@{
            Status        = 'UnknownError'
            StatusMessage = $ErrorMessage
        }
    }

    return [PSCustomObject]@{
        Status        = 'Valid'
        StatusMessage = 'Signature verified.'
    }
}

function Remove-PowerShellSignatureBlock {
<#
.SYNOPSIS
    Strips an existing Authenticode signature block from a PowerShell script file.

.DESCRIPTION
    PowerShell scripts carry their Authenticode signature as a comment block
    delimited by '# SIG # Begin signature block' / '# SIG # End signature block'
    appended at the end of the file.

    Set-AuthenticodeSignature (Windows) replaces an existing block in place, but
    Set-OpenAuthenticodeSignature (Linux/macOS) appends a *second* block instead
    of replacing the first. Two stacked blocks make the signature invalid.

    To get deterministic behaviour on every platform this helper removes any
    pre-existing block before signing. It is a no-op for non-script files
    (.exe / .dll) and for files that contain no signature block.

    The file's original encoding (UTF-8 with/without BOM, UTF-16 LE/BE) is
    detected from its byte-order mark and preserved when rewriting, so the
    cleaned content hashes identically to the original sans-signature script.

.PARAMETER FilePath
    Absolute path of the file to clean.

.OUTPUTS
    System.Boolean. $true when a block was removed, $false otherwise.
#>
    [CmdletBinding(SupportsShouldProcess)]
    [OutputType([bool])]
    param(
        [string] $FilePath
    )

    $scriptExtensions = @('.ps1', '.psm1', '.psd1')
    if ($scriptExtensions -notcontains [IO.Path]::GetExtension($FilePath)) {
        return $false
    }

    $bytes = [System.IO.File]::ReadAllBytes($FilePath)
    if ($bytes.Length -eq 0) { return $false }

    # Detect the encoding from the byte-order mark so the file is rewritten in a
    # form compatible with the original (a different encoding would change every
    # byte and could break callers that read the script with a fixed encoding).
    if ($bytes.Length -ge 3 -and $bytes[0] -eq 0xEF -and $bytes[1] -eq 0xBB -and $bytes[2] -eq 0xBF) {
        $encoding = New-Object System.Text.UTF8Encoding($true)   # UTF-8 with BOM
    }
    elseif ($bytes.Length -ge 2 -and $bytes[0] -eq 0xFF -and $bytes[1] -eq 0xFE) {
        $encoding = [System.Text.Encoding]::Unicode              # UTF-16 LE
    }
    elseif ($bytes.Length -ge 2 -and $bytes[0] -eq 0xFE -and $bytes[1] -eq 0xFF) {
        $encoding = [System.Text.Encoding]::BigEndianUnicode     # UTF-16 BE
    }
    else {
        $encoding = New-Object System.Text.UTF8Encoding($false)  # UTF-8 no BOM
    }

    $text = $encoding.GetString($bytes)
    # Drop a decoded BOM character if present so it is not duplicated on write.
    if ($text.Length -gt 0 -and $text[0] -eq [char]0xFEFF) {
        $text = $text.Substring(1)
    }

    # The Authenticode signature block always starts at column 0. Anchor the
    # match to the beginning of a line (multiline mode) so an occurrence of the
    # marker embedded mid-line in a string or comment -- such as this script's
    # own comment-based help -- is not mistaken for the real block, which would
    # truncate the script at the wrong place. Taking the first line-anchored
    # match also correctly removes stacked blocks (Set-OpenAuthenticodeSignature
    # appends a second one) from the first real block onward.
    $match = [regex]::Match($text, '^# SIG # Begin signature block', [System.Text.RegularExpressions.RegexOptions]::Multiline)
    if (-not $match.Success) { return $false }
    $idx = $match.Index

    if (-not $PSCmdlet.ShouldProcess($FilePath, 'Remove existing signature block')) {
        return $false
    }

    # Truncate at the marker, drop the blank line(s) that precede it, and
    # terminate the cleaned script with a single trailing newline.
    $clean = $text.Substring(0, $idx).TrimEnd("`r", "`n", ' ', "`t") + "`r`n"

    [System.IO.File]::WriteAllText($FilePath, $clean, $encoding)
    return $true
}

function Invoke-FileSign {
<#
.SYNOPSIS
    Signs a single file with an Authenticode certificate.

.DESCRIPTION
    Dispatches to Set-OpenAuthenticodeSignature (Linux/macOS) or
    Set-AuthenticodeSignature (Windows) and normalises the result.
    Returns $true on success, $false on failure (failure details are
    written via Write-Warning).

    Any pre-existing signature block is stripped first (see
    Remove-PowerShellSignatureBlock) to avoid stacking signature blocks.

.PARAMETER FilePath
    Absolute path of the file to sign.

.PARAMETER Certificate
    A valid code-signing X509Certificate2 with a private key.

.PARAMETER TimestampServer
    Optional RFC 3161 timestamp server URL.

.OUTPUTS
    System.Boolean
#>
    [OutputType([bool])]
    param(
        [string] $FilePath,
        [System.Security.Cryptography.X509Certificates.X509Certificate2] $Certificate,
        [string] $TimestampServer
    )

    # Remove any existing signature block before (re)signing so platforms that
    # append rather than replace do not produce a stacked, invalid signature.
    if (Remove-PowerShellSignatureBlock -FilePath $FilePath) {
        Write-Verbose "  Removed existing signature block from $FilePath"
    }

    if ($IsLinux -or $IsMacOS) {
        $params = @{
            Path          = $FilePath
            Certificate   = $Certificate
            HashAlgorithm = 'SHA256'
        }
        if ($TimestampServer) { $params['TimeStampServer'] = $TimestampServer }
        try {
            Set-OpenAuthenticodeSignature @params
            $result = Convert-SignatureResult
        }
        catch {
            $result = Convert-SignatureResult -ErrorMessage $_.Exception.Message
        }
    }
    else {
        $params = @{
            FilePath      = $FilePath
            Certificate   = $Certificate
            HashAlgorithm = 'SHA256'
        }
        if ($TimestampServer) { $params['TimestampServer'] = $TimestampServer }
        $result = Set-AuthenticodeSignature @params
    }

    if ($result.Status -eq 'Valid') {
        Write-Verbose "  [OK]   $FilePath"
        return $true
    }
    else {
        Write-Warning "[FAIL] $FilePath - $($result.Status): $($result.StatusMessage)"
        return $false
    }
}

function Copy-SourceTree {
<#
.SYNOPSIS
    Copies a file or directory tree to a destination, honouring the exclusion list.

.DESCRIPTION
    When Source is a single file, copies it directly to Destination.
    When Source is a directory, mirrors the tree structure under Destination,
    skipping any directory whose name appears in ExcludeDirectory.

.PARAMETER Source
    Path to the source file or directory.

.PARAMETER Destination
    Path to the destination file or directory.

.PARAMETER ExcludeDirectory
    Directory names to skip during traversal.

.PARAMETER Recurse
    When present, copies sub-directories recursively.
#>
    param(
        [string]   $Source,
        [string]   $Destination,
        [string[]] $ExcludeDirectory,
        [switch]   $Recurse
    )

    Write-Verbose "Copying '$Source' -> '$Destination'"

    if (Test-Path -LiteralPath $Source -PathType Leaf) {
        $destDir = Split-Path $Destination -Parent
        if (-not (Test-Path $destDir)) { New-Item -ItemType Directory -Path $destDir -Force | Out-Null }
        Copy-Item -LiteralPath $Source -Destination $Destination -Force
        return
    }

    if (-not (Test-Path $Destination)) { New-Item -ItemType Directory -Path $Destination -Force | Out-Null }

    Get-ChildItem -Path $Source -Recurse:$Recurse.IsPresent | ForEach-Object {
        $item = $_
        $relative = $item.FullName.Substring($Source.Length).TrimStart(
            [char[]]@([IO.Path]::DirectorySeparatorChar, [IO.Path]::AltDirectorySeparatorChar)
        )

        $parts = $relative.Split(
            [char[]]@([IO.Path]::DirectorySeparatorChar, [IO.Path]::AltDirectorySeparatorChar),
            [System.StringSplitOptions]::RemoveEmptyEntries
        )
        if ($parts | Where-Object { $ExcludeDirectory -contains $_ }) { return }

        $destItem = Join-Path $Destination $relative
        if ($item.PSIsContainer) {
            if (-not (Test-Path $destItem)) { New-Item -ItemType Directory -Path $destItem -Force | Out-Null }
        }
        else {
            Copy-Item -LiteralPath $item.FullName -Destination $destItem -Force
        }
    }
}

# ─────────────────────────────────────────────────────────────────────────────
# Parameter validation
# ─────────────────────────────────────────────────────────────────────────────

$CertificatePath = Resolve-FullPath $CertificatePath '-CertificatePath'
$SourcePath      = Resolve-FullPath $SourcePath      '-SourcePath'

if (-not (Test-Path -LiteralPath $CertificatePath)) {
    throw "Certificate file not found: '$CertificatePath'"
}
if (-not (Test-Path -LiteralPath $SourcePath)) {
    throw "SourcePath not found: '$SourcePath'"
}

$isSingleFile = Test-Path -LiteralPath $SourcePath -PathType Leaf
$isCopyMode   = $PSBoundParameters.ContainsKey('DestinationPath')

if ($isCopyMode) {
    $DestinationPath = Resolve-FullPath $DestinationPath '-DestinationPath'

    if (-not $isSingleFile) {
        $srcNorm = $SourcePath.TrimEnd('\', '/')
        $dstNorm = $DestinationPath.TrimEnd('\', '/')
        if ($dstNorm -eq $srcNorm) {
            throw '-DestinationPath must differ from -SourcePath.'
        }
        $sep = [IO.Path]::DirectorySeparatorChar
        if ($DestinationPath.StartsWith($SourcePath + $sep)) {
            throw "-DestinationPath ('$DestinationPath') is inside -SourcePath ('$SourcePath'). This would cause a copy loop."
        }
    }
}

if ($isSingleFile -and $Recurse) {
    Write-Warning '-Recurse has no effect when -SourcePath is a single file.'
}

# ─────────────────────────────────────────────────────────────────────────────
# Certificate password
# ─────────────────────────────────────────────────────────────────────────────

if (-not $CertificatePassword) {
    $CertificatePassword = Read-Host -Prompt 'Enter PFX certificate password' -AsSecureString
}

# ─────────────────────────────────────────────────────────────────────────────
# Import & validate certificate
# ─────────────────────────────────────────────────────────────────────────────

$cert = Import-SigningCertificate -PfxPath $CertificatePath -Password $CertificatePassword
Write-Verbose "Certificate: $($cert.Subject)  |  expires $($cert.NotAfter.ToString('yyyy-MM-dd'))"

# ─────────────────────────────────────────────────────────────────────────────
# Main flow
# ─────────────────────────────────────────────────────────────────────────────

$successCount = 0
$failCount    = 0

if ($isSingleFile) {
    # ── Single-file path ──────────────────────────────────────────────────────
    if ($isCopyMode) {
        if ($PSCmdlet.ShouldProcess($SourcePath, "Copy to '$DestinationPath'")) {
            Copy-SourceTree -Source $SourcePath -Destination $DestinationPath `
                -ExcludeDirectory $ExcludeDirectory
        }
        $signTarget = $DestinationPath
    }
    else {
        $signTarget = $SourcePath
    }

    if ($PSCmdlet.ShouldProcess($signTarget, 'Set-AuthenticodeSignature')) {
        if (Invoke-FileSign -FilePath $signTarget -Certificate $cert -TimestampServer $TimestampServer) {
            $successCount++
        }
        else {
            $failCount++
        }
    }
}
else {
    # ── Directory path ────────────────────────────────────────────────────────
    if ($isCopyMode) {
        if ($PSCmdlet.ShouldProcess($SourcePath, "Copy to '$DestinationPath'")) {
            Copy-SourceTree -Source $SourcePath -Destination $DestinationPath `
                -ExcludeDirectory $ExcludeDirectory -Recurse:$Recurse
        }
    }

    $signingRoot = if ($isCopyMode) { $DestinationPath } else { $SourcePath }
    $files = Get-TargetFilesSet -Directory $signingRoot -Extensions $Extensions `
        -ExcludeDirectory $ExcludeDirectory -Recurse:$Recurse

    if ($files.Count -eq 0) {
        Write-Warning "No files matching ($($Extensions -join ', ')) found in '$signingRoot'."
        exit 0
    }

    Write-Output "Signing $($files.Count) file(s) in '$signingRoot'..."

    foreach ($file in $files) {
        if ($PSCmdlet.ShouldProcess($file.FullName, 'Set-AuthenticodeSignature')) {
            if (Invoke-FileSign -FilePath $file.FullName -Certificate $cert -TimestampServer $TimestampServer) {
                $successCount++
            }
            else {
                $failCount++
            }
        }
    }
}

# ─────────────────────────────────────────────────────────────────────────────
# Summary
# ─────────────────────────────────────────────────────────────────────────────

Write-Output "Signed: $successCount  |  Failed: $failCount"

if ($failCount -gt 0) { exit 1 }
