"""fireai/core/tests/test_edge_cases.py — Edge Case Tests for FireAI Core
=======================================================================
Task 2.17: Add edge case tests for fireai/

Tests cover:
  1. Extreme ceiling heights (very low, very high)
  2. Negative/zero dimensions in models and calculations
  3. NaN/Inf inputs in NFPA 72 calculations
  4. Empty room lists
  5. Single-detector rooms
  6. Very large rooms
  7. Point3D and Geometry edge cases
  8. SemanticProperties validation edge cases
  9. UniversalElement immutability edge cases
"""

from __future__ import annotations

import pytest

from core.models import (
    Conflict,
    ConflictType,
    ElementType,
    Geometry,
    Point3D,
    Relationship,
    SemanticProperties,
    UniversalElement,
)
from fireai.core.nfpa72_engine import (
    calculate_battery,
    calculate_voltage_drop,
    estimate_detector_count,
    get_detector_spacing,
    temperature_corrected_resistance,
)

# ═══════════════════════════════════════════════════════════════════════════════
# Fixtures
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.fixture
def valid_points():
    """Standard 10x10 square polygon points."""
    return (
        Point3D(x=0.0, y=0.0),
        Point3D(x=10.0, y=0.0),
        Point3D(x=10.0, y=10.0),
        Point3D(x=0.0, y=10.0),
    )


# ═══════════════════════════════════════════════════════════════════════════════
# 1. Extreme Ceiling Heights
# ═══════════════════════════════════════════════════════════════════════════════


class TestExtremeCeilingHeights:
    """NFPA 72 detector spacing with extreme ceiling heights."""

    def test_very_low_ceiling(self):
        """Height of 0.5m — very low ceiling, should use tightest spacing."""
        result = get_detector_spacing(0.5, "smoke")
        assert result.max_spacing_m <= 9.10  # Standard smoke spacing

    def test_ceiling_at_table_boundary(self):
        """Height exactly at table boundary (3.0m)."""
        result = get_detector_spacing(3.0, "smoke")
        assert result.max_spacing_m == 9.10

    def test_just_above_table_boundary(self):
        """Height just above a table boundary (3.1m)."""
        result = get_detector_spacing(3.1, "smoke")
        # Should use next row
        assert result.max_spacing_m <= 9.10

    def test_very_high_ceiling_smoke(self):
        """Height of 18m — near smoke detector limit."""
        result = get_detector_spacing(18.0, "smoke")
        assert result.max_spacing_m >= 3.0  # Conservative minimum

    def test_very_high_ceiling_heat(self):
        """Height of 15m — above heat detector table."""
        result = get_detector_spacing(15.0, "heat")
        assert result.max_spacing_m >= 3.0

    def test_zero_ceiling_height_rejected(self):
        """Height of 0 is invalid."""
        with pytest.raises(ValueError, match="positive finite"):
            get_detector_spacing(0.0, "smoke")

    def test_negative_ceiling_height_rejected(self):
        """Negative ceiling height is invalid."""
        with pytest.raises(ValueError, match="positive finite"):
            get_detector_spacing(-1.0, "smoke")

    def test_nan_ceiling_height_rejected(self):
        """NaN ceiling height is rejected."""
        with pytest.raises(ValueError, match="positive finite"):
            get_detector_spacing(float("nan"), "smoke")

    def test_inf_ceiling_height_rejected(self):
        """Infinity ceiling height is rejected."""
        with pytest.raises(ValueError, match="positive finite"):
            get_detector_spacing(float("inf"), "smoke")


# ═══════════════════════════════════════════════════════════════════════════════
# 2. Negative/Zero Dimensions
# ═══════════════════════════════════════════════════════════════════════════════


class TestNegativeZeroDimensions:
    """Negative and zero dimensions are rejected in models and calculations."""

    def test_point3d_rejects_nan_x(self):
        with pytest.raises(ValueError, match="finite"):
            Point3D(x=float("nan"), y=0.0)

    def test_point3d_rejects_nan_y(self):
        with pytest.raises(ValueError, match="finite"):
            Point3D(x=0.0, y=float("nan"))

    def test_point3d_rejects_nan_z(self):
        with pytest.raises(ValueError, match="finite"):
            Point3D(x=0.0, y=0.0, z=float("nan"))

    def test_point3d_rejects_inf_x(self):
        with pytest.raises(ValueError, match="finite"):
            Point3D(x=float("inf"), y=0.0)

    def test_point3d_rejects_neg_inf_y(self):
        with pytest.raises(ValueError, match="finite"):
            Point3D(x=0.0, y=float("-inf"))

    def test_semantic_properties_rejects_negative_height(self):
        with pytest.raises(ValueError, match="non-negative"):
            SemanticProperties(element_type=ElementType.WALL, height=-1.0)

    def test_semantic_properties_rejects_negative_width(self):
        with pytest.raises(ValueError, match="non-negative"):
            SemanticProperties(element_type=ElementType.WALL, width=-0.5)

    def test_semantic_properties_rejects_nan_height(self):
        with pytest.raises(ValueError, match="finite"):
            SemanticProperties(element_type=ElementType.WALL, height=float("nan"))

    def test_semantic_properties_rejects_inf_width(self):
        with pytest.raises(ValueError, match="finite"):
            SemanticProperties(element_type=ElementType.WALL, width=float("inf"))

    def test_semantic_properties_zero_height_allowed(self):
        """Zero height is allowed (e.g., a floor slab)."""
        props = SemanticProperties(element_type=ElementType.WALL, height=0.0)
        assert props.height == 0.0

    def test_semantic_properties_zero_width_allowed(self):
        """Zero width is allowed (e.g., a membrane)."""
        props = SemanticProperties(element_type=ElementType.WALL, width=0.0)
        assert props.width == 0.0

    def test_semantic_properties_none_height_allowed(self):
        """None height is allowed (unknown dimension)."""
        props = SemanticProperties(element_type=ElementType.WALL, height=None)
        assert props.height is None

    def test_detector_count_negative_area(self):
        """estimate_detector_count with negative area returns error."""
        result = estimate_detector_count(-100.0, 3.0, "smoke")
        assert result["min_detector_count"] == 0
        assert result["error"] is not None

    def test_detector_count_zero_area(self):
        """estimate_detector_count with zero area returns error."""
        result = estimate_detector_count(0.0, 3.0, "smoke")
        assert result["min_detector_count"] == 0

    def test_battery_negative_standby_rejected(self):
        """calculate_battery with negative standby current raises ValueError."""
        with pytest.raises(ValueError, match="non-negative finite"):
            calculate_battery(-0.5, 1.0)

    def test_battery_negative_alarm_rejected(self):
        """calculate_battery with negative alarm current raises ValueError."""
        with pytest.raises(ValueError, match="non-negative finite"):
            calculate_battery(0.5, -1.0)

    def test_battery_both_zero_rejected(self):
        """calculate_battery with both currents zero raises ValueError."""
        with pytest.raises(ValueError, match="no load"):
            calculate_battery(0.0, 0.0)

    def test_voltage_drop_negative_current_rejected(self):
        """calculate_voltage_drop with negative current raises ValueError."""
        with pytest.raises(ValueError, match="non-negative finite"):
            calculate_voltage_drop(-1.0, 100.0)

    def test_voltage_drop_negative_length_rejected(self):
        """calculate_voltage_drop with negative length raises ValueError."""
        with pytest.raises(ValueError, match="non-negative finite"):
            calculate_voltage_drop(1.0, -100.0)

    def test_voltage_drop_zero_voltage_rejected(self):
        """calculate_voltage_drop with zero ps_voltage raises ValueError."""
        with pytest.raises(ValueError, match="positive finite"):
            calculate_voltage_drop(1.0, 100.0, ps_voltage=0.0)

    def test_voltage_drop_negative_voltage_rejected(self):
        """calculate_voltage_drop with negative ps_voltage raises ValueError."""
        with pytest.raises(ValueError, match="positive finite"):
            calculate_voltage_drop(1.0, 100.0, ps_voltage=-24.0)


# ═══════════════════════════════════════════════════════════════════════════════
# 3. NaN/Inf Inputs in Calculations
# ═══════════════════════════════════════════════════════════════════════════════


class TestNaNInfInputs:
    """NaN and Inf inputs are rejected in all NFPA 72 calculations."""

    def test_spacing_nan_height(self):
        with pytest.raises(ValueError):
            get_detector_spacing(float("nan"), "smoke")

    def test_spacing_inf_height(self):
        with pytest.raises(ValueError):
            get_detector_spacing(float("inf"), "smoke")

    def test_detector_count_nan_area(self):
        result = estimate_detector_count(float("nan"), 3.0, "smoke")
        assert result["min_detector_count"] == 0
        assert result["area_per_detector_m2"] is None  # C-4 FIX

    def test_detector_count_inf_area(self):
        result = estimate_detector_count(float("inf"), 3.0, "smoke")
        assert result["min_detector_count"] == 0

    def test_battery_nan_standby(self):
        with pytest.raises(ValueError):
            calculate_battery(float("nan"), 1.0)

    def test_battery_nan_alarm(self):
        with pytest.raises(ValueError):
            calculate_battery(1.0, float("nan"))

    def test_battery_inf_standby(self):
        with pytest.raises(ValueError):
            calculate_battery(float("inf"), 1.0)

    def test_voltage_drop_nan_current(self):
        with pytest.raises(ValueError):
            calculate_voltage_drop(float("nan"), 100.0)

    def test_voltage_drop_nan_length(self):
        with pytest.raises(ValueError):
            calculate_voltage_drop(1.0, float("nan"))

    def test_voltage_drop_nan_voltage(self):
        with pytest.raises(ValueError):
            calculate_voltage_drop(1.0, 100.0, ps_voltage=float("nan"))

    def test_temp_corrected_resistance_nan(self):
        with pytest.raises(ValueError):
            temperature_corrected_resistance(float("nan"))

    def test_temp_corrected_resistance_inf(self):
        with pytest.raises(ValueError):
            temperature_corrected_resistance(float("inf"))

    def test_temp_corrected_resistance_negative(self):
        with pytest.raises(ValueError):
            temperature_corrected_resistance(-1.0)

    def test_battery_nan_safety_margin(self):
        with pytest.raises(ValueError):
            calculate_battery(1.0, 1.0, safety_margin=float("nan"))

    def test_battery_negative_safety_margin(self):
        with pytest.raises(ValueError):
            calculate_battery(1.0, 1.0, safety_margin=-0.1)

    def test_battery_zero_standby_hours(self):
        with pytest.raises(ValueError):
            calculate_battery(1.0, 1.0, standby_hours=0)

    def test_battery_zero_alarm_minutes(self):
        with pytest.raises(ValueError):
            calculate_battery(1.0, 1.0, alarm_minutes=0)


# ═══════════════════════════════════════════════════════════════════════════════
# 4. Empty Room Lists
# ═══════════════════════════════════════════════════════════════════════════════


class TestEmptyRoomLists:
    """Edge cases with empty room lists and zero-area rooms."""

    def test_estimate_detector_count_single_detector_room(self):
        """A small room that needs exactly 1 detector."""
        result = estimate_detector_count(10.0, 3.0, "smoke")
        assert result["min_detector_count"] >= 1

    def test_estimate_detector_count_very_small_room(self):
        """A 1 m² room still gets at least 1 detector."""
        result = estimate_detector_count(1.0, 3.0, "smoke")
        assert result["min_detector_count"] >= 1

    def test_geometry_zero_points(self):
        """Geometry with no points has zero area and perimeter."""
        geom = Geometry(points=(), polyline_closed=False)
        assert geom.area == 0.0
        assert geom.perimeter == 0.0

    def test_geometry_single_point(self):
        """Geometry with 1 point has zero area and perimeter."""
        geom = Geometry(points=(Point3D(x=0.0, y=0.0),), polyline_closed=False)
        assert geom.area == 0.0
        assert geom.perimeter == 0.0

    def test_geometry_two_points_open(self):
        """Open polyline with 2 points has perimeter but no area."""
        geom = Geometry(
            points=(Point3D(x=0.0, y=0.0), Point3D(x=10.0, y=0.0)),
            polyline_closed=False,
        )
        assert geom.area == 0.0
        assert geom.perimeter == 10.0

    def test_geometry_two_points_closed(self):
        """V83 FIX: Closed polyline with 2 points includes round-trip edge."""
        geom = Geometry(
            points=(Point3D(x=0.0, y=0.0), Point3D(x=10.0, y=0.0)),
            polyline_closed=True,
        )
        assert geom.perimeter == 20.0  # 10 out + 10 back


# ═══════════════════════════════════════════════════════════════════════════════
# 5. Single-Detector Rooms
# ═══════════════════════════════════════════════════════════════════════════════


class TestSingleDetectorRooms:
    """Small rooms where a single detector suffices."""

    def test_small_office_one_detector(self):
        """A 5x4m office (20 m²) needs at least 1 detector."""
        result = estimate_detector_count(20.0, 3.0, "smoke")
        assert result["min_detector_count"] >= 1

    def test_large_conference_multiple_detectors(self):
        """A 20x15m conference room (300 m²) needs multiple detectors."""
        result = estimate_detector_count(300.0, 3.0, "smoke")
        assert result["min_detector_count"] > 1

    def test_high_ceiling_reduces_spacing(self):
        """Higher ceilings produce tighter spacing for heat detectors only.
        Per NFPA 72-2022 Table 17.6.3.1, smoke detector spacing is flat 9.1m
        at all ceiling heights — so we test heat detectors here.
        """
        low = get_detector_spacing(3.0, "heat")
        high = get_detector_spacing(9.0, "heat")
        assert high.max_spacing_m <= low.max_spacing_m

    def test_smoke_spacing_flat_at_all_heights(self):
        """NFPA 72-2022: smoke detector spacing is flat 9.1m at all ceiling heights."""
        low = get_detector_spacing(3.0, "smoke")
        high = get_detector_spacing(9.0, "smoke")
        assert low.max_spacing_m == 9.1
        assert high.max_spacing_m == 9.1


# ═══════════════════════════════════════════════════════════════════════════════
# 6. Very Large Rooms
# ═══════════════════════════════════════════════════════════════════════════════


class TestVeryLargeRooms:
    """Large rooms like warehouses and auditoriums."""

    def test_warehouse_5000_sqm(self):
        """5000 m² warehouse needs many detectors."""
        result = estimate_detector_count(5000.0, 4.0, "smoke")
        assert result["min_detector_count"] > 10

    def test_auditorium_10000_sqm(self):
        """10000 m² auditorium needs even more detectors."""
        result = estimate_detector_count(10000.0, 6.0, "smoke")
        assert result["min_detector_count"] > 20

    def test_detector_count_scales_with_area(self):
        """Detector count roughly scales with area."""
        small = estimate_detector_count(100.0, 3.0, "smoke")
        large = estimate_detector_count(1000.0, 3.0, "smoke")
        assert large["min_detector_count"] > small["min_detector_count"]


# ═══════════════════════════════════════════════════════════════════════════════
# 7. Point3D and Geometry Edge Cases
# ═══════════════════════════════════════════════════════════════════════════════


class TestPoint3DEdgeCases:
    """Point3D edge cases."""

    def test_origin(self):
        p = Point3D(x=0.0, y=0.0, z=0.0)
        assert p.x == 0.0
        assert p.y == 0.0
        assert p.z == 0.0

    def test_default_z_is_zero(self):
        p = Point3D(x=1.0, y=2.0)
        assert p.z == 0.0

    def test_very_large_coordinates(self):
        """Very large but finite coordinates are accepted."""
        p = Point3D(x=1e10, y=1e10, z=1e10)
        assert p.x == 1e10

    def test_very_small_coordinates(self):
        """Very small coordinates are accepted."""
        p = Point3D(x=1e-15, y=1e-15, z=1e-15)
        assert p.x == 1e-15

    def test_negative_coordinates_allowed(self):
        """Negative coordinates are valid (e.g., below ground level)."""
        p = Point3D(x=-5.0, y=-3.0, z=-2.0)
        assert p.x == -5.0


class TestGeometryEdgeCases:
    """Geometry edge cases."""

    def test_triangle_area(self):
        """Right triangle with area 50 m²."""
        pts = (
            Point3D(x=0.0, y=0.0),
            Point3D(x=10.0, y=0.0),
            Point3D(x=0.0, y=10.0),
        )
        geom = Geometry(points=pts, polyline_closed=True)
        assert abs(geom.area - 50.0) < 0.01

    def test_degenerate_collinear_polygon(self):
        """Three collinear points have zero area."""
        pts = (
            Point3D(x=0.0, y=0.0),
            Point3D(x=5.0, y=0.0),
            Point3D(x=10.0, y=0.0),
        )
        geom = Geometry(points=pts, polyline_closed=True)
        assert geom.area == 0.0

    def test_open_polyline_no_area(self):
        """Open polyline has zero area regardless of shape."""
        pts = (
            Point3D(x=0.0, y=0.0),
            Point3D(x=10.0, y=0.0),
            Point3D(x=10.0, y=10.0),
        )
        geom = Geometry(points=pts, polyline_closed=False)
        assert geom.area == 0.0

    def test_l_shaped_room_area(self):
        """L-shaped polygon area calculation."""
        pts = (
            Point3D(x=0.0, y=0.0),
            Point3D(x=10.0, y=0.0),
            Point3D(x=10.0, y=5.0),
            Point3D(x=5.0, y=5.0),
            Point3D(x=5.0, y=10.0),
            Point3D(x=0.0, y=10.0),
        )
        geom = Geometry(points=pts, polyline_closed=True)
        # L-shape: 10x5 + 5x5 = 75 m²
        assert abs(geom.area - 75.0) < 0.01


# ═══════════════════════════════════════════════════════════════════════════════
# 8. SemanticProperties Validation Edge Cases
# ═══════════════════════════════════════════════════════════════════════════════


class TestSemanticPropertiesEdgeCases:
    """SemanticProperties validation edge cases."""

    def test_to_dict_with_enum_type(self):
        """to_dict serializes ElementType enum correctly."""
        props = SemanticProperties(element_type=ElementType.WALL, name="Wall-1")
        d = props.to_dict()
        assert d["element_type"] == "wall"

    def test_to_dict_with_string_type(self):
        """to_dict serializes string element_type correctly."""
        props = SemanticProperties(element_type="custom_type", name="Custom")
        d = props.to_dict()
        assert d["element_type"] == "custom_type"

    def test_all_optional_fields_none(self):
        """All optional fields default to None."""
        props = SemanticProperties(element_type=ElementType.ROOM)
        assert props.description is None
        assert props.material is None
        assert props.fire_rating is None
        assert props.height is None
        assert props.width is None
        assert props.layer is None
        assert props.revit_category is None


# ═══════════════════════════════════════════════════════════════════════════════
# 9. UniversalElement Immutability Edge Cases
# ═══════════════════════════════════════════════════════════════════════════════


class TestUniversalElementEdgeCases:
    """UniversalElement immutability and mandatory ID enforcement."""

    def test_empty_element_id_rejected(self):
        """V83 FIX: Empty element_id is rejected."""
        with pytest.raises(ValueError, match="MANDATORY"):
            UniversalElement(element_id="")

    def test_valid_element_id_accepted(self):
        """Non-empty element_id is accepted."""
        elem = UniversalElement(element_id="test-id-123")
        assert elem.element_id == "test-id-123"

    def test_frozen_immutability(self):
        """UniversalElement is frozen — cannot modify fields."""
        elem = UniversalElement(element_id="test-id")
        with pytest.raises(AttributeError):
            elem.element_id = "new-id"

    def test_to_dict_round_trip(self):
        """to_dict produces a serializable dictionary."""
        elem = UniversalElement(
            element_id="elem-1",
            properties=SemanticProperties(element_type=ElementType.WALL, name="Wall"),
            source_file="test.py",
        )
        d = elem.to_dict()
        assert d["element_id"] == "elem-1"
        assert d["source_file"] == "test.py"
        assert isinstance(d["properties"], dict)

    def test_relationship_to_dict(self):
        """Relationship.to_dict includes connection_id."""
        rel = Relationship(
            from_element_id="A",
            to_element_id="B",
            relationship_type="adjacent",
            connection_id="conn-1",
        )
        d = rel.to_dict()
        assert d["connection_id"] == "conn-1"

    def test_conflict_defaults(self):
        """Conflict dataclass has sensible defaults."""
        conflict = Conflict()
        assert conflict.conflict_id == ""
        assert conflict.resolved is False
        assert conflict.conflict_type == ConflictType.GEOMETRY_MISMATCH


# ═══════════════════════════════════════════════════════════════════════════════
# 10. Temperature Correction Edge Cases
# ═══════════════════════════════════════════════════════════════════════════════


class TestTemperatureCorrectionEdgeCases:
    """Temperature-corrected resistance edge cases."""

    def test_at_reference_temp_20c(self):
        """At 20°C reference temperature, resistance is unchanged."""
        r = temperature_corrected_resistance(8.45, 20.0)
        assert abs(r - 8.45) < 0.001

    def test_at_75c_higher_resistance(self):
        """At 75°C, resistance is ~21.6% higher than at 20°C."""
        r_20 = temperature_corrected_resistance(8.45, 20.0)
        r_75 = temperature_corrected_resistance(8.45, 75.0)
        assert r_75 > r_20
        increase_pct = (r_75 / r_20 - 1) * 100
        assert abs(increase_pct - 21.6) < 1.0

    def test_below_freezing(self):
        """Below 0°C, resistance decreases but remains positive."""
        r = temperature_corrected_resistance(8.45, -10.0)
        assert r > 0
        assert r < 8.45

    def test_extreme_cold_rejected(self):
        """Below -50°C is rejected (unrealistic for building wiring)."""
        with pytest.raises(ValueError):
            temperature_corrected_resistance(8.45, -60.0)

    def test_zero_resistance(self):
        """Zero resistance is accepted (superconductor edge case)."""
        r = temperature_corrected_resistance(0.0, 75.0)
        assert r == 0.0
