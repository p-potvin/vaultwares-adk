<#
.SYNOPSIS
    Registers the run-spool drain as an hourly scheduled task.

.DESCRIPTION
    The recorder POSTs directly and only spools when that fails, so this is the
    retry path for everything the API missed. Without it a spooled batch is
    lost: five sat undelivered from 2026-08-10 until this task was added.

    Hourly rather than daily, matching the recorder's own send cadence -- a
    backlog should clear on roughly the same rhythm it accumulates.
#>
[CmdletBinding()]
param(
    [string]$SpoolDir = "D:\AiHistory\run-spool",
    [string]$ApiUrl = "https://api.vaultwares.ca",
    [switch]$StartNow
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$TaskName = "VaultWares Run Spool Drain"
$Script   = Join-Path $PSScriptRoot "drain-run-spool.ps1"
if (-not (Test-Path $Script)) { throw "drain script not found: $Script" }

[Environment]::SetEnvironmentVariable("VW_RUNS_SPOOL_DIR", $SpoolDir, "Machine")
[Environment]::SetEnvironmentVariable("VW_API_URL", $ApiUrl, "Machine")

$key = $env:VW_TELEMETRY_API_KEY
if (-not $key) { $key = [Environment]::GetEnvironmentVariable("VW_TELEMETRY_API_KEY", "User") }
if ($key) {
    [Environment]::SetEnvironmentVariable("VW_TELEMETRY_API_KEY", $key, "Machine")
} else {
    Write-Warning "VW_TELEMETRY_API_KEY not found - the drain will get 401s"
}

Unregister-ScheduledTask -TaskName $TaskName -TaskPath '\VaultWares\' -Confirm:$false -ErrorAction SilentlyContinue | Out-Null

$conhost  = (Get-Command "conhost.exe" -ErrorAction Stop).Source
$pwshPath = (Get-Command "pwsh.exe" -ErrorAction Stop).Source

$action = New-ScheduledTaskAction `
    -Execute $conhost `
    -Argument ("--headless `"$pwshPath`" -NoProfile -WindowStyle Hidden -NonInteractive " +
               "-ExecutionPolicy Bypass -File `"$Script`"") `
    -WorkingDirectory (Split-Path -Parent $PSScriptRoot)

# At logon plus hourly forever: the backlog is time-sensitive only in that it
# should not grow, so a short catch-up cadence is enough.
$triggerLogon = New-ScheduledTaskTrigger -AtLogOn
$triggerHourly = New-ScheduledTaskTrigger -Once -At (Get-Date).Date `
    -RepetitionInterval (New-TimeSpan -Hours 1)

$settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 30) `
    -MultipleInstances IgnoreNew `
    -StartWhenAvailable

$principal = New-ScheduledTaskPrincipal -GroupId "BUILTIN\Administrators" -RunLevel Highest

Register-ScheduledTask -TaskName $TaskName -TaskPath '\VaultWares\' -Action $action `
    -Trigger @($triggerLogon, $triggerHourly) -Settings $settings -Principal $principal `
    -Description ("VaultWares: retries model-run telemetry batches the API did not accept. " +
                  "The recorder spools to disk on a failed POST; nothing else ever retries them.") `
    | Out-Null

Write-Host "task '$TaskName' registered (at logon + hourly)" -ForegroundColor Green

if ($StartNow) {
    Start-ScheduledTask -TaskName $TaskName -TaskPath '\VaultWares\'
    Start-Sleep -Seconds 4
    Write-Host "state: $((Get-ScheduledTask -TaskName $TaskName -TaskPath '\VaultWares\').State)" -ForegroundColor Green
}
