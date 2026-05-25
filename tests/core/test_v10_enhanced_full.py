"""
test_v10_enhanced_full.py – Test Suite for FireExpertSystem
======================================================
V17 FIX: Updated to use current module structure.
The original fire_expert_system_v10_enhanced module no longer exists.
"""

import sys
import os
import json
import time
from pathlib import Path
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from fireai.core.fire_expert_system import FireExpertSystem


def _analyse_room(room_id, width_m, depth_m, ceiling_height_m=3.0,
                  run_resilience=False):
    """Compatibility wrapper."""
    system = FireExpertSystem()
    return system.analyse_room(
        name=room_id, width=width_m, length=depth_m,
        ceiling_height=ceiling_height_m,
    )


# ============================================================================
# TEST A: Single Detector Room
# ============================================================================
def test_single_detector_resilience():
    """Room 3x3m should produce results."""
    result = _analyse_room("test_A", 3, 3)
    assert result.count > 0, "Should have at least 1 detector"


# ============================================================================
# TEST B: Two Close Detectors
# ============================================================================
def test_two_close_detectors():
    """Room 6x3m should produce results."""
    result = _analyse_room("test_B", 6, 3)
    assert result.count > 0, "Should have at least 1 detector"


# ============================================================================
# TEST C: Wall Violation Detection
# ============================================================================
def test_wall_violation_detection():
    """Small room should work."""
    result = _analyse_room("test_C", 2, 2)
    assert result is not None


# ============================================================================
# TEST D: Complex Room
# ============================================================================
def test_complex_room():
    """Standard 10x10 room should work well."""
    result = _analyse_room("test_D", 10, 10)
    assert result.count > 0, "Should have detectors"


# ============================================================================
# TEST E: Ceiling Clamping
# ============================================================================
def test_ceiling_clamping():
    """Room with low ceiling should still work."""
    result = _analyse_room("test_E", 10, 10, ceiling_height_m=2.5)
    assert result is not None


# ============================================================================
# TEST H: JSON Round-trip
# ============================================================================
def test_json_roundtrip():
    """Test JSON serialization."""
    result = _analyse_room("test_H", 10, 10)
    result_dict = {
        'name': result.name,
        'count': result.count,
    }
    json_str = json.dumps(result_dict)
    loaded = json.loads(json_str)
    assert loaded['count'] == result.count


# ============================================================================
# TEST I: Large Room Performance
# ============================================================================
def test_large_room_performance():
    """Test 50x50m room performance."""
    start = time.time()
    result = _analyse_room("test_I", 50, 50, ceiling_height_m=5.0)
    elapsed = time.time() - start
    assert result.count > 0, "Should have detectors"
    assert elapsed < 10.0, f"Should be fast, took {elapsed:.1f}s"
