"""Debug the 4 failing endpoints."""
import urllib.request
import json
from pathlib import Path

BASE = "http://127.0.0.1:8765"
TOKEN = Path.home().joinpath(".closedclaw", "token").read_text().strip()
AUTH = {"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"}

# 1. Add a memory first
data = json.dumps({"content": "My cat is named Luna", "user_id": "debug-test"}).encode()
r = urllib.request.urlopen(urllib.request.Request(f"{BASE}/v1/memory", data=data, headers=AUTH, method="POST"))
body = json.loads(r.read().decode())
mem_id = body["id"]
print(f"Added memory: {mem_id}")
print(f"  Full response: {json.dumps(body, indent=2)[:300]}")

# 2. Search
print("\n--- Search ---")
try:
    r = urllib.request.urlopen(urllib.request.Request(
        f"{BASE}/v1/memory?query=cat&user_id=debug-test", headers=AUTH))
    body = json.loads(r.read().decode())
    print(f"  Search response type: {type(body).__name__}")
    print(f"  Response: {json.dumps(body, indent=2)[:300]}")
except urllib.error.HTTPError as e:
    print(f"  Error {e.code}: {e.read().decode()[:200]}")

# 3. Update
print("\n--- Update ---")
try:
    data = json.dumps({"content": "My cat is named Stella"}).encode()
    r = urllib.request.urlopen(urllib.request.Request(
        f"{BASE}/v1/memory/{mem_id}", data=data, headers=AUTH, method="PATCH"))
    body = json.loads(r.read().decode())
    print(f"  Update response: {json.dumps(body, indent=2)[:300]}")
except urllib.error.HTTPError as e:
    print(f"  Error {e.code}: {e.read().decode()[:200]}")

# 4. Delete
print("\n--- Delete ---")
try:
    r = urllib.request.urlopen(urllib.request.Request(
        f"{BASE}/v1/memory/{mem_id}", headers=AUTH, method="DELETE"))
    body = json.loads(r.read().decode())
    print(f"  Delete response: {json.dumps(body, indent=2)[:300]}")
except urllib.error.HTTPError as e:
    print(f"  Error {e.code}: {e.read().decode()[:200]}")

# 5. Audit export
print("\n--- Audit Export ---")
try:
    r = urllib.request.urlopen(urllib.request.Request(
        f"{BASE}/v1/audit/export", headers=AUTH))
    body = json.loads(r.read().decode())
    print(f"  Export keys: {list(body.keys())}")
except urllib.error.HTTPError as e:
    print(f"  Error {e.code}: {e.read().decode()[:200]}")
