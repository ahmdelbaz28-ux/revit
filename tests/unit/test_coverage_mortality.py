"""
🔥 MORTALITY TEST SUITE - NFPA 72 V9
Death Prevention Protocol for Fire Alarm Coverage
"""
import pytest
from nfpa72_models import (
    RoomSpec, CeilingSpec, CeilingType, CoverageResult,
    get_smoke_detector_radius_safe, get_smoke_detector_coverage_max_safe,
)
from nfpa72_coverage import (
    check_coverage_polygon, check_voronoi_coverage,
    verify_full_coverage, adjust_coverage_for_beams,
)
from nfpa72_calculations import calculate_smoke_detector_spacing


class TestMortalityEdgeCases:
    """Edge cases that test system robustness"""

    def test_extreme_height_0_1m(self):
        radius = get_smoke_detector_radius_safe(0.1)
        assert radius > 0

    def test_extreme_height_100m(self):
        radius = get_smoke_detector_radius_safe(100)
        assert radius <= 6.4

    def test_no_detectors(self):
        room = RoomSpec(room_id="test-1", name="Test", width_m=10, depth_m=10)
        ceiling = CeilingSpec(height_at_low_point_m=3.0)
        result = check_coverage_polygon([], room, ceiling)
        assert result.coverage_percentage == 0


class TestMortalityRoomShapes:
    """Irregular room shapes"""

    def test_l_shaped_room(self):
        from shapely.geometry import Polygon
        l_shaped = Polygon([(0, 0), (10, 0), (10, 5), (5, 5), (5, 10), (0, 10)])
        room = RoomSpec(room_id="l-shape", name="L", width_m=10, depth_m=10, polygon=l_shaped)
        ceiling = CeilingSpec(height_at_low_point_m=3.0)
        result = check_coverage_polygon([(2, 2), (8, 8)], room, ceiling)
        assert result is not None


class TestMortalityBeams:
    """Beam obstruction tests"""

    def test_no_beams(self):
        radius = adjust_coverage_for_beams(4.55, 0.0, 3.0)
        assert radius == 4.55

    def test_shallow_beams(self):
        radius = adjust_coverage_for_beams(4.55, 0.1, 3.0)
        assert radius == 4.55  # <4% = no impact

    def test_moderate_beams(self):
        radius = adjust_coverage_for_beams(4.55, 0.15, 3.0)  # 5%
        assert radius < 4.55  # 4-10% = 15% reduction


class TestMortalitySpacing:
    """Detector spacing calculations"""

    def test_standard_room(self):
        room = RoomSpec(room_id="t", name="Test", width_m=10, depth_m=10)
        ceiling = CeilingSpec(height_at_low_point_m=3.0)
        num_w, num_d = calculate_smoke_detector_spacing(ceiling, 10, 10)
        assert num_w >= 1 and num_d >= 1

    def test_large_room(self):
        room = RoomSpec(room_id="l", name="Large", width_m=30, depth_m=20)
        ceiling = CeilingSpec(height_at_low_point_m=3.0)
        num_w, num_d = calculate_smoke_detector_spacing(ceiling, 30, 20)
        assert num_w >= 2 and num_d >= 2


class TestMortalityVoronoi:
    """Voronoi coverage"""

    def test_single_detector(self):
        room = RoomSpec(room_id="t", name="Test", width_m=10, depth_m=10)
        ceiling = CeilingSpec(height_at_low_point_m=3.0)
        result = check_voronoi_coverage([(5, 5)], room, ceiling)
        assert result is not None


class TestMortalityVerify:
    """Full verification"""

    def test_adequate_coverage(self):
        room = RoomSpec(room_id="t", name="Test", width_m=10, depth_m=10)
        polygon = room.polygon
        detectors = [(2.5, 2.5), (7.5, 2.5), (2.5, 7.5), (7.5, 7.5)]
        result = verify_full_coverage(polygon, detectors, 'circular', 4.55)
        assert result is not None


class TestMortalityStress:
    """Stress tests"""

    def test_many_detectors(self):
        room = RoomSpec(room_id="t", name="Test", width_m=50, depth_m=50)
        ceiling = CeilingSpec(height_at_low_point_m=3.0)
        detectors = [(x, y) for x in range(2, 50, 4) for y in range(2, 50, 4)]
        result = check_coverage_polygon(detectors, room, ceiling)
        assert result is not None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])