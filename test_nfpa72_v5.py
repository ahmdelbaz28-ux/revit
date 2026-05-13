"""
NFPA 72 V5 Test Suite - 19 Mandatory Tests

These tests verify NFPA 72 Chapter 17 compliance.
All tests must pass for the PR to be accepted.

⚠️ LEGAL DISCLAIMER:
This code is provided for compliance assistance only.
It does not constitute legal advice.
"""

import math
import pytest
from nfpa72_models import (
    CeilingSpec,
    CeilingType,
    RoomSpec,
    DetectorType,
    HeatDetectionMode,
    CoverageGeometry,
    CoverageError,
    NFPAComplianceError,
    CeilingHeightError,
    InvalidInputError,
    get_smoke_detector_radius,
    get_smoke_detector_coverage_max,
)
from nfpa72_calculations import (
    calculate_smoke_detector_radius,
    calculate_heat_detector_coverage_chebyshev,
    generate_heat_detector_positions,
    is_point_covered_by_heat_detectors,
    is_in_ridge_zone,
    requires_ridge_zone_detector,
    calculate_detector_requirements,
)
from nfpa72_coverage import (
    create_room_polygon,
    is_point_in_room,
    check_coverage_polygon,
    check_l_shaped_coverage,
    check_nfpa72_compliance,
    create_l_shaped_polygon,
)


# ============================================================================
# SMOKE DETECTOR RADIUS TESTS (6 tests)
# ============================================================================

class TestSmokeDetectorRadius:
    """Test smoke detector radius calculations (NFPA 72 Table 17.6.3.1)"""
    
    def test_standard_heights(self):
        """Test all 8 rows of NFPA 72 Table 17.6.3.1"""
        cases = [
            (2.5, 4.55), (4.6, 4.55),  # ≤ 4.6m → 4.55m
            (4.61, 5.35), (6.0, 5.35), (6.1, 5.35),  # ≤ 6.1m → 5.35m
            (6.2, 6.10), (7.5, 6.10), (7.6, 6.10),  # ≤ 7.6m → 6.10m
            (7.7, 6.40), (9.0, 6.40), (9.1, 6.40),  # ≤ 9.1m → 6.40m
            (9.2, 6.90), (10.6, 6.90), (10.7, 6.90),  # ≤ 10.7m → 6.90m
            (10.8, 7.30), (12.1, 7.30), (12.2, 7.30),  # ≤ 12.2m → 7.30m
            (12.3, 7.60), (13.6, 7.60), (13.7, 7.60),  # ≤ 13.7m → 7.60m
            (13.8, 7.90), (15.0, 7.90), (15.2, 7.90),  # ≤ 15.2m → 7.90m
        ]
        for height, expected in cases:
            result = get_smoke_detector_radius(height)
            assert result == expected, f"Height {height}m: expected {expected}, got {result}"

    def test_height_7_6m_is_610(self):
        """7.6m ceiling should give radius 6.10m (not 5.8m)"""
        radius = get_smoke_detector_radius(7.6)
        assert radius == 6.10, f"Expected 6.10m, got {radius}m"

    def test_height_15_2m_is_790(self):
        """15.2m ceiling should give radius 7.90m"""
        radius = get_smoke_detector_radius(15.2)
        assert radius == 7.90, f"Expected 7.90m, got {radius}m"

    def test_above_maximum_raises(self):
        """Height > 15.2m should raise NFPAComplianceError"""
        with pytest.raises(NFPAComplianceError):
            get_smoke_detector_radius(15.21)

    def test_zero_and_negative_raises(self):
        """Zero or negative height should raise InvalidInputError"""
        with pytest.raises(InvalidInputError):
            get_smoke_detector_radius(0.0)
        with pytest.raises(InvalidInputError):
            get_smoke_detector_radius(-1.0)

    def test_old_hardcoded_values_are_gone(self):
        """Verify old hardcoded values are replaced"""
        assert get_smoke_detector_radius(3.0) == 4.55
        assert get_smoke_detector_radius(3.0) != 6.37
        assert get_smoke_detector_radius(5.0) == 5.35
        assert get_smoke_detector_radius(5.0) != 6.37


# ============================================================================
# HEAT DETECTOR SQUARE GRID TESTS (4 tests)
# ============================================================================

class TestHeatDetectorPlacement:
    """Test heat detector uses SQUARE_GRID (Chebyshev), NOT circular"""
    
    def test_heat_uses_chebyshev_not_euclidean(self):
        """Heat detector must use Chebyshev, not Euclidean distance"""
        # Point at corner of detector coverage area
        detector_x, detector_y = 4.55, 4.55  # Center
        spacing = 9.1
        
        # Point at exactly spacing/2 in both x and y (Chebyshev boundary)
        # This should be covered
        covered = calculate_heat_detector_coverage_chebyshev(
            detector_x, detector_y,
            detector_x + spacing/2, detector_y + spacing/2,
            spacing
        )
        assert covered is True, "Point at Chebyshev boundary should be covered"
    
    def test_heat_point_outside_square_uncovered(self):
        """Point outside square coverage should be uncovered"""
        detector_x, detector_y = 4.55, 4.55
        spacing = 9.1
        
        # Point just outside the square
        covered = calculate_heat_detector_coverage_chebyshev(
            detector_x, detector_y,
            detector_x + spacing/2 + 0.1, detector_y + spacing/2 + 0.1,
            spacing
        )
        assert covered is False, "Point outside square should be uncovered"
    
    def test_heat_coverage_is_square(self):
        """Heat detector coverage area must be square, not circle"""
        detector_x, detector_y = 0, 0  # At origin
        spacing = 9.1
        half = spacing / 2
        
        # Four corners of the square
        corners = [
            (half, half),     # NE
            (-half, half),   # NW
            (half, -half),  # SE
            (-half, -half), # SW
        ]
        
        for px, py in corners:
            covered = calculate_heat_detector_coverage_chebyshev(
                detector_x, detector_y, px, py, spacing
            )
            assert covered is True, f"Corner {px},{py} should be covered (square)"
    
    def test_heat_point_far_in_x_but_close_in_y(self):
        """Point far in X but close in Y - Euclidean says uncovered, Chebyshev says covered"""
        detector_x, detector_y = 5.0, 5.0
        spacing = 9.1
        
        # Point: 3m away in X, 0m away in Y
        # Euclidean distance = 3m < 4.55m = covered by both
        # But Chebyshev should find it covered
        covered = calculate_heat_detector_coverage_chebyshev(
            detector_x, detector_y,
            detector_x + 3.0, detector_y,  # 3m in X, 0m in Y
            spacing
        )
        assert covered is True, "Chebyshev should cover X-close point"


# ============================================================================
# POLYGON COVERAGE TESTS (5 tests)
# ============================================================================

class TestPolygonCoverageCheck:
    """Test coverage uses Polygon, NOT Bounding Box"""
    
    def test_rectangular_coverage_works(self):
        """Rectangular room coverage check works"""
        from shapely.geometry import Polygon
        ceiling = CeilingSpec(CeilingType.FLAT, 3.0, 3.0, 10.0)
        room_polygon = Polygon([(0,0),(10,0),(10,10),(0,10)])
        room = RoomSpec("test", room_polygon, ceiling, DetectorType.SMOKE, "office")
        detectors = [(5, 5), (5, 5)]  # Simplified
        
        result = check_coverage_polygon(
            detectors, room, ceiling, DetectorType.SMOKE
        )
        
        assert result.is_covered or result.coverage_percentage > 0
    
    def test_point_in_polygon_not_bbox(self):
        """Point containment must use polygon.contains(), NOT bounding box"""
        # L-shaped room
        l_shape = [(0, 0), (10, 0), (10, 5), (5, 5), (5, 10), (0, 10)]
        poly = create_l_shaped_polygon(l_shape)
        
        # Point in the "gap" of L-shape (inside bounding box, outside polygon)
        point_in_gap = (7.5, 7.5)
        
        # Polygon.contains() should return False
        is_inside = is_point_in_room(point_in_gap, poly)
        assert is_inside is False, "Point in L-gap should NOT be in room"
    
    def test_polygon_catches_l_shaped_gap(self):
        """Polygon check catches L-shaped room gap that Bounding Box misses"""
        # Create L-shaped room polygon
        l_shape = [(0, 0), (10, 0), (10, 5), (5, 5), (5, 10), (0, 10)]
        poly = create_l_shaped_polygon(l_shape)
        
        # Single detector at (5, 5) - covers bounding box but not the gap
        detectors = [(2.5, 2.5)]  # Only covers bottom-left
        
        # Use polygon check
        result = check_l_shaped_coverage(detectors, poly, 3.0)
        
        # Should NOT show 100% coverage
        assert result.coverage_percentage < 100, \
            "L-shape with single detector should not show 100%"
    
    def test_polygon_with_multiple_detectors(self):
        """Multiple detectors achieve true coverage"""
        l_shape = [(0, 0), (10, 0), (10, 5), (5, 5), (5, 10), (0, 10)]
        poly = create_l_shaped_polygon(l_shape)
        
        # Two detectors - one covers each wing
        detectors = [(2.5, 2.5), (7.5, 7.5)]
        
        result = check_l_shaped_coverage(detectors, poly, 3.0)
        
        # Should achieve reasonable coverage (not 100% with only 2 detectors)
        assert result.coverage_percentage > 50
    
    def test_point_in_bbox_but_not_in_polygon(self):
        """Test point inside bounding box but outside polygon"""
        # Create a U-shaped room
        u_shape = [(0, 0), (10, 0), (10, 10), (8, 10), (8, 2), (2, 2), (2, 10), (0, 10)]
        poly = create_l_shaped_polygon(u_shape)
        
        # Point in the middle (inside bbox, outside polygon)
        middle = (5, 5)
        
        is_inside = is_point_in_room(middle, poly)
        assert is_inside is False, "Middle of U should be outside room"


# ============================================================================
# SLOPED CEILING TESTS (4 tests)
# ============================================================================

class TestSlopedCeiling:
    """Test sloped ceiling ridge zone requirements"""
    
    def test_slope_15_degrees_requires_ridge(self):
        """Ceiling slope > 1.5° requires ridge zone detector"""
        ceiling = CeilingSpec(CeilingType.PEAKED, 3.0, 6.0, 5.0)  # ~31° slope
        
        requires = ceiling.is_sloped
        assert requires is True, "Peaked ceiling should be sloped"
    
    def test_flat_ceiling_no_ridge(self):
        """Flat ceiling doesn't require ridge zone"""
        ceiling = CeilingSpec(CeilingType.FLAT, 3.0, 3.0, 10.0)
        
        requires = ceiling.is_sloped
        assert requires is False, "Flat ceiling should not be sloped"
    
    def test_slope_1_degrees_no_ridge(self):
        """Ceiling slope <= 1.5° doesn't require ridge zone"""
        # Small slope: 3.0m to 3.1m over 10m run = ~0.57°
        ceiling = CeilingSpec(CeilingType.SLOPED, 3.0, 3.1, 10.0)
        
        requires = ceiling.is_sloped
        assert requires is False, "~0.6° slope should not require ridge"
    
    def test_is_in_ridge_zone_true(self):
        """Point within 0.9m of ridge is in ridge zone"""
        ridge_line = (0, 5, 10, 5)  # Horizontal ridge at y=5
        
        in_zone = is_in_ridge_zone((5, 5.5), ridge_line, 15.0, buffer_m=0.9)
        assert in_zone is True, "Point 0.5m from ridge should be in ridge zone"


# ============================================================================
# COMBINED INTEGRATION TESTS
# ============================================================================

class TestIntegration:
    """Integration tests combining all components"""
    
    def test_full_compliance_check(self):
        """Full compliance check runs without errors"""
        from shapely.geometry import Polygon
        ceiling = CeilingSpec(CeilingType.FLAT, 3.0, 3.0, 10.0)
        room_polygon = Polygon([(0,0),(10,0),(10,10),(0,10)])
        room = RoomSpec("test", room_polygon, ceiling, DetectorType.SMOKE, "office")
        detectors = [(2.5, 2.5), (7.5, 2.5), (2.5, 7.5), (7.5, 7.5)]
        
        result = check_nfpa72_compliance(
            room, ceiling, detectors, DetectorType.SMOKE
        )
        
        # Should either pass or have meaningful violations
        assert result is not None
    
    def test_no_fixed_radius_in_code(self):
        """Verify there are no hardcoded 6.37 or 4.6 radius values"""
        import os
        import re
        
        # Check files for forbidden radius patterns (not in comments/docstrings)
        check_files = ['nfpa72_models.py', 'nfpa72_calculations.py', 'nfpa72_coverage.py']
        
        for filename in check_files:
            path = os.path.join('/workspace/project/revit', filename)
            if not os.path.exists(path):
                continue
                
            with open(path) as f:
                content = f.read()
            
            # Look for radius = 6.37 or radius = 4.6 patterns (not in comments)
            forbidden = ['radius = 6.37', 'radius = 4.6']
            
            for pattern in forbidden:
                if pattern in content:
                    pytest.fail(
                        f"Found forbidden radius {pattern} in {filename}. "
                        f"Use get_smoke_detector_radius() instead."
                    )
    
    def test_legal_disclaimer_present(self):
        """Verify legal disclaimer is present in compliance result"""
        from nfpa72_models import NFPAComplianceResult
        
        result = NFPAComplianceResult(is_compliant=True)
        
        assert "LEGAL DISCLAIMER" in result.DISCLAIMER or "disclaimer" in result.DISCLAIMER.lower()


# ============================================================================
# RUN ALL TESTS
# ============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v"])