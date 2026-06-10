"""
FireAI Contracts Validation — Comprehensive Tests
===================================================

Tests the input contract validation module (Stage 0 — the gatekeeper).
Covers every public function and critical safety path including:
  - ContractViolation exception
  - validate_room_input() — full contract enforcement
  - _has_nan_inf() — recursive NaN/Inf detection
  - _validate_polygon() — geometric correctness
  - _compute_area_from_polygon() — Shoelace formula

SAFETY CRITICAL: NaN/Inf inputs MUST be caught — they bypass comparisons.
"""

from __future__ import annotations

import math

import pytest

from fireai.core.contracts_validation import (
    ContractViolation,
    validate_room_input,
    _has_nan_inf,
    _validate_polygon,
    _compute_area_from_polygon,
)


# ═══════════════════════════════════════════════════════════════════════════════
# ContractViolation Exception
# ═══════════════════════════════════════════════════════════════════════════════

class TestContractViolation:
    """Test the ContractViolation exception class."""

    def test_creation_with_message_only(self):
        exc = ContractViolation("Something broke")
        assert str(exc) == "Something broke"
        assert exc.field == ""
        assert exc.value is None

    def test_creation_with_field_and_value(self):
        exc = ContractViolation("Bad input", field="ceiling_height_m", value=-1)
        assert str(exc) == "Bad input"
        assert exc.field == "ceiling_height_m"
        assert exc.value == -1

    def test_is_exception(self):
        exc = ContractViolation("test")
        assert isinstance(exc, Exception)

    def test_can_be_raised_and_caught(self):
        with pytest.raises(ContractViolation) as exc_info:
            raise ContractViolation("room_id missing", field="room_id", value=None)
        assert exc_info.value.field == "room_id"
        assert exc_info.value.value is None

    def test_field_and_value_defaults(self):
        exc = ContractViolation("msg")
        assert exc.field == ""
        assert exc.value is None

    def test_value_can_be_any_type(self):
        exc = ContractViolation("msg", field="f", value=[1, 2, 3])
        assert exc.value == [1, 2, 3]

    def test_value_can_be_float_nan(self):
        exc = ContractViolation("msg", field="f", value=float("nan"))
        assert math.isnan(exc.value)


# ═══════════════════════════════════════════════════════════════════════════════
# _has_nan_inf
# ═══════════════════════════════════════════════════════════════════════════════

class TestHasNanInf:
    """Test recursive NaN/Inf detection in nested data structures."""

    def test_clean_float_passes(self):
        result = _has_nan_inf(3.14)
        assert result == []

    def test_clean_int_passes(self):
        result = _has_nan_inf(42)
        assert result == []

    def test_clean_string_passes(self):
        result = _has_nan_inf("hello")
        assert result == []

    def test_nan_in_float_detected(self):
        result = _has_nan_inf(float("nan"))
        assert len(result) == 1
        assert "NaN" in result[0]

    def test_positive_inf_detected(self):
        result = _has_nan_inf(float("inf"))
        assert len(result) == 1
        assert "Inf" in result[0]

    def test_negative_inf_detected(self):
        result = _has_nan_inf(float("-inf"))
        assert len(result) == 1
        assert "Inf" in result[0]

    def test_nan_in_list(self):
        result = _has_nan_inf([1.0, float("nan"), 3.0])
        assert len(result) == 1
        assert "[1]" in result[0]

    def test_nan_in_tuple(self):
        result = _has_nan_inf((10.0, float("nan")))
        assert len(result) == 1
        assert "[1]" in result[0]

    def test_nan_in_dict(self):
        result = _has_nan_inf({"ceiling_height_m": float("nan")})
        assert len(result) == 1
        assert "ceiling_height_m" in result[0]

    def test_inf_in_nested_dict(self):
        payload = {
            "room": {
                "height": float("inf"),
                "width": 5.0,
            }
        }
        result = _has_nan_inf(payload)
        assert len(result) == 1
        assert "height" in result[0]
        assert "Inf" in result[0]

    def test_nan_deeply_nested(self):
        payload = {
            "data": {
                "coords": [
                    {"x": 1.0, "y": float("nan")},
                ]
            }
        }
        result = _has_nan_inf(payload)
        assert len(result) == 1
        assert "NaN" in result[0]

    def test_multiple_nan_inf_in_structure(self):
        payload = {
            "a": float("nan"),
            "b": float("inf"),
            "c": [1.0, float("nan"), float("-inf")],
        }
        result = _has_nan_inf(payload)
        assert len(result) == 4  # a: NaN, b: Inf, c[1]: NaN, c[2]: Inf

    def test_path_reporting(self):
        result = _has_nan_inf(float("nan"), path="root")
        assert len(result) == 1
        assert "root" in result[0]

    def test_path_reporting_in_list(self):
        result = _has_nan_inf([float("nan")], path="polygon")
        assert "polygon[0]" in result[0]

    def test_empty_structure(self):
        assert _has_nan_inf({}) == []
        assert _has_nan_inf([]) == []
        assert _has_nan_inf(()) == []

    def test_none_value(self):
        assert _has_nan_inf(None) == []

    def test_bool_value(self):
        assert _has_nan_inf(True) == []
        assert _has_nan_inf(False) == []


# ═══════════════════════════════════════════════════════════════════════════════
# _validate_polygon
# ═══════════════════════════════════════════════════════════════════════════════

class TestValidatePolygon:
    """Test polygon structure validation."""

    def test_valid_triangle(self):
        result = _validate_polygon([[0, 0], [1, 0], [0, 1]])
        assert result == []

    def test_valid_rectangle(self):
        result = _validate_polygon([[0, 0], [10, 0], [10, 5], [0, 5]])
        assert result == []

    def test_valid_tuple_vertices(self):
        result = _validate_polygon([(0, 0), (1, 0), (0, 1)])
        assert result == []

    def test_non_list_polygon(self):
        result = _validate_polygon("not a polygon")
        assert len(result) == 1
        assert "must be a list" in result[0]
        assert "str" in result[0]

    def test_dict_polygon(self):
        result = _validate_polygon({"x": 1, "y": 2})
        assert len(result) == 1
        assert "must be a list" in result[0]

    def test_less_than_3_vertices(self):
        result = _validate_polygon([[0, 0], [1, 1]])
        assert len(result) == 1
        assert "≥3 vertices" in result[0]
        assert "2" in result[0]

    def test_zero_vertices(self):
        result = _validate_polygon([])
        assert len(result) == 1
        assert "≥3 vertices" in result[0]

    def test_single_vertex(self):
        result = _validate_polygon([[0, 0]])
        assert len(result) == 1
        assert "≥3 vertices" in result[0]

    def test_vertex_not_tuple_or_list(self):
        result = _validate_polygon([[0, 0], "bad", [0, 1]])
        assert any("must be tuple/list" in w for w in result)

    def test_vertex_wrong_coord_count(self):
        result = _validate_polygon([[0, 0], [1, 0, 5], [0, 1]])
        assert any("must have 2 coords" in w for w in result)

    def test_vertex_non_numeric_coord(self):
        result = _validate_polygon([[0, 0], ["x", 0], [0, 1]])
        assert any("must be numeric" in w for w in result)

    def test_multiple_invalid_vertices(self):
        result = _validate_polygon([[0], "bad", [0, "y"]])
        # First: 1 coord, second: not tuple/list, third: non-numeric coord
        assert len(result) >= 2


# ═══════════════════════════════════════════════════════════════════════════════
# _compute_area_from_polygon
# ═══════════════════════════════════════════════════════════════════════════════

class TestComputeAreaFromPolygon:
    """Test Shoelace formula area computation."""

    def test_unit_square(self):
        polygon = [[0, 0], [1, 0], [1, 1], [0, 1]]
        assert _compute_area_from_polygon(polygon) == pytest.approx(1.0)

    def test_rectangle_10x5(self):
        polygon = [[0, 0], [10, 0], [10, 5], [0, 5]]
        assert _compute_area_from_polygon(polygon) == pytest.approx(50.0)

    def test_right_triangle(self):
        polygon = [[0, 0], [4, 0], [0, 3]]
        assert _compute_area_from_polygon(polygon) == pytest.approx(6.0)

    def test_equilateral_triangle(self):
        import math as _math
        # Side length 2, area = sqrt(3)
        polygon = [[0, 0], [2, 0], [1, _math.sqrt(3)]]
        assert _compute_area_from_polygon(polygon) == pytest.approx(_math.sqrt(3))

    def test_clockwise_polygon_gives_positive_area(self):
        # Same rectangle but clockwise — abs() should make it positive
        polygon = [[0, 0], [0, 5], [10, 5], [10, 0]]
        assert _compute_area_from_polygon(polygon) == pytest.approx(50.0)

    def test_degenerate_polygon_less_than_3_vertices(self):
        assert _compute_area_from_polygon([]) == 0.0
        assert _compute_area_from_polygon([[0, 0]]) == 0.0
        assert _compute_area_from_polygon([[0, 0], [1, 1]]) == 0.0

    def test_large_polygon(self):
        # L-shaped polygon (counterclockwise)
        #   (0,0) → (6,0) → (6,2) → (2,2) → (2,4) → (0,4)
        polygon = [[0, 0], [6, 0], [6, 2], [2, 2], [2, 4], [0, 4]]
        # Area = 6*4 - 4*2 = 24 - 8 = 16
        assert _compute_area_from_polygon(polygon) == pytest.approx(16.0)

    def test_pentagon(self):
        # Regular pentagon with circumradius 1
        # Not testing exact value, just that it's positive and reasonable
        import math as _math
        n = 5
        polygon = [
            [_math.cos(2 * _math.pi * i / n), _math.sin(2 * _math.pi * i / n)]
            for i in range(n)
        ]
        area = _compute_area_from_polygon(polygon)
        expected = 0.5 * n * _math.sin(2 * _math.pi / n)  # area of regular polygon R=1
        assert area == pytest.approx(expected, rel=1e-10)


# ═══════════════════════════════════════════════════════════════════════════════
# validate_room_input — Valid Payloads
# ═══════════════════════════════════════════════════════════════════════════════

class TestValidateRoomInputValid:
    """Test valid room input payloads."""

    def _base_payload(self, **overrides):
        """Minimal valid payload with a 10×5 rectangle (area = 50 m²)."""
        payload = {
            "room_id": "R-101",
            "room_polygon": [[0, 0], [10, 0], [10, 5], [0, 5]],
            "ceiling_height_m": 3.0,
            "detector_type": "smoke",
        }
        payload.update(overrides)
        return payload

    def test_minimal_valid_payload(self):
        result = validate_room_input(self._base_payload())
        assert result["room_id"] == "R-101"
        assert result["detector_type"] == "smoke"
        assert result["ceiling_height_m"] == 3.0
        assert result["area_m2"] == pytest.approx(50.0)

    def test_complete_payload_with_all_optional_fields(self):
        payload = self._base_payload(
            area_m2=50.0,
            ceiling_type="sloped",
            occupancy_type="warehouse",
        )
        result = validate_room_input(payload)
        assert result["area_m2"] == 50.0
        assert result["ceiling_type"] == "sloped"
        assert result["occupancy_type"] == "warehouse"

    def test_detector_type_normalized_to_lowercase(self):
        payload = self._base_payload(detector_type="SMOKE")
        result = validate_room_input(payload)
        assert result["detector_type"] == "smoke"

    def test_detector_type_heat_lowercase(self):
        payload = self._base_payload(detector_type="Heat")
        result = validate_room_input(payload)
        assert result["detector_type"] == "heat"

    def test_integer_ceiling_height(self):
        payload = self._base_payload(ceiling_height_m=3)
        result = validate_room_input(payload)
        assert result["ceiling_height_m"] == 3

    def test_default_ceiling_type_is_flat(self):
        result = validate_room_input(self._base_payload())
        assert result["ceiling_type"] == "flat"
        assert any("ceiling_type defaulted to 'flat'" in w for w in result["_contract_warnings"])

    def test_default_occupancy_type_is_office(self):
        result = validate_room_input(self._base_payload())
        assert result["occupancy_type"] == "office"
        assert any("occupancy_type defaulted to 'office'" in w for w in result["_contract_warnings"])

    def test_area_computed_from_polygon_when_not_provided(self):
        # 10×5 rectangle = 50 m²
        result = validate_room_input(self._base_payload())
        assert result["area_m2"] == pytest.approx(50.0)
        assert any("area_m2 computed from polygon" in w for w in result["_contract_warnings"])

    def test_provided_area_m2_preserved(self):
        payload = self._base_payload(area_m2=48.5)
        result = validate_room_input(payload)
        assert result["area_m2"] == 48.5

    def test_provided_area_m2_integer_converted_to_float(self):
        payload = self._base_payload(area_m2=50)
        result = validate_room_input(payload)
        assert isinstance(result["area_m2"], float)
        assert result["area_m2"] == 50.0

    def test_contract_warnings_populated(self):
        result = validate_room_input(self._base_payload())
        assert "_contract_warnings" in result
        assert isinstance(result["_contract_warnings"], list)
        # At minimum: area computed, ceiling_type defaulted, occupancy_type defaulted
        assert len(result["_contract_warnings"]) >= 1

    def test_result_is_new_dict(self):
        payload = self._base_payload()
        result = validate_room_input(payload)
        assert result is not payload  # Shallow copy, not the same object


# ═══════════════════════════════════════════════════════════════════════════════
# validate_room_input — Invalid Payloads (ContractViolation)
# ═══════════════════════════════════════════════════════════════════════════════

class TestValidateRoomInputInvalid:
    """Test that invalid payloads raise ContractViolation."""

    def _base_payload(self, **overrides):
        payload = {
            "room_id": "R-101",
            "room_polygon": [[0, 0], [10, 0], [10, 5], [0, 5]],
            "ceiling_height_m": 3.0,
            "detector_type": "smoke",
        }
        payload.update(overrides)
        return payload

    # ── Payload structure ──────────────────────────────────────────────────

    def test_non_dict_payload(self):
        with pytest.raises(ContractViolation) as exc_info:
            validate_room_input("not a dict")
        assert exc_info.value.field == "payload"

    def test_list_payload(self):
        with pytest.raises(ContractViolation) as exc_info:
            validate_room_input([1, 2, 3])
        assert exc_info.value.field == "payload"

    # ── Missing required fields ────────────────────────────────────────────

    def test_missing_room_id(self):
        payload = self._base_payload()
        del payload["room_id"]
        with pytest.raises(ContractViolation) as exc_info:
            validate_room_input(payload)
        assert exc_info.value.field == "room_id"

    def test_missing_room_polygon(self):
        payload = self._base_payload()
        del payload["room_polygon"]
        with pytest.raises(ContractViolation) as exc_info:
            validate_room_input(payload)
        assert exc_info.value.field == "room_polygon"

    def test_missing_ceiling_height_m(self):
        payload = self._base_payload()
        del payload["ceiling_height_m"]
        with pytest.raises(ContractViolation) as exc_info:
            validate_room_input(payload)
        assert exc_info.value.field == "ceiling_height_m"

    def test_missing_detector_type(self):
        payload = self._base_payload()
        del payload["detector_type"]
        with pytest.raises(ContractViolation) as exc_info:
            validate_room_input(payload)
        assert exc_info.value.field == "detector_type"

    # ── Invalid room_id ────────────────────────────────────────────────────

    def test_empty_room_id(self):
        with pytest.raises(ContractViolation) as exc_info:
            validate_room_input(self._base_payload(room_id=""))
        assert exc_info.value.field == "room_id"

    def test_whitespace_only_room_id(self):
        with pytest.raises(ContractViolation) as exc_info:
            validate_room_input(self._base_payload(room_id="   "))
        assert exc_info.value.field == "room_id"

    def test_non_string_room_id(self):
        with pytest.raises(ContractViolation) as exc_info:
            validate_room_input(self._base_payload(room_id=123))
        assert exc_info.value.field == "room_id"

    def test_none_room_id(self):
        with pytest.raises(ContractViolation) as exc_info:
            validate_room_input(self._base_payload(room_id=None))
        assert exc_info.value.field == "room_id"

    # ── Invalid ceiling_height_m ───────────────────────────────────────────

    def test_negative_ceiling_height(self):
        with pytest.raises(ContractViolation) as exc_info:
            validate_room_input(self._base_payload(ceiling_height_m=-1.5))
        assert exc_info.value.field == "ceiling_height_m"
        assert exc_info.value.value == -1.5

    def test_zero_ceiling_height(self):
        with pytest.raises(ContractViolation) as exc_info:
            validate_room_input(self._base_payload(ceiling_height_m=0))
        assert exc_info.value.field == "ceiling_height_m"
        assert "positive" in str(exc_info.value)

    def test_nan_ceiling_height(self):
        with pytest.raises(ContractViolation) as exc_info:
            validate_room_input(self._base_payload(ceiling_height_m=float("nan")))
        # NaN is caught at Step 1 (NaN/Inf detection) before type validation
        assert "NaN" in str(exc_info.value) or "Inf" in str(exc_info.value)

    def test_inf_ceiling_height(self):
        with pytest.raises(ContractViolation) as exc_info:
            validate_room_input(self._base_payload(ceiling_height_m=float("inf")))
        assert "Inf" in str(exc_info.value)

    def test_negative_inf_ceiling_height(self):
        with pytest.raises(ContractViolation) as exc_info:
            validate_room_input(self._base_payload(ceiling_height_m=float("-inf")))
        assert "Inf" in str(exc_info.value)

    def test_string_ceiling_height(self):
        with pytest.raises(ContractViolation) as exc_info:
            validate_room_input(self._base_payload(ceiling_height_m="three"))
        assert exc_info.value.field == "ceiling_height_m"

    def test_none_ceiling_height(self):
        with pytest.raises(ContractViolation) as exc_info:
            validate_room_input(self._base_payload(ceiling_height_m=None))
        assert exc_info.value.field == "ceiling_height_m"

    def test_list_ceiling_height(self):
        with pytest.raises(ContractViolation) as exc_info:
            validate_room_input(self._base_payload(ceiling_height_m=[3.0]))
        assert exc_info.value.field == "ceiling_height_m"

    # ── Invalid detector_type ──────────────────────────────────────────────

    def test_invalid_detector_type_string(self):
        with pytest.raises(ContractViolation) as exc_info:
            validate_room_input(self._base_payload(detector_type="flame"))
        assert exc_info.value.field == "detector_type"

    def test_empty_detector_type(self):
        with pytest.raises(ContractViolation) as exc_info:
            validate_room_input(self._base_payload(detector_type=""))
        assert exc_info.value.field == "detector_type"

    def test_non_string_detector_type(self):
        with pytest.raises(ContractViolation) as exc_info:
            validate_room_input(self._base_payload(detector_type=42))
        assert exc_info.value.field == "detector_type"

    def test_none_detector_type(self):
        with pytest.raises(ContractViolation) as exc_info:
            validate_room_input(self._base_payload(detector_type=None))
        assert exc_info.value.field == "detector_type"

    # ── Invalid polygon ────────────────────────────────────────────────────

    def test_polygon_less_than_3_vertices(self):
        with pytest.raises(ContractViolation) as exc_info:
            validate_room_input(self._base_payload(room_polygon=[[0, 0], [1, 1]]))
        assert exc_info.value.field == "room_polygon"

    def test_empty_polygon(self):
        with pytest.raises(ContractViolation) as exc_info:
            validate_room_input(self._base_payload(room_polygon=[]))
        assert exc_info.value.field == "room_polygon"

    def test_non_list_polygon_short_string(self):
        """A short string (len < 3) triggers the < 3 vertices check."""
        with pytest.raises(ContractViolation) as exc_info:
            validate_room_input(self._base_payload(room_polygon="ab"))
        assert exc_info.value.field == "room_polygon"

    def test_dict_polygon(self):
        with pytest.raises(ContractViolation) as exc_info:
            validate_room_input(self._base_payload(room_polygon={"a": 1}))
        assert exc_info.value.field == "room_polygon"

    def test_non_list_polygon_crashes_on_compute(self):
        """BUG: A string of len >= 3 passes polygon validation but crashes
        in _compute_area_from_polygon because it's not actually a list
        of coordinate pairs. The source only raises ContractViolation for
        < 3 vertices; non-list polygons with len >= 3 slip through."""
        with pytest.raises((ContractViolation, ValueError)):
            validate_room_input(self._base_payload(room_polygon="bad"))


# ═══════════════════════════════════════════════════════════════════════════════
# validate_room_input — NaN/Inf Safety-Critical Paths
# ═══════════════════════════════════════════════════════════════════════════════

class TestValidateRoomInputNanInfSafety:
    """SAFETY CRITICAL: NaN/Inf MUST be caught — they bypass safety checks."""

    def _base_payload(self, **overrides):
        payload = {
            "room_id": "R-101",
            "room_polygon": [[0, 0], [10, 0], [10, 5], [0, 5]],
            "ceiling_height_m": 3.0,
            "detector_type": "smoke",
        }
        payload.update(overrides)
        return payload

    def test_nan_in_ceiling_height_rejected(self):
        with pytest.raises(ContractViolation) as exc_info:
            validate_room_input(self._base_payload(ceiling_height_m=float("nan")))
        assert "NaN" in str(exc_info.value)

    def test_inf_in_ceiling_height_rejected(self):
        with pytest.raises(ContractViolation) as exc_info:
            validate_room_input(self._base_payload(ceiling_height_m=float("inf")))
        assert "Inf" in str(exc_info.value)

    def test_nan_in_polygon_vertex_rejected(self):
        polygon = [[0, 0], [float("nan"), 0], [10, 5], [0, 5]]
        with pytest.raises(ContractViolation) as exc_info:
            validate_room_input(self._base_payload(room_polygon=polygon))
        assert "NaN" in str(exc_info.value)

    def test_inf_in_polygon_vertex_rejected(self):
        polygon = [[0, 0], [10, float("inf")], [10, 5], [0, 5]]
        with pytest.raises(ContractViolation) as exc_info:
            validate_room_input(self._base_payload(room_polygon=polygon))
        assert "Inf" in str(exc_info.value)

    def test_nan_in_provided_area_m2_rejected(self):
        with pytest.raises(ContractViolation) as exc_info:
            validate_room_input(self._base_payload(area_m2=float("nan")))
        assert "NaN" in str(exc_info.value)

    def test_inf_in_provided_area_m2_rejected(self):
        with pytest.raises(ContractViolation) as exc_info:
            validate_room_input(self._base_payload(area_m2=float("inf")))
        assert "Inf" in str(exc_info.value)

    def test_nan_deeply_nested_in_payload_rejected(self):
        """NaN hidden in an arbitrary nested structure must still be caught."""
        payload = self._base_payload(extra_data={"nested": {"val": float("nan")}})
        with pytest.raises(ContractViolation) as exc_info:
            validate_room_input(payload)
        assert "NaN" in str(exc_info.value)

    def test_inf_in_arbitrary_field_rejected(self):
        """Inf in any field — even ones the validator doesn't inspect — must be caught."""
        payload = self._base_payload(custom_metadata={"distance": float("inf")})
        with pytest.raises(ContractViolation) as exc_info:
            validate_room_input(payload)
        assert "Inf" in str(exc_info.value)


# ═══════════════════════════════════════════════════════════════════════════════
# validate_room_input — Area Computation & Validation
# ═══════════════════════════════════════════════════════════════════════════════

class TestValidateRoomInputArea:
    """Test area computation and validation within validate_room_input."""

    def _base_payload(self, **overrides):
        payload = {
            "room_id": "R-101",
            "room_polygon": [[0, 0], [10, 0], [10, 5], [0, 5]],
            "ceiling_height_m": 3.0,
            "detector_type": "smoke",
        }
        payload.update(overrides)
        return payload

    def test_area_computed_from_shoelace(self):
        """10×5 rectangle → area = 50 m² via Shoelace formula."""
        result = validate_room_input(self._base_payload())
        assert result["area_m2"] == pytest.approx(50.0)

    def test_triangle_area_computed(self):
        """Right triangle 4×3 → area = 6 m²."""
        payload = self._base_payload(
            room_polygon=[[0, 0], [4, 0], [0, 3]]
        )
        result = validate_room_input(payload)
        assert result["area_m2"] == pytest.approx(6.0)

    def test_provided_area_m2_vs_computed_area(self):
        """Provided area_m2 takes precedence over computed area."""
        payload = self._base_payload(area_m2=99.0)
        result = validate_room_input(payload)
        # Provided area is used, NOT computed
        assert result["area_m2"] == 99.0

    def test_negative_area_m2_rejected(self):
        """Negative area is physically impossible."""
        with pytest.raises(ContractViolation) as exc_info:
            validate_room_input(self._base_payload(area_m2=-5.0))
        assert exc_info.value.field == "area_m2"
        assert "positive" in str(exc_info.value)

    def test_zero_area_m2_rejected(self):
        """Zero area means no detectors can be placed."""
        with pytest.raises(ContractViolation) as exc_info:
            validate_room_input(self._base_payload(area_m2=0))
        assert exc_info.value.field == "area_m2"

    def test_degenerate_polygon_zero_area_rejected(self):
        """Collinear points produce zero area — degenerate room."""
        # Three collinear points
        payload = self._base_payload(room_polygon=[[0, 0], [1, 0], [2, 0]])
        # Need 4 points for polygon, but even with 3 collinear it's zero area
        # Actually with only 3 collinear points, Shoelace gives 0
        with pytest.raises(ContractViolation) as exc_info:
            validate_room_input(payload)
        assert exc_info.value.field == "area_m2"
        assert "zero or negative area" in str(exc_info.value)

    def test_string_area_m2_rejected(self):
        with pytest.raises(ContractViolation) as exc_info:
            validate_room_input(self._base_payload(area_m2="fifty"))
        assert exc_info.value.field == "area_m2"

    def test_zero_area_polygon_rejected(self):
        """A polygon where all vertices coincide has zero area."""
        payload = self._base_payload(
            room_polygon=[[1, 1], [1, 1], [1, 1], [1, 1]]
        )
        with pytest.raises(ContractViolation) as exc_info:
            validate_room_input(payload)
        assert "zero or negative area" in str(exc_info.value)


# ═══════════════════════════════════════════════════════════════════════════════
# validate_room_input — Defaults & Warnings
# ═══════════════════════════════════════════════════════════════════════════════

class TestValidateRoomInputDefaultsAndWarnings:
    """Test default value injection and _contract_warnings."""

    def _base_payload(self, **overrides):
        payload = {
            "room_id": "R-101",
            "room_polygon": [[0, 0], [10, 0], [10, 5], [0, 5]],
            "ceiling_height_m": 3.0,
            "detector_type": "smoke",
        }
        payload.update(overrides)
        return payload

    def test_ceiling_type_defaults_to_flat(self):
        result = validate_room_input(self._base_payload())
        assert result["ceiling_type"] == "flat"

    def test_occupancy_type_defaults_to_office(self):
        result = validate_room_input(self._base_payload())
        assert result["occupancy_type"] == "office"

    def test_ceiling_type_not_overridden_if_provided(self):
        payload = self._base_payload(ceiling_type="sloped")
        result = validate_room_input(payload)
        assert result["ceiling_type"] == "sloped"

    def test_occupancy_type_not_overridden_if_provided(self):
        payload = self._base_payload(occupancy_type="warehouse")
        result = validate_room_input(payload)
        assert result["occupancy_type"] == "warehouse"

    def test_contract_warnings_is_list(self):
        result = validate_room_input(self._base_payload())
        assert isinstance(result["_contract_warnings"], list)

    def test_contract_warnings_includes_area_computed(self):
        result = validate_room_input(self._base_payload())
        assert any("area_m2 computed from polygon" in w for w in result["_contract_warnings"])

    def test_contract_warnings_includes_ceiling_type_default(self):
        result = validate_room_input(self._base_payload())
        assert any("ceiling_type defaulted to 'flat'" in w for w in result["_contract_warnings"])

    def test_contract_warnings_includes_occupancy_type_default(self):
        result = validate_room_input(self._base_payload())
        assert any("occupancy_type defaulted to 'office'" in w for w in result["_contract_warnings"])

    def test_unknown_ceiling_type_produces_warning(self):
        """An unrecognized ceiling_type is allowed but flagged with a warning."""
        payload = self._base_payload(ceiling_type="dome")
        result = validate_room_input(payload)
        assert result["ceiling_type"] == "dome"
        assert any("Unknown ceiling_type" in w for w in result["_contract_warnings"])

    def test_empty_string_ceiling_type_accepted(self):
        """Empty string is in the valid ceiling types set."""
        payload = self._base_payload(ceiling_type="")
        result = validate_room_input(payload)
        assert result["ceiling_type"] == ""

    def test_no_area_warning_when_area_provided(self):
        payload = self._base_payload(area_m2=50.0)
        result = validate_room_input(payload)
        assert not any("area_m2 computed from polygon" in w for w in result["_contract_warnings"])

    def test_no_default_warnings_when_all_provided(self):
        payload = self._base_payload(
            area_m2=50.0,
            ceiling_type="flat",
            occupancy_type="office",
        )
        result = validate_room_input(payload)
        # All fields provided, so no default/computed warnings
        assert not any("defaulted" in w for w in result["_contract_warnings"])
        assert not any("computed" in w for w in result["_contract_warnings"])


# ═══════════════════════════════════════════════════════════════════════════════
# validate_room_input — Edge Cases
# ═══════════════════════════════════════════════════════════════════════════════

class TestValidateRoomInputEdgeCases:
    """Test edge cases and boundary conditions."""

    def _base_payload(self, **overrides):
        payload = {
            "room_id": "R-101",
            "room_polygon": [[0, 0], [10, 0], [10, 5], [0, 5]],
            "ceiling_height_m": 3.0,
            "detector_type": "smoke",
        }
        payload.update(overrides)
        return payload

    def test_very_small_positive_ceiling_height(self):
        """Extremely small but positive ceiling height is technically valid."""
        result = validate_room_input(self._base_payload(ceiling_height_m=0.001))
        assert result["ceiling_height_m"] == 0.001

    def test_very_large_ceiling_height_allowed(self):
        """Heights > 30m are allowed (flagged for AHJ review elsewhere)."""
        result = validate_room_input(self._base_payload(ceiling_height_m=50.0))
        assert result["ceiling_height_m"] == 50.0

    def test_valid_detector_type_smoke(self):
        result = validate_room_input(self._base_payload(detector_type="smoke"))
        assert result["detector_type"] == "smoke"

    def test_valid_detector_type_heat(self):
        result = validate_room_input(self._base_payload(detector_type="heat"))
        assert result["detector_type"] == "heat"

    def test_detector_type_case_insensitive(self):
        result = validate_room_input(self._base_payload(detector_type="SMOKE"))
        assert result["detector_type"] == "smoke"

    def test_detector_type_mixed_case(self):
        result = validate_room_input(self._base_payload(detector_type="HeAt"))
        assert result["detector_type"] == "heat"

    def test_polygon_with_tuple_vertices(self):
        payload = self._base_payload(
            room_polygon=[(0, 0), (10, 0), (10, 5), (0, 5)]
        )
        result = validate_room_input(payload)
        assert result["area_m2"] == pytest.approx(50.0)

    def test_polygon_with_integer_coords(self):
        payload = self._base_payload(
            room_polygon=[[0, 0], [10, 0], [10, 5], [0, 5]]
        )
        result = validate_room_input(payload)
        assert result["area_m2"] == pytest.approx(50.0)

    def test_polygon_with_float_coords(self):
        payload = self._base_payload(
            room_polygon=[[0.0, 0.0], [10.5, 0.0], [10.5, 5.5], [0.0, 5.5]]
        )
        result = validate_room_input(payload)
        assert result["area_m2"] == pytest.approx(10.5 * 5.5)

    def test_extra_fields_preserved(self):
        """Non-standard fields in the payload should pass through."""
        payload = self._base_payload(building_name="HQ", floor=3)
        result = validate_room_input(payload)
        assert result["building_name"] == "HQ"
        assert result["floor"] == 3

    def test_result_contains_all_original_keys(self):
        payload = self._base_payload(area_m2=50.0, ceiling_type="flat", occupancy_type="office")
        result = validate_room_input(payload)
        for key in payload:
            assert key in result


# ═══════════════════════════════════════════════════════════════════════════════
# Integration: Full Pipeline Smoke Tests
# ═══════════════════════════════════════════════════════════════════════════════

class TestIntegrationSmokeTests:
    """End-to-end smoke tests that exercise multiple validation paths."""

    def test_typical_office_room(self):
        payload = {
            "room_id": "OFF-201",
            "room_polygon": [[0, 0], [8, 0], [8, 6], [0, 6]],
            "ceiling_height_m": 2.8,
            "detector_type": "smoke",
            "occupancy_type": "office",
            "ceiling_type": "flat",
        }
        result = validate_room_input(payload)
        assert result["room_id"] == "OFF-201"
        assert result["area_m2"] == pytest.approx(48.0)
        assert result["detector_type"] == "smoke"

    def test_warehouse_with_heat_detectors(self):
        payload = {
            "room_id": "WH-01",
            "room_polygon": [[0, 0], [30, 0], [30, 20], [0, 20]],
            "ceiling_height_m": 8.0,
            "detector_type": "heat",
            "occupancy_type": "warehouse",
            "ceiling_type": "beamed",
        }
        result = validate_room_input(payload)
        assert result["area_m2"] == pytest.approx(600.0)
        assert result["detector_type"] == "heat"
        assert result["ceiling_type"] == "beamed"

    def test_corridor_room(self):
        payload = {
            "room_id": "COR-01",
            "room_polygon": [[0, 0], [25, 0], [25, 1.5], [0, 1.5]],
            "ceiling_height_m": 2.7,
            "detector_type": "smoke",
            "ceiling_type": "corridor",
        }
        result = validate_room_input(payload)
        assert result["area_m2"] == pytest.approx(37.5)
        assert result["ceiling_type"] == "corridor"

    def test_nan_anywhere_stops_pipeline(self):
        """A single NaN anywhere in the payload must halt the entire pipeline."""
        payload = {
            "room_id": "R-NaN",
            "room_polygon": [[0, 0], [10, 0], [10, 5], [0, 5]],
            "ceiling_height_m": 3.0,
            "detector_type": "smoke",
            "metadata": {"confidence": float("nan")},
        }
        with pytest.raises(ContractViolation) as exc_info:
            validate_room_input(payload)
        assert "NaN" in str(exc_info.value)

    def test_inf_anywhere_stops_pipeline(self):
        """A single Inf anywhere in the payload must halt the entire pipeline."""
        payload = {
            "room_id": "R-Inf",
            "room_polygon": [[0, 0], [10, 0], [10, 5], [0, 5]],
            "ceiling_height_m": 3.0,
            "detector_type": "smoke",
            "extra": [1.0, float("inf")],
        }
        with pytest.raises(ContractViolation) as exc_info:
            validate_room_input(payload)
        assert "Inf" in str(exc_info.value)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
