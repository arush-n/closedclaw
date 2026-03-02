"""
Deep integration test for closedclaw cross-module data flows.

Tests the actual interconnections between modules:
  1. Memory operations create audit entries
  2. Proxy creates consent requests for sensitive memories
  3. Consent decisions create audit entries with receipts
  4. Sensitivity classification drives policy evaluation
  5. Audit chain maintains integrity across all operations
"""
import urllib.request
import json
import sys
from pathlib import Path
import time

BASE = "http://127.0.0.1:8765"
TOKEN = Path.home().joinpath(".closedclaw", "token").read_text().strip()

PASS = 0
FAIL = 0
ERRORS = []


def req(method, path, data=None, auth=True, expect_code=200):
    """Make a request and return (code, body_dict)."""
    headers = {"Content-Type": "application/json"}
    if auth:
        headers["Authorization"] = f"Bearer {TOKEN}"
    body_bytes = json.dumps(data).encode() if data else None
    r = urllib.request.Request(f"{BASE}{path}", data=body_bytes, headers=headers, method=method)
    try:
        resp = urllib.request.urlopen(r)
        return resp.getcode(), json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        try:
            return e.code, json.loads(body)
        except json.JSONDecodeError:
            return e.code, {"raw": body}


def check(name, passed, detail=""):
    global PASS, FAIL
    status = "PASS" if passed else "FAIL"
    msg = f"  [{status}] {name}" + (f" — {detail}" if detail else "")
    print(msg)
    if passed:
        PASS += 1
    else:
        FAIL += 1
        ERRORS.append(name)
    return passed


print("=" * 60)
print("DEEP INTEGRATION: Cross-Module Data Flows")
print("=" * 60)

# Get initial audit state
code, body = req("GET", "/v1/audit?limit=1000")
initial_audit_count = body.get("total", 0)
print(f"  [INFO] Initial audit entries: {initial_audit_count}")


# ========================================================================
# TEST 1: Memory Add -> Audit Entry Created
# ========================================================================
print()
print("--- TEST 1: Memory Add creates Audit Entry ---")

code, body = req("POST", "/v1/memory", {
    "content": "Cross-module test memory for integration testing",
    "user_id": "deep-integration-test",
    "tags": ["integration-test"]
})
check("Memory add succeeds", code == 200 and "id" in body)
test_mem_id = body.get("id", "")

# Short delay for async operations
time.sleep(0.1)

code, body = req("GET", "/v1/audit?limit=1000")
new_audit_count = body.get("total", 0)
check("Audit entry created after memory add", new_audit_count > initial_audit_count, 
      f"before={initial_audit_count}, after={new_audit_count}")

# Verify audit entry content
if body.get("entries"):
    latest = body["entries"][0]  # Most recent
    check("Audit entry references memory ID", test_mem_id in str(latest.get("memory_ids", [])),
          f"memory_ids={latest.get('memory_ids', [])}")


# ========================================================================
# TEST 2: Memory Update -> Audit Entry Created  
# ========================================================================
print()
print("--- TEST 2: Memory Update creates Audit Entry ---")

before_update_count = new_audit_count

code, body = req("PATCH", f"/v1/memory/{test_mem_id}", {"sensitivity": 2})
check("Memory update succeeds", code == 200)

time.sleep(0.1)

code, body = req("GET", "/v1/audit?limit=1000")
after_update_count = body.get("total", 0)
check("Audit entry created after memory update", after_update_count > before_update_count,
      f"before={before_update_count}, after={after_update_count}")


# ========================================================================
# TEST 3: Sensitivity -> Policy Evaluation Flow
# ========================================================================
print()
print("--- TEST 3: Sensitivity drives Policy Evaluation ---")

# Add memories with different sensitivities
memories = []

# L0 - should be permitted
code, body = req("POST", "/v1/memory", {
    "content": "Public preference: I prefer dark themes",
    "user_id": "policy-test",
    "sensitivity": 0,
})
check("L0 memory added", code == 200)
memories.append(body.get("id"))

# L1 - should be redacted for cloud
code, body = req("POST", "/v1/memory", {
    "content": "My name is TestUser and my email is test@example.com",
    "user_id": "policy-test",
    "sensitivity": 1,
})
check("L1 memory added", code == 200)
memories.append(body.get("id"))

# L2 - should be blocked from cloud
code, body = req("POST", "/v1/memory", {
    "content": "My home address is 456 Private Lane",
    "user_id": "policy-test",
    "sensitivity": 2,
})
check("L2 memory added", code == 200)
memories.append(body.get("id"))

# L3 - should trigger consent gate
code, body = req("POST", "/v1/memory", {
    "content": "Medical: I have a prescription for medication XYZ",
    "user_id": "policy-test",
    "sensitivity": 3,
})
check("L3 memory added", code == 200)
memories.append(body.get("id"))

# Verify search respects sensitivity filters
code, body = req("GET", "/v1/memory?q=preference&user_id=policy-test&sensitivity_max=0")
check("Search sensitivity_max=0 works", body.get("count", -1) >= 0)

code, body = req("GET", "/v1/memory?q=address&user_id=policy-test&sensitivity_max=1")
l2_filtered = body.get("count", -1) == 0
check("L2 memory filtered by sensitivity_max=1", l2_filtered, f"count={body.get('count')}")


# ========================================================================
# TEST 4: Proxy -> Memory Search -> Policy -> Audit Pipeline
# ========================================================================
print()
print("--- TEST 4: Proxy creates Consent Requests for L3 ---")

# Check pending consents before
code, body = req("GET", "/v1/consent/pending")
pending_before = body.get("count", 0)

# Proxy call will fail (no API key) but will exercise the memory enrichment path.
# Use X-User-ID header so retrieval targets policy-test memories.
proxy_headers = {
    "Authorization": f"Bearer {TOKEN}",
    "Content-Type": "application/json",
    "X-User-ID": "policy-test",
}
proxy_req = urllib.request.Request(
    f"{BASE}/v1/chat/completions",
    data=json.dumps({
        "model": "gpt-4o-mini",
        "messages": [{"role": "user", "content": "medical prescription"}],
    }).encode(),
    headers=proxy_headers,
    method="POST",
)
try:
    urllib.request.urlopen(proxy_req)
except urllib.error.HTTPError:
    pass
# We expect 502 (no API key), but the memory enrichment should have run

# Check if consent request was created for L3 memory
code, body = req("GET", "/v1/consent/pending")
pending_after = body.get("count", 0)
check("Consent request created for L3 memory", pending_after > pending_before,
      f"before={pending_before}, after={pending_after}")


# ========================================================================
# TEST 5: Consent Decision -> Audit Entry with Receipt
# ========================================================================
print()
print("--- TEST 5: Consent Decision creates Audit Entry ---")

code, body = req("GET", "/v1/audit?limit=1000")
audit_before_consent = body.get("total", 0)

# Get pending consent if any
code, body = req("GET", "/v1/consent/pending")
if body.get("count", 0) > 0:
    pending = body["pending"][0]
    pending_id = pending["request_id"]
    
    # Respond to consent
    code, body = req("POST", f"/v1/consent/{pending_id}", {
        "decision": "approve",
        "remember_for_provider": False,
    })
    check("Consent approval succeeds", code == 200, f"code={code}")
    
    # Check receipt was created
    receipt = body.get("receipt")
    check("Consent receipt created", receipt is not None and "receipt_id" in receipt,
          f"receipt={receipt}")
    
    # Save receipt_id
    receipt_id = receipt.get("receipt_id") if receipt else None
    
    # Check audit entry created
    code, body = req("GET", "/v1/audit?limit=1000")
    audit_after_consent = body.get("total", 0)
    check("Audit entry created for consent decision", audit_after_consent > audit_before_consent,
          f"before={audit_before_consent}, after={audit_after_consent}")
    
    # Verify audit references consent receipt
    if body.get("entries"):
        consent_audit = [e for e in body["entries"] if e.get("consent_receipt_id")]
        check("Audit entry links to consent receipt", len(consent_audit) > 0)
    
    # Verify consent receipt
    if receipt_id:
        code, body = req("POST", f"/v1/consent/receipts/{receipt_id}/verify")
        check("Consent receipt verifies", code == 200 and body.get("valid", False),
              f"valid={body.get('valid')}")
else:
    print("  [SKIP] No pending consent (L3 memory may not have been found by proxy)")


# ========================================================================
# TEST 6: Audit Chain Integrity After All Operations
# ========================================================================
print()
print("--- TEST 6: Audit Chain Integrity ---")

code, body = req("GET", "/v1/audit/verify")
check("Audit chain valid after all operations", code == 200 and body.get("valid") is True,
      f"valid={body.get('valid')}, reason={body.get('reason', 'ok')}")

# Export and verify structure
code, body = req("GET", "/v1/audit/export")
check("Audit export successful", code == 200 and "entries_count" in body)
check("Audit export includes entry count", isinstance(body.get("entries_count"), int))
check("Audit export signed", body.get("signature") is not None)


# ========================================================================
# TEST 7: Memory Delete -> Audit Entry
# ========================================================================
print()
print("--- TEST 7: Memory Delete creates Audit Entry ---")

code, body = req("GET", "/v1/audit?limit=1000")
audit_before_delete = body.get("total", 0)

if test_mem_id:
    code, body = req("DELETE", f"/v1/memory/{test_mem_id}")
    check("Memory delete succeeds", code == 200)
    
    time.sleep(0.1)
    
    code, body = req("GET", "/v1/audit?limit=1000")
    audit_after_delete = body.get("total", 0)
    check("Audit entry created for memory delete", audit_after_delete > audit_before_delete,
          f"before={audit_before_delete}, after={audit_after_delete}")


# ========================================================================
# CLEANUP
# ========================================================================
print()
print("--- CLEANUP ---")

# Delete test memories
for mem_id in memories:
    if mem_id:
        req("DELETE", f"/v1/memory/{mem_id}")

# Delete test user memories
req("DELETE", "/v1/memory?user_id=policy-test&confirm=true")
req("DELETE", "/v1/memory?user_id=deep-integration-test&confirm=true")

print("  [INFO] Cleanup complete")


# ========================================================================
# SUMMARY
# ========================================================================
print()
print("=" * 60)
total = PASS + FAIL
print(f"TOTAL: {PASS}/{total} passed, {FAIL} failed")
if ERRORS:
    print(f"\nFailed tests:")
    for e in ERRORS:
        print(f"  - {e}")
print("=" * 60)

sys.exit(0 if FAIL == 0 else 1)
