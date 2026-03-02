"""
Persistent Storage for Audit Entries and Consent Receipts.

Uses SQLite for durable, append-only storage so that records survive
server restarts. This is critical for the audit hash chain and for
consent receipt legal relevance.
"""

import json
import logging
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, List, Dict, Any

logger = logging.getLogger(__name__)


class PersistentStore:
    """SQLite-backed persistent store for audit and consent data."""

    def __init__(self, db_path: Optional[Path] = None):
        if db_path is None:
            db_path = Path.home() / ".closedclaw" / "audit.db"
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self.db_path = db_path
        self._conn: Optional[sqlite3.Connection] = None
        self._write_lock = threading.Lock()
        self._init_db()

    @property
    def conn(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
            self._conn.row_factory = sqlite3.Row
            # Performance PRAGMAs
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA synchronous=NORMAL")
            self._conn.execute("PRAGMA cache_size=-8000")  # 8MB cache
            self._conn.execute("PRAGMA temp_store=MEMORY")
            self._conn.execute("PRAGMA mmap_size=67108864")  # 64MB mmap
        return self._conn

    def _init_db(self) -> None:
        c = self.conn
        c.executescript("""
            CREATE TABLE IF NOT EXISTS audit_entries (
                entry_id TEXT PRIMARY KEY,
                request_id TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                provider TEXT NOT NULL,
                model TEXT NOT NULL DEFAULT '',
                memories_retrieved INTEGER DEFAULT 0,
                memories_used INTEGER DEFAULT 0,
                memory_ids TEXT DEFAULT '[]',
                redactions_applied INTEGER DEFAULT 0,
                blocked_memories INTEGER DEFAULT 0,
                consent_required INTEGER DEFAULT 0,
                consent_receipt_id TEXT,
                context_tokens INTEGER DEFAULT 0,
                total_tokens INTEGER,
                prev_hash TEXT,
                entry_hash TEXT,
                signature TEXT,
                data TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS consent_receipts (
                receipt_id TEXT PRIMARY KEY,
                timestamp TEXT NOT NULL,
                memory_id TEXT NOT NULL,
                memory_hash TEXT NOT NULL,
                provider TEXT NOT NULL,
                sensitivity_level INTEGER NOT NULL,
                user_decision TEXT NOT NULL,
                rule_triggered TEXT,
                user_pubkey TEXT,
                signature TEXT,
                data TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS consent_pending (
                request_id TEXT PRIMARY KEY,
                created_at TEXT NOT NULL,
                memory_id TEXT NOT NULL,
                memory_text TEXT NOT NULL,
                memory_hash TEXT NOT NULL,
                sensitivity INTEGER NOT NULL,
                provider TEXT NOT NULL,
                rule_triggered TEXT,
                data TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS memory_metadata (
                memory_id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL DEFAULT 'default',
                content TEXT NOT NULL DEFAULT '',
                sensitivity INTEGER NOT NULL DEFAULT 1,
                tags TEXT NOT NULL DEFAULT '[]',
                source TEXT NOT NULL DEFAULT 'manual',
                expires_at TEXT,
                content_hash TEXT,
                encrypted INTEGER NOT NULL DEFAULT 0,
                dek_enc TEXT,
                dek_nonce TEXT,
                ciphertext TEXT,
                nonce TEXT,
                access_count INTEGER NOT NULL DEFAULT 0,
                last_accessed TEXT,
                consent_required INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT
            );

            CREATE TABLE IF NOT EXISTS consent_preferences (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                preference_type TEXT NOT NULL,
                preference_key TEXT NOT NULL,
                action TEXT NOT NULL,
                created_at TEXT NOT NULL,
                UNIQUE(preference_type, preference_key)
            );

            CREATE INDEX IF NOT EXISTS idx_audit_timestamp ON audit_entries(timestamp);
            CREATE INDEX IF NOT EXISTS idx_audit_provider ON audit_entries(provider);
            CREATE INDEX IF NOT EXISTS idx_consent_memory ON consent_receipts(memory_id);
            CREATE INDEX IF NOT EXISTS idx_meta_user ON memory_metadata(user_id);
            CREATE INDEX IF NOT EXISTS idx_meta_sensitivity ON memory_metadata(sensitivity);
            CREATE INDEX IF NOT EXISTS idx_meta_expires ON memory_metadata(expires_at);
        """)
        c.commit()

    # ------------------------------------------------------------------
    # Audit Entries
    # ------------------------------------------------------------------

    def save_audit_entry(self, entry_dict: Dict[str, Any]) -> None:
        """Save an audit entry to persistent storage."""
        with self._write_lock:
            self.conn.execute(
                """INSERT OR REPLACE INTO audit_entries
                   (entry_id, request_id, timestamp, provider, model,
                    memories_retrieved, memories_used, memory_ids,
                    redactions_applied, blocked_memories, consent_required,
                    consent_receipt_id, context_tokens, total_tokens,
                    prev_hash, entry_hash, signature, data)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    entry_dict.get("entry_id", ""),
                    entry_dict.get("request_id", ""),
                    entry_dict.get("timestamp", datetime.now(timezone.utc).isoformat()),
                    entry_dict.get("provider", ""),
                    entry_dict.get("model", ""),
                    entry_dict.get("memories_retrieved", 0),
                    entry_dict.get("memories_used", 0),
                    json.dumps(entry_dict.get("memory_ids", [])),
                    entry_dict.get("redactions_applied", 0),
                    entry_dict.get("blocked_memories", 0),
                    1 if entry_dict.get("consent_required") else 0,
                    entry_dict.get("consent_receipt_id"),
                    entry_dict.get("context_tokens", 0),
                    entry_dict.get("total_tokens"),
                    entry_dict.get("prev_hash"),
                    entry_dict.get("entry_hash"),
                    entry_dict.get("signature"),
                    json.dumps(entry_dict, default=str),
                ),
            )
            self.conn.commit()

    def load_audit_entries(
        self,
        limit: int = 1000,
        offset: int = 0,
        provider: Optional[str] = None,
        from_time: Optional[str] = None,
        to_time: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Load audit entries with optional filtering."""
        query = "SELECT data FROM audit_entries WHERE 1=1"
        params: list = []

        if provider:
            query += " AND provider = ?"
            params.append(provider)
        if from_time:
            query += " AND timestamp >= ?"
            params.append(from_time)
        if to_time:
            query += " AND timestamp <= ?"
            params.append(to_time)

        query += " ORDER BY timestamp DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])

        rows = self.conn.execute(query, params).fetchall()
        return [json.loads(row["data"]) for row in rows]

    def get_last_audit_hash(self) -> Optional[str]:
        """Get the hash of the last audit entry for chain continuity."""
        row = self.conn.execute(
            "SELECT entry_hash FROM audit_entries ORDER BY rowid DESC LIMIT 1"
        ).fetchone()
        return row["entry_hash"] if row else None

    def count_audit_entries(self) -> int:
        row = self.conn.execute("SELECT COUNT(*) as c FROM audit_entries").fetchone()
        return row["c"] if row else 0

    # ------------------------------------------------------------------
    # Consent Receipts
    # ------------------------------------------------------------------

    def save_consent_receipt(self, receipt_dict: Dict[str, Any]) -> None:
        with self._write_lock:
            self.conn.execute(
                """INSERT OR REPLACE INTO consent_receipts
                   (receipt_id, timestamp, memory_id, memory_hash, provider,
                    sensitivity_level, user_decision, rule_triggered,
                    user_pubkey, signature, data)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    receipt_dict.get("receipt_id", ""),
                    receipt_dict.get("timestamp", datetime.now(timezone.utc).isoformat()),
                    receipt_dict.get("memory_id", ""),
                    receipt_dict.get("memory_hash", ""),
                    receipt_dict.get("provider", ""),
                    receipt_dict.get("sensitivity_level", 0),
                    receipt_dict.get("user_decision", ""),
                    receipt_dict.get("rule_triggered"),
                    receipt_dict.get("user_pubkey"),
                    receipt_dict.get("signature"),
                    json.dumps(receipt_dict, default=str),
                ),
            )
            self.conn.commit()

    def load_consent_receipts(
        self,
        memory_id: Optional[str] = None,
        provider: Optional[str] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        query = "SELECT data FROM consent_receipts WHERE 1=1"
        params: list = []
        if memory_id:
            query += " AND memory_id = ?"
            params.append(memory_id)
        if provider:
            query += " AND provider = ?"
            params.append(provider)
        query += " ORDER BY timestamp DESC LIMIT ?"
        params.append(limit)

        rows = self.conn.execute(query, params).fetchall()
        return [json.loads(row["data"]) for row in rows]

    # ------------------------------------------------------------------
    # Consent Pending
    # ------------------------------------------------------------------

    def save_pending_consent(self, pending_dict: Dict[str, Any]) -> None:
        with self._write_lock:
            self.conn.execute(
                """INSERT OR REPLACE INTO consent_pending
                   (request_id, created_at, memory_id, memory_text, memory_hash,
                    sensitivity, provider, rule_triggered, data)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    pending_dict.get("request_id", ""),
                    pending_dict.get("created_at", datetime.now(timezone.utc).isoformat()),
                    pending_dict.get("memory_id", ""),
                    pending_dict.get("memory_text", ""),
                    pending_dict.get("memory_hash", ""),
                    pending_dict.get("sensitivity", 0),
                    pending_dict.get("provider", ""),
                    pending_dict.get("rule_triggered"),
                    json.dumps(pending_dict, default=str),
                ),
            )
            self.conn.commit()

    def load_pending_consents(self) -> List[Dict[str, Any]]:
        rows = self.conn.execute(
            "SELECT data FROM consent_pending ORDER BY created_at DESC"
        ).fetchall()
        return [json.loads(row["data"]) for row in rows]

    def delete_pending_consent(self, request_id: str) -> None:
        with self._write_lock:
            self.conn.execute(
                "DELETE FROM consent_pending WHERE request_id = ?", (request_id,)
            )
            self.conn.commit()

    # ------------------------------------------------------------------
    # Memory Metadata
    # ------------------------------------------------------------------

    def save_memory_metadata(self, meta: Dict[str, Any]) -> None:
        """Upsert extended metadata for a memory."""
        with self._write_lock:
            self.conn.execute(
                """INSERT OR REPLACE INTO memory_metadata
                   (memory_id, user_id, content, sensitivity, tags, source,
                    expires_at, content_hash, encrypted, dek_enc, dek_nonce,
                    ciphertext, nonce, access_count, last_accessed,
                    consent_required, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    meta["memory_id"],
                    meta.get("user_id", "default"),
                    meta.get("content", ""),
                    meta.get("sensitivity", 1),
                    json.dumps(meta.get("tags", [])),
                    meta.get("source", "manual"),
                    meta.get("expires_at"),
                    meta.get("content_hash"),
                    1 if meta.get("encrypted") else 0,
                    meta.get("dek_enc"),
                    meta.get("dek_nonce"),
                    meta.get("ciphertext"),
                    meta.get("nonce"),
                    meta.get("access_count", 0),
                    meta.get("last_accessed"),
                    1 if meta.get("consent_required") else 0,
                    meta.get("created_at", datetime.now(timezone.utc).isoformat()),
                    datetime.now(timezone.utc).isoformat(),
                ),
            )
            self.conn.commit()

    def load_memory_metadata(self, memory_id: str) -> Optional[Dict[str, Any]]:
        """Load extended metadata for a single memory."""
        row = self.conn.execute(
            "SELECT * FROM memory_metadata WHERE memory_id = ?", (memory_id,)
        ).fetchone()
        if not row:
            return None
        return self._row_to_meta(row)

    def load_memory_metadata_batch(self, memory_ids: List[str]) -> Dict[str, Dict[str, Any]]:
        """Load metadata for many memory IDs in one query."""
        ids = [memory_id for memory_id in memory_ids if memory_id]
        if not ids:
            return {}

        placeholders = ",".join("?" for _ in ids)
        rows = self.conn.execute(
            f"SELECT * FROM memory_metadata WHERE memory_id IN ({placeholders})",
            ids,
        ).fetchall()
        return {row["memory_id"]: self._row_to_meta(row) for row in rows}

    def load_all_memory_metadata(
        self,
        user_id: Optional[str] = None,
        sensitivity_max: Optional[int] = None,
        tags: Optional[List[str]] = None,
        limit: Optional[int] = None,
        include_expired: bool = False,
    ) -> List[Dict[str, Any]]:
        """Load all extended metadata with optional filtering."""
        query = "SELECT * FROM memory_metadata WHERE 1=1"
        params: list = []

        if user_id:
            query += " AND user_id = ?"
            params.append(user_id)
        if sensitivity_max is not None:
            query += " AND sensitivity <= ?"
            params.append(sensitivity_max)
        if not include_expired:
            query += " AND (expires_at IS NULL OR expires_at > ?)"
            params.append(datetime.now(timezone.utc).isoformat())
        # Push tag filtering into SQL with LIKE clauses for indexed scan
        if tags:
            tag_clauses = ["tags LIKE ?" for _ in tags]
            query += " AND (" + " OR ".join(tag_clauses) + ")"
            params.extend(f"%\"{tag}\"%" for tag in tags)

        query += " ORDER BY created_at DESC"
        if limit is not None:
            query += " LIMIT ?"
            params.append(limit)

        rows = self.conn.execute(query, params).fetchall()
        return [self._row_to_meta(row) for row in rows]

    def update_memory_metadata(self, memory_id: str, updates: Dict[str, Any]) -> bool:
        """Update specific fields in memory metadata using a partial SQL update."""
        if not updates:
            return False

        allowed_fields = {
            "user_id",
            "content",
            "sensitivity",
            "tags",
            "source",
            "expires_at",
            "content_hash",
            "encrypted",
            "dek_enc",
            "dek_nonce",
            "ciphertext",
            "nonce",
            "access_count",
            "last_accessed",
            "consent_required",
            "created_at",
        }

        set_parts: List[str] = []
        values: List[Any] = []
        for key, value in updates.items():
            if key not in allowed_fields:
                continue
            if key == "tags":
                value = json.dumps(value if value is not None else [])
            elif key in {"encrypted", "consent_required"}:
                value = 1 if value else 0
            set_parts.append(f"{key} = ?")
            values.append(value)

        if not set_parts:
            return False

        set_parts.append("updated_at = ?")
        values.append(datetime.now(timezone.utc).isoformat())
        values.append(memory_id)

        with self._write_lock:
            cursor = self.conn.execute(
                f"UPDATE memory_metadata SET {', '.join(set_parts)} WHERE memory_id = ?",
                values,
            )
            self.conn.commit()
        return cursor.rowcount > 0

    def delete_memory_metadata(self, memory_id: str) -> bool:
        """Delete metadata for a memory."""
        with self._write_lock:
            cursor = self.conn.execute(
                "DELETE FROM memory_metadata WHERE memory_id = ?", (memory_id,)
            )
            self.conn.commit()
        return cursor.rowcount > 0

    def delete_all_memory_metadata(self, user_id: str) -> int:
        """Delete all metadata for a user. Returns count deleted."""
        with self._write_lock:
            cursor = self.conn.execute(
                "DELETE FROM memory_metadata WHERE user_id = ?", (user_id,)
            )
            self.conn.commit()
        return cursor.rowcount

    def increment_access_count(self, memory_id: str) -> None:
        """Increment access count and update last_accessed."""
        with self._write_lock:
            self.conn.execute(
                """UPDATE memory_metadata
                   SET access_count = access_count + 1,
                       last_accessed = ?
                   WHERE memory_id = ?""",
                (datetime.now(timezone.utc).isoformat(), memory_id),
            )
            self.conn.commit()

    def increment_access_counts(self, memory_ids: List[str]) -> None:
        """Increment access count for multiple memories in one transaction."""
        ids = [memory_id for memory_id in memory_ids if memory_id]
        if not ids:
            return

        now = datetime.now(timezone.utc).isoformat()
        with self._write_lock:
            with self.conn:
                self.conn.executemany(
                    """UPDATE memory_metadata
                       SET access_count = access_count + 1,
                           last_accessed = ?
                       WHERE memory_id = ?""",
                    [(now, memory_id) for memory_id in ids],
                )

    def get_tags_counts(self, user_id: Optional[str] = None) -> Dict[str, int]:
        """Get tag counts across all memories."""
        query = "SELECT tags FROM memory_metadata WHERE 1=1"
        params: list = []
        if user_id:
            query += " AND user_id = ?"
            params.append(user_id)

        rows = self.conn.execute(query, params).fetchall()
        tag_counts: Dict[str, int] = {}
        for row in rows:
            for tag in json.loads(row["tags"]):
                tag_counts[tag] = tag_counts.get(tag, 0) + 1
        return tag_counts

    def get_expiring_memories(self, within_days: int = 7) -> List[Dict[str, Any]]:
        """Get memories expiring within N days."""
        from datetime import timedelta
        cutoff = (datetime.now(timezone.utc) + timedelta(days=within_days)).isoformat()
        rows = self.conn.execute(
            """SELECT * FROM memory_metadata
               WHERE expires_at IS NOT NULL AND expires_at <= ?
               ORDER BY expires_at ASC""",
            (cutoff,),
        ).fetchall()
        return [self._row_to_meta(row) for row in rows]

    def count_memories(self, user_id: Optional[str] = None) -> int:
        """Count memories, optionally by user."""
        query = "SELECT COUNT(*) as c FROM memory_metadata"
        params: list = []
        if user_id:
            query += " WHERE user_id = ?"
            params.append(user_id)
        row = self.conn.execute(query, params).fetchone()
        return row["c"] if row else 0

    def _row_to_meta(self, row: sqlite3.Row) -> Dict[str, Any]:
        """Convert a sqlite3 Row to a dict with parsed JSON fields."""
        d = dict(row)
        d["tags"] = json.loads(d.get("tags", "[]"))
        d["encrypted"] = bool(d.get("encrypted", 0))
        d["consent_required"] = bool(d.get("consent_required", 0))
        return d

    # ------------------------------------------------------------------
    # Consent Preferences
    # ------------------------------------------------------------------

    def save_memory_metadata_batch(self, metas: List[Dict[str, Any]]) -> int:
        """Batch-insert memory metadata in a single transaction."""
        if not metas:
            return 0
        now = datetime.now(timezone.utc).isoformat()
        rows = []
        for meta in metas:
            rows.append((
                meta["memory_id"],
                meta.get("user_id", "default"),
                meta.get("content", ""),
                meta.get("sensitivity", 1),
                json.dumps(meta.get("tags", [])),
                meta.get("source", "manual"),
                meta.get("expires_at"),
                meta.get("content_hash"),
                1 if meta.get("encrypted") else 0,
                meta.get("dek_enc"),
                meta.get("dek_nonce"),
                meta.get("ciphertext"),
                meta.get("nonce"),
                meta.get("access_count", 0),
                meta.get("last_accessed"),
                1 if meta.get("consent_required") else 0,
                meta.get("created_at", now),
                now,
            ))
        with self._write_lock:
            with self.conn:
                self.conn.executemany(
                    """INSERT OR REPLACE INTO memory_metadata
                       (memory_id, user_id, content, sensitivity, tags, source,
                        expires_at, content_hash, encrypted, dek_enc, dek_nonce,
                        ciphertext, nonce, access_count, last_accessed,
                        consent_required, created_at, updated_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    rows,
                )
        return len(rows)

    def save_consent_preference(self, pref_type: str, pref_key: str, action: str) -> None:
        """Save a consent preference (remember_for_provider or remember_for_tag)."""
        with self._write_lock:
            self.conn.execute(
                """INSERT OR REPLACE INTO consent_preferences
                   (preference_type, preference_key, action, created_at)
                   VALUES (?, ?, ?, ?)""",
                (pref_type, pref_key, action, datetime.now(timezone.utc).isoformat()),
            )
            self.conn.commit()

    def get_consent_preference(self, pref_type: str, pref_key: str) -> Optional[str]:
        """Get a consent preference action, if stored."""
        row = self.conn.execute(
            "SELECT action FROM consent_preferences WHERE preference_type = ? AND preference_key = ?",
            (pref_type, pref_key),
        ).fetchone()
        return row["action"] if row else None

    def close(self) -> None:
        if self._conn:
            self._conn.close()
            self._conn = None


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

_store: Optional[PersistentStore] = None


def get_persistent_store(db_path: Optional[Path] = None) -> PersistentStore:
    """Get or create the singleton PersistentStore."""
    global _store
    if _store is None:
        _store = PersistentStore(db_path)
    return _store
