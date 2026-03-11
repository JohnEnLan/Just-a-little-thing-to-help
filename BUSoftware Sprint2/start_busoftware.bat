@echo off
setlocal
cd /d "%~dp0"

set "APP_URL=http://127.0.0.1:5000/dashboard"
set "OPEN_BROWSER=1"
if /I "%~1"=="--no-browser" set "OPEN_BROWSER=0"

call :probe_server
if not errorlevel 1 goto :open_browser

call :start_server
if errorlevel 1 goto :startup_failed

for /l %%I in (1,1,20) do (
    timeout /t 1 /nobreak >nul
    call :probe_server
    if not errorlevel 1 goto :open_browser
)

goto :startup_failed

:open_browser
if "%OPEN_BROWSER%"=="1" start "" "%APP_URL%"
exit /b 0

:startup_failed
echo Failed to start Green Campus.
echo Check server.err for details.
pause
exit /b 1

:probe_server
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
    "try { (Invoke-WebRequest -UseBasicParsing '%APP_URL%' -TimeoutSec 2) | Out-Null; exit 0 } catch { exit 1 }"
exit /b %errorlevel%

:start_server
if exist ".venv\Scripts\python.exe" (
    start "Green Campus Server" /min cmd /c ""%CD%\.venv\Scripts\python.exe" run_server.py 1>server.out 2>server.err"
    exit /b 0
)

where py >nul 2>nul
if not errorlevel 1 (
    start "Green Campus Server" /min cmd /c "py -3 run_server.py 1>server.out 2>server.err"
    exit /b 0
)

where python >nul 2>nul
if not errorlevel 1 (
    start "Green Campus Server" /min cmd /c "python run_server.py 1>server.out 2>server.err"
    exit /b 0
)

echo Python was not found.
exit /b 1
