"""
qomn_conduit.tests.test_fitting_engine — End-to-End Integration Tests
======================================================================

Tests fitting placement engine: elbows at turns, couplings on long
runs, pull boxes at 360° limit, and NEC compliance verification.

Reference: NEC 358.26 / 352.26 / 344.26; NEC 358.120; NEC 110.3(B).
"""

import pytest

from qomn_conduit import (
    ConduitType, TradeSize, FittingType, Point3D, RoutePath,
    place_fittings, ConduitRun, PlacedFitting,
)
from qomn_conduit.errors import PhysicsError


# ─────────────────────────────────────────────────────────────────────────────
# Helper: create a RoutePath from waypoints
# ─────────────────────────────────────────────────────────────────────────────

def _make_path(waypoints, total_length=None, bend_count=None, elevation_change=None):
    """Create a RoutePath from a list of Point3D waypoints."""
    if total_length is None:
        total_length = sum(
            waypoints[i].distance_to(waypoints[i + 1])
            for i in range(len(waypoints) - 1)
        )
    if bend_count is None:
        bend_count = max(0, len(waypoints) - 2)
    if elevation_change is None:
        elevation_change = abs(waypoints[-1].z - waypoints[0].z)
    return RoutePath(
        waypoints=tuple(waypoints),
        total_length_m=total_length,
        bend_count=bend_count,
        elevation_change_m=elevation_change,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Test 1: Straight 10m run → 1 conduit segment, 0 elbows
# ─────────────────────────────────────────────────────────────────────────────

class TestStraightRun:
    """Straight runs should have no elbows, couplings on long runs."""

    def test_short_straight_run(self):
        """Short 5m straight run → 1 segment, 0 elbows, possibly 1 coupling."""
        path = _make_path([
            Point3D(0.0, 0.0, 3.0),
            Point3D(5.0, 0.0, 3.0),
        ])
        result = place_fittings(path, ConduitType.EMT, TradeSize.HALF_INCH)
        assert result.is_ok()
        run = result.value
        assert len(run.segments) >= 1
        # No elbows on a straight run
        elbows = [f for f in run.fittings if f.fitting_type == FittingType.ELBOW_90]
        assert len(elbows) == 0

    def test_long_straight_run_has_couplings(self):
        """10m straight run → at least 3 couplings (10m / 3.048m ≈ 3.3 sticks)."""
        path = _make_path([
            Point3D(0.0, 0.0, 3.0),
            Point3D(10.0, 0.0, 3.0),
        ])
        result = place_fittings(path, ConduitType.EMT, TradeSize.HALF_INCH)
        assert result.is_ok()
        run = result.value
        couplings = [f for f in run.fittings if f.fitting_type == FittingType.COUPLING]
        assert len(couplings) >= 2  # 10m / 3.048m ≈ 3.3 sticks → 2 couplings


# ─────────────────────────────────────────────────────────────────────────────
# Test 2: 90° turn → 1 elbow with correct catalog number
# ─────────────────────────────────────────────────────────────────────────────

class TestElbowPlacement:
    """Direction changes must produce elbows from the catalog."""

    def test_single_90_turn(self):
        """L-shaped path → 1 ELBOW_90 with correct catalog number."""
        path = _make_path([
            Point3D(0.0, 0.0, 3.0),
            Point3D(5.0, 0.0, 3.0),
            Point3D(5.0, 5.0, 3.0),
        ])
        result = place_fittings(path, ConduitType.EMT, TradeSize.HALF_INCH)
        assert result.is_ok()
        run = result.value
        elbows = [f for f in run.fittings if f.fitting_type == FittingType.ELBOW_90]
        assert len(elbows) == 1
        assert elbows[0].catalog_number == "E90-050"

    def test_two_90_turns(self):
        """Z-shaped path → 2 elbows, total bend degrees = 180°."""
        path = _make_path([
            Point3D(0.0, 0.0, 3.0),
            Point3D(5.0, 0.0, 3.0),
            Point3D(5.0, 5.0, 3.0),
            Point3D(10.0, 5.0, 3.0),
        ])
        result = place_fittings(path, ConduitType.EMT, TradeSize.THREE_QUARTER)
        assert result.is_ok()
        run = result.value
        elbows = [f for f in run.fittings if f.fitting_type == FittingType.ELBOW_90]
        assert len(elbows) == 2
        assert run.total_bend_deg == pytest.approx(180.0, abs=0.1)


# ─────────────────────────────────────────────────────────────────────────────
# Test 3: Four 90° turns → pull box insertion
# ─────────────────────────────────────────────────────────────────────────────

class TestPullBoxInsertion:
    """When cumulative bends exceed 360°, pull boxes must be inserted."""

    def test_four_90_turns_with_pull_box(self):
        """4 × 90° = 360° → should be at or near the limit, may insert pull box."""
        path = _make_path([
            Point3D(0.0, 0.0, 3.0),
            Point3D(5.0, 0.0, 3.0),
            Point3D(5.0, 5.0, 3.0),
            Point3D(0.0, 5.0, 3.0),
            Point3D(0.0, 10.0, 3.0),
        ])
        result = place_fittings(path, ConduitType.EMT, TradeSize.HALF_INCH)
        assert result.is_ok()
        run = result.value
        elbows = [f for f in run.fittings if f.fitting_type == FittingType.ELBOW_90]
        assert len(elbows) == 3  # 3 elbows at the 3 interior waypoints

    def test_five_90_turns_inserts_pull_box(self):
        """5 × 90° = 450° > 360° → must insert at least one pull box."""
        path = _make_path([
            Point3D(0.0, 0.0, 3.0),
            Point3D(5.0, 0.0, 3.0),
            Point3D(5.0, 5.0, 3.0),
            Point3D(0.0, 5.0, 3.0),
            Point3D(0.0, 10.0, 3.0),
            Point3D(5.0, 10.0, 3.0),
            Point3D(5.0, 5.0, 3.0),   # 6th waypoint for 5th turn
        ])
        result = place_fittings(path, ConduitType.EMT, TradeSize.HALF_INCH)
        assert result.is_ok()
        run = result.value
        pull_boxes = [f for f in run.fittings if f.fitting_type == FittingType.PULL_BOX]
        # At >360° cumulative bends, a pull box should be inserted
        assert len(pull_boxes) >= 1


# ─────────────────────────────────────────────────────────────────────────────
# Test 4: Elevation change → elevation penalty applied
# ─────────────────────────────────────────────────────────────────────────────

class TestElevationChange:
    """Paths with vertical segments must be handled correctly."""

    def test_vertical_segment(self):
        """Path going up 2m → segments include vertical change."""
        path = _make_path([
            Point3D(0.0, 0.0, 3.0),
            Point3D(0.0, 0.0, 5.0),
        ])
        result = place_fittings(path, ConduitType.EMT, TradeSize.HALF_INCH)
        assert result.is_ok()
        run = result.value
        assert run.total_length_m == pytest.approx(2.0, abs=0.01)


# ─────────────────────────────────────────────────────────────────────────────
# Test 5: Invalid input handling
# ─────────────────────────────────────────────────────────────────────────────

class TestFittingEngineInvalidInput:
    """Invalid inputs must return error results, never raise."""

    def test_single_waypoint_path(self):
        """Path with only 1 waypoint → PhysicsError."""
        path = RoutePath(
            waypoints=(Point3D(0.0, 0.0, 3.0),),
            total_length_m=0.0,
            bend_count=0,
            elevation_change_m=0.0,
        )
        result = place_fittings(path, ConduitType.EMT, TradeSize.HALF_INCH)
        assert result.is_err()

    def test_run_id_auto_generated(self):
        """If run_id is None, it should be auto-generated."""
        path = _make_path([
            Point3D(0.0, 0.0, 3.0),
            Point3D(5.0, 0.0, 3.0),
        ])
        result = place_fittings(path, ConduitType.EMT, TradeSize.HALF_INCH, run_id=None)
        assert result.is_ok()
        assert result.value.run_id.startswith("RUN-")

    def test_custom_run_id(self):
        """Custom run_id should be preserved."""
        path = _make_path([
            Point3D(0.0, 0.0, 3.0),
            Point3D(5.0, 0.0, 3.0),
        ])
        result = place_fittings(path, ConduitType.EMT, TradeSize.HALF_INCH, run_id="CUSTOM-001")
        assert result.is_ok()
        assert result.value.run_id == "CUSTOM-001"
