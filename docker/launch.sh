#!/usr/bin/env bash
# =============================================================================
# Closedclaw + Openclaw — Full Launch Script (Linux/Mac)
# =============================================================================
# Launches both the Docker services (openclaw, bridge, qdrant) and the
# closedclaw host server + dashboard.
#
# Usage:
#   ./launch.sh              # Launch everything
#   ./launch.sh --docker     # Only launch Docker services
#   ./launch.sh --host       # Only launch closedclaw host
#   ./launch.sh --stop       # Stop everything
#   ./launch.sh --rebuild    # Rebuild Docker images and launch
# =============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(dirname "$SCRIPT_DIR")"
DOCKER_DIR="$SCRIPT_DIR"
CLOSEDCLAW_DIR="$ROOT_DIR/closedclaw-master"

DOCKER_ONLY=false
HOST_ONLY=false
STOP=false
REBUILD=false

for arg in "$@"; do
    case "$arg" in
        --docker)  DOCKER_ONLY=true ;;
        --host)    HOST_ONLY=true ;;
        --stop)    STOP=true ;;
        --rebuild) REBUILD=true ;;
        *) echo "Unknown arg: $arg"; exit 1 ;;
    esac
done

# Colors
header() { echo -e "\n\033[36m=== $1 ===\033[0m"; }
ok()     { echo -e "  \033[32m[OK]\033[0m $1"; }
warn()   { echo -e "  \033[33m[!]\033[0m $1"; }
err()    { echo -e "  \033[31m[X]\033[0m $1"; }

# --- Stop ---
if $STOP; then
    header "Stopping all services"
    
    cd "$DOCKER_DIR"
    docker compose down 2>/dev/null || true
    ok "Docker services stopped"

    # Stop closedclaw host
    pkill -f "uvicorn.*closedclaw" 2>/dev/null || true
    pkill -f "next.*closedclaw" 2>/dev/null || true
    ok "Host processes stopped"
    
    echo -e "\nAll services stopped."
    exit 0
fi

# --- Pre-flight ---
header "Pre-flight checks"

if ! $HOST_ONLY; then
    if ! docker info >/dev/null 2>&1; then
        err "Docker is not running"
        exit 1
    fi
    ok "Docker is running"
fi

# .env
if [ ! -f "$DOCKER_DIR/.env" ]; then
    if [ -f "$DOCKER_DIR/.env.example" ]; then
        cp "$DOCKER_DIR/.env.example" "$DOCKER_DIR/.env"
        warn ".env created from .env.example — edit it with your API keys"
    fi
fi

if ! $DOCKER_ONLY; then
    if ! command -v python3 &>/dev/null && ! command -v python &>/dev/null; then
        err "Python not found"
        exit 1
    fi
    ok "Python is available"
fi

# --- Docker ---
if ! $HOST_ONLY; then
    header "Starting Docker services"
    cd "$DOCKER_DIR"
    
    if $REBUILD; then
        echo "  Building images..."
        docker compose build
    fi
    
    docker compose up -d
    ok "Docker services started"
    
    echo "  Waiting for services..."
    for i in $(seq 1 20); do
        if curl -sf http://localhost:9000/health >/dev/null 2>&1; then
            ok "Control bridge is healthy"
            break
        fi
        sleep 3
        echo "  ... waiting ($((i*3))/60s)"
    done
fi

# --- Host ---
if ! $DOCKER_ONLY; then
    header "Starting Closedclaw host server"
    
    # Load .env
    if [ -f "$DOCKER_DIR/.env" ]; then
        set -a
        source "$DOCKER_DIR/.env"
        set +a
    fi
    
    CLOSEDCLAW_PORT="${CLOSEDCLAW_PORT:-8765}"
    DASHBOARD_PORT="${CLOSEDCLAW_DASHBOARD_PORT:-3001}"
    PY="$(command -v python3 || command -v python)"
    
    cd "$CLOSEDCLAW_DIR"
    
    $PY -m uvicorn closedclaw.api.app:create_app --factory \
        --host 127.0.0.1 --port "$CLOSEDCLAW_PORT" --reload &
    SERV_PID=$!
    ok "Closedclaw server on http://localhost:$CLOSEDCLAW_PORT (PID: $SERV_PID)"
    
    UI_DIR="$CLOSEDCLAW_DIR/src/closedclaw/ui"
    if [ -d "$UI_DIR" ]; then
        cd "$UI_DIR"
        [ -d node_modules ] || npm install
        PORT=$DASHBOARD_PORT npx next dev -p "$DASHBOARD_PORT" &
        DASH_PID=$!
        ok "Closedclaw dashboard on http://localhost:$DASHBOARD_PORT (PID: $DASH_PID)"
    else
        warn "Dashboard UI not found at $UI_DIR"
    fi
fi

# --- Summary ---
header "All services launched"
echo ""
echo "  Service                    URL                     Access"
echo "  -------                    ---                     ------"

if ! $HOST_ONLY; then
    echo -e "  \033[32mOpenclaw Dashboard\033[0m         http://localhost:3000    Host"
    echo -e "  \033[33mOpenclaw MCP\033[0m               :8766                   Docker only"
    echo -e "  \033[33mControl Bridge\033[0m             :9000                   Docker only"
    echo -e "  \033[33mQdrant\033[0m                     :6333                   Docker only"
fi

if ! $DOCKER_ONLY; then
    echo -e "  \033[36mClosedclaw Server\033[0m          http://localhost:${CLOSEDCLAW_PORT:-8765}    Host only"
    echo -e "  \033[36mClosedclaw Dashboard\033[0m       http://localhost:${DASHBOARD_PORT:-3001}    Host only"
fi

echo ""
echo "  Configs:"
echo "    Closedclaw: docker/config/closedclaw.yaml"
echo "    Openclaw:   docker/config/openclaw.yaml"
echo "    Env:        docker/.env"
echo ""
echo "  To stop:  ./launch.sh --stop"
echo "  To logs:  cd docker && docker compose logs -f"
echo ""
