@echo off
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0stop_busoftware.ps1"
if errorlevel 1 (
    echo.
    pause
)
