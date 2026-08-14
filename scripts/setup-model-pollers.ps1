<#
.SYNOPSIS
    Registers the model-runtime telemetry pollers as a scheduled task.

.DESCRIPTION
    Mirrors agent-ledger/scripts/setup-input-tracker.ps1 deliberately: same
    conhost --headless + hidden pwsh launch so nothing flashes on screen, same
    restart-on-crash policy, same at-logon trigger.

    Registering the task is not enough on its own -- the recorder needs
    nvidia-ml-py and psutil to fill the VRAM/GPU columns, so this installs the
    `telemetry` extra too. Without them those fields are silently null, which
    reads identically to a host with no GPU.

.EXAMPLE
    pwsh -File scripts/setup-model-pollers.ps1 -StartNow
#>
[CmdletBinding()]
param(
    [string]$PythonExe,
    [double]$IntervalSeconds = 60,
    [string]$ApiUrl = "https://api.vaultwares.ca",
    [string]$SpoolDir = "D:\AiHistory\run-spool",
    [string]$Project,
    [switch]$StartNow,
    [switch]$SkipDeps
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$TaskName  = "VaultWares Model Pollers"
$ScriptDir = $PSScriptRoot
$RepoRoot  = Split-Path -Parent $ScriptDir
$Launcher  = Join-Path $ScriptDir "run-model-pollers.ps1"

if (-not (Test-Path $Launcher)) { throw "launcher not found: $Launcher" }

# --- python -----------------------------------------------------------------
if (-not $PythonExe) {
    $cmd = Get-Command "python.exe" -ErrorAction SilentlyContinue
    if (-not $cmd) { throw "no python.exe on PATH; pass -PythonExe" }
    $PythonExe = $cmd.Source
}
Write-Host "python: $PythonExe" -ForegroundColor Cyan

if (-not $SkipDeps) {
    Write-Host "installing telemetry probe dependencies..." -ForegroundColor Cyan
    & $PythonExe -m pip install --quiet --upgrade "nvidia-ml-py>=12.0.0" "psutil>=5.9.0"
    if ($LASTEXITCODE -ne 0) {
        Write-Warning "probe dependency install failed - GPU and memory columns will stay null"
    }
}

# --- environment ------------------------------------------------------------
# Machine scope: the task runs with -NoProfile and must not depend on an
# interactive session having been set up first.
[Environment]::SetEnvironmentVariable("VW_API_URL", $ApiUrl, "Machine")
[Environment]::SetEnvironmentVariable("VW_RUNS_SPOOL_DIR", $SpoolDir, "Machine")

$key = $env:VW_TELEMETRY_API_KEY
if (-not $key) { $key = [Environment]::GetEnvironmentVariable("VW_TELEMETRY_API_KEY", "User") }
if ($key) {
    [Environment]::SetEnvironmentVariable("VW_TELEMETRY_API_KEY", $key, "Machine")
    Write-Host "telemetry key: propagated to Machine scope" -ForegroundColor Green
} else {
    Write-Warning "VW_TELEMETRY_API_KEY not found - batches will spool instead of posting"
}

if (-not (Test-Path $SpoolDir)) { New-Item -ItemType Directory -Path $SpoolDir -Force | Out-Null }

# --- task -------------------------------------------------------------------
Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue | Out-Null

$conhost    = (Get-Command "conhost.exe" -ErrorAction Stop).Source
$pwshPath   = (Get-Command "pwsh.exe" -ErrorAction Stop).Source

$launchArgs = "-NoProfile -WindowStyle Hidden -NonInteractive -ExecutionPolicy Bypass " +
              "-File `"$Launcher`" -PythonExe `"$PythonExe`" -IntervalSeconds $IntervalSeconds"
if ($Project) { $launchArgs += " -Project `"$Project`"" }

$action = New-ScheduledTaskAction `
    -Execute $conhost `
    -Argument "--headless `"$pwshPath`" $launchArgs" `
    -WorkingDirectory $RepoRoot

$trigger = New-ScheduledTaskTrigger -AtLogOn

# ExecutionTimeLimit 0 = never killed: this is a long-lived loop, and Windows
# would otherwise stop it after the default 3 days.
$settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -ExecutionTimeLimit (New-TimeSpan -Hours 0) `
    -MultipleInstances IgnoreNew `
    -RestartCount 99 `
    -RestartInterval (New-TimeSpan -Minutes 1) `
    -StartWhenAvailable

$principal = New-ScheduledTaskPrincipal -GroupId "BUILTIN\Administrators" -RunLevel Highest

Register-ScheduledTask `
    -TaskName $TaskName `
    -Action $action `
    -Trigger $trigger `
    -Settings $settings `
    -Principal $principal `
    -Description ("VaultWares: polls ComfyUI and Ollama for model-run telemetry and ships it to " +
                  "vaultwares-api. ComfyUI history is in-memory and lost on restart, so this runs " +
                  "continuously rather than on a long interval.") `
    | Out-Null

Write-Host "task '$TaskName' registered (at logon, restarts on crash)" -ForegroundColor Green

if ($StartNow) {
    Start-ScheduledTask -TaskName $TaskName
    Start-Sleep -Seconds 3
    $state = (Get-ScheduledTask -TaskName $TaskName).State
    Write-Host "task state: $state" -ForegroundColor Green
}

Write-Host ""
Write-Host "  logs:  $RepoRoot\_logs\model-pollers-<date>.log"
Write-Host "  stop:  Stop-ScheduledTask -TaskName '$TaskName'"
Write-Host "  once:  pwsh -File `"$Launcher`" -Once"
