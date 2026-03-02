"""Quick test to verify proxy & other fixes."""
import urllib.request
import json
from pathlib import Path

BASE = "http://127.0.0.1:8765"
TOKEN = Path.home().joinpath(".closedclaw", "token").read_text().strip()

def test_proxy_no_api_key():
    """Proxy should return 502 when no LLM API key is configured."""
    data = json.dumps({
        "model": "gpt-4o-mini",
        "messages": [{"role": "user", "content": "hi"}],
    }).encode()
    req = urllib.request.Request(
        f"{BASE}/v1/chat/completions",
        data=data,
        headers={
            "Authorization": f"Bearer {TOKEN}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        urllib.request.urlopen(req)
        print("FAIL: Expected 502, got 200")
    except urllib.error.HTTPError as e:
        body = json.loads(e.read().decode())
        detail = body.get("detail", "")
        if e.code == 502:
            print(f"PASS: Proxy returns 502 - {detail[:80]}")
        else:
            print(f"FAIL: Expected 502, got {e.code} - {detail[:80]}")

def test_cors():
    """CORS should allow localhost origins."""
    req = urllib.request.Request(
        f"{BASE}/health",
        headers={"Origin": "http://localhost:3000"},
    )
    r = urllib.request.urlopen(req)
    cors = r.headers.get("Access-Control-Allow-Origin", "NOT SET")
    if "localhost" in cors:
        print(f"PASS: CORS allows localhost:3000 -> {cors}")
    else:
        print(f"FAIL: CORS header = {cors}")

def test_memory_add():
    """Memory add should work."""
    data = json.dumps({
        "content": "I like pasta",
        "user_id": "test-verify",
    }).encode()
    req = urllib.request.Request(
        f"{BASE}/v1/memory",
        data=data,
        headers={
            "Authorization": f"Bearer {TOKEN}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    r = urllib.request.urlopen(req)
    body = json.loads(r.read().decode())
    if body.get("id") and body.get("memory"):
        print(f"PASS: Memory added - id={body['id'][:8]}... sensitivity={body.get('sensitivity')}")
    else:
        print(f"FAIL: Memory add returned {body}")

def test_audit_verify():
    """Audit chain should be valid."""
    req = urllib.request.Request(
        f"{BASE}/v1/audit/verify",
        headers={"Authorization": f"Bearer {TOKEN}"},
    )
    r = urllib.request.urlopen(req)
    body = json.loads(r.read().decode())
    if body.get("valid") is True:
        print(f"PASS: Audit chain valid - {body.get('entries_checked')} entries")
    else:
        print(f"FAIL: Audit chain invalid - {body}")

if __name__ == "__main__":
    print("=== Closedclaw Fix Verification ===\n")
    test_cors()
    test_memory_add()
    test_audit_verify()
    test_proxy_no_api_key()
    print("\n=== Done ===")
