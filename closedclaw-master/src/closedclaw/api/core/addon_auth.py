"""
Addon Session Manager — challenge-response authentication for browser extensions.

Protocol:
  1. Addon registers its Ed25519 public key via POST /addon/register
  2. Server returns a random 32-byte challenge
  3. Addon signs the challenge and sends it back via POST /addon/auth
  4. Server verifies the signature and issues an HMAC-SHA256 session token
  5. All subsequent requests carry the session token in X-Addon-Session header

Sessions expire after a configurable TTL (default 1 hour).
"""

import base64
import hashlib
import hmac
import logging
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Optional

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from cryptography.hazmat.primitives import serialization

logger = logging.getLogger(__name__)

# Server secret used to sign session tokens — generated once per boot
_SERVER_SECRET: Optional[bytes] = None


def _get_server_secret() -> bytes:
    """Get or generate the per-boot server secret for HMAC signing."""
    global _SERVER_SECRET
    if _SERVER_SECRET is None:
        secret_path = Path.home() / ".closedclaw" / "addon_secret"
        secret_path.parent.mkdir(parents=True, exist_ok=True)
        if secret_path.exists():
            _SERVER_SECRET = secret_path.read_bytes()
        else:
            _SERVER_SECRET = os.urandom(32)
            secret_path.write_bytes(_SERVER_SECRET)
            try:
                secret_path.chmod(0o600)
            except OSError:
                pass
    return _SERVER_SECRET


@dataclass
class AddonSession:
    """A registered addon session."""
    addon_id: str
    pubkey_b64: str
    pubkey: Ed25519PublicKey
    challenge: bytes
    challenge_issued_at: float
    session_token: Optional[str] = None
    authenticated: bool = False
    created_at: float = field(default_factory=time.time)
    last_active: float = field(default_factory=time.time)
    expires_at: float = 0.0


class AddonSessionManager:
    """Manages addon registration, authentication, and session lifecycle."""

    def __init__(
        self,
        session_ttl_seconds: int = 3600,
        challenge_ttl_seconds: int = 60,
        max_sessions: int = 50,
    ):
        self._sessions: Dict[str, AddonSession] = {}  # addon_id -> session
        self._token_index: Dict[str, str] = {}  # session_token -> addon_id
        self._session_ttl = session_ttl_seconds
        self._challenge_ttl = challenge_ttl_seconds
        self._max_sessions = max_sessions

    def register_addon(self, pubkey_b64: str) -> dict:
        """Register an addon's Ed25519 public key and return a challenge.

        Args:
            pubkey_b64: Base64-encoded raw Ed25519 public key (32 bytes)

        Returns:
            dict with addon_id and session_challenge (base64)
        """
        self._evict_expired()

        # Parse the public key
        try:
            raw_bytes = base64.b64decode(pubkey_b64)
            if len(raw_bytes) != 32:
                raise ValueError(f"Expected 32 bytes, got {len(raw_bytes)}")
            pubkey = Ed25519PublicKey.from_public_bytes(raw_bytes)
        except Exception as exc:
            raise ValueError(f"Invalid Ed25519 public key: {exc}") from exc

        # Generate addon_id from pubkey hash
        addon_id = hashlib.sha256(raw_bytes).hexdigest()[:16]

        # Generate challenge
        challenge = os.urandom(32)

        # Create or overwrite session
        session = AddonSession(
            addon_id=addon_id,
            pubkey_b64=pubkey_b64,
            pubkey=pubkey,
            challenge=challenge,
            challenge_issued_at=time.time(),
        )
        self._sessions[addon_id] = session

        # Enforce max sessions
        if len(self._sessions) > self._max_sessions:
            self._evict_oldest()

        logger.info("Addon registered: %s", addon_id)
        return {
            "addon_id": addon_id,
            "session_challenge": base64.b64encode(challenge).decode(),
        }

    def authenticate(self, session_challenge_b64: str, signature_b64: str) -> dict:
        """Verify the signed challenge and issue a session token.

        Args:
            session_challenge_b64: The challenge that was returned from register
            signature_b64: Ed25519 signature of the challenge bytes

        Returns:
            dict with session_token and expires_in
        """
        challenge_bytes = base64.b64decode(session_challenge_b64)

        # Find the session that owns this challenge
        session = None
        for s in self._sessions.values():
            if s.challenge == challenge_bytes:
                session = s
                break

        if session is None:
            raise ValueError("Unknown or expired challenge")

        # Check challenge TTL
        if time.time() - session.challenge_issued_at > self._challenge_ttl:
            del self._sessions[session.addon_id]
            raise ValueError("Challenge expired")

        # Verify Ed25519 signature
        sig_bytes = base64.b64decode(signature_b64)
        try:
            session.pubkey.verify(sig_bytes, challenge_bytes)
        except Exception:
            raise ValueError("Invalid signature — authentication failed")

        # Issue session token: HMAC-SHA256(challenge + addon_id + server_secret)
        server_secret = _get_server_secret()
        token_data = challenge_bytes + session.addon_id.encode()
        session_token = hmac.new(server_secret, token_data, hashlib.sha256).hexdigest()

        # Update session
        now = time.time()
        session.session_token = session_token
        session.authenticated = True
        session.last_active = now
        session.expires_at = now + self._session_ttl

        # Index by token for fast lookup
        self._token_index[session_token] = session.addon_id

        # Clear the challenge so it can't be reused
        session.challenge = b""

        logger.info("Addon authenticated: %s (expires in %ds)", session.addon_id, self._session_ttl)
        return {
            "session_token": session_token,
            "addon_id": session.addon_id,
            "expires_in": self._session_ttl,
        }

    def validate_session(self, session_token: str) -> Optional[AddonSession]:
        """Validate a session token and return the session if valid.

        Returns None if the token is invalid or expired.
        """
        addon_id = self._token_index.get(session_token)
        if addon_id is None:
            return None

        session = self._sessions.get(addon_id)
        if session is None:
            self._token_index.pop(session_token, None)
            return None

        if not session.authenticated:
            return None

        now = time.time()
        if now > session.expires_at:
            # Expired — clean up
            self._token_index.pop(session_token, None)
            del self._sessions[addon_id]
            return None

        session.last_active = now
        return session

    def revoke_session(self, session_token: str) -> bool:
        """Revoke an active session. Returns True if found and revoked."""
        addon_id = self._token_index.pop(session_token, None)
        if addon_id and addon_id in self._sessions:
            del self._sessions[addon_id]
            logger.info("Addon session revoked: %s", addon_id)
            return True
        return False

    def get_active_sessions(self) -> list[dict]:
        """List all active sessions (for admin/status endpoints)."""
        self._evict_expired()
        result = []
        for s in self._sessions.values():
            if s.authenticated:
                result.append({
                    "addon_id": s.addon_id,
                    "authenticated": s.authenticated,
                    "created_at": s.created_at,
                    "last_active": s.last_active,
                    "expires_at": s.expires_at,
                })
        return result

    def _evict_expired(self) -> None:
        """Remove expired sessions."""
        now = time.time()
        expired = [
            aid for aid, s in self._sessions.items()
            if s.authenticated and s.expires_at > 0 and now > s.expires_at
        ]
        for aid in expired:
            session = self._sessions.pop(aid)
            if session.session_token:
                self._token_index.pop(session.session_token, None)

    def _evict_oldest(self) -> None:
        """Remove the oldest session to stay under max_sessions."""
        if not self._sessions:
            return
        oldest_id = min(self._sessions, key=lambda k: self._sessions[k].created_at)
        session = self._sessions.pop(oldest_id)
        if session.session_token:
            self._token_index.pop(session.session_token, None)


# Singleton
_addon_manager: Optional[AddonSessionManager] = None


def get_addon_session_manager() -> AddonSessionManager:
    """Get the singleton AddonSessionManager."""
    global _addon_manager
    if _addon_manager is None:
        _addon_manager = AddonSessionManager()
    return _addon_manager
