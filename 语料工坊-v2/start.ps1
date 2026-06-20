$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$Backend = Join-Path $Root "backend"
$Frontend = Join-Path $Root "frontend"
$BackendPython = Join-Path $Backend ".venv\Scripts\python.exe"
$BackendUrl = "http://127.0.0.1:8765"
$FrontendUrl = "http://127.0.0.1:5173"
$BackendLog = Join-Path $Backend "backend.log"
$BackendErrLog = Join-Path $Backend "backend.err.log"
$FrontendLog = Join-Path $Frontend "frontend.log"
$FrontendErrLog = Join-Path $Frontend "frontend.err.log"

function Test-PortOpen {
    param([int]$Port)
    $connection = Get-NetTCPConnection -LocalPort $Port -ErrorAction SilentlyContinue
    return $null -ne $connection
}

function Wait-HttpOk {
    param(
        [string]$Url,
        [int]$TimeoutSeconds = 30
    )
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        try {
            Invoke-RestMethod -Uri $Url -Method Get -TimeoutSec 2 | Out-Null
            return $true
        } catch {
            Start-Sleep -Milliseconds 500
        }
    }
    return $false
}

if (-not (Test-Path $BackendPython)) {
    Write-Host "Backend virtual environment not found: $BackendPython" -ForegroundColor Red
    Write-Host "Create it first: cd backend; python -m venv .venv; .\.venv\Scripts\Activate.ps1; pip install -r requirements.txt"
    exit 1
}

if (-not (Test-Path (Join-Path $Frontend "node_modules"))) {
    Write-Host "Frontend dependencies not found. Running npm install..." -ForegroundColor Yellow
    Push-Location $Frontend
    npm install
    Pop-Location
}

if (-not (Test-PortOpen 8765)) {
    Write-Host "Starting backend: $BackendUrl"
    Start-Process powershell -ArgumentList @(
        "-NoProfile",
        "-ExecutionPolicy", "Bypass",
        "-Command",
        "cd `"$Backend`"; & `"$BackendPython`" -m app.main 1> `"$BackendLog`" 2> `"$BackendErrLog`""
    ) -WindowStyle Hidden
} else {
    Write-Host "Backend already running on port 8765"
}

if (-not (Wait-HttpOk "$BackendUrl/api/health" 30)) {
    Write-Host "Backend did not become ready in time." -ForegroundColor Red
    exit 1
}

if (-not (Test-PortOpen 5173)) {
    Write-Host "Starting frontend: $FrontendUrl"
    Start-Process powershell -ArgumentList @(
        "-NoProfile",
        "-ExecutionPolicy", "Bypass",
        "-Command",
        "cd `"$Frontend`"; npm run dev 1> `"$FrontendLog`" 2> `"$FrontendErrLog`""
    ) -WindowStyle Hidden
} else {
    Write-Host "Frontend already running on port 5173"
}

if (-not (Wait-HttpOk "$FrontendUrl/" 30)) {
    Write-Host "Frontend did not become ready in time." -ForegroundColor Red
    Write-Host "Check log: $FrontendErrLog"
    exit 1
}

Start-Process $FrontendUrl
Write-Host "Corpus Workshop is running in the background." -ForegroundColor Green
Write-Host "Logs:"
Write-Host "  $BackendLog"
Write-Host "  $BackendErrLog"
Write-Host "  $FrontendLog"
Write-Host "  $FrontendErrLog"
