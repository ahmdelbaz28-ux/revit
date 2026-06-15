"""
tests/test_models_v21.py
=========================
Comprehensive test suite for fireai/core/models_v21.py

SAFETY CRITICAL: V21 Pydantic models enforce fail-fast validation for
hazardous area classification per IEC 60079 / NFPA standards. Invalid
objects CANNOT exist — every validator runs at construction.

Standards tested:
  IEC 60079-0:2017     – Temperature classes (T1-T6 + subdivisions)
  IEC 60079-10-1:2015  – Gas zone classification, purge time, BW LFL
  IEC 60079-14:2013    – Thermal margin, protection modes
  NFPA 497-2021        – Flammable gas/liquid classification
  ATEX 2014/34/EU      – Equipment categories
  FM Global DS 5-48    – Lens fouling, transparency thresholds
"""

from __future__ import annotations

import math

import pytest
from pydantic import ValidationError

from fireai.core.models_v21 import (
    _DEFAULT_MEDIUM_ALPHA,
    _MW_HIGH_THRESHOLD,
    _MW_LOW_THRESHOLD,
    # Constants
    _T_CLASS_MAX,
    MIN_REDUNDANCY_BY_ZONE,
    ATEXEquipmentSpec,
    ElevationTier,
    EnvironmentalContext,
    EPLDust,
    EPLGas,
    EPLMining,
    FlameDetectorSpec,
    FoulingCategory,
    HACResult,
    HazardType,
    Jurisdiction,
    Obstruction,
    PasquillStability,
    RayTracePoint,
    RegionProfile,
    RegSelectorResult,
    RegulatoryFramework,
    SpectralSignature,
    SpectralSignatureRegistry,
    # Pydantic Models
    SubstanceProperties,
    TemperatureClass,
    ThermalMarginRule,
    # Enums
    VentilationLevel,
    VolumetricMedium,
    WavelengthBand,
    ZoneExtent,
    ZoneType,
    _ray_aabb_path_length,
    # Functions
    _select_temp_class,
    _select_temp_class_with_margin,
    beer_lambert_transmittance,
    burgess_wheeler_lfl,
    room_concentration_at_time,
    room_purge_time,
    vapor_density_tier,
    volumetric_path_transmittance,
)

# ═══════════════════════════════════════════════════════════════════════════════
# Enum Tests
# ═══════════════════════════════════════════════════════════════════════════════


class TestEnums:
    """Validate all enum members and values."""

    def test_ventilation_level_members(self):
        assert {v.value for v in VentilationLevel} == {"HIGH", "MEDIUM", "LOW", "POOR"}

    def test_hazard_type_members(self):
        assert {v.value for v in HazardType} == {"GAS", "DUST", "HYBRID", "FIBER"}

    def test_zone_type_members(self):
        expected = {"ZONE_0", "ZONE_1", "ZONE_2", "ZONE_20", "ZONE_21", "ZONE_22", "UNCLASSIFIED"}
        assert {v.value for v in ZoneType} == expected

    def test_epl_gas_hierarchy(self):
        """Fix #14: Ga > Gb > Gc (Ga = highest protection)."""
        assert EPLGas.Ga.value == "Ga"
        assert EPLGas.Gb.value == "Gb"
        assert EPLGas.Gc.value == "Gc"

    def test_epl_dust_hierarchy(self):
        assert EPLDust.Da.value == "Da"
        assert EPLDust.Db.value == "Db"
        assert EPLDust.Dc.value == "Dc"

    def test_epl_mining(self):
        assert EPLMining.Ma.value == "Ma"
        assert EPLMining.Mb.value == "Mb"

    def test_temperature_class_extended(self):
        """V21.2: Extended T-class subdivisions T2A-T2D, T3A-T3C, T4A."""
        expected = {"T1", "T2", "T2A", "T2B", "T2C", "T2D", "T3", "T3A",
                     "T3B", "T3C", "T4", "T4A", "T5", "T6"}
        assert {v.value for v in TemperatureClass} == expected

    def test_t_class_max_values(self):
        """IEC 60079-0:2017 §7.3 Table 3 — key values."""
        assert _T_CLASS_MAX["T1"] == 450.0
        assert _T_CLASS_MAX["T4"] == 135.0
        assert _T_CLASS_MAX["T6"] == 85.0
        assert _T_CLASS_MAX["T2A"] == 280.0
        assert _T_CLASS_MAX["T3B"] == 165.0

    def test_t_class_descending_order(self):
        """T-class max temps must be strictly descending."""
        ordered = ["T1", "T2", "T2A", "T2B", "T2C", "T2D", "T3", "T3A",
                    "T3B", "T3C", "T4", "T4A", "T5", "T6"]
        for i in range(len(ordered) - 1):
            assert _T_CLASS_MAX[ordered[i]] > _T_CLASS_MAX[ordered[i + 1]], (
                f"{ordered[i]} ({_T_CLASS_MAX[ordered[i]]}) should be > "
                f"{ordered[i+1]} ({_T_CLASS_MAX[ordered[i+1]]})"
            )

    def test_wavelength_band_members(self):
        assert {v.value for v in WavelengthBand} == {"UV", "VIS", "IR1", "IR3"}

    def test_regulatory_framework_members(self):
        expected = {"ATEX_EU", "IECEx", "NEC_US", "CEC_CANADA", "EFTA"}
        assert {v.value for v in RegulatoryFramework} == expected

    def test_pasquill_stability_members(self):
        assert {v.value for v in PasquillStability} == {"A", "B", "C", "D", "E", "F"}

    def test_thermal_margin_rule_members(self):
        assert {v.value for v in ThermalMarginRule} == {"STRICT_5PCT", "STANDARD_5PCT", "BASIC"}

    def test_region_profile_members(self):
        expected = {"STANDARD_IEC", "MENA_SUMMER_OUTDOOR", "GULF_HCIS",
                     "EGYPT_CODE", "EUROPE_IEC", "USA_NFPA"}
        assert {v.value for v in RegionProfile} == expected

    def test_jurisdiction_members(self):
        expected = {"GLOBAL_IEC", "SAUDI_HCIS", "EGYPTIAN_FIRE_CODE", "USA_NFPA"}
        assert {v.value for v in Jurisdiction} == expected

    def test_fouling_category_members(self):
        assert {v.value for v in FoulingCategory} == {"CLEAN", "MODERATE", "HEAVY", "SEVERE"}

    def test_elevation_tier_members(self):
        assert {v.value for v in ElevationTier} == {"LOW", "BREATHING_ZONE", "HIGH"}


# ═══════════════════════════════════════════════════════════════════════════════
# SubstanceProperties Tests
# ═══════════════════════════════════════════════════════════════════════════════


class TestSubstanceProperties:
    """SubstanceProperties — IEC 60079-10-1, NFPA 497."""

    def test_valid_gas_substance(self):
        s = SubstanceProperties(name="Methane", hazard_type=HazardType.GAS, lfl_vol_pct=5.0)
        assert s.name == "Methane"
        assert s.hazard_type == HazardType.GAS
        assert s.lfl_vol_pct == 5.0

    def test_valid_dust_substance(self):
        s = SubstanceProperties(name="Grain Dust", hazard_type=HazardType.DUST, mec_g_m3=0.06)
        assert s.mec_g_m3 == 0.06

    def test_hybrid_requires_both_lfl_and_mec(self):
        with pytest.raises(ValidationError, match="HYBRID"):
            SubstanceProperties(name="Hybrid Mix", hazard_type=HazardType.HYBRID, lfl_vol_pct=2.0)

    def test_hybrid_valid_with_both(self):
        s = SubstanceProperties(
            name="Hybrid Mix", hazard_type=HazardType.HYBRID,
            lfl_vol_pct=2.0, mec_g_m3=0.05,
        )
        assert s.hazard_type == HazardType.HYBRID

    def test_gas_requires_lfl(self):
        with pytest.raises(ValidationError, match="GAS hazard requires lfl_vol_pct"):
            SubstanceProperties(name="No-LFL Gas", hazard_type=HazardType.GAS)

    def test_dust_requires_mec(self):
        with pytest.raises(ValidationError, match="DUST hazard requires mec_g_m3"):
            SubstanceProperties(name="No-MEC Dust", hazard_type=HazardType.DUST)

    def test_fiber_requires_flammability(self):
        """Fix #5: FIBER without lfl_vol_pct or mec_g_m3 is rejected."""
        with pytest.raises(ValidationError, match="FIBER"):
            SubstanceProperties(name="Cotton Fiber", hazard_type=HazardType.FIBER)

    def test_fiber_valid_with_lfl(self):
        s = SubstanceProperties(name="Cotton Fiber", hazard_type=HazardType.FIBER, lfl_vol_pct=3.0)
        assert s.lfl_vol_pct == 3.0

    def test_fiber_valid_with_mec(self):
        s = SubstanceProperties(name="Textile Fiber", hazard_type=HazardType.FIBER, mec_g_m3=0.04)
        assert s.mec_g_m3 == 0.04

    def test_flash_point_above_autoignition_rejected(self):
        """NFPA 497 §4.2: flash_point must be < autoignition."""
        with pytest.raises(ValidationError, match="flash_point_c"):
            SubstanceProperties(
                name="Bad", hazard_type=HazardType.GAS, lfl_vol_pct=5.0,
                flash_point_c=500.0, autoignition_c=400.0,
            )

    def test_flash_point_below_autoignition_valid(self):
        s = SubstanceProperties(
            name="Propane", hazard_type=HazardType.GAS, lfl_vol_pct=2.1,
            flash_point_c=-104.0, autoignition_c=450.0,
        )
        assert s.flash_point_c == -104.0

    def test_lfl_gte_ufl_rejected(self):
        with pytest.raises(ValidationError, match="lfl_vol_pct"):
            SubstanceProperties(
                name="Bad", hazard_type=HazardType.GAS,
                lfl_vol_pct=10.0, ufl_vol_pct=5.0,
            )

    def test_lfl_lt_ufl_valid(self):
        s = SubstanceProperties(
            name="Good", hazard_type=HazardType.GAS,
            lfl_vol_pct=2.0, ufl_vol_pct=10.0,
        )
        assert s.lfl_vol_pct < s.ufl_vol_pct

    def test_frozen_model(self):
        s = SubstanceProperties(name="Methane", hazard_type=HazardType.GAS, lfl_vol_pct=5.0)
        with pytest.raises(ValidationError):
            s.name = "Changed"

    def test_strict_mode_rejects_string_as_float(self):
        """Strict mode: string "5.0" should NOT auto-convert to float."""
        with pytest.raises(ValidationError):
            SubstanceProperties(name="Gas", hazard_type=HazardType.GAS, lfl_vol_pct="5.0")

    def test_lfl_zero_rejected(self):
        with pytest.raises(ValidationError):
            SubstanceProperties(name="Gas", hazard_type=HazardType.GAS, lfl_vol_pct=0.0)

    def test_lfl_negative_rejected(self):
        with pytest.raises(ValidationError):
            SubstanceProperties(name="Gas", hazard_type=HazardType.GAS, lfl_vol_pct=-1.0)


# ═══════════════════════════════════════════════════════════════════════════════
# ZoneExtent Tests
# ═══════════════════════════════════════════════════════════════════════════════


class TestZoneExtent:
    def test_valid_indoor(self):
        ze = ZoneExtent(horizontal_m=3.0, vertical_m=3.0, volume_m3=10.0)
        assert ze.is_outdoor is False

    def test_valid_outdoor(self):
        ze = ZoneExtent(horizontal_m=3.0, vertical_m=3.0, volume_m3=100.0, is_outdoor=True)
        assert ze.is_outdoor is True

    def test_negative_horizontal_rejected(self):
        with pytest.raises(ValidationError):
            ZoneExtent(horizontal_m=-1.0, vertical_m=3.0, volume_m3=10.0)

    def test_volume_exceeds_hemisphere(self):
        """IEC 60079-10-1 Annex A: volume > 105% of hemisphere rejected."""
        r = 3.0
        max_vol = (2.0 / 3.0) * math.pi * r ** 3 * 1.05
        with pytest.raises(ValidationError, match="hemisphere"):
            ZoneExtent(horizontal_m=r, vertical_m=r, volume_m3=max_vol + 10.0)

    def test_volume_within_5pct_tolerance(self):
        """5% tolerance for rounding — volume just within tolerance."""
        r = 3.0
        max_vol = (2.0 / 3.0) * math.pi * r ** 3 * 1.04  # 4% over
        ze = ZoneExtent(horizontal_m=r, vertical_m=r, volume_m3=max_vol)
        assert ze.volume_m3 == max_vol

    def test_outdoor_sphere_check(self):
        r = 3.0
        max_vol = (4.0 / 3.0) * math.pi * r ** 3
        ze = ZoneExtent(horizontal_m=r, vertical_m=r, volume_m3=max_vol, is_outdoor=True)
        assert ze.is_outdoor is True


# ═══════════════════════════════════════════════════════════════════════════════
# HACResult Tests
# ═══════════════════════════════════════════════════════════════════════════════


class TestHACResult:
    def _make_extent(self, **kw):
        return ZoneExtent(horizontal_m=3.0, vertical_m=3.0, volume_m3=10.0, **kw)

    def test_non_critical_combination(self):
        hr = HACResult(
            zone=ZoneType.ZONE_2, extent=self._make_extent(),
            ventilation=VentilationLevel.MEDIUM, hazard_type=HazardType.GAS,
        )
        assert hr.critical_flags == []

    def test_zone0_poor_requires_critical_flag(self):
        """Fix #16: Zone 0 + POOR must have critical_flags set."""
        flag = (
            "CRITICAL: Zone 0/20 with POOR ventilation — "
            "most dangerous possible classification. "
            "Mandatory engineering review required. "
            "[IEC 60079-10-1 §6.3]"
        )
        with pytest.raises(ValidationError, match="CRITICAL"):
            HACResult(
                zone=ZoneType.ZONE_0, extent=self._make_extent(),
                ventilation=VentilationLevel.POOR, hazard_type=HazardType.GAS,
            )
        # With flag explicitly set, should pass
        hr = HACResult(
            zone=ZoneType.ZONE_0, extent=self._make_extent(),
            ventilation=VentilationLevel.POOR, hazard_type=HazardType.GAS,
            critical_flags=[flag],
        )
        assert flag in hr.critical_flags

    def test_zone20_poor_requires_critical_flag(self):
        flag = (
            "CRITICAL: Zone 0/20 with POOR ventilation — "
            "most dangerous possible classification. "
            "Mandatory engineering review required. "
            "[IEC 60079-10-1 §6.3]"
        )
        hr = HACResult(
            zone=ZoneType.ZONE_20, extent=self._make_extent(),
            ventilation=VentilationLevel.POOR, hazard_type=HazardType.DUST,
            critical_flags=[flag],
        )
        assert flag in hr.critical_flags


# ═══════════════════════════════════════════════════════════════════════════════
# _select_temp_class Tests
# ═══════════════════════════════════════════════════════════════════════════════


class TestSelectTempClass:
    """Fix #15: T-class max surface temp must be STRICTLY < autoignition."""

    def test_high_autoignition_returns_t1(self):
        assert _select_temp_class(500.0) == TemperatureClass.T1

    def test_autoignition_180_returns_t3b(self):
        """V21.2 Round 4: 180C -> T3B (max 165C), not T4 (max 135C)."""
        result = _select_temp_class(180.0)
        assert result == TemperatureClass.T3B
        assert _T_CLASS_MAX[result.value] < 180.0

    def test_autoignition_90_returns_t6(self):
        assert _select_temp_class(90.0) == TemperatureClass.T6

    def test_autoignition_85_raises(self):
        """85C is T6 max surface — nothing strictly below."""
        with pytest.raises(ValueError, match="No safe temperature class"):
            _select_temp_class(85.0)

    def test_autoignition_50_raises(self):
        with pytest.raises(ValueError):
            _select_temp_class(50.0)

    def test_all_t_classes_strictly_below(self):
        """For each T-class, autoignition at max+1 must select it."""
        for t_class, max_temp in _T_CLASS_MAX.items():
            result = _select_temp_class(max_temp + 0.01)
            assert result == TemperatureClass(t_class)


# ═══════════════════════════════════════════════════════════════════════════════
# _select_temp_class_with_margin Tests
# ═══════════════════════════════════════════════════════════════════════════════


class TestSelectTempClassWithMargin:
    """IEC 60079-14 §5.3 thermal margin."""

    def test_zone0_strict_margin(self):
        """Zone 0: t_safe = autoignition - max(10, 0.05*autoignition)."""
        # autoignition=300: t_safe = 300 - max(10, 15) = 285
        # T2 max=300 > 285 → not safe; T2A max=280 < 285 → safe
        result = _select_temp_class_with_margin(300.0, ZoneType.ZONE_0)
        assert result == TemperatureClass.T2A

    def test_zone1_standard_margin(self):
        # autoignition=300: t_safe = 300 - max(5, 15) = 285
        result = _select_temp_class_with_margin(300.0, ZoneType.ZONE_1)
        assert _T_CLASS_MAX[result.value] <= 285.0

    def test_zone2_basic_margin(self):
        """Zone 2: just strictly below (autoignition - 1)."""
        # autoignition=136: t_safe=135, T4 max=135 ≤ 135 → safe
        result = _select_temp_class_with_margin(136.0, ZoneType.ZONE_2)
        assert _T_CLASS_MAX[result.value] <= 135.0

    def test_zone20_strict_margin(self):
        result = _select_temp_class_with_margin(200.0, ZoneType.ZONE_20)
        # t_safe = 200 - max(10, 10) = 190; T3A(180) < 190
        assert _T_CLASS_MAX[result.value] <= 190.0

    def test_no_safe_class_raises(self):
        with pytest.raises(ValueError, match="No safe temperature class"):
            _select_temp_class_with_margin(86.0, ZoneType.ZONE_0)


# ═══════════════════════════════════════════════════════════════════════════════
# ATEXEquipmentSpec Tests
# ═══════════════════════════════════════════════════════════════════════════════


class TestATEXEquipmentSpec:
    def test_valid_zone0_ga(self):
        spec = ATEXEquipmentSpec(
            zone=ZoneType.ZONE_0, epl_required="Ga", atex_category="1G",
            temp_class=TemperatureClass.T4, protection_modes=["ia"],
        )
        assert spec.epl_required == "Ga"

    def test_ga_sufficient_for_zone1(self):
        """Ga satisfies Gb requirement for Zone 1 (Fix #14)."""
        spec = ATEXEquipmentSpec(
            zone=ZoneType.ZONE_1, epl_required="Ga", atex_category="1G",
            temp_class=TemperatureClass.T4, protection_modes=["ia"],
        )
        assert spec.epl_required == "Ga"

    def test_gc_insufficient_for_zone0(self):
        with pytest.raises(ValidationError, match="INSUFFICIENT"):
            ATEXEquipmentSpec(
                zone=ZoneType.ZONE_0, epl_required="Gc", atex_category="3G",
                temp_class=TemperatureClass.T4, protection_modes=["ic"],
            )

    def test_invalid_atex_category(self):
        with pytest.raises(ValidationError, match="not a valid ATEX"):
            ATEXEquipmentSpec(
                zone=ZoneType.ZONE_1, epl_required="Gb", atex_category="4G",
                temp_class=TemperatureClass.T4, protection_modes=["d"],
            )

    def test_zone0_rejects_flameproof(self):
        """V25 FIX: 'd' (flameproof) is EPL Gb — Zone 1 only."""
        with pytest.raises(ValidationError, match="not permitted"):
            ATEXEquipmentSpec(
                zone=ZoneType.ZONE_0, epl_required="Ga", atex_category="1G",
                temp_class=TemperatureClass.T4, protection_modes=["d"],
            )

    def test_zone1_allows_flameproof(self):
        spec = ATEXEquipmentSpec(
            zone=ZoneType.ZONE_1, epl_required="Gb", atex_category="2G",
            temp_class=TemperatureClass.T4, protection_modes=["d"],
        )
        assert "d" in spec.protection_modes

    def test_zone2_allows_ic(self):
        spec = ATEXEquipmentSpec(
            zone=ZoneType.ZONE_2, epl_required="Gc", atex_category="3G",
            temp_class=TemperatureClass.T4, protection_modes=["ic"],
        )
        assert "ic" in spec.protection_modes

    def test_zone20_rejects_tb(self):
        """Zone 20: 'tb' is EPL Db (Zone 21 only)."""
        with pytest.raises(ValidationError, match="not permitted"):
            ATEXEquipmentSpec(
                zone=ZoneType.ZONE_20, epl_required="Da", atex_category="1D",
                temp_class=TemperatureClass.T4, protection_modes=["tb"],
            )

    def test_zone21_rejects_tc(self):
        """V48 FIX: 'tc' is EPL Dc (Zone 22 only)."""
        with pytest.raises(ValidationError, match="not permitted"):
            ATEXEquipmentSpec(
                zone=ZoneType.ZONE_21, epl_required="Db", atex_category="2D",
                temp_class=TemperatureClass.T4, protection_modes=["tc"],
            )

    def test_zone22_allows_tc(self):
        spec = ATEXEquipmentSpec(
            zone=ZoneType.ZONE_22, epl_required="Dc", atex_category="3D",
            temp_class=TemperatureClass.T4, protection_modes=["tc"],
        )
        assert "tc" in spec.protection_modes

    def test_thermal_margin_violation_zone1(self):
        """V54 FIX: T-class exceeding 95% of autoignition → hac_critical."""
        spec = ATEXEquipmentSpec(
            zone=ZoneType.ZONE_1, epl_required="Gb", atex_category="2G",
            temp_class=TemperatureClass.T3, protection_modes=["d"],
            autoignition_c=200.0,  # 95% = 190; T3 max=200 > 190
        )
        assert len(spec.hac_critical) > 0
        assert "Thermal margin violation" in spec.hac_critical[0]

    def test_thermal_margin_ok_zone1(self):
        spec = ATEXEquipmentSpec(
            zone=ZoneType.ZONE_1, epl_required="Gb", atex_category="2G",
            temp_class=TemperatureClass.T4, protection_modes=["d"],
            autoignition_c=200.0,  # 95% = 190; T4 max=135 < 190
        )
        assert len(spec.hac_critical) == 0

    def test_thermal_margin_violation_zone2_strict_below(self):
        """Zone 2: T-class max must be strictly below autoignition."""
        spec = ATEXEquipmentSpec(
            zone=ZoneType.ZONE_2, epl_required="Gc", atex_category="3G",
            temp_class=TemperatureClass.T4, protection_modes=["ic"],
            autoignition_c=135.0,  # T4 max=135, not strictly below
        )
        assert len(spec.hac_critical) > 0

    def test_da_sufficient_for_zone21(self):
        """Da satisfies Db requirement for Zone 21."""
        spec = ATEXEquipmentSpec(
            zone=ZoneType.ZONE_21, epl_required="Da", atex_category="1D",
            temp_class=TemperatureClass.T4, protection_modes=["tb"],
        )
        assert spec.epl_required == "Da"


# ═══════════════════════════════════════════════════════════════════════════════
# Obstruction Tests
# ═══════════════════════════════════════════════════════════════════════════════


class TestObstruction:
    def test_default_opaque(self):
        o = Obstruction(obstruction_id="wall1", vertices=[[0, 0, 0], [1, 0, 0], [1, 1, 0]])
        for band in WavelengthBand:
            assert o.transmittance_for(band) == 0.0

    def test_glass_partial_transparency(self):
        o = Obstruction(
            obstruction_id="glass1",
            vertices=[[0, 0, 0], [1, 0, 0]],
            spectral_transparency={
                WavelengthBand.UV: 0.0,
                WavelengthBand.VIS: 0.9,
                WavelengthBand.IR1: 0.8,
                WavelengthBand.IR3: 0.8,
            },
        )
        assert o.is_transparent_for(WavelengthBand.IR3) is True
        assert o.is_transparent_for(WavelengthBand.UV) is False

    def test_transparency_above_70_threshold(self):
        """V54 FIX / V66 FIX: >= 0.70 is transparent."""
        o = Obstruction(
            obstruction_id="test1",
            vertices=[[0, 0, 0]],
            spectral_transparency={WavelengthBand.IR3: 0.70},
        )
        assert o.is_transparent_for(WavelengthBand.IR3) is True

    def test_transparency_below_70(self):
        o = Obstruction(
            obstruction_id="test2",
            vertices=[[0, 0, 0]],
            spectral_transparency={WavelengthBand.IR3: 0.69},
        )
        assert o.is_transparent_for(WavelengthBand.IR3) is False

    def test_out_of_range_rejected(self):
        with pytest.raises(ValidationError, match="must be in"):
            Obstruction(
                obstruction_id="bad",
                vertices=[[0, 0, 0]],
                spectral_transparency={WavelengthBand.UV: 1.5},
            )

    def test_negative_transparency_rejected(self):
        with pytest.raises(ValidationError):
            Obstruction(
                obstruction_id="bad2",
                vertices=[[0, 0, 0]],
                spectral_transparency={WavelengthBand.UV: -0.1},
            )


# ═══════════════════════════════════════════════════════════════════════════════
# FlameDetectorSpec Tests
# ═══════════════════════════════════════════════════════════════════════════════


class TestFlameDetectorSpec:
    def test_valid_spec(self):
        fd = FlameDetectorSpec(
            detector_id="FD-1",
            position=[1.0, 2.0, 3.0],
            orientation_vector=[1.0, 0.0, 0.0],
            rated_range_m=30.0,
            aoc_deg=90.0,
            spectral_bands=[WavelengthBand.UV, WavelengthBand.IR3],
        )
        assert fd.detector_id == "FD-1"

    def test_zero_orientation_rejected(self):
        with pytest.raises(ValidationError, match="zero vector"):
            FlameDetectorSpec(
                detector_id="FD-BAD",
                position=[1.0, 2.0, 3.0],
                orientation_vector=[0.0, 0.0, 0.0],
                rated_range_m=30.0,
                aoc_deg=90.0,
                spectral_bands=[WavelengthBand.UV],
            )

    def test_nan_position_rejected(self):
        with pytest.raises(ValidationError, match="non-finite"):
            FlameDetectorSpec(
                detector_id="FD-NAN",
                position=[1.0, float("nan"), 3.0],
                orientation_vector=[1.0, 0.0, 0.0],
                rated_range_m=30.0,
                aoc_deg=90.0,
                spectral_bands=[WavelengthBand.UV],
            )

    def test_inf_position_rejected(self):
        with pytest.raises(ValidationError, match="non-finite"):
            FlameDetectorSpec(
                detector_id="FD-INF",
                position=[1.0, 2.0, float("inf")],
                orientation_vector=[1.0, 0.0, 0.0],
                rated_range_m=30.0,
                aoc_deg=90.0,
                spectral_bands=[WavelengthBand.UV],
            )

    def test_orientation_unit_vector(self):
        fd = FlameDetectorSpec(
            detector_id="FD-U",
            position=[0.0, 0.0, 0.0],
            orientation_vector=[3.0, 4.0, 0.0],
            rated_range_m=30.0,
            aoc_deg=90.0,
            spectral_bands=[WavelengthBand.IR3],
        )
        unit = fd.orientation_unit
        assert unit[0] == pytest.approx(0.6, abs=1e-6)
        assert unit[1] == pytest.approx(0.8, abs=1e-6)

    def test_is_facing_upward(self):
        fd_up = FlameDetectorSpec(
            detector_id="UP",
            position=[0, 0, 5],
            orientation_vector=[0.0, 0.0, 1.0],
            rated_range_m=20.0,
            aoc_deg=90.0,
            spectral_bands=[WavelengthBand.UV],
        )
        assert fd_up.is_facing_upward() is True

    def test_is_not_facing_upward(self):
        fd_horiz = FlameDetectorSpec(
            detector_id="HORIZ",
            position=[0, 0, 5],
            orientation_vector=[1.0, 0.0, 0.0],
            rated_range_m=20.0,
            aoc_deg=90.0,
            spectral_bands=[WavelengthBand.UV],
        )
        assert fd_horiz.is_facing_upward() is False

    def test_range_exceeds_200_rejected(self):
        with pytest.raises(ValidationError):
            FlameDetectorSpec(
                detector_id="FAR",
                position=[0, 0, 0],
                orientation_vector=[1, 0, 0],
                rated_range_m=201.0,
                aoc_deg=90.0,
                spectral_bands=[WavelengthBand.UV],
            )

    def test_aoc_zero_rejected(self):
        with pytest.raises(ValidationError):
            FlameDetectorSpec(
                detector_id="ZERO-AOC",
                position=[0, 0, 0],
                orientation_vector=[1, 0, 0],
                rated_range_m=20.0,
                aoc_deg=0.0,
                spectral_bands=[WavelengthBand.UV],
            )


# ═══════════════════════════════════════════════════════════════════════════════
# RayTracePoint Tests
# ═══════════════════════════════════════════════════════════════════════════════


class TestRayTracePoint:
    def test_create(self):
        p = RayTracePoint(x=1.0, y=2.0, z=3.0)
        assert p.x == 1.0
        assert p.z == 3.0

    def test_default_z(self):
        p = RayTracePoint(x=1.0, y=2.0)
        assert p.z == 0.0

    def test_to_tuple(self):
        p = RayTracePoint(x=1.5, y=2.5, z=3.5)
        assert p.to_tuple() == (1.5, 2.5, 3.5)


# ═══════════════════════════════════════════════════════════════════════════════
# RegSelectorResult Tests
# ═══════════════════════════════════════════════════════════════════════════════


class TestRegSelectorResult:
    def test_valid(self):
        r = RegSelectorResult(
            country_code="US",
            framework=RegulatoryFramework.NEC_US,
            zone_system="DIVISION",
            warnings=[],
        )
        assert r.country_code == "US"

    def test_frozen(self):
        r = RegSelectorResult(
            country_code="US",
            framework=RegulatoryFramework.NEC_US,
            zone_system="ZONE",
            warnings=["test"],
        )
        with pytest.raises(ValidationError):
            r.country_code = "XX"


# ═══════════════════════════════════════════════════════════════════════════════
# EnvironmentalContext Tests
# ═══════════════════════════════════════════════════════════════════════════════


class TestEnvironmentalContext:
    def test_defaults(self):
        """Defaults are worst-case: F stability, 0.5 m/s wind, 40C."""
        ctx = EnvironmentalContext()
        assert ctx.ambient_temp_c == 40.0
        assert ctx.wind_speed_m_s == 0.5
        assert ctx.stability_class == PasquillStability.F
        assert ctx.is_indoor is True
        assert ctx.lens_fouling_factor == 0.85

    def test_unstable_with_low_wind_rejected(self):
        """Pasquill-Gifford: A/B stability needs ≥2 m/s wind."""
        with pytest.raises(ValidationError, match="Physics Violation"):
            EnvironmentalContext(wind_speed_m_s=1.0, stability_class=PasquillStability.A)

    def test_stable_with_low_wind_ok(self):
        ctx = EnvironmentalContext(wind_speed_m_s=0.5, stability_class=PasquillStability.F)
        assert ctx.stability_class == PasquillStability.F

    def test_mena_temp_advisory(self):
        ctx = EnvironmentalContext(
            region=RegionProfile.MENA_SUMMER_OUTDOOR,
            ambient_temp_c=35.0,
            wind_speed_m_s=3.0,
            stability_class=PasquillStability.D,
        )
        advisories = ctx.advisories
        assert any("MENA/GULF" in a and "50-55" in a for a in advisories)

    def test_mena_no_temp_advisory_at_50(self):
        ctx = EnvironmentalContext(
            region=RegionProfile.MENA_SUMMER_OUTDOOR,
            ambient_temp_c=51.0,
            wind_speed_m_s=3.0,
            stability_class=PasquillStability.D,
        )
        temp_ads = [a for a in ctx.advisories if "ambient temperature" in a]
        assert len(temp_ads) == 0

    def test_mena_fouling_clean_advisory(self):
        ctx = EnvironmentalContext(
            region=RegionProfile.GULF_HCIS,
            ambient_temp_c=55.0,
            wind_speed_m_s=3.0,
            stability_class=PasquillStability.D,
            fouling_category=FoulingCategory.CLEAN,
        )
        advisories = ctx.advisories
        assert any("CLEAN" in a for a in advisories)

    def test_egypt_temp_advisory(self):
        ctx = EnvironmentalContext(
            region=RegionProfile.EGYPT_CODE,
            ambient_temp_c=35.0,
            wind_speed_m_s=3.0,
            stability_class=PasquillStability.D,
        )
        advisories = ctx.advisories
        assert any("EGYPT" in a and "45.0C" in a for a in advisories)

    def test_standard_iec_no_advisories(self):
        ctx = EnvironmentalContext()
        assert ctx.advisories == []

    def test_wind_speed_zero_rejected(self):
        with pytest.raises(ValidationError):
            EnvironmentalContext(wind_speed_m_s=0.0)

    def test_fouling_factor_zero_rejected(self):
        with pytest.raises(ValidationError):
            EnvironmentalContext(lens_fouling_factor=0.0)


# ═══════════════════════════════════════════════════════════════════════════════
# MIN_REDUNDANCY_BY_ZONE Tests
# ═══════════════════════════════════════════════════════════════════════════════


class TestMinRedundancy:
    def test_zone0_requires_3(self):
        """2oo3 voting — continuous presence."""
        assert MIN_REDUNDANCY_BY_ZONE[ZoneType.ZONE_0] == 3

    def test_zone1_requires_2(self):
        """1oo2 minimum — NFPA 72 §17.8.3.4."""
        assert MIN_REDUNDANCY_BY_ZONE[ZoneType.ZONE_1] == 2

    def test_zone2_requires_1(self):
        assert MIN_REDUNDANCY_BY_ZONE[ZoneType.ZONE_2] == 1

    def test_unclassified_requires_0(self):
        assert MIN_REDUNDANCY_BY_ZONE[ZoneType.UNCLASSIFIED] == 0

    def test_all_zones_present(self):
        assert len(MIN_REDUNDANCY_BY_ZONE) == len(ZoneType)


# ═══════════════════════════════════════════════════════════════════════════════
# vapor_density_tier Tests
# ═══════════════════════════════════════════════════════════════════════════════


class TestVaporDensityTier:
    def test_hydrogen_is_light(self):
        """H2 MW=2 → rises to ceiling."""
        assert vapor_density_tier(2.0) == ElevationTier.HIGH

    def test_methane_is_light(self):
        """CH4 MW=16 → lighter than air."""
        assert vapor_density_tier(16.0) == ElevationTier.HIGH

    def test_air_is_breathing_zone(self):
        """Air MW=28.96 → breathing zone."""
        assert vapor_density_tier(28.96) == ElevationTier.BREATHING_ZONE

    def test_propane_is_heavy(self):
        """C3H8 MW=44 → pools at floor."""
        assert vapor_density_tier(44.0) == ElevationTier.LOW

    def test_boundary_high(self):
        """MW just below HIGH threshold."""
        assert vapor_density_tier(_MW_HIGH_THRESHOLD - 0.01) == ElevationTier.HIGH

    def test_boundary_low(self):
        """MW just above LOW threshold."""
        assert vapor_density_tier(_MW_LOW_THRESHOLD + 0.01) == ElevationTier.LOW

    def test_nan_rejected(self):
        """V57 FIX: NaN molecular_weight must raise ValueError."""
        with pytest.raises(ValueError, match="finite"):
            vapor_density_tier(float("nan"))

    def test_inf_rejected(self):
        with pytest.raises(ValueError, match="finite"):
            vapor_density_tier(float("inf"))

    def test_negative_mw_rejected(self):
        with pytest.raises(ValueError, match="greater than 0"):
            vapor_density_tier(-1.0)

    def test_zero_mw_rejected(self):
        with pytest.raises(ValueError, match="greater than 0"):
            vapor_density_tier(0.0)


# ═══════════════════════════════════════════════════════════════════════════════
# room_purge_time Tests
# ═══════════════════════════════════════════════════════════════════════════════


class TestRoomPurgeTime:
    def test_basic_calculation(self):
        """t = -3600/ACH * ln(target_fraction)."""
        t = room_purge_time(room_volume_m3=100.0, ach=6.0, target_fraction=0.01)
        expected = -3600.0 / 6.0 * math.log(0.01)
        assert t == pytest.approx(expected, rel=1e-6)

    def test_zero_ach_returns_inf(self):
        assert room_purge_time(100.0, ach=0.0) == float("inf")

    def test_negative_ach_returns_inf(self):
        assert room_purge_time(100.0, ach=-1.0) == float("inf")

    def test_target_fraction_zero_returns_inf(self):
        assert room_purge_time(100.0, ach=6.0, target_fraction=0.0) == float("inf")

    def test_target_fraction_one_returns_inf(self):
        assert room_purge_time(100.0, ach=6.0, target_fraction=1.0) == float("inf")

    def test_result_non_negative(self):
        t = room_purge_time(100.0, ach=6.0, target_fraction=0.5)
        assert t >= 0.0


# ═══════════════════════════════════════════════════════════════════════════════
# room_concentration_at_time Tests
# ═══════════════════════════════════════════════════════════════════════════════


class TestRoomConcentrationAtTime:
    def test_initial_concentration(self):
        c = room_concentration_at_time(5.0, ach=6.0, time_seconds=0.0)
        assert c == pytest.approx(5.0)

    def test_decay_over_time(self):
        c = room_concentration_at_time(5.0, ach=6.0, time_seconds=3600.0)
        # After 1 hour at 6 ACH: C = 5 * exp(-6) ≈ 0.0124
        expected = 5.0 * math.exp(-6.0)
        assert c == pytest.approx(expected, rel=1e-6)

    def test_zero_ach_no_decay(self):
        c = room_concentration_at_time(5.0, ach=0.0, time_seconds=3600.0)
        assert c == 5.0

    def test_negative_ach_no_decay(self):
        c = room_concentration_at_time(5.0, ach=-1.0, time_seconds=3600.0)
        assert c == 5.0


# ═══════════════════════════════════════════════════════════════════════════════
# burgess_wheeler_lfl Tests
# ═══════════════════════════════════════════════════════════════════════════════


class TestBurgessWheelerLFL:
    def test_no_correction_at_25c(self):
        lfl = burgess_wheeler_lfl(5.0, 25.0)
        assert lfl == 5.0

    def test_no_correction_below_25c(self):
        lfl = burgess_wheeler_lfl(5.0, 20.0)
        assert lfl == 5.0

    def test_correction_at_100c(self):
        """LFL_100 = 5.0 * (1 - 0.001824 * 75) ≈ 5.0 * 0.8632 = 4.316."""
        lfl = burgess_wheeler_lfl(5.0, 100.0)
        expected = 5.0 * (1.0 - 0.001824 * 75.0)
        assert lfl == pytest.approx(expected, rel=1e-6)

    def test_floor_50_pct(self):
        """Default 50% floor prevents extreme correction."""
        # Extreme: 5.0 at 1000C → correction = 1-0.001824*975 → negative
        # Floor = 5.0 * 0.5 = 2.5
        lfl = burgess_wheeler_lfl(5.0, 1000.0)
        assert lfl >= 2.5

    def test_no_floor_when_none(self):
        """lfl_floor_ratio=None: no floor — conservative for zone extent."""
        lfl = burgess_wheeler_lfl(5.0, 500.0, lfl_floor_ratio=None)
        # Very high T should reduce LFL significantly
        assert lfl < 5.0

    def test_zero_lfl_rejected(self):
        with pytest.raises(ValueError, match="must be > 0"):
            burgess_wheeler_lfl(0.0, 40.0)

    def test_negative_lfl_rejected(self):
        with pytest.raises(ValueError, match="must be > 0"):
            burgess_wheeler_lfl(-1.0, 40.0)

    def test_lfl_decreases_with_temperature(self):
        lfl_low = burgess_wheeler_lfl(5.0, 50.0)
        lfl_high = burgess_wheeler_lfl(5.0, 200.0)
        assert lfl_high < lfl_low


# ═══════════════════════════════════════════════════════════════════════════════
# SpectralSignature & Registry Tests
# ═══════════════════════════════════════════════════════════════════════════════


class TestSpectralSignature:
    def test_create(self):
        sig = SpectralSignature(
            cas_number="74-82-8",
            substance_name="Methane",
            alpha_uv=0.1,
            alpha_vis=0.0,
            alpha_ir1=0.05,
            alpha_ir3=0.4,
        )
        assert sig.cas_number == "74-82-8"

    def test_alpha_for(self):
        sig = SpectralSignature(
            cas_number="TEST",
            substance_name="Test",
            alpha_uv=1.0,
            alpha_vis=2.0,
            alpha_ir1=3.0,
            alpha_ir3=4.0,
        )
        assert sig.alpha_for(WavelengthBand.UV) == 1.0
        assert sig.alpha_for(WavelengthBand.IR3) == 4.0

    def test_negative_alpha_rejected(self):
        with pytest.raises(ValidationError):
            SpectralSignature(
                cas_number="BAD",
                substance_name="Bad",
                alpha_uv=-1.0,
            )


class TestSpectralSignatureRegistry:
    def test_lazy_load(self):
        reg = SpectralSignatureRegistry()
        assert reg._loaded is False
        reg.get("74-82-8")
        assert reg._loaded is True

    def test_methane_lookup(self):
        reg = SpectralSignatureRegistry()
        sig = reg.get("74-82-8")
        assert sig is not None
        assert sig.substance_name == "Methane"

    def test_unknown_cas_returns_none(self):
        reg = SpectralSignatureRegistry()
        assert reg.get("00-00-0") is None

    def test_register_custom(self):
        reg = SpectralSignatureRegistry()
        custom = SpectralSignature(
            cas_number="CUSTOM-1",
            substance_name="Custom",
            alpha_uv=0.5,
        )
        reg.register(custom)
        assert reg.get("CUSTOM-1") is not None
        assert reg.get("CUSTOM-1").substance_name == "Custom"

    def test_list_available(self):
        reg = SpectralSignatureRegistry()
        cas_list = reg.list_available()
        assert "74-82-8" in cas_list
        assert len(cas_list) > 5

    def test_count(self):
        reg = SpectralSignatureRegistry()
        n = reg.count()
        assert n >= 20  # Many built-in signatures


# ═══════════════════════════════════════════════════════════════════════════════
# VolumetricMedium Tests
# ═══════════════════════════════════════════════════════════════════════════════


class TestVolumetricMedium:
    def test_valid_smoke(self):
        vm = VolumetricMedium(
            medium_id="smoke1",
            medium_type="SMOKE",
            bbox_min=[0.0, 0.0, 0.0],
            bbox_max=[10.0, 10.0, 3.0],
        )
        assert vm.medium_type == "SMOKE"

    def test_inverted_bbox_rejected(self):
        with pytest.raises(ValidationError, match="bbox_min"):
            VolumetricMedium(
                medium_id="bad",
                medium_type="SMOKE",
                bbox_min=[10.0, 0.0, 0.0],
                bbox_max=[0.0, 10.0, 3.0],
            )

    def test_zero_volume_rejected(self):
        """GAP-07: Zero volume has no physical meaning."""
        with pytest.raises(ValidationError, match="zero or near-zero"):
            VolumetricMedium(
                medium_id="flat",
                medium_type="SMOKE",
                bbox_min=[0.0, 0.0, 0.0],
                bbox_max=[0.0, 10.0, 3.0],  # dx=0
            )

    def test_get_alpha_with_defaults(self):
        vm = VolumetricMedium(
            medium_id="smoke1",
            medium_type="SMOKE",
            bbox_min=[0, 0, 0],
            bbox_max=[10, 10, 3],
        )
        alpha = vm.get_alpha(WavelengthBand.VIS)
        # SMOKE default VIS = 3.0
        assert alpha == pytest.approx(3.0)

    def test_get_alpha_with_override(self):
        vm = VolumetricMedium(
            medium_id="custom",
            medium_type="SMOKE",
            bbox_min=[0, 0, 0],
            bbox_max=[10, 10, 3],
            alpha_override={WavelengthBand.UV: 5.0},
        )
        alpha = vm.get_alpha(WavelengthBand.UV)
        assert alpha == pytest.approx(5.0)

    def test_concentration_factor(self):
        vm = VolumetricMedium(
            medium_id="dense",
            medium_type="SMOKE",
            bbox_min=[0, 0, 0],
            bbox_max=[10, 10, 3],
            concentration_factor=2.0,
        )
        alpha = vm.get_alpha(WavelengthBand.VIS)
        assert alpha == pytest.approx(6.0)  # 3.0 * 2.0

    def test_get_alpha_with_registry(self):
        vm = VolumetricMedium(
            medium_id="ch4",
            medium_type="GAS_CLOUD",
            bbox_min=[0, 0, 0],
            bbox_max=[10, 10, 3],
            cas_number="74-82-8",
        )
        reg = SpectralSignatureRegistry()
        alpha = vm.get_alpha_with_registry(WavelengthBand.IR3, reg)
        # Methane IR3 = 0.4
        assert alpha == pytest.approx(0.4)

    def test_unknown_medium_type(self):
        vm = VolumetricMedium(
            medium_id="unknown",
            medium_type="UNKNOWN_TYPE",
            bbox_min=[0, 0, 0],
            bbox_max=[10, 10, 3],
        )
        alpha = vm.get_alpha(WavelengthBand.UV)
        assert alpha == 0.0  # Fallback


# ═══════════════════════════════════════════════════════════════════════════════
# beer_lambert_transmittance Tests
# ═══════════════════════════════════════════════════════════════════════════════


class TestBeerLambertTransmittance:
    def test_clear_path(self):
        """alpha=0 → T=1.0 (no absorption)."""
        assert beer_lambert_transmittance(0.0, 10.0) == 1.0

    def test_zero_length(self):
        assert beer_lambert_transmittance(1.0, 0.0) == 1.0

    def test_negative_alpha(self):
        assert beer_lambert_transmittance(-1.0, 10.0) == 1.0

    def test_known_absorption(self):
        """T = exp(-0.5 * 2) = exp(-1) ≈ 0.368."""
        t = beer_lambert_transmittance(0.5, 2.0)
        assert t == pytest.approx(math.exp(-1.0), rel=1e-6)

    def test_result_bounded(self):
        t = beer_lambert_transmittance(100.0, 100.0)
        assert 0.0 <= t <= 1.0

    def test_high_absorption_near_zero(self):
        t = beer_lambert_transmittance(10.0, 10.0)
        assert t < 0.001


# ═══════════════════════════════════════════════════════════════════════════════
# volumetric_path_transmittance Tests
# ═══════════════════════════════════════════════════════════════════════════════


class TestVolumetricPathTransmittance:
    def test_no_media_returns_1(self):
        t = volumetric_path_transmittance((0, 0, 0), (10, 0, 0), [], WavelengthBand.IR3)
        assert t == 1.0

    def test_media_not_in_path(self):
        vm = VolumetricMedium(
            medium_id="far",
            medium_type="SMOKE",
            bbox_min=[50, 50, 0],
            bbox_max=[60, 60, 3],
        )
        t = volumetric_path_transmittance((0, 0, 0), (10, 0, 0), [vm], WavelengthBand.IR3)
        assert t == 1.0  # Ray doesn't intersect

    def test_media_in_path_reduces_transmittance(self):
        vm = VolumetricMedium(
            medium_id="smoke1",
            medium_type="SMOKE",
            bbox_min=[0, 0, 0],
            bbox_max=[10, 10, 3],
            alpha_override={WavelengthBand.IR3: 2.0},
        )
        t = volumetric_path_transmittance((0, 0, 1.5), (10, 0, 1.5), [vm], WavelengthBand.IR3)
        assert t < 1.0


# ═══════════════════════════════════════════════════════════════════════════════
# _ray_aabb_path_length Tests
# ═══════════════════════════════════════════════════════════════════════════════


class TestRayAABBPathLength:
    def test_ray_through_box(self):
        """Ray from (0,5,1.5) to (20,5,1.5) through box [2,8]x[0,10]x[0,3]."""
        path = _ray_aabb_path_length(
            (0, 5, 1.5), (20, 5, 1.5),
            [2.0, 0.0, 0.0], [8.0, 10.0, 3.0],
        )
        assert path == pytest.approx(6.0, abs=0.1)  # 8-2=6 along X

    def test_ray_misses_box(self):
        path = _ray_aabb_path_length(
            (0, 20, 5), (10, 20, 5),
            [2.0, 0.0, 0.0], [8.0, 10.0, 3.0],
        )
        assert path == 0.0

    def test_ray_parallel_to_face(self):
        path = _ray_aabb_path_length(
            (0, 5, 5), (10, 5, 5),  # z=5, above box
            [2.0, 0.0, 0.0], [8.0, 10.0, 3.0],
        )
        assert path == 0.0


# ═══════════════════════════════════════════════════════════════════════════════
# _DEFAULT_MEDIUM_ALPHA Tests
# ═══════════════════════════════════════════════════════════════════════════════


class TestDefaultMediumAlpha:
    def test_smoke_has_all_bands(self):
        assert "SMOKE" in _DEFAULT_MEDIUM_ALPHA
        smoke = _DEFAULT_MEDIUM_ALPHA["SMOKE"]
        for band in ("UV", "VIS", "IR1", "IR3"):
            assert band in smoke

    def test_clear_is_zero(self):
        clear = _DEFAULT_MEDIUM_ALPHA["CLEAR"]
        assert all(v == 0.0 for v in clear.values())

    def test_all_types_present(self):
        expected = {"SMOKE", "STEAM", "DUST_SUSPENSION", "GAS_CLOUD", "MIST", "CLEAR"}
        assert set(_DEFAULT_MEDIUM_ALPHA.keys()) == expected


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
