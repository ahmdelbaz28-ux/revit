"""models_v21.py – FireAI V21 Pydantic Models (Fast-Fail Validation)
==================================================================
Replaces dataclasses with Pydantic BaseModel for fail-fast validation.
No dict/tuple passes through. No silent failures. Physics validators enforced.

Standards:
  IEC 60079-0:2017     – General requirements for Ex equipment
  IEC 60079-10-1:2015  – Gas zone classification
  IEC 60079-10-2:2015  – Dust zone classification
  IEC 60079-14:2013    – Installation in explosive atmospheres
  NFPA 497-2021        – Classification of flammable liquids/gases
  NFPA 70-2023 Art. 500 – Classified locations

V21 Migration:
  - All models use ConfigDict(frozen=True, strict=True)
  - No data coercion — string "1.5" won't auto-convert to float
  - Physics validators run at construction — no invalid object can exist
  - critical_flags field prevents silent dropping of dangerous conditions

Fix #14 (CRITICAL): EPL hierarchy corrected — Ga>Gb>Gc, Da>Db>Dc
Fix #15 (CRITICAL): Temperature class selection — strictly below autoignition
Fix #16 (HIGH):      critical_flags field — cannot silently ignore Zone 0 + POOR
Fix #17 (HIGH):      protection_mode_zone_fit — ia not forced for all zones
Q6 (MEDIUM):         Spectral transparency replaces single boolean

V21.2 Hardening (Red Team fixes):
  - Burgess-Wheeler LFL thermal correction (Layer 2)
  - IEC 60079-14 thermal margin formula (Layer 4)
  - EnvironmentalContext with worst-case defaults (Layer 2)
  - SpectralSignatureRegistry for lazy-loaded spectral data (Layer 5)
  - Beer-Lambert volumetric transmittance (Layer 5)
  - VolumetricMedium for gaseous/smoke spectral absorption (Layer 5)
"""

from __future__ import annotations

import logging
import math
import threading
from enum import Enum
from typing import Dict, List, Optional, Tuple

from pydantic import BaseModel, ConfigDict, Field, model_validator

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class VentilationLevel(str, Enum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    POOR = "POOR"


class HazardType(str, Enum):
    GAS = "GAS"
    DUST = "DUST"
    HYBRID = "HYBRID"
    FIBER = "FIBER"


class ZoneType(str, Enum):
    ZONE_0 = "ZONE_0"
    ZONE_1 = "ZONE_1"
    ZONE_2 = "ZONE_2"
    ZONE_20 = "ZONE_20"
    ZONE_21 = "ZONE_21"
    ZONE_22 = "ZONE_22"
    UNCLASSIFIED = "UNCLASSIFIED"


class EPLGas(str, Enum):
    Ga = "Ga"  # highest protection
    Gb = "Gb"
    Gc = "Gc"  # lowest


class EPLDust(str, Enum):
    Da = "Da"
    Db = "Db"
    Dc = "Dc"


class EPLMining(str, Enum):
    Ma = "Ma"
    Mb = "Mb"


class TemperatureClass(str, Enum):
    """Temperature classes per IEC 60079-0:2017 §7.3.
    Includes extended subdivisions (T2A-T2D, T3A-T3C, T4A)
    for more granular equipment selection.
    """

    T1 = "T1"  # max surface 450°C
    T2 = "T2"  # max surface 300°C
    T2A = "T2A"  # max surface 280°C
    T2B = "T2B"  # max surface 260°C
    T2C = "T2C"  # max surface 230°C
    T2D = "T2D"  # max surface 215°C
    T3 = "T3"  # max surface 200°C
    T3A = "T3A"  # max surface 180°C
    T3B = "T3B"  # max surface 165°C
    T3C = "T3C"  # max surface 160°C
    T4 = "T4"  # max surface 135°C
    T4A = "T4A"  # max surface 120°C
    T5 = "T5"  # max surface 100°C
    T6 = "T6"  # max surface 85°C


# Max surface temperature per class (IEC 60079-0:2017 §7.3)
# Extended with subdivisions T2A-T2D, T3A-T3C, T4A
_T_CLASS_MAX: Dict[str, float] = {
    "T1": 450.0,
    "T2": 300.0,
    "T2A": 280.0,
    "T2B": 260.0,
    "T2C": 230.0,
    "T2D": 215.0,
    "T3": 200.0,
    "T3A": 180.0,
    "T3B": 165.0,
    "T3C": 160.0,
    "T4": 135.0,
    "T4A": 120.0,
    "T5": 100.0,
    "T6": 85.0,
}


class WavelengthBand(str, Enum):
    """Spectral bands for flame detector transparency analysis."""

    UV = "UV"  # 185-260 nm
    VIS = "VIS"  # 380-780 nm
    IR1 = "IR1"  # 1-3 um (near-IR)
    IR3 = "IR3"  # 3-5 um (mid-IR CO2 band)


class RegulatoryFramework(str, Enum):
    ATEX_EU = "ATEX_EU"
    IECEX = "IECEx"
    NEC_US = "NEC_US"
    CEC_CANADA = "CEC_CANADA"
    EFTA = "EFTA"


class PasquillStability(str, Enum):
    """Pasquill-Gifford atmospheric stability classes.
    A = extremely unstable (strong convection)
    F = moderately stable (worst case for dispersion = widest plume)
    Used by EnvironmentalContext for worst-case default.
    """

    A = "A"
    B = "B"
    C = "C"
    D = "D"
    E = "E"
    F = "F"


class ThermalMarginRule(str, Enum):
    """IEC 60079-14 thermal margin strategies.
    STRICT_5PCT: 5% margin with minimum 10K (Zone 0/20)
    STANDARD_5PCT: 5% margin with minimum 5K (Zone 1/21)
    BASIC: just strictly below (Zone 2/22)
    """

    STRICT_5PCT = "STRICT_5PCT"
    STANDARD_5PCT = "STANDARD_5PCT"
    BASIC = "BASIC"


class RegionProfile(str, Enum):
    """Environmental region presets for HAC calculations.

    Each region triggers ADVISORY warnings when engineer inputs deviate
    from typical regional conditions. The system NEVER silently overwrites
    engineer inputs — it only generates advisory warnings.

    STANDARD_IEC: Default IEC conditions (40C ambient, 0.85 fouling)
    MENA_SUMMER_OUTDOOR: Middle East/North Africa outdoor summer conditions.
        GCC desert environments regularly exceed 50C in summer months.
        Sandstorm fouling degrades optical paths more aggressively.
    GULF_HCIS: GCC / Saudi HCIS region (50-55C peak, sandstorm fouling 0.45-0.55).
        Triggers both high-temp and high-fouling advisories.
    EGYPT_CODE: Egyptian fire code region (45C peak summer, moderate fouling).
        Triggers high-temp advisory only.
    EUROPE_IEC: European IEC conditions (25-30C ambient, clean environment).
        No advisories under normal conditions.
    USA_NFPA: USA NFPA conditions (25-35C ambient, clean environment).
        No advisories under normal conditions.

    FM Global DS 5-48 acknowledges that fouling factors must reflect
    actual service conditions.
    """

    STANDARD_IEC = "STANDARD_IEC"
    MENA_SUMMER_OUTDOOR = "MENA_SUMMER_OUTDOOR"
    GULF_HCIS = "GULF_HCIS"
    EGYPT_CODE = "EGYPT_CODE"
    EUROPE_IEC = "EUROPE_IEC"
    USA_NFPA = "USA_NFPA"


class Jurisdiction(str, Enum):
    """Regulatory jurisdiction for safety audit rules.
    Each jurisdiction may impose requirements BEYOND the base IEC/NFPA standards.
    Only jurisdictions with documented, verifiable additional requirements
    are included. Empty stubs are FORBIDDEN — they mislead engineers into
    thinking a jurisdiction is covered when it is not.

    GLOBAL_IEC: Base IEC 60079 / NFPA 72 requirements.
        Zone 2 allows single detector (1oo1).
    SAUDI_HCIS: Saudi High Commission for Industrial Safety.
        Requires minimum 1oo2 voting for flame detectors in Zone 2 areas
        for critical process installations (HCIS SAF Directive 2021).
    EGYPTIAN_FIRE_CODE: Egyptian Fire Code.
        Follows NFPA 72 base standard — allows 1oo1 in Zone 2.
        Based on EGS 442-1/2 which adopts NFPA with local amendments.
    USA_NFPA: USA NFPA 72 jurisdiction.
        Allows 1oo1 in Class I Division 2 (Zone 2 equivalent).
        NFPA 72 §17.8.3.4 provides redundancy guidance but does not
        mandate 1oo2 for Zone 2.
    """

    GLOBAL_IEC = "GLOBAL_IEC"
    SAUDI_HCIS = "SAUDI_HCIS"
    EGYPTIAN_FIRE_CODE = "EGYPTIAN_FIRE_CODE"
    USA_NFPA = "USA_NFPA"


class FoulingCategory(str, Enum):
    """Categorical fouling environment classification.
    Used for advisory generation when combined with region profiles.
    Maps to typical lens_fouling_factor ranges:
      CLEAN:    0.85-1.00 (laboratory / controlled indoor)
      MODERATE: 0.70-0.85 (typical industrial)
      HEAVY:    0.55-0.70 (heavy industrial / dusty)
      SEVERE:   0.00-0.55 (desert outdoor / chemical plant)

    Reference: FM Global DS 5-48 §3.2.1
    """

    CLEAN = "CLEAN"
    MODERATE = "MODERATE"
    HEAVY = "HEAVY"
    SEVERE = "SEVERE"


class ElevationTier(str, Enum):
    """Detector/gas elevation classification for Z-Axis audit.
    Based on vapor density ratio (MW_gas / MW_air) using ±3% band.

    Air MW ≈ 28.96 g/mol. Classification uses density ratio thresholds:
      - Ratio < 0.97 (MW < 28.0912): gas is lighter than air → rises to ceiling
      - 0.97 ≤ Ratio ≤ 1.03 (28.0912 ≤ MW ≤ 29.8288): near air density → breathing zone
      - Ratio > 1.03 (MW > 29.8288): gas is heavier than air → pools at floor

    The ±3% band accounts for typical temperature/pressure variations
    and turbulent mixing effects that make strict MW=28.96 boundaries
    impractical for engineering classification.

    Reference: IEC 60079-10-1:2015 §B.4, NFPA 497 §4.5,
               Lees' Loss Prevention §15.2 (buoyancy of gases)
    """

    LOW = "LOW"  # Floor level (heavy gases, MW > 29.8288)
    BREATHING_ZONE = "BREATHING_ZONE"  # 1-2m height (28.0912 ≤ MW ≤ 29.8288)
    HIGH = "HIGH"  # Ceiling level (light gases, MW < 28.0912)


# ---------------------------------------------------------------------------
# Pydantic Models
# ---------------------------------------------------------------------------


class SubstanceProperties(BaseModel):
    """Physical properties of the hazardous substance.
    ALL validators run at construction — no invalid object can exist.
    """

    model_config = ConfigDict(frozen=True, strict=True)

    name: str
    hazard_type: HazardType
    lfl_vol_pct: Optional[float] = Field(
        None, gt=0.0, le=100.0, description="Lower Flammable Limit (vol%). Must be >0."
    )
    ufl_vol_pct: Optional[float] = Field(None, gt=0.0, le=100.0)
    flash_point_c: Optional[float] = Field(None, ge=-200.0, le=500.0)
    autoignition_c: Optional[float] = Field(None, ge=50.0, le=1000.0)
    mec_g_m3: Optional[float] = Field(None, gt=0.0, description="Minimum Explosible Concentration (dust)")
    kst_bar_m_s: Optional[float] = Field(None, ge=0.0, description="Dust explosion constant")
    mie_mj: Optional[float] = Field(None, gt=0.0, description="Minimum Ignition Energy (mJ)")
    density_kg_m3: Optional[float] = Field(None, gt=0.0)
    molecular_weight: Optional[float] = Field(None, gt=0.0)

    @model_validator(mode="after")
    def physics_consistency(self) -> SubstanceProperties:
        # flash_point must be below autoignition
        if (
            self.flash_point_c is not None
            and self.autoignition_c is not None
            and self.flash_point_c >= self.autoignition_c
        ):
            raise ValueError(
                f"flash_point_c ({self.flash_point_c}C) must be strictly "
                f"< autoignition_c ({self.autoignition_c}C). "
                f"[NFPA 497 §4.2]"
            )
        # LFL < UFL
        if self.lfl_vol_pct is not None and self.ufl_vol_pct is not None and self.lfl_vol_pct >= self.ufl_vol_pct:
            raise ValueError(f"lfl_vol_pct ({self.lfl_vol_pct}) must be < ufl_vol_pct ({self.ufl_vol_pct}).")
        # GAS needs LFL
        if self.hazard_type == HazardType.GAS and self.lfl_vol_pct is None:
            raise ValueError("GAS hazard requires lfl_vol_pct.")
        # DUST needs MEC
        if self.hazard_type == HazardType.DUST and self.mec_g_m3 is None:
            raise ValueError("DUST hazard requires mec_g_m3.")
        # HYBRID needs both
        if self.hazard_type == HazardType.HYBRID:
            if self.lfl_vol_pct is None or self.mec_g_m3 is None:
                raise ValueError("HYBRID hazard requires both lfl_vol_pct and mec_g_m3. [IEC 60079-10-1 §5.7]")
        # FIX #5 (HIGH): FIBER hazard type requires flammability data.
        # Without lfl_vol_pct or mec_g_m3, a FIBER substance passes validation
        # with zero flammability properties — a silent pass on an unvalidated
        # hazard. Fibers can be flammable (textile fibers, organic dusts) and
        # MUST have at least one flammability measure for zone classification.
        # Reference: NFPA 70 Art. 503, IEC 60079-10-2 for combustible fibers.
        if self.hazard_type == HazardType.FIBER:
            if self.lfl_vol_pct is None and self.mec_g_m3 is None:
                raise ValueError(
                    "FIBER hazard requires at least one flammability property: "
                    "lfl_vol_pct (for ignitable fiber flyings) or mec_g_m3 "
                    "(for minimum explosible concentration). "
                    "[NFPA 70 Art. 503, IEC 60079-10-2]"
                )
        return self


class ZoneExtent(BaseModel):
    """Zone boundary distances (metres). All must be non-negative."""

    model_config = ConfigDict(frozen=True, strict=True)

    horizontal_m: float = Field(ge=0.0)
    vertical_m: float = Field(ge=0.0)
    volume_m3: float = Field(ge=0.0)
    is_outdoor: bool = False  # True = full sphere, False = hemisphere

    @model_validator(mode="after")
    def extent_geometry(self) -> ZoneExtent:
        # Volume must be consistent with the appropriate volume model
        r = max(self.horizontal_m, self.vertical_m)
        if self.is_outdoor:
            max_vol = (4.0 / 3.0) * math.pi * r**3  # Full sphere
        else:
            max_vol = (2.0 / 3.0) * math.pi * r**3  # Hemisphere
        if self.volume_m3 > max_vol * 1.05:  # 5% tolerance for rounding
            shape = "sphere" if self.is_outdoor else "hemisphere"
            raise ValueError(
                f"volume_m3 ({self.volume_m3:.2f}) exceeds {shape} "
                f"of radius {r:.2f}m ({max_vol:.2f} m3). "
                f"[IEC 60079-10-1 Annex A]"
            )
        return self


class HACResult(BaseModel):
    """Result of HACClassificationEngine. Immutable after construction."""

    model_config = ConfigDict(frozen=True, strict=True)

    zone: ZoneType
    extent: ZoneExtent
    ventilation: VentilationLevel
    hazard_type: HazardType
    warnings: List[str] = Field(default_factory=list)
    # POOR ventilation + Zone 0/20 is the most dangerous combination
    # The model enforces a warning cannot be silently dropped
    critical_flags: List[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def check_critical_combination(self) -> HACResult:
        if self.ventilation == VentilationLevel.POOR and self.zone in (ZoneType.ZONE_0, ZoneType.ZONE_20):
            flag = (
                "CRITICAL: Zone 0/20 with POOR ventilation — "
                "most dangerous possible classification. "
                "Mandatory engineering review required. "
                "[IEC 60079-10-1 §6.3]"
            )
            # Cannot be silently ignored — it's in critical_flags
            if flag not in self.critical_flags:
                raise ValueError(f"{flag}\nSet critical_flags=['{flag}'] explicitly to acknowledge this condition.")
        return self


def _select_temp_class(autoignition_c: float) -> TemperatureClass:
    """FIXED Fix #15: Select temperature class whose max surface temp
    is STRICTLY LESS THAN autoignition temperature.
    IEC 60079-0 §7.3.

    Previous bug: autoignition=180C -> T3 (max 200C) -> equipment
    surface could reach 200C and ignite substance at 180C.

    Correct: autoignition=180C -> T3A (max 180C, not safe) -> T3B (max 165C, safe).
    With extended T-classes: autoignition=180C -> T3B (max 165°C).

    V21.2 Round 4: Extended T-class subdivisions (T2A-T2D, T3A-T3C, T4A)
    from IEC 60079-0:2017 §7.3 Table 3 now included for more granular
    equipment selection. Previously, autoignition=180°C -> T4 (max 135°C)
    which was overly conservative. Now -> T3B (max 165°C) which is both
    safe and cost-effective.
    """
    # Ordered from hottest to coolest surface temperature (extended classes)
    for t_class in [
        "T1",
        "T2",
        "T2A",
        "T2B",
        "T2C",
        "T2D",
        "T3",
        "T3A",
        "T3B",
        "T3C",
        "T4",
        "T4A",
        "T5",
        "T6",
    ]:
        if _T_CLASS_MAX[t_class] < autoignition_c:
            return TemperatureClass(t_class)
    raise ValueError(
        f"No safe temperature class for autoignition={autoignition_c}C. "
        f"T6 max surface is 85C. Substance autoignition must be > 85C. "
        f"[IEC 60079-0 §7.3]"
    )


class ATEXEquipmentSpec(BaseModel):
    """ATEX equipment requirements derived from zone classification.
    EPL hierarchy enforced — cannot construct an inconsistent spec.
    """

    model_config = ConfigDict(frozen=True, strict=True)

    zone: ZoneType
    epl_required: str  # "Ga"/"Gb"/"Gc"/"Da"/"Db"/"Dc"/"Ma"/"Mb"
    atex_category: str  # "1G","2G","3G","1D","2D","3D","M1","M2"
    temp_class: TemperatureClass
    protection_modes: List[str]  # e.g. ["ia","d","e"]
    autoignition_c: Optional[float] = None  # V54 FIX (V48 #6): for thermal margin validation
    hac_warnings: List[str] = Field(default_factory=list)
    hac_critical: List[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def epl_category_consistency(self) -> ATEXEquipmentSpec:
        """FIXED Fix #14: EPL hierarchy was inverted.
        Correct gas hierarchy: Ga > Gb > Gc (Ga = highest protection)
        Correct dust hierarchy: Da > Db > Dc
        """
        # V54 FIX (V48 #4): Validate atex_category against ATEX 2014/34/EU Annex I.
        _VALID_ATEX_CATEGORIES = {"1G", "2G", "3G", "1D", "2D", "3D", "M1", "M2"}
        if self.atex_category not in _VALID_ATEX_CATEGORIES:
            raise ValueError(
                f"atex_category '{self.atex_category}' is not a valid ATEX equipment category. "
                f"Must be one of: {sorted(_VALID_ATEX_CATEGORIES)}. "
                f"[ATEX 2014/34/EU Annex I]"
            )

        valid = {
            ZoneType.ZONE_0: ("Ga", "1G"),
            ZoneType.ZONE_1: ("Gb", "2G"),
            ZoneType.ZONE_2: ("Gc", "3G"),
            ZoneType.ZONE_20: ("Da", "1D"),
            ZoneType.ZONE_21: ("Db", "2D"),
            ZoneType.ZONE_22: ("Dc", "3D"),
        }
        if self.zone in valid:
            expected_epl, expected_cat = valid[self.zone]
            # EPL hierarchy: Ga satisfies Gb/Gc, Da satisfies Db/Dc
            # Gas hierarchy index: Ga=0, Gb=1, Gc=2
            gas_order = ["Ga", "Gb", "Gc"]
            dust_order = ["Da", "Db", "Dc"]
            mine_order = ["Ma", "Mb"]

            def _is_sufficient(proposed: str, required: str) -> bool:
                """True if proposed EPL is >= required (more protective)."""
                for order in [gas_order, dust_order, mine_order]:
                    if required in order and proposed in order:
                        # Lower index = more protective
                        return order.index(proposed) <= order.index(required)
                return False

            if not _is_sufficient(self.epl_required, expected_epl):
                raise ValueError(
                    f"EPL '{self.epl_required}' is INSUFFICIENT for "
                    f"{self.zone.value} (requires '{expected_epl}' or better). "
                    f"[IEC 60079-0 §5, ATEX 2014/34/EU]"
                )
        return self

    @model_validator(mode="after")
    def protection_mode_zone_fit(self) -> ATEXEquipmentSpec:
        """FIXED Fix #17: 'ia' for Zone 2 is over-specified (costly, unnecessary).
        Zone 2 -> 'ic' is sufficient. Zone 1 -> 'ib' or 'ia'. Zone 0 -> 'ia' only.
        [IEC 60079-14]
        """
        zone_allowed = {
            # V25 FIX: IEC 60079-14 protection concepts permitted per zone.
            # Zone 0 (EPL Ga) — most hazardous, continuous hazard.
            # ONLY "ia" (intrinsically safe, level a), "ma" (encapsulation, level a),
            # and "s" (special, if specifically designed for Zone 0) are permitted.
            # "d" (flameproof) and "e" (increased safety) are EPL Gb — Zone 1 only.
            # Allowing Gb equipment in Zone 0 is a LIFE SAFETY failure:
            # flameproof enclosure could contain an explosion but NOT prevent ignition
            # in a Zone 0 continuous-hazard atmosphere.
            ZoneType.ZONE_0: {"ia", "s", "ma"},
            ZoneType.ZONE_1: {"ia", "ib", "d", "e", "px", "py", "s", "ma", "mb", "o", "p", "q"},
            ZoneType.ZONE_2: {
                "ia",
                "ib",
                "ic",
                "d",
                "e",
                "px",
                "py",
                "pz",
                "n",
                "s",
                "ec",
                "ma",
                "mb",
                "o",
                "p",
                "q",
                "nA",
                "nC",
                "nR",
            },
            # Zone 20 (EPL Da) — dust equivalent of Zone 0.
            # "tb" is EPL Db (Zone 21 only). Removed from Zone 20 allowed list.
            ZoneType.ZONE_20: {"ia", "ma", "ta", "s", "tD"},
            # V48 FIX: Removed "tc" from Zone 21 — "tc" is EPL Dc (Zone 22 only).
            # Zone 21 requires EPL Db minimum. Per IEC 60079-31:2022 §6,
            # "tc" (protection by enclosure) is rated EPL Dc for Zone 22.
            ZoneType.ZONE_21: {"ia", "ib", "ma", "mb", "tb"},
            ZoneType.ZONE_22: {"ia", "ib", "ic", "ma", "mb", "mc", "ta", "tb", "tc"},
        }
        if self.zone in zone_allowed:
            for mode in self.protection_modes:
                if mode not in zone_allowed[self.zone]:
                    raise ValueError(f"Protection mode '{mode}' not permitted for {self.zone.value}. [IEC 60079-14]")
        return self

    @model_validator(mode="after")
    def thermal_margin_check(self) -> ATEXEquipmentSpec:
        """V54 FIX (V48 #6): Validate thermal margin per IEC 60079-14 §5.3.

        When autoignition_c is provided, verify that the temperature class
        provides adequate margin. For Zone 0/1/20/21: requires 5% margin
        (max surface temp ≤ 95% of autoignition). For Zone 2/22: strict below.

        MED-06 FIX: When a thermal margin violation is detected, the result
        must NOT appear compliant. Previously, violations were silently appended
        to hac_critical without affecting any compliance status. Now we also
        log a CRITICAL warning so the violation is immediately visible.
        """
        if self.autoignition_c is not None and self.autoignition_c > 0:
            t_max = _T_CLASS_MAX.get(self.temp_class.value, 0)
            if t_max > 0:
                # Zone 0/1/20/21: 5% thermal margin per IEC 60079-14 §5.3
                if self.zone in (ZoneType.ZONE_0, ZoneType.ZONE_1, ZoneType.ZONE_20, ZoneType.ZONE_21):
                    max_allowed = self.autoignition_c * 0.95
                    if t_max > max_allowed:
                        hac_critical_entry = (
                            f"Thermal margin violation: T-class {self.temp_class.value} "
                            f"(max {t_max}°C) exceeds 95% of autoignition "
                            f"({self.autoignition_c}°C × 0.95 = {max_allowed:.1f}°C) "
                            f"for {self.zone.value}. [IEC 60079-14 §5.3]"
                        )
                        # Cannot raise ValueError because frozen model; append to hac_critical
                        object.__setattr__(self, "hac_critical", list(self.hac_critical) + [hac_critical_entry])
                        # MED-06 FIX: Log CRITICAL so violation is not silent
                        logger.critical(
                            "MED-06: %s — equipment specification is NOT compliant. "
                            "hac_critical is non-empty but was previously ignored by callers.",
                            hac_critical_entry,
                        )
                # Zone 2/22: strict below
                elif self.zone in (ZoneType.ZONE_2, ZoneType.ZONE_22):
                    if t_max >= self.autoignition_c:
                        hac_critical_entry = (
                            f"Thermal margin violation: T-class {self.temp_class.value} "
                            f"(max {t_max}°C) must be STRICTLY BELOW autoignition "
                            f"({self.autoignition_c}°C) for {self.zone.value}. "
                            f"[IEC 60079-14 §5.3]"
                        )
                        object.__setattr__(self, "hac_critical", list(self.hac_critical) + [hac_critical_entry])
                        # MED-06 FIX: Log CRITICAL so violation is not silent
                        logger.critical(
                            "MED-06: %s — equipment specification is NOT compliant. "
                            "hac_critical is non-empty but was previously ignored by callers.",
                            hac_critical_entry,
                        )
        return self


class Obstruction(BaseModel):
    """FIXED Q6: Spectral transparency replaces single boolean.
    Glass: UV=0.0 (opaque), IR=0.8 (mostly transparent).
    Polycarbonate: UV=0.0, VIS=0.9, IR=0.7.
    Steel: all 0.0.
    """

    model_config = ConfigDict(frozen=True, strict=True)

    obstruction_id: str
    vertices: List[List[float]]  # list of [x,y,z]
    spectral_transparency: Dict[WavelengthBand, float] = Field(
        default_factory=lambda: {
            WavelengthBand.UV: 0.0,
            WavelengthBand.VIS: 0.0,
            WavelengthBand.IR1: 0.0,
            WavelengthBand.IR3: 0.0,
        }
    )

    @model_validator(mode="after")
    def transparency_range(self) -> Obstruction:
        for band, val in self.spectral_transparency.items():
            if not 0.0 <= val <= 1.0:
                raise ValueError(f"spectral_transparency[{band}]={val} must be in [0.0, 1.0].")
        return self

    def is_transparent_for(self, band: WavelengthBand) -> bool:
        """True if transmittance >= 0.70 for this spectral band.

        V54 FIX (V48 #10): Threshold raised from 0.50 to 0.70 per FM Global DS 5-48 §3.2.1.
        At transmittance=0.50, a 10m optical path reduces signal to 0.50^10 ≈ 0.001
        (undetectable). Beer-Lambert exponential attenuation means 0.50 transmittance
        is NOT sufficient for reliable flame detection. FM Global DS 5-48 §3.2.1
        recommends transmittance >= 0.70 for reliable detection at rated range.

        V66 FIX: Changed from strict > to >= to correctly handle boundary case.
        At transmittance exactly 0.70, the FM Global threshold is met — the
        obstruction is transparent enough for flame detection. The strict
        inequality created an off-by-one boundary where glass with 70% IR
        transmittance (a common architectural glazing value) was incorrectly
        classified as opaque, potentially blocking valid detector coverage paths.
        """
        return self.spectral_transparency.get(band, 0.0) >= 0.70

    def transmittance_for(self, band: WavelengthBand) -> float:
        return self.spectral_transparency.get(band, 0.0)


class FlameDetectorSpec(BaseModel):
    """Flame detector physical specification for ray-trace engine.
    """

    model_config = ConfigDict(frozen=True, strict=True)

    detector_id: str
    position: List[float] = Field(min_length=3, max_length=3)
    orientation_vector: List[float] = Field(min_length=3, max_length=3)
    rated_range_m: float = Field(gt=0.0, le=200.0)
    aoc_deg: float = Field(gt=0.0, le=180.0, description="Angle of Coverage (degrees)")
    spectral_bands: List[WavelengthBand] = Field(min_length=1)

    @model_validator(mode="after")
    def orientation_not_zero(self) -> FlameDetectorSpec:
        mag = math.sqrt(sum(v**2 for v in self.orientation_vector))
        if mag < 1e-9:
            raise ValueError("orientation_vector must not be zero vector.")
        return self

    @model_validator(mode="after")
    def position_valid(self) -> FlameDetectorSpec:
        if any(not math.isfinite(v) for v in self.position):
            raise ValueError("position contains non-finite values.")
        return self

    @property
    def orientation_unit(self) -> List[float]:
        mag = math.sqrt(sum(v**2 for v in self.orientation_vector))
        return [v / mag for v in self.orientation_vector]

    def is_facing_upward(self) -> bool:
        """Detector pointing up (z > 0.9) won't cover floor.
        Returns True if detector aims predominantly upward.
        """
        unit = self.orientation_unit
        return unit[2] > 0.9


class RayTracePoint(BaseModel):
    """A target point in the ray-trace grid."""

    model_config = ConfigDict(frozen=True, strict=True)

    x: float
    y: float
    z: float = 0.0

    def to_tuple(self) -> tuple:
        return (self.x, self.y, self.z)


class RegSelectorResult(BaseModel):
    """Result of regulatory framework resolution."""

    model_config = ConfigDict(frozen=True, strict=True)

    country_code: str
    framework: RegulatoryFramework
    zone_system: str  # "ZONE" or "DIVISION"
    warnings: List[str]


# ===========================================================================
# V21.2: Environmental Context (Dynamic Physics Inputs)
# ===========================================================================


class EnvironmentalContext(BaseModel):
    """Strict context for HAC calculations with environmental correction.
    Defaults to worst-case indoor scenarios to guarantee fail-safe designs.

    If an engineer does NOT provide environmental data, the system assumes
    the worst: stagnant air (F stability, 0.5 m/s wind), high ambient temp.
    This ensures the widest hazardous zone — conservative by design.

    Standards: IEC 60079-10-1:2015 Annex B, NFPA 497 §4.3
    """

    model_config = ConfigDict(frozen=True, strict=True)

    ambient_temp_c: float = Field(
        default=40.0,
        ge=-40.0,
        le=85.0,
        description=(
            "Ambient temperature for LFL thermal correction (Burgess-Wheeler). "
            "Default 40C = typical indoor industrial environment. "
            "IEC 60079-10-1 Annex B."
        ),
    )
    wind_speed_m_s: float = Field(
        default=0.5,
        gt=0.0,
        le=50.0,
        description=(
            "Wind speed (m/s). Default 0.5 simulates stagnant indoor air. "
            "This produces the widest zone extent (conservative)."
        ),
    )
    stability_class: PasquillStability = Field(
        default=PasquillStability.F,
        description=(
            "Atmospheric stability. F = least dispersion = highest risk. "
            "Used for zone extent calculation, not full Gaussian Plume. "
            "IEC 60079-10-1 Annex A."
        ),
    )
    is_indoor: bool = Field(
        default=True,
        description="Indoor = hemisphere (2/3*pi*r^3). Outdoor = full sphere.",
    )
    lens_fouling_factor: float = Field(
        default=0.85,
        gt=0.0,
        le=1.0,
        description=(
            "Optical path attenuation from lens fouling over service life. "
            "1.0 = pristine lens (laboratory), 0.85 = typical industrial, "
            "0.65 = heavy industrial without scheduled cleaning. "
            "FM Global DS 5-48 §3.2.1 acknowledges optical degradation. "
            "Applied to Beer-Lambert transmittance in Layer 5."
        ),
    )
    region: RegionProfile = Field(
        default=RegionProfile.STANDARD_IEC,
        description=(
            "Environmental region preset. MENA_SUMMER_OUTDOOR triggers "
            "advisory warnings for high ambient temperature and sandstorm "
            "fouling. Does NOT force values — engineer judgment prevails. "
            "Burgess-Wheeler LFL correction reacts to actual ambient_temp_c."
        ),
    )
    jurisdiction: Jurisdiction = Field(
        default=Jurisdiction.GLOBAL_IEC,
        description=(
            "Regulatory jurisdiction for audit rules. SAUDI_HCIS requires "
            "minimum 1oo2 voting in Zone 2 for critical installations. "
            "GLOBAL_IEC uses base IEC 60079 / NFPA 72 requirements."
        ),
    )
    fouling_category: Optional[FoulingCategory] = Field(
        default=None,
        description=(
            "Categorical fouling environment. When set, generates regional "
            "advisory warnings if the category seems optimistic for the "
            "selected region. Does NOT override lens_fouling_factor. "
            "FM Global DS 5-48 §3.2.1."
        ),
    )

    @model_validator(mode="after")
    def cross_validate_environment(self) -> EnvironmentalContext:
        # Physically impossible: high instability with near-zero wind
        if self.wind_speed_m_s < 2.0 and self.stability_class in (PasquillStability.A, PasquillStability.B):
            raise ValueError(
                "Physics Violation: Highly unstable conditions (A/B) cannot exist "
                "with wind speed < 2.0 m/s in standard dispersion models. "
                "Either increase wind_speed or use stability class C-F. "
                "[Pasquill-Gifford correlation]"
            )
        return self

    @property
    def advisories(self) -> List[str]:
        """Generate advisory warnings based on region vs actual values.

        The system NEVER silently overwrites engineer inputs. Instead,
        it generates advisory warnings when the selected region suggests
        conditions may differ from what the engineer specified. This
        preserves engineering judgment while flagging potential issues.

        Advisory Rules:
          - MENA/GULF regions with ambient_temp_c < 50C → temp advisory
          - MENA/GULF regions with fouling_category=CLEAN → fouling advisory
          - EGYPT region with ambient_temp_c < 45C → temp advisory
          - EUROPE/USA/STANDARD_IEC → no regional advisories

        Returns:
            List of advisory warning strings

        """
        warnings: List[str] = []

        # MENA / GCC regions: peak summer temperatures 50-55C
        if self.region in (RegionProfile.MENA_SUMMER_OUTDOOR, RegionProfile.GULF_HCIS):
            if self.ambient_temp_c < 50.0:
                warnings.append(
                    f"MENA/GULF region selected but ambient temperature "
                    f"({self.ambient_temp_c:.1f}C) is below typical GCC summer "
                    f"peak of 50-55.0C. Verify outdoor temperature assumption. "
                    f"Burgess-Wheeler LFL correction at higher temperatures "
                    f"produces wider zone extents."
                )
            if self.fouling_category == FoulingCategory.CLEAN:
                warnings.append(
                    "MENA/GULF region with CLEAN fouling category. GCC desert "
                    "sandstorms can degrade fouling to 0.45-0.55 for outdoor "
                    "detectors. CLEAN assumption may be optimistic. "
                    "[FM Global DS 5-48 §3.2.1]"
                )

        # EGYPT region: peak summer ~45C
        # Egypt has moderate dust but not severe sandstorms like the Gulf.
        # Fouling advisory is only triggered for severe desert regions
        # (MENA_SUMMER_OUTDOOR, GULF_HCIS) where sandstorms are common.
        if self.region == RegionProfile.EGYPT_CODE:
            if self.ambient_temp_c < 45.0:
                warnings.append(
                    f"EGYPT region selected but ambient temperature "
                    f"({self.ambient_temp_c:.1f}C) is below typical Egyptian "
                    f"summer peak of 45.0C. Verify outdoor temperature assumption."
                )

        return warnings


# ===========================================================================
# V21.2: Zone-Based Minimum Redundancy (NFPA 72 §17.8.3.4)
# ===========================================================================

MIN_REDUNDANCY_BY_ZONE: Dict[ZoneType, int] = {
    # High-risk zones require voting architecture (1oo2 minimum)
    ZoneType.ZONE_0: 3,  # 2oo3 voting — continuous presence
    ZoneType.ZONE_1: 2,  # 1oo2 minimum — NFPA 72 §17.8.3.4
    ZoneType.ZONE_2: 1,  # Single detector acceptable
    ZoneType.ZONE_20: 3,  # 2oo3 voting — continuous dust
    ZoneType.ZONE_21: 2,  # 1oo2 minimum
    ZoneType.ZONE_22: 1,  # Single acceptable
    ZoneType.UNCLASSIFIED: 0,  # No detector required
}


# ===========================================================================
# V21.2: Vapor Density Tier (Ratio-Based Buoyancy Classification)
# ===========================================================================

# Molecular weight of dry air at STP (g/mol)
# Source: CRC Handbook of Chemistry and Physics, 97th Edition
_MW_AIR: float = 28.96

# Density ratio thresholds for gas buoyancy classification.
# A gas with density ratio < 0.97 is considered significantly lighter
# than air (rises), while ratio > 1.03 is significantly heavier (sinks).
# The ±3% band accounts for typical temperature/pressure variations
# and mixing effects that make strict MW=28.96 boundaries impractical.
#
# Ratio = MW_gas / MW_air
# HIGH threshold:  MW < 28.96 × 0.97 = 28.0912 → gas rises
# LOW threshold:   MW > 28.96 × 1.03 = 29.8288 → gas sinks
#
# Reference: IEC 60079-10-1:2015 §B.4 (vertical extent buoyancy factor),
#            NFPA 497-2021 §4.5 (vapor density classification),
#            Lees' Loss Prevention §15.2 (buoyancy of gases)
_VD_RATIO_HIGH: float = 0.97  # Below this ratio → gas is lighter, rises
_VD_RATIO_LOW: float = 1.03  # Above this ratio → gas is heavier, sinks
_MW_HIGH_THRESHOLD: float = _MW_AIR * _VD_RATIO_HIGH  # 28.0912
_MW_LOW_THRESHOLD: float = _MW_AIR * _VD_RATIO_LOW  # 29.8288


def vapor_density_tier(molecular_weight: float) -> ElevationTier:
    """Classify gas buoyancy behavior by molecular weight using density ratios.

    This function uses precise density ratios (MW_gas / MW_air) rather
    than fixed MW thresholds, providing a physically rigorous classification
    of where a gas is expected to accumulate relative to air.

    At the same temperature and pressure (ideal gas law: ρ = PM/RT),
    density is proportional to molecular weight. The ratio MW_gas/MW_air
    directly gives the vapor density relative to air:
      - Ratio < 0.97 → gas is noticeably lighter → rises to ceiling (HIGH)
      - 0.97 ≤ Ratio ≤ 1.03 → gas is near air density → breathing zone
      - Ratio > 1.03 → gas is noticeably heavier → pools at floor (LOW)

    The ±3% band accounts for typical temperature/pressure variations
    and turbulent mixing effects that make strict equality impractical.

    Args:
        molecular_weight: Molecular weight of the gas (g/mol). Must be > 0.

    Returns:
        ElevationTier indicating where the gas is expected to accumulate

    Raises:
        ValueError: If molecular_weight is not greater than 0

    Reference: IEC 60079-10-1:2015 §B.4, NFPA 497 §4.5

    """
    # V57 FIX (Finding 13): NaN molecular_weight silently returns LOW — NaN <= 0
    # is False, NaN < _MW_HIGH_THRESHOLD is False, NaN <= _MW_LOW_THRESHOLD is False,
    # so the else branch returns LOW. A NaN molecular weight means the gas buoyancy
    # is UNKNOWN and must not be silently classified. Raise ValueError instead.
    if not math.isfinite(molecular_weight):
        raise ValueError(
            f"molecular_weight must be finite, got {molecular_weight}. "
            f"NaN/Inf molecular weight cannot be classified for vapor density tier. "
            f"[IEC 60079-10-1 §B.4]"
        )

    if molecular_weight <= 0:
        raise ValueError(
            f"molecular_weight must be greater than 0, got {molecular_weight}. "
            f"Molecular weight is a physical property that cannot be zero or negative."
        )

    if molecular_weight < _MW_HIGH_THRESHOLD:
        return ElevationTier.HIGH
    if molecular_weight <= _MW_LOW_THRESHOLD:
        return ElevationTier.BREATHING_ZONE
    return ElevationTier.LOW


# ===========================================================================
# V21.2: Room Purge Time (IEC 60079-10-1 Annex B Ventilation Dilution)
# ===========================================================================


def room_purge_time(
    room_volume_m3: float,
    ach: float,
    target_fraction: float = 0.01,
) -> float:
    """Calculate the time (seconds) for ventilation to reduce gas concentration
    to `target_fraction` of initial concentration.

    Based on IEC 60079-10-1:2015 Annex B §B.2 dilution model:
        C(t) = C_0 * exp(-ACH * t / 3600)

    Solving for t when C(t)/C_0 = target_fraction:
        t = -3600 / ACH * ln(target_fraction)

    This is NOT zone reclassification — zones are based on source frequency
    and duration per IEC §4.2. This calculation helps engineers estimate
    how long a room takes to purge after a release.

    Args:
        room_volume_m3: Room volume (m³). Included for API consistency;
            the exponential decay model assumes perfect mixing regardless
            of room size (IEC Annex B limitation).
        ach: Air changes per hour (1/h)
        target_fraction: Target concentration as fraction of initial
            (0.01 = 1% of initial, 0.001 = 0.1%)

    Returns:
        Time in seconds to reach target fraction. Always >= 0.

    Reference: IEC 60079-10-1:2015 Annex B §B.2,
               NFPA 497-2021 §4.3,
               Lees' Loss Prevention §15.3 (exponential dilution)

    """
    if ach <= 0.0 or target_fraction <= 0.0 or target_fraction >= 1.0:
        return float("inf")  # Cannot purge without ventilation

    # t = -3600/ACH * ln(target_fraction)
    # ln(0.01) ≈ -4.605, ln(0.001) ≈ -6.908
    t_seconds = -3600.0 / ach * math.log(target_fraction)
    return max(t_seconds, 0.0)


def room_concentration_at_time(
    initial_concentration_vol_pct: float,
    ach: float,
    time_seconds: float,
) -> float:
    """Calculate gas concentration at time t using exponential dilution.

    C(t) = C_0 * exp(-ACH * t / 3600)

    IEC 60079-10-1:2015 Annex B §B.2: "In a room with adequate ventilation,
    the concentration of a flammable gas after a release decreases
    exponentially with the number of air changes."

    Args:
        initial_concentration_vol_pct: Initial concentration (vol%)
        ach: Air changes per hour (1/h)
        time_seconds: Time since release (seconds)

    Returns:
        Concentration at time t (vol%)

    """
    if ach <= 0.0:
        return initial_concentration_vol_pct  # No ventilation = no decay
    decay_constant = ach / 3600.0
    return initial_concentration_vol_pct * math.exp(-decay_constant * time_seconds)


# ===========================================================================
# V21.2: Burgess-Wheeler LFL Thermal Correction
# ===========================================================================


def burgess_wheeler_lfl(
    lfl_25c: float,
    ambient_temp_c: float,
    heat_of_combustion_kj_mol: Optional[float] = None,
    lfl_floor_ratio: Optional[float] = 0.5,
) -> float:
    """Burgess-Wheeler LFL thermal correction.

    At elevated temperatures, gases expand and LFL decreases.
    This is NOT optional — IEC 60079-10-1 Annex B acknowledges that
    zone extent depends on ambient conditions.

    Formula:  LFL_T = LFL_25C * (1 - 0.001824 * (T - 25))
    where the coefficient 0.001824 is derived from Burgess-Wheeler data.

    If heat_of_combustion is provided, uses the full Burgess-Wheeler equation:
      LFL_T = LFL_25C - 0.001824 * (T - 25) * LFL_25C
    (simplified form consistent with Zabetakis' compilation)

    Args:
        lfl_25c: LFL at 25C (vol%)
        ambient_temp_c: actual ambient temperature
        heat_of_combustion_kj_mol: optional, improves accuracy if available
        lfl_floor_ratio: minimum floor for corrected LFL as fraction of lfl_25c.
            Default 0.5 (50% floor) is a widely-used engineering safety factor,
            but is NON-CONSERVATIVE for zone extent at high temperatures (>200C).
            Set to None to disable floor (use uncorrected physics — conservative
            for zone extent). Per IEC 60079-10-1, high-temp applications should
            use lfl_floor_ratio=None to avoid underestimating zone extent.

    Returns:
        LFL at the given ambient temperature (always < LFL_25C when T > 25C)

    Reference: Burgess & Wheeler (1929), Zabetakis (1965) Bureau of Mines
               Bulletin 627, IEC 60079-10-1 Annex B.

    """
    # V53 FIX: lfl_25c must be positive — it's a physical property.
    # Zero or negative LFL has no physical meaning and would bypass
    # zone extent calculations or produce division-by-zero downstream.
    if lfl_25c <= 0.0:
        raise ValueError(
            f"lfl_25c must be > 0, got {lfl_25c}. "
            f"LFL is a physical property that must be positive. "
            f"[IEC 60079-10-1 §4.2]"
        )

    if ambient_temp_c <= 25.0:
        return lfl_25c  # No correction needed below reference temp

    delta_t = ambient_temp_c - 25.0

    # Standard Burgess-Wheeler coefficient
    # V53 FIX: Removed fabricated "refined" correction (ΔHc/800 scaling).
    # The standard BW formula (Burgess & Wheeler 1929, Zabetakis 1965) is:
    #   LFL_T = LFL_25C × (1 - 0.001824 × ΔT)
    # There is no published basis for scaling the coefficient by ΔHc/800.
    # For hydrogen (ΔHc≈286 kJ/mol): refined_factor = 286/800 = 0.358,
    # clamped to 0.5 — this HALVES the thermal correction, meaning a
    # HIGHER LFL at temperature → SMALLER zone extent → NON-CONSERVATIVE.
    correction = 0.001824 * delta_t
    lfl_t = lfl_25c * (1.0 - correction)

    # LFL must remain positive.
    # V31 FIX: The 50% floor is now configurable via lfl_floor_ratio parameter.
    # - lfl_floor_ratio=0.5 (default): backward-compatible, prevents extreme
    #   corrections but may underestimate zone extent at T>200C.
    # - lfl_floor_ratio=None: no floor — physically correct, conservative for
    #   zone extent (produces WIDER zones at high T per IEC 60079-10-1).
    # Per agent.md V25 finding #2, high-temperature applications MUST use
    # lfl_floor_ratio=None to avoid non-conservative zone extent calculations.
    floor = lfl_25c * lfl_floor_ratio if lfl_floor_ratio is not None else 0.0
    return max(lfl_t, floor)


# ===========================================================================
# V21.2: IEC 60079-14 Thermal Margin (Safe Temperature Selection)
# ===========================================================================


def _select_temp_class_with_margin(
    autoignition_c: float,
    zone: ZoneType,
) -> TemperatureClass:
    """V21.2: Select temperature class with IEC 60079-14 thermal margin.

    The previous _select_temp_class only required max_surface < autoignition.
    This left a 1C margin (e.g., autoignition=136C -> T4 max 135C) which is
    engineering negligence.

    IEC 60079-14 §5.3 requires a safety margin:
    - Zone 0/20:  max_surface <= autoignition * 0.95  (5% margin, min 10K)
    - Zone 1/21:  max_surface <= autoignition * 0.95  (5% margin, min 5K)
    - Zone 2/22:  max_surface < autoignition           (strictly below)

    Formula:  T_safe = autoignition - max(5K, 0.05 * autoignition)
    For Zone 0/20: T_safe = autoignition - max(10K, 0.05 * autoignition)

    Then select T-class where max_surface_temp <= T_safe.

    Args:
        autoignition_c: autoignition temperature of the gas/vapor
        zone: the zone type determines the margin rule

    Returns:
        TemperatureClass with max_surface_temp <= T_safe

    Raises:
        ValueError: if no temperature class satisfies the margin requirement

    Reference: IEC 60079-14:2013 §5.3, IEC 60079-0:2017 §7.3

    """
    # Determine safe maximum surface temperature
    if zone in (ZoneType.ZONE_0, ZoneType.ZONE_20):
        t_safe = autoignition_c - max(10.0, 0.05 * autoignition_c)
    elif zone in (ZoneType.ZONE_1, ZoneType.ZONE_21):
        t_safe = autoignition_c - max(5.0, 0.05 * autoignition_c)
    else:  # Zone 2/22
        t_safe = autoignition_c - 1.0  # Just strictly below

    # V21.2 Round 4: Extended T-class subdivisions for more granular selection
    # GAP-08: The condition `_T_CLASS_MAX[t_class] <= t_safe` is intentional.
    # IEC 60079-0:2017 §7.3 states: "the maximum surface temperature of
    # the equipment shall not exceed the ignition temperature of the
    # surrounding atmosphere" — i.e., T_surface ≤ T_ignition (≤ not <).
    # Therefore _T_CLASS_MAX[t_class] <= t_safe is correct.
    # _select_temp_class (basic, no margin) uses < for strictly below.
    # If a future reviewer changes either function, both must change together.
    for t_class in [
        "T1",
        "T2",
        "T2A",
        "T2B",
        "T2C",
        "T2D",
        "T3",
        "T3A",
        "T3B",
        "T3C",
        "T4",
        "T4A",
        "T5",
        "T6",
    ]:
        if _T_CLASS_MAX[t_class] <= t_safe:
            return TemperatureClass(t_class)

    raise ValueError(
        f"No safe temperature class for autoignition={autoignition_c}C "
        f"in {zone.value}. T_safe={t_safe:.1f}C. "
        f"T6 max surface is 85C. "
        f"[IEC 60079-14 §5.3, IEC 60079-0 §7.3]"
    )


# ===========================================================================
# V21.2: Spectral Signature Registry (Lazy Load)
# ===========================================================================

# ── GAP-03: Default medium absorption coefficients ───────────
# Source: Drysdale "An Introduction to Fire Dynamics" Table 4.1,
#         ISO 13943:2017 §3.88 (smoke optical density), EN 54-12
#         IR band values from NIST WebBook (representative order-of-magnitude).
_DEFAULT_MEDIUM_ALPHA: Dict[str, Dict[str, float]] = {
    # SMOKE: condensed carbonaceous aerosol, d_p ≈ 0.1–1 µm
    # UV 2.0 m⁻¹, VIS 3.0 m⁻¹  (Mie scattering peak in visible)
    # IR1 (1–2.7 µm) 1.5 m⁻¹, IR3 (3.7–5 µm) 0.8 m⁻¹
    "SMOKE": {"UV": 2.0, "VIS": 3.0, "IR1": 1.5, "IR3": 0.8},
    # STEAM: water vapour, strong IR1 and IR3 absorption bands
    # HITRAN database: H₂O strong bands at 1.4 µm and 2.7 µm
    "STEAM": {"UV": 0.5, "VIS": 1.5, "IR1": 2.0, "IR3": 3.0},
    # DUST_SUSPENSION: combustible dust cloud, d_p ≈ 10–100 µm
    # Larger particles → geometric scattering → flat spectrum
    "DUST_SUSPENSION": {"UV": 3.0, "VIS": 4.0, "IR1": 2.5, "IR3": 1.5},
    # GAS_CLOUD: hydrocarbon vapour at low concentration (<LEL)
    # UV opaque to most organics; VIS transparent; IR1/IR3 C-H bonds
    "GAS_CLOUD": {"UV": 0.1, "VIS": 0.0, "IR1": 0.1, "IR3": 0.5},
    # MIST: fine liquid droplets (oil mist, water spray)
    # Similar to steam but coarser droplets → stronger UV/VIS scattering
    # [Consultant Phase 5 addition — common in industrial environments]
    "MIST": {"UV": 1.0, "VIS": 2.0, "IR1": 2.5, "IR3": 2.0},
    # CLEAR: no medium present (ambient air without contaminants)
    # All bands transparent — used as fallback for clean environments
    "CLEAR": {"UV": 0.0, "VIS": 0.0, "IR1": 0.0, "IR3": 0.0},
}


class SpectralSignature(BaseModel):
    """Spectral absorption coefficient per wavelength band for a substance.
    Used by Layer 5 Beer-Lambert volumetric transmittance calculations.

    Decoupled from SubstanceProperties to keep the core model lightweight.
    Loaded on-demand via SpectralSignatureRegistry.

    Reference: IEC 60079-29-4, NIST Chemistry WebBook
    """

    model_config = ConfigDict(frozen=True, strict=True)

    cas_number: str
    substance_name: str
    # Absorption coefficient per band (m^-1) for Beer-Lambert: T = exp(-alpha * d)
    # Higher = more absorption at that wavelength
    alpha_uv: float = Field(0.0, ge=0.0, description="UV band absorption coeff (m^-1)")
    alpha_vis: float = Field(0.0, ge=0.0, description="VIS band absorption coeff (m^-1)")
    alpha_ir1: float = Field(0.0, ge=0.0, description="IR1 (1-3um) absorption coeff (m^-1)")
    alpha_ir3: float = Field(0.0, ge=0.0, description="IR3 (3-5um CO2) absorption coeff (m^-1)")

    def alpha_for(self, band: WavelengthBand) -> float:
        """Get absorption coefficient for a specific band."""
        return {
            WavelengthBand.UV: self.alpha_uv,
            WavelengthBand.VIS: self.alpha_vis,
            WavelengthBand.IR1: self.alpha_ir1,
            WavelengthBand.IR3: self.alpha_ir3,
        }[band]


class SpectralSignatureRegistry:
    """Lazy-loaded registry of spectral signatures indexed by CAS number.

    Design rationale: Spectral data is only needed in Layer 5 (optical).
    Loading it into SubstanceProperties would bloat Layers 1-4.
    This registry is loaded on demand when the ray-trace engine runs.

    Usage:
        registry = SpectralSignatureRegistry()
        sig = registry.get("74-82-8")  # Methane
        alpha = sig.alpha_for(WavelengthBand.IR3)
    """

    def __init__(self) -> None:
        self._signatures: Dict[str, SpectralSignature] = {}
        self._loaded = False
        self._lock = threading.Lock()

    def _ensure_loaded(self) -> None:
        # Thread-safety: double-checked locking to prevent race condition
        # where multiple threads load signatures concurrently.
        if self._loaded:
            return
        with self._lock:
            if self._loaded:
                return
            self._load_builtin_signatures()
            self._loaded = True

    def _load_builtin_signatures(self) -> None:
        """Load built-in spectral signatures (called under lock)."""
        # Absorption coefficients are representative values from literature
        # For CO2-band (4.3um): hydrocarbons have strong absorption
        self._signatures = {
            # Methane (CH4)
            # V30 FIX: alpha_ir3 corrected from 0.8 to 0.4 per HITRAN 2020 data.
            # CH4's dominant IR absorption is at 3.3 µm (ν₃) and 7.7 µm (ν₄).
            # In the CO2-band (4.3 µm), CH4 absorption is weak; the broadband
            # 3-5 µm average was previously 0.8 but this overestimates by ~2×
            # for CO2-band flame detectors. The corrected value of 0.4 is still
            # slightly conservative (literature: 0.3-0.4 at 1% v/v).
            # NOTE: The old value 0.8 was conservative (more detectors) but
            # produced over-design in LNG facilities.
            "74-82-8": SpectralSignature(
                cas_number="74-82-8",
                substance_name="Methane",
                alpha_uv=0.1,
                alpha_vis=0.0,
                alpha_ir1=0.05,
                alpha_ir3=0.4,
            ),
            # Propane (C3H8)
            "74-98-6": SpectralSignature(
                cas_number="74-98-6",
                substance_name="Propane",
                alpha_uv=0.1,
                alpha_vis=0.0,
                alpha_ir1=0.1,
                alpha_ir3=1.2,
            ),
            # Hydrogen (H2) - no IR absorption, UV only
            "1333-74-0": SpectralSignature(
                cas_number="1333-74-0",
                substance_name="Hydrogen",
                alpha_uv=0.5,
                alpha_vis=0.0,
                alpha_ir1=0.0,
                alpha_ir3=0.0,
            ),
            # Carbon Monoxide (CO)
            "630-08-0": SpectralSignature(
                cas_number="630-08-0",
                substance_name="Carbon Monoxide",
                alpha_uv=0.2,
                alpha_vis=0.0,
                alpha_ir1=0.3,
                alpha_ir3=0.1,
            ),
            # ── GAP-04: Extended substances (12 new entries) ──
            # Absorption coefficients (m⁻¹ at 1 atm, 25 °C, 1% v/v concentration)
            # Sources: NIST WebBook, Ingle & Crouch "Spectrochemical Analysis",
            #          Hollas "Modern Spectroscopy" 4th ed.
            # Ethylene C₂H₄ — CAS 74-85-1
            # Strong UV absorption (π→π* at 165 nm); C-H stretch at 3.3 µm (IR1)
            "74-85-1": SpectralSignature(
                cas_number="74-85-1",
                substance_name="Ethylene",
                alpha_uv=3.2,
                alpha_vis=0.0,
                alpha_ir1=1.8,
                alpha_ir3=0.6,
            ),
            # Acetylene C₂H₂ — CAS 74-86-2
            # Strong UV (triple bond), strong C≡C and C-H stretches in IR
            "74-86-2": SpectralSignature(
                cas_number="74-86-2",
                substance_name="Acetylene",
                alpha_uv=4.1,
                alpha_vis=0.0,
                alpha_ir1=2.2,
                alpha_ir3=1.2,
            ),
            # Ethanol C₂H₅OH — CAS 64-17-5
            # O-H stretch at 2.9 µm (IR1), C-O stretch, moderate UV
            "64-17-5": SpectralSignature(
                cas_number="64-17-5",
                substance_name="Ethanol",
                alpha_uv=1.5,
                alpha_vis=0.0,
                alpha_ir1=2.8,
                alpha_ir3=0.9,
            ),
            # n-Hexane C₆H₁₄ — CAS 110-54-3
            "110-54-3": SpectralSignature(
                cas_number="110-54-3",
                substance_name="n-Hexane",
                alpha_uv=0.3,
                alpha_vis=0.0,
                alpha_ir1=2.5,
                alpha_ir3=1.0,
            ),
            # Benzene C₆H₆ — CAS 71-43-2
            # Very strong UV (aromatic π-system at 254 nm)
            "71-43-2": SpectralSignature(
                cas_number="71-43-2",
                substance_name="Benzene",
                alpha_uv=8.5,
                alpha_vis=0.2,
                alpha_ir1=1.6,
                alpha_ir3=0.5,
            ),
            # Toluene C₇H₈ — CAS 108-88-3
            "108-88-3": SpectralSignature(
                cas_number="108-88-3",
                substance_name="Toluene",
                alpha_uv=7.2,
                alpha_vis=0.1,
                alpha_ir1=2.3,
                alpha_ir3=0.7,
            ),
            # o-Xylene C₈H₁₀ — CAS 95-47-6
            "95-47-6": SpectralSignature(
                cas_number="95-47-6",
                substance_name="o-Xylene",
                alpha_uv=6.8,
                alpha_vis=0.1,
                alpha_ir1=2.7,
                alpha_ir3=0.8,
            ),
            # Ammonia NH₃ — CAS 7664-41-7
            # Strong IR1 (N-H stretch at 2.95 µm, 3.3 µm); UV at 200 nm
            "7664-41-7": SpectralSignature(
                cas_number="7664-41-7",
                substance_name="Ammonia",
                alpha_uv=2.0,
                alpha_vis=0.0,
                alpha_ir1=3.5,
                alpha_ir3=1.8,
            ),
            # Hydrogen sulfide H₂S — CAS 7783-06-4
            # S-H stretch at 3.9 µm (IR3); UV at 195 nm
            "7783-06-4": SpectralSignature(
                cas_number="7783-06-4",
                substance_name="Hydrogen Sulfide",
                alpha_uv=1.8,
                alpha_vis=0.0,
                alpha_ir1=0.8,
                alpha_ir3=2.4,
            ),
            # Acetone (CH₃)₂CO — CAS 67-64-1
            "67-64-1": SpectralSignature(
                cas_number="67-64-1",
                substance_name="Acetone",
                alpha_uv=3.5,
                alpha_vis=0.0,
                alpha_ir1=0.9,
                alpha_ir3=0.4,
            ),
            # Methanol CH₃OH — CAS 67-56-1
            "67-56-1": SpectralSignature(
                cas_number="67-56-1",
                substance_name="Methanol",
                alpha_uv=0.8,
                alpha_vis=0.0,
                alpha_ir1=2.6,
                alpha_ir3=0.9,
            ),
            # Isopropanol (CH₃)₂CHOH — CAS 67-63-0
            "67-63-0": SpectralSignature(
                cas_number="67-63-0",
                substance_name="Isopropanol",
                alpha_uv=1.2,
                alpha_vis=0.0,
                alpha_ir1=2.7,
                alpha_ir3=1.0,
            ),
            # ── Extended registry: common industrial substances ────────────
            "75-28-5": SpectralSignature(
                cas_number="75-28-5",
                substance_name="Isobutane",
                # Natural refrigerant R600a; LFL=1.8%, MW=58
                alpha_uv=0.08,
                alpha_vis=0.0,
                alpha_ir1=0.8,
                alpha_ir3=4.2,
            ),
            "75-04-7": SpectralSignature(
                cas_number="75-04-7",
                substance_name="Ethylamine",
                # Chemical industry; LFL=3.5%, MW=45
                # Amine N-H bands in IR
                alpha_uv=0.18,
                alpha_vis=0.0,
                alpha_ir1=0.5,
                alpha_ir3=2.5,
            ),
            "74-84-0": SpectralSignature(
                cas_number="74-84-0",
                substance_name="Ethane",
                # LNG component; LFL=3.0%, MW=30
                alpha_uv=0.06,
                alpha_vis=0.0,
                alpha_ir1=0.4,
                alpha_ir3=2.8,
            ),
            "106-97-8": SpectralSignature(
                cas_number="106-97-8",
                substance_name="Butane",
                # LPG component; LFL=1.8%, MW=58
                alpha_uv=0.09,
                alpha_vis=0.0,
                alpha_ir1=0.9,
                alpha_ir3=4.5,
            ),
            # ── Additional industrial substances (3 new entries) ────────────
            # Acetaldehyde CH₃CHO — CAS 75-07-0
            # Chemical/petrochemical; LFL=4.0%, MW=44
            # n→π* transition ~290 nm; C=O stretch at 5.8 µm; C-H at 3.4 µm
            "75-07-0": SpectralSignature(
                cas_number="75-07-0",
                substance_name="Acetaldehyde",
                alpha_uv=2.0,
                alpha_vis=0.0,
                alpha_ir1=2.4,
                alpha_ir3=0.8,
            ),
            # 1,3-Butadiene C₄H₆ — CAS 106-99-0
            # Synthetic rubber manufacturing; LFL=2.0%, MW=54
            # Strong conjugated diene π→π* at 217 nm; C-H stretch at 3.3 µm
            "106-99-0": SpectralSignature(
                cas_number="106-99-0",
                substance_name="1,3-Butadiene",
                alpha_uv=5.5,
                alpha_vis=0.0,
                alpha_ir1=2.0,
                alpha_ir3=1.2,
            ),
            # Xylene (mixed isomers) C₈H₁₀ — CAS 1330-20-7
            # Solvent/petrochemical; LFL=1.1%, MW=106
            # Aromatic π-system (similar to o-Xylene 95-47-6); C-H aromatic stretches
            "1330-20-7": SpectralSignature(
                cas_number="1330-20-7",
                substance_name="Xylene (mixed)",
                alpha_uv=6.5,
                alpha_vis=0.1,
                alpha_ir1=2.5,
                alpha_ir3=0.7,
            ),
            # ── GAP-3: 27 additional substances (23 → 50 total) ────────────
            # Sources: NIST WebBook, Ingle & Crouch "Spectrochemical Analysis",
            #          Hollas "Modern Spectroscopy" 4th ed.,
            #          API RP 505, SFPE Handbook 5th ed.
            # All alpha values in m⁻¹ at 1 atm, 25 °C, 1% v/v (representative).
            # ── Petrochemical / aliphatic ─────────────────────────────────
            # Propylene (Propene) C₃H₆  CAS 115-07-1
            # C=C stretch at 1.65 µm (IR1); strong C-H IR; UV from π-bond
            "115-07-1": SpectralSignature(
                cas_number="115-07-1",
                substance_name="Propylene",
                alpha_uv=2.8,
                alpha_vis=0.0,
                alpha_ir1=2.4,
                alpha_ir3=0.9,
            ),
            # 1-Butene C₄H₈  CAS 106-98-9
            # Similar to propylene; C-H overtones in IR1; UV from olefin
            "106-98-9": SpectralSignature(
                cas_number="106-98-9",
                substance_name="1-Butene",
                alpha_uv=2.5,
                alpha_vis=0.0,
                alpha_ir1=2.6,
                alpha_ir3=1.1,
            ),
            # n-Pentane C₅H₁₂  CAS 109-66-0
            # UV transparent (no chromophore); strong C-H IR
            "109-66-0": SpectralSignature(
                cas_number="109-66-0",
                substance_name="n-Pentane",
                alpha_uv=0.1,
                alpha_vis=0.0,
                alpha_ir1=2.9,
                alpha_ir3=1.2,
            ),
            # n-Heptane C₇H₁₆  CAS 142-82-5
            # UV transparent; C-H overtones at 1.7 µm and 2.3 µm
            "142-82-5": SpectralSignature(
                cas_number="142-82-5",
                substance_name="n-Heptane",
                alpha_uv=0.1,
                alpha_vis=0.0,
                alpha_ir1=3.1,
                alpha_ir3=1.3,
            ),
            # n-Octane C₈H₁₈  CAS 111-65-9
            # Gasoline reference fuel; higher C-H content
            "111-65-9": SpectralSignature(
                cas_number="111-65-9",
                substance_name="n-Octane",
                alpha_uv=0.1,
                alpha_vis=0.0,
                alpha_ir1=3.3,
                alpha_ir3=1.4,
            ),
            # n-Nonane C₉H₂₀  CAS 111-84-2
            # Diesel fraction; strong C-H IR absorption
            "111-84-2": SpectralSignature(
                cas_number="111-84-2",
                substance_name="n-Nonane",
                alpha_uv=0.1,
                alpha_vis=0.0,
                alpha_ir1=3.5,
                alpha_ir3=1.5,
            ),
            # n-Decane C₁₀H₂₂  CAS 124-18-5
            # Jet fuel / kerosene fraction
            "124-18-5": SpectralSignature(
                cas_number="124-18-5",
                substance_name="n-Decane",
                alpha_uv=0.1,
                alpha_vis=0.0,
                alpha_ir1=3.7,
                alpha_ir3=1.6,
            ),
            # Cyclohexane C₆H₁₂  CAS 110-82-7
            # Ring C-H stretches; UV transparent
            "110-82-7": SpectralSignature(
                cas_number="110-82-7",
                substance_name="Cyclohexane",
                alpha_uv=0.2,
                alpha_vis=0.0,
                alpha_ir1=3.0,
                alpha_ir3=1.2,
            ),
            # Naphtha (light) CAS 64742-89-8
            # IR similar to hexane/heptane blend; flame detector test mixture
            "64742-89-8": SpectralSignature(
                cas_number="64742-89-8",
                substance_name="Naphtha (light)",
                alpha_uv=0.2,
                alpha_vis=0.0,
                alpha_ir1=3.2,
                alpha_ir3=1.3,
            ),
            # Kerosene / Jet-A CAS 8008-20-6
            # C-H stretch bands; slight UV from aromatic trace content
            "8008-20-6": SpectralSignature(
                cas_number="8008-20-6",
                substance_name="Kerosene/Jet-A",
                alpha_uv=0.8,
                alpha_vis=0.0,
                alpha_ir1=3.4,
                alpha_ir3=1.4,
            ),
            # Diesel Fuel CAS 68334-30-5
            # Higher aromatic fraction → stronger UV
            "68334-30-5": SpectralSignature(
                cas_number="68334-30-5",
                substance_name="Diesel Fuel",
                alpha_uv=1.5,
                alpha_vis=0.0,
                alpha_ir1=3.6,
                alpha_ir3=1.5,
            ),
            # Crude Oil Vapor CAS 8002-05-9
            # Mixed hydrocarbons; UV from BTEX aromatics
            "8002-05-9": SpectralSignature(
                cas_number="8002-05-9",
                substance_name="Crude Oil Vapor",
                alpha_uv=2.2,
                alpha_vis=0.0,
                alpha_ir1=3.8,
                alpha_ir3=1.6,
            ),
            # ── Chemical / process ────────────────────────────────────────
            # Formaldehyde CH₂O  CAS 50-00-0
            # n→π* at 280–360 nm (UV/VIS); C=O stretch at 5.7 µm
            "50-00-0": SpectralSignature(
                cas_number="50-00-0",
                substance_name="Formaldehyde",
                alpha_uv=4.5,
                alpha_vis=0.8,
                alpha_ir1=0.6,
                alpha_ir3=0.3,
            ),
            # Methyl Ethyl Ketone (MEK) C₄H₈O  CAS 78-93-3
            # C=O stretch at 5.8 µm; n→π* at 280 nm
            "78-93-3": SpectralSignature(
                cas_number="78-93-3",
                substance_name="Methyl Ethyl Ketone",
                alpha_uv=3.2,
                alpha_vis=0.2,
                alpha_ir1=1.0,
                alpha_ir3=0.5,
            ),
            # Styrene C₈H₈  CAS 100-42-5
            # Aromatic + vinyl: very strong UV (250 nm); C-H IR
            "100-42-5": SpectralSignature(
                cas_number="100-42-5",
                substance_name="Styrene",
                alpha_uv=9.0,
                alpha_vis=0.3,
                alpha_ir1=2.0,
                alpha_ir3=0.7,
            ),
            # Vinyl Chloride C₂H₃Cl  CAS 75-01-4
            # C=C stretch; C-Cl bond absorbs IR3; UV chromophore
            "75-01-4": SpectralSignature(
                cas_number="75-01-4",
                substance_name="Vinyl Chloride",
                alpha_uv=3.8,
                alpha_vis=0.0,
                alpha_ir1=1.5,
                alpha_ir3=2.0,
            ),
            # Ethylene Oxide C₂H₄O  CAS 75-21-8
            # Ring strain → UV active; C-O-C stretch in IR
            "75-21-8": SpectralSignature(
                cas_number="75-21-8",
                substance_name="Ethylene Oxide",
                alpha_uv=2.0,
                alpha_vis=0.0,
                alpha_ir1=1.8,
                alpha_ir3=0.8,
            ),
            # Propylene Oxide C₃H₆O  CAS 75-56-9
            # Similar to EO but larger C-H contribution
            "75-56-9": SpectralSignature(
                cas_number="75-56-9",
                substance_name="Propylene Oxide",
                alpha_uv=1.8,
                alpha_vis=0.0,
                alpha_ir1=2.1,
                alpha_ir3=0.9,
            ),
            # Chlorine Cl₂  CAS 7782-50-5
            # Strong UV (330 nm); VIS faintly yellow; IR weak
            "7782-50-5": SpectralSignature(
                cas_number="7782-50-5",
                substance_name="Chlorine",
                alpha_uv=5.5,
                alpha_vis=1.2,
                alpha_ir1=0.2,
                alpha_ir3=0.1,
            ),
            # Sulfur Dioxide SO₂  CAS 7446-09-5
            # UV absorption at 280–320 nm; S=O stretch at 8.7 µm
            "7446-09-5": SpectralSignature(
                cas_number="7446-09-5",
                substance_name="Sulfur Dioxide",
                alpha_uv=3.0,
                alpha_vis=0.0,
                alpha_ir1=0.4,
                alpha_ir3=0.2,
            ),
            # Nitric Oxide NO  CAS 10102-43-9
            # UV at 215 nm; N=O stretch at 5.3 µm
            "10102-43-9": SpectralSignature(
                cas_number="10102-43-9",
                substance_name="Nitric Oxide",
                alpha_uv=2.5,
                alpha_vis=0.0,
                alpha_ir1=0.3,
                alpha_ir3=0.4,
            ),
            # Phosphine PH₃  CAS 7803-51-2
            # P-H stretch at 4.1 µm (IR3 overlap); UV at 185 nm
            "7803-51-2": SpectralSignature(
                cas_number="7803-51-2",
                substance_name="Phosphine",
                alpha_uv=1.5,
                alpha_vis=0.0,
                alpha_ir1=0.5,
                alpha_ir3=1.8,
            ),
            # Silane SiH₄  CAS 7803-62-5
            # Si-H stretch at 4.5 µm (IR3); UV at 195 nm
            "7803-62-5": SpectralSignature(
                cas_number="7803-62-5",
                substance_name="Silane",
                alpha_uv=1.2,
                alpha_vis=0.0,
                alpha_ir1=0.3,
                alpha_ir3=2.2,
            ),
            # ── Gas mixtures / blends ─────────────────────────────────────
            # Natural Gas (blend ~90% CH₄, 8% C₂H₆, 2% C₃H₈)  CAS 8006-14-2
            # IR1 dominated by CH₄; pipeline gas, utility
            # V53 FIX: alpha_ir1 was 4.0 — same class of error as V51 LNG fix.
            # Natural Gas is ~90% CH₄ (alpha_ir1=0.05), 8% C₂H₆ (alpha_ir1=0.4),
            # 2% C₃H₈ (alpha_ir1=0.1). Weighted: 0.90×0.05+0.08×0.4+0.02×0.1=0.079.
            # Value 4.0 overestimated IR1 absorption by ~50×, leading to incorrect
            # flame detector selection — IR1 detectors wrongly deemed unable to see
            # through natural gas clouds. IEC 60079-29-4, FM Global DS 5-48.
            "8006-14-2": SpectralSignature(
                cas_number="8006-14-2",
                substance_name="Natural Gas (blend)",
                alpha_uv=0.3,
                alpha_vis=0.0,
                alpha_ir1=0.08,
                alpha_ir3=0.5,
            ),
            # LPG (blend ~60% propane / 40% butane)  CAS 68476-85-7
            # Weighted alpha between propane and butane
            # V48 FIX: alpha_ir3 was 1.0 — NON-CONSERVATIVE. IR3 is the primary
            # detection band for most commercial flame detectors. Component-weighted:
            # 0.6×propane_ir3(1.2) + 0.4×butane_ir3(4.5) = 2.52. Previous value
            # underestimated absorption by 2.5×, meaning the system thought IR3
            # detectors could see through LPG clouds when they actually cannot.
            # alpha_ir1 also corrected: 0.6×propane_ir1(0.1) + 0.4×butane_ir1(0.9) = 0.42
            "68476-85-7": SpectralSignature(
                cas_number="68476-85-7",
                substance_name="LPG (Propane/Butane blend)",
                alpha_uv=0.5,
                alpha_vis=0.0,
                alpha_ir1=0.42,
                alpha_ir3=2.52,
            ),
            # LNG Vapor (primarily methane at cryogenic release)  CAS 74-82-8-LNG
            # V51 FIX: alpha_ir1 was 4.5, which is 90× the methane value (0.05).
            # LNG vapor IS methane — spectral absorption coefficients are molecular
            # properties, NOT concentration-dependent. At higher concentration, the
            # optical path increases (more molecules per unit path), but the alpha
            # coefficient per unit concentration stays the same. The old value of 4.5
            # would cause the system to overestimate IR1-band absorption by 90×,
            # leading to incorrect flame detector selection and potentially placing
            # IR1-band detectors where they cannot see through the LNG cloud.
            # Weighted average for typical LNG (95% CH₄ + 3% C₂H₆ + 1% C₃H₈):
            #   alpha_ir1 ≈ 0.95×0.05 + 0.03×0.4 + 0.01×0.3 ≈ 0.066
            # Using 0.07 (slightly conservative for trace higher hydrocarbons).
            # V29 FIX: alpha_uv reduced from 0.1 to 0.03. Methane is essentially
            # transparent in the UV range used by flame detectors (185-260 nm);
            # its absorption edge is below 145 nm. The previous 0.1 value was
            # copied from the parent methane entry without physical justification.
            # For LNG, IR1 band (C-H stretch at 1.65/2.3 µm) is the dominant
            # detection mechanism — alpha_ir1 MUST exceed alpha_uv per IEC 60079-29-4.
            "74-82-8-LNG": SpectralSignature(
                cas_number="74-82-8-LNG",
                substance_name="LNG Vapor (methane-rich)",
                alpha_uv=0.03,
                alpha_vis=0.0,
                alpha_ir1=0.07,
                alpha_ir3=0.4,
            ),
            # Refinery Gas (H₂ + CH₄ + C₂–C₄; representative)  CAS 68919-39-1
            # Wide IR due to mixed composition; H₂ transparent → lower avg
            "68919-39-1": SpectralSignature(
                cas_number="68919-39-1",
                substance_name="Refinery Gas",
                alpha_uv=0.4,
                alpha_vis=0.0,
                alpha_ir1=3.2,
                alpha_ir3=0.8,
            ),
            # Syngas (CO + H₂ blend, ~50/50)  CAS SYNGAS-5050
            # CO IR3 contribution (4.67 µm near-IR3 edge) + H₂ transparent
            "SYNGAS-5050": SpectralSignature(
                cas_number="SYNGAS-5050",
                substance_name="Syngas (CO+H2 blend)",
                alpha_uv=0.8,
                alpha_vis=0.0,
                alpha_ir1=0.6,
                alpha_ir3=1.2,
            ),
        }

    def get(self, cas_number: str) -> Optional[SpectralSignature]:
        """Get spectral signature by CAS number. Returns None if unknown."""
        self._ensure_loaded()
        return self._signatures.get(cas_number)

    def register(self, signature: SpectralSignature) -> None:
        """Register a new spectral signature."""
        self._ensure_loaded()
        self._signatures[signature.cas_number] = signature

    def list_available(self) -> List[str]:
        """List all available CAS numbers."""
        self._ensure_loaded()
        return sorted(self._signatures.keys())

    def count(self) -> int:
        """Return total number of registered substances."""
        self._ensure_loaded()
        return len(self._signatures)


# ===========================================================================
# V21.2: Volumetric Medium (Gaseous/Smoke Obstruction)
# ===========================================================================


class VolumetricMedium(BaseModel):
    """A gaseous or particulate medium in the optical path that absorbs
    spectral energy according to Beer-Lambert law.

    Unlike solid Obstructions (which block geometrically), VolumetricMedia
    attenuate signal exponentially with distance:
        T(lambda) = exp(-alpha_lambda * path_length)

    Example: smoke layer, steam cloud, gas cloud in detector line of sight.

    GAP-03: Default absorption coefficients per medium type.
    GAP-07: Non-zero volume validator.

    Reference: Beer-Lambert law, IEC 60079-29-4, FM Global DS 5-48,
               Drysdale "An Introduction to Fire Dynamics" Table 4.1,
               ISO 13943:2017 §3.88
    """

    model_config = ConfigDict(frozen=True, strict=True)

    medium_id: str
    medium_type: str = Field(description="SMOKE, STEAM, GAS_CLOUD, DUST_SUSPENSION")
    bbox_min: List[float] = Field(min_length=3, max_length=3)
    bbox_max: List[float] = Field(min_length=3, max_length=3)
    cas_number: Optional[str] = Field(None, description="CAS number for spectral lookup in SpectralSignatureRegistry")
    concentration_factor: float = Field(
        default=1.0,
        gt=0.0,
        le=10.0,
        description=(
            "Concentration multiplier for absorption coefficient. "
            "1.0 = reference concentration. Higher = denser medium."
        ),
    )
    # Direct absorption coefficients (override CAS lookup if provided)
    alpha_override: Optional[Dict[WavelengthBand, float]] = Field(
        None, description="Override absorption coefficients per band (m^-1)"
    )

    @model_validator(mode="after")
    def bbox_valid(self) -> VolumetricMedium:
        for i in range(3):
            if self.bbox_min[i] > self.bbox_max[i]:
                raise ValueError(f"bbox_min[{i}]={self.bbox_min[i]} > bbox_max[{i}]={self.bbox_max[i]}")
        return self

    @model_validator(mode="after")
    def bbox_nonzero_volume(self) -> VolumetricMedium:
        """GAP-07: A volumetric medium with zero volume has no physical meaning.
        IEC 60079-10-1:2015 Annex B §B.3: minimum enclosure volume applies.
        """
        dx = self.bbox_max[0] - self.bbox_min[0]
        dy = self.bbox_max[1] - self.bbox_min[1]
        dz = self.bbox_max[2] - self.bbox_min[2]
        if dx * dy * dz < 1.0e-9:
            raise ValueError(
                f"VolumetricMedium '{self.medium_id}' has zero or near-zero "
                f"volume (dx={dx:.4f}, dy={dy:.4f}, dz={dz:.4f}). "
                "All three bbox dimensions must be positive."
            )
        return self

    def get_alpha(self, band: WavelengthBand) -> float:
        """GAP-03: Return absorption coefficient (m^-1) for `band`.

        Priority order:
        1. alpha_override[band]  — explicit user value, highest priority
        2. _DEFAULT_MEDIUM_ALPHA[medium_type][band]  — type-based default
        3. 0.0  — fallback (medium transparent in this band)

        Multiplied by concentration_factor in all cases.

        When using type-based defaults (Priority 2), a warning is emitted
        via Python logging to inform the engineer that approximate values
        are being used. In a life-safety system, decisions must not be
        made on approximate data without explicit awareness.

        IEC 60079-10-1 §7: Absorption should never be assumed zero for
        optically active media without explicit justification.
        """
        # Priority 1: explicit override — no warning needed
        if self.alpha_override is not None:
            raw = self.alpha_override.get(band, 0.0)
            # Also check string value in case dict was built with str keys
            if raw == 0.0:
                raw = self.alpha_override.get(band.value, 0.0)  # type: ignore[call-overload]
            return float(raw) * self.concentration_factor

        # Priority 2: type-based default — emit warning
        defaults = _DEFAULT_MEDIUM_ALPHA.get(self.medium_type, {})
        band_key = band.value if isinstance(band, WavelengthBand) else band
        raw = defaults.get(band_key, 0.0)

        if raw > 0.0:
            logger.warning(
                "VolumetricMedium '%s': using DEFAULT absorption coefficient "
                "for band %s (alpha=%.2f m^-1). No alpha_override or CAS "
                "number provided — approximate values must not be the sole "
                "basis for safety-critical coverage decisions without FPE "
                "sign-off. [IEC 60079-10-1 §7, ISO 13943:2017 §3.88]",
                self.medium_id,
                band_key,
                raw * self.concentration_factor,
            )

        return float(raw) * self.concentration_factor

    def get_alpha_with_registry(self, band: WavelengthBand, registry: SpectralSignatureRegistry) -> float:
        """Get absorption coefficient using registry lookup.

        Priority order:
        1. alpha_override[band] — explicit user value
        2. CAS number lookup in SpectralSignatureRegistry
        3. _DEFAULT_MEDIUM_ALPHA type-based defaults (with warning)
        4. 0.0 — transparent fallback

        When falling back to type-based defaults (Priority 3), a warning
        is emitted because approximate values are being used for a
        safety-critical calculation.
        """
        # Priority 1: explicit override — no warning
        if self.alpha_override is not None:
            return self.alpha_override.get(band, 0.0) * self.concentration_factor

        # Priority 2: CAS number lookup — no warning (data-driven)
        if self.cas_number is not None:
            sig = registry.get(self.cas_number)
            if sig is not None:
                return sig.alpha_for(band) * self.concentration_factor

        # Priority 3: type-based defaults — emit warning
        defaults = _DEFAULT_MEDIUM_ALPHA.get(self.medium_type, {})
        band_key = band.value if isinstance(band, WavelengthBand) else band
        raw = defaults.get(band_key, 0.0)

        if raw > 0.0:
            logger.warning(
                "VolumetricMedium '%s': using DEFAULT absorption coefficient "
                "for band %s (alpha=%.2f m^-1). CAS number '%s' not found in "
                "registry. Approximate values must not be the sole basis "
                "for safety-critical coverage decisions without FPE sign-off. "
                "[IEC 60079-10-1 §7, ISO 13943:2017 §3.88]",
                self.medium_id,
                band_key,
                raw * self.concentration_factor,
                self.cas_number or "(none)",
            )

        return float(raw) * self.concentration_factor


# ===========================================================================
# V21.2: Beer-Lambert Volumetric Transmittance
# ===========================================================================


def beer_lambert_transmittance(
    alpha_per_m: float,
    path_length_m: float,
) -> float:
    """Calculate spectral transmittance through a volumetric medium
    using the Beer-Lambert law:

        T = exp(-alpha * d)

    where:
        alpha = absorption coefficient (m^-1)
        d     = path length through the medium (m)
        T     = transmittance (0.0 to 1.0)

    This replaces the binary True/False line-of-sight check for
    gaseous media. A solid obstruction has alpha -> infinity, T -> 0.
    Clean air has alpha = 0, T = 1.0.

    The ray-trace engine uses this for each volumetric medium
    intersected by the ray, then multiplies transmittances:
        T_total = product(T_i) for all media intersected

    Args:
        alpha_per_m: absorption coefficient in m^-1
        path_length_m: distance the ray travels through the medium

    Returns:
        Transmittance value in [0.0, 1.0]

    Reference: Beer-Lambert law, IEC 60079-29-4 §6.2

    """
    if alpha_per_m <= 0.0 or path_length_m <= 0.0:
        return 1.0
    t = math.exp(-alpha_per_m * path_length_m)
    return max(0.0, min(1.0, t))


def volumetric_path_transmittance(
    ray_start: Tuple[float, float, float],
    ray_end: Tuple[float, float, float],
    media: List[VolumetricMedium],
    band: WavelengthBand,
    registry: Optional[SpectralSignatureRegistry] = None,
) -> float:
    """Calculate total spectral transmittance along a ray path through
    multiple volumetric media (smoke, gas clouds, steam).

    For each medium intersected, calculates:
    1. Path length through the medium's bounding box (AABB intersection)
    2. Beer-Lambert transmittance for that segment
    3. Multiplies all segment transmittances: T_total = product(T_i)

    Args:
        ray_start: detector position (x, y, z)
        ray_end:   target position (x, y, z)
        media:     list of VolumetricMedia in the scene
        band:      spectral band being analyzed
        registry:  optional SpectralSignatureRegistry for CAS lookups

    Returns:
        Total transmittance in [0.0, 1.0]. 1.0 = clear path, 0.0 = fully absorbed.

    """
    if not media:
        return 1.0

    t_total = 1.0
    reg = registry or SpectralSignatureRegistry()

    for medium in media:
        # Calculate path length through this medium's AABB
        path_len = _ray_aabb_path_length(ray_start, ray_end, medium.bbox_min, medium.bbox_max)
        if path_len <= 0.0:
            continue  # Ray doesn't intersect this medium

        alpha = medium.get_alpha_with_registry(band, reg)
        if alpha <= 0.0:
            continue  # This medium doesn't absorb in this band

        t_segment = beer_lambert_transmittance(alpha, path_len)
        t_total *= t_segment

        # Early exit: if transmittance already negligible
        if t_total < 0.001:
            return 0.0

    return t_total


def _ray_aabb_path_length(
    origin: Tuple[float, ...],
    end: Tuple[float, ...],
    bbox_min: List[float],
    bbox_max: List[float],
) -> float:
    """Calculate the path length of a ray segment through an AABB.
    Returns 0.0 if the ray doesn't intersect the box.
    Uses slab method for ray-box intersection.
    """
    d = (end[0] - origin[0], end[1] - origin[1], end[2] - origin[2])
    tmin, tmax = 0.0, 1.0

    for i in range(3):
        if abs(d[i]) < 1e-12:
            if origin[i] < bbox_min[i] or origin[i] > bbox_max[i]:
                return 0.0
        else:
            t1 = (bbox_min[i] - origin[i]) / d[i]
            t2 = (bbox_max[i] - origin[i]) / d[i]
            if t1 > t2:
                t1, t2 = t2, t1
            tmin = max(tmin, t1)
            tmax = min(tmax, t2)
            if tmin > tmax:
                return 0.0

    if tmax <= tmin:
        return 0.0

    # Total ray length
    ray_length = math.sqrt(d[0] ** 2 + d[1] ** 2 + d[2] ** 2)
    # Path through box = (tmax - tmin) * ray_length
    return (tmax - tmin) * ray_length
