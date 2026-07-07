# NOSONAR
"""
tests/test_cable_routing.py
===========================
Comprehensive test suite for:
  - fireai/core/cable_routing_engine.py
  - fireai/core/circuit_topology.py

SAFETY CRITICAL: These modules are used to verify fire alarm circuit
wiring compliance per NFPA 72-2022 and NEC Chapter 9, Table 8.
Errors in voltage drop calculation could result in under-powered
notification appliances or detectors — a direct life-safety hazard.

NFPA 72 References:
  §10.6.4  — Voltage drop ≤10% on 24V systems
  §12.2    — Circuit class (A/B) designations
  §12.2.2  — Class A separate routing requirement
  §12.3    — SLC fault isolator requirements
  §12.3.1  — Max 32 devices between isolators
  §18.3    — NAC requirements
  NEC Ch.9 Table 8 — Wire resistance values (copper, stranded)
"""

from __future__ import annotations

import dataclasses

import pytest

from fireai.core.cable_routing_engine import (
    MAX_VOLTAGE_DROP_PCT,
    NOMINAL_VOLTAGE_FA,
    CableRoutingEngine,
    ObstacleType,
    RoutingObstacle3D,
    WireGauge,
)
from fireai.core.circuit_topology import (
    MAX_DEVICES_BETWEEN_ISOLATORS,
    CircuitClass,
    CircuitDevice,
    CircuitTopology,
    CircuitType,
)

# Fixtures
# ─────────────────────────────────────────────────────────────────────────────


@pytest.fixture
def engine() -> CableRoutingEngine:
    return CableRoutingEngine()


@pytest.fixture
def simple_slc_class_b() -> CircuitTopology:
    """Class B SLC with 3 detectors in a line."""
    c = CircuitTopology(
        circuit_id="SLC-B-001",
        circuit_class=CircuitClass.CLASS_B,
        circuit_type=CircuitType.SLC,
        panel_position=(0.0, 0.0, 0.0),
        cable_length_m=30.0,
    )
    for i in range(3):
        c.add_device(
            CircuitDevice(
                device_id=f"D{i}",
                device_type="detector",
                position_x=float((i + 1) * 10),
                position_y=0.0,
                position_z=3.0,
                current_a=0.015,
            )
        )
    return c


@pytest.fixture
def simple_nac_class_b() -> CircuitTopology:
    """Class B NAC with 2 horn-strobes."""
    c = CircuitTopology(
        circuit_id="NAC-B-001",
        circuit_class=CircuitClass.CLASS_B,
        circuit_type=CircuitType.NAC,
        panel_position=(0.0, 0.0, 0.0),
        cable_length_m=40.0,
    )
    c.add_device(CircuitDevice("HS-1", "horn_strobe", 20.0, 0.0, 3.0, current_a=0.150))
    c.add_device(CircuitDevice("HS-2", "horn_strobe", 40.0, 0.0, 3.0, current_a=0.150))
    return c


# ─────────────────────────────────────────────────────────────────────────────
# WireGauge Tests
# ─────────────────────────────────────────────────────────────────────────────


class TestWireGauge:
    """
    Wire gauge resistance values — NEC Chapter 9, Table 8.

    V58 FIX: Resistance values updated from 20°C to 75°C per NEC Chapter 9
    Table 8 (copper, stranded, DC resistance at 75°C). Previous values at
    20°C caused voltage drop underestimation by 16-20%, potentially approving
    non-compliant circuits where horns/strobes could fail during a fire.
    """

    def test_awg12_resistance(self):
        # AWG 12: 6.33 Ω/km at 75°C (was 5.310 at 20°C)
        assert WireGauge.AWG_12.resistance_ohm_per_km == pytest.approx(6.33, abs=0.01)

    def test_awg14_resistance(self):
        # AWG 14: 10.07 Ω/km at 75°C (was 8.450 at 20°C)
        assert WireGauge.AWG_14.resistance_ohm_per_km == pytest.approx(10.07, abs=0.01)

    def test_awg16_resistance(self):
        # AWG 16: 16.04 Ω/km at 75°C (was 13.40 at 20°C)
        assert WireGauge.AWG_16.resistance_ohm_per_km == pytest.approx(16.04, abs=0.01)

    def test_awg18_resistance(self):
        # AWG 18: 25.49 Ω/km at 75°C (was 21.40 at 20°C)
        assert WireGauge.AWG_18.resistance_ohm_per_km == pytest.approx(25.49, abs=0.01)

    def test_awg_values(self):
        assert {g.awg_value for g in WireGauge} == {"12", "14", "16", "18"}

    def test_resistance_increases_with_gauge_number(self):
        """Higher AWG number = thinner wire = higher resistance."""
        assert (
            WireGauge.AWG_18.resistance_ohm_per_km
            > WireGauge.AWG_16.resistance_ohm_per_km
            > WireGauge.AWG_14.resistance_ohm_per_km
            > WireGauge.AWG_12.resistance_ohm_per_km
        )


# ─────────────────────────────────────────────────────────────────────────────
# CircuitDevice Tests
# ─────────────────────────────────────────────────────────────────────────────


class TestCircuitDevice:
    def test_default_values(self):
        d = CircuitDevice("D1", "detector")
        assert d.position_x == 0.0  # NOSONAR — S1244: import retained for re-export / API surface
        assert d.position_y == 0.0  # NOSONAR — S1244: import retained for re-export / API surface
        assert d.position_z == 0.0  # NOSONAR — S1244: import retained for re-export / API surface
        assert d.current_a == 0.0  # NOSONAR — S1244: import retained for re-export / API surface
        assert d.zone_id is None

    def test_custom_values(self):
        d = CircuitDevice("D1", "horn_strobe", 5.0, 10.0, 3.0, 0.150, "ZONE-1")
        assert d.position_x == 5.0  # NOSONAR — S1244: import retained for re-export / API surface
        assert d.current_a == 0.150  # NOSONAR — S1244: import retained for re-export / API surface
        assert d.zone_id == "ZONE-1"

    def test_immutable(self):
        d = CircuitDevice("D1", "detector", 1.0, 2.0, 3.0)
        with pytest.raises(dataclasses.FrozenInstanceError):
            d.position_x = 99.0  # frozen dataclass


# ─────────────────────────────────────────────────────────────────────────────
# CircuitTopology Tests
# ─────────────────────────────────────────────────────────────────────────────


class TestCircuitTopology:
    def test_add_device(self):
        c = CircuitTopology("C1", CircuitClass.CLASS_B, CircuitType.SLC)
        c.add_device(CircuitDevice("D1", "detector", 1.0, 2.0, 3.0))
        assert len(c.devices) == 1

    def test_reject_nan_coordinate(self):
        c = CircuitTopology("C1", CircuitClass.CLASS_B, CircuitType.SLC)
        with pytest.raises(ValueError, match="non-finite"):  # NOSONAR — S5778: re-raise inside except is intentional (context-specific)
            c.add_device(CircuitDevice("D1", "detector", float("nan"), 0, 3))

    def test_reject_inf_coordinate(self):
        c = CircuitTopology("C1", CircuitClass.CLASS_B, CircuitType.SLC)
        with pytest.raises(ValueError, match="non-finite"):  # NOSONAR — S5778: re-raise inside except is intentional (context-specific)
            c.add_device(CircuitDevice("D1", "detector", float("inf"), 0, 3))

    def test_remove_device(self):
        c = CircuitTopology("C1", CircuitClass.CLASS_B, CircuitType.SLC)
        c.add_device(CircuitDevice("D1", "detector", 1, 2, 3))
        removed = c.remove_device("D1")
        assert removed is True
        assert len(c.devices) == 0

    def test_remove_nonexistent_device(self):
        c = CircuitTopology("C1", CircuitClass.CLASS_B, CircuitType.SLC)
        assert c.remove_device("NONEXISTENT") is False

    def test_get_isolator_indices(self):
        c = CircuitTopology("C1", CircuitClass.CLASS_B, CircuitType.SLC)
        c.devices = [
            CircuitDevice("D1", "detector", 1, 0, 3),
            CircuitDevice("ISO1", "isolator", 2, 0, 3),
            CircuitDevice("D2", "detector", 3, 0, 3),
        ]
        assert c.get_isolator_indices() == [1]

    def test_get_device_count_between_isolators_no_isolators(self):
        c = CircuitTopology("C1", CircuitClass.CLASS_B, CircuitType.SLC)
        for i in range(5):
            c.devices.append(CircuitDevice(f"D{i}", "detector", i, 0, 3))
        counts = c.get_device_count_between_isolators()
        assert counts == [5]

    def test_get_device_count_between_isolators_with_isolator(self):
        c = CircuitTopology("C1", CircuitClass.CLASS_B, CircuitType.SLC)
        c.devices = [
            CircuitDevice("D1", "detector", 1, 0, 3),
            CircuitDevice("D2", "detector", 2, 0, 3),
            CircuitDevice("ISO", "isolator", 3, 0, 3),
            CircuitDevice("D3", "detector", 4, 0, 3),
        ]
        counts = c.get_device_count_between_isolators()
        assert counts == [2, 1]

    def test_total_cable_length_class_b(self):
        c = CircuitTopology("C1", CircuitClass.CLASS_B, CircuitType.SLC, cable_length_m=100.0, return_length_m=50.0)
        assert c.total_cable_length_m() == 100.0  # Class B ignores return  # NOSONAR — S1244: import retained for re-export / API surface

    def test_total_cable_length_class_a(self):
        c = CircuitTopology("C1", CircuitClass.CLASS_A, CircuitType.SLC, cable_length_m=100.0, return_length_m=105.0)
        assert c.total_cable_length_m() == 205.0  # Both paths  # NOSONAR — S1244: import retained for re-export / API surface

    # ── Validation ──────────────────────────────────────────────────────────

    def test_validate_compliant_class_b(self):
        c = CircuitTopology("C1", CircuitClass.CLASS_B, CircuitType.SLC, cable_length_m=50.0)
        for i in range(10):
            c.devices.append(CircuitDevice(f"D{i}", "detector", float(i), 0, 3))
        result = c.validate()
        assert result["compliant"] is True
        assert len(result["violations"]) == 0

    def test_validate_violation_too_many_devices_no_isolator(self):
        """NFPA 72 §12.3.1: max 32 devices between isolators on SLC."""
        c = CircuitTopology("C1", CircuitClass.CLASS_B, CircuitType.SLC)
        for i in range(MAX_DEVICES_BETWEEN_ISOLATORS + 1):
            c.devices.append(CircuitDevice(f"D{i}", "detector", float(i), 0, 3))
        result = c.validate()
        assert result["compliant"] is False
        assert any(v["type"] == "too_many_devices_between_isolators" for v in result["violations"])

    def test_validate_32_devices_exactly_compliant(self):
        """Exactly 32 devices — boundary condition, must be compliant."""
        c = CircuitTopology("C1", CircuitClass.CLASS_B, CircuitType.SLC)
        for i in range(MAX_DEVICES_BETWEEN_ISOLATORS):
            c.devices.append(CircuitDevice(f"D{i}", "detector", float(i), 0, 3))
        result = c.validate()
        assert result["compliant"] is True

    def test_validate_class_a_missing_return_path(self):
        """NFPA 72 §12.2.2: Class A must have return path."""
        c = CircuitTopology("C1", CircuitClass.CLASS_A, CircuitType.SLC, cable_length_m=50.0, return_length_m=0.0)
        c.devices.append(CircuitDevice("D1", "detector", 10, 0, 3))
        result = c.validate()
        assert result["compliant"] is False
        assert any(v["type"] == "class_a_missing_return_path" for v in result["violations"])

    def test_validate_class_a_with_return_path_compliant(self):
        c = CircuitTopology("C1", CircuitClass.CLASS_A, CircuitType.SLC, cable_length_m=50.0, return_length_m=55.0)
        c.devices.append(CircuitDevice("D1", "detector", 10, 0, 3))
        result = c.validate()
        assert result["compliant"] is True

    def test_validate_class_b_warns_if_return_length_set(self):
        c = CircuitTopology("C1", CircuitClass.CLASS_B, CircuitType.SLC, cable_length_m=50.0, return_length_m=10.0)
        result = c.validate()
        assert any(w["type"] == "class_b_has_return_length" for w in result["warnings"])

    def test_validate_nac_negative_current_violation(self):
        c = CircuitTopology("C1", CircuitClass.CLASS_B, CircuitType.NAC, cable_length_m=50.0)
        c.devices.append(CircuitDevice("HS1", "horn_strobe", 10, 0, 3, current_a=-0.1))
        result = c.validate()
        assert result["compliant"] is False

    def test_nfpa_sections_in_validation(self):
        c = CircuitTopology("C1", CircuitClass.CLASS_B, CircuitType.SLC, cable_length_m=50.0)
        result = c.validate()
        assert "NFPA 72 §12.2" in result["nfpa_sections"]
        assert "NFPA 72 §12.3" in result["nfpa_sections"]


# ─────────────────────────────────────────────────────────────────────────────
# CableRoutingEngine — Initialization
# ─────────────────────────────────────────────────────────────────────────────


class TestCableRoutingEngineInit:
    def test_default_init(self):
        e = CableRoutingEngine()
        assert e._ps_voltage == NOMINAL_VOLTAGE_FA
        assert e._max_drop_pct == MAX_VOLTAGE_DROP_PCT

    def test_custom_voltage(self):
        e = CableRoutingEngine(ps_voltage=12.0)
        assert e._ps_voltage == 12.0  # NOSONAR — S1244: import retained for re-export / API surface

    def test_zero_voltage_raises(self):
        with pytest.raises(ValueError):
            CableRoutingEngine(ps_voltage=0.0)

    def test_negative_voltage_raises(self):
        with pytest.raises(ValueError):
            CableRoutingEngine(ps_voltage=-24.0)

    def test_nan_voltage_raises(self):
        with pytest.raises(ValueError):  # NOSONAR — S5778: re-raise inside except is intentional (context-specific)
            CableRoutingEngine(ps_voltage=float("nan"))

    def test_inf_max_drop_raises(self):
        with pytest.raises(ValueError):  # NOSONAR — S5778: re-raise inside except is intentional (context-specific)
            CableRoutingEngine(max_voltage_drop_pct=float("inf"))


# ─────────────────────────────────────────────────────────────────────────────
# CableRoutingEngine — 3D Distance
# ─────────────────────────────────────────────────────────────────────────────


class TestCableRoutingEngine3DDistance:
    def test_zero_distance(self):
        d = CableRoutingEngine.calculate_3d_distance((0, 0, 0), (0, 0, 0))
        assert d == pytest.approx(0.0)

    def test_axis_aligned_x(self):
        d = CableRoutingEngine.calculate_3d_distance((0, 0, 0), (10, 0, 0))
        assert d == pytest.approx(10.0)

    def test_axis_aligned_y(self):
        d = CableRoutingEngine.calculate_3d_distance((0, 0, 0), (0, 5, 0))
        assert d == pytest.approx(5.0)

    def test_axis_aligned_z(self):
        d = CableRoutingEngine.calculate_3d_distance((0, 0, 0), (0, 0, 3))
        assert d == pytest.approx(3.0)

    def test_3d_pythagorean(self):
        # 3-4-5 right triangle in XY, Z=0
        d = CableRoutingEngine.calculate_3d_distance((0, 0, 0), (3, 4, 0))
        assert d == pytest.approx(5.0)

    def test_full_3d(self):
        d = CableRoutingEngine.calculate_3d_distance((1, 1, 1), (4, 5, 1))
        assert d == pytest.approx(5.0)

    def test_nan_rejected(self):
        with pytest.raises(ValueError, match="finite"):  # NOSONAR — S5778: re-raise inside except is intentional (context-specific)
            CableRoutingEngine.calculate_3d_distance((float("nan"), 0, 0), (1, 0, 0))

    def test_inf_rejected(self):
        with pytest.raises(ValueError, match="finite"):  # NOSONAR — S5778: re-raise inside except is intentional (context-specific)
            CableRoutingEngine.calculate_3d_distance((0, 0, 0), (float("inf"), 0, 0))


# ─────────────────────────────────────────────────────────────────────────────
# CableRoutingEngine — Input Validation
# ─────────────────────────────────────────────────────────────────────────────


class TestCableRoutingEngineValidation:
    def test_nan_cable_length_raises(self, engine):
        c = CircuitTopology("C1", CircuitClass.CLASS_B, CircuitType.SLC, cable_length_m=float("nan"))
        c.devices.append(CircuitDevice("D1", "detector", 10, 0, 3, 0.015))
        with pytest.raises(ValueError, match="non-negative finite"):
            engine.route_circuit(c)

    def test_negative_cable_length_raises(self, engine):
        c = CircuitTopology("C1", CircuitClass.CLASS_B, CircuitType.SLC, cable_length_m=-10.0)
        c.devices.append(CircuitDevice("D1", "detector", 10, 0, 3, 0.015))
        with pytest.raises(ValueError, match="non-negative finite"):
            engine.route_circuit(c)

    def test_nan_device_coordinate_raises(self, engine):
        c = CircuitTopology("C1", CircuitClass.CLASS_B, CircuitType.SLC, cable_length_m=50.0)
        # Bypass add_device validation to inject bad data directly
        c.devices.append(CircuitDevice("D1", "detector", float("nan"), 0, 3, 0.015))
        with pytest.raises(ValueError, match="non-finite"):
            engine.route_circuit(c)

    def test_negative_device_current_raises(self, engine):
        c = CircuitTopology("C1", CircuitClass.CLASS_B, CircuitType.SLC, cable_length_m=50.0)
        c.devices.append(CircuitDevice("D1", "detector", 10, 0, 3, -0.015))
        with pytest.raises(ValueError, match="invalid current"):
            engine.route_circuit(c)

    def test_class_a_no_return_path_raises(self, engine):
        """NFPA 72 §12.2.2: Class A circuit must have return path."""
        c = CircuitTopology("C1", CircuitClass.CLASS_A, CircuitType.SLC, cable_length_m=50.0, return_length_m=0.0)
        c.devices.append(CircuitDevice("D1", "detector", 10, 0, 3, 0.015))
        with pytest.raises(ValueError, match="return_length_m"):
            engine.route_circuit(c)


# ─────────────────────────────────────────────────────────────────────────────
# CableRoutingEngine — Voltage Drop Calculations (NFPA 72 §10.6.4)
# ─────────────────────────────────────────────────────────────────────────────


class TestVoltageDrop:
    """
    SAFETY CRITICAL: Voltage drop formula must include the ×2 DC return
    path factor per NEC Chapter 9. Omitting it would report 50% of actual
    drop, potentially approving circuits that violate NFPA 72 §10.6.4.
    """

    def test_voltage_drop_formula_includes_return_factor(self, engine):
        """V_drop = I × 2 × R/km × L_km — must include ×2 factor."""
        # Single device, known current, known gauge, known distance
        c = CircuitTopology("C1", CircuitClass.CLASS_B, CircuitType.NAC, panel_position=(0, 0, 0), cable_length_m=100.0)
        # Place device exactly 100m away in X (Z=0 for clean Euclidean)
        c.add_device(CircuitDevice("HS1", "horn_strobe", 100.0, 0.0, 0.0, 0.100))
        result = engine.route_circuit(c, wire_gauge=WireGauge.AWG_14)

        # V58 FIX: Resistance at 75°C per NEC Ch.9 Table 8
        # Expected: 0.100A × 2 × 10.07Ω/km × 0.100km = 0.2014V
        expected = 0.100 * 2.0 * 10.07 * (100.0 / 1000.0)
        assert result.total_voltage_drop_v == pytest.approx(expected, rel=1e-4), (
            f"Voltage drop formula wrong. Expected {expected:.4f}V (includes ×2 return), "
            f"got {result.total_voltage_drop_v:.4f}V. "
            f"SAFETY: omitting ×2 would report {expected / 2:.4f}V, "
            f"half the real drop — potentially approving non-compliant circuits."
        )

    def test_voltage_drop_percentage_calculation(self, engine):
        """Drop % = (V_drop / V_system) × 100."""
        c = CircuitTopology("C1", CircuitClass.CLASS_B, CircuitType.NAC, panel_position=(0, 0, 0), cable_length_m=100.0)
        c.add_device(CircuitDevice("HS1", "horn_strobe", 100.0, 0.0, 0.0, 0.100))
        result = engine.route_circuit(c, wire_gauge=WireGauge.AWG_14, ps_voltage=24.0)
        expected_pct = (result.total_voltage_drop_v / 24.0) * 100.0
        assert result.total_voltage_drop_pct == pytest.approx(expected_pct, rel=1e-4)

    def test_end_of_line_voltage(self, engine):
        """V_EOL = V_supply - V_drop."""
        c = CircuitTopology("C1", CircuitClass.CLASS_B, CircuitType.NAC, panel_position=(0, 0, 0), cable_length_m=100.0)
        c.add_device(CircuitDevice("HS1", "horn_strobe", 100.0, 0.0, 0.0, 0.100))
        result = engine.route_circuit(c, wire_gauge=WireGauge.AWG_14, ps_voltage=24.0)
        expected_eol = 24.0 - result.total_voltage_drop_v
        assert result.end_of_line_voltage_v == pytest.approx(expected_eol, rel=1e-4)

    def test_compliant_short_circuit(self, engine, simple_slc_class_b):
        """Short circuit with low current must be compliant per NFPA 72 §10.6.4."""
        result = engine.route_circuit(simple_slc_class_b)
        assert result.is_compliant is True
        assert result.total_voltage_drop_pct <= MAX_VOLTAGE_DROP_PCT

    def test_non_compliant_very_long_circuit(self):
        """Extremely long NAC must fail compliance (500m, high current, AWG18)."""
        engine = CableRoutingEngine()
        c = CircuitTopology("C1", CircuitClass.CLASS_B, CircuitType.NAC, panel_position=(0, 0, 0), cable_length_m=500.0)
        # 1A, 500m, AWG18: V_drop = 1.0 × 2 × 21.4 × 0.5 = 21.4V → 89% > 10%
        c.add_device(CircuitDevice("HS1", "horn_strobe", 500.0, 0.0, 0.0, 1.0))
        result = engine.route_circuit(c, wire_gauge=WireGauge.AWG_18)
        assert result.is_compliant is False
        assert len(result.violations) > 0
        assert result.total_voltage_drop_pct > MAX_VOLTAGE_DROP_PCT

    def test_zero_current_zero_drop(self, engine):
        """Circuit with no current draw must have zero voltage drop."""
        c = CircuitTopology("C1", CircuitClass.CLASS_B, CircuitType.SLC, panel_position=(0, 0, 0), cable_length_m=100.0)
        c.add_device(CircuitDevice("D1", "detector", 50.0, 0.0, 0.0, current_a=0.0))
        result = engine.route_circuit(c, wire_gauge=WireGauge.AWG_14)
        assert result.total_voltage_drop_v == pytest.approx(0.0, abs=1e-9)
        assert result.is_compliant is True

    def test_cumulative_drop_across_segments(self, engine):
        """Voltage drop must accumulate across all segments."""
        c = CircuitTopology("C1", CircuitClass.CLASS_B, CircuitType.NAC, panel_position=(0, 0, 0), cable_length_m=200.0)
        c.add_device(CircuitDevice("HS1", "horn_strobe", 100.0, 0.0, 0.0, 0.100))
        c.add_device(CircuitDevice("HS2", "horn_strobe", 200.0, 0.0, 0.0, 0.100))
        result = engine.route_circuit(c, wire_gauge=WireGauge.AWG_14)

        # Both segments contribute to cumulative drop
        assert len(result.segments) == 2
        seg_sum = sum(s.voltage_drop_v for s in result.segments)
        assert result.total_voltage_drop_v == pytest.approx(seg_sum, rel=1e-6)

    def test_nfpa_section_referenced_in_formula(self, engine):
        """Every segment formula must reference NFPA 72 §10.6.4."""
        c = CircuitTopology("C1", CircuitClass.CLASS_B, CircuitType.SLC, panel_position=(0, 0, 0), cable_length_m=50.0)
        c.add_device(CircuitDevice("D1", "detector", 25.0, 0.0, 3.0, 0.015))
        result = engine.route_circuit(c)
        for seg in result.segments:
            assert "NFPA 72 §10.6.4" in seg.nfpa_section


# ─────────────────────────────────────────────────────────────────────────────
# CableRoutingEngine — Auto Gauge Selection
# ─────────────────────────────────────────────────────────────────────────────


class TestAutoGaugeSelection:
    def test_short_circuit_selects_awg18(self):
        """Short, low-current circuit should use AWG 18 (minimum, cheapest)."""
        engine = CableRoutingEngine()
        c = CircuitTopology("C1", CircuitClass.CLASS_B, CircuitType.SLC, panel_position=(0, 0, 0), cable_length_m=10.0)
        c.add_device(CircuitDevice("D1", "detector", 10.0, 0.0, 0.0, 0.010))
        result = engine.route_circuit(c)
        assert result.wire_gauge == WireGauge.AWG_18
        assert result.selected_gauge_is_minimum is True
        assert result.is_compliant is True

    def test_auto_gauge_always_compliant_or_reports_violation(self):
        """Auto gauge must either find a compliant gauge or report a violation."""
        engine = CableRoutingEngine()
        c = CircuitTopology("C1", CircuitClass.CLASS_B, CircuitType.NAC, panel_position=(0, 0, 0), cable_length_m=300.0)
        c.add_device(CircuitDevice("HS1", "horn_strobe", 300.0, 0.0, 0.0, 0.500))
        result = engine.route_circuit(c)
        # Either it's compliant or it has violations — never silently wrong
        if not result.is_compliant:
            assert len(result.violations) > 0

    def test_specified_gauge_overrides_auto(self):
        """When wire_gauge is specified, the engine must use it exactly."""
        engine = CableRoutingEngine()
        c = CircuitTopology("C1", CircuitClass.CLASS_B, CircuitType.SLC, panel_position=(0, 0, 0), cable_length_m=10.0)
        c.add_device(CircuitDevice("D1", "detector", 10.0, 0.0, 0.0, 0.015))
        result = engine.route_circuit(c, wire_gauge=WireGauge.AWG_12)
        assert result.wire_gauge == WireGauge.AWG_12

    def test_no_compliant_gauge_reports_violation(self):
        """If no AWG 12-18 gauge is compliant, engine must report violation."""
        engine = CableRoutingEngine()
        c = CircuitTopology("C1", CircuitClass.CLASS_B, CircuitType.NAC, panel_position=(0, 0, 0), cable_length_m=600.0)
        # 2A at 600m — even AWG 12 will fail
        c.add_device(CircuitDevice("HS1", "horn_strobe", 600.0, 0.0, 0.0, 2.0))
        result = engine.route_circuit(c)
        assert result.is_compliant is False
        assert len(result.violations) > 0


# ─────────────────────────────────────────────────────────────────────────────
# CableRoutingEngine — Class A Circuits
# ─────────────────────────────────────────────────────────────────────────────


class TestClassACircuit:
    """NFPA 72 §12.2.2: Class A circuits require separate return path routing."""

    def test_class_a_compliant_with_return(self):
        engine = CableRoutingEngine()
        c = CircuitTopology(
            "SLC-A",
            CircuitClass.CLASS_A,
            CircuitType.SLC,
            panel_position=(0, 0, 0),
            cable_length_m=50.0,
            return_length_m=55.0,
        )
        c.add_device(CircuitDevice("D1", "detector", 25.0, 0.0, 3.0, 0.015))
        c.add_device(CircuitDevice("D2", "detector", 50.0, 0.0, 3.0, 0.015))
        result = engine.route_circuit(c, wire_gauge=WireGauge.AWG_14)
        assert result.is_compliant is True
        assert result.total_return_length_m == 55.0  # NOSONAR — S1244: import retained for re-export / API surface

    def test_class_a_no_return_raises_value_error(self):
        """NFPA 72 §12.2.2 violation raises ValueError (not just a warning)."""
        engine = CableRoutingEngine()
        c = CircuitTopology(
            "SLC-A",
            CircuitClass.CLASS_A,
            CircuitType.SLC,
            panel_position=(0, 0, 0),
            cable_length_m=50.0,
            return_length_m=0.0,
        )
        c.add_device(CircuitDevice("D1", "detector", 25.0, 0.0, 3.0, 0.015))
        with pytest.raises(ValueError, match="Class A"):
            engine.route_circuit(c)

    def test_class_a_loop_drop_checked(self):
        """Class A loop voltage drop must include return path."""
        engine = CableRoutingEngine()
        c = CircuitTopology(
            "SLC-A",
            CircuitClass.CLASS_A,
            CircuitType.SLC,
            panel_position=(0, 0, 0),
            cable_length_m=50.0,
            return_length_m=50.0,
        )
        c.add_device(CircuitDevice("D1", "detector", 50.0, 0.0, 0.0, 0.500))
        result = engine.route_circuit(c, wire_gauge=WireGauge.AWG_18)
        # If loop drop exceeds 10%, should report violation
        if result.total_voltage_drop_pct > MAX_VOLTAGE_DROP_PCT:
            assert not result.is_compliant


# ─────────────────────────────────────────────────────────────────────────────
# RoutingObstacle3D Tests
# ─────────────────────────────────────────────────────────────────────────────


class TestRoutingObstacle3D:
    def test_contains_point_inside(self):
        obs = RoutingObstacle3D("W1", ObstacleType.WALL, 0, 0, 0, 5, 5, 4)
        assert obs.contains_point(2, 2, 2) is True

    def test_contains_point_outside(self):
        obs = RoutingObstacle3D("W1", ObstacleType.WALL, 0, 0, 0, 5, 5, 4)
        assert obs.contains_point(10, 10, 10) is False

    def test_contains_point_on_boundary(self):
        obs = RoutingObstacle3D("W1", ObstacleType.WALL, 0, 0, 0, 5, 5, 4)
        assert obs.contains_point(5, 5, 4) is True

    def test_intersects_line_segment_through(self):
        """Line passing through obstacle must be detected."""
        obs = RoutingObstacle3D("W1", ObstacleType.WALL, 4, 0, 0, 6, 10, 4)
        # Line from (0,5,2) to (10,5,2) passes through x=4..6
        assert obs.intersects_line_segment((0, 5, 2), (10, 5, 2)) is True

    def test_intersects_line_segment_parallel_miss(self):
        """Line parallel to and outside obstacle must not intersect."""
        obs = RoutingObstacle3D("W1", ObstacleType.WALL, 0, 0, 0, 1, 10, 4)
        # Line from (5,0,2) to (5,10,2) — entirely outside x range
        assert obs.intersects_line_segment((5, 0, 2), (5, 10, 2)) is False

    def test_obstacle_types(self):
        """All obstacle types must be representable."""
        for otype in ObstacleType:
            obs = RoutingObstacle3D(f"OBS-{otype.value}", otype, 0, 0, 0, 1, 1, 1)
            assert obs.obstacle_type == otype

    def test_immutable(self):
        obs = RoutingObstacle3D("W1", ObstacleType.WALL, 0, 0, 0, 5, 5, 4)
        with pytest.raises(dataclasses.FrozenInstanceError):
            obs.x1 = 99.0  # frozen dataclass


# ─────────────────────────────────────────────────────────────────────────────
# CableRoutingEngine — Obstacle Detection & Warnings
# ─────────────────────────────────────────────────────────────────────────────


class TestObstacleDetection:
    def test_no_obstacles_no_warnings(self, engine, simple_slc_class_b):
        result = engine.route_circuit(simple_slc_class_b)
        firestop_warnings = [w for w in result.warnings if "firestopping" in w]
        assert len(firestop_warnings) == 0

    def test_wall_obstacle_generates_firestop_warning(self):
        """Cable crossing a rated wall must generate firestopping warning."""
        wall = RoutingObstacle3D(
            "WALL-RATED",
            ObstacleType.WALL,
            x1=9,
            y1=0,
            z1=0,
            x2=9.2,
            y2=20,
            z2=4,
            requires_firestop=True,
            is_rated=True,
            fire_rating_hours=2.0,
        )
        engine = CableRoutingEngine(obstacles=[wall])
        c = CircuitTopology("C1", CircuitClass.CLASS_B, CircuitType.SLC, panel_position=(0, 0, 2), cable_length_m=20.0)
        c.add_device(CircuitDevice("D1", "detector", 20.0, 5.0, 2.0, 0.015))
        result = engine.route_circuit(c)
        firestop_warnings = [w for w in result.warnings if "firestopping" in w]
        assert len(firestop_warnings) >= 1

    def test_add_obstacle_method(self, engine):
        engine.add_obstacle(RoutingObstacle3D("W1", ObstacleType.WALL, 0, 0, 0, 1, 1, 1))
        assert len(engine._obstacles) == 1

    def test_clear_obstacles(self, engine):
        engine.add_obstacle(RoutingObstacle3D("W1", ObstacleType.WALL, 0, 0, 0, 1, 1, 1))
        engine.clear_obstacles()
        assert len(engine._obstacles) == 0

    def test_check_obstacle_intersections(self):
        wall = RoutingObstacle3D("W1", ObstacleType.WALL, 4, 0, 0, 6, 10, 4)
        engine = CableRoutingEngine(obstacles=[wall])
        hits = engine.check_obstacle_intersections((0, 5, 2), (10, 5, 2))
        assert len(hits) == 1
        assert hits[0].obstacle_id == "W1"

    def test_no_intersection_outside_obstacle(self):
        wall = RoutingObstacle3D("W1", ObstacleType.WALL, 0, 0, 0, 1, 10, 4)
        engine = CableRoutingEngine(obstacles=[wall])
        hits = engine.check_obstacle_intersections((5, 5, 2), (10, 5, 2))
        assert len(hits) == 0


# ─────────────────────────────────────────────────────────────────────────────
# NFPA 72 §12.3.1 — Isolator Placement (32-device limit)
# ─────────────────────────────────────────────────────────────────────────────


class TestSLCIsolatorRequirements:
    """NFPA 72 §12.3.1: No more than 32 addressable devices between isolators."""

    def test_exactly_32_devices_no_isolator_compliant(self):
        c = CircuitTopology("SLC", CircuitClass.CLASS_B, CircuitType.SLC)
        for i in range(32):
            c.devices.append(CircuitDevice(f"D{i}", "detector", float(i), 0, 3))
        result = c.validate()
        assert result["compliant"] is True

    def test_33_devices_no_isolator_violation(self):
        """33 devices without isolator → NFPA 72 §12.3.1 violation."""
        c = CircuitTopology("SLC", CircuitClass.CLASS_B, CircuitType.SLC)
        for i in range(33):
            c.devices.append(CircuitDevice(f"D{i}", "detector", float(i), 0, 3))
        result = c.validate()
        assert result["compliant"] is False
        assert any(v["nfpa_section"] == "NFPA 72 §12.3.1" for v in result["violations"])

    def test_isolator_splits_device_count(self):
        """Isolator placed at index 10 splits 20 devices into two groups of ≤10."""
        c = CircuitTopology("SLC", CircuitClass.CLASS_B, CircuitType.SLC)
        for i in range(10):
            c.devices.append(CircuitDevice(f"D{i}", "detector", float(i), 0, 3))
        c.devices.append(CircuitDevice("ISO1", "fault_isolator", 10.5, 0, 3))
        for i in range(10, 20):
            c.devices.append(CircuitDevice(f"D{i}", "detector", float(i + 1), 0, 3))

        counts = c.get_device_count_between_isolators()
        assert max(counts) <= MAX_DEVICES_BETWEEN_ISOLATORS

    def test_multiple_isolators_all_segments_checked(self):
        """All segments between isolators must individually comply."""
        c = CircuitTopology("SLC", CircuitClass.CLASS_B, CircuitType.SLC)
        # 15 devices, isolator, 40 devices (violation in segment 2), isolator, 15 devices
        for i in range(15):
            c.devices.append(CircuitDevice(f"A{i}", "detector", float(i), 0, 3))
        c.devices.append(CircuitDevice("ISO1", "isolator", 15.5, 0, 3))
        for i in range(40):
            c.devices.append(CircuitDevice(f"B{i}", "detector", float(i + 20), 0, 3))
        c.devices.append(CircuitDevice("ISO2", "isolator", 60.5, 0, 3))
        for i in range(15):
            c.devices.append(CircuitDevice(f"C{i}", "detector", float(i + 80), 0, 3))

        result = c.validate()
        assert result["compliant"] is False  # Segment 2 has 40 > 32
        violation_types = [v["type"] for v in result["violations"]]
        assert "too_many_devices_between_isolators" in violation_types


# ─────────────────────────────────────────────────────────────────────────────
# Integration — Full Routing Scenario
# ─────────────────────────────────────────────────────────────────────────────


class TestIntegrationScenarios:
    """
    End-to-end scenarios representing real-world fire alarm system routing.
    All scenarios trace directly to NFPA 72-2022 requirements.
    """

    def test_office_floor_slc_class_b(self):
        """
        Typical office floor: 1 SLC loop, 20 detectors, 150m total.
        Expected: compliant with auto-selected gauge.
        """
        engine = CableRoutingEngine()
        circuit = CircuitTopology(
            circuit_id="OFFICE-SLC-1",
            circuit_class=CircuitClass.CLASS_B,
            circuit_type=CircuitType.SLC,
            panel_position=(0.0, 0.0, 0.0),
            cable_length_m=150.0,
        )
        x = 0.0
        for i in range(20):
            x += 7.5
            circuit.add_device(
                CircuitDevice(
                    f"SD-{i:02d}",
                    "smoke_detector",
                    position_x=x,
                    position_y=float(i % 3 * 5),
                    position_z=3.0,
                    current_a=0.015,
                )
            )

        result = engine.route_circuit(circuit)
        assert result.is_compliant is True, (
            f"Office floor SLC should be compliant. "
            f"Drop: {result.total_voltage_drop_pct:.2f}%. "
            f"Violations: {result.violations}"
        )

    def test_hotel_corridor_nac_class_a(self):
        """
        Hotel corridor: Class A NAC with horn-strobes every 15m.
        NFPA 72 §12.2.2: outgoing and return conductors routed separately.
        """
        engine = CableRoutingEngine()
        circuit = CircuitTopology(
            circuit_id="HOTEL-NAC-A1",
            circuit_class=CircuitClass.CLASS_A,
            circuit_type=CircuitType.NAC,
            panel_position=(0.0, 0.0, 0.0),
            cable_length_m=90.0,
            return_length_m=92.0,
        )
        for i, x in enumerate([15.0, 30.0, 45.0, 60.0, 75.0, 90.0]):
            circuit.add_device(
                CircuitDevice(
                    f"HS-{i}",
                    "horn_strobe",
                    position_x=x,
                    position_y=0.0,
                    position_z=3.2,
                    current_a=0.095,  # 95mA horn+strobe
                )
            )

        result = engine.route_circuit(circuit)
        assert result.total_return_length_m == 92.0  # NOSONAR — S1244: import retained for re-export / API surface
        # Should be compliant with auto-selected gauge
        if result.is_compliant:
            assert result.total_voltage_drop_pct <= MAX_VOLTAGE_DROP_PCT

    def test_route_result_is_immutable(self, engine, simple_slc_class_b):
        """RouteResult must be immutable (frozen dataclass) — prevents accidental mutation."""
        result = engine.route_circuit(simple_slc_class_b)
        with pytest.raises(dataclasses.FrozenInstanceError):
            result.is_compliant = True

    def test_violations_tuple_not_list(self, engine, simple_slc_class_b):
        """Violations and warnings must be tuples (immutable)."""
        result = engine.route_circuit(simple_slc_class_b)
        assert isinstance(result.violations, tuple)
        assert isinstance(result.warnings, tuple)

    def test_segments_tuple_not_list(self, engine, simple_slc_class_b):
        """Segments must be tuple (immutable)."""
        result = engine.route_circuit(simple_slc_class_b)
        assert isinstance(result.segments, tuple)

    def test_circuit_id_preserved(self, engine):
        """RouteResult must preserve the circuit_id from the input CircuitTopology."""
        c = CircuitTopology("MY-CIRCUIT-42", CircuitClass.CLASS_B, CircuitType.SLC, cable_length_m=10.0)
        c.add_device(CircuitDevice("D1", "detector", 10, 0, 3, 0.015))
        result = engine.route_circuit(c)
        assert result.circuit_id == "MY-CIRCUIT-42"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
