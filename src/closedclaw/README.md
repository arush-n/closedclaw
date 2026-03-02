# Closedclaw

**Your Memory. Your Rules. Your Machine.**

Closedclaw is a privacy-first AI memory middleware that wraps [mem0](https://github.com/mem0ai/mem0) with consent-gated, encrypted, and auditable personal data governance.

## Features

- 🔌 **OpenAI-Compatible Proxy**: Drop-in replacement for OpenAI API with memory enrichment
- 🧠 **Memory Vault**: CRUD operations for personal memories with sensitivity classification
- 🛡️ **Privacy Firewall**: Policy-based access control with PII redaction (22 entity types via Presidio)
- ✅ **Consent Gates**: Explicit consent for sensitive memory sharing with signed receipts
- 📝 **Audit Log**: Hash-chained, Ed25519-signed log of all context injections
- 🔐 **Encryption**: AES-256-GCM envelope encryption at rest with per-memory DEKs and cryptographic deletion
- 🌐 **Dashboard UI**: Full Next.js dashboard with Memory Graph, Vault, Audit, Policies, Insights, and Chat views
- 🤖 **ClawdBot Agent**: LangGraph-style agent with 5 memory tools for guided exploration
- 🔍 **Insight Engine**: AI-powered life summaries, trend detection, contradiction analysis, expiry review
- 📊 **Context Inspector**: Per-message transparency showing which memories were used, redacted, or blocked
- 🔒 **Differential Privacy**: Laplacian noise on retrieval scores to prevent exact-match inference

## Quick Start

### Installation

```bash
pip install closedclaw
```

### Initialize

```bash
closedclaw init
closedclaw config set provider openai
closedclaw config set openai_api_key sk-...
```

### Start the Server

```bash
closedclaw serve
```

### Connect Your Tools

Simply point your OpenAI SDK to closedclaw:

```python
import openai

client = openai.OpenAI(
    base_url="http://localhost:8765/v1",
    api_key="your-openai-key"  # forwarded to OpenAI
)

# That's it! All existing code works unchanged.
response = client.chat.completions.create(
    model="gpt-4o-mini",
    messages=[{"role": "user", "content": "Hello!"}]
)
```

Or set the environment variable:

```bash
export OPENAI_BASE_URL=http://localhost:8765/v1
```

## API Endpoints

| Endpoint | Description |
|----------|-------------|
| `GET /v1/status` | System status and health |
| `GET /v1/memory` | Search memories semantically |
| `POST /v1/memory` | Add a new memory |
| `GET /v1/memory/{id}` | Get a specific memory |
| `PATCH /v1/memory/{id}` | Update a memory |
| `DELETE /v1/memory/{id}` | Delete a memory (cryptographic) |
| `POST /v1/chat/completions` | OpenAI-compatible proxy |
| `GET /v1/consent/pending` | List pending consent requests |
| `POST /v1/consent/{id}` | Respond to consent request |
| `GET /v1/audit` | Retrieve audit log |
| `GET /v1/audit/verify` | Verify hash chain integrity |

## Sensitivity Levels

| Level | Name | Description | Default Handling |
|-------|------|-------------|-----------------|
| 0 | Public | General facts, public info | Any provider |
| 1 | General | Name, profession, general preferences | Cloud OK, names redacted |
| 2 | Personal | Address, relationships, finances | Local LLM only |
| 3 | Sensitive | Medical, legal, credentials | Consent required |

## Configuration

All settings can be configured via:
- Environment variables (prefixed with `CLOSEDCLAW_`)
- Config file at `~/.closedclaw/config.json`
- CLI commands

```bash
# List all config
closedclaw config list

# Get a value
closedclaw config get provider

# Set a value
closedclaw config set provider ollama
```

## Privacy Policies

Define custom privacy rules in `~/.closedclaw/policies/`:

```json
{
  "id": "no-health-to-cloud",
  "name": "Block health memories from cloud LLMs",
  "priority": 100,
  "conditions": {
    "tags_include": ["health"],
    "provider_not": ["ollama"]
  },
  "action": "BLOCK"
}
```

## Local-Only Mode

For fully private, local operation:

```bash
# Install and start Ollama
ollama pull llama3.1
ollama pull nomic-embed-text

# Configure closedclaw
closedclaw config set provider ollama
closedclaw serve
```

## Development

```bash
# Clone the repo
git clone https://github.com/closedclaw/closedclaw
cd closedclaw/src/closedclaw

# Install with dev dependencies
pip install -e ".[all]"

# Run with hot-reload
closedclaw serve --reload --debug

# Load demo data (15 memories + 3 audit entries)
closedclaw demo

# Run unit tests (no server required)
PYTHONPATH=src pytest tests/test_smoke.py tests/test_persistence_encryption.py -v

# Run integration tests (requires running server on port 8765)
closedclaw serve &
PYTHONPATH=src python tests/integration_test.py
```

### Dashboard UI

```bash
cd src/closedclaw/ui
npm install
npm run dev   # → http://localhost:3001
```

The dashboard provides:
- **Graph View** — Force-directed graph of memory clusters with d3-force
- **Memory Vault** — Searchable, filterable memory list with sensitivity badges
- **Audit Log** — Hash-chain integrity verification, filters, export
- **Policy Manager** — CRUD for privacy policies, compliance profiles (HIPAA/GDPR/COPPA)
- **Insights** — AI-generated life summary, trends, contradictions, expiring memories
- **Consent Center** — Approve/deny pending consent requests, browse receipt history
- **Chat** — Memory chat with Context Inspector showing retrieval transparency

## Architecture

```
User's Tool (Continue.dev, Cursor, etc.)
         │
         ▼
    ┌─────────────────────────────────────┐
    │         Closedclaw Proxy            │
    │  localhost:8765/v1/chat/completions │
    └─────────────────────────────────────┘
         │                           │
         ▼                           ▼
    ┌──────────┐              ┌──────────────┐
    │ Memory   │              │   Privacy    │
    │ Search   │◄────────────►│   Firewall   │
    └──────────┘              └──────────────┘
         │                           │
         ▼                           ▼
    ┌──────────┐              ┌──────────────┐
    │ mem0     │              │   Policy     │
    │ Store    │              │   Engine     │
    └──────────┘              └──────────────┘
                                     │
         ┌───────────────────────────┘
         ▼
    ┌──────────────────────────────────────┐
    │        LLM Provider                  │
    │  (OpenAI / Anthropic / Ollama)       │
    └──────────────────────────────────────┘
```

## License

MIT License - see [LICENSE](LICENSE) for details.
