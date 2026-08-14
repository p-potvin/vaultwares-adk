<#
.SYNOPSIS
    Launcher for the model-runtime telemetry pollers.

.DESCRIPTION
    Watches ComfyUI and Ollama and records their runs through
    vaultwares_adk.telemetry. Invoked by the scheduled task registered by
    setup-model-pollers.ps1; can also be run by hand for a one-shot check.

    The loop is long-lived on purpose: ComfyUI's history is in-memory and is
    wiped when it restarts, so anything not polled before a restart is gone.
#>
[CmdletBinding()]
param(
    [string]$PythonExe,
    [double]$IntervalSeconds = 60,
    [string]$ComfyUiUrl = "http://127.0.0.1:8188",
    [string]$OllamaUrl  = "http://127.0.0.1:11434",
    [string]$Project,
    [switch]$Once
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$RepoRoot = Split-Path -Parent $PSScriptRoot
$LogDir   = Join-Path $RepoRoot "_logs"
if (-not (Test-Path $LogDir)) { New-Item -ItemType Directory -Path $LogDir -Force | Out-Null }
$LogPath = Join-Path $LogDir ("model-pollers-{0}.log" -f (Get-Date -Format "yyyyMMdd"))

function Write-PollerLog {
    param([string]$Message)
    $line = "{0} {1}" -f (Get-Date -Format "ddd, dd MMM yyyy HH:mm"), $Message
    Add-Content -Path $LogPath -Value $line -Encoding UTF8 -ErrorAction SilentlyContinue
    Write-Host $line
}

if (-not $PythonExe) {
    $cmd = Get-Command "python.exe" -ErrorAction SilentlyContinue
    if (-not $cmd) { $cmd = Get-Command "python3.exe" -ErrorAction SilentlyContinue }
    if (-not $cmd) { Write-PollerLog "ERROR no python on PATH"; exit 1 }
    $PythonExe = $cmd.Source
}

# The task runs without a profile, so the machine-scoped values are the ones
# that reach it. Fall back to User scope for a hand-run.
foreach ($name in @("VW_API_URL", "VW_TELEMETRY_API_KEY", "VW_RUNS_SPOOL_DIR")) {
    if (-not [Environment]::GetEnvironmentVariable($name, "Process")) {
        $value = [Environment]::GetEnvironmentVariable($name, "Machine")
        if (-not $value) { $value = [Environment]::GetEnvironmentVariable($name, "User") }
        if ($value) { Set-Item -Path "Env:$name" -Value $value }
    }
}

if (-not $env:VW_TELEMETRY_API_KEY) {
    # Not fatal: the recorder spools to disk and the drain ships it later.
    Write-PollerLog "WARN VW_TELEMETRY_API_KEY not set - batches will spool rather than post"
}

$env:PYTHONPATH = $RepoRoot
$arguments = @(
    "-m", "vaultwares_adk.telemetry.pollers",
    "--interval", $IntervalSeconds,
    "--comfyui-url", $ComfyUiUrl,
    "--ollama-url", $OllamaUrl
)
if ($Project) { $arguments += @("--project", $Project) }
if ($Once)    { $arguments += "--once" }

Write-PollerLog ("starting: {0} (interval {1}s, comfy {2}, ollama {3})" -f `
    $PythonExe, $IntervalSeconds, $ComfyUiUrl, $OllamaUrl)

& $PythonExe @arguments 2>&1 | ForEach-Object { Write-PollerLog $_ }
$code = $LASTEXITCODE
Write-PollerLog "exited with code $code"
exit $code
