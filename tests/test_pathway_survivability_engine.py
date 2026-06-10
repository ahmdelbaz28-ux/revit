"""
tests/test_pathway_survivability_engine.py
===========================================
Comprehensive test suite for:
  fireai/core/pathway_survivability_engine.py

NFPA 72-2022 §12.4 Pathway Survivability Classification.

SAFETY CRITICAL: Incorrect pathway survivability classification can
result in unprotected fire alarm cables burning through during a fire,
causing loss of alarm capability on upper floors — a life-safety hazard.

NFPA 72 References:
  §12.3.3 — Level 1 permitted ONLY in fully sprinklered buildings
  §12.3.4 — Level 2 minimum for high-rise, partial evac, voice evac
  §12.3.5 — Level 3 for staged evacuation in non-sprinklered buildings
  IBC §403 — High-rise definition: >23 m (75 ft)
"""

from __future__ import annotations

import math
import pytest

from fireai.core.pathway_survivability_engine import (
    BuildingSpec,
    SurvivabilityResult,
    CableRequirement,
    PathwaySurvivabilityEngine,
)
from fireai.core.contracts import (
    CableType,
    OccupancyCategory,
    PathwaySurvivabilityLevel,
)


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────


@pytest.fixture
def engine() -> PathwaySurvivabilityEngine:
    return PathwaySurvivabilityEngine()


# ─────────────────────────────────────────────────────────────────────────────
# BuildingSpec — Construction and Validation
# ─────────────────────────────────────────────────────────────────────────────


class TestBuildingSpec:
    """BuildingSpec construction and auto-detection logic."""

    def test_default_values(self):
        spec = BuildingSpec()
        assert spec.occupancy == OccupancyCategory.BUSINESS
        assert spec.height_m == 12.0
        assert spec.num_floors == 3
        assert spec.is_sprinklered is False
        assert spec.has_voice_evac is False
        assert spec.evacuation_type == "full"
        assert spec.is_high_rise is False

    def test_custom_values(self):
        spec = BuildingSpec(
            occupancy=OccupancyCategory.RESIDENTIAL,
            height_m=50.0,
            num_floors=15,
            is_sprinklered=True,
            has_voice_evac=True,
        )
        assert spec.occupancy == OccupancyCategory.RESIDENTIAL
        assert spec.height_m == 50.0
        assert spec.is_sprinklered is True
        assert spec.has_voice_evac is True

    def test_auto_detect_high_rise(self):
        """V20.2 FIX: Building >22.86m auto-detected as high-rise per IBC §403."""
        spec = BuildingSpec(height_m=23.0)
        assert spec.is_high_rise is True

    def test_just_below_high_rise_threshold(self):
        """Building at 22.86m exactly → NOT high-rise (must be >22.86)."""
        spec = BuildingSpec(height_m=22.86)
        assert spec.is_high_rise is False

    def test_just_above_high_rise_threshold(self):
        """Building at 22.87m → IS high-rise."""
        spec = BuildingSpec(height_m=22.87)
        assert spec.is_high_rise is True

    def test_nan_height_conservatively_high_rise(self):
        """V55 FIX: NaN height → conservatively assume high-rise."""
        spec = BuildingSpec(height_m=float("nan"))
        assert spec.is_high_rise is True

    def test_inf_height_conservatively_high_rise(self):
        """Inf height → conservatively assume high-rise."""
        spec = BuildingSpec(height_m=float("inf"))
        assert spec.is_high_rise is True

    def test_auto_detect_detention_occupancy(self):
        """DETENTION occupancy auto-sets has_detention=True."""
        spec = BuildingSpec(occupancy=OccupancyCategory.DETENTION)
        assert spec.has_detention is True

    def test_non_detention_no_auto_flag(self):
        """Non-detention occupancy does not auto-set has_detention."""
        spec = BuildingSpec(occupancy=OccupancyCategory.BUSINESS)
        assert spec.has_detention is False


# ─────────────────────────────────────────────────────────────────────────────
# PathwaySurvivabilityEngine — Level 1 Classification
# ─────────────────────────────────────────────────────────────────────────────


class TestLevel1Classification:
    """Level 1: Only permitted in fully sprinklered buildings with full evacuation."""

    def test_sprinklered_full_evac_office(self):
        """Simple sprinklered office → Level 1."""
        spec = BuildingSpec(
            occupancy=OccupancyCategory.BUSINESS,
            is_sprinklered=True,
            evacuation_type="full",
        )
        engine = PathwaySurvivabilityEngine()
        result = engine.classify(spec)
        assert result.building_level == PathwaySurvivabilityLevel.LEVEL_1
        assert result.compliant is True

    def test_sprinklered_full_evac_no_high_rise_no_voice(self):
        """Sprinklered + full evac + not high-rise + no voice → Level 1."""
        spec = BuildingSpec(
            is_sprinklered=True,
            evacuation_type="full",
            is_high_rise=False,
            has_voice_evac=False,
        )
        engine = PathwaySurvivabilityEngine()
        result = engine.classify(spec)
        assert result.building_level == PathwaySurvivabilityLevel.LEVEL_1


# ─────────────────────────────────────────────────────────────────────────────
# PathwaySurvivabilityEngine — Level 2 Classification
# ─────────────────────────────────────────────────────────────────────────────


class TestLevel2Classification:
    """Level 2: Required for non-sprinklered, high-rise, partial/staged evac, voice."""

    def test_non_sprinklered_requires_level_2(self):
        """§12.3.3: Non-sprinklered → Level 2 minimum."""
        spec = BuildingSpec(is_sprinklered=False)
        engine = PathwaySurvivabilityEngine()
        result = engine.classify(spec)
        assert result.building_level >= PathwaySurvivabilityLevel.LEVEL_2

    def test_high_rise_requires_level_2(self):
        """§12.3.4: High-rise → Level 2 minimum (even if sprinklered)."""
        spec = BuildingSpec(
            is_sprinklered=True,
            is_high_rise=True,
            evacuation_type="full",
        )
        engine = PathwaySurvivabilityEngine()
        result = engine.classify(spec)
        assert result.building_level >= PathwaySurvivabilityLevel.LEVEL_2

    def test_partial_evacuation_requires_level_2(self):
        """§12.3.4: Partial evacuation → Level 2 minimum."""
        spec = BuildingSpec(
            is_sprinklered=True,
            evacuation_type="partial",
        )
        engine = PathwaySurvivabilityEngine()
        result = engine.classify(spec)
        assert result.building_level >= PathwaySurvivabilityLevel.LEVEL_2

    def test_voice_evac_requires_level_2(self):
        """§12.3.4: Voice evacuation → Level 2 minimum."""
        spec = BuildingSpec(
            is_sprinklered=True,
            has_voice_evac=True,
            evacuation_type="full",
        )
        engine = PathwaySurvivabilityEngine()
        result = engine.classify(spec)
        assert result.building_level >= PathwaySurvivabilityLevel.LEVEL_2

    def test_staged_evacuation_sprinklered_level_2(self):
        """§12.3.4: Staged evacuation + sprinklered → Level 2 minimum."""
        spec = BuildingSpec(
            is_sprinklered=True,
            evacuation_type="staged",
        )
        engine = PathwaySurvivabilityEngine()
        result = engine.classify(spec)
        assert result.building_level >= PathwaySurvivabilityLevel.LEVEL_2

    def test_health_care_requires_level_2(self):
        """NFPA 101 §18/19: Health care → Level 2."""
        spec = BuildingSpec(
            occupancy=OccupancyCategory.HEALTH_CARE,
            is_sprinklered=True,
        )
        engine = PathwaySurvivabilityEngine()
        result = engine.classify(spec)
        assert result.building_level >= PathwaySurvivabilityLevel.LEVEL_2

    def test_detention_requires_level_2(self):
        """NFPA 101 §14/15: Detention → Level 2."""
        spec = BuildingSpec(
            occupancy=OccupancyCategory.DETENTION,
            is_sprinklered=True,
        )
        engine = PathwaySurvivabilityEngine()
        result = engine.classify(spec)
        assert result.building_level >= PathwaySurvivabilityLevel.LEVEL_2


# ─────────────────────────────────────────────────────────────────────────────
# PathwaySurvivabilityEngine — Level 3 Classification
# ─────────────────────────────────────────────────────────────────────────────


class TestLevel3Classification:
    """Level 3: Staged evacuation + non-sprinklered."""

    def test_staged_non_sprinklered_requires_level_3(self):
        """§12.3.5: Staged evacuation + non-sprinklered → Level 3."""
        spec = BuildingSpec(
            is_sprinklered=False,
            evacuation_type="staged",
        )
        engine = PathwaySurvivabilityEngine()
        result = engine.classify(spec)
        assert result.building_level == PathwaySurvivabilityLevel.LEVEL_3

    def test_staged_sprinklered_not_level_3(self):
        """Staged + sprinklered → Level 2 (NOT Level 3)."""
        spec = BuildingSpec(
            is_sprinklered=True,
            evacuation_type="staged",
        )
        engine = PathwaySurvivabilityEngine()
        result = engine.classify(spec)
        assert result.building_level == PathwaySurvivabilityLevel.LEVEL_2


# ─────────────────────────────────────────────────────────────────────────────
# PathwaySurvivabilityEngine — Cable Requirements
# ─────────────────────────────────────────────────────────────────────────────


class TestCableRequirements:
    """Verify cable type and enclosure requirements per survivability level."""

    def test_level_1_riser_uses_fplr(self, engine):
        """Level 1: Riser cable = FPLR."""
        spec = BuildingSpec(is_sprinklered=True, evacuation_type="full")
        result = engine.classify(spec)
        riser = [r for r in result.cable_requirements if r.route_type == "riser"]
        assert len(riser) == 1
        assert riser[0].cable_type == CableType.FPLR
        assert riser[0].in_rated_enclosure is False

    def test_level_1_horizontal_uses_fpl(self, engine):
        """Level 1: Horizontal cable = FPL."""
        spec = BuildingSpec(is_sprinklered=True, evacuation_type="full")
        result = engine.classify(spec)
        horiz = [r for r in result.cable_requirements if r.route_type == "horizontal"]
        assert len(horiz) == 1
        assert horiz[0].cable_type == CableType.FPL

    def test_level_2_riser_uses_ci(self, engine):
        """Level 2: Riser cable = CI."""
        spec = BuildingSpec(is_sprinklered=False)
        result = engine.classify(spec)
        riser = [r for r in result.cable_requirements if r.route_type == "riser"]
        assert len(riser) == 1
        assert riser[0].cable_type == CableType.CI

    def test_level_3_riser_ci_in_rated_enclosure(self, engine):
        """Level 3: Riser = CI cable in 2-hour rated enclosure."""
        spec = BuildingSpec(is_sprinklered=False, evacuation_type="staged")
        result = engine.classify(spec)
        riser = [r for r in result.cable_requirements if r.route_type == "riser"]
        assert len(riser) == 1
        assert riser[0].cable_type == CableType.CI
        assert riser[0].in_rated_enclosure is True
        assert riser[0].enclosure_rating_hr == 2.0

    def test_plenum_always_fplp_or_ci(self, engine):
        """Plenum always requires FPLP minimum; Level 2+ requires CI."""
        # Level 1: plenum should be FPLP (or CI, depending on impl)
        spec1 = BuildingSpec(is_sprinklered=True, evacuation_type="full")
        r1 = engine.classify(spec1)
        plenum1 = [r for r in r1.cable_requirements if r.route_type == "plenum"]
        assert len(plenum1) == 1
        # Level 2+: plenum should be CI
        spec2 = BuildingSpec(is_sprinklered=False)
        r2 = engine.classify(spec2)
        plenum2 = [r for r in r2.cable_requirements if r.route_type == "plenum"]
        assert plenum2[0].cable_type == CableType.CI

    def test_all_four_route_types_generated(self, engine):
        """All four route types must be present in cable requirements."""
        spec = BuildingSpec(is_sprinklered=True, evacuation_type="full")
        result = engine.classify(spec)
        route_types = {r.route_type for r in result.cable_requirements}
        assert route_types == {"riser", "horizontal", "plenum", "general"}

    def test_nfpa_reference_in_cable_requirements(self, engine):
        """Each cable requirement must reference an NFPA section."""
        spec = BuildingSpec(is_sprinklered=True, evacuation_type="full")
        result = engine.classify(spec)
        for req in result.cable_requirements:
            assert "NFPA 72" in req.nfpa_reference


# ─────────────────────────────────────────────────────────────────────────────
# PathwaySurvivabilityEngine — Warnings and Errors
# ─────────────────────────────────────────────────────────────────────────────


class TestWarningsAndErrors:
    """Warning and error generation in classification."""

    def test_high_rise_without_voice_evac_warns(self, engine):
        """High-rise without voice evacuation should generate warning."""
        spec = BuildingSpec(
            is_sprinklered=True,
            is_high_rise=True,
            has_voice_evac=False,
        )
        result = engine.classify(spec)
        assert any("voice" in w.lower() for w in result.warnings)

    def test_many_floors_not_high_rise_warns(self, engine):
        """10+ floors but not flagged as high-rise → verify warning."""
        spec = BuildingSpec(
            num_floors=12,
            height_m=20.0,  # < 22.86m so not high-rise
        )
        result = engine.classify(spec)
        assert any("verify height" in w.lower() for w in result.warnings)

    def test_compliant_when_no_errors(self, engine):
        """Result should be compliant when no errors."""
        spec = BuildingSpec(is_sprinklered=True, evacuation_type="full")
        result = engine.classify(spec)
        assert result.compliant is True
        assert len(result.errors) == 0


# ─────────────────────────────────────────────────────────────────────────────
# PathwaySurvivabilityEngine — get_required_cable_type
# ─────────────────────────────────────────────────────────────────────────────


class TestGetRequiredCableType:
    """Convenience method for cable type lookup."""

    def test_general_cable_type_level_1(self):
        """Level 1 general cable = FPL."""
        engine = PathwaySurvivabilityEngine()
        spec = BuildingSpec(is_sprinklered=True, evacuation_type="full")
        cable = engine.get_required_cable_type(spec, "general")
        assert cable == CableType.FPL

    def test_riser_cable_type_level_2(self):
        """Level 2 riser cable = CI."""
        engine = PathwaySurvivabilityEngine()
        spec = BuildingSpec(is_sprinklered=False)
        cable = engine.get_required_cable_type(spec, "riser")
        assert cable == CableType.CI

    def test_unknown_route_returns_fpl_default(self):
        """Unknown route type returns FPL as safe default."""
        engine = PathwaySurvivabilityEngine()
        spec = BuildingSpec(is_sprinklered=True, evacuation_type="full")
        cable = engine.get_required_cable_type(spec, "nonexistent")
        assert cable == CableType.FPL


# ─────────────────────────────────────────────────────────────────────────────
# PathwaySurvivabilityEngine — Classification Rationale
# ─────────────────────────────────────────────────────────────────────────────


class TestClassificationRationale:
    """Audit trail: classification rationale must be recorded."""

    def test_rationale_not_empty(self, engine):
        """Classification must record rationale for audit."""
        spec = BuildingSpec(is_sprinklered=False)
        result = engine.classify(spec)
        assert len(result.classification_rationale) > 0

    def test_rationale_mentions_nfpa_sections(self, engine):
        """Rationale must cite specific NFPA sections."""
        spec = BuildingSpec(is_sprinklered=False)
        result = engine.classify(spec)
        rationale_text = " ".join(result.classification_rationale)
        assert "§12.3" in rationale_text

    def test_rationale_for_level_3(self, engine):
        """Level 3 must explain staged + non-sprinklered reasoning."""
        spec = BuildingSpec(is_sprinklered=False, evacuation_type="staged")
        result = engine.classify(spec)
        rationale_text = " ".join(result.classification_rationale)
        assert "staged" in rationale_text.lower() or "§12.3.5" in rationale_text


# ─────────────────────────────────────────────────────────────────────────────
# PathwaySurvivabilityEngine — SurvivabilityResult Defaults
# ─────────────────────────────────────────────────────────────────────────────


class TestSurvivabilityResultDefaults:
    """V114 FIX: SurvivabilityResult must default to non-compliant."""

    def test_default_compliant_is_false(self):
        """Fail-safe: unevaluated result must NOT claim compliance."""
        result = SurvivabilityResult()
        assert result.compliant is False

    def test_default_errors_empty(self):
        result = SurvivabilityResult()
        assert result.errors == []

    def test_default_warnings_empty(self):
        result = SurvivabilityResult()
        assert result.warnings == []

    def test_default_level_is_1(self):
        result = SurvivabilityResult()
        assert result.building_level == PathwaySurvivabilityLevel.LEVEL_1

    def test_nfpa_version_present(self):
        result = SurvivabilityResult()
        assert "NFPA 72-2022" in result.nfpa_version


# ─────────────────────────────────────────────────────────────────────────────
# Integration — Real-World Scenarios
# ─────────────────────────────────────────────────────────────────────────────


class TestIntegrationScenarios:
    """End-to-end scenarios representing real buildings."""

    def test_hotel_high_rise_sprinklered_voice(self):
        """Typical hotel: high-rise, sprinklered, voice evac → Level 2."""
        spec = BuildingSpec(
            occupancy=OccupancyCategory.RESIDENTIAL,
            height_m=35.0,
            num_floors=12,
            is_sprinklered=True,
            has_voice_evac=True,
            evacuation_type="full",
        )
        engine = PathwaySurvivabilityEngine()
        result = engine.classify(spec)
        assert result.building_level == PathwaySurvivabilityLevel.LEVEL_2
        assert result.compliant is True

    def test_hospital_sprinklered(self):
        """Hospital: health care, sprinklered → Level 2."""
        spec = BuildingSpec(
            occupancy=OccupancyCategory.HEALTH_CARE,
            is_sprinklered=True,
            evacuation_type="full",
        )
        engine = PathwaySurvivabilityEngine()
        result = engine.classify(spec)
        assert result.building_level >= PathwaySurvivabilityLevel.LEVEL_2

    def test_prison_non_sprinklered_staged(self):
        """Prison: detention, non-sprinklered, staged → Level 3."""
        spec = BuildingSpec(
            occupancy=OccupancyCategory.DETENTION,
            is_sprinklered=False,
            evacuation_type="staged",
        )
        engine = PathwaySurvivabilityEngine()
        result = engine.classify(spec)
        assert result.building_level == PathwaySurvivabilityLevel.LEVEL_3

    def test_small_office_sprinklered(self):
        """Small sprinklered office → Level 1."""
        spec = BuildingSpec(
            occupancy=OccupancyCategory.BUSINESS,
            height_m=10.0,
            num_floors=2,
            is_sprinklered=True,
            evacuation_type="full",
        )
        engine = PathwaySurvivabilityEngine()
        result = engine.classify(spec)
        assert result.building_level == PathwaySurvivabilityLevel.LEVEL_1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
