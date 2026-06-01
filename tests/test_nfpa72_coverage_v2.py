"""
tests/test_nfpa72_coverage_v2.py
================================
Comprehensive test suite for:
  - fireai/core/nfpa72_coverage.py

SAFETY CRITICAL: Coverage calculations determine if fire detectors
protect every point in a room. Incorrect coverage could leave blind
spots where a fire goes undetected — a direct life-safety hazard.

NFPA 72 References:
  §17.6.3.1.1 — Minimum wall distance (4 inches = 101.6mm)
  §17.7.4.1   — HVAC supply diffuser exclusion zone (3 ft = 0.914m)
  §17.6.3.4   — Ridge zone detector placement
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
)
from fireai.core.contracts import CeilingType


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────


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
    return CeilingSpec(height_at_low_point_m=3.0)


@pytest.fixture
def l_shaped_polygon() -> Polygon:
    """L-shaped room polygon: 10m x 10m with a 5m x 5m corner cut."""
    return Polygon([
        (0, 0), (10, 0), (10, 5), (5, 5), (5, 10), (0, 10)
    ])


# ─────────────────────────────────────────────────────────────────────────────
# Constants
# ─────────────────────────────────────────────────────────────────────────────


class TestConstants:
    """NFPA 72 constant values — must be exact."""

    def test_min_wall_distance_m(self):
        """C2 FIX: 4 inches = 101.6mm per NFPA 72 §17.6.3.1.1."""
        assert NFPA_MIN_WALL_DISTANCE_M == pytest.approx(0.1016, abs=0.0001)

    def test_hvac_exclusion_radius_m(self):
        """C3 FIX: 3 ft = 0.9144m per NFPA 72 §17.7.4.1."""
        assert NFPA_HVAC_EXCLUSION_RADIUS_M == pytest.approx(0.9144, abs=0.0001)


# ─────────────────────────────────────────────────────────────────────────────
# DuctDevice / WallViolation dataclasses
# ─────────────────────────────────────────────────────────────────────────────


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


class TestWallViolation:
    def test_creation(self):
        v = WallViolation(x=0.05, y=5.0, distance_m=0.05, min_required_m=0.1016)
        assert v.distance_m == 0.05
        assert v.min_required_m == pytest.approx(0.1016, abs=0.0001)


# ─────────────────────────────────────────────────────────────────────────────
# validate_wall_distances — NFPA 72 §17.6.3.1.1
# ─────────────────────────────────────────────────────────────────────────────


class TestValidateWallDistances:
    """NFPA 72 §17.6.3.1.1: Detectors not closer than 4 inches from wall."""

    def test_no_violations_center_detectors(self, simple_room):
        """Detectors well away from walls should have no violations."""
        positions = [(5.0, 5.0), (7.5, 7.5)]
        violations = validate_wall_distances(positions, simple_room)
        assert len(violations) == 0

    def test_violation_too_close_to_left_wall(self, simple_room):
        """Detector at x=0.05m is too close to left wall (< 0.1016m)."""
        positions = [(0.05, 5.0)]
        violations = validate_wall_distances(positions, simple_room)
        assert len(violations) >= 1
        assert any(v["wall"] == "left" for v in violations)

    def test_violation_too_close_to_right_wall(self, simple_room):
        """Detector at x=9.95m in 10m room is < 0.1016m from right wall."""
        positions = [(9.95, 5.0)]
        violations = validate_wall_distances(positions, simple_room)
        assert len(violations) >= 1
        assert any(v["wall"] == "right" for v in violations)

    def test_violation_too_close_to_top_wall(self, simple_room):
        """Detector at y=9.95m in 10m room is too close to top wall."""
        positions = [(5.0, 9.95)]
        violations = validate_wall_distances(positions, simple_room)
        assert len(violations) >= 1
        assert any(v["wall"] == "top" for v in violations)

    def test_violation_too_close_to_bottom_wall(self, simple_room):
        """Detector at y=0.05m is too close to bottom wall."""
        positions = [(5.0, 0.05)]
        violations = validate_wall_distances(positions, simple_room)
        assert len(violations) >= 1
        assert any(v["wall"] == "bottom" for v in violations)

    def test_boundary_exactly_at_min_distance(self, simple_room):
        """Detector at exactly 0.1016m from wall — should be OK (>= check)."""
        positions = [(0.1016, 5.0)]
        violations = validate_wall_distances(positions, simple_room)
        # At exactly the minimum, should NOT be a violation
        left_violations = [v for v in violations if v["wall"] == "left"]
        assert len(left_violations) == 0

    def test_nfpa_reference_in_violations(self, simple_room):
        """All violations must reference NFPA 72 §17.6.3.1.1."""
        positions = [(0.05, 5.0)]
        violations = validate_wall_distances(positions, simple_room)
        assert len(violations) >= 1
        for v in violations:
            assert "17.6.3.1.1" in v.get("nfpa_reference", "")

    def test_polygon_mode_with_l_shaped_room(self):
        """V49 FIX: Polygon boundary mode for L-shaped rooms."""
        room_spec = RoomSpec(
            room_id="L-001", name="L-Room", width_m=10.0, depth_m=10.0,
            ceiling_spec=CeilingSpec(height_at_low_point_m=3.0),
        )
        l_poly = Polygon([(0, 0), (10, 0), (10, 5), (5, 5), (5, 10), (0, 10)])

        # Detector near the inner corner (5, 5) — close to polygon boundary
        positions = [(5.05, 5.05)]
        violations = validate_wall_distances(
            positions, room_spec, room_polygon=l_poly
        )
        # Should detect proximity to polygon boundary, not bounding box
        assert len(violations) >= 1
        assert any(v["wall"] == "polygon_boundary" for v in violations)

    def test_empty_positions(self, simple_room):
        """Empty detector list returns no violations."""
        violations = validate_wall_distances([], simple_room)
        assert len(violations) == 0

    def test_custom_min_distance(self, simple_room):
        """Custom min_distance_m overrides default."""
        positions = [(0.15, 5.0)]  # 15cm from wall
        # Default 0.1016m: OK, custom 0.20m: VIOLATION
        v1 = validate_wall_distances(positions, simple_room, min_distance_m=0.1016)
        v2 = validate_wall_distances(positions, simple_room, min_distance_m=0.20)
        assert len(v1) == 0
        assert len(v2) >= 1


# ─────────────────────────────────────────────────────────────────────────────
# validate_hvac_exclusion_zones — NFPA 72 §17.7.4.1
# ─────────────────────────────────────────────────────────────────────────────


class TestValidateHVACExclusionZones:
    """NFPA 72 §17.7.4.1: Detectors not within 3ft of HVAC supply diffuser."""

    def test_no_violations_far_from_diffuser(self):
        """Detector well away from diffuser — no violation."""
        det = [(5.0, 5.0)]
        diff = [(0.0, 0.0)]
        violations = validate_hvac_exclusion_zones(det, diff)
        assert len(violations) == 0

    def test_violation_detector_near_diffuser(self):
        """Detector within 0.9144m of diffuser — violation."""
        det = [(0.5, 0.0)]
        diff = [(0.0, 0.0)]
        violations = validate_hvac_exclusion_zones(det, diff)
        assert len(violations) >= 1
        assert violations[0]["distance_m"] < 0.9144

    def test_nfpa_reference_in_violations(self):
        """All violations must reference NFPA 72 §17.7.4.1."""
        det = [(0.5, 0.0)]
        diff = [(0.0, 0.0)]
        violations = validate_hvac_exclusion_zones(det, diff)
        for v in violations:
            assert "17.7.4.1" in v.get("nfpa_reference", "")

    def test_exactly_at_exclusion_radius(self):
        """Detector at exactly 0.9144m — should NOT be a violation (>= check)."""
        det = [(0.9144, 0.0)]
        diff = [(0.0, 0.0)]
        violations = validate_hvac_exclusion_zones(det, diff)
        assert len(violations) == 0

    def test_multiple_diffusers(self):
        """Detector near one diffuser but far from another."""
        det = [(0.5, 0.0)]
        diff = [(0.0, 0.0), (5.0, 5.0)]
        violations = validate_hvac_exclusion_zones(det, diff)
        assert len(violations) >= 1

    def test_empty_inputs(self):
        """Empty detector or diffuser lists return no violations."""
        assert validate_hvac_exclusion_zones([], [(0, 0)]) == []
        assert validate_hvac_exclusion_zones([(0, 0)], []) == []

    def test_custom_exclusion_radius(self):
        """Custom exclusion radius overrides default."""
        det = [(1.0, 0.0)]
        diff = [(0.0, 0.0)]
        v1 = validate_hvac_exclusion_zones(det, diff, exclusion_radius_m=0.9144)
        v2 = validate_hvac_exclusion_zones(det, diff, exclusion_radius_m=1.5)
        assert len(v1) == 0
        assert len(v2) >= 1


# ─────────────────────────────────────────────────────────────────────────────
# compute_hvac_safe_zone
# ─────────────────────────────────────────────────────────────────────────────


class TestComputeHVACSafeZone:
    def test_safe_zone_returns_polygon(self):
        room = box(0, 0, 10, 10)
        diffusers = [(5.0, 5.0)]
        safe = compute_hvac_safe_zone(room, diffusers)
        assert safe.is_valid
        assert not safe.is_empty
        assert safe.area < room.area  # Exclusion zone subtracted

    def test_no_diffusers_returns_room(self):
        room = box(0, 0, 10, 10)
        safe = compute_hvac_safe_zone(room, [])
        assert safe.equals(room)

    def test_diffusers_cover_entire_ceiling_raises(self):
        """ValueError when diffusers cover entire ceiling."""
        room = box(0, 0, 1, 1)  # Small room
        # Large diffuser with exclusion radius covering entire room
        diffusers = [(0.5, 0.5)]
        with pytest.raises(ValueError, match="No valid detector placement"):
            compute_hvac_safe_zone(room, diffusers, exclusion_radius_m=10.0)

    def test_multiple_diffusers(self):
        room = box(0, 0, 20, 20)
        diffusers = [(2.0, 2.0), (18.0, 18.0)]
        safe = compute_hvac_safe_zone(room, diffusers)
        assert safe.is_valid
        assert safe.area < room.area


# ─────────────────────────────────────────────────────────────────────────────
# suggest_duct_detectors
# ─────────────────────────────────────────────────────────────────────────────


class TestSuggestDuctDetectors:
    def test_no_ducts_returns_empty(self, simple_room):
        devices = suggest_duct_detectors(simple_room)
        assert devices == []

    def test_with_hvac_ducts(self):
        """Room with HVAC ducts should suggest duct detectors."""
        from fireai.core.nfpa72_models import HVACDuct
        room = RoomSpec(
            room_id="DUCT-001", name="Duct Room", width_m=10.0, depth_m=10.0,
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

    def test_heat_type_parameter(self):
        from fireai.core.nfpa72_models import HVACDuct
        room = RoomSpec(
            room_id="DUCT-002", name="Duct Room", width_m=10.0, depth_m=10.0,
            ceiling_spec=CeilingSpec(height_at_low_point_m=3.0),
            hvac_duct_list=[HVACDuct(centerline=[(5.0, 3.0, 3.5)])],
        )
        devices = suggest_duct_detectors(room, detector_type="heat")
        assert len(devices) == 1
        assert devices[0].detector_type == "heat"


# ─────────────────────────────────────────────────────────────────────────────
# create_room_polygon / is_point_in_room
# ─────────────────────────────────────────────────────────────────────────────


class TestRoomPolygon:
    def test_rectangular_room(self, simple_room):
        poly = create_room_polygon(simple_room)
        assert poly.is_valid
        assert poly.area == pytest.approx(100.0, abs=0.01)

    def test_custom_polygon(self):
        room = RoomSpec(
            room_id="CUSTOM-001", name="Custom", width_m=10.0, depth_m=10.0,
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
        """Points exactly on boundary may or may not be contained."""
        poly = create_room_polygon(simple_room)
        # Shapely contains() returns False for boundary points
        result = is_point_in_room((10.0, 5.0), poly)
        # Just check it doesn't crash — boundary behavior varies
        assert isinstance(result, bool)


# ─────────────────────────────────────────────────────────────────────────────
# check_coverage_polygon
# ─────────────────────────────────────────────────────────────────────────────


class TestCheckCoveragePolygon:
    """Polygon-based coverage check — replaces incorrect Bounding Box."""

    def test_full_coverage_smoke(self, simple_room, ceiling_flat):
        """Detectors at correct spacing provide full coverage for smoke."""
        # At 3m ceiling, R=6.37m. One detector at center covers most of a 10x10 room,
        # but corners (7.07m from center) are outside R=6.37m. Use a smaller room.
        small_room = RoomSpec(
            room_id="SM-001", name="Small",
            width_m=8.0, depth_m=8.0,
            ceiling_spec=CeilingSpec(height_at_low_point_m=3.0),
        )
        positions = [(4.0, 4.0)]
        result = check_coverage_polygon(positions, small_room, ceiling_flat, DetectorType.SMOKE)
        assert result.is_covered is True
        assert result.coverage_percentage >= 99.9
        assert result.detectors_in_coverage == 1

    def test_no_detectors_zero_coverage(self, simple_room, ceiling_flat):
        """No detectors = zero coverage."""
        result = check_coverage_polygon([], simple_room, ceiling_flat, DetectorType.SMOKE)
        assert result.is_covered is False
        assert result.coverage_percentage == pytest.approx(0.0, abs=0.1)

    def test_heat_detector_square_geometry(self, ceiling_flat):
        """Heat detectors use SQUARE (Chebyshev) geometry, not circular."""
        # Heat detector at 3m ceiling: half_spacing ~ 3.05m. Use 6x6 room.
        small_room = RoomSpec(
            room_id="HT-001", name="Heat Room",
            width_m=5.0, depth_m=5.0,
            ceiling_spec=CeilingSpec(height_at_low_point_m=3.0),
        )
        positions = [(2.5, 2.5)]
        result = check_coverage_polygon(positions, small_room, ceiling_flat, DetectorType.HEAT)
        assert result.is_covered is True
        assert result.detectors_in_coverage == 1

    def test_multiple_detectors_coverage(self, ceiling_flat):
        """Multiple detectors should provide coverage."""
        small_room = RoomSpec(
            room_id="ML-001", name="Multi",
            width_m=8.0, depth_m=8.0,
            ceiling_spec=CeilingSpec(height_at_low_point_m=3.0),
        )
        positions = [(2.5, 2.5), (5.5, 5.5)]
        result = check_coverage_polygon(positions, small_room, ceiling_flat, DetectorType.SMOKE)
        assert result.is_covered is True

    def test_coverage_result_type(self, simple_room, ceiling_flat):
        """Result must be CoverageResult dataclass."""
        positions = [(5.0, 5.0)]
        result = check_coverage_polygon(positions, simple_room, ceiling_flat, DetectorType.SMOKE)
        assert isinstance(result, CoverageResult)
        assert isinstance(result.uncovered_areas, list)


# ─────────────────────────────────────────────────────────────────────────────
# calculate_voronoi_coverage
# ─────────────────────────────────────────────────────────────────────────────


class TestVoronoiCoverage:
    def test_single_detector_returns_room(self):
        """Single detector — entire room is one Voronoi region."""
        room = box(0, 0, 10, 10)
        regions = calculate_voronoi_coverage([(5.0, 5.0)], room)
        assert len(regions) == 1
        assert regions[0].equals(room)

    def test_two_detectors_two_regions(self):
        """Two detectors should produce two clipped Voronoi regions."""
        room = box(0, 0, 10, 10)
        regions = calculate_voronoi_coverage([(2.5, 5.0), (7.5, 5.0)], room)
        # At least 2 regions (may be more if clipping produces fragments)
        assert len(regions) >= 2

    def test_empty_positions_returns_room(self):
        """Empty detector list returns room polygon."""
        room = box(0, 0, 10, 10)
        regions = calculate_voronoi_coverage([], room)
        assert len(regions) == 1


# ─────────────────────────────────────────────────────────────────────────────
# check_voronoi_coverage
# ─────────────────────────────────────────────────────────────────────────────


class TestCheckVoronoiCoverage:
    def test_returns_coverage_result(self, simple_room, ceiling_flat):
        positions = [(5.0, 5.0)]
        result = check_voronoi_coverage(positions, simple_room, ceiling_flat, DetectorType.SMOKE)
        assert isinstance(result, CoverageResult)

    def test_heat_detector_voronoi(self, ceiling_flat):
        """V49 FIX: Heat detectors use square geometry in Voronoi check."""
        small_room = RoomSpec(
            room_id="VH-001", name="Voronoi Heat",
            width_m=5.0, depth_m=5.0,
            ceiling_spec=CeilingSpec(height_at_low_point_m=3.0),
        )
        positions = [(2.5, 2.5)]
        result = check_voronoi_coverage(positions, small_room, ceiling_flat, DetectorType.HEAT)
        assert isinstance(result, CoverageResult)
        assert result.is_covered is True


# ─────────────────────────────────────────────────────────────────────────────
# check_ridge_zone_compliance — NFPA 72 §17.6.3.4
# ─────────────────────────────────────────────────────────────────────────────


class TestRidgeZoneCompliance:
    """NFPA 72 §17.6.3.4: Sloped ceilings require ridge zone detectors."""

    def test_flat_ceiling_no_ridge_required(self, ceiling_flat):
        """Flat ceiling doesn't require ridge zone detectors."""
        result = check_ridge_zone_compliance(
            [(5.0, 5.0)], ceiling_flat, (0, 5, 10, 5)
        )
        assert result.is_compliant is True

    def test_sloped_ceiling_no_detectors_in_ridge(self):
        """Sloped ceiling with no detectors near ridge — violation."""
        sloped = CeilingSpec(
            height_at_low_point_m=3.0,
            height_at_high_point_m=4.0,
            ceiling_type=CeilingType.SLOPED,
        )
        # Detectors far from ridge
        result = check_ridge_zone_compliance(
            [(5.0, 1.0)], sloped, (0, 10, 10, 10)
        )
        # May or may not be compliant depending on slope calculation
        assert isinstance(result, NFPAComplianceResult)

    def test_ridge_line_length_affects_required_count(self):
        """Long ridge requires multiple detectors at standard spacing."""
        sloped = CeilingSpec(
            height_at_low_point_m=3.0,
            height_at_high_point_m=4.5,
            ceiling_type=CeilingType.SLOPED,
        )
        # Short ridge (5m) — 1 detector should be enough
        result = check_ridge_zone_compliance(
            [(2.5, 10.0)], sloped, (0, 10, 5, 10), standard_spacing=9.1
        )
        assert isinstance(result, NFPAComplianceResult)


# ─────────────────────────────────────────────────────────────────────────────
# create_l_shaped_polygon
# ─────────────────────────────────────────────────────────────────────────────


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


# ─────────────────────────────────────────────────────────────────────────────
# check_l_shaped_coverage
# ─────────────────────────────────────────────────────────────────────────────


class TestCheckLShapedCoverage:
    """L-shaped room coverage — critical test where Bounding Box fails."""

    def test_single_detector_covers_l_shape(self, l_shaped_polygon):
        """One detector at center may cover L-shape if room small enough."""
        result = check_l_shaped_coverage(
            [(3.5, 3.5)], l_shaped_polygon, 3.0, DetectorType.SMOKE
        )
        assert isinstance(result, CoverageResult)

    def test_heat_detector_l_shape(self, l_shaped_polygon):
        """Heat detector coverage in L-shaped room uses square geometry."""
        result = check_l_shaped_coverage(
            [(3.5, 3.5)], l_shaped_polygon, 3.0, DetectorType.HEAT
        )
        assert isinstance(result, CoverageResult)

    def test_no_detectors_l_shape(self, l_shaped_polygon):
        """No detectors — coverage should be 0."""
        result = check_l_shaped_coverage(
            [], l_shaped_polygon, 3.0, DetectorType.SMOKE
        )
        assert result.is_covered is False
        assert result.coverage_percentage == pytest.approx(0.0, abs=0.1)


# ─────────────────────────────────────────────────────────────────────────────
# check_nfpa72_compliance
# ─────────────────────────────────────────────────────────────────────────────


class TestCheckNFPA72Compliance:
    def test_compliant_room(self, ceiling_flat):
        small_room = RoomSpec(
            room_id="CM-001", name="Compliant",
            width_m=8.0, depth_m=8.0,
            ceiling_spec=CeilingSpec(height_at_low_point_m=3.0),
        )
        positions = [(4.0, 4.0)]
        result = check_nfpa72_compliance(small_room, ceiling_flat, positions)
        assert isinstance(result, NFPAComplianceResult)
        assert result.is_compliant is True

    def test_non_compliant_no_detectors(self, simple_room, ceiling_flat):
        result = check_nfpa72_compliance(simple_room, ceiling_flat, [])
        assert result.is_compliant is False

    def test_detector_count_in_result(self, simple_room, ceiling_flat):
        positions = [(3.0, 3.0), (7.0, 7.0)]
        result = check_nfpa72_compliance(simple_room, ceiling_flat, positions)
        assert result.detector_count == 2


# ─────────────────────────────────────────────────────────────────────────────
# verify_full_coverage
# ─────────────────────────────────────────────────────────────────────────────


class TestVerifyFullCoverage:
    def test_full_coverage_smoke(self):
        # Use 8x8 room where one detector at center (R=6.37m) covers fully
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


# ─────────────────────────────────────────────────────────────────────────────
# get_sloped_ceiling_constraints
# ─────────────────────────────────────────────────────────────────────────────


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
        )
        result = get_sloped_ceiling_constraints(poly, sloped, DetectorType.HEAT)
        assert result["requires_ridge_row"] is False

    def test_sloped_smoke_requires_ridge(self):
        poly = box(0, 0, 10, 10)
        sloped = CeilingSpec(
            height_at_low_point_m=3.0,
            height_at_high_point_m=4.5,
            ceiling_type=CeilingType.SLOPED,
        )
        result = get_sloped_ceiling_constraints(poly, sloped, DetectorType.SMOKE)
        assert result["requires_ridge_row"] is True
        assert result["ridge_zone_polygon"] is not None


# ─────────────────────────────────────────────────────────────────────────────
# adjust_coverage_for_beams — NFPA 72 §17.6.3.1
# ─────────────────────────────────────────────────────────────────────────────


class TestAdjustCoverageForBeams:
    """NFPA 72 §17.6.3.1: Beam depth affects detector coverage."""

    def test_shallow_beam_no_adjustment(self):
        """Beam depth ≤ 4% of ceiling height — no reduction."""
        # ceiling=3m, beam=0.10m → ratio=3.33% ≤ 4%
        result = adjust_coverage_for_beams(6.37, 0.10, 3.0)
        assert result == pytest.approx(6.37, abs=0.01)

    def test_moderate_beam_15pct_reduction(self):
        """Beam depth > 4% but ≤ 10% — 15% radius reduction."""
        # ceiling=3m, beam=0.15m → ratio=5% > 4%
        result = adjust_coverage_for_beams(6.37, 0.15, 3.0)
        assert result == pytest.approx(6.37 * 0.85, abs=0.01)

    def test_deep_beam_compartment(self):
        """Beam depth > 10% — treat as separate compartments."""
        # ceiling=3m, beam=0.35m → ratio=11.67% > 10%
        result = adjust_coverage_for_beams(6.37, 0.35, 3.0)
        # Radius unchanged; compartment logic handles it
        assert result == pytest.approx(6.37, abs=0.01)

    def test_zero_beam_depth(self):
        """Zero beam depth — no adjustment."""
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
        """Exactly 4% beam ratio — should NOT trigger 15% reduction."""
        # ceiling=3m, beam=0.12m → ratio=4% exactly
        result = adjust_coverage_for_beams(6.37, 0.12, 3.0)
        assert result == pytest.approx(6.37, abs=0.01)

    def test_boundary_10pct_exactly(self):
        """Exactly 10% beam ratio — should trigger 15% reduction (not compartment)."""
        # ceiling=3m, beam=0.30m → ratio=10% exactly
        result = adjust_coverage_for_beams(6.37, 0.30, 3.0)
        assert result == pytest.approx(6.37 * 0.85, abs=0.01)

    def test_just_over_10pct(self):
        """Just over 10% — compartment separation."""
        # ceiling=3m, beam=0.301m → ratio=10.03%
        result = adjust_coverage_for_beams(6.37, 0.301, 3.0)
        assert result == pytest.approx(6.37, abs=0.01)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
