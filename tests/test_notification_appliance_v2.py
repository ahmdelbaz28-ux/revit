"""
tests/test_notification_appliance_v2.py
========================================
Extended test suite for fireai.core.notification_appliance.

Supplements test_notification_appliance.py with additional edge cases,
boundary conditions, round-trip consistency, and deeper NFPA compliance
verification.

NFPA 72 References:
  §10.6.4.2 — NAC current ≤80% of rating
  §18.4.3   — SPL ≥15 dBA above ambient (5 dBA in mechanical rooms)
  §18.5.5   — Strobe candela table
  §18.5.5.4 — Corridor strobe spacing
"""

from __future__ import annotations

import math
import pytest

from fireai.core.notification_appliance import (
    NACLoadResult,
    NotificationDevice,
    NotificationAssessment,
    SPLResult,
    StrobeResult,
    CorridorStrobeResult,
    calculate_nac_load,
    calculate_spl,
    calculate_strobe_candela,
    calculate_corridor_strobes,
    min_horn_rating_for_room,
    _NAC_LOAD_FACTOR,
    _MIN_SPL_ABOVE_AMBIENT_DBA,
    _MIN_ABSOLUTE_SPL_DBA,
    _MAX_SPL_DBA,
    _HORN_REFERENCE_DISTANCE_M,
    _SQFT_PER_SQM,
    _MAX_CORRIDOR_STROBE_SPACING_M,
    _MAX_END_OF_CORRIDOR_DISTANCE_M,
    _STROBE_CANDELA_TABLE_LOW_CEILING,
    _STROBE_CANDELA_TABLE_HIGH_CEILING,
)


# ═══════════════════════════════════════════════════════════════════════════════
# NAC Load — Extended Edge Cases
# ═══════════════════════════════════════════════════════════════════════════════


class TestNACLoadExtended:
    """Extended NAC load calculations — boundary and edge-case coverage."""

    def test_device_inf_current_raises(self):
        """Infinite current is not finite — must raise."""
        devices = [NotificationDevice("D1", "horn", float("inf"))]
        with pytest.raises(ValueError, match="invalid current"):
            calculate_nac_load(devices, nac_rating_a=2.0)

    def test_large_nac_rating(self):
        """Very large NAC rating should work."""
        devices = [NotificationDevice("D1", "horn", 0.05)]
        result = calculate_nac_load(devices, nac_rating_a=100.0)
        assert result.is_compliant is True
        assert result.max_allowed_a == pytest.approx(100.0 * _NAC_LOAD_FACTOR)

    def test_small_nac_rating(self):
        """Very small NAC rating (0.01A) — single device may overload."""
        devices = [NotificationDevice("D1", "horn", 0.05)]
        result = calculate_nac_load(devices, nac_rating_a=0.01)
        assert result.is_compliant is False

    def test_many_devices_compliant(self):
        """50 devices at 0.02A each on a 4A NAC → 1.0A ≤ 3.2A."""
        devices = [NotificationDevice(f"D{i}", "speaker", 0.02) for i in range(50)]
        result = calculate_nac_load(devices, nac_rating_a=4.0)
        assert result.total_current_a == pytest.approx(1.0)
        assert result.is_compliant is True
        assert result.device_count == 50

    def test_headroom_positive_when_compliant(self):
        """Headroom must be positive when compliant."""
        devices = [NotificationDevice("H1", "horn", 0.05)]
        result = calculate_nac_load(devices, nac_rating_a=2.0)
        assert result.headroom_a > 0

    def test_headroom_negative_when_overloaded(self):
        """Headroom must be negative when overloaded."""
        devices = [NotificationDevice("D1", "horn_strobe", 2.0)]
        result = calculate_nac_load(devices, nac_rating_a=2.0)
        assert result.headroom_a < 0

    def test_zero_current_device_is_compliant(self):
        """A device with zero current should not contribute to load."""
        devices = [NotificationDevice("D1", "detector", 0.0)]
        result = calculate_nac_load(devices, nac_rating_a=2.0)
        assert result.total_current_a == 0.0
        assert result.is_compliant is True

    def test_result_is_frozen(self):
        """NACLoadResult is frozen — must not allow mutation."""
        result = calculate_nac_load([], nac_rating_a=2.0)
        with pytest.raises(AttributeError):
            result.is_compliant = False

    def test_nac_load_factor_is_80_percent(self):
        """NEC 760: The derating factor must be exactly 0.80."""
        assert _NAC_LOAD_FACTOR == 0.80

    def test_formula_string_contains_total_current(self):
        """Formula must embed the calculated total current."""
        devices = [NotificationDevice("H1", "horn", 0.15)]
        result = calculate_nac_load(devices, nac_rating_a=2.0)
        assert "0.1500" in result.formula

    def test_boundary_exactly_80_pct_with_multiple_devices(self):
        """Multiple devices summing to exactly 80% of rating."""
        # 2A NAC → 1.6A max; 8 devices × 0.2A = 1.6A
        devices = [NotificationDevice(f"D{i}", "strobe", 0.2) for i in range(8)]
        result = calculate_nac_load(devices, nac_rating_a=2.0)
        assert result.total_current_a == pytest.approx(1.6)
        assert result.is_compliant is True

    def test_just_above_80_pct_by_epsilon(self):
        """0.001A over the 80% boundary → non-compliant."""
        devices = [NotificationDevice("D1", "horn", 1.601)]
        result = calculate_nac_load(devices, nac_rating_a=2.0)
        assert result.is_compliant is False


# ═══════════════════════════════════════════════════════════════════════════════
# SPL — Extended Edge Cases
# ═══════════════════════════════════════════════════════════════════════════════


class TestSPLExtended:
    """Extended SPL calculation edge cases."""

    def test_closer_than_reference_distance(self):
        """Closer than 3.05m — SPL increases (negative attenuation)."""
        result = calculate_spl(95.0, 1.0)
        # At 1m < 3.05m: attenuation is negative → SPL > 95 dBA
        assert result.spl_dba > 95.0

    def test_closer_than_reference_formula(self):
        """Verify SPL formula when d < d_ref."""
        horn = 95.0
        dist = 1.0
        expected = horn - 20.0 * math.log10(dist / _HORN_REFERENCE_DISTANCE_M)
        result = calculate_spl(horn, dist)
        assert result.spl_dba == pytest.approx(expected, abs=0.01)

    def test_mechanical_room_5dba_above_ambient(self):
        """Mechanical room requires only 5 dBA above ambient."""
        result = calculate_spl(90.0, 10.0, ambient_dba=80.0, is_mechanical_room=True)
        assert result.min_required_dba == 85.0  # 80 + 5

    def test_non_mechanical_room_15dba_above_ambient(self):
        """Normal room requires 15 dBA above ambient."""
        result = calculate_spl(90.0, 10.0, ambient_dba=80.0, is_mechanical_room=False)
        assert result.min_required_dba == 95.0  # 80 + 15

    def test_quiet_room_minimum_is_75_dba(self):
        """Very quiet room: ambient + 15 < 75 → minimum is 75 dBA."""
        result = calculate_spl(95.0, 10.0, ambient_dba=10.0)
        assert result.min_required_dba == 75.0

    def test_spl_result_is_frozen(self):
        """SPLResult must be immutable."""
        result = calculate_spl(95.0, 10.0)
        with pytest.raises(AttributeError):
            result.spl_dba = 0.0

    def test_exact_boundary_spl_compliant(self):
        """SPL exactly at the minimum required → compliant."""
        # At 3.05m, SPL = horn rating. Choose horn = 75 dBA, ambient = 45
        # min_required = max(45+15, 75) = 75. SPL at 3.05m = 75. → compliant
        result = calculate_spl(75.0, _HORN_REFERENCE_DISTANCE_M, ambient_dba=45.0)
        assert result.spl_dba >= result.min_required_dba - 0.01
        assert result.is_compliant is True

    def test_exactly_at_max_spl(self):
        """SPL exactly at 120 dBA should NOT exceed max (it's the boundary)."""
        # Need a horn/distance combo that gives exactly 120 dBA
        # At 3.05m, SPL = horn rating. If horn = 120, SPL at 3.05m = 120
        result = calculate_spl(120.0, _HORN_REFERENCE_DISTANCE_M)
        assert result.spl_dba == pytest.approx(120.0, abs=0.01)
        assert result.exceeds_max is False

    def test_formula_contains_distance(self):
        """Formula string must contain the distance value."""
        result = calculate_spl(95.0, 15.0)
        assert "15.00" in result.formula

    def test_inf_distance_raises(self):
        """Infinite distance is not finite."""
        with pytest.raises(ValueError, match="positive finite"):
            calculate_spl(95.0, float("inf"))

    def test_negative_ambient_not_finite_passes(self):
        """Negative ambient is technically finite — should not raise."""
        # -10 dBA ambient: unusual but mathematically valid
        result = calculate_spl(95.0, 10.0, ambient_dba=-10.0)
        assert result.ambient_dba == -10.0


# ═══════════════════════════════════════════════════════════════════════════════
# min_horn_rating_for_room — Extended
# ═══════════════════════════════════════════════════════════════════════════════


class TestMinHornRatingExtended:
    """Extended tests for min_horn_rating_for_room()."""

    def test_nan_dimension_returns_error(self):
        """NaN dimension → error with -1.0 rating (V96 FIX)."""
        result = min_horn_rating_for_room(float("nan"))
        assert result["min_horn_rating_dba"] == -1.0
        assert "error" in result

    def test_inf_dimension_returns_error(self):
        """Infinite dimension → error."""
        result = min_horn_rating_for_room(float("inf"))
        assert result["min_horn_rating_dba"] == -1.0
        assert "error" in result

    def test_negative_dimension_returns_error(self):
        """Negative dimension → error."""
        result = min_horn_rating_for_room(-5.0)
        assert result["min_horn_rating_dba"] == -1.0
        assert "error" in result

    def test_coverage_distance_matches_input(self):
        """Coverage distance in result equals input room dimension."""
        result = min_horn_rating_for_room(20.0)
        assert result["coverage_distance_m"] == 20.0

    def test_round_trip_with_calculate_spl(self):
        """min_horn_rating should produce a horn that passes calculate_spl."""
        room_dim = 15.0
        ambient = 50.0
        horn_info = min_horn_rating_for_room(room_dim, ambient_dba=ambient)
        horn_rating = horn_info["min_horn_rating_dba"]
        spl_result = calculate_spl(horn_rating, room_dim, ambient_dba=ambient)
        assert spl_result.is_compliant is True

    def test_very_small_room(self):
        """Very small room (1m) — horn rating should still be reasonable."""
        result = min_horn_rating_for_room(1.0, ambient_dba=45.0)
        assert result["min_horn_rating_dba"] > 0

    def test_room_dimension_at_reference_distance(self):
        """Room dimension equal to reference distance (3.05m)."""
        result = min_horn_rating_for_room(_HORN_REFERENCE_DISTANCE_M, ambient_dba=45.0)
        # No gain needed at reference distance
        assert result["min_horn_rating_dba"] > 0


# ═══════════════════════════════════════════════════════════════════════════════
# Strobe Candela — Extended
# ═══════════════════════════════════════════════════════════════════════════════


class TestStrobeCandelaExtended:
    """Extended strobe candela edge cases."""

    def test_very_large_room_highest_table_entry(self):
        """Room > 4000 ft² uses the last table entry (highest candela)."""
        # 500 m² = ~5382 ft² → exceeds 4000 ft² → use last entry
        result = calculate_strobe_candela(500.0, 3.0)
        assert result.required_candela == _STROBE_CANDELA_TABLE_LOW_CEILING[-1][1]

    def test_high_ceiling_very_large_room(self):
        """High ceiling + very large room → highest high-ceiling table entry."""
        result = calculate_strobe_candela(500.0, 4.0)  # 4m = 13.1ft > 10ft
        assert result.required_candela == _STROBE_CANDELA_TABLE_HIGH_CEILING[-1][1]

    def test_ceiling_exactly_10ft(self):
        """Ceiling exactly at 10ft threshold uses low-ceiling table."""
        # 3.048m = exactly 10ft
        result = calculate_strobe_candela(50.0, 3.048)
        assert result.table_used == "Table 18.5.5.1(a)"

    def test_ceiling_just_above_10ft(self):
        """Ceiling just above 10ft uses high-ceiling table."""
        # 3.05m = 10.01ft → just above threshold
        result = calculate_strobe_candela(50.0, 3.05)
        assert result.table_used == "Table 18.5.5.1(b)"

    def test_inf_ceiling_raises(self):
        """Infinite ceiling height is not valid."""
        with pytest.raises(ValueError, match="positive finite"):
            calculate_strobe_candela(50.0, float("inf"))

    def test_nan_ceiling_raises(self):
        """NaN ceiling height is not valid."""
        with pytest.raises(ValueError, match="positive finite"):
            calculate_strobe_candela(50.0, float("nan"))

    def test_nan_installed_candela_raises(self):
        """NaN installed candela is not valid."""
        with pytest.raises(ValueError, match="non-negative finite"):
            calculate_strobe_candela(50.0, 3.0, installed_candela=float("nan"))

    def test_inf_installed_candela_compliant(self):
        """Infinite installed candela — not finite, should raise."""
        with pytest.raises(ValueError, match="non-negative finite"):
            calculate_strobe_candela(50.0, 3.0, installed_candela=float("inf"))

    def test_installed_candela_zero_non_compliant(self):
        """0 cd installed is always non-compliant (needs ≥ 15)."""
        result = calculate_strobe_candela(50.0, 3.0, installed_candela=0.0)
        assert result.is_compliant is False

    def test_installed_candela_exactly_required(self):
        """Installed candela exactly at required → compliant."""
        result_base = calculate_strobe_candela(50.0, 3.0)
        required = result_base.candela_per_strobe
        result = calculate_strobe_candela(50.0, 3.0, installed_candela=required)
        assert result.is_compliant is True

    def test_area_conversion_m2_to_sqft(self):
        """Verify area conversion: 1 m² = 10.764 ft²."""
        result = calculate_strobe_candela(1.0, 3.0)
        assert result.room_area_sqft == pytest.approx(1.0 * _SQFT_PER_SQM, abs=0.01)

    def test_ceiling_height_conversion(self):
        """Verify ceiling height conversion: 3.0m → 9.84ft."""
        result = calculate_strobe_candela(50.0, 3.0)
        expected_ft = 3.0 / 0.3048
        assert result.ceiling_height_ft == pytest.approx(expected_ft, abs=0.01)

    def test_strobe_count_negative_raises(self):
        """Negative strobe count is invalid."""
        with pytest.raises(ValueError, match="≥1"):
            calculate_strobe_candela(50.0, 3.0, strobe_count=-1)

    def test_result_is_frozen(self):
        """StrobeResult is frozen."""
        result = calculate_strobe_candela(50.0, 3.0)
        with pytest.raises(AttributeError):
            result.required_candela = 0


# ═══════════════════════════════════════════════════════════════════════════════
# Corridor Strobes — Extended
# ═══════════════════════════════════════════════════════════════════════════════


class TestCorridorStrobesExtended:
    """Extended corridor strobe placement tests."""

    def test_inf_length_raises(self):
        """Infinite corridor length is not valid."""
        with pytest.raises(ValueError, match="positive finite"):
            calculate_corridor_strobes(float("inf"))

    def test_very_short_corridor_one_strobe(self):
        """Corridor of 1m → 1 strobe, compliant."""
        result = calculate_corridor_strobes(1.0)
        assert result.strobe_count == 1
        assert result.is_compliant is True

    def test_corridor_exactly_max_spacing_length(self):
        """Corridor exactly at 15.24m — 1 strobe may suffice."""
        result = calculate_corridor_strobes(_MAX_CORRIDOR_STROBE_SPACING_M)
        assert result.strobe_count >= 1
        assert result.end_distance_m <= _MAX_END_OF_CORRIDOR_DISTANCE_M + 0.01

    def test_two_strobes_even_spacing(self):
        """2 strobes with auto-spacing → evenly distributed."""
        result = calculate_corridor_strobes(30.0)
        if result.strobe_count == 2:
            # First at end_distance, second at length - end_distance
            assert result.spacing_m <= _MAX_CORRIDOR_STROBE_SPACING_M + 0.1

    def test_corridor_result_is_frozen(self):
        """CorridorStrobeResult is frozen."""
        result = calculate_corridor_strobes(30.0)
        with pytest.raises(AttributeError):
            result.is_compliant = False

    def test_violations_list_content(self):
        """Violations should contain NFPA section reference when non-compliant."""
        result = calculate_corridor_strobes(100.0, strobe_count=1)
        if not result.is_compliant:
            for v in result.violations:
                assert "NFPA 72" in v or "§18.5.5.4" in v

    def test_auto_calculated_strobe_count_is_reasonable(self):
        """Auto-calculated strobe count should be proportional to length."""
        r_short = calculate_corridor_strobes(15.0)
        r_long = calculate_corridor_strobes(60.0)
        assert r_long.strobe_count >= r_short.strobe_count

    def test_custom_strobe_count_forces_compliance_check(self):
        """Custom count that violates spacing → non-compliant."""
        # 50m corridor with 2 strobes → spacing = (50-2*7.62)/(2-1) = 34.76m > 15.24m
        result = calculate_corridor_strobes(50.0, strobe_count=2)
        assert not result.is_compliant

    def test_nac_section_reference(self):
        """NFPA section reference must be present."""
        result = calculate_corridor_strobes(10.0)
        assert "18.5.5.4" in result.nfpa_section


# ═══════════════════════════════════════════════════════════════════════════════
# NotificationAssessment — Extended
# ═══════════════════════════════════════════════════════════════════════════════


class TestNotificationAssessmentExtended:
    """Extended NotificationAssessment tests."""

    def test_default_not_compliant_before_evaluate(self):
        """V96 FIX: unevaluated assessment must NOT claim compliance."""
        assessment = NotificationAssessment(room_id="R1")
        assert assessment.is_compliant is False

    def test_evaluate_resets_violations(self):
        """evaluate() must reset violations before re-computing."""
        devices = [NotificationDevice("H1", "horn", 0.05)]
        nac = calculate_nac_load(devices, nac_rating_a=2.0)
        assessment = NotificationAssessment(room_id="R1", nac_result=nac)
        # Pre-populate with stale violation
        assessment.violations = ["stale"]
        assessment.evaluate()
        assert "stale" not in assessment.violations

    def test_corridor_strobe_violation_propagates(self):
        """Corridor strobe violation → overall non-compliant."""
        corridor = calculate_corridor_strobes(100.0, strobe_count=1)
        if not corridor.is_compliant:
            assessment = NotificationAssessment(
                room_id="R1", corridor_strobe=corridor
            )
            assessment.evaluate()
            assert assessment.is_compliant is False

    def test_all_pass_includes_all_nfpa_refs(self):
        """When all results provided, all NFPA refs should be present."""
        devices = [NotificationDevice("H1", "horn", 0.05)]
        nac = calculate_nac_load(devices, nac_rating_a=2.0)
        spl = calculate_spl(95.0, 10.0, ambient_dba=45.0)
        strobe = calculate_strobe_candela(50.0, 3.0, installed_candela=75.0)
        corridor = calculate_corridor_strobes(10.0)

        assessment = NotificationAssessment(
            room_id="R1",
            nac_result=nac,
            spl_result=spl,
            strobe_result=strobe,
            corridor_strobe=corridor,
        )
        assessment.evaluate()
        assert "NFPA 72 §10.6.4.2" in assessment.nfpa_references
        assert "NFPA 72 §18.4.3" in assessment.nfpa_references
        assert "NFPA 72 §18.5.5" in assessment.nfpa_references
        assert "NFPA 72 §18.5.5.4" in assessment.nfpa_references

    def test_spl_exceeds_max_violation_message(self):
        """When SPL exceeds 120 dBA, violation must mention it."""
        spl = calculate_spl(130.0, 1.0)
        assert spl.exceeds_max is True
        assessment = NotificationAssessment(room_id="R1", spl_result=spl)
        assessment.evaluate()
        assert assessment.is_compliant is False
        assert any("exceeds maximum" in v or "120" in v for v in assessment.violations)

    def test_room_id_preserved(self):
        """Room ID must be preserved in assessment."""
        assessment = NotificationAssessment(room_id="FLOOR-3-ROOM-12")
        assert assessment.room_id == "FLOOR-3-ROOM-12"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
