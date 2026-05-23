"""
hac_classification_engine.py – Hazardous Area Classification Engine
=====================================================================
Classifies hazardous areas from physical parameters (physics-first,
no manual human input for zone assignment).

V21 Migration:
  - Uses Pydantic SubstanceProperties, HACResult, ZoneExtent from models_v21
  - Fast-Fail on invalid input — no dict/tuple passes through
  - critical_flags enforced by Pydantic model (Zone 0 + POOR must acknowledge)
  - _select_temp_class from models_v21 (Fix #15: strictly below autoignition)

Standards:
  IEC 60079-10-1:2015  – Explosive gas atmospheres (Zone 0/1/2)
  IEC 60079-10-2:2015  – Explosive dust atmospheres (Zone 20/21/22)
  NFPA 497-2021        – Classification of flammable liquids/gases (NEC)
  NFPA 499-2021        – Classification of combustible dusts (NEC)

Fix #6 (CRITICAL):  Ventilation affects dust zones (was silently ignored)
Fix #7 (CRITICAL):  No arbitrary x10 multiplier, hemisphere for indoor
Fix #8 (CRITICAL):  Hybrid = classify separately, take most severe
Fix #9 (HIGH):      Flash point check against ambient temp
Fix #10 (HIGH):     MIE < 3mJ = electrostatic ignition risk
Fix #11 (HIGH):     POOR + Zone 0/20 = critical flag (not silent)
Fix #12 (MEDIUM):   Temperature class vs autoignition
Fix #13 (MEDIUM):   Indoor = hemisphere (2/3*pi*r^3), not full sphere
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Tuple

from fireai.core.models_v21 import (
    SubstanceProperties, HACResult, ZoneExtent, ZoneType,
    VentilationLevel, HazardType, _select_temp_class, TemperatureClass,
    EnvironmentalContext, burgess_wheeler_lfl,
)
from fireai.core.international_reg_selector import (
    ATEXZone, HazardClass, HazardSystem, NECDivision,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Legacy Enums (preserved for backward compatibility)
# ---------------------------------------------------------------------------

class ReleaseGrade(str, Enum):
    CONTINUOUS  = "CONTINUOUS"
    PRIMARY     = "PRIMARY"
    SECONDARY   = "SECONDARY"


class VentilationDegree(str, Enum):
    HIGH    = "HIGH"
    MEDIUM  = "MEDIUM"
    LOW     = "LOW"


class VentilationAvailability(str, Enum):
    GOOD    = "GOOD"
    FAIR    = "FAIR"
    POOR    = "POOR"


class HazardousMaterial(str, Enum):
    GAS         = "GAS"
    VAPOR       = "VAPOR"
    DUST_COMB   = "DUST_COMB"
    DUST_HYBRID = "DUST_HYBRID"
    MIST        = "MIST"


class SoRGeometry(str, Enum):
    POINT    = "POINT"
    LINE     = "LINE"
    AREA     = "AREA"
    VOLUME   = "VOLUME"


# ---------------------------------------------------------------------------
# V21 mapping helpers
# ---------------------------------------------------------------------------

# Convert V21 VentilationLevel to legacy VentilationDegree
_V21_TO_LEGACY_DEGREE = {
    VentilationLevel.HIGH:   VentilationDegree.HIGH,
    VentilationLevel.MEDIUM: VentilationDegree.MEDIUM,
    VentilationLevel.LOW:    VentilationDegree.LOW,
    VentilationLevel.POOR:   VentilationDegree.LOW,  # POOR maps to LOW in legacy
}

# Convert V21 ZoneType to legacy ATEXZone
_V21_TO_ATEX_ZONE = {
    ZoneType.ZONE_0:       ATEXZone.ZONE_0,
    ZoneType.ZONE_1:       ATEXZone.ZONE_1,
    ZoneType.ZONE_2:       ATEXZone.ZONE_2,
    ZoneType.ZONE_20:      ATEXZone.ZONE_20,
    ZoneType.ZONE_21:      ATEXZone.ZONE_21,
    ZoneType.ZONE_22:      ATEXZone.ZONE_22,
    ZoneType.UNCLASSIFIED: ATEXZone.SAFE,
}

# Convert V21 HazardType to legacy HazardousMaterial
_V21_TO_HAZMAT = {
    HazardType.GAS:    HazardousMaterial.GAS,
    HazardType.DUST:   HazardousMaterial.DUST_COMB,
    HazardType.HYBRID: HazardousMaterial.DUST_HYBRID,
    HazardType.FIBER:  HazardousMaterial.DUST_COMB,
}

# Temperature class limits (legacy, used by _check_temperature_class)
T_CLASS_MAX_TEMP: Dict[str, float] = {
    "T1": 450.0, "T2": 300.0, "T2A": 280.0, "T2B": 260.0,
    "T2C": 230.0, "T2D": 215.0, "T3": 200.0, "T3A": 180.0,
    "T3B": 165.0, "T3C": 160.0, "T4": 135.0, "T4A": 120.0,
    "T5": 100.0, "T6": 85.0,
}

# Zone hazard ordering (legacy)
_ZONE_HAZARD_ORDER: Dict[ATEXZone, int] = {
    ATEXZone.ZONE_0:  0,
    ATEXZone.ZONE_20: 1,
    ATEXZone.ZONE_1:  2,
    ATEXZone.ZONE_21: 3,
    ATEXZone.ZONE_2:  4,
    ATEXZone.ZONE_22: 5,
    ATEXZone.SAFE:    99,
}

# Base radii per IEC 60079-10-1 Annex A (legacy)
_BASE_RADII_M: Dict[ATEXZone, float] = {
    ATEXZone.ZONE_0:  3.0,
    ATEXZone.ZONE_1:  6.0,
    ATEXZone.ZONE_2:  10.0,
    ATEXZone.ZONE_20: 1.5,
    ATEXZone.ZONE_21: 3.0,
    ATEXZone.ZONE_22: 6.0,
    ATEXZone.SAFE:    0.0,
}


# ---------------------------------------------------------------------------
# Legacy dataclasses (preserved for backward compatibility)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class SubstancePropertiesLegacy:
    """Legacy substance properties dataclass."""
    substance_name:   str
    cas_number:       str = ""
    lfl_vol_pct:      float = 0.0
    ufl_vol_pct:      float = 100.0
    flash_point_c:    Optional[float] = None
    autoignition_c:   Optional[float] = None
    vapor_density:    float = 1.0
    mec_g_m3:         Optional[float] = None
    mie_mj:           Optional[float] = None
    kst_bar_m_s:      Optional[float] = None
    pmax_bar:         Optional[float] = None
    dust_group:       str = ""
    nec_group:        str = ""
    temperature_class: str = "T3"
    material_type:    HazardousMaterial = HazardousMaterial.GAS


@dataclass(frozen=True)
class ReleaseSource:
    """Source of hazardous material release."""
    source_id:    str
    grade:        ReleaseGrade
    geometry:     SoRGeometry
    release_rate_kg_s: float = 0.0
    diameter_m:   float = 0.0
    length_m:     float = 0.0
    area_m2:      float = 0.0


@dataclass(frozen=True)
class ZoneExtentLegacy:
    """Legacy zone extent dataclass."""
    zone:          ATEXZone
    radius_m:      float
    area_m2:       float
    volume_m3:     float
    is_negligible: bool


@dataclass(frozen=True)
class HACResultLegacy:
    """Legacy HAC result dataclass."""
    space_id:          str
    substance:         SubstancePropertiesLegacy
    release_sources:   Tuple[ReleaseSource, ...]
    ventilation_degree: VentilationDegree
    ventilation_avail:  VentilationAvailability
    classified_zone:   ATEXZone
    zone_extent:       ZoneExtentLegacy
    hazard_class:      HazardClass
    nec_division:      Optional[str]    = None
    temperature_class: str              = "T3"
    confidence_pct:    float            = 100.0
    assumptions:       Tuple[str, ...]  = ()
    warnings:          Tuple[str, ...]  = ()
    nfpa_reference:    str              = ""
    iec_reference:     str              = ""


# ---------------------------------------------------------------------------
# V21 Classification Engine
# ---------------------------------------------------------------------------

class HACClassificationEngine:
    """
    Classifies hazardous areas from physical parameters.

    V21 API:  classify_v21() uses Pydantic models (strict, fail-fast)
    Legacy:   classify() still available for backward compatibility

    Physics-first: zone is derived from substance properties,
    release grade, and ventilation — not from user opinion.

    IEC 60079-10-1:2015 (Gas) / IEC 60079-10-2:2015 (Dust)
    """

    # ── V21 API ────────────────────────────────────────────────────────────

    def classify_v21(
        self,
        substance:   SubstanceProperties,
        ventilation: VentilationLevel,
        is_indoor:   bool,
        source_height_m: float = 0.0,
        ambient_temp_c:  float = 20.0,
        env_context:     Optional[EnvironmentalContext] = None,
    ) -> HACResult:
        """
        V21.2 classify using Pydantic models — fail-fast on invalid input.
        SubstanceProperties is validated at construction — no dict/tuple passes.

        V21.2 adds EnvironmentalContext for Burgess-Wheeler LFL correction.
        If env_context is provided, uses its ambient_temp for LFL correction.
        Otherwise, uses ambient_temp_c parameter for backward compatibility.
        """
        warnings: List[str] = []
        critical_flags: List[str] = []

        # V21.2: Apply Burgess-Wheeler LFL correction if env_context provided
        lfl_corrected = None
        if env_context is not None and substance.lfl_vol_pct is not None:
            lfl_corrected = burgess_wheeler_lfl(
                substance.lfl_vol_pct, env_context.ambient_temp_c
            )
            if lfl_corrected < substance.lfl_vol_pct:
                pct_reduction = (1.0 - lfl_corrected / substance.lfl_vol_pct) * 100.0
                warnings.append(
                    f"LFL thermal correction applied: "
                    f"{substance.lfl_vol_pct:.2f}% -> {lfl_corrected:.2f}% "
                    f"({pct_reduction:.1f}% reduction at "
                    f"{env_context.ambient_temp_c}C). "
                    f"[Burgess-Wheeler / IEC 60079-10-1 Annex B]"
                )

        if substance.hazard_type == HazardType.GAS:
            return self._classify_gas_v21(
                substance, ventilation, is_indoor,
                source_height_m, ambient_temp_c,
                warnings, critical_flags, lfl_corrected,
            )
        elif substance.hazard_type == HazardType.DUST:
            return self._classify_dust_v21(
                substance, ventilation, is_indoor,
                source_height_m, warnings, critical_flags,
            )
        elif substance.hazard_type == HazardType.HYBRID:
            return self._classify_hybrid_v21(
                substance, ventilation, is_indoor,
                source_height_m, ambient_temp_c,
                warnings, critical_flags, lfl_corrected,
            )
        else:
            raise ValueError(f"Unsupported hazard_type: {substance.hazard_type}")

    def _classify_gas_v21(
        self, sub, vent, indoor, src_h, ambient, warnings, critical_flags,
        lfl_corrected=None,
    ) -> HACResult:
        """IEC 60079-10-1 gas zone classification (V21.2 with LFL correction)."""

        # Fix #9: Flash point check (NFPA 497 §4.2)
        if sub.flash_point_c is not None:
            if sub.flash_point_c > ambient + 20.0:
                warnings.append(
                    f"Flash point ({sub.flash_point_c}C) > ambient+20C "
                    f"({ambient+20:.0f}C). Liquid may not produce flammable "
                    f"atmosphere unless heated. [NFPA 497 §4.2]"
                )

        # Fix #12: Temperature class vs autoignition check
        if sub.autoignition_c is not None:
            t_class = _select_temp_class(sub.autoignition_c)
            warnings.append(
                f"Max temperature class for autoignition "
                f"{sub.autoignition_c}C -> {t_class.value} "
                f"[IEC 60079-0 §7.3]"
            )

        # Zone determination from ventilation
        zone = self._gas_zone_from_ventilation_v21(vent)
        # Fix #6: Ventilation DOES affect gas zones
        zone = self._apply_ventilation_gas_v21(zone, vent)

        # Fix #11: POOR + Zone 0 -> critical flag
        # CRITICAL: Flag string must EXACTLY match HACResult.check_critical_combination validator
        if vent == VentilationLevel.POOR and zone == ZoneType.ZONE_0:
            flag = (
                "CRITICAL: Zone 0/20 with POOR ventilation — "
                "most dangerous possible classification. "
                "Mandatory engineering review required. "
                "[IEC 60079-10-1 §6.3]"
            )
            critical_flags.append(flag)

        # V21.2: Use corrected LFL if available (wider zone)
        effective_lfl = lfl_corrected if lfl_corrected is not None else (sub.lfl_vol_pct or 1.0)
        extent = self._compute_extent_v21(
            effective_lfl, vent, indoor, src_h)

        return HACResult(
            zone=zone,
            extent=extent,
            ventilation=vent,
            hazard_type=sub.hazard_type,
            warnings=warnings,
            critical_flags=critical_flags,
        )

    def _classify_dust_v21(
        self, sub, vent, indoor, src_h, warnings, critical_flags,
    ) -> HACResult:
        """IEC 60079-10-2 dust zone classification (V21)."""

        # Fix #10: MIE check
        if sub.mie_mj is not None and sub.mie_mj < 3.0:
            warnings.append(
                f"MIE={sub.mie_mj} mJ < 3 mJ — dust ignitable by "
                f"electrostatic discharge. Additional bonding/grounding required. "
                f"[IEC 60079-10-2 §5.2]"
            )

        # Kst classification
        if sub.kst_bar_m_s is not None and sub.kst_bar_m_s > 300:
            warnings.append(
                f"Kst={sub.kst_bar_m_s} bar*m/s — St3 class dust, "
                f"extremely explosive. [IEC 60079-10-2 §5.2]"
            )

        # Fix #6: Ventilation determines dust zone
        zone = self._dust_zone_from_ventilation_v21(vent)

        # Fix #11: POOR + Zone 20 -> critical flag
        # Uses same flag string as HACResult validator for consistency
        if vent == VentilationLevel.POOR and zone == ZoneType.ZONE_20:
            flag = (
                "CRITICAL: Zone 0/20 with POOR ventilation — "
                "most dangerous possible classification. "
                "Mandatory engineering review required. "
                "[IEC 60079-10-1 §6.3]"
            )
            critical_flags.append(flag)

        extent = self._compute_extent_dust_v21(
            sub.mec_g_m3 or 30.0, vent, indoor, src_h)

        return HACResult(
            zone=zone,
            extent=extent,
            ventilation=vent,
            hazard_type=sub.hazard_type,
            warnings=warnings,
            critical_flags=critical_flags,
        )

    def _classify_hybrid_v21(
        self, sub, vent, indoor, src_h, ambient, warnings, critical_flags,
        lfl_corrected=None,
    ) -> HACResult:
        """Fix #8: Hybrid = classify separately, take most severe (V21.2)."""
        warnings.append(
            "HYBRID mixture: classified independently for gas and dust. "
            "Most severe zone applies. [IEC 60079-10-1 §5.7]"
        )

        gas_result = self._classify_gas_v21(
            sub, vent, indoor, src_h, ambient,
            warnings=[], critical_flags=[], lfl_corrected=lfl_corrected,
        )
        dust_result = self._classify_dust_v21(
            sub, vent, indoor, src_h,
            warnings=[], critical_flags=[],
        )

        warnings.extend(gas_result.warnings)
        warnings.extend(dust_result.warnings)
        critical_flags.extend(gas_result.critical_flags)
        critical_flags.extend(dust_result.critical_flags)

        # Severity order (most severe first)
        severity = [
            ZoneType.ZONE_0, ZoneType.ZONE_20,
            ZoneType.ZONE_1, ZoneType.ZONE_21,
            ZoneType.ZONE_2, ZoneType.ZONE_22,
            ZoneType.UNCLASSIFIED,
        ]
        gas_sev  = severity.index(gas_result.zone)
        dust_sev = severity.index(dust_result.zone)
        final_zone = gas_result.zone if gas_sev <= dust_sev else dust_result.zone

        g_ext = gas_result.extent
        d_ext = dust_result.extent
        extent = ZoneExtent(
            horizontal_m=max(g_ext.horizontal_m, d_ext.horizontal_m),
            vertical_m  =max(g_ext.vertical_m,   d_ext.vertical_m),
            volume_m3   =max(g_ext.volume_m3,     d_ext.volume_m3),
        )

        return HACResult(
            zone=final_zone,
            extent=extent,
            ventilation=vent,
            hazard_type=HazardType.HYBRID,
            warnings=warnings,
            critical_flags=critical_flags,
        )

    # ── V21 Zone determination helpers ──────────────────────────────────────

    @staticmethod
    def _gas_zone_from_ventilation_v21(vent: VentilationLevel) -> ZoneType:
        return {
            VentilationLevel.HIGH:   ZoneType.ZONE_2,
            VentilationLevel.MEDIUM: ZoneType.ZONE_1,
            VentilationLevel.LOW:    ZoneType.ZONE_1,
            VentilationLevel.POOR:   ZoneType.ZONE_0,
        }[vent]

    @staticmethod
    def _apply_ventilation_gas_v21(zone: ZoneType, vent: VentilationLevel) -> ZoneType:
        """Fix #6: Ventilation modifiers for GAS zones."""
        upgrades = {
            (ZoneType.ZONE_1, VentilationLevel.HIGH):   ZoneType.ZONE_2,
            (ZoneType.ZONE_1, VentilationLevel.MEDIUM): ZoneType.ZONE_1,
            (ZoneType.ZONE_1, VentilationLevel.LOW):    ZoneType.ZONE_0,
            (ZoneType.ZONE_2, VentilationLevel.MEDIUM): ZoneType.ZONE_2,
            (ZoneType.ZONE_2, VentilationLevel.HIGH):   ZoneType.UNCLASSIFIED,
        }
        return upgrades.get((zone, vent), zone)

    @staticmethod
    def _dust_zone_from_ventilation_v21(vent: VentilationLevel) -> ZoneType:
        """Fix #6: Ventilation determines dust zone."""
        return {
            VentilationLevel.HIGH:   ZoneType.ZONE_22,
            VentilationLevel.MEDIUM: ZoneType.ZONE_21,
            VentilationLevel.LOW:    ZoneType.ZONE_21,
            VentilationLevel.POOR:   ZoneType.ZONE_20,
        }[vent]

    # ── V21 Extent calculations ─────────────────────────────────────────────

    @staticmethod
    def _compute_extent_v21(
        lfl: float, vent: VentilationLevel, indoor: bool, src_h: float,
    ) -> ZoneExtent:
        """Fix #7 + Fix #13: No x10, hemisphere for indoor, IEC Annex A."""
        k = {
            VentilationLevel.HIGH:   2.0,
            VentilationLevel.MEDIUM: 5.0,
            VentilationLevel.LOW:    8.0,
            VentilationLevel.POOR:   15.0,
        }[vent]

        r_h = k / lfl
        r_v = r_h * 0.5

        if indoor:
            vol = (2.0 / 3.0) * math.pi * r_h ** 3   # Fix #13
        else:
            vol = (4.0 / 3.0) * math.pi * r_h ** 3

        return ZoneExtent(
            horizontal_m=round(r_h, 2),
            vertical_m  =round(r_v, 2),
            volume_m3   =round(vol, 2),
            is_outdoor  =not indoor,
        )

    @staticmethod
    def _compute_extent_dust_v21(
        mec: float, vent: VentilationLevel, indoor: bool, src_h: float,
    ) -> ZoneExtent:
        """Dust extent per IEC 60079-10-2 Annex A."""
        k = {
            VentilationLevel.HIGH:   3.0,
            VentilationLevel.MEDIUM: 6.0,
            VentilationLevel.LOW:    10.0,
            VentilationLevel.POOR:   20.0,
        }[vent]

        r_h = k / (mec / 30.0)
        r_h = min(r_h, 50.0)
        r_v = r_h * 0.4

        if indoor:
            vol = (2.0 / 3.0) * math.pi * r_h ** 3
        else:
            vol = (4.0 / 3.0) * math.pi * r_h ** 3

        return ZoneExtent(
            horizontal_m=round(r_h, 2),
            vertical_m  =round(r_v, 2),
            volume_m3   =round(vol, 2),
            is_outdoor  =not indoor,
        )

    # ── Legacy API ──────────────────────────────────────────────────────────

    def classify(
        self,
        space_id:            str,
        substance:           SubstancePropertiesLegacy,
        release_sources:     List[ReleaseSource],
        ventilation_degree:  VentilationDegree,
        ventilation_avail:   VentilationAvailability,
        room_volume_m3:      float = 100.0,
        is_indoor:           bool = True,
        ambient_temp_c:      float = 25.0,
    ) -> HACResultLegacy:
        """
        Legacy classify — backward compatible with dataclass inputs.
        Prefer classify_v21() for new code.
        """
        if not release_sources:
            return self._safe_result(space_id, substance)

        warnings: List[str] = []
        assumptions: List[str] = []

        worst_grade = self._worst_grade(release_sources)
        base_zone = self._grade_to_base_zone(worst_grade, substance)

        if substance.material_type == HazardousMaterial.DUST_HYBRID:
            base_zone = self._classify_hybrid(
                worst_grade, ventilation_degree, ventilation_avail)
            warnings.append(
                "Hybrid mixture (gas + dust): classified for both gas and "
                "dust, using more stringent result per IEC 60079-10-1 §5.7."
            )
        else:
            base_zone, zone_note = self._apply_ventilation_degree(
                base_zone, ventilation_degree, substance)
            if zone_note:
                assumptions.append(zone_note)
            base_zone = self._apply_ventilation_availability(
                base_zone, ventilation_avail, warnings)

        zone = base_zone
        extent = self._compute_extent(
            zone, release_sources, ventilation_degree,
            room_volume_m3, is_indoor, substance)

        if self._can_be_negligible(zone, ventilation_degree, ventilation_avail):
            extent = ZoneExtentLegacy(
                zone=zone, radius_m=0.0, area_m2=0.0,
                volume_m3=0.0, is_negligible=True,
            )
            assumptions.append(
                "Zone reduced to negligible extent due to HIGH ventilation "
                "with GOOD availability. IEC 60079-10-1 §6.4.2."
            )

        self._check_flash_point(substance, worst_grade, ambient_temp_c, warnings)
        self._check_dust_properties(substance, warnings)
        self._check_temperature_class(substance, warnings)

        if substance.lfl_vol_pct <= 0 and substance.material_type in (
            HazardousMaterial.GAS, HazardousMaterial.VAPOR
        ):
            warnings.append(
                f"Substance {substance.substance_name!r} has LFL <= 0%. "
                "Verify substance data before using classification result."
            )

        hazard_class = self._substance_to_hazard_class(substance)
        nec_div = self._zone_to_nec_division(zone)
        nfpa_ref = (
            "NFPA 497-2021" if substance.material_type not in (
                HazardousMaterial.DUST_COMB, HazardousMaterial.DUST_HYBRID)
            else "NFPA 499-2021"
        )
        iec_ref = (
            "IEC 60079-10-1:2015"
            if substance.material_type not in (
                HazardousMaterial.DUST_COMB, HazardousMaterial.DUST_HYBRID)
            else "IEC 60079-10-2:2015"
        )

        return HACResultLegacy(
            space_id=space_id,
            substance=substance,
            release_sources=tuple(release_sources),
            ventilation_degree=ventilation_degree,
            ventilation_avail=ventilation_avail,
            classified_zone=zone,
            zone_extent=extent,
            hazard_class=hazard_class,
            nec_division=nec_div,
            temperature_class=substance.temperature_class,
            confidence_pct=self._confidence(warnings, assumptions),
            assumptions=tuple(assumptions),
            warnings=tuple(warnings),
            nfpa_reference=nfpa_ref,
            iec_reference=iec_ref,
        )

    # ── Legacy private helpers ──────────────────────────────────────────────

    @staticmethod
    def _worst_grade(sources: List[ReleaseSource]) -> ReleaseGrade:
        order = {ReleaseGrade.CONTINUOUS: 0, ReleaseGrade.PRIMARY: 1, ReleaseGrade.SECONDARY: 2}
        return min(sources, key=lambda s: order[s.grade]).grade

    @staticmethod
    def _grade_to_base_zone(grade, substance):
        is_dust = substance.material_type in (
            HazardousMaterial.DUST_COMB, HazardousMaterial.DUST_HYBRID)
        if is_dust:
            mapping = {
                ReleaseGrade.CONTINUOUS: ATEXZone.ZONE_20,
                ReleaseGrade.PRIMARY:    ATEXZone.ZONE_21,
                ReleaseGrade.SECONDARY:  ATEXZone.ZONE_22,
            }
        else:
            mapping = {
                ReleaseGrade.CONTINUOUS: ATEXZone.ZONE_0,
                ReleaseGrade.PRIMARY:    ATEXZone.ZONE_1,
                ReleaseGrade.SECONDARY:  ATEXZone.ZONE_2,
            }
        return mapping[grade]

    @staticmethod
    def _apply_ventilation_degree(base_zone, degree, substance):
        note = ""
        gas_upgrade = {
            ATEXZone.ZONE_0: ATEXZone.ZONE_1,
            ATEXZone.ZONE_1: ATEXZone.ZONE_2,
            ATEXZone.ZONE_2: ATEXZone.ZONE_2,
        }
        dust_upgrade = {
            ATEXZone.ZONE_20: ATEXZone.ZONE_21,
            ATEXZone.ZONE_21: ATEXZone.ZONE_22,
            ATEXZone.ZONE_22: ATEXZone.ZONE_22,
        }
        gas_downgrade = {
            ATEXZone.ZONE_2: ATEXZone.ZONE_1,
            ATEXZone.ZONE_1: ATEXZone.ZONE_0,
            ATEXZone.ZONE_0: ATEXZone.ZONE_0,
        }
        dust_downgrade = {
            ATEXZone.ZONE_22: ATEXZone.ZONE_21,
            ATEXZone.ZONE_21: ATEXZone.ZONE_20,
            ATEXZone.ZONE_20: ATEXZone.ZONE_20,
        }
        is_dust = base_zone in (ATEXZone.ZONE_20, ATEXZone.ZONE_21, ATEXZone.ZONE_22)

        if degree == VentilationDegree.HIGH:
            lookup = dust_upgrade if is_dust else gas_upgrade
            new_zone = lookup.get(base_zone, base_zone)
            if new_zone != base_zone:
                std = 'IEC 60079-10-2' if is_dust else 'IEC 60079-10-1'
                note = f"Zone upgraded {base_zone.value}->{new_zone.value} due to HIGH ventilation. {std} §6.2."
            return new_zone, note
        elif degree == VentilationDegree.LOW:
            lookup = dust_downgrade if is_dust else gas_downgrade
            new_zone = lookup.get(base_zone, base_zone)
            if new_zone != base_zone:
                std = 'IEC 60079-10-2' if is_dust else 'IEC 60079-10-1'
                note = f"Zone downgraded {base_zone.value}->{new_zone.value} due to LOW ventilation. {std} §6.2."
            return new_zone, note
        return base_zone, note

    @staticmethod
    def _apply_ventilation_availability(zone, avail, warnings):
        if avail == VentilationAvailability.POOR:
            downgrade = {
                ATEXZone.ZONE_2:  ATEXZone.ZONE_1,
                ATEXZone.ZONE_1:  ATEXZone.ZONE_0,
                ATEXZone.ZONE_22: ATEXZone.ZONE_21,
                ATEXZone.ZONE_21: ATEXZone.ZONE_20,
            }
            new_zone = downgrade.get(zone, zone)
            if zone in (ATEXZone.ZONE_0, ATEXZone.ZONE_20):
                warnings.append(
                    f"SAFETY: Zone {zone.value} with POOR ventilation "
                    "availability — most hazardous combination. "
                    "IEC 60079-10-1 §6.3."
                )
            return new_zone
        return zone

    @staticmethod
    def _compute_extent(zone, sources, ventilation, room_volume_m3, is_indoor=True, substance=None):
        base_r = _BASE_RADII_M.get(zone, 3.0)
        max_rate = max((s.release_rate_kg_s for s in sources), default=0.0)
        rate_factor = 1.0 + math.log1p(max_rate)
        kst_factor = 1.0
        if substance is not None and substance.kst_bar_m_s is not None:
            if substance.kst_bar_m_s > 200:
                kst_factor = 1.0 + (substance.kst_bar_m_s - 200) / 400.0
                kst_factor = min(kst_factor, 2.0)
        vent_factor = {
            VentilationDegree.HIGH: 0.5, VentilationDegree.MEDIUM: 1.0,
            VentilationDegree.LOW:  1.5,
        }.get(ventilation, 1.0)
        location_factor = 1.0 if is_indoor else 1.5
        radius = base_r * rate_factor * vent_factor * location_factor * kst_factor
        area = math.pi * radius ** 2
        if is_indoor:
            volume = (2.0 / 3.0) * math.pi * radius ** 3
        else:
            volume = (4.0 / 3.0) * math.pi * radius ** 3
        volume = min(volume, room_volume_m3)
        return ZoneExtentLegacy(
            zone=zone, radius_m=round(radius, 2),
            area_m2=round(area, 2), volume_m3=round(volume, 2),
            is_negligible=False,
        )

    @staticmethod
    def _can_be_negligible(zone, degree, avail):
        return (
            degree == VentilationDegree.HIGH
            and avail == VentilationAvailability.GOOD
            and zone in (ATEXZone.ZONE_2, ATEXZone.ZONE_22)
        )

    @staticmethod
    def _substance_to_hazard_class(sub):
        if sub.material_type in (HazardousMaterial.DUST_COMB, HazardousMaterial.DUST_HYBRID):
            return HazardClass.DUST
        return HazardClass.GAS_VAPOR

    @staticmethod
    def _zone_to_nec_division(zone):
        mapping = {
            ATEXZone.ZONE_0: "DIVISION_1", ATEXZone.ZONE_1: "DIVISION_1",
            ATEXZone.ZONE_2: "DIVISION_2", ATEXZone.ZONE_20: "DIVISION_1",
            ATEXZone.ZONE_21: "DIVISION_1", ATEXZone.ZONE_22: "DIVISION_2",
            ATEXZone.SAFE: None,
        }
        return mapping.get(zone)

    @staticmethod
    def _confidence(warnings, assumptions):
        base = 100.0
        base -= len(warnings) * 10.0
        base -= len(assumptions) * 5.0
        return max(50.0, base)

    def _safe_result(self, space_id, substance):
        return HACResultLegacy(
            space_id=space_id, substance=substance,
            release_sources=(),
            ventilation_degree=VentilationDegree.HIGH,
            ventilation_avail=VentilationAvailability.GOOD,
            classified_zone=ATEXZone.SAFE,
            zone_extent=ZoneExtentLegacy(
                zone=ATEXZone.SAFE, radius_m=0.0, area_m2=0.0,
                volume_m3=0.0, is_negligible=True,
            ),
            hazard_class=HazardClass.GAS_VAPOR,
            nec_division=None, confidence_pct=100.0,
            assumptions=("No release sources defined — space classified SAFE.",),
            warnings=(),
            nfpa_reference="NFPA 497-2021",
            iec_reference="IEC 60079-10-1:2015",
        )

    def _classify_hybrid(self, grade, ventilation_degree, ventilation_avail):
        gas_zone = self._grade_to_base_zone(
            grade, SubstancePropertiesLegacy(
                substance_name="_hybrid_gas", material_type=HazardousMaterial.GAS))
        gas_zone, _ = self._apply_ventilation_degree(
            gas_zone, ventilation_degree,
            SubstancePropertiesLegacy(
                substance_name="_hybrid_gas", material_type=HazardousMaterial.GAS))
        dust_zone = self._grade_to_base_zone(
            grade, SubstancePropertiesLegacy(
                substance_name="_hybrid_dust", material_type=HazardousMaterial.DUST_COMB))
        dust_zone, _ = self._apply_ventilation_degree(
            dust_zone, ventilation_degree,
            SubstancePropertiesLegacy(
                substance_name="_hybrid_dust", material_type=HazardousMaterial.DUST_COMB))
        dummy_warnings = []
        gas_zone = self._apply_ventilation_availability(gas_zone, ventilation_avail, dummy_warnings)
        dust_zone = self._apply_ventilation_availability(dust_zone, ventilation_avail, dummy_warnings)
        if _ZONE_HAZARD_ORDER.get(gas_zone, 99) <= _ZONE_HAZARD_ORDER.get(dust_zone, 99):
            return gas_zone
        return dust_zone

    @staticmethod
    def _check_flash_point(substance, worst_grade, ambient_temp_c, warnings):
        if (substance.flash_point_c is not None
                and substance.material_type in (HazardousMaterial.VAPOR, HazardousMaterial.GAS)):
            margin = substance.flash_point_c - ambient_temp_c
            if margin > 20 and worst_grade != ReleaseGrade.CONTINUOUS:
                warnings.append(
                    f"Flash point ({substance.flash_point_c:.0f}C) exceeds "
                    f"ambient ({ambient_temp_c:.0f}C) by {margin:.0f}C. "
                    "NFPA 497 §4.2."
                )

    @staticmethod
    def _check_dust_properties(substance, warnings):
        if substance.material_type not in (HazardousMaterial.DUST_COMB, HazardousMaterial.DUST_HYBRID):
            return
        if substance.mie_mj is not None and substance.mie_mj < 3.0:
            warnings.append(
                f"MIE = {substance.mie_mj:.1f} mJ < 3 mJ. Static ignition risk. "
                "IEC 60079-10-2 §5.2."
            )
        if substance.kst_bar_m_s is not None and substance.kst_bar_m_s > 200:
            st_class = "St-2" if substance.kst_bar_m_s <= 300 else "St-3"
            warnings.append(
                f"Kst = {substance.kst_bar_m_s:.0f} bar*m/s ({st_class}). "
                "Enhanced protection required. NFPA 654."
            )

    @staticmethod
    def _check_temperature_class(substance, warnings):
        if substance.autoignition_c is None:
            return
        max_surface_temp = T_CLASS_MAX_TEMP.get(substance.temperature_class)
        if max_surface_temp is None:
            warnings.append(
                f"Unknown temperature class {substance.temperature_class!r}. "
                "Cannot validate against autoignition."
            )
            return
        if max_surface_temp >= substance.autoignition_c:
            safe_classes = [
                tc for tc, temp in sorted(T_CLASS_MAX_TEMP.items(), key=lambda x: x[1])
                if temp < substance.autoignition_c
            ]
            recommended = safe_classes[-1] if safe_classes else "T6 or lower"
            warnings.append(
                f"SAFETY: Equipment T-class {substance.temperature_class} "
                f"(max surface {max_surface_temp:.0f}C) >= autoignition "
                f"({substance.autoignition_c:.0f}C). Must use T-class {recommended}. "
                "IEC 60079-0 §7.3."
            )
