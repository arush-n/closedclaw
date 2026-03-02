"""
Closedclaw Vector Stores

Provides SQLite + sqlite-vec based vector storage with:
- Zero-dependency local vector search
- Single file database (easy to inspect, backup, migrate)
- Closedclaw extensions: sensitivity, TTL, encryption, audit
- Full compatibility with mem0 vector store interface
"""

from .sqlite_vec import SQLiteVecStore, OutputData
from .config import SQLiteVecConfig
from .mem0_adapter import (
    Mem0SQLiteVecStore, 
    create_sqlite_vec_store
)

__all__ = [
    "SQLiteVecStore", 
    "SQLiteVecConfig", 
    "OutputData",
    "Mem0SQLiteVecStore",
    "create_sqlite_vec_store",
]
