"""
test_v17_life_safety_triad.py — Tests for V17 Life-Safety Triad
================================================================
Tests the three critical V17 modules:
  1. Battery Aging/Derating Auditor (NFPA 72 §10.6.7)
  2. Acoustic SPL Calculator with 3D barriers (NFPA 72 §18.4)
  3. ASET/RSET Tenability Calculator (NFPA 101 §9.3)

These tests verify that:
  - Temperature derating works correctly
  - Aging derating accounts for end-of-life capacity
  - Battery sizing fails when capacity is insufficient
  - Acoustic calculations use correct inverse square law
  - 3D distance is used (not 2D like consultant's code)
  - Barrier attenuation is applied correctly
  - ASET/RSET validation works with safety factors
  - Integration with release_gates.py works
"""

import sys
from pathlib import Path
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

import math
import pytest


# ============================================================================
# Battery Aging/Derating Tests
# ============================================================================

class TestBatteryTemperatureDerating:
    """Test temperature derating per IEEE 485 / manufacturer data."""

    def test_reference_temperature_no_derating(self):
        """At 25°C (reference), derating factor should be 1.0."""
        from fireai.core.battery_aging_derating import get_temperature_derating_factor
        assert get_temperature_derating_factor(25.0) == 1.0

    def test_freezing_derating(self):
        """At 0°C, battery loses ~28% capacity."""
        from fireai.core.battery_aging_derating import get_temperature_derating_factor
        factor = get_temperature_derating_factor(0.0)
        assert factor == 0.72  # Exact value from table

    def test_severe_cold_derating(self):
        """At -10°C, battery only has 60% capacity."""
        from fireai.core.battery_aging_derating import get_temperature_derating_factor
        assert get_temperature_derating_factor(-10.0) == 0.60

    def test_below_table_minimum(self):
        """Below -10°C, should use the minimum table value (0.60)."""
        from fireai.core.battery_aging_derating import get_temperature_derating_factor
        assert get_temperature_derating_factor(-20.0) == 0.60

    def test_hot_temperature_slight_gain(self):
        """V20.2 FIX: At 30°C, derating is capped at 1.00 (not 1.02).
        Elevated temperatures accelerate VRLA aging — any marginal capacity
        gain is offset by accelerated degradation. Per IEEE 1188 §5.3 and
        NFPA 72 §10.6.7, life-safety design must not overestimate capacity
        at high temperatures."""
        from fireai.core.battery_aging_derating import get_temperature_derating_factor
        assert get_temperature_derating_factor(30.0) == 1.00

    def test_interpolation_between_points(self):
        """Between data points, should interpolate."""
        from fireai.core.battery_aging_derating import get_temperature_derating_factor
        # Between 20°C (0.95) and 25°C (1.00)
        factor = get_temperature_derating_factor(22.5)
        assert 0.95 < factor < 1.00  # Should be between the two values


class TestBatteryAgingDerating:
    """Test aging derating per IEEE 1188."""

    def test_new_battery_no_aging_derating(self):
        """New installation (age=0) should return 1.0 (EOL handled separately)."""
        from fireai.core.battery_aging_derating import get_aging_derating_factor
        assert get_aging_derating_factor(current_age_years=0.0) == 1.0

    def test_eol_derating_constant(self):
        """End-of-life derating should be 80% (IEEE 1188)."""
        from fireai.core.battery_aging_derating import AGING_DERATING_EOL
        assert AGING_DERATING_EOL == 0.80

    def test_mid_life_derating(self):
        """At 2.5 years (mid-life), derating should be ~90%."""
        from fireai.core.battery_aging_derating import get_aging_derating_factor
        factor = get_aging_derating_factor(service_life_years=5, current_age_years=2.5)
        assert 0.85 < factor < 0.95  # Should be around 90%


class TestBatterySizing:
    """Test battery sizing calculations per NFPA 72 §10.6.7."""

    def test_adequate_battery_passes(self):
        """Battery with sufficient capacity should pass."""
        from fireai.core.battery_aging_derating import (
            size_battery, BatterySpec,
        )
        result = size_battery(
            standby_load_amps=0.5,
            alarm_load_amps=2.0,
            standby_hours=24.0,
            alarm_hours=0.083,
            battery=BatterySpec(amp_hour_20h=55.0, cells=6),
            min_temperature_c=25.0,
            safety_margin_pct=0.0,
        )
        # 0.5A * 24h + 2.0A * 0.083h = 12.0 + 0.166 = 12.166 Ah
        # At 25°C: derating = 1.0, aging = 0.80
        # Required = 12.166 / (1.0 * 0.80 * 0.90) ≈ 16.9 Ah
        # 55 Ah >> 16.9 Ah — should pass easily
        assert result.is_adequate

    def test_insufficient_battery_fails(self):
        """Battery with insufficient capacity should fail."""
        from fireai.core.battery_aging_derating import (
            size_battery, BatterySpec,
        )
        result = size_battery(
            standby_load_amps=3.0,
            alarm_load_amps=8.0,
            standby_hours=24.0,
            alarm_hours=0.5,
            battery=BatterySpec(amp_hour_20h=7.0, cells=6),
            min_temperature_c=0.0,  # Cold!
            safety_margin_pct=0.0,
        )
        # 3A * 24h + 8A * 0.5h = 72 + 4 = 76 Ah
        # At 0°C: temp_derating = 0.72, aging = 0.80, discharge = ~0.80
        # Required = 76 / (0.72 * 0.80 * 0.80) ≈ 165 Ah
        # 7 Ah << 165 Ah — should fail
        assert not result.is_adequate
        assert len(result.violations) > 0

    def test_cold_battery_loses_capacity(self):
        """Battery at 0°C should show lower usable capacity than at 25°C."""
        from fireai.core.battery_aging_derating import (
            size_battery, BatterySpec,
        )
        result_warm = size_battery(
            standby_load_amps=1.0,
            alarm_load_amps=3.0,
            battery=BatterySpec(amp_hour_20h=26.0, cells=6),
            min_temperature_c=25.0,
            safety_margin_pct=0.0,
        )
        result_cold = size_battery(
            standby_load_amps=1.0,
            alarm_load_amps=3.0,
            battery=BatterySpec(amp_hour_20h=26.0, cells=6),
            min_temperature_c=0.0,
            safety_margin_pct=0.0,
        )
        # Cold battery should require MORE capacity
        assert result_cold.required_ah > result_warm.required_ah

    def test_battery_spec_voltage(self):
        """BatterySpec should compute correct voltage."""
        from fireai.core.battery_aging_derating import BatterySpec
        bat_12v = BatterySpec(amp_hour_20h=26.0, cells=6)
        assert bat_12v.nominal_voltage == 12.0
        assert bat_12v.end_of_discharge_voltage == 10.5  # 6 * 1.75

        bat_24v = BatterySpec(amp_hour_20h=55.0, cells=12)
        assert bat_24v.nominal_voltage == 24.0
        assert bat_24v.end_of_discharge_voltage == 21.0

    def test_battery_auditor_class(self):
        """BatteryAuditor class interface should work."""
        from fireai.core.battery_aging_derating import BatteryAuditor, BatterySpec
        auditor = BatteryAuditor(
            battery=BatterySpec(amp_hour_20h=26.0, cells=6),
            min_temperature_c=20.0,
            safety_margin_pct=10.0,
        )
        result = auditor.audit(standby_load_amps=0.5, alarm_load_amps=2.0)
        assert result is not None
        assert hasattr(result, 'is_adequate')
        assert hasattr(result, 'required_ah')

    def test_battery_result_for_gate(self):
        """battery_result_for_gate should produce dict for release_gates Gate 8."""
        from fireai.core.battery_aging_derating import (
            size_battery, BatterySpec, battery_result_for_gate,
        )
        result = size_battery(
            standby_load_amps=0.5,
            alarm_load_amps=2.0,
            battery=BatterySpec(amp_hour_20h=26.0, cells=6),
        )
        gate_dict = battery_result_for_gate(result)
        assert "required_ah" in gate_dict
        assert "installed_ah" in gate_dict
        assert "is_adequate" in gate_dict
        assert gate_dict["required_ah"] == result.required_ah
        assert gate_dict["installed_ah"] == result.installed_ah

    def test_safety_margin_increases_required(self):
        """Safety margin should increase required capacity."""
        from fireai.core.battery_aging_derating import size_battery, BatterySpec
        no_margin = size_battery(
            standby_load_amps=1.0, alarm_load_amps=2.0,
            battery=BatterySpec(amp_hour_20h=26.0, cells=6),
            safety_margin_pct=0.0,
        )
        with_margin = size_battery(
            standby_load_amps=1.0, alarm_load_amps=2.0,
            battery=BatterySpec(amp_hour_20h=26.0, cells=6),
            safety_margin_pct=20.0,
        )
        assert with_margin.required_ah > no_margin.required_ah


# ============================================================================
# Acoustic SPL Calculator Tests
# ============================================================================

class TestAcousticSPLCalculator:
    """Test multi-speaker room SPL analysis with 3D barriers."""

    def test_basic_single_speaker_room(self):
        """Single speaker in a room should produce compliant SPL near speaker."""
        from fireai.core.acoustic_calculator import (
            AcousticSPLCalculator, Speaker, CheckPoint,
        )
        calc = AcousticSPLCalculator()
        result = calc.calculate_room_spl(
            room_id="R-101",
            occ_type="office_normal",
            speakers=[Speaker(x=5.0, y=5.0, z=2.8, rating_dba=95.0)],
            check_points=[CheckPoint(x=5.0, y=5.0, z=1.5, label="center")],
        )
        # Speaker at 2.8m height, listener at 1.5m = 1.3m vertical distance
        # Total distance ≈ 1.3m, which is within 3m ref distance
        # SPL should be very high at this distance
        assert result.worst_point_spl > 70.0

    def test_3d_distance_not_2d(self):
        """Calculator must use 3D distance (x,y,z), not 2D (x,y) like consultant's code."""
        from fireai.core.acoustic_calculator import (
            AcousticSPLCalculator, Speaker, CheckPoint,
        )
        calc = AcousticSPLCalculator()
        # Speaker at ceiling (z=3.0), listener at floor (z=0.0)
        # Same x,y → 2D distance would be 0, but 3D distance is 3.0m
        result = calc.calculate_room_spl(
            room_id="R-3D",
            occ_type="office_quiet",
            speakers=[Speaker(x=5.0, y=5.0, z=3.0, rating_dba=95.0)],
            check_points=[CheckPoint(x=5.0, y=5.0, z=0.0, label="floor")],
        )
        # 3D distance = 3.0m, SPL at 3m = 95 dBA (reference distance)
        # Required for office_quiet: 40 + 15 = 55 dBA
        # 95 dBA >> 55 dBA — should pass
        assert result.compliant
        assert result.worst_point_spl >= 90.0  # Very close to speaker

    def test_barrier_attenuation_reduces_spl(self):
        """Barrier should reduce SPL at check points."""
        from fireai.core.acoustic_calculator import (
            AcousticSPLCalculator, Speaker, CheckPoint, Barrier,
        )
        calc = AcousticSPLCalculator()
        # Without barrier
        result_no_barrier = calc.calculate_room_spl(
            room_id="R-no-barrier",
            occ_type="office_normal",
            speakers=[Speaker(x=5.0, y=5.0, z=2.8, rating_dba=95.0)],
            check_points=[CheckPoint(x=10.0, y=5.0, z=1.5)],
        )
        # With standard door barrier (-15 dB)
        result_with_barrier = calc.calculate_room_spl(
            room_id="R-barrier",
            occ_type="office_normal",
            speakers=[Speaker(x=5.0, y=5.0, z=2.8, rating_dba=95.0)],
            check_points=[CheckPoint(x=10.0, y=5.0, z=1.5)],
            barriers=[Barrier(barrier_type="standard_door")],
        )
        # SPL with barrier should be lower
        assert result_with_barrier.worst_point_spl < result_no_barrier.worst_point_spl

    def test_multiple_speakers_add_spl(self):
        """Multiple speakers should produce higher SPL than one (logarithmic addition)."""
        from fireai.core.acoustic_calculator import (
            AcousticSPLCalculator, Speaker, CheckPoint,
        )
        calc = AcousticSPLCalculator()
        # Single speaker
        result_single = calc.calculate_room_spl(
            room_id="R-single",
            occ_type="office_normal",
            speakers=[Speaker(x=3.0, y=5.0, z=2.8, rating_dba=90.0)],
            check_points=[CheckPoint(x=10.0, y=5.0, z=1.5)],
        )
        # Two speakers (same position = double power = +3 dB)
        result_double = calc.calculate_room_spl(
            room_id="R-double",
            occ_type="office_normal",
            speakers=[
                Speaker(x=3.0, y=5.0, z=2.8, rating_dba=90.0),
                Speaker(x=3.0, y=5.0, z=2.8, rating_dba=90.0),
            ],
            check_points=[CheckPoint(x=10.0, y=5.0, z=1.5)],
        )
        # Two identical sources at same position should add ~3 dB
        assert result_double.worst_point_spl > result_single.worst_point_spl
        # Should be approximately +3 dB
        diff = result_double.worst_point_spl - result_single.worst_point_spl
        assert 2.0 < diff < 4.0  # Approximately 3 dB

    def test_consultant_wrong_formula_detected(self):
        """Verify we use correct formula: 20*log10(d/d_ref), NOT 20*log10(d)."""
        from fireai.core.acoustic_calculator import calculate_spl_at_distance
        # At 3m (reference distance), there should be ZERO attenuation
        result = calculate_spl_at_distance(
            source_dba=95.0, target_distance_m=3.0, ref_distance_m=3.0,
            include_reverberant_field=False,
        )
        assert result.direct_attenuation_dB == pytest.approx(0.0, abs=0.01)
        assert result.effective_dba == pytest.approx(95.0, abs=0.01)

        # At 6m (2x reference), attenuation should be ~6 dB (not 15.6 dB)
        result_6m = calculate_spl_at_distance(
            source_dba=95.0, target_distance_m=6.0, ref_distance_m=3.0,
            include_reverberant_field=False,
        )
        # 20*log10(6/3) = 20*log10(2) = 6.02 dB
        assert result_6m.direct_attenuation_dB == pytest.approx(6.02, abs=0.1)

    def test_barrier_types(self):
        """Different barrier types should have different attenuation values."""
        from fireai.core.acoustic_calculator import BARRIER_ATTENUATION_DB, Barrier
        assert BARRIER_ATTENUATION_DB["standard_door"] == 15.0
        assert BARRIER_ATTENUATION_DB["fire_door"] == 25.0
        assert BARRIER_ATTENUATION_DB["concrete_wall"] == 45.0

        # Custom attenuation
        custom = Barrier(barrier_type="standard_door", attenuation_dba=20.0)
        assert custom.effective_attenuation_dba == 20.0  # Override


# ============================================================================
# ASET/RSET Tests
# ============================================================================

class TestASETRSETCalculator:
    """Test ASET/RSET tenability calculations per NFPA 101 §9.3."""

    def test_aset_from_smoke_fill_time(self):
        """ASET from smoke fill time should be reasonable."""
        from fireai.core.aset_rset_calculator import calculate_aset
        result = calculate_aset(
            smoke_fill_time_s=120.0,  # 2 minutes to reach detector
            room_height_m=3.0,
        )
        # ASET should be > smoke_fill_time (smoke still needs to descend to 1.8m)
        assert result.aset_seconds > 120.0
        assert result.aset_method == "smoke_fill_estimate"

    def test_aset_from_time_series(self):
        """ASET from time-series data should find exact untenable point."""
        from fireai.core.aset_rset_calculator import calculate_aset
        # Smoke layer at 2.5m at t=120s, 1.5m at t=300s
        series = [
            (0.0, 3.0), (60.0, 2.8), (120.0, 2.5),
            (180.0, 2.0), (240.0, 1.5), (300.0, 0.5),
        ]
        result = calculate_aset(smoke_layer_height_series=series, room_height_m=3.0)
        # ASET should be at t=240s (first time smoke below 1.8m... wait, 1.5m at 240s)
        # Actually 2.0m at 180s is still above 1.8m, and 1.5m at 240s is below
        assert result.aset_seconds > 0
        assert result.aset_method == "tenability_check"
        assert "smoke_layer" in result.limiting_factor

    def test_rset_calculation(self):
        """RSET should include premovement delay + travel time."""
        from fireai.core.aset_rset_calculator import calculate_rset
        result = calculate_rset(
            travel_distance_m=45.0,
            occupancy_type="business",
            is_sprinklered=True,
        )
        # Business premovement delay: 90s (design value)
        # Walking speed: 1.0 m/s
        # Travel time: 45/1.0 = 45s
        # RSET = 90 + 45 = 135s (before safety factor)
        assert result.premovement_delay_s == 90.0
        assert result.travel_time_s == 45.0
        assert result.rset_seconds == 135.0
        # With safety factor (standard 1.5, sprinklered → 1.25)
        assert result.safety_factor == 1.25

    def test_rset_healthcare_slower_speed(self):
        """Healthcare should have slower walking speed."""
        from fireai.core.aset_rset_calculator import calculate_rset
        result = calculate_rset(
            travel_distance_m=30.0,
            occupancy_type="healthcare",
        )
        # Healthcare design speed: 0.5 m/s
        assert result.walking_speed_mps == 0.5
        # Travel time: 30/0.5 = 60s
        assert result.travel_time_s == 60.0

    def test_aset_vs_rset_safe(self):
        """When ASET >> RSET, design should be safe."""
        from fireai.core.aset_rset_calculator import (
            calculate_aset, calculate_rset, validate_aset_vs_rset,
        )
        aset = calculate_aset(
            smoke_layer_height_series=[
                (0, 3.0), (60, 2.9), (120, 2.8), (300, 2.5), (600, 2.0),
            ],
            room_height_m=3.0,
        )
        rset = calculate_rset(
            travel_distance_m=30.0,
            occupancy_type="business",
            is_sprinklered=True,
        )
        validation = validate_aset_vs_rset(aset, rset)
        # ASET is ~600s, RSET with safety factor ~ 135*1.25 = 169s
        assert validation.is_safe

    def test_aset_vs_rset_unsafe(self):
        """When ASET < RSET, design should fail."""
        from fireai.core.aset_rset_calculator import (
            calculate_aset, calculate_rset, validate_aset_vs_rset,
        )
        # Very fast smoke fill
        aset = calculate_aset(
            smoke_layer_height_series=[
                (0, 3.0), (10, 2.5), (20, 1.5),
            ],
            room_height_m=3.0,
        )
        rset = calculate_rset(
            travel_distance_m=60.0,
            occupancy_type="healthcare",  # Slow speed
            is_sprinklered=False,
        )
        validation = validate_aset_vs_rset(aset, rset)
        # ASET ~20s, RSET with high safety factor >> 20s
        assert not validation.is_safe
        assert "FAIL" in validation.verdict

    def test_population_density_reduces_speed(self):
        """High population density should reduce walking speed."""
        from fireai.core.aset_rset_calculator import calculate_rset
        result_low = calculate_rset(
            travel_distance_m=30.0,
            occupancy_type="business",
            population_density=0.3,  # Low density
        )
        result_high = calculate_rset(
            travel_distance_m=30.0,
            occupancy_type="business",
            population_density=2.0,  # High density — crowded
        )
        # High density should result in slower speed → longer travel time
        assert result_high.walking_speed_mps < result_low.walking_speed_mps
        assert result_high.travel_time_s > result_low.travel_time_s


# ============================================================================
# Integration Test: Release Gates
# ============================================================================

class TestReleaseGateIntegration:
    """Test that V17 modules integrate correctly with release_gates.py."""

    def test_battery_gate_passes_with_adequate_battery(self):
        """Gate 8 should pass when battery is adequately sized."""
        from fireai.core.battery_aging_derating import (
            size_battery, BatterySpec, battery_result_for_gate,
        )
        from fireai.core.release_gates import verify_and_evaluate

        result = size_battery(
            standby_load_amps=0.5,
            alarm_load_amps=2.0,
            battery=BatterySpec(amp_hour_20h=55.0, cells=6),
            min_temperature_c=25.0,
        )
        gate_result = verify_and_evaluate(battery_result=battery_result_for_gate(result))
        assert gate_result["checks"]["battery_sized"] is True

    def test_battery_gate_fails_with_insufficient_battery(self):
        """Gate 8 should fail when battery is too small."""
        from fireai.core.battery_aging_derating import (
            size_battery, BatterySpec, battery_result_for_gate,
        )
        from fireai.core.release_gates import verify_and_evaluate

        result = size_battery(
            standby_load_amps=5.0,
            alarm_load_amps=15.0,
            battery=BatterySpec(amp_hour_20h=7.0, cells=6),
            min_temperature_c=0.0,
        )
        gate_result = verify_and_evaluate(battery_result=battery_result_for_gate(result))
        assert gate_result["checks"]["battery_sized"] is False

    def test_aset_rset_gate(self):
        """Gate 7 should work with ASET/RSET results."""
        from fireai.core.aset_rset_calculator import perform_aset_rset_analysis
        from fireai.core.release_gates import verify_and_evaluate

        aset_rset = perform_aset_rset_analysis(
            room_area_m2=100.0,
            room_height_m=3.0,
            travel_distance_m=30.0,
            occupancy_type="business",
            is_sprinklered=True,
        )
        gate_result = verify_and_evaluate(aset_rset_result=aset_rset)
        # Gate 7 should be in the result
        assert "aset_rset_valid" in gate_result["checks"]
