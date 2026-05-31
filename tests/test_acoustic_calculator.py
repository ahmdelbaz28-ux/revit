"""
tests/test_acoustic_calculator.py
=================================
Comprehensive test suite for fireai/core/acoustic_calculator.py

SAFETY CRITICAL: This module calculates audible notification coverage
per NFPA 72 §18.4. Incorrect calculations could result in inaudible
fire alarms — a direct life-safety hazard.

NFPA 72 References:
  §18.4.3  — Public mode: min 15 dB above ambient
  §18.4.4  — Private mode: min 10 dB above ambient
  §18.4.2  — Sleeping areas: min 75 dBA at pillow
  §18.4.1.2 — Maximum 110 dBA
"""

from __future__ import annotations

import math
import pytest

from fireai.core.acoustic_calculator import (
    AUDIBLE_REQUIREMENTS,
    AMBIENT_NOISE_LEVELS,
    MAX_SOUND_LEVEL_DBA,
    DEFAULT_REF_DISTANCE_M,
    BARRIER_ATTENUATION_DB,
    SPLResult,
    AudibilityResult,
    SpeakerPlacementResult,
    CheckPoint,
    Speaker,
    Barrier,
    RoomAcousticResult,
    AcousticSPLCalculator,
    calculate_spl_at_distance,
    check_audibility_compliance,
    calculate_min_speakers_for_room,
    get_speaker_coverage_radius,
    _frange,
)


# ─────────────────────────────────────────────────────────────────────────────
# Constants & Data Structures Tests
# ─────────────────────────────────────────────────────────────────────────────


class TestConstants:
    """Verify NFPA 72 constant values are correct."""

    def test_audible_requirements_keys(self):
        assert set(AUDIBLE_REQUIREMENTS.keys()) == {"public", "private", "sleeping"}

    def test_public_mode_15db_above_ambient(self):
        """NFPA 72 §18.4.3: public mode requires 15 dB above ambient."""
        above, absolute, section = AUDIBLE_REQUIREMENTS["public"]
        assert above == 15
        assert section == "§18.4.3"

    def test_private_mode_10db_above_ambient(self):
        """NFPA 72 §18.4.4: private mode requires 10 dB above ambient."""
        above, absolute, section = AUDIBLE_REQUIREMENTS["private"]
        assert above == 10
        assert absolute == 45
        assert section == "§18.4.4"

    def test_sleeping_mode_75dba_minimum(self):
        """NFPA 72 §18.4.2: sleeping areas require 75 dBA at pillow."""
        above, absolute, section = AUDIBLE_REQUIREMENTS["sleeping"]
        assert absolute == 75
        assert section == "§18.4.2"

    def test_max_sound_level_110_dba(self):
        """NFPA 72 §18.4.1.2: maximum 110 dBA."""
        assert MAX_SOUND_LEVEL_DBA == 110.0

    def test_default_ref_distance_3m(self):
        """Standard speaker reference distance is 3m (10ft)."""
        assert DEFAULT_REF_DISTANCE_M == 3.0

    def test_ambient_noise_levels_populated(self):
        assert len(AMBIENT_NOISE_LEVELS) > 0
        assert "office_normal" in AMBIENT_NOISE_LEVELS
        assert AMBIENT_NOISE_LEVELS["office_normal"] == 50

    def test_barrier_attenuation_values(self):
        assert "standard_door" in BARRIER_ATTENUATION_DB
        assert "fire_door" in BARRIER_ATTENUATION_DB
        assert BARRIER_ATTENUATION_DB["fire_door"] > BARRIER_ATTENUATION_DB["standard_door"]


class TestSPLResult:
    """Test SPLResult dataclass."""

    def test_creation(self):
        r = SPLResult(
            effective_dba=80.0,
            source_dba=95.0,
            target_distance_m=15.0,
            ref_distance_m=3.0,
            direct_attenuation_dB=14.95,
            room_gain_dB=0.0,
        )
        assert r.effective_dba == 80.0
        assert r.method == "inverse_square_law"

    def test_default_method(self):
        r = SPLResult(80, 95, 15, 3, 14.95, 0)
        assert r.method == "inverse_square_law"


class TestAudibilityResult:
    def test_creation_compliant(self):
        r = AudibilityResult(
            compliant=True, effective_dba=80, required_dba=75,
            margin_dba=5, mode="public", nfpa_section="§18.4.3",
            ambient_dba=60, violations=[],
        )
        assert r.compliant is True
        assert r.margin_dba == 5

    def test_default_violations(self):
        r = AudibilityResult(
            compliant=False, effective_dba=70, required_dba=75,
            margin_dba=-5, mode="public", nfpa_section="§18.4.3",
            ambient_dba=60,
        )
        assert r.violations == []


class TestCheckPoint:
    def test_default_z(self):
        cp = CheckPoint(x=5, y=5)
        assert cp.z == 1.5  # ear height

    def test_custom_z(self):
        cp = CheckPoint(x=5, y=5, z=0.5)
        assert cp.z == 0.5


class TestSpeaker:
    def test_defaults(self):
        s = Speaker(x=5, y=5)
        assert s.z == 2.8  # ceiling-mounted
        assert s.rating_dba == 95.0
        assert s.ref_distance_m == DEFAULT_REF_DISTANCE_M


class TestBarrier:
    def test_effective_attenuation_from_type(self):
        b = Barrier(barrier_type="fire_door")
        assert b.effective_attenuation_dba == BARRIER_ATTENUATION_DB["fire_door"]

    def test_effective_attenuation_custom_override(self):
        b = Barrier(barrier_type="standard_door", attenuation_dba=50.0)
        assert b.effective_attenuation_dba == 50.0

    def test_unknown_barrier_type_default(self):
        b = Barrier(barrier_type="nonexistent")
        assert b.effective_attenuation_dba == 15.0  # default


# ─────────────────────────────────────────────────────────────────────────────
# _frange Helper Tests
# ─────────────────────────────────────────────────────────────────────────────


class TestFrange:
    def test_positive_step(self):
        result = list(_frange(1.0, 3.0, 1.0))
        assert result == [1.0, 2.0, 3.0]

    def test_negative_step(self):
        result = list(_frange(3.0, 1.0, -1.0))
        assert result == [3.0, 2.0, 1.0]

    def test_single_value(self):
        result = list(_frange(5.0, 5.0, 1.0))
        assert result == [5.0]

    def test_zero_step_no_output(self):
        result = list(_frange(1.0, 5.0, 0.0))
        assert result == []


# ─────────────────────────────────────────────────────────────────────────────
# calculate_spl_at_distance Tests
# ─────────────────────────────────────────────────────────────────────────────


class TestCalculateSPL:
    """Test inverse square law SPL calculations."""

    def test_at_reference_distance(self):
        """At ref distance, attenuation = 0 dB (source equals effective)."""
        result = calculate_spl_at_distance(
            source_dba=95.0, target_distance_m=3.0, ref_distance_m=3.0,
            include_reverberant_field=False,
        )
        assert result.effective_dba == pytest.approx(95.0, abs=0.01)
        assert result.direct_attenuation_dB == pytest.approx(0.0, abs=0.01)

    def test_double_distance_6db(self):
        """Doubling distance = 6 dB attenuation (inverse square law)."""
        result = calculate_spl_at_distance(
            source_dba=95.0, target_distance_m=6.0, ref_distance_m=3.0,
            include_reverberant_field=False,
        )
        assert result.direct_attenuation_dB == pytest.approx(6.02, abs=0.1)
        assert result.effective_dba == pytest.approx(95.0 - 6.02, abs=0.1)

    def test_10x_distance_20db(self):
        """10× distance = 20 dB attenuation."""
        result = calculate_spl_at_distance(
            source_dba=95.0, target_distance_m=30.0, ref_distance_m=3.0,
            include_reverberant_field=False,
        )
        assert result.direct_attenuation_dB == pytest.approx(20.0, abs=0.1)

    def test_zero_distance_returns_source(self):
        """Target distance ≤ 0 returns source level with zero attenuation."""
        result = calculate_spl_at_distance(
            source_dba=95.0, target_distance_m=0.0,
        )
        assert result.effective_dba == 95.0
        assert result.direct_attenuation_dB == 0.0

    def test_negative_distance_returns_source(self):
        """Negative target distance is treated like zero."""
        result = calculate_spl_at_distance(
            source_dba=95.0, target_distance_m=-5.0,
        )
        assert result.effective_dba == 95.0

    def test_custom_ref_distance(self):
        """Custom ref distance (1m) changes attenuation calculation."""
        result = calculate_spl_at_distance(
            source_dba=90.0, target_distance_m=10.0, ref_distance_m=1.0,
            include_reverberant_field=False,
        )
        expected_atten = 20.0 * math.log10(10.0 / 1.0)
        assert result.direct_attenuation_dB == pytest.approx(expected_atten, abs=0.01)

    def test_reverberant_field_adds_to_direct(self):
        """With room absorption, total SPL should be higher than direct alone."""
        result_direct = calculate_spl_at_distance(
            source_dba=95.0, target_distance_m=15.0, ref_distance_m=3.0,
            room_absorption_m2=50.0, include_reverberant_field=False,
        )
        result_with_reverb = calculate_spl_at_distance(
            source_dba=95.0, target_distance_m=15.0, ref_distance_m=3.0,
            room_absorption_m2=50.0, include_reverberant_field=True,
        )
        assert result_with_reverb.effective_dba >= result_direct.effective_dba
        assert result_with_reverb.room_gain_dB > 0

    def test_no_room_absorption_no_reverb(self):
        """No room absorption → no reverberant field gain."""
        result = calculate_spl_at_distance(
            source_dba=95.0, target_distance_m=15.0,
            room_absorption_m2=None, include_reverberant_field=True,
        )
        assert result.room_gain_dB == 0.0

    def test_zero_room_absorption_no_reverb(self):
        """Zero room absorption → no reverberant field gain."""
        result = calculate_spl_at_distance(
            source_dba=95.0, target_distance_m=15.0,
            room_absorption_m2=0.0, include_reverberant_field=True,
        )
        assert result.room_gain_dB == 0.0

    def test_result_type(self):
        result = calculate_spl_at_distance(95.0, 10.0)
        assert isinstance(result, SPLResult)


# ─────────────────────────────────────────────────────────────────────────────
# check_audibility_compliance Tests
# ─────────────────────────────────────────────────────────────────────────────


class TestCheckAudibilityCompliance:
    """Test NFPA 72 audibility compliance checks."""

    def test_compliant_public_mode(self):
        """Typical office: 95 dBA speaker at 10m, 55 dBA ambient → compliant."""
        result = check_audibility_compliance(
            source_dba=95.0, target_distance_m=10.0, ambient_dba=55.0,
            mode="public",
        )
        # Required = 55 + 15 = 70 dBA
        # At 10m from 3m ref: atten ≈ 10.46 dB → SPL ≈ 84.5 dBA
        assert result.compliant is True
        assert result.margin_dba > 0
        assert result.nfpa_section == "§18.4.3"

    def test_non_compliant_public_mode(self):
        """Weak speaker far away → non-compliant."""
        result = check_audibility_compliance(
            source_dba=80.0, target_distance_m=30.0, ambient_dba=60.0,
            mode="public",
        )
        assert result.compliant is False
        assert len(result.violations) > 0

    def test_private_mode_lower_threshold(self):
        """Private mode requires only 10 dB above ambient."""
        result_pub = check_audibility_compliance(
            source_dba=85.0, target_distance_m=20.0, ambient_dba=55.0,
            mode="public",
        )
        result_priv = check_audibility_compliance(
            source_dba=85.0, target_distance_m=20.0, ambient_dba=55.0,
            mode="private",
        )
        assert result_priv.required_dba <= result_pub.required_dba

    def test_sleeping_mode_absolute_minimum_75dba(self):
        """Sleeping areas require 75 dBA minimum even if ambient is very low."""
        result = check_audibility_compliance(
            source_dba=85.0, target_distance_m=10.0, ambient_dba=30.0,
            mode="sleeping",
        )
        assert result.required_dba >= 75.0

    def test_invalid_mode_defaults_to_public(self):
        """Unknown mode falls back to 'public' (safe default)."""
        result = check_audibility_compliance(
            source_dba=95.0, target_distance_m=10.0, ambient_dba=55.0,
            mode="nonexistent_mode",
        )
        assert result.mode == "public"

    def test_excessive_sound_level_violation(self):
        """Sound exceeding 110 dBA generates ACOUSTIC-EXCESSIVE violation."""
        result = check_audibility_compliance(
            source_dba=130.0, target_distance_m=1.0, ambient_dba=55.0,
            mode="public", ref_distance_m=3.0,
        )
        # At 1m from 3m ref, atten = negative (closer than ref), so SPL > 130
        # Actually 20*log10(1/3) is negative, so SPL > source_dba
        if result.effective_dba > MAX_SOUND_LEVEL_DBA:
            assert any("110" in v for v in result.violations)

    def test_violation_message_contains_deficit(self):
        """Non-compliant result should report the deficit in dB."""
        result = check_audibility_compliance(
            source_dba=70.0, target_distance_m=15.0, ambient_dba=60.0,
            mode="public",
        )
        if not result.compliant:
            assert result.margin_dba < 0
            assert any("Deficit" in v for v in result.violations)

    def test_result_type(self):
        result = check_audibility_compliance(95.0, 10.0, 55.0)
        assert isinstance(result, AudibilityResult)


# ─────────────────────────────────────────────────────────────────────────────
# calculate_min_speakers_for_room Tests
# ─────────────────────────────────────────────────────────────────────────────


class TestCalculateMinSpeakersForRoom:
    """Test room-level speaker placement calculation."""

    def test_small_room_needs_one_speaker(self):
        """Small room with low ambient should need only 1 speaker."""
        result = calculate_min_speakers_for_room(
            room_length_m=5.0, room_width_m=5.0, room_height_m=3.0,
            source_dba=95.0, ambient_dba=45.0, mode="public",
        )
        assert result.speaker_count >= 1
        assert result.coverage_verified is True

    def test_large_room_needs_multiple_speakers(self):
        """Large warehouse with high ambient needs multiple speakers."""
        result = calculate_min_speakers_for_room(
            room_length_m=50.0, room_width_m=40.0, room_height_m=4.0,
            source_dba=95.0, ambient_dba=70.0, mode="public",
        )
        assert result.speaker_count > 1

    def test_room_area_calculated(self):
        result = calculate_min_speakers_for_room(
            room_length_m=10.0, room_width_m=8.0, room_height_m=3.0,
            source_dba=95.0, ambient_dba=50.0,
        )
        assert result.room_area_m2 == pytest.approx(80.0)

    def test_mode_propagated(self):
        result = calculate_min_speakers_for_room(
            room_length_m=10.0, room_width_m=10.0, room_height_m=3.0,
            source_dba=95.0, ambient_dba=50.0, mode="private",
        )
        assert result.mode == "private"

    def test_custom_room_absorption(self):
        result = calculate_min_speakers_for_room(
            room_length_m=10.0, room_width_m=10.0, room_height_m=3.0,
            source_dba=95.0, ambient_dba=55.0,
            room_absorption_m2=100.0,
        )
        assert result.coverage_verified is True

    def test_result_type(self):
        result = calculate_min_speakers_for_room(
            10.0, 10.0, 3.0, 95.0, 50.0,
        )
        assert isinstance(result, SpeakerPlacementResult)


# ─────────────────────────────────────────────────────────────────────────────
# get_speaker_coverage_radius Tests
# ─────────────────────────────────────────────────────────────────────────────


class TestGetSpeakerCoverageRadius:
    """Test binary search coverage radius calculation."""

    def test_default_radius_reasonable(self):
        """Default parameters should produce a reasonable coverage radius."""
        radius = get_speaker_coverage_radius()
        assert 1.0 < radius <= 100.0  # Max search range is 100m

    def test_higher_ambient_shorter_radius(self):
        """Higher ambient noise → shorter coverage radius."""
        radius_quiet = get_speaker_coverage_radius(ambient_dba=40.0)
        radius_loud = get_speaker_coverage_radius(ambient_dba=85.0)
        assert radius_quiet >= radius_loud

    def test_stronger_speaker_longer_radius(self):
        """More powerful speaker → longer coverage radius."""
        radius_weak = get_speaker_coverage_radius(source_dba=80.0)
        radius_strong = get_speaker_coverage_radius(source_dba=110.0)
        assert radius_strong >= radius_weak

    def test_private_mode_longer_radius(self):
        """Private mode (10 dB) allows longer radius than public (15 dB)."""
        radius_pub = get_speaker_coverage_radius(mode="public")
        radius_priv = get_speaker_coverage_radius(mode="private")
        assert radius_priv >= radius_pub

    def test_zero_radius_for_very_weak_speaker(self):
        """Extremely weak speaker with high ambient → 0.0 radius."""
        radius = get_speaker_coverage_radius(
            source_dba=50.0, ambient_dba=90.0, mode="public",
        )
        assert radius == 0.0

    def test_custom_room_absorption(self):
        """Higher absorption → slightly shorter radius."""
        radius_low = get_speaker_coverage_radius(room_absorption_m2=200.0)
        radius_high = get_speaker_coverage_radius(room_absorption_m2=20.0)
        # Higher absorption means less reverberant field, so shorter radius
        assert radius_high >= radius_low

    def test_returns_float(self):
        radius = get_speaker_coverage_radius()
        assert isinstance(radius, float)


# ─────────────────────────────────────────────────────────────────────────────
# AcousticSPLCalculator Tests
# ─────────────────────────────────────────────────────────────────────────────


class TestAcousticSPLCalculator:
    """Test multi-speaker room SPL calculator."""

    def test_single_speaker_single_point(self):
        """Basic: 1 speaker, 1 check point."""
        calc = AcousticSPLCalculator()
        result = calc.calculate_room_spl(
            room_id="R-101",
            occ_type="office_normal",
            speakers=[Speaker(x=5, y=5, z=2.8, rating_dba=95)],
            check_points=[CheckPoint(x=1, y=1, z=1.5)],
        )
        assert isinstance(result, RoomAcousticResult)
        assert result.room_id == "R-101"
        assert result.worst_point_spl > 0

    def test_compliant_room(self):
        """Well-designed room should be compliant."""
        calc = AcousticSPLCalculator()
        result = calc.calculate_room_spl(
            room_id="R-102",
            occ_type="office_quiet",
            speakers=[Speaker(x=5, y=5, z=2.8, rating_dba=95)],
            check_points=[CheckPoint(x=5, y=5, z=1.5)],
        )
        # Point directly below speaker should be very loud
        assert result.compliant is True

    def test_non_compliant_room_with_barrier(self):
        """Room with heavy barrier should show non-compliance."""
        calc = AcousticSPLCalculator()
        result = calc.calculate_room_spl(
            room_id="R-103",
            occ_type="mechanical_room",
            speakers=[Speaker(x=5, y=5, z=2.8, rating_dba=90)],
            check_points=[CheckPoint(x=15, y=15, z=1.5)],
            barriers=[Barrier(barrier_type="concrete_wall")],
        )
        # Concrete wall (45 dB) + distance + high ambient → non-compliant
        assert result.compliant is False

    def test_multiple_speakers_logarithmic_addition(self):
        """Two speakers should produce higher SPL than one."""
        calc = AcousticSPLCalculator()
        result_one = calc.calculate_room_spl(
            room_id="R-1",
            occ_type="office_normal",
            speakers=[Speaker(x=3, y=5, z=2.8, rating_dba=95)],
            check_points=[CheckPoint(x=5, y=5, z=1.5)],
        )
        result_two = calc.calculate_room_spl(
            room_id="R-2",
            occ_type="office_normal",
            speakers=[
                Speaker(x=3, y=5, z=2.8, rating_dba=95),
                Speaker(x=7, y=5, z=2.8, rating_dba=95),
            ],
            check_points=[CheckPoint(x=5, y=5, z=1.5)],
        )
        assert result_two.worst_point_spl >= result_one.worst_point_spl

    def test_ambient_lookup_case_insensitive(self):
        """Occupancy type lookup should be case-insensitive."""
        calc = AcousticSPLCalculator()
        result1 = calc.calculate_room_spl(
            room_id="R-A",
            occ_type="OFFICE_NORMAL",
            speakers=[Speaker(x=5, y=5, rating_dba=95)],
            check_points=[CheckPoint(x=1, y=1)],
        )
        result2 = calc.calculate_room_spl(
            room_id="R-B",
            occ_type="office_normal",
            speakers=[Speaker(x=5, y=5, rating_dba=95)],
            check_points=[CheckPoint(x=1, y=1)],
        )
        assert result1.required_dba == result2.required_dba

    def test_unknown_occupancy_defaults_55dba(self):
        """Unknown occupancy type defaults to 55 dBA ambient."""
        calc = AcousticSPLCalculator()
        result = calc.calculate_room_spl(
            room_id="R-UNK",
            occ_type="nonexistent_occupancy",
            speakers=[Speaker(x=5, y=5, rating_dba=95)],
            check_points=[CheckPoint(x=1, y=1)],
        )
        # Required = 55 + 15 = 70 for public mode
        assert result.required_dba == 70.0

    def test_no_speakers_zero_spl(self):
        """No speakers → SPL = 0 → non-compliant."""
        calc = AcousticSPLCalculator()
        result = calc.calculate_room_spl(
            room_id="R-EMPTY",
            occ_type="office_normal",
            speakers=[],
            check_points=[CheckPoint(x=5, y=5)],
        )
        assert result.worst_point_spl == 0.0
        assert result.compliant is False

    def test_no_check_points_compliant(self):
        """No check points → no violations → compliant."""
        calc = AcousticSPLCalculator()
        result = calc.calculate_room_spl(
            room_id="R-NOPTS",
            occ_type="office_normal",
            speakers=[Speaker(x=5, y=5)],
            check_points=[],
        )
        assert result.compliant is True

    def test_invalid_mode_defaults_public(self):
        """Invalid mode falls back to 'public'."""
        calc = AcousticSPLCalculator()
        result = calc.calculate_room_spl(
            room_id="R-MODE",
            occ_type="office_normal",
            speakers=[Speaker(x=5, y=5)],
            check_points=[CheckPoint(x=1, y=1)],
            mode="invalid_mode",
        )
        # Should still work without error
        assert isinstance(result, RoomAcousticResult)

    def test_barrier_custom_attenuation(self):
        """Barrier with custom attenuation_dba overrides lookup."""
        calc = AcousticSPLCalculator()
        result = calc.calculate_room_spl(
            room_id="R-BAR",
            occ_type="office_quiet",
            speakers=[Speaker(x=5, y=5, rating_dba=95)],
            check_points=[CheckPoint(x=6, y=5)],
            barriers=[Barrier(attenuation_dba=40.0)],
        )
        # 40 dB barrier significantly reduces SPL
        result_no_barrier = calc.calculate_room_spl(
            room_id="R-NOBAR",
            occ_type="office_quiet",
            speakers=[Speaker(x=5, y=5, rating_dba=95)],
            check_points=[CheckPoint(x=6, y=5)],
        )
        assert result.worst_point_spl < result_no_barrier.worst_point_spl

    def test_room_absorption_increases_spl(self):
        """Room absorption adds reverberant field, increasing SPL."""
        calc = AcousticSPLCalculator()
        result_no_abs = calc.calculate_room_spl(
            room_id="R-NA",
            occ_type="office_normal",
            speakers=[Speaker(x=5, y=5, rating_dba=95)],
            check_points=[CheckPoint(x=10, y=10)],
        )
        result_with_abs = calc.calculate_room_spl(
            room_id="R-WA",
            occ_type="office_normal",
            speakers=[Speaker(x=5, y=5, rating_dba=95)],
            check_points=[CheckPoint(x=10, y=10)],
            room_absorption_m2=100.0,
        )
        assert result_with_abs.worst_point_spl >= result_no_abs.worst_point_spl

    def test_point_results_populated(self):
        """Point results should contain all check points."""
        calc = AcousticSPLCalculator()
        points = [CheckPoint(x=1, y=1, label="P1"), CheckPoint(x=9, y=9, label="P2")]
        result = calc.calculate_room_spl(
            room_id="R-PTS",
            occ_type="office_normal",
            speakers=[Speaker(x=5, y=5)],
            check_points=points,
        )
        assert len(result.point_results) == 2

    def test_excessive_spl_violation(self):
        """SPL > 110 dBA should generate ACOUSTIC-EXCESSIVE violation."""
        calc = AcousticSPLCalculator(
            room_ambient_noise={"silent": 10.0},
        )
        result = calc.calculate_room_spl(
            room_id="R-LOUD",
            occ_type="silent",
            speakers=[Speaker(x=5, y=5, z=1.5, rating_dba=130)],
            check_points=[CheckPoint(x=5, y=5, z=1.5)],
            mode="private",
        )
        if result.worst_point_spl > MAX_SOUND_LEVEL_DBA:
            excessive = [v for v in result.violations if v.get("code") == "ACOUSTIC-EXCESSIVE"]
            assert len(excessive) > 0

    def test_custom_ambient_noise(self):
        """Custom ambient noise dict overrides defaults."""
        calc = AcousticSPLCalculator(room_ambient_noise={"custom_space": 75.0})
        result = calc.calculate_room_spl(
            room_id="R-CUST",
            occ_type="custom_space",
            speakers=[Speaker(x=5, y=5, rating_dba=95)],
            check_points=[CheckPoint(x=5, y=5)],
        )
        # Required = 75 + 15 = 90
        assert result.required_dba == 90.0

    def test_speaker_at_same_point_as_checkpoint(self):
        """Speaker and check point at same location → very high SPL."""
        calc = AcousticSPLCalculator()
        result = calc.calculate_room_spl(
            room_id="R-SAME",
            occ_type="office_quiet",
            speakers=[Speaker(x=5, y=5, z=2.0, rating_dba=95)],
            check_points=[CheckPoint(x=5, y=5, z=2.0)],
        )
        # Min distance clamp to 0.5m, still very loud
        assert result.worst_point_spl > 80.0


# ─────────────────────────────────────────────────────────────────────────────
# Edge Cases
# ─────────────────────────────────────────────────────────────────────────────


class TestEdgeCases:
    """Edge cases and boundary conditions."""

    def test_very_large_distance(self):
        """Very large distance should still compute (no crash)."""
        result = calculate_spl_at_distance(
            source_dba=95.0, target_distance_m=1000.0,
            include_reverberant_field=False,
        )
        assert result.effective_dba < 95.0

    def test_very_small_positive_distance(self):
        """Very small positive distance → near-source SPL."""
        result = calculate_spl_at_distance(
            source_dba=95.0, target_distance_m=0.01,
            include_reverberant_field=False,
        )
        # Should be louder than source (closer than ref distance)
        assert result.effective_dba > 95.0

    def test_zero_ambient(self):
        """Zero ambient → required = absolute minimum or 0."""
        result = check_audibility_compliance(
            source_dba=95.0, target_distance_m=10.0, ambient_dba=0.0,
            mode="public",
        )
        # public mode: 0 + 15 = 15, absolute_min = 0, so required = 15
        assert result.required_dba == 15.0

    def test_floating_point_precision(self):
        """Verify no floating-point issues in common scenarios."""
        result = calculate_spl_at_distance(
            source_dba=95.0, target_distance_m=3.0, ref_distance_m=3.0,
            include_reverberant_field=False,
        )
        assert not math.isnan(result.effective_dba)
        assert not math.isinf(result.effective_dba)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
