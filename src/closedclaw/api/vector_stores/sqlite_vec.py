"""
SQLite-Vec Vector Store Implementation

A high-performance, zero-dependency local vector store built on SQLite + sqlite-vec.
This implementation provides:
- Efficient cosine/L2/inner-product similarity search
- Single-file database for easy backup and migration
- Full compatibility with mem0 vector store interface
- Closedclaw privacy extensions (sensitivity, TTL, encryption, audit)

sqlite-vec is a SQLite extension that provides vector search capabilities
using approximate nearest neighbor algorithms.
"""

import json
import logging
import sqlite3
import struct
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional, Tuple, Union

import numpy as np
from pydantic import BaseModel

from .config import SQLiteVecConfig

logger = logging.getLogger(__name__)


def _serialize_vector(vector: List[float]) -> bytes:
    """
    Serialize a float vector to bytes for sqlite-vec storage.
    Uses little-endian float32 format.
    """
    return struct.pack(f"<{len(vector)}f", *vector)


def _deserialize_vector(data: bytes) -> List[float]:
    """
    Deserialize bytes back to a float vector.
    """
    if data is None:
        return []
    n_floats = len(data) // 4
    return list(struct.unpack(f"<{n_floats}f", data))


class OutputData(BaseModel):
    """Standard output format for vector store operations."""
    id: Optional[str] = None
    score: Optional[float] = None
    payload: Optional[Dict[str, Any]] = None
    
    # Closedclaw extensions
    sensitivity: Optional[int] = None
    encrypted: Optional[bool] = None
    expires_at: Optional[str] = None


class VectorEntry(BaseModel):
    """Internal representation of a vector entry with all metadata."""
    model_config = {"arbitrary_types_allowed": True}
    
    id: str
    vector: List[float]
    payload: Dict[str, Any]
    
    # Closedclaw extensions
    sensitivity: int = 0
    tags: List[str] = []
    source: str = "manual"
    expires_at: Optional[datetime] = None
    content_hash: Optional[str] = None
    encrypted: bool = False
    dek_enc: Optional[str] = None
    access_count: int = 0
    last_accessed: Optional[datetime] = None
    consent_required: bool = False
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class SQLiteVecStore:
    """
    SQLite + sqlite-vec Vector Store
    
    A local-first vector database implementation that provides:
    - Single-file SQLite storage with sqlite-vec extension
    - Multiple distance metrics (cosine, L2, inner product)
    - Closedclaw privacy extensions for sensitivity, TTL, encryption
    - Thread-safe operations with connection pooling
    - Efficient batch operations
    
    Usage:
        store = SQLiteVecStore(
            collection_name="memories",
            path="~/.closedclaw/memory.db",
            embedding_dim=768
        )
        store.insert(
            vectors=[[0.1, 0.2, ...]],
            payloads=[{"text": "memory content"}],
            ids=["mem-123"]
        )
        results = store.search(query="", vectors=[[0.1, 0.2, ...]], limit=5)
    """
    
    # SQL distance functions for sqlite-vec
    DISTANCE_FUNCTIONS = {
        "cosine": "vec_distance_cosine",
        "l2": "vec_distance_L2", 
        "inner_product": "vec_distance_ip"
    }
    
    def __init__(
        self,
        collection_name: str = "mem0",
        path: Optional[str] = None,
        distance_metric: Literal["cosine", "l2", "inner_product"] = "cosine",
        embedding_dim: int = 768,
        config: Optional[SQLiteVecConfig] = None,
        **kwargs
    ):
        """
        Initialize SQLite-Vec vector store.
        
        Args:
            collection_name: Name of the collection (table prefix)
            path: Path to SQLite database file. None = in-memory
            distance_metric: 'cosine', 'l2', or 'inner_product'
            embedding_dim: Dimension of embedding vectors
            config: Optional full configuration object
            **kwargs: Additional config options
        """
        # Build config from parameters
        if config is not None:
            self.config = config
        else:
            self.config = SQLiteVecConfig(
                collection_name=collection_name,
                path=path,
                distance_metric=distance_metric,
                embedding_dim=embedding_dim,
                **{k: v for k, v in kwargs.items() if k in SQLiteVecConfig.model_fields}
            )
        
        self.collection_name = self.config.collection_name
        self.path = self.config.path or ":memory:"
        self.distance_metric = self.config.distance_metric
        self.embedding_dim = self.config.embedding_dim
        self.table_prefix = self.config.get_table_prefix()
        
        # Thread safety
        self._lock = threading.RLock()
        self._local = threading.local()
        
        # Table names
        self._vectors_table = f"{self.table_prefix}_vectors"
        self._metadata_table = f"{self.table_prefix}_metadata"
        self._audit_table = f"{self.table_prefix}_audit"
        
        # Initialize database
        self._ensure_db_path()
        self._init_database()
        
        logger.info(
            f"SQLiteVecStore initialized: collection={collection_name}, "
            f"path={self.path}, dim={embedding_dim}, metric={distance_metric}"
        )
    
    def _ensure_db_path(self):
        """Ensure database directory exists."""
        if self.path != ":memory:":
            db_path = Path(self.path).expanduser().resolve()
            db_path.parent.mkdir(parents=True, exist_ok=True)
            self.path = str(db_path)
    
    @property
    def _conn(self) -> sqlite3.Connection:
        """Get thread-local database connection."""
        if not hasattr(self._local, "conn") or self._local.conn is None:
            conn = sqlite3.connect(self.path, check_same_thread=False)
            conn.row_factory = sqlite3.Row
            
            # Try to load sqlite-vec extension
            self._use_native_vec = False
            
            try:
                # First try the sqlite_vec Python package (preferred)
                import sqlite_vec
                sqlite_vec.load(conn)  # type: ignore[attr-defined]
                self._use_native_vec = True
                logger.debug("Loaded sqlite-vec via sqlite_vec package")
            except ImportError:
                # sqlite_vec package not installed
                logger.info(
                    "sqlite-vec Python package not installed. "
                    "Using pure Python vector search. "
                    "For better performance: pip install sqlite-vec"
                )
            except sqlite3.OperationalError as e:
                if "not authorized" in str(e):
                    # SQLite was compiled without ENABLE_LOAD_EXTENSION
                    logger.info(
                        "SQLite extensions not authorized (Python compiled without "
                        "ENABLE_LOAD_EXTENSION). Using pure Python vector search."
                    )
                else:
                    logger.warning(f"Failed to load sqlite-vec: {e}")
            except Exception as e:
                logger.warning(f"Could not load sqlite-vec extension: {e}")
            
            self._local.conn = conn
        
        return self._local.conn
    
    def _init_database(self):
        """Initialize database schema."""
        with self._lock:
            conn = self._conn
            cursor = conn.cursor()
            
            try:
                cursor.execute("BEGIN")
                
                # Main vectors table - stores vectors as BLOBs
                cursor.execute(f"""
                    CREATE TABLE IF NOT EXISTS {self._vectors_table} (
                        id TEXT PRIMARY KEY,
                        vector BLOB NOT NULL,
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL
                    )
                """)
                
                # Metadata table - stores all payload and closedclaw extensions
                cursor.execute(f"""
                    CREATE TABLE IF NOT EXISTS {self._metadata_table} (
                        id TEXT PRIMARY KEY,
                        payload TEXT NOT NULL,
                        
                        -- Closedclaw extensions
                        sensitivity INTEGER DEFAULT 0,
                        tags TEXT DEFAULT '[]',
                        source TEXT DEFAULT 'manual',
                        expires_at TEXT,
                        content_hash TEXT,
                        encrypted INTEGER DEFAULT 0,
                        dek_enc TEXT,
                        access_count INTEGER DEFAULT 0,
                        last_accessed TEXT,
                        consent_required INTEGER DEFAULT 0,
                        
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL,
                        
                        FOREIGN KEY (id) REFERENCES {self._vectors_table}(id) ON DELETE CASCADE
                    )
                """)
                
                # Audit table for tracking access
                if self.config.enable_audit:
                    cursor.execute(f"""
                        CREATE TABLE IF NOT EXISTS {self._audit_table} (
                            id TEXT PRIMARY KEY,
                            memory_id TEXT NOT NULL,
                            event_type TEXT NOT NULL,
                            event_data TEXT,
                            timestamp TEXT NOT NULL,
                            
                            FOREIGN KEY (memory_id) REFERENCES {self._vectors_table}(id)
                        )
                    """)
                
                # Create indexes for common queries
                cursor.execute(f"""
                    CREATE INDEX IF NOT EXISTS idx_{self.table_prefix}_sensitivity 
                    ON {self._metadata_table}(sensitivity)
                """)
                cursor.execute(f"""
                    CREATE INDEX IF NOT EXISTS idx_{self.table_prefix}_expires 
                    ON {self._metadata_table}(expires_at) 
                    WHERE expires_at IS NOT NULL
                """)
                cursor.execute(f"""
                    CREATE INDEX IF NOT EXISTS idx_{self.table_prefix}_source 
                    ON {self._metadata_table}(source)
                """)
                
                # Try to create virtual table for sqlite-vec if available
                if getattr(self, "_use_native_vec", False):
                    try:
                        cursor.execute(f"""
                            CREATE VIRTUAL TABLE IF NOT EXISTS {self._vectors_table}_vec 
                            USING vec0(
                                id TEXT PRIMARY KEY,
                                embedding FLOAT[{self.embedding_dim}]
                            )
                        """)
                        self._vec_table = f"{self._vectors_table}_vec"
                    except sqlite3.OperationalError as e:
                        logger.warning(f"Could not create vec0 virtual table: {e}")
                        self._use_native_vec = False
                
                conn.commit()
                
            except Exception as e:
                conn.rollback()
                logger.error(f"Failed to initialize database: {e}")
                raise
    
    def create_col(self, name: str, vector_size: Optional[int] = None, distance: Optional[str] = None):
        """
        Create a new collection.
        
        Args:
            name: Collection name
            vector_size: Vector dimension (uses config default if not specified)
            distance: Distance metric (uses config default if not specified)
        """
        # Update config
        self.collection_name = name
        self.table_prefix = SQLiteVecConfig(collection_name=name).get_table_prefix()
        if vector_size:
            self.embedding_dim = vector_size
        if distance:
            self.distance_metric = distance
        
        # Update table names
        self._vectors_table = f"{self.table_prefix}_vectors"
        self._metadata_table = f"{self.table_prefix}_metadata"
        self._audit_table = f"{self.table_prefix}_audit"
        
        # Reinitialize tables
        self._init_database()
        
        return self
    
    def insert(
        self,
        vectors: List[List[float]],
        payloads: Optional[List[Dict[str, Any]]] = None,
        ids: Optional[List[str]] = None,
        # Closedclaw extensions
        sensitivities: Optional[List[int]] = None,
        tags_list: Optional[List[List[str]]] = None,
        sources: Optional[List[str]] = None,
        expires_at_list: Optional[List[Optional[datetime]]] = None,
        content_hashes: Optional[List[Optional[str]]] = None,
        encrypted_flags: Optional[List[bool]] = None,
        dek_enc_list: Optional[List[Optional[str]]] = None,
        consent_required_list: Optional[List[bool]] = None,
    ) -> List[str]:
        """
        Insert vectors into the collection.
        
        Args:
            vectors: List of embedding vectors
            payloads: Optional list of metadata dicts
            ids: Optional list of vector IDs (auto-generated if not provided)
            
            # Closedclaw extensions
            sensitivities: Sensitivity levels (0-3) for each vector
            tags_list: Tags for each vector
            sources: Source identifiers
            expires_at_list: TTL expiry times
            content_hashes: SHA-256 hashes of original content
            encrypted_flags: Whether content is encrypted
            dek_enc_list: Encrypted DEK for each entry
            consent_required_list: Whether consent is required
        
        Returns:
            List of inserted vector IDs
        """
        if not vectors:
            return []
        
        n = len(vectors)
        
        # Generate defaults
        if ids is None:
            ids = [str(uuid.uuid4()) for _ in range(n)]
        if payloads is None:
            payloads = [{} for _ in range(n)]
        if sensitivities is None:
            sensitivities = [0] * n
        if tags_list is None:
            tags_list = [[] for _ in range(n)]
        if sources is None:
            sources = ["manual"] * n
        if expires_at_list is None:
            expires_at_list = [None for _ in range(n)]
        if content_hashes is None:
            content_hashes = [None for _ in range(n)]
        if encrypted_flags is None:
            encrypted_flags = [False] * n
        if dek_enc_list is None:
            dek_enc_list = [None for _ in range(n)]
        if consent_required_list is None:
            consent_required_list = [False] * n
        
        # Validate lengths
        if not all(len(lst) == n for lst in [
            ids, payloads, sensitivities, tags_list, sources,
            expires_at_list, content_hashes, encrypted_flags,
            dek_enc_list, consent_required_list
        ]):
            raise ValueError("All input lists must have the same length")
        
        # Validate vector dimensions
        for i, vec in enumerate(vectors):
            if len(vec) != self.embedding_dim:
                raise ValueError(
                    f"Vector {i} has dimension {len(vec)}, "
                    f"expected {self.embedding_dim}"
                )
        
        now = datetime.now(timezone.utc).isoformat()
        
        with self._lock:
            conn = self._conn
            cursor = conn.cursor()
            
            try:
                cursor.execute("BEGIN")
                
                for i in range(n):
                    vector_blob = _serialize_vector(vectors[i])
                    
                    # Insert vector
                    cursor.execute(f"""
                        INSERT OR REPLACE INTO {self._vectors_table}
                        (id, vector, created_at, updated_at)
                        VALUES (?, ?, ?, ?)
                    """, (ids[i], vector_blob, now, now))
                    
                    # Prepare metadata
                    exp_val = expires_at_list[i]
                    expires_str = exp_val.isoformat() if exp_val else None
                    
                    cursor.execute(f"""
                        INSERT OR REPLACE INTO {self._metadata_table}
                        (id, payload, sensitivity, tags, source, expires_at,
                         content_hash, encrypted, dek_enc, access_count,
                         last_accessed, consent_required, created_at, updated_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        ids[i],
                        json.dumps(payloads[i]),
                        sensitivities[i],
                        json.dumps(tags_list[i]),
                        sources[i],
                        expires_str,
                        content_hashes[i],
                        1 if encrypted_flags[i] else 0,
                        dek_enc_list[i],
                        0,  # access_count
                        None,  # last_accessed
                        1 if consent_required_list[i] else 0,
                        now,
                        now
                    ))
                    
                    # Insert into vec0 virtual table if available
                    if getattr(self, "_use_native_vec", False) and hasattr(self, "_vec_table"):
                        cursor.execute(f"""
                            INSERT OR REPLACE INTO {self._vec_table}
                            (id, embedding)
                            VALUES (?, ?)
                        """, (ids[i], vector_blob))
                    
                    # Audit log
                    if self.config.enable_audit:
                        cursor.execute(f"""
                            INSERT INTO {self._audit_table}
                            (id, memory_id, event_type, event_data, timestamp)
                            VALUES (?, ?, ?, ?, ?)
                        """, (
                            str(uuid.uuid4()),
                            ids[i],
                            "insert",
                            json.dumps({"sensitivity": sensitivities[i]}),
                            now
                        ))
                
                conn.commit()
                logger.info(f"Inserted {n} vectors into {self.collection_name}")
                
                return ids
                
            except Exception as e:
                conn.rollback()
                logger.error(f"Failed to insert vectors: {e}")
                raise
    
    def search(
        self,
        query: str,
        vectors: List[List[float]],
        limit: int = 5,
        filters: Optional[Dict[str, Any]] = None,
        # Closedclaw extensions
        sensitivity_max: Optional[int] = None,
        include_expired: bool = False,
    ) -> List[OutputData]:
        """
        Search for similar vectors.
        
        Args:
            query: Query string (not used directly, kept for API compatibility)
            vectors: Query vectors to search with
            limit: Maximum results to return
            filters: Metadata filters to apply
            sensitivity_max: Maximum sensitivity level to include
            include_expired: Whether to include expired entries
        
        Returns:
            List of search results with scores and payloads
        """
        if not vectors:
            return []
        
        # Use first vector for search
        query_vector: List[float] = vectors[0] if isinstance(vectors[0], list) else vectors  # type: ignore[assignment]
        
        if len(query_vector) != self.embedding_dim:
            raise ValueError(
                f"Query vector has dimension {len(query_vector)}, "
                f"expected {self.embedding_dim}"
            )
        
        with self._lock:
            conn = self._conn
            
            # Check for expired entries if TTL is enabled
            if not include_expired:
                self._cleanup_expired()
            
            if getattr(self, "_use_native_vec", False) and hasattr(self, "_vec_table"):
                results = self._search_native(
                    query_vector, limit, filters, sensitivity_max
                )
            else:
                results = self._search_python(
                    query_vector, limit, filters, sensitivity_max
                )
            
            # Update access counts and last_accessed
            if results and self.config.enable_audit:
                self._record_access([r.id for r in results if r.id])
            
            return results
    
    def _search_native(
        self,
        query_vector: List[float],
        limit: int,
        filters: Optional[Dict[str, Any]],
        sensitivity_max: Optional[int]
    ) -> List[OutputData]:
        """
        Search using sqlite-vec native functions.
        """
        conn = self._conn
        cursor = conn.cursor()
        
        query_blob = _serialize_vector(query_vector)
        distance_fn = self.DISTANCE_FUNCTIONS.get(self.distance_metric, "vec_distance_cosine")
        
        # Build WHERE clause
        where_clauses = ["1=1"]
        params = [query_blob, limit * 2]  # Over-fetch for filtering
        
        if sensitivity_max is not None:
            where_clauses.append("m.sensitivity <= ?")
            params.append(sensitivity_max)
        
        where_sql = " AND ".join(where_clauses)
        
        # Query using vec0 virtual table
        cursor.execute(f"""
            SELECT 
                v.id,
                {distance_fn}(v.embedding, ?) as distance,
                m.payload,
                m.sensitivity,
                m.encrypted,
                m.expires_at,
                m.tags
            FROM {self._vec_table} v
            JOIN {self._metadata_table} m ON v.id = m.id
            WHERE {where_sql}
            ORDER BY distance ASC
            LIMIT ?
        """, params)
        
        rows = cursor.fetchall()
        results = []
        
        for row in rows:
            payload = json.loads(row["payload"]) if row["payload"] else {}
            
            # Apply additional filters
            if filters and not self._apply_filters(payload, filters):
                continue
            
            # Convert distance to similarity score (1 - distance for cosine)
            distance = float(row["distance"])
            if self.distance_metric == "cosine":
                score = 1.0 - distance
            elif self.distance_metric == "inner_product":
                score = -distance  # Inner product: higher is better
            else:
                score = -distance  # L2: lower distance is better, negate for consistency
            
            results.append(OutputData(
                id=row["id"],
                score=score,
                payload=payload,
                sensitivity=row["sensitivity"],
                encrypted=bool(row["encrypted"]),
                expires_at=row["expires_at"]
            ))
            
            if len(results) >= limit:
                break
        
        return results
    
    def _search_python(
        self,
        query_vector: List[float],
        limit: int,
        filters: Optional[Dict[str, Any]],
        sensitivity_max: Optional[int]
    ) -> List[OutputData]:
        """
        Pure Python fallback search using numpy.
        Computes similarities in memory when sqlite-vec is not available.
        """
        conn = self._conn
        cursor = conn.cursor()
        
        # Build WHERE clause
        where_clauses = ["1=1"]
        params = []
        
        if sensitivity_max is not None:
            where_clauses.append("m.sensitivity <= ?")
            params.append(sensitivity_max)
        
        where_sql = " AND ".join(where_clauses)
        
        # Fetch all vectors and metadata
        cursor.execute(f"""
            SELECT 
                v.id,
                v.vector,
                m.payload,
                m.sensitivity,
                m.encrypted,
                m.expires_at,
                m.tags
            FROM {self._vectors_table} v
            JOIN {self._metadata_table} m ON v.id = m.id
            WHERE {where_sql}
        """, params)
        
        rows = cursor.fetchall()
        
        if not rows:
            return []
        
        # Compute similarities using numpy
        query_np = np.array(query_vector, dtype=np.float32)
        query_norm = np.linalg.norm(query_np)
        
        scored_results = []
        
        for row in rows:
            vector = _deserialize_vector(row["vector"])
            payload = json.loads(row["payload"]) if row["payload"] else {}
            
            # Apply additional filters
            if filters and not self._apply_filters(payload, filters):
                continue
            
            # Compute similarity based on distance metric
            vec_np = np.array(vector, dtype=np.float32)
            
            if self.distance_metric == "cosine":
                vec_norm = np.linalg.norm(vec_np)
                if query_norm > 0 and vec_norm > 0:
                    score = float(np.dot(query_np, vec_np) / (query_norm * vec_norm))
                else:
                    score = 0.0
            elif self.distance_metric == "inner_product":
                score = float(np.dot(query_np, vec_np))
            else:  # L2
                distance = float(np.linalg.norm(query_np - vec_np))
                score = -distance  # Negate so higher is better
            
            scored_results.append((
                score,
                OutputData(
                    id=row["id"],
                    score=score,
                    payload=payload,
                    sensitivity=row["sensitivity"],
                    encrypted=bool(row["encrypted"]),
                    expires_at=row["expires_at"]
                )
            ))
        
        # Sort by score (descending) and take top k
        scored_results.sort(key=lambda x: x[0], reverse=True)
        
        return [r[1] for r in scored_results[:limit]]
    
    def _apply_filters(self, payload: Dict[str, Any], filters: Dict[str, Any]) -> bool:
        """Apply metadata filters to a payload."""
        if not filters or not payload:
            return True
        
        for key, value in filters.items():
            if key not in payload:
                return False
            
            if isinstance(value, list):
                if payload[key] not in value:
                    return False
            elif payload[key] != value:
                return False
        
        return True
    
    def _record_access(self, memory_ids: List[str]):
        """Record access events for audit trail."""
        now = datetime.now(timezone.utc).isoformat()
        conn = self._conn
        cursor = conn.cursor()
        
        try:
            cursor.execute("BEGIN")
            
            for memory_id in memory_ids:
                # Update access count
                cursor.execute(f"""
                    UPDATE {self._metadata_table}
                    SET access_count = access_count + 1,
                        last_accessed = ?
                    WHERE id = ?
                """, (now, memory_id))
                
                # Audit log entry
                if self.config.enable_audit:
                    cursor.execute(f"""
                        INSERT INTO {self._audit_table}
                        (id, memory_id, event_type, event_data, timestamp)
                        VALUES (?, ?, ?, ?, ?)
                    """, (str(uuid.uuid4()), memory_id, "access", None, now))
            
            conn.commit()
        except Exception as e:
            conn.rollback()
            logger.warning(f"Failed to record access: {e}")
    
    def _cleanup_expired(self):
        """Remove entries that have passed their TTL."""
        now = datetime.now(timezone.utc).isoformat()
        conn = self._conn
        cursor = conn.cursor()
        
        try:
            cursor.execute("BEGIN")
            
            # Find expired entries
            cursor.execute(f"""
                SELECT id FROM {self._metadata_table}
                WHERE expires_at IS NOT NULL AND expires_at < ?
            """, (now,))
            
            expired_ids = [row["id"] for row in cursor.fetchall()]
            
            if expired_ids:
                # Log deletions
                if self.config.enable_audit:
                    for memory_id in expired_ids:
                        cursor.execute(f"""
                            INSERT INTO {self._audit_table}
                            (id, memory_id, event_type, event_data, timestamp)
                            VALUES (?, ?, ?, ?, ?)
                        """, (str(uuid.uuid4()), memory_id, "ttl_expire", None, now))
                
                # Delete from metadata  
                cursor.execute(f"""
                    DELETE FROM {self._metadata_table}
                    WHERE expires_at IS NOT NULL AND expires_at < ?
                """, (now,))
                
                # Delete from vectors
                cursor.execute(f"""
                    DELETE FROM {self._vectors_table}
                    WHERE id IN ({','.join('?' * len(expired_ids))})
                """, expired_ids)
                
                # Delete from vec0 if available
                if getattr(self, "_use_native_vec", False) and hasattr(self, "_vec_table"):
                    cursor.execute(f"""
                        DELETE FROM {self._vec_table}
                        WHERE id IN ({','.join('?' * len(expired_ids))})
                    """, expired_ids)
                
                logger.info(f"Expired {len(expired_ids)} entries due to TTL")
            
            conn.commit()
        except Exception as e:
            conn.rollback()
            logger.warning(f"Failed to cleanup expired entries: {e}")
    
    def delete(self, vector_id: str) -> bool:
        """
        Delete a vector by ID.
        
        This performs cryptographic deletion by removing the entry entirely.
        For encrypted entries, this means the DEK is destroyed, making
        recovery impossible.
        
        Args:
            vector_id: ID of the vector to delete
        
        Returns:
            True if deleted, False if not found
        """
        with self._lock:
            conn = self._conn
            cursor = conn.cursor()
            
            try:
                cursor.execute("BEGIN")
                
                # Check if exists
                cursor.execute(f"""
                    SELECT id FROM {self._vectors_table} WHERE id = ?
                """, (vector_id,))
                
                if not cursor.fetchone():
                    conn.rollback()
                    logger.warning(f"Vector {vector_id} not found for deletion")
                    return False
                
                now = datetime.now(timezone.utc).isoformat()
                
                # Audit log
                if self.config.enable_audit:
                    cursor.execute(f"""
                        INSERT INTO {self._audit_table}
                        (id, memory_id, event_type, event_data, timestamp)
                        VALUES (?, ?, ?, ?, ?)
                    """, (str(uuid.uuid4()), vector_id, "delete", None, now))
                
                # Delete from all tables
                cursor.execute(f"""
                    DELETE FROM {self._metadata_table} WHERE id = ?
                """, (vector_id,))
                
                cursor.execute(f"""
                    DELETE FROM {self._vectors_table} WHERE id = ?
                """, (vector_id,))
                
                if getattr(self, "_use_native_vec", False) and hasattr(self, "_vec_table"):
                    cursor.execute(f"""
                        DELETE FROM {self._vec_table} WHERE id = ?
                    """, (vector_id,))
                
                conn.commit()
                logger.info(f"Deleted vector {vector_id} from {self.collection_name}")
                return True
                
            except Exception as e:
                conn.rollback()
                logger.error(f"Failed to delete vector {vector_id}: {e}")
                raise
    
    def update(
        self,
        vector_id: str,
        vector: Optional[List[float]] = None,
        payload: Optional[Dict[str, Any]] = None,
        # Closedclaw extensions
        sensitivity: Optional[int] = None,
        tags: Optional[List[str]] = None,
        expires_at: Optional[datetime] = None,
        consent_required: Optional[bool] = None,
    ) -> bool:
        """
        Update a vector and/or its metadata.
        
        Args:
            vector_id: ID of the vector to update
            vector: New vector (optional)
            payload: New payload (optional)
            sensitivity: New sensitivity level (optional)
            tags: New tags (optional)  
            expires_at: New expiry time (optional)
            consent_required: New consent requirement (optional)
        
        Returns:
            True if updated, False if not found
        """
        with self._lock:
            conn = self._conn
            cursor = conn.cursor()
            
            try:
                cursor.execute("BEGIN")
                
                # Check if exists
                cursor.execute(f"""
                    SELECT id FROM {self._vectors_table} WHERE id = ?
                """, (vector_id,))
                
                if not cursor.fetchone():
                    conn.rollback()
                    logger.warning(f"Vector {vector_id} not found for update")
                    return False
                
                now = datetime.now(timezone.utc).isoformat()
                
                # Update vector if provided
                if vector is not None:
                    if len(vector) != self.embedding_dim:
                        raise ValueError(
                            f"Vector has dimension {len(vector)}, "
                            f"expected {self.embedding_dim}"
                        )
                    
                    vector_blob = _serialize_vector(vector)
                    cursor.execute(f"""
                        UPDATE {self._vectors_table}
                        SET vector = ?, updated_at = ?
                        WHERE id = ?
                    """, (vector_blob, now, vector_id))
                    
                    if getattr(self, "_use_native_vec", False) and hasattr(self, "_vec_table"):
                        cursor.execute(f"""
                            UPDATE {self._vec_table}
                            SET embedding = ?
                            WHERE id = ?
                        """, (vector_blob, vector_id))
                
                # Build metadata update
                updates = ["updated_at = ?"]
                params: List[Any] = [now]
                
                if payload is not None:
                    updates.append("payload = ?")
                    params.append(json.dumps(payload))
                
                if sensitivity is not None:
                    updates.append("sensitivity = ?")
                    params.append(sensitivity)
                
                if tags is not None:
                    updates.append("tags = ?")
                    params.append(json.dumps(tags))
                
                if expires_at is not None:
                    updates.append("expires_at = ?")
                    params.append(expires_at.isoformat())
                
                if consent_required is not None:
                    updates.append("consent_required = ?")
                    params.append(1 if consent_required else 0)
                
                params.append(vector_id)
                
                cursor.execute(f"""
                    UPDATE {self._metadata_table}
                    SET {', '.join(updates)}
                    WHERE id = ?
                """, params)
                
                # Audit log
                if self.config.enable_audit:
                    cursor.execute(f"""
                        INSERT INTO {self._audit_table}
                        (id, memory_id, event_type, event_data, timestamp)
                        VALUES (?, ?, ?, ?, ?)
                    """, (
                        str(uuid.uuid4()), 
                        vector_id, 
                        "update",
                        json.dumps({"fields_updated": len(updates) - 1}),
                        now
                    ))
                
                conn.commit()
                logger.info(f"Updated vector {vector_id} in {self.collection_name}")
                return True
                
            except Exception as e:
                conn.rollback()
                logger.error(f"Failed to update vector {vector_id}: {e}")
                raise
    
    def get(self, vector_id: str) -> Optional[OutputData]:
        """
        Retrieve a vector by ID.
        
        Args:
            vector_id: ID of the vector to retrieve
        
        Returns:
            OutputData with vector info, or None if not found
        """
        with self._lock:
            conn = self._conn
            cursor = conn.cursor()
            
            cursor.execute(f"""
                SELECT 
                    v.id,
                    m.payload,
                    m.sensitivity,
                    m.encrypted,
                    m.expires_at
                FROM {self._vectors_table} v
                JOIN {self._metadata_table} m ON v.id = m.id
                WHERE v.id = ?
            """, (vector_id,))
            
            row = cursor.fetchone()
            
            if not row:
                return None
            
            # Record access
            if self.config.enable_audit:
                self._record_access([vector_id])
            
            return OutputData(
                id=row["id"],
                score=None,
                payload=json.loads(row["payload"]) if row["payload"] else {},
                sensitivity=row["sensitivity"],
                encrypted=bool(row["encrypted"]),
                expires_at=row["expires_at"]
            )
    
    def list(
        self,
        filters: Optional[Dict[str, Any]] = None,
        limit: int = 100,
        # Closedclaw extensions
        sensitivity_max: Optional[int] = None,
        include_expired: bool = False,
    ) -> List[OutputData]:
        """
        List all vectors in the collection.
        
        Args:
            filters: Metadata filters
            limit: Maximum results
            sensitivity_max: Maximum sensitivity level
            include_expired: Whether to include expired entries
        
        Returns:
            List of OutputData entries
        """
        with self._lock:
            conn = self._conn
            cursor = conn.cursor()
            
            now = datetime.now(timezone.utc).isoformat()
            
            # Build WHERE clause
            where_clauses = ["1=1"]
            params = []
            
            if sensitivity_max is not None:
                where_clauses.append("m.sensitivity <= ?")
                params.append(sensitivity_max)
            
            if not include_expired:
                where_clauses.append(
                    "(m.expires_at IS NULL OR m.expires_at >= ?)"
                )
                params.append(now)
            
            params.append(limit)
            where_sql = " AND ".join(where_clauses)
            
            cursor.execute(f"""
                SELECT 
                    v.id,
                    m.payload,
                    m.sensitivity,
                    m.encrypted,
                    m.expires_at,
                    m.tags
                FROM {self._vectors_table} v
                JOIN {self._metadata_table} m ON v.id = m.id
                WHERE {where_sql}
                LIMIT ?
            """, params)
            
            results = []
            
            for row in cursor.fetchall():
                payload = json.loads(row["payload"]) if row["payload"] else {}
                
                if filters and not self._apply_filters(payload, filters):
                    continue
                
                results.append(OutputData(
                    id=row["id"],
                    score=None,
                    payload=payload,
                    sensitivity=row["sensitivity"],
                    encrypted=bool(row["encrypted"]),
                    expires_at=row["expires_at"]
                ))
            
            return results
    
    def list_cols(self) -> List[str]:
        """List all collections in the database."""
        with self._lock:
            conn = self._conn
            cursor = conn.cursor()
            
            # Find all tables that match the pattern <prefix>_vectors
            cursor.execute("""
                SELECT name FROM sqlite_master 
                WHERE type='table' AND name LIKE '%_vectors'
                AND name NOT LIKE '%_vec'
            """)
            
            collections = []
            for row in cursor.fetchall():
                table_name = row["name"]
                # Remove _vectors suffix to get collection name
                collection_name = table_name.rsplit("_vectors", 1)[0]
                collections.append(collection_name)
            
            return collections
    
    def delete_col(self) -> bool:
        """Delete the current collection."""
        with self._lock:
            conn = self._conn
            cursor = conn.cursor()
            
            try:
                cursor.execute("BEGIN")
                
                # Drop all tables
                cursor.execute(f"DROP TABLE IF EXISTS {self._metadata_table}")
                cursor.execute(f"DROP TABLE IF EXISTS {self._vectors_table}")
                cursor.execute(f"DROP TABLE IF EXISTS {self._audit_table}")
                
                if getattr(self, "_use_native_vec", False) and hasattr(self, "_vec_table"):
                    cursor.execute(f"DROP TABLE IF EXISTS {self._vec_table}")
                
                conn.commit()
                logger.info(f"Deleted collection {self.collection_name}")
                return True
                
            except Exception as e:
                conn.rollback()
                logger.error(f"Failed to delete collection: {e}")
                raise
    
    def col_info(self) -> Dict[str, Any]:
        """Get information about the current collection."""
        with self._lock:
            conn = self._conn
            cursor = conn.cursor()
            
            # Count entries
            cursor.execute(f"SELECT COUNT(*) as count FROM {self._vectors_table}")
            count = cursor.fetchone()["count"]
            
            # Get sensitivity distribution
            cursor.execute(f"""
                SELECT sensitivity, COUNT(*) as count 
                FROM {self._metadata_table}
                GROUP BY sensitivity
            """)
            sensitivity_dist = {
                row["sensitivity"]: row["count"] 
                for row in cursor.fetchall()
            }
            
            # Get encrypted count
            cursor.execute(f"""
                SELECT SUM(encrypted) as encrypted_count 
                FROM {self._metadata_table}
            """)
            encrypted_count = cursor.fetchone()["encrypted_count"] or 0
            
            return {
                "name": self.collection_name,
                "count": count,
                "dimension": self.embedding_dim,
                "distance_metric": self.distance_metric,
                "sensitivity_distribution": sensitivity_dist,
                "encrypted_count": encrypted_count,
                "audit_enabled": self.config.enable_audit,
            }
    
    def reset(self):
        """Reset the collection (delete and recreate)."""
        logger.warning(f"Resetting collection {self.collection_name}")
        self.delete_col()
        self._init_database()
    
    # Closedclaw-specific methods
    
    def get_by_sensitivity(
        self, 
        sensitivity: int, 
        limit: int = 100
    ) -> List[OutputData]:
        """Get all entries with a specific sensitivity level."""
        return self.list(sensitivity_max=sensitivity, limit=limit)
    
    def get_expiring_soon(
        self, 
        within_hours: int = 24
    ) -> List[OutputData]:
        """Get entries expiring within the specified hours."""
        with self._lock:
            conn = self._conn
            cursor = conn.cursor()
            
            from datetime import timedelta
            now = datetime.now(timezone.utc)
            deadline = (now + timedelta(hours=within_hours)).isoformat()
            
            cursor.execute(f"""
                SELECT 
                    v.id,
                    m.payload,
                    m.sensitivity,
                    m.encrypted,
                    m.expires_at
                FROM {self._vectors_table} v
                JOIN {self._metadata_table} m ON v.id = m.id
                WHERE m.expires_at IS NOT NULL 
                  AND m.expires_at > ?
                  AND m.expires_at <= ?
            """, (now.isoformat(), deadline))
            
            return [
                OutputData(
                    id=row["id"],
                    score=None,
                    payload=json.loads(row["payload"]) if row["payload"] else {},
                    sensitivity=row["sensitivity"],
                    encrypted=bool(row["encrypted"]),
                    expires_at=row["expires_at"]
                )
                for row in cursor.fetchall()
            ]
    
    def get_audit_trail(
        self, 
        memory_id: str,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """Get audit trail for a specific memory."""
        if not self.config.enable_audit:
            return []
        
        with self._lock:
            conn = self._conn
            cursor = conn.cursor()
            
            cursor.execute(f"""
                SELECT id, memory_id, event_type, event_data, timestamp
                FROM {self._audit_table}
                WHERE memory_id = ?
                ORDER BY timestamp DESC
                LIMIT ?
            """, (memory_id, limit))
            
            return [
                {
                    "id": row["id"],
                    "memory_id": row["memory_id"],
                    "event_type": row["event_type"],
                    "event_data": json.loads(row["event_data"]) if row["event_data"] else None,
                    "timestamp": row["timestamp"]
                }
                for row in cursor.fetchall()
            ]
    
    def extend_ttl(
        self, 
        vector_id: str, 
        new_expires_at: datetime
    ) -> bool:
        """Extend the TTL of a memory entry."""
        return self.update(vector_id, expires_at=new_expires_at)
    
    def mark_consent_required(
        self, 
        vector_id: str, 
        required: bool = True
    ) -> bool:
        """Mark a memory as requiring consent for sharing."""
        return self.update(vector_id, consent_required=required)
    
    def get_stats(self) -> Dict[str, Any]:
        """Get detailed statistics about the vector store."""
        with self._lock:
            conn = self._conn
            cursor = conn.cursor()
            
            # Basic counts
            info = self.col_info()
            
            # Most accessed
            cursor.execute(f"""
                SELECT id, access_count 
                FROM {self._metadata_table}
                ORDER BY access_count DESC
                LIMIT 5
            """)
            most_accessed = [
                {"id": row["id"], "count": row["access_count"]}
                for row in cursor.fetchall()
            ]
            
            # Source distribution
            cursor.execute(f"""
                SELECT source, COUNT(*) as count
                FROM {self._metadata_table}
                GROUP BY source
            """)
            source_dist = {
                row["source"]: row["count"]
                for row in cursor.fetchall()
            }
            
            # Get database file size if not in-memory
            db_size_bytes = 0
            if self.path != ":memory:":
                try:
                    db_size_bytes = Path(self.path).stat().st_size
                except:
                    pass
            
            return {
                **info,
                "most_accessed": most_accessed,
                "source_distribution": source_dist,
                "database_size_bytes": db_size_bytes,
                "native_vec_enabled": getattr(self, "_use_native_vec", False),
            }
    
    def vacuum(self):
        """Optimize database by running VACUUM."""
        with self._lock:
            conn = self._conn
            conn.execute("VACUUM")
            logger.info(f"Vacuumed database: {self.path}")
    
    def close(self):
        """Close database connection."""
        if hasattr(self._local, "conn") and self._local.conn:
            self._local.conn.close()
            self._local.conn = None
            logger.info(f"Closed connection to {self.path}")
