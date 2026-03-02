import urllib.request, json
from pathlib import Path

token = Path.home().joinpath(".closedclaw", "token").read_text().strip()
headers = {"Authorization": f"Bearer {token}"}

req = urllib.request.Request("http://127.0.0.1:8765/v1/audit", headers=headers)
r = urllib.request.urlopen(req)
body = json.loads(r.read().decode())

entries = body.get("entries", [])
print(f"Audit entries: {len(entries)}")
for e in entries[:5]:
    print(f"  - {e['action']} | {e.get('resource_type', '')} | {str(e.get('details', ''))[:60]}")
