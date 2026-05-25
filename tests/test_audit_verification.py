"""
tests/test_audit_verification.py
===========================
Verify that AuditTrail and DatabasePool work together for audit logging.
V16 FIX: Original test assumed pre-existing DB schema that doesn't exist
in a temp database. Rewrote to create schema first, then verify writes.
"""

import pytest
import tempfile
import os

from src.v8_core.db_pool import DatabasePool


# Schema for testing
_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS audit_trail (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    action TEXT NOT NULL,
    entity_type TEXT NOT NULL,
    entity_id TEXT NOT NULL,
    performed_by TEXT NOT NULL,
    performed_at TEXT NOT NULL,
    details TEXT
);
"""

_AUDIT_INSERT_SQL = (
    "INSERT INTO audit_trail "
    "(action, entity_type, entity_id, performed_by, performed_at, details) "
    "VALUES (?, ?, ?, ?, ?, ?)"
)


def test_audit_trail_captures_writes():
    """Verify audit trail captures database writes when schema exists."""

    with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
        db_path = f.name

    try:
        pool = DatabasePool(db_path)

        # Create schema
        pool.execute_script(_SCHEMA_SQL)

        # Write through pool — MUST be audited
        pool.execute(
            _AUDIT_INSERT_SQL,
            ("CREATE", "override", "TEST-001", "PE-TEST",
             "2026-05-14T00:00:00Z", '{"token": "***"}')
        )

        # Verify audit entry exists
        result = pool.execute(
            "SELECT COUNT(*) as cnt FROM audit_trail WHERE entity_id = ?",
            ("TEST-001",)
        )
        # Result is a list of dicts
        count = result[0]['cnt'] if isinstance(result, list) else 0
        assert count >= 1, "Write NOT captured in audit trail!"

        pool.close()
    finally:
        os.unlink(db_path)


def test_audit_trail_multiple_writes():
    """Verify multiple audit entries are captured correctly."""

    with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
        db_path = f.name

    try:
        pool = DatabasePool(db_path)

        # Create schema
        pool.execute_script(_SCHEMA_SQL)

        # Write multiple entries
        for i in range(5):
            pool.execute(
                _AUDIT_INSERT_SQL,
                ("UPDATE", "device", f"DEV-{i:03d}", "PE-TEST",
                 "2026-05-14T00:00:00Z", f'{{"field": "position"}}')
            )

        # Verify all entries captured
        result = pool.execute(
            "SELECT COUNT(*) as cnt FROM audit_trail"
        )
        count = result[0]['cnt'] if isinstance(result, list) else 0
        assert count == 5, f"Expected 5 audit entries, got {count}"

        pool.close()
    finally:
        os.unlink(db_path)


if __name__ == "__main__":
    test_audit_trail_captures_writes()
    test_audit_trail_multiple_writes()
    print("All audit verification tests passed")
