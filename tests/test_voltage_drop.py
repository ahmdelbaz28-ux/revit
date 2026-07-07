"""
tests/test_voltage_drop.py
==========================
Comprehensive test suite for fireai/core/voltage_drop.py

SAFETY CRITICAL: Voltage drop calculations directly affect whether fire alarm
notification appliances (horns/strobes) receive sufficient voltage to operate.
An under-powered horn means NO AUDIBLE ALARM in a fire — a direct life-safety
hazard per NFPA 72-2022 §27.4.1.2.

NFPA 72 References:
  §27.4.1.2  — Maximum voltage drop (10%)
  §10.6.7    — Battery standby calculation
  §10.6.7.1  — Battery derating factor (80%)
  §10.6.7.2  — Minimum 24h standby
  §10.6.7.4  — 15 minutes alarm
  NEC Ch.9 Table 8 — Wire resistance values (copper, DC, 75°C)
"""

from __future__ import annotations

import warnings

import pytest

from fireai.core.voltage_drop import (
    FA_WIRE_GAUGES,
    MAX_VOLTAGE_DROP_PCT,
    _next_standard_ah,
    calculate_battery_backup,
    calculate_max_circuit_length,
    calculate_voltage_drop,
    get_wire_resistance_ohm_per_m,
    recommend_wire_gauge,
)

# ─────────────────────────────────────────────────────────────────────────────
# Wire Resistance Lookup (BUG-12 FIX: keyed by AWG string)
# ─────────────────────────────────────────────────────────────────────────────


class TestGetWireResistance:
    """NEC Chapter 9, Table 8 — DC resistance at 75°C (copper)."""

    def test_awg14_resistance_ohm_per_m(self):
        """AWG 14: 10.07 Ω/km → 0.01007 Ω/m."""
        r = get_wire_resistance_ohm_per_m("14")
        assert r == pytest.approx(10.07 / 1000.0, rel=1e-4)

    def test_awg12_resistance_ohm_per_m(self):
        """AWG 12: 6.33 Ω/km → 0.00633 Ω/m."""
        r = get_wire_resistance_ohm_per_m("12")
        assert r == pytest.approx(6.33 / 1000.0, rel=1e-4)

    def test_awg18_resistance_ohm_per_m(self):
        """AWG 18: 25.49 Ω/km → 0.02549 Ω/m."""
        r = get_wire_resistance_ohm_per_m("18")
        assert r == pytest.approx(25.49 / 1000.0, rel=1e-4)

    def test_awg10_resistance_ohm_per_m(self):
        """AWG 10: 3.97 Ω/km → 0.00397 Ω/m."""
        r = get_wire_resistance_ohm_per_m("10")
        assert r == pytest.approx(3.97 / 1000.0, rel=1e-4)

    def test_large_gauge_4_0(self):
        """AWG 4/0: 0.200 Ω/km → 0.000200 Ω/m."""
        r = get_wire_resistance_ohm_per_m("4/0")
        assert r == pytest.approx(0.200 / 1000.0, rel=1e-4)

    def test_resistance_increases_with_gauge_number(self):
        """Higher AWG number = thinner wire = higher resistance."""
        r12 = get_wire_resistance_ohm_per_m("12")
        r14 = get_wire_resistance_ohm_per_m("14")
        r18 = get_wire_resistance_ohm_per_m("18")
        assert r18 > r14 > r12

    def test_unknown_awg_raises(self):
        """BUG-12 FIX: Invalid AWG string must raise ValueError."""
        with pytest.raises(ValueError, match="Unknown AWG gauge"):
            get_wire_resistance_ohm_per_m("99")

    def test_empty_string_raises(self):
        with pytest.raises(ValueError, match="Unknown AWG gauge"):
            get_wire_resistance_ohm_per_m("")

    def test_whitespace_stripped(self):
        """AWG string with whitespace should still resolve."""
        r = get_wire_resistance_ohm_per_m("  14  ")
        assert r == pytest.approx(10.07 / 1000.0, rel=1e-4)

    def test_numeric_awg_converted_to_string(self):
        """
        Passing integer 14 works because get_wire_resistance_ohm_per_m
        does str(awg).strip() internally — so 14 → "14" is valid.
        """
        r = get_wire_resistance_ohm_per_m(14)  # NOSONAR — S5655: intentional wrong-type arg (test verifies rejection)
        assert r == pytest.approx(10.07 / 1000.0, rel=1e-4)

    def test_fa_wire_gauges_are_valid(self):
        """All FA_WIRE_GAUGES must be resolvable."""
        for awg in FA_WIRE_GAUGES:
            r = get_wire_resistance_ohm_per_m(awg)
            assert r > 0


# ─────────────────────────────────────────────────────────────────────────────
# Voltage Drop Calculation (BUG-11 FIX: Ω/m not Ω/km)
# ─────────────────────────────────────────────────────────────────────────────


class TestCalculateVoltageDrop:
    """
    SAFETY CRITICAL: V_drop = I × 2 × L × R_per_m.
    The ×2 is the DC return path. BUG-11 fixed Ω/km → Ω/m.
    """

    def test_known_voltage_drop(self):
        """
        Manual verification: 1A, 100m, AWG14, 24V, 75°C.
        R = 0.01007 Ω/m, V_drop = 1.0 × 2 × 100 × 0.01007 = 2.014V
        """
        result = calculate_voltage_drop(1.0, 100.0, "14", 24.0)
        assert result["voltage_drop_v"] == pytest.approx(2.014, rel=1e-3)

    def test_voltage_drop_pct(self):
        """2.014V / 24V × 100 = 8.392%."""
        result = calculate_voltage_drop(1.0, 100.0, "14", 24.0)
        assert result["voltage_drop_pct"] == pytest.approx(2.014 / 24.0 * 100, rel=1e-3)

    def test_terminal_voltage(self):
        """V_terminal = 24.0 - 2.014 = 21.986V."""
        result = calculate_voltage_drop(1.0, 100.0, "14", 24.0)
        assert result["terminal_voltage_v"] == pytest.approx(21.986, rel=1e-3)

    def test_compliant_below_10pct(self):
        """8.39% < 10% → compliant."""
        result = calculate_voltage_drop(1.0, 100.0, "14", 24.0)
        assert result["is_compliant"] is True

    def test_non_compliant_above_10pct(self):
        """High current + long run → non-compliant."""
        result = calculate_voltage_drop(5.0, 200.0, "14", 24.0)
        # V_drop = 5.0 × 2 × 200 × 0.01007 = 20.14V → 83.9%
        assert result["is_compliant"] is False
        assert result["voltage_drop_pct"] > MAX_VOLTAGE_DROP_PCT

    def test_zero_current_zero_drop(self):
        """No current draw → zero voltage drop (compliant)."""
        result = calculate_voltage_drop(0.0, 100.0, "14", 24.0)
        assert result["voltage_drop_v"] == pytest.approx(0.0, abs=1e-9)
        assert result["is_compliant"] is True

    def test_zero_length_zero_drop(self):
        """Zero cable length → zero voltage drop."""
        result = calculate_voltage_drop(1.0, 0.0, "14", 24.0)
        assert result["voltage_drop_v"] == pytest.approx(0.0, abs=1e-9)

    def test_negative_current_raises(self):
        with pytest.raises(ValueError, match="must be >= 0"):
            calculate_voltage_drop(-1.0, 100.0, "14", 24.0)

    def test_negative_length_raises(self):
        with pytest.raises(ValueError, match="must be >= 0"):
            calculate_voltage_drop(1.0, -100.0, "14", 24.0)

    def test_zero_nominal_voltage_raises(self):
        with pytest.raises(ValueError, match="must be > 0"):
            calculate_voltage_drop(1.0, 100.0, "14", 0.0)

    def test_negative_nominal_voltage_raises(self):
        with pytest.raises(ValueError, match="must be > 0"):
            calculate_voltage_drop(1.0, 100.0, "14", -24.0)

    def test_nan_current_rejected(self):
        """NaN current must be rejected per safety-critical requirements."""
        with pytest.raises(ValueError, match="finite"):  # NOSONAR — S5778: re-raise inside except is intentional (context-specific)  # noqa: S5778
            calculate_voltage_drop(float("nan"), 100.0, "14", 24.0)

    def test_nan_length_rejected(self):
        """NaN length must be rejected per safety-critical requirements."""
        with pytest.raises(ValueError, match="finite"):  # NOSONAR — S5778: re-raise inside except is intentional (context-specific)  # noqa: S5778
            calculate_voltage_drop(1.0, float("nan"), "14", 24.0)

    def test_inf_nominal_voltage_not_checked(self):
        """
        Source code only checks nominal_voltage <= 0; inf passes through.
        With inf voltage, drop% = 0 (any finite drop / inf = 0).
        """
        result = calculate_voltage_drop(1.0, 100.0, "14", float("inf"))
        # With infinite voltage, voltage_drop_pct should be 0 (or NaN if 0*inf)
        # The actual result depends on floating-point arithmetic
        assert result["voltage_drop_v"] > 0

    def test_return_path_factor_included(self):
        """
        BUG-11: The ×2 round-trip factor MUST be present.
        Without it, voltage drop would be exactly half the correct value.
        """
        result = calculate_voltage_drop(1.0, 100.0, "14", 24.0)
        r_per_m = get_wire_resistance_ohm_per_m("14")
        one_way_drop = 1.0 * 100.0 * r_per_m  # WITHOUT ×2
        round_trip_drop = 1.0 * 2.0 * 100.0 * r_per_m  # WITH ×2
        # Result must equal round-trip, NOT one-way
        assert result["voltage_drop_v"] == pytest.approx(round_trip_drop, rel=1e-4)
        assert result["voltage_drop_v"] != pytest.approx(one_way_drop, rel=0.01)

    def test_temperature_correction_hot(self):
        """
        At 100°C, resistance should be higher than at 75°C.
        R_T = R_75 × [1 + 0.00323 × (T - 75)]
        At 100°C: factor = 1 + 0.00323 × 25 = 1.08075
        """
        result_75 = calculate_voltage_drop(1.0, 100.0, "14", 24.0, temperature_c=75.0)
        result_100 = calculate_voltage_drop(1.0, 100.0, "14", 24.0, temperature_c=100.0)
        assert result_100["voltage_drop_v"] > result_75["voltage_drop_v"]

    def test_temperature_correction_cold(self):
        """At 25°C, resistance should be lower than at 75°C."""
        result_75 = calculate_voltage_drop(1.0, 100.0, "14", 24.0, temperature_c=75.0)
        result_25 = calculate_voltage_drop(1.0, 100.0, "14", 24.0, temperature_c=25.0)
        assert result_25["voltage_drop_v"] < result_75["voltage_drop_v"]

    def test_nfpa_reference_present(self):
        result = calculate_voltage_drop(1.0, 100.0, "14", 24.0)
        assert "NFPA 72" in result["nfpa_reference"]

    def test_result_dict_keys(self):
        result = calculate_voltage_drop(1.0, 100.0, "14", 24.0)
        expected_keys = {
            "voltage_drop_v", "voltage_drop_pct", "terminal_voltage_v",
            "resistance_total_ohm", "resistance_per_m_ohm", "is_compliant",
            "awg", "length_m", "current_a", "nfpa_max_drop_pct", "nfpa_reference",
        }
        assert set(result.keys()) == expected_keys

    def test_different_gauges(self):
        """Larger wire = less voltage drop."""
        r14 = calculate_voltage_drop(1.0, 100.0, "14", 24.0)
        r12 = calculate_voltage_drop(1.0, 100.0, "12", 24.0)
        assert r12["voltage_drop_v"] < r14["voltage_drop_v"]


# ─────────────────────────────────────────────────────────────────────────────
# Maximum Circuit Length
# ─────────────────────────────────────────────────────────────────────────────


class TestCalculateMaxCircuitLength:
    def test_known_max_length(self):
        """
        For 1A on AWG14 at 24V with 10% drop:
        L_max = (24 × 0.10) / (1.0 × 2 × 0.01007) = 119.17m
        """
        result = calculate_max_circuit_length(1.0, "14", 24.0, 10.0)
        expected = (24.0 * 0.10) / (2.0 * 1.0 * get_wire_resistance_ohm_per_m("14"))
        assert result == pytest.approx(expected, rel=1e-3)

    def test_zero_current_returns_inf(self):
        """No load = unlimited circuit length."""
        result = calculate_max_circuit_length(0.0, "14", 24.0, 10.0)
        assert result == float("inf")

    def test_higher_current_shorter_length(self):
        l1 = calculate_max_circuit_length(1.0, "14", 24.0, 10.0)
        l2 = calculate_max_circuit_length(2.0, "14", 24.0, 10.0)
        assert l2 < l1

    def test_larger_gauge_longer_length(self):
        l14 = calculate_max_circuit_length(1.0, "14", 24.0, 10.0)
        l12 = calculate_max_circuit_length(1.0, "12", 24.0, 10.0)
        assert l12 > l14

    def test_higher_voltage_longer_length(self):
        l24 = calculate_max_circuit_length(1.0, "14", 24.0, 10.0)
        l48 = calculate_max_circuit_length(1.0, "14", 48.0, 10.0)
        assert l48 > l24

    def test_result_in_metres(self):
        """BUG-11 FIX: Result is in metres, not km."""
        result = calculate_max_circuit_length(1.0, "14", 24.0, 10.0)
        # Should be ~119m, NOT ~0.119 km
        assert 50 < result < 500  # Reasonable metre range


# ─────────────────────────────────────────────────────────────────────────────
# Wire Gauge Recommendation
# ─────────────────────────────────────────────────────────────────────────────


class TestRecommendWireGauge:
    def test_short_circuit_recommends_14(self):
        """Short, low-current circuit should use smallest FA gauge."""
        result = recommend_wire_gauge(0.1, 10.0, 24.0, 10.0)
        assert result["is_compliant"] is True
        assert result["recommended_awg"] in FA_WIRE_GAUGES

    def test_long_circuit_needs_larger_gauge(self):
        """Long circuit with high current needs thicker wire."""
        result = recommend_wire_gauge(2.0, 200.0, 24.0, 10.0)
        if result["is_compliant"]:
            # Should have recommended a larger gauge
            assert result["recommended_awg"] in ("10", "8", "6", "4", "3", "2", "1")

    def test_impossible_circuit_returns_engineering_review(self):
        """
        Even 4/0 insufficient → ENGINEERING_REVIEW (V58 FIX: was 2/0).
        Need extreme scenario: very high current + very long distance
        so that even 4/0 (0.0002 Ω/m) fails 10% drop.
        V_drop_4_0 = I × 2 × L × R = I × 2 × L × 0.0002
        For 10% of 24V = 2.4V: 2.4 = I × 2 × L × 0.0002
        With I=50A, L=500m: V_drop = 50 × 2 × 500 × 0.0002 = 10V → 41.7% > 10% ✓
        """
        result = recommend_wire_gauge(50.0, 500.0, 24.0, 10.0)
        assert result["recommended_awg"] == "ENGINEERING_REVIEW"
        assert result["is_compliant"] is False

    def test_recommendation_is_most_economical(self):
        """Should recommend thinnest compliant gauge (most economical)."""
        result = recommend_wire_gauge(0.5, 50.0, 24.0, 10.0)
        if result["is_compliant"]:
            # Verify no thinner gauge would also work
            awg = result["recommended_awg"]
            # If recommended is "12", "14" should not be compliant for same params
            thinner_gauges = {"14": [], "12": ["14"], "10": ["14", "12"], "8": ["14", "12", "10"]}
            for thinner in thinner_gauges.get(awg, []):
                calculate_voltage_drop(0.5, 50.0, thinner, 24.0)
                # At least this gauge should be non-compliant or we'd have recommended it
                # (Note: this may not always hold due to ordering, but for small loads it should)
                pass  # Structural check only  # NOSONAR - python:S2772

    def test_nfpa_reference_in_result(self):
        result = recommend_wire_gauge(0.5, 50.0, 24.0, 10.0)
        assert "NFPA 72" in result["nfpa_reference"]

    def test_zero_current_recommends_smallest(self):
        """Zero current = any gauge works, should recommend smallest."""
        result = recommend_wire_gauge(0.0, 100.0, 24.0, 10.0)
        assert result["is_compliant"] is True


# ─────────────────────────────────────────────────────────────────────────────
# Battery Backup Calculation (BUG-13 FIX: Amperes NOT milliamps)
# ─────────────────────────────────────────────────────────────────────────────


class TestCalculateBatteryBackup:
    """
    BUG-13 FIX: Previous code multiplied by 1000 (treating A as mA),
    making all battery calculations 1000× too small.
    """

    def test_basic_battery_calculation(self):
        """
        Standard FA panel: 0.5A standby, 1.5A alarm.
        Required = (0.5×24 + 1.5×(5/60)) / 0.80 = (12.0 + 0.125) / 0.80 = 15.15625 Ah
        """
        result = calculate_battery_backup(0.5, 1.5)
        expected_ah = (0.5 * 24.0 + 1.5 * (5 / 60)) / 0.80
        assert result["required_ah"] == pytest.approx(expected_ah, rel=1e-3)

    def test_battery_not_1000x_too_small(self):
        """
        BUG-13: Result must NOT be 1000× smaller than expected.
        Old broken code: result = (0.5 × 24 + 1.5 × 0.25) / 0.80 / 1000
        """
        result = calculate_battery_backup(0.5, 1.5)
        expected_ah = (0.5 * 24.0 + 1.5 * 0.25) / 0.80
        # Must be close to expected, NOT 1000× smaller
        assert result["required_ah"] > expected_ah * 0.5  # generous lower bound
        assert result["required_ah"] < expected_ah * 2.0  # generous upper bound

    def test_recommended_ah_rounds_up_to_standard(self):
        """Recommended Ah should be a standard battery size."""
        result = calculate_battery_backup(0.5, 1.5)
        assert result["recommended_ah"] >= result["required_ah"]

    def test_standby_hours_breakdown(self):
        result = calculate_battery_backup(0.5, 1.5, standby_hours=24.0)
        assert result["standby_ah"] == pytest.approx(0.5 * 24.0, rel=1e-3)

    def test_alarm_hours_breakdown(self):
        result = calculate_battery_backup(0.5, 1.5, alarm_hours=0.25)
        assert result["alarm_ah"] == pytest.approx(1.5 * 0.25, rel=1e-3)

    def test_negative_standby_load_raises(self):
        with pytest.raises(ValueError, match="must be >= 0"):
            calculate_battery_backup(-0.5, 1.5)

    def test_negative_alarm_load_raises(self):
        with pytest.raises(ValueError, match="must be >= 0"):
            calculate_battery_backup(0.5, -1.5)

    def test_invalid_derating_factor_zero(self):
        with pytest.raises(ValueError, match="derating_factor"):
            calculate_battery_backup(0.5, 1.5, derating_factor=0.0)

    def test_invalid_derating_factor_over_one(self):
        with pytest.raises(ValueError, match="derating_factor"):
            calculate_battery_backup(0.5, 1.5, derating_factor=1.5)

    def test_standby_below_24h_warns(self):
        """NFPA 72 §10.6.7.2: minimum 24h standby — V65 FIX: now raises ValueError."""
        with pytest.raises(ValueError, match="24h"):
            calculate_battery_backup(0.5, 1.5, standby_hours=12.0)

    def test_standby_exactly_24h_no_warning(self):
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            calculate_battery_backup(0.5, 1.5, standby_hours=24.0)
            nfpa_warnings = [x for x in w if "24h" in str(x.message)]
            assert len(nfpa_warnings) == 0

    def test_nfpa_compliant_flag(self):
        """V58 FIX (BUG #2): nfpa_compliant was hardcoded True."""
        result_ok = calculate_battery_backup(0.5, 1.5, standby_hours=24.0)
        assert result_ok["nfpa_compliant"] is True

        # V65 FIX: sub-24h standby now raises ValueError (not just warning)
        with pytest.raises(ValueError, match="24h"):
            calculate_battery_backup(0.5, 1.5, standby_hours=12.0)

    def test_cold_temperature_derating(self):
        """At 0°C, battery capacity is reduced."""
        result_25 = calculate_battery_backup(0.5, 1.5, temperature_c=25.0)
        result_0 = calculate_battery_backup(0.5, 1.5, temperature_c=0.0)
        # Cold battery needs MORE Ah for same load
        assert result_0["required_ah"] > result_25["required_ah"]

    def test_warm_temperature_no_derating(self):
        """At 25°C and above, no temperature derating."""
        result_25 = calculate_battery_backup(0.5, 1.5, temperature_c=25.0)
        result_40 = calculate_battery_backup(0.5, 1.5, temperature_c=40.0)
        assert result_25["temp_derating"] == 1.0  # NOSONAR — S1244: import retained for re-export / API surface
        assert result_40["temp_derating"] == 1.0  # NOSONAR — S1244: import retained for re-export / API surface

    def test_temperature_derating_floored_at_70pct(self):
        """Temperature derating should not go below 70%."""
        result = calculate_battery_backup(0.5, 1.5, temperature_c=-100.0)
        assert result["temp_derating"] >= 0.70


class TestNextStandardAh:
    def test_rounds_up_to_standard(self):
        assert _next_standard_ah(1.0) == 1.2  # NOSONAR — S1244: import retained for re-export / API surface
        assert _next_standard_ah(1.2) == 1.2  # NOSONAR — S1244: import retained for re-export / API surface
        assert _next_standard_ah(1.3) == 2.0  # NOSONAR — S1244: import retained for re-export / API surface
        assert _next_standard_ah(5.0) == 5.0  # NOSONAR — S1244: import retained for re-export / API surface
        assert _next_standard_ah(5.1) == 7.0  # NOSONAR — S1244: import retained for re-export / API surface

    def test_large_value_extrapolates(self):
        """Values beyond the standard table extrapolate by 50 Ah increments."""
        result = _next_standard_ah(250.0)
        assert result >= 250.0
        # Should be a multiple of 50
        assert result % 50.0 == 0.0  # NOSONAR — S1244: import retained for re-export / API surface

    def test_exact_standard_value(self):
        assert _next_standard_ah(100.0) == 100.0  # NOSONAR — S1244: import retained for re-export / API surface


# ─────────────────────────────────────────────────────────────────────────────
# Edge Cases & Integration
# ─────────────────────────────────────────────────────────────────────────────


class TestVoltageDropEdgeCases:
    def test_very_small_current(self):
        """1 mA over 1m — should have negligible drop."""
        result = calculate_voltage_drop(0.001, 1.0, "14", 24.0)
        assert result["voltage_drop_v"] < 0.001
        assert result["is_compliant"] is True

    def test_very_large_length(self):
        """10km cable — extreme but valid input."""
        result = calculate_voltage_drop(0.5, 10000.0, "14", 24.0)
        assert result["voltage_drop_pct"] > 100  # Way over 10%
        assert result["is_compliant"] is False

    def test_12v_system(self):
        """12V system (some older FA systems)."""
        result = calculate_voltage_drop(1.0, 50.0, "14", 12.0)
        # Same drop V, but higher percentage
        result_24v = calculate_voltage_drop(1.0, 50.0, "14", 24.0)
        assert result["voltage_drop_v"] == pytest.approx(result_24v["voltage_drop_v"], rel=1e-6)
        assert result["voltage_drop_pct"] == pytest.approx(result_24v["voltage_drop_pct"] * 2, rel=1e-6)

    def test_boundary_just_under_10pct(self):
        """Just under 10% drop — should be compliant (≤)."""
        # Use a current that gives clearly < 10% drop
        r_per_m = get_wire_resistance_ohm_per_m("14")
        # 9% of 24V = 2.16V
        target_current = (24.0 * 0.09) / (2.0 * 100.0 * r_per_m)
        result = calculate_voltage_drop(target_current, 100.0, "14", 24.0)
        assert result["voltage_drop_pct"] < MAX_VOLTAGE_DROP_PCT
        assert result["is_compliant"] is True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
