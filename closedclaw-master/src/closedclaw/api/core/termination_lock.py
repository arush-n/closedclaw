"""
Termination Lock — prevents unauthorized server shutdown.

Intercepts SIGTERM and SIGINT signals. The server can only be shut down
via the DELETE /server/shutdown endpoint with the correct password, or
by explicitly unlocking the lock first.

Password is stored as an Argon2id hash in ~/.closedclaw/shutdown.key.
On first boot (no hash file), the user is prompted to set a password,
or a random one is generated and stored.
"""

import hashlib
import logging
import os
import signal
import sys
import threading
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

_SHUTDOWN_KEY_FILE = Path.home() / ".closedclaw" / "shutdown.key"


def _hash_password(password: str, salt: Optional[bytes] = None) -> tuple[bytes, bytes]:
    """Hash a password with Argon2id via the cryptography library's Scrypt fallback.

    We try argon2-cffi first, falling back to PBKDF2-HMAC-SHA256 if unavailable.
    Returns (hash_bytes, salt).
    """
    if salt is None:
        salt = os.urandom(16)

    try:
        from argon2.low_level import Type, hash_secret_raw

        h = hash_secret_raw(
            secret=password.encode(),
            salt=salt,
            time_cost=3,
            memory_cost=65536,
            parallelism=4,
            hash_len=32,
            type=Type.ID,
        )
        return h, salt
    except ImportError:
        # Fallback: PBKDF2 with high iteration count
        h = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, iterations=600_000, dklen=32)
        return h, salt


def _verify_password(password: str, stored_hash: bytes, salt: bytes) -> bool:
    """Verify a password against a stored hash."""
    candidate, _ = _hash_password(password, salt=salt)
    return candidate == stored_hash


class TerminationLock:
    """Blocks SIGTERM/SIGINT until the correct shutdown password is provided."""

    def __init__(self, key_file: Optional[Path] = None):
        self._key_file = key_file or _SHUTDOWN_KEY_FILE
        self._locked = True
        self._shutdown_event = threading.Event()
        self._salt: bytes = b""
        self._hash: bytes = b""
        self._original_sigterm = None
        self._original_sigint = None

    def install(self) -> None:
        """Install signal handlers and load or generate the shutdown password."""
        self._load_or_generate_key()
        self._original_sigterm = signal.getsignal(signal.SIGTERM)
        self._original_sigint = signal.getsignal(signal.SIGINT)
        signal.signal(signal.SIGTERM, self._handle_signal)
        signal.signal(signal.SIGINT, self._handle_signal)
        logger.info("Termination lock installed — shutdown requires password")

    def _handle_signal(self, signum: int, frame) -> None:
        """Intercept termination signals."""
        sig_name = signal.Signals(signum).name
        if not self._locked:
            logger.info("Termination lock unlocked — allowing %s", sig_name)
            self._shutdown_event.set()
            # Restore original handler and re-raise
            if signum == signal.SIGTERM and self._original_sigterm:
                signal.signal(signal.SIGTERM, self._original_sigterm)
                os.kill(os.getpid(), signal.SIGTERM)
            elif signum == signal.SIGINT and self._original_sigint:
                signal.signal(signal.SIGINT, self._original_sigint)
                os.kill(os.getpid(), signal.SIGINT)
            else:
                sys.exit(0)
        else:
            logger.warning(
                "Termination BLOCKED (%s) — send DELETE /server/shutdown with password",
                sig_name,
            )

    def unlock(self, password: str) -> bool:
        """Attempt to unlock the termination lock with a password.

        Returns True if the password is correct and the lock is now disengaged.
        """
        if _verify_password(password, self._hash, self._salt):
            self._locked = False
            logger.info("Termination lock UNLOCKED — server can now be shut down")
            return True
        logger.warning("Termination lock unlock FAILED — wrong password")
        return False

    @property
    def is_locked(self) -> bool:
        return self._locked

    def _load_or_generate_key(self) -> None:
        """Load existing shutdown key or generate a new one."""
        self._key_file.parent.mkdir(parents=True, exist_ok=True)

        if self._key_file.exists():
            data = self._key_file.read_bytes()
            if len(data) >= 48:  # 16 bytes salt + 32 bytes hash
                self._salt = data[:16]
                self._hash = data[16:48]
                return

        # Generate a random shutdown password and store its hash
        import secrets

        password = secrets.token_urlsafe(20)
        self._hash, self._salt = _hash_password(password)
        self._key_file.write_bytes(self._salt + self._hash)
        try:
            self._key_file.chmod(0o600)
        except OSError:
            pass

        # Display password ONCE in terminal — never written to disk as plaintext
        logger.warning(
            "SHUTDOWN PASSWORD (shown once, save it now): %s", password,
        )

        # Remove any legacy plaintext password file
        pw_file = self._key_file.with_suffix(".password")
        if pw_file.exists():
            pw_file.unlink(missing_ok=True)

    def set_password(self, new_password: str) -> None:
        """Set a new shutdown password (requires server restart to take effect on disk)."""
        self._hash, self._salt = _hash_password(new_password)
        self._key_file.parent.mkdir(parents=True, exist_ok=True)
        self._key_file.write_bytes(self._salt + self._hash)
        try:
            self._key_file.chmod(0o600)
        except OSError:
            pass
        # Remove the plaintext password file if it exists
        pw_file = self._key_file.with_suffix(".password")
        pw_file.unlink(missing_ok=True)
        logger.info("Shutdown password updated")


# Singleton
_termination_lock: Optional[TerminationLock] = None


def get_termination_lock() -> TerminationLock:
    """Get the singleton TerminationLock instance."""
    global _termination_lock
    if _termination_lock is None:
        _termination_lock = TerminationLock()
    return _termination_lock
