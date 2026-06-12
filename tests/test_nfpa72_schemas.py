"""
tests/test_nfpa72_schemas.py
==============================
Comprehensive test suite for fireai/core/nfpa72_schemas.py

SAFETY CRITICAL: Pydantic schemas validate all inputs to the NFPA 72
calculation pipeline. Invalid data that bypasses validation could produce
incorrect voltage drop or coverage radius results — a direct life-safety
hazard.

NFPA 72 References:
  §17.6.3.1.1 — Height-adjusted spacing table
  §17.7.4.2.3.1 — Coverage radius R = 0.7 × S
  §10.14 — Voltage drop
  Table 17.6.3.1.2(a) — Sloped ceiling spacing reduction

NEC References:
  §210.19(A)(1) — Continuous load factor (125%)
  §215.2(A)(2) — 5% total voltage drop limit
  Table 310.15(B)(2)(a) — Temperature correction
  Table 310.15(B)(3)(a) — Conductor bundling derating
"""

from __future__ import annotations

import math
import pytest
from pydantic import ValidationError

from fireai.core.nfpa72_schemas import (
    CeilingTypePydantic,
    DetectorTypePydantic,
    NFPA72Input,
    VoltageDropInput,
    ConvergenceConfig,
)


# ─────────────────────────────────────────────────────────────────────────────
# CeilingTypePydantic Enum
# ─────────────────────────────────────────────────────────────────────────────


class TestCeilingTypePydantic:
    def test_all_values(self):
        assert CeilingTypePydantic.FLAT.value == "flat"
        assert CeilingTypePydantic.SLOPED.value == "sloped"
        assert CeilingTypePydantic.GABLE.value == "gable"
        assert CeilingTypePydantic.SHED.value == "shed"
        assert CeilingTypePydantic.WAFFLE.value == "waffle"
        assert CeilingTypePydantic.ACOUSTIC_TILE.value == "acoustic_tile"
        assert CeilingTypePydantic.BEAM_AND_POCKET.value == "beam_and_pocket"

    def test_is_str_enum(self):
        assert isinstance(CeilingTypePydantic.FLAT, str)

    def test_member_count(self):
        assert len(CeilingTypePydantic) == 7


# ─────────────────────────────────────────────────────────────────────────────
# DetectorTypePydantic Enum
# ─────────────────────────────────────────────────────────────────────────────


class TestDetectorTypePydantic:
    def test_all_values(self):
        assert DetectorTypePydantic.SMOKE.value == "smoke"
        assert DetectorTypePydantic.HEAT.value == "heat"
        assert DetectorTypePydantic.DUCT.value == "duct"
        assert DetectorTypePydantic.BEAM.value == "beam"
        assert DetectorTypePydantic.FLAME.value == "flame"
        assert DetectorTypePydantic.GAS.value == "gas"

    def test_is_str_enum(self):
        assert isinstance(DetectorTypePydantic.SMOKE, str)


# ─────────────────────────────────────────────────────────────────────────────
# NFPA72Input Schema
# ─────────────────────────────────────────────────────────────────────────────


class TestNFPA72Input:
    """Pydantic-validated input for smoke detector coverage radius."""

    def test_valid_input(self):
        data = NFPA72Input(
            spacing_m=9.1,
            ceiling_height_m=3.0,
            ceiling_type=CeilingTypePydantic.FLAT,
        )
        assert data.spacing_m == 9.1
        assert data.ceiling_height_m == 3.0

    def test_defaults(self):
        data = NFPA72Input(spacing_m=9.1, ceiling_height_m=3.0)
        assert data.ceiling_type == CeilingTypePydantic.FLAT
        assert data.hvac_velocity_ms == 0.0
        assert data.beam_depth_m == 0.0
        assert data.detector_type == DetectorTypePydantic.SMOKE

    def test_reject_zero_spacing(self):
        with pytest.raises(ValidationError, match="greater than 0"):
            NFPA72Input(spacing_m=0.0, ceiling_height_m=3.0)

    def test_reject_negative_spacing(self):
        with pytest.raises(ValidationError, match="greater than 0"):
            NFPA72Input(spacing_m=-1.0, ceiling_height_m=3.0)

    def test_reject_spacing_above_30(self):
        with pytest.raises(ValidationError, match="less than or equal to 30"):
            NFPA72Input(spacing_m=31.0, ceiling_height_m=3.0)

    def test_reject_nan_spacing(self):
        with pytest.raises(ValidationError):
            NFPA72Input(spacing_m=float("nan"), ceiling_height_m=3.0)

    def test_reject_inf_spacing(self):
        with pytest.raises(ValidationError):
            NFPA72Input(spacing_m=float("inf"), ceiling_height_m=3.0)

    def test_reject_zero_ceiling_height(self):
        with pytest.raises(ValidationError, match="greater than 0"):
            NFPA72Input(spacing_m=9.1, ceiling_height_m=0.0)

    def test_reject_negative_ceiling_height(self):
        with pytest.raises(ValidationError, match="greater than 0"):
            NFPA72Input(spacing_m=9.1, ceiling_height_m=-1.0)

    def test_reject_ceiling_height_above_18_288(self):
        # V128 FIX: Max ceiling height is now 18.288m (60ft) per NFPA 72 §17.7.3.2.4
        with pytest.raises(ValidationError, match="less than or equal to 18.288"):
            NFPA72Input(spacing_m=9.1, ceiling_height_m=19.0)

    def test_reject_nan_ceiling_height(self):
        with pytest.raises(ValidationError):
            NFPA72Input(spacing_m=9.1, ceiling_height_m=float("nan"))

    def test_reject_inf_ceiling_height(self):
        with pytest.raises(ValidationError):
            NFPA72Input(spacing_m=9.1, ceiling_height_m=float("inf"))

    def test_reject_negative_hvac_velocity(self):
        with pytest.raises(ValidationError, match="greater than or equal to 0"):
            NFPA72Input(spacing_m=9.1, ceiling_height_m=3.0, hvac_velocity_ms=-1.0)

    def test_reject_hvac_velocity_above_5(self):
        with pytest.raises(ValidationError, match="less than or equal to 5"):
            NFPA72Input(spacing_m=9.1, ceiling_height_m=3.0, hvac_velocity_ms=6.0)

    def test_reject_negative_beam_depth(self):
        with pytest.raises(ValidationError, match="greater than or equal to 0"):
            NFPA72Input(spacing_m=9.1, ceiling_height_m=3.0, beam_depth_m=-0.1)

    def test_reject_beam_depth_above_3(self):
        with pytest.raises(ValidationError, match="less than or equal to 3"):
            NFPA72Input(spacing_m=9.1, ceiling_height_m=3.0, beam_depth_m=4.0)

    def test_flag_low_ceiling_height(self):
        """Heights below 3.0m are accepted but flagged for PE review."""
        data = NFPA72Input(spacing_m=9.1, ceiling_height_m=2.5)
        assert data.ceiling_height_m == 2.5  # Accepted

    def test_sloped_ceiling_spacing_exceeds_max(self):
        """NFPA 72 Table 17.6.3.1.2(a): sloped ceiling max spacing 6.4m."""
        with pytest.raises(ValidationError, match="Sloped ceiling"):
            NFPA72Input(
                spacing_m=9.1,
                ceiling_height_m=3.0,
                ceiling_type=CeilingTypePydantic.SLOPED,
            )

    def test_sloped_ceiling_spacing_within_limit(self):
        data = NFPA72Input(
            spacing_m=6.4,
            ceiling_height_m=3.0,
            ceiling_type=CeilingTypePydantic.SLOPED,
        )
        assert data.spacing_m == 6.4

    def test_heat_detector_type(self):
        data = NFPA72Input(
            spacing_m=6.1,
            ceiling_height_m=3.0,
            detector_type=DetectorTypePydantic.HEAT,
        )
        assert data.detector_type == DetectorTypePydantic.HEAT


class TestNFPA72InputComputeCoverageRadius:
    """R = 0.7 × S with correction factors."""

    def test_flat_ceiling_base_factor(self):
        """Flat ceiling: R = 0.7 × S."""
        data = NFPA72Input(spacing_m=9.1, ceiling_height_m=3.0)
        r = data.compute_coverage_radius()
        assert r == pytest.approx(0.7 * 9.1, rel=0.01)

    def test_sloped_ceiling_reduced_factor(self):
        """Non-flat ceiling: R = 0.6 × S."""
        data = NFPA72Input(
            spacing_m=6.4,
            ceiling_height_m=3.0,
            ceiling_type=CeilingTypePydantic.SLOPED,
        )
        r = data.compute_coverage_radius()
        assert r == pytest.approx(0.6 * 6.4, rel=0.01)

    def test_hvac_velocity_derating(self):
        """HVAC velocity > 0 reduces coverage radius."""
        data_no_hvac = NFPA72Input(spacing_m=9.1, ceiling_height_m=3.0, hvac_velocity_ms=0.0)
        data_with_hvac = NFPA72Input(spacing_m=9.1, ceiling_height_m=3.0, hvac_velocity_ms=2.0)
        r_no = data_no_hvac.compute_coverage_radius()
        r_with = data_with_hvac.compute_coverage_radius()
        assert r_with < r_no

    def test_hvac_correction_formula(self):
        """hvac_correction = max(0.0, 1.0 - velocity × 0.10)."""
        data = NFPA72Input(spacing_m=9.1, ceiling_height_m=3.0, hvac_velocity_ms=1.0)
        r = data.compute_coverage_radius()
        expected = round(0.7 * 9.1 * (1.0 - 0.10), 3)
        assert r == pytest.approx(expected, abs=0.001)

    def test_beam_depth_correction(self):
        """Beam depth > 10% of ceiling height reduces radius."""
        data_no_beam = NFPA72Input(spacing_m=9.1, ceiling_height_m=3.0, beam_depth_m=0.0)
        data_with_beam = NFPA72Input(spacing_m=9.1, ceiling_height_m=3.0, beam_depth_m=0.5)
        r_no = data_no_beam.compute_coverage_radius()
        r_with = data_with_beam.compute_coverage_radius()
        assert r_with < r_no

    def test_beam_depth_below_threshold_no_effect(self):
        """Beam depth ≤ 10% of ceiling height: no correction."""
        data = NFPA72Input(spacing_m=9.1, ceiling_height_m=3.0, beam_depth_m=0.29)  # < 10% of 3.0
        r = data.compute_coverage_radius()
        expected = round(0.7 * 9.1, 3)
        assert r == pytest.approx(expected, abs=0.01)

    def test_beam_depth_above_threshold_correction(self):
        """Beam depth > 10%: correction = max(0.25, 1.0 - excess × 2.0)."""
        data = NFPA72Input(spacing_m=9.1, ceiling_height_m=3.0, beam_depth_m=0.6)
        r = data.compute_coverage_radius()
        depth_fraction = 0.6 / 3.0  # 0.20
        excess = depth_fraction - 0.10  # 0.10
        beam_correction = max(0.25, 1.0 - excess * 2.0)  # 0.80
        expected = round(0.7 * 9.1 * beam_correction, 3)
        assert r == pytest.approx(expected, abs=0.01)

    def test_result_rounded_to_3_decimals(self):
        data = NFPA72Input(spacing_m=9.1, ceiling_height_m=3.0)
        r = data.compute_coverage_radius()
        # Check rounding
        assert r == round(r, 3)


# ─────────────────────────────────────────────────────────────────────────────
# VoltageDropInput Schema
# ─────────────────────────────────────────────────────────────────────────────


class TestVoltageDropInput:
    """Pydantic-validated input for voltage drop calculations per NEC/NFPA 72."""

    def test_valid_input(self):
        data = VoltageDropInput(
            supply_voltage_v=24.0,
            load_current_a=0.5,
            cable_resistance_ohm_per_m=0.00820,
            cable_length_m=100.0,
        )
        assert data.supply_voltage_v == 24.0

    def test_defaults(self):
        data = VoltageDropInput(
            supply_voltage_v=24.0,
            load_current_a=0.5,
            cable_resistance_ohm_per_m=0.00820,
            cable_length_m=100.0,
        )
        assert data.ambient_temp_c == 30.0
        assert data.num_conductors == 2
        assert data.is_continuous_load is True

    def test_reject_zero_supply_voltage(self):
        with pytest.raises(ValidationError, match="greater than 0"):
            VoltageDropInput(
                supply_voltage_v=0.0,
                load_current_a=0.5,
                cable_resistance_ohm_per_m=0.00820,
                cable_length_m=100.0,
            )

    def test_reject_negative_supply_voltage(self):
        with pytest.raises(ValidationError, match="greater than 0"):
            VoltageDropInput(
                supply_voltage_v=-24.0,
                load_current_a=0.5,
                cable_resistance_ohm_per_m=0.00820,
                cable_length_m=100.0,
            )

    def test_reject_supply_voltage_above_125(self):
        with pytest.raises(ValidationError, match="less than or equal to 125"):
            VoltageDropInput(
                supply_voltage_v=130.0,
                load_current_a=0.5,
                cable_resistance_ohm_per_m=0.00820,
                cable_length_m=100.0,
            )

    def test_reject_negative_load_current(self):
        with pytest.raises(ValidationError, match="greater than or equal to 0"):
            VoltageDropInput(
                supply_voltage_v=24.0,
                load_current_a=-0.5,
                cable_resistance_ohm_per_m=0.00820,
                cable_length_m=100.0,
            )

    def test_reject_load_current_above_50(self):
        with pytest.raises(ValidationError, match="less than or equal to 50"):
            VoltageDropInput(
                supply_voltage_v=24.0,
                load_current_a=55.0,
                cable_resistance_ohm_per_m=0.00820,
                cable_length_m=100.0,
            )

    def test_reject_zero_cable_resistance(self):
        with pytest.raises(ValidationError, match="greater than 0"):
            VoltageDropInput(
                supply_voltage_v=24.0,
                load_current_a=0.5,
                cable_resistance_ohm_per_m=0.0,
                cable_length_m=100.0,
            )

    def test_reject_cable_resistance_above_1(self):
        with pytest.raises(ValidationError, match="less than or equal to 1"):
            VoltageDropInput(
                supply_voltage_v=24.0,
                load_current_a=0.5,
                cable_resistance_ohm_per_m=1.5,
                cable_length_m=100.0,
            )

    def test_reject_negative_cable_length(self):
        with pytest.raises(ValidationError, match="greater than or equal to 0"):
            VoltageDropInput(
                supply_voltage_v=24.0,
                load_current_a=0.5,
                cable_resistance_ohm_per_m=0.00820,
                cable_length_m=-10.0,
            )

    def test_reject_cable_length_above_2000(self):
        with pytest.raises(ValidationError, match="less than or equal to 2000"):
            VoltageDropInput(
                supply_voltage_v=24.0,
                load_current_a=0.5,
                cable_resistance_ohm_per_m=0.00820,
                cable_length_m=2500.0,
            )

    def test_reject_nan_supply_voltage(self):
        with pytest.raises(ValidationError):
            VoltageDropInput(
                supply_voltage_v=float("nan"),
                load_current_a=0.5,
                cable_resistance_ohm_per_m=0.00820,
                cable_length_m=100.0,
            )

    def test_reject_inf_load_current(self):
        with pytest.raises(ValidationError):
            VoltageDropInput(
                supply_voltage_v=24.0,
                load_current_a=float("inf"),
                cable_resistance_ohm_per_m=0.00820,
                cable_length_m=100.0,
            )

    def test_reject_ambient_temp_below_minus_40(self):
        with pytest.raises(ValidationError, match="greater than or equal to -40"):
            VoltageDropInput(
                supply_voltage_v=24.0,
                load_current_a=0.5,
                cable_resistance_ohm_per_m=0.00820,
                cable_length_m=100.0,
                ambient_temp_c=-50.0,
            )

    def test_reject_ambient_temp_above_90(self):
        with pytest.raises(ValidationError, match="less than or equal to 90"):
            VoltageDropInput(
                supply_voltage_v=24.0,
                load_current_a=0.5,
                cable_resistance_ohm_per_m=0.00820,
                cable_length_m=100.0,
                ambient_temp_c=100.0,
            )

    def test_reject_num_conductors_below_1(self):
        with pytest.raises(ValidationError, match="greater than or equal to 1"):
            VoltageDropInput(
                supply_voltage_v=24.0,
                load_current_a=0.5,
                cable_resistance_ohm_per_m=0.00820,
                cable_length_m=100.0,
                num_conductors=0,
            )

    def test_reject_num_conductors_above_50(self):
        with pytest.raises(ValidationError, match="less than or equal to 50"):
            VoltageDropInput(
                supply_voltage_v=24.0,
                load_current_a=0.5,
                cable_resistance_ohm_per_m=0.00820,
                cable_length_m=100.0,
                num_conductors=55,
            )


class TestVoltageDropInputCompute:
    """Voltage drop computation per NFPA 72 §10.14 and NEC."""

    def test_simple_voltage_drop(self):
        """V_drop = I_eff × R_total × temp_correction / bundling."""
        data = VoltageDropInput(
            supply_voltage_v=24.0,
            load_current_a=0.5,
            cable_resistance_ohm_per_m=0.00820,
            cable_length_m=100.0,
        )
        result = data.compute_voltage_drop()
        # V14 Bug #12 FIX: total_resistance = R × L × 2
        total_r = 0.00820 * 100.0 * 2.0
        # Continuous load: I_eff = 0.5 × 1.25
        i_eff = 0.5 * 1.25
        expected_drop = i_eff * total_r  # No temp/bundling correction at defaults
        assert result["drop_v"] == pytest.approx(expected_drop, rel=0.01)

    def test_return_path_factor_included(self):
        """V14 Bug #12 FIX: DC return path factor (×2) MUST be included."""
        data = VoltageDropInput(
            supply_voltage_v=24.0,
            load_current_a=1.0,
            cable_resistance_ohm_per_m=0.01,
            cable_length_m=100.0,
        )
        result = data.compute_voltage_drop()
        # total_resistance = 0.01 × 100 × 2 = 2.0
        # i_eff = 1.0 × 1.25 = 1.25
        # drop = 1.25 × 2.0 = 2.5V
        assert result["drop_v"] == pytest.approx(2.5, rel=0.01)

    def test_continuous_load_factor(self):
        """NEC §210.19(A)(1): continuous load = 125%."""
        data_cont = VoltageDropInput(
            supply_voltage_v=24.0,
            load_current_a=1.0,
            cable_resistance_ohm_per_m=0.01,
            cable_length_m=100.0,
            is_continuous_load=True,
        )
        data_non = VoltageDropInput(
            supply_voltage_v=24.0,
            load_current_a=1.0,
            cable_resistance_ohm_per_m=0.01,
            cable_length_m=100.0,
            is_continuous_load=False,
        )
        r_cont = data_cont.compute_voltage_drop()
        r_non = data_non.compute_voltage_drop()
        assert r_cont["drop_v"] > r_non["drop_v"]
        assert r_cont["continuous_load_factor"] == 1.25
        assert r_non["continuous_load_factor"] == 1.0

    def test_temperature_correction(self):
        """NEC Table 310.15(B)(2)(a): temp above 75°C increases resistance.

        V78 FIX: Temperature correction now uses (T - 75) instead of (T - 30)
        because cable_resistance_ohm_per_m is specified at 75°C per NEC Table 8.
        Temps below 75°C produce no correction (clamped to 1.0).
        """
        data_30 = VoltageDropInput(
            supply_voltage_v=24.0,
            load_current_a=1.0,
            cable_resistance_ohm_per_m=0.01,
            cable_length_m=100.0,
            ambient_temp_c=30.0,
        )
        data_80 = VoltageDropInput(
            supply_voltage_v=24.0,
            load_current_a=1.0,
            cable_resistance_ohm_per_m=0.01,
            cable_length_m=100.0,
            ambient_temp_c=80.0,
        )
        r_30 = data_30.compute_voltage_drop()
        r_80 = data_80.compute_voltage_drop()
        assert r_80["drop_v"] > r_30["drop_v"]
        assert r_80["temp_correction_factor"] > 1.0

    def test_bundling_derating(self):
        """NEC Table 310.15(B)(3)(a): bundling factor is an ampacity derating,
        NOT a resistance increase.

        V78 FIX: bundling_factor was incorrectly divided into voltage drop.
        Bundling reduces ampacity (current-carrying capacity), not wire
        resistance. Wire resistance does not change when wires are bundled.
        Voltage drop should be the SAME regardless of bundling.
        """
        data_2 = VoltageDropInput(
            supply_voltage_v=24.0,
            load_current_a=1.0,
            cable_resistance_ohm_per_m=0.01,
            cable_length_m=100.0,
            num_conductors=2,
        )
        data_6 = VoltageDropInput(
            supply_voltage_v=24.0,
            load_current_a=1.0,
            cable_resistance_ohm_per_m=0.01,
            cable_length_m=100.0,
            num_conductors=6,
        )
        r_2 = data_2.compute_voltage_drop()
        r_6 = data_6.compute_voltage_drop()
        # V78 FIX: bundling no longer affects voltage drop — same resistance
        assert r_6["drop_v"] == pytest.approx(r_2["drop_v"], rel=0.001)
        # Bundling factor is still reported for ampacity checks
        assert r_6["bundling_derating_factor"] == 0.80

    def test_bundling_factor_table(self):
        """Verify all bundling factor tiers per NEC Table 310.15(B)(3)(a)."""
        cases = [
            (2, 1.0),
            (4, 0.80),
            (7, 0.70),
            (12, 0.50),
            (25, 0.45),
            (35, 0.40),
            (45, 0.35),
        ]
        for n_cond, expected_factor in cases:
            data = VoltageDropInput(
                supply_voltage_v=24.0,
                load_current_a=1.0,
                cable_resistance_ohm_per_m=0.01,
                cable_length_m=100.0,
                num_conductors=n_cond,
            )
            result = data.compute_voltage_drop()
            assert result["bundling_derating_factor"] == expected_factor, (
                f"Bundling factor for {n_cond} conductors: "
                f"expected {expected_factor}, got {result['bundling_derating_factor']}"
            )

    def test_terminal_voltage(self):
        """V_terminal = V_supply - V_drop."""
        data = VoltageDropInput(
            supply_voltage_v=24.0,
            load_current_a=0.5,
            cable_resistance_ohm_per_m=0.00820,
            cable_length_m=100.0,
        )
        result = data.compute_voltage_drop()
        expected_terminal = 24.0 - result["drop_v"]
        assert result["terminal_voltage_v"] == pytest.approx(expected_terminal, rel=0.001)

    def test_compliance_branch_3pct(self):
        """NEC §210.19(A)(1): branch circuit ≤ 3%."""
        data = VoltageDropInput(
            supply_voltage_v=24.0,
            load_current_a=0.1,
            cable_resistance_ohm_per_m=0.00328,
            cable_length_m=10.0,
        )
        result = data.compute_voltage_drop()
        # Short circuit should be compliant
        assert result["compliant_branch_3pct"] is True

    def test_compliance_total_5pct(self):
        """NEC §215.2(A)(2): total drop ≤ 5%."""
        data = VoltageDropInput(
            supply_voltage_v=24.0,
            load_current_a=0.1,
            cable_resistance_ohm_per_m=0.00328,
            cable_length_m=10.0,
        )
        result = data.compute_voltage_drop()
        assert result["compliant_total_5pct"] is True

    def test_compliance_terminal_voltage(self):
        """NFPA 72 §10.14.1: terminal voltage ≥ 16V."""
        data = VoltageDropInput(
            supply_voltage_v=24.0,
            load_current_a=0.1,
            cable_resistance_ohm_per_m=0.00328,
            cable_length_m=10.0,
        )
        result = data.compute_voltage_drop()
        assert result["compliant_terminal_voltage"] is True

    def test_references_in_result(self):
        data = VoltageDropInput(
            supply_voltage_v=24.0,
            load_current_a=0.5,
            cable_resistance_ohm_per_m=0.00820,
            cable_length_m=100.0,
        )
        result = data.compute_voltage_drop()
        refs = result["references"]
        assert "nfpa72_10_14" in refs
        assert "nec_210_19_A_1" in refs
        assert "nec_215_2_A_2" in refs
        assert "nec_310_15_B_2a" in refs
        assert "nec_310_15_B_3a" in refs

    def test_drop_fraction_calculation(self):
        """drop_fraction = drop_v / supply_voltage_v."""
        data = VoltageDropInput(
            supply_voltage_v=24.0,
            load_current_a=0.5,
            cable_resistance_ohm_per_m=0.00820,
            cable_length_m=100.0,
        )
        result = data.compute_voltage_drop()
        expected_frac = result["drop_v"] / 24.0
        assert result["drop_fraction"] == pytest.approx(expected_frac, rel=0.001)

    def test_zero_current_zero_drop(self):
        data = VoltageDropInput(
            supply_voltage_v=24.0,
            load_current_a=0.0,
            cable_resistance_ohm_per_m=0.00820,
            cable_length_m=100.0,
        )
        result = data.compute_voltage_drop()
        assert result["drop_v"] == pytest.approx(0.0, abs=0.0001)


# ─────────────────────────────────────────────────────────────────────────────
# ConvergenceConfig Schema
# ─────────────────────────────────────────────────────────────────────────────


class TestConvergenceConfig:
    """Termination configuration for density optimizer."""

    def test_defaults(self):
        cfg = ConvergenceConfig()
        assert cfg.epsilon == 1e-4
        assert cfg.max_iterations == 10_000
        assert cfg.monotonicity_check is True
        assert cfg.timeout_seconds == 300.0

    def test_custom_values(self):
        cfg = ConvergenceConfig(epsilon=0.01, max_iterations=100, timeout_seconds=60.0)
        assert cfg.epsilon == 0.01
        assert cfg.max_iterations == 100
        assert cfg.timeout_seconds == 60.0

    def test_reject_zero_epsilon(self):
        with pytest.raises(ValidationError, match="greater than 0"):
            ConvergenceConfig(epsilon=0.0)

    def test_reject_negative_epsilon(self):
        with pytest.raises(ValidationError, match="greater than 0"):
            ConvergenceConfig(epsilon=-0.01)

    def test_reject_epsilon_above_1(self):
        with pytest.raises(ValidationError, match="less than or equal to 1"):
            ConvergenceConfig(epsilon=1.5)

    def test_reject_zero_max_iterations(self):
        with pytest.raises(ValidationError, match="greater than 0"):
            ConvergenceConfig(max_iterations=0)

    def test_reject_max_iterations_above_1m(self):
        with pytest.raises(ValidationError, match="less than or equal to 1000000"):
            ConvergenceConfig(max_iterations=2_000_000)

    def test_reject_zero_timeout(self):
        with pytest.raises(ValidationError, match="greater than 0"):
            ConvergenceConfig(timeout_seconds=0.0)

    def test_reject_timeout_above_3600(self):
        with pytest.raises(ValidationError, match="less than or equal to 3600"):
            ConvergenceConfig(timeout_seconds=4000.0)

    def test_monotonicity_check_boolean(self):
        cfg = ConvergenceConfig(monotonicity_check=False)
        assert cfg.monotonicity_check is False
