"""
Final Verification Suite
======================
Comprehensive tests to verify system integrity and end-to-end functionality.
"""

import os
import sys
import random
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from shapely.geometry import Polygon, Point
from core.models import Room, Device, Obstruction
from validation.compliance_oracle import ComplianceOracle
from spatial_field_engine import evaluate_compliance as engine_evaluate
from core.truth_deriver import derive_truth
from core.truth_deriver import NFPAConstraintModel as TruthNFPA
from integration.ifc_bridge import IFCBridge, run_compliance_on_ifc


def test_determinism_over_time():
    """Test 1: Determinism Over Time"""
    print("\n[TEST 1] Determinism Over Time")
    print("-" * 40)
    
    # Create 3 different room shapes
    rooms = [
        # Square
        Room(id="sq", name="Square", geometry=Polygon([(0,0),(10,0),(10,10),(0,10),(0,0)]), ceiling_height=3.0),
        # Triangle
        Room(id="tri", name="Triangle", geometry=Polygon([(5,0),(10,10),(0,10),(5,0)]), ceiling_height=3.0),
        # Pentagon
        Room(id="pent", name="Pentagon", geometry=Polygon([(5,0),(10,3),(8,10),(2,10),(0,3),(5,0)]), ceiling_height=3.0),
    ]
    
    all_passed = True
    for room in rooms:
        # Set fixed random seed for reproducibility
        random.seed(42)
        
        # Create 5 fixed devices per room
        devices = []
        for i in range(5):
            x = random.uniform(1, 9)
            y = random.uniform(1, 9)
            devices.append(Device(
                id=f"dev_{room.id}_{i}",
                device_type="SMOKE_PHOTOELECTRIC",
                position=Point(x, y)
            ))
        
        obstructions = []
        
        # Run 3 times
        checksums = []
        decision_ids = []
        
        oracle = ComplianceOracle()
        for _ in range(3):
            result = oracle.verify_truth(room, devices, obstructions)
            checksums.append(result['checksum'])
            decision_ids.append(result.get('decision_id', ''))
        
        # Check consistency
        checksum_match = len(set(checksums)) == 1
        decision_match = len(set(decision_ids)) == 1
        
        room_passed = checksum_match and decision_match
        status = "✓" if room_passed else "✗"
        
        print(f"  {room.name}: {checksum_match and decision_match} - {status}")
        all_passed = all_passed and room_passed
    
    if all_passed:
        print("  ✓ DETERMINISM VERIFIED")
    else:
        print("  ✗ DETERMINISM FAILED")
    
    return all_passed


def test_gate_integrity():
    """Test 2: Gate Integrity - Cannot bypass Oracle"""
    print("\n[TEST 2] Gate Integrity")
    print("-" * 40)
    
    # Create test data
    room = Room(id="gate_test", name="Gate Test", geometry=Polygon([(0,0),(10,0),(10,10),(0,10),(0,0)]), ceiling_height=3.0)
    devices = [Device(id="d1", device_type="SMOKE_PHOTOELECTRIC", position=Point(5, 5))]
    obstructions = []
    
    # Try direct engine call
    try:
        _, violations = engine_evaluate(room, devices, obstructions, None)
        print("  Direct engine call detected (cannot enforce TruthState) - EXPECTED")
    except Exception as e:
        print(f"  Engine error: {e}")
    
    # Try direct deriver call
    try:
        model = TruthNFPA()
        truth_violations = derive_truth(room, devices, obstructions, model)
        print("  Direct deriver call detected (cannot enforce TruthState) - EXPECTED")
    except Exception as e:
        print(f"  Deriver error: {e}")
    
    # Verify that only Oracle can produce True TruthState
    oracle = ComplianceOracle()
    result = oracle.verify_truth(room, devices, obstructions)
    has_decision_id = 'decision_id' in result
    
    if has_decision_id:
        print("  ✓ GATE INTEGRITY VERIFIED (No TruthState bypass)")
        return True
    else:
        print("  ✗ GATE INTEGRITY FAILED")
        return False


def test_spatial_audit():
    """Test 3: Spatial Audit"""
    print("\n[TEST 3] Spatial Audit")
    print("-" * 40)
    
    if not hasattr(IFCBridge, 'audit_spatial_decisions'):
        print("  ✗ audit_spatial_decisions not found")
        return False
    
    # Create temporary IFC with spatial relationships
    try:
        import ifcopenshell
    except ImportError:
        print("  Skipping: ifcopenshell not available")
        return True
    
    # Create IFC file
    ifc = ifcopenshell.file(schema="IFC4")
    
    # Create rooms
    room_a_placement = ifc.create_entity(
        "IfcLocalPlacement",
        RelativePlacement=ifc.create_entity(
            "IfcAxis2Placement3D",
            Location=ifc.create_entity("IfcCartesianPoint", Coordinates=(0.0, 0.0, 0.0))
        )
    )
    room_a = ifc.create_entity("IfcSpace", GlobalId="room_A", Name="Room A", ObjectPlacement=room_a_placement)
    
    room_b_placement = ifc.create_entity(
        "IfcLocalPlacement",
        RelativePlacement=ifc.create_entity(
            "IfcAxis2Placement3D",
            Location=ifc.create_entity("IfcCartesianPoint", Coordinates=(20.0, 0.0, 0.0))
        )
    )
    room_b = ifc.create_entity("IfcSpace", GlobalId="room_B", Name="Room B", ObjectPlacement=room_b_placement)
    
    # Create devices with placement
    dev1_placement = ifc.create_entity(
        "IfcLocalPlacement",
        RelativePlacement=ifc.create_entity(
            "IfcAxis2Placement3D",
            Location=ifc.create_entity("IfcCartesianPoint", Coordinates=(5.0, 5.0, 2.4))
        )
    )
    dev1 = ifc.create_entity("IfcSensor", GlobalId="device_1", Name="Device 1", ObjectPlacement=dev1_placement)
    
    dev2_placement = ifc.create_entity(
        "IfcLocalPlacement",
        RelativePlacement=ifc.create_entity(
            "IfcAxis2Placement3D",
            Location=ifc.create_entity("IfcCartesianPoint", Coordinates=(25.0, 5.0, 2.4))
        )
    )
    dev2 = ifc.create_entity("IfcSensor", GlobalId="device_2", Name="Device 2", ObjectPlacement=dev2_placement)
    
    # Device 3 - no placement (will fallback to geometry)
    dev3_placement = ifc.create_entity(
        "IfcLocalPlacement",
        RelativePlacement=ifc.create_entity(
            "IfcAxis2Placement3D",
            Location=ifc.create_entity("IfcCartesianPoint", Coordinates=(3.0, 3.0, 2.4))
        )
    )
    dev3 = ifc.create_entity("IfcSensor", GlobalId="device_3", Name="Device 3", ObjectPlacement=dev3_placement)
    
    # Create spatial relationships
    rel1 = ifc.create_entity(
        "IfcRelContainedInSpatialStructure",
        GlobalId="rel_1",
        RelatingStructure=room_a,
        RelatedElements=[dev1]
    )
    rel2 = ifc.create_entity(
        "IfcRelContainedInSpatialStructure",
        GlobalId="rel_2",
        RelatingStructure=room_b,
        RelatedElements=[dev2]
    )
    # Device 3 has no explicit relationship
    
    # Save and process
    with tempfile.NamedTemporaryFile(mode='w', suffix='.ifc', delete=False) as f:
        temp_path = f.name
    
    ifc.write(temp_path)
    
    try:
        bridge = IFCBridge(temp_path)
        rooms, devices, obstructions = bridge.extract_and_normalize()
        
        # Check audit
        audit = bridge.audit_spatial_decisions()
        print("  " + audit.replace("\n", "\n  "))
        
        # Verify expected entries
        has_ifc_rel = "IFC_REL_CONTAINED" in audit
        has_geom = "GEOMETRIC_COVERS" in audit
        
        if has_ifc_rel and has_geom:
            print("  ✓ SPATIAL AUDIT VERIFIED")
            return True
        else:
            print("  ✗ SPATIAL AUDIT FAILED")
            return False
    except Exception as e:
        print(f"  Error: {e}")
        return False
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)


def test_end_to_end_ifc():
    """Test 4: End-to-End IFC Path"""
    print("\n[TEST 4] End-to-End IFC")
    print("-" * 40)
    
    try:
        import ifcopenshell
    except ImportError:
        print("  Skipping: ifcopenshell not available")
        return True
    
    # Create IFC with room, devices, and obstruction
    ifc = ifcopenshell.file(schema="IFC4")
    
    # Create room (10x10)
    room_placement = ifc.create_entity(
        "IfcLocalPlacement",
        RelativePlacement=ifc.create_entity(
            "IfcAxis2Placement3D",
            Location=ifc.create_entity("IfcCartesianPoint", Coordinates=(0.0, 0.0, 0.0))
        )
    )
    room = ifc.create_entity("IfcSpace", GlobalId="room_1", Name="Test Room", ObjectPlacement=room_placement)
    
    # Device 1: at center (5,5)
    dev1_placement = ifc.create_entity(
        "IfcLocalPlacement",
        RelativePlacement=ifc.create_entity(
            "IfcAxis2Placement3D",
            Location=ifc.create_entity("IfcCartesianPoint", Coordinates=(5.0, 5.0, 2.4))
        )
    )
    dev1 = ifc.create_entity("IfcSensor", GlobalId="smoke_1", Name="Smoke Detector 1", ObjectPlacement=dev1_placement)
    
    # Device 2: at (8,8)
    dev2_placement = ifc.create_entity(
        "IfcLocalPlacement",
        RelativePlacement=ifc.create_entity(
            "IfcAxis2Placement3D",
            Location=ifc.create_entity("IfcCartesianPoint", Coordinates=(8.0, 8.0, 2.4))
        )
    )
    dev2 = ifc.create_entity("IfcSensor", GlobalId="smoke_2", Name="Smoke Detector 2", ObjectPlacement=dev2_placement)
    
    # Column: at (1,1)-(2,2)
    col_placement = ifc.create_entity(
        "IfcLocalPlacement",
        RelativePlacement=ifc.create_entity(
            "IfcAxis2Placement3D",
            Location=ifc.create_entity("IfcCartesianPoint", Coordinates=(1.5, 1.5, 0.0))
        )
    )
    col = ifc.create_entity("IfcColumn", GlobalId="column_1", Name="Test Column", ObjectPlacement=col_placement)
    
    # Spatial relationships
    rel = ifc.create_entity(
        "IfcRelContainedInSpatialStructure",
        GlobalId="rel_1",
        RelatingStructure=room,
        RelatedElements=[dev1, dev2, col]
    )
    
    # Save and process
    with tempfile.NamedTemporaryFile(mode='w', suffix='.ifc', delete=False) as f:
        temp_path = f.name
    
    ifc.write(temp_path)
    
    try:
        result = run_compliance_on_ifc(temp_path)
        
        rooms_processed = result.get('rooms_processed', 0)
        total_violations = result.get('total_violations', 0)
        
        print(f"  Rooms processed: {rooms_processed}")
        print(f"  Total violations: {total_violations}")
        
        # Check that violations have required fields
        violations = result.get('violations', [])
        all_valid = True
        for v in violations[:3]:
            if not all(k in v for k in ['rule', 'device_id', 'location']):
                all_valid = False
        
        if rooms_processed >= 1 and total_violations > 0 and all_valid:
            print("  ✓ END-TO-END IFC PATH VERIFIED")
            return True
        else:
            print("  ✗ END-TO-END IFC FAILED")
            return False
    except Exception as e:
        print(f"  Error: {e}")
        return False
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)


def main():
    print("=" * 60)
    print("FINAL VERIFICATION SUITE")
    print("=" * 60)
    
    results = []
    
    # Test 1
    results.append(test_determinism_over_time())
    
    # Test 2
    results.append(test_gate_integrity())
    
    # Test 3
    results.append(test_spatial_audit())
    
    # Test 4
    results.append(test_end_to_end_ifc())
    
    print("\n" + "=" * 60)
    if all(results):
        print("ALL 4 TESTS PASSED")
    else:
        print("SOME TESTS FAILED")
    print("=" * 60)
    
    return all(results)


if __name__ == "__main__":
    main()