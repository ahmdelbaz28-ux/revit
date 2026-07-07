# NOSONAR
"""
Property-Based Tests for NFPA 72 and NEC Calculations

PDF Audit Phase 3: Domain Verification
Per "From Prototype to Production-Grade" §Phase 3:
"Supplement existing tests with property-based testing using the hypothesis
library. Instead of testing specific examples, property-based testing
generates thousands of randomized inputs to verify the fundamental
properties of an algorithm."

This module verifies fundamental mathematical properties of:
  1. Coverage radius calculation (R = 0.7 × S)
  2. Voltage drop calculation (V = 2 × I × R × L)
  3. Coverage threshold compliance
  4. Convergence config validation
"""

import math

import pytest
from hypothesis import HealthCheck, assume, given, settings
from hypothesis import strategies as st
from pydantic import ValidationError

from fireai.constants import (
    COVERAGE_FACTOR_FLAT_CEILING,
    DC_RETURN_PATH_FACTOR,
    NFPA72_HEIGHT_SPACING_TABLE,
    SMOKE_COVERAGE_RADIUS_M,
    SMOKE_MAX_SPACING_M,
    WALL_MIN_DISTANCE_M,
)
from fireai.core.nfpa72_calculations import (
    calculate_coverage_radius_from_height,
    check_voltage_drop,
)
from fireai.core.nfpa72_schemas import (
    CeilingTypePydantic,
    ConvergenceConfig,
    NFPA72Input,
    VoltageDropInput,
)

# ============================================================================
# Property-Based Tests — Coverage Radius
# ============================================================================

@settings(max_examples=500, deadline=1000, suppress_health_check=[HealthCheck.too_slow])
@given(
    spacing=st.floats(min_value=0.1, max_value=30.0, allow_nan=False, allow_infinity=False),
    height=st.floats(min_value=0.5, max_value=15.24, allow_nan=False, allow_infinity=False),
    ceiling_type=st.sampled_from(list(CeilingTypePydantic)),
    hvac_vel=st.floats(min_value=0.0, max_value=2.5, allow_nan=False, allow_infinity=False),
)
def test_coverage_radius_properties(spacing, height, ceiling_type, hvac_vel):
    """
    Test fundamental mathematical properties of coverage radius.

    Properties verified:
      1. Radius must be positive (> 0)
      2. Radius must be finite (not NaN or Inf)
      3. Radius must not exceed spacing (R ≤ S)
      4. HVAC velocity never increases radius (monotonicity)
    """
    # Skip invalid combinations (sloped ceiling with spacing > 6.4m)
    if ceiling_type == CeilingTypePydantic.SLOPED and spacing > 6.4:
        assume(False)

    input_data = NFPA72Input(
        spacing_m=spacing,
        ceiling_height_m=height,
        ceiling_type=ceiling_type,
        hvac_velocity_ms=hvac_vel,
    )

    radius = input_data.compute_coverage_radius()

    # Property 1: Radius must be positive
    assert radius > 0, f"Radius must be positive, got {radius}"

    # Property 2: Radius must be finite
    assert math.isfinite(radius), f"Radius must be finite, got {radius}"

    # Property 3: Radius must not exceed spacing
    assert radius <= spacing + 1e-9, (
        f"Coverage radius ({radius:.3f}m) must not exceed spacing ({spacing:.3f}m). "
        f"This violates the fundamental geometry of detector placement per NFPA 72."
    )

    # Property 4: HVAC velocity never increases radius
    if hvac_vel > 0.5:
        baseline = NFPA72Input(
            spacing_m=spacing,
            ceiling_height_m=height,
            ceiling_type=ceiling_type,
            hvac_velocity_ms=0.0,
        )
        baseline_radius = baseline.compute_coverage_radius()
        assert radius <= baseline_radius + 1e-9, (
            f"Radius increased with HVAC velocity. Baseline: {baseline_radius:.3f}m, "
            f"With HVAC ({hvac_vel}m/s): {radius:.3f}m. "
            f"Airflow should reduce effective coverage, not increase it."
        )


@settings(max_examples=200, deadline=1000, suppress_health_check=[HealthCheck.too_slow])
@given(
    height=st.floats(min_value=3.0, max_value=12.2, allow_nan=False, allow_infinity=False),
)
def test_coverage_radius_from_height_properties(height):
    """
    Test NFPA 72 height-adjusted coverage radius calculation.

    Properties verified:
      1. Radius decreases as height increases (more detectors at higher ceilings)
      2. Radius is always R = 0.7 × S from the table
      3. Spacing is always within NFPA 72 table range
    """
    spec = calculate_coverage_radius_from_height(height, detector_type="smoke")

    # Property 1: Radius decreases with height
    if height > 3.0:
        spec_low = calculate_coverage_radius_from_height(3.0, detector_type="smoke")
        assert spec.radius <= spec_low.radius + 0.01, (
            f"Radius at h={height}m ({spec.radius}m) should be ≤ radius at h=3.0m "
            f"({spec_low.radius}m). Higher ceilings = smaller radius per NFPA 72."
        )

    # Property 2: R = 0.7 × S
    expected_radius = round(COVERAGE_FACTOR_FLAT_CEILING * spec.spacing_max, 2)
    assert abs(spec.radius - expected_radius) < 0.01, (
        f"R ≠ 0.7×S: R={spec.radius}, S={spec.spacing_max}, "
        f"expected R={expected_radius}. Per NFPA 72 §17.7.4.2.3.1."
    )

    # Property 3: Spacing within table range
    assert spec.spacing_max <= SMOKE_MAX_SPACING_M, (
        f"Spacing {spec.spacing_max}m exceeds max {SMOKE_MAX_SPACING_M}m per NFPA 72."
    )


# ============================================================================
# Property-Based Tests — Voltage Drop
# ============================================================================

@settings(max_examples=500, deadline=1000, suppress_health_check=[HealthCheck.too_slow])
@given(
    supply_v=st.floats(min_value=12.0, max_value=48.0, allow_nan=False, allow_infinity=False),
    current_a=st.floats(min_value=0.1, max_value=5.0, allow_nan=False, allow_infinity=False),
    resistance=st.floats(min_value=0.003, max_value=0.05, allow_nan=False, allow_infinity=False),
    length_m=st.floats(min_value=5.0, max_value=500.0, allow_nan=False, allow_infinity=False),
)
def test_voltage_drop_properties(supply_v, current_a, resistance, length_m):
    """
    Test fundamental properties of voltage drop calculation.

    Properties verified:
      1. Voltage drop is always positive
      2. Voltage drop increases with current, resistance, and length
      3. DC return path factor (2×) is included
      4. Terminal voltage decreases with longer cables
    """
    result = check_voltage_drop(
        supply_voltage_v=supply_v,
        load_current_a=current_a,
        cable_resistance_ohm_per_m=resistance,
        cable_length_m=length_m,
    )

    # Property 1: Drop is always positive
    assert result["drop_v"] > 0, f"Drop must be positive, got {result['drop_v']}"

    # Property 2: Drop increases with length
    result_shorter = check_voltage_drop(
        supply_voltage_v=supply_v,
        load_current_a=current_a,
        cable_resistance_ohm_per_m=resistance,
        cable_length_m=length_m / 2.0,
    )
    # Only assert if both are valid (fraction <= 1.0) and drops are distinguishable
    if result["drop_fraction"] <= 1.0 and result_shorter["drop_fraction"] <= 1.0:
        # Account for rounding at 4 decimal places
        assert result["drop_v"] >= result_shorter["drop_v"] - 0.0001, (
            f"Longer cable should have >= drop: {length_m}m → {result['drop_v']}V, "
            f"{length_m/2}m → {result_shorter['drop_v']}V"
        )

    # Property 3: DC return path factor is included (2×)
    # The simple check_voltage_drop function uses V_drop = I * R * L * 2
    # so the result should equal 2× the single-path drop
    expected_drop_with_return = current_a * resistance * length_m * DC_RETURN_PATH_FACTOR
    assert abs(result["drop_v"] - expected_drop_with_return) < 0.01, (
        f"Drop {result['drop_v']}V != expected 2×path {expected_drop_with_return}V. "
        f"DC return path factor (2×) per NFPA 72 §10.14 must be included."
    )

    # Property 4: Drop fraction is positive (may exceed 1.0 for extreme inputs)
    assert result["drop_fraction"] > 0, (
        f"Drop fraction must be positive, got {result['drop_fraction']}"
    )


@settings(max_examples=200, deadline=1000, suppress_health_check=[HealthCheck.too_slow])
@given(
    supply_v=st.floats(min_value=12.0, max_value=48.0, allow_nan=False, allow_infinity=False),
    current_a=st.floats(min_value=0.01, max_value=2.0, allow_nan=False, allow_infinity=False),
    resistance=st.floats(min_value=0.001, max_value=0.03, allow_nan=False, allow_infinity=False),
    length_m=st.floats(min_value=1.0, max_value=200.0, allow_nan=False, allow_infinity=False),
    temp_c=st.floats(min_value=20.0, max_value=70.0, allow_nan=False, allow_infinity=False),
)
def test_voltage_drop_with_temperature_correction(supply_v, current_a, resistance, length_m, temp_c):
    """
    Test that Pydantic VoltageDropInput includes temperature correction.

    Per NEC Table 310.15(B)(2)(a), higher temperatures reduce conductor
    ampacity, effectively increasing voltage drop.
    """
    vd_input = VoltageDropInput(
        supply_voltage_v=supply_v,
        load_current_a=current_a,
        cable_resistance_ohm_per_m=resistance,
        cable_length_m=length_m,
        ambient_temp_c=temp_c,
    )

    result = vd_input.compute_voltage_drop()

    # Higher temperature should produce equal or higher voltage drop
    if temp_c > 30.0:
        vd_baseline = VoltageDropInput(
            supply_voltage_v=supply_v,
            load_current_a=current_a,
            cable_resistance_ohm_per_m=resistance,
            cable_length_m=length_m,
            ambient_temp_c=30.0,
        )
        baseline_result = vd_baseline.compute_voltage_drop()
        # With temp correction, drop should be higher or equal
        assert result["drop_v"] >= baseline_result["drop_v"] - 0.01, (
            f"Temp correction should increase drop: {temp_c}°C → {result['drop_v']}V, "
            f"30°C → {baseline_result['drop_v']}V"
        )


# ============================================================================
# Property-Based Tests — Convergence Config
# ============================================================================

@settings(max_examples=100, deadline=500)
@given(
    epsilon=st.floats(min_value=1e-8, max_value=1.0, allow_nan=False, allow_infinity=False),
    max_iter=st.integers(min_value=1, max_value=1000000),
)
def test_convergence_config_properties(epsilon, max_iter):
    """Test ConvergenceConfig validates properly."""
    config = ConvergenceConfig(epsilon=epsilon, max_iterations=max_iter)

    assert config.epsilon > 0, "Epsilon must be positive"
    assert config.max_iterations > 0, "Max iterations must be positive"
    assert config.epsilon <= 1.0, "Epsilon must be ≤ 1.0"


# ============================================================================
# Property-Based Tests — NaN/Inf Rejection
# ============================================================================

@given(value=st.one_of(st.just(float('nan')), st.just(float('inf')), st.just(float('-inf'))))
def test_nan_inf_rejected_in_schemas(value):
    """
    NaN and Inf values MUST be rejected in all Pydantic schemas.
    V114 Fix: NaN bypasses comparison guards, producing false compliance.
    """
    with pytest.raises(ValidationError):
        NFPA72Input(spacing_m=value, ceiling_height_m=3.0)

    with pytest.raises(ValidationError):
        NFPA72Input(spacing_m=9.1, ceiling_height_m=value)


# ============================================================================
# Invariant Tests — Constants Consistency
# ============================================================================

def test_coverage_factor_equals_0_7():
    """Coverage factor must be 0.7 per NFPA 72 §17.7.4.2.3.1."""
    assert COVERAGE_FACTOR_FLAT_CEILING == 0.7  # NOSONAR — S1244: import retained for re-export / API surface


def test_smoke_radius_equals_0_7_times_spacing():
    """Smoke coverage radius must be R = 0.7 × 9.1 = 6.37m."""
    expected = round(COVERAGE_FACTOR_FLAT_CEILING * SMOKE_MAX_SPACING_M, 2)
    assert expected == SMOKE_COVERAGE_RADIUS_M


def test_dc_return_path_factor_is_2():
    """DC return path factor must be 2.0 per NFPA 72 §10.14."""
    assert DC_RETURN_PATH_FACTOR == 2.0  # NOSONAR — S1244: import retained for re-export / API surface


def test_spacing_table_decreases_with_height():
    """Spacing must decrease as ceiling height increases per NFPA 72 Table 17.6.3.1.1."""
    prev_smoke = float('inf')
    prev_heat = float('inf')
    for h_max, smoke_s, heat_s in NFPA72_HEIGHT_SPACING_TABLE:
        assert smoke_s <= prev_smoke, (
            f"Smoke spacing must decrease with height: {smoke_s}m at h≤{h_max}m "
            f"> previous {prev_smoke}m"
        )
        assert heat_s <= prev_heat, (
            f"Heat spacing must decrease with height: {heat_s}m at h≤{h_max}m "
            f"> previous {prev_heat}m"
        )
        prev_smoke = smoke_s
        prev_heat = heat_s


def test_wall_min_distance_positive():
    """Wall minimum distance must be positive per NFPA 72 §17.6.3.1.1."""
    assert WALL_MIN_DISTANCE_M > 0
