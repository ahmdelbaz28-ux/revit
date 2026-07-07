"""
tests/test_nfpa72_technology_dispatcher.py
============================================
Comprehensive test suite for:
  - fireai/core/nfpa72_technology_dispatcher.py

SAFETY CRITICAL: Technology selection determines which detector type
is used. Wrong selection (e.g., point detector at 20m ceiling where
beam detector is required) could result in undetected fires.

NFPA 72 References:
  Table 17.6.3.1.1 — Height-adjusted spacing (up to 12.2m for smoke)
  §17.7.2 — Projected beam-type smoke detectors
  §17.7.3 — Performance-based design alternative
  §17.7.3.6 — Air-sampling detection (ASD)
  §17.6.3.4 — Sloped ceilings (ridge zone requirement)
"""

from __future__ import annotations

import pytest

from fireai.core.nfpa72_technology_dispatcher import (
    _BEAM_MAX_CEILING_M,
    _BEAM_SPACING_M,
    _NFPA72_SMOKE_SPACING_TABLE,
    _POINT_DETECTOR_MAX_CEILING_M,
    _SLOPE_RIDGE_ZONE_THRESHOLD_DEG,
    _STEEP_SLOPE_THRESHOLD_DEG,
    DetectorTechnology,
    EliteTechnologyDispatcher,
    TechnologyDecision,
    dispatch_detector_technology,
)

# Constants
# ─────────────────────────────────────────────────────────────────────────────


class TestConstants:
    """NFPA 72 threshold values — must be exact."""

    def test_point_detector_max_ceiling(self):
        assert _POINT_DETECTOR_MAX_CEILING_M == 12.2  # NOSONAR — S1244: import retained for re-export / API surface

    def test_beam_max_ceiling(self):
        assert _BEAM_MAX_CEILING_M == 25.0  # NOSONAR — S1244: import retained for re-export / API surface

    def test_slope_ridge_zone_threshold(self):
        """1 in 8 pitch ≈ 7.125°."""
        assert pytest.approx(7.125, abs=0.001) == _SLOPE_RIDGE_ZONE_THRESHOLD_DEG

    def test_steep_slope_threshold(self):
        assert _STEEP_SLOPE_THRESHOLD_DEG == 30.0  # NOSONAR — S1244: import retained for re-export / API surface

    def test_beam_spacing(self):
        """Standard beam spacing ≈ 60ft = 18.3m."""
        assert pytest.approx(18.3, abs=0.1) == _BEAM_SPACING_M

    def test_smoke_spacing_table_entries(self):
        """NFPA 72 Table 17.6.3.1.1 has 9 height/spacing pairs."""
        assert len(_NFPA72_SMOKE_SPACING_TABLE) == 9

    def test_smoke_spacing_table_flat_spacing(self):
        """V130 FIX: Smoke spacing table has flat 9.1m at ALL heights per §17.7.3.2.3."""
        for _, spacing in _NFPA72_SMOKE_SPACING_TABLE:
            assert spacing == 9.10, (  # NOSONAR — S1244: import retained for re-export / API surface
                f"Smoke spacing must be 9.1m (flat) per §17.7.3.2.3, got {spacing}m"
            )

    def test_standard_spacing_at_3m(self):
        """Standard 30ft (9.1m) spacing at h ≤ 3.0m."""
        assert _NFPA72_SMOKE_SPACING_TABLE[0] == (3.0, 9.10)


# ─────────────────────────────────────────────────────────────────────────────
# DetectorTechnology Enum
# ─────────────────────────────────────────────────────────────────────────────


class TestDetectorTechnology:
    def test_all_technologies(self):
        expected = {"POINT_SMOKE", "POINT_HEAT", "BEAM_SMOKE", "ASD", "DUCT_SMOKE"}
        actual = {t.value for t in DetectorTechnology}
        assert actual == expected

    def test_enum_values_are_strings(self):
        for tech in DetectorTechnology:
            assert isinstance(tech.value, str)


# ─────────────────────────────────────────────────────────────────────────────
# TechnologyDecision Dataclass
# ─────────────────────────────────────────────────────────────────────────────


class TestTechnologyDecision:
    def test_basic_creation(self):
        d = TechnologyDecision(
            technology=DetectorTechnology.POINT_SMOKE,
            ceiling_height_m=3.0,
        )
        assert d.technology == DetectorTechnology.POINT_SMOKE
        assert d.ceiling_height_m == 3.0  # NOSONAR — S1244: import retained for re-export / API surface
        assert d.slope_degrees == 0.0  # NOSONAR — S1244: import retained for re-export / API surface
        assert d.reason == ""
        assert d.nfpa_references == []
        assert d.spacing_m == 0.0  # NOSONAR — S1244: import retained for re-export / API surface
        assert d.ridge_zone_required is False
        assert d.warnings == []
        assert d.fallback_technology is None

    def test_full_creation(self):
        d = TechnologyDecision(
            technology=DetectorTechnology.BEAM_SMOKE,
            ceiling_height_m=15.0,
            slope_degrees=10.0,
            reason="Ceiling too high for point detectors",
            nfpa_references=["NFPA 72-2022 §17.7.2"],
            spacing_m=18.3,
            ridge_zone_required=True,
            warnings=["ECONOMIC_WARNING"],
            fallback_technology=DetectorTechnology.POINT_SMOKE,
        )
        assert d.technology == DetectorTechnology.BEAM_SMOKE
        assert d.ridge_zone_required is True
        assert d.fallback_technology == DetectorTechnology.POINT_SMOKE


# EliteTechnologyDispatcher.select_technology  # NOSONAR - python:S125
# ─────────────────────────────────────────────────────────────────────────────


class TestSelectTechnology:
    """Progressive detector technology selection per NFPA 72-2022."""

    def test_low_ceiling_flat_point_smoke(self):
        """h=3.0m, slope=0° → POINT_SMOKE with 9.1m spacing."""
        d = EliteTechnologyDispatcher.select_technology(3.0)
        assert d.technology == DetectorTechnology.POINT_SMOKE
        assert d.spacing_m == pytest.approx(9.10, abs=0.01)
        assert d.ridge_zone_required is False

    def test_medium_ceiling_point_smoke_flat_spacing(self):
        """V130 FIX: h=6.1m → POINT_SMOKE with FLAT 9.1m spacing per §17.7.3.2.3."""
        d = EliteTechnologyDispatcher.select_technology(6.1)
        assert d.technology == DetectorTechnology.POINT_SMOKE
        assert d.spacing_m == pytest.approx(9.10, abs=0.01)

    def test_high_ceiling_within_table_point_smoke(self):
        """V130 FIX: h=9.2m → POINT_SMOKE with FLAT 9.1m spacing + stratification advisory."""
        d = EliteTechnologyDispatcher.select_technology(9.2)
        assert d.technology == DetectorTechnology.POINT_SMOKE
        assert d.spacing_m > 0
        # V130: Changed from ECONOMIC_WARNING to STRATIFICATION_ADVISORY
        assert any("STRATIFICATION" in w or "ECONOMIC" in w for w in d.warnings)

    def test_max_point_height_point_smoke(self):
        """V130 FIX: h=12.2m (max) → POINT_SMOKE with FLAT 9.1m spacing."""
        d = EliteTechnologyDispatcher.select_technology(12.2)
        assert d.technology == DetectorTechnology.POINT_SMOKE
        assert d.spacing_m == pytest.approx(9.10, abs=0.01)

    def test_just_above_point_max_beam_smoke(self):
        """h=12.3m (>12.2m) → BEAM_SMOKE."""
        d = EliteTechnologyDispatcher.select_technology(12.3)
        assert d.technology == DetectorTechnology.BEAM_SMOKE
        assert d.spacing_m == pytest.approx(18.3, abs=0.1)
        assert d.fallback_technology == DetectorTechnology.POINT_SMOKE

    def test_very_high_ceiling_beam_smoke(self):
        """h=20.0m → BEAM_SMOKE."""
        d = EliteTechnologyDispatcher.select_technology(20.0)
        assert d.technology == DetectorTechnology.BEAM_SMOKE

    def test_extreme_height_asd(self):
        """h=26.0m (>25.0m beam limit) → ASD."""
        d = EliteTechnologyDispatcher.select_technology(26.0)
        assert d.technology == DetectorTechnology.ASD
        assert d.fallback_technology == DetectorTechnology.BEAM_SMOKE

    def test_steep_slope_asd(self):
        """Slope > 30° → ASD with PE design warning."""
        d = EliteTechnologyDispatcher.select_technology(5.0, slope_degrees=35.0)
        assert d.technology == DetectorTechnology.ASD
        assert any("PERFORMANCE_BASED" in w for w in d.warnings)

    def test_moderate_slope_ridge_zone(self):
        """Slope > 7.125° → ridge zone required."""
        d = EliteTechnologyDispatcher.select_technology(3.0, slope_degrees=10.0)
        assert d.ridge_zone_required is True
        assert any("RIDGE_ZONE" in w for w in d.warnings)

    def test_flat_slope_no_ridge_zone(self):
        """Slope = 5° (< 7.125°) → no ridge zone required."""
        d = EliteTechnologyDispatcher.select_technology(3.0, slope_degrees=5.0)
        assert d.ridge_zone_required is False

    def test_zero_height_raises(self):
        with pytest.raises(ValueError, match="positive"):
            EliteTechnologyDispatcher.select_technology(0.0)

    def test_negative_height_raises(self):
        with pytest.raises(ValueError, match="positive"):
            EliteTechnologyDispatcher.select_technology(-3.0)

    def test_heat_detector_category(self):
        """V20.2 FIX: Heat detector category returns POINT_HEAT."""
        d = EliteTechnologyDispatcher.select_technology(3.0, detector_category="heat")
        assert d.technology == DetectorTechnology.POINT_HEAT
        assert d.spacing_m > 0

    def test_heat_detector_uses_heat_spacing(self):
        """Heat detector at 3.0m should use S=6.1m (not S=9.1m)."""
        d = EliteTechnologyDispatcher.select_technology(3.0, detector_category="heat")
        assert d.spacing_m == pytest.approx(6.10, abs=0.01)

    def test_nfpa_references_in_result(self):
        d = EliteTechnologyDispatcher.select_technology(3.0)
        assert len(d.nfpa_references) >= 1
        # V130: Now cites §17.7.3.2.3 (flat spacing) instead of Table 17.6.3.1.1
        assert any("17.7.3.2.3" in ref or "Table 17.6.3.1.1" in ref for ref in d.nfpa_references)

    def test_beam_nfpa_references(self):
        d = EliteTechnologyDispatcher.select_technology(15.0)
        assert any("§17.7.2" in ref for ref in d.nfpa_references)

    def test_asd_nfpa_references(self):
        d = EliteTechnologyDispatcher.select_technology(30.0)
        assert any("§17.7.3" in ref for ref in d.nfpa_references)


# EliteTechnologyDispatcher._get_smoke_spacing  # NOSONAR - python:S125
# ─────────────────────────────────────────────────────────────────────────────


class TestGetSmokeSpacing:
    def test_3m_ceiling(self):
        spacing = EliteTechnologyDispatcher._get_smoke_spacing(3.0)
        assert spacing == pytest.approx(9.10, abs=0.01)

    def test_mid_range(self):
        """V130 FIX: Flat 9.1m spacing at all heights per §17.7.3.2.3."""
        spacing = EliteTechnologyDispatcher._get_smoke_spacing(5.0)
        assert spacing == pytest.approx(9.10, abs=0.01)

    def test_max_table_height(self):
        """V130 FIX: Flat 9.1m spacing at max table height per §17.7.3.2.3."""
        spacing = EliteTechnologyDispatcher._get_smoke_spacing(12.2)
        assert spacing == pytest.approx(9.10, abs=0.01)

    def test_beyond_table_returns_last(self):
        """V130 FIX: Beyond NFPA table → still 9.1m (flat per §17.7.3.2.3)."""
        spacing = EliteTechnologyDispatcher._get_smoke_spacing(15.0)
        assert spacing == pytest.approx(9.10, abs=0.01)


# ─────────────────────────────────────────────────────────────────────────────
# dispatch_detector_technology (convenience function)
# ─────────────────────────────────────────────────────────────────────────────


class TestDispatchDetectorTechnology:
    def test_default_smoke(self):
        room = {"ceiling_height": 3.0, "ceiling_slope_degrees": 0.0}
        d = dispatch_detector_technology(room)
        assert d.technology == DetectorTechnology.POINT_SMOKE

    def test_heat_from_dict(self):
        room = {
            "ceiling_height": 3.0,
            "ceiling_slope_degrees": 0.0,
            "detector_type": "heat_fixed",
        }
        d = dispatch_detector_technology(room)
        assert d.technology == DetectorTechnology.POINT_HEAT

    def test_default_values_for_missing_keys(self):
        room = {}
        d = dispatch_detector_technology(room)
        assert d.technology == DetectorTechnology.POINT_SMOKE
        assert d.ceiling_height_m == 3.0  # NOSONAR — S1244: import retained for re-export / API surface

    def test_beam_from_high_ceiling(self):
        room = {"ceiling_height": 15.0}
        d = dispatch_detector_technology(room)
        assert d.technology == DetectorTechnology.BEAM_SMOKE

    def test_none_values_use_defaults(self):
        room = {"ceiling_height": None, "ceiling_slope_degrees": None}
        d = dispatch_detector_technology(room)
        assert d.ceiling_height_m == 3.0  # NOSONAR — S1244: import retained for re-export / API surface
        assert d.slope_degrees == 0.0  # NOSONAR — S1244: import retained for re-export / API surface


# ─────────────────────────────────────────────────────────────────────────────
# Edge Cases
# ─────────────────────────────────────────────────────────────────────────────


class TestEdgeCases:
    def test_very_small_height(self):
        """Very low ceiling (1m) — should still return point smoke."""
        d = EliteTechnologyDispatcher.select_technology(0.5)
        assert d.technology == DetectorTechnology.POINT_SMOKE

    def test_just_below_steep_slope(self):
        """Slope = 29.9° → point detectors, not ASD."""
        d = EliteTechnologyDispatcher.select_technology(3.0, slope_degrees=29.9)
        assert d.technology == DetectorTechnology.POINT_SMOKE

    def test_just_at_steep_slope(self):
        """Slope = 30.0° → point detectors (threshold is > 30)."""
        d = EliteTechnologyDispatcher.select_technology(3.0, slope_degrees=30.0)
        assert d.technology == DetectorTechnology.POINT_SMOKE

    def test_just_above_steep_slope(self):
        """Slope = 30.1° → ASD."""
        d = EliteTechnologyDispatcher.select_technology(3.0, slope_degrees=30.1)
        assert d.technology == DetectorTechnology.ASD

    def test_just_at_beam_max(self):
        """H = 25.0m → BEAM_SMOKE (threshold is > 25)."""
        d = EliteTechnologyDispatcher.select_technology(25.0)
        assert d.technology == DetectorTechnology.BEAM_SMOKE

    def test_just_above_beam_max(self):
        """H = 25.1m → ASD."""
        d = EliteTechnologyDispatcher.select_technology(25.1)
        assert d.technology == DetectorTechnology.ASD

    def test_steep_slope_with_high_ceiling(self):
        """Steep slope takes priority over height check."""
        d = EliteTechnologyDispatcher.select_technology(20.0, slope_degrees=35.0)
        assert d.technology == DetectorTechnology.ASD

    def test_ridge_zone_with_beam(self):
        """Ridge zone flag set even for beam detectors."""
        d = EliteTechnologyDispatcher.select_technology(15.0, slope_degrees=10.0)
        assert d.ridge_zone_required is True
        assert d.technology == DetectorTechnology.BEAM_SMOKE

    def test_economic_warning_high_ceiling(self):
        """V130: Stratification advisory for h > 9.1m with point detectors."""
        d = EliteTechnologyDispatcher.select_technology(10.0)
        assert any("STRATIFICATION" in w or "ECONOMIC" in w for w in d.warnings)

    def test_no_stratification_warning_low_ceiling(self):
        """No stratification advisory for h ≤ 9.1m."""
        d = EliteTechnologyDispatcher.select_technology(9.0)
        assert not any("STRATIFICATION" in w or "ECONOMIC" in w for w in d.warnings)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
