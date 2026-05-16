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
sys.path.insert(0, '/workspace/project/revit')

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
    """Test V12 integration works."""
    print("\n" + "=" * 60)
    print("TEST 3: V12 Integration")
    print("=" * 60)
    
    from fireai.core.nfpa72_models import CeilingSpec, CeilingType
    from fireai.core.fire_expert_system_v12 import (
        ExpertSystemV12, RoomSpec, ConfidenceLevel
    )
    
    ceiling_spec = CeilingSpec(3.0, 3.0, CeilingType.FLAT)
    room_spec = RoomSpec(
        room_id="test_v12",
        width_m=10.0,
        depth_m=10.0,
        ceiling_spec=ceiling_spec,
        occupancy_type="office",
    )
    
    expert = ExpertSystemV12()
    result = expert.analyse_room(
        room_spec=room_spec,
        run_resilience=True,
    )
    
    print(f"  Detectors: {len(result.detector_positions)}")
    print(f"  Confidence: {result.confidence}")
    print(f"  Errors: {result.errors}")
    
    if result.confidence == ConfidenceLevel.UNSAFE:
        print("  FAILED: Result is UNSAFE")
        return False
    
    if result.errors:
        print(f"  WARNING: Errors present: {result.errors}")
    
    print("  TEST 3: PASSED")
    return True


def test_resilience():
    """Test resilience checks."""
    print("\n" + "=" * 60)
    print("TEST 4: Resilience Checks")
    print("=" * 60)
    
    from fireai.core.nfpa72_models import CeilingSpec, CeilingType
    from fireai.core.fire_expert_system_v12 import ExpertSystemV12, RoomSpec
    
    # Test 1: Single detector
    ceiling1 = CeilingSpec(3.0, 3.0, CeilingType.FLAT)
    room1 = RoomSpec(
        room_id="single",
        width_m=3.0,
        depth_m=3.0,
        ceiling_spec=ceiling1,
        occupancy_type="corridor",
    )
    
    expert = ExpertSystemV12()
    result1 = expert.analyse_room(room_spec=room1, run_resilience=True)
    
    single_count = len(result1.detector_positions)
    resilient1 = result1.resilience.resilient if result1.resilience else True
    print(f"  Single detector ({single_count}): resilient={resilient1}")
    
    # Test 2: Multiple detectors
    ceiling2 = CeilingSpec(3.0, 3.0, CeilingType.FLAT)
    room2 = RoomSpec(
        room_id="multi",
        width_m=10.0,
        depth_m=10.0,
        ceiling_spec=ceiling2,
        occupancy_type="office",
    )
    
    result2 = expert.analyse_room(room_spec=room2, run_resilience=True)
    
    multi_count = len(result2.detector_positions)
    resilient2 = result2.resilience.resilient if result2.resilience else False
    print(f"  Multi detectors ({multi_count}): resilient={resilient2}")
    
    # Test 3: Skip resilience
    result3 = expert.analyse_room(room_spec=room2, run_resilience=False)
    has_resilience = result3.resilience is not None
    print(f"  Skip resilience: has_resilience={has_resilience} (expected False)")
    
    # Validate
    if single_count <= 1 and resilient1:
        print("  FAILED: Single detector should not be resilient")
        return False
    
    if multi_count > 1 and not resilient2:
        print("  FAILED: Multiple detectors should be resilient")
        return False
    
    if has_resilience:
        print("  FAILED: run_resilience=False should skip")
        return False
    
    print("  TEST 4: PASSED")
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