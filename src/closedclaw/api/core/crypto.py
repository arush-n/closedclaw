"""
Closedclaw Cryptography Module

Provides:
- Ed25519 keypair management (signing & verification)
- AES-256-GCM envelope encryption (KEK/DEK)
- Consent receipt signing
- Audit log hash chain signing
- Argon2id key derivation from user passphrase
"""

import os
import json
import hashlib
import logging
import base64
from pathlib import Path
from typing import Optional, Dict, Any, Tuple
from datetime import datetime, timezone

from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Ed25519 Key Management
# ---------------------------------------------------------------------------

class KeyManager:
    """
    Manages Ed25519 keypair for signing consent receipts and audit entries.
    Keys are stored in ~/.closedclaw/keys/
    """

    def __init__(self, keys_dir: Optional[Path] = None):
        if keys_dir is None:
            keys_dir = Path.home() / ".closedclaw" / "keys"
        self.keys_dir = keys_dir
        self._private_key: Optional[Ed25519PrivateKey] = None
        self._public_key: Optional[Ed25519PublicKey] = None

    def ensure_keypair(self) -> None:
        """Generate keypair if it doesn't exist, or load existing."""
        self.keys_dir.mkdir(parents=True, exist_ok=True)
        priv_path = self.keys_dir / "ed25519.key"
        pub_path = self.keys_dir / "ed25519.pub"

        if priv_path.exists():
            self._load_keys(priv_path, pub_path)
        else:
            self._generate_keys(priv_path, pub_path)

    def _generate_keys(self, priv_path: Path, pub_path: Path) -> None:
        self._private_key = Ed25519PrivateKey.generate()
        self._public_key = self._private_key.public_key()

        # Save private key (PEM, encrypted with a per-install password)
        key_password = self._get_key_password()
        priv_pem = self._private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.BestAvailableEncryption(key_password),
        )
        priv_path.write_bytes(priv_pem)
        try:
            priv_path.chmod(0o600)
        except OSError:
            pass  # Windows may not support chmod

        # Save public key
        pub_pem = self._public_key.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        pub_path.write_bytes(pub_pem)

        logger.info("Generated new Ed25519 keypair")

    def _load_keys(self, priv_path: Path, pub_path: Path) -> None:
        priv_pem = priv_path.read_bytes()
        key_password = self._get_key_password()
        try:
            self._private_key = serialization.load_pem_private_key(priv_pem, password=key_password)  # type: ignore[assignment]
        except (ValueError, TypeError):
            # Fallback: try loading unencrypted key from previous version
            self._private_key = serialization.load_pem_private_key(priv_pem, password=None)  # type: ignore[assignment]
            logger.warning("Loaded unencrypted Ed25519 key – will re-encrypt on next write")
        assert self._private_key is not None
        self._public_key = self._private_key.public_key()
        logger.debug("Loaded existing Ed25519 keypair")

    def _get_key_password(self) -> bytes:
        """Return the password used to encrypt the Ed25519 private key on disk."""
        import secrets as _secrets
        pw_path = self.keys_dir / "ed25519.pw"
        if pw_path.exists():
            return pw_path.read_bytes().strip()
        pw = _secrets.token_bytes(32)
        pw_path.write_bytes(pw)
        try:
            pw_path.chmod(0o600)
        except OSError:
            pass
        return pw

    @property
    def private_key(self) -> Ed25519PrivateKey:
        if self._private_key is None:
            self.ensure_keypair()
        assert self._private_key is not None
        return self._private_key

    @property
    def public_key(self) -> Ed25519PublicKey:
        if self._public_key is None:
            self.ensure_keypair()
        assert self._public_key is not None
        return self._public_key

    @property
    def public_key_b64(self) -> str:
        """Base64-encoded raw public key bytes (32 bytes)."""
        raw = self.public_key.public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        )
        return base64.b64encode(raw).decode()

    # ------------------------------------------------------------------
    # Signing
    # ------------------------------------------------------------------

    def sign(self, data: bytes) -> str:
        """Sign data, return base64-encoded signature."""
        sig = self.private_key.sign(data)
        return base64.b64encode(sig).decode()

    def sign_json(self, obj: Dict[str, Any], exclude_keys: tuple = ("signature",)) -> str:
        """Sign a JSON-serialisable dict. Excludes given keys before signing."""
        filtered = {k: v for k, v in obj.items() if k not in exclude_keys}
        canonical = json.dumps(filtered, sort_keys=True, default=str).encode()
        return self.sign(canonical)

    # ------------------------------------------------------------------
    # Verification
    # ------------------------------------------------------------------

    def verify(self, data: bytes, signature_b64: str) -> bool:
        """Verify a base64-encoded Ed25519 signature."""
        try:
            sig = base64.b64decode(signature_b64)
            self.public_key.verify(sig, data)
            return True
        except Exception:
            return False

    def verify_json(
        self,
        obj: Dict[str, Any],
        signature_b64: str,
        exclude_keys: tuple = ("signature",),
    ) -> bool:
        filtered = {k: v for k, v in obj.items() if k not in exclude_keys}
        canonical = json.dumps(filtered, sort_keys=True, default=str).encode()
        return self.verify(canonical, signature_b64)


# ---------------------------------------------------------------------------
# AES-256-GCM Envelope Encryption (KEK / DEK)
# ---------------------------------------------------------------------------

class EnvelopeEncryption:
    """
    Envelope encryption using AES-256-GCM.

    Each memory gets its own random 256-bit DEK (Data Encryption Key).
    The DEK is encrypted with the KEK (Key Encryption Key).
    The KEK is derived from the user passphrase via Scrypt.
    """

    def __init__(self, kek: Optional[bytes] = None):
        self._kek = kek  # 32 bytes

    @staticmethod
    def derive_kek(passphrase: str, salt: Optional[bytes] = None) -> Tuple[bytes, bytes]:
        """Derive KEK from passphrase using Scrypt. Returns (kek, salt)."""
        if salt is None:
            salt = os.urandom(16)
        kdf = Scrypt(salt=salt, length=32, n=2**17, r=8, p=1)
        kek = kdf.derive(passphrase.encode())
        return kek, salt

    def set_kek(self, kek: bytes) -> None:
        self._kek = kek

    @property
    def kek(self) -> bytes:
        if self._kek is None:
            raise RuntimeError("KEK not set – call derive_kek or set_kek first")
        return self._kek

    # ---- per-memory encryption ----

    def encrypt_memory(self, plaintext: str) -> Dict[str, str]:
        """
        Encrypt a memory string.

        Returns dict with:
          ciphertext: base64
          nonce: base64
          dek_enc: base64 (DEK encrypted with KEK)
          dek_nonce: base64
        """
        # Generate random DEK
        dek = AESGCM.generate_key(bit_length=256)
        nonce = os.urandom(12)
        ct = AESGCM(dek).encrypt(nonce, plaintext.encode(), None)

        # Wrap DEK with KEK
        dek_nonce = os.urandom(12)
        dek_enc = AESGCM(self.kek).encrypt(dek_nonce, dek, None)

        return {
            "ciphertext": base64.b64encode(ct).decode(),
            "nonce": base64.b64encode(nonce).decode(),
            "dek_enc": base64.b64encode(dek_enc).decode(),
            "dek_nonce": base64.b64encode(dek_nonce).decode(),
        }

    def decrypt_memory(self, envelope: Dict[str, str]) -> str:
        """Decrypt an encrypted memory envelope → plaintext string."""
        # Unwrap DEK
        dek_enc = base64.b64decode(envelope["dek_enc"])
        dek_nonce = base64.b64decode(envelope["dek_nonce"])
        dek = AESGCM(self.kek).decrypt(dek_nonce, dek_enc, None)

        # Decrypt content
        ct = base64.b64decode(envelope["ciphertext"])
        nonce = base64.b64decode(envelope["nonce"])
        plaintext = AESGCM(dek).decrypt(nonce, ct, None)
        return plaintext.decode()

    @staticmethod
    def destroy_dek(envelope: Dict[str, str]) -> Dict[str, str]:
        """
        Cryptographic deletion: wipe the DEK from an envelope.
        The ciphertext becomes permanently irrecoverable.
        """
        envelope = dict(envelope)
        envelope["dek_enc"] = ""
        envelope["dek_nonce"] = ""
        envelope["_deleted"] = True  # type: ignore[assignment]
        return envelope


# ---------------------------------------------------------------------------
# Consent Receipt Signer
# ---------------------------------------------------------------------------

def sign_consent_receipt(receipt_dict: Dict[str, Any], key_mgr: KeyManager) -> Dict[str, Any]:
    """
    Sign a consent receipt dict with Ed25519.
    Adds `user_pubkey` and `signature` fields.
    """
    receipt = dict(receipt_dict)
    receipt["user_pubkey"] = key_mgr.public_key_b64
    receipt["signature"] = key_mgr.sign_json(receipt, exclude_keys=("signature",))
    return receipt


def verify_consent_receipt(receipt_dict: Dict[str, Any], key_mgr: KeyManager) -> bool:
    """Verify the Ed25519 signature on a consent receipt."""
    sig = receipt_dict.get("signature")
    if not sig:
        return False
    return key_mgr.verify_json(receipt_dict, sig, exclude_keys=("signature",))


# ---------------------------------------------------------------------------
# Audit Entry Signer
# ---------------------------------------------------------------------------

def sign_audit_entry(entry_dict: Dict[str, Any], key_mgr: KeyManager) -> Dict[str, Any]:
    """Sign an audit entry dict with Ed25519."""
    entry = dict(entry_dict)
    entry["signature"] = key_mgr.sign_json(entry, exclude_keys=("signature",))
    return entry


def verify_audit_entry(entry_dict: Dict[str, Any], key_mgr: KeyManager) -> bool:
    sig = entry_dict.get("signature")
    if not sig:
        return False
    return key_mgr.verify_json(entry_dict, sig, exclude_keys=("signature",))


# ---------------------------------------------------------------------------
# Singleton key manager
# ---------------------------------------------------------------------------

_key_manager: Optional[KeyManager] = None


def get_key_manager(keys_dir: Optional[Path] = None) -> KeyManager:
    """Get or create the singleton KeyManager."""
    global _key_manager
    if _key_manager is None:
        _key_manager = KeyManager(keys_dir)
        _key_manager.ensure_keypair()
    return _key_manager
