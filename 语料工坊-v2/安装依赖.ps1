$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$Backend = Join-Path $Root "backend"
$Frontend = Join-Path $Root "frontend"
$VenvPython = Join-Path $Backend ".venv\Scripts\python.exe"

function Test-CommandExists {
    param([string]$Command)
    return $null -ne (Get-Command $Command -ErrorAction SilentlyContinue)
}

Write-Host "Checking Corpus Workshop runtime..." -ForegroundColor Cyan

if (-not (Test-CommandExists "python")) {
    Write-Host "Python was not found. Install Python 3.10 or 3.11 and add it to PATH." -ForegroundColor Red
    exit 1
}

if (-not (Test-CommandExists "npm")) {
    Write-Host "Node.js / npm was not found. Install Node.js LTS first." -ForegroundColor Red
    exit 1
}

if (-not (Test-CommandExists "ffmpeg")) {
    Write-Host "FFmpeg was not found. Transcription and acoustic analysis require FFmpeg in PATH." -ForegroundColor Yellow
} else {
    Write-Host "FFmpeg detected." -ForegroundColor Green
}

if (-not (Test-Path $VenvPython)) {
    Write-Host "Creating backend Python virtual environment..." -ForegroundColor Cyan
    Push-Location $Backend
    python -m venv .venv
    Pop-Location
}

Write-Host "Installing backend dependencies. WhisperX / PyTorch may take a long time on first install..." -ForegroundColor Cyan
Push-Location $Backend
& $VenvPython -m pip install --upgrade pip
& $VenvPython -m pip install -r requirements.txt
Pop-Location

Write-Host "Installing frontend dependencies..." -ForegroundColor Cyan
Push-Location $Frontend
npm install
Pop-Location

Write-Host "Install complete. Use the startup script to run Corpus Workshop." -ForegroundColor Green
