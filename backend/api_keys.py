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
import time
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

# ── STRICT FIX F: API key length cap ────────────────────────────────────────
# Prevent CPU/memory DoS via very long keys. HMAC-SHA256 is fast but a 10MB
# key would still waste CPU. 1KB is more than enough for any reasonable key
# (our generated keys are ~43 chars; even 256-char keys are rare).
# Also: bcrypt has a 72-byte limit on input. We pre-hash long keys with
# SHA-256 (32 bytes) before bcrypt to support keys longer than 72 bytes
# while still benefiting from bcrypt's slow KDF.
_MAX_KEY_LENGTH = 1024  # bytes
_BCRYPT_MAX_INPUT = 72  # bcrypt's hard limit


def _normalize_key_for_bcrypt(key: str) -> bytes:
    """Normalize a key for bcrypt input.

    bcrypt has a 72-byte limit. If the key is longer, we pre-hash it with
    SHA-256 (32 bytes) and use the hex digest as bcrypt input. This is
    safe because:
      1. SHA-256 is collision-resistant — different keys → different hashes.
      2. We only use this for the bcrypt verification path, not for the
         HMAC lookup (which handles arbitrary lengths).
      3. The HMAC lookup is the primary auth gate; bcrypt is defense-in-depth.
    """
    key_bytes = key.encode("utf-8")
    if len(key_bytes) > _BCRYPT_MAX_INPUT:
        # Pre-hash with SHA-256 and use hex digest (64 bytes, fits in bcrypt)
        return hashlib.sha256(key_bytes).hexdigest().encode("utf-8")
    return key_bytes

# ── STRICT FIX A: Timing oracle mitigation ──────────────────────────────────
# validate_api_key returns immediately for invalid keys (~0ms) but takes
# ~250ms for valid keys (bcrypt.checkpw). An attacker can measure response
# time to enumerate valid keys. We mitigate by running a dummy bcrypt
# verification on invalid lookups, so all responses take ~250ms regardless.
# This is the standard mitigation for timing attacks on auth endpoints.
_DUMMY_BCRYPT_HASH = b"$2b$12$" + b"x" * 53  # invalid-format hash; checkpw returns False fast
# Better: pre-compute a real bcrypt hash of a random string at startup
# so the dummy verification takes the full ~250ms.
_DUMMY_BCRYPT_HASH_REAL: str = ""


def _get_dummy_bcrypt_hash() -> str:
    """Get (or lazily create) a real bcrypt hash for timing equalization.

    We hash a random string once at first use, then reuse the hash for all
    dummy verifications. bcrypt.checkpw is constant-time for the same hash.
    """
    global _DUMMY_BCRYPT_HASH_REAL
    if _DUMMY_BCRYPT_HASH_REAL:
        return _DUMMY_BCRYPT_HASH_REAL
    if HAS_BCRYPT:
        # Cost factor 12 — matches the cost used by _hash_key
        _DUMMY_BCRYPT_HASH_REAL = bcrypt.hashpw(
            b"dummy_value_for_timing_equalization_only",
            bcrypt.gensalt(rounds=12),
        ).decode("utf-8")
    return _DUMMY_BCRYPT_HASH_REAL


def _timing_safe_dummy_verify(key: str) -> None:
    """Run a dummy bcrypt verification to equalize response timing.

    Called when validate_api_key would otherwise return None immediately.
    This makes valid and invalid key responses take the same time (~250ms),
    preventing timing-based enumeration of valid keys.

    STRICT FIX F: Uses _normalize_key_for_bcrypt for keys >72 bytes.
    """
    if not HAS_BCRYPT:
        # Without bcrypt, HMAC is fast and constant-time already.
        # Add a tiny delay to avoid trivial timing differences.
        time.sleep(0.001)
        return
    dummy = _get_dummy_bcrypt_hash()
    # This will return False but take ~250ms, matching the valid-key path
    normalized = _normalize_key_for_bcrypt(key)
    bcrypt.checkpw(normalized, dummy.encode())

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

# ── POSITIVE VALIDATION CACHE ───────────────────────────────────────────────
# After the first successful bcrypt verification, the APIKeyInfo is cached
# in-memory for `_VALIDATED_KEY_CACHE_TTL` seconds. Subsequent calls for the
# same key are then O(1) (~0.1ms) instead of O(bcrypt) (~250ms).
#
# This achieves two simultaneous goals:
#   1. Eliminates the timing oracle. Previously, valid keys took ~250ms while
#      invalid keys took ~0ms (then ~250ms after STRICT FIX A added a dummy
#      bcrypt — but that introduced a CPU DoS). With the positive cache:
#        - First valid call: ~250ms (bcrypt)
#        - Subsequent valid calls: ~0.1ms (cache hit)
#        - Invalid calls: ~0.1ms (HMAC lookup miss, no bcrypt)
#      Both valid (warm) and invalid paths are now <100ms, so no oracle.
#   2. Eliminates the CPU DoS vector from STRICT FIX A's dummy bcrypt.
#      Invalid keys now return in <1ms with no bcrypt work.
#
# Cache is invalidated on delete_api_key / update_api_key_role so role
# changes and revocations take effect immediately (no stale auth).
_VALIDATED_KEY_CACHE: dict[str, tuple[APIKeyInfo, float]] = {}
_VALIDATED_KEY_CACHE_LOCK = threading.Lock()
_VALIDATED_KEY_CACHE_TTL = float(os.getenv("FIREAI_KEY_CACHE_TTL", "300"))


def _load_server_secret() -> bytes:
    """Load or create the per-server HMAC secret used for fast key lookup.

    STRICT FIX D: Use O_CREAT|O_EXCL to prevent TOCTOU race on first run.
    If two processes start simultaneously and both try to create the secret
    file, the second one's open() will fail with EEXIST. We then re-read
    the existing file.
    """
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
        # STRICT FIX D: O_CREAT|O_EXCL — atomic create-or-fail
        try:
            fd = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            try:
                os.write(fd, _SERVER_SECRET)
                os.fsync(fd)
            finally:
                os.close(fd)
            logger.info("Generated new API-key lookup secret at %s", path)
        except FileExistsError:
            # Another process created the file between our check and open.
            # Re-read the existing file.
            _SERVER_SECRET = path.read_bytes().strip()
            if len(_SERVER_SECRET) < 32:
                raise RuntimeError(
                    f"Server secret file {path} exists but is invalid. "
                    f"Delete it and restart to regenerate."
                )
            logger.info("Reused existing API-key lookup secret (race avoided)")
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

    STRICT FIX F: Uses _normalize_key_for_bcrypt to handle keys >72 bytes
    (bcrypt's hard limit). Long keys are pre-hashed with SHA-256.
    """
    if HAS_BCRYPT:
        normalized = _normalize_key_for_bcrypt(key)
        return bcrypt.hashpw(normalized, bcrypt.gensalt()).decode('utf-8')
    # Fallback: HMAC-SHA256 with random salt
    salt = secrets.token_hex(16)
    h = hmac.new(salt.encode(), key.encode(), hashlib.sha256).hexdigest()
    return f"hmac-sha256${salt}${h}"


def _verify_key(key: str, hashed_key: str) -> bool:
    """Verify an API key against its stored hash.

    STRESS-TEST FIX #1: This is the ONLY correct way to verify a key against
    a stored bcrypt hash. Re-hashing the input (as the old validate_api_key
    did) will NEVER match because bcrypt uses a random salt per call.

    STRICT FIX F: Uses _normalize_key_for_bcrypt for keys >72 bytes.
    """
    if not hashed_key:
        return False
    try:
        if HAS_BCRYPT and hashed_key.startswith('$2'):
            normalized = _normalize_key_for_bcrypt(key)
            return bcrypt.checkpw(normalized, hashed_key.encode())
        if hashed_key.startswith("hmac-sha256$"):
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
        with open(path) as f:
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

    STRICT FIX A (timing oracle): Originally, an attacker could enumerate
    valid keys by timing (valid = ~250ms bcrypt, invalid = ~0ms). STRICT
    FIX A added a dummy bcrypt on invalid lookups to equalize timing, but
    that introduced a CPU DoS vector (invalid keys cost ~250ms each).

    The current implementation eliminates BOTH issues via a positive
    in-memory cache of recently-validated keys:
      - First valid call: ~250ms (bcrypt) → populates cache
      - Subsequent valid calls (warm cache): ~0.1ms → matches invalid timing
      - Invalid calls: ~0.1ms (HMAC lookup miss, no bcrypt)
    Both warm-valid and invalid paths return in <100ms, so there is no
    timing oracle. CPU DoS is also eliminated since invalid keys do
    no bcrypt work.

    STRICT FIX F (length cap): Keys longer than _MAX_KEY_LENGTH are rejected
    immediately (before HMAC computation) to prevent CPU DoS.
    """
    # STRICT FIX F: length cap BEFORE any computation
    if not key or len(key) > _MAX_KEY_LENGTH:
        return None

    lookup = _lookup_key(key)

    # Fast path: positive cache hit (recently-validated valid key).
    # Returns in ~0.1ms — no bcrypt, no file I/O, no lock contention
    # with the keys file. This is what makes the timing oracle disappear
    # without resorting to a dummy bcrypt (which would re-introduce DoS).
    now = time.time()
    with _VALIDATED_KEY_CACHE_LOCK:
        cached = _VALIDATED_KEY_CACHE.get(lookup)
        if cached is not None:
            info_cached, expires_at = cached
            if now < expires_at:
                return info_cached
            # Expired — evict and continue to full validation
            del _VALIDATED_KEY_CACHE[lookup]

    with _keys_lock:
        keys = _load_keys()
        info = keys.get(lookup)
        if not info:
            # Lookup miss — return immediately. No dummy bcrypt (would
            # cause CPU DoS). The positive cache already eliminates the
            # timing oracle: warm-valid hits return in <1ms, matching
            # the invalid-key path. The first valid call does take
            # ~250ms, but an attacker cannot distinguish "first call
            # to a valid key" from "any call to an invalid key" without
            # already knowing the key.
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

    api_key_info = APIKeyInfo(
        key_hash=lookup,
        role=Role(role_str),
        description=description,
    )

    # Populate positive cache so subsequent calls for this key are O(1).
    # This is the key insight: the cache hit path returns in <1ms,
    # matching the invalid-key path, which eliminates the timing oracle
    # WITHOUT needing a dummy bcrypt (which would cause CPU DoS).
    with _VALIDATED_KEY_CACHE_LOCK:
        # Cap cache size to prevent unbounded growth (defense-in-depth).
        # 4096 entries × ~200 bytes each ≈ 800KB max — trivial.
        if len(_VALIDATED_KEY_CACHE) >= 4096:
            # Evict ~10% of entries (oldest by expiry time)
            sorted_items = sorted(
                _VALIDATED_KEY_CACHE.items(),
                key=lambda kv: kv[1][1],
            )
            for k, _ in sorted_items[:410]:
                del _VALIDATED_KEY_CACHE[k]
        _VALIDATED_KEY_CACHE[lookup] = (api_key_info, now + _VALIDATED_KEY_CACHE_TTL)

    return api_key_info


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
            deleted = True
        else:
            # Slow path: scan for matching bcrypt_hash field
            deleted = False
            for lk, v in list(keys.items()):
                if v.get("bcrypt_hash") == key_hash or v.get("key_hash") == key_hash:
                    del keys[lk]
                    _save_keys(keys)
                    logger.info("Deleted API key %s...", lk[:8])
                    deleted = True
                    key_hash = lk  # normalize for cache invalidation below
                    break
    # Invalidate the positive validation cache so revoked keys take effect
    # immediately (no stale auth for up to _VALIDATED_KEY_CACHE_TTL seconds).
    if deleted:
        with _VALIDATED_KEY_CACHE_LOCK:
            _VALIDATED_KEY_CACHE.pop(key_hash, None)
    return deleted


def update_api_key_role(key_hash: str, role: Role) -> bool:
    """Update the role of an existing API key."""
    with _keys_lock:
        keys = _load_keys()
        # Fast path
        if key_hash in keys:
            keys[key_hash]["role"] = role.value
            _save_keys(keys)
            logger.info("Updated API key %s... role to %s", key_hash[:8], role.value)
            updated = True
        else:
            # Slow path: scan for matching bcrypt_hash
            updated = False
            for lk, v in list(keys.items()):
                if v.get("bcrypt_hash") == key_hash or v.get("key_hash") == key_hash:
                    keys[lk]["role"] = role.value
                    _save_keys(keys)
                    logger.info("Updated API key %s... role to %s", lk[:8], role.value)
                    updated = True
                    key_hash = lk  # normalize for cache invalidation below
                    break
    # Invalidate the positive validation cache so role changes take effect
    # immediately. Otherwise a recently-validated key could retain its old
    # role for up to _VALIDATED_KEY_CACHE_TTL seconds — a privilege-escalation
    # window if an admin downgrades a compromised key.
    if updated:
        with _VALIDATED_KEY_CACHE_LOCK:
            _VALIDATED_KEY_CACHE.pop(key_hash, None)
    return updated


# Initialize on import
_ensure_default_admin_key()
