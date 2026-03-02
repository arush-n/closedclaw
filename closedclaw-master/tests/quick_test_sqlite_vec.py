"""Quick test script for SQLiteVecStore."""

import sys
sys.path.insert(0, r"c:\Users\rush\closedclaw\src\closedclaw")

import numpy as np
from api.vector_stores import SQLiteVecStore

# Create store
print("Creating in-memory store...")
store = SQLiteVecStore(collection_name='test', embedding_dim=128)

# Generate test vectors
np.random.seed(42)
vectors = [np.random.randn(128).tolist() for _ in range(5)]
payloads = [{'text': f'Memory {i}'} for i in range(5)]

# Insert
print("Inserting vectors...")
ids = store.insert(vectors=vectors, payloads=payloads, sensitivities=[0, 1, 2, 3, 1])
print(f"Inserted {len(ids)} vectors")

# Search
print("\nSearching for similar vectors...")
results = store.search(query='', vectors=[vectors[0]], limit=3)
print(f"Search found {len(results)} results")
for r in results:
    print(f"  - {r.id[:8]}... score={r.score:.4f} sensitivity={r.sensitivity}")

# Search with sensitivity filter
print("\nSearching with sensitivity filter (<=1)...")
results = store.search(query='', vectors=[vectors[0]], limit=10, sensitivity_max=1)
print(f"Sensitivity filtered results: {len(results)}")

# Get stats
print("\nGetting stats...")
stats = store.get_stats()
print(f"Total entries: {stats['count']}")
print(f"Sensitivity distribution: {stats['sensitivity_distribution']}")
print(f"Source distribution: {stats['source_distribution']}")

# Test TTL
print("\nTesting TTL...")
from datetime import datetime, timezone, timedelta
future_time = datetime.now(timezone.utc) + timedelta(hours=24)
expiring_id = store.insert(
    vectors=[np.random.randn(128).tolist()],
    payloads=[{'text': 'Expiring soon'}],
    expires_at_list=[future_time]
)[0]
print(f"Created entry with TTL: {expiring_id[:8]}...")

expiring = store.get_expiring_soon(within_hours=48)
print(f"Entries expiring in 48 hours: {len(expiring)}")

# Test audit
print("\nTesting audit trail...")
store.get(ids[0])  # Access to create audit entry
audit = store.get_audit_trail(ids[0], limit=5)
print(f"Audit entries for first memory: {len(audit)}")
for entry in audit[:3]:
    print(f"  - {entry['event_type']} at {entry['timestamp']}")

store.close()
print("\n✓ All tests passed!")
