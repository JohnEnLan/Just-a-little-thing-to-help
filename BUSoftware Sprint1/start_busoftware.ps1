$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$pythonExe = Join-Path $projectRoot ".venv\Scripts\python.exe"
$runnerScript = Join-Path $projectRoot "run_server.py"
$pidFile = Join-Path $projectRoot "server.pid"
$stdoutFile = Join-Path $projectRoot "server.out"
$stderrFile = Join-Path $projectRoot "server.err"
$port = 5050
$url = "http://127.0.0.1:$port/dashboard"

function Get-ManagedProcesses {
    param([string]$RunnerPath)

    $runnerPattern = [regex]::Escape($RunnerPath)
    Get-CimInstance Win32_Process -Filter "Name = 'python.exe'" -ErrorAction SilentlyContinue |
        Where-Object { $_.CommandLine -match $runnerPattern }
}

if (-not (Test-Path $pythonExe)) {
    Write-Host "Missing Python executable: $pythonExe"
    exit 1
}

if (-not (Test-Path $runnerScript)) {
    Write-Host "Missing runner script: $runnerScript"
    exit 1
}

if (Test-Path $pidFile) {
    $savedPid = (Get-Content $pidFile -ErrorAction SilentlyContinue | Select-Object -First 1).Trim()
    if ($savedPid -match '^\d+$') {
        $savedProcess = Get-CimInstance Win32_Process -Filter "ProcessId = $savedPid" -ErrorAction SilentlyContinue
        if ($savedProcess -and $savedProcess.CommandLine -match [regex]::Escape($runnerScript)) {
            Start-Process $url
            Write-Host "BUSoftware is already running at $url"
            exit 0
        }
    }

    Remove-Item $pidFile -ErrorAction SilentlyContinue
}

$existingProcesses = @(Get-ManagedProcesses -RunnerPath $runnerScript)
if ($existingProcesses.Count -gt 0) {
    $existingPid = Get-NetTCPConnection -State Listen -LocalPort $port -ErrorAction SilentlyContinue |
        Select-Object -ExpandProperty OwningProcess -First 1
    if (-not $existingPid) {
        $existingPid = $existingProcesses[0].ProcessId
    }

    Set-Content -Path $pidFile -Value $existingPid
    Start-Process $url
    Write-Host "BUSoftware is already running at $url"
    exit 0
}

$portOwner = Get-NetTCPConnection -State Listen -LocalPort $port -ErrorAction SilentlyContinue |
    Select-Object -First 1
if ($portOwner) {
    Write-Host "Port $port is already in use by PID $($portOwner.OwningProcess)."
    exit 1
}

Remove-Item $stdoutFile, $stderrFile -ErrorAction SilentlyContinue

$process = Start-Process `
    -FilePath $pythonExe `
    -ArgumentList ('"{0}"' -f $runnerScript) `
    -WorkingDirectory $projectRoot `
    -RedirectStandardOutput $stdoutFile `
    -RedirectStandardError $stderrFile `
    -WindowStyle Hidden `
    -PassThru

$ready = $false
for ($attempt = 0; $attempt -lt 20; $attempt++) {
    Start-Sleep -Milliseconds 500

    $currentProcess = Get-Process -Id $process.Id -ErrorAction SilentlyContinue
    if (-not $currentProcess) {
        break
    }

    try {
        $null = Invoke-WebRequest -Uri $url -UseBasicParsing -TimeoutSec 2
        $ready = $true
        break
    }
    catch {
    }
}

if (-not $ready) {
    Remove-Item $pidFile -ErrorAction SilentlyContinue
    Write-Host "BUSoftware failed to start. Check server.err for details."
    exit 1
}

$listeningPid = Get-NetTCPConnection -State Listen -LocalPort $port -ErrorAction SilentlyContinue |
    Select-Object -ExpandProperty OwningProcess -First 1
if (-not $listeningPid) {
    $listeningPid = $process.Id
}

Set-Content -Path $pidFile -Value $listeningPid

Start-Process $url
Write-Host "BUSoftware started at $url"
