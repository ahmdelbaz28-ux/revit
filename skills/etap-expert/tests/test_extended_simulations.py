# NOSONAR
"""
Gate 4 Extension: Tests for Extended Simulations + LLM Classifier (V131 Phase 3).
=================================================================================
Validates the 3 new simulations + LLM classifier added in V131 Phase 3:
    8. Motor Starting (IEEE 399)
    9. Cable Pulling (IEEE 835)
    10. Ground Grid (IEEE 80-2013)
    + LLM-based classifier with pattern fallback

Per FireAI agent.md Rule 10 (TEST-AND-FIX LOOP):
    After ANY code modification, tests MUST be run immediately.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

SKILL_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(SKILL_ROOT / "scripts"))

from extended_simulations import (  # noqa: E402
    BODY_RESISTANCE_OHM,
    FOOT_RADIUS_M,
    VOLTAGE_DIP_LIMITS,
    simulate_cable_pulling,
    simulate_ground_grid,
    simulate_motor_starting,
)
from llm_classifier import (  # noqa: E402
    classify_with_llm,
)

# ═══════════════════════════════════════════════════════════════════════════
# SIMULATION 8: MOTOR STARTING (IEEE 399)
# ═══════════════════════════════════════════════════════════════════════════


class TestMotorStarting:
    """Verify motor starting simulation per IEEE 399."""

    def test_simulation_runs_with_defaults(self):
        result = simulate_motor_starting()
        assert result is not None
        assert result.motor_fla_a > 0
        assert result.starting_current_a > 0
        assert result.voltage_dip_pct > 0

    def test_fla_calculation_matches_protection_coordination(self):
        """FLA must match the value from Protection Coordination simulation."""
        result = simulate_motor_starting(motor_hp=500.0, motor_voltage_v=4160.0)
        # FLA = 500 × 746 / (√3 × 4160 × 0.9 × 0.93) ≈ 62A
        assert abs(result.motor_fla_a - 62.0) < 1.0

    def test_dol_starting_current_6_to_8_times_fla(self):
        """DOL starting current must be 6-8× FLA per skill Section 7.3."""
        result = simulate_motor_starting(starting_method="DOL")
        multiple = result.starting_current_a / result.motor_fla_a
        assert 6.0 <= multiple <= 8.0

    def test_vfd_starting_current_lowest(self):
        """VFD must produce lowest starting current (1-1.5× FLA)."""
        result = simulate_motor_starting(starting_method="VFD")
        multiple = result.starting_current_a / result.motor_fla_a
        assert 1.0 <= multiple <= 1.5

    def test_all_starting_methods_supported(self):
        """All 5 starting methods from skill table must be supported."""
        for method in ["DOL", "star-delta", "autotransformer", "soft-starter", "VFD"]:
            result = simulate_motor_starting(starting_method=method)
            assert result.starting_method == method

    def test_invalid_starting_method_raises_error(self):
        """Unknown starting method must raise ValueError."""
        with pytest.raises(ValueError, match="Unknown starting method"):
            simulate_motor_starting(starting_method="invalid-method")

    def test_voltage_dip_increases_with_starting_current(self):
        """Higher starting current → higher voltage dip (Ohm's law)."""
        result_dol = simulate_motor_starting(starting_method="DOL")
        result_vfd = simulate_motor_starting(starting_method="VFD")
        assert result_dol.voltage_dip_pct > result_vfd.voltage_dip_pct

    def test_voltage_dip_limits_per_skill_table(self):
        """Verify voltage dip limits match skill Section 7.3 table."""
        assert VOLTAGE_DIP_LIMITS["lighting"] == pytest.approx(5.0)
        assert VOLTAGE_DIP_LIMITS["computers"] == pytest.approx(10.0)
        assert VOLTAGE_DIP_LIMITS["motors_running"] == pytest.approx(15.0)
        assert VOLTAGE_DIP_LIMITS["motors_starting"] == pytest.approx(20.0)
        assert VOLTAGE_DIP_LIMITS["process_control"] == pytest.approx(10.0)

    def test_acceleration_time_calculated(self):
        """Acceleration time = J × ω / (T_motor - T_load)."""
        result = simulate_motor_starting(
            load_inertia_kg_m2=50.0,
            motor_torque_nm=1500.0,
            load_torque_nm=800.0,
        )
        # ω = 2π × 1800/60 = 188.5 rad/s
        # t = 50 × 188.5 / (1500 - 800) = 13.46s
        assert abs(result.acceleration_time_s - 13.46) < 0.5

    def test_warning_when_acceleration_exceeds_stall_time(self):
        """If t_acc > safe_stall_time, warning must be generated."""
        result = simulate_motor_starting(
            load_inertia_kg_m2=50.0,
            motor_torque_nm=1500.0,
            load_torque_nm=800.0,
            safe_stall_time_s=10.0,  # Less than 13.46s
        )
        assert not result.acceleration_compliant
        assert any("stall time" in w for w in result.warnings)

    def test_warning_when_motor_torque_insufficient(self):
        """If T_motor ≤ T_load, motor cannot start (warning)."""
        result = simulate_motor_starting(
            motor_torque_nm=500.0,
            load_torque_nm=800.0,  # Higher than motor
        )
        assert any("insufficient accelerating torque" in w for w in result.warnings)

    def test_assumptions_documented(self):
        result = simulate_motor_starting()
        assert len(result.assumptions) >= 5
        assert any("Starting method" in a for a in result.assumptions)


# ═══════════════════════════════════════════════════════════════════════════
# SIMULATION 9: CABLE PULLING (IEEE 835)
# ═══════════════════════════════════════════════════════════════════════════


class TestCablePulling:
    """Verify cable pulling tension per IEEE 835."""

    def test_simulation_runs_with_defaults(self):
        result = simulate_cable_pulling()
        assert result is not None
        assert result.outgoing_tension_lb > 0
        assert result.incoming_tension_lb > 0

    def test_outgoing_tension_greater_than_incoming(self):
        """T_out must be > T_in (friction adds tension)."""
        result = simulate_cable_pulling()
        assert result.outgoing_tension_lb > result.incoming_tension_lb

    def test_bend_increases_tension_exponentially(self):
        """Bends add tension via exp(μ×θ) — more bends = more tension."""
        result_no_bend = simulate_cable_pulling(conduit_bends_deg=0.0)
        result_90_bend = simulate_cable_pulling(conduit_bends_deg=90.0)
        assert result_90_bend.outgoing_tension_lb > result_no_bend.outgoing_tension_lb

    def test_sidewall_pressure_calculated_at_bends(self):
        """Sidewall pressure = T / R (only when bends exist)."""
        result = simulate_cable_pulling(conduit_bends_deg=90.0, bend_radius_ft=5.0)
        assert result.sidewall_pressure_lb_per_ft > 0
        # P = T_out / R = ~1480 / 5 ≈ 296 lb/ft
        assert abs(result.sidewall_pressure_lb_per_ft - 296.0) < 50.0

    def test_no_sidewall_pressure_without_bends(self):
        """Without bends, sidewall pressure = 0."""
        result = simulate_cable_pulling(conduit_bends_deg=0.0)
        assert result.sidewall_pressure_lb_per_ft == pytest.approx(0.0)

    def test_warning_when_tension_exceeds_limit(self):
        """Excessive tension must trigger warning."""
        result = simulate_cable_pulling(
            conduit_length_ft=1000.0,  # Long pull
            tension_limit_lb=500.0,  # Low limit
        )
        assert not result.tension_compliant
        assert any("exceeds limit" in w for w in result.warnings)

    def test_warning_when_sidewall_exceeds_limit(self):
        """Excessive sidewall pressure must trigger warning."""
        result = simulate_cable_pulling(
            conduit_bends_deg=180.0,  # Sharp bends
            bend_radius_ft=1.0,  # Small radius
            sidewall_limit_lb_per_ft=100.0,  # Low limit
        )
        assert not result.sidewall_compliant

    def test_warning_for_excessive_pull_speed(self):
        """Pull speed > 25 ft/min must trigger warning (IEEE 835)."""
        result = simulate_cable_pulling(pull_speed_ft_per_min=40.0)
        assert any("exceeds IEEE 835 recommended" in w for w in result.warnings)

    def test_assumptions_documented(self):
        result = simulate_cable_pulling()
        assert len(result.assumptions) >= 5
        assert any("Friction coefficient" in a for a in result.assumptions)


# ═══════════════════════════════════════════════════════════════════════════
# SIMULATION 10: GROUND GRID (IEEE 80-2013)
# ═══════════════════════════════════════════════════════════════════════════


class TestGroundGrid:
    """Verify ground grid design per IEEE 80-2013."""

    def test_simulation_runs_with_defaults(self):
        result = simulate_ground_grid()
        assert result is not None
        assert result.grid_resistance_ohm > 0
        assert result.ground_potential_rise_v > 0

    def test_foot_resistance_formula_correct(self):
        """R_f = ρ × C / (4 × b) per IEEE 80 §12.5."""
        result = simulate_ground_grid(
            soil_resistivity_ohm_m=100.0,
        )
        # R_f = 100 × 1 / (4 × 0.08) = 312.5 Ω
        assert abs(result.foot_resistance_ohm - 312.5) < 1.0

    def test_body_resistance_is_1000_ohm(self):
        """IEEE 80 standard body resistance = 1000Ω."""
        assert BODY_RESISTANCE_OHM == pytest.approx(1000.0)

    def test_foot_radius_is_8cm(self):
        """IEEE 80 standard foot equivalent radius = 8cm."""
        assert FOOT_RADIUS_M == pytest.approx(0.08)

    def test_touch_voltage_limit_less_than_step_voltage_limit(self):
        """Touch V limit < Step V limit (step has 2× foot resistance)."""
        result = simulate_ground_grid()
        assert result.touch_voltage_limit_v < result.step_voltage_limit_v

    def test_gpr_calculation_correct(self):
        """GPR = I_fault × R_grid."""
        result = simulate_ground_grid(
            fault_current_a=5000.0,
            soil_resistivity_ohm_m=100.0,
        )
        expected_gpr = 5000.0 * result.grid_resistance_ohm
        assert abs(result.ground_potential_rise_v - expected_gpr) < 1.0

    def test_fibrillation_current_50kg_formula(self):
        """For 50kg: I_b = 0.116 / sqrt(t) (Dalziel's equation)."""
        # Use 0.5s fault duration → I_b = 0.164A
        # V_touch = (1000 + 312.5) × 0.164 = 215.3V
        result = simulate_ground_grid(
            fault_duration_s=0.5,
            body_weight_kg=50.0,
        )
        assert abs(result.touch_voltage_limit_v - 215.3) < 5.0

    def test_warning_when_gpr_exceeds_touch_limit(self):
        """GPR > touch V limit must trigger warning."""
        result = simulate_ground_grid(
            fault_current_a=50000.0,  # High fault current
        )
        assert not result.touch_voltage_compliant
        assert any("touch voltage" in w for w in result.warnings)

    def test_higher_soil_resistivity_increases_gpr(self):
        """Higher ρ → higher R_g → higher GPR."""
        result_low_rho = simulate_ground_grid(soil_resistivity_ohm_m=50.0)
        result_high_rho = simulate_ground_grid(soil_resistivity_ohm_m=500.0)
        assert result_high_rho.ground_potential_rise_v > result_low_rho.ground_potential_rise_v

    def test_assumptions_documented(self):
        result = simulate_ground_grid()
        assert len(result.assumptions) >= 5
        assert any("IEEE 80" in a or "Body resistance" in a for a in result.assumptions)


# ═══════════════════════════════════════════════════════════════════════════
# LLM CLASSIFIER (with pattern fallback)
# ═══════════════════════════════════════════════════════════════════════════


class TestLLMClassifier:
    """Verify LLM classifier with pattern fallback."""

    @pytest.mark.parametrize(
        ("request_text", "expected_category"),
        [
            ("What cable size for 200A load, 300ft, 480V?", "A"),
            ("Size transformer for 500kW", "B"),
            ("Run Load Flow to find fault current", "C"),
            ("Need 0% voltage drop on 1000ft cable", "C"),
            ("How does FLISR work for fault on Feeder 1?", "D"),
            ("Size BESS for 1MW 4-hour peak shaving", "DER"),
        ],
    )
    def test_classification_categories(self, request_text, expected_category):
        """LLM classifier (with fallback) must produce correct categories."""
        result = classify_with_llm(request_text, use_llm=False)  # Force pattern
        assert result.category == expected_category
        assert result.classifier_used in ("pattern", "llm")

    def test_result_has_reasoning(self):
        """Every result must include reasoning string."""
        result = classify_with_llm("Size transformer for 500kW", use_llm=False)
        assert result.reasoning
        assert len(result.reasoning) > 0

    def test_missing_data_listed_for_incomplete(self):
        """Incomplete requests must list missing parameters."""
        result = classify_with_llm("Size transformer for 500kW", use_llm=False)
        assert result.category == "B"
        assert len(result.missing_data) > 0

    def test_correct_study_for_wrong_request(self):
        """Wrong requests must suggest correct study type."""
        result = classify_with_llm(
            "Run Load Flow to find fault current", use_llm=False
        )
        assert result.category == "C"
        assert result.correct_study is not None
        assert "Short Circuit" in result.correct_study

    def test_empty_request_returns_b(self):
        """Empty request must be classified as B (incomplete)."""
        result = classify_with_llm("", use_llm=False)
        assert result.category == "B"

    def test_llm_unavailable_falls_back_gracefully(self):
        """When LLM is unavailable, must fall back to pattern-based."""
        # Force LLM attempt but it should fall back
        result = classify_with_llm("What cable size for 200A load, 300ft, 480V?", use_llm=True)
        # Either LLM succeeded, or pattern fallback was used
        assert result.classifier_used in ("pattern", "llm")
        assert result.category == "A"

    def test_confidence_in_valid_range(self):
        """Confidence must be 0.0-1.0."""
        result = classify_with_llm("Any request", use_llm=False)
        assert 0.0 <= result.confidence <= 1.0


# ═══════════════════════════════════════════════════════════════════════════
# CROSS-SIMULATION CONSISTENCY
# ═══════════════════════════════════════════════════════════════════════════


class TestExtendedSimulationsConsistency:
    """Verify consistency across all 10 simulations."""

    def test_all_3_extended_simulations_in_runner(self):
        """run_extended_simulations() must include all 3 new simulations."""
        from extended_simulations import run_extended_simulations

        results = run_extended_simulations()
        assert len(results) == 3
        expected_keys = {"motor_starting", "cable_pulling", "ground_grid"}
        assert set(results.keys()) == expected_keys

    def test_motor_fla_matches_protection_coordination(self):
        """Motor Starting FLA must match Protection Coordination FLA for same inputs."""
        from internal_simulation_engine import simulate_protection_coordination

        ms_result = simulate_motor_starting(motor_hp=500.0, motor_voltage_v=4160.0)
        pc_result = simulate_protection_coordination(motor_hp=500.0, motor_voltage_v=4160.0)
        # Both should calculate the same FLA
        assert abs(ms_result.motor_fla_a - pc_result.motor_fla_a) < 0.01

    def test_all_extended_simulations_have_assumptions(self):
        """Every simulation must document assumptions (Rule 8)."""
        from extended_simulations import run_extended_simulations

        results = run_extended_simulations()
        for name, result in results.items():
            assert "assumptions" in result, f"{name} missing assumptions"
            assert len(result["assumptions"]) >= 3
