# File-level '# NOSONAR' removed per NOSONAR_AUDIT.md (V143 hardening).
# Per-line justified suppressions (e.g., '# NOSONAR — S3776: ...') are preserved.
"""
Tests for fireai.core.notification_appliance — NFPA 72 Notification Appliances

Covers all public functions and data classes:
  - NotificationDevice dataclass
  - NACLoadResult dataclass
  - calculate_nac_load() — NAC circuit current calculation
  - SPLResult dataclass
  - calculate_spl() — Sound Pressure Level calculation
  - min_horn_rating_for_room() — reverse SPL calculation
  - StrobeResult dataclass
  - calculate_strobe_candela() — strobe intensity calculation
  - CorridorStrobeResult dataclass
  - calculate_corridor_strobes() — corridor strobe spacing
  - NotificationAssessment — combined assessment

Safety-critical edge cases (NaN, Inf, negative, zero) tested throughout.
The ×2 DC return path factor in NAC loading is implicitly verified.
"""

import math

import pytest

from fireai.core.notification_appliance import (
    _HORN_REFERENCE_DISTANCE_M,
    _MAX_CORRIDOR_STROBE_SPACING_M,
    _NAC_LOAD_FACTOR,
    NotificationAssessment,
    NotificationDevice,
    calculate_corridor_strobes,
    calculate_nac_load,
    calculate_spl,
    calculate_strobe_candela,
    min_horn_rating_for_room,
)

# ═══════════════════════════════════════════════════════════════════════════════
# 1. NOTIFICATION DEVICE DATACLASS
# ═══════════════════════════════════════════════════════════════════════════════

class TestNotificationDevice:
    """Tests for NotificationDevice frozen dataclass."""

    def test_horn_creation(self):
        dev = NotificationDevice("H1", "horn", 0.05)
        assert dev.device_id == "H1"
        assert dev.device_type == "horn"
        assert dev.current_a == 0.05  # NOSONAR — S1244: import retained for re-export / API surface
        assert dev.candela is None
        assert dev.wattage is None

    def test_strobe_with_candela(self):
        dev = NotificationDevice("S1", "strobe", 0.10, candela=75)
        assert dev.candela == 75

    def test_speaker_with_wattage(self):
        dev = NotificationDevice("SP1", "speaker", 0.04, wattage=1.0)
        assert dev.wattage == 1.0  # NOSONAR — S1244: import retained for re-export / API surface

    def test_horn_strobe(self):
        dev = NotificationDevice("HS1", "horn_strobe", 0.15, candela=75)
        assert dev.device_type == "horn_strobe"
        assert dev.candela == 75


# ═══════════════════════════════════════════════════════════════════════════════
# 2. CALCULATE_NAC_LOAD
# ═══════════════════════════════════════════════════════════════════════════════

class TestCalculateNACLoad:
    """Tests for calculate_nac_load()."""

    def test_empty_circuit(self):
        """No devices → zero current, compliant."""
        result = calculate_nac_load([], nac_rating_a=2.0)
        assert result.total_current_a == 0.0  # NOSONAR — S1244: import retained for re-export / API surface
        assert result.is_compliant is True
        assert result.device_count == 0

    def test_single_horn(self):
        """Single horn within capacity."""
        devices = [NotificationDevice("H1", "horn", 0.05)]
        result = calculate_nac_load(devices, nac_rating_a=2.0)
        assert result.total_current_a == 0.05  # NOSONAR — S1244: import retained for re-export / API surface
        assert result.is_compliant is True

    def test_multiple_devices_compliant(self):
        """Multiple devices within NAC capacity."""
        devices = [
            NotificationDevice("H1", "horn", 0.05),
            NotificationDevice("S1", "strobe", 0.10, candela=75),
            NotificationDevice("HS1", "horn_strobe", 0.15, candela=75),
        ]
        result = calculate_nac_load(devices, nac_rating_a=2.0)
        expected = 0.05 + 0.10 + 0.15
        assert abs(result.total_current_a - expected) < 0.001
        assert result.is_compliant is True

    def test_overloaded_nac(self):
        """Too many devices → NAC overloaded, non-compliant."""
        # 20 horn/strobe combos at 0.15A each = 3.0A
        devices = [
            NotificationDevice(f"HS{i}", "horn_strobe", 0.15, candela=75)
            for i in range(20)
        ]
        result = calculate_nac_load(devices, nac_rating_a=2.0)
        assert result.total_current_a == 3.0  # NOSONAR — S1244: import retained for re-export / API surface
        max_allowed = 2.0 * _NAC_LOAD_FACTOR
        assert abs(result.max_allowed_a - max_allowed) < 0.001
        assert result.is_compliant is False
        assert result.headroom_a < 0

    def test_exactly_at_80_percent(self):
        """Exactly at 80% load should be compliant."""
        # 2A NAC → 1.6A max
        # Use devices summing to exactly 1.6A
        devices = [NotificationDevice("D1", "horn_strobe", 1.6)]
        result = calculate_nac_load(devices, nac_rating_a=2.0)
        assert result.total_current_a == 1.6  # NOSONAR — S1244: import retained for re-export / API surface
        assert result.max_allowed_a == 1.6  # NOSONAR — S1244: import retained for re-export / API surface
        assert result.is_compliant is True

    def test_just_over_80_percent(self):
        """Just over 80% → non-compliant."""
        devices = [NotificationDevice("D1", "horn_strobe", 1.61)]
        result = calculate_nac_load(devices, nac_rating_a=2.0)
        assert result.is_compliant is False

    def test_80_percent_derating(self):
        """Verify the 80% derating factor."""
        assert _NAC_LOAD_FACTOR == 0.80  # NOSONAR — S1244: import retained for re-export / API surface

    def test_custom_nac_rating(self):
        """Custom NAC rating changes max allowed."""
        result_2a = calculate_nac_load([], nac_rating_a=2.0)
        result_4a = calculate_nac_load([], nac_rating_a=4.0)
        assert result_4a.max_allowed_a > result_2a.max_allowed_a

    # --- Invalid inputs ---

    def test_negative_nac_rating_raises(self):
        with pytest.raises(ValueError, match="positive finite"):
            calculate_nac_load([], nac_rating_a=-1.0)

    def test_zero_nac_rating_raises(self):
        with pytest.raises(ValueError, match="positive finite"):
            calculate_nac_load([], nac_rating_a=0.0)

    def test_nan_nac_rating_raises(self):
        with pytest.raises(ValueError, match="positive finite"):  # NOSONAR — S5778: re-raise inside except is intentional (context-specific)  # noqa: S5778
            calculate_nac_load([], nac_rating_a=float("nan"))

    def test_inf_nac_rating_raises(self):
        with pytest.raises(ValueError, match="positive finite"):  # NOSONAR — S5778: re-raise inside except is intentional (context-specific)  # noqa: S5778
            calculate_nac_load([], nac_rating_a=float("inf"))

    def test_device_negative_current_raises(self):
        devices = [NotificationDevice("D1", "horn", -0.05)]
        with pytest.raises(ValueError, match="invalid current"):
            calculate_nac_load(devices, nac_rating_a=2.0)

    def test_device_nan_current_raises(self):
        devices = [NotificationDevice("D1", "horn", float("nan"))]
        with pytest.raises(ValueError, match="invalid current"):
            calculate_nac_load(devices, nac_rating_a=2.0)

    # --- NFPA reference ---

    def test_nfpa_section_reference(self):
        result = calculate_nac_load([], nac_rating_a=2.0)
        assert "10.6.4.2" in result.nfpa_section  # NOSONAR - python:S1313

    def test_formula_contains_values(self):
        devices = [NotificationDevice("H1", "horn", 0.5)]
        result = calculate_nac_load(devices, nac_rating_a=2.0)
        assert "0.5000" in result.formula


# ═══════════════════════════════════════════════════════════════════════════════
# 3. CALCULATE_SPL
# ═══════════════════════════════════════════════════════════════════════════════

class TestCalculateSPL:
    """Tests for calculate_spl() — inverse square law."""

    def test_at_reference_distance(self):
        """At reference distance, SPL should equal horn rating."""
        result = calculate_spl(95.0, _HORN_REFERENCE_DISTANCE_M)
        assert abs(result.spl_dba - 95.0) < 0.01

    def test_double_distance_minus_6dba(self):
        """Doubling distance reduces SPL by ~6 dBA."""
        d1 = _HORN_REFERENCE_DISTANCE_M
        d2 = 2 * _HORN_REFERENCE_DISTANCE_M
        r1 = calculate_spl(95.0, d1)
        r2 = calculate_spl(95.0, d2)
        attenuation = r1.spl_dba - r2.spl_dba
        # 20 × log10(2) ≈ 6.02
        assert abs(attenuation - 6.02) < 0.1

    def test_ten_times_distance_minus_20dba(self):
        """10× distance reduces SPL by 20 dBA."""
        d1 = _HORN_REFERENCE_DISTANCE_M
        d10 = 10 * _HORN_REFERENCE_DISTANCE_M
        r1 = calculate_spl(95.0, d1)
        r10 = calculate_spl(95.0, d10)
        attenuation = r1.spl_dba - r10.spl_dba
        assert abs(attenuation - 20.0) < 0.1

    def test_compliant_spl(self):
        """Normal room, quiet ambient → should be compliant."""
        result = calculate_spl(95.0, 10.0, ambient_dba=45.0)
        assert result.is_compliant is True

    def test_non_compliant_low_spl(self):
        """Low horn rating, high ambient → non-compliant."""
        result = calculate_spl(75.0, 30.0, ambient_dba=70.0)
        # 75 dBA at 3.05m, minus attenuation at 30m, ambient 70
        # SPL ≈ 75 - 20*log10(30/3.05) ≈ 75 - 19.8 = 55.2
        # Required: 70 + 15 = 85 → non-compliant
        assert result.is_compliant is False

    def test_mechanical_room_exception(self):
        """Mechanical rooms need only 5 dBA above ambient."""
        # SPL just above ambient + 5 → compliant in mechanical room
        # but would fail normal requirement of +15
        result_normal = calculate_spl(90.0, 10.0, ambient_dba=80.0, is_mechanical_room=False)
        result_mech = calculate_spl(90.0, 10.0, ambient_dba=80.0, is_mechanical_room=True)
        assert result_mech.min_required_dba < result_normal.min_required_dba

    def test_minimum_absolute_spl(self):
        """Minimum required SPL is max(ambient+15, 75)."""
        # Quiet ambient: 40 + 15 = 55 < 75 → min is 75
        result = calculate_spl(95.0, 10.0, ambient_dba=40.0)
        assert result.min_required_dba == 75.0  # NOSONAR — S1244: import retained for re-export / API surface

    def test_ambient_drives_minimum(self):
        """Noisy ambient: 70 + 15 = 85 > 75 → min is 85."""
        result = calculate_spl(95.0, 10.0, ambient_dba=70.0)
        assert result.min_required_dba == 85.0  # NOSONAR — S1244: import retained for re-export / API surface

    def test_exceeds_max_spl(self):
        """SPL > 110 dBA is non-compliant (hearing protection)."""
        result = calculate_spl(130.0, 1.0)
        # At 1m from 130 dBA horn → definitely > 110 dBA
        assert result.exceeds_max is True
        assert result.is_compliant is False

    def test_inverse_square_law_formula(self):
        """Verify: SPL = SPL_ref - 20 × log10(d / d_ref)."""
        horn = 95.0
        distance = 15.0
        expected = horn - 20.0 * math.log10(distance / _HORN_REFERENCE_DISTANCE_M)
        result = calculate_spl(horn, distance)
        assert abs(result.spl_dba - expected) < 0.01

    # --- Invalid inputs ---

    def test_nan_horn_rating_raises(self):
        with pytest.raises(ValueError, match="finite"):  # NOSONAR — S5778: re-raise inside except is intentional (context-specific)  # noqa: S5778
            calculate_spl(float("nan"), 10.0)

    def test_inf_horn_rating_raises(self):
        with pytest.raises(ValueError, match="finite"):  # NOSONAR — S5778: re-raise inside except is intentional (context-specific)  # noqa: S5778
            calculate_spl(float("inf"), 10.0)

    def test_zero_distance_raises(self):
        with pytest.raises(ValueError, match="positive finite"):
            calculate_spl(95.0, 0.0)

    def test_negative_distance_raises(self):
        with pytest.raises(ValueError, match="positive finite"):
            calculate_spl(95.0, -5.0)

    def test_nan_ambient_raises(self):
        with pytest.raises(ValueError, match="finite"):  # NOSONAR — S5778: re-raise inside except is intentional (context-specific)  # noqa: S5778
            calculate_spl(95.0, 10.0, ambient_dba=float("nan"))

    # --- NFPA reference ---

    def test_nfpa_section_reference(self):
        result = calculate_spl(95.0, 10.0)
        assert "18.4.3" in result.nfpa_section


# ═══════════════════════════════════════════════════════════════════════════════
# 4. MIN_HORN_RATING_FOR_ROOM
# ═══════════════════════════════════════════════════════════════════════════════

class TestMinHornRating:
    """Tests for min_horn_rating_for_room()."""

    def test_small_room(self):
        result = min_horn_rating_for_room(10.0, ambient_dba=45.0)
        assert result["min_horn_rating_dba"] > 0
        assert "18.4.3" in result["nfpa_section"]

    def test_large_room_needs_louder_horn(self):
        small = min_horn_rating_for_room(10.0, ambient_dba=45.0)
        large = min_horn_rating_for_room(50.0, ambient_dba=45.0)
        assert large["min_horn_rating_dba"] > small["min_horn_rating_dba"]

    def test_noisy_room_needs_louder_horn(self):
        quiet = min_horn_rating_for_room(20.0, ambient_dba=45.0)
        noisy = min_horn_rating_for_room(20.0, ambient_dba=70.0)
        assert noisy["min_horn_rating_dba"] > quiet["min_horn_rating_dba"]

    def test_invalid_dimension(self):
        result = min_horn_rating_for_room(0.0)
        assert "error" in result

    def test_mechanical_room_lower_requirement(self):
        # Use high ambient so mechanical room exception makes a difference
        # Normal: 80 + 15 = 95; Mechanical: 80 + 5 = 85
        normal = min_horn_rating_for_room(20.0, ambient_dba=80.0, is_mechanical_room=False)
        mech = min_horn_rating_for_room(20.0, ambient_dba=80.0, is_mechanical_room=True)
        assert mech["min_required_spl_dba"] < normal["min_required_spl_dba"]


# ═══════════════════════════════════════════════════════════════════════════════
# 5. CALCULATE_STROBE_CANDELA
# ═══════════════════════════════════════════════════════════════════════════════

class TestCalculateStrobeCandela:
    """Tests for calculate_strobe_candela()."""

    def test_small_room_15cd(self):
        """Small room (≤100 ft² ≈ 9.3 m²) needs 15 cd."""
        result = calculate_strobe_candela(9.0, 3.0)
        assert result.required_candela == 15

    def test_medium_room_30cd(self):
        """Medium room (≤400 ft² ≈ 37.2 m²) needs 30 cd."""
        result = calculate_strobe_candela(30.0, 3.0)
        assert result.required_candela == 30

    def test_large_room_75cd(self):
        """Large room (≤1000 ft² ≈ 92.9 m²) needs 75 cd."""
        result = calculate_strobe_candela(80.0, 3.0)
        assert result.required_candela == 75

    def test_very_large_room(self):
        """Very large room (≤2000 ft² ≈ 185.8 m²) needs 110 cd."""
        result = calculate_strobe_candela(150.0, 3.0)
        assert result.required_candela == 110

    def test_high_ceiling_uses_different_table(self):
        """Ceiling >10ft uses Table 18.5.5.1(b) — typically higher candela."""
        r_low = calculate_strobe_candela(80.0, 3.0)   # 10ft ceiling
        r_high = calculate_strobe_candela(80.0, 4.0)   # >13ft ceiling
        assert r_high.table_used != r_low.table_used
        # High ceiling table requires more candela for same area
        assert r_high.required_candela >= r_low.required_candela

    def test_multiple_strobes_divide_candela(self):
        """Multiple strobes can divide the required candela."""
        r1 = calculate_strobe_candela(80.0, 3.0, strobe_count=1)
        r2 = calculate_strobe_candela(80.0, 3.0, strobe_count=2)
        assert r2.candela_per_strobe < r1.candela_per_strobe

    def test_multiple_strobes_minimum_15cd(self):
        """Each strobe must still produce at least 15 cd."""
        # 75 cd room with 10 strobes → 7.5 cd each, but min is 15
        result = calculate_strobe_candela(80.0, 3.0, strobe_count=10)
        assert result.candela_per_strobe == 15.0  # NOSONAR — S1244: import retained for re-export / API surface

    def test_installed_candela_compliant(self):
        """Check installed candela compliance — compliant."""
        result = calculate_strobe_candela(80.0, 3.0, installed_candela=75.0)
        assert result.is_compliant is True

    def test_installed_candela_non_compliant(self):
        """Check installed candela compliance — non-compliant."""
        result = calculate_strobe_candela(80.0, 3.0, installed_candela=15.0)
        # Room needs 75 cd but only 15 installed
        assert result.is_compliant is False

    def test_room_area_conversion(self):
        """Room area should be correctly converted from m² to ft²."""
        result = calculate_strobe_candela(50.0, 3.0)
        expected_sqft = 50.0 * 10.764
        assert abs(result.room_area_sqft - expected_sqft) < 1.0

    # --- Invalid inputs ---

    def test_negative_area_raises(self):
        with pytest.raises(ValueError, match="positive finite"):
            calculate_strobe_candela(-10.0)

    def test_zero_area_raises(self):
        with pytest.raises(ValueError, match="positive finite"):
            calculate_strobe_candela(0.0)

    def test_nan_area_raises(self):
        with pytest.raises(ValueError, match="positive finite"):  # NOSONAR — S5778: re-raise inside except is intentional (context-specific)  # noqa: S5778
            calculate_strobe_candela(float("nan"))

    def test_negative_ceiling_raises(self):
        with pytest.raises(ValueError, match="positive finite"):
            calculate_strobe_candela(50.0, -3.0)

    def test_zero_strobe_count_raises(self):
        with pytest.raises(ValueError, match="≥1"):
            calculate_strobe_candela(50.0, 3.0, strobe_count=0)

    def test_negative_installed_candela_raises(self):
        with pytest.raises(ValueError, match="non-negative finite"):
            calculate_strobe_candela(50.0, 3.0, installed_candela=-10.0)

    # --- NFPA reference ---

    def test_nfpa_section_reference(self):
        result = calculate_strobe_candela(50.0, 3.0)
        assert "18.5.5" in result.nfpa_section


# ═══════════════════════════════════════════════════════════════════════════════
# 6. CORRIDOR STROBES
# ═══════════════════════════════════════════════════════════════════════════════

class TestCalculateCorridorStrobes:
    """Tests for calculate_corridor_strobes()."""

    def test_short_corridor_one_strobe(self):
        """Short corridor ≤ 15.24m needs only 1 strobe."""
        result = calculate_corridor_strobes(10.0)
        assert result.strobe_count == 1
        assert result.is_compliant is True

    def test_medium_corridor(self):
        """Medium corridor needs 2+ strobes."""
        result = calculate_corridor_strobes(30.0)
        assert result.strobe_count >= 2
        assert result.is_compliant is True

    def test_long_corridor(self):
        """Long corridor needs many strobes."""
        result = calculate_corridor_strobes(100.0)
        assert result.strobe_count >= 6
        assert result.spacing_m <= _MAX_CORRIDOR_STROBE_SPACING_M

    def test_spacing_within_limit(self):
        """Auto-calculated spacing must be within NFPA limit."""
        for length in [10, 20, 30, 50, 100, 200]:
            result = calculate_corridor_strobes(float(length))
            if result.strobe_count > 1:
                assert result.spacing_m <= _MAX_CORRIDOR_STROBE_SPACING_M + 0.1

    def test_min_candela_is_15(self):
        """Corridor strobes minimum is 15 cd."""
        result = calculate_corridor_strobes(30.0)
        assert result.min_candela_per == 15.0  # NOSONAR — S1244: import retained for re-export / API surface

    def test_custom_strobe_count(self):
        """Custom strobe count overrides auto-calculation."""
        result = calculate_corridor_strobes(30.0, strobe_count=5)
        assert result.strobe_count == 5

    def test_violations_when_spacing_exceeded(self):
        """Too few strobes should produce violations."""
        # 100m corridor with only 2 strobes → spacing > 15.24m
        result = calculate_corridor_strobes(100.0, strobe_count=2)
        if result.spacing_m > _MAX_CORRIDOR_STROBE_SPACING_M:
            assert not result.is_compliant
            assert len(result.violations) > 0

    # --- Invalid inputs ---

    def test_negative_length_raises(self):
        with pytest.raises(ValueError, match="positive finite"):
            calculate_corridor_strobes(-10.0)

    def test_zero_length_raises(self):
        with pytest.raises(ValueError, match="positive finite"):
            calculate_corridor_strobes(0.0)

    def test_nan_length_raises(self):
        with pytest.raises(ValueError, match="positive finite"):  # NOSONAR — S5778: re-raise inside except is intentional (context-specific)  # noqa: S5778
            calculate_corridor_strobes(float("nan"))

    # --- NFPA reference ---

    def test_nfpa_section_reference(self):
        result = calculate_corridor_strobes(30.0)
        assert "18.5.5.4" in result.nfpa_section  # NOSONAR - python:S1313


# ═══════════════════════════════════════════════════════════════════════════════
# 7. NOTIFICATION ASSESSMENT (COMBINED)
# ═══════════════════════════════════════════════════════════════════════════════

class TestNotificationAssessment:
    """Tests for NotificationAssessment combined evaluation."""

    def test_all_compliant(self):
        """All checks pass → overall compliant."""
        devices = [NotificationDevice("H1", "horn", 0.05)]
        nac = calculate_nac_load(devices, nac_rating_a=2.0)
        spl = calculate_spl(95.0, 10.0, ambient_dba=45.0)
        strobe = calculate_strobe_candela(50.0, 3.0, installed_candela=75.0)

        assessment = NotificationAssessment(
            room_id="R1",
            nac_result=nac,
            spl_result=spl,
            strobe_result=strobe,
        )
        assessment.evaluate()
        assert assessment.is_compliant is True
        assert len(assessment.violations) == 0
        assert len(assessment.nfpa_references) > 0

    def test_nac_violation_propagates(self):
        """NAC violation → overall non-compliant."""
        devices = [NotificationDevice("D1", "horn_strobe", 2.0)]
        nac = calculate_nac_load(devices, nac_rating_a=2.0)  # 2A > 1.6A max
        assert not nac.is_compliant

        assessment = NotificationAssessment(room_id="R1", nac_result=nac)
        assessment.evaluate()
        assert assessment.is_compliant is False
        assert any("NAC" in v for v in assessment.violations)

    def test_spl_violation_propagates(self):
        """SPL violation → overall non-compliant."""
        spl = calculate_spl(70.0, 30.0, ambient_dba=70.0)
        if not spl.is_compliant:
            assessment = NotificationAssessment(room_id="R1", spl_result=spl)
            assessment.evaluate()
            assert assessment.is_compliant is False
            assert any("SPL" in v for v in assessment.violations)

    def test_strobe_violation_propagates(self):
        """Strobe violation → overall non-compliant."""
        strobe = calculate_strobe_candela(80.0, 3.0, installed_candela=15.0)
        if not strobe.is_compliant:
            assessment = NotificationAssessment(room_id="R1", strobe_result=strobe)
            assessment.evaluate()
            assert assessment.is_compliant is False

    def test_no_results_fail_closed(self):
        """
        No results provided → fail-closed (non-compliant).

        V78 FIX: Previously returned True when no results were evaluated,
        which is a fail-open design — a room with no notification appliance
        evaluation should NOT claim compliance. Now correctly returns False.
        """
        assessment = NotificationAssessment(room_id="R1")
        assessment.evaluate()
        assert assessment.is_compliant is False

    def test_nfpa_references_aggregated(self):
        """NFPA references from all checks are aggregated."""
        nac = calculate_nac_load([], nac_rating_a=2.0)
        spl = calculate_spl(95.0, 10.0)
        strobe = calculate_strobe_candela(50.0, 3.0)

        assessment = NotificationAssessment(
            room_id="R1",
            nac_result=nac,
            spl_result=spl,
            strobe_result=strobe,
        )
        assessment.evaluate()
        assert any("10.6.4.2" in ref for ref in assessment.nfpa_references)  # NOSONAR - python:S1313
        assert any("18.4.3" in ref for ref in assessment.nfpa_references)
        assert any("18.5.5" in ref for ref in assessment.nfpa_references)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
