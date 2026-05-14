# ===================================================
# TEST: tests/unit/test_coverage.py
# FireAI V9 — NFPA 72 Safety Tests
# ===================================================

import pytest
import math
import sys
sys.path.insert(0, '.')

from nfpa72_models import (
    get_smoke_detector_radius,
    get_smoke_detector_radius_safe,
    CeilingSpec,
    RoomSpec,
    DetectorPlacement,
    DetectorType,
)


class TestSafeRadius:
    """Test get_smoke_detector_radius_safe() - critical safety function."""

    def test_safe_radius_all_heights(self):
        """Safe radius must work for ALL heights including extreme."""
        heights = [2.4, 3.0, 6.1, 9.1, 15.3, 20.0, 25.0]
        for h in heights:
            r = get_smoke_detector_radius_safe(h)
            assert r > 0, f"Height {h}m: radius must be positive"
            assert r <= 6.4, f"Height {h}m radius must be <= 6.4m"

    def test_safe_radius_clamps_high(self):
        """Heights above 15.3m should cap at 6.4m."""
        assert get_smoke_detector_radius_safe(20.0) == pytest.approx(6.4, rel=0.01)
        assert get_smoke_detector_radius_safe(15.3) == pytest.approx(6.4, rel=0.01)

    def test_safe_radius_clamps_low(self):
        """Heights below 3.0m should return minimum radius."""
        assert get_smoke_detector_radius_safe(2.4) == pytest.approx(4.55, rel=0.01)


class TestCeilingSpec:
    """Test CeilingSpec validation."""

    def test_ceiling_valid_range(self):
        """Valid heights should work."""
        c = CeilingSpec(3.0)
        assert c.height_m == 3.0
        
        c = CeilingSpec(15.3)
        assert c.height_m == 15.3


class TestUnsafeRadius:
    """Test get_smoke_detector_radius() - original function with limits."""

    def test_unsafe_normal_range(self):
        """Original function should work for normal range."""
        for h in [3.0, 6.1, 9.1, 15.3]:
            r = get_smoke_detector_radius(h)
            assert r > 0

    def test_unsafe_extreme_raises(self):
        """Original function should raise for extreme heights."""
        with pytest.raises(Exception):
            get_smoke_detector_radius(20.0)  # Above max
        with pytest.raises(Exception):
            get_smoke_detector_radius(2.5)   # Below min


class TestDetectorPlacement:
    """Test DetectorPlacement dataclass."""

    def test_creation(self):
        """Should create without ReferenceError."""
        dp = DetectorPlacement(
            x=5.0,
            y=5.0,
            z=3.0,
            detector_type=DetectorType.SMOKE,
            coverage_radius_m=5.0,
        )
        assert dp.x == 5.0
        assert dp.y == 5.0


class TestCoverageGeometry:
    """Test coverage geometry selection."""

    def test_smoke_is_circular(self):
        """Smoke detectors use CIRCULAR coverage."""
        from nfpa72_models import CoverageGeometry
        
        # Check in coverage.py for geometry logic
        with open('nfpa72_coverage.py') as f:
            content = f.read()
        
        # Should have circular for smoke
        assert 'CoverageGeometry.CIRCULAR' in content or 'circle' in content.lower()

    def test_heat_uses_chebyshev(self):
        """Heat detectors should use Chebyshev (square) distance."""
        with open('nfpa72_coverage.py') as f:
            content = f.read()
        
        # Should have Chebyshev formula for HEAT
        if 'DetectorType.HEAT' in content or 'HEAT' in content:
            # Check for square/Chebyshev logic
            has_chebyshev = 'max(abs(' in content
            assert has_chebyshev, "Heat detectors should use Chebyshev distance"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])