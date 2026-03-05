"""
Agent Keyring — per-agent Ed25519 + X25519 keypairs for signed AND encrypted
inter-agent messages.

Security layers:
  1. Ed25519 signatures — message authenticity & integrity
  2. X25519 ECDH + AES-256-GCM — payload encryption between agents
  3. Scrypt-derived key — encrypts private keys at rest
  4. Nonce registry — prevents message replay attacks
  5. Hash chain — tamper-evident audit trail linking every message

Each of the 7 agents + the coordinator gets its own keypair stored under
~/.closedclaw/keys/agents/{agent_name}/.
"""

import base64
import hashlib
import json
import logging
import os
import platform
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)
from cryptography.hazmat.primitives.asymmetric.x25519 import (
    X25519PrivateKey,
    X25519PublicKey,
)
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt

from closedclaw.api.agents.swarm.models import AgentMessage

logger = logging.getLogger(__name__)

AGENT_NAMES = [
    "coordinator",
    "governance",
    "maker",
    "accessor",
    "policy",
    "sentinel",
    "arbitrator",
    "auditor",
]

# ── Machine-derived secret for encrypting keys at rest ─────────────────
def _machine_secret() -> bytes:
    """Derive a machine-specific secret for encrypting private keys at rest.

    Combines hostname + platform + username into a deterministic seed.
    This is NOT a password — it simply ties keys to this machine so they
    can't be trivially copied and used elsewhere.
    """
    parts = [
        platform.node(),
        platform.system(),
        platform.machine(),
        os.environ.get("USERNAME", os.environ.get("USER", "closedclaw")),
    ]
    return hashlib.sha256("|".join(parts).encode()).digest()


# ── Nonce Registry ─────────────────────────────────────────────────────
class NonceRegistry:
    """Tracks message nonces to prevent replay attacks.

    Stores nonces with timestamps and evicts expired entries.
    """

    def __init__(self, ttl_seconds: int = 3600, max_nonces: int = 50_000):
        self._nonces: Dict[str, float] = {}  # nonce -> timestamp
        self._ttl = ttl_seconds
        self._max = max_nonces

    def register(self, nonce: str) -> bool:
        """Register a nonce. Returns False if already seen (replay detected)."""
        self._evict_expired()
        if nonce in self._nonces:
            return False
        self._nonces[nonce] = time.time()
        return True

    def _evict_expired(self) -> None:
        now = time.time()
        if len(self._nonces) > self._max:
            cutoff = now - self._ttl
            self._nonces = {n: t for n, t in self._nonces.items() if t > cutoff}


# ── Hash Chain ─────────────────────────────────────────────────────────
class HashChain:
    """Tamper-evident hash chain for audit trail integrity.

    Each entry's hash includes the previous entry's hash, creating an
    immutable chain. Any modification to an earlier entry invalidates
    all subsequent hashes.
    """

    def __init__(self):
        self._chain: List[str] = []
        self._genesis = hashlib.sha256(b"closedclaw:genesis").hexdigest()

    @property
    def latest_hash(self) -> str:
        return self._chain[-1] if self._chain else self._genesis

    @property
    def length(self) -> int:
        return len(self._chain)

    def append(self, data: bytes) -> str:
        """Add data to the chain, returning the new hash."""
        prev = self.latest_hash
        entry = hashlib.sha256(prev.encode() + data).hexdigest()
        self._chain.append(entry)
        return entry

    def verify(self, index: int, data: bytes) -> bool:
        """Verify that a specific chain entry is valid."""
        if index < 0 or index >= len(self._chain):
            return False
        prev = self._chain[index - 1] if index > 0 else self._genesis
        expected = hashlib.sha256(prev.encode() + data).hexdigest()
        return self._chain[index] == expected

    def verify_full_chain(self, data_list: List[bytes]) -> bool:
        """Verify the entire chain against a list of data entries."""
        if len(data_list) != len(self._chain):
            return False
        return all(self.verify(i, d) for i, d in enumerate(data_list))


# ── Payload Encryption (X25519 ECDH + AES-256-GCM) ────────────────────
class PayloadEncryptor:
    """Encrypts/decrypts message payloads using X25519 key agreement + AES-256-GCM.

    Flow:
      1. Sender uses their X25519 private key + recipient's X25519 public key
         to derive a shared secret via ECDH.
      2. HKDF expands the shared secret into a 256-bit AES key.
      3. AES-256-GCM encrypts the payload with a random 96-bit nonce.
      4. The ciphertext, nonce, and sender's X25519 public key are bundled
         into the encrypted message.
    """

    @staticmethod
    def derive_shared_key(
        private_key: X25519PrivateKey,
        peer_public_key: X25519PublicKey,
        context: bytes = b"closedclaw-swarm-v1",
    ) -> bytes:
        """Derive a 256-bit AES key from ECDH shared secret + HKDF."""
        shared_secret = private_key.exchange(peer_public_key)
        derived = HKDF(
            algorithm=hashes.SHA256(),
            length=32,
            salt=None,
            info=context,
        ).derive(shared_secret)
        return derived

    @staticmethod
    def encrypt(plaintext: bytes, aes_key: bytes) -> Tuple[bytes, bytes]:
        """Encrypt with AES-256-GCM. Returns (ciphertext, nonce)."""
        nonce = os.urandom(12)  # 96-bit nonce for GCM
        aesgcm = AESGCM(aes_key)
        ciphertext = aesgcm.encrypt(nonce, plaintext, None)
        return ciphertext, nonce

    @staticmethod
    def decrypt(ciphertext: bytes, nonce: bytes, aes_key: bytes) -> bytes:
        """Decrypt AES-256-GCM ciphertext."""
        aesgcm = AESGCM(aes_key)
        return aesgcm.decrypt(nonce, ciphertext, None)


# ── Agent Keyring ──────────────────────────────────────────────────────
class AgentKeyring:
    """Manages Ed25519 (signing) + X25519 (encryption) keypairs for all swarm agents.

    Security features:
      - Ed25519 signatures on every inter-agent message
      - X25519 ECDH + AES-256-GCM payload encryption
      - Private keys encrypted at rest with Scrypt-derived key
      - Nonce registry for replay attack prevention
      - Hash chain for tamper-evident audit trail
    """

    def __init__(self, keys_dir: Optional[Path] = None):
        if keys_dir is None:
            keys_dir = Path.home() / ".closedclaw" / "keys" / "agents"
        self._keys_dir = keys_dir

        # Ed25519 signing keys
        self._private_keys: Dict[str, Ed25519PrivateKey] = {}
        self._public_keys: Dict[str, Ed25519PublicKey] = {}

        # X25519 encryption keys
        self._x25519_private: Dict[str, X25519PrivateKey] = {}
        self._x25519_public: Dict[str, X25519PublicKey] = {}

        # Security modules
        self._nonce_registry = NonceRegistry()
        self._hash_chain = HashChain()
        self._encryptor = PayloadEncryptor()
        self._machine_key = self._derive_storage_key()

    def _derive_storage_key(self) -> bytes:
        """Derive a key from machine secret to encrypt private keys at rest."""
        secret = _machine_secret()
        salt = hashlib.sha256(b"closedclaw:key-storage-salt:" + secret[:8]).digest()[:16]
        kdf = Scrypt(salt=salt, length=32, n=2**14, r=8, p=1)
        return kdf.derive(secret)

    # ── Key Lifecycle ──────────────────────────────────────────────────

    def ensure_all_keys(self) -> None:
        """Generate keypairs for all agents if they don't exist."""
        for name in AGENT_NAMES:
            self._ensure_key(name)

    def _ensure_key(self, agent_name: str) -> None:
        """Load or generate Ed25519 + X25519 keypairs for an agent."""
        # Skip if already loaded
        if agent_name in self._private_keys and agent_name in self._x25519_private:
            return

        agent_dir = self._keys_dir / agent_name
        agent_dir.mkdir(parents=True, exist_ok=True)

        # Ed25519 (signing)
        self._load_or_generate_ed25519(agent_name, agent_dir)

        # X25519 (encryption)
        self._load_or_generate_x25519(agent_name, agent_dir)

    def _load_or_generate_ed25519(self, agent_name: str, agent_dir: Path) -> None:
        """Load or generate Ed25519 signing keypair."""
        priv_path = agent_dir / "ed25519.enc"
        pub_path = agent_dir / "ed25519.pub"

        # Try legacy unencrypted format first for migration
        legacy_priv = agent_dir / "private.pem"
        legacy_pub = agent_dir / "public.pem"

        if priv_path.exists() and pub_path.exists():
            try:
                priv_enc = priv_path.read_bytes()
                priv_bytes = self._decrypt_key_file(priv_enc)
                self._private_keys[agent_name] = serialization.load_pem_private_key(
                    priv_bytes, password=None
                )
                pub_bytes = pub_path.read_bytes()
                self._public_keys[agent_name] = serialization.load_pem_public_key(pub_bytes)
                return
            except Exception:
                logger.warning("Corrupt encrypted Ed25519 key for %s, regenerating", agent_name)

        # Migrate from legacy unencrypted format
        if legacy_priv.exists() and legacy_pub.exists():
            try:
                priv_bytes = legacy_priv.read_bytes()
                self._private_keys[agent_name] = serialization.load_pem_private_key(
                    priv_bytes, password=None
                )
                pub_bytes = legacy_pub.read_bytes()
                self._public_keys[agent_name] = serialization.load_pem_public_key(pub_bytes)
                # Re-save encrypted
                self._save_encrypted_key(priv_path, priv_bytes)
                pub_path.write_bytes(pub_bytes)
                # Remove legacy files
                legacy_priv.unlink(missing_ok=True)
                legacy_pub.unlink(missing_ok=True)
                logger.info("Migrated Ed25519 key for %s to encrypted format", agent_name)
                return
            except Exception:
                logger.warning("Failed to migrate legacy key for %s", agent_name)

        # Generate new
        private_key = Ed25519PrivateKey.generate()
        public_key = private_key.public_key()

        priv_pem = private_key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
        pub_pem = public_key.public_bytes(
            serialization.Encoding.PEM,
            serialization.PublicFormat.SubjectPublicKeyInfo,
        )

        self._save_encrypted_key(priv_path, priv_pem)
        pub_path.write_bytes(pub_pem)
        self._private_keys[agent_name] = private_key
        self._public_keys[agent_name] = public_key
        logger.info("Generated Ed25519 keypair for agent: %s (encrypted at rest)", agent_name)

    def _load_or_generate_x25519(self, agent_name: str, agent_dir: Path) -> None:
        """Load or generate X25519 encryption keypair."""
        priv_path = agent_dir / "x25519.enc"
        pub_path = agent_dir / "x25519.pub"

        if priv_path.exists() and pub_path.exists():
            try:
                priv_enc = priv_path.read_bytes()
                priv_bytes = self._decrypt_key_file(priv_enc)
                self._x25519_private[agent_name] = serialization.load_pem_private_key(
                    priv_bytes, password=None
                )
                pub_bytes = pub_path.read_bytes()
                self._x25519_public[agent_name] = serialization.load_pem_public_key(pub_bytes)
                return
            except Exception:
                logger.warning("Corrupt X25519 key for %s, regenerating", agent_name)

        private_key = X25519PrivateKey.generate()
        public_key = private_key.public_key()

        priv_pem = private_key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
        pub_pem = public_key.public_bytes(
            serialization.Encoding.PEM,
            serialization.PublicFormat.SubjectPublicKeyInfo,
        )

        self._save_encrypted_key(priv_path, priv_pem)
        pub_path.write_bytes(pub_pem)
        self._x25519_private[agent_name] = private_key
        self._x25519_public[agent_name] = public_key
        logger.info("Generated X25519 keypair for agent: %s (encrypted at rest)", agent_name)

    # ── Key File Encryption ────────────────────────────────────────────

    def _save_encrypted_key(self, path: Path, key_pem: bytes) -> None:
        """Encrypt a PEM private key with AES-256-GCM and save it."""
        nonce = os.urandom(12)
        aesgcm = AESGCM(self._machine_key)
        ciphertext = aesgcm.encrypt(nonce, key_pem, None)
        # Format: nonce (12 bytes) + ciphertext
        path.write_bytes(nonce + ciphertext)

    def _decrypt_key_file(self, data: bytes) -> bytes:
        """Decrypt an encrypted private key file."""
        nonce = data[:12]
        ciphertext = data[12:]
        aesgcm = AESGCM(self._machine_key)
        return aesgcm.decrypt(nonce, ciphertext, None)

    # ── Ed25519 Signing ────────────────────────────────────────────────

    def get_public_key_b64(self, agent_name: str) -> str:
        """Return base64-encoded raw Ed25519 public key bytes."""
        self._ensure_key(agent_name)
        pub = self._public_keys[agent_name]
        raw = pub.public_bytes(
            serialization.Encoding.Raw,
            serialization.PublicFormat.Raw,
        )
        return base64.b64encode(raw).decode()

    def sign_message(self, message: AgentMessage, agent_name: str) -> AgentMessage:
        """Sign an AgentMessage with the specified agent's Ed25519 private key."""
        self._ensure_key(agent_name)
        priv = self._private_keys[agent_name]
        canonical = self._canonical_bytes(message)
        sig = priv.sign(canonical)
        message.signature = base64.b64encode(sig).decode()
        message.sender_pubkey = self.get_public_key_b64(agent_name)

        # Generate and attach nonce for replay protection
        msg_nonce = base64.b64encode(os.urandom(16)).decode()
        message.nonce = msg_nonce

        # Add to hash chain
        chain_data = canonical + sig
        chain_hash = self._hash_chain.append(chain_data)
        message.chain_hash = chain_hash

        return message

    def verify_message(self, message: AgentMessage) -> bool:
        """Verify an AgentMessage's Ed25519 signature.

        Also checks nonce for replay prevention.
        """
        sender = message.sender
        if sender not in self._public_keys:
            self._ensure_key(sender)
        if sender not in self._public_keys:
            return False

        # Replay check: reject if nonce was already seen
        if message.nonce and not self._nonce_registry.register(message.nonce):
            logger.warning("REPLAY DETECTED: nonce %s already seen from %s", message.nonce, sender)
            return False

        pub = self._public_keys[sender]
        sig_bytes = base64.b64decode(message.signature or "")
        canonical = self._canonical_bytes(message)
        try:
            pub.verify(sig_bytes, canonical)
            return True
        except Exception:
            return False

    # ── X25519 Payload Encryption ──────────────────────────────────────

    def encrypt_payload(
        self,
        message: AgentMessage,
        sender_name: str,
        recipient_name: str,
    ) -> AgentMessage:
        """Encrypt the message payload using X25519 ECDH + AES-256-GCM.

        The sender's X25519 private key and recipient's X25519 public key
        are used to derive a shared AES key. The payload is then encrypted
        in-place.
        """
        self._ensure_key(sender_name)
        self._ensure_key(recipient_name)

        sender_priv = self._x25519_private[sender_name]
        recipient_pub = self._x25519_public[recipient_name]

        # Derive shared AES key
        aes_key = PayloadEncryptor.derive_shared_key(sender_priv, recipient_pub)

        # Serialize payload to JSON
        plaintext = json.dumps(message.payload, sort_keys=True, default=str).encode("utf-8")

        # Encrypt
        ciphertext, nonce = PayloadEncryptor.encrypt(plaintext, aes_key)

        # Replace payload with encrypted envelope
        message.payload = {
            "_encrypted": True,
            "_ciphertext": base64.b64encode(ciphertext).decode(),
            "_nonce": base64.b64encode(nonce).decode(),
            "_sender_x25519_pub": self._get_x25519_pub_b64(sender_name),
            "_algorithm": "X25519-ECDH+AES-256-GCM",
        }
        message.encrypted = True

        return message

    def decrypt_payload(
        self,
        message: AgentMessage,
        recipient_name: str,
    ) -> AgentMessage:
        """Decrypt an encrypted message payload.

        The recipient's X25519 private key and the sender's X25519 public key
        (embedded in the encrypted envelope) are used to derive the shared
        AES key and decrypt.
        """
        if not message.encrypted or not message.payload.get("_encrypted"):
            return message  # Not encrypted, return as-is

        self._ensure_key(recipient_name)
        self._ensure_key(message.sender)

        recipient_priv = self._x25519_private[recipient_name]
        sender_pub = self._x25519_public[message.sender]

        # Derive shared AES key (same as sender derived)
        aes_key = PayloadEncryptor.derive_shared_key(recipient_priv, sender_pub)

        # Extract encrypted data
        ciphertext = base64.b64decode(message.payload["_ciphertext"])
        nonce = base64.b64decode(message.payload["_nonce"])

        # Decrypt
        plaintext = PayloadEncryptor.decrypt(ciphertext, nonce, aes_key)

        # Restore payload
        message.payload = json.loads(plaintext)
        message.encrypted = False

        return message

    def _get_x25519_pub_b64(self, agent_name: str) -> str:
        """Return base64-encoded raw X25519 public key bytes."""
        pub = self._x25519_public[agent_name]
        raw = pub.public_bytes(
            serialization.Encoding.Raw,
            serialization.PublicFormat.Raw,
        )
        return base64.b64encode(raw).decode()

    # ── Hash Chain Access ──────────────────────────────────────────────

    @property
    def hash_chain(self) -> HashChain:
        return self._hash_chain

    @property
    def nonce_registry(self) -> NonceRegistry:
        return self._nonce_registry

    def get_chain_status(self) -> Dict[str, Any]:
        """Return hash chain integrity status."""
        return {
            "chain_length": self._hash_chain.length,
            "latest_hash": self._hash_chain.latest_hash,
            "nonces_tracked": len(self._nonce_registry._nonces),
        }

    # ── Canonical Form ─────────────────────────────────────────────────

    @staticmethod
    def _canonical_bytes(message: AgentMessage) -> bytes:
        """Deterministic byte representation for signing.

        Excludes signature, sender_pubkey, nonce, chain_hash, and encrypted
        fields — these are set during/after signing.
        """
        data = message.model_dump(
            exclude={"signature", "sender_pubkey", "nonce", "chain_hash", "encrypted"}
        )
        return json.dumps(data, sort_keys=True, default=str).encode("utf-8")

    # ── Key Rotation ───────────────────────────────────────────────────

    def rotate_keys(self, agent_name: str) -> None:
        """Rotate all keys for a specific agent.

        Generates new Ed25519 + X25519 keypairs, saves encrypted, and
        removes old keys from memory.
        """
        # Remove cached keys
        self._private_keys.pop(agent_name, None)
        self._public_keys.pop(agent_name, None)
        self._x25519_private.pop(agent_name, None)
        self._x25519_public.pop(agent_name, None)

        # Remove old key files
        agent_dir = self._keys_dir / agent_name
        for f in agent_dir.glob("*"):
            f.unlink(missing_ok=True)

        # Generate fresh keys
        self._ensure_key(agent_name)
        logger.info("Rotated all keys for agent: %s", agent_name)

    def get_security_status(self) -> Dict[str, Any]:
        """Return overall security status of the keyring."""
        agents_with_signing = set(self._private_keys.keys())
        agents_with_encryption = set(self._x25519_private.keys())
        return {
            "signing_agents": sorted(agents_with_signing),
            "encryption_agents": sorted(agents_with_encryption),
            "all_agents_secured": agents_with_signing == agents_with_encryption == set(AGENT_NAMES),
            "chain_status": self.get_chain_status(),
            "keys_encrypted_at_rest": True,
            "algorithms": {
                "signing": "Ed25519",
                "key_exchange": "X25519-ECDH",
                "payload_encryption": "AES-256-GCM",
                "key_derivation": "HKDF-SHA256",
                "key_storage": "AES-256-GCM + Scrypt",
            },
        }
