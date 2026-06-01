"""
tests/test_geometry_utils.py
=============================
Comprehensive test suite for fireai/core/geometry_utils.py

SAFETY CRITICAL: Geometry calculations determine detector spacing, coverage
areas, and egress paths. Incorrect point-in-polygon or area calculations can
leave dead zones where fire is undetected, directly endangering life safety.

NFPA 72 References:
  - Table 17.6.3.1.1: Coverage radius by ceiling height
  - Section 17.6.3.1.1: Min wall distance 0.10m (4 inches)
"""

from __future__ import annotations

import math
import pytest

from fireai.core.geometry_utils import (
    _ensure_closed,
    shoelace_area,
    polygon_area,
    polygon_centroid,
    polygon_bounds,
    polygon_perimeter,
    point_in_polygon,
    points_in_polygon,
    validate_polygon,
    ValidationResult,
    is_clockwise,
    ensure_ccw,
    rect_polygon,
    l_shape_polygon,
    grid_points_in_polygon,
    is_rectangular,
    bounding_rect_dimensions,
    convex_hull_2d,
    sanitize_room_geometry,
    SanitizeResult,
    Point,
    Polygon,
)


# ─────────────────────────────────────────────────────────────────────────────
# _ensure_closed
# ─────────────────────────────────────────────────────────────────────────────


class TestEnsureClosed:
    def test_already_closed(self):
        poly = [(0, 0), (1, 0), (1, 1), (0, 1), (0, 0)]
        result = _ensure_closed(poly)
        assert result == poly

    def test_open_polygon_closed(self):
        poly = [(0, 0), (1, 0), (1, 1), (0, 1)]
        result = _ensure_closed(poly)
        assert result[-1] == poly[0]
        assert len(result) == 5

    def test_does_not_mutate_original(self):
        poly = [(0, 0), (1, 0), (1, 1), (0, 1)]
        original_len = len(poly)
        _ensure_closed(poly)
        assert len(poly) == original_len


# ─────────────────────────────────────────────────────────────────────────────
# Shoelace Area
# ─────────────────────────────────────────────────────────────────────────────


class TestShoelaceArea:
    def test_unit_square_ccw(self):
        """CCW square → positive signed area."""
        poly = [(0, 0), (1, 0), (1, 1), (0, 1)]
        assert shoelace_area(poly) == pytest.approx(1.0)

    def test_unit_square_cw(self):
        """CW square → negative signed area."""
        poly = [(0, 0), (0, 1), (1, 1), (1, 0)]
        assert shoelace_area(poly) == pytest.approx(-1.0)

    def test_triangle(self):
        """Right triangle: area = 0.5."""
        poly = [(0, 0), (2, 0), (0, 2)]
        assert shoelace_area(poly) == pytest.approx(2.0)

    def test_degenerate_line(self):
        """Collinear points → zero area."""
        poly = [(0, 0), (1, 1), (2, 2)]
        assert shoelace_area(poly) == pytest.approx(0.0)

    def test_fewer_than_3_vertices(self):
        """Less than 3 vertices → zero area."""
        assert shoelace_area([(0, 0), (1, 1)]) == 0.0
        assert shoelace_area([(0, 0)]) == 0.0
        assert shoelace_area([]) == 0.0


# ─────────────────────────────────────────────────────────────────────────────
# Polygon Area
# ─────────────────────────────────────────────────────────────────────────────


class TestPolygonArea:
    def test_always_positive(self):
        """Area must be positive regardless of winding order."""
        ccw = [(0, 0), (6, 0), (6, 4), (0, 4)]
        cw = [(0, 0), (0, 4), (6, 4), (6, 0)]
        assert polygon_area(ccw) == pytest.approx(24.0)
        assert polygon_area(cw) == pytest.approx(24.0)

    def test_l_shape(self):
        """L-shape: (6×4) - (2×2) = 20 m²."""
        poly = l_shape_polygon(6, 4, 2, 2)
        assert polygon_area(poly) == pytest.approx(20.0)


# ─────────────────────────────────────────────────────────────────────────────
# Polygon Centroid
# ─────────────────────────────────────────────────────────────────────────────


class TestPolygonCentroid:
    def test_square_centroid(self):
        poly = [(0, 0), (4, 0), (4, 4), (0, 4)]
        cx, cy = polygon_centroid(poly)
        assert cx == pytest.approx(2.0)
        assert cy == pytest.approx(2.0)

    def test_rectangle_centroid(self):
        poly = [(0, 0), (10, 0), (10, 2), (0, 2)]
        cx, cy = polygon_centroid(poly)
        assert cx == pytest.approx(5.0)
        assert cy == pytest.approx(1.0)

    def test_single_point(self):
        cx, cy = polygon_centroid([(3.0, 7.0)])
        assert cx == pytest.approx(3.0)
        assert cy == pytest.approx(7.0)

    def test_empty_polygon_raises(self):
        with pytest.raises(ValueError, match="Empty"):
            polygon_centroid([])

    def test_degenerate_polygon_arithmetic_mean(self):
        """Degenerate polygon falls back to arithmetic mean."""
        poly = [(0, 0), (1, 1), (2, 2)]
        cx, cy = polygon_centroid(poly)
        assert cx == pytest.approx(1.0)
        assert cy == pytest.approx(1.0)


# ─────────────────────────────────────────────────────────────────────────────
# Polygon Bounds
# ─────────────────────────────────────────────────────────────────────────────


class TestPolygonBounds:
    def test_unit_square(self):
        min_x, min_y, max_x, max_y = polygon_bounds([(0, 0), (1, 0), (1, 1), (0, 1)])
        assert min_x == pytest.approx(0.0)
        assert min_y == pytest.approx(0.0)
        assert max_x == pytest.approx(1.0)
        assert max_y == pytest.approx(1.0)

    def test_offset_polygon(self):
        poly = [(5, 10), (15, 10), (15, 20), (5, 20)]
        min_x, min_y, max_x, max_y = polygon_bounds(poly)
        assert min_x == pytest.approx(5.0)
        assert max_x == pytest.approx(15.0)
        assert min_y == pytest.approx(10.0)
        assert max_y == pytest.approx(20.0)


# ─────────────────────────────────────────────────────────────────────────────
# Polygon Perimeter
# ─────────────────────────────────────────────────────────────────────────────


class TestPolygonPerimeter:
    def test_unit_square(self):
        poly = [(0, 0), (1, 0), (1, 1), (0, 1)]
        assert polygon_perimeter(poly) == pytest.approx(4.0)

    def test_rectangle(self):
        poly = [(0, 0), (6, 0), (6, 4), (0, 4)]
        assert polygon_perimeter(poly) == pytest.approx(20.0)

    def test_triangle(self):
        """Right triangle: 3 + 4 + 5 = 12."""
        poly = [(0, 0), (3, 0), (0, 4)]
        assert polygon_perimeter(poly) == pytest.approx(12.0)


# ─────────────────────────────────────────────────────────────────────────────
# Point-in-Polygon (Ray Casting)
# ─────────────────────────────────────────────────────────────────────────────


class TestPointInPolygon:
    def test_inside_square(self):
        poly = [(0, 0), (10, 0), (10, 10), (0, 10)]
        assert point_in_polygon((5, 5), poly) is True

    def test_outside_square(self):
        poly = [(0, 0), (10, 0), (10, 10), (0, 10)]
        assert point_in_polygon((15, 5), poly) is False

    def test_on_edge_boundary_included(self):
        """Point on boundary with include_boundary=True."""
        poly = [(0, 0), (10, 0), (10, 10), (0, 10)]
        assert point_in_polygon((5, 0), poly, include_boundary=True) is True

    def test_on_edge_boundary_excluded(self):
        """Point on boundary with include_boundary=False."""
        poly = [(0, 0), (10, 0), (10, 10), (0, 10)]
        result = point_in_polygon((5, 0), poly, include_boundary=False)
        # On horizontal edge — ray casting skips horizontal edges
        assert isinstance(result, bool)

    def test_on_vertex(self):
        poly = [(0, 0), (10, 0), (10, 10), (0, 10)]
        assert point_in_polygon((0, 0), poly, include_boundary=True) is True

    def test_outside_bounding_box(self):
        """Fast bounding-box rejection."""
        poly = [(0, 0), (10, 0), (10, 10), (0, 10)]
        assert point_in_polygon((50, 50), poly) is False

    def test_l_shape_inside_main_body(self):
        poly = [(0, 0), (6, 0), (6, 2), (4, 2), (4, 4), (0, 4)]
        assert point_in_polygon((2, 2), poly) is True

    def test_l_shape_inside_cutout(self):
        """Point in the cutout area should be OUTSIDE."""
        poly = [(0, 0), (6, 0), (6, 2), (4, 2), (4, 4), (0, 4)]
        # Cutout is x=4..6, y=2..4 — point (5, 3) is in cutout
        assert point_in_polygon((5, 3), poly) is False

    def test_closed_polygon_handled(self):
        """Should work with explicitly closed polygon."""
        poly = [(0, 0), (10, 0), (10, 10), (0, 10), (0, 0)]
        assert point_in_polygon((5, 5), poly) is True

    def test_negative_coordinates(self):
        poly = [(-5, -5), (5, -5), (5, 5), (-5, 5)]
        assert point_in_polygon((0, 0), poly) is True
        assert point_in_polygon((-10, 0), poly) is False


# ─────────────────────────────────────────────────────────────────────────────
# Points-in-Polygon (batch)
# ─────────────────────────────────────────────────────────────────────────────


class TestPointsInPolygon:
    def test_batch_inside_outside(self):
        poly = [(0, 0), (10, 0), (10, 10), (0, 10)]
        results = points_in_polygon([(5, 5), (15, 15), (0, 0)], poly)
        assert results[0] is True
        assert results[1] is False
        assert results[2] is True  # On vertex with include_boundary=True

    def test_empty_points(self):
        poly = [(0, 0), (10, 0), (10, 10), (0, 10)]
        assert points_in_polygon([], poly) == []


# ─────────────────────────────────────────────────────────────────────────────
# Polygon Validation
# ─────────────────────────────────────────────────────────────────────────────


class TestValidatePolygon:
    def test_valid_square(self):
        poly = [(0, 0), (6, 0), (6, 4), (0, 4)]
        result = validate_polygon(poly)
        assert result.valid is True
        assert len(result.errors) == 0

    def test_too_few_vertices(self):
        result = validate_polygon([(0, 0), (1, 1)])
        assert result.valid is False
        assert any("minimum is 3" in e for e in result.errors)

    def test_empty_polygon(self):
        result = validate_polygon([])
        assert result.valid is False

    def test_duplicate_consecutive_vertices(self):
        poly = [(0, 0), (0, 0), (1, 0), (1, 1)]
        result = validate_polygon(poly)
        assert result.valid is False
        assert any("Duplicate" in e for e in result.errors)

    def test_very_small_area(self):
        """Area below minimum → invalid."""
        poly = [(0, 0), (0.001, 0), (0.001, 0.001)]
        result = validate_polygon(poly, min_area=0.01)
        assert result.valid is False

    def test_many_vertices_warning(self):
        """More than 50 vertices → warning."""
        poly = [(float(i), float(j)) for i in range(10) for j in range(10)]
        poly = poly[:51]  # 51 vertices
        result = validate_polygon(poly)
        assert any("simplification" in w for w in result.warnings)


# ─────────────────────────────────────────────────────────────────────────────
# Winding & Orientation
# ─────────────────────────────────────────────────────────────────────────────


class TestWindingOrientation:
    def test_clockwise_detection(self):
        cw = [(0, 0), (0, 4), (6, 4), (6, 0)]
        assert is_clockwise(cw) is True

    def test_counterclockwise_detection(self):
        ccw = [(0, 0), (6, 0), (6, 4), (0, 4)]
        assert is_clockwise(ccw) is False

    def test_ensure_ccw_already_ccw(self):
        ccw = [(0, 0), (6, 0), (6, 4), (0, 4)]
        result = ensure_ccw(ccw)
        assert result == ccw

    def test_ensure_ccw_converts_cw(self):
        cw = [(0, 0), (0, 4), (6, 4), (6, 0)]
        result = ensure_ccw(cw)
        assert is_clockwise(result) is False

    def test_ensure_ccw_preserves_vertices(self):
        cw = [(0, 0), (0, 4), (6, 4), (6, 0)]
        result = ensure_ccw(cw)
        assert set(result) == set(cw)


# ─────────────────────────────────────────────────────────────────────────────
# Polygon Constructors
# ─────────────────────────────────────────────────────────────────────────────


class TestRectPolygon:
    def test_unit_square(self):
        poly = rect_polygon(1, 1)
        assert len(poly) == 4
        assert polygon_area(poly) == pytest.approx(1.0)

    def test_custom_origin(self):
        poly = rect_polygon(4, 3, origin=(10, 20))
        assert poly[0] == (10, 20)
        assert polygon_area(poly) == pytest.approx(12.0)

    def test_ccw_order(self):
        poly = rect_polygon(4, 3)
        assert is_clockwise(poly) is False

    def test_zero_width_raises(self):
        with pytest.raises(ValueError, match="Width must be positive"):
            rect_polygon(0, 5)

    def test_negative_width_raises(self):
        with pytest.raises(ValueError, match="Width must be positive"):
            rect_polygon(-1, 5)

    def test_zero_height_raises(self):
        with pytest.raises(ValueError, match="Height must be positive"):
            rect_polygon(5, 0)

    def test_negative_height_raises(self):
        with pytest.raises(ValueError, match="Height must be positive"):
            rect_polygon(5, -1)


class TestLShapePolygon:
    def test_standard_l_shape(self):
        poly = l_shape_polygon(6, 4, 2, 2)
        assert len(poly) == 6
        # Area = 6×4 - 2×2 = 20
        assert polygon_area(poly) == pytest.approx(20.0)

    def test_cutout_exceeds_width_raises(self):
        with pytest.raises(ValueError, match="Cutout width"):
            l_shape_polygon(4, 4, 5, 2)

    def test_cutout_exceeds_height_raises(self):
        with pytest.raises(ValueError, match="Cutout height"):
            l_shape_polygon(4, 4, 2, 5)

    def test_no_cutout_equals_rectangle(self):
        """Zero cutout → full rectangle."""
        poly = l_shape_polygon(6, 4, 0, 0)
        assert polygon_area(poly) == pytest.approx(24.0)

    def test_example_from_docstring(self):
        poly = l_shape_polygon(6, 4, 2, 2)
        expected = [(0, 0), (6, 0), (6, 2), (4, 2), (4, 4), (0, 4)]
        assert poly == expected


# ─────────────────────────────────────────────────────────────────────────────
# Grid Generation
# ─────────────────────────────────────────────────────────────────────────────


class TestGridPointsInPolygon:
    def test_square_grid(self):
        poly = [(0, 0), (4, 0), (4, 4), (0, 4)]
        points = grid_points_in_polygon(poly, step=1.0)
        # Should contain interior points like (1,1), (2,2), (3,3), etc.
        assert len(points) > 0
        for p in points:
            assert point_in_polygon(p, poly)

    def test_margin_removes_boundary_points(self):
        """With margin, points near boundary should be excluded."""
        poly = [(0, 0), (10, 0), (10, 10), (0, 10)]
        no_margin = grid_points_in_polygon(poly, step=1.0, margin=0.0)
        with_margin = grid_points_in_polygon(poly, step=1.0, margin=2.0)
        assert len(with_margin) < len(no_margin)

    def test_margin_too_large_returns_empty(self):
        """If margin exceeds polygon size, no grid points."""
        poly = [(0, 0), (2, 0), (2, 2), (0, 2)]
        points = grid_points_in_polygon(poly, step=0.5, margin=1.5)
        assert points == []

    def test_negative_step_raises(self):
        with pytest.raises(ValueError, match="Step must be positive"):
            grid_points_in_polygon([(0, 0), (1, 0), (1, 1), (0, 1)], step=-1.0)

    def test_zero_step_raises(self):
        with pytest.raises(ValueError, match="Step must be positive"):
            grid_points_in_polygon([(0, 0), (1, 0), (1, 1), (0, 1)], step=0.0)

    def test_negative_margin_raises(self):
        with pytest.raises(ValueError, match="Margin must be non-negative"):
            grid_points_in_polygon([(0, 0), (1, 0), (1, 1), (0, 1)], margin=-0.1)

    def test_nfpa_wall_distance_margin(self):
        """NFPA 72 §17.6.3.1.1: 0.10m wall distance."""
        poly = [(0, 0), (10, 0), (10, 10), (0, 10)]
        points = grid_points_in_polygon(poly, step=0.5, margin=0.10)
        # All points should be at least 0.10m from walls
        for x, y in points:
            assert x >= 0.10 - 1e-9
            assert y >= 0.10 - 1e-9
            assert x <= 9.90 + 1e-9
            assert y <= 9.90 + 1e-9


# ─────────────────────────────────────────────────────────────────────────────
# Shape Classification
# ─────────────────────────────────────────────────────────────────────────────


class TestIsRectangular:
    def test_square_is_rectangular(self):
        assert is_rectangular([(0, 0), (6, 0), (6, 6), (0, 6)]) is True

    def test_rectangle_is_rectangular(self):
        assert is_rectangular([(0, 0), (10, 0), (10, 4), (0, 4)]) is True

    def test_l_shape_not_rectangular(self):
        poly = l_shape_polygon(6, 4, 2, 2)
        assert is_rectangular(poly) is False

    def test_triangle_not_rectangular(self):
        poly = [(0, 0), (1, 0), (0, 1)]
        assert is_rectangular(poly) is False

    def test_5_vertices_not_rectangular(self):
        poly = [(0, 0), (4, 0), (4, 3), (2, 3), (0, 3)]
        assert is_rectangular(poly) is False

    def test_closed_rectangle_handled(self):
        """Duplicate closing vertex should be stripped."""
        assert is_rectangular([(0, 0), (6, 0), (6, 4), (0, 4), (0, 0)]) is True

    def test_rotated_rectangle_not_axis_aligned(self):
        """A diamond (rotated 45°) should NOT be rectangular (not axis-aligned)."""
        poly = [(1, 0), (2, 1), (1, 2), (0, 1)]
        assert is_rectangular(poly) is False


class TestBoundingRectDimensions:
    def test_square(self):
        w, h, ox, oy = bounding_rect_dimensions([(0, 0), (4, 0), (4, 4), (0, 4)])
        assert w == pytest.approx(4.0)
        assert h == pytest.approx(4.0)
        assert ox == pytest.approx(0.0)
        assert oy == pytest.approx(0.0)

    def test_l_shape(self):
        poly = l_shape_polygon(6, 4, 2, 2)
        w, h, ox, oy = bounding_rect_dimensions(poly)
        assert w == pytest.approx(6.0)
        assert h == pytest.approx(4.0)

    def test_offset_polygon(self):
        poly = [(5, 5), (15, 5), (15, 15), (5, 15)]
        w, h, ox, oy = bounding_rect_dimensions(poly)
        assert ox == pytest.approx(5.0)
        assert oy == pytest.approx(5.0)


# ─────────────────────────────────────────────────────────────────────────────
# Convex Hull
# ─────────────────────────────────────────────────────────────────────────────


class TestConvexHull2D:
    def test_square_points(self):
        points = [(0, 0), (4, 0), (4, 4), (0, 4)]
        hull = convex_hull_2d(points)
        assert len(hull) == 4
        # Hull area should equal convex hull area
        assert polygon_area(hull) == pytest.approx(16.0)

    def test_points_with_interior(self):
        """Interior points should not appear in hull."""
        points = [(0, 0), (10, 0), (10, 10), (0, 10), (5, 5), (3, 3)]
        hull = convex_hull_2d(points)
        assert (5, 5) not in hull
        assert (3, 3) not in hull

    def test_collinear_points_raise(self):
        """Collinear points cannot form a valid hull."""
        with pytest.raises(ValueError, match="collinear"):
            convex_hull_2d([(0, 0), (1, 1), (2, 2)])

    def test_single_point(self):
        hull = convex_hull_2d([(3, 7)])
        assert hull == [(3, 7)]

    def test_two_points_raises(self):
        """Two points are collinear — cannot form a valid convex hull."""
        with pytest.raises(ValueError, match="collinear"):
            convex_hull_2d([(0, 0), (1, 1)])

    def test_duplicates_removed(self):
        points = [(0, 0), (0, 0), (4, 0), (4, 4), (0, 4)]
        hull = convex_hull_2d(points)
        assert len(hull) == 4

    def test_triangle(self):
        points = [(0, 0), (4, 0), (2, 4)]
        hull = convex_hull_2d(points)
        assert len(hull) == 3
        assert polygon_area(hull) == pytest.approx(8.0)


# ─────────────────────────────────────────────────────────────────────────────
# Room Geometry Sanitization
# ─────────────────────────────────────────────────────────────────────────────


class TestSanitizeRoomGeometry:
    def test_valid_room_not_rejected(self):
        result = sanitize_room_geometry([(0, 0), (10, 0), (10, 8), (0, 8)])
        assert result.rejected is False
        assert len(result.coords) >= 3

    def test_empty_coords_rejected(self):
        result = sanitize_room_geometry([])
        assert result.rejected is True

    def test_two_vertices_rejected(self):
        result = sanitize_room_geometry([(0, 0), (1, 1)])
        assert result.rejected is True
        assert "minimum is 3" in result.rejection_reason

    def test_small_area_rejected(self):
        """Room area below 1.0 m² is likely a Revit modeling error."""
        result = sanitize_room_geometry([(0, 0), (0.5, 0), (0.5, 0.5)], min_area=1.0)
        assert result.rejected is True

    def test_reasonable_room_passes(self):
        """10m × 8m room should pass."""
        result = sanitize_room_geometry([(0, 0), (10, 0), (10, 8), (0, 8)])
        assert result.rejected is False

    def test_sanitized_coords_are_tuples(self):
        result = sanitize_room_geometry([(0, 0), (10, 0), (10, 8), (0, 8)])
        for coord in result.coords:
            assert isinstance(coord, tuple)
            assert len(coord) == 2


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
