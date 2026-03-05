# Closedclaw + Openclaw Docker Integration

## Architecture

```
┌─────────────────────────────────────────────────────┐
│                    HOST MACHINE                      │
│                                                      │
│  ┌──────────────────────────────┐                    │
│  │  Closedclaw Server           │                    │
│  │  http://localhost:8765       │                    │
│  │  (NOT exposed to Docker)     │◄──── User access   │
│  │                              │                    │
│  │  ┌────────────────────────┐  │                    │
│  │  │ Closedclaw Dashboard   │  │                    │
│  │  │ http://localhost:3001  │  │                    │
│  │  └────────────────────────┘  │                    │
│  └──────────┬───────────────────┘                    │
│             │ docker network bridge                  │
│             ▼                                        │
│  ┌──────────────────────────────────────────────┐    │
│  │              DOCKER NETWORK                   │    │
│  │                                               │    │
│  │  ┌─────────────┐  ┌───────────────────────┐  │    │
│  │  │ Qdrant      │  │ Openclaw MCP Server   │  │    │
│  │  │ Vector DB   │  │ (openmemory-mcp)      │  │    │
│  │  │ :6333       │  │ :8765 (internal only) │  │    │
│  │  └─────────────┘  └───────────┬───────────┘  │    │
│  │                               │               │    │
│  │  ┌───────────────────────┐    │               │    │
│  │  │ Openclaw Dashboard    │    │               │    │
│  │  │ (openmemory-ui)       │    │               │    │
│  │  │ :3000 → host:3000     │    │               │    │
│  │  └───────────────────────┘    │               │    │
│  │                               │               │    │
│  │  ┌───────────────────────┐    │               │    │
│  │  │ Closedclaw Bridge     │◄───┘               │    │
│  │  │ (control-bridge)      │                    │    │
│  │  │ Enforces policies     │                    │    │
│  │  │ Proxies restricted    │                    │    │
│  │  │ access (gmail, banks) │                    │    │
│  │  │ Guards memory writes  │                    │    │
│  │  └───────────────────────┘                    │    │
│  └──────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────┘
```

## Quick Start

```bash
# 1. Copy and edit configs
cp config/closedclaw.yaml config/closedclaw.local.yaml
cp config/openclaw.yaml config/openclaw.local.yaml

# 2. Set environment
cp .env.example .env
# Edit .env with your API keys

# 3. Launch everything
./launch.ps1        # Windows
./launch.sh         # Linux/Mac
# OR
docker compose up -d
```

## Configuration

### Closedclaw Config (`config/closedclaw.yaml`)
Controls the closedclaw governance system:
- Restricted app policies (gmail, banking, etc.)
- Memory safety rules
- Agent swarm settings
- MCP proxy rules

### Openclaw Config (`config/openclaw.yaml`)
Controls the openclaw memory system:
- Memory auto-capture settings
- LLM provider configuration
- Memory categories and thresholds

## Ports

| Service | Port | Accessible From |
|---------|------|----------------|
| Closedclaw Server | 8765 | Host only |
| Closedclaw Dashboard | 3001 | Host only |
| Openclaw Dashboard | 3000 | Host (via Docker) |
| Openclaw MCP | 8765 | Docker internal only |
| Qdrant | 6333 | Docker internal only |
| Control Bridge | 9000 | Docker internal only |

## Key Features

### Restricted App Access
Openclaw cannot directly access gmail, banking sites, etc. Instead, these requests are routed through closedclaw's controlled MCP proxy which:
- Requires explicit consent for each access
- Logs all access attempts in audit trail
- Redacts sensitive PII before passing data
- Enforces rate limits on sensitive operations

### Memory Guardian
All memory writes from openclaw pass through the memory guardian agent:
- Dangerous memories (credentials, financial data, private keys) are auto-restricted
- Sensitive memories require consent before storage
- All memory operations are audit-logged
- Memory classification happens before storage

### Continuous Context Writing
Openclaw is configured to continuously write memories to maintain context:
- Auto-capture is enforced via config
- Session memories bridge conversation gaps
- Long-term memories are curated by the guardian
