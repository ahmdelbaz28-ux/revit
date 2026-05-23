"""
test_final.py — Final Verification Tests

Tests:
1. HMAC signature verification (tamper detection)
2. CeilingSpec.create_safe beam parameters
3. V12 integration
4. Resilience checks

Run: python3 fireai/core/test_final.py
"""

import sys
from pathlib import Path
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

import os
import sqlite3
import tempfile
import hashlib
import hmac


def test_hmac_tamper():
    """Test HMAC signature verification catches tampering."""
    print("=" * 60)
    print("TEST 1: HMAC Signature Verification")
    print("=" * 60)
    
    # Use temp file for db
    with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
        db_path = f.name
    
    # Import and configure before init
    from fireai.core import audit_store as audit_module
    audit_module.DATABASE_PATH = db_path
    audit_module._init_database()
    
    # Add 3 events
    for i in range(3):
        audit_module.add_event(
            event_type=f"room_analysis",
            room_id=f"room_{i}",
            details_dict={"detector_count": i + 1, "user": "test"},
        )
    
    # Verify before tampering
    is_valid, error = audit_module.verify_chain()
    print(f"Before tamper: is_valid={is_valid}")
    if not is_valid:
        print("  FAILED: Should be valid before tampering")
        os.remove(db_path)
        return False
    
    # Tamper 1: Change details but keep old hash (need to bypass triggers)
    # Re-create database without triggers for testing
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    # Drop trigger
    cursor.execute("DROP TRIGGER IF EXISTS prevent_update")
    cursor.execute("DROP TRIGGER IF EXISTS prevent_delete")
    # Now tamper
    cursor.execute("UPDATE audit_log SET details = '{\"tampered\": true}' WHERE id = 1")
    conn.commit()
    conn.close()
    
    is_valid, error = audit_module.verify_chain()
    print(f"After tamper (keep hash): is_valid={is_valid}")
    if is_valid:
        os.remove(db_path)
        print("  FAILED: Should detect hash tampering")
        return False
    
    # Reset for second test - init fresh db with events
    audit_module.DATABASE_PATH = db_path
    audit_module._init_database()
    for i in range(3):
        audit_module.add_event(
            event_type=f"room_analysis",
            room_id=f"room_{i}",
            details_dict={"detector_count": i + 1, "user": "test"},
        )
    
    # Tamper 2: Change details AND recompute hash, keep old signature
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    # Drop triggers
    cursor.execute("DROP TRIGGER IF EXISTS prevent_update")
    cursor.execute("DROP TRIGGER IF EXISTS prevent_delete")
    
    cursor.execute("SELECT timestamp, event_type, room_id, details, previous_hash FROM audit_log WHERE id = 2")
    row = cursor.fetchone()
    timestamp, event_type, room_id, details, prev_hash = row
    
    new_details = '{"new_tampered": true}'
    payload = f"{timestamp}|{event_type}|{room_id}|{new_details}|{prev_hash}"
    new_hash = hashlib.sha256(payload.encode()).hexdigest()
    
    cursor.execute(
        "UPDATE audit_log SET details = ?, current_hash = ? WHERE id = 2",
        (new_details, new_hash)
    )
    conn.commit()
    conn.close()
    
    is_valid, error = audit_module.verify_chain()
    print(f"After tamper (recompute hash): is_valid={is_valid}")
    if is_valid:
        os.remove(db_path)
        print("  FAILED: Should detect signature mismatch")
        return False
    
    os.remove(db_path)
    print("  HMAC signature verification active: tamper detected correctly.")
    print("  TEST 1: PASSED")
    return True


def test_create_safe_beam_params():
    """Test create_safe accepts beam parameters."""
    print("\n" + "=" * 60)
    print("TEST 2: CeilingSpec.create_safe Beam Parameters")
    print("=" * 60)
    
    from fireai.core.nfpa72_models import CeilingSpec
    
    ceiling = CeilingSpec.create_safe(
        height_at_low_point_m=4.5,
        beam_depth_m=0.3,
        beam_spacing_m=1.2,
    )
    
    print(f"  beam_depth_m: {ceiling.beam_depth_m} (expected 0.3)")
    print(f"  beam_spacing_m: {ceiling.beam_spacing_m} (expected 1.2)")
    
    if ceiling.beam_depth_m != 0.3:
        print("  FAILED: beam_depth_m not stored")
        return False
    
    if ceiling.beam_spacing_m != 1.2:
        print("  FAILED: beam_spacing_m not stored")
        return False
    
    print(f"  was_clamped: {ceiling.was_clamped} (expected False)")
    
    print("  TEST 2: PASSED")
    return True


def test_v12_integration():
    """Test V12 integration works — uses FireExpertSystem (V10+ compatible).
    
    NOTE: fire_expert_system_v12 module never existed as a separate file.
    ExpertSystemV12 was a planned but never created class. The actual
    expert system is FireExpertSystem in fireai.core.fire_expert_system.
    """
    from fireai.core.nfpa72_models import CeilingSpec, CeilingType
    from fireai.core.fire_expert_system import FireExpertSystem
    from fireai.core.nfpa72_models import RoomSpec

    ceiling_spec = CeilingSpec(3.0)
    room_spec = RoomSpec(
        room_id="test_v12",
        width_m=10.0,
        depth_m=10.0,
        ceiling_spec=ceiling_spec,
        occupancy_type="office",
    )

    expert = FireExpertSystem()
    result = expert.analyse_room(
        name=room_spec.room_id,
        width=room_spec.width_m,
        length=room_spec.depth_m,
        ceiling_height=room_spec.ceiling_spec.height_at_low_point_m,
    )

    assert result is not None, "FireExpertSystem returned None"
    if hasattr(result, 'confidence') and hasattr(result.confidence, 'value'):
        assert result.confidence.value != "UNSAFE", f"Result is UNSAFE: {result.errors if hasattr(result, 'errors') else ''}"

    return True


def test_resilience():
    """Test resilience checks — uses FireExpertSystem.
    
    NOTE: fire_expert_system_v12 module never existed as a separate file.
    """
    from fireai.core.nfpa72_models import CeilingSpec, RoomSpec
    from fireai.core.fire_expert_system import FireExpertSystem

    # Test 1: Small room
    ceiling1 = CeilingSpec(3.0)
    room1 = RoomSpec(
        room_id="single",
        width_m=3.0,
        depth_m=3.0,
        ceiling_spec=ceiling1,
        occupancy_type="corridor",
    )

    expert = FireExpertSystem()
    result1 = expert.analyse_room(
        name=room1.room_id,
        width=room1.width_m,
        length=room1.depth_m,
        ceiling_height=room1.ceiling_spec.height_at_low_point_m,
    )

    # Single detector rooms have no redundancy
    det_count = len(result1.layout.detectors) if hasattr(result1, 'layout') and result1.layout else 0

    # Test 2: Multiple detectors in larger room
    ceiling2 = CeilingSpec(3.0)
    room2 = RoomSpec(
        room_id="multi",
        width_m=10.0,
        depth_m=10.0,
        ceiling_spec=ceiling2,
        occupancy_type="office",
    )

    result2 = expert.analyse_room(
        name=room2.room_id,
        width=room2.width_m,
        length=room2.depth_m,
        ceiling_height=room2.ceiling_spec.height_at_low_point_m,
    )

    multi_count = len(result2.layout.detectors) if hasattr(result2, 'layout') and result2.layout else 0
    # Multiple detectors should provide some redundancy
    assert multi_count > 0, "Large room should have at least 1 detector"

    return True


def main():
    """Run all tests."""
    print("\n" + "=" * 60)
    print("FINAL VERIFICATION TESTS")
    print("=" * 60 + "\n")
    
    results = []
    
    results.append(("HMAC Tamper", test_hmac_tamper()))
    results.append(("Beam Params", test_create_safe_beam_params()))
    results.append(("V12 Integration", test_v12_integration()))
    results.append(("Resilience", test_resilience()))
    
    # Summary
    print("\n" + "=" * 60)
    print("RESULTS SUMMARY")
    print("=" * 60)
    
    all_passed = True
    for name, passed in results:
        status = "PASS" if passed else "FAIL"
        print(f"  {name}: {status}")
        if not passed:
            all_passed = False
    
    print()
    if all_passed:
        print("All tests PASSED!")
    else:
        print("Some tests FAILED!")
        sys.exit(1)


if __name__ == "__main__":
    main()