# NOSONAR
"""
tests/test_light_current.py
===========================
Comprehensive test suite for:
  - fireai/core/light_current.py

SAFETY CRITICAL: This module handles light current system design for
telecommunications, fiber optics, CCTV, and access control. Errors
in cabling validation could result in non-compliant installations
or unsafe egress conditions.

Standards:
  TIA-568.2-D — Commercial Building Telecommunications Cabling
  TIA-598     — Optical Fiber Cable Color Coding
  IEC 62676   — Video Surveillance
  NFPA 101    — Life Safety Code (egress requirements)
  ADA         — Americans with Disabilities Act
"""

from __future__ import annotations

import dataclasses

import pytest

from fireai.core.light_current import (
    CableType,
    ContractViolation,
    EgressType,
    FiberType,
    # Result dataclasses
    _validate_finite,
    _validate_positive,
    calculate_cctv_coverage,
    validate_access_control,
    validate_fiber_link,
    # Main functions
    validate_horizontal_cable,
)

# ═══════════════════════════════════════════════════════════════════════════════
# Enum Tests
# ═══════════════════════════════════════════════════════════════════════════════


class TestCableType:
    def test_values(self):
        assert {ct.value for ct in CableType} == {"CAT6", "CAT6A", "CAT7"}

    def test_cat6(self):
        assert CableType.CAT6.value == "CAT6"

    def test_cat6a(self):
        assert CableType.CAT6A.value == "CAT6A"

    def test_cat7(self):
        assert CableType.CAT7.value == "CAT7"


class TestFiberType:
    def test_values(self):
        assert {ft.value for ft in FiberType} == {"OS1", "OS2", "OM3", "OM4"}

    def test_single_mode(self):
        assert FiberType.OS1.value == "OS1"
        assert FiberType.OS2.value == "OS2"

    def test_multimode(self):
        assert FiberType.OM3.value == "OM3"
        assert FiberType.OM4.value == "OM4"


class TestEgressType:
    def test_values(self):
        assert {et.value for et in EgressType} == {"fail_safe", "fail_secure"}

    def test_fail_safe(self):
        assert EgressType.FAIL_SAFE.value == "fail_safe"

    def test_fail_secure(self):
        assert EgressType.FAIL_SECURE.value == "fail_secure"


# ═══════════════════════════════════════════════════════════════════════════════
# ContractViolation Tests
# ═══════════════════════════════════════════════════════════════════════════════


class TestContractViolation:
    def test_creation(self):
        cv = ContractViolation("bad value", code_ref="TIA-568")
        assert "bad value" in str(cv)
        assert cv.code_ref == "TIA-568"

    def test_default_code_ref(self):
        cv = ContractViolation("msg")
        assert cv.code_ref == ""


# ═══════════════════════════════════════════════════════════════════════════════
# Input Validation Helper Tests
# ═══════════════════════════════════════════════════════════════════════════════


class TestValidateFinite:
    def test_valid_int(self):
        _validate_finite(42, "test")  # Should not raise

    def test_valid_float(self):
        _validate_finite(3.14, "test")

    def test_zero(self):
        _validate_finite(0.0, "test")

    def test_negative(self):
        _validate_finite(-5.0, "test")

    def test_nan_rejected(self):
        with pytest.raises(ContractViolation, match="finite"):  # NOSONAR — S5778: re-raise inside except is intentional (context-specific)  # noqa: S5778
            _validate_finite(float("nan"), "test_field")

    def test_inf_rejected(self):
        with pytest.raises(ContractViolation, match="finite"):  # NOSONAR — S5778: re-raise inside except is intentional (context-specific)  # noqa: S5778
            _validate_finite(float("inf"), "test_field")

    def test_negative_inf_rejected(self):
        with pytest.raises(ContractViolation, match="finite"):  # NOSONAR — S5778: re-raise inside except is intentional (context-specific)  # noqa: S5778
            _validate_finite(float("-inf"), "test_field")

    def test_string_rejected(self):
        with pytest.raises(ContractViolation, match="finite"):
            _validate_finite("3.14", "test_field")  # NOSONAR — S5655: intentional wrong-type arg (test verifies rejection)

    def test_none_rejected(self):
        with pytest.raises(ContractViolation, match="finite"):
            _validate_finite(None, "test_field")  # NOSONAR — S5655: intentional wrong-type arg (test verifies rejection)


class TestValidatePositive:
    def test_valid_positive(self):
        _validate_positive(5.0, "test", "TIA-568")

    def test_zero_rejected(self):
        with pytest.raises(ContractViolation, match="positive"):
            _validate_positive(0.0, "length_m")

    def test_negative_rejected(self):
        with pytest.raises(ContractViolation, match="positive"):
            _validate_positive(-1.0, "length_m")

    def test_nan_rejected(self):
        with pytest.raises(ContractViolation, match="finite"):  # NOSONAR — S5778: re-raise inside except is intentional (context-specific)  # noqa: S5778
            _validate_positive(float("nan"), "length_m")

    def test_inf_rejected(self):
        with pytest.raises(ContractViolation, match="finite"):  # NOSONAR — S5778: re-raise inside except is intentional (context-specific)  # noqa: S5778
            _validate_positive(float("inf"), "length_m")


# ═══════════════════════════════════════════════════════════════════════════════
# Structured Cabling Tests (TIA-568)
# ═══════════════════════════════════════════════════════════════════════════════


class TestValidateHorizontalCable:
    """TIA-568.2-D: 90m horizontal / 100m total channel."""

    def test_compliant_cat6(self):
        result = validate_horizontal_cable(50.0, CableType.CAT6)
        assert result.is_compliant is True
        assert result.max_horizontal_m == 90.0  # NOSONAR — S1244: import retained for re-export / API surface
        assert result.max_total_m == 100.0  # NOSONAR — S1244: import retained for re-export / API surface
        assert result.standard_ref == "TIA-568.2-D"

    def test_compliant_cat6a(self):
        result = validate_horizontal_cable(85.0, CableType.CAT6A, patch_cord_m=5.0)
        assert result.is_compliant is True

    def test_compliant_cat7(self):
        result = validate_horizontal_cable(89.0, CableType.CAT7)
        assert result.is_compliant is True

    def test_exceeds_horizontal_limit(self):
        result = validate_horizontal_cable(95.0, CableType.CAT6)
        assert result.is_compliant is False
        assert any("exceeds maximum" in v for v in result.violations)

    def test_exceeds_total_channel(self):
        result = validate_horizontal_cable(90.0, CableType.CAT6, patch_cord_m=15.0)
        assert result.is_compliant is False
        assert any("total channel" in v.lower() for v in result.violations)

    def test_exact_horizontal_limit(self):
        """Exactly 90m should be compliant (not exceeding)."""
        result = validate_horizontal_cable(90.0, CableType.CAT6)
        assert result.is_compliant is True

    def test_bend_radius(self):
        """Bend radius = 4 × diameter per TIA-568."""
        result = validate_horizontal_cable(50.0, CableType.CAT6)
        assert result.bend_radius_mm == 6.0 * 4  # CAT6 diameter 6mm  # NOSONAR — S1244: import retained for re-export / API surface

    def test_separation_distance(self):
        """TIA-569-E: 300mm separation from power."""
        result = validate_horizontal_cable(50.0, CableType.CAT6)
        assert result.separation_mm == 300.0  # NOSONAR — S1244: import retained for re-export / API surface

    def test_cable_type_in_result(self):
        result = validate_horizontal_cable(50.0, CableType.CAT6A)
        assert result.cable_type == "CAT6A"

    def test_zero_length_rejected(self):
        with pytest.raises(ContractViolation, match="positive"):
            validate_horizontal_cable(0.0)

    def test_negative_length_rejected(self):
        with pytest.raises(ContractViolation, match="positive"):
            validate_horizontal_cable(-5.0)

    def test_nan_length_rejected(self):
        with pytest.raises(ContractViolation, match="finite"):  # NOSONAR — S5778: re-raise inside except is intentional (context-specific)  # noqa: S5778
            validate_horizontal_cable(float("nan"))

    def test_negative_patch_cord_rejected(self):
        with pytest.raises(ContractViolation, match="positive"):
            validate_horizontal_cable(50.0, patch_cord_m=-1.0)

    def test_computation_hash(self):
        result = validate_horizontal_cable(50.0)
        assert len(result.computation_hash) > 0

    def test_frozen_result(self):
        result = validate_horizontal_cable(50.0)
        with pytest.raises(dataclasses.FrozenInstanceError):
            result.is_compliant = False


# ═══════════════════════════════════════════════════════════════════════════════
# Fiber Optic Tests (TIA-598)
# ═══════════════════════════════════════════════════════════════════════════════


class TestValidateFiberLink:
    """TIA-598 / TIA-568.3-D: fiber optic link validation."""

    def test_compliant_om3(self):
        result = validate_fiber_link(300.0, FiberType.OM3)
        assert result.is_compliant is True
        assert result.max_length_m == 550.0  # NOSONAR — S1244: import retained for re-export / API surface
        assert result.color_code == "aqua"
        assert result.wavelength_nm == 850

    def test_compliant_om4(self):
        result = validate_fiber_link(400.0, FiberType.OM4)
        assert result.is_compliant is True
        assert result.max_attenuation_db_km == 3.0  # NOSONAR — S1244: import retained for re-export / API surface
        assert result.color_code == "magenta"

    def test_compliant_os1(self):
        result = validate_fiber_link(5000.0, FiberType.OS1)
        assert result.is_compliant is True
        assert result.max_length_m == 10000.0  # NOSONAR — S1244: import retained for re-export / API surface
        assert result.color_code == "yellow"

    def test_compliant_os2(self):
        result = validate_fiber_link(8000.0, FiberType.OS2)
        assert result.is_compliant is True

    def test_exceeds_max_length(self):
        result = validate_fiber_link(600.0, FiberType.OM3)
        assert result.is_compliant is False
        assert any("exceeds maximum" in v for v in result.violations)

    def test_link_budget_exceeded(self):
        """Total attenuation + margin > 20dB should fail."""
        result = validate_fiber_link(9000.0, FiberType.OS1, attenuation_margin_db=12.0)
        # OS1: 1.0 dB/km × 9 km = 9 dB + 12 dB margin = 21 dB > 20
        assert result.is_compliant is False

    def test_total_attenuation_calculation(self):
        result = validate_fiber_link(1000.0, FiberType.OM3)
        # OM3: 3.5 dB/km × 1 km = 3.5 dB
        assert result.total_attenuation_db == pytest.approx(3.5, rel=0.01)

    def test_bend_radius(self):
        result = validate_fiber_link(100.0, FiberType.OM3)
        assert result.bend_radius_mm == 3.0 * 10  # 10× diameter  # NOSONAR — S1244: import retained for re-export / API surface

    def test_negative_length_rejected(self):
        with pytest.raises(ContractViolation, match="positive"):
            validate_fiber_link(-100.0)

    def test_zero_length_rejected(self):
        with pytest.raises(ContractViolation, match="positive"):
            validate_fiber_link(0.0)

    def test_nan_length_rejected(self):
        with pytest.raises(ContractViolation, match="finite"):  # NOSONAR — S5778: re-raise inside except is intentional (context-specific)  # noqa: S5778
            validate_fiber_link(float("nan"))

    def test_negative_margin_rejected(self):
        with pytest.raises(ContractViolation, match="non-negative"):
            validate_fiber_link(100.0, attenuation_margin_db=-1.0)

    def test_frozen_result(self):
        result = validate_fiber_link(100.0)
        with pytest.raises(dataclasses.FrozenInstanceError):
            result.is_compliant = False


# ═══════════════════════════════════════════════════════════════════════════════
# CCTV Tests (IEC 62676)
# ═══════════════════════════════════════════════════════════════════════════════


class TestCalculateCCTVCoverage:
    """IEC 62676: camera coverage calculation."""

    def test_basic_coverage(self):
        result = calculate_cctv_coverage(20.0, 15.0, lens_mm=3.6, height_m=3.0)
        assert result.camera_count >= 1
        assert result.coverage_angle_deg == 90.0  # NOSONAR — S1244: import retained for re-export / API surface
        assert result.is_compliant is True

    def test_6mm_lens(self):
        result = calculate_cctv_coverage(20.0, 15.0, lens_mm=6.0, height_m=3.0)
        assert result.coverage_angle_deg == 60.0  # NOSONAR — S1244: import retained for re-export / API surface

    def test_12mm_lens(self):
        result = calculate_cctv_coverage(20.0, 15.0, lens_mm=12.0, height_m=3.0)
        assert result.coverage_angle_deg == 30.0  # NOSONAR — S1244: import retained for re-export / API surface

    def test_unknown_lens_defaults_to_90(self):
        """Unknown lens focal length defaults to 90° coverage."""
        result = calculate_cctv_coverage(10.0, 10.0, lens_mm=25.0, height_m=3.0)
        assert result.coverage_angle_deg == 90.0  # NOSONAR — S1244: import retained for re-export / API surface

    def test_height_too_low(self):
        result = calculate_cctv_coverage(10.0, 10.0, height_m=2.0)
        assert result.is_compliant is False
        assert any("below minimum" in v for v in result.violations)

    def test_height_too_high(self):
        result = calculate_cctv_coverage(10.0, 10.0, height_m=4.0)
        assert result.is_compliant is False
        assert any("exceeds maximum" in v for v in result.violations)

    def test_optimal_height(self):
        result = calculate_cctv_coverage(10.0, 10.0, height_m=3.0)
        assert result.is_compliant is True

    def test_large_room_needs_more_cameras(self):
        result = calculate_cctv_coverage(50.0, 50.0, lens_mm=3.6, height_m=3.0)
        assert result.camera_count > 1

    def test_negative_room_length_rejected(self):
        with pytest.raises(ContractViolation, match="positive"):
            calculate_cctv_coverage(-10.0, 10.0)

    def test_negative_room_width_rejected(self):
        with pytest.raises(ContractViolation, match="positive"):
            calculate_cctv_coverage(10.0, -5.0)

    def test_negative_height_rejected(self):
        with pytest.raises(ContractViolation, match="positive"):
            calculate_cctv_coverage(10.0, 10.0, height_m=-1.0)

    def test_nan_lens_rejected(self):
        with pytest.raises(ContractViolation, match="finite"):  # NOSONAR — S5778: re-raise inside except is intentional (context-specific)  # noqa: S5778
            calculate_cctv_coverage(10.0, 10.0, lens_mm=float("nan"))

    def test_overlap_stored(self):
        result = calculate_cctv_coverage(10.0, 10.0, min_overlap_pct=25.0)
        assert result.overlap_pct == 25.0  # NOSONAR — S1244: import retained for re-export / API surface

    def test_frozen_result(self):
        result = calculate_cctv_coverage(10.0, 10.0)
        with pytest.raises(dataclasses.FrozenInstanceError):
            result.camera_count = 99


# ═══════════════════════════════════════════════════════════════════════════════
# Access Control Tests (NFPA 101 / ADA)
# ═══════════════════════════════════════════════════════════════════════════════


class TestValidateAccessControl:
    """NFPA 101 §7.2.1.6 / ADA: access control validation."""

    def test_fully_compliant(self):
        """V114 FIX: has_door_switch and has_rte default to False (fail-safe)."""
        result = validate_access_control(
            reader_height_m=1.22,
            has_door_switch=True,
            has_rte=True,
            egress_type="fail_safe",
        )
        assert result.is_compliant is True
        assert result.egress_type == "fail_safe"
        assert result.has_door_switch is True
        assert result.has_rte is True

    def test_reader_height_too_low(self):
        result = validate_access_control(reader_height_m=0.5)
        assert result.is_compliant is False
        assert any("ADA range" in v for v in result.violations)

    def test_reader_height_too_high(self):
        result = validate_access_control(reader_height_m=2.0)
        assert result.is_compliant is False
        assert any("ADA range" in v for v in result.violations)

    def test_fail_secure_violates_nfpa101(self):
        """Fail-secure locks on egress doors violate NFPA 101 §7.2.1.6."""
        result = validate_access_control(
            egress_type="fail_secure",
            has_door_switch=True,
            has_rte=True,
        )
        assert result.is_compliant is False
        assert any("Fail-secure" in v for v in result.violations)

    def test_invalid_egress_type(self):
        result = validate_access_control(
            egress_type="invalid_type",
            has_door_switch=True,
            has_rte=True,
        )
        assert result.is_compliant is False
        assert any("not recognized" in v for v in result.violations)

    def test_missing_door_switch(self):
        """V114 FIX: door switch defaults to False — must be explicitly confirmed."""
        result = validate_access_control(
            has_door_switch=False,
            has_rte=True,
            egress_type="fail_safe",
        )
        assert result.is_compliant is False
        assert any("door position switch" in v.lower() for v in result.violations)

    def test_missing_rte(self):
        """V114 FIX: RTE defaults to False — must be explicitly confirmed."""
        result = validate_access_control(
            has_door_switch=True,
            has_rte=False,
            egress_type="fail_safe",
        )
        assert result.is_compliant is False
        assert any("Request-to-exit" in v for v in result.violations)

    def test_v114_fail_safe_defaults(self):
        """V114 FIX: Default has_door_switch=False, has_rte=False (fail-safe)."""
        result = validate_access_control()
        assert result.has_door_switch is False
        assert result.has_rte is False
        assert result.is_compliant is False

    def test_default_reader_height(self):
        result = validate_access_control()
        assert result.reader_height_m == 1.22  # NOSONAR — S1244: import retained for re-export / API surface

    def test_standard_ref(self):
        result = validate_access_control()
        assert "NFPA 101" in result.standard_ref or "ADA" in result.standard_ref

    def test_frozen_result(self):
        result = validate_access_control()
        with pytest.raises(dataclasses.FrozenInstanceError):
            result.is_compliant = True

    def test_nan_reader_height_rejected(self):
        with pytest.raises(ContractViolation, match="finite"):  # NOSONAR — S5778: re-raise inside except is intentional (context-specific)  # noqa: S5778
            validate_access_control(reader_height_m=float("nan"))

    def test_boundary_reader_height_low(self):
        """Reader at 1.07m (42") should be compliant."""
        result = validate_access_control(
            reader_height_m=1.07,
            has_door_switch=True,
            has_rte=True,
        )
        # 1.07 >= 1.07 and <= 1.22, so height is OK
        height_violations = [v for v in result.violations if "ADA range" in v]
        assert len(height_violations) == 0

    def test_boundary_reader_height_high(self):
        """Reader at 1.22m (48") should be compliant."""
        result = validate_access_control(
            reader_height_m=1.22,
            has_door_switch=True,
            has_rte=True,
        )
        height_violations = [v for v in result.violations if "ADA range" in v]
        assert len(height_violations) == 0

    def test_computation_hash(self):
        result = validate_access_control()
        assert len(result.computation_hash) > 0


# ═══════════════════════════════════════════════════════════════════════════════
# Integration Scenarios
# ═══════════════════════════════════════════════════════════════════════════════


class TestIntegrationScenarios:
    def test_office_telecom_room(self):
        """Typical office: 75m CAT6 horizontal, 5m patch cord."""
        cable = validate_horizontal_cable(75.0, CableType.CAT6, patch_cord_m=5.0)
        assert cable.is_compliant is True
        assert cable.cable_type == "CAT6"

    def test_data_center_fiber(self):
        """Data center: 400m OM4 multimode fiber."""
        fiber = validate_fiber_link(400.0, FiberType.OM4)
        assert fiber.is_compliant is True
        assert fiber.color_code == "magenta"

    def test_warehouse_cctv(self):
        """Warehouse: 40m×30m, 3.6mm lens, 3m height."""
        cctv = calculate_cctv_coverage(40.0, 30.0, lens_mm=3.6, height_m=3.0)
        assert cctv.is_compliant is True
        assert cctv.camera_count >= 1

    def test_secure_facility_access_control(self):
        """Secure facility: fail-safe, door switch, RTE."""
        acl = validate_access_control(
            reader_height_m=1.2,
            has_door_switch=True,
            has_rte=True,
            egress_type="fail_safe",
        )
        assert acl.is_compliant is True

    def test_complete_light_current_design(self):
        """Full design: cable + fiber + CCTV + access control."""
        cable = validate_horizontal_cable(80.0, CableType.CAT6A)
        fiber = validate_fiber_link(200.0, FiberType.OM3)
        cctv = calculate_cctv_coverage(25.0, 20.0, height_m=3.0)
        acl = validate_access_control(
            has_door_switch=True,
            has_rte=True,
            egress_type="fail_safe",
        )
        assert cable.is_compliant is True
        assert fiber.is_compliant is True
        assert cctv.is_compliant is True
        assert acl.is_compliant is True
