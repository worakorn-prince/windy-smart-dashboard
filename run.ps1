#run.ps1 — One-step launcher for Windy Smart Dashboard.
#
#Usage:
#  .\run.ps1            Build frontend if needed, then run server; opens the
#                       dashboard in your browser once the server is ready.
#  .\run.ps1 -Dev       Run both backend (port 8000) and frontend dev (5173)
#                       in separate windows for HMR; opens the browser when
#                       both are up.
#  .\run.ps1 -NoBrowser Do not auto-open the browser (server only).
#  .\run.ps1 -Install    Install/reinstall backend + frontend deps.
#  .\run.ps1 -Clean      Wipe caches; does NOT remove node_modules or pip pkgs.
#
# Prerequisites: Python 3.10+ and Node 18+ on PATH.

param(
  [Alias("d")][switch]$Dev,
  [Alias("i")][switch]$Install,
  [Alias("c")][switch]$Clean,
  [Alias("n")][switch]$NoBrowser
)

# --- Auto-elevate ------------------------------------------------------------
# Hardware temperatures & fan speeds are read via LibreHardwareMonitor, which
# requires Administrator privileges. Relaunch elevated (one UAC prompt) so the
# dashboard "just works" without the user having to open an admin shell.
$isAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $isAdmin) {
  Write-Host "[run] Hardware sensors (CPU/GPU temps, fan RPM) need Administrator - relaunching elevated..." -ForegroundColor Yellow
  $relaunch = @("-NoProfile", "-ExecutionPolicy", "Bypass", "-File", $MyInvocation.MyCommand.Definition)
  if ($Dev)    { $relaunch += "-Dev" }
  if ($Install){ $relaunch += "-Install" }
  if ($Clean)  { $relaunch += "-Clean" }
  if ($NoBrowser){ $relaunch += "-NoBrowser" }
  Start-Process powershell -ArgumentList $relaunch -Verb RunAs
  exit
}

$ErrorActionPreference = "Stop"
$root   = Split-Path -Parent $MyInvocation.MyCommand.Definition
$be     = Join-Path $root "backend"
$fe     = Join-Path $root "frontend"
$venv   = Join-Path $be ".venv"

function Write-Step($msg) { Write-Host "`n[run] $msg" -ForegroundColor Cyan }
function Write-Ok($msg)   { Write-Host "  OK  $msg" -ForegroundColor Green }
function Write-Warn($msg) { Write-Host "  !   $msg" -ForegroundColor Yellow }
function Die($msg)        { Write-Host "  X   $msg" -ForegroundColor Red; exit 1 }

# --- Auto-open browser when the server is ready --------------------------------
# A tiny standalone script is written to %TEMP% and launched as a background job:
#  - production mode: job runs in this process, polls 8000, opens the dashboard
#    then the job lives until the server stops.
#  - dev mode: the SAME script is launched as a job inside the frontend window,
#    so the frontend window is the one that opens the browser once 8000 answers.
# This keeps one polling implementation instead of two inlined copies.
$autoOpenPs1 = Join-Path $env:TEMP "windy-dashboard-autoopen.ps1"

function New-AutoOpenScript {
  @'
# Auto-open the dashboard browser once the backend answers.
# Usage:  powershell -File <this.ps1> <readyUrl> <openUrl> <timeoutSec>
param(
  [Parameter(Mandatory)][string]$ReadyUrl,
  [Parameter(Mandatory)][string]$OpenUrl,
  [int]$TimeoutSec = 120
)
$deadline = (Get-Date).AddSeconds($TimeoutSec)
while ((Get-Date) -lt $deadline) {
  try {
    $r = Invoke-WebRequest -Uri $ReadyUrl -UseBasicParsing -TimeoutSec 2 -ErrorAction Stop
    if ($r.StatusCode -lt 500) {
      Write-Host "[auto-open] $ReadyUrl is ready - opening $OpenUrl" -ForegroundColor Green
      try { Start-Process $OpenUrl } catch { }
      break
    }
  } catch { }
  Start-Sleep -Milliseconds 700
}
'@ | Set-Content -Path $autoOpenPs1 -Encoding ASCII
}

if (-not $NoBrowser) { New-AutoOpenScript }

# --- Resolve Python from venv ---------------------------------------------------
function Get-VenvPython {
  $py = Join-Path $venv "Scripts\python.exe"
  if (Test-Path $py) { return $py }
  # fallback to global python
  $py = (Get-Command python -ErrorAction SilentlyContinue).Source
  if (-not $py) { Die "Python not found. Install Python 3.10+ from https://python.org" }
  return $py
}

$py = Get-VenvPython
$pyVer = ((& $py -c "import sys; print(sys.version_info[:2])") 2>$null)
Write-Ok "Python: $py ($pyVer)"

$node = (Get-Command node.exe -ErrorAction SilentlyContinue).Source
if (-not $node) { Die "Node not on PATH. Install Node 18+ from https://nodejs.org" }
$nodeVer = (& node --version)
Write-Ok "Node: $nodeVer"

# --- Ensure venv exists ---------------------------------------------------------
if (-not (Test-Path $venv)) {
  Write-Step "Creating Python virtual environment"
  & $py -m venv $venv
  if ($LASTEXITCODE -ne 0) { Die "Failed to create venv" }
  Write-Ok "Virtual environment created at $venv"
}

$venvPip = Join-Path $venv "Scripts\pip.exe"
$venvPython = Join-Path $venv "Scripts\python.exe"

# --- Optional: clean caches ---------------------------------------------------
if ($Clean) {
  Write-Step "Cleaning caches"
  Get-ChildItem -Path $be -Recurse -Include "__pycache__" -Directory -ErrorAction SilentlyContinue |
    Remove-Item -Recurse -Force
  if (Test-Path (Join-Path $be ".cache")) { Remove-Item -Recurse -Force (Join-Path $be ".cache") }
  Write-Ok "Removed __pycache__ and backend\.cache"
}

# --- Install / verify deps ----------------------------------------------------
if ($Install -or -not (Test-Path (Join-Path $be ".venv-marker"))) {
  Write-Step "Installing backend Python packages (in venv)"
  & $venvPip install --upgrade pip --quiet
  if ($LASTEXITCODE -ne 0) { Die "pip install --upgrade pip failed" }
  & $venvPip install -r (Join-Path $be "requirements.txt") --quiet
  if ($LASTEXITCODE -ne 0) { Die "pip install -r requirements.txt failed" }
  Set-Content -Path (Join-Path $be ".venv-marker") -Value (Get-Date -Format o)
  Write-Ok "Backend dependencies installed"
}

if ($Install -or -not (Test-Path (Join-Path $fe "node_modules"))) {
  Write-Step "Installing frontend Node packages"
  Push-Location $fe
  & npm install --silent
  if ($LASTEXITCODE -ne 0) { Pop-Location; Die "npm install failed" }
  Pop-Location
  Write-Ok "Frontend dependencies installed"
}

# --- Dev mode -----------------------------------------------------------------
if ($Dev) {
  Write-Step "Starting dev servers (two windows)"
  $beCmd = "Set-Location -LiteralPath '$be'; & '$venvPython' main.py"
  Start-Process powershell -ArgumentList "-NoExit","-Command",$beCmd
  $feCmd = "Set-Location -LiteralPath '$fe'; npm run dev"
  if (-not $NoBrowser) {
    # Launch the shared auto-open job from inside the frontend window so it can
    # open the browser (5173) once the backend answers (8000).
    $feCmd += "; Start-Job -FilePath '$autoOpenPs1' -ArgumentList 'http://127.0.0.1:8000','http://127.0.0.1:5173',120 | Out-Null"
  }
  Start-Process powershell -ArgumentList "-NoExit","-Command",$feCmd
  Write-Host ""
  Write-Ok "Backend  → http://127.0.0.1:8000  (with /docs Swagger)"
  Write-Ok "Frontend → http://localhost:5173  (HMR + proxied to backend)"
  if (-not $NoBrowser) {
    Write-Ok "Browser will open automatically once the backend is up."
  }
  Write-Host "  Close both PowerShell windows to stop."
  exit 0
}

# --- Production build + run ---------------------------------------------------
if (-not (Test-Path (Join-Path $fe "dist\index.html"))) {
  Write-Step "Building frontend (first run takes ~30s)"
  Push-Location $fe
  & npm run build
  if ($LASTEXITCODE -ne 0) { Pop-Location; Die "npm run build failed" }
  Pop-Location
  Write-Ok "Frontend built at frontend\dist"
}

Write-Step "Starting backend (binds 127.0.0.1:8000 only)"
if (-not $NoBrowser) {
  Start-Job -FilePath $autoOpenPs1 -ArgumentList "http://127.0.0.1:8000","http://127.0.0.1:8000",120 | Out-Null
  Write-Host "  Auto-open: browser will open once the server responds (use -NoBrowser to skip)."
}
Write-Host "  Press Ctrl+C to stop."
Write-Host ""
Push-Location $be
& (Join-Path $venv "Scripts\python.exe") main.py
Pop-Location