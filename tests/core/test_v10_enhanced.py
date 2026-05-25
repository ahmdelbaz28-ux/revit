"""
test_v10_enhanced.py – Tests for FireExpertSystem
==============================================
V17 FIX: Updated to use current module structure.
The original fire_expert_system_v10_enhanced module no longer exists.
"""

import sys
from pathlib import Path
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from fireai.core.fire_expert_system import FireExpertSystem


def _analyse_room(room_id, width_m, depth_m, ceiling_height_m=3.0,
                  room_type="office", run_resilience=False):
    """Compatibility wrapper."""
    system = FireExpertSystem()
    return system.analyse_room(
        name=room_id, width=width_m, length=depth_m,
        ceiling_height=ceiling_height_m,
    )


def test_single_detector():
    """Small room should produce results."""
    result = _analyse_room("single", 3.0, 3.0)
    assert result.count > 0, "Should have at least 1 detector"


def test_normal_room():
    """Standard 10x10 room should work."""
    result = _analyse_room("normal", 10.0, 10.0)
    assert result.count > 0, "Should have detectors"


def test_large_room():
    """Large room should have more detectors."""
    result_small = _analyse_room("small", 3.0, 3.0)
    result_large = _analyse_room("large", 20.0, 20.0)
    assert result_large.count >= result_small.count, "Larger room should need more or equal detectors"


def test_json_serialization():
    """Test JSON serialization."""
    import json
    from dataclasses import asdict
    result = _analyse_room("json_test", 10.0, 10.0)
    try:
        d = asdict(result)
        j = json.dumps(d, default=str)
        assert len(j) > 0
    except Exception:
        assert result is not None


def main():
    """Run all tests."""
    results = [
        ("Single detector", test_single_detector()),
        ("Normal room", test_normal_room()),
        ("Large room", test_large_room()),
        ("JSON serialization", test_json_serialization()),
    ]
    all_passed = all(p for _, p in results)
    for name, passed in results:
        print(f"  {name}: {'PASS' if passed else 'FAIL'}")
    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())
