"""
test_final_system.py – Final Integration Test for FireAI Production System
==========================================================================
Tests the full FireAISystem with V10 ExpertSystem and AuditStore.
"""

import sys
import os
sys.path.insert(0, '/workspace/project/revit')

# Remove old database if exists
DB_PATH = '/workspace/project/revit/fireai/core/audit_store.db'
if os.path.exists(DB_PATH):
    os.remove(DB_PATH)

# Test imports
from fireai.core.fireai_core import FireAISystem
from fireai.core.nfpa72_models import RoomSpec, CeilingSpec

print("=== FireAI Production System Test ===")
print()

# Create system
system = FireAISystem(db_path=":memory:")
print("1. System created: OK")

# Create test room
room = RoomSpec(
    room_id="test_room_001",
    width_m=10,
    depth_m=10,
    ceiling_spec=CeilingSpec(height_at_low_point_m=3.0),
)
print("2. Room created: OK")

# Analyze room
result = system.analyse_room(room, user_id="test_user")
print("3. Analysis completed")

# Check results
print()
print("=== Results ===")
print(f"Detectors placed: {len(result.detector_positions)}")
print(f"Confidence: {result.confidence.value if result.confidence else 'UNKNOWN'}")
print(f"Coverage: {result.placement_proof.coverage_fraction * 100:.1f}%" if result.placement_proof else "N/A")

# Assertions
print()
print("=== Assertions ===")
errors = []

# 1. Confidence NOT UNSAFE
if result.confidence and result.confidence.value == "UNSAFE":
    errors.append(f"Confidence is UNSAFE: {result.errors}")
else:
    print("1. Confidence NOT UNSAFE: PASS")

# 2. Audit trail has event
events = system.get_audit_trail()
if not events:
    errors.append("Audit trail is empty")
else:
    print(f"2. Audit trail has {len(events)} event(s): PASS")

# 3. Audit integrity verified
if not system.verify_audit_integrity():
    errors.append("Audit integrity verification failed")
else:
    print("3. Audit integrity verified: PASS")

# Final result
print()
if errors:
    print("=== FAILURES ===")
    for e in errors:
        print(f"  - {e}")
    print()
    print("SYSTEM FINAL: FAIL")
else:
    print("=== ALL TESTS PASSED ===")
    print("SYSTEM FINAL: PASS")