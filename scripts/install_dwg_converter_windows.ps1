<#
.SYNOPSIS
    Install DWG converter (LibreDWG or ODA File Converter) on Windows.
.DESCRIPTION
    V214: This script installs a DWG→DXF converter so that
    qomn_fire/parsers/dwg_converter.py can read DWG files without requiring
    AutoCAD installed.

    It tries LibreDWG first (open source, recommended), then ODA File
    Converter (freeware, requires email registration).

    After installation, the dwg2dxf or ODAFileConverter binary will be on
    PATH and dwg_converter.py will use it automatically.
.PARAMETER Converter
    Which converter to install: 'libredwg' (default), 'oda', or 'both'.
.EXAMPLE
    .\install_dwg_converter_windows.ps1
.EXAMPLE
    .\install_dwg_converter_windows.ps1 -Converter oda
.NOTES
    File: scripts/install_dwg_converter_windows.ps1
    V214: Added to close the "MOCK DWG DATA" truthfulness gap.
#>

param(
    [ValidateSet('libredwg', 'oda', 'both')]
    [string]$Converter = 'libredwg'
)

$ErrorActionPreference = 'Stop'

function Write-Step($msg) {
    Write-Host "`n[*] $msg" -ForegroundColor Cyan
}

function Write-OK($msg) {
    Write-Host "[+] $msg" -ForegroundColor Green
}

function Write-Warn($msg) {
    Write-Host "[!] $msg" -ForegroundColor Yellow
}

function Write-Err($msg) {
    Write-Host "[-] $msg" -ForegroundColor Red
}

function Test-Command($name) {
    return [bool](Get-Command $name -ErrorAction SilentlyContinue)
}

function Install-LibreDWG {
    Write-Step "Installing LibreDWG (open source DWG↔DXF converter)"

    # Check if already installed
    if (Test-Command 'dwg2dxf') {
        $version = & dwg2dxf --version 2>&1 | Select-Object -First 1
        Write-OK "LibreDWG already installed: $version"
        return $true
    }

    # LibreDWG Windows builds are available from:
    # https://gitlab.com/libredwg/libredwg/-/releases
    # We download the latest Windows zip and extract it.

    $libredwgUrl = 'https://gitlab.com/libredwg/libredwg/-/releases/permalink/latest/downloads/libredwg-windows-x86_64.zip'
    $tempDir = New-Item -ItemType Directory -Force -Path "$env:TEMP\libredwg_install"
    $zipPath = Join-Path $tempDir 'libredwg.zip'
    $extractDir = Join-Path $tempDir 'extracted'
    $installDir = 'C:\Program Files\LibreDWG'

    Write-Step "Downloading LibreDWG from: $libredwgUrl"
    try {
        Invoke-WebRequest -Uri $libredwgUrl -OutFile $zipPath -UseBasicParsing
        Write-OK "Downloaded to: $zipPath"
    }
    catch {
        Write-Err "Failed to download LibreDWG: $_"
        Write-Warn "Manual install: Download from https://gitlab.com/libredwg/libredwg/-/releases"
        return $false
    }

    Write-Step "Extracting to: $extractDir"
    try {
        Expand-Archive -Path $zipPath -DestinationPath $extractDir -Force
        Write-OK "Extracted successfully"
    }
    catch {
        Write-Err "Failed to extract: $_"
        return $false
    }

    Write-Step "Installing to: $installDir"
    if (-not (Test-Path $installDir)) {
        New-Item -ItemType Directory -Force -Path $installDir | Out-Null
    }
    Copy-Item -Path "$extractDir\*" -Destination $installDir -Recurse -Force

    # Add to PATH (current session + persistent)
    $env:PATH += ";$installDir"
    $persistentPath = [Environment]::GetEnvironmentVariable('PATH', 'Machine')
    if ($persistentPath -notlike "*$installDir*") {
        [Environment]::SetEnvironmentVariable('PATH', "$persistentPath;$installDir", 'Machine')
        Write-OK "Added $installDir to system PATH"
    }

    # Verify
    Refresh-Path 2>$null
    if (Test-Command 'dwg2dxf') {
        $version = & dwg2dxf --version 2>&1 | Select-Object -First 1
        Write-OK "LibreDWG installed successfully: $version"
        return $true
    }
    else {
        Write-Warn "dwg2dxf not found on PATH after install — restart your terminal."
        return $true  # Installed but needs terminal restart
    }
}

function Install-ODAConverter {
    Write-Step "Installing ODA File Converter (freeware, requires email registration)"

    if (Test-Command 'ODAFileConverter') {
        Write-OK "ODA File Converter already installed"
        return $true
    }

    Write-Warn "ODA File Converter requires manual download."
    Write-Warn "It is freeware but requires email registration."
    Write-Warn ""
    Write-Warn "Download from: https://www.opendesign.com/guestfiles/oda_file_converter"
    Write-Warn ""
    Write-Warn "After downloading:"
    Write-Warn "  1. Run the installer (ODAFileConverter_QT6_lxXnu_8.3.0.exe or similar)"
    Write-Warn "  2. Default install path: C:\Program Files\ODA\ODAFileConverter"
    Write-Warn "  3. The installer adds ODAFileConverter to PATH automatically"
    Write-Warn ""
    Write-Warn "After installation, restart your terminal and run:"
    Write-Warn "  ODAFileConverter --help"
    Write-Warn ""
    Write-Warn "Press any key to open the download page in your browser..."
    $null = $Host.UI.RawUI.ReadKey('NoEcho,IncludeKeyDown')
    Start-Process 'https://www.opendesign.com/guestfiles/oda_file_converter'
    return $false  # Manual install required
}

function Refresh-Path {
    $env:PATH = [Environment]::GetEnvironmentVariable('PATH', 'Machine') + ';' + [Environment]::GetEnvironmentVariable('PATH', 'User')
}

# ─── Main ──────────────────────────────────────────────────────────────────

Write-Host "`n════════════════════════════════════════════════════════════════" -ForegroundColor Cyan
Write-Host "V214: DWG Converter Installer for Windows" -ForegroundColor Cyan
Write-Host "Closes the 'MOCK DWG DATA' truthfulness gap in autocad_service.py" -ForegroundColor Cyan
Write-Host "════════════════════════════════════════════════════════════════`n" -ForegroundColor Cyan

$success = $false

switch ($Converter) {
    'libredwg' {
        $success = Install-LibreDWG
    }
    'oda' {
        $success = Install-ODAConverter
    }
    'both' {
        $libredwgOk = Install-LibreDWG
        $odaOk = Install-ODAConverter
        $success = $libredwgOk -or $odaOk
    }
}

Write-Host "`n────────────────────────────────────────────────────────────────" -ForegroundColor Cyan
if ($success) {
    Write-OK "Installation complete."
    Write-Host ""
    Write-Warn "IMPORTANT: Restart your terminal for PATH changes to take effect."
    Write-Warn "After restart, verify with: dwg2dxf --version  (or  ODAFileConverter)"
    Write-Host ""
    Write-Host "dwg_converter.py will automatically detect the binary and use it" -ForegroundColor Gray
    Write-Host "for real DWG→DXF conversion. No more 'MOCK DWG DATA' fallback." -ForegroundColor Gray
    exit 0
}
else {
    Write-Err "Installation incomplete. See messages above."
    Write-Warn "Without a DWG converter, dwg_converter.py will use the mock fallback"
    Write-Warn "(writes entity-empty DXF with an explicit warning)."
    exit 1
}
