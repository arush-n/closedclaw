"""Comprehensive endpoint verification for closedclaw."""
import urllib.request
import json
from pathlib import Path

BASE = "http://127.0.0.1:8765"
TOKEN = Path.home().joinpath(".closedclaw", "token").read_text().strip()
AUTH = {"Authorization": f"Bearer {TOKEN}"}


def req(method, path, data=None, auth=True, expect_code=200):
    """Make a request and return (code, body)."""
    headers = {"Content-Type": "application/json"}
    if auth:
        headers.update(AUTH)
    body_bytes = json.dumps(data).encode() if data else None
    r = urllib.request.Request(f"{BASE}{path}", data=body_bytes, headers=headers, method=method)
    try:
        resp = urllib.request.urlopen(r)
        return resp.getcode(), json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode())


def test(name, passed, detail=""):
    status = "PASS" if passed else "FAIL"
    print(f"  [{status}] {name}" + (f" - {detail}" if detail else ""))
    return passed


results = []

print("=== HEALTH & STATUS ===")
code, body = req("GET", "/health", auth=False)
results.append(test("GET /health", code == 200 and body["status"] == "healthy"))

code, body = req("GET", "/v1/status")
results.append(test("GET /v1/status", code == 200 and "provider" in body, f"provider={body.get('provider')}"))

code, body = req("GET", "/v1/info", auth=False)
results.append(test("GET /v1/info", code == 200 and "version" in body, f"version={body.get('version')}"))

print("\n=== MEMORY CRUD ===")
# Add
code, body = req("POST", "/v1/memory", {"content": "My favorite color is blue", "user_id": "audit-test"})
results.append(test("POST /v1/memory (add)", code == 200 and "id" in body, f"id={body.get('id', '')[:8]}"))
mem_id = body.get("id", "")

# Search
code, body = req("GET", "/v1/memory?q=color&user_id=audit-test")
results.append(test("GET /v1/memory (search)", code == 200, f"results={len(body.get('results', body if isinstance(body, list) else []))}"))

# Tags
code, body = req("GET", "/v1/memory/tags")
results.append(test("GET /v1/memory/tags", code == 200))

# Update
code, body = req("PATCH", f"/v1/memory/{mem_id}", {"content": "My favorite color is green"})
results.append(test(f"PATCH /v1/memory/:id (update)", code == 200))

# Delete
code, body = req("DELETE", f"/v1/memory/{mem_id}")
results.append(test(f"DELETE /v1/memory/:id", code == 200))

print("\n=== CONSENT ===")
code, body = req("GET", "/v1/consent/pending")
results.append(test("GET /v1/consent/pending", code == 200, f"pending={len(body)}"))

code, body = req("GET", "/v1/consent/receipts")
results.append(test("GET /v1/consent/receipts", code == 200))

print("\n=== AUDIT ===")
code, body = req("GET", "/v1/audit")
results.append(test("GET /v1/audit", code == 200 and "entries" in body, f"entries={len(body.get('entries', []))}"))

code, body = req("GET", "/v1/audit/verify")
results.append(test("GET /v1/audit/verify", code == 200 and body.get("valid") is True))

code, body = req("GET", "/v1/audit/export")
results.append(test("GET /v1/audit/export", code == 200 and "bundle_id" in body))

print("\n=== PROXY ===")
code, body = req("POST", "/v1/chat/completions", {
    "model": "gpt-4o-mini",
    "messages": [{"role": "user", "content": "hi"}],
})
results.append(test("POST /v1/chat/completions (no API key)", code == 502, f"detail={body.get('detail', '')[:60]}"))

# Test 401 with no auth
code, body = req("POST", "/v1/memory", {"content": "test"}, auth=False)
results.append(test("POST /v1/memory (no auth -> 401)", code == 401))

print(f"\n=== SUMMARY: {sum(results)}/{len(results)} passed ===")
