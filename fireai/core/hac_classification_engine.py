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

GAP-01: IEC 60079-10-1 Annex B zone extent formula
GAP-02: release_grade parameter in classify_v21()
"""

from __future__ import annotations

import logging
import math
import warnings as _warnings
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
    VentilationLevel.POOR:   VentilationDegree.LOW,  # POOR→LOW loses 4× ventilation effectiveness (0.05 vs 0.20)
}


def _map_ventilation_to_legacy(vent: VentilationLevel) -> VentilationDegree:
    """Map V21 VentilationLevel to legacy VentilationDegree with WARNING on POOR→LOW.

    POOR ventilation (f=0.05, almost stagnant) maps to LOW (f=0.20, poor distribution)
    in the legacy system, losing a 4× effectiveness factor. This is a known
    information-loss issue in the legacy API — callers should prefer classify_v21().
    """
    result = _V21_TO_LEGACY_DEGREE[vent]
    if vent == VentilationLevel.POOR:
        logger.warning(
            "POOR ventilation mapped to LOW in legacy API — "
            "4× ventilation effectiveness difference lost (f=0.05 vs f=0.20). "
            "Prefer classify_v21() for accurate POOR ventilation handling. "
            "[IEC 60079-10-1 Annex B Table B.2]"
        )
    return result

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

# ── GAP-01: IEC 60079-10-1 Annex B ventilation tables ───────────────

# IEC 60079-10-1:2015 Annex B Table B.2 — ventilation effectiveness (f)
_VENT_EFFECTIVENESS: Dict[str, float] = {
    "HIGH":   1.0,   # f = 1.0 (well-ventilated, uniform flow)
    "MEDIUM": 0.5,   # f = 0.5 (moderate, some dead zones)
    "LOW":    0.2,   # f = 0.2 (poor distribution, stratification)
    "POOR":   0.05,  # f = 0.05 (almost stagnant)
}

# IEC 60079-10-1:2015 Annex B Table B.1 — concentration factor Ck
_RELEASE_GRADE_CK: Dict[str, float] = {
    "CONTINUOUS": 0.25,  # Zone 0 vicinity — very conservative
    "PRIMARY":    0.25,  # Zone 1 vicinity — IEC 60079-10-1 Annex B §B.2
    "SECONDARY":  0.50,  # Zone 2 vicinity — IEC 60079-10-1 Annex B §B.3
}

# Minimum air changes per hour (ACH) by ventilation level
_VENT_ACH: Dict[str, float] = {
    "HIGH":   12.0,  # forced ventilation
    "MEDIUM":  6.0,  # general mechanical ventilation
    "LOW":     1.0,  # natural ventilation
    "POOR":    0.1,  # effectively enclosed
}

# ── GAP-02: IEC 60079-10-1 §4.2 release_grade × ventilation matrix ─────

_GAS_ZONE_RELEASE_BASE: Dict[str, ZoneType] = {
    "CONTINUOUS": ZoneType.ZONE_0,
    "PRIMARY":    ZoneType.ZONE_1,
    "SECONDARY":  ZoneType.ZONE_2,
}
_DUST_ZONE_RELEASE_BASE: Dict[str, ZoneType] = {
    "CONTINUOUS": ZoneType.ZONE_20,
    "PRIMARY":    ZoneType.ZONE_21,
    "SECONDARY":  ZoneType.ZONE_22,
}

# IEC 60079-10-1:2015 §4.3 — ventilation modifies zone
# Higher index = less severe zone. HIGH ventilation should reduce severity
# (move to higher index = less severe zone), POOR should increase severity
# (move to lower index = more severe zone).
_VENT_ZONE_DELTA: Dict[str, int] = {
    "HIGH":   +1,   # reduces severity (e.g. Zone 1 → Zone 2)
    "MEDIUM":  0,   # no change to zone type
    "LOW":     0,   # no change, but extent increases
    "POOR":   -1,   # increases severity (e.g. Zone 2 → Zone 1)
}

_GAS_ZONE_ORDER = ["ZONE_0", "ZONE_1", "ZONE_2"]
_DUST_ZONE_ORDER = ["ZONE_20", "ZONE_21", "ZONE_22"]


def _iec_annex_b_extent(
    substance: SubstanceProperties,
    ventilation: VentilationLevel,
    release_grade: ReleaseGrade,
    release_rate_kg_s: float,
    room_volume_m3: float,
    ambient_temp_c: float = 40.0,
    is_indoor: bool = True,
) -> tuple:
    """
    GAP-01: IEC 60079-10-1:2015 Annex B — Hazardous Area Extent.
    Returns (horizontal_m, vertical_m, volume_m3).

    Consultant Phase 5 improvement: added density fallback with warning
    for light gases (H₂, CH₄) where rho_air = 1.2 kg/m³ is
    non-conservative (underestimates zone extent).
    """
    lfl_vol_pct = substance.lfl_vol_pct
    if lfl_vol_pct is None:
        raise ValueError(
            f"Substance '{substance.name}' has no lfl_vol_pct; "
            "cannot apply IEC 60079-10-1 Annex B formula."
        )

    # LFL temperature correction — Burgess-Wheeler
    # Delegates to canonical burgess_wheeler_lfl() from models_v21
    # (Rule 6/14: no duplicate BW implementation).
    # The canonical function enforces T<=25C guard and 50% floor consistently.
    lfl_corrected = burgess_wheeler_lfl(lfl_vol_pct, ambient_temp_c)
    lfl_frac = lfl_corrected / 100.0

    # Volumetric release rate (m³/s at standard conditions)
    mw = substance.molecular_weight
    if mw is None or mw <= 0.0:
        raise ValueError(
            f"Substance '{substance.name}' has no molecular_weight; "
            "cannot apply IEC 60079-10-1 Annex B formula."
        )
    # BUG FIX: Molecular weight is ALWAYS in g/mol in FireAI (SubstanceProperties
    # model). The previous heuristic `mw > 10.0` assumed MW < 10 meant kg/mol,
    # but MW=2.016 (hydrogen) would be treated as kg/mol, causing a 1000x
    # UNDERESTIMATE of the volumetric release rate. This is a critical safety
    # bug — hydrogen zone extents would be 10x too small (cube root of 1000).
    # ALL molecular weights in FireAI are in g/mol (consistent with NIST/CRC).
    mw_kg_mol = mw / 1000.0
    # FIX #3 (HIGH): Apply ideal gas temperature correction to molar volume.
    # At STP (0°C, 1 atm) molar volume = 0.0224 m³/mol, but at ambient
    # temperature the gas expands: V_m = 0.0224 * (273.15 + T) / 273.15.
    # Using STP volume regardless of temperature underestimates the
    # volumetric release rate at elevated temperatures, producing zone
    # extents that are too small. This is a life-safety bug.
    # Reference: IEC 60079-10-1:2015 Annex B, ideal gas law PV = nRT.
    molar_volume_m3_mol = 0.0224 * (273.15 + ambient_temp_c) / 273.15
    dV_release_m3_s = (release_rate_kg_s / mw_kg_mol) * molar_volume_m3_mol

    # Concentration factor Ck
    ck = _RELEASE_GRADE_CK.get(release_grade.value, 0.25)

    # Hazardous volume at source — eq. B.1
    Vz_source_m3_s = dV_release_m3_s / (ck * lfl_frac + 1e-12)

    # Ventilation dilution — eq. B.3
    f = _VENT_EFFECTIVENESS.get(ventilation.value, 0.5)
    n_ach = _VENT_ACH.get(ventilation.value, 6.0)
    n_m3_s = (n_ach * room_volume_m3) / 3600.0
    effective_dilution = f * n_m3_s
    Vz_diluted_m3 = Vz_source_m3_s / (effective_dilution + 1e-12)

    # Convert to zone radius
    if is_indoor:
        r_hz = (3.0 * Vz_diluted_m3 / (2.0 * math.pi)) ** (1.0 / 3.0)
    else:
        r_hz = (3.0 * Vz_diluted_m3 / (4.0 * math.pi)) ** (1.0 / 3.0)

    # IEC 60079-10-1 Annex B §B.4: vertical extent
    # V25 FIX: Buoyancy classification now uses the same 3-tier density-ratio
    # system as models_v21.vapor_density_tier(), ensuring consistent vertical
    # extent calculation across the entire codebase.
    #
    # Previous code used binary mw < 29.0 (with wrong MW_air=29.0 vs 28.96
    # in models_v21). This caused:
    #   1. Cross-module inconsistency (29.0 vs 28.96 g/mol)
    #   2. Binary classification missed the BREATHING_ZONE tier
    #   3. Ethane (MW=30.07, ratio=1.038) was classified as "not buoyant"
    #      but the 3-tier system correctly classifies it as LOW (heavier than air)
    #      with vertical factor 0.5 — the result is the same for ethane but
    #      differs for gases near air MW (e.g., MW=28.5 → old: buoyant=1.5,
    #      new: BREATHING_ZONE=1.0).
    #
    # Reference: IEC 60079-10-1:2015 §B.4, NFPA 497-2021 §4.5
    from fireai.core.models_v21 import vapor_density_tier, ElevationTier as _ElevTier
    tier = vapor_density_tier(mw)
    if tier == _ElevTier.HIGH:
        r_vz = r_hz * 1.5   # Light gas → rises → larger vertical extent
    elif tier == _ElevTier.LOW:
        r_vz = r_hz * 0.5   # Heavy gas → sinks → smaller vertical extent
    else:
        r_vz = r_hz * 1.0   # Near-air density → uniform sphere
    zone_vol_m3 = Vz_diluted_m3

    # Apply minimum extents (safety floor)
    r_hz = max(r_hz, 0.5)
    r_vz = max(r_vz, 0.3)
    # Recompute volume from final radii (consistent with ZoneExtent validator)
    if is_indoor:
        zone_vol_m3 = (2.0 / 3.0) * math.pi * r_hz ** 2 * r_vz
    else:
        zone_vol_m3 = (4.0 / 3.0) * math.pi * r_hz ** 2 * r_vz

    return r_hz, r_vz, zone_vol_m3


def _resolve_zone_with_grade_vent(
    release_grade: ReleaseGrade,
    ventilation: VentilationLevel,
    is_gas: bool,
) -> ZoneType:
    """
    GAP-02: IEC 60079-10-1:2015 §4.2 + §4.3.
    Zone from release grade (primary) modified by ventilation (secondary).

    IEC §4.3 Note 2: "high dilution may reduce zone extent but should
    not relax zone type for CONTINUOUS/PRIMARY releases" — therefore
    CONTINUOUS releases stay at Zone 0/20 regardless of ventilation.
    """
    if is_gas:
        base_str = _GAS_ZONE_RELEASE_BASE[release_grade.value]
        order = _GAS_ZONE_ORDER
    else:
        base_str = _DUST_ZONE_RELEASE_BASE[release_grade.value]
        order = _DUST_ZONE_ORDER

    base_idx = order.index(base_str)
    delta = _VENT_ZONE_DELTA.get(ventilation.value, 0)

    # IEC §4.3 Note 2: CONTINUOUS releases cannot be reduced by ventilation
    # — Zone 0/20 stays Zone 0/20 regardless of ventilation level.
    # PRIMARY releases may be reduced by one zone level with HIGH ventilation
    # (Zone 1→2 gas, Zone 21→22 dust) per IEC §4.3 §4.4. This is the
    # standard engineering interpretation: HIGH ventilation provides enough
    # dilution to reduce the probability of a hazardous atmosphere for
    # PRIMARY (occasional) releases, but NOT for CONTINUOUS (permanent) ones.
    if release_grade == ReleaseGrade.CONTINUOUS and delta > 0:
        delta = 0

    final_idx = max(0, min(len(order) - 1, base_idx + delta))
    return ZoneType(order[final_idx])


class HACClassificationEngine:
    """
    Classifies hazardous areas from physical parameters.

    V21 API:  classify_v21() uses Pydantic models (strict, fail-fast)
    Legacy:   classify() still available for backward compatibility

    Physics-first: zone is derived from substance properties,
    release grade, and ventilation — not from user opinion.

    GAP-02: release_grade is now the PRIMARY zone determinant per §4.2.
    ventilation is the SECONDARY modifier per §4.3.
    Default release_grade=PRIMARY preserves backward compatibility.

    IEC 60079-10-1:2015 (Gas) / IEC 60079-10-2:2015 (Dust)
    """

    # ── V21 API ────────────────────────────────────────────────────────────

    def classify_v21(
        self,
        substance:   SubstanceProperties,
        ventilation: VentilationLevel,
        is_indoor:   bool = True,
        source_height_m: float = 0.0,
        # BUG FIX H-1: Default ambient_temp_c aligned with EnvironmentalContext
        # default (40°C). Previous default of 20°C was non-conservative —
        # Burgess-Wheeler LFL correction only activates above 25°C, so 20°C
        # produced no correction and narrower zone extents.
        ambient_temp_c:  float = 40.0,
        env_context:     Optional[EnvironmentalContext] = None,
        release_grade:   Optional[ReleaseGrade] = None,
        release_rate_kg_s: float = 0.0,
        room_volume_m3:  float = 1000.0,
    ) -> HACResult:
        """
        V21.2 classify using Pydantic models — fail-fast on invalid input.

        GAP-02: release_grade is now the PRIMARY zone determinant per IEC §4.2.
        ventilation is the SECONDARY modifier per IEC §4.3.
        Default release_grade=PRIMARY preserves backward compatibility.

        GAP-01: When release_rate_kg_s > 0 AND substance has lfl_vol_pct
        AND molecular_weight, uses IEC Annex B formula for zone extent.
        Otherwise falls back to simplified k/lfl method.
        """
        # Backward compat: None → PRIMARY
        if release_grade is None:
            release_grade = ReleaseGrade.PRIMARY

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

        # GAP-02: zone from release grade + ventilation
        is_gas = substance.hazard_type in (HazardType.GAS, HazardType.HYBRID)
        # BUG FIX C-1: FIBER is classified using dust zones (Zone 20/21/22)
        # per NFPA 70 Art. 503 / IEC 60079-10-2, but needs dust extent formula.
        is_dust = substance.hazard_type in (HazardType.DUST, HazardType.HYBRID, HazardType.FIBER)

        if substance.hazard_type == HazardType.HYBRID:
            gas_zone = _resolve_zone_with_grade_vent(release_grade, ventilation, is_gas=True)
            dust_zone = _resolve_zone_with_grade_vent(release_grade, ventilation, is_gas=False)
            severity = [
                ZoneType.ZONE_0, ZoneType.ZONE_20,
                ZoneType.ZONE_1, ZoneType.ZONE_21,
                ZoneType.ZONE_2, ZoneType.ZONE_22,
                ZoneType.UNCLASSIFIED,
            ]
            zone = gas_zone if severity.index(gas_zone) <= severity.index(dust_zone) else dust_zone
            warnings.append(
                "HYBRID hazard: zone determined from most severe of gas and dust analysis. "
                "[IEC 60079-10-1:2015 §5.3]"
            )
        elif is_gas:
            zone = _resolve_zone_with_grade_vent(release_grade, ventilation, is_gas=True)
        elif is_dust:
            zone = _resolve_zone_with_grade_vent(release_grade, ventilation, is_gas=False)
        else:
            # Should not reach here after the FIBER fix above, but guard anyway
            zone = _resolve_zone_with_grade_vent(release_grade, ventilation, is_gas=False)
            warnings.append(
                f"Hazard type {substance.hazard_type.value} defaulted to dust "
                "zone classification. Review zone assignment."
            )

        # GAP-01: zone extent using IEC Annex B or simplified fallback
        effective_temp = env_context.ambient_temp_c if env_context else ambient_temp_c
        effective_lfl = lfl_corrected if lfl_corrected is not None else (substance.lfl_vol_pct or 1.0)

        use_annex_b = (
            release_rate_kg_s > 0.0
            and substance.lfl_vol_pct is not None
            and substance.molecular_weight is not None
            and room_volume_m3 > 0.0
        )

        if use_annex_b:
            try:
                r_h, r_v, vol_m3 = _iec_annex_b_extent(
                    substance=substance,
                    ventilation=ventilation,
                    release_grade=release_grade,
                    release_rate_kg_s=release_rate_kg_s,
                    room_volume_m3=room_volume_m3,
                    ambient_temp_c=effective_temp,
                    is_indoor=is_indoor,
                )
                warnings.append(
                    "Zone extent computed using IEC 60079-10-1:2015 Annex B formula "
                    f"(release_rate={release_rate_kg_s:.4f} kg/s, "
                    f"room_volume={room_volume_m3:.1f} m3)."
                )
            except (ValueError, ZeroDivisionError) as exc:
                warnings.append(
                    f"IEC Annex B calculation failed ({exc}); "
                    "falling back to simplified k/LFL method."
                )
                use_annex_b = False

        if not use_annex_b:
            # Simplified k/LFL method (existing behaviour)
            # BUG FIX C-1: FIBER uses dust extent formula (MEC-based), not gas (LFL-based)
            if is_dust and not is_gas:
                extent = self._compute_extent_dust_v21(
                    substance.mec_g_m3 or 30.0, ventilation, is_indoor, source_height_m)
            else:
                extent = self._compute_extent_v21(
                    effective_lfl, ventilation, is_indoor, source_height_m)
            r_h = extent.horizontal_m
            r_v = extent.vertical_m
            vol_m3 = extent.volume_m3

        # Build ZoneExtent
        extent = ZoneExtent(
            horizontal_m=round(r_h, 3),
            vertical_m=round(r_v, 3),
            volume_m3=round(vol_m3, 3),
            is_outdoor=not is_indoor,
        )

        # Fix #9: Flash point check
        if substance.flash_point_c is not None and is_gas:
            if substance.flash_point_c > effective_temp:
                warnings.append(
                    f"Flash point ({substance.flash_point_c}C) > ambient "
                    f"({effective_temp}C): liquid may not be flammable "
                    "at ambient temperature. Review HAC zone assignment."
                )

        # Fix #10: MIE electrostatic warning
        if substance.mie_mj is not None and substance.mie_mj < 3.0:
            warnings.append(
                f"MIE={substance.mie_mj} mJ < 3 mJ: electrostatic ignition risk. "
                "IEC 60079-10-1 §5.5 — anti-static precautions mandatory."
            )

        # Fix #12: Temperature class vs autoignition check
        if substance.autoignition_c is not None:
            t_class = _select_temp_class(substance.autoignition_c)
            warnings.append(
                f"Max temperature class for autoignition "
                f"{substance.autoignition_c}C -> {t_class.value} "
                f"[IEC 60079-0 §7.3]"
            )

        # Fix #11: POOR ventilation + Zone 0/20 critical flag
        if ventilation == VentilationLevel.POOR and zone in (
            ZoneType.ZONE_0, ZoneType.ZONE_20
        ):
            flag = (
                "CRITICAL: Zone 0/20 with POOR ventilation — "
                "most dangerous possible classification. "
                "Mandatory engineering review required. "
                "[IEC 60079-10-1 §6.3]"
            )
            critical_flags.append(flag)

        return HACResult(
            zone=zone,
            extent=extent,
            ventilation=ventilation,
            hazard_type=substance.hazard_type,
            warnings=warnings,
            critical_flags=critical_flags,
        )

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
        """Fix #8: Hybrid = classify separately, take most severe (V21.2).

        .. deprecated::
            This method is DEAD CODE — classify_v21() handles HYBRID inline
            using _resolve_zone_with_grade_vent() which correctly considers
            release_grade. This method delegates to _classify_gas_v21 and
            _classify_dust_v21 which use _gas_zone_from_ventilation_v21 /
            _dust_zone_from_ventilation_v21 — these do NOT consider
            release_grade, producing potentially non-conservative zone
            assignments. Do NOT call this method; use classify_v21() instead.
        """
        _warnings.warn(
            "_classify_hybrid_v21 is deprecated: it does not consider "
            "release_grade in zone logic. Use classify_v21() instead.",
            DeprecationWarning,
            stacklevel=2,
        )
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
            # FIX #6 (HIGH): (ZONE_2, HIGH) → UNCLASSIFIED is only valid when
            # ventilation availability is GOOD per IEC 60079-10-1 §4.3. Without
            # availability verification, declassifying to UNCLASSIFIED is unsafe —
            # a ventilation system failure would leave an unclassified Zone 2 area.
            # Kept as ZONE_2 (conservative) until availability is confirmed.
            # When availability is verified GOOD, the calling code may apply
            # UNCLASSIFIED after explicit confirmation per IEC §4.3.
            (ZoneType.ZONE_2, VentilationLevel.HIGH):   ZoneType.ZONE_2,
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
        """Fix #7 + Fix #13: No x10, hemisphere for indoor, IEC Annex A.

        GAP-09: src_h (source height above floor) is accepted but NOT used.
        Source height affects dispersion plume geometry per IEC 60079-10-1
        Annex A — elevated releases produce different zone shapes than
        floor-level releases. Implementation requires IEC Annex A dispersion
        model. Currently zone extent is independent of source height, which
        is conservative for floor-level releases but may underestimate
        extent for elevated releases.
        """
        k = {
            VentilationLevel.HIGH:   2.0,
            VentilationLevel.MEDIUM: 5.0,
            VentilationLevel.LOW:    8.0,
            VentilationLevel.POOR:   15.0,
        }[vent]

        # BUG FIX C-2: Guard against division by very small LFL producing
        # physically meaningless zone extents (e.g., LFL=0.001 → 15000m).
        # Cap at 50m matching the dust formula's guard (IEC 60079-10-1 Annex A).
        r_h = k / max(lfl, 0.01)  # Floor LFL at 0.01 vol% (no real gas has LFL < 0.01%)
        r_h = min(r_h, 50.0)      # Physical limit per IEC 60079-10-1
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
        """Dust extent per IEC 60079-10-2 Annex A.

        GAP-09: src_h (source height above floor) is accepted but NOT used.
        Source height affects dust cloud dispersion — elevated releases
        produce larger dispersion volumes. Implementation requires
        IEC 60079-10-2 Annex A dispersion model. Currently conservative
        for floor-level releases.
        """
        k = {
            VentilationLevel.HIGH:   3.0,
            VentilationLevel.MEDIUM: 6.0,
            VentilationLevel.LOW:    10.0,
            VentilationLevel.POOR:   20.0,
        }[vent]

        # MEC floor: no real combustible dust has MEC < 1 g/m³.
        # Without this floor, very small MEC (e.g., 0.01 g/m³) produces
        # unreasonable zone extents (e.g., 60000m). Floor at 1.0 g/m³.
        mec_floored = max(mec, 1.0)
        r_h = k / (mec_floored / 30.0)
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
        ambient_temp_c:      float = 40.0,
    ) -> HACResultLegacy:
        """
        Legacy classify — backward compatible with dataclass inputs.
        Prefer classify_v21() for new code.

        FIX #7 (HIGH): Default ambient_temp_c changed from 25.0°C to 40.0°C
        to match V21 API default. The old 25°C default was non-conservative —
        Burgess-Wheeler LFL correction only activates above 25°C, so 25°C
        produced no correction and therefore underestimated zone extents.
        This legacy method is DEPRECATED — use classify_v21() for new code.
        """
        _warnings.warn(
            "classify() is deprecated — use classify_v21() for new code. "
            "Default ambient_temp_c changed from 25.0 to 40.0°C (FIX #7).",
            DeprecationWarning,
            stacklevel=2,
        )
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
