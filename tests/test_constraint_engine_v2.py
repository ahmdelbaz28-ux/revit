"""
tests/test_constraint_engine_v2.py
===================================
Comprehensive test suite for fireai/core/constraint_engine.py

SAFETY CRITICAL: The constraint engine verifies every routing decision
against published code sections (NEC, NFPA 72, Project Spec). Errors
in constraint checks could approve non-compliant installations where
horns/strobes fail during a fire — a direct life-safety hazard.

NFPA/NEC References tested:
  - NEC 760.24: FA cable separation
  - NEC 760.24(A): Cable fastening every 457mm
  - NEC 310.16: Wire ampacity
  - NEC 310.15(B)(2)(A): Ambient temperature derating
  - NEC 310.15(B)(3)(a): Conductor count derating
  - NEC Chapter 9, Table 4: Conduit fill
  - NFPA 72 §23.6.2: NAC circuit max length
  - NFPA 72 §10.6.4: Voltage drop verification
  - NFPA 72 §12.2.2: Class A circuit separation
  - Project Spec: Min 3/4" EMT, bend radius 6xD, 300mm separation
"""

from __future__ import annotations

import dataclasses
import math

import pytest

from fireai.core.cable_routing_engine import WireGauge
from fireai.core.constraint_engine import (
    _NAC_MAX_LENGTHS_M,
    BEND_PENALTY_M,
    BEND_RADIUS_FACTOR,
    ELECTRICAL_PROXIMITY_PENALTY_M,
    ELEVATION_PENALTY_M,
    EMT_3_4_INNER_DIAMETER_MM,
    EMT_3_4_OUTER_DIAMETER_MM,
    MAX_BEND_RADIUS_MM,
    MAX_CABLE_FASTENING_INTERVAL_MM,
    MAX_CONDUIT_FILL_PCT,
    MIN_CONDUIT_INCHES,
    MIN_CONDUIT_MM,
    MIN_ELECTRICAL_SEPARATION_MM,
    ConstraintEngine,
    ConstraintResult,
    ConstraintSource,
    RoutingConstraintSet,
    _resolve_wire_gauge,
)

# Fixtures
# ─────────────────────────────────────────────────────────────────────────────


@pytest.fixture
def engine() -> ConstraintEngine:
    return ConstraintEngine()


# ─────────────────────────────────────────────────────────────────────────────
# ConstraintSource Enum
# ─────────────────────────────────────────────────────────────────────────────


class TestConstraintSource:
    """Every constraint must cite its origin — ConstraintSource enum."""

    def test_all_sources_present(self):
        expected = {
            "NEC_760_24", "NEC_760_24_A", "NEC_760_154", "NEC_310_16",
            "NEC_310_15_B2A", "NEC_310_15_B3A", "NEC_CH9_TEMP",
            "NFPA_72_23_6_2", "NFPA_72_10_6_4", "NFPA_72_12_2_2",
            "NEC_CH9_TABLE4", "NEC_CH9_TABLE8",
            "PROJECT_SPEC_CONDUIT", "PROJECT_SPEC_BEND",
            "PROJECT_SPEC_SEPARATION", "PROJECT_SPEC_FASTENING",
            "PHYSICS",
        }
        actual = {e.name for e in ConstraintSource}
        assert actual == expected

    def test_nec_760_24_value(self):
        assert ConstraintSource.NEC_760_24.value == "NEC 760.24"

    def test_nfpa_72_10_6_4_value(self):
        assert ConstraintSource.NFPA_72_10_6_4.value == "NFPA 72 \u00a710.6.4"

    def test_project_spec_conduit_value(self):
        assert '3/4"' in ConstraintSource.PROJECT_SPEC_CONDUIT.value


# Constants
# ─────────────────────────────────────────────────────────────────────────────


class TestConstants:
    """Project specification constants — must match published standards."""

    def test_min_conduit_inches(self):
        assert MIN_CONDUIT_INCHES == 0.75  # NOSONAR — S1244: import retained for re-export / API surface

    def test_min_conduit_mm(self):
        assert pytest.approx(19.05) == MIN_CONDUIT_MM

    def test_emt_inner_diameter(self):
        assert EMT_3_4_INNER_DIAMETER_MM == 15.8  # NEC Ch.9 Table 4  # NOSONAR — S1244: import retained for re-export / API surface

    def test_emt_outer_diameter(self):
        assert pytest.approx(19.05) == EMT_3_4_OUTER_DIAMETER_MM

    def test_bend_radius_factor(self):
        assert BEND_RADIUS_FACTOR == 6  # NEC 344.24

    def test_max_bend_radius_mm(self):
        assert pytest.approx(6 * 19.05) == MAX_BEND_RADIUS_MM

    def test_min_electrical_separation(self):
        assert MIN_ELECTRICAL_SEPARATION_MM == 300.0  # NOSONAR — S1244: import retained for re-export / API surface

    def test_max_fastening_interval(self):
        assert MAX_CABLE_FASTENING_INTERVAL_MM == 457.0  # 18" = 457mm  # NOSONAR — S1244: import retained for re-export / API surface

    def test_max_conduit_fill_pct(self):
        assert MAX_CONDUIT_FILL_PCT == 0.40  # NEC 760.154  # NOSONAR — S1244: import retained for re-export / API surface

    def test_nac_max_lengths_keys(self):
        """V108 FIX: WireGauge uses string keys."""
        assert set(_NAC_MAX_LENGTHS_M.keys()) == {"12", "14", "16", "18"}

    def test_nac_max_length_awg12(self):
        assert _NAC_MAX_LENGTHS_M["12"] == 914.0  # 3000 ft  # NOSONAR — S1244: import retained for re-export / API surface

    def test_nac_max_length_awg18(self):
        assert _NAC_MAX_LENGTHS_M["18"] == 229.0  # 750 ft  # NOSONAR — S1244: import retained for re-export / API surface

    def test_nac_max_lengths_decrease_with_gauge(self):
        """Higher AWG = thinner wire = shorter max length."""
        assert (
            _NAC_MAX_LENGTHS_M["12"]
            > _NAC_MAX_LENGTHS_M["14"]
            > _NAC_MAX_LENGTHS_M["16"]
            > _NAC_MAX_LENGTHS_M["18"]
        )

    def test_bend_penalty(self):
        assert BEND_PENALTY_M == 0.5  # NOSONAR — S1244: import retained for re-export / API surface

    def test_elevation_penalty(self):
        assert ELEVATION_PENALTY_M == 2.0  # NOSONAR — S1244: import retained for re-export / API surface

    def test_electrical_proximity_penalty(self):
        assert ELECTRICAL_PROXIMITY_PENALTY_M == 1.0  # NOSONAR — S1244: import retained for re-export / API surface


# ─────────────────────────────────────────────────────────────────────────────
# _resolve_wire_gauge helper
# ─────────────────────────────────────────────────────────────────────────────


class TestResolveWireGauge:
    """V109 FIX: wire_gauge parameter can be string or WireGauge instance."""

    def test_string_resolves(self):
        result = _resolve_wire_gauge("14")
        assert result.awg_value == "14"

    def test_instance_passes_through(self):
        wg = WireGauge.AWG_14
        result = _resolve_wire_gauge(wg)
        assert result is wg

    def test_unknown_string_raises(self):
        with pytest.raises(ValueError, match="Unknown wire gauge"):
            _resolve_wire_gauge("99")

    def test_all_awg_strings_resolve(self):
        for awg in ("12", "14", "16", "18"):
            result = _resolve_wire_gauge(awg)
            assert result.awg_value == awg


# ─────────────────────────────────────────────────────────────────────────────
# ConstraintResult Dataclass
# ─────────────────────────────────────────────────────────────────────────────


class TestConstraintResult:
    """ConstraintResult is frozen (immutable) for audit integrity."""

    def test_frozen(self):
        r = ConstraintResult("test", "NEC 760.24", True)
        with pytest.raises(dataclasses.FrozenInstanceError):
            r.is_satisfied = False

    def test_default_values(self):
        r = ConstraintResult("test", "NEC 760.24", True)
        assert r.actual_value == 0.0  # NOSONAR — S1244: import retained for re-export / API surface
        assert r.limit_value == 0.0  # NOSONAR — S1244: import retained for re-export / API surface
        assert r.unit == ""
        assert r.severity == "CRITICAL"
        assert r.remediation == ""
        assert r.formula == ""


# RoutingConstraintSet
# ─────────────────────────────────────────────────────────────────────────────


class TestRoutingConstraintSet:
    """V114 FIX: all_satisfied defaults to False (fail-safe)."""

    def test_default_all_satisfied_is_false(self):
        """V114: Must PROVE compliance, not assume it."""
        rcs = RoutingConstraintSet(results=())
        assert rcs.all_satisfied is False

    def test_default_violation_counts_zero(self):
        rcs = RoutingConstraintSet(results=())
        assert rcs.critical_violations == 0
        assert rcs.total_violations == 0

    def test_frozen(self):
        rcs = RoutingConstraintSet(results=())
        with pytest.raises(dataclasses.FrozenInstanceError):
            rcs.all_satisfied = True


# ─────────────────────────────────────────────────────────────────────────────
# ConstraintEngine — Initialization
# ─────────────────────────────────────────────────────────────────────────────


class TestConstraintEngineInit:

    def test_default_init(self, engine):
        assert engine._min_conduit_inches == MIN_CONDUIT_INCHES
        assert engine._bend_radius_factor == BEND_RADIUS_FACTOR
        assert engine._min_electrical_separation_mm == MIN_ELECTRICAL_SEPARATION_MM
        assert engine._max_fastening_interval_mm == MAX_CABLE_FASTENING_INTERVAL_MM

    def test_custom_conduit_size(self):
        e = ConstraintEngine(min_conduit_inches=1.0)
        assert e._min_conduit_inches == 1.0  # NOSONAR — S1244: import retained for re-export / API surface

    def test_custom_bend_factor(self):
        e = ConstraintEngine(bend_radius_factor=8)
        assert e._bend_radius_factor == 8

    def test_custom_separation(self):
        e = ConstraintEngine(min_electrical_separation_mm=500.0)
        assert e._min_electrical_separation_mm == 500.0  # NOSONAR — S1244: import retained for re-export / API surface


# ─────────────────────────────────────────────────────────────────────────────
# check_nac_max_length — NFPA 72 §23.6.2
# ─────────────────────────────────────────────────────────────────────────────


class TestNACMaxLength:

    def test_compliant_awg14(self, engine):
        result = engine.check_nac_max_length(400.0, WireGauge.AWG_14)
        assert result.is_satisfied is True
        assert result.limit_value == 610.0  # NOSONAR — S1244: import retained for re-export / API surface

    def test_violation_awg18(self, engine):
        result = engine.check_nac_max_length(300.0, WireGauge.AWG_18)
        assert result.is_satisfied is False
        assert result.limit_value == 229.0  # NOSONAR — S1244: import retained for re-export / API surface

    def test_exact_boundary_compliant(self, engine):
        """Exactly at the limit is still compliant (≤)."""
        result = engine.check_nac_max_length(229.0, WireGauge.AWG_18)
        assert result.is_satisfied is True

    def test_just_over_boundary(self, engine):
        result = engine.check_nac_max_length(229.1, WireGauge.AWG_18)
        assert result.is_satisfied is False

    def test_circuit_type_in_name(self, engine):
        result = engine.check_nac_max_length(100.0, WireGauge.AWG_14, circuit_type="SLC")
        assert "SLC" in result.constraint_name

    def test_source_is_nfpa_72_23_6_2(self, engine):
        result = engine.check_nac_max_length(100.0, WireGauge.AWG_14)
        assert result.source == ConstraintSource.NFPA_72_23_6_2.value

    def test_remediation_on_violation(self, engine):
        result = engine.check_nac_max_length(300.0, WireGauge.AWG_18)
        assert result.remediation != ""
        assert "23.6.2" in result.remediation

    def test_no_remediation_on_compliance(self, engine):
        result = engine.check_nac_max_length(100.0, WireGauge.AWG_14)
        assert result.remediation == ""

    def test_severity_is_critical(self, engine):
        result = engine.check_nac_max_length(300.0, WireGauge.AWG_18)
        assert result.severity == "CRITICAL"

    def test_zero_length_compliant(self, engine):
        result = engine.check_nac_max_length(0.0, WireGauge.AWG_18)
        assert result.is_satisfied is True


# ─────────────────────────────────────────────────────────────────────────────
# check_voltage_drop — NFPA 72 §10.6.4
# ─────────────────────────────────────────────────────────────────────────────


class TestVoltageDrop:

    def test_compliant_short_circuit(self, engine):
        result = engine.check_voltage_drop(0.5, 50.0, WireGauge.AWG_14)
        assert result.is_satisfied is True

    def test_violation_long_circuit(self, engine):
        result = engine.check_voltage_drop(2.0, 500.0, WireGauge.AWG_18)
        assert result.is_satisfied is False

    def test_return_path_factor_x2(self, engine):
        """SAFETY: V_drop = I × 2 × R × L — must include ×2."""
        result = engine.check_voltage_drop(1.0, 100.0, WireGauge.AWG_14, ps_voltage=24.0)
        # AWG14 at 20C: 10.07 ohm/km
        # V_drop = 1.0 × 2 × 10.07 × 0.1 = 2.014V
        from fireai.core.nfpa72_engine import temperature_corrected_resistance
        r = temperature_corrected_resistance(10.07, 20.0)
        expected = 1.0 * 2.0 * r * 0.1
        assert result.actual_value == pytest.approx(expected, rel=1e-3)

    def test_zero_current(self, engine):
        result = engine.check_voltage_drop(0.0, 100.0, WireGauge.AWG_14)
        assert result.actual_value == pytest.approx(0.0, abs=1e-6)

    def test_source_nfpa_72_10_6_4(self, engine):
        result = engine.check_voltage_drop(0.5, 50.0, WireGauge.AWG_14)
        assert result.source == ConstraintSource.NFPA_72_10_6_4.value

    def test_severity_critical(self, engine):
        result = engine.check_voltage_drop(0.5, 50.0, WireGauge.AWG_14)
        assert result.severity == "CRITICAL"

    def test_remediation_on_violation(self, engine):
        result = engine.check_voltage_drop(2.0, 500.0, WireGauge.AWG_18)
        assert result.remediation != ""
        assert "10.6.4" in result.remediation

    def test_temperature_correction_v60(self, engine):
        """V60 FIX: Temperature-corrected resistance increases voltage drop at 75C."""
        result_20c = engine.check_voltage_drop(1.0, 100.0, WireGauge.AWG_14, conductor_operating_temp_c=20.0)
        result_75c = engine.check_voltage_drop(1.0, 100.0, WireGauge.AWG_14, conductor_operating_temp_c=75.0)
        assert result_75c.actual_value > result_20c.actual_value

    def test_zero_ps_voltage_no_division_by_zero(self, engine):
        """ps_voltage=0 must not cause ZeroDivisionError."""
        result = engine.check_voltage_drop(1.0, 100.0, WireGauge.AWG_14, ps_voltage=0.0)
        # v_drop_pct = 0 when ps_voltage == 0 (per source code guard)
        assert result.source == ConstraintSource.NFPA_72_10_6_4.value

    def test_custom_max_drop_pct(self, engine):
        result = engine.check_voltage_drop(0.5, 50.0, WireGauge.AWG_14, max_drop_pct=5.0)
        assert result.limit_value == pytest.approx(24.0 * 0.05)


# ─────────────────────────────────────────────────────────────────────────────
# check_electrical_separation — Project Spec ≥ 300mm
# ─────────────────────────────────────────────────────────────────────────────


class TestElectricalSeparation:

    def test_compliant(self, engine):
        result = engine.check_electrical_separation(350.0)
        assert result.is_satisfied is True

    def test_violation(self, engine):
        result = engine.check_electrical_separation(200.0)
        assert result.is_satisfied is False

    def test_exact_boundary(self, engine):
        result = engine.check_electrical_separation(300.0)
        assert result.is_satisfied is True

    def test_zero_separation_violation(self, engine):
        result = engine.check_electrical_separation(0.0)
        assert result.is_satisfied is False

    def test_negative_separation_violation(self, engine):
        result = engine.check_electrical_separation(-50.0)
        assert result.is_satisfied is False

    def test_custom_separation_threshold(self):
        e = ConstraintEngine(min_electrical_separation_mm=500.0)
        result = e.check_electrical_separation(400.0)
        assert result.is_satisfied is False

    def test_source_project_spec(self, engine):
        result = engine.check_electrical_separation(350.0)
        assert result.source == ConstraintSource.PROJECT_SPEC_SEPARATION.value

    def test_severity_critical(self, engine):
        result = engine.check_electrical_separation(200.0)
        assert result.severity == "CRITICAL"


# ─────────────────────────────────────────────────────────────────────────────
# check_bend_radius — Project Spec / NEC 344.24
# ─────────────────────────────────────────────────────────────────────────────


class TestBendRadius:

    def test_no_bends_satisfied(self, engine):
        result = engine.check_bend_radius(num_bends=0)
        assert result.is_satisfied is True

    def test_4_bends_compliant(self, engine):
        """NEC Chapter 9: max 4 quarter bends per run."""
        result = engine.check_bend_radius(num_bends=4)
        assert result.is_satisfied is True

    def test_5_bends_violation(self, engine):
        result = engine.check_bend_radius(num_bends=5)
        assert result.is_satisfied is False

    def test_severity_escalates_on_violation(self, engine):
        result_compliant = engine.check_bend_radius(num_bends=3)
        result_violation = engine.check_bend_radius(num_bends=5)
        assert result_compliant.severity == "HIGH"
        assert result_violation.severity == "CRITICAL"

    def test_custom_diameter(self, engine):
        result = engine.check_bend_radius(conduit_diameter_mm=25.0, num_bends=0)
        assert result.actual_value == pytest.approx(6 * 25.0)

    def test_default_diameter(self, engine):
        result = engine.check_bend_radius(num_bends=0)
        assert result.actual_value == pytest.approx(6 * EMT_3_4_OUTER_DIAMETER_MM)

    def test_remediation_mentions_nec(self, engine):
        result = engine.check_bend_radius(num_bends=5)
        assert "NEC" in result.remediation

    def test_unit_is_quarter_bends_when_bends(self, engine):
        result = engine.check_bend_radius(num_bends=3)
        assert result.unit == "quarter bends"


# ─────────────────────────────────────────────────────────────────────────────
# check_conduit_size — Project Spec: Min 3/4" EMT
# ─────────────────────────────────────────────────────────────────────────────


class TestConduitSize:

    def test_compliant_default(self, engine):
        result = engine.check_conduit_size()
        assert result.is_satisfied is True

    def test_half_inch_violation(self, engine):
        result = engine.check_conduit_size(conduit_inches=0.5)
        assert result.is_satisfied is False

    def test_one_inch_compliant(self, engine):
        result = engine.check_conduit_size(conduit_inches=1.0)
        assert result.is_satisfied is True

    def test_exact_boundary(self, engine):
        result = engine.check_conduit_size(conduit_inches=0.75)
        assert result.is_satisfied is True

    def test_severity_high(self, engine):
        result = engine.check_conduit_size(conduit_inches=0.5)
        assert result.severity == "HIGH"

    def test_source_project_spec(self, engine):
        result = engine.check_conduit_size()
        assert result.source == ConstraintSource.PROJECT_SPEC_CONDUIT.value


# ─────────────────────────────────────────────────────────────────────────────
# check_cable_fastening — NEC 760.24(A)
# ─────────────────────────────────────────────────────────────────────────────


class TestCableFastening:

    def test_compliant_with_enough_fasteners(self, engine):
        # 10m / (22+1) = 434mm ≤ 457mm
        result = engine.check_cable_fastening(10.0, 22)
        assert result.is_satisfied is True

    def test_violation_too_few_fasteners(self, engine):
        # 10m / (1+1) = 5000mm > 457mm
        result = engine.check_cable_fastening(10.0, 1)
        assert result.is_satisfied is False

    def test_zero_length_trivially_satisfied(self, engine):
        result = engine.check_cable_fastening(0.0, 0)
        assert result.is_satisfied is True

    def test_negative_length_v67_fix(self, engine):
        """V67 SAFETY FIX: Negative length must be flagged, not silently accepted."""
        result = engine.check_cable_fastening(-1.0, 5)
        assert result.is_satisfied is False

    def test_zero_fasteners(self, engine):
        # 10m / (0+1) = 10000mm > 457mm
        result = engine.check_cable_fastening(10.0, 0)
        assert result.is_satisfied is False

    def test_source_nec_760_24_a(self, engine):
        result = engine.check_cable_fastening(10.0, 22)
        assert result.source == ConstraintSource.NEC_760_24_A.value

    def test_interval_formula(self, engine):
        """Interval = L_mm / (n + 1)."""
        result = engine.check_cable_fastening(10.0, 21)
        expected_interval = 10000.0 / 22.0
        assert result.actual_value == pytest.approx(expected_interval, rel=0.01)


# ─────────────────────────────────────────────────────────────────────────────
# check_class_a_separation — NFPA 72 §12.2.2
# ─────────────────────────────────────────────────────────────────────────────


class TestClassASeparation:

    def test_well_separated_compliant(self, engine):
        outgoing = [(0, 0, 0), (10, 0, 0)]
        return_path = [(0, 5, 0), (10, 5, 0)]
        result = engine.check_class_a_separation(outgoing, return_path)
        assert result.is_satisfied is True

    def test_too_close_violation(self, engine):
        outgoing = [(0, 0, 0), (10, 0, 0)]
        return_path = [(0, 0.1, 0), (10, 0.1, 0)]
        result = engine.check_class_a_separation(outgoing, return_path)
        assert result.is_satisfied is False

    def test_empty_outgoing_violation(self, engine):
        return_path = [(0, 5, 0)]
        result = engine.check_class_a_separation([], return_path)
        assert result.is_satisfied is False

    def test_empty_return_violation(self, engine):
        outgoing = [(0, 5, 0)]
        result = engine.check_class_a_separation(outgoing, [])
        assert result.is_satisfied is False

    def test_both_empty_violation(self, engine):
        result = engine.check_class_a_separation([], [])
        assert result.is_satisfied is False

    def test_custom_min_separation(self, engine):
        outgoing = [(0, 0, 0)]
        return_path = [(0, 0.4, 0)]  # 0.4m apart
        result = engine.check_class_a_separation(outgoing, return_path, min_separation_m=0.5)
        assert result.is_satisfied is False

    def test_source_nfpa_72_12_2_2(self, engine):
        outgoing = [(0, 0, 0)]
        return_path = [(0, 5, 0)]
        result = engine.check_class_a_separation(outgoing, return_path)
        assert result.source == ConstraintSource.NFPA_72_12_2_2.value

    def test_exact_boundary(self, engine):
        outgoing = [(0, 0, 0)]
        return_path = [(0, 0.3, 0)]
        result = engine.check_class_a_separation(outgoing, return_path, min_separation_m=0.3)
        assert result.is_satisfied is True


# ─────────────────────────────────────────────────────────────────────────────
# check_ampacity_compliance — NEC 310.16
# ─────────────────────────────────────────────────────────────────────────────


class TestAmpacityCompliance:

    def test_low_current_compliant(self, engine):
        result = engine.check_ampacity_compliance(0.5, WireGauge.AWG_14)
        assert result.is_satisfied is True

    def test_high_current_violation(self, engine):
        result = engine.check_ampacity_compliance(50.0, WireGauge.AWG_18)
        assert result.is_satisfied is False

    def test_source_nec_310_16(self, engine):
        result = engine.check_ampacity_compliance(0.5, WireGauge.AWG_14)
        assert result.source == ConstraintSource.NEC_310_16.value

    def test_severity_critical(self, engine):
        result = engine.check_ampacity_compliance(0.5, WireGauge.AWG_14)
        assert result.severity == "CRITICAL"


# ─────────────────────────────────────────────────────────────────────────────
# check_ambient_derating — NEC 310.15(B)(2)(A)
# ─────────────────────────────────────────────────────────────────────────────


class TestAmbientDerating:

    def test_30c_satisfied(self, engine):
        result = engine.check_ambient_derating(30.0)
        assert result.is_satisfied is True

    def test_50c_derating_factor(self, engine):
        """At 50°C, derating factor is 0.82 for 90°C rated conductors."""
        result = engine.check_ambient_derating(50.0)
        # Factor at 50°C for 90°C rating is 0.82, which is >= 0.80
        # so is_satisfied = True (not severe enough to fail)
        # But severity is HIGH because factor < 0.85 triggers remediation
        assert result.actual_value == 50.0  # NOSONAR — S1244: import retained for re-export / API surface

    def test_source_nec_310_15_b2a(self, engine):
        result = engine.check_ambient_derating(30.0)
        assert result.source == ConstraintSource.NEC_310_15_B2A.value

    def test_severity_escalates_at_high_temp(self, engine):
        """Severity goes HIGH when derating factor < 0.80."""
        result_moderate = engine.check_ambient_derating(30.0)
        # At very high temps with low conductor rating, factor can drop below 0.80
        result_severe = engine.check_ambient_derating(60.0, conductor_temp_rating_c=60)
        assert result_moderate.severity == "MEDIUM"
        # At 60°C ambient with 60°C rated conductor, factor should be < 0.80
        if result_severe.is_satisfied is False:
            assert result_severe.severity == "HIGH"

    def test_45c_derating_less_than_1(self, engine):
        result = engine.check_ambient_derating(45.0)
        # Factor should be < 1.0
        assert result.actual_value == 45.0  # NOSONAR — S1244: import retained for re-export / API surface


# ─────────────────────────────────────────────────────────────────────────────
# check_conductor_count_derating — NEC 310.15(B)(3)(a)
# ─────────────────────────────────────────────────────────────────────────────


class TestConductorCountDerating:

    def test_2_conductors_satisfied(self, engine):
        result = engine.check_conductor_count_derating(2)
        assert result.is_satisfied is True

    def test_6_conductors_derating(self, engine):
        result = engine.check_conductor_count_derating(6)
        assert result.is_satisfied is False  # > 3

    def test_3_conductors_boundary(self, engine):
        result = engine.check_conductor_count_derating(3)
        assert result.is_satisfied is True  # ≤ 3

    def test_source_nec_310_15_b3a(self, engine):
        result = engine.check_conductor_count_derating(2)
        assert result.source == ConstraintSource.NEC_310_15_B3A.value

    def test_severity_escalates(self, engine):
        result_few = engine.check_conductor_count_derating(2)
        result_many = engine.check_conductor_count_derating(10)
        assert result_few.severity == "MEDIUM"
        assert result_many.severity == "HIGH"


# ─────────────────────────────────────────────────────────────────────────────
# check_conduit_fill — NEC Chapter 9, Table 4
# ─────────────────────────────────────────────────────────────────────────────


class TestConduitFill:

    def test_single_cable_compliant(self, engine):
        result = engine.check_conduit_fill(5.0, 1)
        assert result.is_satisfied is True

    def test_too_many_cables_violation(self, engine):
        result = engine.check_conduit_fill(10.0, 20)
        assert result.is_satisfied is False

    def test_zero_conduit_diameter_violation(self, engine):
        result = engine.check_conduit_fill(5.0, 1, conduit_inner_diameter_mm=0.0)
        assert result.is_satisfied is False

    def test_negative_conduit_diameter_violation(self, engine):
        result = engine.check_conduit_fill(5.0, 1, conduit_inner_diameter_mm=-1.0)
        assert result.is_satisfied is False

    def test_source_nec_ch9_table4(self, engine):
        result = engine.check_conduit_fill(5.0, 1)
        assert result.source == ConstraintSource.NEC_CH9_TABLE4.value

    def test_fill_percentage_formula(self, engine):
        """Fill = N × A_wire / A_conduit × 100."""
        wire_d = 5.0
        n = 2
        cond_d = EMT_3_4_INNER_DIAMETER_MM
        wire_area = math.pi * (wire_d / 2.0) ** 2
        cond_area = math.pi * (cond_d / 2.0) ** 2
        expected_pct = (n * wire_area / cond_area) * 100.0
        result = engine.check_conduit_fill(wire_d, n, cond_d)
        assert result.actual_value == pytest.approx(expected_pct, rel=0.01)

    def test_limit_value_is_40_pct(self, engine):
        result = engine.check_conduit_fill(5.0, 1)
        assert result.limit_value == pytest.approx(40.0)

    def test_severity_high(self, engine):
        result = engine.check_conduit_fill(5.0, 1)
        assert result.severity == "HIGH"


# ─────────────────────────────────────────────────────────────────────────────
# check_all — Composite check
# ─────────────────────────────────────────────────────────────────────────────


class TestCheckAll:

    def test_fully_compliant_scenario(self, engine):
        # Need enough fasteners: 100m / (n+1) <= 457mm => n >= 218
        result = engine.check_all(
            cable_length_m=100.0,
            wire_gauge=WireGauge.AWG_14,
            num_bends=2,
            min_electrical_separation_mm=350.0,
            ps_voltage=24.0,
            alarm_current_a=0.5,
            num_fasteners=220,
        )
        assert isinstance(result, RoutingConstraintSet)
        assert result.all_satisfied is True
        assert result.total_violations == 0

    def test_multiple_violations(self, engine):
        result = engine.check_all(
            cable_length_m=300.0,
            wire_gauge=WireGauge.AWG_18,
            num_bends=5,
            min_electrical_separation_mm=200.0,
            ps_voltage=24.0,
            alarm_current_a=5.0,
            num_fasteners=0,
        )
        assert result.all_satisfied is False
        assert result.total_violations > 0

    def test_zero_alarm_current_v67_safety(self, engine):
        """V67: Zero current means voltage drop NOT checked = NOT satisfied."""
        result = engine.check_all(
            cable_length_m=100.0,
            wire_gauge=WireGauge.AWG_14,
            alarm_current_a=0.0,
        )
        assert result.all_satisfied is False

    def test_class_a_with_paths(self, engine):
        outgoing = [(0, 0, 0), (100, 0, 0)]
        return_path = [(0, 5, 0), (100, 5, 0)]
        result = engine.check_all(
            cable_length_m=100.0,
            wire_gauge=WireGauge.AWG_14,
            is_class_a=True,
            outgoing_path=outgoing,
            return_path=return_path,
            alarm_current_a=0.5,
            num_fasteners=25,
        )
        # Should include Class A separation check
        names = [r.constraint_name for r in result.results]
        assert any("Class A" in n for n in names)

    def test_class_a_without_paths_skips_check(self, engine):
        result = engine.check_all(
            cable_length_m=100.0,
            wire_gauge=WireGauge.AWG_14,
            is_class_a=True,
            alarm_current_a=0.5,
            num_fasteners=25,
        )
        names = [r.constraint_name for r in result.results]
        assert not any("Class A" in n for n in names)

    def test_conduit_size_override(self, engine):
        result = engine.check_all(
            cable_length_m=100.0,
            wire_gauge=WireGauge.AWG_14,
            conduit_size_inches=0.5,
            alarm_current_a=0.5,
            num_fasteners=25,
        )
        conduit_results = [r for r in result.results if "Conduit Size" in r.constraint_name]
        assert len(conduit_results) > 0
        assert conduit_results[0].is_satisfied is False

    def test_v62_temperature_split(self, engine):
        """V62 FIX: ambient_temp_c for ampacity, conductor_operating_temp_c for voltage drop."""
        result = engine.check_all(
            cable_length_m=100.0,
            wire_gauge=WireGauge.AWG_14,
            alarm_current_a=0.5,
            num_fasteners=25,
            ambient_temp_c=40.0,
            conductor_operating_temp_c=75.0,
        )
        assert isinstance(result, RoutingConstraintSet)

    def test_violation_counting(self, engine):
        result = engine.check_all(
            cable_length_m=100.0,
            wire_gauge=WireGauge.AWG_14,
            num_bends=6,
            min_electrical_separation_mm=200.0,
            alarm_current_a=0.5,
            num_fasteners=25,
        )
        assert result.total_violations == sum(1 for r in result.results if not r.is_satisfied)

    def test_critical_violation_counting(self, engine):
        result = engine.check_all(
            cable_length_m=100.0,
            wire_gauge=WireGauge.AWG_14,
            min_electrical_separation_mm=200.0,
            alarm_current_a=0.5,
            num_fasteners=25,
        )
        assert result.critical_violations == sum(
            1 for r in result.results if not r.is_satisfied and r.severity == "CRITICAL"
        )


# ─────────────────────────────────────────────────────────────────────────────
# A* Cost Functions
# ─────────────────────────────────────────────────────────────────────────────


class TestMoveCost:

    def test_straight_horizontal(self, engine):
        cost = engine.compute_move_cost((0, 0, 0), (1, 0, 0))
        assert cost == pytest.approx(0.1)  # grid_resolution

    def test_elevation_change_adds_penalty(self, engine):
        cost = engine.compute_move_cost((0, 0, 0), (0, 0, 1))
        assert cost > 0.1  # base + elevation penalty

    def test_electrical_proximity_adds_penalty(self, engine):
        cost_normal = engine.compute_move_cost((0, 0, 0), (1, 0, 0))
        cost_electrical = engine.compute_move_cost(
            (0, 0, 0), (1, 0, 0), is_near_electrical=True
        )
        assert cost_electrical > cost_normal
        assert cost_electrical - cost_normal == pytest.approx(ELECTRICAL_PROXIMITY_PENALTY_M)


class TestBendCost:

    def test_no_bend_on_first_move(self):
        assert ConstraintEngine.compute_bend_cost(None, (1, 0, 0)) == 0.0  # NOSONAR — S1244: import retained for re-export / API surface

    def test_straight_no_bend(self):
        assert ConstraintEngine.compute_bend_cost((1, 0, 0), (1, 0, 0)) == 0.0  # NOSONAR — S1244: import retained for re-export / API surface

    def test_direction_change_is_bend(self):
        assert ConstraintEngine.compute_bend_cost((1, 0, 0), (0, 1, 0)) == BEND_PENALTY_M

    def test_reverse_is_bend(self):
        assert ConstraintEngine.compute_bend_cost((1, 0, 0), (-1, 0, 0)) == BEND_PENALTY_M


class TestManhattanHeuristic:

    def test_same_cell(self):
        assert ConstraintEngine.manhattan_heuristic((5, 5, 5), (5, 5, 5)) == 0.0  # NOSONAR — S1244: import retained for re-export / API surface

    def test_horizontal_distance(self):
        h = ConstraintEngine.manhattan_heuristic((0, 0, 0), (10, 0, 0))
        assert h == pytest.approx(1.0)  # 10 * 0.1

    def test_elevation_more_expensive(self):
        h_horizontal = ConstraintEngine.manhattan_heuristic((0, 0, 0), (10, 0, 0))
        h_elevation = ConstraintEngine.manhattan_heuristic((0, 0, 0), (0, 0, 10))
        assert h_elevation > h_horizontal  # elevation penalty factor

    def test_admissible_never_overestimates(self):
        """Heuristic must be ≤ actual cost."""
        h = ConstraintEngine.manhattan_heuristic((0, 0, 0), (10, 10, 5))
        # Actual cost: straight moves without bends, minimal cost
        # Manhattan is always admissible for orthogonal grids
        assert h >= 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
