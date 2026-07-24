@echo off
rem ---------------------------------------------------------------------------
rem  ONE-TIME SETUP for Whisper Transcriber.
rem  Just double-click this file. It installs everything needed (Python,
rem  ffmpeg, and the Whisper engine) and creates a Desktop shortcut.
rem  No PowerShell or command-line knowledge needed — just double-click.
rem ---------------------------------------------------------------------------
title Whisper Transcriber - Setup
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0Setup.ps1"
echo.
pause
