"""
test_geometry_utils.py — Tests for fireai.core.geometry_utils
==============================================================
Covers: area, centroid, bounds, perimeter, point-in-polygon,
validation, orientation, constructors, grid generation, convex hull.
"""

import math
import pytest
from fireai.core.geometry_utils import (
    polygon_area, polygon_centroid, polygon_bounds, polygon_perimeter,
    point_in_polygon, points_in_polygon, validate_polygon,
    grid_points_in_polygon, is_clockwise, ensure_ccw,
    rect_polygon, l_shape_polygon, shoelace_area,
    convex_hull_2d,
    is_rectangular, bounding_rect_dimensions,
)


class TestPolygonArea:
    def test_unit_square(self):
        assert polygon_area([(0, 0), (1, 0), (1, 1), (0, 1)]) == pytest.approx(1.0)

    def test_rectangle(self):
        assert polygon_area([(0, 0), (4, 0), (4, 3), (0, 3)]) == pytest.approx(12.0)

    def test_l_shape(self):
        poly = l_shape_polygon(6, 4, 2, 2)
        assert polygon_area(poly) == pytest.approx(20.0)

    def test_triangle(self):
        assert polygon_area([(0, 0), (4, 0), (0, 3)]) == pytest.approx(6.0)

    def test_cw_same_as_ccw(self):
        cw = [(0, 0), (0, 1), (1, 1), (1, 0)]
        ccw = [(0, 0), (1, 0), (1, 1), (0, 1)]
        assert polygon_area(cw) == pytest.approx(polygon_area(ccw))

    def test_degenerate_line(self):
        assert polygon_area([(0, 0), (1, 1), (2, 2)]) == pytest.approx(0.0)

    def test_shoelace_signed_ccw(self):
        ccw = [(0, 0), (1, 0), (1, 1), (0, 1)]
        assert shoelace_area(ccw) > 0

    def test_shoelace_signed_cw(self):
        cw = [(0, 0), (0, 1), (1, 1), (1, 0)]
        assert shoelace_area(cw) < 0


class TestCentroid:
    def test_square_centroid(self):
        cx, cy = polygon_centroid([(0, 0), (2, 0), (2, 2), (0, 2)])
        assert cx == pytest.approx(1.0)
        assert cy == pytest.approx(1.0)

    def test_rectangle_centroid(self):
        cx, cy = polygon_centroid([(0, 0), (6, 0), (6, 4), (0, 4)])
        assert cx == pytest.approx(3.0)
        assert cy == pytest.approx(2.0)

    def test_single_point_returns_itself(self):
        assert polygon_centroid([(3.0, 5.0)]) == (3.0, 5.0)

    def test_l_shape_centroid(self):
        """L-shape centroid should be offset from geometric center."""
        poly = l_shape_polygon(6, 4, 2, 2)
        cx, cy = polygon_centroid(poly)
        assert cx < 3.0  # Left of bounding box center
        assert cy < 2.0  # Below bounding box center


class TestBoundsAndPerimeter:
    def test_square_bounds(self):
        min_x, min_y, max_x, max_y = polygon_bounds([(0, 0), (3, 0), (3, 3), (0, 3)])
        assert min_x == 0 and min_y == 0 and max_x == 3 and max_y == 3

    def test_offset_rect_bounds(self):
        poly = rect_polygon(5, 3, origin=(10, 20))
        min_x, min_y, max_x, max_y = polygon_bounds(poly)
        assert min_x == 10 and min_y == 20 and max_x == 15 and max_y == 23

    def test_square_perimeter(self):
        assert polygon_perimeter([(0, 0), (1, 0), (1, 1), (0, 1)]) == pytest.approx(4.0)


class TestPointInPolygon:
    square = [(0, 0), (4, 0), (4, 4), (0, 4)]

    def test_center_inside(self):
        assert point_in_polygon((2, 2), self.square)

    def test_outside(self):
        assert not point_in_polygon((5, 5), self.square)

    def test_on_edge_included(self):
        assert point_in_polygon((2, 0), self.square, include_boundary=True)

    def test_on_edge_excluded(self):
        assert not point_in_polygon((2, 0), self.square, include_boundary=False)

    def test_corner_included(self):
        assert point_in_polygon((0, 0), self.square, include_boundary=True)

    def test_l_shape_inside(self):
        poly = l_shape_polygon(6, 4, 2, 2)
        assert point_in_polygon((1, 1), poly)

    def test_l_shape_cutout_outside(self):
        """Point in the cutout region should be OUTSIDE the L-shape."""
        poly = l_shape_polygon(6, 4, 2, 2)
        assert not point_in_polygon((5.0, 3.0), poly)

    def test_far_outside_fast_rejection(self):
        assert not point_in_polygon((100, 100), self.square)

    def test_batch_points(self):
        pts = [(2, 2), (5, 5), (0, 0)]
        results = points_in_polygon(pts, self.square)
        assert results == [True, False, True]


class TestValidation:
    def test_valid_square(self):
        r = validate_polygon([(0, 0), (4, 0), (4, 4), (0, 4)])
        assert r.valid

    def test_too_few_vertices(self):
        r = validate_polygon([(0, 0), (1, 1)])
        assert not r.valid
        assert any("3" in e for e in r.errors)

    def test_zero_area(self):
        r = validate_polygon([(0, 0), (1, 0), (0, 0)], min_area=0.01)
        assert not r.valid

    def test_duplicate_vertex_error(self):
        r = validate_polygon([(0, 0), (0, 0), (1, 1), (0, 1)])
        assert not r.valid

    def test_self_intersecting_hourglass(self):
        """Hourglass/bowtie shape should fail validation."""
        poly = [(0, 0), (4, 4), (4, 0), (0, 4)]
        r = validate_polygon(poly)
        assert not r.valid
        assert any("Self-intersection" in e for e in r.errors)


class TestOrientation:
    def test_ccw_detection(self):
        assert not is_clockwise([(0, 0), (1, 0), (1, 1), (0, 1)])

    def test_cw_detection(self):
        assert is_clockwise([(0, 0), (0, 1), (1, 1), (1, 0)])

    def test_ensure_ccw_idempotent(self):
        poly = [(0, 0), (1, 0), (1, 1), (0, 1)]
        assert ensure_ccw(poly) == poly

    def test_ensure_ccw_flips_cw(self):
        cw = [(0, 0), (0, 1), (1, 1), (1, 0)]
        assert not is_clockwise(ensure_ccw(cw))


class TestConstructors:
    def test_rect_polygon_area(self):
        assert polygon_area(rect_polygon(5, 3)) == pytest.approx(15.0)

    def test_rect_polygon_with_origin(self):
        poly = rect_polygon(4, 3, origin=(10, 20))
        assert poly[0] == (10, 20)
        assert polygon_area(poly) == pytest.approx(12.0)

    def test_rect_polygon_invalid_width(self):
        with pytest.raises(ValueError, match="positive"):
            rect_polygon(0, 5)

    def test_rect_polygon_is_ccw(self):
        poly = rect_polygon(5, 3)
        assert not is_clockwise(poly)

    def test_l_shape_area(self):
        poly = l_shape_polygon(6, 4, 2, 2)
        assert polygon_area(poly) == pytest.approx(20.0)

    def test_l_shape_6_vertices(self):
        poly = l_shape_polygon(6, 4, 2, 2)
        assert len(poly) == 6

    def test_l_shape_is_ccw(self):
        poly = l_shape_polygon(6, 4, 2, 2)
        assert not is_clockwise(poly)

    def test_l_shape_invalid_cutout_exceeds_width(self):
        with pytest.raises(ValueError, match="exceeds"):
            l_shape_polygon(4, 4, 5, 2)

    def test_l_shape_invalid_cutout_exceeds_height(self):
        with pytest.raises(ValueError, match="exceeds"):
            l_shape_polygon(4, 4, 2, 5)


class TestGridGeneration:
    def test_grid_all_inside_square(self):
        poly = rect_polygon(4, 4)
        pts = grid_points_in_polygon(poly, step=1.0)
        for p in pts:
            assert point_in_polygon(p, poly), f"{p} outside polygon"

    def test_grid_nonempty(self):
        poly = rect_polygon(5, 5)
        assert len(grid_points_in_polygon(poly, step=1.0)) > 0

    def test_l_shape_grid_excludes_cutout(self):
        poly = l_shape_polygon(6, 4, 2, 2)
        pts = grid_points_in_polygon(poly, step=0.5)
        for p in pts:
            assert point_in_polygon(p, poly), f"{p} outside L-shape"

    def test_invalid_step_raises(self):
        with pytest.raises(ValueError, match="positive"):
            grid_points_in_polygon(rect_polygon(4, 4), step=0)

    def test_negative_margin_raises(self):
        with pytest.raises(ValueError, match="non-negative"):
            grid_points_in_polygon(rect_polygon(4, 4), step=1.0, margin=-0.1)

    def test_margin_reduces_points(self):
        poly = rect_polygon(10, 10)
        pts_no_margin = grid_points_in_polygon(poly, step=1.0, margin=0.0)
        pts_with_margin = grid_points_in_polygon(poly, step=1.0, margin=0.5)
        assert len(pts_with_margin) < len(pts_no_margin)

    def test_nfpa_wall_margin(self):
        """NFPA 72 §17.6.3.1.1: All grid points >= 0.10m from walls."""
        poly = rect_polygon(6, 6)
        margin = 0.10
        pts = grid_points_in_polygon(poly, step=0.5, margin=margin)
        for px, py in pts:
            assert px >= margin - 1e-9
            assert py >= margin - 1e-9
            assert 6.0 - px >= margin - 1e-9
            assert 6.0 - py >= margin - 1e-9

    def test_large_margin_empty_grid(self):
        poly = rect_polygon(2, 2)
        pts = grid_points_in_polygon(poly, step=0.5, margin=1.5)
        assert len(pts) == 0


class TestConvexHull:
    def test_square_hull(self):
        pts = [(0, 0), (1, 0), (1, 1), (0, 1)]
        hull = convex_hull_2d(pts)
        assert polygon_area(hull) == pytest.approx(1.0)

    def test_hull_with_interior_points(self):
        pts = [(0, 0), (4, 0), (4, 4), (0, 4), (2, 2), (1, 1), (3, 1)]
        hull = convex_hull_2d(pts)
        assert polygon_area(hull) == pytest.approx(16.0)
        assert len(hull) == 4

    def test_hull_collinear_raises(self):
        with pytest.raises(ValueError, match="collinear"):
            convex_hull_2d([(0, 0), (1, 1), (2, 2)])

    def test_hull_triangle(self):
        pts = [(0, 0), (4, 0), (2, 3)]
        hull = convex_hull_2d(pts)
        assert polygon_area(hull) == pytest.approx(6.0)

    def test_hull_removes_duplicates(self):
        pts = [(0, 0), (0, 0), (4, 0), (4, 4), (0, 4)]
        hull = convex_hull_2d(pts)
        assert polygon_area(hull) == pytest.approx(16.0)

    def test_hull_single_point(self):
        result = convex_hull_2d([(3, 7)])
        assert result == [(3, 7)]


# ============================================================================
# Shape Classification Tests
# ============================================================================

class TestIsRectangular:

    def test_rect_is_rectangular(self):
        poly = [(0, 0), (6, 0), (6, 4), (0, 4)]
        assert is_rectangular(poly) is True

    def test_l_shape_is_not_rectangular(self):
        poly = l_shape_polygon(6, 4, 2, 2)
        assert is_rectangular(poly) is False

    def test_triangle_is_not_rectangular(self):
        poly = [(0, 0), (4, 0), (2, 3)]
        assert is_rectangular(poly) is False

    def test_closed_rect_is_rectangular(self):
        """Rect with first==last vertex (closed) should still be rectangular."""
        poly = [(0, 0), (6, 0), (6, 4), (0, 4), (0, 0)]
        assert is_rectangular(poly) is True

    def test_rect_from_constructor(self):
        poly = rect_polygon(5, 3)
        assert is_rectangular(poly) is True

    def test_pentagon_is_not_rectangular(self):
        import math as _m
        poly = [(3 + 2 * _m.cos(2 * _m.pi * i / 5),
                 3 + 2 * _m.sin(2 * _m.pi * i / 5)) for i in range(5)]
        assert is_rectangular(poly) is False

    def test_3_vertices_not_rectangular(self):
        """Triangle has 3 vertices — not rectangular."""
        poly = [(0, 0), (1, 0), (0.5, 0.87)]
        assert is_rectangular(poly) is False

    def test_rotated_rect_not_axis_aligned(self):
        """45-degree rotated rectangle is NOT axis-aligned."""
        poly = [(0, 0), (1, 1), (0, 2), (-1, 1)]
        assert is_rectangular(poly) is False


class TestBoundingRectDimensions:

    def test_rect_dimensions(self):
        poly = [(0, 0), (6, 0), (6, 4), (0, 4)]
        w, h, ox, oy = bounding_rect_dimensions(poly)
        assert w == pytest.approx(6.0)
        assert h == pytest.approx(4.0)
        assert ox == pytest.approx(0.0)
        assert oy == pytest.approx(0.0)

    def test_l_shape_dimensions(self):
        poly = l_shape_polygon(6, 4, 2, 2)
        w, h, ox, oy = bounding_rect_dimensions(poly)
        assert w == pytest.approx(6.0)
        assert h == pytest.approx(4.0)
        assert ox == pytest.approx(0.0)
        assert oy == pytest.approx(0.0)

    def test_offset_polygon(self):
        poly = rect_polygon(5, 3, origin=(10, 20))
        w, h, ox, oy = bounding_rect_dimensions(poly)
        assert w == pytest.approx(5.0)
        assert h == pytest.approx(3.0)
        assert ox == pytest.approx(10.0)
        assert oy == pytest.approx(20.0)
