#!/usr/bin/env bash
# Closedclaw — One-command start
# Usage: ./start.sh

set -euo pipefail
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Create .env if missing
if [ ! -f "$DIR/.env" ]; then
    if [ -f "$DIR/.env.example" ]; then
        cp "$DIR/.env.example" "$DIR/.env"
        echo "[setup] Created .env from .env.example"
    fi
fi

# Start everything
echo "[start] Starting all services..."
cd "$DIR"
docker compose up -d --build

# Wait for health
echo "[start] Waiting for services..."
for i in $(seq 1 20); do
    if curl -sf http://localhost:8765/health >/dev/null 2>&1; then
        echo "[ready] Closedclaw server is up"
        break
    fi
    sleep 3
done

echo ""
echo "  Closedclaw API:    http://localhost:8765"
echo "  Closedclaw Docs:   http://localhost:8765/docs"
echo "  Openclaw UI:       http://localhost:3000"
echo ""
echo "  Stop:  cd docker && docker compose down"
echo "  Logs:  cd docker && docker compose logs -f"
echo ""
