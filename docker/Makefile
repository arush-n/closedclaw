# =============================================================================
# Closedclaw + Openclaw — Makefile
# =============================================================================

.PHONY: env build up down logs restart status shell-bridge shell-mcp \
        bridge-logs mcp-logs ui-logs reload-config clean

# --- Setup ---
env:
	@if not exist .env copy .env.example .env
	@echo ".env file ready — edit it with your API keys"

# --- Docker Operations ---
build:
	docker compose build

up: env
	docker compose up -d
	@echo ""
	@echo "=== Docker services started ==="
	@echo "  Openclaw Dashboard: http://localhost:3000"
	@echo "  Control Bridge:     internal (port 9000)"
	@echo "  Openclaw MCP:       internal (port 8766)"
	@echo "  Qdrant:             internal (port 6333)"
	@echo ""
	@echo "Now start closedclaw on the host:"
	@echo "  cd ../closedclaw-master && python -m closedclaw.api.cli serve"
	@echo "  Closedclaw Server:    http://localhost:8765"
	@echo "  Closedclaw Dashboard: http://localhost:3001"

down:
	docker compose down

restart:
	docker compose restart

status:
	docker compose ps

# --- Logs ---
logs:
	docker compose logs -f

bridge-logs:
	docker compose logs -f control-bridge

mcp-logs:
	docker compose logs -f openmemory-mcp

ui-logs:
	docker compose logs -f openmemory-ui

# --- Shell Access ---
shell-bridge:
	docker compose exec control-bridge sh

shell-mcp:
	docker compose exec openmemory-mcp bash

# --- Config ---
reload-config:
	docker compose exec control-bridge curl -X POST http://localhost:9000/config/reload
	@echo "Bridge config reloaded"

# --- Cleanup ---
clean:
	docker compose down -v --remove-orphans
	@echo "All containers and volumes removed"
