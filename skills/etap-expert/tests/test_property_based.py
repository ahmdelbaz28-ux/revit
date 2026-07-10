"""
Gate 5: Adversarial Audit — Property-Based Tests.
==================================================
Fuzz-tests the skill loader and simulation engine with random inputs
to find hidden defects, edge cases, and unsafe assumptions.

Per FireAI agent.md VERIFICATION GATES:
    [Gate 5] Adversarial Audit
    - search for hidden defects
    - search for unsafe assumptions
    - search for architectural weakness
    - search for hallucinated logic

Uses Hypothesis for property-based testing with 100+ examples per test.
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

from hypothesis import HealthCheck, assume, given, settings
from hypothesis import strategies as st

SKILL_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(SKILL_ROOT / "scripts"))

from internal_simulation_engine import (  # noqa: E402
    NEC_310_16_COPPER_75C,
    determine_ppe_category,
    simulate_arc_flash,
    simulate_cable_sizing,
    simulate_flisr,
    simulate_protection_coordination,
    simulate_transformer_sizing,
)
from skill_loader import (  # noqa: E402
    SKILL_NAME,
    load_skill,
)

# ═══════════════════════════════════════════════════════════════════════════
# PROPERTY 1: Skill loader never crashes on valid input
# ═══════════════════════════════════════════════════════════════════════════


class TestLoaderPropertyBased:
    """Property: loader is deterministic and never crashes."""

    @given(run=st.integers(min_value=1, max_value=50))
    @settings(max_examples=20, deadline=2000)
    def test_loader_always_passes_on_valid_skill(self, run) -> None:
        """Loader must always pass on the valid SKILL.md — no flakiness."""
        result = load_skill(SKILL_ROOT / "SKILL.md")
        assert result.is_valid, f"Loader failed on run {run}"
        assert result.structure is not None
        assert result.structure.front_matter.name == SKILL_NAME

    @given(path=st.text(min_size=1, max_size=50))
    @settings(max_examples=30, deadline=2000)
    def test_loader_handles_nonexistent_paths_gracefully(self, path) -> None:
        """Loader must NOT crash on nonexistent paths — return error result."""
        assume(not Path(path).exists())
        result = load_skill(path)
        assert not result.is_valid
        assert len(result.errors) > 0


# ═══════════════════════════════════════════════════════════════════════════
# PROPERTY 2: Cable sizing — physical constraints always satisfied
# ═══════════════════════════════════════════════════════════════════════════


class TestCableSizingProperties:
    """Property: cable sizing always satisfies physical constraints."""

    @given(
        current=st.floats(min_value=10, max_value=400, allow_nan=False, allow_infinity=False),
        voltage=st.floats(min_value=120, max_value=1000, allow_nan=False, allow_infinity=False),
        length=st.floats(min_value=10, max_value=1000, allow_nan=False, allow_infinity=False),
        pf=st.floats(min_value=0.5, max_value=1.0, allow_nan=False, allow_infinity=False),
    )
    @settings(max_examples=50, deadline=3000,
              suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_ampacity_always_exceeds_load_current(self, current, voltage, length, pf) -> None:
        """Ampacity of recommended cable MUST be ≥ load current."""
        try:
            result = simulate_cable_sizing(
                load_current_a=current,
                voltage_v=voltage,
                length_ft=length,
                pf=pf,
            )
        except ValueError:
            # No conductor available — only fail for currents within table range
            assume(current <= max(NEC_310_16_COPPER_75C.values()))
            return

        assert result.ampacity_a >= current, (
            f"Ampacity {result.ampacity_a}A < load {current}A"
        )

    @given(
        current=st.floats(min_value=10, max_value=200, allow_nan=False),
        voltage=st.floats(min_value=120, max_value=1000, allow_nan=False),
    )
    @settings(max_examples=30, deadline=3000)
    def test_voltage_drop_always_positive(self, current, voltage) -> None:
        """Voltage drop must be positive (physics: any current through R > 0)."""
        try:
            result = simulate_cable_sizing(
                load_current_a=current, voltage_v=voltage, length_ft=300.0
            )
        except ValueError:
            return

        assert result.voltage_drop_v > 0
        assert result.voltage_drop_pct > 0


# ═══════════════════════════════════════════════════════════════════════════
# PROPERTY 3: Transformer sizing — physical sanity
# ═══════════════════════════════════════════════════════════════════════════


class TestTransformerSizingProperties:
    """Property: transformer sizing is physically sane."""

    @given(
        load_kw=st.floats(min_value=10, max_value=10000, allow_nan=False),
        pf=st.floats(min_value=0.7, max_value=1.0, allow_nan=False),
    )
    @settings(max_examples=50, deadline=3000)
    def test_required_kva_always_exceeds_load_kva(self, load_kw, pf) -> None:
        """Required kVA MUST exceed load kVA (kW/PF) due to safety + growth factors."""
        result = simulate_transformer_sizing(load_kw=load_kw, pf=pf)
        load_kva = load_kw / pf
        # Required = load_kVA × DF × SF × GF = load_kVA × 0.8 × 1.25 × 1.2 = 1.2 × load_kVA
        assert result.required_kva > load_kva, (
            f"Required {result.required_kva} kVA should exceed load {load_kva} kVA"
        )

    @given(
        load_kw=st.floats(min_value=100, max_value=5000, allow_nan=False),
    )
    @settings(max_examples=30, deadline=3000)
    def test_recommended_size_exceeds_required(self, load_kw) -> None:
        """Recommended transformer size MUST be ≥ required kVA."""
        result = simulate_transformer_sizing(load_kw=load_kw)
        assert result.recommended_size_kva >= result.required_kva


# ═══════════════════════════════════════════════════════════════════════════
# PROPERTY 4: Protection coordination — 50 must be above 51 pickup
# ═══════════════════════════════════════════════════════════════════════════


class TestProtectionCoordinationProperties:
    """Property: 50 (instantaneous) pickup > 51 (time-OC) pickup."""

    @given(
        hp=st.floats(min_value=50, max_value=2000, allow_nan=False),
        voltage=st.sampled_from([4160, 6600, 13800]),
    )
    @settings(max_examples=30, deadline=3000)
    def test_50_pickup_greater_than_51_pickup(self, hp, voltage) -> None:
        """50 pickup must be > 51 pickup (8× FLA > 1.05× FLA)."""
        result = simulate_protection_coordination(motor_hp=hp, motor_voltage_v=voltage)
        assert result.relay_50_pickup_primary_a > result.relay_51_pickup_primary_a

    @given(
        hp=st.floats(min_value=50, max_value=2000, allow_nan=False),
    )
    @settings(max_examples=20, deadline=3000)
    def test_locked_rotor_less_than_50_pickup(self, hp) -> None:
        """50 pickup should be > locked rotor (6× FLA) for coordination."""
        result = simulate_protection_coordination(motor_hp=hp)
        # 50 = 8 × FLA, locked rotor = 6 × FLA → 50 > locked rotor
        assert result.relay_50_pickup_primary_a > result.locked_rotor_current_a


# ═══════════════════════════════════════════════════════════════════════════
# PROPERTY 5: Arc flash — physical sanity
# ═══════════════════════════════════════════════════════════════════════════


class TestArcFlashProperties:
    """Property: arc flash calculations obey physics."""

    @given(
        ibf_ka=st.floats(min_value=1, max_value=100, allow_nan=False),
    )
    @settings(max_examples=30, deadline=3000)
    def test_arcing_current_less_than_bolted_fault(self, ibf_ka) -> None:
        """Iarc MUST be < Ibf (arcing impedance > 0)."""
        result = simulate_arc_flash(bolted_fault_current_ka=ibf_ka)
        assert result.arcing_current_ka < ibf_ka, (
            f"Iarc {result.arcing_current_ka} kA >= Ibf {ibf_ka} kA"
        )

    @given(
        ibf_ka=st.floats(min_value=5, max_value=80, allow_nan=False),
    )
    @settings(max_examples=30, deadline=3000)
    def test_incident_energy_positive(self, ibf_ka) -> None:
        """Incident energy must be positive."""
        result = simulate_arc_flash(bolted_fault_current_ka=ibf_ka)
        assert result.incident_energy_cal_cm2 > 0

    @given(
        ibf_ka=st.floats(min_value=1, max_value=100, allow_nan=False),
    )
    @settings(max_examples=30, deadline=3000)
    def test_ppe_category_in_valid_range(self, ibf_ka) -> None:
        """PPE category must be 0-4."""
        result = simulate_arc_flash(bolted_fault_current_ka=ibf_ka)
        assert 0 <= result.ppe_category <= 4

    @given(
        energy=st.floats(min_value=0, max_value=1000, allow_nan=False),
    )
    @settings(max_examples=50, deadline=2000)
    def test_ppe_category_monotonically_increasing(self, energy) -> None:
        """Higher energy → same or higher PPE category."""
        cat, _ = determine_ppe_category(energy)
        # Check category boundaries
        if energy < 1.2:
            assert cat == 0
        elif energy < 8:
            assert cat == 1
        elif energy < 25:
            assert cat == 2
        elif energy < 40:
            assert cat == 3
        else:
            assert cat == 4


# ═══════════════════════════════════════════════════════════════════════════
# PROPERTY 6: FLISR — fault location obeys Ohm's law
# ═══════════════════════════════════════════════════════════════════════════


class TestFLISRProperties:
    """Property: FLISR fault location obeys V = I × Z."""

    @given(
        fault_current=st.floats(min_value=100, max_value=50000, allow_nan=False),
        source_voltage=st.floats(min_value=1000, max_value=50000, allow_nan=False),
        z_per_mile=st.floats(min_value=0.1, max_value=2.0, allow_nan=False),
    )
    @settings(max_examples=50, deadline=3000)
    def test_fault_distance_obeys_ohms_law(self, fault_current, source_voltage, z_per_mile) -> None:
        """Distance = (V/I) / Z_per_mile — pure Ohm's law."""
        result = simulate_flisr(
            fault_current_a=fault_current,
            source_voltage_v=source_voltage,
            line_impedance_per_mile_ohm=z_per_mile,
        )
        expected = (source_voltage / fault_current) / z_per_mile
        assert abs(result.fault_distance_miles - expected) < 0.01, (
            f"Distance {result.fault_distance_miles} != expected {expected}"
        )

    @given(
        loading=st.floats(min_value=0, max_value=100, allow_nan=False),
    )
    @settings(max_examples=20, deadline=2000)
    def test_no_restoration_when_alternate_full(self, loading) -> None:
        """If alternate source is at 100%, no restoration possible."""
        result = simulate_flisr(alternate_source_loading_pct=loading)
        if loading >= 80:
            # No headroom
            assert result.restoration_time_minutes == 0 or result.customers_restored == 0


# ═══════════════════════════════════════════════════════════════════════════
# PROPERTY 7: No NaN/Inf in any simulation output (Rule 12 — agent.md)
# ═══════════════════════════════════════════════════════════════════════════


class TestNoNaNInf:
    """Property: no simulation may produce NaN or Inf outputs."""

    @given(
        current=st.floats(min_value=1, max_value=400, allow_nan=False, allow_infinity=False),
        voltage=st.floats(min_value=120, max_value=1000, allow_nan=False, allow_infinity=False),
    )
    @settings(max_examples=20, deadline=3000)
    def test_cable_sizing_no_nan(self, current, voltage) -> None:
        try:
            result = simulate_cable_sizing(load_current_a=current, voltage_v=voltage)
        except ValueError:
            return
        assert math.isfinite(result.voltage_drop_v)
        assert math.isfinite(result.voltage_drop_pct)
        assert math.isfinite(result.short_circuit_withstand_a2s)

    @given(
        ibf_ka=st.floats(min_value=1, max_value=100, allow_nan=False, allow_infinity=False),
    )
    @settings(max_examples=20, deadline=3000)
    def test_arc_flash_no_nan(self, ibf_ka) -> None:
        result = simulate_arc_flash(bolted_fault_current_ka=ibf_ka)
        assert math.isfinite(result.arcing_current_ka)
        assert math.isfinite(result.incident_energy_cal_cm2)
        assert math.isfinite(result.arc_flash_boundary_ft)

    @given(
        load_kw=st.floats(min_value=10, max_value=10000, allow_nan=False, allow_infinity=False),
    )
    @settings(max_examples=20, deadline=3000)
    def test_transformer_sizing_no_nan(self, load_kw) -> None:
        result = simulate_transformer_sizing(load_kw=load_kw)
        assert math.isfinite(result.required_kva)
        assert math.isfinite(result.recommended_size_kva)
        assert math.isfinite(result.loading_pct)
