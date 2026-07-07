# NOSONAR
"""
tests/test_audit_store_v2.py
=============================
Comprehensive test suite for fireai/core/audit_store.py.

SAFETY CRITICAL: Audit store provides tamper-evident hash chain logging
for NFPA 72 compliance. Chain corruption could compromise legal evidence
and violate NFPA 72 §14.2.4 documentation integrity requirements.

NFPA 72 References:
  §14.2.4 — Documentation integrity requirements
  §10.6.7 — Record retention

Key features tested:
  - SHA-256 hash chain with HMAC-SHA256 signatures
  - SQLite immutability (prevent UPDATE/DELETE triggers)
  - ECDSA optional signing layer (V11)
  - SecurityError for short HMAC keys
  - AuditStore facade class
"""

from __future__ import annotations

import os
import sqlite3
from unittest.mock import patch

import pytest

from fireai.core.audit_store import (
    _MIN_HMAC_KEY_LENGTH,
    NFPA_VERSION,
    AuditStore,
    SecurityError,
    _compute_hash,
    _get_hmac_key,
    add_event,
    get_events,
    verify_chain,
)

# ─────────────────────────────────────────────────────────────────────────────
# Fixtures — Use :memory: SQLite for isolation
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def reset_database():
    """
    Reset the module-level database state before each test.

    Uses :memory: database for isolation between tests.
    """
    import fireai.core.audit_store as _as

    # Save original state
    orig_db_path = _as.DATABASE_PATH
    orig_initialized = _as._db_initialized
    orig_memory_conn = _as._memory_conn

    # Reset to :memory: for test isolation
    _as.DATABASE_PATH = ":memory:"
    _as._db_initialized = False
    _as._memory_conn = None

    # Reset ECDSA state
    _as._ecdsa_initialized = False
    _as._ecdsa_signing_key = None

    # Reset dev key
    _as._DEV_HMAC_KEY = None
    _as._DEV_KEY_WARNED = False

    yield

    # Restore original state
    _as.DATABASE_PATH = orig_db_path
    _as._db_initialized = orig_initialized
    _as._memory_conn = orig_memory_conn


# Constants and SecurityError  # NOSONAR - python:S125
# ─────────────────────────────────────────────────────────────────────────────


class TestConstants:
    def test_nfpa_version(self):
        assert NFPA_VERSION == "NFPA 72-2022"

    def test_min_hmac_key_length(self):
        assert _MIN_HMAC_KEY_LENGTH == 32


class TestSecurityError:
    def test_is_exception(self):
        assert issubclass(SecurityError, Exception)

    def test_can_be_raised(self):
        with pytest.raises(SecurityError, match="too short"):
            raise SecurityError("HMAC key is too short")


# _get_hmac_key
# ─────────────────────────────────────────────────────────────────────────────


class TestGetHmacKey:
    def test_dev_fallback_key(self):
        """When AUDIT_HMAC_KEY is not set, a dev key is auto-generated."""
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("AUDIT_HMAC_KEY", None)
            import fireai.core.audit_store as _as
            _as._DEV_HMAC_KEY = None
            _as._DEV_KEY_WARNED = False
            key = _get_hmac_key()
            assert len(key) >= _MIN_HMAC_KEY_LENGTH

    def test_env_key_accepted(self):
        """AUDIT_HMAC_KEY from env var is used when set."""
        with patch.dict(os.environ, {"AUDIT_HMAC_KEY": "a" * 32}):
            key = _get_hmac_key()
            assert key == "a" * 32

    def test_short_key_raises_security_error(self):
        """AUDIT_HMAC_KEY shorter than 32 chars → SecurityError."""
        with patch.dict(os.environ, {"AUDIT_HMAC_KEY": "tooshort"}):
            with pytest.raises(SecurityError, match="too short"):
                _get_hmac_key()

    def test_exactly_32_char_key_accepted(self):
        with patch.dict(os.environ, {"AUDIT_HMAC_KEY": "a" * 32}):
            key = _get_hmac_key()
            assert key == "a" * 32

    def test_long_key_accepted(self):
        with patch.dict(os.environ, {"AUDIT_HMAC_KEY": "a" * 64}):
            key = _get_hmac_key()
            assert key == "a" * 64


# _compute_hash
# ─────────────────────────────────────────────────────────────────────────────


class TestComputeHash:
    def test_deterministic(self):
        h1 = _compute_hash("2024-01-01", "TEST", "R1", '{"k":"v"}', "prev123")
        h2 = _compute_hash("2024-01-01", "TEST", "R1", '{"k":"v"}', "prev123")
        assert h1 == h2

    def test_different_inputs_different_hashes(self):
        h1 = _compute_hash("2024-01-01", "TEST1", "R1", '{}', "prev")
        h2 = _compute_hash("2024-01-01", "TEST2", "R1", '{}', "prev")
        assert h1 != h2

    def test_hash_is_64_hex_chars(self):
        h = _compute_hash("2024-01-01", "TEST", "R1", '{}', "prev")
        assert len(h) == 64
        assert all(c in "0123456789abcdef" for c in h)

    def test_genesis_hash(self):
        """First event should use 'GENESIS' as previous hash."""
        h = _compute_hash("2024-01-01", "FIRST", "", '{}', "GENESIS")
        assert len(h) == 64


# add_event
# ─────────────────────────────────────────────────────────────────────────────


class TestAddEvent:
    def test_add_event_returns_hash(self):
        result = add_event("ROOM_ANALYSIS", "R1", {"detector_count": 2})
        assert isinstance(result, str)
        assert len(result) == 64  # SHA-256 hex digest

    def test_add_event_invalid_details_raises(self):
        with pytest.raises(ValueError, match="dictionary"):
            add_event("TEST", "R1", "not a dict")  # NOSONAR — S5655: intentional wrong-type arg (test verifies rejection)

    def test_add_event_none_details_raises(self):
        with pytest.raises(ValueError, match="dictionary"):
            add_event("TEST", "R1", None)  # NOSONAR — S5655: intentional wrong-type arg (test verifies rejection)

    def test_add_event_list_details_raises(self):
        with pytest.raises(ValueError, match="dictionary"):
            add_event("TEST", "R1", [1, 2, 3])  # NOSONAR — S5655: intentional wrong-type arg (test verifies rejection)

    def test_add_event_stores_data(self):
        add_event("DETECTOR_PLACEMENT", "R1", {"count": 5, "type": "smoke"})
        events = get_events()
        assert len(events) == 1
        assert events[0]["event_type"] == "DETECTOR_PLACEMENT"
        assert events[0]["room_id"] == "R1"
        assert events[0]["details"]["count"] == 5

    def test_chain_links(self):
        """Each event's previous_hash must match the prior event's current_hash."""
        h1 = add_event("EVENT_1", "R1", {"step": 1})
        add_event("EVENT_2", "R1", {"step": 2})
        events = get_events()
        assert events[1]["previous_hash"] == events[0]["current_hash"]
        assert events[0]["current_hash"] == h1

    def test_first_event_uses_genesis(self):
        add_event("FIRST", "R1", {"step": 1})
        events = get_events()
        assert events[0]["previous_hash"] == "GENESIS"

    def test_hmac_signature_present(self):
        add_event("TEST", "R1", {"key": "value"})
        events = get_events()
        assert events[0]["signature"] is not None
        assert len(events[0]["signature"]) > 0

    def test_empty_details_dict(self):
        result = add_event("EMPTY", "R1", {})
        assert len(result) == 64

    def test_complex_details(self):
        details = {
            "room_id": "R1",
            "detectors": [
                {"id": "D1", "x": 1.0, "y": 2.0},
                {"id": "D2", "x": 3.0, "y": 4.0},
            ],
            "coverage_pct": 99.9,
        }
        add_event("COMPLEX", "R1", details)
        events = get_events()
        assert events[0]["details"]["detectors"][0]["id"] == "D1"


# verify_chain
# ─────────────────────────────────────────────────────────────────────────────


class TestVerifyChain:
    def test_empty_chain_valid(self):
        is_valid, error = verify_chain()
        assert is_valid is True
        assert error is None

    def test_single_event_valid(self):
        add_event("TEST", "R1", {"key": "value"})
        is_valid, _error = verify_chain()
        assert is_valid is True

    def test_multiple_events_valid(self):
        for i in range(10):
            add_event("TEST", f"R{i}", {"step": i})
        is_valid, _error = verify_chain()
        assert is_valid is True

    def test_tampered_hash_detected(self):
        """Tampering with a hash must be detected."""
        add_event("EVENT_1", "R1", {"step": 1})
        add_event("EVENT_2", "R1", {"step": 2})

        # Tamper with the database directly
        import fireai.core.audit_store as _as
        conn = _as._get_connection()
        cursor = conn.cursor()
        # Try to update (should fail due to trigger)
        with pytest.raises(sqlite3.IntegrityError):
            cursor.execute("UPDATE audit_log SET current_hash = 'tampered' WHERE id = 1")
        _as._release_connection(conn)

    def test_missing_signature_detected(self):
        """Missing HMAC signature must be detected."""
        # Add a valid event first so we have a previous hash
        add_event("TEST", "R1", {"key": "value"})

        # Get the last hash to chain correctly
        import fireai.core.audit_store as _as
        prev_hash = _as._get_last_hash()

        # Insert a row with valid hash chain but empty signature
        conn = _as._get_connection()
        cursor = conn.cursor()
        ts = "2024-01-02T00:00:00Z"
        details = '{"bad":true}'
        cur_hash = _compute_hash(ts, "BAD_EVENT", "R1", details, prev_hash)
        # Empty signature — this is the violation we want to detect
        cursor.execute(
            "INSERT INTO audit_log (timestamp, event_type, room_id, details, previous_hash, current_hash, signature) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (ts, "BAD_EVENT", "R1", details, prev_hash, cur_hash, ""),
        )
        conn.commit()
        _as._release_connection(conn)

        is_valid, error = verify_chain()
        assert is_valid is False
        assert error is not None
        assert "Missing HMAC signature" in error["reason"]

    def test_wrong_signature_detected(self):
        """Wrong HMAC signature must be detected."""
        add_event("TEST", "R1", {"key": "value"})

        import fireai.core.audit_store as _as
        conn = _as._get_connection()
        cursor = conn.cursor()
        # Insert a row with wrong signature
        ts = "2024-01-02T00:00:00Z"
        prev_hash = _as._get_last_hash()
        details = '{"bad":true}'
        cur_hash = _compute_hash(ts, "TAMPERED", "R1", details, prev_hash)
        cursor.execute(
            "INSERT INTO audit_log (timestamp, event_type, room_id, details, previous_hash, current_hash, signature) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (ts, "TAMPERED", "R1", details, prev_hash, cur_hash, "wrong_signature"),
        )
        conn.commit()
        _as._release_connection(conn)

        is_valid, _error = verify_chain()
        assert is_valid is False


# get_events
# ─────────────────────────────────────────────────────────────────────────────


class TestGetEvents:
    def test_empty_database(self):
        events = get_events()
        assert events == []

    def test_returns_all_events(self):
        add_event("EVENT_1", "R1", {"step": 1})
        add_event("EVENT_2", "R2", {"step": 2})
        events = get_events()
        assert len(events) == 2

    def test_event_structure(self):
        add_event("TEST", "R1", {"key": "value"})
        events = get_events()
        e = events[0]
        assert "id" in e
        assert "timestamp" in e
        assert "event_type" in e
        assert "room_id" in e
        assert "details" in e
        assert "previous_hash" in e
        assert "current_hash" in e
        assert "signature" in e

    def test_details_deserialized(self):
        add_event("TEST", "R1", {"count": 5, "name": "smoke"})
        events = get_events()
        assert isinstance(events[0]["details"], dict)
        assert events[0]["details"]["count"] == 5

    def test_events_ordered_by_id(self):
        add_event("FIRST", "R1", {"step": 1})
        add_event("SECOND", "R2", {"step": 2})
        events = get_events()
        assert events[0]["event_type"] == "FIRST"
        assert events[1]["event_type"] == "SECOND"


# ─────────────────────────────────────────────────────────────────────────────
# AuditStore Facade Class
# ─────────────────────────────────────────────────────────────────────────────


class TestAuditStoreFacade:
    def test_add_event_delegates(self):
        result = AuditStore.add_event("TEST", "R1", {"key": "value"})
        assert isinstance(result, str)
        assert len(result) == 64

    def test_verify_chain_delegates(self):
        AuditStore.add_event("TEST", "R1", {"key": "value"})
        is_valid, _error = AuditStore.verify_chain()
        assert is_valid is True

    def test_get_events_delegates(self):
        AuditStore.add_event("TEST", "R1", {"key": "value"})
        events = AuditStore.get_events()
        assert len(events) == 1

    def test_facade_matches_functional_api(self):
        """Facade and functional API must produce the same results."""
        h1 = AuditStore.add_event("FACADE", "R1", {"test": True})
        events = AuditStore.get_events()
        assert events[0]["current_hash"] == h1


# ─────────────────────────────────────────────────────────────────────────────
# SQLite Immutability Triggers
# ─────────────────────────────────────────────────────────────────────────────


class TestSQLiteImmutability:
    def test_update_prevented(self):
        """UPDATE trigger must prevent modification of audit records."""
        add_event("TEST", "R1", {"key": "value"})
        import fireai.core.audit_store as _as
        conn = _as._get_connection()
        cursor = conn.cursor()
        with pytest.raises(sqlite3.IntegrityError, match="UPDATE"):
            cursor.execute("UPDATE audit_log SET event_type = 'TAMPERED' WHERE id = 1")
        _as._release_connection(conn)

    def test_delete_prevented(self):
        """DELETE trigger must prevent removal of audit records."""
        add_event("TEST", "R1", {"key": "value"})
        import fireai.core.audit_store as _as
        conn = _as._get_connection()
        cursor = conn.cursor()
        with pytest.raises(sqlite3.IntegrityError, match="DELETE"):
            cursor.execute("DELETE FROM audit_log WHERE id = 1")
        _as._release_connection(conn)


# ─────────────────────────────────────────────────────────────────────────────
# ECDSA Layer (optional)
# ─────────────────────────────────────────────────────────────────────────────


class TestECDSALayer:
    def test_ecdsa_not_configured_by_default(self):
        """ECDSA signing is disabled when AUDIT_ECDSA_KEY_PEM is not set."""
        import fireai.core.audit_store as _as
        signer = _as._get_ecdsa_signer()
        assert signer is None

    def test_ecdsa_signature_field_in_events(self):
        """When ECDSA is disabled, ecdsa_signature should be None."""
        add_event("TEST", "R1", {"key": "value"})
        events = get_events()
        # Without ECDSA key, ecdsa_signature may be None or absent
        e = events[0]
        assert "ecdsa_signature" not in e or e.get("ecdsa_signature") is None


# ─────────────────────────────────────────────────────────────────────────────
# Edge Cases
# ─────────────────────────────────────────────────────────────────────────────


class TestEdgeCases:
    def test_special_characters_in_room_id(self):
        """Room IDs with special characters must be handled."""
        result = add_event("TEST", "Room #101 (Floor-2)", {"key": "value"})
        assert len(result) == 64

    def test_unicode_in_details(self):
        """Unicode values in details must be handled."""
        add_event("TEST", "R1", {"name": "Büro-101", "description": "空调房间"})
        events = get_events()
        assert events[0]["details"]["name"] == "Büro-101"

    def test_large_details_dict(self):
        """Large details dictionary must be handled."""
        details = {f"key_{i}": f"value_{i}" for i in range(100)}
        add_event("TEST", "R1", details)
        events = get_events()
        assert len(events[0]["details"]) == 100

    def test_nested_details(self):
        """Nested dictionaries in details must be serialized properly."""
        details = {
            "room": {"id": "R1", "area_sqm": 25.0},
            "detectors": [{"id": "D1", "x": 1.0}],
        }
        add_event("TEST", "R1", details)
        events = get_events()
        assert events[0]["details"]["room"]["area_sqm"] == 25.0  # NOSONAR — S1244: import retained for re-export / API surface

    def test_timestamp_is_utc(self):
        """V54 FIX (AUDIT-012): Timestamps must use UTC."""
        add_event("TEST", "R1", {"key": "value"})
        events = get_events()
        ts = events[0]["timestamp"]
        assert ts.endswith("Z") or "+00:00" in ts

    def test_many_events_performance(self):
        """Adding 100 events should not take too long."""
        import time
        start = time.monotonic()
        for i in range(100):
            add_event("PERF_TEST", f"R{i}", {"step": i})
        elapsed = time.monotonic() - start
        # Should complete in reasonable time (< 10 seconds)
        assert elapsed < 10.0

    def test_verify_chain_after_100_events(self):
        """Chain must remain valid after 100 events."""
        for i in range(100):
            add_event("TEST", f"R{i}", {"step": i})
        is_valid, _error = verify_chain()
        assert is_valid is True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
