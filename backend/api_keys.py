"""API Key management with role-based access control.

Each API key is associated with a role (admin, engineer, viewer).
Keys are stored as SHA-256 hashes (never plaintext).
On first startup, creates an admin key from FIREAI_API_KEY env var.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import secrets
import threading
from pathlib import Path
from typing import Optional

# Import bcrypt for stronger password hashing
try:
    import bcrypt
    HAS_BCRYPT = True
except ImportError:
    HAS_BCRYPT = False
    logging.warning("bcrypt not available - using SHA-256 for API key hashing (less secure)")

from backend.rbac import APIKeyInfo, Role

logger = logging.getLogger(__name__)

KEYS_FILE = os.getenv("FIREAI_API_KEYS_FILE", "db/api_keys.json")

# Thread-safety lock for TOCTOU prevention on load-modify-save cycles
_keys_lock = threading.Lock()

# ── STRESS-TEST FIX #1: fast O(1) lookup index ─────────────────────────────
# A deterministic HMAC-SHA256 over (server_secret, key) is used as the dict
# key. This makes validate_api_key O(1) (vs the original O(N) bcrypt.checkpw
# iteration that allowed CPU-exhaustion DoS). The bcrypt hash is STILL stored
# as a value field and verified on each successful lookup to keep brute-force
# resistance; the HMAC index just lets us find the right entry in O(1).
#
# The server secret is generated once and persisted alongside the keys file
# so that restarts preserve lookup determinism. If the secret file is lost,
# all keys become invalid (fail-closed — admin must re-issue keys).
_SERVER_SECRET_FILE = os.getenv(
    "FIREAI_API_KEYS_SECRET_FILE",
    os.path.join(os.path.dirname(KEYS_FILE) or ".", "api_keys.secret"),
)
_SERVER_SECRET: bytes = b""


def _load_server_secret() -> bytes:
    """Load or create the per-server HMAC secret used for fast key lookup."""
    global _SERVER_SECRET
    if _SERVER_SECRET:
        return _SERVER_SECRET
    path = Path(_SERVER_SECRET_FILE)
    try:
        if path.exists():
            _SERVER_SECRET = path.read_bytes().strip()
            if len(_SERVER_SECRET) >= 32:
                return _SERVER_SECRET
        # Generate a new 32-byte secret
        path.parent.mkdir(parents=True, exist_ok=True)
        _SERVER_SECRET = secrets.token_bytes(32)
        # Write with restrictive permissions (0o600)
        fd = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        try:
            os.write(fd, _SERVER_SECRET)
        finally:
            os.close(fd)
        logger.info("Generated new API-key lookup secret at %s", path)
    except OSError as e:
        # If we can't persist a secret, generate an ephemeral one. Keys won't
        # survive restart but the system remains functional.
        logger.warning("Could not persist API-key secret (%s); using ephemeral", e)
        _SERVER_SECRET = secrets.token_bytes(32)
    return _SERVER_SECRET


def _lookup_key(key: str) -> str:
    """Compute the deterministic lookup key (HMAC-SHA256) for an API key.

    This is the O(1) index into the keys dict. The same input always yields
    the same output, so we can find a stored key without iterating.
    """
    secret = _load_server_secret()
    return "hk$" + hmac.new(secret, key.encode(), hashlib.sha256).hexdigest()


def _hash_key(key: str) -> str:
    """Hash an API key using bcrypt if available, otherwise HMAC-SHA256 with salt.

    FIX #30: Previously the SHA-256 fallback had no salt, making all
    identical keys produce the same hash (vulnerable to rainbow tables).
    Now uses HMAC-SHA256 with a random salt stored alongside the hash.

    STRESS-TEST FIX #1: This function is INTENTIONALLY non-deterministic
    (random salt per call). It is only used when STORING a new key.
    Validation MUST use _verify_key() with the stored hash, NOT re-hash
    the input and compare. The previous validate_api_key did exactly that,
    making authentication fail 100% of the time when bcrypt was enabled.
    """
    if HAS_BCRYPT:
        return bcrypt.hashpw(key.encode(), bcrypt.gensalt()).decode('utf-8')
    else:
        # Fallback: HMAC-SHA256 with random salt
        salt = secrets.token_hex(16)
        h = hmac.new(salt.encode(), key.encode(), hashlib.sha256).hexdigest()
        return f"hmac-sha256${salt}${h}"


def _verify_key(key: str, hashed_key: str) -> bool:
    """Verify an API key against its stored hash.

    STRESS-TEST FIX #1: This is the ONLY correct way to verify a key against
    a stored bcrypt hash. Re-hashing the input (as the old validate_api_key
    did) will NEVER match because bcrypt uses a random salt per call.
    """
    if not hashed_key:
        return False
    try:
        if HAS_BCRYPT and hashed_key.startswith('$2'):
            return bcrypt.checkpw(key.encode(), hashed_key.encode())
        elif hashed_key.startswith("hmac-sha256$"):
            # FIX #30: Verify HMAC-SHA256 with salt
            try:
                _, salt, stored_hash = hashed_key.split("$", 2)
                computed = hmac.new(salt.encode(), key.encode(), hashlib.sha256).hexdigest()
                return hmac.compare_digest(computed, stored_hash)
            except (ValueError, IndexError):
                return False
        elif hashed_key.startswith("hk$"):
            # This is a lookup key, not a verification hash — reject.
            return False
        else:
            # Legacy: plain SHA-256 (no salt) for backwards compatibility
            return hmac.compare_digest(
                hashlib.sha256(key.encode()).hexdigest(),
                hashed_key,
            )
    except (ValueError, TypeError):
        return False


def _load_keys() -> dict:
    """Load API keys from the JSON file."""
    path = Path(KEYS_FILE)
    if not path.exists():
        return {}
    try:
        with open(path, "r") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        logger.warning("Failed to load API keys file: %s", e)
        return {}


def _save_keys(keys: dict) -> None:
    """Save API keys to the JSON file.

    STRESS-TEST FIX #4: Atomic write — write to a temp file in the same
    directory, fsync, then atomically rename. Prevents corruption from
    crashes mid-write or interleaved writes from concurrent admin ops.
    """
    path = Path(KEYS_FILE)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    # Write to temp file
    fd = os.open(str(tmp_path), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(keys, f, indent=2)
            f.flush()
            os.fsync(f.fileno())
    except Exception:
        # Make sure we don't leave a stale .tmp file
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise
    # Atomic rename (POSIX guarantees atomicity when src and dst are on the
    # same filesystem). On Windows, os.replace is atomic too.
    os.replace(tmp_path, path)


def _ensure_default_admin_key() -> None:
    """Ensure at least one admin key exists (from env var on first run).

    STRESS-TEST FIX #1: Uses the new add_api_key() which stores both the
    HMAC lookup key and the bcrypt hash, so the key is actually usable.
    """
    with _keys_lock:
        keys = _load_keys()
        if not keys:
            env_key = os.getenv("FIREAI_API_KEY")
            if env_key:
                # Release the lock and call add_api_key (which re-acquires it)
                pass
            else:
                return
        else:
            return
    # Outside the lock — add_api_key will take the lock itself
    env_key = os.getenv("FIREAI_API_KEY")
    if env_key:
        add_api_key(env_key, Role.ADMIN, "Default admin key (from FIREAI_API_KEY)")
        logger.info("Created default admin API key from FIREAI_API_KEY env var")


def add_api_key(key: str, role: Role, description: str = "") -> str:
    """Add a new API key. Returns the key hash.

    STRESS-TEST FIX #1: We now store BOTH a deterministic lookup key (HMAC)
    AND a bcrypt hash of the key. The lookup key is the dict key for O(1)
    validation; the bcrypt hash is stored as a value field and verified
    on each successful lookup. This prevents the original O(N) bcrypt
    iteration that allowed CPU DoS.
    """
    with _keys_lock:
        keys = _load_keys()
        lookup = _lookup_key(key)
        # If key already exists, fail (don't silently overwrite)
        if lookup in keys:
            logger.warning("Attempted to add duplicate API key (role=%s)", role.value)
            # Update role/description instead of creating duplicate
            existing = keys[lookup]
            # Preserve backward compat: existing entry may not have bcrypt_hash
            key_hash = existing.get("bcrypt_hash", existing.get("key_hash", ""))
        else:
            key_hash = _hash_key(key)
        keys[lookup] = {
            "role": role.value,
            "description": description,
            "bcrypt_hash": key_hash,
            # Legacy field name for backward-compat with older readers
            "key_hash": key_hash,
        }
        _save_keys(keys)
    logger.info("Added API key with role=%s, desc=%s", role.value, description)
    return key_hash


def validate_api_key(key: str) -> Optional[APIKeyInfo]:
    """Validate an API key and return its info including role.

    Returns None if the key is invalid or empty.

    STRESS-TEST FIX #1: Previously this function did:
        key_hash = _hash_key(key)   # NEW random salt → new hash
        info = keys.get(key_hash)   # NEVER matches the stored hash
    Making authentication fail 100% of the time when bcrypt was enabled.

    The fix uses a deterministic HMAC-SHA256 lookup key for O(1) finding,
    then verifies the candidate key against the stored bcrypt hash. If the
    bcrypt hash is missing (legacy entry), we fall back to trusting the
    lookup match (still cryptographically bound to the server secret).
    """
    if not key:
        return None
    lookup = _lookup_key(key)
    with _keys_lock:
        keys = _load_keys()
        info = keys.get(lookup)
        if not info:
            return None
        # Copy out the fields we need under the lock, then release.
        stored_hash = info.get("bcrypt_hash") or info.get("key_hash", "")
        role_str = info.get("role", Role.VIEWER.value)
        description = info.get("description", "")
    # Verify the key against the stored bcrypt hash OUTSIDE the lock
    # (bcrypt.checkpw is slow — don't hold the lock during it).
    if stored_hash:
        if not _verify_key(key, stored_hash):
            # Lookup matched but bcrypt verification failed — possible
            # HMAC collision or tampering. Reject.
            logger.warning("API key HMAC lookup matched but bcrypt verify failed")
            return None
    return APIKeyInfo(
        key_hash=lookup,
        role=Role(role_str),
        description=description,
    )


def validate_api_key_by_hash(key_hash: str) -> Optional[APIKeyInfo]:
    """Validate an API key by its hash (for internal lookups).

    Returns None if the hash is not found.

    STRESS-TEST FIX #1: Accepts either the new HMAC lookup key ("hk$...")
    or the legacy bcrypt hash. For legacy hashes, we iterate the dict to
    find a matching bcrypt_hash field (slower but backward compatible).
    """
    if not key_hash:
        return None
    with _keys_lock:
        keys = _load_keys()
        # Fast path: key_hash is the new HMAC lookup key
        info = keys.get(key_hash)
        if info is None:
            # Slow path: key_hash is a legacy bcrypt hash — scan values
            for lk, v in keys.items():
                if v.get("bcrypt_hash") == key_hash or v.get("key_hash") == key_hash:
                    info = v
                    key_hash = lk  # normalize to lookup key
                    break
        if not info:
            return None
        return APIKeyInfo(
            key_hash=key_hash,
            role=Role(info["role"]),
            description=info.get("description", ""),
        )


def generate_api_key(role: Role, description: str = "") -> str:
    """Generate a new random API key with the given role.

    Returns the plaintext key (show once!).
    """
    key = f"fireai_{secrets.token_urlsafe(32)}"
    add_api_key(key, role, description)
    return key


def list_api_keys() -> list:
    """List all API keys (without the actual key values)."""
    with _keys_lock:
        keys = _load_keys()
    return [
        {
            "key_hash": kh,
            "role": info["role"],
            "description": info.get("description", ""),
        }
        for kh, info in keys.items()
    ]


def delete_api_key(key_hash: str) -> bool:
    """Delete an API key by its hash (or lookup key).

    STRESS-TEST FIX #1: Accepts both old (bcrypt hash) and new (HMAC lookup)
    key identifiers for backward compatibility.
    """
    with _keys_lock:
        keys = _load_keys()
        # Fast path: key_hash is the new HMAC lookup key
        if key_hash in keys:
            del keys[key_hash]
            _save_keys(keys)
            logger.info("Deleted API key %s...", key_hash[:8])
            return True
        # Slow path: scan for matching bcrypt_hash field
        for lk, v in list(keys.items()):
            if v.get("bcrypt_hash") == key_hash or v.get("key_hash") == key_hash:
                del keys[lk]
                _save_keys(keys)
                logger.info("Deleted API key %s...", lk[:8])
                return True
    return False


def update_api_key_role(key_hash: str, role: Role) -> bool:
    """Update the role of an existing API key."""
    with _keys_lock:
        keys = _load_keys()
        # Fast path
        if key_hash in keys:
            keys[key_hash]["role"] = role.value
            _save_keys(keys)
            logger.info("Updated API key %s... role to %s", key_hash[:8], role.value)
            return True
        # Slow path: scan for matching bcrypt_hash
        for lk, v in list(keys.items()):
            if v.get("bcrypt_hash") == key_hash or v.get("key_hash") == key_hash:
                keys[lk]["role"] = role.value
                _save_keys(keys)
                logger.info("Updated API key %s... role to %s", lk[:8], role.value)
                return True
    return False


# Initialize on import
_ensure_default_admin_key()
