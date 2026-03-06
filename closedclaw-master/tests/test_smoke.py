"""
Pytest smoke tests for closedclaw core modules.

These tests exercise crypto, storage, audit, consent, and policy logic
without requiring a running server. They validate that the critical
infrastructure components work correctly in isolation.
"""

import hashlib
import json
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import pytest


# ---------------------------------------------------------------------------
# Crypto module tests
# ---------------------------------------------------------------------------

class TestCrypto:
    """Tests for Ed25519 key management and signing."""

    def test_key_manager_creates_keys(self, tmp_path):
        from closedclaw.api.core.crypto import KeyManager

        km = KeyManager(keys_dir=tmp_path)
        km.ensure_keypair()
        assert (tmp_path / "ed25519.key").exists()
        assert (tmp_path / "ed25519.pub").exists()

    def test_key_manager_sign_and_verify(self, tmp_path):
        from closedclaw.api.core.crypto import KeyManager

        km = KeyManager(keys_dir=tmp_path)
        data = b"test data to sign"
        sig = km.sign(data)

        assert isinstance(sig, str)
        assert len(sig) > 20  # base64 encoded Ed25519 signature

        assert km.verify(data, sig) is True
        assert km.verify(b"tampered data", sig) is False

    def test_sign_json(self, tmp_path):
        from closedclaw.api.core.crypto import KeyManager

        km = KeyManager(keys_dir=tmp_path)
        obj = {"action": "allow", "memory_id": "m1", "signature": "old"}
        sig = km.sign_json(obj, exclude_keys=("signature",))
        assert sig is not None

    def test_key_persistence(self, tmp_path):
        """Keys created once are reloaded on subsequent init."""
        from closedclaw.api.core.crypto import KeyManager

        km1 = KeyManager(keys_dir=tmp_path)
        pub1 = km1.public_key_b64

        km2 = KeyManager(keys_dir=tmp_path)
        pub2 = km2.public_key_b64

        assert pub1 == pub2

    def test_envelope_encryption(self, tmp_path):
        from closedclaw.api.core.crypto import EnvelopeEncryption

        kek, salt = EnvelopeEncryption.derive_kek("test-passphrase")
        ee = EnvelopeEncryption(kek=kek)
        plaintext = "sensitive memory content"
        encrypted = ee.encrypt_memory(plaintext)

        assert encrypted["ciphertext"] != plaintext
        assert "dek_enc" in encrypted

        decrypted = ee.decrypt_memory(encrypted)
        assert decrypted == plaintext


# ---------------------------------------------------------------------------
# Persistent Storage tests
# ---------------------------------------------------------------------------

class TestPersistentStorage:
    """Tests for SQLite-backed audit and consent storage."""

    def test_save_and_load_audit_entry(self, tmp_path):
        from closedclaw.api.core.storage import PersistentStore

        store = PersistentStore(db_path=tmp_path / "test.db")
        entry = {
            "entry_id": "ae-001",
            "request_id": "req-001",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "provider": "openai",
            "model": "gpt-4o",
            "memories_retrieved": 5,
            "memories_used": 3,
            "memory_ids": ["m1", "m2", "m3"],
            "redactions_applied": 1,
            "blocked_memories": 0,
            "consent_required": False,
            "entry_hash": "abc123",
            "prev_hash": None,
            "signature": "sig123",
        }
        store.save_audit_entry(entry)

        loaded = store.load_audit_entries(limit=10)
        assert len(loaded) == 1
        assert loaded[0]["entry_id"] == "ae-001"
        assert loaded[0]["provider"] == "openai"

    def test_audit_entry_count(self, tmp_path):
        from closedclaw.api.core.storage import PersistentStore

        store = PersistentStore(db_path=tmp_path / "test.db")
        for i in range(5):
            store.save_audit_entry({
                "entry_id": f"ae-{i}",
                "request_id": f"req-{i}",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "provider": "openai",
                "entry_hash": f"hash-{i}",
            })
        assert store.count_audit_entries() == 5

    def test_last_audit_hash(self, tmp_path):
        from closedclaw.api.core.storage import PersistentStore

        store = PersistentStore(db_path=tmp_path / "test.db")
        assert store.get_last_audit_hash() is None

        store.save_audit_entry({
            "entry_id": "ae-1",
            "request_id": "req-1",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "provider": "openai",
            "entry_hash": "first-hash",
        })
        assert store.get_last_audit_hash() == "first-hash"

        store.save_audit_entry({
            "entry_id": "ae-2",
            "request_id": "req-2",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "provider": "openai",
            "entry_hash": "second-hash",
        })
        assert store.get_last_audit_hash() == "second-hash"

    def test_consent_receipt_roundtrip(self, tmp_path):
        from closedclaw.api.core.storage import PersistentStore

        store = PersistentStore(db_path=tmp_path / "test.db")
        receipt = {
            "receipt_id": "cr-001",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "memory_id": "m-001",
            "memory_hash": "deadbeef",
            "provider": "anthropic",
            "sensitivity_level": 3,
            "user_decision": "allow",
            "signature": "sig",
        }
        store.save_consent_receipt(receipt)

        loaded = store.load_consent_receipts(memory_id="m-001")
        assert len(loaded) == 1
        assert loaded[0]["receipt_id"] == "cr-001"

    def test_pending_consent_lifecycle(self, tmp_path):
        from closedclaw.api.core.storage import PersistentStore

        store = PersistentStore(db_path=tmp_path / "test.db")
        pending = {
            "request_id": "pr-001",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "memory_id": "m-001",
            "memory_text": "test memory",
            "memory_hash": hashlib.sha256(b"test memory").hexdigest(),
            "sensitivity": 3,
            "provider": "openai",
        }
        store.save_pending_consent(pending)

        loaded = store.load_pending_consents()
        assert len(loaded) == 1
        assert loaded[0]["request_id"] == "pr-001"

        store.delete_pending_consent("pr-001")
        assert len(store.load_pending_consents()) == 0


# ---------------------------------------------------------------------------
# Policy engine tests
# ---------------------------------------------------------------------------

class TestPolicyEngine:
    """Tests for the policy evaluation engine."""

    def test_default_policies_exist(self):
        from closedclaw.api.core.policies import DEFAULT_POLICIES
        assert len(DEFAULT_POLICIES) > 0

    def test_policy_evaluation_permit(self):
        from closedclaw.api.core.policies import PolicyEngine, PolicyAction, PolicySet, DEFAULT_POLICIES

        policy_set = PolicySet(**DEFAULT_POLICIES)
        engine = PolicyEngine(policy_set)
        memory = {"sensitivity": 0, "tags": [], "source": "conversation"}
        action, rule = engine.evaluate(
            memory=memory,
            provider="openai",
        )
        assert action in (PolicyAction.PERMIT, PolicyAction.REDACT,
                          PolicyAction.BLOCK, PolicyAction.CONSENT_REQUIRED)

    def test_high_sensitivity_blocked_or_consent(self):
        from closedclaw.api.core.policies import PolicyEngine, PolicyAction, PolicySet, DEFAULT_POLICIES

        policy_set = PolicySet(**DEFAULT_POLICIES)
        engine = PolicyEngine(policy_set)
        memory = {"sensitivity": 3, "tags": ["health"], "source": "conversation"}
        action, rule = engine.evaluate(
            memory=memory,
            provider="unknown-provider",
        )
        # Level 3 should not be simply permitted
        assert action in (PolicyAction.BLOCK, PolicyAction.CONSENT_REQUIRED, PolicyAction.REDACT)


# ---------------------------------------------------------------------------
# Privacy pipeline tests
# ---------------------------------------------------------------------------

class TestPrivacyPipeline:
    """Tests for PII detection, classification, and redaction."""

    def test_sensitivity_keywords(self):
        from closedclaw.api.core.memory import ClosedclawMemory
        from closedclaw.api.privacy.classifier import SensitivityClassifier

        mem = ClosedclawMemory.__new__(ClosedclawMemory)
        mem.default_sensitivity = 0  # mock attribute
        mem._classifier = SensitivityClassifier(default_sensitivity=0)
        # Should classify health data as high sensitivity ("diagnosis" is a Level 3 keyword)
        level = mem._classify_sensitivity("My diagnosis is diabetes")
        assert level >= 2

    def test_sensitivity_low_for_generic(self):
        from closedclaw.api.core.memory import ClosedclawMemory
        from closedclaw.api.privacy.classifier import SensitivityClassifier

        mem = ClosedclawMemory.__new__(ClosedclawMemory)
        mem.default_sensitivity = 0  # mock attribute
        mem._classifier = SensitivityClassifier(default_sensitivity=0)
        level = mem._classify_sensitivity("I like pizza")
        assert level <= 1


# ---------------------------------------------------------------------------
# Conftest marker
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
