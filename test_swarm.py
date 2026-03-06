#!/usr/bin/env python3
"""
End-to-end test: multi-agent swarm + memory system
Tests the full store → retrieve → hallucination-check pipeline
using the live closedclaw server at localhost:8765.
"""

import json
import sys
import time
from pathlib import Path

try:
    import httpx
except ImportError:
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install", "httpx", "-q"])
    import httpx

BASE = "http://localhost:8765"
TOKEN_FILE = Path.home() / ".closedclaw" / "token"
DOCKER_CONTAINER = "closedclaw-server"

# ── Auth ──────────────────────────────────────────────────────────────

def get_token() -> str:
    # Try host token file first (local dev mode)
    if TOKEN_FILE.exists():
        t = TOKEN_FILE.read_text().strip()
        if t:
            return t
    # Fall back: read token from Docker container (production mode)
    import subprocess
    result = subprocess.run(
        ["docker", "exec", "closedclaw-server", "cat", "/root/.closedclaw/token"],
        capture_output=True, text=True,
    )
    if result.returncode == 0 and result.stdout.strip():
        token = result.stdout.strip()
        # Cache it locally for next run
        TOKEN_FILE.parent.mkdir(parents=True, exist_ok=True)
        TOKEN_FILE.write_text(token)
        return token
    print("ERROR: Could not find token. Make sure closedclaw-server is running.")
    sys.exit(1)

def headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

# ── Helpers ───────────────────────────────────────────────────────────

def pp(label: str, data: dict):
    print(f"\n{'='*60}")
    print(f"  {label}")
    print(f"{'='*60}")
    print(json.dumps(data, indent=2, default=str))

def post_task(client: httpx.Client, token: str, task_type: str, input_data: dict, context: dict = None) -> dict:
    payload = {
        "task_type": task_type,
        "user_id": "default-user",
        "provider": "ollama",
        "input_data": input_data,
        "context": context or {},
    }
    r = client.post(f"{BASE}/v1/swarm/tasks", json=payload, headers=headers(token), timeout=120)
    r.raise_for_status()
    return r.json()

# ── Tests ─────────────────────────────────────────────────────────────

def test_health(client, token):
    print("\n[1] Health check...")
    r = client.get(f"{BASE}/health")
    assert r.status_code == 200, f"Health failed: {r.text}"
    print(f"    OK — {r.json()['status']}")

def test_swarm_status(client, token):
    print("\n[2] Swarm status + agent list...")
    r = client.get(f"{BASE}/v1/swarm/status", headers=headers(token))
    if r.status_code == 503:
        print("    SKIP — swarm not enabled (set swarm_enabled=true to enable)")
        return False
    r.raise_for_status()
    status = r.json()
    agents = status.get("agents", {})
    print(f"    Swarm enabled | Agents loaded: {list(agents.keys())}")
    print(f"    Constitution principles: {status.get('constitution_principles', 0)}")
    return True

def test_store_memory(client, token):
    print("\n[3] STORE_MEMORY — maker → governance → policy agents...")
    result = post_task(client, token, "store_memory", {
        "text": "I work as a machine learning engineer at a startup called NeuralEdge. "
                "I prefer Python and use PyTorch for training. "
                "My salary is $180k and I live in San Francisco.",
        "source": "test_script",
    })
    pp("store_memory result", {
        "status": result.get("status"),
        "agents_invoked": result.get("agents_invoked", []),
        "memories_stored": result.get("output", {}).get("memories_stored", "?"),
        "blocked_count": result.get("output", {}).get("blocked_count", 0),
        "error": result.get("error"),
    })
    return result.get("status") != "error"

def test_retrieve_memory(client, token):
    print("\n[4] RETRIEVE_MEMORY — accessor → governance agents...")
    result = post_task(client, token, "retrieve_memory", {
        "query": "What is my job and where do I work?",
    })
    output = result.get("output", {})
    pp("retrieve_memory result", {
        "status": result.get("status"),
        "agents_invoked": result.get("agents_invoked", []),
        "memories_found": len(output.get("retrieved_memories", [])),
        "permitted": output.get("permitted_count", 0),
        "blocked": output.get("blocked_count", 0),
        "context_preview": (output.get("context_text", "")[:200] + "...") if output.get("context_text") else None,
        "error": result.get("error"),
    })
    return result.get("status") != "error"

def test_hallucination_check(client, token):
    print("\n[5] DETECT_HALLUCINATION — accessor → sentinel (qwen3.5:4b)...")
    result = post_task(client, token, "detect_hallucination", {
        "query": "What is my job?",
        "response": "You work as a data scientist at Google and make $500k a year.",
    })
    output = result.get("output", {})
    pp("detect_hallucination result", {
        "status": result.get("status"),
        "agents_invoked": result.get("agents_invoked", []),
        "hallucinations_detected": output.get("hallucinations_detected", []),
        "confidence": output.get("confidence", "?"),
        "verdict": output.get("verdict", "?"),
        "error": result.get("error"),
    })

def test_full_pipeline(client, token):
    print("\n[6] FULL_PIPELINE — accessor → governance → sentinel...")
    result = post_task(client, token, "full_pipeline", {
        "query": "Tell me about my work and career.",
        "response": "You are a machine learning engineer at NeuralEdge.",
    })
    output = result.get("output", {})
    pp("full_pipeline result", {
        "status": result.get("status"),
        "agents_invoked": result.get("agents_invoked", []),
        "permitted": output.get("permitted_count", 0),
        "blocked": output.get("blocked_count", 0),
        "redactions": output.get("redaction_count", 0),
        "hallucination_check": output.get("hallucination_check", {}),
        "error": result.get("error"),
    })

def test_audit_verify(client, token):
    print("\n[7] AUDIT_VERIFY — auditor agent (no LLM, pure crypto)...")
    result = post_task(client, token, "audit_verify", {"action": "verify_chain"})
    output = result.get("output", {})
    pp("audit_verify result", {
        "status": result.get("status"),
        "chain_valid": output.get("chain_valid", "?"),
        "entries_checked": output.get("entries_checked", 0),
        "violations": output.get("violations", []),
        "error": result.get("error"),
    })

def test_swarm_stats(client, token):
    print("\n[8] Swarm stats (LLM calls per agent)...")
    r = client.get(f"{BASE}/v1/swarm/stats", headers=headers(token))
    r.raise_for_status()
    pp("swarm stats", r.json())

def test_mem0_direct(client, token):
    """Test the raw memory API (not swarm) to verify mem0 storage works."""
    print("\n[9] Direct memory store/search (closedclaw /v1/memory API)...")

    # Store a memory
    r = client.post(f"{BASE}/v1/memory", headers=headers(token), json={
        "content": "My favourite programming language is Python. I use it daily for ML.",
        "user_id": "default-user",
        "source": "manual",
        "tags": ["programming", "python"],
    }, timeout=120)
    mem_id = None
    if r.status_code in (200, 201):
        result = r.json()
        mem_id = result.get("id")
        print(f"    Stored memory id={mem_id}")
        print(f"      content: {result.get('content','')[:80]}")
    else:
        print(f"    Store returned {r.status_code}: {r.text[:300]}")

    # List all memories
    r2 = client.get(f"{BASE}/v1/memory/all",
                    params={"user_id": "default-user", "limit": 5},
                    headers=headers(token), timeout=30)
    if r2.status_code == 200:
        results = r2.json()
        memories = results if isinstance(results, list) else results.get("memories", results.get("results", []))
        print(f"\n    All memories ({len(memories)} total):")
        for m in memories[:5]:
            content = m.get("content", m.get("memory", ""))
            tags = m.get("tags", m.get("categories", []))
            print(f"      [{', '.join(tags) if tags else 'no tags'}] {content[:80]}")
    else:
        print(f"    List returned {r2.status_code}: {r2.text[:200]}")

# ── Main ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    token = get_token()
    print(f"Token loaded ({len(token)} chars)")

    with httpx.Client(timeout=30) as client:
        test_health(client, token)

        swarm_up = test_swarm_status(client, token)

        # Always test direct memory API
        test_mem0_direct(client, token)

        if swarm_up:
            ok = test_store_memory(client, token)
            if ok:
                time.sleep(1)  # brief pause for vector indexing
                test_retrieve_memory(client, token)
                test_hallucination_check(client, token)
                test_full_pipeline(client, token)
                test_audit_verify(client, token)
                test_swarm_stats(client, token)
        else:
            print("\nSwarm tests skipped — enable with CLOSEDCLAW_SWARM_ENABLED=true")

    print("\n\nDone.")
