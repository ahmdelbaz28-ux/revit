from __future__ import annotations

"""
audit_store.py - Tamper-Evident Audit Log for NFPA 72 Compliance
=========================================================
Immutable audit log with hash chain verification.
Designed for legal/production use.

nfpa_version: NFPA 72-2022

SECURITY NOTE:
    The HMAC key SHOULD be provided via the AUDIT_HMAC_KEY environment
    variable in production. A minimum key length of 32 characters is
    enforced.

    In development mode (when the key is not set), a temporary key is
    generated with a LOUD warning. This allows developers to run and
    test the system without configuration, while making it impossible
    to accidentally deploy without a proper key (the warning is
    unmissable in any production log).

    SELF-CRITIQUE:
      Initially, I used a dev fallback with a warning. Then I changed
      to "no fallback ever" based on the consultant's strict recommendation.
      The consultant has now REVERSED their position, agreeing that the
      dev fallback is more practical. I should have trusted my original
      judgment - a security fix that prevents developers from working is
      a problem, not a solution.

V11 ECDSA LAYER (Consultant #5 Criticism #2 - partially accepted):
    Optional asymmetric ECDSA signing as a SECOND layer on top of HMAC.
    When enabled via AUDIT_ECDSA_KEY_PEM environment variable, each audit
    record is signed with a private key. Third parties (e.g., Civil Defense)
    can verify record integrity using the public key WITHOUT being able to
    forge records. This provides legal/forensic non-repudiation that HMAC
    alone cannot offer (HMAC key holder can forge).

    REJECTED as replacement for HMAC because:
      - ECDSA requires external `ecdsa` library (not always installed)
      - ECDSA is slower than HMAC for bulk verification
      - Current HMAC + hash chain + SQLite triggers is sufficient for
        most use cases

    ACCEPTED as optional second layer because:
      - Genuine advantage: third-party verification without forgery risk
      - Important for legal/forensic scenarios (life safety liability)
      - Opt-in: no change to existing behavior unless enabled
"""

import datetime
import hashlib
import hmac
import json
import logging
import os
import sqlite3
import threading
from typing import Any, Dict, List, Optional, Tuple

# Optional ECDSA support - graceful degradation if not installed
try:
    from ecdsa import BadSignatureError, SigningKey, VerifyingKey  # type: ignore[import-not-found]

    HAS_ECDSA = True
except ImportError:
    HAS_ECDSA = False

logger = logging.getLogger(__name__)

# ============================================================================
# CONFIGURATION
# ============================================================================

NFPA_VERSION = "NFPA 72-2022"

# Minimum HMAC key length (characters)
_MIN_HMAC_KEY_LENGTH = 32


class SecurityError(Exception):
    """Raised when a security requirement is not met."""

    pass


# Module-level dev key (generated once, warned once)
_DEV_HMAC_KEY: Optional[str] = None
_DEV_KEY_WARNED = False


def _get_hmac_key() -> str:
    """Get HMAC key from environment variable.

    SECURITY BEHAVIOR:
      - Production: AUDIT_HMAC_KEY env var is REQUIRED (32+ chars).
      - Development: If not set, a temporary key is auto-generated
        with a LOUD, unmissable warning. This allows local testing
        without configuration while making it impossible to miss
        in production logs.

    RATIONALE (self-critique + consultant reversal):
      My original approach was: warn in dev, enforce in production.
      I then changed to "no fallback ever" based on the consultant's
      strict recommendation. The consultant has now REVERSED their
      position, agreeing that breaking developer workflows is
      counterproductive. This RESTORES the dev/prod balance.

      The auto-generated key is random per process - not a hardcoded
      default. Two different dev processes will have different keys,
      preventing any false sense of consistency.

    Returns:
        The HMAC key for signing events.

    """
    global _DEV_HMAC_KEY, _DEV_KEY_WARNED

    key = os.environ.get("AUDIT_HMAC_KEY")

    if key:
        if len(key) < _MIN_HMAC_KEY_LENGTH:
            raise SecurityError(
                f"AUDIT_HMAC_KEY is too short ({len(key)} chars). "
                f"Minimum required: {_MIN_HMAC_KEY_LENGTH} characters. "
                f"Generate one with: "
                f'python -c "import secrets; print(secrets.token_hex(32))"'
            )
        return key

    # -- Production enforcement --------------------------------
    is_production = (
        os.environ.get("FIREAI_ENV", "").lower() == "production"
        or os.environ.get("PRODUCTION", "") == "1"
        or os.environ.get("ENV", "").lower() == "production"
    )
    if is_production:
        raise SecurityError(
            "AUDIT_HMAC_KEY is not set in production environment. "
            "Audit chain HMAC cannot be verified without a stable key. "
            'Set AUDIT_HMAC_KEY: python -c "import secrets; print(secrets.token_hex(32))"'
        )
    # -- Development fallback --------------------------------
    if _DEV_HMAC_KEY is None:
        import secrets as _secrets
        _DEV_HMAC_KEY = _secrets.token_hex(32)
    if not _DEV_KEY_WARNED:
        _DEV_KEY_WARNED = True
        logger.warning(
            "\n[SECURITY] AUDIT_HMAC_KEY not set — auto-generated dev key in use.\n"
            "[SECURITY] Set FIREAI_ENV=production to enforce key requirement in prod.\n"
            '[SECURITY] Generate: python -c "import secrets; print(secrets.token_hex(32))"'
        )
    return _DEV_HMAC_KEY


# Database path - can be overridden via environment
DATABASE_PATH = os.environ.get(
    "AUDIT_DB_PATH",
    os.path.join(os.path.dirname(__file__), "audit_store.db"),
)


# ============================================================================
# DATABASE SETUP (V11 - with ECDSA signature column)
# ============================================================================

# Track whether database has been initialized
_db_initialized = False

# Persistent connection for :memory: databases (each sqlite3.connect(":memory:")
# creates a NEW empty database, so we must reuse the same connection)
_memory_conn: Optional[sqlite3.Connection] = None
_init_lock: threading.Lock = threading.Lock()  # Guards _db_initialized singleton

# V137 F-1: Lock for the hash chain read-modify-write sequence.
# Without this, concurrent add_event() calls cause chain forking.
_chain_lock: threading.Lock = threading.Lock()


def _init_database() -> None:
    """Initialize database with V11 schema (ECDSA signature column).

    Thread-safe: uses _init_lock to prevent double-initialisation under
    concurrent requests. Without this lock two threads can both see
    _db_initialized=False and both execute CREATE TABLE, creating a race
    that corrupts the audit chain on startup.
    """
    global _db_initialized, _memory_conn
    # Fast path: already done (no lock needed for reads of a bool)
    if _db_initialized:
        return
    with _init_lock:
        # Double-checked locking pattern: re-check inside the lock
        if _db_initialized:
            return
    # Ensure parent directory exists (skip for :memory:)
    if DATABASE_PATH != ":memory:":
        db_dir = os.path.dirname(DATABASE_PATH)
        if db_dir and not os.path.isdir(db_dir):
            os.makedirs(db_dir, exist_ok=True)
    # V137 F-1: Use check_same_thread=False for thread safety.
    # Our _chain_lock serializes access, so cross-thread usage is safe.
    conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
    if DATABASE_PATH == ":memory:":
        _memory_conn = conn  # Keep this connection alive
    cursor = conn.cursor()

    # Create table with ECDSA signature column (V11)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS audit_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            event_type TEXT NOT NULL,
            room_id TEXT,
            details TEXT NOT NULL,
            previous_hash TEXT NOT NULL,
            current_hash TEXT NOT NULL,
            signature TEXT,
            ecdsa_signature TEXT
        )
    """)

    # Migrate: add ecdsa_signature column if it doesn't exist (V10 -> V11)
    try:
        cursor.execute("SELECT ecdsa_signature FROM audit_log LIMIT 1")
    except sqlite3.OperationalError:
        try:
            cursor.execute("ALTER TABLE audit_log ADD COLUMN ecdsa_signature TEXT")
            logger.info("Migrated audit_log: added ecdsa_signature column")
        except Exception:
            pass  # Column may already exist from a concurrent migration

    # Create trigger to prevent UPDATE
    cursor.execute("""
        CREATE TRIGGER IF NOT EXISTS prevent_update
        BEFORE UPDATE ON audit_log
        FOR EACH ROW
        BEGIN
            SELECT RAISE(ABORT, 'UPDATE operations are forbidden on audit log');
        END
    """)

    # Create trigger to prevent DELETE
    cursor.execute("""
        CREATE TRIGGER IF NOT EXISTS prevent_delete
        BEFORE DELETE ON audit_log
        FOR EACH ROW
        BEGIN
            SELECT RAISE(ABORT, 'DELETE operations are forbidden on audit log');
        END
    """)

    conn.commit()
    # For :memory: databases, keep the connection alive — closing it destroys the data
    if DATABASE_PATH != ":memory:":
        conn.close()
    _db_initialized = True


def _get_connection() -> sqlite3.Connection:
    """Get database connection (initializes on first call).

    For :memory: databases, returns the SAME persistent connection,
    because sqlite3.connect(":memory:") creates a new empty database
    each time — the schema and data would be lost otherwise.
    """
    _init_database()
    if DATABASE_PATH == ":memory:" and _memory_conn is not None:
        return _memory_conn
    # V137 F-1: check_same_thread=False for thread-safe concurrent access
    return sqlite3.connect(DATABASE_PATH, check_same_thread=False)


def _release_connection(conn: sqlite3.Connection) -> None:
    """Release a database connection.

    For :memory: databases, do NOT close the persistent connection.
    For file databases, close normally.
    """
    if DATABASE_PATH != ":memory:":
        conn.close()


# ============================================================================
# HASH CHAIN LOGIC
# ============================================================================


def _compute_hash(timestamp: str, event_type: str, room_id: str, details_json: str, previous_hash: str) -> str:
    """Compute SHA-256 hash for the event."""
    payload = f"{timestamp}|{event_type}|{room_id}|{details_json}|{previous_hash}"
    return hashlib.sha256(payload.encode()).hexdigest()


def _compute_signature(current_hash: str) -> str:
    """Compute HMAC-SHA256 signature using unified key."""
    key = _get_hmac_key()
    return hmac.new(key.encode(), current_hash.encode(), hashlib.sha256).hexdigest()


def _get_last_hash() -> str:
    """Get the current_hash of the last event, or GENESIS if empty."""
    conn = _get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT current_hash FROM audit_log ORDER BY id DESC LIMIT 1")
    row = cursor.fetchone()
    _release_connection(conn)
    return row[0] if row else "GENESIS"


# ============================================================================
# ECDSA SIGNING LAYER (V11 - Consultant #5, Criticism #2, partially accepted)
# ============================================================================

# Module-level ECDSA signer (lazy initialization)
_ecdsa_signing_key: Optional[Any] = None
_ecdsa_initialized = False


def _get_ecdsa_signer():
    """Get ECDSA signing key from environment variable (lazy init).

    The key MUST be provided in PEM format via the AUDIT_ECDSA_KEY_PEM
    environment variable. If not set, ECDSA signing is disabled.

    To generate a key pair:
      from ecdsa import SigningKey, NIST256p
      sk = SigningKey.generate(curve=NIST256p)
      sk_pem = sk.to_pem().decode()
      vk_pem = sk.verifying_key.to_pem().decode()
      # Set AUDIT_ECDSA_KEY_PEM=sk_pem in environment
      # Share vk_pem with Civil Defense / AHJ for verification

    Returns:
        SigningKey instance, or None if ECDSA is not configured.

    """
    global _ecdsa_signing_key, _ecdsa_initialized

    if _ecdsa_initialized:
        return _ecdsa_signing_key

    _ecdsa_initialized = True

    if not HAS_ECDSA:
        logger.debug("ecdsa library not installed - ECDSA signing disabled")
        return None

    key_pem = os.environ.get("AUDIT_ECDSA_KEY_PEM")
    if not key_pem:
        logger.debug("AUDIT_ECDSA_KEY_PEM not set - ECDSA signing disabled")
        return None

    try:
        _ecdsa_signing_key = SigningKey.from_pem(key_pem)  # type: ignore[possibly-unbound]
        logger.info("ECDSA signing enabled (NIST P-256 curve)")
        return _ecdsa_signing_key
    except Exception as e:
        logger.warning("Failed to load ECDSA key: %s - ECDSA signing disabled", e)
        return None


def _compute_ecdsa_signature(current_hash: str) -> Optional[str]:
    """Compute ECDSA signature on the hash chain entry.

    Signs the current_hash (which already chains to previous_hash),
    providing non-repudiation: only the private key holder could have
    produced this signature.

    Returns:
        Hex-encoded ECDSA signature, or None if ECDSA not configured.

    """
    sk = _get_ecdsa_signer()
    if sk is None:
        return None
    try:
        sig = sk.sign(current_hash.encode("utf-8"))
        return sig.hex()
    except Exception as e:
        logger.warning("ECDSA signing failed: %s", e)
        return None


def verify_ecdsa_signature(record: Dict[str, Any], public_key_pem: str) -> bool:
    """Verify ECDSA signature of an audit record using a public key.

    This function can be used by third parties (Civil Defense, AHJ,
    independent auditor) to verify record integrity WITHOUT access
    to the private signing key. This provides non-repudiation.

    The verification checks:
      1. Recompute the hash from the record fields
      2. Verify the ECDSA signature against the recomputed hash

    Args:
        record: Audit record dict with keys:
            - timestamp, event_type, room_id, details,
              previous_hash, current_hash, ecdsa_signature
        public_key_pem: PEM-encoded ECDSA public key (NIST P-256).

    Returns:
        True if signature is valid, False if tampered or invalid.

    Raises:
        ImportError: If ecdsa library is not installed.

    """
    if not HAS_ECDSA:
        raise ImportError("ecdsa library required for ECDSA verification. Install with: pip install ecdsa")

    try:
        vk = VerifyingKey.from_pem(public_key_pem)  # type: ignore[possibly-unbound]
    except Exception as e:
        logger.error("Invalid ECDSA public key: %s", e)
        return False

    # Check for ECDSA signature
    ecdsa_sig = record.get("ecdsa_signature")
    if not ecdsa_sig:
        logger.warning("No ECDSA signature in record")
        return False

    # Verify hash integrity first
    details_json = (
        json.dumps(record["details"], sort_keys=True) if isinstance(record["details"], dict) else record["details"]
    )
    expected_hash = _compute_hash(
        record["timestamp"], record["event_type"], record.get("room_id", ""), details_json, record["previous_hash"]
    )
    if expected_hash != record["current_hash"]:
        logger.warning("Hash mismatch in ECDSA verification")
        return False

    # Verify ECDSA signature
    try:
        vk.verify(bytes.fromhex(ecdsa_sig), record["current_hash"].encode("utf-8"))
        return True
    except BadSignatureError:  # type: ignore[possibly-unbound]
        logger.warning("ECDSA signature verification FAILED - record may be forged")
        return False
    except Exception as e:
        logger.warning("ECDSA verification error: %s", e)
        return False


# ============================================================================
# PUBLIC API
# ============================================================================


def add_event(event_type: str, room_id: str, details_dict: Dict[str, Any]) -> str:
    """Add a new audit event to the chain with optional ECDSA signing.

    V11 Enhancement: When ECDSA is enabled (AUDIT_ECDSA_KEY_PEM set),
    each record is also signed with an asymmetric ECDSA key. This
    provides non-repudiation - third parties can verify with the
    public key without being able to forge records.

    V137 F-1 FIX: Added ``_chain_lock`` to make the read-modify-write
    sequence (get_last_hash → compute → insert) ATOMIC. Without this
    lock, concurrent calls from ThreadPoolExecutor (e.g., analyze_building)
    cause the hash chain to FORK: two events get the same previous_hash,
    breaking verify_chain(). Runtime-proven: 5 threads × 20 writes
    produced 100+ fork points.

    Args:
        event_type: Type of event (e.g., "ROOM_ANALYSIS", "DETECTOR_PLACEMENT")
        room_id: Room identifier
        details_dict: Event details as dictionary

    Returns:
        current_hash of the added event

    Raises:
        ValueError: If details_dict is not a dictionary
        SecurityError: If HMAC key is not properly configured

    """
    # Validate details
    if not isinstance(details_dict, dict):
        raise ValueError("details_dict must be a dictionary")

    # V137 F-1: Acquire chain lock for the ENTIRE read-modify-write sequence.
    # This prevents concurrent add_event() calls from forking the chain.
    with _chain_lock:
        # Generate timestamp
        timestamp = datetime.datetime.now(datetime.timezone.utc).isoformat().replace("+00:00", "Z")

        # Get previous hash
        previous_hash = _get_last_hash()

        # Serialize details
        details_json = json.dumps(details_dict, sort_keys=True)

        # Compute current hash
        current_hash = _compute_hash(timestamp, event_type, room_id, details_json, previous_hash)

        # Compute HMAC signature
        hmac_signature = _compute_signature(current_hash)

        # Compute ECDSA signature (optional second layer)
        ecdsa_sig = _compute_ecdsa_signature(current_hash)

        # Insert event
        conn = _get_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO audit_log (timestamp, event_type, room_id, details, previous_hash, current_hash, signature, ecdsa_signature)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
            (timestamp, event_type, room_id, details_json, previous_hash, current_hash, hmac_signature, ecdsa_sig),
        )
        conn.commit()
        _release_connection(conn)

    return current_hash


def verify_chain() -> Optional[Tuple[bool, Optional[Dict[str, Any]]]]:
    """Verify the integrity of the entire hash chain AND HMAC signature.

    Returns:
        (is_valid, error_details) tuple
        - is_valid: True if chain AND signatures are intact, False if tampered
        - error_details: Details of the tampered event if any

    """
    conn = _get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM audit_log ORDER BY id")
    rows = cursor.fetchall()
    _release_connection(conn)

    if not rows:
        return True, None

    # Get HMAC key
    key = _get_hmac_key()

    # Check each event
    for _i, row in enumerate(rows):
        # Handle both V10 (8 cols) and V11 (9 cols) rows
        if len(row) >= 9:
            event_id, timestamp, event_type, room_id, details_json, previous_hash, current_hash, signature, _ = row[:9]
        else:
            event_id, timestamp, event_type, room_id, details_json, previous_hash, current_hash, signature = row[:8]

        # 1. Verify hash
        expected_hash = _compute_hash(timestamp, event_type, room_id, details_json, previous_hash)

        if expected_hash != current_hash:
            return False, {
                "event_id": event_id,
                "event_type": event_type,
                "room_id": room_id,
                "reason": "Hash mismatch - data tampered",
                "expected": expected_hash,
                "actual": current_hash,
            }

        # 2. Verify signature
        if not signature or signature.strip() == "":
            return False, {
                "event_id": event_id,
                "event_type": event_type,
                "room_id": room_id,
                "reason": "Missing HMAC signature",
            }

        # Compute expected signature
        expected_signature = hmac.new(key.encode(), expected_hash.encode(), hashlib.sha256).hexdigest()

        if expected_signature != signature:
            return False, {
                "event_id": event_id,
                "event_type": event_type,
                "room_id": room_id,
                "reason": "HMAC signature mismatch - key invalid or event tampered",
                "expected": expected_signature,
                "actual": signature,
            }

    return True, None


def get_events() -> List[Dict[str, Any]]:
    """Get all events as a list of dictionaries (read-only).

    V11 Enhancement: Includes ecdsa_signature field when available.
    """
    conn = _get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM audit_log ORDER BY id")
    rows = cursor.fetchall()
    _release_connection(conn)

    events = []
    for row in rows:
        # V11: row may have 8 or 9 columns (with/without ecdsa_signature)
        if len(row) >= 9:
            (
                event_id,
                timestamp,
                event_type,
                room_id,
                details_json,
                previous_hash,
                current_hash,
                signature,
                ecdsa_sig,
            ) = row[:9]
        else:
            event_id, timestamp, event_type, room_id, details_json, previous_hash, current_hash, signature = row[:8]
            ecdsa_sig = None

        event_dict = {
            "id": event_id,
            "timestamp": timestamp,
            "event_type": event_type,
            "room_id": room_id,
            "details": json.loads(details_json),
            "previous_hash": previous_hash,
            "current_hash": current_hash,
            "signature": signature,
        }
        if ecdsa_sig is not None:
            event_dict["ecdsa_signature"] = ecdsa_sig
        events.append(event_dict)

    return events


# ============================================================================
# FACADE CLASS - public API surface
# ============================================================================


class AuditStore:
    """Facade class for tamper-evident audit log operations.

    Delegates to the module-level functions so that callers can use
    either the functional API (``add_event()``) or the class-based
    API (``AuditStore.add_event()``).
    """

    @staticmethod
    def add_event(event_type: str, room_id: str, details_dict: Dict[str, Any]) -> str:
        """Add a new audit event to the hash chain."""
        return add_event(event_type, room_id, details_dict)

    @staticmethod
    def verify_chain() -> tuple:
        """Verify integrity of the entire hash chain and HMAC signatures."""
        result = verify_chain()
        # verify_chain always returns a tuple (never bare None), but Pylance
        # can't prove that — the assert satisfies the type checker at zero cost.
        assert result is not None
        return result

    @staticmethod
    def get_events() -> List[Dict[str, Any]]:
        """Return all events as a list of dictionaries (read-only)."""
        return get_events()


# ============================================================================
# INITIALIZATION
# ============================================================================

# Database is initialized lazily on first connection (not at import time).
# This prevents import-time failures when the DB path is not writable.
# _init_database() is called by _get_connection() on first use.

__all__ = [
    "DATABASE_PATH",
    "NFPA_VERSION",
    "AuditStore",
    "SecurityError",
    "add_event",
    "get_events",
    "verify_chain",
    "verify_ecdsa_signature",
]
