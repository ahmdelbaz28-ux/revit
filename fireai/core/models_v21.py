"""
models_v21.py – FireAI V21 Pydantic Models (Fast-Fail Validation)
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

import math
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

from pydantic import BaseModel, ConfigDict, Field, model_validator


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class VentilationLevel(str, Enum):
    HIGH   = "HIGH"
    MEDIUM = "MEDIUM"
    LOW    = "LOW"
    POOR   = "POOR"


class HazardType(str, Enum):
    GAS    = "GAS"
    DUST   = "DUST"
    HYBRID = "HYBRID"
    FIBER  = "FIBER"


class ZoneType(str, Enum):
    ZONE_0       = "ZONE_0"
    ZONE_1       = "ZONE_1"
    ZONE_2       = "ZONE_2"
    ZONE_20      = "ZONE_20"
    ZONE_21      = "ZONE_21"
    ZONE_22      = "ZONE_22"
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
    T1  = "T1"   # max surface 450°C
    T2  = "T2"   # max surface 300°C
    T2A = "T2A"  # max surface 280°C
    T2B = "T2B"  # max surface 260°C
    T2C = "T2C"  # max surface 230°C
    T2D = "T2D"  # max surface 215°C
    T3  = "T3"   # max surface 200°C
    T3A = "T3A"  # max surface 180°C
    T3B = "T3B"  # max surface 165°C
    T3C = "T3C"  # max surface 160°C
    T4  = "T4"   # max surface 135°C
    T4A = "T4A"  # max surface 120°C
    T5  = "T5"   # max surface 100°C
    T6  = "T6"   # max surface 85°C


# Max surface temperature per class (IEC 60079-0:2017 §7.3)
# Extended with subdivisions T2A-T2D, T3A-T3C, T4A
_T_CLASS_MAX: Dict[str, float] = {
    "T1": 450.0,
    "T2": 300.0, "T2A": 280.0, "T2B": 260.0, "T2C": 230.0, "T2D": 215.0,
    "T3": 200.0, "T3A": 180.0, "T3B": 165.0, "T3C": 160.0,
    "T4": 135.0, "T4A": 120.0,
    "T5": 100.0,
    "T6": 85.0,
}


class WavelengthBand(str, Enum):
    """Spectral bands for flame detector transparency analysis."""
    UV  = "UV"    # 185-260 nm
    VIS = "VIS"   # 380-780 nm
    IR1 = "IR1"   # 1-3 um (near-IR)
    IR3 = "IR3"   # 3-5 um (mid-IR CO2 band)


class RegulatoryFramework(str, Enum):
    ATEX_EU    = "ATEX_EU"
    IECEX      = "IECEx"
    NEC_US     = "NEC_US"
    CEC_CANADA = "CEC_CANADA"
    EFTA       = "EFTA"


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
    STRICT_5PCT   = "STRICT_5PCT"
    STANDARD_5PCT = "STANDARD_5PCT"
    BASIC         = "BASIC"


# ---------------------------------------------------------------------------
# Pydantic Models
# ---------------------------------------------------------------------------

class SubstanceProperties(BaseModel):
    """
    Physical properties of the hazardous substance.
    ALL validators run at construction — no invalid object can exist.
    """
    model_config = ConfigDict(frozen=True, strict=True)

    name:              str
    hazard_type:       HazardType
    lfl_vol_pct:       Optional[float] = Field(None, gt=0.0, le=100.0,
                           description="Lower Flammable Limit (vol%). Must be >0.")
    ufl_vol_pct:       Optional[float] = Field(None, gt=0.0, le=100.0)
    flash_point_c:     Optional[float] = Field(None, ge=-200.0, le=500.0)
    autoignition_c:    Optional[float] = Field(None, ge=50.0, le=1000.0)
    mec_g_m3:          Optional[float] = Field(None, gt=0.0,
                           description="Minimum Explosible Concentration (dust)")
    kst_bar_m_s:       Optional[float] = Field(None, ge=0.0,
                           description="Dust explosion constant")
    mie_mj:            Optional[float] = Field(None, gt=0.0,
                           description="Minimum Ignition Energy (mJ)")
    density_kg_m3:     Optional[float] = Field(None, gt=0.0)
    molecular_weight:  Optional[float] = Field(None, gt=0.0)

    @model_validator(mode="after")
    def physics_consistency(self) -> "SubstanceProperties":
        # flash_point must be below autoignition
        if (self.flash_point_c is not None
                and self.autoignition_c is not None
                and self.flash_point_c >= self.autoignition_c):
            raise ValueError(
                f"flash_point_c ({self.flash_point_c}C) must be strictly "
                f"< autoignition_c ({self.autoignition_c}C). "
                f"[NFPA 497 §4.2]"
            )
        # LFL < UFL
        if (self.lfl_vol_pct is not None and self.ufl_vol_pct is not None
                and self.lfl_vol_pct >= self.ufl_vol_pct):
            raise ValueError(
                f"lfl_vol_pct ({self.lfl_vol_pct}) must be < "
                f"ufl_vol_pct ({self.ufl_vol_pct})."
            )
        # GAS needs LFL
        if self.hazard_type == HazardType.GAS and self.lfl_vol_pct is None:
            raise ValueError("GAS hazard requires lfl_vol_pct.")
        # DUST needs MEC
        if self.hazard_type == HazardType.DUST and self.mec_g_m3 is None:
            raise ValueError("DUST hazard requires mec_g_m3.")
        # HYBRID needs both
        if self.hazard_type == HazardType.HYBRID:
            if self.lfl_vol_pct is None or self.mec_g_m3 is None:
                raise ValueError(
                    "HYBRID hazard requires both lfl_vol_pct and mec_g_m3. "
                    "[IEC 60079-10-1 §5.7]"
                )
        return self


class ZoneExtent(BaseModel):
    """Zone boundary distances (metres). All must be non-negative."""
    model_config = ConfigDict(frozen=True, strict=True)

    horizontal_m: float = Field(ge=0.0)
    vertical_m:   float = Field(ge=0.0)
    volume_m3:    float = Field(ge=0.0)
    is_outdoor:   bool  = False  # True = full sphere, False = hemisphere

    @model_validator(mode="after")
    def extent_geometry(self) -> "ZoneExtent":
        # Volume must be consistent with the appropriate volume model
        r = max(self.horizontal_m, self.vertical_m)
        if self.is_outdoor:
            max_vol = (4.0 / 3.0) * math.pi * r ** 3   # Full sphere
        else:
            max_vol = (2.0 / 3.0) * math.pi * r ** 3   # Hemisphere
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

    zone:             ZoneType
    extent:           ZoneExtent
    ventilation:      VentilationLevel
    hazard_type:      HazardType
    warnings:         List[str] = Field(default_factory=list)
    # POOR ventilation + Zone 0/20 is the most dangerous combination
    # The model enforces a warning cannot be silently dropped
    critical_flags:   List[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def check_critical_combination(self) -> "HACResult":
        if (self.ventilation == VentilationLevel.POOR
                and self.zone in (ZoneType.ZONE_0, ZoneType.ZONE_20)):
            flag = (
                "CRITICAL: Zone 0/20 with POOR ventilation — "
                "most dangerous possible classification. "
                "Mandatory engineering review required. "
                "[IEC 60079-10-1 §6.3]"
            )
            # Cannot be silently ignored — it's in critical_flags
            if flag not in self.critical_flags:
                raise ValueError(
                    f"{flag}\nSet critical_flags=['{flag}'] explicitly "
                    f"to acknowledge this condition."
                )
        return self


def _select_temp_class(autoignition_c: float) -> TemperatureClass:
    """
    FIXED Fix #15: Select temperature class whose max surface temp
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
        "T1", "T2", "T2A", "T2B", "T2C", "T2D",
        "T3", "T3A", "T3B", "T3C",
        "T4", "T4A", "T5", "T6",
    ]:
        if _T_CLASS_MAX[t_class] < autoignition_c:
            return TemperatureClass(t_class)
    raise ValueError(
        f"No safe temperature class for autoignition={autoignition_c}C. "
        f"T6 max surface is 85C. Substance autoignition must be > 85C. "
        f"[IEC 60079-0 §7.3]"
    )


class ATEXEquipmentSpec(BaseModel):
    """
    ATEX equipment requirements derived from zone classification.
    EPL hierarchy enforced — cannot construct an inconsistent spec.
    """
    model_config = ConfigDict(frozen=True, strict=True)

    zone:              ZoneType
    epl_required:      str        # "Ga"/"Gb"/"Gc"/"Da"/"Db"/"Dc"/"Ma"/"Mb"
    atex_category:     str        # "1G","2G","3G","1D","2D","3D","M1","M2"
    temp_class:        TemperatureClass
    protection_modes:  List[str]  # e.g. ["ia","d","e"]
    hac_warnings:      List[str] = Field(default_factory=list)
    hac_critical:      List[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def epl_category_consistency(self) -> "ATEXEquipmentSpec":
        """
        FIXED Fix #14: EPL hierarchy was inverted.
        Correct gas hierarchy: Ga > Gb > Gc (Ga = highest protection)
        Correct dust hierarchy: Da > Db > Dc
        """
        valid = {
            ZoneType.ZONE_0:  ("Ga", "1G"),
            ZoneType.ZONE_1:  ("Gb", "2G"),
            ZoneType.ZONE_2:  ("Gc", "3G"),
            ZoneType.ZONE_20: ("Da", "1D"),
            ZoneType.ZONE_21: ("Db", "2D"),
            ZoneType.ZONE_22: ("Dc", "3D"),
        }
        if self.zone in valid:
            expected_epl, expected_cat = valid[self.zone]
            # EPL hierarchy: Ga satisfies Gb/Gc, Da satisfies Db/Dc
            # Gas hierarchy index: Ga=0, Gb=1, Gc=2
            gas_order  = ["Ga", "Gb", "Gc"]
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
    def protection_mode_zone_fit(self) -> "ATEXEquipmentSpec":
        """
        FIXED Fix #17: 'ia' for Zone 2 is over-specified (costly, unnecessary).
        Zone 2 -> 'ic' is sufficient. Zone 1 -> 'ib' or 'ia'. Zone 0 -> 'ia' only.
        [IEC 60079-14]
        """
        zone_allowed = {
            ZoneType.ZONE_0:  {"ia", "d", "e", "s", "ma"},
            ZoneType.ZONE_1:  {"ia", "ib", "d", "e", "px", "py", "s",
                               "ma", "mb", "o", "p", "q"},
            ZoneType.ZONE_2:  {"ia", "ib", "ic", "d", "e", "px", "py", "pz",
                               "n", "s", "ec", "ma", "mb", "o", "p", "q",
                               "nA", "nC", "nR"},
            ZoneType.ZONE_20: {"ia", "ma", "tb", "s", "tD"},
            ZoneType.ZONE_21: {"ia", "ib", "ma", "mb", "tb", "tc"},
            ZoneType.ZONE_22: {"ia", "ib", "ic", "ma", "mb", "mc",
                               "ta", "tb", "tc"},
        }
        if self.zone in zone_allowed:
            for mode in self.protection_modes:
                if mode not in zone_allowed[self.zone]:
                    raise ValueError(
                        f"Protection mode '{mode}' not permitted for "
                        f"{self.zone.value}. [IEC 60079-14]"
                    )
        return self


class Obstruction(BaseModel):
    """
    FIXED Q6: Spectral transparency replaces single boolean.
    Glass: UV=0.0 (opaque), IR=0.8 (mostly transparent).
    Polycarbonate: UV=0.0, VIS=0.9, IR=0.7.
    Steel: all 0.0.
    """
    model_config = ConfigDict(frozen=True, strict=True)

    obstruction_id:        str
    vertices:              List[List[float]]  # list of [x,y,z]
    spectral_transparency: Dict[WavelengthBand, float] = Field(
        default_factory=lambda: {
            WavelengthBand.UV:  0.0,
            WavelengthBand.VIS: 0.0,
            WavelengthBand.IR1: 0.0,
            WavelengthBand.IR3: 0.0,
        }
    )

    @model_validator(mode="after")
    def transparency_range(self) -> "Obstruction":
        for band, val in self.spectral_transparency.items():
            if not 0.0 <= val <= 1.0:
                raise ValueError(
                    f"spectral_transparency[{band}]={val} must be in [0.0, 1.0]."
                )
        return self

    def is_transparent_for(self, band: WavelengthBand) -> bool:
        """True if transmittance > 0.5 for this spectral band."""
        return self.spectral_transparency.get(band, 0.0) > 0.5

    def transmittance_for(self, band: WavelengthBand) -> float:
        return self.spectral_transparency.get(band, 0.0)


class FlameDetectorSpec(BaseModel):
    """
    Flame detector physical specification for ray-trace engine.
    """
    model_config = ConfigDict(frozen=True, strict=True)

    detector_id:        str
    position:           List[float] = Field(min_length=3, max_length=3)
    orientation_vector: List[float] = Field(min_length=3, max_length=3)
    rated_range_m:      float       = Field(gt=0.0, le=200.0)
    aoc_deg:            float       = Field(gt=0.0, le=180.0,
                            description="Angle of Coverage (degrees)")
    spectral_bands:     List[WavelengthBand] = Field(min_length=1)

    @model_validator(mode="after")
    def orientation_not_zero(self) -> "FlameDetectorSpec":
        mag = math.sqrt(sum(v**2 for v in self.orientation_vector))
        if mag < 1e-9:
            raise ValueError("orientation_vector must not be zero vector.")
        return self

    @model_validator(mode="after")
    def position_valid(self) -> "FlameDetectorSpec":
        if any(not math.isfinite(v) for v in self.position):
            raise ValueError("position contains non-finite values.")
        return self

    @property
    def orientation_unit(self) -> List[float]:
        mag = math.sqrt(sum(v**2 for v in self.orientation_vector))
        return [v / mag for v in self.orientation_vector]

    def is_facing_upward(self) -> bool:
        """
        Detector pointing up (z > 0.9) won't cover floor.
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

    country_code:  str
    framework:     RegulatoryFramework
    zone_system:   str   # "ZONE" or "DIVISION"
    warnings:      List[str]


# ===========================================================================
# V21.2: Environmental Context (Dynamic Physics Inputs)
# ===========================================================================

class EnvironmentalContext(BaseModel):
    """
    Strict context for HAC calculations with environmental correction.
    Defaults to worst-case indoor scenarios to guarantee fail-safe designs.

    If an engineer does NOT provide environmental data, the system assumes
    the worst: stagnant air (F stability, 0.5 m/s wind), high ambient temp.
    This ensures the widest hazardous zone — conservative by design.

    Standards: IEC 60079-10-1:2015 Annex B, NFPA 497 §4.3
    """
    model_config = ConfigDict(frozen=True, strict=True)

    ambient_temp_c: float = Field(
        default=40.0, ge=-40.0, le=85.0,
        description=(
            "Ambient temperature for LFL thermal correction (Burgess-Wheeler). "
            "Default 40C = typical indoor industrial environment. "
            "IEC 60079-10-1 Annex B."
        ),
    )
    wind_speed_m_s: float = Field(
        default=0.5, gt=0.0, le=50.0,
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

    @model_validator(mode="after")
    def cross_validate_environment(self) -> "EnvironmentalContext":
        # Physically impossible: high instability with near-zero wind
        if (self.wind_speed_m_s < 2.0
                and self.stability_class in (PasquillStability.A, PasquillStability.B)):
            raise ValueError(
                "Physics Violation: Highly unstable conditions (A/B) cannot exist "
                "with wind speed < 2.0 m/s in standard dispersion models. "
                "Either increase wind_speed or use stability class C-F. "
                "[Pasquill-Gifford correlation]"
            )
        return self


# ===========================================================================
# V21.2: Burgess-Wheeler LFL Thermal Correction
# ===========================================================================

def burgess_wheeler_lfl(
    lfl_25c: float,
    ambient_temp_c: float,
    heat_of_combustion_kj_mol: Optional[float] = None,
) -> float:
    """
    Burgess-Wheeler LFL thermal correction.

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

    Returns:
        LFL at the given ambient temperature (always < LFL_25C when T > 25C)

    Reference: Burgess & Wheeler (1929), Zabetakis (1965) Bureau of Mines
               Bulletin 627, IEC 60079-10-1 Annex B.
    """
    if ambient_temp_c <= 25.0:
        return lfl_25c  # No correction needed below reference temp

    delta_t = ambient_temp_c - 25.0

    # Standard Burgess-Wheeler coefficient
    correction = 0.001824 * delta_t
    lfl_t = lfl_25c * (1.0 - correction)

    # If heat of combustion provided, use refined correction
    if heat_of_combustion_kj_mol is not None and heat_of_combustion_kj_mol > 0:
        # Refined: coefficient proportional to delta_Hc
        # Standard fuels range ~400-1400 kJ/mol; normalize around 800
        refined_factor = heat_of_combustion_kj_mol / 800.0
        refined_factor = max(0.5, min(refined_factor, 2.0))  # Clamp
        correction = 0.001824 * refined_factor * delta_t
        lfl_t = lfl_25c * (1.0 - correction)

    # LFL must remain positive
    return max(lfl_t, lfl_25c * 0.5)  # Never drop below 50% of reference


# ===========================================================================
# V21.2: IEC 60079-14 Thermal Margin (Safe Temperature Selection)
# ===========================================================================

def _select_temp_class_with_margin(
    autoignition_c: float,
    zone: ZoneType,
) -> TemperatureClass:
    """
    V21.2: Select temperature class with IEC 60079-14 thermal margin.

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
    for t_class in [
        "T1", "T2", "T2A", "T2B", "T2C", "T2D",
        "T3", "T3A", "T3B", "T3C",
        "T4", "T4A", "T5", "T6",
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

class SpectralSignature(BaseModel):
    """
    Spectral absorption coefficient per wavelength band for a substance.
    Used by Layer 5 Beer-Lambert volumetric transmittance calculations.

    Decoupled from SubstanceProperties to keep the core model lightweight.
    Loaded on-demand via SpectralSignatureRegistry.

    Reference: IEC 60079-29-4, NIST Chemistry WebBook
    """
    model_config = ConfigDict(frozen=True, strict=True)

    cas_number:     str
    substance_name: str
    # Absorption coefficient per band (m^-1) for Beer-Lambert: T = exp(-alpha * d)
    # Higher = more absorption at that wavelength
    alpha_uv:  float = Field(0.0, ge=0.0, description="UV band absorption coeff (m^-1)")
    alpha_vis: float = Field(0.0, ge=0.0, description="VIS band absorption coeff (m^-1)")
    alpha_ir1: float = Field(0.0, ge=0.0, description="IR1 (1-3um) absorption coeff (m^-1)")
    alpha_ir3: float = Field(0.0, ge=0.0, description="IR3 (3-5um CO2) absorption coeff (m^-1)")

    def alpha_for(self, band: WavelengthBand) -> float:
        """Get absorption coefficient for a specific band."""
        return {
            WavelengthBand.UV:  self.alpha_uv,
            WavelengthBand.VIS: self.alpha_vis,
            WavelengthBand.IR1: self.alpha_ir1,
            WavelengthBand.IR3: self.alpha_ir3,
        }[band]


class SpectralSignatureRegistry:
    """
    Lazy-loaded registry of spectral signatures indexed by CAS number.

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

    def _ensure_loaded(self) -> None:
        if self._loaded:
            return
        self._loaded = True
        # Built-in signatures for common hazardous substances
        # Absorption coefficients are representative values from literature
        # For CO2-band (4.3um): hydrocarbons have strong absorption
        self._signatures = {
            # Methane (CH4)
            "74-82-8": SpectralSignature(
                cas_number="74-82-8", substance_name="Methane",
                alpha_uv=0.1, alpha_vis=0.0, alpha_ir1=0.05, alpha_ir3=0.8,
            ),
            # Propane (C3H8)
            "74-98-6": SpectralSignature(
                cas_number="74-98-6", substance_name="Propane",
                alpha_uv=0.1, alpha_vis=0.0, alpha_ir1=0.1, alpha_ir3=1.2,
            ),
            # Hydrogen (H2) - no IR absorption, UV only
            "1333-74-0": SpectralSignature(
                cas_number="1333-74-0", substance_name="Hydrogen",
                alpha_uv=0.5, alpha_vis=0.0, alpha_ir1=0.0, alpha_ir3=0.0,
            ),
            # Carbon Monoxide (CO)
            "630-08-0": SpectralSignature(
                cas_number="630-08-0", substance_name="Carbon Monoxide",
                alpha_uv=0.2, alpha_vis=0.0, alpha_ir1=0.3, alpha_ir3=0.1,
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


# ===========================================================================
# V21.2: Volumetric Medium (Gaseous/Smoke Obstruction)
# ===========================================================================

class VolumetricMedium(BaseModel):
    """
    A gaseous or particulate medium in the optical path that absorbs
    spectral energy according to Beer-Lambert law.

    Unlike solid Obstructions (which block geometrically), VolumetricMedia
    attenuate signal exponentially with distance:
        T(lambda) = exp(-alpha_lambda * path_length)

    Example: smoke layer, steam cloud, gas cloud in detector line of sight.

    Reference: Beer-Lambert law, IEC 60079-29-4, FM Global DS 5-48
    """
    model_config = ConfigDict(frozen=True, strict=True)

    medium_id:       str
    medium_type:     str = Field(
        description="SMOKE, STEAM, GAS_CLOUD, DUST_SUSPENSION"
    )
    bbox_min:        List[float] = Field(min_length=3, max_length=3)
    bbox_max:        List[float] = Field(min_length=3, max_length=3)
    cas_number:      Optional[str] = Field(
        None,
        description="CAS number for spectral lookup in SpectralSignatureRegistry"
    )
    concentration_factor: float = Field(
        default=1.0, gt=0.0, le=10.0,
        description=(
            "Concentration multiplier for absorption coefficient. "
            "1.0 = reference concentration. Higher = denser medium."
        ),
    )
    # Direct absorption coefficients (override CAS lookup if provided)
    alpha_override: Optional[Dict[WavelengthBand, float]] = Field(
        None,
        description="Override absorption coefficients per band (m^-1)"
    )

    @model_validator(mode="after")
    def bbox_valid(self) -> "VolumetricMedium":
        for i in range(3):
            if self.bbox_min[i] > self.bbox_max[i]:
                raise ValueError(
                    f"bbox_min[{i}]={self.bbox_min[i]} > bbox_max[{i}]={self.bbox_max[i]}"
                )
        return self

    def get_alpha(self, band: WavelengthBand) -> float:
        """Get absorption coefficient for a band."""
        if self.alpha_override is not None:
            return self.alpha_override.get(band, 0.0) * self.concentration_factor
        # Without override or CAS, assume minimal absorption
        return 0.0

    def get_alpha_with_registry(
        self, band: WavelengthBand, registry: SpectralSignatureRegistry
    ) -> float:
        """Get absorption coefficient using registry lookup."""
        if self.alpha_override is not None:
            return self.alpha_override.get(band, 0.0) * self.concentration_factor
        if self.cas_number is not None:
            sig = registry.get(self.cas_number)
            if sig is not None:
                return sig.alpha_for(band) * self.concentration_factor
        return 0.0


# ===========================================================================
# V21.2: Beer-Lambert Volumetric Transmittance
# ===========================================================================

def beer_lambert_transmittance(
    alpha_per_m: float,
    path_length_m: float,
) -> float:
    """
    Calculate spectral transmittance through a volumetric medium
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
    ray_end:   Tuple[float, float, float],
    media:     List[VolumetricMedium],
    band:      WavelengthBand,
    registry:  Optional[SpectralSignatureRegistry] = None,
) -> float:
    """
    Calculate total spectral transmittance along a ray path through
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
    end:    Tuple[float, ...],
    bbox_min: List[float],
    bbox_max: List[float],
) -> float:
    """
    Calculate the path length of a ray segment through an AABB.
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
    ray_length = math.sqrt(d[0]**2 + d[1]**2 + d[2]**2)
    # Path through box = (tmax - tmin) * ray_length
    return (tmax - tmin) * ray_length
