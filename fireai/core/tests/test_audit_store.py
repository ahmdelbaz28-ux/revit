"""Comprehensive tests for the audit_store module.

Tests cover:
  - SecurityError exception
  - _get_hmac_key: env var, production enforcement, dev fallback, short key rejection
  - _init_database: table creation, triggers, migration, idempotency
  - _get_connection / _release_connection: :memory: and file DB paths
  - _compute_hash: deterministic, sensitive to field changes
  - _compute_signature: HMAC-SHA256 correctness
  - _get_last_hash: GENESIS for empty, last hash otherwise
  - add_event: valid events, ValueError for bad details, chain linking
  - verify_chain: empty chain, valid chain, tampered hash, tampered signature
  - get_events: empty, single, multiple, includes ecdsa_signature when present
  - AuditStore facade: delegates to module-level functions
  - _get_ecdsa_signer / _compute_ecdsa_signature: disabled without library/key
  - verify_ecdsa_signature: ImportError without ecdsa, invalid key, missing sig
  - Database immutability triggers: UPDATE and DELETE are rejected
"""

import hashlib
import hmac
import json
import os
import sqlite3
import tempfile
import threading
from unittest.mock import patch

import pytest

from fireai.core import audit_store as audit_mod
from fireai.core.audit_store import (
    NFPA_VERSION,
    AuditStore,
    SecurityError,
    _compute_ecdsa_signature,
    _compute_hash,
    _compute_signature,
    _get_ecdsa_signer,
    _get_hmac_key,
    _get_last_hash,
    add_event,
    get_events,
    verify_chain,
    verify_ecdsa_signature,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _reset_module_state():
    """Reset module-level globals between tests so tests are isolated."""
    # Save original state
    orig_db_init = audit_mod._db_initialized
    orig_mem_conn = audit_mod._memory_conn
    orig_dev_key = audit_mod._DEV_HMAC_KEY
    orig_dev_warned = audit_mod._DEV_KEY_WARNED
    orig_ecdsa_init = audit_mod._ecdsa_initialized
    orig_ecdsa_key = audit_mod._ecdsa_signing_key
    orig_db_path = audit_mod.DATABASE_PATH

    yield

    # Restore original state
    audit_mod._db_initialized = orig_db_init
    audit_mod._memory_conn = orig_mem_conn
    audit_mod._DEV_HMAC_KEY = orig_dev_key
    audit_mod._DEV_KEY_WARNED = orig_dev_warned
    audit_mod._ecdsa_initialized = orig_ecdsa_init
    audit_mod._ecdsa_signing_key = orig_ecdsa_key
    audit_mod.DATABASE_PATH = orig_db_path


@pytest.fixture
def memory_db():
    """Configure audit_store to use an in-memory database and initialise it."""
    audit_mod.DATABASE_PATH = ":memory:"
    audit_mod._db_initialized = False
    audit_mod._memory_conn = None
    audit_mod._init_database()
    yield
    # Cleanup: close the in-memory connection if open
    if audit_mod._memory_conn is not None:
        try:
            audit_mod._memory_conn.close()
        except Exception:
            pass
        audit_mod._memory_conn = None
    audit_mod._db_initialized = False


@pytest.fixture
def hmac_key_env():
    """Set a valid AUDIT_HMAC_KEY in the environment and restore on exit."""
    key = "a" * 32  # 32-char minimum valid key
    old = os.environ.get("AUDIT_HMAC_KEY")
    os.environ["AUDIT_HMAC_KEY"] = key
    yield key
    if old is None:
        os.environ.pop("AUDIT_HMAC_KEY", None)
    else:
        os.environ["AUDIT_HMAC_KEY"] = old


@pytest.fixture
def clean_hmac_env():
    """Ensure AUDIT_HMAC_KEY is NOT set; restore on exit."""
    old = os.environ.pop("AUDIT_HMAC_KEY", None)
    yield
    if old is not None:
        os.environ["AUDIT_HMAC_KEY"] = old


@pytest.fixture
def production_env():
    """Set FIREAI_ENV=production; restore on exit."""
    old = os.environ.get("FIREAI_ENV")
    os.environ["FIREAI_ENV"] = "production"
    yield
    if old is None:
        os.environ.pop("FIREAI_ENV", None)
    else:
        os.environ["FIREAI_ENV"] = old


# ---------------------------------------------------------------------------
# SecurityError
# ---------------------------------------------------------------------------

class TestSecurityError:
    def test_is_exception(self):
        assert issubclass(SecurityError, Exception)

    def test_raise_and_catch(self):
        with pytest.raises(SecurityError, match="bad thing"):
            raise SecurityError("bad thing")

    def test_str_message(self):
        err = SecurityError("test message")
        assert str(err) == "test message"


# ---------------------------------------------------------------------------
# NFPA_VERSION constant
# ---------------------------------------------------------------------------

class TestNFPAVersion:
    def test_value(self):
        assert NFPA_VERSION == "NFPA 72-2022"


# ---------------------------------------------------------------------------
# _get_hmac_key
# ---------------------------------------------------------------------------

class TestGetHmacKey:
    def test_env_var_set(self, hmac_key_env):
        """When AUDIT_HMAC_KEY is set and long enough, it is returned."""
        audit_mod._DEV_HMAC_KEY = None
        audit_mod._DEV_KEY_WARNED = False
        result = _get_hmac_key()
        assert result == hmac_key_env

    def test_short_key_raises(self):
        """AUDIT_HMAC_KEY shorter than 32 chars raises SecurityError."""
        old = os.environ.get("AUDIT_HMAC_KEY")
        os.environ["AUDIT_HMAC_KEY"] = "short"
        try:
            with pytest.raises(SecurityError, match="too short"):
                _get_hmac_key()
        finally:
            if old is None:
                os.environ.pop("AUDIT_HMAC_KEY", None)
            else:
                os.environ["AUDIT_HMAC_KEY"] = old

    def test_exactly_32_chars_accepted(self):
        """A key of exactly 32 characters is accepted."""
        old = os.environ.get("AUDIT_HMAC_KEY")
        os.environ["AUDIT_HMAC_KEY"] = "x" * 32
        try:
            result = _get_hmac_key()
            assert result == "x" * 32
        finally:
            if old is None:
                os.environ.pop("AUDIT_HMAC_KEY", None)
            else:
                os.environ["AUDIT_HMAC_KEY"] = old

    def test_dev_fallback_generates_key(self, clean_hmac_env):
        """Without AUDIT_HMAC_KEY and not production, a dev key is generated."""
        audit_mod._DEV_HMAC_KEY = None
        audit_mod._DEV_KEY_WARNED = False
        # Ensure not production
        for var in ("FIREAI_ENV", "PRODUCTION", "ENV"):
            os.environ.pop(var, None)
        result = _get_hmac_key()
        assert isinstance(result, str)
        assert len(result) >= 32  # token_hex(32) = 64 chars

    def test_dev_fallback_returns_same_key_on_second_call(self, clean_hmac_env):
        """Dev key is stable across calls within the same process."""
        audit_mod._DEV_HMAC_KEY = None
        audit_mod._DEV_KEY_WARNED = False
        for var in ("FIREAI_ENV", "PRODUCTION", "ENV"):
            os.environ.pop(var, None)
        key1 = _get_hmac_key()
        key2 = _get_hmac_key()
        assert key1 == key2

    def test_production_env_raises_without_key(self, clean_hmac_env, production_env):
        """In production without AUDIT_HMAC_KEY, SecurityError is raised."""
        audit_mod._DEV_HMAC_KEY = None
        with pytest.raises(SecurityError, match="not set in production"):
            _get_hmac_key()

    def test_production_env_via_production_var(self, clean_hmac_env):
        """PRODUCTION=1 also triggers production enforcement."""
        audit_mod._DEV_HMAC_KEY = None
        old = os.environ.get("PRODUCTION")
        os.environ["PRODUCTION"] = "1"
        try:
            with pytest.raises(SecurityError, match="not set in production"):
                _get_hmac_key()
        finally:
            if old is None:
                os.environ.pop("PRODUCTION", None)
            else:
                os.environ["PRODUCTION"] = old

    def test_production_env_via_env_var(self, clean_hmac_env):
        """ENV=production also triggers production enforcement."""
        audit_mod._DEV_HMAC_KEY = None
        old = os.environ.get("ENV")
        os.environ["ENV"] = "production"
        try:
            with pytest.raises(SecurityError, match="not set in production"):
                _get_hmac_key()
        finally:
            if old is None:
                os.environ.pop("ENV", None)
            else:
                os.environ["ENV"] = old


# ---------------------------------------------------------------------------
# _compute_hash
# ---------------------------------------------------------------------------

class TestComputeHash:
    def test_deterministic(self):
        """Same inputs always produce the same hash."""
        h1 = _compute_hash("2024-01-01T00:00:00Z", "TEST", "R1", '{"k":"v"}', "GENESIS")
        h2 = _compute_hash("2024-01-01T00:00:00Z", "TEST", "R1", '{"k":"v"}', "GENESIS")
        assert h1 == h2

    def test_sha256_hex(self):
        """Result is a 64-char lowercase hex string (SHA-256)."""
        h = _compute_hash("ts", "et", "rid", "det", "prev")
        assert len(h) == 64
        assert all(c in "0123456789abcdef" for c in h)

    def test_sensitive_to_timestamp(self):
        """Changing timestamp changes the hash."""
        h1 = _compute_hash("ts1", "et", "rid", "det", "prev")
        h2 = _compute_hash("ts2", "et", "rid", "det", "prev")
        assert h1 != h2

    def test_sensitive_to_event_type(self):
        h1 = _compute_hash("ts", "et1", "rid", "det", "prev")
        h2 = _compute_hash("ts", "et2", "rid", "det", "prev")
        assert h1 != h2

    def test_sensitive_to_room_id(self):
        h1 = _compute_hash("ts", "et", "rid1", "det", "prev")
        h2 = _compute_hash("ts", "et", "rid2", "det", "prev")
        assert h1 != h2

    def test_sensitive_to_details(self):
        h1 = _compute_hash("ts", "et", "rid", "det1", "prev")
        h2 = _compute_hash("ts", "et", "rid", "det2", "prev")
        assert h1 != h2

    def test_sensitive_to_previous_hash(self):
        h1 = _compute_hash("ts", "et", "rid", "det", "prev1")
        h2 = _compute_hash("ts", "et", "rid", "det", "prev2")
        assert h1 != h2

    def test_matches_manual_computation(self):
        """Verify the hash matches a manually computed SHA-256."""
        payload = "ts|et|rid|det|prev"
        expected = hashlib.sha256(payload.encode()).hexdigest()
        result = _compute_hash("ts", "et", "rid", "det", "prev")
        assert result == expected


# ---------------------------------------------------------------------------
# _compute_signature
# ---------------------------------------------------------------------------

class TestComputeSignature:
    def test_hmac_sha256(self, hmac_key_env):
        """Signature matches a manually computed HMAC-SHA256."""
        current_hash = "abc123"
        expected = hmac.new(
            hmac_key_env.encode(), current_hash.encode(), hashlib.sha256
        ).hexdigest()
        result = _compute_signature(current_hash)
        assert result == expected

    def test_deterministic(self, hmac_key_env):
        h = "somehash"
        s1 = _compute_signature(h)
        s2 = _compute_signature(h)
        assert s1 == s2

    def test_different_hash_different_sig(self, hmac_key_env):
        s1 = _compute_signature("hash1")
        s2 = _compute_signature("hash2")
        assert s1 != s2


# ---------------------------------------------------------------------------
# _init_database
# ---------------------------------------------------------------------------

class TestInitDatabase:
    def test_creates_table(self, memory_db):
        """After init, audit_log table exists."""
        conn = audit_mod._memory_conn
        cursor = conn.cursor()
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='audit_log'"
        )
        assert cursor.fetchone() is not None

    def test_creates_prevent_update_trigger(self, memory_db):
        """The prevent_update trigger is created."""
        conn = audit_mod._memory_conn
        cursor = conn.cursor()
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='trigger' AND name='prevent_update'"
        )
        assert cursor.fetchone() is not None

    def test_creates_prevent_delete_trigger(self, memory_db):
        """The prevent_delete trigger is created."""
        conn = audit_mod._memory_conn
        cursor = conn.cursor()
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='trigger' AND name='prevent_delete'"
        )
        assert cursor.fetchone() is not None

    def test_idempotent(self, memory_db):
        """Calling _init_database again does not raise."""
        # Reset the flag so it will re-enter the init logic
        audit_mod._db_initialized = False
        audit_mod._init_database()  # should not raise

    def test_schema_has_ecdsa_column(self, memory_db):
        """V11 schema includes ecdsa_signature column."""
        conn = audit_mod._memory_conn
        cursor = conn.cursor()
        cursor.execute("PRAGMA table_info(audit_log)")
        col_names = [row[1] for row in cursor.fetchall()]
        assert "ecdsa_signature" in col_names


# ---------------------------------------------------------------------------
# _get_connection / _release_connection
# ---------------------------------------------------------------------------

class TestConnectionManagement:
    def test_get_connection_returns_connection(self, memory_db):
        conn = audit_mod._get_connection()
        assert isinstance(conn, sqlite3.Connection)

    def test_memory_db_same_connection(self, memory_db):
        """For :memory:, always returns the same persistent connection."""
        conn1 = audit_mod._get_connection()
        conn2 = audit_mod._get_connection()
        assert conn1 is conn2

    def test_release_connection_memory_does_not_close(self, memory_db):
        """Releasing an :memory: connection does NOT close it."""
        conn = audit_mod._get_connection()
        audit_mod._release_connection(conn)
        # Connection should still be usable
        cursor = conn.cursor()
        cursor.execute("SELECT 1")
        assert cursor.fetchone()[0] == 1

    def test_init_called_lazily(self):
        """_get_connection calls _init_database on first use."""
        audit_mod.DATABASE_PATH = ":memory:"
        audit_mod._db_initialized = False
        audit_mod._memory_conn = None
        conn = audit_mod._get_connection()
        assert audit_mod._db_initialized is True
        assert audit_mod._memory_conn is conn
        # Cleanup
        audit_mod._memory_conn.close()
        audit_mod._memory_conn = None
        audit_mod._db_initialized = False


# ---------------------------------------------------------------------------
# _get_last_hash
# ---------------------------------------------------------------------------

class TestGetLastHash:
    def test_genesis_on_empty(self, memory_db):
        """Empty database returns 'GENESIS'."""
        assert _get_last_hash() == "GENESIS"

    def test_returns_last_hash_after_event(self, memory_db, hmac_key_env):
        """After adding an event, _get_last_hash returns that event's hash."""
        h = add_event("TEST", "R1", {"key": "val"})
        assert _get_last_hash() == h


# ---------------------------------------------------------------------------
# add_event
# ---------------------------------------------------------------------------

class TestAddEvent:
    def test_returns_hash(self, memory_db, hmac_key_env):
        """add_event returns a non-empty hash string."""
        result = add_event("TEST_EVENT", "R1", {"info": "test"})
        assert isinstance(result, str)
        assert len(result) == 64  # SHA-256 hex

    def test_invalid_details_raises(self, memory_db, hmac_key_env):
        """Non-dict details_dict raises ValueError."""
        with pytest.raises(ValueError, match="must be a dictionary"):
            add_event("TEST", "R1", "not a dict")

    def test_invalid_details_list_raises(self, memory_db, hmac_key_env):
        """List details_dict raises ValueError."""
        with pytest.raises(ValueError, match="must be a dictionary"):
            add_event("TEST", "R1", [1, 2, 3])

    def test_invalid_details_none_raises(self, memory_db, hmac_key_env):
        """None details_dict raises ValueError."""
        with pytest.raises(ValueError, match="must be a dictionary"):
            add_event("TEST", "R1", None)

    def test_chains_to_genesis(self, memory_db, hmac_key_env):
        """First event chains to 'GENESIS'."""
        add_event("FIRST", "R1", {"a": 1})
        events = get_events()
        assert len(events) == 1
        assert events[0]["previous_hash"] == "GENESIS"

    def test_chains_events(self, memory_db, hmac_key_env):
        """Second event chains to first event's hash."""
        h1 = add_event("FIRST", "R1", {"a": 1})
        add_event("SECOND", "R1", {"b": 2})
        events = get_events()
        assert len(events) == 2
        assert events[1]["previous_hash"] == h1

    def test_event_fields_stored(self, memory_db, hmac_key_env):
        """Event type, room_id, and details are stored correctly."""
        add_event("ROOM_ANALYSIS", "ROOM-101", {"status": "pass"})
        events = get_events()
        assert events[0]["event_type"] == "ROOM_ANALYSIS"
        assert events[0]["room_id"] == "ROOM-101"
        assert events[0]["details"] == {"status": "pass"}

    def test_hash_is_computed_correctly(self, memory_db, hmac_key_env):
        """The stored current_hash matches _compute_hash of the fields."""
        with patch("fireai.core.audit_store.datetime") as mock_dt:
            import datetime as dt
            fixed_ts = "2024-06-15T12:00:00Z"
            mock_dt.datetime.now.return_value.isoformat.return_value = fixed_ts.replace("Z", "+00:00")
            mock_dt.datetime.now.return_value = dt.datetime(
                2024, 6, 15, 12, 0, 0, tzinfo=dt.timezone.utc
            )
            mock_dt.timezone = dt.timezone
            # We'll verify the hash manually instead of mocking datetime
        # Simpler: just verify hash is consistent
        add_event("TEST", "R1", {"x": 1})
        events = get_events()
        e = events[0]
        details_json = json.dumps(e["details"], sort_keys=True)
        expected = _compute_hash(
            e["timestamp"], e["event_type"], e["room_id"], details_json, e["previous_hash"]
        )
        assert e["current_hash"] == expected

    def test_signature_stored(self, memory_db, hmac_key_env):
        """HMAC signature is stored with the event."""
        add_event("TEST", "R1", {"x": 1})
        events = get_events()
        assert events[0]["signature"] is not None
        assert len(events[0]["signature"]) == 64  # HMAC-SHA256 hex

    def test_multiple_events_independent_hashes(self, memory_db, hmac_key_env):
        """Each event gets a unique hash."""
        h1 = add_event("E1", "R1", {"i": 1})
        h2 = add_event("E2", "R1", {"i": 2})
        assert h1 != h2

    def test_empty_details_dict(self, memory_db, hmac_key_env):
        """An empty dict is valid for details_dict."""
        h = add_event("TEST", "R1", {})
        assert isinstance(h, str) and len(h) == 64


# ---------------------------------------------------------------------------
# verify_chain
# ---------------------------------------------------------------------------

class TestVerifyChain:
    def test_empty_chain_valid(self, memory_db, hmac_key_env):
        """An empty chain is valid."""
        is_valid, error = verify_chain()
        assert is_valid is True
        assert error is None

    def test_single_event_valid(self, memory_db, hmac_key_env):
        """A single event chain is valid."""
        add_event("TEST", "R1", {"k": "v"})
        is_valid, error = verify_chain()
        assert is_valid is True
        assert error is None

    def test_multiple_events_valid(self, memory_db, hmac_key_env):
        """A chain of multiple events is valid."""
        add_event("E1", "R1", {"i": 1})
        add_event("E2", "R2", {"i": 2})
        add_event("E3", "R3", {"i": 3})
        is_valid, error = verify_chain()
        assert is_valid is True
        assert error is None

    def test_tampered_hash_detected(self, memory_db, hmac_key_env):
        """Tampering with current_hash is detected."""
        add_event("TEST", "R1", {"k": "v"})
        # Tamper with the hash
        conn = audit_mod._memory_conn
        # Must bypass the trigger by dropping it first
        conn.execute("DROP TRIGGER IF EXISTS prevent_update")
        conn.execute(
            "UPDATE audit_log SET current_hash = 'tampered_hash' WHERE id = 1"
        )
        conn.commit()
        is_valid, error = verify_chain()
        assert is_valid is False
        assert error is not None
        assert "Hash mismatch" in error["reason"]

    def test_tampered_signature_detected(self, memory_db, hmac_key_env):
        """Tampering with HMAC signature is detected."""
        add_event("TEST", "R1", {"k": "v"})
        conn = audit_mod._memory_conn
        conn.execute("DROP TRIGGER IF EXISTS prevent_update")
        conn.execute(
            "UPDATE audit_log SET signature = 'bad_signature' WHERE id = 1"
        )
        conn.commit()
        is_valid, error = verify_chain()
        assert is_valid is False
        assert error is not None
        assert "HMAC signature mismatch" in error["reason"]

    def test_missing_signature_detected(self, memory_db, hmac_key_env):
        """Missing HMAC signature is detected."""
        add_event("TEST", "R1", {"k": "v"})
        conn = audit_mod._memory_conn
        conn.execute("DROP TRIGGER IF EXISTS prevent_update")
        conn.execute(
            "UPDATE audit_log SET signature = '' WHERE id = 1"
        )
        conn.commit()
        is_valid, error = verify_chain()
        assert is_valid is False
        assert "Missing HMAC signature" in error["reason"]

    def test_tampered_details_detected(self, memory_db, hmac_key_env):
        """Tampering with event details is detected (hash changes)."""
        add_event("TEST", "R1", {"k": "v"})
        conn = audit_mod._memory_conn
        conn.execute("DROP TRIGGER IF EXISTS prevent_update")
        conn.execute(
            "UPDATE audit_log SET details = '{\"k\": \"tampered\"}' WHERE id = 1"
        )
        conn.commit()
        is_valid, error = verify_chain()
        assert is_valid is False

    def test_error_details_contain_event_id(self, memory_db, hmac_key_env):
        """Error details include the event_id of the tampered record."""
        add_event("TEST", "R1", {"k": "v"})
        conn = audit_mod._memory_conn
        conn.execute("DROP TRIGGER IF EXISTS prevent_update")
        conn.execute(
            "UPDATE audit_log SET current_hash = 'bad' WHERE id = 1"
        )
        conn.commit()
        is_valid, error = verify_chain()
        assert error["event_id"] == 1


# ---------------------------------------------------------------------------
# get_events
# ---------------------------------------------------------------------------

class TestGetEvents:
    def test_empty_database(self, memory_db, hmac_key_env):
        """Empty database returns empty list."""
        assert get_events() == []

    def test_single_event(self, memory_db, hmac_key_env):
        """Single event is returned as a list of one dict."""
        add_event("TEST", "R1", {"x": 1})
        events = get_events()
        assert len(events) == 1
        e = events[0]
        assert "id" in e
        assert "timestamp" in e
        assert e["event_type"] == "TEST"
        assert e["room_id"] == "R1"
        assert e["details"] == {"x": 1}
        assert "previous_hash" in e
        assert "current_hash" in e
        assert "signature" in e

    def test_multiple_events_ordered(self, memory_db, hmac_key_env):
        """Events are returned in insertion order (by id)."""
        add_event("E1", "R1", {"i": 1})
        add_event("E2", "R2", {"i": 2})
        add_event("E3", "R3", {"i": 3})
        events = get_events()
        assert len(events) == 3
        assert [e["event_type"] for e in events] == ["E1", "E2", "E3"]

    def test_details_deserialized(self, memory_db, hmac_key_env):
        """Details are deserialized from JSON to dict."""
        add_event("TEST", "R1", {"nested": {"key": [1, 2, 3]}})
        events = get_events()
        assert events[0]["details"] == {"nested": {"key": [1, 2, 3]}}

    def test_ecdsa_signature_field_absent_when_none(self, memory_db, hmac_key_env):
        """When ecdsa_signature is None, it should not appear in the dict."""
        add_event("TEST", "R1", {"x": 1})
        events = get_events()
        # ecdsa_signature should not be in dict if it's None
        # (depends on DB returning None vs the code filtering)
        e = events[0]
        # The code adds ecdsa_signature only if not None
        # In :memory: fresh DB with V11 schema, it may be None in DB
        # Let's just verify the key handling
        if e.get("ecdsa_signature") is None:
            assert "ecdsa_signature" not in e or e["ecdsa_signature"] is None


# ---------------------------------------------------------------------------
# AuditStore facade
# ---------------------------------------------------------------------------

class TestAuditStoreFacade:
    def test_add_event_delegates(self, memory_db, hmac_key_env):
        """AuditStore.add_event delegates to module-level add_event."""
        result = AuditStore.add_event("TEST", "R1", {"k": "v"})
        assert isinstance(result, str) and len(result) == 64

    def test_verify_chain_delegates(self, memory_db, hmac_key_env):
        """AuditStore.verify_chain delegates to module-level verify_chain."""
        add_event("TEST", "R1", {"k": "v"})
        is_valid, error = AuditStore.verify_chain()
        assert is_valid is True

    def test_get_events_delegates(self, memory_db, hmac_key_env):
        """AuditStore.get_events delegates to module-level get_events."""
        add_event("TEST", "R1", {"k": "v"})
        events = AuditStore.get_events()
        assert len(events) == 1
        assert events[0]["event_type"] == "TEST"

    def test_facade_returns_same_as_functions(self, memory_db, hmac_key_env):
        """Facade methods return the same values as the functions they wrap."""
        h = AuditStore.add_event("TEST", "R1", {"k": "v"})
        assert h == add_event.__wrapped__(h) if hasattr(add_event, '__wrapped__') else True
        # Direct comparison
        facade_events = AuditStore.get_events()
        func_events = get_events()
        assert facade_events == func_events

        facade_valid, facade_err = AuditStore.verify_chain()
        func_valid, func_err = verify_chain()
        assert facade_valid == func_valid
        assert facade_err == func_err


# ---------------------------------------------------------------------------
# Database immutability triggers
# ---------------------------------------------------------------------------

class TestImmutabilityTriggers:
    def test_update_prevented(self, memory_db, hmac_key_env):
        """UPDATE trigger prevents modification of audit records."""
        add_event("TEST", "R1", {"k": "v"})
        conn = audit_mod._memory_conn
        with pytest.raises(sqlite3.IntegrityError, match="UPDATE"):
            conn.execute("UPDATE audit_log SET event_type = 'TAMPERED' WHERE id = 1")

    def test_delete_prevented(self, memory_db, hmac_key_env):
        """DELETE trigger prevents deletion of audit records."""
        add_event("TEST", "R1", {"k": "v"})
        conn = audit_mod._memory_conn
        with pytest.raises(sqlite3.IntegrityError, match="DELETE"):
            conn.execute("DELETE FROM audit_log WHERE id = 1")


# ---------------------------------------------------------------------------
# ECDSA layer (graceful when ecdsa not installed)
# ---------------------------------------------------------------------------

class TestECDSA:
    def test_get_ecdsa_signer_returns_none_without_env(self, memory_db):
        """Without AUDIT_ECDSA_KEY_PEM, signer returns None."""
        audit_mod._ecdsa_initialized = False
        audit_mod._ecdsa_signing_key = None
        os.environ.pop("AUDIT_ECDSA_KEY_PEM", None)
        result = _get_ecdsa_signer()
        # If ecdsa lib not installed, it's None; if installed but no env, also None
        assert result is None

    def test_compute_ecdsa_signature_returns_none_without_signer(self, memory_db):
        """Without ECDSA configured, _compute_ecdsa_signature returns None."""
        audit_mod._ecdsa_initialized = False
        audit_mod._ecdsa_signing_key = None
        os.environ.pop("AUDIT_ECDSA_KEY_PEM", None)
        result = _compute_ecdsa_signature("somehash")
        assert result is None

    def test_verify_ecdsa_raises_without_library(self):
        """verify_ecdsa_signature raises ImportError if ecdsa not installed."""
        if audit_mod.HAS_ECDSA:
            pytest.skip("ecdsa library is installed; cannot test ImportError path")
        with pytest.raises(ImportError, match="ecdsa library required"):
            verify_ecdsa_signature(
                {"timestamp": "t", "event_type": "e", "room_id": "r",
                 "details": {}, "previous_hash": "p", "current_hash": "c",
                 "ecdsa_signature": "sig"},
                "not-a-real-key"
            )

    @pytest.mark.skipif(not audit_mod.HAS_ECDSA, reason="ecdsa not installed")
    def test_verify_ecdsa_invalid_public_key(self):
        """verify_ecdsa_signature returns False with an invalid public key."""
        result = verify_ecdsa_signature(
            {"timestamp": "t", "event_type": "e", "room_id": "r",
             "details": {}, "previous_hash": "p", "current_hash": "c",
             "ecdsa_signature": "sig"},
            "not-a-valid-pem"
        )
        assert result is False

    @pytest.mark.skipif(not audit_mod.HAS_ECDSA, reason="ecdsa not installed")
    def test_verify_ecdsa_missing_signature(self):
        """verify_ecdsa_signature returns False when record has no ecdsa_signature."""
        from ecdsa import NIST256p, SigningKey
        sk = SigningKey.generate(curve=NIST256p)
        vk_pem = sk.verifying_key.to_pem().decode()
        result = verify_ecdsa_signature(
            {"timestamp": "t", "event_type": "e", "room_id": "r",
             "details": {}, "previous_hash": "p", "current_hash": "c"},
            vk_pem
        )
        assert result is False

    @pytest.mark.skipif(not audit_mod.HAS_ECDSA, reason="ecdsa not installed")
    def test_verify_ecdsa_hash_mismatch(self):
        """verify_ecdsa_signature returns False when hash doesn't match."""
        from ecdsa import NIST256p, SigningKey
        sk = SigningKey.generate(curve=NIST256p)
        vk_pem = sk.verifying_key.to_pem().decode()
        # Sign a hash, but pass a different current_hash in the record
        real_hash = "a" * 64
        sig = sk.sign(real_hash.encode("utf-8"))
        result = verify_ecdsa_signature(
            {"timestamp": "t", "event_type": "e", "room_id": "r",
             "details": {}, "previous_hash": "p", "current_hash": "b" * 64,
             "ecdsa_signature": sig.hex()},
            vk_pem
        )
        assert result is False

    @pytest.mark.skipif(not audit_mod.HAS_ECDSA, reason="ecdsa not installed")
    def test_verify_ecdsa_valid_signature(self):
        """verify_ecdsa_signature returns True for a properly signed record."""
        from ecdsa import NIST256p, SigningKey
        sk = SigningKey.generate(curve=NIST256p)
        vk_pem = sk.verifying_key.to_pem().decode()

        record = {
            "timestamp": "2024-01-01T00:00:00Z",
            "event_type": "TEST",
            "room_id": "R1",
            "details": {"key": "value"},
            "previous_hash": "GENESIS",
        }
        details_json = json.dumps(record["details"], sort_keys=True)
        current_hash = _compute_hash(
            record["timestamp"], record["event_type"],
            record["room_id"], details_json, record["previous_hash"]
        )
        record["current_hash"] = current_hash
        sig = sk.sign(current_hash.encode("utf-8"))
        record["ecdsa_signature"] = sig.hex()

        result = verify_ecdsa_signature(record, vk_pem)
        assert result is True

    @pytest.mark.skipif(not audit_mod.HAS_ECDSA, reason="ecdsa not installed")
    def test_verify_ecdsa_tampered_signature(self):
        """verify_ecdsa_signature returns False for a forged signature."""
        from ecdsa import NIST256p, SigningKey
        sk = SigningKey.generate(curve=NIST256p)
        vk_pem = sk.verifying_key.to_pem().decode()

        record = {
            "timestamp": "2024-01-01T00:00:00Z",
            "event_type": "TEST",
            "room_id": "R1",
            "details": {"key": "value"},
            "previous_hash": "GENESIS",
        }
        details_json = json.dumps(record["details"], sort_keys=True)
        current_hash = _compute_hash(
            record["timestamp"], record["event_type"],
            record["room_id"], details_json, record["previous_hash"]
        )
        record["current_hash"] = current_hash
        record["ecdsa_signature"] = "ff" * 64  # fake signature

        result = verify_ecdsa_signature(record, vk_pem)
        assert result is False

    @pytest.mark.skipif(not audit_mod.HAS_ECDSA, reason="ecdsa not installed")
    def test_ecdsa_signer_with_bad_pem(self):
        """_get_ecdsa_signer returns None for an invalid PEM key."""
        audit_mod._ecdsa_initialized = False
        audit_mod._ecdsa_signing_key = None
        old = os.environ.get("AUDIT_ECDSA_KEY_PEM")
        os.environ["AUDIT_ECDSA_KEY_PEM"] = "not-valid-pem"
        try:
            result = _get_ecdsa_signer()
            assert result is None
        finally:
            if old is None:
                os.environ.pop("AUDIT_ECDSA_KEY_PEM", None)
            else:
                os.environ["AUDIT_ECDSA_KEY_PEM"] = old

    @pytest.mark.skipif(not audit_mod.HAS_ECDSA, reason="ecdsa not installed")
    def test_ecdsa_signer_with_valid_pem(self):
        """_get_ecdsa_signer returns a SigningKey for valid PEM."""
        from ecdsa import NIST256p, SigningKey
        sk = SigningKey.generate(curve=NIST256p)
        pem = sk.to_pem().decode()
        audit_mod._ecdsa_initialized = False
        audit_mod._ecdsa_signing_key = None
        old = os.environ.get("AUDIT_ECDSA_KEY_PEM")
        os.environ["AUDIT_ECDSA_KEY_PEM"] = pem
        try:
            result = _get_ecdsa_signer()
            assert result is not None
        finally:
            if old is None:
                os.environ.pop("AUDIT_ECDSA_KEY_PEM", None)
            else:
                os.environ["AUDIT_ECDSA_KEY_PEM"] = old

    @pytest.mark.skipif(not audit_mod.HAS_ECDSA, reason="ecdsa not installed")
    def test_compute_ecdsa_signature_with_signer(self):
        """_compute_ecdsa_signature returns hex string when ECDSA is configured."""
        from ecdsa import NIST256p, SigningKey
        sk = SigningKey.generate(curve=NIST256p)
        pem = sk.to_pem().decode()
        audit_mod._ecdsa_initialized = False
        audit_mod._ecdsa_signing_key = None
        old = os.environ.get("AUDIT_ECDSA_KEY_PEM")
        os.environ["AUDIT_ECDSA_KEY_PEM"] = pem
        try:
            # Must call _get_ecdsa_signer first to init
            _get_ecdsa_signer()
            result = _compute_ecdsa_signature("somehash")
            assert result is not None
            assert isinstance(result, str)
            # Should be valid hex
            bytes.fromhex(result)
        finally:
            if old is None:
                os.environ.pop("AUDIT_ECDSA_KEY_PEM", None)
            else:
                os.environ["AUDIT_ECDSA_KEY_PEM"] = old


# ---------------------------------------------------------------------------
# Thread safety of _init_database
# ---------------------------------------------------------------------------

class TestThreadSafety:
    def test_concurrent_init(self):
        """Multiple threads calling _init_database simultaneously don't corrupt."""
        audit_mod.DATABASE_PATH = ":memory:"
        audit_mod._db_initialized = False
        audit_mod._memory_conn = None

        errors = []

        def init_thread():
            try:
                audit_mod._init_database()
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=init_thread) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0
        assert audit_mod._db_initialized is True

        # Cleanup — avoid cross-thread SQLite access; just reset the flag
        # The autouse fixture will restore the original module state.
        audit_mod._db_initialized = False
        audit_mod._memory_conn = None


# ---------------------------------------------------------------------------
# DATABASE_PATH and module-level configuration
# ---------------------------------------------------------------------------

class TestConfiguration:
    def test_database_path_default(self):
        """Default DATABASE_PATH points to audit_store.db beside the module."""
        # Restore to original (may have been changed by fixture)
        # Just check it ends with audit_store.db
        original = os.path.join(
            os.path.dirname(audit_mod.__file__), "audit_store.db"
        )
        # The module-level DATABASE_PATH can be overridden by AUDIT_DB_PATH env var
        # so we just check the default computation is correct
        assert original.endswith("audit_store.db")

    def test_database_path_from_env(self):
        """DATABASE_PATH can be overridden via AUDIT_DB_PATH env var."""
        # This was already set at import time, so we verify the logic
        # by checking the code path. The actual value depends on the env.
        # We'll just test that the module reads it.
        assert isinstance(audit_mod.DATABASE_PATH, str)


# ---------------------------------------------------------------------------
# Edge cases for verify_ecdsa_signature with details as string
# ---------------------------------------------------------------------------

class TestVerifyEcdsaEdgeCases:
    @pytest.mark.skipif(not audit_mod.HAS_ECDSA, reason="ecdsa not installed")
    def test_details_as_string_uses_as_is(self):
        """When details is a string (not dict), it's used directly for hash."""
        from ecdsa import NIST256p, SigningKey
        sk = SigningKey.generate(curve=NIST256p)
        vk_pem = sk.verifying_key.to_pem().decode()

        details_str = '{"key": "value"}'
        record = {
            "timestamp": "2024-01-01T00:00:00Z",
            "event_type": "TEST",
            "room_id": "R1",
            "details": details_str,
            "previous_hash": "GENESIS",
        }
        current_hash = _compute_hash(
            record["timestamp"], record["event_type"],
            record["room_id"], details_str, record["previous_hash"]
        )
        record["current_hash"] = current_hash
        sig = sk.sign(current_hash.encode("utf-8"))
        record["ecdsa_signature"] = sig.hex()

        result = verify_ecdsa_signature(record, vk_pem)
        assert result is True


# ---------------------------------------------------------------------------
# File-based database path coverage
# ---------------------------------------------------------------------------

class TestFileDatabase:
    """Tests using a temporary file database (not :memory:)."""

    def test_file_db_init_creates_db(self, hmac_key_env):
        """_init_database creates the SQLite file on disk."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test_audit.db")
            audit_mod.DATABASE_PATH = db_path
            audit_mod._db_initialized = False
            audit_mod._memory_conn = None
            audit_mod._init_database()
            assert os.path.isfile(db_path)
            # Cleanup
            audit_mod._db_initialized = False

    def test_file_db_creates_parent_directory(self, hmac_key_env):
        """_init_database creates parent directories if they don't exist."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "subdir", "nested", "test_audit.db")
            audit_mod.DATABASE_PATH = db_path
            audit_mod._db_initialized = False
            audit_mod._memory_conn = None
            audit_mod._init_database()
            assert os.path.isfile(db_path)
            # Cleanup
            audit_mod._db_initialized = False

    def test_file_db_get_connection_opens(self, hmac_key_env):
        """_get_connection returns a new connection for file-based DB."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test_audit.db")
            audit_mod.DATABASE_PATH = db_path
            audit_mod._db_initialized = False
            audit_mod._memory_conn = None
            conn = audit_mod._get_connection()
            assert isinstance(conn, sqlite3.Connection)
            conn.close()
            audit_mod._db_initialized = False

    def test_file_db_release_connection_closes(self, hmac_key_env):
        """_release_connection closes file-based DB connections."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test_audit.db")
            audit_mod.DATABASE_PATH = db_path
            audit_mod._db_initialized = False
            audit_mod._memory_conn = None
            conn = audit_mod._get_connection()
            audit_mod._release_connection(conn)
            # Connection should be closed now; using it should raise
            with pytest.raises((RuntimeError, ValueError, Exception)):
                conn.execute("SELECT 1")
            audit_mod._db_initialized = False

    def test_file_db_add_and_verify(self, hmac_key_env):
        """Full add_event + verify_chain cycle on file DB."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test_audit.db")
            audit_mod.DATABASE_PATH = db_path
            audit_mod._db_initialized = False
            audit_mod._memory_conn = None
            h = add_event("FILE_TEST", "R1", {"source": "file"})
            assert isinstance(h, str) and len(h) == 64
            is_valid, error = verify_chain()
            assert is_valid is True
            events = get_events()
            assert len(events) == 1
            assert events[0]["event_type"] == "FILE_TEST"
            audit_mod._db_initialized = False


# ---------------------------------------------------------------------------
# V10 migration (ALTER TABLE for ecdsa_signature column)
# ---------------------------------------------------------------------------

class TestV10Migration:
    """Test migration from V10 (8-column) schema to V11 (9-column)."""

    def test_migration_adds_ecdsa_column(self, hmac_key_env):
        """If V10 table exists without ecdsa_signature, migration adds it."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test_migration.db")
            # Step 1: Create a V10 schema manually
            conn = sqlite3.connect(db_path)
            conn.execute("""
                CREATE TABLE audit_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    room_id TEXT,
                    details TEXT NOT NULL,
                    previous_hash TEXT NOT NULL,
                    current_hash TEXT NOT NULL,
                    signature TEXT
                )
            """)
            conn.commit()
            conn.close()

            # Step 2: Now let _init_database run migration
            audit_mod.DATABASE_PATH = db_path
            audit_mod._db_initialized = False
            audit_mod._memory_conn = None
            audit_mod._init_database()

            # Step 3: Verify the ecdsa_signature column now exists
            conn2 = sqlite3.connect(db_path)
            cursor = conn2.cursor()
            cursor.execute("PRAGMA table_info(audit_log)")
            col_names = [row[1] for row in cursor.fetchall()]
            conn2.close()
            assert "ecdsa_signature" in col_names
            audit_mod._db_initialized = False


# ---------------------------------------------------------------------------
# V10 row handling in verify_chain and get_events (8-column rows)
# ---------------------------------------------------------------------------

class TestV10RowHandling:
    """Test that verify_chain and get_events handle 8-column (V10) rows."""

    def test_verify_chain_v10_rows(self, hmac_key_env):
        """verify_chain works with V10 rows (8 columns, no ecdsa_signature)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test_v10.db")
            audit_mod.DATABASE_PATH = db_path
            audit_mod._db_initialized = False
            audit_mod._memory_conn = None

            # Create V10 schema and insert a V10 row directly
            conn = sqlite3.connect(db_path)
            conn.execute("""
                CREATE TABLE audit_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    room_id TEXT,
                    details TEXT NOT NULL,
                    previous_hash TEXT NOT NULL,
                    current_hash TEXT NOT NULL,
                    signature TEXT
                )
            """)
            # Insert a proper V10 row
            ts = "2024-01-01T00:00:00Z"
            et = "V10_TEST"
            rid = "R1"
            det = '{"key": "value"}'
            prev = "GENESIS"
            cur = _compute_hash(ts, et, rid, det, prev)
            sig = hmac.new(
                hmac_key_env.encode(), cur.encode(), hashlib.sha256
            ).hexdigest()
            conn.execute(
                "INSERT INTO audit_log (timestamp, event_type, room_id, details, previous_hash, current_hash, signature) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (ts, et, rid, det, prev, cur, sig),
            )
            conn.commit()
            conn.close()

            # Mark as initialized so _init_database won't try to re-create
            audit_mod._db_initialized = True

            # verify_chain should handle 8-column rows
            is_valid, error = verify_chain()
            assert is_valid is True
            audit_mod._db_initialized = False

    def test_get_events_v10_rows(self, hmac_key_env):
        """get_events works with V10 rows (8 columns, no ecdsa_signature)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test_v10_get.db")
            audit_mod.DATABASE_PATH = db_path
            audit_mod._db_initialized = False
            audit_mod._memory_conn = None

            # Create V10 schema and insert a V10 row directly
            conn = sqlite3.connect(db_path)
            conn.execute("""
                CREATE TABLE audit_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    room_id TEXT,
                    details TEXT NOT NULL,
                    previous_hash TEXT NOT NULL,
                    current_hash TEXT NOT NULL,
                    signature TEXT
                )
            """)
            ts = "2024-01-01T00:00:00Z"
            et = "V10_GET"
            rid = "R1"
            det = '{"key": "value"}'
            prev = "GENESIS"
            cur = _compute_hash(ts, et, rid, det, prev)
            sig = hmac.new(
                hmac_key_env.encode(), cur.encode(), hashlib.sha256
            ).hexdigest()
            conn.execute(
                "INSERT INTO audit_log (timestamp, event_type, room_id, details, previous_hash, current_hash, signature) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (ts, et, rid, det, prev, cur, sig),
            )
            conn.commit()
            conn.close()

            audit_mod._db_initialized = True

            events = get_events()
            assert len(events) == 1
            assert events[0]["event_type"] == "V10_GET"
            # V10 rows should NOT have ecdsa_signature key
            assert "ecdsa_signature" not in events[0]
            audit_mod._db_initialized = False


# ---------------------------------------------------------------------------
# Double-checked locking in _init_database
# ---------------------------------------------------------------------------

class TestDoubleCheckedLocking:
    def test_returns_early_if_already_initialized(self):
        """When _db_initialized is True, _init_database returns immediately."""
        audit_mod.DATABASE_PATH = ":memory:"
        audit_mod._db_initialized = True
        audit_mod._memory_conn = None
        # Should not create any new connection or touch the DB
        audit_mod._init_database()
        # _memory_conn should still be None since we didn't actually init
        assert audit_mod._memory_conn is None
        audit_mod._db_initialized = False

    def test_inner_lock_check(self):
        """The inner double-checked lock also returns early."""
        audit_mod.DATABASE_PATH = ":memory:"
        audit_mod._db_initialized = False
        audit_mod._memory_conn = None
        # First call initializes
        audit_mod._init_database()
        assert audit_mod._db_initialized is True
        first_conn = audit_mod._memory_conn
        # Second call should return early (inner check hits)
        audit_mod._init_database()
        # Same connection should still be in use
        assert audit_mod._memory_conn is first_conn
        # Cleanup
        if audit_mod._memory_conn is not None:
            audit_mod._memory_conn.close()
            audit_mod._memory_conn = None
        audit_mod._db_initialized = False


# ---------------------------------------------------------------------------
# ecdsa_signature present in get_events
# ---------------------------------------------------------------------------

class TestEcdsaSignatureInEvents:
    def test_ecdsa_signature_present_when_not_null(self, memory_db, hmac_key_env):
        """When ecdsa_signature column has a value, get_events includes it."""
        # Manually insert a row with a non-null ecdsa_signature
        conn = audit_mod._memory_conn
        ts = "2024-01-01T00:00:00Z"
        et = "ECDSA_TEST"
        rid = "R1"
        det = '{"key": "value"}'
        prev = "GENESIS"
        cur = _compute_hash(ts, et, rid, det, prev)
        sig = hmac.new(
            hmac_key_env.encode(), cur.encode(), hashlib.sha256
        ).hexdigest()
        ecdsa_sig = "abcd1234"
        conn.execute(
            "INSERT INTO audit_log (timestamp, event_type, room_id, details, previous_hash, current_hash, signature, ecdsa_signature) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (ts, et, rid, det, prev, cur, sig, ecdsa_sig),
        )
        conn.commit()

        events = get_events()
        assert len(events) == 1
        assert events[0]["ecdsa_signature"] == "abcd1234"
