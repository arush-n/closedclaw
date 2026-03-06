#!/usr/bin/env python3
"""
Cross-system integration test for ClosedClaw.

Tests all services working together:
  1. closedclaw-server (API + memory + swarm)
  2. closedclaw-dashboard (Next.js UI proxy)
  3. openmemory-mcp (OpenMemory API)
  4. qdrant (vector store)
  5. ollama (local LLM)
"""

import json
import sys
import time
import urllib.request
import urllib.error

SERVER = "http://localhost:8765"
DASHBOARD = "http://localhost:3001"
OPENMEMORY = "http://localhost:8766"
TOKEN = None  # auto-detected

passed = 0
failed = 0
errors = []


def get_token():
    """Read auth token from Docker container."""
    import subprocess
    result = subprocess.run(
        ["docker", "exec", "closedclaw-server", "cat", "/root/.closedclaw/token"],
        capture_output=True, text=True
    )
    return result.stdout.strip()


def req(url, method="GET", data=None, headers=None, timeout=120):
    """Simple HTTP request helper."""
    hdrs = headers or {}
    if TOKEN:
        hdrs.setdefault("Authorization", f"Bearer {TOKEN}")
    if data is not None:
        body = json.dumps(data).encode() if isinstance(data, dict) else data
        hdrs["Content-Type"] = "application/json"
    else:
        body = None
    r = urllib.request.Request(url, data=body, headers=hdrs, method=method)
    try:
        resp = urllib.request.urlopen(r, timeout=timeout)
        raw = resp.read().decode()
        try:
            return resp.status, json.loads(raw)
        except json.JSONDecodeError:
            return resp.status, {"raw": raw[:200]}
    except urllib.error.HTTPError as e:
        raw = e.read().decode()
        try:
            return e.code, json.loads(raw)
        except Exception:
            return e.code, {"raw": raw[:200]}
    except Exception as e:
        return 0, {"error": str(e)}


def check(name, condition, detail=""):
    global passed, failed
    status = "PASS" if condition else "FAIL"
    if condition:
        passed += 1
    else:
        failed += 1
        errors.append(f"{name}: {detail}")
    print(f"  [{status}] {name}" + (f" -- {detail}" if detail and not condition else ""))


def section(title):
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}")


# ─── Section 1: Service Health ───────────────────────────────────

section("1. SERVICE HEALTH")

code, data = req(f"{SERVER}/health")
check("Server health", code == 200, f"HTTP {code}")

code, data = req(f"{DASHBOARD}", headers={})
check("Dashboard serves pages", code == 200, f"HTTP {code}")

code, data = req(f"{OPENMEMORY}/docs", headers={})
check("OpenMemory MCP docs", code == 200, f"HTTP {code}")

# Qdrant
code, data = req("http://localhost:6333/collections")
check("Qdrant reachable", code == 200, f"HTTP {code}")

# Ollama
code, data = req("http://localhost:11434/api/tags")
check("Ollama reachable", code == 200, f"HTTP {code}")
if code == 200:
    models = [m["name"] for m in data.get("models", [])]
    check("Ollama has models", len(models) > 0, f"Models: {models}")
    check("nomic-embed-text available", any("nomic" in m for m in models), f"Available: {models}")


# ─── Section 2: Auth ────────────────────────────────────────────

section("2. AUTHENTICATION")

TOKEN = get_token()
check("Auth token retrieved", len(TOKEN) > 10, f"Token length: {len(TOKEN)}")

code, _ = req(f"{SERVER}/v1/memory", method="GET")
# This will fail because q is required, but 422 means auth passed
check("Valid token accepted", code in (200, 422), f"HTTP {code}")

# Test without token
old_token = TOKEN
TOKEN = None
code, _ = req(f"{SERVER}/v1/memory", method="GET")
check("Missing token rejected (401)", code == 401, f"HTTP {code}")
TOKEN = old_token


# ─── Section 3: Direct Memory API ───────────────────────────────

section("3. DIRECT MEMORY API (closedclaw-server)")

# Store a memory
test_content = "Cross-system test: the user enjoys playing chess every Sunday morning at the park."
code, data = req(f"{SERVER}/v1/memory", method="POST", data={
    "content": test_content,
    "user_id": "cross-test-user",
    "sensitivity": 1,
    "tags": ["hobby", "chess", "cross-test"],
})
check("Memory store (direct API)", code in (200, 201), f"HTTP {code}")
has_id = isinstance(data, dict) and ("result" in data or "id" in data)
check("Memory store returned data", has_id, f"Keys: {list(data.keys()) if isinstance(data, dict) else 'N/A'}")

# Search for it
time.sleep(1)  # brief pause for indexing
code, data = req(f"{SERVER}/v1/memory?q=chess+park&user_id=cross-test-user")
check("Memory search (direct API)", code == 200, f"HTTP {code}")
count = data.get("count", 0) if isinstance(data, dict) else 0
check("Search found memories", count > 0, f"Found {count} memories")


# ─── Section 4: Swarm Pipeline ──────────────────────────────────

section("4. SWARM AGENT PIPELINE")

# Check swarm status
code, data = req(f"{SERVER}/v1/swarm/status")
check("Swarm status endpoint", code == 200, f"HTTP {code}")
if code == 200:
    check("Swarm is active", data.get("swarm_active") is True)
    agents = data.get("agents", {})
    check("Swarm has agents configured", len(agents) >= 7, f"Agent count: {len(agents)}")

# Store via swarm
print("\n  [....] Swarm store_memory (this takes ~30-70s for LLM calls)...")
t0 = time.time()
code, data = req(f"{SERVER}/v1/swarm/tasks", method="POST", data={
    "task_type": "store_memory",
    "user_id": "cross-test-user",
    "input_data": {
        "raw_text": "The user is a senior software engineer at TechCorp who specializes in distributed systems. They prefer Go and Rust for backend work."
    },
}, timeout=300)
t1 = time.time()
check("Swarm store_memory", code == 200, f"HTTP {code}")
if code == 200:
    status = data.get("status", "")
    check("Swarm status: completed", status == "completed", f"Status: {status}")
    invoked = data.get("agents_invoked", [])
    check("Maker agent invoked", "maker" in invoked, f"Invoked: {invoked}")
    check("Governance agent invoked", "governance" in invoked, f"Invoked: {invoked}")
    check("Policy agent invoked", "policy" in invoked, f"Invoked: {invoked}")
    stored = data.get("output", {}).get("memories_stored", 0)
    check("Memories actually persisted", stored > 0, f"Stored: {stored}")
    print(f"  (Store pipeline took {t1-t0:.1f}s)")

# Retrieve via swarm
print("\n  [....] Swarm retrieve_memory...")
t0 = time.time()
code, data = req(f"{SERVER}/v1/swarm/tasks", method="POST", data={
    "task_type": "retrieve_memory",
    "user_id": "cross-test-user",
    "input_data": {
        "query": "What programming languages does the user prefer?"
    },
}, timeout=120)
t1 = time.time()
check("Swarm retrieve_memory", code == 200, f"HTTP {code}")
if code == 200:
    status = data.get("status", "")
    check("Retrieve status: completed", status == "completed", f"Status: {status}")
    invoked = data.get("agents_invoked", [])
    check("Accessor agent invoked", "accessor" in invoked, f"Invoked: {invoked}")
    check("Governance agent invoked (retrieve)", "governance" in invoked, f"Invoked: {invoked}")
    memories = data.get("output", {}).get("retrieved_memories", [])
    check("Retrieved memories > 0", len(memories) > 0, f"Found: {len(memories)}")
    print(f"  (Retrieve pipeline took {t1-t0:.1f}s)")


# ─── Section 5: Dashboard / UI Proxy ────────────────────────────

section("5. DASHBOARD (Next.js UI)")

# Dashboard serves pages
code, _ = req(f"{DASHBOARD}/vault", headers={})
check("Dashboard /vault page", code == 200, f"HTTP {code}")

code, _ = req(f"{DASHBOARD}/swarm", headers={})
check("Dashboard /swarm page", code == 200, f"HTTP {code}")


# ─── Section 6: OpenMemory MCP ──────────────────────────────────

section("6. OPENMEMORY MCP")

code, data = req(f"{OPENMEMORY}/api/v1/memories/?user_id=default-user&page_size=5", headers={})
check("OpenMemory memories list", code == 200, f"HTTP {code}")
if code == 200:
    check("OpenMemory returns data structure", isinstance(data, dict) and "items" in data or "results" in data,
          f"Keys: {list(data.keys()) if isinstance(data, dict) else 'N/A'}")

code, data = req(f"{OPENMEMORY}/api/v1/apps/", headers={})
check("OpenMemory apps list", code == 200, f"HTTP {code}")


# ─── Section 7: Cross-System Flow ───────────────────────────────

section("7. CROSS-SYSTEM INTEGRATION")

# The memories stored via swarm (section 4) should be findable via direct API (section 3)
code, data = req(f"{SERVER}/v1/memory?q=distributed+systems+Go+Rust&user_id=cross-test-user")
check("Swarm-stored memories found via direct API", code == 200 and data.get("count", 0) > 0,
      f"HTTP {code}, count={data.get('count', 0) if code == 200 else 'N/A'}")

# Qdrant should have the collection with points
code, data = req("http://localhost:6333/collections/closedclaw_memories")
check("Qdrant collection exists", code == 200, f"HTTP {code}")
if code == 200:
    points = data.get("result", {}).get("points_count", 0)
    check("Qdrant has stored vectors", points > 0, f"Points: {points}")

# Swarm message bus should have messages from all tests
code, data = req(f"{SERVER}/v1/swarm/messages?limit=20")
check("Swarm message bus has messages", code == 200 and len(data.get("messages", [])) > 0,
      f"Messages: {len(data.get('messages', [])) if code == 200 else 'N/A'}")

# Constitution should be loadable
code, data = req(f"{SERVER}/v1/swarm/constitution")
check("Constitution accessible", code == 200, f"HTTP {code}")
if code == 200:
    check("Constitution has principles", len(data.get("principles", [])) > 0,
          f"Principles: {len(data.get('principles', []))}")


# ─── Summary ────────────────────────────────────────────────────

section("RESULTS")
total = passed + failed
print(f"  {passed}/{total} tests passed, {failed} failed")
if errors:
    print(f"\n  Failures:")
    for e in errors:
        print(f"    - {e}")
print()
sys.exit(0 if failed == 0 else 1)
