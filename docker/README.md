# Closedclaw Docker

## Quick Start

```bash
cd docker
./start.sh        # Linux/Mac
.\start.ps1       # Windows
```

That's it. This will:
1. Create `.env` from `.env.example` if missing
2. Build and start all containers
3. Wait for services to be healthy

## Services

| Service | URL | Description |
|---------|-----|-------------|
| Closedclaw API | http://localhost:8765 | Privacy governance server |
| API Docs | http://localhost:8765/docs | Swagger UI |
| Openclaw UI | http://localhost:3000 | Memory dashboard |

Internal services (not exposed): Qdrant (vector DB), Control Bridge (policy enforcement), Ollama (local LLM).

## Configuration

Edit `docker/.env` before starting (or edit `.env.example` and re-run start):

```bash
# Required for cloud LLM (skip for local-only with Ollama)
OPENAI_API_KEY=sk-your-key-here

# Optional
USER_ID=default-user
CLOSEDCLAW_PROVIDER=ollama   # or openai
```

## Commands

```bash
docker compose down          # Stop everything
docker compose logs -f       # View logs
docker compose up -d --build # Rebuild and restart
```

## Architecture

```
Closedclaw Server (:8765) ─── Control Bridge ─── Openclaw MCP
        │                                              │
        └──── Ollama (local LLM)              Qdrant (vectors)
                                                       │
                                              Openclaw UI (:3000)
```

## Advanced

For more control, use the full launch scripts:

```bash
./launch.sh              # Start everything (host + Docker)
./launch.sh --docker     # Docker services only
./launch.sh --host       # Host server only
./launch.sh --stop       # Stop everything
```
