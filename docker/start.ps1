# Closedclaw — One-command start
# Usage: .\start.ps1

$ErrorActionPreference = "Continue"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path

# Create .env if missing
if (-not (Test-Path "$ScriptDir\.env")) {
    if (Test-Path "$ScriptDir\.env.example") {
        Copy-Item "$ScriptDir\.env.example" "$ScriptDir\.env"
        Write-Host "[setup] Created .env from .env.example" -ForegroundColor Yellow
    }
}

# Start Docker services
Write-Host "[start] Starting all services..." -ForegroundColor Cyan
Push-Location $ScriptDir
docker compose up -d --build
$exitCode = $LASTEXITCODE
Pop-Location

if ($exitCode -ne 0) {
    Write-Host "[error] Docker failed. Is Docker Desktop running?" -ForegroundColor Red
    exit 1
}

# Wait for health
Write-Host "[start] Waiting for services to be ready..." -ForegroundColor Gray
for ($i = 0; $i -lt 20; $i++) {
    Start-Sleep -Seconds 3
    try {
        $null = Invoke-RestMethod -Uri "http://localhost:8765/health" -TimeoutSec 2 -ErrorAction SilentlyContinue
        Write-Host "[ready] Closedclaw server is up" -ForegroundColor Green
        break
    } catch {}
}

Write-Host ""
Write-Host "  Closedclaw API:    http://localhost:8765" -ForegroundColor Green
Write-Host "  Closedclaw Docs:   http://localhost:8765/docs" -ForegroundColor Green
Write-Host "  Openclaw UI:       http://localhost:3000" -ForegroundColor Green
Write-Host ""
Write-Host "  Stop:  cd docker && docker compose down" -ForegroundColor Gray
Write-Host "  Logs:  cd docker && docker compose logs -f" -ForegroundColor Gray
Write-Host ""
