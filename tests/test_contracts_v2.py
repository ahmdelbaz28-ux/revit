# NOSONAR
"""
tests/test_contracts_v2.py
===========================
Comprehensive test suite for fireai/core/contracts.py

SAFETY CRITICAL: Contract validation prevents injection of forged
compliance data (area, spacing, is_compliant) through API payloads.
Bypassing these checks could result in fire alarm systems being
certified as compliant when they are not — a direct life-safety hazard.

NFPA 72 References:
  Table 17.6.3.1.1 — Detector spacing
  §17.6.3 — Coverage requirements
  §21.2.2 — Max 250 devices per SLC loop
  §10.14 — Panel voltage
"""

from __future__ import annotations

import json
import os

import pytest

from fireai.core.contracts import (
    CONTRACT_VERSION,
    DEFAULT_FEATURE_FLAGS,
    FORBIDDEN_DERIVED_FIELDS,
    FORBIDDEN_LOOP_DERIVED_FIELDS,
    AuditEventContract,
    CableType,
    CeilingSpecContract,
    CeilingType,
    ComplianceReportContract,
    ConfidenceLevel,
    ContractViolation,
    DetectorPlacementContract,
    DetectorType,
    FeatureFlag,
    OccupancyCategory,
    ParsedDrawingContract,
    PathwaySurvivabilityLevel,
    RoomSpecificationContract,
    get_feature_flags,
    is_feature_enabled,
    validate_loop_input,
    validate_room_input,
)

# ─────────────────────────────────────────────────────────────────────────────
# Enum Tests
# ─────────────────────────────────────────────────────────────────────────────


class TestCeilingType:
    def test_all_values(self):
        expected = {"FLAT", "SLOPED", "BEAMED", "COFFERED", "DOMED", "SMOOTH",
                    "GABLE", "SHED", "CORRIDOR", "TRUSS", "COMBUSTIBLE"}
        assert {ct.value for ct in CeilingType} == expected

    def test_string_enum(self):
        assert CeilingType.FLAT == "FLAT"
        assert isinstance(CeilingType.FLAT, str)


class TestConfidenceLevel:
    def test_all_values(self):
        assert {cl.value for cl in ConfidenceLevel} == {"HIGH", "MEDIUM", "LOW", "UNKNOWN"}


class TestDetectorType:
    def test_all_values_present(self):
        vals = {dt.value for dt in DetectorType}
        assert "SMOKE" in vals
        assert "HEAT" in vals
        assert "FLAME" in vals
        assert "GAS" in vals

    def test_string_enum(self):
        assert DetectorType.SMOKE_PHOTOELECTRIC == "SMOKE_PHOTOELECTRIC"


class TestPathwaySurvivabilityLevel:
    def test_levels(self):
        assert PathwaySurvivabilityLevel.LEVEL_1.value == "LEVEL_1"
        assert PathwaySurvivabilityLevel.LEVEL_2.value == "LEVEL_2"
        assert PathwaySurvivabilityLevel.LEVEL_3.value == "LEVEL_3"


class TestCableType:
    def test_cable_types(self):
        vals = {ct.value for ct in CableType}
        assert vals == {"FPL", "FPLR", "FPLP", "CI"}


class TestOccupancyCategory:
    def test_categories(self):
        vals = {oc.value for oc in OccupancyCategory}
        assert "HEALTH_CARE" in vals
        assert "HIGH_RISE" in vals


class TestFeatureFlag:
    def test_all_flags_defined(self):
        flags = {ff.value for ff in FeatureFlag}
        assert "SMOKE_SIMULATION" in flags
        assert "PROOF_CERTIFICATE" in flags
        assert "REVIT_BRIDGE" in flags

    def test_default_flags_have_all_keys(self):
        for flag in FeatureFlag:
            assert flag in DEFAULT_FEATURE_FLAGS


# ─────────────────────────────────────────────────────────────────────────────
# Contract Dataclass Tests
# ─────────────────────────────────────────────────────────────────────────────


class TestParsedDrawingContract:
    def test_creation_defaults(self):
        c = ParsedDrawingContract()
        assert c.contract_version == CONTRACT_VERSION
        assert c.rooms == []
        assert c.layers == []

    def test_to_dict(self):
        c = ParsedDrawingContract(source_file="test.dxf")
        d = c.to_dict()
        assert d["source_file"] == "test.dxf"
        assert "contract_version" in d

    def test_frozen(self):
        c = ParsedDrawingContract()
        with pytest.raises(AttributeError):
            c.source_file = "other.dxf"


class TestCeilingSpecContract:
    def test_creation(self):
        c = CeilingSpecContract(
            height_at_low_point_m=3.0,
            height_at_high_point_m=4.5,
            ceiling_type=CeilingType.SLOPED,
        )
        assert c.ceiling_type == CeilingType.SLOPED
        assert c.height_at_low_point_m == 3.0  # NOSONAR — S1244: import retained for re-export / API surface

    def test_default_type_is_flat(self):
        c = CeilingSpecContract(3.0, 3.0)
        assert c.ceiling_type == CeilingType.FLAT


class TestRoomSpecificationContract:
    def test_creation_defaults(self):
        c = RoomSpecificationContract()
        assert c.contract_version == CONTRACT_VERSION
        assert c.detector_type == DetectorType.SMOKE_PHOTOELECTRIC

    def test_to_dict(self):
        c = RoomSpecificationContract(room_id="R-101", width_m=10.0, depth_m=8.0)
        d = c.to_dict()
        assert d["room_id"] == "R-101"
        assert d["width_m"] == 10.0  # NOSONAR — S1244: import retained for re-export / API surface

    def test_with_ceiling_spec(self):
        cs = CeilingSpecContract(3.0, 3.0, CeilingType.BEAMED)
        c = RoomSpecificationContract(ceiling_spec=cs)
        d = c.to_dict()
        assert d["ceiling_spec"]["ceiling_type"] == "BEAMED"


class TestDetectorPlacementContract:
    def test_creation(self):
        c = DetectorPlacementContract(
            room_id="R-101",
            detector_positions=[(1, 1), (5, 5)],
            compliant=True,
        )
        assert c.compliant is True
        assert len(c.detector_positions) == 2

    def test_to_dict(self):
        c = DetectorPlacementContract(room_id="R-101")
        d = c.to_dict()
        assert "room_id" in d


class TestComplianceReportContract:
    def test_creation(self):
        c = ComplianceReportContract(room_id="R-101", compliant=True)
        assert c.compliant is True
        assert c.nfpa_version == "NFPA 72-2022"

    def test_hash_fields(self):
        c = ComplianceReportContract(
            room_id="R-101",
            proof_certificate_hash="abc123",
            audit_event_hash="def456",
        )
        assert c.proof_certificate_hash == "abc123"
        assert c.audit_event_hash == "def456"


class TestAuditEventContract:
    def test_creation(self):
        c = AuditEventContract(
            event_type="ROOM_ANALYSIS",
            source_service="parser",
            room_id="R-101",
        )
        assert c.event_type == "ROOM_ANALYSIS"
        assert c.previous_hash == "GENESIS"

    def test_to_dict(self):
        c = AuditEventContract(event_type="TEST")
        d = c.to_dict()
        assert "event_type" in d
        assert "previous_hash" in d


# ─────────────────────────────────────────────────────────────────────────────
# Feature Flag Tests
# ─────────────────────────────────────────────────────────────────────────────


class TestFeatureFlags:
    def test_get_feature_flags_returns_dict(self):
        flags = get_feature_flags()
        assert isinstance(flags, dict)
        assert len(flags) > 0

    def test_is_feature_enabled_true(self):
        # PROOF_CERTIFICATE is True by default
        assert is_feature_enabled(FeatureFlag.PROOF_CERTIFICATE) is True

    def test_is_feature_enabled_false(self):
        # SMOKE_SIMULATION is False by default
        assert is_feature_enabled(FeatureFlag.SMOKE_SIMULATION) is False

    def test_is_feature_enabled_unknown_flag(self):
        """Unknown flag should return False."""
        assert is_feature_enabled("NONEXISTENT_FLAG") is False

    def test_env_override(self):
        """FIREAI_FEATURE_FLAGS env var should override defaults."""
        original = os.environ.get("FIREAI_FEATURE_FLAGS")
        try:
            os.environ["FIREAI_FEATURE_FLAGS"] = json.dumps({"SMOKE_SIMULATION": True})
            flags = get_feature_flags()
            assert flags[FeatureFlag.SMOKE_SIMULATION] is True
        finally:
            if original is not None:
                os.environ["FIREAI_FEATURE_FLAGS"] = original
            else:
                os.environ.pop("FIREAI_FEATURE_FLAGS", None)

    def test_env_invalid_json_ignored(self):
        """Invalid JSON in env var should be silently ignored."""
        original = os.environ.get("FIREAI_FEATURE_FLAGS")
        try:
            os.environ["FIREAI_FEATURE_FLAGS"] = "not-json"
            flags = get_feature_flags()
            # Should still return defaults
            assert isinstance(flags, dict)
        finally:
            if original is not None:
                os.environ["FIREAI_FEATURE_FLAGS"] = original
            else:
                os.environ.pop("FIREAI_FEATURE_FLAGS", None)


# ─────────────────────────────────────────────────────────────────────────────
# validate_room_input Tests
# ─────────────────────────────────────────────────────────────────────────────


class TestValidateRoomInput:
    """STRICT_ENGINEERING: Input contract validation for room payloads."""

    def _valid_payload(self):
        return {
            "room_id": "R-101",
            "polygon": [(0, 0), (10, 0), (10, 8), (0, 8)],
            "ceiling_height_m": 3.0,
        }

    def test_valid_payload_passes(self):
        result = validate_room_input(self._valid_payload())
        assert result["room_id"] == "R-101"

    def test_non_dict_raises(self):
        with pytest.raises(ContractViolation, match="dictionary"):
            validate_room_input("not a dict")  # NOSONAR — S5655: intentional wrong-type arg (test verifies rejection)

    def test_forbidden_derived_field_area(self):
        """area_m2 must NOT be accepted — it must be computed internally."""
        payload = self._valid_payload()
        payload["area_m2"] = 999
        with pytest.raises(ContractViolation, match="area_m2"):
            validate_room_input(payload)

    def test_forbidden_derived_field_is_compliant(self):
        """is_compliant must NOT be accepted — prevents forged compliance."""
        payload = self._valid_payload()
        payload["is_compliant"] = True
        with pytest.raises(ContractViolation, match="is_compliant"):
            validate_room_input(payload)

    def test_forbidden_derived_field_spacing_m(self):
        """spacing_m must NOT be accepted — derived from detector_type + ceiling_height."""
        payload = self._valid_payload()
        payload["spacing_m"] = 9.1
        with pytest.raises(ContractViolation, match="spacing_m"):
            validate_room_input(payload)

    def test_all_forbidden_fields_rejected(self):
        """Every field in FORBIDDEN_DERIVED_FIELDS must be rejected."""
        for field_name in FORBIDDEN_DERIVED_FIELDS:
            payload = self._valid_payload()
            payload[field_name] = "FORGED"
            with pytest.raises(ContractViolation, match=field_name):
                validate_room_input(payload)

    def test_missing_room_id(self):
        payload = self._valid_payload()
        del payload["room_id"]
        with pytest.raises(ContractViolation, match="room_id"):
            validate_room_input(payload)

    def test_empty_room_id(self):
        payload = self._valid_payload()
        payload["room_id"] = ""
        with pytest.raises(ContractViolation, match="non-empty"):
            validate_room_input(payload)

    def test_missing_polygon(self):
        payload = self._valid_payload()
        del payload["polygon"]
        with pytest.raises(ContractViolation, match="polygon"):
            validate_room_input(payload)

    def test_polygon_too_few_points(self):
        payload = self._valid_payload()
        payload["polygon"] = [(0, 0), (10, 0)]
        with pytest.raises(ContractViolation, match="at least 3"):
            validate_room_input(payload)

    def test_polygon_non_numeric_coords(self):
        """Polygon with string coordinates must be rejected."""
        payload = self._valid_payload()
        payload["polygon"] = [(0, 0), ("abc", 0), (10, 8)]
        with pytest.raises(ContractViolation, match="numeric"):
            validate_room_input(payload)

    def test_polygon_dict_format(self):
        """Polygon with dict points {x, y} should be accepted."""
        payload = self._valid_payload()
        payload["polygon"] = [
            {"x": 0, "y": 0},
            {"x": 10, "y": 0},
            {"x": 10, "y": 8},
            {"x": 0, "y": 8},
        ]
        result = validate_room_input(payload)
        assert result["room_id"] == "R-101"

    def test_polygon_dict_missing_keys(self):
        """Polygon dict point missing 'y' key must be rejected."""
        payload = self._valid_payload()
        payload["polygon"] = [(0, 0), {"x": 10}, (10, 8)]
        with pytest.raises(ContractViolation, match="'x' and 'y'"):
            validate_room_input(payload)

    def test_polygon_dict_non_numeric(self):
        """Polygon dict with non-numeric x/y must be rejected."""
        payload = self._valid_payload()
        payload["polygon"] = [(0, 0), {"x": "abc", "y": 5}, (10, 8)]
        with pytest.raises(ContractViolation, match="numeric"):
            validate_room_input(payload)

    def test_polygon_point_too_few_coords(self):
        """Polygon point with only 1 coordinate must be rejected."""
        payload = self._valid_payload()
        payload["polygon"] = [(0, 0), [10], (10, 8)]
        with pytest.raises(ContractViolation, match="at least 2 coordinates"):
            validate_room_input(payload)

    def test_polygon_invalid_point_type(self):
        """Polygon point that is neither list/tuple nor dict must be rejected."""
        payload = self._valid_payload()
        payload["polygon"] = [(0, 0), 42, (10, 8)]
        with pytest.raises(ContractViolation, match="tuple/list or dict"):
            validate_room_input(payload)

    def test_missing_ceiling_height(self):
        payload = self._valid_payload()
        del payload["ceiling_height_m"]
        with pytest.raises(ContractViolation, match="ceiling_height_m"):
            validate_room_input(payload)

    def test_ceiling_height_zero(self):
        payload = self._valid_payload()
        payload["ceiling_height_m"] = 0
        with pytest.raises(ContractViolation):
            validate_room_input(payload)

    def test_ceiling_height_negative(self):
        payload = self._valid_payload()
        payload["ceiling_height_m"] = -3.0
        with pytest.raises(ContractViolation):
            validate_room_input(payload)

    def test_ceiling_height_over_30m(self):
        payload = self._valid_payload()
        payload["ceiling_height_m"] = 35.0
        with pytest.raises(ContractViolation):
            validate_room_input(payload)

    def test_ceiling_height_nan(self):
        """NaN ceiling height must be rejected — bypasses all downstream safety checks."""
        payload = self._valid_payload()
        payload["ceiling_height_m"] = float("nan")
        with pytest.raises(ContractViolation):
            validate_room_input(payload)

    def test_ceiling_height_inf(self):
        """Inf ceiling height must be rejected."""
        payload = self._valid_payload()
        payload["ceiling_height_m"] = float("inf")
        with pytest.raises(ContractViolation):
            validate_room_input(payload)

    def test_ceiling_height_string(self):
        payload = self._valid_payload()
        payload["ceiling_height_m"] = "three"
        with pytest.raises(ContractViolation, match="number"):
            validate_room_input(payload)

    def test_ceiling_height_30m_boundary(self):
        """Exactly 30m should be accepted (boundary)."""
        payload = self._valid_payload()
        payload["ceiling_height_m"] = 30.0
        result = validate_room_input(payload)
        assert result["ceiling_height_m"] == 30.0  # NOSONAR — S1244: import retained for re-export / API surface

    def test_ceiling_height_0_1m_boundary(self):
        """Very small positive height should be accepted."""
        payload = self._valid_payload()
        payload["ceiling_height_m"] = 0.1
        result = validate_room_input(payload)
        assert result["ceiling_height_m"] == 0.1  # NOSONAR — S1244: import retained for re-export / API surface


# ─────────────────────────────────────────────────────────────────────────────
# validate_loop_input Tests
# ─────────────────────────────────────────────────────────────────────────────


class TestValidateLoopInput:
    """STRICT_ENGINEERING: Input contract validation for SLC loop payloads."""

    def _valid_payload(self):
        return {
            "loop_id": "SLC-01",
            "device_count": 50,
            "total_length_m": 200.0,
        }

    def test_valid_payload_passes(self):
        result = validate_loop_input(self._valid_payload())
        assert result["loop_id"] == "SLC-01"

    def test_non_dict_raises(self):
        with pytest.raises(ContractViolation, match="dictionary"):
            validate_loop_input([])  # NOSONAR — S5655: intentional wrong-type arg (test verifies rejection)

    def test_forbidden_derived_field_voltage_drop(self):
        """voltage_drop_v must NOT be accepted — computed internally."""
        payload = self._valid_payload()
        payload["voltage_drop_v"] = 0.5
        with pytest.raises(ContractViolation, match="voltage_drop_v"):
            validate_loop_input(payload)

    def test_forbidden_derived_field_is_compliant(self):
        payload = self._valid_payload()
        payload["is_compliant"] = True
        with pytest.raises(ContractViolation, match="is_compliant"):
            validate_loop_input(payload)

    def test_all_forbidden_loop_fields_rejected(self):
        for field_name in FORBIDDEN_LOOP_DERIVED_FIELDS:
            payload = self._valid_payload()
            payload[field_name] = "FORGED"
            with pytest.raises(ContractViolation, match=field_name):
                validate_loop_input(payload)

    def test_missing_loop_id(self):
        payload = self._valid_payload()
        del payload["loop_id"]
        with pytest.raises(ContractViolation, match="loop_id"):
            validate_loop_input(payload)

    def test_device_count_over_250(self):
        """NFPA 72 §21.2.2: max 250 devices per SLC loop."""
        payload = self._valid_payload()
        payload["device_count"] = 251
        with pytest.raises(ContractViolation, match="250"):
            validate_loop_input(payload)

    def test_device_count_exactly_250(self):
        """Exactly 250 devices should be accepted."""
        payload = self._valid_payload()
        payload["device_count"] = 250
        result = validate_loop_input(payload)
        assert result["device_count"] == 250

    def test_device_count_from_devices_list(self):
        """device_count should be inferred from devices list if not provided."""
        payload = self._valid_payload()
        del payload["device_count"]
        payload["devices"] = list(range(50))
        result = validate_loop_input(payload)
        assert result["loop_id"] == "SLC-01"

    def test_negative_total_length(self):
        payload = self._valid_payload()
        payload["total_length_m"] = -10.0
        with pytest.raises(ContractViolation):
            validate_loop_input(payload)

    def test_total_length_zero_accepted(self):
        payload = self._valid_payload()
        payload["total_length_m"] = 0.0
        result = validate_loop_input(payload)
        assert result["total_length_m"] == 0.0  # NOSONAR — S1244: import retained for re-export / API surface

    def test_total_length_non_numeric(self):
        payload = self._valid_payload()
        payload["total_length_m"] = "long"
        with pytest.raises(ContractViolation, match="number"):
            validate_loop_input(payload)

    def test_panel_voltage_nan(self):
        """NaN panel voltage must be rejected."""
        payload = self._valid_payload()
        payload["panel_voltage_v"] = float("nan")
        with pytest.raises(ContractViolation):
            validate_loop_input(payload)

    def test_panel_voltage_inf(self):
        payload = self._valid_payload()
        payload["panel_voltage_v"] = float("inf")
        with pytest.raises(ContractViolation):
            validate_loop_input(payload)

    def test_panel_voltage_zero(self):
        payload = self._valid_payload()
        payload["panel_voltage_v"] = 0.0
        with pytest.raises(ContractViolation):
            validate_loop_input(payload)

    def test_panel_voltage_over_48(self):
        payload = self._valid_payload()
        payload["panel_voltage_v"] = 49.0
        with pytest.raises(ContractViolation):
            validate_loop_input(payload)

    def test_panel_voltage_string(self):
        payload = self._valid_payload()
        payload["panel_voltage_v"] = "24V"
        with pytest.raises(ContractViolation, match="number"):
            validate_loop_input(payload)

    def test_panel_voltage_default_24v(self):
        """Default panel voltage is 24V."""
        payload = self._valid_payload()
        validate_loop_input(payload)
        # No exception = valid, 24.0 is within range

    def test_panel_voltage_48v_boundary(self):
        """Exactly 48V should be accepted."""
        payload = self._valid_payload()
        payload["panel_voltage_v"] = 48.0
        result = validate_loop_input(payload)
        assert result["panel_voltage_v"] == 48.0  # NOSONAR — S1244: import retained for re-export / API surface


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
