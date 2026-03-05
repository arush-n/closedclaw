# =============================================================================
# Closedclaw + Openclaw — Full Launch Script (Windows PowerShell)
# =============================================================================
# Launches both the Docker services (openclaw, bridge, qdrant) and the
# closedclaw host server + dashboard.
#
# Usage:
#   .\launch.ps1              # Launch everything
#   .\launch.ps1 -DockerOnly  # Only launch Docker services
#   .\launch.ps1 -HostOnly    # Only launch closedclaw host
#   .\launch.ps1 -Stop        # Stop everything
# =============================================================================

param(
    [switch]$DockerOnly,
    [switch]$HostOnly,
    [switch]$Stop,
    [switch]$Rebuild
)

$ErrorActionPreference = "Continue"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RootDir = Split-Path -Parent $ScriptDir
$DockerDir = $ScriptDir
$ClosedclawDir = Join-Path $RootDir "closedclaw-master"

# Colors
function Write-Header($msg) { Write-Host "`n=== $msg ===" -ForegroundColor Cyan }
function Write-Ok($msg) { Write-Host "  [OK] $msg" -ForegroundColor Green }
function Write-Warn($msg) { Write-Host "  [!] $msg" -ForegroundColor Yellow }
function Write-Err($msg) { Write-Host "  [X] $msg" -ForegroundColor Red }

# --- Stop ---
if ($Stop) {
    Write-Header "Stopping all services"
    
    # Stop Docker
    Push-Location $DockerDir
    docker compose down 2>$null
    Pop-Location
    Write-Ok "Docker services stopped"

    # Stop closedclaw host processes
    Get-Process -Name "python" -ErrorAction SilentlyContinue | Where-Object {
        $_.CommandLine -like "*closedclaw*" -or $_.CommandLine -like "*uvicorn*closedclaw*"
    } | Stop-Process -Force -ErrorAction SilentlyContinue
    Write-Ok "Closedclaw host processes stopped"

    # Stop Next.js dashboard
    Get-Process -Name "node" -ErrorAction SilentlyContinue | Where-Object {
        $_.CommandLine -like "*closedclaw*next*"
    } | Stop-Process -Force -ErrorAction SilentlyContinue
    Write-Ok "Dashboard processes stopped"
    
    Write-Host "`nAll services stopped." -ForegroundColor Green
    exit 0
}

# --- Pre-flight checks ---
Write-Header "Pre-flight checks"

# Check Docker
$dockerAvailable = $false
try {
    docker info 2>$null | Out-Null
    if ($LASTEXITCODE -eq 0) {
        $dockerAvailable = $true
        Write-Ok "Docker is running"
    }
} catch {}
if (-not $dockerAvailable) {
    Write-Err "Docker is not running. Please start Docker Desktop."
    if (-not $HostOnly) { exit 1 }
}

# Check .env
$envFile = Join-Path $DockerDir ".env"
$envExample = Join-Path $DockerDir ".env.example"
if (-not (Test-Path $envFile)) {
    if (Test-Path $envExample) {
        Copy-Item $envExample $envFile
        Write-Warn ".env created from .env.example — please edit it with your API keys"
    } else {
        Write-Err ".env.example not found"
    }
}

# Check Python
$pythonAvailable = $false
try {
    python --version 2>$null | Out-Null
    if ($LASTEXITCODE -eq 0) {
        $pythonAvailable = $true
        Write-Ok "Python is available"
    }
} catch {}
if (-not $pythonAvailable -and -not $DockerOnly) {
    Write-Err "Python not found. Cannot start closedclaw host server."
    if (-not $DockerOnly) { exit 1 }
}

# --- Launch Docker services ---
if (-not $HostOnly) {
    Write-Header "Starting Docker services (openclaw + bridge + qdrant)"
    
    Push-Location $DockerDir
    
    if ($Rebuild) {
        Write-Host "  Building images..." -ForegroundColor Gray
        docker compose build
    }

    docker compose up -d
    
    if ($LASTEXITCODE -eq 0) {
        Write-Ok "Docker services started"
    } else {
        Write-Err "Failed to start Docker services"
        Pop-Location
        exit 1
    }
    
    Pop-Location

    # Wait for services to be healthy
    Write-Host "  Waiting for services to be ready..." -ForegroundColor Gray
    $maxWait = 60
    $waited = 0
    while ($waited -lt $maxWait) {
        Start-Sleep -Seconds 3
        $waited += 3
        
        try {
            $bridgeHealth = Invoke-RestMethod -Uri "http://localhost:9000/health" -TimeoutSec 3 -ErrorAction SilentlyContinue
            if ($bridgeHealth.status -eq "ok") {
                Write-Ok "Control bridge is healthy"
                break
            }
        } catch {}
        
        Write-Host "  ... waiting ($waited/$maxWait seconds)" -ForegroundColor Gray
    }
}

# --- Launch Closedclaw Host Server ---
if (-not $DockerOnly) {
    Write-Header "Starting Closedclaw host server"
    
    # Set environment variables from .env
    if (Test-Path $envFile) {
        Get-Content $envFile | ForEach-Object {
            if ($_ -match '^\s*([^#][^=]+)=(.*)$') {
                $key = $matches[1].Trim()
                $val = $matches[2].Trim()
                [Environment]::SetEnvironmentVariable($key, $val, "Process")
            }
        }
    }
    
    # Start closedclaw server in background
    $closedclawPort = $env:CLOSEDCLAW_PORT
    if (-not $closedclawPort) { $closedclawPort = "8765" }
    
    Push-Location $ClosedclawDir
    
    $serverJob = Start-Process -FilePath "python" -ArgumentList @(
        "-m", "uvicorn",
        "closedclaw.api.app:create_app",
        "--factory",
        "--host", "127.0.0.1",
        "--port", $closedclawPort,
        "--reload"
    ) -PassThru -WindowStyle Normal
    
    Write-Ok "Closedclaw server starting on http://localhost:$closedclawPort (PID: $($serverJob.Id))"
    
    Pop-Location

    # Start closedclaw dashboard
    $dashboardPort = $env:CLOSEDCLAW_DASHBOARD_PORT
    if (-not $dashboardPort) { $dashboardPort = "3001" }
    
    $uiDir = Join-Path $ClosedclawDir "src\closedclaw\ui"
    if (Test-Path $uiDir) {
        Push-Location $uiDir
        
        # Install deps if needed
        if (-not (Test-Path "node_modules")) {
            Write-Host "  Installing dashboard dependencies..." -ForegroundColor Gray
            npm install 2>$null
        }
        
        $env:PORT = $dashboardPort
        $dashboardJob = Start-Process -FilePath "npx" -ArgumentList @(
            "next", "dev", "-p", $dashboardPort
        ) -PassThru -WindowStyle Normal
        
        Write-Ok "Closedclaw dashboard starting on http://localhost:$dashboardPort (PID: $($dashboardJob.Id))"
        
        Pop-Location
    } else {
        Write-Warn "Dashboard UI not found at $uiDir"
    }
}

# --- Summary ---
Write-Header "All services launched"
Write-Host ""
Write-Host "  Service                    URL                          Access" -ForegroundColor White
Write-Host "  -------                    ---                          ------" -ForegroundColor Gray

if (-not $HostOnly) {
    Write-Host "  Openclaw Dashboard         http://localhost:3000         Host" -ForegroundColor Green
    Write-Host "  Openclaw MCP               :8766                        Docker only" -ForegroundColor Yellow
    Write-Host "  Control Bridge             :9000                        Docker only" -ForegroundColor Yellow
    Write-Host "  Qdrant Vector DB           :6333                        Docker only" -ForegroundColor Yellow
}

if (-not $DockerOnly) {
    Write-Host "  Closedclaw Server          http://localhost:$closedclawPort         Host only" -ForegroundColor Cyan
    Write-Host "  Closedclaw Dashboard       http://localhost:$dashboardPort         Host only" -ForegroundColor Cyan
    Write-Host "  Closedclaw API Docs        http://localhost:$closedclawPort/docs    Host only" -ForegroundColor Cyan
}

Write-Host ""
Write-Host "  Configs:" -ForegroundColor White
Write-Host "    Closedclaw: docker\config\closedclaw.yaml" -ForegroundColor Gray
Write-Host "    Openclaw:   docker\config\openclaw.yaml" -ForegroundColor Gray
Write-Host "    Env:        docker\.env" -ForegroundColor Gray
Write-Host ""
Write-Host "  To stop:  .\launch.ps1 -Stop" -ForegroundColor Gray
Write-Host "  To logs:  cd docker && docker compose logs -f" -ForegroundColor Gray
Write-Host ""
