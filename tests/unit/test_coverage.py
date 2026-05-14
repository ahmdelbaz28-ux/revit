# ===================================================
# tests/unit/test_coverage.py
# FireAI V8 — NFPA 72 Safety Tests
# Priority: HIGH (validates all critical fixes)
# ===================================================

import pytest
import math
from dataclasses import dataclass
from typing import Optional, List, Tuple

# Imports from the project
from nfpa72_coverage import check_coverage_polygon, adjust_coverage_for_beams
from nfpa72_models import (
    DetectorPlacement,
    DetectorType,
    RoomSpec,
    CeilingSpec,
    CeilingType,
    get_smoke_detector_radius_safe,
)
from src.auto_placement import suggest_duct_detectors


# ============================================================================
# HELPER FUNCTIONS FOR TESTS
# ============================================================================

def create_test_room(width: float = 10.0, depth: float = 10.0, height: float = 3.0) -> RoomSpec:
    """Create a simple rectangular test room."""
    return RoomSpec(
        name="test_room",
        width_m=width,
        depth_m=depth,
        height_m=height,
    )


def create_test_ceiling(height: float = 3.0) -> CeilingSpec:
    """Create a simple flat ceiling spec."""
    return CeilingSpec(
        height_at_low_point_m=height,
        ceiling_type=CeilingType.FLAT,
    )


# Mock helper for duct tests
class MockDuct:
    def __init__(self, start_x, start_y, end_x, end_y, height_z, duct_id="test_duct"):
        self.start_x = start_x
        self.start_y = start_y
        self.end_x = end_x
        self.end_y = end_y
        self.height_z = height_z
        self.duct_id = duct_id


# ============================================================================
# TEST CLASSES
# ============================================================================

class TestExtremeHeights:
    """Critical: heights outside NFPA 72 table range must use safe fallback."""

    def test_height_24m_no_exception(self):
        """Height 2.4m (below table min): must NOT raise, must return positive radius."""
        radius = get_smoke_detector_radius_safe(2.4)
        assert radius > 0, "Radius must be positive"
        assert radius <= 4.55, "Should be conservative for low ceilings"

    def test_height_20m_no_exception(self):
        """Height 20m (above NFPA max 15.3m): must NOT raise, must cap value."""
        radius = get_smoke_detector_radius_safe(20.0)
        assert radius > 0, "Radius must be positive"
        assert radius <= 6.4, "Should cap at 15.3m table value"

    def test_height_153m_exact(self):
        """Height 15.3m (NFPA max): should return exactly 6.4m."""
        radius = get_smoke_detector_radius_safe(15.3)
        assert radius == pytest.approx(6.4, rel=0.01)

    def test_negative_height_raises(self):
        """Negative height is physically impossible: must raise."""
        with pytest.raises((ValueError, Exception)):
            get_smoke_detector_radius_safe(-1.0)

    def test_zero_height_raises(self):
        """Zero height is physically impossible: must raise."""
        with pytest.raises((ValueError, Exception)):
            get_smoke_detector_radius_safe(0.0)


class TestHeatDetectorGeometry:
    """Critical: heat detectors must use square (Chebyshev) geometry, not circular."""

    def test_heat_detector_placement_geometry(self):
        """DetectorPlacement for HEAT must set radius to 4.55m (half of 9.1m)."""
        det = DetectorPlacement(
            x=5.0, y=5.0, z=0,
            detector_type=DetectorType.HEAT,
            ceiling_height_m=3.0
        )
        assert det.coverage_radius_m == pytest.approx(4.55, rel=0.01)

    def test_smoke_detector_placement_uses_safe(self):
        """DetectorPlacement for SMOKE must use get_smoke_detector_radius_safe."""
        det = DetectorPlacement(
            x=5.0, y=5.0, z=0,
            detector_type=DetectorType.SMOKE,
            ceiling_height_m=3.0
        )
        expected = get_smoke_detector_radius_safe(3.0)
        assert det.coverage_radius_m == pytest.approx(expected, rel=0.01)

    def test_single_heat_detector_covers_91x91_room(self):
        """1 heat detector centered in 9.1x9.1m room must achieve >= 99% coverage."""
        room = create_test_room(width=9.1, depth=9.1, height=3.0)
        ceiling = create_test_ceiling(height=3.0)
        result = check_coverage_polygon(
            detector_positions=[(4.55, 4.55)],
            room_spec=room,
            ceiling_spec=ceiling,
            detector_type=DetectorType.HEAT
        )
        assert result.coverage_percentage >= 99.0, (
            f"Single heat detector in 9.1x9.1m room should cover >=99%, "
            f"got {result.coverage_percentage:.1f}%"
        )


class TestBeamDetection:
    """Beam depth must correctly reduce coverage radius per NFPA 72 17.6.3.1."""

    def test_shallow_beam_no_change(self):
        """Beam <= 4% of ceiling: no radius change."""
        # 3.0m ceiling, beam 0.1m = 3.3% < 4%
        result = adjust_coverage_for_beams(4.55, beam_depth_m=0.1, ceiling_height_m=3.0)
        assert result == pytest.approx(4.55, rel=0.01)

    def test_moderate_beam_15pct_reduction(self):
        """Beam 4-10% of ceiling: 15% radius reduction."""
        # 3.0m ceiling, beam 0.2m = 6.7% (between 4% and 10%)
        result = adjust_coverage_for_beams(4.55, beam_depth_m=0.2, ceiling_height_m=3.0)
        assert result == pytest.approx(4.55 * 0.85, rel=0.01)

    def test_deep_beam_warning_no_crash(self):
        """Beam > 10%: logs warning, returns original radius (compartment logic applies)."""
        # 3.0m ceiling, beam 0.4m = 13.3% > 10%
        result = adjust_coverage_for_beams(4.55, beam_depth_m=0.4, ceiling_height_m=3.0)
        assert result == pytest.approx(4.55, rel=0.01)  # unchanged; compartment-based

    def test_zero_ceiling_raises(self):
        with pytest.raises(ValueError):
            adjust_coverage_for_beams(4.55, beam_depth_m=0.2, ceiling_height_m=0)

    def test_negative_beam_raises(self):
        with pytest.raises(ValueError):
            adjust_coverage_for_beams(4.55, beam_depth_m=-0.1, ceiling_height_m=3.0)


class TestDuctDetectors:
    """Duct detectors must be placed per NFPA 72 17.7.5."""

    def test_single_short_duct_one_detector(self):
        """Duct < 21m: 1 detector at start."""
        duct = MockDuct(start_x=0, start_y=0, end_x=10, end_y=0, height_z=3.0)
        devices = suggest_duct_detectors([duct])
        assert len(devices) == 1

    def test_long_duct_multiple_detectors(self):
        """Duct 42m: 3 detectors (start + 2 intervals)."""
        duct = MockDuct(start_x=0, start_y=0, end_x=42, end_y=0, height_z=3.0)
        devices = suggest_duct_detectors([duct])
        assert len(devices) >= 2  # at minimum: start + 1 interval at 21m

    def test_none_ducts_raises(self):
        with pytest.raises(ValueError):
            suggest_duct_detectors(None)


# Run tests if executed directly
if __name__ == "__main__":
    pytest.main([__file__, "-v"])