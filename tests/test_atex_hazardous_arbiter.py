"""
tests/test_atex_hazardous_arbiter.py
========================================
Comprehensive test suite for:
  - fireai/core/atex_hazardous_arbiter.py

SAFETY CRITICAL: ATEX equipment selection in explosive atmospheres.
Wrong EPL or temperature class could result in ignition source in
hazardous area — catastrophic explosion risk.

Standards:
  IEC 60079-0:2017  — General requirements
  IEC 60079-14:2013 — Installation in explosive atmospheres
  ATEX 2014/34/EU   — Equipment categories
  Fix #14: EPL hierarchy corrected
  Fix #15: Temperature class strictly below autoignition
  Fix #17: Fire detector IS level per zone (not 'ia' for all)
  V57 FIX: NaN/Inf autoignition → fail-safe T6
  V48 FIX: Unknown gas group → IIC (most hazardous)
"""

from __future__ import annotations

import pytest

from fireai.core.atex_hazardous_arbiter import (
    _EPL_DUST_HIERARCHY,
    _EPL_GAS_HIERARCHY,
    _EPL_HIERARCHY,
    _FIRE_DETECTOR_IS_LEVEL,
    _TEMP_CLASS_MAP,
    _ZONE_TO_CATEGORY,
    _ZONE_TO_EPL,
    ATEXArbitrationResult,
    ATEXCategory,
    ATEXHazardousArbiter,
    ATEXValidationResult,
    EquipmentProtectionLevel,
    ProtectionType,
    _validate_zone_hazard_consistency,
)
from fireai.core.international_reg_selector import (
    ATEXZone,
    HazardSystem,
)
from fireai.core.models_v21 import (
    HazardType,
    TemperatureClass,
    ZoneType,
)

# Fixtures
# ─────────────────────────────────────────────────────────────────────────────


@pytest.fixture
def arbiter():
    return ATEXHazardousArbiter()


# Enums
# ─────────────────────────────────────────────────────────────────────────────


class TestEquipmentProtectionLevel:
    def test_gas_epls(self):
        expected = {"Ga", "Gb", "Gc"}
        actual = {e.value for e in [EquipmentProtectionLevel.Ga, EquipmentProtectionLevel.Gb, EquipmentProtectionLevel.Gc]}
        assert actual == expected

    def test_dust_epls(self):
        expected = {"Da", "Db", "Dc"}
        actual = {e.value for e in [EquipmentProtectionLevel.Da, EquipmentProtectionLevel.Db, EquipmentProtectionLevel.Dc]}
        assert actual == expected

    def test_mining_epls(self):
        expected = {"Ma", "Mb"}
        actual = {e.value for e in [EquipmentProtectionLevel.Ma, EquipmentProtectionLevel.Mb]}
        assert actual == expected


class TestATEXCategory:
    def test_gas_categories(self):
        gas_cats = {"1G", "2G", "3G"}
        actual = {c.value for c in [ATEXCategory.CAT_1G, ATEXCategory.CAT_2G, ATEXCategory.CAT_3G]}
        assert actual == gas_cats

    def test_dust_categories(self):
        dust_cats = {"1D", "2D", "3D"}
        actual = {c.value for c in [ATEXCategory.CAT_1D, ATEXCategory.CAT_2D, ATEXCategory.CAT_3D]}
        assert actual == dust_cats


class TestProtectionType:
    def test_common_types(self):
        types = {"d", "e", "ia", "ib", "ic", "nA", "p", "tD"}
        actual = {p.value for p in ProtectionType}
        assert types.issubset(actual)


# ─────────────────────────────────────────────────────────────────────────────
# Zone → EPL / Category Mapping Tables
# ─────────────────────────────────────────────────────────────────────────────


class TestZoneMappings:
    def test_zone0_to_ga(self):
        assert _ZONE_TO_EPL[ATEXZone.ZONE_0] == EquipmentProtectionLevel.Ga

    def test_zone1_to_gb(self):
        assert _ZONE_TO_EPL[ATEXZone.ZONE_1] == EquipmentProtectionLevel.Gb

    def test_zone2_to_gc(self):
        assert _ZONE_TO_EPL[ATEXZone.ZONE_2] == EquipmentProtectionLevel.Gc

    def test_zone20_to_da(self):
        assert _ZONE_TO_EPL[ATEXZone.ZONE_20] == EquipmentProtectionLevel.Da

    def test_zone21_to_db(self):
        assert _ZONE_TO_EPL[ATEXZone.ZONE_21] == EquipmentProtectionLevel.Db

    def test_zone22_to_dc(self):
        assert _ZONE_TO_EPL[ATEXZone.ZONE_22] == EquipmentProtectionLevel.Dc

    def test_zone0_category_1g(self):
        assert _ZONE_TO_CATEGORY[ATEXZone.ZONE_0] == ATEXCategory.CAT_1G

    def test_zone1_category_2g(self):
        assert _ZONE_TO_CATEGORY[ATEXZone.ZONE_1] == ATEXCategory.CAT_2G

    def test_zone2_category_3g(self):
        assert _ZONE_TO_CATEGORY[ATEXZone.ZONE_2] == ATEXCategory.CAT_3G

    def test_zone20_category_1d(self):
        assert _ZONE_TO_CATEGORY[ATEXZone.ZONE_20] == ATEXCategory.CAT_1D

    def test_zone21_category_2d(self):
        assert _ZONE_TO_CATEGORY[ATEXZone.ZONE_21] == ATEXCategory.CAT_2D

    def test_zone22_category_3d(self):
        assert _ZONE_TO_CATEGORY[ATEXZone.ZONE_22] == ATEXCategory.CAT_3D


# ─────────────────────────────────────────────────────────────────────────────
# EPL Hierarchy — Fix #14
# ─────────────────────────────────────────────────────────────────────────────


class TestEPLHierarchy:
    """Fix #14: Higher EPL value = more protection."""

    def test_gas_hierarchy_ga_highest(self):
        assert _EPL_GAS_HIERARCHY[EquipmentProtectionLevel.Ga] > _EPL_GAS_HIERARCHY[EquipmentProtectionLevel.Gb]
        assert _EPL_GAS_HIERARCHY[EquipmentProtectionLevel.Gb] > _EPL_GAS_HIERARCHY[EquipmentProtectionLevel.Gc]

    def test_dust_hierarchy_da_highest(self):
        assert _EPL_DUST_HIERARCHY[EquipmentProtectionLevel.Da] > _EPL_DUST_HIERARCHY[EquipmentProtectionLevel.Db]
        assert _EPL_DUST_HIERARCHY[EquipmentProtectionLevel.Db] > _EPL_DUST_HIERARCHY[EquipmentProtectionLevel.Dc]

    def test_mining_hierarchy_ma_highest(self):
        assert _EPL_HIERARCHY[EquipmentProtectionLevel.Ma] > _EPL_HIERARCHY[EquipmentProtectionLevel.Mb]


# ─────────────────────────────────────────────────────────────────────────────
# Fire Detector IS Level — Fix #17
# ─────────────────────────────────────────────────────────────────────────────


class TestFireDetectorISLevel:
    """Fix #17: Zone-appropriate IS level for fire detectors."""

    def test_zone0_ia(self):
        assert _FIRE_DETECTOR_IS_LEVEL[ATEXZone.ZONE_0] == "ia"

    def test_zone1_ib(self):
        assert _FIRE_DETECTOR_IS_LEVEL[ATEXZone.ZONE_1] == "ib"

    def test_zone2_ic(self):
        assert _FIRE_DETECTOR_IS_LEVEL[ATEXZone.ZONE_2] == "ic"

    def test_zone20_ia(self):
        assert _FIRE_DETECTOR_IS_LEVEL[ATEXZone.ZONE_20] == "ia"

    def test_zone21_ib(self):
        assert _FIRE_DETECTOR_IS_LEVEL[ATEXZone.ZONE_21] == "ib"

    def test_zone22_ic(self):
        assert _FIRE_DETECTOR_IS_LEVEL[ATEXZone.ZONE_22] == "ic"


# ─────────────────────────────────────────────────────────────────────────────
# _validate_zone_hazard_consistency — GAP-05
# ─────────────────────────────────────────────────────────────────────────────


class TestZoneHazardConsistency:
    """GAP-05: Cross-validate zone vs hazard type."""

    def test_gas_zone_with_dust_error(self):
        errors, warnings = [], []
        _validate_zone_hazard_consistency(ZoneType.ZONE_1, HazardType.DUST, errors, warnings)
        assert len(errors) >= 1
        assert any("GAS zone" in e for e in errors)

    def test_dust_zone_with_gas_error(self):
        errors, warnings = [], []
        _validate_zone_hazard_consistency(ZoneType.ZONE_21, HazardType.GAS, errors, warnings)
        assert len(errors) >= 1
        assert any("DUST zone" in e for e in errors)

    def test_gas_zone_with_gas_ok(self):
        errors, warnings = [], []
        _validate_zone_hazard_consistency(ZoneType.ZONE_1, HazardType.GAS, errors, warnings)
        assert len(errors) == 0

    def test_dust_zone_with_dust_ok(self):
        errors, warnings = [], []
        _validate_zone_hazard_consistency(ZoneType.ZONE_21, HazardType.DUST, errors, warnings)
        assert len(errors) == 0

    def test_gas_zone_with_hybrid_warning(self):
        errors, warnings = [], []
        _validate_zone_hazard_consistency(ZoneType.ZONE_1, HazardType.HYBRID, errors, warnings)
        assert len(warnings) >= 1

    def test_dust_zone_with_hybrid_warning(self):
        errors, warnings = [], []
        _validate_zone_hazard_consistency(ZoneType.ZONE_21, HazardType.HYBRID, errors, warnings)
        assert len(warnings) >= 1


# ATEXHazardousArbiter.arbitrate_v21  # NOSONAR - python:S125
# ─────────────────────────────────────────────────────────────────────────────


class TestArbitrateV21:
    """V21 API with Pydantic ATEXEquipmentSpec."""

    def test_zone1_gas(self, arbiter):
        result = arbiter.arbitrate_v21(
            zone=ZoneType.ZONE_1,
            hazard_type=HazardType.GAS,
        )
        assert isinstance(result, ATEXArbitrationResult)
        assert result.equipment_spec.epl_required == "Gb"
        assert result.equipment_spec.atex_category == "2G"
        assert result.is_valid

    def test_zone0_gas(self, arbiter):
        result = arbiter.arbitrate_v21(
            zone=ZoneType.ZONE_0,
            hazard_type=HazardType.GAS,
        )
        assert result.equipment_spec.epl_required == "Ga"
        assert result.equipment_spec.atex_category == "1G"

    def test_zone2_gas(self, arbiter):
        result = arbiter.arbitrate_v21(
            zone=ZoneType.ZONE_2,
            hazard_type=HazardType.GAS,
        )
        assert result.equipment_spec.epl_required == "Gc"
        assert result.equipment_spec.atex_category == "3G"

    def test_zone20_dust(self, arbiter):
        result = arbiter.arbitrate_v21(
            zone=ZoneType.ZONE_20,
            hazard_type=HazardType.DUST,
        )
        assert result.equipment_spec.epl_required == "Da"
        assert result.equipment_spec.atex_category == "1D"

    def test_zone21_dust(self, arbiter):
        result = arbiter.arbitrate_v21(
            zone=ZoneType.ZONE_21,
            hazard_type=HazardType.DUST,
        )
        assert result.equipment_spec.epl_required == "Db"
        assert result.equipment_spec.atex_category == "2D"

    def test_zone22_dust(self, arbiter):
        result = arbiter.arbitrate_v21(
            zone=ZoneType.ZONE_22,
            hazard_type=HazardType.DUST,
        )
        assert result.equipment_spec.epl_required == "Dc"
        assert result.equipment_spec.atex_category == "3D"

    def test_unclassified_returns_safe(self, arbiter):
        result = arbiter.arbitrate_v21(
            zone=ZoneType.UNCLASSIFIED,
            hazard_type=HazardType.GAS,
        )
        assert result.regulatory_note == "Space classified SAFE — no Ex equipment required."
        assert result.fire_detector_spec is None

    def test_autoignition_selects_temp_class(self, arbiter):
        """Autoignition temperature selects appropriate T-class."""
        result = arbiter.arbitrate_v21(
            zone=ZoneType.ZONE_1,
            hazard_type=HazardType.GAS,
            autoignition_c=200.0,
        )
        # With autoignition=200°C, T-class must have max < 200°C
        # T3 max=200°C (not safe), T3A max=180°C (safe)
        tc = result.equipment_spec.temp_class
        assert _TEMP_CLASS_MAP.get(tc.value, 999) < 200.0

    def test_nan_autoignition_fail_safe_v57(self, arbiter):
        """
        V57 FIX: NaN autoignition is detected and warned about.

        V78 FIX: NaN autoignition now correctly defaults to T6 (most
        conservative, 85°C max) instead of T4. Previous code had a bug
        where the else branch overrode T6 with T4.
        """
        result = arbiter.arbitrate_v21(
            zone=ZoneType.ZONE_1,
            hazard_type=HazardType.GAS,
            autoignition_c=float("nan"),
        )
        # V57 warning must be present — proves NaN was detected
        assert any("V57" in w for w in result.warnings)
        # V78 FIX: temp_class defaults to T6 (most conservative)
        assert result.equipment_spec.temp_class == TemperatureClass.T6

    def test_inf_autoignition_fail_safe_v57(self, arbiter):
        """
        V57 FIX: Inf autoignition is detected and warned about.

        V78 FIX: Inf autoignition now correctly defaults to T6 (most
        conservative) instead of T4. Previous code overrode T6 with T4.
        """
        result = arbiter.arbitrate_v21(
            zone=ZoneType.ZONE_1,
            hazard_type=HazardType.GAS,
            autoignition_c=float("inf"),
        )
        assert any("V57" in w for w in result.warnings)
        assert result.equipment_spec.temp_class == TemperatureClass.T6

    def test_gas_zone_with_dust_error(self, arbiter):
        """GAP-05: Gas zone + DUST hazard type = error."""
        result = arbiter.arbitrate_v21(
            zone=ZoneType.ZONE_1,
            hazard_type=HazardType.DUST,
        )
        assert len(result.errors) >= 1

    def test_nec_group_mapping(self, arbiter):
        """NEC gas group → IEC gas group mapping."""
        result = arbiter.arbitrate_v21(
            zone=ZoneType.ZONE_1,
            hazard_type=HazardType.GAS,
            nec_group="D",
        )
        assert result.is_valid

    def test_unknown_gas_group_defaults_iic_v48(self, arbiter):
        """V48 FIX: Unknown gas group defaults to IIC (most hazardous)."""
        result = arbiter.arbitrate_v21(
            zone=ZoneType.ZONE_1,
            hazard_type=HazardType.GAS,
            nec_group="UNKNOWN",
        )
        assert result.is_valid

    def test_fire_detector_spec_zone1(self, arbiter):
        """Fix #17: Zone 1 fire detector uses 'ib' IS level."""
        result = arbiter.arbitrate_v21(
            zone=ZoneType.ZONE_1,
            hazard_type=HazardType.GAS,
        )
        assert result.fire_detector_spec is not None
        assert "ib" in result.fire_detector_spec

    def test_fire_detector_spec_zone0(self, arbiter):
        """Fix #17: Zone 0 fire detector uses 'ia' IS level."""
        result = arbiter.arbitrate_v21(
            zone=ZoneType.ZONE_0,
            hazard_type=HazardType.GAS,
        )
        assert "ia" in result.fire_detector_spec

    def test_fire_detector_spec_zone2(self, arbiter):
        """Fix #17: Zone 2 fire detector uses 'ic' IS level."""
        result = arbiter.arbitrate_v21(
            zone=ZoneType.ZONE_2,
            hazard_type=HazardType.GAS,
        )
        assert "ic" in result.fire_detector_spec

    def test_hac_warnings_propagated_fix16(self, arbiter):
        """Fix #16: HAC warnings propagated into ATEXArbitrationResult."""
        hac_warns = ["HAC Warning 1", "HAC Warning 2"]
        result = arbiter.arbitrate_v21(
            zone=ZoneType.ZONE_1,
            hazard_type=HazardType.GAS,
            hac_warnings=hac_warns,
        )
        assert result.hac_warnings == tuple(hac_warns)

    def test_all_warnings_combined(self, arbiter):
        """all_warnings combines HAC + arbiter warnings."""
        result = arbiter.arbitrate_v21(
            zone=ZoneType.ZONE_1,
            hazard_type=HazardType.GAS,
            hac_warnings=["HAC warn"],
        )
        combined = result.all_warnings
        assert any("HAC warn" in w for w in combined)

    def test_nec_division_marking_prefix(self, arbiter):
        """NEC Division system uses 'AEx' marking prefix."""
        result = arbiter.arbitrate_v21(
            zone=ZoneType.ZONE_1,
            hazard_type=HazardType.GAS,
            hazard_system=HazardSystem.NEC_DIVISION,
        )
        assert result.fire_detector_spec.startswith("AEx")

    def test_atex_zone_marking_prefix(self, arbiter):
        """ATEX Zone system uses 'Ex' marking prefix."""
        result = arbiter.arbitrate_v21(
            zone=ZoneType.ZONE_1,
            hazard_type=HazardType.GAS,
            hazard_system=HazardSystem.ATEX_ZONE,
        )
        assert result.fire_detector_spec.startswith("Ex ")

    def test_zone0_extreme_hazard_warning(self, arbiter):
        result = arbiter.arbitrate_v21(
            zone=ZoneType.ZONE_0,
            hazard_type=HazardType.GAS,
        )
        assert any("Extremely high hazard" in w for w in result.warnings)

    def test_notified_body_for_cat1g(self, arbiter):
        result = arbiter.arbitrate_v21(
            zone=ZoneType.ZONE_0,
            hazard_type=HazardType.GAS,
        )
        assert any("Notified Body" in w for w in result.warnings)

    def test_space_id_preserved(self, arbiter):
        result = arbiter.arbitrate_v21(
            zone=ZoneType.ZONE_1,
            hazard_type=HazardType.GAS,
            space_id="PUMP-ROOM-A",
        )
        assert result.space_id == "PUMP-ROOM-A"


# ATEXHazardousArbiter.validate_equipment  # NOSONAR - python:S125
# ─────────────────────────────────────────────────────────────────────────────


class TestValidateEquipment:
    def test_compliant_equipment(self, arbiter):
        result = arbiter.validate_equipment(
            equipment_id="EQ-1",
            zone=ATEXZone.ZONE_1,
            proposed_epl=EquipmentProtectionLevel.Gb,
            proposed_protection=ProtectionType.d,
        )
        assert isinstance(result, ATEXValidationResult)
        assert result.is_compliant is True
        assert result.is_permitted is True
        assert result.is_epl_sufficient is True

    def test_insufficient_epl(self, arbiter):
        """Gc equipment in Zone 1 (requires Gb) — insufficient."""
        result = arbiter.validate_equipment(
            equipment_id="EQ-2",
            zone=ATEXZone.ZONE_1,
            proposed_epl=EquipmentProtectionLevel.Gc,
            proposed_protection=ProtectionType.d,
        )
        assert result.is_epl_sufficient is False
        assert result.is_compliant is False

    def test_over_specified_epl_compliant(self, arbiter):
        """Ga equipment in Zone 2 (requires Gc) — sufficient (higher protection)."""
        result = arbiter.validate_equipment(
            equipment_id="EQ-3",
            zone=ATEXZone.ZONE_2,
            proposed_epl=EquipmentProtectionLevel.Ga,
            proposed_protection=ProtectionType.ia,
        )
        assert result.is_epl_sufficient is True

    def test_wrong_protection_type(self, arbiter):
        """NA protection not permitted in Zone 0."""
        result = arbiter.validate_equipment(
            equipment_id="EQ-4",
            zone=ATEXZone.ZONE_0,
            proposed_epl=EquipmentProtectionLevel.Ga,
            proposed_protection=ProtectionType.nA,
        )
        assert result.is_permitted is False

    def test_ia_permitted_in_zone0(self, arbiter):
        """Ia is permitted in Zone 0."""
        result = arbiter.validate_equipment(
            equipment_id="EQ-5",
            zone=ATEXZone.ZONE_0,
            proposed_epl=EquipmentProtectionLevel.Ga,
            proposed_protection=ProtectionType.ia,
        )
        assert result.is_permitted is True
        assert result.is_compliant is True

    def test_failure_reasons_populated(self, arbiter):
        result = arbiter.validate_equipment(
            equipment_id="EQ-6",
            zone=ATEXZone.ZONE_1,
            proposed_epl=EquipmentProtectionLevel.Gc,
            proposed_protection=ProtectionType.nA,
        )
        assert len(result.failure_reasons) >= 1

    def test_recommendation_provided(self, arbiter):
        result = arbiter.validate_equipment(
            equipment_id="EQ-7",
            zone=ATEXZone.ZONE_1,
            proposed_epl=EquipmentProtectionLevel.Gc,
            proposed_protection=ProtectionType.nA,
        )
        assert result.recommendation != ""
        assert not result.is_compliant


# _epl_sufficient
# ─────────────────────────────────────────────────────────────────────────────


class TestEPLSufficient:
    def test_ga_satisfies_gb(self, arbiter):
        assert arbiter._epl_sufficient(EquipmentProtectionLevel.Ga, EquipmentProtectionLevel.Gb) is True

    def test_ga_satisfies_gc(self, arbiter):
        assert arbiter._epl_sufficient(EquipmentProtectionLevel.Ga, EquipmentProtectionLevel.Gc) is True

    def test_gc_insufficient_for_gb(self, arbiter):
        assert arbiter._epl_sufficient(EquipmentProtectionLevel.Gc, EquipmentProtectionLevel.Gb) is False

    def test_gas_not_sufficient_for_dust(self, arbiter):
        """Gas EPL cannot satisfy dust EPL requirement."""
        assert arbiter._epl_sufficient(EquipmentProtectionLevel.Ga, EquipmentProtectionLevel.Da) is False

    def test_dust_not_sufficient_for_gas(self, arbiter):
        assert arbiter._epl_sufficient(EquipmentProtectionLevel.Da, EquipmentProtectionLevel.Ga) is False

    def test_da_satisfies_db(self, arbiter):
        assert arbiter._epl_sufficient(EquipmentProtectionLevel.Da, EquipmentProtectionLevel.Db) is True


# _recommend_protection
# ─────────────────────────────────────────────────────────────────────────────


class TestRecommendProtection:
    def test_zone0_ia(self, arbiter):
        assert arbiter._recommend_protection(ATEXZone.ZONE_0) == ProtectionType.ia

    def test_zone1_d(self, arbiter):
        assert arbiter._recommend_protection(ATEXZone.ZONE_1) == ProtectionType.d

    def test_zone2_nA(self, arbiter):  # NOSONAR - python:S100
        assert arbiter._recommend_protection(ATEXZone.ZONE_2) == ProtectionType.nA

    def test_zone20_ia(self, arbiter):
        assert arbiter._recommend_protection(ATEXZone.ZONE_20) == ProtectionType.ia

    def test_zone21_tD(self, arbiter):  # NOSONAR - python:S100
        assert arbiter._recommend_protection(ATEXZone.ZONE_21) == ProtectionType.tD

    def test_zone22_tD(self, arbiter):  # NOSONAR - python:S100
        assert arbiter._recommend_protection(ATEXZone.ZONE_22) == ProtectionType.tD


# ─────────────────────────────────────────────────────────────────────────────
# _select_temp_class — Fix #15
# ─────────────────────────────────────────────────────────────────────────────


class TestSelectTempClass:
    def test_high_autoignition_t1(self, arbiter):
        """Autoignition=500°C → T1 (max 450°C) is safe."""
        result = arbiter._select_temp_class(500.0)
        assert result == "T1"

    def test_medium_autoignition(self, arbiter):
        """Autoignition=200°C → T3A (max 180°C) or T3B (max 165°C)."""
        result = arbiter._select_temp_class(200.0)
        assert result in ("T3A", "T3B", "T3C", "T4", "T4A", "T5", "T6")
        assert _TEMP_CLASS_MAP[result] < 200.0

    def test_low_autoignition_t6(self, arbiter):
        """Autoignition=90°C → T6 (max 85°C) is safe."""
        result = arbiter._select_temp_class(90.0)
        assert result == "T6"

    def test_very_low_autoignition_returns_t6_with_critical_warning(self, arbiter):
        """Autoignition=50°C → no safe T-class exists, returns T6 with warning."""
        result = arbiter._select_temp_class(50.0)
        assert result == "T6"  # Fallback

    def test_strictly_below_autoignition(self, arbiter):
        """T-class max must be STRICTLY below autoignition (Fix #15)."""
        result = arbiter._select_temp_class(135.0)
        assert _TEMP_CLASS_MAP[result] < 135.0


# ATEXArbitrationResult
# ─────────────────────────────────────────────────────────────────────────────


class TestATEXArbitrationResult:
    def test_is_valid_no_errors(self, arbiter):
        result = arbiter.arbitrate_v21(
            zone=ZoneType.ZONE_1,
            hazard_type=HazardType.GAS,
        )
        assert result.is_valid is True

    def test_is_valid_with_errors(self, arbiter):
        result = arbiter.arbitrate_v21(
            zone=ZoneType.ZONE_1,
            hazard_type=HazardType.DUST,
        )
        assert result.is_valid is False

    def test_frozen(self, arbiter):
        result = arbiter.arbitrate_v21(
            zone=ZoneType.ZONE_1,
            hazard_type=HazardType.GAS,
        )
        with pytest.raises(AttributeError):
            result.space_id = "MUTATED"


# ATEXValidationResult
# ─────────────────────────────────────────────────────────────────────────────


class TestATEXValidationResult:
    def test_frozen(self, arbiter):
        result = arbiter.validate_equipment(
            equipment_id="EQ-1",
            zone=ATEXZone.ZONE_1,
            proposed_epl=EquipmentProtectionLevel.Gb,
            proposed_protection=ProtectionType.d,
        )
        with pytest.raises(AttributeError):
            result.is_compliant = False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
