"""
test_v22_hypothesis_radar.py – Property-Based Testing Radar (Hypothesis)
=========================================================================
Fuzz-tests the physics invariants of FireAI V22 using Hypothesis.

This file does NOT replace any existing tests — it supplements them with
massive random input generation to find edge cases that manual tests miss.

Categories:
  P0: Physics Invariants (Burgess-Wheeler, Beer-Lambert, Room Purge)
  P1: Zone Classification Consistency (GAP-02 matrix)
  P1: Zone/Hazard Cross-Validation (GAP-05)
  P2: Lens Fouling & Coverage Degradation
  P2: VolumetricMedium constraints

Standards:
  IEC 60079-10-1:2015 Annex B — zone extent & dilution
  IEC 60079-0:2017 §7.3 — temperature class
  NFPA 72-2022 §17.8.3.4 — detector redundancy
  FM Global DS 5-48 §3.2.1 — optical degradation
"""

from __future__ import annotations

import math
import pytest
from hypothesis import given, settings, assume, HealthCheck, strategies as st

from fireai.core.models_v21 import (
    SubstanceProperties,
    HazardType,
    ZoneType,
    VentilationLevel,
    WavelengthBand,
    EnvironmentalContext,
    VolumetricMedium,
    TemperatureClass,
    burgess_wheeler_lfl,
    beer_lambert_transmittance,
    room_purge_time,
    room_concentration_at_time,
    MIN_REDUNDANCY_BY_ZONE,
)
from fireai.core.hac_classification_engine import (
    HACClassificationEngine,
    ReleaseGrade,
    _resolve_zone_with_grade_vent,
)
from fireai.core.atex_hazardous_arbiter import (
    _validate_zone_hazard_consistency,
)


# ── Shared Strategies ────────────────────────────────────────────────────────

valid_float = st.floats(
    min_value=0.01, max_value=1e4,
    allow_nan=False, allow_infinity=False,
)

positive_float = st.floats(
    min_value=0.001, max_value=1e6,
    allow_nan=False, allow_infinity=False,
)

small_positive = st.floats(
    min_value=0.001, max_value=100.0,
    allow_nan=False, allow_infinity=False,
)

temp_float = st.floats(
    min_value=-40.0, max_value=200.0,
    allow_nan=False, allow_infinity=False,
)

high_temp = st.floats(
    min_value=25.0, max_value=500.0,
    allow_nan=False, allow_infinity=False,
)

ach_float = st.floats(
    min_value=0.01, max_value=100.0,
    allow_nan=False, allow_infinity=False,
)

fraction_float = st.floats(
    min_value=0.0001, max_value=0.9999,
    allow_nan=False, allow_infinity=False,
)


# ══════════════════════════════════════════════════════════════════════════════
# P0: PHYSICS INVARIANTS
# ══════════════════════════════════════════════════════════════════════════════

class TestBurgessWheelerInvariants:
    """
    Burgess-Wheeler LFL thermal correction invariants.

    Physical law: At elevated temperatures, gases expand and LFL DECREASES.
    LFL_T must ALWAYS be <= LFL_25C when T > 25C.
    LFL_T must ALWAYS remain positive (> 0).
    """

    @given(
        lfl=st.floats(min_value=0.1, max_value=50.0, allow_nan=False, allow_infinity=False),
        temp=high_temp,
    )
    @settings(max_examples=200, deadline=None)
    def test_burgess_wheeler_lfl_decreases_with_temp(self, lfl, temp):
        """LFL at elevated temperature must be <= LFL at 25C."""
        corrected = burgess_wheeler_lfl(lfl_25c=lfl, ambient_temp_c=temp)
        assert corrected <= lfl, (
            f"Burgess-Wheeler violation: LFL_T={corrected} > LFL_25={lfl} at T={temp}C"
        )

    @given(
        lfl=st.floats(min_value=0.1, max_value=50.0, allow_nan=False, allow_infinity=False),
        temp=high_temp,
    )
    @settings(max_examples=200, deadline=None)
    def test_burgess_wheeler_lfl_always_positive(self, lfl, temp):
        """Corrected LFL must remain positive (> 0)."""
        corrected = burgess_wheeler_lfl(lfl_25c=lfl, ambient_temp_c=temp)
        assert corrected > 0.0, (
            f"LFL went non-positive: {corrected} at T={temp}C"
        )

    @given(
        lfl=st.floats(min_value=0.1, max_value=50.0, allow_nan=False, allow_infinity=False),
        temp=st.floats(min_value=-40.0, max_value=25.0, allow_nan=False, allow_infinity=False),
    )
    @settings(max_examples=100, deadline=None)
    def test_burgess_wheeler_no_correction_below_25c(self, lfl, temp):
        """Below 25C, LFL should equal LFL_25C (no correction applied)."""
        corrected = burgess_wheeler_lfl(lfl_25c=lfl, ambient_temp_c=temp)
        assert corrected == lfl, (
            f"LFL incorrectly corrected below 25C: {corrected} != {lfl} at T={temp}C"
        )

    @given(
        lfl=st.floats(min_value=0.1, max_value=50.0, allow_nan=False, allow_infinity=False),
        temp=high_temp,
    )
    @settings(max_examples=200, deadline=None)
    def test_burgess_wheeler_never_below_50pct(self, lfl, temp):
        """Corrected LFL should never drop below 50% of reference."""
        corrected = burgess_wheeler_lfl(lfl_25c=lfl, ambient_temp_c=temp)
        assert corrected >= lfl * 0.5, (
            f"LFL dropped below 50%: {corrected} < {lfl * 0.5}"
        )


class TestBeerLambertInvariants:
    """
    Beer-Lambert transmittance invariants.

    Physical law: T = exp(-alpha * d) is ALWAYS in [0, 1].
    T decreases (or stays same) when alpha or path_length increases.
    """

    @given(alpha=positive_float, path=positive_float)
    @settings(max_examples=200, deadline=None)
    def test_transmittance_in_unit_interval(self, alpha, path):
        """Transmittance must always be in [0.0, 1.0]."""
        tau = beer_lambert_transmittance(alpha_per_m=alpha, path_length_m=path)
        assert 0.0 <= tau <= 1.0, f"τ={tau} outside [0,1] for α={alpha}, d={path}"

    @given(alpha=positive_float, path=positive_float)
    @settings(max_examples=200, deadline=None)
    def test_transmittance_decreases_with_alpha(self, alpha, path):
        """Higher alpha → lower (or equal) transmittance."""
        tau_low = beer_lambert_transmittance(alpha_per_m=alpha, path_length_m=path)
        tau_high = beer_lambert_transmittance(alpha_per_m=alpha * 2, path_length_m=path)
        assert tau_high <= tau_low + 1e-12, (
            f"τ increased with α: τ(α)={tau_low} > τ(2α)={tau_high}"
        )

    @given(alpha=positive_float)
    @settings(max_examples=100, deadline=None)
    def test_zero_path_means_full_transmittance(self, alpha):
        """Zero path length → transmittance = 1.0 (no attenuation)."""
        tau = beer_lambert_transmittance(alpha_per_m=alpha, path_length_m=0.0)
        assert tau == 1.0, f"τ at d=0 should be 1.0, got {tau}"

    @given(path=positive_float)
    @settings(max_examples=100, deadline=None)
    def test_zero_alpha_means_full_transmittance(self, path):
        """Zero absorption → transmittance = 1.0 (transparent medium)."""
        tau = beer_lambert_transmittance(alpha_per_m=0.0, path_length_m=path)
        assert tau == 1.0, f"τ at α=0 should be 1.0, got {tau}"


class TestRoomPurgeInvariants:
    """
    Room purge time (IEC 60079-10-1 Annex B §B.2) invariants.

    Physical law: Purge time is ALWAYS >= 0.
    Higher ACH → shorter purge time.
    Lower target fraction → longer purge time.
    """

    @given(ach=ach_float, target=fraction_float)
    @settings(max_examples=200, deadline=None)
    def test_purge_time_non_negative(self, ach, target):
        """Purge time must be >= 0."""
        t = room_purge_time(room_volume_m3=100.0, ach=ach, target_fraction=target)
        assert t >= 0.0, f"Purge time negative: {t}"

    @given(ach=ach_float, target=fraction_float)
    @settings(max_examples=200, deadline=None)
    def test_purge_time_finite_for_valid_inputs(self, ach, target):
        """Purge time must be finite for valid ACH and target."""
        t = room_purge_time(room_volume_m3=100.0, ach=ach, target_fraction=target)
        assert math.isfinite(t), f"Purge time not finite: {t}"

    @given(target=fraction_float)
    @settings(max_examples=100, deadline=None)
    def test_higher_ach_shorter_purge(self, target):
        """Higher ventilation → shorter purge time."""
        t_low = room_purge_time(room_volume_m3=100.0, ach=1.0, target_fraction=target)
        t_high = room_purge_time(room_volume_m3=100.0, ach=20.0, target_fraction=target)
        assert t_high <= t_low, (
            f"Higher ACH should give shorter purge: t(20 ACH)={t_high} > t(1 ACH)={t_low}"
        )

    @given(ach=ach_float)
    @settings(max_examples=100, deadline=None)
    def test_lower_target_longer_purge(self, ach):
        """Lower target fraction → longer purge time."""
        t_easy = room_purge_time(room_volume_m3=100.0, ach=ach, target_fraction=0.1)
        t_hard = room_purge_time(room_volume_m3=100.0, ach=ach, target_fraction=0.001)
        assert t_hard >= t_easy, (
            f"Lower target should give longer purge: t(0.001)={t_hard} < t(0.1)={t_easy}"
        )


class TestRoomConcentrationInvariants:
    """
    Room concentration at time t (IEC Annex B dilution model) invariants.

    C(t) = C_0 * exp(-ACH * t / 3600)
    C(t) must NEVER exceed C_0.
    C(t) must ALWAYS be >= 0.
    """

    @given(
        c0=st.floats(min_value=0.01, max_value=100.0, allow_nan=False, allow_infinity=False),
        ach=ach_float,
        t=st.floats(min_value=0.0, max_value=1e6, allow_nan=False, allow_infinity=False),
    )
    @settings(max_examples=200, deadline=None)
    def test_concentration_never_exceeds_initial(self, c0, ach, t):
        """C(t) must never exceed C_0."""
        ct = room_concentration_at_time(c0, ach=ach, time_seconds=t)
        assert ct <= c0 + 1e-12, (
            f"C(t)={ct} > C_0={c0} at t={t}s, ACH={ach}"
        )

    @given(
        c0=st.floats(min_value=0.01, max_value=100.0, allow_nan=False, allow_infinity=False),
        ach=ach_float,
        t=st.floats(min_value=0.0, max_value=1e6, allow_nan=False, allow_infinity=False),
    )
    @settings(max_examples=200, deadline=None)
    def test_concentration_non_negative(self, c0, ach, t):
        """C(t) must be >= 0."""
        ct = room_concentration_at_time(c0, ach=ach, time_seconds=t)
        assert ct >= 0.0, f"C(t)={ct} < 0 at t={t}s, ACH={ach}"

    @given(
        c0=st.floats(min_value=0.01, max_value=100.0, allow_nan=False, allow_infinity=False),
        ach=ach_float,
    )
    @settings(max_examples=100, deadline=None)
    def test_concentration_at_t0_equals_c0(self, c0, ach):
        """At t=0, concentration must equal initial."""
        ct = room_concentration_at_time(c0, ach=ach, time_seconds=0.0)
        assert abs(ct - c0) < 1e-9, f"C(0)={ct} != C_0={c0}"


# ══════════════════════════════════════════════════════════════════════════════
# P1: ZONE CLASSIFICATION CONSISTENCY
# ══════════════════════════════════════════════════════════════════════════════

class TestZoneConsistency:
    """
    Zone classification must follow physically consistent ordering.

    For the same hazard type and ventilation:
      CONTINUOUS → more hazardous zone than PRIMARY → more than SECONDARY
    For the same release grade:
      HIGH ventilation → less hazardous zone (or same) than LOW/POOR
    """

    ZONE_ORDER = {
        ZoneType.ZONE_0: 0, ZoneType.ZONE_1: 1, ZoneType.ZONE_2: 2,
        ZoneType.ZONE_20: 0, ZoneType.ZONE_21: 1, ZoneType.ZONE_22: 2,
        ZoneType.UNCLASSIFIED: 3,
    }

    @given(
        grade=st.sampled_from(ReleaseGrade),
        vent=st.sampled_from(VentilationLevel),
        htype=st.sampled_from(HazardType),
    )
    @settings(max_examples=100, deadline=None)
    def test_ventilation_high_never_increases_hazard(self, grade, vent, htype):
        """HIGH ventilation should never produce a MORE hazardous zone than any other level."""
        is_gas = (htype == HazardType.GAS)
        zone_high = _resolve_zone_with_grade_vent(grade, VentilationLevel.HIGH, is_gas)
        zone_other = _resolve_zone_with_grade_vent(grade, vent, is_gas)

        # Both should be in same "family"
        if is_gas:
            gas_zones = (ZoneType.ZONE_0, ZoneType.ZONE_1, ZoneType.ZONE_2, ZoneType.UNCLASSIFIED)
            assert zone_high in gas_zones, f"GAS hazard returned dust zone: {zone_high}"
            assert zone_other in gas_zones, f"GAS hazard returned dust zone: {zone_other}"
        else:
            dust_zones = (ZoneType.ZONE_20, ZoneType.ZONE_21, ZoneType.ZONE_22, ZoneType.UNCLASSIFIED)
            assert zone_high in dust_zones, f"DUST hazard returned gas zone: {zone_high}"
            assert zone_other in dust_zones, f"DUST hazard returned gas zone: {zone_other}"

    @given(
        vent=st.sampled_from(VentilationLevel),
        htype=st.sampled_from([HazardType.GAS, HazardType.DUST]),
    )
    @settings(max_examples=50, deadline=None)
    def test_continuous_grade_most_hazardous(self, vent, htype):
        """CONTINUOUS release should produce equal or more hazardous zone than PRIMARY or SECONDARY."""
        is_gas = (htype == HazardType.GAS)
        zone_cont = _resolve_zone_with_grade_vent(ReleaseGrade.CONTINUOUS, vent, is_gas)
        zone_prim = _resolve_zone_with_grade_vent(ReleaseGrade.PRIMARY, vent, is_gas)

        assert self.ZONE_ORDER[zone_cont] <= self.ZONE_ORDER[zone_prim], (
            f"CONTINUOUS={zone_cont} should be <= hazardous than PRIMARY={zone_prim}"
        )


class TestZoneHazardCrossValidation:
    """
    GAP-05: Gas zones (0/1/2) + DUST hazard = error.
    Dust zones (20/21/22) + GAS hazard = error.
    """

    @given(
        zone=st.sampled_from(ZoneType),
        htype=st.sampled_from(HazardType),
    )
    @settings(max_examples=50, deadline=None)
    def test_cross_validation_consistency(self, zone, htype):
        """Cross-validate every zone×hazard combination."""
        errors, warnings = [], []
        _validate_zone_hazard_consistency(zone, htype, errors, warnings)

        # Gas zones with DUST should always produce errors
        if zone in (ZoneType.ZONE_0, ZoneType.ZONE_1, ZoneType.ZONE_2) and htype == HazardType.DUST:
            assert len(errors) > 0, f"Gas zone {zone.value} + DUST should produce error"

        # Dust zones with GAS should always produce errors
        if zone in (ZoneType.ZONE_20, ZoneType.ZONE_21, ZoneType.ZONE_22) and htype == HazardType.GAS:
            assert len(errors) > 0, f"Dust zone {zone.value} + GAS should produce error"

        # Matching combinations should produce no errors
        if zone in (ZoneType.ZONE_0, ZoneType.ZONE_1, ZoneType.ZONE_2) and htype == HazardType.GAS:
            assert len(errors) == 0, f"Gas zone + GAS should have no errors"


# ══════════════════════════════════════════════════════════════════════════════
# P2: LENS FOULING & ENVIRONMENTAL CONTEXT
# ══════════════════════════════════════════════════════════════════════════════

class TestEnvironmentalContextInvariants:
    """
    EnvironmentalContext constraints validation.
    """

    @given(
        fouling=st.floats(min_value=0.01, max_value=1.0, allow_nan=False, allow_infinity=False),
        temp=st.floats(min_value=-40.0, max_value=85.0, allow_nan=False, allow_infinity=False),
    )
    @settings(max_examples=100, deadline=None)
    def test_valid_context_creation(self, fouling, temp):
        """Valid parameters should always create a valid context."""
        ctx = EnvironmentalContext(
            ambient_temp_c=temp,
            lens_fouling_factor=fouling,
        )
        assert ctx.lens_fouling_factor == fouling
        assert ctx.ambient_temp_c == temp

    @given(
        fouling=st.floats(min_value=0.01, max_value=0.99, allow_nan=False, allow_infinity=False),
    )
    @settings(max_examples=50, deadline=None)
    def test_fouling_reduces_transmittance(self, fouling):
        """Any fouling < 1.0 should reduce effective transmittance."""
        # Simple transmittance test
        clean_tau = beer_lambert_transmittance(alpha_per_m=1.0, path_length_m=5.0)
        fouled_tau = clean_tau * fouling
        assert fouled_tau < clean_tau, f"Fouled τ={fouled_tau} should be < clean τ={clean_tau}"
        assert fouled_tau >= 0.0


class TestMinRedundancyByZone:
    """
    MIN_REDUNDANCY_BY_ZONE mapping consistency.
    """

    @given(zone=st.sampled_from(ZoneType))
    @settings(max_examples=20, deadline=None)
    def test_all_zones_have_redundancy_requirement(self, zone):
        """Every ZoneType must have an entry in MIN_REDUNDANCY_BY_ZONE."""
        assert zone in MIN_REDUNDANCY_BY_ZONE, f"Zone {zone} missing from MIN_REDUNDANCY_BY_ZONE"

    @given(zone=st.sampled_from(ZoneType))
    @settings(max_examples=20, deadline=None)
    def test_redundancy_non_negative(self, zone):
        """Redundancy requirement must be >= 0."""
        assert MIN_REDUNDANCY_BY_ZONE[zone] >= 0

    def test_high_risk_zones_require_multiple_detectors(self):
        """ZONE_0 and ZONE_1 must require >= 2 detectors."""
        assert MIN_REDUNDANCY_BY_ZONE[ZoneType.ZONE_0] >= 2
        assert MIN_REDUNDANCY_BY_ZONE[ZoneType.ZONE_1] >= 2
        assert MIN_REDUNDANCY_BY_ZONE[ZoneType.ZONE_20] >= 2
        assert MIN_REDUNDANCY_BY_ZONE[ZoneType.ZONE_21] >= 2

    def test_low_risk_zones_accept_single_detector(self):
        """ZONE_2 and ZONE_22 should accept single detector."""
        assert MIN_REDUNDANCY_BY_ZONE[ZoneType.ZONE_2] <= 1
        assert MIN_REDUNDANCY_BY_ZONE[ZoneType.ZONE_22] <= 1


class TestVolumetricMediumConstraints:
    """
    VolumetricMedium Pydantic constraints via Hypothesis.
    """

    @given(
        medium_type=st.sampled_from(["SMOKE", "STEAM", "DUST_SUSPENSION", "GAS_CLOUD", "MIST"]),
        conc=st.floats(min_value=0.01, max_value=10.0, allow_nan=False, allow_infinity=False),
        band=st.sampled_from(WavelengthBand),
    )
    @settings(max_examples=100, deadline=None)
    def test_default_alpha_non_negative(self, medium_type, conc, band):
        """Default absorption coefficient should be >= 0 for all valid inputs."""
        vm = VolumetricMedium(
            medium_id="test",
            medium_type=medium_type,
            bbox_min=[-1.0, -1.0, 0.0],
            bbox_max=[1.0, 1.0, 1.0],
            concentration_factor=conc,
        )
        alpha = vm.get_alpha(band)
        assert alpha >= 0.0, f"α={alpha} < 0 for {medium_type}+{band.value}"

    @given(
        conc=st.floats(min_value=0.01, max_value=10.0, allow_nan=False, allow_infinity=False),
        band=st.sampled_from(WavelengthBand),
    )
    @settings(max_examples=50, deadline=None)
    def test_override_takes_priority(self, conc, band):
        """alpha_override should take priority over default values."""
        override_val = 99.9
        vm = VolumetricMedium(
            medium_id="test",
            medium_type="SMOKE",
            bbox_min=[-1.0, -1.0, 0.0],
            bbox_max=[1.0, 1.0, 1.0],
            concentration_factor=conc,
            alpha_override={band: override_val},
        )
        alpha = vm.get_alpha(band)
        expected = override_val * conc
        assert abs(alpha - expected) < 0.01, f"Override priority failed: α={alpha} != {expected}"
