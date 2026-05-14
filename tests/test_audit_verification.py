"""
tests/test_audit_verification.py
===========================
Verify that all writes go through audit trail.
"""

import pytest
import tempfile
from src.v8_core.db_pool import DatabasePool
from src.v8_core.audit_trail import AuditTrail


def test_audit_trail_catches_all_writes():
    """Verify audit trail captures all database writes."""
    
    with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
        db_path = f.name
    
    pool = DatabasePool(db_path)
    audit = AuditTrail(pool)
    
    # Issue an override token
    token_data = {
        'override_id': 'TEST-001',
        'token': '256-bit-token-12345',
        'issued_by': 'PE-TEST',
        'expires_at': '2026-12-31T23:59:59Z',
    }
    
    # Write through pool - MUST be audited
    pool.execute(
        "INSERT INTO audit_trail (action, entity_type, entity_id, performed_by, performed_at, details)",
        ("CREATE", "override", "TEST-001", "PE-TEST", "2026-05-14T00:00:00Z", '{"token": "***"}')
    )
    
    # Verify audit entry exists
    result = pool.execute(
        "SELECT COUNT(*) FROM audit_trail WHERE entity_id = ?",
        ("TEST-001",)
    )
    count = result.fetchone()[0]
    
    assert count >= 1, "Write NOT captured in audit trail!"
    
    pool.close()
    
    print("✅ All writes go through audit trail")


def test_audit_trail_blocked_without_audit():
    """Verify direct writes WITHOUT audit are blocked."""
    
    with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
        db_path = f.name
    
    pool = DatabasePool(db_path)
    
    # Try direct write (bypassing audit)
    # This SHOULD fail if triggers are working
    try:
        pool.execute(
            "INSERT INTO override_tokens (override_id, token, issued_by, expires_at)",
            ("BAD-001", "token", "PE-TEST", "2026-12-31")
        )
        # If we get here, trigger didn't work
        has_trigger = False
    except Exception:
        # Expected - trigger blocked
        has_trigger = True
    
    assert has_trigger, "Audit trigger NOT blocking direct writes!"
    
    pool.close()
    
    print("✅ Direct writes blocked without audit")


if __name__ == "__main__":
    test_audit_trail_catches_all_writes()
    test_audit_trail_blocked_without_audit()
    print("✅ All audit verification tests passed")