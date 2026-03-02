# Local LLM Engine Setup Guide

Closedclaw supports running completely locally using Ollama for both LLM inference and embeddings. This ensures your memories and conversations never leave your machine.

## Quick Start

### 1. Install Ollama

**macOS / Linux:**
```bash
curl -fsSL https://ollama.ai/install.sh | sh
```

**Windows:**
Download from [ollama.ai/download](https://ollama.ai/download)

### 2. Start Ollama Server
```bash
ollama serve
```

### 3. Pull the Default Model (3B, 4-bit quantized - runs on any laptop)
```bash
ollama pull llama3.2:3b-instruct-q4_K_M
ollama pull nomic-embed-text
```

### 4. Configure Closedclaw

Set environment variables or edit `~/.closedclaw/config.json`:

```bash
# Use local Ollama as the provider
export CLOSEDCLAW_PROVIDER=ollama

# Local engine settings
export CLOSEDCLAW_LOCAL_ENABLED=true
export CLOSEDCLAW_LOCAL_LLM_MODEL=llama3.2-3b-q4
export CLOSEDCLAW_LOCAL_EMBEDDING_MODEL=nomic-embed-text
```

Or in config.json:
```json
{
  "provider": "ollama",
  "local_engine": {
    "enabled": true,
    "llm_model": "llama3.2-3b-q4",
    "embedding_model": "nomic-embed-text",
    "hardware_profile": "minimal"
  }
}
```

---

## Model Selection Guide

### Recommended by Hardware Profile

| Profile | RAM | Example Hardware | Recommended LLM | Notes |
|---------|-----|------------------|-----------------|-------|
| **minimal** | 8GB | MacBook Air M1, Budget laptops | `llama3.2-3b-q4` | Default, runs everywhere |
| **standard** | 16GB | MacBook Air M2, Most laptops | `llama3.1-8b-q4` | Better quality |
| **performance** | 32GB | MacBook Pro M2/M3, Gaming laptops | `llama3.1-8b-q8` | Near full quality |
| **workstation** | 64GB+ | Mac Studio, Workstations | `llama3.1-70b-q4` | Frontier quality |

### Available LLM Models

#### Minimal Hardware (8GB RAM)

| Key | Model | Params | Quantization | VRAM | Best For |
|-----|-------|--------|--------------|------|----------|
| `llama3.2-3b-q4` | Llama 3.2 3B | 3B | Q4_K_M | 2.5GB | **Default choice** - best balance |
| `phi3-mini-q4` | Phi-3 Mini | 3.8B | Q4_K_M | 2.2GB | Strong reasoning |
| `qwen2.5-3b-q4` | Qwen 2.5 3B | 3B | Q4_K_M | 2.3GB | Multilingual, long context |
| `gemma2-2b-q4` | Gemma 2 2B | 2B | Q4_K_M | 1.8GB | Fastest inference |
| `tinyllama-1b` | TinyLlama | 1.1B | Q4_K_M | 0.8GB | Ultra-constrained hardware |

#### Standard Hardware (16GB RAM)

| Key | Model | Params | Quantization | VRAM | Best For |
|-----|-------|--------|--------------|------|----------|
| `llama3.2-3b-q8` | Llama 3.2 3B | 3B | Q8_0 | 4.0GB | Higher quality 3B |
| `mistral-7b-q4` | Mistral 7B | 7B | Q4_K_M | 4.5GB | Complex reasoning |
| `llama3.1-8b-q4` | Llama 3.1 8B | 8B | Q4_K_M | 5.0GB | **Recommended** |
| `qwen2.5-7b-q4` | Qwen 2.5 7B | 7B | Q4_K_M | 4.8GB | Coding, multilingual |
| `deepseek-r1-7b-q4` | DeepSeek R1 7B | 7B | Q4_K_M | 4.5GB | Deep analysis |

#### Performance Hardware (32GB RAM)

| Key | Model | Params | Quantization | VRAM | Best For |
|-----|-------|--------|--------------|------|----------|
| `llama3.1-8b-q8` | Llama 3.1 8B | 8B | Q8_0 | 9.0GB | Near full precision |
| `qwen2.5-14b-q4` | Qwen 2.5 14B | 14B | Q4_K_M | 9.5GB | Complex tasks |
| `mistral-nemo-12b-q4` | Mistral Nemo 12B | 12B | Q4_K_M | 8.0GB | Long context |
| `llava-7b-q4` | LLaVA 7B | 7B | Q4_K_M | 5.5GB | **Vision** tasks |

#### Workstation Hardware (64GB+ RAM)

| Key | Model | Params | Quantization | VRAM | Best For |
|-----|-------|--------|--------------|------|----------|
| `llama3.1-70b-q4` | Llama 3.1 70B | 70B | Q4_K_M | 42GB | Frontier quality |
| `qwen2.5-72b-q4` | Qwen 2.5 72B | 72B | Q4_K_M | 45GB | Best coding |

### Embedding Models

| Key | Model | Dimensions | Best For |
|-----|-------|------------|----------|
| `nomic-embed-text` | Nomic Embed Text | 768 | **Default** - good quality |
| `mxbai-embed-large` | MXBai Embed Large | 1024 | High quality |
| `bge-m3` | BGE-M3 | 1024 | Multilingual |
| `all-minilm` | All-MiniLM | 384 | Ultra-fast, small |

---

## Memory Chat API

Once configured, you can chat with your memories locally:

### Chat Endpoint
```bash
curl -X POST http://localhost:8765/v1/memory-chat/chat \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "message": "What are my preferences about coffee?",
    "include_memories": true,
    "memory_limit": 5
  }'
```

### Explore Memories
```bash
# Get a summary of your memories
curl -X POST http://localhost:8765/v1/memory-chat/explore \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"mode": "summary"}'

# Get topic analysis
curl -X POST http://localhost:8765/v1/memory-chat/explore \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"mode": "topics"}'

# Get insights
curl -X POST http://localhost:8765/v1/memory-chat/explore \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"mode": "insights"}'
```

### Check Engine Status
```bash
curl http://localhost:8765/v1/memory-chat/status \
  -H "Authorization: Bearer YOUR_TOKEN"
```

### List Available Models
```bash
curl "http://localhost:8765/v1/memory-chat/models?profile=minimal" \
  -H "Authorization: Bearer YOUR_TOKEN"
```

---

## Configuration Reference

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `CLOSEDCLAW_LOCAL_ENABLED` | `true` | Enable local engine |
| `CLOSEDCLAW_LOCAL_HARDWARE_PROFILE` | `standard` | Hardware profile |
| `CLOSEDCLAW_LOCAL_LLM_MODEL` | `llama3.2-3b-q4` | LLM model key |
| `CLOSEDCLAW_LOCAL_LLM_TEMPERATURE` | `0.7` | Generation temperature |
| `CLOSEDCLAW_LOCAL_LLM_MAX_TOKENS` | `2000` | Max response tokens |
| `CLOSEDCLAW_LOCAL_EMBEDDING_MODEL` | `nomic-embed-text` | Embedding model key |
| `CLOSEDCLAW_LOCAL_OLLAMA_BASE_URL` | `http://localhost:11434` | Ollama server URL |
| `CLOSEDCLAW_LOCAL_AUTO_PULL_MODELS` | `true` | Auto-pull missing models |
| `CLOSEDCLAW_LOCAL_MEMORY_CONTEXT_BUDGET` | `4096` | Max tokens for memory context |

### config.json Example

```json
{
  "provider": "ollama",
  "local_engine": {
    "enabled": true,
    "hardware_profile": "standard",
    "llm_model": "llama3.1-8b-q4",
    "llm_temperature": 0.7,
    "llm_max_tokens": 2000,
    "embedding_model": "nomic-embed-text",
    "ollama_base_url": "http://localhost:11434",
    "auto_pull_models": true,
    "memory_context_budget": 4096
  }
}
```

---

## Troubleshooting

### Ollama Not Running
```bash
# Start Ollama
ollama serve

# Verify it's running
curl http://localhost:11434/api/version
```

### Model Not Found
```bash
# Pull the model manually
ollama pull llama3.2:3b-instruct-q4_K_M

# List installed models
ollama list
```

### Out of Memory
1. Switch to a smaller model (e.g., `tinyllama-1b` or `gemma2-2b-q4`)
2. Reduce `memory_context_budget`
3. Reduce `llm_max_tokens`

### Slow Inference
1. Ensure Ollama is using GPU (check `ollama ps`)
2. Use a smaller model with less VRAM
3. On macOS, ensure you're using Apple Silicon acceleration

### Vision Models
To use vision capabilities (like `llava-7b-q4`), include base64-encoded images in your messages.

---

## Performance Tips

1. **First run is slow**: Models are loaded into memory. Subsequent requests are faster.
2. **Keep models loaded**: Ollama keeps recently used models in memory.
3. **GPU acceleration**: Ensure your GPU drivers are up to date.
4. **Apple Silicon**: Ollama automatically uses Metal acceleration on M1/M2/M3 Macs.
5. **Context length**: Longer memory context = more compute. Adjust `memory_context_budget` for speed.
