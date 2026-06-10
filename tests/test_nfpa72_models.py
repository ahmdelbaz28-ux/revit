"""
tests/test_nfpa72_models.py
============================
Comprehensive test suite for fireai/core/nfpa72_models.py

SAFETY CRITICAL: NFPA 72 data models form the backbone of all detector
placement and compliance calculations. Errors in radius lookups, ceiling
height validation, or model construction could produce incorrect detector
counts — a direct life-safety hazard.

NFPA 72 References:
  §17.6.3.1.1 — Height-adjusted spacing table
  §17.7.4.2.3.1 — Coverage radius R = 0.7 × S
  §17.6.3.2 — Maximum coverage per ceiling height
  §21.2.2 — Maximum devices per panel (250)
  §17.6.3.1.1 — Wall distance ≥ 0.10m (4 inches)
"""

from __future__ import annotations

import math
import pytest
from shapely.geometry import Polygon as ShapelyPolygon

from fireai.core.nfpa72_models import (
    # Constants
    MIN_WALL_DISTANCE_M,
    MAX_DIMENSION_M,
    MAX_POLYGON_VERTICES,
    MAX_STRING_LENGTH,
    # Enums
    CoverageGeometry,
    HeatDetectionMode,
    # Exceptions
    NFPAComplianceError,
    CeilingHeightError,
    CoverageError,
    SpacingError,
    RidgeZoneError,
    PanelCapacityError,
    # Dataclasses
    CeilingSpec,
    HVACDuct,
    RoomSpec,
    SmokeDetectorSpec,
    HeatDetectorSpec,
    DetectorPlacement,
    CoverageResult,
    NFPAComplianceResult,
    FireAlarmPanel,
    # Functions
    sanitize_string,
    get_smoke_detector_radius,
    get_smoke_detector_coverage_max,
    validate_ceiling_height,
    get_smoke_detector_radius_safe,
    get_smoke_detector_coverage_max_safe,
    _get_radius_internal,
    _get_max_internal,
    # Re-exports from contracts
    DetectorType,
    CeilingType,
    # Constants
    DISCLAIMER,
)


# ─────────────────────────────────────────────────────────────────────────────
# Constants
# ─────────────────────────────────────────────────────────────────────────────


class TestConstants:
    """Module-level constants per NFPA 72."""

    def test_min_wall_distance(self):
        """NFPA 72 §17.6.3.1.1: 4 inches = 0.10m."""
        assert MIN_WALL_DISTANCE_M == pytest.approx(0.10, abs=0.01)

    def test_max_dimension_m(self):
        assert MAX_DIMENSION_M == 1000.0

    def test_max_polygon_vertices(self):
        assert MAX_POLYGON_VERTICES == 5000

    def test_max_string_length(self):
        assert MAX_STRING_LENGTH == 200

    def test_disclaimer_exists(self):
        assert isinstance(DISCLAIMER, str)
        assert "LEGAL DISCLAIMER" in DISCLAIMER


# ─────────────────────────────────────────────────────────────────────────────
# sanitize_string
# ─────────────────────────────────────────────────────────────────────────────


class TestSanitizeString:
    """Input sanitization — SQL injection prevention."""

    def test_valid_string(self):
        assert sanitize_string("room_101") == "room_101"

    def test_strips_whitespace(self):
        assert sanitize_string("  room_101  ") == "room_101"

    def test_rejects_non_string(self):
        with pytest.raises(ValueError, match="must be a string"):
            sanitize_string(123)

    def test_rejects_long_string(self):
        with pytest.raises(ValueError, match="too long"):
            sanitize_string("a" * 101, max_length=100)

    def test_max_length_capped_to_200(self):
        """effective_max = min(200, max_length) when max_length > 0."""
        # max_length=300 → effective_max=200
        with pytest.raises(ValueError, match="too long"):
            sanitize_string("a" * 201, max_length=300)

    def test_zero_max_length_uses_global_cap(self):
        """max_length <= 0 uses MAX_STRING_LENGTH."""
        with pytest.raises(ValueError, match="too long"):
            sanitize_string("a" * 201, max_length=0)

    def test_rejects_semicolon(self):
        with pytest.raises(ValueError, match="invalid characters"):
            sanitize_string("room;DROP TABLE")

    def test_rejects_single_quote(self):
        with pytest.raises(ValueError, match="invalid characters"):
            sanitize_string("room'OR'1'='1")

    def test_rejects_double_quote(self):
        with pytest.raises(ValueError, match="invalid characters"):
            sanitize_string('room"inject')

    def test_rejects_newline(self):
        with pytest.raises(ValueError, match="invalid characters"):
            sanitize_string("room\ninjected")

    def test_rejects_null_byte(self):
        with pytest.raises(ValueError, match="invalid characters"):
            sanitize_string("room\x00evil")

    def test_rejects_sql_comment(self):
        with pytest.raises(ValueError, match="invalid sequence"):
            sanitize_string("room--DROP TABLE")

    def test_rejects_backslash(self):
        with pytest.raises(ValueError, match="invalid characters"):
            sanitize_string("room\\path")

    def test_rejects_tab(self):
        with pytest.raises(ValueError, match="invalid characters"):
            sanitize_string("room\ttab")


# ─────────────────────────────────────────────────────────────────────────────
# Enums
# ─────────────────────────────────────────────────────────────────────────────


class TestCoverageGeometry:
    def test_values(self):
        assert CoverageGeometry.CIRCULAR.value == "circular"
        assert CoverageGeometry.SQUARE_GRID.value == "square_grid"

    def test_members(self):
        assert set(CoverageGeometry.__members__.keys()) == {"CIRCULAR", "SQUARE_GRID"}


class TestHeatDetectionMode:
    def test_values(self):
        assert HeatDetectionMode.CIRCULAR.value == "circular"
        assert HeatDetectionMode.SQUARE_GRID.value == "square_grid"


class TestDetectorTypeReexport:
    """DetectorType re-exported from contracts.py."""

    def test_smoke_exists(self):
        assert DetectorType.SMOKE is not None

    def test_heat_exists(self):
        assert DetectorType.HEAT is not None

    def test_heat_fixed_temp_alias(self):
        """HEAT_FIXED_TEMP is alias for HEAT_FIXED per NFPA 72."""
        assert DetectorType.HEAT_FIXED_TEMP is not None


class TestCeilingTypeReexport:
    """CeilingType re-exported from contracts.py."""

    def test_flat_exists(self):
        assert CeilingType.FLAT is not None

    def test_gable_exists(self):
        assert CeilingType.GABLE is not None


# ─────────────────────────────────────────────────────────────────────────────
# Exceptions
# ─────────────────────────────────────────────────────────────────────────────


class TestExceptions:
    def test_nfpa_compliance_error_hierarchy(self):
        assert issubclass(CeilingHeightError, NFPAComplianceError)
        assert issubclass(CoverageError, NFPAComplianceError)
        assert issubclass(SpacingError, NFPAComplianceError)
        assert issubclass(RidgeZoneError, NFPAComplianceError)
        assert issubclass(PanelCapacityError, NFPAComplianceError)

    def test_nfpa_compliance_error_is_exception(self):
        assert issubclass(NFPAComplianceError, Exception)

    def test_ceiling_height_error_message(self):
        with pytest.raises(CeilingHeightError) as exc_info:
            raise CeilingHeightError("height 2.0m below minimum")
        assert "2.0m" in str(exc_info.value)


# ─────────────────────────────────────────────────────────────────────────────
# CeilingSpec
# ─────────────────────────────────────────────────────────────────────────────


class TestCeilingSpec:
    """Ceiling specification — strict validation per NFPA 72 §17.6.3."""

    def test_valid_flat_ceiling(self):
        spec = CeilingSpec(3.0, 3.0, CeilingType.FLAT, 0.0)
        assert spec.height_m == 3.0
        assert spec.is_sloped is False
        assert spec.ridge_line is None

    def test_sloped_ceiling_auto_slope(self):
        """Slope computed from low/high point difference."""
        spec = CeilingSpec(3.0, 4.5, CeilingType.SLOPED)
        assert spec.is_sloped is True
        # rise=1.5, run=3.0 → atan(0.5) ≈ 26.57°
        assert spec.slope_degrees == pytest.approx(math.degrees(math.atan(0.5)), rel=0.01)

    def test_gable_ridge_line(self):
        spec = CeilingSpec(3.0, 5.0, CeilingType.GABLE)
        ridge = spec.ridge_line
        assert ridge is not None
        assert len(ridge) == 4

    def test_shed_ridge_line(self):
        spec = CeilingSpec(3.0, 4.0, CeilingType.SHED)
        assert spec.ridge_line is not None

    def test_flat_no_ridge_line(self):
        spec = CeilingSpec(3.0, 3.0, CeilingType.FLAT)
        assert spec.ridge_line is None

    def test_reject_height_below_nfpa_min(self):
        """V24: Heights below 3.0m MUST raise ValueError (strict function)."""
        with pytest.raises(ValueError, match="outside NFPA 72 normative range"):
            CeilingSpec(2.5)

    def test_reject_height_above_nfpa_max(self):
        with pytest.raises(ValueError, match="outside NFPA 72 normative range"):
            CeilingSpec(20.0)

    def test_reject_zero_height(self):
        with pytest.raises(CeilingHeightError, match="must be > 0"):
            CeilingSpec(0.0)

    def test_reject_negative_height(self):
        with pytest.raises(CeilingHeightError, match="must be > 0"):
            CeilingSpec(-1.0)

    def test_reject_nan_height(self):
        with pytest.raises(CeilingHeightError, match="finite"):
            CeilingSpec(float("nan"))

    def test_reject_inf_height(self):
        with pytest.raises(CeilingHeightError, match="finite"):
            CeilingSpec(float("inf"))

    def test_reject_non_numeric_height(self):
        with pytest.raises(CeilingHeightError, match="must be a number"):
            CeilingSpec("three")

    def test_reject_none_ceiling_type(self):
        with pytest.raises(CeilingHeightError, match="must be CeilingType enum"):
            CeilingSpec(3.0, ceiling_type=None)

    def test_reject_high_point_lower_than_low(self):
        with pytest.raises(CeilingHeightError, match="height_at_high_point_m"):
            CeilingSpec(4.0, height_at_high_point_m=3.0)

    def test_was_clamped_default_false(self):
        spec = CeilingSpec(3.0, 3.0, CeilingType.FLAT, 0.0)
        assert spec.was_clamped is False

    def test_beam_depth_default_zero(self):
        spec = CeilingSpec(3.0, 3.0, CeilingType.FLAT, 0.0)
        assert spec.beam_depth_m == 0.0


class TestCeilingSpecCreateSafe:
    """CeilingSpec.create_safe() — V9 factory with clamping."""

    def test_normal_height_unchanged(self):
        spec = CeilingSpec.create_safe(3.5)
        assert spec.height_m == 3.5
        assert spec.was_clamped is False
        assert spec.original_height_m == 3.5

    def test_low_height_clamped_to_min(self):
        spec = CeilingSpec.create_safe(2.0)
        assert spec.height_m == 3.0
        assert spec.was_clamped is True
        assert spec.original_height_m == 2.0

    def test_high_height_clamped_to_max(self):
        spec = CeilingSpec.create_safe(20.0)
        assert spec.height_m == 15.24
        assert spec.was_clamped is True
        assert spec.original_height_m == 20.0

    def test_reject_zero_height(self):
        with pytest.raises(ValueError, match="must be positive"):
            CeilingSpec.create_safe(0.0)

    def test_reject_negative_height(self):
        with pytest.raises(ValueError, match="must be positive"):
            CeilingSpec.create_safe(-1.0)

    def test_custom_ceiling_type(self):
        spec = CeilingSpec.create_safe(3.0, ceiling_type=CeilingType.SLOPED)
        assert spec.ceiling_type == CeilingType.SLOPED

    def test_beam_depth_passed(self):
        spec = CeilingSpec.create_safe(3.0, beam_depth_m=0.5)
        assert spec.beam_depth_m == 0.5

    def test_beam_spacing_passed(self):
        spec = CeilingSpec.create_safe(3.0, beam_spacing_m=2.0)
        assert spec.beam_spacing_m == 2.0

    def test_high_point_passed_through(self):
        spec = CeilingSpec.create_safe(3.0, height_at_high_point_m=4.0)
        assert spec.height_at_high_point_m == 4.0

    def test_exactly_3m_not_clamped(self):
        spec = CeilingSpec.create_safe(3.0)
        assert spec.was_clamped is False

    def test_exactly_1524_not_clamped(self):
        spec = CeilingSpec.create_safe(15.24)
        assert spec.was_clamped is False


# ─────────────────────────────────────────────────────────────────────────────
# HVACDuct
# ─────────────────────────────────────────────────────────────────────────────


class TestHVACDuct:
    def test_defaults(self):
        duct = HVACDuct()
        assert duct.duct_id == ""
        assert duct.centerline == []
        assert duct.width_m == 0.3
        assert duct.height_m == 0.3
        assert duct.airflow_m3s == 0.0

    def test_custom_values(self):
        duct = HVACDuct(duct_id="D1", width_m=0.6, height_m=0.4, airflow_m3s=1.5)
        assert duct.duct_id == "D1"
        assert duct.width_m == 0.6


# ─────────────────────────────────────────────────────────────────────────────
# RoomSpec
# ─────────────────────────────────────────────────────────────────────────────


class TestRoomSpec:
    """Room specification — STRICT VALIDATION at creation."""

    def test_valid_room(self):
        room = RoomSpec(room_id="R1", width_m=10, depth_m=8)
        assert room.room_id == "R1"
        assert room.width_m == 10
        assert room.depth_m == 8
        assert room.area_sqm == pytest.approx(80.0)
        assert room.occupancy_type == "office"

    def test_default_ceiling_spec_created(self):
        room = RoomSpec(room_id="R1", width_m=10, depth_m=10)
        assert room.ceiling_spec is not None
        assert room.ceiling_spec.height_m == 3.0

    def test_default_detector_type_smoke(self):
        room = RoomSpec(room_id="R1", width_m=10, depth_m=10)
        assert room.detector_type == DetectorType.SMOKE

    def test_polygon_built_from_dimensions(self):
        room = RoomSpec(room_id="R1", width_m=10, depth_m=8)
        assert room.polygon is not None
        assert room.polygon.area == pytest.approx(80.0)

    def test_custom_polygon(self):
        pts = [(0, 0), (10, 0), (10, 8), (0, 8)]
        room = RoomSpec(room_id="R1", width_m=10, depth_m=8, custom_polygon=pts)
        assert room.polygon is not None
        assert room.polygon.area == pytest.approx(80.0)

    def test_custom_polygon_with_list_points(self):
        pts = [[0, 0], [10, 0], [10, 8], [0, 8]]
        room = RoomSpec(room_id="R1", width_m=10, depth_m=8, custom_polygon=pts)
        assert room.polygon is not None

    def test_reject_empty_room_id(self):
        with pytest.raises(ValueError, match="room_id is required"):
            RoomSpec(room_id="", width_m=10, depth_m=10)

    def test_reject_whitespace_room_id(self):
        """Whitespace-only room_id gets stripped to empty → rejected."""
        with pytest.raises(ValueError, match="room_id is required"):
            RoomSpec(room_id="   ", width_m=10, depth_m=10)

    def test_reject_zero_width(self):
        with pytest.raises(ValueError, match="width_m must be > 0"):
            RoomSpec(room_id="R1", width_m=0, depth_m=10)

    def test_reject_negative_depth(self):
        with pytest.raises(ValueError, match="depth_m must be > 0"):
            RoomSpec(room_id="R1", width_m=10, depth_m=-5)

    def test_reject_nan_width(self):
        with pytest.raises(ValueError, match="finite"):
            RoomSpec(room_id="R1", width_m=float("nan"), depth_m=10)

    def test_reject_inf_depth(self):
        with pytest.raises(ValueError, match="finite"):
            RoomSpec(room_id="R1", width_m=10, depth_m=float("inf"))

    def test_reject_width_exceeds_max(self):
        with pytest.raises(ValueError, match="exceeds maximum"):
            RoomSpec(room_id="R1", width_m=1001, depth_m=10)

    def test_reject_depth_exceeds_max(self):
        with pytest.raises(ValueError, match="exceeds maximum"):
            RoomSpec(room_id="R1", width_m=10, depth_m=1001)

    def test_reject_boolean_width(self):
        with pytest.raises(ValueError, match="not boolean"):
            RoomSpec(room_id="R1", width_m=True, depth_m=10)

    def test_reject_boolean_depth(self):
        with pytest.raises(ValueError, match="not boolean"):
            RoomSpec(room_id="R1", width_m=10, depth_m=False)

    def test_reject_empty_occupancy_type(self):
        with pytest.raises(ValueError, match="occupancy_type is required"):
            RoomSpec(room_id="R1", width_m=10, depth_m=10, occupancy_type="")

    def test_reject_invalid_occupancy_type(self):
        with pytest.raises(ValueError, match="not in valid set"):
            RoomSpec(room_id="R1", width_m=10, depth_m=10, occupancy_type="kitchen")

    def test_reject_assembly_occupancy(self):
        """V20.2: kitchen and assembly removed for safety."""
        with pytest.raises(ValueError, match="not in valid set"):
            RoomSpec(room_id="R1", width_m=10, depth_m=10, occupancy_type="assembly")

    def test_valid_occupancy_types(self):
        """All valid types should work."""
        for occ in ["office", "corridor", "storage", "bathroom", "meeting",
                     "hazardous", "industrial", "laboratory", "data_center"]:
            room = RoomSpec(room_id="R1", width_m=10, depth_m=10, occupancy_type=occ)
            assert room.occupancy_type == occ

    def test_occupancy_case_insensitive(self):
        room = RoomSpec(room_id="R1", width_m=10, depth_m=10, occupancy_type="Office")
        assert room.occupancy_type == "Office"

    def test_custom_polygon_too_few_points(self):
        with pytest.raises(ValueError, match="at least 4 points"):
            RoomSpec(room_id="R1", width_m=10, depth_m=10, custom_polygon=[(0, 0), (1, 0), (1, 1)])

    def test_custom_polygon_too_many_vertices(self):
        pts = [(i, i) for i in range(5001)]
        with pytest.raises(ValueError, match="exceeds max vertices"):
            RoomSpec(room_id="R1", width_m=10, depth_m=10, custom_polygon=pts)

    def test_custom_polygon_invalid_point(self):
        pts = [(0, 0), (10, 0), (10, "eight"), (0, 8)]
        with pytest.raises(ValueError, match="must be numeric"):
            RoomSpec(room_id="R1", width_m=10, depth_m=10, custom_polygon=pts)

    def test_custom_polygon_non_tuple_point(self):
        pts = [(0, 0), (10, 0), (10, 8, 0), (0, 8)]
        with pytest.raises(ValueError, match="must be \\(x,y\\) tuple"):
            RoomSpec(room_id="R1", width_m=10, depth_m=10, custom_polygon=pts)

    def test_polygon_coords_property(self):
        room = RoomSpec(room_id="R1", width_m=10, depth_m=8)
        coords = room.polygon_coords
        assert len(coords) == 4
        assert coords[0] == (0.0, 0.0)

    def test_ceiling_property_compatibility(self):
        room = RoomSpec(room_id="R1", width_m=10, depth_m=10)
        assert room.ceiling == room.ceiling_spec

    def test_hvac_ducts_property(self):
        duct = HVACDuct(duct_id="D1")
        room = RoomSpec(room_id="R1", width_m=10, depth_m=10, hvac_duct_list=[duct])
        assert len(room.hvac_ducts) == 1
        assert room.hvac_ducts == room._hvac_ducts

    def test_geometry_unresolved_flag(self):
        room = RoomSpec(room_id="R1", width_m=10, depth_m=10, geometry_unresolved=True)
        assert room.geometry_unresolved is True

    def test_create_validated_factory(self):
        room = RoomSpec.create_validated(room_id="R1", width_m=10, depth_m=10)
        assert room.room_id == "R1"

    def test_area_sqm_from_polygon(self):
        """CRITICAL FIX: area from polygon, not width*depth."""
        pts = [(0, 0), (10, 0), (10, 8), (0, 8)]
        room = RoomSpec(room_id="R1", width_m=10, depth_m=10, custom_polygon=pts)
        assert room.area_sqm == pytest.approx(80.0)  # polygon area, not 100

    def test_shapely_polygon_as_input(self):
        poly = ShapelyPolygon([(0, 0), (10, 0), (10, 8), (0, 8)])
        room = RoomSpec(room_id="R1", width_m=10, depth_m=10, polygon=poly)
        assert room.area_sqm == pytest.approx(80.0)


# ─────────────────────────────────────────────────────────────────────────────
# SmokeDetectorSpec
# ─────────────────────────────────────────────────────────────────────────────


class TestSmokeDetectorSpec:
    def test_radius_m_at_3m(self):
        """R = 0.7 × 9.1 = 6.37m at h=3.0m."""
        ceiling = CeilingSpec(3.0, 3.0, CeilingType.FLAT)
        room = RoomSpec(room_id="R1", width_m=10, depth_m=10, ceiling_spec=ceiling)
        spec = SmokeDetectorSpec(ceiling_spec=ceiling, room_spec=room)
        assert spec.radius_m == pytest.approx(6.37, abs=0.01)

    def test_coverage_max_at_3m(self):
        ceiling = CeilingSpec(3.0, 3.0, CeilingType.FLAT)
        room = RoomSpec(room_id="R1", width_m=10, depth_m=10, ceiling_spec=ceiling)
        spec = SmokeDetectorSpec(ceiling_spec=ceiling, room_spec=room)
        assert spec.coverage_max_m == pytest.approx(5.5, abs=0.01)

    def test_default_detector_type(self):
        ceiling = CeilingSpec(3.0, 3.0, CeilingType.FLAT)
        room = RoomSpec(room_id="R1", width_m=10, depth_m=10, ceiling_spec=ceiling)
        spec = SmokeDetectorSpec(ceiling_spec=ceiling, room_spec=room)
        assert spec.detector_type == DetectorType.SMOKE


# ─────────────────────────────────────────────────────────────────────────────
# HeatDetectorSpec
# ─────────────────────────────────────────────────────────────────────────────


class TestHeatDetectorSpec:
    def test_spacing_m(self):
        """V20.2 FIX: Heat detector spacing = 6.1m (20ft), NOT 9.1m (30ft)."""
        ceiling = CeilingSpec(3.0, 3.0, CeilingType.FLAT)
        room = RoomSpec(room_id="R1", width_m=10, depth_m=10, ceiling_spec=ceiling)
        spec = HeatDetectorSpec(ceiling_spec=ceiling, room_spec=room)
        assert spec.spacing_m == 6.1

    def test_radius_m(self):
        """V20.2 FIX: R = 0.7 × 6.1 = 4.27m."""
        ceiling = CeilingSpec(3.0, 3.0, CeilingType.FLAT)
        room = RoomSpec(room_id="R1", width_m=10, depth_m=10, ceiling_spec=ceiling)
        spec = HeatDetectorSpec(ceiling_spec=ceiling, room_spec=room)
        assert spec.radius_m == pytest.approx(4.27, abs=0.01)

    def test_fixed_spacing_ft(self):
        ceiling = CeilingSpec(3.0, 3.0, CeilingType.FLAT)
        room = RoomSpec(room_id="R1", width_m=10, depth_m=10, ceiling_spec=ceiling)
        spec = HeatDetectorSpec(ceiling_spec=ceiling, room_spec=room)
        assert spec.FIXED_SPACING_FT == 20

    def test_default_detector_type(self):
        ceiling = CeilingSpec(3.0, 3.0, CeilingType.FLAT)
        room = RoomSpec(room_id="R1", width_m=10, depth_m=10, ceiling_spec=ceiling)
        spec = HeatDetectorSpec(ceiling_spec=ceiling, room_spec=room)
        assert spec.detector_type == DetectorType.HEAT


# ─────────────────────────────────────────────────────────────────────────────
# DetectorPlacement
# ─────────────────────────────────────────────────────────────────────────────


class TestDetectorPlacement:
    """DetectorPlacement — FIXED 2026-05-14 (ReferenceError bug)."""

    def test_smoke_detector_default_radius(self):
        """Smoke detector gets safe fallback radius."""
        dp = DetectorPlacement(x=5.0, y=5.0, z=3.0, detector_type=DetectorType.SMOKE)
        assert dp.coverage_radius_m is not None
        assert dp.coverage_radius_m > 0

    def test_heat_detector_default_radius(self):
        """V20.2 FIX: Heat detector uses 4.27m, NOT smoke radius."""
        dp = DetectorPlacement(x=5.0, y=5.0, z=3.0, detector_type=DetectorType.HEAT)
        assert dp.coverage_radius_m == 4.27

    def test_heat_fixed_detector_default_radius(self):
        dp = DetectorPlacement(x=5.0, y=5.0, z=3.0, detector_type=DetectorType.HEAT_FIXED)
        assert dp.coverage_radius_m == 4.27

    def test_explicit_radius_overrides_default(self):
        dp = DetectorPlacement(x=5.0, y=5.0, z=3.0, detector_type=DetectorType.SMOKE, coverage_radius_m=5.0)
        assert dp.coverage_radius_m == 5.0

    def test_position_3d(self):
        dp = DetectorPlacement(x=1.0, y=2.0, z=3.0, detector_type=DetectorType.SMOKE)
        assert dp.position_3d == (1.0, 2.0, 3.0)

    def test_effective_coverage_area(self):
        dp = DetectorPlacement(x=5.0, y=5.0, z=3.0, detector_type=DetectorType.SMOKE, coverage_radius_m=6.37)
        expected = math.pi * 6.37 ** 2
        assert dp.effective_coverage_area == pytest.approx(expected, rel=0.01)

    def test_ceiling_height_m_default(self):
        dp = DetectorPlacement(x=5.0, y=5.0, z=3.0, detector_type=DetectorType.SMOKE)
        assert dp.ceiling_height_m == 3.0


# ─────────────────────────────────────────────────────────────────────────────
# CoverageResult
# ─────────────────────────────────────────────────────────────────────────────


class TestCoverageResult:
    def test_bool_true_when_covered(self):
        result = CoverageResult(is_covered=True, coverage_percentage=100.0)
        assert bool(result) is True

    def test_bool_false_when_not_covered(self):
        result = CoverageResult(is_covered=False, coverage_percentage=50.0)
        assert bool(result) is False

    def test_default_proof_valid_false(self):
        """V112: FAIL-SAFE — proof not valid until verified."""
        result = CoverageResult(is_covered=True)
        assert result.proof_valid is False

    def test_default_coverage_fraction_zero(self):
        """V112: FAIL-SAFE — no coverage until verified."""
        result = CoverageResult(is_covered=True)
        assert result.coverage_fraction == 0.0

    def test_uncovered_areas_default_empty(self):
        result = CoverageResult(is_covered=True)
        assert result.uncovered_areas == []


# ─────────────────────────────────────────────────────────────────────────────
# NFPAComplianceResult
# ─────────────────────────────────────────────────────────────────────────────


class TestNFPAComplianceResult:
    def test_compliant_result(self):
        result = NFPAComplianceResult(is_compliant=True)
        assert bool(result) is True

    def test_non_compliant_result(self):
        result = NFPAComplianceResult(is_compliant=False)
        assert bool(result) is False

    def test_add_violation(self):
        result = NFPAComplianceResult(is_compliant=True)
        result.add_violation("Insufficient coverage")
        assert result.is_compliant is False
        assert "Insufficient coverage" in result.violations

    def test_add_warning(self):
        result = NFPAComplianceResult(is_compliant=True)
        result.add_warning("PE review required")
        assert result.is_compliant is True  # Warnings don't change compliance
        assert "PE review required" in result.warnings

    def test_disclaimer_class_var(self):
        assert "LEGAL DISCLAIMER" in NFPAComplianceResult.DISCLAIMER

    def test_add_violation_flips_compliance(self):
        result = NFPAComplianceResult(is_compliant=True)
        result.add_violation("V1")
        result.add_violation("V2")
        assert len(result.violations) == 2
        assert result.is_compliant is False


# ─────────────────────────────────────────────────────────────────────────────
# FireAlarmPanel
# ─────────────────────────────────────────────────────────────────────────────


class TestFireAlarmPanel:
    """Fire Alarm Control Panel per NFPA 72 Chapter 21."""

    def test_defaults(self):
        panel = FireAlarmPanel(panel_id="P1")
        assert panel.max_devices == 250
        assert panel.voltage == 24.0
        assert panel.min_voltage == 16.0

    def test_add_device(self):
        panel = FireAlarmPanel(panel_id="P1")
        panel.add_device("D1")
        assert "D1" in panel.connected_devices

    def test_add_device_capacity_exceeded(self):
        """NFPA 72 §21.2.2: max 250 devices per panel."""
        panel = FireAlarmPanel(panel_id="P1", max_devices=2)
        panel.add_device("D1")
        panel.add_device("D2")
        with pytest.raises(PanelCapacityError, match="capacity exceeded"):
            panel.add_device("D3")

    def test_check_voltage_drop_deprecated(self):
        """Issue #12: check_voltage_drop is deprecated."""
        panel = FireAlarmPanel(panel_id="P1")
        with pytest.warns(DeprecationWarning, match="deprecated"):
            v_drop = panel.check_voltage_drop(100.0)
        assert v_drop == pytest.approx(0.04, abs=0.001)  # 100m × 0.0004

    def test_verify_voltage_compliant(self):
        panel = FireAlarmPanel(panel_id="P1")
        with pytest.warns(DeprecationWarning):
            assert panel.verify_voltage(1000.0) is True

    def test_is_accessible(self):
        panel = FireAlarmPanel(panel_id="P1")
        assert panel.is_accessible() is True


# ─────────────────────────────────────────────────────────────────────────────
# get_smoke_detector_radius — STRICT function
# ─────────────────────────────────────────────────────────────────────────────


class TestGetSmokeDetectorRadius:
    """NFPA 72 Table 17.6.3.2 — R = 0.7 × S per height bracket."""

    def test_h_3_0m(self):
        assert get_smoke_detector_radius(3.0) == pytest.approx(6.37, abs=0.01)

    def test_h_3_5m(self):
        """V20.2 FIX: h=3.5 falls in (3.0, 3.7) bracket → R=6.37."""
        assert get_smoke_detector_radius(3.5) == pytest.approx(6.37, abs=0.01)

    def test_h_3_7m(self):
        """Boundary: h=3.7 falls in (3.7, 4.6) bracket → R=6.09."""
        assert get_smoke_detector_radius(3.7) == pytest.approx(6.09, abs=0.01)

    def test_h_4_0m(self):
        assert get_smoke_detector_radius(4.0) == pytest.approx(6.09, abs=0.01)

    def test_h_5_0m(self):
        assert get_smoke_detector_radius(5.0) == pytest.approx(5.74, abs=0.01)

    def test_h_6_0m(self):
        assert get_smoke_detector_radius(6.0) == pytest.approx(5.39, abs=0.01)

    def test_h_7_0m(self):
        assert get_smoke_detector_radius(7.0) == pytest.approx(5.11, abs=0.01)

    def test_h_8_0m(self):
        assert get_smoke_detector_radius(8.0) == pytest.approx(4.76, abs=0.01)

    def test_h_9_5m(self):
        assert get_smoke_detector_radius(9.5) == pytest.approx(4.48, abs=0.01)

    def test_h_11_0m(self):
        assert get_smoke_detector_radius(11.0) == pytest.approx(4.20, abs=0.01)

    def test_h_13_0m(self):
        assert get_smoke_detector_radius(13.0) == pytest.approx(3.64, abs=0.01)

    def test_h_15_24m(self):
        """Upper boundary: h=15.24 must return R=3.64."""
        assert get_smoke_detector_radius(15.24) == pytest.approx(3.64, abs=0.01)

    def test_reject_below_3m(self):
        """V24 FIX: h < 3.0m must raise CeilingHeightError."""
        with pytest.raises(CeilingHeightError):
            get_smoke_detector_radius(2.5)

    def test_reject_above_15_24m(self):
        with pytest.raises(CeilingHeightError):
            get_smoke_detector_radius(16.0)

    def test_radius_decreases_with_height(self):
        """Higher ceilings → smaller radius → more detectors → safer."""
        r_3 = get_smoke_detector_radius(3.0)
        r_6 = get_smoke_detector_radius(6.0)
        r_12 = get_smoke_detector_radius(12.5)
        assert r_3 > r_6 > r_12


# ─────────────────────────────────────────────────────────────────────────────
# get_smoke_detector_coverage_max
# ─────────────────────────────────────────────────────────────────────────────


class TestGetSmokeDetectorCoverageMax:
    def test_h_3_0m(self):
        assert get_smoke_detector_coverage_max(3.0) == pytest.approx(5.5, abs=0.01)

    def test_h_5_0m(self):
        assert get_smoke_detector_coverage_max(5.0) == pytest.approx(6.5, abs=0.01)

    def test_h_7_0m(self):
        assert get_smoke_detector_coverage_max(7.0) == pytest.approx(8.1, abs=0.01)

    def test_h_8_0m(self):
        assert get_smoke_detector_coverage_max(8.0) == pytest.approx(9.0, abs=0.01)

    def test_h_10_0m(self):
        assert get_smoke_detector_coverage_max(10.0) == pytest.approx(10.1, abs=0.01)

    def test_h_15_24m(self):
        assert get_smoke_detector_coverage_max(15.24) == pytest.approx(10.1, abs=0.01)

    def test_out_of_range_returns_default(self):
        """Heights outside range get default 10.1m max."""
        assert get_smoke_detector_coverage_max(2.0) == pytest.approx(10.1)


# ─────────────────────────────────────────────────────────────────────────────
# validate_ceiling_height
# ─────────────────────────────────────────────────────────────────────────────


class TestValidateCeilingHeight:
    def test_valid_height_no_raise(self):
        validate_ceiling_height(3.0)  # Should not raise
        validate_ceiling_height(10.0)
        validate_ceiling_height(15.24)

    def test_below_min_raises(self):
        with pytest.raises(CeilingHeightError, match="below NFPA 72 minimum"):
            validate_ceiling_height(2.5)

    def test_above_max_raises(self):
        with pytest.raises(CeilingHeightError, match="exceeds NFPA 72 maximum"):
            validate_ceiling_height(16.0)


# ─────────────────────────────────────────────────────────────────────────────
# get_smoke_detector_radius_safe — ELITE SAFE FUNCTION
# ─────────────────────────────────────────────────────────────────────────────


class TestGetSmokeDetectorRadiusSafe:
    """Conservative fallback — more detectors = safer."""

    def test_reject_zero_height(self):
        with pytest.raises(ValueError, match="MUST_BE_POSITIVE"):
            get_smoke_detector_radius_safe(0.0)

    def test_reject_negative_height(self):
        with pytest.raises(ValueError, match="MUST_BE_POSITIVE"):
            get_smoke_detector_radius_safe(-1.0)

    def test_standard_3m(self):
        r = get_smoke_detector_radius_safe(3.0)
        assert r == pytest.approx(6.37, abs=0.01)

    def test_low_ceiling_uses_3m_values(self):
        """Heights < 3.0m use 3.0m values (conservative)."""
        r = get_smoke_detector_radius_safe(2.4)
        assert r == pytest.approx(6.37, abs=0.01)

    def test_high_ceiling_capped(self):
        """Heights > 15.24m capped at 15.24m values."""
        r = get_smoke_detector_radius_safe(20.0)
        assert r == pytest.approx(3.64, abs=0.01)

    def test_return_details_standard(self):
        r, details = get_smoke_detector_radius_safe(3.0, _return_details=True)
        assert details["flag"] is None
        assert details["conservative"] is False
        assert details["input_height"] == 3.0
        assert details["effective_height"] == 3.0

    def test_return_details_low_ceiling(self):
        r, details = get_smoke_detector_radius_safe(2.4, _return_details=True)
        assert details["flag"] is not None
        assert "LOW_CEILING" in details["flag"]
        assert details["conservative"] is True
        assert details["effective_height"] == 3.0

    def test_return_details_high_ceiling(self):
        r, details = get_smoke_detector_radius_safe(20.0, _return_details=True)
        assert details["flag"] is not None
        assert "HIGH_CEILING" in details["flag"]
        assert details["conservative"] is True
        assert details["effective_height"] == 15.24

    def test_15_24m_standard(self):
        r = get_smoke_detector_radius_safe(15.24)
        assert r == pytest.approx(3.64, abs=0.01)


# ─────────────────────────────────────────────────────────────────────────────
# get_smoke_detector_coverage_max_safe
# ─────────────────────────────────────────────────────────────────────────────


class TestGetSmokeDetectorCoverageMaxSafe:
    def test_standard_3m(self):
        r = get_smoke_detector_coverage_max_safe(3.0)
        assert r == pytest.approx(5.5, abs=0.01)

    def test_low_ceiling_uses_3m(self):
        r = get_smoke_detector_coverage_max_safe(2.0)
        assert r == pytest.approx(5.5, abs=0.01)

    def test_high_ceiling_capped(self):
        r = get_smoke_detector_coverage_max_safe(20.0)
        assert r == pytest.approx(10.1, abs=0.01)

    def test_return_details_low(self):
        r, details = get_smoke_detector_coverage_max_safe(2.0, _return_details=True)
        assert details["flag"] == "LOW_CEILING"

    def test_return_details_high(self):
        r, details = get_smoke_detector_coverage_max_safe(20.0, _return_details=True)
        assert details["flag"] == "HIGH_CEILING"


# ─────────────────────────────────────────────────────────────────────────────
# Internal functions
# ─────────────────────────────────────────────────────────────────────────────


class TestInternalFunctions:
    def test_get_radius_internal_3m(self):
        assert _get_radius_internal(3.0) == pytest.approx(6.37, abs=0.01)

    def test_get_radius_internal_outside_range(self):
        with pytest.raises(CeilingHeightError):
            _get_radius_internal(0.5)

    def test_get_max_internal_3m(self):
        assert _get_max_internal(3.0) == pytest.approx(5.5, abs=0.01)

    def test_get_max_internal_boundary_4_3(self):
        """Issue #11 FIX: h=4.3 falls in (4.3, 6.1) bracket."""
        assert _get_max_internal(4.3) == pytest.approx(6.5, abs=0.01)
