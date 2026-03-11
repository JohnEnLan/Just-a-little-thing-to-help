@echo off
setlocal
cd /d "%~dp0"

powershell -NoProfile -ExecutionPolicy Bypass -Command ^
    "$processIds = Get-NetTCPConnection -LocalPort 5000 -ErrorAction SilentlyContinue | Select-Object -ExpandProperty OwningProcess -Unique; " ^
    "if (-not $processIds) { Write-Host 'Green Campus is not running.'; exit 0 }; " ^
    "foreach ($processId in $processIds) { Stop-Process -Id $processId -Force -ErrorAction SilentlyContinue }; " ^
    "Write-Host 'Green Campus has been stopped.'"

exit /b %errorlevel%
