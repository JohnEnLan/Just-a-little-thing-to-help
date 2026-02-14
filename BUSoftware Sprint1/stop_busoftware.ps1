$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$runnerScript = Join-Path $projectRoot "run_server.py"
$pidFile = Join-Path $projectRoot "server.pid"

function Get-ManagedProcesses {
    param([string]$RunnerPath)

    $runnerPattern = [regex]::Escape($RunnerPath)
    Get-CimInstance Win32_Process -Filter "Name = 'python.exe'" -ErrorAction SilentlyContinue |
        Where-Object { $_.CommandLine -match $runnerPattern }
}

$managedProcesses = @()

if (Test-Path $pidFile) {
    $savedPid = (Get-Content $pidFile -ErrorAction SilentlyContinue | Select-Object -First 1).Trim()
    if ($savedPid -match '^\d+$') {
        $savedProcess = Get-CimInstance Win32_Process -Filter "ProcessId = $savedPid" -ErrorAction SilentlyContinue
        if ($savedProcess -and $savedProcess.CommandLine -match [regex]::Escape($runnerScript)) {
            $managedProcesses += $savedProcess
        }
    }
}

$managedProcesses += @(Get-ManagedProcesses -RunnerPath $runnerScript)
$managedProcesses = $managedProcesses |
    Group-Object -Property ProcessId |
    ForEach-Object { $_.Group[0] }

if ($managedProcesses.Count -eq 0) {
    Remove-Item $pidFile -ErrorAction SilentlyContinue
    Write-Host "BUSoftware is not running."
    exit 0
}

Stop-Process -Id ($managedProcesses | Select-Object -ExpandProperty ProcessId) -Force -ErrorAction SilentlyContinue
Remove-Item $pidFile -ErrorAction SilentlyContinue

Write-Host "BUSoftware stopped."
