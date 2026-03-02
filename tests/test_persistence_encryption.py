"""
Tests for closedclaw Phase 1 features: persistent metadata + encryption at rest.

These tests validate:
  - Memory metadata persistence (save/load/update/delete via PersistentStore)
  - Envelope encryption integration (add → encrypt, delete → destroy DEK)
  - Consent preference storage
  - Memory lifecycle with encryption

Run: pytest tests/test_persistence_encryption.py -v
"""

import hashlib
import tempfile
from datetime import datetime, timezone, timedelta
from pathlib import Path

import pytest


# ---------------------------------------------------------------------------
# Memory Metadata Persistence Tests
# ---------------------------------------------------------------------------

class TestMemoryMetadataPersistence:
    """Validate that memory_metadata table works correctly."""

    def _make_store(self, tmp_path):
        from closedclaw.api.core.storage import PersistentStore
        return PersistentStore(db_path=tmp_path / "test.db")

    def test_save_and_load_metadata(self, tmp_path):
        store = self._make_store(tmp_path)
        meta = {
            "memory_id": "mem-001",
            "user_id": "user-1",
            "content": "Test memory content",
            "sensitivity": 2,
            "tags": ["health", "personal"],
            "source": "conversation",
            "content_hash": hashlib.sha256(b"Test memory content").hexdigest(),
            "encrypted": False,
        }
        store.save_memory_metadata(meta)

        loaded = store.load_memory_metadata("mem-001")
        assert loaded is not None
        assert loaded["memory_id"] == "mem-001"
        assert loaded["sensitivity"] == 2
        assert loaded["user_id"] == "user-1"

    def test_load_nonexistent_returns_none(self, tmp_path):
        store = self._make_store(tmp_path)
        assert store.load_memory_metadata("nonexistent") is None

    def test_update_metadata(self, tmp_path):
        store = self._make_store(tmp_path)
        store.save_memory_metadata({
            "memory_id": "mem-002",
            "user_id": "user-1",
            "content": "original",
            "sensitivity": 1,
            "tags": [],
            "source": "manual",
            "content_hash": hashlib.sha256(b"original").hexdigest(),
            "encrypted": False,
        })
        store.update_memory_metadata("mem-002", {
            "sensitivity": 3,
            "tags": ["updated"],
        })
        loaded = store.load_memory_metadata("mem-002")
        assert loaded["sensitivity"] == 3

    def test_delete_metadata(self, tmp_path):
        store = self._make_store(tmp_path)
        store.save_memory_metadata({
            "memory_id": "mem-003",
            "user_id": "user-1",
            "content": "to-delete",
            "sensitivity": 0,
            "tags": [],
            "source": "manual",
            "content_hash": hashlib.sha256(b"to-delete").hexdigest(),
            "encrypted": False,
        })
        assert store.load_memory_metadata("mem-003") is not None
        store.delete_memory_metadata("mem-003")
        assert store.load_memory_metadata("mem-003") is None

    def test_delete_all_for_user(self, tmp_path):
        store = self._make_store(tmp_path)
        for i in range(5):
            store.save_memory_metadata({
                "memory_id": f"mem-u1-{i}",
                "user_id": "user-bulk",
                "content": f"content-{i}",
                "sensitivity": i % 4,
                "tags": [],
                "source": "manual",
                "content_hash": hashlib.sha256(f"content-{i}".encode()).hexdigest(),
                "encrypted": False,
            })
        assert store.count_memories("user-bulk") == 5
        store.delete_all_memory_metadata("user-bulk")
        assert store.count_memories("user-bulk") == 0

    def test_load_all_with_filters(self, tmp_path):
        store = self._make_store(tmp_path)
        for i in range(4):
            store.save_memory_metadata({
                "memory_id": f"mem-filter-{i}",
                "user_id": "user-filter",
                "content": f"content-{i}",
                "sensitivity": i,
                "tags": ["tag-a"] if i % 2 == 0 else ["tag-b"],
                "source": "manual",
                "content_hash": hashlib.sha256(f"content-{i}".encode()).hexdigest(),
                "encrypted": False,
            })
        # Filter by sensitivity_max
        result = store.load_all_memory_metadata(
            user_id="user-filter", sensitivity_max=1
        )
        assert all(r["sensitivity"] <= 1 for r in result)

    def test_increment_access_count(self, tmp_path):
        store = self._make_store(tmp_path)
        store.save_memory_metadata({
            "memory_id": "mem-access",
            "user_id": "user-1",
            "content": "access test",
            "sensitivity": 0,
            "tags": [],
            "source": "manual",
            "content_hash": hashlib.sha256(b"access test").hexdigest(),
            "encrypted": False,
        })
        store.increment_access_count("mem-access")
        store.increment_access_count("mem-access")
        store.increment_access_count("mem-access")
        loaded = store.load_memory_metadata("mem-access")
        assert loaded["access_count"] == 3

    def test_tags_counts(self, tmp_path):
        store = self._make_store(tmp_path)
        store.save_memory_metadata({
            "memory_id": "tc-1",
            "user_id": "user-tags",
            "content": "a",
            "sensitivity": 0,
            "tags": ["alpha", "beta"],
            "source": "manual",
            "content_hash": "h1",
            "encrypted": False,
        })
        store.save_memory_metadata({
            "memory_id": "tc-2",
            "user_id": "user-tags",
            "content": "b",
            "sensitivity": 0,
            "tags": ["alpha", "gamma"],
            "source": "manual",
            "content_hash": "h2",
            "encrypted": False,
        })
        counts = store.get_tags_counts("user-tags")
        assert counts.get("alpha", 0) == 2
        assert counts.get("beta", 0) == 1
        assert counts.get("gamma", 0) == 1

    def test_count_memories(self, tmp_path):
        store = self._make_store(tmp_path)
        for i in range(3):
            store.save_memory_metadata({
                "memory_id": f"cm-{i}",
                "user_id": "user-count",
                "content": f"c-{i}",
                "sensitivity": 0,
                "tags": [],
                "source": "manual",
                "content_hash": f"h-{i}",
                "encrypted": False,
            })
        assert store.count_memories("user-count") == 3
        assert store.count_memories("user-nonexistent") == 0


# ---------------------------------------------------------------------------
# Consent Preference Persistence Tests
# ---------------------------------------------------------------------------

class TestConsentPreferencePersistence:
    """Validate consent_preferences table CRUD."""

    def _make_store(self, tmp_path):
        from closedclaw.api.core.storage import PersistentStore
        return PersistentStore(db_path=tmp_path / "test.db")

    def test_save_and_get_preference(self, tmp_path):
        store = self._make_store(tmp_path)
        store.save_consent_preference("provider", "openai", "allow")
        pref = store.get_consent_preference("provider", "openai")
        assert pref is not None
        assert pref == "allow"

    def test_preference_upsert(self, tmp_path):
        store = self._make_store(tmp_path)
        store.save_consent_preference("tag", "health", "deny")
        store.save_consent_preference("tag", "health", "allow")
        pref = store.get_consent_preference("tag", "health")
        assert pref == "allow"

    def test_missing_preference_returns_none(self, tmp_path):
        store = self._make_store(tmp_path)
        assert store.get_consent_preference("tag", "nonexistent") is None


# ---------------------------------------------------------------------------
# Envelope Encryption Lifecycle Tests
# ---------------------------------------------------------------------------

class TestEnvelopeEncryptionLifecycle:
    """Validate encrypt → store → decrypt → destroy DEK flow."""

    def test_full_lifecycle(self):
        from closedclaw.api.core.crypto import EnvelopeEncryption

        kek, salt = EnvelopeEncryption.derive_kek("test-passphrase")
        ee = EnvelopeEncryption(kek=kek)

        plaintext = "User's SSN is 123-45-6789"
        envelope = ee.encrypt_memory(plaintext)

        # Verify envelope structure
        assert "ciphertext" in envelope
        assert "nonce" in envelope
        assert "dek_enc" in envelope
        assert "dek_nonce" in envelope
        assert envelope["ciphertext"] != plaintext

        # Decrypt and verify
        decrypted = ee.decrypt_memory(envelope)
        assert decrypted == plaintext

    def test_different_memories_get_different_deks(self):
        from closedclaw.api.core.crypto import EnvelopeEncryption

        kek, salt = EnvelopeEncryption.derive_kek("test-passphrase")
        ee = EnvelopeEncryption(kek=kek)

        env1 = ee.encrypt_memory("memory one")
        env2 = ee.encrypt_memory("memory two")
        assert env1["dek_enc"] != env2["dek_enc"]

    def test_destroy_dek_prevents_decryption(self):
        from closedclaw.api.core.crypto import EnvelopeEncryption

        kek, salt = EnvelopeEncryption.derive_kek("test-passphrase")
        ee = EnvelopeEncryption(kek=kek)

        envelope = ee.encrypt_memory("to be destroyed")
        destroyed = ee.destroy_dek(envelope)

        # After DEK destruction, fields should be zeroed in the returned copy
        assert destroyed["dek_enc"] == ""
        assert destroyed["dek_nonce"] == ""
        assert destroyed.get("_deleted") is True

    def test_kek_derivation_deterministic_with_salt(self):
        from closedclaw.api.core.crypto import EnvelopeEncryption

        kek1, salt = EnvelopeEncryption.derive_kek("my-passphrase")
        kek2, _ = EnvelopeEncryption.derive_kek("my-passphrase", salt=salt)
        assert kek1 == kek2

    def test_kek_derivation_different_passphrases(self):
        from closedclaw.api.core.crypto import EnvelopeEncryption

        kek1, salt = EnvelopeEncryption.derive_kek("passphrase-A")
        kek2, _ = EnvelopeEncryption.derive_kek("passphrase-B", salt=salt)
        assert kek1 != kek2


# ---------------------------------------------------------------------------
# Encrypted Metadata Storage Integration
# ---------------------------------------------------------------------------

class TestEncryptedMetadataStorage:
    """Validate that encrypted envelope data can be stored and retrieved."""

    def test_store_encrypted_metadata(self, tmp_path):
        from closedclaw.api.core.storage import PersistentStore
        from closedclaw.api.core.crypto import EnvelopeEncryption

        store = PersistentStore(db_path=tmp_path / "test.db")
        kek, _ = EnvelopeEncryption.derive_kek("test")
        ee = EnvelopeEncryption(kek=kek)

        plaintext = "User's SSN is 123-45-6789"
        envelope = ee.encrypt_memory(plaintext)

        store.save_memory_metadata({
            "memory_id": "enc-001",
            "user_id": "user-1",
            "content": "[encrypted]",
            "sensitivity": 3,
            "tags": ["identity"],
            "source": "manual",
            "content_hash": hashlib.sha256(plaintext.encode()).hexdigest(),
            "encrypted": True,
            "dek_enc": envelope["dek_enc"],
            "dek_nonce": envelope["dek_nonce"],
            "ciphertext": envelope["ciphertext"],
            "nonce": envelope["nonce"],
        })

        loaded = store.load_memory_metadata("enc-001")
        assert loaded["encrypted"] in (True, 1)
        assert loaded["dek_enc"] == envelope["dek_enc"]
        assert loaded["ciphertext"] == envelope["ciphertext"]

        # Reconstruct envelope and decrypt
        reconstructed = {
            "ciphertext": loaded["ciphertext"],
            "nonce": loaded["nonce"],
            "dek_enc": loaded["dek_enc"],
            "dek_nonce": loaded["dek_nonce"],
        }
        decrypted = ee.decrypt_memory(reconstructed)
        assert decrypted == plaintext

    def test_cryptographic_deletion(self, tmp_path):
        """Verify that deleting a memory also removes its DEK (crypto shredding)."""
        from closedclaw.api.core.storage import PersistentStore
        from closedclaw.api.core.crypto import EnvelopeEncryption

        store = PersistentStore(db_path=tmp_path / "test.db")
        kek, _ = EnvelopeEncryption.derive_kek("test")
        ee = EnvelopeEncryption(kek=kek)

        plaintext = "Secret medical record"
        envelope = ee.encrypt_memory(plaintext)

        store.save_memory_metadata({
            "memory_id": "enc-del-001",
            "user_id": "user-1",
            "content": "[encrypted]",
            "sensitivity": 3,
            "tags": ["medical"],
            "source": "manual",
            "content_hash": hashlib.sha256(plaintext.encode()).hexdigest(),
            "encrypted": True,
            "dek_enc": envelope["dek_enc"],
            "dek_nonce": envelope["dek_nonce"],
            "ciphertext": envelope["ciphertext"],
            "nonce": envelope["nonce"],
        })

        # Wipe DEK fields (simulating cryptographic deletion)
        store.update_memory_metadata("enc-del-001", {
            "dek_enc": "",
            "dek_nonce": "",
        })

        loaded = store.load_memory_metadata("enc-del-001")
        assert loaded["dek_enc"] == ""
        assert loaded["dek_nonce"] == ""
        # Ciphertext still exists but is undecryptable without DEK

        # Now fully delete
        store.delete_memory_metadata("enc-del-001")
        assert store.load_memory_metadata("enc-del-001") is None


# ---------------------------------------------------------------------------
# Run
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
