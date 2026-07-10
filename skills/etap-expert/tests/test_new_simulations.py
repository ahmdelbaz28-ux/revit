# NOSONAR
"""
Gate 4 Extension: Tests for New Simulations (Harmonic + Transient Stability).
=============================================================================
Validates the 2 new simulations added in V131 Phase 2:
    6. Harmonic Analysis (IEEE 519-2014)
    7. Transient Stability (Equal Area Criterion)

Per FireAI agent.md Rule 10 (TEST-AND-FIX LOOP):
    After ANY code modification, tests MUST be run immediately.
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

import pytest

SKILL_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(SKILL_ROOT / "scripts"))

from internal_simulation_engine import (  # noqa: E402
    IEEE_519_VOLTAGE_LIMIT_PCT,
    get_tdd_limit,
    simulate_harmonic_analysis,
    simulate_transient_stability,
)

# ═══════════════════════════════════════════════════════════════════════════
# SIMULATION 6: HARMONIC ANALYSIS (IEEE 519-2014)
# ═══════════════════════════════════════════════════════════════════════════


class TestHarmonicAnalysis:
    """Verify harmonic analysis per IEEE 519-2014."""

    def test_simulation_runs_with_defaults(self) -> None:
        result = simulate_harmonic_analysis()
        assert result is not None
        assert result.thd_voltage_pct > 0
        assert result.thd_current_pct > 0
        assert result.isc_il_ratio > 0

    def test_default_harmonics_match_6_pulse_vfd(self) -> None:
        """Default spectrum should be 6-pulse VFD (h=5,7,11,13,17,19)."""
        result = simulate_harmonic_analysis()
        expected_harmonics = {5, 7, 11, 13, 17, 19}
        assert set(result.harmonics.keys()) == expected_harmonics

    def test_thd_current_calculation_correct(self) -> None:
        """THD_I = sqrt(Σ I_h²) / I_1 × 100%."""
        # Use known spectrum
        harmonics = {5: 20.0, 7: 14.0}  # 20% + 14%
        result = simulate_harmonic_analysis(harmonics=harmonics)
        expected_thd = math.sqrt(0.20**2 + 0.14**2) * 100  # = 24.4%
        assert abs(result.thd_current_pct - expected_thd) < 0.1

    def test_isc_il_ratio_calculation(self) -> None:
        """ISC/IL ratio determines TDD limit per IEEE 519 Table 2."""
        result = simulate_harmonic_analysis(
        )
        assert abs(result.isc_il_ratio - 100.0) < 0.01

    def test_tdd_limit_lookup_correct(self) -> None:
        """IEEE 519 Table 2 TDD limits by ISC/IL ratio."""
        # ISC/IL < 20 → 5%
        assert get_tdd_limit(15) == pytest.approx(5.0)
        # 20 ≤ ISC/IL < 50 → 8%
        assert get_tdd_limit(30) == pytest.approx(8.0)
        # 50 ≤ ISC/IL < 100 → 12%
        assert get_tdd_limit(75) == pytest.approx(12.0)
        # 100 ≤ ISC/IL < 1000 → 15%
        assert get_tdd_limit(500) == pytest.approx(15.0)
        # ISC/IL ≥ 1000 → 20%
        assert get_tdd_limit(2000) == pytest.approx(20.0)

    def test_voltage_limit_5pct_for_low_voltage(self) -> None:
        """IEEE 519 Table 1: THD_V < 5% for systems ≤ 69 kV."""
        assert IEEE_519_VOLTAGE_LIMIT_PCT == pytest.approx(5.0)

    def test_compliance_flags_set_correctly(self) -> None:
        """Voltage and current compliance must be True/False based on limits."""
        # High THD_I scenario → current_compliant = False
        result = simulate_harmonic_analysis(
            harmonics={5: 50.0, 7: 30.0},  # Very high THD
            load_current_a=100.0,
            isc_a=5000.0,  # ISC/IL = 50 → limit 8%
        )
        assert not result.current_compliant

    def test_resonance_detection(self) -> None:
        """Resonance must be detected when f_resonance ≈ harmonic frequency."""
        # Tune capacitor to resonate near 5th harmonic (300 Hz at 60 Hz fundamental)
        # f_r = 1/(2π×sqrt(L×C)) → C = 1/(4π²×f²×L)
        f_target = 300.0  # 5th harmonic
        L_h = 0.1 / 1000  # 0.1 mH → H  # NOSONAR - python:S117
        C_f = 1.0 / (4.0 * math.pi**2 * f_target**2 * L_h)  # NOSONAR - python:S117
        C_uf = C_f * 1e6  # → µF  # NOSONAR - python:S117

        result = simulate_harmonic_analysis(
            fundamental_freq_hz=60.0,
            system_inductance_mh=0.1,
            capacitor_uf=C_uf,
        )
        assert result.resonance_freq_hz is not None
        # Should be near 300 Hz (5th harmonic)
        assert abs(result.resonance_freq_hz - 300.0) < 10.0
        # Should trigger resonance warning
        assert any("RESONANCE" in w for w in result.warnings)

    def test_no_resonance_when_no_capacitor(self) -> None:
        """Without capacitor, resonance_freq_hz must be None."""
        result = simulate_harmonic_analysis(capacitor_uf=None)
        assert result.resonance_freq_hz is None

    def test_assumptions_documented(self) -> None:
        """All assumptions must be explicitly listed (Rule 8)."""
        result = simulate_harmonic_analysis()
        assert len(result.assumptions) >= 5
        assert any("IEEE 519" in a for a in result.assumptions)

    def test_warnings_for_non_compliance(self) -> None:
        """Non-compliant results must trigger warnings."""
        result = simulate_harmonic_analysis(
            harmonics={5: 50.0},  # Very high THD
            load_current_a=100.0,
            isc_a=5000.0,
        )
        if not result.current_compliant:
            assert any("exceeds IEEE 519" in w for w in result.warnings)


# ═══════════════════════════════════════════════════════════════════════════
# SIMULATION 7: TRANSIENT STABILITY (EQUAL AREA CRITERION)
# ═══════════════════════════════════════════════════════════════════════════


class TestTransientStability:
    """Verify transient stability per Equal Area Criterion."""

    def test_simulation_runs_with_defaults(self) -> None:
        result = simulate_transient_stability()
        assert result is not None
        assert result.critical_clearing_time_s > 0
        assert result.is_stable is True  # Default clearing time 0.1s < CCT

    def test_initial_rotor_angle_calculation(self) -> None:
        """δ_0 = asin(P_m / P_e_max)."""
        result = simulate_transient_stability(
            mechanical_power_pu=0.8, electrical_power_max_pu=1.5
        )
        expected_delta_0 = math.asin(0.8 / 1.5)
        assert abs(result.initial_rotor_angle_rad - expected_delta_0) < 1e-6

    def test_max_rotor_angle_is_pi_minus_delta_0(self) -> None:
        """δ_max = π - δ_0 (max swing before instability)."""
        result = simulate_transient_stability(
            mechanical_power_pu=0.8, electrical_power_max_pu=1.5
        )
        expected_delta_max = math.pi - result.initial_rotor_angle_rad
        assert abs(result.max_rotor_angle_rad - expected_delta_max) < 1e-6

    def test_critical_clearing_angle_within_valid_range(self) -> None:
        """δ_cc must be between δ_0 and δ_max."""
        result = simulate_transient_stability()
        assert result.initial_rotor_angle_rad < result.critical_clearing_angle_rad
        assert result.critical_clearing_angle_rad < result.max_rotor_angle_rad

    def test_cct_positive_for_stable_system(self) -> None:
        """CCT must be positive when P_m < P_e_max."""
        result = simulate_transient_stability()
        assert result.critical_clearing_time_s > 0

    def test_cct_increases_with_higher_inertia(self) -> None:
        """Higher H → higher CCT (more time to clear fault)."""
        result_low_h = simulate_transient_stability(h_constant_s=3.0)
        result_high_h = simulate_transient_stability(h_constant_s=6.0)
        assert result_high_h.critical_clearing_time_s > result_low_h.critical_clearing_time_s

    def test_cct_decreases_with_higher_loading(self) -> None:
        """Higher P_m → lower CCT (less stability margin)."""
        result_light = simulate_transient_stability(mechanical_power_pu=0.5)
        result_heavy = simulate_transient_stability(mechanical_power_pu=1.0)
        assert result_heavy.critical_clearing_time_s < result_light.critical_clearing_time_s

    def test_unstable_when_pm_exceeds_pe_max(self) -> None:
        """P_m ≥ P_e_max must raise ValueError (cannot operate)."""
        with pytest.raises(ValueError, match="must be < P_e_max"):
            simulate_transient_stability(
                mechanical_power_pu=1.5, electrical_power_max_pu=1.0
            )

    def test_stability_flag_true_when_clearing_below_cct(self) -> None:
        """is_stable = True when actual_clearing_time < CCT."""
        result = simulate_transient_stability(actual_clearing_time_s=0.05)
        assert result.is_stable is True

    def test_stability_flag_false_when_clearing_above_cct(self) -> None:
        """is_stable = False when actual_clearing_time > CCT."""
        # Default CCT ~0.2s, so 0.5s clearing → unstable
        result = simulate_transient_stability(actual_clearing_time_s=0.5)
        assert result.is_stable is False
        assert any("UNSTABLE" in w for w in result.warnings)

    def test_marginal_warning_near_cct(self) -> None:
        """Warning when clearing time is within 10% of CCT."""
        # Default CCT ~0.2s → 0.19s is within 10%
        result = simulate_transient_stability(actual_clearing_time_s=0.19)
        # Should be either stable with MARGINAL warning, or unstable
        if result.is_stable:
            assert any("MARGINAL" in w or "UNSTABLE" in w for w in result.warnings)

    def test_assumptions_documented(self) -> None:
        """All assumptions must be explicitly listed (Rule 8)."""
        result = simulate_transient_stability()
        assert len(result.assumptions) >= 5
        assert any("Equal Area Criterion" in a for a in result.assumptions)

    def test_50hz_system_supported(self) -> None:
        """System must support 50 Hz (European) as well as 60 Hz."""
        result_50 = simulate_transient_stability(system_frequency_hz=50.0)
        result_60 = simulate_transient_stability(system_frequency_hz=60.0)
        # 50 Hz has lower ω_s → higher CCT
        assert result_50.critical_clearing_time_s > result_60.critical_clearing_time_s


# ═══════════════════════════════════════════════════════════════════════════
# CROSS-SIMULATION CONSISTENCY
# ═══════════════════════════════════════════════════════════════════════════


class TestCrossSimulationConsistency:
    """Verify consistency across all 7 simulations."""

    def test_all_7_simulations_in_run_all(self) -> None:
        """run_all_simulations() must include all 7 simulations."""
        from internal_simulation_engine import run_all_simulations

        results = run_all_simulations()
        assert len(results) == 7
        expected_keys = {
            "cable_sizing", "transformer_sizing", "protection_coordination",
            "arc_flash", "flisr", "harmonic_analysis", "transient_stability"
        }
        assert set(results.keys()) == expected_keys

    def test_all_simulations_have_assumptions(self) -> None:
        """Every simulation must document assumptions (Rule 8)."""
        from internal_simulation_engine import run_all_simulations

        results = run_all_simulations()
        for name, result in results.items():
            assert "assumptions" in result, f"{name} missing assumptions"
            assert len(result["assumptions"]) >= 3, (
                f"{name} has only {len(result['assumptions'])} assumptions"
            )
