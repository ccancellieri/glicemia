"""Field-level encryption for sensitive data stored in the database.

Uses Fernet (AES-128-CBC + HMAC-SHA256) with a key derived from DB_PASSPHRASE
via PBKDF2. This provides defense-in-depth on top of SQLCipher's full-DB
encryption: even if an attacker gets a raw DB session, API keys and passwords
remain encrypted.

Usage in SQLAlchemy models:
    from app.crypto import EncryptedText
    api_key = Column(EncryptedText)       # transparently encrypts/decrypts
"""

import base64
import logging
from typing import Optional

from cryptography.fernet import Fernet
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes

from sqlalchemy import String, TypeDecorator

log = logging.getLogger(__name__)

_fernet: Optional[Fernet] = None
_SALT_FILE = ".field_encryption_salt"


def _get_or_create_salt() -> bytes:
    """Get the per-deployment random salt, creating it on first run.
    Stored alongside the database file for portability."""
    import os
    from app.config import settings

    salt_path = settings.DB_PATH.parent / _SALT_FILE
    if salt_path.exists():
        return salt_path.read_bytes()

    # First run: generate a cryptographically random 32-byte salt
    salt = os.urandom(32)
    salt_path.write_bytes(salt)
    os.chmod(str(salt_path), 0o600)
    log.info("Generated new field-encryption salt at %s", salt_path)
    return salt


def _get_fernet() -> Fernet:
    """Lazily initialize Fernet from DB_PASSPHRASE + per-deployment random salt."""
    global _fernet
    if _fernet is not None:
        return _fernet

    from app.config import settings

    if not settings.DB_PASSPHRASE:
        raise RuntimeError(
            "DB_PASSPHRASE must be set to encrypt sensitive fields. "
            "Set it in .env before running GliceMia."
        )

    if settings.DB_PASSPHRASE == "change_this_to_a_strong_passphrase":
        raise RuntimeError(
            "DB_PASSPHRASE is still the default placeholder! "
            "Change it to a strong random value before running GliceMia."
        )

    salt = _get_or_create_salt()

    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=480_000,
    )
    key = base64.urlsafe_b64encode(kdf.derive(settings.DB_PASSPHRASE.encode()))
    _fernet = Fernet(key)
    return _fernet


def encrypt(plaintext: str) -> str:
    """Encrypt a string. Returns a base64-encoded ciphertext."""
    f = _get_fernet()
    return f.encrypt(plaintext.encode()).decode("ascii")


def decrypt(ciphertext: str) -> str:
    """Decrypt a base64-encoded ciphertext. Returns plaintext."""
    f = _get_fernet()
    return f.decrypt(ciphertext.encode()).decode()


class EncryptedText(TypeDecorator):
    """SQLAlchemy column type that transparently encrypts on write and
    decrypts on read. Stores ciphertext as TEXT in the database.

    Null values pass through unchanged.
    """

    impl = String
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None or value == "":
            return value
        try:
            return encrypt(value)
        except Exception:
            log.exception("Failed to encrypt field value")
            raise

    def process_result_value(self, value, dialect):
        if value is None or value == "":
            return value
        try:
            return decrypt(value)
        except Exception:
            log.warning("Failed to decrypt field — returning raw value (migration?)")
            return value
