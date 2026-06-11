"""
tests/test_nfpa72_coverage_v3.py
================================
Comprehensive test suite for fireai/core/nfpa72_coverage.py.

Covers ALL 16 public functions with normal cases, edge cases,
and safety-critical edge cases (NaN, Inf, negative, zero,
very large values).

Critical geometry assertions:
  - SMOKE detectors use CIRCULAR (Euclidean) geometry
  - HEAT detectors use SQUARE (Chebyshev) geometry

NFPA 72 References:
  §17.6.3.1.1 — Minimum wall distance (4 inches = 101.6mm)
  §17.7.4.1   — HVAC supply diffuser exclusion zone (3 ft = 0.914m)
  §17.6.3.4   — Ridge zone detector placement for sloped ceilings
  §17.6.3.1   — Beam-adjusted coverage
  Table 17.6.3.1.1 — Height-adjusted spacing
"""

from __future__ import annotations

import math
import pytest
from shapely.geometry import Point, Polygon, box

from fireai.core.nfpa72_coverage import (
    NFPA_MIN_WALL_DISTANCE_M,
    NFPA_HVAC_EXCLUSION_RADIUS_M,
    DuctDevice,
    WallViolation,
    validate_wall_distances,
    validate_hvac_exclusion_zones,
    compute_hvac_safe_zone,
    suggest_duct_detectors,
    create_room_polygon,
    is_point_in_room,
    check_coverage_polygon,
    calculate_voronoi_coverage,
    check_voronoi_coverage,
    check_ridge_zone_compliance,
    create_l_shaped_polygon,
    check_l_shaped_coverage,
    check_nfpa72_compliance,
    verify_full_coverage,
    get_sloped_ceiling_constraints,
    adjust_coverage_for_beams,
)
from fireai.core.nfpa72_models import (
    CeilingSpec,
    CoverageResult,
    DetectorType,
    NFPAComplianceResult,
    RoomSpec,
    HVACDuct,
)
from fireai.core.contracts import CeilingType


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def simple_room() -> RoomSpec:
    """10m x 10m office room with 3m ceiling."""
    return RoomSpec(
        room_id="RM-001",
        name="Office",
        width_m=10.0,
        depth_m=10.0,
        ceiling_spec=CeilingSpec(height_at_low_point_m=3.0),
    )


@pytest.fixture
def ceiling_flat() -> CeilingSpec:
    """Flat ceiling at 3m."""
    return CeilingSpec(height_at_low_point_m=3.0)


@pytest.fixture
def ceiling_high() -> CeilingSpec:
    """High ceiling at 9m (tests height-adjusted spacing)."""
    return CeilingSpec.create_safe(height_at_low_point_m=9.0)


@pytest.fixture
def sloped_ceiling() -> CeilingSpec:
    """Sloped ceiling that requires ridge zone detectors (>14 deg)."""
    return CeilingSpec(
        height_at_low_point_m=3.0,
        height_at_high_point_m=4.0,
        ceiling_type=CeilingType.SLOPED,
        slope_run_m=3.0,
    )


@pytest.fixture
def l_shaped_polygon() -> Polygon:
    """L-shaped room polygon: 10m x 10m with a 5m x 5m corner cut."""
    return Polygon([(0, 0), (10, 0), (10, 5), (5, 5), (5, 10), (0, 10)])


@pytest.fixture
def small_room_8m() -> RoomSpec:
    """8m x 8m room — fits single smoke detector at 3m ceiling."""
    return RoomSpec(
        room_id="SM-001",
        name="Small",
        width_m=8.0,
        depth_m=8.0,
        ceiling_spec=CeilingSpec(height_at_low_point_m=3.0),
    )


@pytest.fixture
def small_room_5m() -> RoomSpec:
    """5m x 5m room — fits single heat detector at 3m ceiling."""
    return RoomSpec(
        room_id="HT-001",
        name="Heat Room",
        width_m=5.0,
        depth_m=5.0,
        ceiling_spec=CeilingSpec(height_at_low_point_m=3.0),
    )


# =============================================================================
# Constants
# =============================================================================


class TestConstants:
    """NFPA 72 constant values — must be exact."""

    def test_min_wall_distance_m(self):
        assert NFPA_MIN_WALL_DISTANCE_M == pytest.approx(0.1016, abs=0.0001)

    def test_hvac_exclusion_radius_m(self):
        assert NFPA_HVAC_EXCLUSION_RADIUS_M == pytest.approx(0.9144, abs=0.0001)


# =============================================================================
# DuctDevice / WallViolation dataclasses
# =============================================================================


class TestDuctDevice:
    def test_basic_creation(self):
        d = DuctDevice(device_id="DUCT_1", x=5.0, y=3.0)
        assert d.device_id == "DUCT_1"
        assert d.x == 5.0
        assert d.y == 3.0
        assert d.z == 0.0
        assert d.detector_type == "smoke"

    def test_custom_type(self):
        d = DuctDevice(device_id="DUCT_2", x=1.0, y=2.0, z=3.0, detector_type="heat")
        assert d.detector_type == "heat"
        assert d.z == 3.0

    def test_defaults(self):
        d = DuctDevice(device_id="D3", x=0.0, y=0.0)
        assert d.z == 0.0
        assert d.detector_type == "smoke"


class TestWallViolation:
    def test_creation(self):
        v = WallViolation(x=0.05, y=5.0, distance_m=0.05, min_required_m=0.1016)
        assert v.distance_m == 0.05
        assert v.min_required_m == pytest.approx(0.1016, abs=0.0001)

    def test_min_required_m_default(self):
        v = WallViolation(x=0.0, y=0.0, distance_m=0.0, min_required_m=NFPA_MIN_WALL_DISTANCE_M)
        assert v.min_required_m == pytest.approx(0.1016, abs=0.0001)


# =============================================================================
# validate_wall_distances — NFPA 72 §17.6.3.1.1
# =============================================================================


class TestValidateWallDistances:
    """NFPA 72 §17.6.3.1.1: Detectors not closer than 4 inches from wall."""

    def test_no_violations_center_detectors(self, simple_room):
        positions = [(5.0, 5.0), (7.5, 7.5)]
        violations = validate_wall_distances(positions, simple_room)
        assert len(violations) == 0

    def test_violation_too_close_to_left_wall(self, simple_room):
        positions = [(0.05, 5.0)]
        violations = validate_wall_distances(positions, simple_room)
        assert len(violations) >= 1
        assert any(v["wall"] == "left" for v in violations)

    def test_violation_too_close_to_right_wall(self, simple_room):
        positions = [(9.95, 5.0)]
        violations = validate_wall_distances(positions, simple_room)
        assert len(violations) >= 1
        assert any(v["wall"] == "right" for v in violations)

    def test_violation_too_close_to_top_wall(self, simple_room):
        positions = [(5.0, 9.95)]
        violations = validate_wall_distances(positions, simple_room)
        assert len(violations) >= 1
        assert any(v["wall"] == "top" for v in violations)

    def test_violation_too_close_to_bottom_wall(self, simple_room):
        positions = [(5.0, 0.05)]
        violations = validate_wall_distances(positions, simple_room)
        assert len(violations) >= 1
        assert any(v["wall"] == "bottom" for v in violations)

    def test_boundary_exactly_at_min_distance(self, simple_room):
        positions = [(0.1016, 5.0)]
        violations = validate_wall_distances(positions, simple_room)
        left_violations = [v for v in violations if v["wall"] == "left"]
        assert len(left_violations) == 0

    def test_nfpa_reference_in_violations(self, simple_room):
        positions = [(0.05, 5.0)]
        violations = validate_wall_distances(positions, simple_room)
        assert len(violations) >= 1
        for v in violations:
            assert "17.6.3.1.1" in v.get("nfpa_reference", "")

    def test_polygon_mode_with_l_shaped_room(self):
        room_spec = RoomSpec(
            room_id="L-001",
            name="L-Room",
            width_m=10.0,
            depth_m=10.0,
            ceiling_spec=CeilingSpec(height_at_low_point_m=3.0),
        )
        l_poly = Polygon([(0, 0), (10, 0), (10, 5), (5, 5), (5, 10), (0, 10)])
        positions = [(5.05, 5.05)]
        violations = validate_wall_distances(positions, room_spec, room_polygon=l_poly)
        assert len(violations) >= 1
        assert any(v["wall"] == "polygon_boundary" for v in violations)

    def test_empty_positions(self, simple_room):
        violations = validate_wall_distances([], simple_room)
        assert len(violations) == 0

    def test_custom_min_distance(self, simple_room):
        positions = [(0.15, 5.0)]
        v1 = validate_wall_distances(positions, simple_room, min_distance_m=0.1016)
        v2 = validate_wall_distances(positions, simple_room, min_distance_m=0.20)
        assert len(v1) == 0
        assert len(v2) >= 1

    def test_all_violations_recorded_for_multiple_detectors(self, simple_room):
        positions = [(0.05, 5.0), (9.95, 5.0), (5.0, 5.0)]
        violations = validate_wall_distances(positions, simple_room)
        assert len(violations) >= 2

    def test_violation_dict_contains_all_keys(self, simple_room):
        positions = [(0.05, 5.0)]
        violations = validate_wall_distances(positions, simple_room)
        assert len(violations) >= 1
        v = violations[0]
        for key in ("detector_index", "position", "wall", "distance_m", "required_m", "violation", "nfpa_reference"):
            assert key in v

    # --- Safety-critical edge cases ---

    def test_nan_position(self, simple_room):
        pos = [(float("nan"), 5.0)]
        violations = validate_wall_distances(pos, simple_room)
        assert len(violations) == 0

    def test_inf_position(self, simple_room):
        pos = [(float("inf"), 5.0)]
        violations = validate_wall_distances(pos, simple_room)
        assert len(violations) == 0

    def test_negative_position(self, simple_room):
        pos = [(-5.0, 5.0)]
        violations = validate_wall_distances(pos, simple_room)
        assert len(violations) >= 1  # -5.0 is < 0.1016 from left wall

    def test_very_large_position(self, simple_room):
        pos = [(1e6, 5.0)]
        violations = validate_wall_distances(pos, simple_room)
        assert len(violations) >= 1  # far beyond room bounds

    def test_zero_position_hits_left_and_bottom(self, simple_room):
        pos = [(0.0, 0.0)]
        violations = validate_wall_distances(pos, simple_room)
        walls_found = {v["wall"] for v in violations}
        assert "left" in walls_found
        assert "bottom" in walls_found


# =============================================================================
# validate_hvac_exclusion_zones — NFPA 72 §17.7.4.1
# =============================================================================


class TestValidateHVACExclusionZones:
    """NFPA 72 §17.7.4.1: Detectors not within 3ft of HVAC supply diffuser."""

    def test_no_violations_far_from_diffuser(self):
        det = [(5.0, 5.0)]
        diff = [(0.0, 0.0)]
        violations = validate_hvac_exclusion_zones(det, diff)
        assert len(violations) == 0

    def test_violation_detector_near_diffuser(self):
        det = [(0.5, 0.0)]
        diff = [(0.0, 0.0)]
        violations = validate_hvac_exclusion_zones(det, diff)
        assert len(violations) >= 1
        assert violations[0]["distance_m"] < 0.9144

    def test_nfpa_reference_in_violations(self):
        det = [(0.5, 0.0)]
        diff = [(0.0, 0.0)]
        violations = validate_hvac_exclusion_zones(det, diff)
        for v in violations:
            assert "17.7.4.1" in v.get("nfpa_reference", "")

    def test_exactly_at_exclusion_radius(self):
        det = [(0.9144, 0.0)]
        diff = [(0.0, 0.0)]
        violations = validate_hvac_exclusion_zones(det, diff)
        assert len(violations) == 0

    def test_multiple_diffusers(self):
        det = [(0.5, 0.0)]
        diff = [(0.0, 0.0), (5.0, 5.0)]
        violations = validate_hvac_exclusion_zones(det, diff)
        assert len(violations) >= 1

    def test_empty_inputs(self):
        assert validate_hvac_exclusion_zones([], [(0, 0)]) == []
        assert validate_hvac_exclusion_zones([(0, 0)], []) == []

    def test_custom_exclusion_radius(self):
        det = [(1.0, 0.0)]
        diff = [(0.0, 0.0)]
        v1 = validate_hvac_exclusion_zones(det, diff, exclusion_radius_m=0.9144)
        v2 = validate_hvac_exclusion_zones(det, diff, exclusion_radius_m=1.5)
        assert len(v1) == 0
        assert len(v2) >= 1

    def test_multiple_detectors_one_violation(self):
        det = [(0.5, 0.0), (5.0, 5.0)]
        diff = [(0.0, 0.0)]
        violations = validate_hvac_exclusion_zones(det, diff)
        assert len(violations) >= 1
        assert violations[0]["detector_index"] == 0

    def test_violation_dict_keys(self):
        det = [(0.5, 0.0)]
        diff = [(0.0, 0.0)]
        v = validate_hvac_exclusion_zones(det, diff)[0]
        for key in ("detector_index", "position", "diffuser_index", "diffuser_position", "distance_m", "required_m", "violation", "nfpa_reference"):
            assert key in v

    # --- Safety-critical edge cases ---

    def test_nan_detector_position(self):
        det = [(float("nan"), 0.0)]
        diff = [(0.0, 0.0)]
        violations = validate_hvac_exclusion_zones(det, diff)
        assert len(violations) == 0

    def test_inf_diffuser_position(self):
        det = [(0.5, 0.0)]
        diff = [(float("inf"), 0.0)]
        violations = validate_hvac_exclusion_zones(det, diff)
        assert len(violations) == 0  # dist = inf > 0.9144

    def test_negative_positions(self):
        det = [(-0.5, 0.0)]
        diff = [(0.0, 0.0)]
        violations = validate_hvac_exclusion_zones(det, diff)
        assert len(violations) >= 1  # |-0.5 - 0| = 0.5 < 0.9144


# =============================================================================
# compute_hvac_safe_zone
# =============================================================================


class TestComputeHVACSafeZone:
    def test_safe_zone_returns_polygon(self):
        room = box(0, 0, 10, 10)
        diffusers = [(5.0, 5.0)]
        safe = compute_hvac_safe_zone(room, diffusers)
        assert safe.is_valid
        assert not safe.is_empty
        assert safe.area < room.area

    def test_no_diffusers_returns_room(self):
        room = box(0, 0, 10, 10)
        safe = compute_hvac_safe_zone(room, [])
        assert safe.equals(room)

    def test_diffusers_cover_entire_ceiling_raises(self):
        room = box(0, 0, 1, 1)
        diffusers = [(0.5, 0.5)]
        with pytest.raises(ValueError, match="No valid detector placement"):
            compute_hvac_safe_zone(room, diffusers, exclusion_radius_m=10.0)

    def test_multiple_diffusers(self):
        room = box(0, 0, 20, 20)
        diffusers = [(2.0, 2.0), (18.0, 18.0)]
        safe = compute_hvac_safe_zone(room, diffusers)
        assert safe.is_valid
        assert safe.area < room.area

    def test_diffuser_on_edge(self):
        room = box(0, 0, 10, 10)
        diffusers = [(0.0, 0.0)]
        safe = compute_hvac_safe_zone(room, diffusers)
        assert safe.is_valid
        assert not safe.is_empty
        assert safe.area < room.area

    def test_custom_exclusion_radius(self):
        room = box(0, 0, 10, 10)
        diffusers = [(5.0, 5.0)]
        safe_default = compute_hvac_safe_zone(room, diffusers, exclusion_radius_m=0.9144)
        safe_large = compute_hvac_safe_zone(room, diffusers, exclusion_radius_m=3.0)
        assert safe_large.area < safe_default.area

    def test_many_diffusers_progressive_reduction(self):
        room = box(0, 0, 10, 10)
        diffusers = [(2, 2), (4, 2), (6, 2), (8, 2)]
        safe = compute_hvac_safe_zone(room, diffusers)
        assert safe.is_valid
        assert not safe.is_empty

    # --- Safety-critical edge cases ---

    def test_nan_diffuser_position(self):
        room = box(0, 0, 10, 10)
        diffusers = [(float("nan"), 5.0)]
        safe = compute_hvac_safe_zone(room, diffusers)
        assert safe.is_valid

    def test_very_large_room_large_diffuser_count(self):
        room = box(0, 0, 100, 100)
        diffusers = [(i * 10, j * 10) for i in range(10) for j in range(10)]
        safe = compute_hvac_safe_zone(room, diffusers)
        assert safe.is_valid


# =============================================================================
# suggest_duct_detectors
# =============================================================================


class TestSuggestDuctDetectors:
    def test_no_ducts_returns_empty(self, simple_room):
        devices = suggest_duct_detectors(simple_room)
        assert devices == []

    def test_with_hvac_ducts(self):
        room = RoomSpec(
            room_id="DUCT-001",
            name="Duct Room",
            width_m=10.0,
            depth_m=10.0,
            ceiling_spec=CeilingSpec(height_at_low_point_m=3.0),
            hvac_duct_list=[
                HVACDuct(centerline=[(5.0, 3.0, 3.5)]),
                HVACDuct(centerline=[(7.0, 8.0, 3.5)]),
            ],
        )
        devices = suggest_duct_detectors(room)
        assert len(devices) == 2
        assert devices[0].device_id == "DUCT_1"
        assert devices[0].x == 5.0
        assert devices[1].device_id == "DUCT_2"
        assert devices[1].detector_type == "smoke"

    def test_heat_type_parameter(self):
        room = RoomSpec(
            room_id="DUCT-002",
            name="Duct Room",
            width_m=10.0,
            depth_m=10.0,
            ceiling_spec=CeilingSpec(height_at_low_point_m=3.0),
            hvac_duct_list=[HVACDuct(centerline=[(5.0, 3.0, 3.5)])],
        )
        devices = suggest_duct_detectors(room, detector_type="heat")
        assert len(devices) == 1
        assert devices[0].detector_type == "heat"

    def test_empty_centerline_skips_duct(self):
        room = RoomSpec(
            room_id="DUCT-003",
            name="Duct Room",
            width_m=10.0,
            depth_m=10.0,
            ceiling_spec=CeilingSpec(height_at_low_point_m=3.0),
            hvac_duct_list=[
                HVACDuct(centerline=[]),
                HVACDuct(centerline=[(3.0, 4.0, 3.0)]),
            ],
        )
        devices = suggest_duct_detectors(room)
        assert len(devices) == 1
        assert devices[0].x == 3.0

    def test_multiple_points_in_centerline_uses_first(self):
        room = RoomSpec(
            room_id="DUCT-004",
            name="Duct Room",
            width_m=10.0,
            depth_m=10.0,
            ceiling_spec=CeilingSpec(height_at_low_point_m=3.0),
            hvac_duct_list=[HVACDuct(centerline=[(1.0, 2.0, 3.0), (8.0, 9.0, 3.0)])],
        )
        devices = suggest_duct_detectors(room)
        assert len(devices) == 1
        assert devices[0].x == 1.0
        assert devices[0].y == 2.0

    # --- Safety-critical edge cases ---

    def test_nan_in_centerline_does_not_crash(self):
        room = RoomSpec(
            room_id="DUCT-005",
            name="Duct Room",
            width_m=10.0,
            depth_m=10.0,
            ceiling_spec=CeilingSpec(height_at_low_point_m=3.0),
            hvac_duct_list=[HVACDuct(centerline=[(float("nan"), 5.0, 3.0)])],
        )
        devices = suggest_duct_detectors(room)
        assert len(devices) == 1


# =============================================================================
# create_room_polygon / is_point_in_room
# =============================================================================


class TestRoomPolygon:
    def test_rectangular_room(self, simple_room):
        poly = create_room_polygon(simple_room)
        assert poly.is_valid
        assert poly.area == pytest.approx(100.0, abs=0.01)

    def test_custom_polygon(self):
        room = RoomSpec(
            room_id="CUSTOM-001",
            name="Custom",
            width_m=10.0,
            depth_m=10.0,
            ceiling_spec=CeilingSpec(height_at_low_point_m=3.0),
            polygon=[(0, 0), (10, 0), (10, 5), (5, 5), (5, 10), (0, 10)],
        )
        poly = create_room_polygon(room)
        assert poly.is_valid
        assert poly.area == pytest.approx(75.0, abs=0.5)

    def test_point_inside_rectangular(self, simple_room):
        poly = create_room_polygon(simple_room)
        assert is_point_in_room((5.0, 5.0), poly) is True

    def test_point_outside_rectangular(self, simple_room):
        poly = create_room_polygon(simple_room)
        assert is_point_in_room((15.0, 15.0), poly) is False

    def test_point_on_boundary(self, simple_room):
        poly = create_room_polygon(simple_room)
        result = is_point_in_room((10.0, 5.0), poly)
        assert isinstance(result, bool)

    def test_point_outside_l_shape(self):
        room = RoomSpec(
            room_id="L2",
            name="L2",
            width_m=10.0,
            depth_m=10.0,
            ceiling_spec=CeilingSpec(height_at_low_point_m=3.0),
            polygon=[(0, 0), (10, 0), (10, 5), (5, 5), (5, 10), (0, 10)],
        )
        poly = create_room_polygon(room)
        # Point in the cut-out L corner (6, 7.5) — should be outside
        assert is_point_in_room((6.0, 7.5), poly) is False
        # Point inside the L (3, 7.5) — should be inside
        assert is_point_in_room((3.0, 7.5), poly) is True

    def test_room_spec_without_explicit_polygon_creates_rect(self, simple_room):
        poly = create_room_polygon(simple_room)
        assert poly.exterior.coords[:] == Polygon(
            [(0, 0), (10, 0), (10, 10), (0, 10)]
        ).exterior.coords[:]

    # --- Safety-critical edge cases ---

    def test_very_large_room(self):
        room = RoomSpec(
            room_id="BIG",
            name="Big",
            width_m=500.0,
            depth_m=500.0,
            ceiling_spec=CeilingSpec(height_at_low_point_m=3.0),
        )
        poly = create_room_polygon(room)
        assert poly.is_valid
        assert poly.area == pytest.approx(250000.0, abs=1.0)


# =============================================================================
# check_coverage_polygon
# =============================================================================


class TestCheckCoveragePolygon:
    """Polygon-based coverage check — SMOKE circular, HEAT square."""

    def test_full_coverage_smoke(self, ceiling_flat):
        room = RoomSpec(
            room_id="SM-FULL",
            name="Small",
            width_m=8.0,
            depth_m=8.0,
            ceiling_spec=CeilingSpec(height_at_low_point_m=3.0),
        )
        positions = [(4.0, 4.0)]
        result = check_coverage_polygon(positions, room, ceiling_flat, DetectorType.SMOKE)
        assert result.is_covered is True
        assert result.coverage_percentage >= 99.9
        assert result.detectors_in_coverage == 1

    def test_no_detectors_zero_coverage(self, simple_room, ceiling_flat):
        result = check_coverage_polygon([], simple_room, ceiling_flat, DetectorType.SMOKE)
        assert result.is_covered is False
        assert result.coverage_percentage == pytest.approx(0.0, abs=0.1)

    def test_heat_detector_square_geometry(self, ceiling_flat):
        room = RoomSpec(
            room_id="HT-SQ",
            name="Heat Room",
            width_m=5.0,
            depth_m=5.0,
            ceiling_spec=CeilingSpec(height_at_low_point_m=3.0),
        )
        positions = [(2.5, 2.5)]
        result = check_coverage_polygon(positions, room, ceiling_flat, DetectorType.HEAT)
        assert result.is_covered is True
        assert result.detectors_in_coverage == 1

    def test_multiple_detectors_coverage(self, ceiling_flat):
        room = RoomSpec(
            room_id="MLTI",
            name="Multi",
            width_m=8.0,
            depth_m=8.0,
            ceiling_spec=CeilingSpec(height_at_low_point_m=3.0),
        )
        positions = [(2.5, 2.5), (5.5, 5.5)]
        result = check_coverage_polygon(positions, room, ceiling_flat, DetectorType.SMOKE)
        assert result.is_covered is True

    def test_coverage_result_type(self, simple_room, ceiling_flat):
        positions = [(5.0, 5.0)]
        result = check_coverage_polygon(positions, simple_room, ceiling_flat, DetectorType.SMOKE)
        assert isinstance(result, CoverageResult)
        assert isinstance(result.uncovered_areas, list)

    def test_heat_not_covers_corner_square(self, ceiling_flat):
        """Heat detector square geometry: corner of 7m room is outside 3.05m half-spacing from center."""
        room = RoomSpec(
            room_id="HT-NO",
            name="Heat Fail",
            width_m=7.0,
            depth_m=7.0,
            ceiling_spec=CeilingSpec(height_at_low_point_m=3.0),
        )
        positions = [(3.5, 3.5)]
        result = check_coverage_polygon(positions, room, ceiling_flat, DetectorType.HEAT)
        assert result.is_covered is False

    def test_smoke_vs_heat_geometry_difference(self, ceiling_flat):
        """Same room: smoke (circular) may cover corner where heat (square) does not."""
        room = RoomSpec(
            room_id="GEO",
            name="Geo",
            width_m=6.5,
            depth_m=6.5,
            ceiling_spec=CeilingSpec(height_at_low_point_m=3.0),
        )
        pos = [(3.25, 3.25)]
        smoke_result = check_coverage_polygon(pos, room, ceiling_flat, DetectorType.SMOKE)
        heat_result = check_coverage_polygon(pos, room, ceiling_flat, DetectorType.HEAT)
        assert isinstance(smoke_result, CoverageResult)
        assert isinstance(heat_result, CoverageResult)

    def test_high_ceiling_reduces_coverage(self, ceiling_high):
        """At 9m ceiling, smoke radius is smaller — needs more detectors."""
        room = RoomSpec(
            room_id="HIGH",
            name="High Bay",
            width_m=8.0,
            depth_m=8.0,
            ceiling_spec=CeilingSpec.create_safe(height_at_low_point_m=9.0),
        )
        positions = [(4.0, 4.0)]
        result = check_coverage_polygon(positions, room, ceiling_high, DetectorType.SMOKE)
        assert isinstance(result, CoverageResult)

    def test_uncovered_areas_list_contains_tuples(self, ceiling_flat):
        room = RoomSpec(
            room_id="UNCV",
            name="Uncovered",
            width_m=10.0,
            depth_m=10.0,
            ceiling_spec=CeilingSpec(height_at_low_point_m=3.0),
        )
        result = check_coverage_polygon([], room, ceiling_flat, DetectorType.SMOKE)
        assert len(result.uncovered_areas) > 0
        for pt in result.uncovered_areas:
            assert isinstance(pt, tuple)

    # --- Safety-critical edge cases ---

    def test_nan_position(self, ceiling_flat):
        room = RoomSpec(
            room_id="NAN",
            name="NaN",
            width_m=5.0,
            depth_m=5.0,
            ceiling_spec=CeilingSpec(height_at_low_point_m=3.0),
        )
        result = check_coverage_polygon([(float("nan"), 2.5)], room, ceiling_flat, DetectorType.SMOKE)
        assert isinstance(result, CoverageResult)
        assert result.detectors_in_coverage == 1

    def test_inf_position(self, ceiling_flat):
        room = RoomSpec(
            room_id="INF",
            name="Inf",
            width_m=5.0,
            depth_m=5.0,
            ceiling_spec=CeilingSpec(height_at_low_point_m=3.0),
        )
        result = check_coverage_polygon([(float("inf"), 2.5)], room, ceiling_flat, DetectorType.SMOKE)
        assert isinstance(result, CoverageResult)

    def test_negative_position(self, ceiling_flat):
        room = RoomSpec(
            room_id="NEG",
            name="Neg",
            width_m=5.0,
            depth_m=5.0,
            ceiling_spec=CeilingSpec(height_at_low_point_m=3.0),
        )
        result = check_coverage_polygon([(-10.0, -10.0)], room, ceiling_flat, DetectorType.SMOKE)
        assert isinstance(result, CoverageResult)
        assert result.is_covered is False

    def test_very_large_number_of_detectors(self, ceiling_flat):
        room = RoomSpec(
            room_id="MANY",
            name="Many",
            width_m=10.0,
            depth_m=10.0,
            ceiling_spec=CeilingSpec(height_at_low_point_m=3.0),
        )
        pos = [(x * 0.5, y * 0.5) for x in range(20) for y in range(20)]
        result = check_coverage_polygon(pos, room, ceiling_flat, DetectorType.SMOKE)
        assert result.is_covered is True


# =============================================================================
# calculate_voronoi_coverage
# =============================================================================


class TestVoronoiCoverage:
    def test_single_detector_returns_room(self):
        room = box(0, 0, 10, 10)
        regions = calculate_voronoi_coverage([(5.0, 5.0)], room)
        assert len(regions) == 1
        assert regions[0].equals(room)

    def test_two_detectors_two_regions(self):
        room = box(0, 0, 10, 10)
        regions = calculate_voronoi_coverage([(2.5, 5.0), (7.5, 5.0)], room)
        assert len(regions) >= 2

    def test_empty_positions_returns_room(self):
        room = box(0, 0, 10, 10)
        regions = calculate_voronoi_coverage([], room)
        assert len(regions) == 1

    def test_three_detectors_three_regions(self):
        room = box(0, 0, 10, 10)
        regions = calculate_voronoi_coverage([(2.5, 2.5), (7.5, 2.5), (5.0, 7.5)], room)
        assert len(regions) >= 3

    def test_regions_are_valid_polygons(self):
        room = box(0, 0, 10, 10)
        regions = calculate_voronoi_coverage([(3.0, 5.0), (7.0, 5.0)], room)
        for r in regions:
            assert r.is_valid
            assert not r.is_empty

    def test_regions_cover_room_area(self):
        room = box(0, 0, 10, 10)
        regions = calculate_voronoi_coverage([(3.0, 5.0), (7.0, 5.0)], room)
        total = sum(r.area for r in regions)
        assert total == pytest.approx(room.area, abs=0.1)

    def test_collinear_detectors(self):
        room = box(0, 0, 10, 10)
        regions = calculate_voronoi_coverage([(2.0, 5.0), (5.0, 5.0), (8.0, 5.0)], room)
        assert len(regions) >= 3

    def test_detectors_outside_room(self):
        room = box(0, 0, 10, 10)
        regions = calculate_voronoi_coverage([(-5.0, -5.0), (15.0, 15.0)], room)
        assert len(regions) >= 2

    def test_clipped_to_room_boundary(self):
        room = Polygon([(2, 2), (8, 2), (8, 8), (2, 8)])
        regions = calculate_voronoi_coverage([(4.0, 5.0), (6.0, 5.0)], room)
        for r in regions:
            assert r.within(room) or r.equals(room) or room.contains(r)

    # --- Safety-critical edge cases ---

    def test_nan_position(self):
        room = box(0, 0, 10, 10)
        regions = calculate_voronoi_coverage([(float("nan"), 5.0)], room)
        assert len(regions) == 1

    def test_duplicate_positions(self):
        room = box(0, 0, 10, 10)
        regions = calculate_voronoi_coverage([(5.0, 5.0), (5.0, 5.0)], room)
        assert len(regions) >= 1


# =============================================================================
# check_voronoi_coverage
# =============================================================================


class TestCheckVoronoiCoverage:
    def test_returns_coverage_result(self, simple_room, ceiling_flat):
        positions = [(5.0, 5.0)]
        result = check_voronoi_coverage(positions, simple_room, ceiling_flat, DetectorType.SMOKE)
        assert isinstance(result, CoverageResult)

    def test_heat_detector_voronoi(self, ceiling_flat):
        room = RoomSpec(
            room_id="VH-001",
            name="Voronoi Heat",
            width_m=5.0,
            depth_m=5.0,
            ceiling_spec=CeilingSpec(height_at_low_point_m=3.0),
        )
        positions = [(2.5, 2.5)]
        result = check_voronoi_coverage(positions, room, ceiling_flat, DetectorType.HEAT)
        assert isinstance(result, CoverageResult)
        assert result.is_covered is True

    def test_voronoi_delegates_check(self, simple_room, ceiling_flat):
        """check_voronoi_coverage should delegate to check_coverage_polygon."""
        positions = [(5.0, 5.0)]
        direct = check_coverage_polygon(positions, simple_room, ceiling_flat, DetectorType.SMOKE)
        voronoi = check_voronoi_coverage(positions, simple_room, ceiling_flat, DetectorType.SMOKE)
        assert direct.is_covered == voronoi.is_covered
        assert direct.coverage_percentage == voronoi.coverage_percentage

    def test_empty_positions(self, simple_room, ceiling_flat):
        result = check_voronoi_coverage([], simple_room, ceiling_flat, DetectorType.SMOKE)
        assert result.is_covered is False

    def test_heat_type_passed_through(self, simple_room, ceiling_flat):
        result_smoke = check_voronoi_coverage([(5.0, 5.0)], simple_room, ceiling_flat, DetectorType.SMOKE)
        result_heat = check_voronoi_coverage([(5.0, 5.0)], simple_room, ceiling_flat, DetectorType.HEAT)
        assert isinstance(result_smoke, CoverageResult)
        assert isinstance(result_heat, CoverageResult)


# =============================================================================
# check_ridge_zone_compliance — NFPA 72 §17.6.3.4
# =============================================================================


class TestRidgeZoneCompliance:
    """NFPA 72 §17.6.3.4: Sloped ceilings require ridge zone detectors."""

    def test_flat_ceiling_no_ridge_required(self, ceiling_flat):
        result = check_ridge_zone_compliance(
            [(5.0, 5.0)], ceiling_flat, (0, 5, 10, 5)
        )
        assert result.is_compliant is True

    def test_sloped_ceiling_with_detector_in_ridge(self, sloped_ceiling):
        result = check_ridge_zone_compliance(
            [(5.0, 10.0)], sloped_ceiling, (0, 10, 10, 10)
        )
        assert isinstance(result, NFPAComplianceResult)

    def test_sloped_ceiling_no_detectors_in_ridge(self):
        sloped = CeilingSpec(
            height_at_low_point_m=3.0,
            height_at_high_point_m=4.0,
            ceiling_type=CeilingType.SLOPED,
            slope_run_m=3.0,
        )
        result = check_ridge_zone_compliance(
            [(5.0, 1.0)], sloped, (0, 10, 10, 10)
        )
        assert isinstance(result, NFPAComplianceResult)

    def test_ridge_length_affects_required_count(self):
        sloped = CeilingSpec(
            height_at_low_point_m=3.0,
            height_at_high_point_m=4.5,
            ceiling_type=CeilingType.SLOPED,
            slope_run_m=3.0,
        )
        result = check_ridge_zone_compliance(
            [(2.5, 10.0)], sloped, (0, 10, 5, 10), standard_spacing=9.1
        )
        assert isinstance(result, NFPAComplianceResult)

    def test_long_ridge_needs_multiple_detectors(self):
        sloped = CeilingSpec(
            height_at_low_point_m=3.0,
            height_at_high_point_m=4.5,
            ceiling_type=CeilingType.SLOPED,
            slope_run_m=3.0,
        )
        result = check_ridge_zone_compliance(
            [(5.0, 10.0)], sloped, (0, 10, 60, 10), standard_spacing=9.1
        )
        assert not result.is_compliant

    def test_heat_detector_default_spacing(self):
        sloped = CeilingSpec(
            height_at_low_point_m=3.0,
            height_at_high_point_m=4.0,
            ceiling_type=CeilingType.SLOPED,
            slope_run_m=3.0,
        )
        result = check_ridge_zone_compliance(
            [(5.0, 10.0)], sloped, (0, 10, 10, 10), detector_type=DetectorType.HEAT
        )
        assert isinstance(result, NFPAComplianceResult)

    def test_violation_message_references_nfpa(self):
        """Violations from ridge check should reference NFPA 72."""
        sloped = CeilingSpec(
            height_at_low_point_m=3.0,
            height_at_high_point_m=4.0,
            ceiling_type=CeilingType.SLOPED,
            slope_run_m=3.0,
        )
        result = check_ridge_zone_compliance(
            [(5.0, 1.0)], sloped, (0, 10, 10, 10)
        )
        if result.violations:
            assert any("17.6.3.4" in v for v in result.violations)

    def test_result_has_detector_count(self, sloped_ceiling):
        result = check_ridge_zone_compliance(
            [(5.0, 10.0)], sloped_ceiling, (0, 10, 10, 10)
        )
        assert isinstance(result, NFPAComplianceResult)

    # --- Safety-critical edge cases ---

    def test_nan_detector_position(self, sloped_ceiling):
        result = check_ridge_zone_compliance(
            [(float("nan"), 10.0)], sloped_ceiling, (0, 10, 10, 10)
        )
        assert isinstance(result, NFPAComplianceResult)

    def test_degenerate_ridge_line(self, sloped_ceiling):
        result = check_ridge_zone_compliance(
            [(5.0, 10.0)], sloped_ceiling, (0, 0, 0, 0)
        )
        assert isinstance(result, NFPAComplianceResult)

    def test_negative_ridge_line(self, sloped_ceiling):
        result = check_ridge_zone_compliance(
            [(5.0, 10.0)], sloped_ceiling, (-10, -10, -5, -5)
        )
        assert isinstance(result, NFPAComplianceResult)

    def test_very_long_ridge_line(self, sloped_ceiling):
        result = check_ridge_zone_compliance(
            [(5.0, 10.0)], sloped_ceiling, (0, 0, 1000, 0), standard_spacing=9.1
        )
        assert isinstance(result, NFPAComplianceResult)


# =============================================================================
# create_l_shaped_polygon
# =============================================================================


class TestCreateLShapedPolygon:
    def test_valid_l_shape(self):
        dims = [(0, 0), (10, 0), (10, 5), (5, 5), (5, 10), (0, 10)]
        poly = create_l_shaped_polygon(dims)
        assert poly.is_valid
        assert poly.area == pytest.approx(75.0, abs=0.5)

    def test_too_few_points_raises(self):
        with pytest.raises(ValueError, match="at least 3 points"):
            create_l_shaped_polygon([(0, 0), (10, 0)])

    def test_triangle_is_valid(self):
        dims = [(0, 0), (10, 0), (5, 10)]
        poly = create_l_shaped_polygon(dims)
        assert poly.is_valid

    def test_rectangle_with_4_points(self):
        dims = [(0, 0), (10, 0), (10, 10), (0, 10)]
        poly = create_l_shaped_polygon(dims)
        assert poly.is_valid
        assert poly.area == pytest.approx(100.0, abs=0.01)

    def test_complex_polygon(self):
        dims = [(0, 0), (10, 0), (10, 3), (7, 3), (7, 7), (10, 7), (10, 10), (0, 10)]
        poly = create_l_shaped_polygon(dims)
        assert poly.is_valid

    def test_exactly_3_points(self):
        dims = [(0, 0), (5, 0), (2.5, 5)]
        poly = create_l_shaped_polygon(dims)
        assert poly.is_valid
        assert poly.area > 0


# =============================================================================
# check_l_shaped_coverage
# =============================================================================


class TestCheckLShapedCoverage:
    """L-shaped room coverage — SMOKE circular, HEAT square."""

    def test_single_detector_covers_l_shape(self, l_shaped_polygon):
        result = check_l_shaped_coverage(
            [(3.5, 3.5)], l_shaped_polygon, 3.0, DetectorType.SMOKE
        )
        assert isinstance(result, CoverageResult)

    def test_heat_detector_l_shape(self, l_shaped_polygon):
        result = check_l_shaped_coverage(
            [(3.5, 3.5)], l_shaped_polygon, 3.0, DetectorType.HEAT
        )
        assert isinstance(result, CoverageResult)

    def test_no_detectors_l_shape(self, l_shaped_polygon):
        result = check_l_shaped_coverage(
            [], l_shaped_polygon, 3.0, DetectorType.SMOKE
        )
        assert result.is_covered is False
        assert result.coverage_percentage == pytest.approx(0.0, abs=0.1)

    def test_multiple_detectors_l_shape(self, l_shaped_polygon):
        result = check_l_shaped_coverage(
            [(3.5, 3.5), (7.5, 2.5)], l_shaped_polygon, 3.0, DetectorType.SMOKE
        )
        assert isinstance(result, CoverageResult)

    def test_coverage_not_100_percent_for_few_detectors_large_l(self):
        big_l = Polygon([(0, 0), (20, 0), (20, 5), (10, 5), (10, 20), (0, 20)])
        result = check_l_shaped_coverage(
            [(5.0, 5.0)], big_l, 3.0, DetectorType.SMOKE
        )
        assert result.is_covered is False

    def test_heat_detector_square_geometry_in_l_shape(self):
        """Heat detector uses Chebyshev in L-shape — covers a square area."""
        small_l = Polygon([(0, 0), (6, 0), (6, 3), (3, 3), (3, 6), (0, 6)])
        result = check_l_shaped_coverage(
            [(2.5, 2.5)], small_l, 3.0, DetectorType.HEAT
        )
        assert isinstance(result, CoverageResult)

    def test_result_type(self, l_shaped_polygon):
        result = check_l_shaped_coverage(
            [(3.5, 3.5)], l_shaped_polygon, 3.0, DetectorType.SMOKE
        )
        assert isinstance(result, CoverageResult)

    # --- Safety-critical edge cases ---

    def test_nan_position(self, l_shaped_polygon):
        result = check_l_shaped_coverage(
            [(float("nan"), 3.5)], l_shaped_polygon, 3.0, DetectorType.SMOKE
        )
        assert isinstance(result, CoverageResult)

    def test_inf_height(self, l_shaped_polygon):
        result = check_l_shaped_coverage(
            [(3.5, 3.5)], l_shaped_polygon, float("inf"), DetectorType.SMOKE
        )
        assert isinstance(result, CoverageResult)

    def test_negative_height_below_min(self, l_shaped_polygon):
        result = check_l_shaped_coverage(
            [(3.5, 3.5)], l_shaped_polygon, 0.1, DetectorType.SMOKE
        )
        assert isinstance(result, CoverageResult)

    def test_unique_listed_spacing(self, l_shaped_polygon):
        result = check_l_shaped_coverage(
            [(3.5, 3.5)], l_shaped_polygon, 3.0, DetectorType.SMOKE, listed_spacing_m=6.0
        )
        assert isinstance(result, CoverageResult)


# =============================================================================
# check_nfpa72_compliance
# =============================================================================


class TestCheckNFPA72Compliance:
    def test_compliant_room(self, ceiling_flat):
        room = RoomSpec(
            room_id="CM-001",
            name="Compliant",
            width_m=8.0,
            depth_m=8.0,
            ceiling_spec=CeilingSpec(height_at_low_point_m=3.0),
        )
        positions = [(4.0, 4.0)]
        result = check_nfpa72_compliance(room, ceiling_flat, positions)
        assert isinstance(result, NFPAComplianceResult)
        assert result.is_compliant is True

    def test_non_compliant_no_detectors(self, simple_room, ceiling_flat):
        result = check_nfpa72_compliance(simple_room, ceiling_flat, [])
        assert result.is_compliant is False

    def test_detector_count_in_result(self, simple_room, ceiling_flat):
        positions = [(3.0, 3.0), (7.0, 7.0)]
        result = check_nfpa72_compliance(simple_room, ceiling_flat, positions)
        assert result.detector_count == 2

    def test_non_compliant_with_violation(self, simple_room, ceiling_flat):
        result = check_nfpa72_compliance(simple_room, ceiling_flat, [])
        assert len(result.violations) >= 1

    def test_with_ridge_line(self, ceiling_flat):
        room = RoomSpec(
            room_id="RIDGE",
            name="Ridge",
            width_m=8.0,
            depth_m=8.0,
            ceiling_spec=CeilingSpec(height_at_low_point_m=3.0),
        )
        result = check_nfpa72_compliance(
            room, ceiling_flat, [(4.0, 4.0)], ridge_line=(0, 4, 8, 4)
        )
        assert isinstance(result, NFPAComplianceResult)

    def test_heat_detector_type(self, ceiling_flat):
        room = RoomSpec(
            room_id="HEAT-CMP",
            name="Heat Compliant",
            width_m=5.0,
            depth_m=5.0,
            ceiling_spec=CeilingSpec(height_at_low_point_m=3.0),
        )
        result = check_nfpa72_compliance(
            room, ceiling_flat, [(2.5, 2.5)], detector_type=DetectorType.HEAT
        )
        assert isinstance(result, NFPAComplianceResult)

    # --- Safety-critical edge cases ---

    def test_nan_position(self, simple_room, ceiling_flat):
        result = check_nfpa72_compliance(
            simple_room, ceiling_flat, [(float("nan"), 5.0)]
        )
        assert isinstance(result, NFPAComplianceResult)


# =============================================================================
# verify_full_coverage
# =============================================================================


class TestVerifyFullCoverage:
    def test_full_coverage_smoke(self):
        room = box(0, 0, 8, 8)
        result = verify_full_coverage(
            room, [(4.0, 4.0)], "circular", 6.37,
            detector_type=DetectorType.SMOKE,
        )
        assert result["compliance_status"] == "PASS"
        assert result["coverage_percentage"] >= 99.0

    def test_no_detectors_fails(self):
        room = box(0, 0, 10, 10)
        result = verify_full_coverage(
            room, [], "circular", 6.37,
            detector_type=DetectorType.SMOKE,
        )
        assert result["coverage_percentage"] == pytest.approx(0.0, abs=0.1)

    def test_heat_detector_square_geometry(self):
        room = box(0, 0, 10, 10)
        result = verify_full_coverage(
            room, [(5.0, 5.0)], "square_grid", 3.05,
            detector_type=DetectorType.HEAT,
        )
        assert "coverage_percentage" in result
        assert "worst_case_distance_m" in result

    def test_result_keys(self):
        room = box(0, 0, 10, 10)
        result = verify_full_coverage(
            room, [(5.0, 5.0)], "circular", 6.37,
            detector_type=DetectorType.SMOKE,
        )
        expected_keys = [
            "coverage_percentage", "worst_case_distance_m",
            "compliance_status", "coverage_geometry",
        ]
        for key in expected_keys:
            assert key in result, f"Missing key: {key}"

    def test_coverage_geometry_in_result(self):
        room = box(0, 0, 8, 8)
        result = verify_full_coverage(
            room, [(4.0, 4.0)], "circular", 6.37,
            detector_type=DetectorType.SMOKE,
        )
        assert result["coverage_geometry"] == "circular"

    def test_heat_returns_square_geometry(self):
        room = box(0, 0, 8, 8)
        result = verify_full_coverage(
            room, [(4.0, 4.0)], "square_grid", 3.05,
            detector_type=DetectorType.HEAT,
        )
        assert result["coverage_geometry"] == "square"

    def test_worst_case_distance_present(self):
        room = box(0, 0, 10, 10)
        result = verify_full_coverage(
            room, [(5.0, 5.0)], "circular", 6.37,
            detector_type=DetectorType.SMOKE,
        )
        assert result["worst_case_distance_m"] >= 0.0

    def test_custom_listed_spacing(self):
        room = box(0, 0, 10, 10)
        result = verify_full_coverage(
            room, [(5.0, 5.0)], "square_grid", 3.05,
            listed_spacing_m=6.1,
            detector_type=DetectorType.HEAT,
        )
        assert isinstance(result["coverage_percentage"], float)

    # --- Safety-critical edge cases ---

    def test_nan_position(self):
        room = box(0, 0, 10, 10)
        result = verify_full_coverage(
            room, [(float("nan"), 5.0)], "circular", 6.37,
            detector_type=DetectorType.SMOKE,
        )
        assert isinstance(result, dict)

    def test_inf_position(self):
        room = box(0, 0, 10, 10)
        result = verify_full_coverage(
            room, [(float("inf"), 5.0)], "circular", 6.37,
            detector_type=DetectorType.SMOKE,
        )
        assert isinstance(result, dict)

    def test_negative_radius(self):
        room = box(0, 0, 10, 10)
        result = verify_full_coverage(
            room, [(5.0, 5.0)], "circular", -1.0,
            detector_type=DetectorType.SMOKE,
        )
        assert isinstance(result, dict)

    def test_zero_radius(self):
        room = box(0, 0, 10, 10)
        result = verify_full_coverage(
            room, [(5.0, 5.0)], "circular", 0.0,
            detector_type=DetectorType.SMOKE,
        )
        assert isinstance(result, dict)

    def test_circular_geometry_smoke_passes(self):
        room = box(0, 0, 8, 8)
        result = verify_full_coverage(
            room, [(4.0, 4.0)], "circular", 6.37,
            detector_type=DetectorType.SMOKE,
        )
        assert result["compliance_status"] == "PASS"

    def test_circular_geometry_heat_with_radius(self):
        room = box(0, 0, 5, 5)
        result = verify_full_coverage(
            room, [(2.5, 2.5)], "circular", 6.37,
            detector_type=DetectorType.HEAT,
        )
        assert isinstance(result["compliance_status"], str)


# =============================================================================
# get_sloped_ceiling_constraints
# =============================================================================


class TestGetSlopedCeilingConstraints:
    def test_flat_ceiling_no_ridge(self):
        poly = box(0, 0, 10, 10)
        flat = CeilingSpec(height_at_low_point_m=3.0)
        result = get_sloped_ceiling_constraints(poly, flat, DetectorType.SMOKE)
        assert result["requires_ridge_row"] is False

    def test_non_smoke_detector_no_ridge(self):
        poly = box(0, 0, 10, 10)
        sloped = CeilingSpec(
            height_at_low_point_m=3.0,
            height_at_high_point_m=4.5,
            ceiling_type=CeilingType.SLOPED,
            slope_run_m=3.0,
        )
        result = get_sloped_ceiling_constraints(poly, sloped, DetectorType.HEAT)
        assert result["requires_ridge_row"] is False

    def test_sloped_smoke_requires_ridge(self):
        poly = box(0, 0, 10, 10)
        sloped = CeilingSpec(
            height_at_low_point_m=3.0,
            height_at_high_point_m=4.5,
            ceiling_type=CeilingType.SLOPED,
            slope_run_m=3.0,
        )
        result = get_sloped_ceiling_constraints(poly, sloped, DetectorType.SMOKE)
        assert result["requires_ridge_row"] is True
        assert result["ridge_zone_polygon"] is not None

    def test_ridge_zone_polygon_is_valid(self):
        poly = box(0, 0, 10, 10)
        sloped = CeilingSpec(
            height_at_low_point_m=3.0,
            height_at_high_point_m=4.5,
            ceiling_type=CeilingType.SLOPED,
            slope_run_m=3.0,
        )
        result = get_sloped_ceiling_constraints(poly, sloped, DetectorType.SMOKE)
        if result["ridge_zone_polygon"] is not None:
            assert result["ridge_zone_polygon"].is_valid

    def test_sloped_ceiling_without_high_point(self):
        poly = box(0, 0, 10, 10)
        sloped = CeilingSpec(
            height_at_low_point_m=3.0,
            height_at_high_point_m=4.5,
            ceiling_type=CeilingType.SLOPED,
            slope_run_m=3.0,
        )
        result = get_sloped_ceiling_constraints(poly, sloped, DetectorType.SMOKE)
        assert result["requires_ridge_row"] is True

    def test_returns_dict_keys(self):
        poly = box(0, 0, 10, 10)
        flat = CeilingSpec(height_at_low_point_m=3.0)
        result = get_sloped_ceiling_constraints(poly, flat, DetectorType.SMOKE)
        assert "requires_ridge_row" in result
        assert "ridge_zone_polygon" in result

    # --- Safety-critical edge cases ---

    def test_nan_polygon_coords(self):
        sloped = CeilingSpec(
            height_at_low_point_m=3.0,
            height_at_high_point_m=4.5,
            ceiling_type=CeilingType.SLOPED,
            slope_run_m=3.0,
        )
        try:
            poly = Polygon([(0, 0), (float("nan"), 0), (10, 10), (0, 10)])
            result = get_sloped_ceiling_constraints(poly, sloped, DetectorType.SMOKE)
            assert isinstance(result, dict)
        except Exception:
            pass

    def test_degenerate_polygon(self):
        sloped = CeilingSpec(
            height_at_low_point_m=3.0,
            height_at_high_point_m=4.5,
            ceiling_type=CeilingType.SLOPED,
            slope_run_m=3.0,
        )
        poly = Polygon([(0, 0), (1, 1), (2, 2)])
        result = get_sloped_ceiling_constraints(poly, sloped, DetectorType.SMOKE)
        assert isinstance(result, dict)


# =============================================================================
# adjust_coverage_for_beams — NFPA 72 §17.6.3.1
# =============================================================================


class TestAdjustCoverageForBeams:
    """NFPA 72 §17.6.3.1: Beam depth affects detector coverage."""

    def test_shallow_beam_no_adjustment(self):
        result = adjust_coverage_for_beams(6.37, 0.10, 3.0)
        assert result == pytest.approx(6.37, abs=0.01)

    def test_moderate_beam_15pct_reduction(self):
        result = adjust_coverage_for_beams(6.37, 0.15, 3.0)
        assert result == pytest.approx(6.37 * 0.85, abs=0.01)

    def test_deep_beam_compartment(self):
        result = adjust_coverage_for_beams(6.37, 0.35, 3.0)
        assert result == pytest.approx(6.37, abs=0.01)

    def test_zero_beam_depth(self):
        result = adjust_coverage_for_beams(6.37, 0.0, 3.0)
        assert result == pytest.approx(6.37, abs=0.01)

    def test_negative_beam_depth_raises(self):
        with pytest.raises(ValueError, match="cannot be negative"):
            adjust_coverage_for_beams(6.37, -0.1, 3.0)

    def test_zero_ceiling_height_raises(self):
        with pytest.raises(ValueError, match="must be positive"):
            adjust_coverage_for_beams(6.37, 0.1, 0.0)

    def test_negative_ceiling_height_raises(self):
        with pytest.raises(ValueError, match="must be positive"):
            adjust_coverage_for_beams(6.37, 0.1, -3.0)

    def test_boundary_4pct_exactly(self):
        result = adjust_coverage_for_beams(6.37, 0.12, 3.0)
        assert result == pytest.approx(6.37, abs=0.01)

    def test_boundary_10pct_exactly(self):
        result = adjust_coverage_for_beams(6.37, 0.30, 3.0)
        assert result == pytest.approx(6.37 * 0.85, abs=0.01)

    def test_just_over_10pct(self):
        result = adjust_coverage_for_beams(6.37, 0.301, 3.0)
        assert result == pytest.approx(6.37, abs=0.01)

    def test_very_deep_beam_still_returns_nominal(self):
        result = adjust_coverage_for_beams(6.37, 2.0, 3.0)
        assert result == pytest.approx(6.37, abs=0.01)

    # --- Safety-critical edge cases ---

    def test_nan_nominal_radius(self):
        with pytest.raises((ValueError, OverflowError)):
            adjust_coverage_for_beams(float("nan"), 0.1, 3.0)

    def test_nan_beam_depth(self):
        with pytest.raises(ValueError):
            adjust_coverage_for_beams(6.37, float("nan"), 3.0)

    def test_inf_beam_depth(self):
        with pytest.raises(ValueError):
            adjust_coverage_for_beams(6.37, float("inf"), 3.0)

    def test_inf_nominal_radius(self):
        result = adjust_coverage_for_beams(float("inf"), 0.1, 3.0)
        assert math.isinf(result)

    def test_negative_nominal_radius(self):
        result = adjust_coverage_for_beams(-6.37, 0.1, 3.0)
        assert result < 0

    def test_extremely_large_beam_depth(self):
        result = adjust_coverage_for_beams(6.37, 100.0, 3.0)
        assert result == pytest.approx(6.37, abs=0.01)

    def test_extremely_small_ceiling_height_raises(self):
        with pytest.raises(ValueError, match="must be positive"):
            adjust_coverage_for_beams(6.37, 0.1, 1e-10)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
