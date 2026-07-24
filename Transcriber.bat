@echo off
rem ---------------------------------------------------------------------------
rem  Double-click launcher for the Whisper Transcriber GUI.
rem  Uses pythonw.exe (no console window). Falls back to whatever is on PATH.
rem ---------------------------------------------------------------------------
set "PYW="
for /d %%D in ("%LOCALAPPDATA%\Programs\Python\Python3*") do (
    if exist "%%D\pythonw.exe" if not defined PYW set "PYW=%%D\pythonw.exe"
)
if not defined PYW (
    where pythonw >nul 2>&1
    if not errorlevel 1 set "PYW=pythonw"
)

if not defined PYW (
    echo.
    echo   Whisper Transcriber can't find Python on this PC.
    echo.
    echo   This usually means the one-time setup didn't finish successfully.
    echo   Try running Setup.bat ^(or the installer^) again, or install Python
    echo   manually from python.org, then try again.
    echo.
    pause
    exit /b 1
)

start "" "%PYW%" "%~dp0transcriber.pyw"
