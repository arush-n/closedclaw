"""
Closedclaw Extended Memory Module

Wraps mem0 with closedclaw's extended schema:
- Sensitivity classification
- TTL and cryptographic deletion
- Encryption at rest (AES-256-GCM envelope encryption)
- Consent-aware write path
- Persistent extended metadata via SQLite
"""

import hashlib
import logging
import uuid
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List
from pathlib import Path

from closedclaw.api.core.storage import get_persistent_store, PersistentStore
from closedclaw.api.core.crypto import EnvelopeEncryption

logger = logging.getLogger(__name__)


class ClosedclawMemory:
    """
    Extended mem0 wrapper with privacy and governance features.
    
    Adds sensitivity classification, encryption, TTL, and consent tracking
    to the base mem0 Memory class.  All extended metadata is persisted in
    SQLite and survives server restarts.
    """

    # Pre-computed keyword sets for sensitivity classification (class-level)
    _L3_TAGS = frozenset({'health', 'medical', 'legal', 'financial', 'ssn', 'password'})
    _L3_KW = frozenset({
        'diagnosis', 'prescription', 'ssn', 'social security',
        'password', 'credit card', 'bank account', 'lawsuit',
    })
    _L2_TAGS = frozenset({'address', 'relationship', 'politics', 'religion'})
    _L2_KW = frozenset({
        'my address', 'home address', 'boyfriend', 'girlfriend',
        'husband', 'wife', 'salary', 'income', 'political',
    })
    _L1_KW = frozenset({'my name', 'i work', 'my job', 'i live'})

    def __init__(
        self,
        config: Optional[Dict[str, Any]] = None,
        enable_encryption: bool = True,
        default_sensitivity: int = 1,
        require_consent_level: int = 2,
    ):
        self.enable_encryption = enable_encryption
        self.default_sensitivity = default_sensitivity
        self.require_consent_level = require_consent_level
        self._mem0 = None
        self._config = config
        self._store: PersistentStore = get_persistent_store()
        
        # Envelope encryption
        self._envelope: Optional[EnvelopeEncryption] = None
        if enable_encryption:
            try:
                self._init_encryption()
            except Exception as e:
                logger.warning(f"Encryption init failed, storing plaintext: {e}")
                self._envelope = None
        
        # Mock memory storage (used when mem0 is not installed)
        self._mock_memories: Dict[str, Dict[str, Any]] = {}
        self._load_mock_from_store()
        
        # Initialize mem0
        self._init_mem0(config)
    
    # ------------------------------------------------------------------
    # Encryption helpers
    # ------------------------------------------------------------------

    def _init_encryption(self) -> None:
        """Initialise envelope encryption with a derived KEK."""
        import os
        keys_dir = Path.home() / ".closedclaw" / "keys"
        keys_dir.mkdir(parents=True, exist_ok=True)
        kek_salt_path = keys_dir / "kek.salt"
        passphrase = os.environ.get(
            "CLOSEDCLAW_KEK_PASSPHRASE",
            "",
        )
        if not passphrase:
            # Fall back to a per-install random passphrase persisted on disk
            passphrase_path = keys_dir / "kek.passphrase"
            if passphrase_path.exists():
                passphrase = passphrase_path.read_text().strip()
            else:
                import secrets
                passphrase = secrets.token_urlsafe(48)
                passphrase_path.write_text(passphrase)
                try:
                    passphrase_path.chmod(0o600)
                except OSError:
                    pass  # Windows may not support chmod
        if kek_salt_path.exists():
            salt = kek_salt_path.read_bytes()
            kek, _ = EnvelopeEncryption.derive_kek(passphrase, salt)
        else:
            kek, salt = EnvelopeEncryption.derive_kek(passphrase)
            kek_salt_path.write_bytes(salt)
        self._envelope = EnvelopeEncryption(kek)
        logger.info("Envelope encryption initialised")

    def _encrypt_content(self, content: str) -> Optional[Dict[str, str]]:
        """Encrypt content if envelope encryption is available."""
        if self._envelope:
            try:
                return self._envelope.encrypt_memory(content)
            except Exception as e:
                logger.warning(f"Encryption failed: {e}")
        return None

    def _decrypt_content(self, meta: Dict[str, Any]) -> Optional[str]:
        """Decrypt content from stored metadata."""
        if self._envelope and meta.get("encrypted") and meta.get("ciphertext"):
            try:
                return self._envelope.decrypt_memory({
                    "ciphertext": meta["ciphertext"],
                    "nonce": meta["nonce"],
                    "dek_enc": meta["dek_enc"],
                    "dek_nonce": meta["dek_nonce"],
                })
            except Exception as e:
                logger.warning(f"Decryption failed: {e}")
        return None

    # ------------------------------------------------------------------
    # Persistent mock store bootstrap
    # ------------------------------------------------------------------

    def _load_mock_from_store(self) -> None:
        """Load mock memories from persistent store on startup."""
        all_meta = self._store.load_all_memory_metadata()
        for meta in all_meta:
            mem_id = meta["memory_id"]
            content = meta.get("content", "")
            # Try to decrypt
            decrypted = self._decrypt_content(meta)
            if decrypted:
                content = decrypted
            self._mock_memories[mem_id] = {
                "id": mem_id,
                "memory": content,
                "user_id": meta.get("user_id", "default"),
                "metadata": meta,
            }
    
    def _init_mem0(self, config: Optional[Dict[str, Any]] = None):
        """Initialize the underlying mem0 instance."""
        try:
            from mem0 import Memory
            
            if config:
                self._mem0 = Memory.from_config(config)
            else:
                self._mem0 = Memory()
            
            logger.info("mem0 initialized successfully")
        except ImportError:
            logger.warning("mem0 not installed, using mock memory store")
            self._mem0 = None
        except Exception as e:
            logger.error(f"Failed to initialize mem0: {e}")
            self._mem0 = None
    
    def _compute_content_hash(self, content: str) -> str:
        """Compute SHA-256 hash of content."""
        return hashlib.sha256(content.encode('utf-8')).hexdigest()
    
    def _classify_sensitivity(
        self, 
        content: str, 
        tags: Optional[List[str]] = None,
        user_override: Optional[int] = None
    ) -> int:
        """
        Classify memory sensitivity level.
        
        Priority:
        1. User override
        2. Tag-based rules
        3. Keyword heuristics
        4. Default
        """
        if user_override is not None:
            return max(0, min(3, user_override))
        
        normalized_tags = frozenset(tag.lower() for tag in tags) if tags else frozenset()
        content_lower = content.lower()
        
        # Level 3 - Sensitive
        if self._L3_TAGS & normalized_tags:
            return 3
        if any(kw in content_lower for kw in self._L3_KW):
            return 3
        
        # Level 2 - Personal  
        if self._L2_TAGS & normalized_tags:
            return 2
        if any(kw in content_lower for kw in self._L2_KW):
            return 2
        
        # Level 1 - General personal
        if any(kw in content_lower for kw in self._L1_KW):
            return 1
        
        return self.default_sensitivity
    
    def add(
        self,
        content: str,
        *,
        user_id: str = "default",
        sensitivity: Optional[int] = None,
        tags: Optional[List[str]] = None,
        source: str = "manual",
        expires_at: Optional[datetime] = None,
        metadata: Optional[Dict[str, Any]] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """Add a memory with encryption + persistent metadata."""
        tags = tags or []
        metadata = metadata or {}
        now = datetime.now(timezone.utc).isoformat()

        final_sensitivity = self._classify_sensitivity(content, tags, sensitivity)
        content_hash = self._compute_content_hash(content)
        consent_required = final_sensitivity >= self.require_consent_level

        # Encrypt content
        envelope_data = self._encrypt_content(content) if self.enable_encryption else None

        extended_meta: Dict[str, Any] = {
            "sensitivity": final_sensitivity,
            "tags": tags,
            "source": source,
            "expires_at": expires_at.isoformat() if expires_at else None,
            "content_hash": content_hash,
            "encrypted": envelope_data is not None,
            "access_count": 0,
            "last_accessed": None,
            "consent_required": consent_required,
            "created_at": now,
        }
        if envelope_data:
            extended_meta.update({
                "dek_enc": envelope_data["dek_enc"],
                "dek_nonce": envelope_data["dek_nonce"],
                "ciphertext": envelope_data["ciphertext"],
                "nonce": envelope_data["nonce"],
            })

        full_metadata = {**metadata, **extended_meta}

        def _persist(mem_id: str) -> None:
            self._store.save_memory_metadata({
                "memory_id": mem_id,
                "user_id": user_id,
                "content": content if not envelope_data else "",
                **extended_meta,
            })

        if self._mem0:
            try:
                result = self._mem0.add(
                    messages=content,
                    user_id=user_id,
                    metadata=full_metadata,
                    **kwargs
                )
                if result and "results" in result:
                    for mem in result["results"]:
                        mid = mem.get("id")
                        if mid:
                            _persist(mid)
                return {
                    "result": result,
                    "extended": extended_meta,
                    "content_hash": content_hash,
                }
            except Exception as e:
                logger.error(f"Failed to add memory: {e}")
                raise
        else:
            mem_id = str(uuid.uuid4())
            self._mock_memories[mem_id] = {
                "id": mem_id,
                "memory": content,
                "user_id": user_id,
                "metadata": full_metadata,
            }
            _persist(mem_id)
            return {
                "result": {"results": [{"id": mem_id, "memory": content}]},
                "extended": extended_meta,
                "content_hash": content_hash,
            }
    
    def search(
        self,
        query: str,
        *,
        user_id: str = "default",
        sensitivity_max: Optional[int] = None,
        tags: Optional[List[str]] = None,
        limit: int = 10,
        **kwargs
    ) -> Dict[str, Any]:
        """Search memories with privacy filtering (persistent metadata)."""
        if self._mem0:
            try:
                results = self._mem0.search(
                    query=query, user_id=user_id, limit=limit * 2, **kwargs
                )
                tags_set = set(tags) if tags else None
                filtered = []
                candidates = results.get("results", [])
                candidate_ids = [mem.get("id") for mem in candidates if mem.get("id")]
                stored_meta = self._store.load_memory_metadata_batch(candidate_ids)
                accessed_ids: List[str] = []

                for mem in candidates:
                    mem_id = mem.get("id")
                    stored = stored_meta.get(mem_id) if mem_id else None
                    sens = stored["sensitivity"] if stored else mem.get("metadata", {}).get("sensitivity", 0)
                    mt = stored["tags"] if stored else mem.get("metadata", {}).get("tags", [])
                    if sensitivity_max is not None and sens > sensitivity_max:
                        continue
                    if tags_set and not tags_set.intersection(mt):
                        continue
                    if mem_id:
                        accessed_ids.append(mem_id)
                    mem["sensitivity"] = sens
                    mem["tags"] = mt
                    mem["consent_required"] = stored.get("consent_required", sens >= 3) if stored else sens >= 3
                    if stored:
                        mem["encrypted"] = stored.get("encrypted", False)
                        mem["content_hash"] = stored.get("content_hash")
                        mem["source"] = stored.get("source", "conversation")
                        mem["access_count"] = stored.get("access_count", 0)
                        mem["last_accessed"] = stored.get("last_accessed")
                        mem["expires_at"] = stored.get("expires_at")
                    filtered.append(mem)
                    if len(filtered) >= limit:
                        break

                if accessed_ids:
                    self._store.increment_access_counts(accessed_ids)
                return {"results": filtered, "count": len(filtered), "query": query}
            except Exception as e:
                logger.error(f"Search failed: {e}")
                raise
        else:
            filtered = []
            query_lower = query.lower()
            tags_set = frozenset(tags) if tags else None
            _strip_chars = ".,!?;:\"'()[]{}"
            query_tokens = frozenset(
                t for raw in query_lower.split()
                if len(t := raw.strip(_strip_chars)) >= 3
            )
            all_meta = self._store.load_memory_metadata_batch(list(self._mock_memories.keys()))
            accessed_ids: List[str] = []
            for mem_id, mem in self._mock_memories.items():
                content = mem.get("memory", "")
                mem_user = mem.get("user_id", "default")
                if mem_user != user_id:
                    continue
                content_lower = content.lower()
                is_substring_match = query_lower in content_lower
                if not is_substring_match and query_tokens:
                    content_tokens = frozenset(
                        t for raw in content_lower.split()
                        if len(t := raw.strip(_strip_chars)) >= 3
                    )
                    token_overlap = len(query_tokens & content_tokens)
                else:
                    token_overlap = 1 if is_substring_match else 0
                if not is_substring_match and token_overlap == 0:
                    continue
                stored = all_meta.get(mem_id)
                sens = stored["sensitivity"] if stored else 0
                mt = stored["tags"] if stored else []
                if sensitivity_max is not None and sens > sensitivity_max:
                    continue
                if tags_set and not tags_set.intersection(mt):
                    continue
                accessed_ids.append(mem_id)
                filtered.append({
                    "id": mem_id,
                    "memory": content,
                    "user_id": mem_user,
                    "sensitivity": sens,
                    "tags": mt,
                    "consent_required": stored.get("consent_required", sens >= 3) if stored else sens >= 3,
                    "encrypted": stored.get("encrypted", False) if stored else False,
                    "content_hash": stored.get("content_hash") if stored else None,
                    "source": stored.get("source", "conversation") if stored else "conversation",
                    "access_count": stored.get("access_count", 0) if stored else 0,
                    "last_accessed": stored.get("last_accessed") if stored else None,
                    "expires_at": stored.get("expires_at") if stored else None,
                    "score": float(token_overlap) if token_overlap > 0 else 1.0,
                })
                if len(filtered) >= limit:
                    break

            if accessed_ids:
                self._store.increment_access_counts(accessed_ids)
            return {"results": filtered, "count": len(filtered), "query": query}
    
    def get(self, memory_id: str) -> Optional[Dict[str, Any]]:
        """Get a single memory by ID with decrypted content."""
        stored = self._store.load_memory_metadata(memory_id)
        if self._mem0:
            try:
                result = self._mem0.get(memory_id)
                if result and stored:
                    result["sensitivity"] = stored.get("sensitivity", 0)
                    result["tags"] = stored.get("tags", [])
                    result["consent_required"] = stored.get("consent_required", False)
                    result["content_hash"] = stored.get("content_hash")
                    result["encrypted"] = stored.get("encrypted", False)
                    result["source"] = stored.get("source", "manual")
                    result["access_count"] = stored.get("access_count", 0)
                    result["last_accessed"] = stored.get("last_accessed")
                    result["expires_at"] = stored.get("expires_at")
                return result
            except Exception as e:
                logger.error(f"Get failed: {e}")
                raise
        else:
            mem = self._mock_memories.get(memory_id)
            if mem:
                extra = {}
                if stored:
                    extra = {
                        "sensitivity": stored.get("sensitivity", 0),
                        "tags": stored.get("tags", []),
                        "consent_required": stored.get("consent_required", False),
                        "content_hash": stored.get("content_hash"),
                        "encrypted": stored.get("encrypted", False),
                        "source": stored.get("source", "manual"),
                        "access_count": stored.get("access_count", 0),
                        "last_accessed": stored.get("last_accessed"),
                        "expires_at": stored.get("expires_at"),
                    }
                return {**mem, **extra}
            return None
    
    def get_all(
        self,
        user_id: str = "default",
        *,
        sensitivity_max: Optional[int] = None,
        tags: Optional[List[str]] = None,
        limit: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Get memories for a user with optional filtering (persistent metadata)."""
        if self._mem0:
            try:
                results = self._mem0.get_all(user_id=user_id)
                filtered_results = []
                tags_set = set(tags) if tags else None
                candidates = results.get("results", [])
                candidate_ids = [mem.get("id") for mem in candidates if mem.get("id")]
                stored_meta = self._store.load_memory_metadata_batch(candidate_ids)

                for mem in candidates:
                    mem_id = mem.get("id")
                    stored = stored_meta.get(mem_id) if mem_id else None
                    s = stored["sensitivity"] if stored else 0
                    t = stored["tags"] if stored else []
                    if sensitivity_max is not None and s > sensitivity_max:
                        continue
                    if tags_set and not tags_set.intersection(t):
                        continue
                    mem["sensitivity"] = s
                    mem["tags"] = t
                    filtered_results.append(mem)
                    if limit is not None and len(filtered_results) >= limit:
                        break
                return {"results": filtered_results, "count": len(filtered_results)}
            except Exception as e:
                logger.error(f"Get all failed: {e}")
                raise
        else:
            results = []
            tags_set = set(tags) if tags else None
            all_ids = list(self._mock_memories.keys())
            all_meta = self._store.load_memory_metadata_batch(all_ids)
            for mem_id, mem in self._mock_memories.items():
                if mem.get("user_id", "default") == user_id:
                    stored = all_meta.get(mem_id)
                    s = stored["sensitivity"] if stored else 0
                    t = stored["tags"] if stored else []
                    if sensitivity_max is not None and s > sensitivity_max:
                        continue
                    if tags_set and not tags_set.intersection(t):
                        continue
                    results.append({
                        **mem,
                        "sensitivity": s,
                        "tags": t,
                        "content_hash": stored.get("content_hash") if stored else None,
                        "encrypted": stored.get("encrypted", False) if stored else False,
                        "source": stored.get("source", "manual") if stored else "manual",
                        "access_count": stored.get("access_count", 0) if stored else 0,
                        "last_accessed": stored.get("last_accessed") if stored else None,
                        "expires_at": stored.get("expires_at") if stored else None,
                    })
                    if limit is not None and len(results) >= limit:
                        break
            return {"results": results}
    
    def update(
        self,
        memory_id: str,
        *,
        content: Optional[str] = None,
        sensitivity: Optional[int] = None,
        tags: Optional[List[str]] = None,
        expires_at: Optional[datetime] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Update a memory's content or metadata (persistent)."""
        if self._mem0 and content:
            try:
                self._mem0.update(memory_id, data=content)
            except Exception as e:
                logger.error(f"Update failed: {e}")
                raise
        elif content and memory_id in self._mock_memories:
            self._mock_memories[memory_id]["memory"] = content

        updates: Dict[str, Any] = {}
        if sensitivity is not None:
            updates["sensitivity"] = max(0, min(3, sensitivity))
            updates["consent_required"] = sensitivity >= self.require_consent_level
        if tags is not None:
            updates["tags"] = tags
        if expires_at is not None:
            updates["expires_at"] = expires_at.isoformat()
        if content:
            updates["content_hash"] = self._compute_content_hash(content)
            updates["content"] = content
            envelope_data = self._encrypt_content(content) if self.enable_encryption else None
            if envelope_data:
                updates["encrypted"] = True
                updates["ciphertext"] = envelope_data["ciphertext"]
                updates["nonce"] = envelope_data["nonce"]
                updates["dek_enc"] = envelope_data["dek_enc"]
                updates["dek_nonce"] = envelope_data["dek_nonce"]
        if updates:
            self._store.update_memory_metadata(memory_id, updates)

        stored = self._store.load_memory_metadata(memory_id)
        return stored if stored else {"memory_id": memory_id}
    
    def delete(self, memory_id: str) -> bool:
        """
        Delete a memory with cryptographic deletion.
        
        Destroys the DEK, making ciphertext permanently irrecoverable
        (GDPR Article 17 at the cryptographic layer).
        """
        stored = self._store.load_memory_metadata(memory_id)
        if stored and stored.get("encrypted") and stored.get("dek_enc"):
            self._store.update_memory_metadata(memory_id, {
                "dek_enc": "",
                "dek_nonce": "",
                "content": "[DELETED]",
            })
            logger.info(f"Memory {memory_id}: DEK destroyed (cryptographic deletion)")
        self._store.delete_memory_metadata(memory_id)
        if self._mem0:
            try:
                self._mem0.delete(memory_id)
            except Exception as e:
                logger.error(f"mem0 delete failed: {e}")
        self._mock_memories.pop(memory_id, None)
        logger.info(f"Memory {memory_id} deleted")
        return True
    
    def delete_all(self, user_id: str = "default") -> bool:
        """Delete all memories for a user."""
        self._store.delete_all_memory_metadata(user_id)
        if self._mem0:
            try:
                self._mem0.delete_all(user_id=user_id)
            except Exception as e:
                logger.error(f"Delete all failed: {e}")
                raise
        to_delete = [mid for mid, m in self._mock_memories.items() if m.get("user_id", "default") == user_id]
        for mid in to_delete:
            self._mock_memories.pop(mid)
        return True
    
    def get_tags(self, user_id: str = "default") -> Dict[str, int]:
        """Get all tags and their counts (from persistent store)."""
        return self._store.get_tags_counts(user_id)


# Singleton instance
_memory_instance: Optional[ClosedclawMemory] = None


def get_memory_instance(
    config: Optional[Dict[str, Any]] = None,
    require_consent_level: int = 2,
) -> ClosedclawMemory:
    """Get or create the singleton memory instance."""
    global _memory_instance
    if _memory_instance is None:
        _memory_instance = ClosedclawMemory(
            config=config, require_consent_level=require_consent_level,
        )
    return _memory_instance
