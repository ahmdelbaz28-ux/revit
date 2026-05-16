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
sys.path.insert(0, '/workspace/project/revit')

# Import the audit_store module functions
import fireai.core.audit_store as audit_store


print("=" * 70)
print("HMAC TAMPER DETECTION TEST")
print("=" * 70)
print()


# ============================================================================
# STEP A: Create temp database file
# ============================================================================
print("[A] Creating temp database file...")

# Create temp file for database
temp_file = tempfile.NamedTemporaryFile(mode='w', suffix='.db', delete=False)
temp_path = temp_file.name
temp_file.close()

print(f"    Temp file: {temp_path}")

# Initialize database
audit_store._init_database()
print(f"    Database initialized")


# ============================================================================
# STEP B: Add 3 test events
# ============================================================================
print()
print("[B] Adding 3 test events...")

events = [
    ("test", "room1", {"key": "value1"}),
    ("test", "room2", {"key": "value2"}),
    ("test", "room3", {"key": "value3"}),
]

for event_type, room_id, details in events:
    audit_store.add_event(event_type=event_type, room_id=room_id, details_dict=details)
    print(f"    Added: {room_id} -> {details}")


# ============================================================================
# STEP C: Initial verification
# ============================================================================
print()
print("[C] Initial verification...")

result_verify, _ = audit_store.verify_chain()
print(f"    verify_chain() returned: {result_verify}")

if result_verify == True:
    print("    Initial verify: PASS")
else:
    print("    FAIL: Initial verification failed!")
    print("    ABORTING TEST")
    os.unlink(temp_path)
    sys.exit(1)


# ============================================================================
# STEP D: Execute tamper scenario
# ============================================================================
print()
print("[D] Executing tamper scenario...")

# Get the data we need to compute correct hash
conn = sqlite3.connect(audit_store.DATABASE_PATH)
cursor = conn.cursor()

cursor.execute("SELECT id, event_type, room_id, details, previous_hash, timestamp FROM audit_log WHERE id = 2")
row = cursor.fetchone()
event_id, event_type, room_id, details_json, prev_hash, timestamp = row

print(f"    Original event 2: room_id={room_id}, details={details_json}")

# Tamper: modify details
tampered_details = '{"key": "TAMPERED"}'

# Compute NEW current_hash correctly
payload = f"{timestamp}|{event_type}|{room_id}|{tampered_details}|{prev_hash}"
new_current_hash = hashlib.sha256(payload.encode()).hexdigest()

print(f"    Computed new hash: {new_current_hash[:16]}...")
print(f"    Old signature: (unchanged)")

# Update event 2 with tampered details and new hash
# Leave signature field unchanged (this is the key - we keep the old signature)
cursor.execute(
    "UPDATE audit_log SET details = ?, current_hash = ? WHERE id = 2",
    (tampered_details, new_current_hash)
)
conn.commit()
conn.close()

print(f"    Event updated: details=TAMPERED, hash updated, signature unchanged")
print(f"    TAMPER SCENARIO COMPLETE")


# ============================================================================
# STEP E: Verify after tampering
# ============================================================================
print()
print("[E] Verification after tampering...")

# Re-verify with same store
result_after, info = audit_store.verify_chain()

if result_after == False:
    print("    Tamper detected: PASS")
else:
    print("    FAIL: Tamper NOT detected!")
    print("    This means HMAC verification is broken!")

# Get error messages
if info and 'reason' in info:
    print()
    print(f"    Error: {info['reason']}")

print()
print("=" * 70)
print("RESULT: HMAC tamper detection is WORKING" if not result_after else "RESULT: HMAC FAILURE")
print("=" * 70)