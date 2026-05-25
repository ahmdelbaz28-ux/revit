"""
test_hmac_tamper.py – Prove HMAC tamper detection works
===========================================
This test proves that verify_chain() detects tampering even when:
- event details are modified
- current_hash is correctly recomputed
- signature is LEFT AS IS (old signature)

This is the most dangerous attack vector.

RESULT: Tamper is detected because the HMAC signature doesn't match the NEW hash.
"""

import sys
import os
import json
import sqlite3
import hashlib
import hmac
import tempfile
import time
from pathlib import Path
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

import fireai.core.audit_store as audit_store


def test_hmac_tamper_detection():
    """Prove that verify_chain() detects tampering even when hash is recomputed."""
    # STEP A: Use a temp database
    with tempfile.NamedTemporaryFile(mode='w', suffix='.db', delete=False) as temp_file:
        temp_path = temp_file.name

    try:
        # Set up audit store to use temp database
        orig_db_path = audit_store.DATABASE_PATH
        orig_db_init = audit_store._db_initialized
        audit_store.DATABASE_PATH = temp_path
        audit_store._db_initialized = False

        # STEP B: Add 3 test events
        events = [
            ("test", "room1", {"key": "value1"}),
            ("test", "room2", {"key": "value2"}),
            ("test", "room3", {"key": "value3"}),
        ]
        for event_type, room_id, details in events:
            audit_store.add_event(event_type=event_type, room_id=room_id, details_dict=details)

        # STEP C: Initial verification
        result_verify, _ = audit_store.verify_chain()
        assert result_verify, "Initial verification should pass"

        # STEP D: Execute tamper scenario
        conn = sqlite3.connect(temp_path)
        cursor = conn.cursor()

        # Drop triggers to simulate an attacker who bypasses DB-level protection.
        # This tests the HMAC chain integrity — even if triggers are bypassed,
        # the HMAC signature should detect the tampering.
        cursor.execute("DROP TRIGGER IF EXISTS prevent_update")
        cursor.execute("DROP TRIGGER IF EXISTS prevent_delete")

        cursor.execute(
            "SELECT id, event_type, room_id, details, previous_hash, timestamp FROM audit_log WHERE id = 2"
        )
        row = cursor.fetchone()
        _event_id, event_type, room_id, _details_json, prev_hash, timestamp = row

        tampered_details = '{"key": "TAMPERED"}'
        payload = f"{timestamp}|{event_type}|{room_id}|{tampered_details}|{prev_hash}"
        new_current_hash = hashlib.sha256(payload.encode()).hexdigest()

        cursor.execute(
            "UPDATE audit_log SET details = ?, current_hash = ? WHERE id = 2",
            (tampered_details, new_current_hash),
        )
        conn.commit()
        conn.close()

        # STEP E: Verify after tampering – must detect the tamper
        result_after, info = audit_store.verify_chain()
        assert not result_after, "Tamper should be detected after modifying event details and hash"

    finally:
        audit_store.DATABASE_PATH = orig_db_path
        audit_store._db_initialized = orig_db_init
        if os.path.exists(temp_path):
            os.unlink(temp_path)


if __name__ == "__main__":
    test_hmac_tamper_detection()
    print("RESULT: HMAC tamper detection is WORKING")
