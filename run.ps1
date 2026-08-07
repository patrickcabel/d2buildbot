<#
.SYNOPSIS
    Sets up (if needed) and starts the D2 Build Maker backend and frontend.

.DESCRIPTION
    - Creates the Python virtualenv and installs backend deps on first run.
    - Runs `npm install` for the frontend on first run.
    - Launches the FastAPI backend (port 8000) and the Vite frontend (port 5173),
      each in its own PowerShell window.

.PARAMETER Setup
    Only perform dependency setup; do not start the servers.

.EXAMPLE
    ./run.ps1
    ./run.ps1 -Setup
#>
param(
    [switch]$Setup
)

$ErrorActionPreference = "Stop"
$root = $PSScriptRoot
$backend = Join-Path $root "backend"
$frontend = Join-Path $root "frontend"
$venvPython = Join-Path $backend ".venv\Scripts\python.exe"

Write-Host "== D2 Build Maker ==" -ForegroundColor Cyan

# --- Backend setup ---
if (-not (Test-Path $venvPython)) {
    Write-Host "Creating Python virtual environment..." -ForegroundColor Yellow
    python -m venv (Join-Path $backend ".venv")
}
Write-Host "Installing backend dependencies..." -ForegroundColor Yellow
& $venvPython -m pip install --quiet --upgrade pip
& $venvPython -m pip install --quiet -r (Join-Path $backend "requirements.txt")

$envFile = Join-Path $backend ".env"
if (-not (Test-Path $envFile)) {
    Copy-Item (Join-Path $backend ".env.example") $envFile
    Write-Host "Created backend/.env from template - fill in your Bungie credentials!" -ForegroundColor Magenta
}

# --- Frontend setup ---
if (-not (Test-Path (Join-Path $frontend "node_modules"))) {
    Write-Host "Installing frontend dependencies..." -ForegroundColor Yellow
    Push-Location $frontend
    npm install
    Pop-Location
}

if ($Setup) {
    Write-Host "Setup complete. Run ./run.ps1 to start the servers." -ForegroundColor Green
    return
}

# --- Launch ---
$certsDir = Join-Path $backend "certs"
$keyPem = Join-Path $certsDir "key.pem"
$certPem = Join-Path $certsDir "cert.pem"
if (-not ((Test-Path $keyPem) -and (Test-Path $certPem))) {
    Write-Host "Generating self-signed HTTPS certs (required for Bungie OAuth)..." -ForegroundColor Yellow
    & $venvPython (Join-Path $backend "make_cert.py")
}

Write-Host "Starting backend on https://127.0.0.1:8000 ..." -ForegroundColor Green
Start-Process powershell -ArgumentList @(
    "-NoExit", "-Command",
    "Set-Location '$backend'; & '$venvPython' -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --ssl-keyfile certs/key.pem --ssl-certfile certs/cert.pem --reload"
)

Write-Host "Starting frontend on http://localhost:5173 ..." -ForegroundColor Green
Start-Process powershell -ArgumentList @(
    "-NoExit", "-Command",
    "Set-Location '$frontend'; npm run dev"
)

Write-Host "Both servers launching in separate windows. Open http://localhost:5173" -ForegroundColor Cyan
Write-Host "API must be HTTPS on 8000 (Vite proxies /api there)." -ForegroundColor DarkGray
