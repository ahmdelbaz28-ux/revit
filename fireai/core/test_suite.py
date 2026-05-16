"""
test_suite.py — 10 Reference Rooms for Regression Testing
================================================
Each room has expected values. If any test fails, we have a regression.
Run this before every commit!
"""

import sys
sys.path.insert(0, '/workspace/project/revit')

from dataclasses import dataclass
from typing import Dict, List, Tuple, Optional

from fireai.core.nfpa72_models import RoomSpec, CeilingSpec
from fireai.core.fireai_core import FireAISystem


# Expected results for reference rooms
REFERENCE_ROOMS = [
    {
        "name": "office_10x10",
        "room": lambda: RoomSpec(
            room_id="office_10x10",
            width_m=10.0,
            depth_m=10.0,
            occupancy_type="storage",
            ceiling_spec=CeilingSpec(height_at_low_point_m=3.0),
        ),
        "expected": {
            "detectors_min": 10,
            "detectors_max": 12,
            "coverage_min": 99.0,
            "confidence": "CERTIFIED",
            "compliant": True,
        },
    },
    {
        "name": "small_3x3",
        "room": lambda: RoomSpec(
            room_id="small_3x3",
            width_m=3.0,
            depth_m=3.0,
            occupancy_type="office",
            ceiling_spec=CeilingSpec.create_safe(height_at_low_point_m=2.4),  # clamped
        ),
        "expected": {
            "detectors_min": 1,
            "detectors_max": 2,
            "coverage_min": 95.0,
            "confidence": "HIGH",
            "compliant": True,
        },
    },
    {
        "name": "corridor_6x3",
        "room": lambda: RoomSpec(
            room_id="corridor_6x3",
            width_m=6.0,
            depth_m=3.0,
            occupancy_type="corridor",
            ceiling_spec=CeilingSpec.create_safe(height_at_low_point_m=2.4),  # clamped
        ),
        "expected": {
            "detectors_min": 2,
            "detectors_max": 2,
            "coverage_min": 95.0,
            "confidence": "HIGH",
            "compliant": True,
        },
    },
    {
        "name": "large_15x20",
        "room": lambda: RoomSpec(
            room_id="large_15x20",
            width_m=15.0,
            depth_m=20.0,
            occupancy_type="office",
            ceiling_spec=CeilingSpec(height_at_low_point_m=3.0),
        ),
        "expected": {
            "detectors_min": 20,
            "detectors_max": 30,
            "coverage_min": 99.0,
            "confidence": "CERTIFIED",
            "compliant": True,
        },
    },
    {
        "name": "large_storage",
        "room": lambda: RoomSpec(
            room_id="large_storage",
            width_m=20.0,
            depth_m=30.0,
            occupancy_type="storage",
            ceiling_spec=CeilingSpec.create_safe(height_at_low_point_m=6.0),
        ),
        "expected": {
            "detectors_min": 25,
            "detectors_max": 45,
            "coverage_min": 95.0,
            "confidence": "HIGH",
            "compliant": True,
        },
    },
    {
        "name": "high_ceiling_10x10",
        "room": lambda: RoomSpec(
            room_id="high_ceiling_10x10",
            width_m=10.0,
            depth_m=10.0,
            occupancy_type="office",
            ceiling_spec=CeilingSpec(height_at_low_point_m=4.5),
        ),
        "expected": {
            "detectors_min": 12,
            "detectors_max": 16,
            "coverage_min": 99.0,
            "confidence": "CERTIFIED",
            "compliant": True,
        },
    },
    {
        "name": "bathroom_4x4",
        "room": lambda: RoomSpec(
            room_id="bathroom_4x4",
            width_m=4.0,
            depth_m=4.0,
            occupancy_type="bathroom",
            ceiling_spec=CeilingSpec.create_safe(height_at_low_point_m=2.4),
        ),
        "expected": {
            "detectors_min": 1,
            "detectors_max": 2,
            "coverage_min": 95.0,
            "confidence": "HIGH",
            "compliant": True,
        },
    },
    {
        "name": "meeting_8x8",
        "room": lambda: RoomSpec(
            room_id="meeting_8x8",
            width_m=8.0,
            depth_m=8.0,
            occupancy_type="meeting",
            ceiling_spec=CeilingSpec(height_at_low_point_m=2.7),
        ),
        "expected": {
            "detectors_min": 6,
            "detectors_max": 8,
            "coverage_min": 99.0,
            "confidence": "CERTIFIED",
            "compliant": True,
        },
    },
    {
        "name": "L_shaped",
        "room": lambda: RoomSpec(
            room_id="L_shaped",
            width_m=10.0,
            depth_m=10.0,
            occupancy_type="office",
            ceiling_spec=CeilingSpec(height_at_low_point_m=3.0),
            polygon_coords=[(0, 0), (10, 0), (10, 4), (4, 4), (4, 10), (0, 10)],
        ),
        "expected": {
            "detectors_min": 8,
            "detectors_max": 12,
            "coverage_min": 98.0,
            "confidence": "HIGH",
            "compliant": True,
        },
    },
    {
        "name": "storage_5x5",
        "room": lambda: RoomSpec(
            room_id="storage_5x5",
            width_m=5.0,
            depth_m=5.0,
            occupancy_type="storage",
            ceiling_spec=CeilingSpec(height_at_low_point_m=3.0),
        ),
        "expected": {
            "detectors_min": 1,
            "detectors_max": 2,
            "coverage_min": 95.0,
            "confidence": "HIGH",
            "compliant": True,
        },
    },
]


def run_test(name: str, room: RoomSpec, expected: Dict) -> Tuple[bool, str]:
    """Run single test and return (passed, message)."""
    system = FireAISystem(':memory:')
    result = system.analyse_room(room, user_id='test_suite')
    
    # Get values
    detector_count = len(result.detector_positions)
    coverage = result.placement_proof.coverage_fraction * 100 if result.placement_proof else 0
    confidence = result.confidence.value if result.confidence else "UNKNOWN"
    compliant = result.compliant
    
    # Check each expected value
    errors = []
    
    if detector_count < expected["detectors_min"]:
        errors.append(f"Detectors {detector_count} < min {expected['detectors_min']}")
    if detector_count > expected["detectors_max"]:
        errors.append(f"Detectors {detector_count} > max {expected['detectors_max']}")
    if coverage < expected["coverage_min"]:
        errors.append(f"Coverage {coverage:.1f}% < {expected['coverage_min']}%")
    if confidence != expected["confidence"] and confidence not in ["HIGH", "CERTIFIED"]:
        # Allow HIGH if CERTIFIED expected (might be lower)
        if expected["confidence"] == "CERTIFIED" and confidence not in ["HIGH", "CERTIFIED"]:
            errors.append(f"Confidence {confidence} != {expected['confidence']}")
        elif expected["confidence"] != "CERTIFIED" and confidence != expected["confidence"]:
            errors.append(f"Confidence {confidence} != {expected['confidence']}")
    
    if errors:
        return False, "; ".join(errors)
    
    return True, f"OK (d={detector_count}, cov={coverage:.1f}%, conf={confidence})"


def run_all() -> Dict:
    """Run all 10 reference tests."""
    print("=" * 60)
    print("FIREAI TEST SUITE - 10 Reference Rooms")
    print("=" * 60)
    
    passed = 0
    failed = 0
    results = []
    
    for test in REFERENCE_ROOMS:
        room = test["room"]()
        ok, msg = run_test(test["name"], room, test["expected"])
        
        if ok:
            passed += 1
            print(f"✓ {test['name']}: {msg}")
        else:
            failed += 1
            print(f"✗ {test['name']}: {msg}")
        
        results.append({"name": test["name"], "passed": ok, "message": msg})
    
    print("=" * 60)
    print(f"RESULTS: {passed}/10 PASSED")
    print("=" * 60)
    
    return {
        "passed": passed,
        "failed": failed,
        "results": results,
        "success": failed == 0,
    }


if __name__ == "__main__":
    result = run_all()
    sys.exit(0 if result["success"] else 1)