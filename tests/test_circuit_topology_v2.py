"""
tests/test_circuit_topology_v2.py
=================================
Comprehensive test suite for fireai/core/circuit_topology.py —
ADDITIONAL coverage beyond test_cable_routing.py.

SAFETY CRITICAL: Circuit topology validates NFPA 72 requirements for
fire alarm wiring. Missed violations could approve non-compliant circuits.

NFPA 72 References:
  §12.2 — Circuit class designations (Class A, Class B)
  §12.3 — SLC fault isolator requirements
  §12.3.1 — Max 32 devices between isolators on SLC
  §10.6.4 — Voltage drop verification
  §18.3 — NAC requirements

Key V-Fixes tested:
  V96 FIX — Panel at origin (0,0,0) warning for voltage drop errors
"""

from __future__ import annotations

import dataclasses

import pytest

from fireai.core.circuit_topology import (
    MAX_DEVICES_BETWEEN_ISOLATORS,
    MAX_NAC_DEVICES_DEFAULT,
    MAX_SLC_DEVICES_DEFAULT,
    CircuitClass,
    CircuitDevice,
    CircuitTopology,
    CircuitType,
)

# ─────────────────────────────────────────────────────────────────────────────
# Constants
# ─────────────────────────────────────────────────────────────────────────────


class TestConstants:
    def test_max_devices_between_isolators(self):
        """NFPA 72 §12.3.1: Max 32 devices between isolators."""
        assert MAX_DEVICES_BETWEEN_ISOLATORS == 32

    def test_max_slc_devices_default(self):
        """Typical manufacturer panel limit for SLC devices."""
        assert MAX_SLC_DEVICES_DEFAULT == 250

    def test_max_nac_devices_default(self):
        """Typical maximum NAC devices (limited by current)."""
        assert MAX_NAC_DEVICES_DEFAULT == 99


# ─────────────────────────────────────────────────────────────────────────────
# CircuitClass and CircuitType Enums
# ─────────────────────────────────────────────────────────────────────────────


class TestCircuitClassEnum:
    def test_class_a_value(self):
        assert CircuitClass.CLASS_A.value == "CLASS_A"

    def test_class_b_value(self):
        assert CircuitClass.CLASS_B.value == "CLASS_B"

    def test_exactly_two_classes(self):
        assert len(CircuitClass) == 2

    def test_class_a_is_loop(self):
        """Class A: loop circuit with return path, survives single open."""
        assert CircuitClass.CLASS_A.value == "CLASS_A"

    def test_class_b_is_branch(self):
        """Class B: star/branch circuit without return path."""
        assert CircuitClass.CLASS_B.value == "CLASS_B"


class TestCircuitTypeEnum:
    def test_slc_value(self):
        assert CircuitType.SLC.value == "SLC"

    def test_nac_value(self):
        assert CircuitType.NAC.value == "NAC"

    def test_exactly_two_types(self):
        assert len(CircuitType) == 2


# ─────────────────────────────────────────────────────────────────────────────
# CircuitDevice — Edge Cases
# ─────────────────────────────────────────────────────────────────────────────


class TestCircuitDeviceEdgeCases:
    def test_frozen_dataclass(self):
        d = CircuitDevice("D1", "detector", 1.0, 2.0, 3.0)
        with pytest.raises(dataclasses.FrozenInstanceError):
            d.device_id = "D2"

    def test_negative_coordinates_allowed_in_constructor(self):
        """Coordinates can be negative (valid building coordinates).
        NaN/Inf rejection happens in add_device validation.
        """
        d = CircuitDevice("D1", "detector", -5.0, -10.0, -3.0)
        assert d.position_x == -5.0
        assert d.position_y == -10.0
        assert d.position_z == -3.0

    def test_zero_current(self):
        d = CircuitDevice("D1", "detector", 10.0, 0.0, 3.0, current_a=0.0)
        assert d.current_a == 0.0

    def test_large_current(self):
        d = CircuitDevice("HS1", "horn_strobe", 10.0, 0.0, 3.0, current_a=2.5)
        assert d.current_a == 2.5

    def test_zone_id_optional(self):
        d = CircuitDevice("D1", "detector")
        assert d.zone_id is None

    def test_zone_id_set(self):
        d = CircuitDevice("D1", "detector", zone_id="ZONE-A")
        assert d.zone_id == "ZONE-A"

    def test_various_device_types(self):
        """All expected device types should be representable."""
        types = ["detector", "module", "isolator", "fault_isolator", "horn",
                 "strobe", "horn_strobe", "pull_station", "damper_module"]
        for dt in types:
            d = CircuitDevice(f"DEV-{dt}", dt)
            assert d.device_type == dt


# ─────────────────────────────────────────────────────────────────────────────
# CircuitTopology — Device Management (additional tests)
# ─────────────────────────────────────────────────────────────────────────────


class TestCircuitTopologyDeviceManagement:
    def test_add_multiple_devices(self):
        c = CircuitTopology("C1", CircuitClass.CLASS_B, CircuitType.SLC)
        for i in range(5):
            c.add_device(CircuitDevice(f"D{i}", "detector", float(i), 0.0, 3.0))
        assert len(c.devices) == 5

    def test_remove_device_from_middle(self):
        c = CircuitTopology("C1", CircuitClass.CLASS_B, CircuitType.SLC)
        c.add_device(CircuitDevice("D0", "detector", 0.0, 0.0, 3.0))
        c.add_device(CircuitDevice("D1", "detector", 10.0, 0.0, 3.0))
        c.add_device(CircuitDevice("D2", "detector", 20.0, 0.0, 3.0))
        removed = c.remove_device("D1")
        assert removed is True
        assert len(c.devices) == 2
        assert c.devices[0].device_id == "D0"
        assert c.devices[1].device_id == "D2"

    def test_remove_device_updates_indices(self):
        c = CircuitTopology("C1", CircuitClass.CLASS_B, CircuitType.SLC)
        c.add_device(CircuitDevice("D0", "detector", 0.0, 0.0, 3.0))
        c.add_device(CircuitDevice("ISO1", "isolator", 10.0, 0.0, 3.0))
        c.add_device(CircuitDevice("D1", "detector", 20.0, 0.0, 3.0))
        c.remove_device("D0")
        # ISO1 is now at index 0
        assert c.get_isolator_indices() == [0]

    def test_add_device_nan_y(self):
        c = CircuitTopology("C1", CircuitClass.CLASS_B, CircuitType.SLC)
        with pytest.raises(ValueError, match="non-finite"):
            c.add_device(CircuitDevice("D1", "detector", 0.0, float("nan"), 3.0))

    def test_add_device_nan_z(self):
        c = CircuitTopology("C1", CircuitClass.CLASS_B, CircuitType.SLC)
        with pytest.raises(ValueError, match="non-finite"):
            c.add_device(CircuitDevice("D1", "detector", 0.0, 0.0, float("nan")))

    def test_add_device_negative_inf(self):
        c = CircuitTopology("C1", CircuitClass.CLASS_B, CircuitType.SLC)
        with pytest.raises(ValueError, match="non-finite"):
            c.add_device(CircuitDevice("D1", "detector", float("-inf"), 0.0, 3.0))


# ─────────────────────────────────────────────────────────────────────────────
# CircuitTopology — get_isolator_indices (additional)
# ─────────────────────────────────────────────────────────────────────────────


class TestGetIsolatorIndices:
    def test_no_isolators(self):
        c = CircuitTopology("C1", CircuitClass.CLASS_B, CircuitType.SLC)
        c.add_device(CircuitDevice("D1", "detector", 1.0, 0.0, 3.0))
        c.add_device(CircuitDevice("D2", "detector", 2.0, 0.0, 3.0))
        assert c.get_isolator_indices() == []

    def test_multiple_isolators(self):
        c = CircuitTopology("C1", CircuitClass.CLASS_B, CircuitType.SLC)
        c.add_device(CircuitDevice("D1", "detector", 1.0, 0.0, 3.0))
        c.add_device(CircuitDevice("ISO1", "isolator", 2.0, 0.0, 3.0))
        c.add_device(CircuitDevice("D2", "detector", 3.0, 0.0, 3.0))
        c.add_device(CircuitDevice("ISO2", "fault_isolator", 4.0, 0.0, 3.0))
        c.add_device(CircuitDevice("D3", "detector", 5.0, 0.0, 3.0))
        indices = c.get_isolator_indices()
        assert indices == [1, 3]

    def test_isolator_at_start(self):
        c = CircuitTopology("C1", CircuitClass.CLASS_B, CircuitType.SLC)
        c.add_device(CircuitDevice("ISO1", "isolator", 0.0, 0.0, 3.0))
        c.add_device(CircuitDevice("D1", "detector", 10.0, 0.0, 3.0))
        assert c.get_isolator_indices() == [0]

    def test_isolator_at_end(self):
        c = CircuitTopology("C1", CircuitClass.CLASS_B, CircuitType.SLC)
        c.add_device(CircuitDevice("D1", "detector", 10.0, 0.0, 3.0))
        c.add_device(CircuitDevice("ISO1", "isolator", 20.0, 0.0, 3.0))
        assert c.get_isolator_indices() == [1]

    def test_case_insensitive_isolator_type(self):
        """'isolator' substring matching should be case-insensitive."""
        c = CircuitTopology("C1", CircuitClass.CLASS_B, CircuitType.SLC)
        c.add_device(CircuitDevice("D1", "detector", 1.0, 0.0, 3.0))
        c.add_device(CircuitDevice("ISO1", "Fault_Isolator", 2.0, 0.0, 3.0))
        c.add_device(CircuitDevice("D2", "detector", 3.0, 0.0, 3.0))
        indices = c.get_isolator_indices()
        assert 1 in indices  # Fault_Isolator contains "isolator"


# ─────────────────────────────────────────────────────────────────────────────
# CircuitTopology — get_device_count_between_isolators (additional)
# ─────────────────────────────────────────────────────────────────────────────


class TestGetDeviceCountBetweenIsolators:
    def test_empty_circuit(self):
        c = CircuitTopology("C1", CircuitClass.CLASS_B, CircuitType.SLC)
        assert c.get_device_count_between_isolators() == []

    def test_only_isolators(self):
        """Circuit with only isolators and no other devices."""
        c = CircuitTopology("C1", CircuitClass.CLASS_B, CircuitType.SLC)
        c.add_device(CircuitDevice("ISO1", "isolator", 0.0, 0.0, 3.0))
        c.add_device(CircuitDevice("ISO2", "isolator", 10.0, 0.0, 3.0))
        counts = c.get_device_count_between_isolators()
        # Before ISO1: 0 devices, between ISO1 and ISO2: 0, after ISO2: 0
        assert counts == [0, 0, 0]

    def test_single_isolator_in_middle(self):
        c = CircuitTopology("C1", CircuitClass.CLASS_B, CircuitType.SLC)
        c.add_device(CircuitDevice("D1", "detector", 1.0, 0.0, 3.0))
        c.add_device(CircuitDevice("D2", "detector", 2.0, 0.0, 3.0))
        c.add_device(CircuitDevice("ISO", "isolator", 3.0, 0.0, 3.0))
        c.add_device(CircuitDevice("D3", "detector", 4.0, 0.0, 3.0))
        c.add_device(CircuitDevice("D4", "detector", 5.0, 0.0, 3.0))
        counts = c.get_device_count_between_isolators()
        assert counts == [2, 2]

    def test_boundary_32_devices(self):
        """Exactly 32 devices before an isolator — must be compliant."""
        c = CircuitTopology("C1", CircuitClass.CLASS_B, CircuitType.SLC)
        for i in range(32):
            c.add_device(CircuitDevice(f"D{i}", "detector", float(i), 0.0, 3.0))
        c.add_device(CircuitDevice("ISO", "isolator", 32.0, 0.0, 3.0))
        counts = c.get_device_count_between_isolators()
        assert counts[0] == 32  # Exactly at the limit

    def test_33_devices_before_isolator(self):
        """33 devices before isolator — NFPA 72 §12.3.1 violation."""
        c = CircuitTopology("C1", CircuitClass.CLASS_B, CircuitType.SLC)
        for i in range(33):
            c.add_device(CircuitDevice(f"D{i}", "detector", float(i), 0.0, 3.0))
        c.add_device(CircuitDevice("ISO", "isolator", 33.0, 0.0, 3.0))
        counts = c.get_device_count_between_isolators()
        assert counts[0] == 33


# ─────────────────────────────────────────────────────────────────────────────
# CircuitTopology — total_cable_length_m (additional)
# ─────────────────────────────────────────────────────────────────────────────


class TestTotalCableLength:
    def test_class_b_zero_length(self):
        c = CircuitTopology("C1", CircuitClass.CLASS_B, CircuitType.SLC, cable_length_m=0.0)
        assert c.total_cable_length_m() == 0.0

    def test_class_a_zero_return(self):
        """Class A with zero return length — only outgoing counted."""
        c = CircuitTopology("C1", CircuitClass.CLASS_A, CircuitType.SLC,
                          cable_length_m=100.0, return_length_m=0.0)
        # total_cable_length_m adds both paths regardless
        assert c.total_cable_length_m() == 100.0

    def test_class_a_equal_paths(self):
        c = CircuitTopology("C1", CircuitClass.CLASS_A, CircuitType.SLC,
                          cable_length_m=100.0, return_length_m=100.0)
        assert c.total_cable_length_m() == 200.0

    def test_class_b_ignores_return(self):
        c = CircuitTopology("C1", CircuitClass.CLASS_B, CircuitType.SLC,
                          cable_length_m=100.0, return_length_m=50.0)
        # Class B: only outgoing path counted
        assert c.total_cable_length_m() == 100.0


# ─────────────────────────────────────────────────────────────────────────────
# CircuitTopology — validate() Comprehensive (additional)
# ─────────────────────────────────────────────────────────────────────────────


class TestValidateComprehensive:
    """Comprehensive validation tests beyond test_cable_routing.py coverage."""

    def test_valid_nac_circuit(self):
        """Valid NAC circuit must be compliant."""
        c = CircuitTopology("NAC-1", CircuitClass.CLASS_B, CircuitType.NAC,
                          cable_length_m=50.0)
        c.add_device(CircuitDevice("HS1", "horn_strobe", 25.0, 0.0, 3.0, current_a=0.150))
        result = c.validate()
        assert result["compliant"] is True

    def test_nan_cable_length_violation(self):
        """NaN cable_length_m → DATA_INTEGRITY violation."""
        c = CircuitTopology("C1", CircuitClass.CLASS_B, CircuitType.SLC,
                          cable_length_m=float("nan"))
        c.add_device(CircuitDevice("D1", "detector", 10.0, 0.0, 3.0))
        result = c.validate()
        assert result["compliant"] is False
        assert any(v["type"] == "invalid_cable_length" for v in result["violations"])

    def test_negative_cable_length_violation(self):
        """Negative cable_length_m → DATA_INTEGRITY violation."""
        c = CircuitTopology("C1", CircuitClass.CLASS_B, CircuitType.SLC,
                          cable_length_m=-10.0)
        c.add_device(CircuitDevice("D1", "detector", 10.0, 0.0, 3.0))
        result = c.validate()
        assert result["compliant"] is False
        assert any(v["type"] == "invalid_cable_length" for v in result["violations"])

    def test_inf_cable_length_violation(self):
        """Inf cable_length_m → DATA_INTEGRITY violation."""
        c = CircuitTopology("C1", CircuitClass.CLASS_B, CircuitType.SLC,
                          cable_length_m=float("inf"))
        c.add_device(CircuitDevice("D1", "detector", 10.0, 0.0, 3.0))
        result = c.validate()
        assert result["compliant"] is False
        assert any(v["type"] == "invalid_cable_length" for v in result["violations"])

    def test_class_a_nan_return_length_violation(self):
        """Class A with NaN return_length → violation."""
        c = CircuitTopology("C1", CircuitClass.CLASS_A, CircuitType.SLC,
                          cable_length_m=50.0, return_length_m=float("nan"))
        c.add_device(CircuitDevice("D1", "detector", 10.0, 0.0, 3.0))
        result = c.validate()
        assert result["compliant"] is False
        assert any(v["type"] == "invalid_return_length" for v in result["violations"])

    def test_class_a_negative_return_length_violation(self):
        """Class A with negative return_length → violation."""
        c = CircuitTopology("C1", CircuitClass.CLASS_A, CircuitType.SLC,
                          cable_length_m=50.0, return_length_m=-10.0)
        c.add_device(CircuitDevice("D1", "detector", 10.0, 0.0, 3.0))
        result = c.validate()
        assert result["compliant"] is False

    def test_panel_at_origin_warning_v96(self):
        """V96 FIX: Panel at (0,0,0) with devices → warning.

        A panel at origin likely means position was never set, causing
        catastrophic voltage drop errors.
        """
        c = CircuitTopology("C1", CircuitClass.CLASS_B, CircuitType.SLC,
                          panel_position=(0.0, 0.0, 0.0), cable_length_m=50.0)
        c.add_device(CircuitDevice("D1", "detector", 10.0, 0.0, 3.0))
        result = c.validate()
        assert any(w["type"] == "panel_at_origin" for w in result["warnings"])

    def test_panel_not_at_origin_no_warning(self):
        """Panel at non-origin position → no warning."""
        c = CircuitTopology("C1", CircuitClass.CLASS_B, CircuitType.SLC,
                          panel_position=(5.0, 10.0, 1.0), cable_length_m=50.0)
        c.add_device(CircuitDevice("D1", "detector", 10.0, 0.0, 3.0))
        result = c.validate()
        assert not any(w["type"] == "panel_at_origin" for w in result["warnings"])

    def test_panel_at_origin_no_devices_no_warning(self):
        """Panel at origin with NO devices → no warning (no calculation error)."""
        c = CircuitTopology("C1", CircuitClass.CLASS_B, CircuitType.SLC,
                          panel_position=(0.0, 0.0, 0.0), cable_length_m=50.0)
        result = c.validate()
        assert not any(w["type"] == "panel_at_origin" for w in result["warnings"])

    def test_nac_nan_current_violation(self):
        """NAC device with NaN current → violation."""
        c = CircuitTopology("C1", CircuitClass.CLASS_B, CircuitType.NAC,
                          cable_length_m=50.0)
        c.devices.append(CircuitDevice("HS1", "horn_strobe", 10.0, 0.0, 3.0, current_a=float("nan")))
        result = c.validate()
        assert result["compliant"] is False
        assert any(v["type"] == "invalid_device_current" for v in result["violations"])

    def test_nac_inf_current_violation(self):
        """NAC device with Inf current → violation."""
        c = CircuitTopology("C1", CircuitClass.CLASS_B, CircuitType.NAC,
                          cable_length_m=50.0)
        c.devices.append(CircuitDevice("HS1", "horn_strobe", 10.0, 0.0, 3.0, current_a=float("inf")))
        result = c.validate()
        assert result["compliant"] is False

    def test_slc_many_devices_no_isolators_warning(self):
        """SLC with >32 devices and no isolators → warning."""
        c = CircuitTopology("C1", CircuitClass.CLASS_B, CircuitType.SLC)
        for i in range(40):
            c.add_device(CircuitDevice(f"D{i}", "detector", float(i), 0.0, 3.0))
        result = c.validate()
        assert any(w["type"] == "no_isolators_on_large_slc" for w in result["warnings"])

    def test_class_a_return_path_excessively_long_warning(self):
        """Return path >3× outgoing → warning to verify routing separation."""
        c = CircuitTopology("C1", CircuitClass.CLASS_A, CircuitType.SLC,
                          cable_length_m=50.0, return_length_m=200.0)
        c.add_device(CircuitDevice("D1", "detector", 10.0, 0.0, 3.0))
        result = c.validate()
        assert any(w["type"] == "class_a_return_path_excessively_long" for w in result["warnings"])

    def test_class_a_return_path_reasonable_no_warning(self):
        """Return path ≤3× outgoing → no excessive length warning."""
        c = CircuitTopology("C1", CircuitClass.CLASS_A, CircuitType.SLC,
                          cable_length_m=50.0, return_length_m=55.0)
        c.add_device(CircuitDevice("D1", "detector", 10.0, 0.0, 3.0))
        result = c.validate()
        assert not any(w["type"] == "class_a_return_path_excessively_long" for w in result["warnings"])

    def test_device_nan_coordinate_via_validate(self):
        """Device with NaN coordinate injected directly → validation catches it."""
        c = CircuitTopology("C1", CircuitClass.CLASS_B, CircuitType.SLC, cable_length_m=50.0)
        c.devices.append(CircuitDevice("D1", "detector", float("nan"), 0.0, 3.0))
        result = c.validate()
        assert result["compliant"] is False
        assert any(v["type"] == "invalid_device_coordinate" for v in result["violations"])

    def test_device_inf_y_coordinate_via_validate(self):
        c = CircuitTopology("C1", CircuitClass.CLASS_B, CircuitType.SLC, cable_length_m=50.0)
        c.devices.append(CircuitDevice("D1", "detector", 0.0, float("inf"), 3.0))
        result = c.validate()
        assert result["compliant"] is False
        assert any(v["coordinate"] == "position_y" for v in result["violations"])

    def test_device_inf_z_coordinate_via_validate(self):
        c = CircuitTopology("C1", CircuitClass.CLASS_B, CircuitType.SLC, cable_length_m=50.0)
        c.devices.append(CircuitDevice("D1", "detector", 0.0, 0.0, float("inf")))
        result = c.validate()
        assert result["compliant"] is False
        assert any(v["coordinate"] == "position_z" for v in result["violations"])

    def test_validate_result_structure(self):
        """Validate result must include required keys."""
        c = CircuitTopology("C1", CircuitClass.CLASS_B, CircuitType.SLC, cable_length_m=50.0)
        result = c.validate()
        assert "compliant" in result
        assert "violations" in result
        assert "warnings" in result
        assert "device_count" in result
        assert "isolator_count" in result
        assert "total_cable_length_m" in result
        assert "nfpa_sections" in result

    def test_validate_nfpa_sections_present(self):
        c = CircuitTopology("C1", CircuitClass.CLASS_B, CircuitType.SLC, cable_length_m=50.0)
        result = c.validate()
        sections = result["nfpa_sections"]
        assert "NFPA 72 §12.2" in sections
        assert "NFPA 72 §12.3" in sections
        assert "NFPA 72 §10.6.4" in sections

    def test_multiple_violations_simultaneously(self):
        """Multiple violations can exist at once."""
        c = CircuitTopology("C1", CircuitClass.CLASS_A, CircuitType.NAC,
                          cable_length_m=-10.0, return_length_m=0.0)
        c.devices.append(CircuitDevice("HS1", "horn_strobe", 10.0, 0.0, 3.0, current_a=-0.1))
        c.devices.append(CircuitDevice("HS2", "horn_strobe", float("nan"), 0.0, 3.0))
        result = c.validate()
        assert result["compliant"] is False
        assert len(result["violations"]) >= 2

    def test_slc_zero_devices_compliant(self):
        """SLC with no devices and valid cable length is compliant."""
        c = CircuitTopology("C1", CircuitClass.CLASS_B, CircuitType.SLC, cable_length_m=50.0)
        result = c.validate()
        assert result["compliant"] is True
        assert result["device_count"] == 0

    def test_nac_with_slc_device_types(self):
        """NAC circuit with detector devices — not typical but should validate."""
        c = CircuitTopology("NAC-1", CircuitClass.CLASS_B, CircuitType.NAC,
                          cable_length_m=50.0)
        c.add_device(CircuitDevice("D1", "detector", 10.0, 0.0, 3.0, current_a=0.015))
        result = c.validate()
        # Should not crash; detector with valid current on NAC
        assert result["compliant"] is True


# ─────────────────────────────────────────────────────────────────────────────
# CircuitTopology — _validate_device_coordinates (internal)
# ─────────────────────────────────────────────────────────────────────────────


class TestValidateDeviceCoordinates:
    """Tests for the static _validate_device_coordinates method."""

    def test_valid_coordinates_pass(self):
        device = CircuitDevice("D1", "detector", 1.0, 2.0, 3.0)
        # Should not raise
        CircuitTopology._validate_device_coordinates(device)

    def test_zero_coordinates_pass(self):
        device = CircuitDevice("D1", "detector", 0.0, 0.0, 0.0)
        CircuitTopology._validate_device_coordinates(device)

    def test_negative_coordinates_pass(self):
        device = CircuitDevice("D1", "detector", -5.0, -10.0, -3.0)
        CircuitTopology._validate_device_coordinates(device)

    def test_nan_x_raises(self):
        device = CircuitDevice("D1", "detector", float("nan"), 0.0, 3.0)
        with pytest.raises(ValueError, match="non-finite"):
            CircuitTopology._validate_device_coordinates(device)

    def test_nan_y_raises(self):
        device = CircuitDevice("D1", "detector", 0.0, float("nan"), 3.0)
        with pytest.raises(ValueError, match="non-finite"):
            CircuitTopology._validate_device_coordinates(device)

    def test_nan_z_raises(self):
        device = CircuitDevice("D1", "detector", 0.0, 0.0, float("nan"))
        with pytest.raises(ValueError, match="non-finite"):
            CircuitTopology._validate_device_coordinates(device)

    def test_inf_x_raises(self):
        device = CircuitDevice("D1", "detector", float("inf"), 0.0, 3.0)
        with pytest.raises(ValueError, match="non-finite"):
            CircuitTopology._validate_device_coordinates(device)

    def test_neg_inf_y_raises(self):
        device = CircuitDevice("D1", "detector", 0.0, float("-inf"), 3.0)
        with pytest.raises(ValueError, match="non-finite"):
            CircuitTopology._validate_device_coordinates(device)

    def test_error_message_contains_device_id(self):
        device = CircuitDevice("MY-DEVICE-42", "detector", float("nan"), 0.0, 3.0)
        with pytest.raises(ValueError, match="MY-DEVICE-42"):
            CircuitTopology._validate_device_coordinates(device)

    def test_error_message_contains_coordinate_name(self):
        device = CircuitDevice("D1", "detector", 0.0, 0.0, float("nan"))
        with pytest.raises(ValueError, match="position_z"):
            CircuitTopology._validate_device_coordinates(device)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
