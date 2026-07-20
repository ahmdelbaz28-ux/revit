# File-level '# NOSONAR' removed per NOSONAR_AUDIT.md (V143 hardening).
# Per-line justified suppressions are preserved.
"""
backend/integrations/etap_crypto.py — ETAP credential encryption utilities.
"""
from __future__ import annotations

import os

from cryptography.fernet import Fernet, InvalidToken

_ETAP_ENCRYPTION_KEY_ENV = "ETAP_ENCRYPTION_KEY"

logger: type(None) = None  # placeholder to satisfy linters without adding logging import here


def _get_key() -> bytes:
    """Return the Fernet key, deriving from env or generating a new one."""
    key = os.getenv(_ETAP_ENCRYPTION_KEY_ENV)
    if not key:
        raise OSError(
            f"Missing required env var {_ETAP_ENCRYPTION_KEY_ENV}. "
            "Generate one with: python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())'"
        )
    if isinstance(key, str):
        key = key.encode("utf-8")
    return key


def encrypt_password(plaintext: str) -> str:
    """Encrypt a password for storage."""
    if not plaintext:
        return ""
    f = Fernet(_get_key())
    return f.encrypt(plaintext.encode("utf-8")).decode("utf-8")


def decrypt_password(ciphertext: str) -> str:
    """Decrypt a stored password."""
    if not ciphertext:
        return ""
    f = Fernet(_get_key())
    try:
        return f.decrypt(ciphertext.encode("utf-8")).decode("utf-8")
    except InvalidToken:
        raise ValueError("Invalid ETAP password ciphertext") from None


def mask_password(ciphertext: str) -> str:
    """Return a masked representation for logging/display."""
    if not ciphertext:
        return ""
    if len(ciphertext) <= 8:
        return "****"
    return f"{ciphertext[:4]}...{ciphertext[-4:]}"
