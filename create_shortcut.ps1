# ---------------------------------------------------------------------------
#  Creates a "Transcriber" shortcut on your Desktop that launches the app.
#  Run this once:  right-click -> Run with PowerShell   (or run from a terminal)
# ---------------------------------------------------------------------------
$projectDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
$batPath    = Join-Path $projectDir "Transcriber.bat"
$desktop    = [Environment]::GetFolderPath("Desktop")
$lnkPath    = Join-Path $desktop "Transcriber.lnk"

$shell = New-Object -ComObject WScript.Shell
$sc = $shell.CreateShortcut($lnkPath)
$sc.TargetPath       = $batPath
$sc.WorkingDirectory = $projectDir
$sc.WindowStyle      = 7   # minimized (the .bat window flashes only briefly)
$sc.Description       = "Whisper Transcriber"
$sc.IconLocation     = "$env:SystemRoot\System32\imageres.dll,264"  # microphone
$sc.Save()

Write-Host "Created shortcut:" $lnkPath
