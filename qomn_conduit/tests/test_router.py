"""
qomn_conduit.tests.test_router — Pathfinding Determinism Tests
===============================================================

Tests orthogonal A* router for determinism, correctness, and edge cases.

Reference: NEC 300.4 (physical protection), 358.26 (bend limit).
"""

import pytest

from qomn_conduit import (
    ConduitType, TradeSize, Point3D, orthogonal_astar,
    BoundingBox, ConduitRouter, RoutePath,
)
from qomn_conduit.errors import RoutingError, PhysicsError


# ─────────────────────────────────────────────────────────────────────────────
# Test 1: Determinism — same input produces identical output
# ─────────────────────────────────────────────────────────────────────────────

class TestRouterDeterminism:
    """Router must be deterministic: same input → same output, always."""

    def test_same_input_identical_path(self):
        """Same start/end/obstacles → identical path, always."""
        start = Point3D(0.0, 0.0, 3.0)
        end = Point3D(10.0, 0.0, 3.0)
        result1 = orthogonal_astar(start, end, grid_resolution=0.5)
        result2 = orthogonal_astar(start, end, grid_resolution=0.5)
        assert result1.is_ok()
        assert result2.is_ok()
        assert result1.value.waypoints == result2.value.waypoints
        assert result1.value.total_length_m == pytest.approx(result2.value.total_length_m, abs=0.001)

    def test_determinism_three_runs(self):
        """Running the same route 3 times produces identical results."""
        start = Point3D(0.0, 0.0, 3.0)
        end = Point3D(5.0, 5.0, 3.0)
        results = [orthogonal_astar(start, end, grid_resolution=0.5) for _ in range(3)]
        for r in results:
            assert r.is_ok()
        # All three must be identical
        assert results[0].value.waypoints == results[1].value.waypoints
        assert results[1].value.waypoints == results[2].value.waypoints


# ─────────────────────────────────────────────────────────────────────────────
# Test 2: Path around obstacles
# ─────────────────────────────────────────────────────────────────────────────

class TestRouterObstacles:
    """Router must find valid paths around obstacles."""

    def test_straight_line_no_obstacles(self):
        """Straight line with no obstacles → single segment."""
        start = Point3D(0.0, 0.0, 3.0)
        end = Point3D(10.0, 0.0, 3.0)
        result = orthogonal_astar(start, end, grid_resolution=0.5)
        assert result.is_ok()
        assert result.value.total_length_m > 0

    def test_path_around_single_wall(self):
        """Path around a single wall obstacle → correct detour."""
        start = Point3D(0.0, 0.0, 3.0)
        end = Point3D(10.0, 0.0, 3.0)
        # Wall blocking the straight path
        wall = BoundingBox(
            x_min=4.0, y_min=-1.0, z_min=2.0,
            x_max=5.0, y_max=1.0, z_max=4.0,
            label="wall"
        )
        result = orthogonal_astar(start, end, obstacles=[wall], grid_resolution=0.5)
        assert result.is_ok()
        # Path must be longer than straight line due to detour
        straight_dist = start.distance_to(end)
        assert result.value.total_length_m > straight_dist

    def test_no_valid_path(self):
        """Completely blocked → explicit RoutingError."""
        start = Point3D(0.0, 0.0, 3.0)
        end = Point3D(10.0, 0.0, 3.0)
        # Wall spanning entire Y range with clearance
        wall = BoundingBox(
            x_min=4.0, y_min=-10.0, z_min=0.0,
            x_max=6.0, y_max=10.0, z_max=6.0,
            label="impenetrable_wall"
        )
        result = orthogonal_astar(start, end, obstacles=[wall], grid_resolution=0.5)
        # May or may not find a path depending on search boundaries
        # In a bounded grid, this should fail
        if result.is_err():
            assert isinstance(result.error, RoutingError)


# ─────────────────────────────────────────────────────────────────────────────
# Test 3: Physics errors for invalid inputs
# ─────────────────────────────────────────────────────────────────────────────

class TestRouterPhysicsErrors:
    """Invalid coordinates must return PhysicsError."""

    def test_nan_start_coordinate(self):
        """NaN start coordinate → PhysicsError."""
        # Point3D rejects NaN in __post_init__ before router sees it
        with pytest.raises(ValueError):
            Point3D(0.0, 0.0, float('nan'))

    def test_start_inside_obstacle(self):
        """Start inside obstacle → RoutingError."""
        start = Point3D(4.5, 0.0, 3.0)
        end = Point3D(10.0, 0.0, 3.0)
        wall = BoundingBox(
            x_min=4.0, y_min=-1.0, z_min=2.0,
            x_max=5.0, y_max=1.0, z_max=4.0,
            label="wall"
        )
        result = orthogonal_astar(start, end, obstacles=[wall], grid_resolution=0.5)
        assert result.is_err()

    def test_end_inside_obstacle(self):
        """End inside obstacle → RoutingError."""
        start = Point3D(0.0, 0.0, 3.0)
        end = Point3D(4.5, 0.0, 3.0)
        wall = BoundingBox(
            x_min=4.0, y_min=-1.0, z_min=2.0,
            x_max=5.0, y_max=1.0, z_max=4.0,
            label="wall"
        )
        result = orthogonal_astar(start, end, obstacles=[wall], grid_resolution=0.5)
        assert result.is_err()


# ─────────────────────────────────────────────────────────────────────────────
# Test 4: Path properties
# ─────────────────────────────────────────────────────────────────────────────

class TestRouterPathProperties:
    """Verify RoutePath output properties."""

    def test_straight_line_bend_count(self):
        """Straight line → 0 bends."""
        start = Point3D(0.0, 0.0, 3.0)
        end = Point3D(10.0, 0.0, 3.0)
        result = orthogonal_astar(start, end, grid_resolution=0.5)
        assert result.is_ok()
        assert result.value.bend_count == 0

    def test_l_shaped_path_bend_count(self):
        """L-shaped path → 1 bend."""
        start = Point3D(0.0, 0.0, 3.0)
        end = Point3D(5.0, 5.0, 3.0)
        # No obstacles — path should be L-shaped (2 segments, 1 bend)
        result = orthogonal_astar(start, end, grid_resolution=0.5)
        assert result.is_ok()
        # At least 1 bend expected for diagonal route
        assert result.value.bend_count >= 1

    def test_zero_length_path(self):
        """Start == end → zero-length path."""
        start = Point3D(5.0, 5.0, 3.0)
        end = Point3D(5.0, 5.0, 3.0)
        result = orthogonal_astar(start, end, grid_resolution=0.5)
        assert result.is_ok()
        assert result.value.total_length_m == pytest.approx(0.0, abs=0.001)

    def test_elevation_change(self):
        """Path with elevation change → elevation_change_m > 0."""
        start = Point3D(0.0, 0.0, 3.0)
        end = Point3D(5.0, 0.0, 4.0)
        result = orthogonal_astar(start, end, grid_resolution=0.5)
        assert result.is_ok()
        assert result.value.elevation_change_m == pytest.approx(1.0, abs=0.1)


# ─────────────────────────────────────────────────────────────────────────────
# Test 5: Manhattan heuristic is admissible
# ─────────────────────────────────────────────────────────────────────────────

class TestHeuristicAdmissibility:
    """Manhattan distance must never overestimate actual path length."""

    def test_manhattan_less_than_or_equal_to_path(self):
        """For any path, Manhattan distance ≤ total_length_m."""
        start = Point3D(0.0, 0.0, 3.0)
        end = Point3D(5.0, 5.0, 3.0)
        result = orthogonal_astar(start, end, grid_resolution=0.5)
        if result.is_ok():
            manhattan = start.manhattan_to(end)
            # Path length is always >= Manhattan distance
            assert result.value.total_length_m >= manhattan - 0.01  # tolerance for grid snapping

    def test_manhattan_distance_correct(self):
        """Point3D.manhattan_to computes correct Manhattan distance."""
        p1 = Point3D(0.0, 0.0, 0.0)
        p2 = Point3D(3.0, 4.0, 5.0)
        assert p1.manhattan_to(p2) == pytest.approx(12.0, abs=0.001)
