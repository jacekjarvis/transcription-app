# ---------------------------------------------------------------------------
#  Whisper Transcriber — prerequisite installer, run automatically by the
#  Inno Setup installer wizard during install (see WhisperTranscriber.iss).
#  Installs Python, ffmpeg, and the Whisper engine. Safe to re-run -- it
#  skips anything already installed.
#
#  (This is the installer-wizard counterpart to Setup.ps1, which is used by
#  the plain double-click/no-installer route. This version doesn't create
#  shortcuts itself -- the Inno wizard's own [Icons] section handles that.)
# ---------------------------------------------------------------------------

$ErrorActionPreference = "Stop"

function Write-Step($msg) { Write-Host "`n==> $msg" -ForegroundColor Cyan }
function Write-Ok($msg)   { Write-Host "    OK: $msg" -ForegroundColor Green }
function Write-Warn2($msg) { Write-Host "    ! $msg" -ForegroundColor Yellow }

Write-Host "Whisper Transcriber - installing prerequisites" -ForegroundColor White
Write-Host "This installs Python, ffmpeg, and the Whisper transcription engine."
Write-Host "All free and local -- nothing is uploaded anywhere."

# --- 1. Check winget -------------------------------------------------------
Write-Step "Checking for Windows Package Manager (winget)..."
$winget = Get-Command winget -ErrorAction SilentlyContinue
if (-not $winget) {
    Write-Warn2 "winget was not found."
    Write-Host ""
    Write-Host "winget comes with Windows 10/11 via the 'App Installer'."
    Write-Host "Open the Microsoft Store, search for 'App Installer', install/update it,"
    Write-Host "then run this installer again."
    exit 1
}
Write-Ok "winget is available."

# --- 2. Python ---------------------------------------------------------------
Write-Step "Checking for Python..."
function Find-PythonExe {
    # Windows ships a "python.exe" App Execution Alias stub under WindowsApps
    # by default on most PCs (so typing `python` with nothing installed opens
    # the Store instead of erroring). It resolves via Get-Command / PATH even
    # when no real Python is installed, so it must be explicitly excluded --
    # otherwise a fresh PC with no real Python looks like it already has one.
    $cmd = Get-Command python -ErrorAction SilentlyContinue
    if ($cmd -and $cmd.Source -notlike "*\WindowsApps\*") { return $cmd.Source }
    $candidates = Get-ChildItem "$env:LocalAppData\Programs\Python\Python3*\python.exe" `
        -ErrorAction SilentlyContinue | Sort-Object FullName -Descending
    if ($candidates) { return $candidates[0].FullName }
    return $null
}

$pythonExe = Find-PythonExe
if (-not $pythonExe) {
    Write-Host "    Python not found -- installing Python 3.12 (silent, per-user install)..."
    winget install --id Python.Python.3.12 -e --silent `
        --accept-package-agreements --accept-source-agreements
    $pythonExe = Find-PythonExe
}
if (-not $pythonExe) {
    Write-Warn2 "Could not locate Python after installation. Please install it manually from python.org and re-run this installer."
    exit 1
}
Write-Ok "Python: $pythonExe"

# --- 3. ffmpeg / ffprobe ------------------------------------------------------
Write-Step "Checking for ffmpeg..."
function Find-FfprobeExe {
    $cmd = Get-Command ffprobe -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }
    $candidates = Get-ChildItem "$env:LocalAppData\Microsoft\WinGet\Packages\Gyan.FFmpeg_*\ffmpeg-*\bin\ffprobe.exe" `
        -ErrorAction SilentlyContinue | Sort-Object FullName -Descending
    if ($candidates) { return $candidates[0].FullName }
    return $null
}

$ffprobeExe = Find-FfprobeExe
if (-not $ffprobeExe) {
    Write-Host "    ffmpeg not found -- installing (silent)..."
    winget install --id Gyan.FFmpeg -e --silent `
        --accept-package-agreements --accept-source-agreements
    $ffprobeExe = Find-FfprobeExe
}
if (-not $ffprobeExe) {
    Write-Warn2 "Could not locate ffmpeg after installation. The app will still try to find it itself when it starts."
} else {
    Write-Ok "ffmpeg: $ffprobeExe"
}

# --- 4. Whisper (pip) --------------------------------------------------------
Write-Step "Installing the Whisper transcription engine (this can take a few minutes)..."
& $pythonExe -m pip install --upgrade pip --quiet
& $pythonExe -m pip install --upgrade openai-whisper
if ($LASTEXITCODE -ne 0) {
    Write-Warn2 "pip install openai-whisper reported an error (see above)."
    exit 1
}
Write-Ok "Whisper engine installed."

# --- 5. Final verification ---------------------------------------------------
# Confirms the things Transcriber.bat / transcriber.pyw actually need exist,
# rather than trusting that each step above "succeeding" really means the
# real tool is usable (e.g. a false-positive Python detection would let
# earlier steps report OK while nothing real was actually installed).
Write-Step "Verifying the install..."
$problems = @()

$pythonwExe = Join-Path (Split-Path $pythonExe -Parent) "pythonw.exe"
if (-not (Test-Path $pythonwExe)) {
    $problems += "pythonw.exe not found at $pythonwExe"
}

$whisperExe = Join-Path (Split-Path $pythonExe -Parent) "Scripts\whisper.exe"
if (-not (Test-Path $whisperExe)) {
    $problems += "whisper.exe not found at $whisperExe"
}

if ($problems.Count -gt 0) {
    Write-Warn2 "Verification failed:"
    foreach ($p in $problems) { Write-Warn2 "  - $p" }
    exit 1
}

Write-Ok "pythonw.exe and whisper.exe both verified present."
Write-Host ""
Write-Host "All prerequisites are installed." -ForegroundColor Green
