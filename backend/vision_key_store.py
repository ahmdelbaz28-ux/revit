"""
backend/vision_key_store.py — AES-256-GCM encrypted storage for Vision API keys.

Implements the V151 Vision API Keys feature per agent.md:

  🌐 Flow:
    1. Customer opens Settings page on Vercel → sees tab "Vision API Keys"
    2. Customer enters OpenAI key + base URL + model name
    3. Frontend POSTs to /api/v1/settings/keys/openai (HF Space backend)
    4. Backend encrypts key with AES-256-GCM and stores in SQLite
    5. Backend returns masked key (fe_***...***f4c1)
    6. CUA Loop reads key from DB (prefers DB over env vars)
    7. OpenAI Vision analyzes screenshots using entered key

  🔒 Security:
    ✅ Key encrypted with AES-256-GCM in DB (authenticated encryption)
    ✅ Plaintext never logged, never returned to frontend (masked: sk-***...***)
    ✅ Optional — system works without it (OpenCV fallback in cua_loop)
    ✅ Customer can add/delete/update anytime
    ✅ Wrong key → automatic fallback

DESIGN NOTES
------------
1. AES-256-GCM (not Fernet) is used because we need explicit control over the
   nonce length and AAD (additional authenticated data). GCM provides both
   confidentiality and integrity — tampering with the ciphertext or the AAD
   causes decryption to fail.

2. The master encryption key is derived as follows (in priority order):
   a. `FIREAI_VISION_KEY_ENCRYPTION_KEY` env var (hex or bytes, 32 bytes raw)
   b. `FIREAI_VISION_KEY_FILE` env var pointing to a 32-byte file (mode 0600)
   c. Default file: `<db_dir>/vision_key_master.key` (auto-generated, mode 0600)
   d. Ephemeral 32-byte random key (in-memory only, logged with WARNING)
      — keys won't survive process restart but the system remains functional.

3. The masked form `fe_***...***f4c1` exposes only:
   - First 2 chars of the plaintext (helps user identify the key)
   - Last 4 chars of the plaintext (helps user verify identity)
   - Middle is replaced with `***...***`
   The masking is applied to the RAW key BEFORE encryption, so the mask is
   derived from the plaintext at the moment of storage. We store the mask
   alongside the ciphertext so we can return it on GET without decrypting.

4. All functions are thread-safe (the file-backed master key uses a lock to
   prevent TOCTOU races on first generation, mirroring the pattern in
   backend/api_keys.py::_load_server_secret).
"""

from __future__ import annotations

import base64
import hashlib
import logging
import os
import secrets
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

# AES-256-GCM via cryptography.hazmat — provides authenticated encryption
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

logger = logging.getLogger(__name__)

# ── Master key management ────────────────────────────────────────────────────

_MASTER_KEY: Optional[bytes] = None
_MASTER_KEY_LOCK = threading.Lock()
_MASTER_KEY_FILE_DEFAULT = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "..",
    "db",
    "vision_key_master.key",
)

# AES-256-GCM parameters
_KEY_LEN = 32  # 256 bits
_NONCE_LEN = 12  # 96 bits — recommended GCM nonce size
_AAD = b"fireai.vision_api_keys.v1"  # additional authenticated data


def _normalize_master_key(raw: bytes | str) -> bytes:
    """Coerce a hex string, base64 string, or raw bytes into 32 raw bytes."""
    if isinstance(raw, str):
        s = raw.strip()
        # Try hex first
        try:
            b = bytes.fromhex(s)
            if len(b) == _KEY_LEN:
                return b
        except ValueError:
            pass
        # Try base64
        try:
            b = base64.b64decode(s, validate=True)
            if len(b) == _KEY_LEN:
                return b
        except (ValueError, base64.binascii.Error):
            pass
        # Fallback: derive via SHA-256 (deterministic, 32 bytes)
        return hashlib.sha256(s.encode("utf-8")).digest()
    if isinstance(raw, (bytes, bytearray)):
        if len(raw) == _KEY_LEN:
            return bytes(raw)
        # Derive via SHA-256 if not already 32 bytes
        return hashlib.sha256(bytes(raw)).digest()
    raise TypeError(f"Unsupported master key type: {type(raw)!r}")


def _load_master_key() -> bytes:
    """
    Load (or generate) the AES-256 master key used for Vision API key encryption.

    Priority order:
      1. FIREAI_VISION_KEY_ENCRYPTION_KEY env var
      2. FIREAI_VISION_KEY_FILE env var (path to a 32-byte file, mode 0600)
      3. <db_dir>/vision_key_master.key (auto-generated, mode 0600)
      4. Ephemeral random key (WARNING — keys won't survive restart)

    Thread-safe via _MASTER_KEY_LOCK with double-checked locking.
    """
    global _MASTER_KEY
    if _MASTER_KEY is not None:
        return _MASTER_KEY

    with _MASTER_KEY_LOCK:
        if _MASTER_KEY is not None:
            return _MASTER_KEY

        # 1. Env var
        env_val = os.environ.get("FIREAI_VISION_KEY_ENCRYPTION_KEY")
        if env_val:
            _MASTER_KEY = _normalize_master_key(env_val)
            logger.info("Vision key master loaded from FIREAI_VISION_KEY_ENCRYPTION_KEY env var")
            return _MASTER_KEY

        # 2. Env var pointing to a file
        env_file = os.environ.get("FIREAI_VISION_KEY_FILE")
        if env_file:
            p = Path(env_file)
            if p.exists():
                raw = p.read_bytes().strip()
                if raw:
                    _MASTER_KEY = _normalize_master_key(raw)
                    logger.info("Vision key master loaded from FIREAI_VISION_KEY_FILE=%s", env_file)
                    return _MASTER_KEY

        # 3. Default file (auto-generate if missing)
        default_path = Path(os.environ.get("FIREAI_VISION_KEY_FILE", _MASTER_KEY_FILE_DEFAULT)).resolve()
        try:
            if default_path.exists():
                raw = default_path.read_bytes().strip()
                if len(raw) >= _KEY_LEN:
                    _MASTER_KEY = _normalize_master_key(raw)
                    logger.info("Vision key master loaded from default file %s", default_path)
                    return _MASTER_KEY
            # Generate a new 32-byte key
            default_path.parent.mkdir(parents=True, exist_ok=True)
            new_key = secrets.token_bytes(_KEY_LEN)
            # O_CREAT|O_EXCL — atomic create-or-fail (prevents TOCTOU race)
            try:
                fd = os.open(str(default_path), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
                try:
                    os.write(fd, new_key)
                    os.fsync(fd)
                finally:
                    os.close(fd)
                _MASTER_KEY = new_key
                logger.info("Vision key master generated at %s (mode 0600)", default_path)
                return _MASTER_KEY
            except FileExistsError:
                # Another process created the file between our check and open.
                raw = default_path.read_bytes().strip()
                if len(raw) >= _KEY_LEN:
                    _MASTER_KEY = _normalize_master_key(raw)
                    logger.info("Vision key master reused (race avoided) at %s", default_path)
                    return _MASTER_KEY
                # Invalid file — fall through to ephemeral
                logger.warning(
                    "Vision key master file %s exists but is invalid; using ephemeral key",
                    default_path,
                )
        except OSError as e:
            logger.warning(
                "Could not persist vision key master at %s (%s); using ephemeral key",
                default_path,
                e,
            )

        # 4. Ephemeral fallback (in-memory only)
        _MASTER_KEY = secrets.token_bytes(_KEY_LEN)
        logger.warning(
            "Using EPHEMERAL vision key master — encrypted keys will NOT survive process restart. "
            "Set FIREAI_VISION_KEY_ENCRYPTION_KEY or ensure the db/ directory is writable."
        )
        return _MASTER_KEY


# ── Encrypt / decrypt primitives ─────────────────────────────────────────────


def encrypt_key(plaintext: str) -> str:
    """
    Encrypt a plaintext Vision API key with AES-256-GCM.

    Returns a string of the form: `v1$<base64(nonce)>$<base64(ciphertext+tag)>`
    where:
      - nonce is 12 bytes (96 bits, GCM standard)
      - ciphertext+tag is the GCM output (tag is appended by AESGCM.encrypt)
      - the version prefix `v1$` allows future algorithm upgrades

    The AAD is the constant _AAD, binding the ciphertext to this application
    context (defends against cross-protocol key confusion).
    """
    if not plaintext:
        raise ValueError("plaintext key must not be empty")
    key = _load_master_key()
    nonce = secrets.token_bytes(_NONCE_LEN)
    aesgcm = AESGCM(key)
    # AESGCM.encrypt returns ciphertext + 16-byte tag appended
    ct = aesgcm.encrypt(nonce, plaintext.encode("utf-8"), _AAD)
    return f"v1${base64.b64encode(nonce).decode('ascii')}${base64.b64encode(ct).decode('ascii')}"


def decrypt_key(encrypted: str) -> str:
    """
    Decrypt a Vision API key previously encrypted with encrypt_key().

    Raises ValueError if the format is wrong or authentication fails.
    NEVER raises a custom exception type that might leak the plaintext —
    the AESGCM InvalidTag exception is caught and re-raised as a generic
    ValueError with no key material in the message.
    """
    if not encrypted or not isinstance(encrypted, str):
        raise ValueError("encrypted key is empty or not a string")
    parts = encrypted.split("$", 2)
    if len(parts) != 3 or parts[0] != "v1":
        raise ValueError("unsupported encrypted key format")
    try:
        nonce = base64.b64decode(parts[1])
        ct = base64.b64decode(parts[2])
    except (ValueError, base64.binascii.Error) as e:
        raise ValueError("malformed base64 in encrypted key") from e
    if len(nonce) != _NONCE_LEN:
        raise ValueError(f"nonce length mismatch (got {len(nonce)}, expected {_NONCE_LEN})")
    key = _load_master_key()
    aesgcm = AESGCM(key)
    try:
        plaintext_bytes = aesgcm.decrypt(nonce, ct, _AAD)
    except Exception as e:
        # Do NOT include the exception message — it could leak bytes.
        # Log the original exception class name at DEBUG for ops debugging.
        logger.debug("Vision key decryption failed: %s", type(e).__name__)
        raise ValueError("decryption failed (authentication tag mismatch or corrupted data)") from e
    return plaintext_bytes.decode("utf-8")


# ── Masking ──────────────────────────────────────────────────────────────────


def mask_key(plaintext: str) -> str:
    """
    Return a masked representation of the key: `fe_***...***f4c1`.

    Exposes only:
      - The literal prefix `fe_` (a stable FireAI marker, NOT from the key)
      - The first 2 chars of the plaintext key (helps the user identify it)
      - `***...***` for the middle
      - The last 4 chars of the plaintext key (helps user verify identity)

    Examples:
      sk-proj-abc123XYZ789qwer  →  fe_sk***...***qwer
      ghp_abcdef1234567890abcd  →  fe_gh***...***abcd

    For very short keys (<=6 chars), the suffix is truncated to avoid
    exposing the entire key:
      abc  →  fe_ab***...***
    """
    if not plaintext:
        return "fe_***...***"
    # Sanitize: never include newlines or whitespace in the masked output
    cleaned = plaintext.strip()
    if len(cleaned) <= 6:
        return f"fe_{cleaned[:2]}***...***"
    prefix = cleaned[:2]
    suffix = cleaned[-4:]
    return f"fe_{prefix}***...***{suffix}"


# ── Dataclass for stored entries ─────────────────────────────────────────────


@dataclass(frozen=True)
class VisionApiKeyRecord:
    """A stored Vision API key record. The plaintext is NEVER in this struct."""

    id: str
    provider: str  # e.g. "openai"
    masked_key: str  # e.g. "fe_sk***...***f4c1"
    base_url: str
    model_name: str
    created_at: str
    updated_at: str
    last_used_at: Optional[str]
    is_active: bool


def utc_now_iso() -> str:
    """Return current UTC time as ISO 8601 string (matches DB datetime format)."""
    return datetime.now(timezone.utc).isoformat()


__all__ = [
    "VisionApiKeyRecord",
    "encrypt_key",
    "decrypt_key",
    "mask_key",
    "utc_now_iso",
]
