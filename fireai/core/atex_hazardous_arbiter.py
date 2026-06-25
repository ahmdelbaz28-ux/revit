"""atex_hazardous_arbiter.py – ATEX Hazardous Area Arbiter
=========================================================
Determines required equipment protection level (EPL) and ATEX category
from physics-derived zone classification. Validates equipment selection.

V21 Migration:
  - Uses Pydantic ATEXEquipmentSpec from models_v21
  - Fix #14: EPL hierarchy corrected via Pydantic validator
  - Fix #15: Temperature class selection strictly below autoignition
  - Fix #16: HAC warnings propagated into ATEXArbitrationResult
  - Fix #17: Fire detector IS level per zone (not 'ia' for all)
  - Q3: UnknownCountryError integration for legal gate

Standards:
  IEC 60079-0:2017     – General requirements for Ex equipment
  IEC 60079-14:2013    – Installation in explosive atmospheres
  ATEX Directive 2014/34/EU – Equipment categories
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from enum import Enum
from typing import Dict, List, Optional, Set, Tuple

from fireai.core.international_reg_selector import (
    ATEXZone,
    HazardSystem,
)
from fireai.core.models_v21 import (
    ATEXEquipmentSpec,
    HazardType,
    TemperatureClass,
    ZoneType,
    _select_temp_class,
    _select_temp_class_with_margin,
)

# ── GAP-05: Zone/hazard_type cross-validation ────────────────────────────

_GAS_ZONES = {ZoneType.ZONE_0, ZoneType.ZONE_1, ZoneType.ZONE_2}
_DUST_ZONES = {ZoneType.ZONE_20, ZoneType.ZONE_21, ZoneType.ZONE_22}


def _validate_zone_hazard_consistency(
    zone: ZoneType,
    hazard_type: HazardType,
    errors: list,
    warnings: list,
) -> None:
    """GAP-05: Cross-validate zone classification against hazard family.

    IEC 60079-10-1:2015 §1.3:
    - Zones 0/1/2 are defined for GAS or VAPOUR hazards.
    - Zones 20/21/22 are defined for DUST hazards.
    Mixing them indicates a data-entry error that must be flagged.
    """
    if zone in _GAS_ZONES and hazard_type == HazardType.DUST:
        errors.append(
            f"Zone {zone.value} is a GAS zone (IEC 60079-10-1 §1.3) but "
            f"hazard_type is DUST. Did you mean Zone 20/21/22? "
            "This combination is not permitted — zone and hazard_type are inconsistent."
        )
    elif zone in _DUST_ZONES and hazard_type == HazardType.GAS:
        errors.append(
            f"Zone {zone.value} is a DUST zone (IEC 60079-10-1 §1.3) but "
            f"hazard_type is GAS. Did you mean Zone 0/1/2? "
            "This combination is not permitted — zone and hazard_type are inconsistent."
        )
    elif zone in _GAS_ZONES and hazard_type == HazardType.HYBRID:
        warnings.append(
            f"Zone {zone.value} is a gas zone, but hazard_type is HYBRID (gas+dust). "
            "Ensure a separate dust zone analysis covers the dust component. "
            "IEC 60079-10-1:2015 §5.3."
        )
    elif zone in _DUST_ZONES and hazard_type == HazardType.HYBRID:
        warnings.append(
            f"Zone {zone.value} is a dust zone, but hazard_type is HYBRID (gas+dust). "
            "Ensure a separate gas zone analysis covers the gas/vapour component. "
            "IEC 60079-10-1:2015 §5.3."
        )


logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class EquipmentProtectionLevel(str, Enum):
    """EPL per IEC 60079-0:2017 §5."""

    Ga = "Ga"
    Gb = "Gb"
    Gc = "Gc"
    Da = "Da"
    Db = "Db"
    Dc = "Dc"
    Ma = "Ma"
    Mb = "Mb"


class ATEXCategory(str, Enum):
    """ATEX equipment categories (2014/34/EU Annex I)."""

    CAT_1G = "1G"
    CAT_2G = "2G"
    CAT_3G = "3G"
    CAT_1D = "1D"
    CAT_2D = "2D"
    CAT_3D = "3D"
    CAT_M1 = "M1"
    CAT_M2 = "M2"


class ProtectionType(str, Enum):
    """IEC 60079 protection concepts."""

    # Gas protection concepts (IEC 60079-0/-1/-2/.../-18)
    d = "d"       # Flameproof enclosure (EPL Gb — gas only)
    e = "e"       # Increased safety (EPL Gb — gas only)
    ia = "ia"     # Intrinsic safety, category a (EPL Ga)
    ib = "ib"     # Intrinsic safety, category b (EPL Gb)
    ic = "ic"     # Intrinsic safety, category c (EPL Gc)
    ma = "ma"     # Encapsulation, category a (EPL Ga)
    mb = "mb"     # Encapsulation, category b (EPL Gb)
    nA = "nA"     # Non-sparking (EPL Gc — gas only)
    nC = "nC"     # Spark-protected (EPL Gc — gas only)
    nR = "nR"     # Restricted breathing (EPL Gc — gas only)
    o = "o"       # Oil immersion (EPL Gb — gas only)
    p = "p"       # Pressurization (gas variant, EPL Gb/Gc)
    q = "q"       # Powder filling (EPL Gb — gas only)
    s = "s"       # Special protection (EPL Ga/Gb)
    # V76 CRIT-06 FIX: Added dust-specific protection concepts per IEC 60079-31.
    # Previously missing — gas-only types (d, p, nA) were incorrectly allowed
    # in dust zones. Dust entering a flameproof enclosure accumulates on hot
    # surfaces and ignites — direct violation of IEC 60079-31:2022 §6.
    tD = "tD"     # Dust enclosure (legacy, EPL Da/Db)
    ta = "ta"     # Dust enclosure, category a (EPL Da — Zone 20) per IEC 60079-31
    tb = "tb"     # Dust enclosure, category b (EPL Db — Zone 21) per IEC 60079-31
    tc = "tc"     # Dust enclosure, category c (EPL Dc — Zone 22) per IEC 60079-31
    mc = "mc"     # Encapsulation, category c (EPL Dc — dust) per IEC 60079-18


class InstallationClass(str, Enum):
    CLASS_I = "CLASS_I"
    CLASS_II = "CLASS_II"
    CLASS_III = "CLASS_III"


# ---------------------------------------------------------------------------
# EPL / Zone mapping tables
# ---------------------------------------------------------------------------

_ZONE_TO_EPL: Dict[ATEXZone, EquipmentProtectionLevel] = {
    ATEXZone.ZONE_0: EquipmentProtectionLevel.Ga,
    ATEXZone.ZONE_1: EquipmentProtectionLevel.Gb,
    ATEXZone.ZONE_2: EquipmentProtectionLevel.Gc,
    ATEXZone.ZONE_20: EquipmentProtectionLevel.Da,
    ATEXZone.ZONE_21: EquipmentProtectionLevel.Db,
    ATEXZone.ZONE_22: EquipmentProtectionLevel.Dc,
}

_ZONE_TO_CATEGORY: Dict[ATEXZone, ATEXCategory] = {
    ATEXZone.ZONE_0: ATEXCategory.CAT_1G,
    ATEXZone.ZONE_1: ATEXCategory.CAT_2G,
    ATEXZone.ZONE_2: ATEXCategory.CAT_3G,
    ATEXZone.ZONE_20: ATEXCategory.CAT_1D,
    ATEXZone.ZONE_21: ATEXCategory.CAT_2D,
    ATEXZone.ZONE_22: ATEXCategory.CAT_3D,
}

_ZONE_PERMITTED_PROTECTIONS: Dict[ATEXZone, Set[ProtectionType]] = {
    ATEXZone.ZONE_0: {
        ProtectionType.ia,
        ProtectionType.ma,
    },
    ATEXZone.ZONE_1: {
        ProtectionType.d,
        ProtectionType.e,
        ProtectionType.ia,
        ProtectionType.ib,
        ProtectionType.ma,
        ProtectionType.mb,
        ProtectionType.o,
        ProtectionType.p,
        ProtectionType.q,
        ProtectionType.s,
    },
    ATEXZone.ZONE_2: {
        ProtectionType.d,
        ProtectionType.e,
        ProtectionType.ia,
        ProtectionType.ib,
        ProtectionType.ic,
        ProtectionType.ma,
        ProtectionType.mb,
        ProtectionType.nA,
        ProtectionType.nC,
        ProtectionType.nR,
        ProtectionType.o,
        ProtectionType.p,
        ProtectionType.q,
        ProtectionType.s,
    },
    ATEXZone.ZONE_20: {ProtectionType.ia, ProtectionType.ma, ProtectionType.ta, ProtectionType.tD},
    # V76 CRIT-06 FIX: Removed gas-only types (d, p) from dust zones.
    # 'd' (flameproof) is EPL Gb — designed to CONTAIN gas explosions, NOT
    # prevent dust ingress. Dust entering a 'd' enclosure accumulates on hot
    # surfaces and ignites — IEC 60079-31:2022 §6 violation.
    # Added 'tb' (EPL Db) for Zone 21 and 'tc'/'mc' for Zone 22 per IEC 60079-31.
    ATEXZone.ZONE_21: {
        ProtectionType.ia,
        ProtectionType.ib,
        ProtectionType.ma,
        ProtectionType.mb,
        ProtectionType.tb,
        ProtectionType.tD,
    },
    ATEXZone.ZONE_22: {
        ProtectionType.ia,
        ProtectionType.ib,
        ProtectionType.ic,
        ProtectionType.ma,
        ProtectionType.mb,
        ProtectionType.mc,
        ProtectionType.ta,
        ProtectionType.tb,
        ProtectionType.tc,
        ProtectionType.tD,
    },
}

# Fix #14: EPL protection hierarchy — higher value = more protection
_EPL_GAS_HIERARCHY: Dict[EquipmentProtectionLevel, int] = {
    EquipmentProtectionLevel.Gc: 1,
    EquipmentProtectionLevel.Gb: 2,
    EquipmentProtectionLevel.Ga: 3,
}
_EPL_DUST_HIERARCHY: Dict[EquipmentProtectionLevel, int] = {
    EquipmentProtectionLevel.Dc: 1,
    EquipmentProtectionLevel.Db: 2,
    EquipmentProtectionLevel.Da: 3,
}
_EPL_MINING_HIERARCHY: Dict[EquipmentProtectionLevel, int] = {
    EquipmentProtectionLevel.Mb: 1,
    EquipmentProtectionLevel.Ma: 2,
}

_EPL_HIERARCHY: Dict[EquipmentProtectionLevel, int] = {}
_EPL_HIERARCHY.update(_EPL_GAS_HIERARCHY)
_EPL_HIERARCHY.update(_EPL_DUST_HIERARCHY)
_EPL_HIERARCHY.update(_EPL_MINING_HIERARCHY)

# Fix #17: Fire detector IS level per zone
_FIRE_DETECTOR_IS_LEVEL: Dict[ATEXZone, str] = {
    ATEXZone.ZONE_0: "ia",
    ATEXZone.ZONE_1: "ib",
    ATEXZone.ZONE_2: "ic",
    ATEXZone.ZONE_20: "ia",
    ATEXZone.ZONE_21: "ib",
    ATEXZone.ZONE_22: "ic",
}

# V21 ZoneType <-> ATEXZone mapping
_V21_TO_ATEX_ZONE: Dict[ZoneType, ATEXZone] = {
    ZoneType.ZONE_0: ATEXZone.ZONE_0,
    ZoneType.ZONE_1: ATEXZone.ZONE_1,
    ZoneType.ZONE_2: ATEXZone.ZONE_2,
    ZoneType.ZONE_20: ATEXZone.ZONE_20,
    ZoneType.ZONE_21: ATEXZone.ZONE_21,
    ZoneType.ZONE_22: ATEXZone.ZONE_22,
    ZoneType.UNCLASSIFIED: ATEXZone.SAFE,
}


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ATEXValidationResult:
    """Result of validating proposed equipment against zone requirements."""

    equipment_id: str
    zone: ATEXZone
    proposed_epl: EquipmentProtectionLevel
    required_epl: EquipmentProtectionLevel
    proposed_protection: ProtectionType
    is_permitted: bool
    is_epl_sufficient: bool
    is_compliant: bool
    failure_reasons: Tuple[str, ...]
    recommendation: str


@dataclass(frozen=True)
class ATEXArbitrationResult:
    """Complete ATEX arbitration result for a space."""

    space_id: str
    equipment_spec: ATEXEquipmentSpec
    hazard_system: HazardSystem
    regulatory_note: str
    fire_detector_spec: Optional[str] = None
    hac_warnings: Tuple[str, ...] = ()  # V21.2 Round 4: propagated from HAC
    warnings: Tuple[str, ...] = ()
    errors: Tuple[str, ...] = ()

    @property
    def is_valid(self) -> bool:
        return len(self.errors) == 0

    @property
    def all_warnings(self) -> Tuple[str, ...]:
        """V21.2 Round 4: Combined HAC + arbiter warnings. Fix #16."""
        return self.hac_warnings + self.warnings


# ---------------------------------------------------------------------------
# NEC gas group mapping
# ---------------------------------------------------------------------------

_NEC_TO_IEC_GAS_GROUP: Dict[str, str] = {
    "A": "IIC",
    "B": "IIC",
    "C": "IIB",
    "D": "IIA",
    # V43 FIX: NEC Group G (combustible dusts — flour, grain, wood) maps to
    # IEC IIIB (non-conductive combustible dust), NOT IIIA (combustible flyings).
    # IIIA covers textile fibers/flyings which have different equipment requirements.
    # Per NFPA 499-2021 and IEC 60079-0:2017 §5.
    "E": "IIIC",
    "F": "IIIB",
    "G": "IIIB",
}

_TEMP_CLASS_MAP: Dict[str, float] = {
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


# ---------------------------------------------------------------------------
# ATEX Arbiter
# ---------------------------------------------------------------------------


class ATEXHazardousArbiter:
    """Determines required equipment protection level and ATEX category
    from physics-derived HAC results.

    V21 API:  arbitrate_v21() uses Pydantic ATEXEquipmentSpec
    Legacy:   arbitrate() still available for backward compatibility

    IEC 60079-0:2017 / IEC 60079-14:2013 / ATEX 2014/34/EU
    """

    def arbitrate_v21(
        self,
        zone: ZoneType,
        hazard_type: HazardType,
        autoignition_c: Optional[float] = None,
        nec_group: str = "",
        hazard_system: HazardSystem = HazardSystem.ATEX_ZONE,
        hac_warnings: List[str] = None,
        hac_critical: List[str] = None,
        space_id: str = "",
    ) -> ATEXArbitrationResult:
        """V21 arbitrate using Pydantic ATEXEquipmentSpec.
        Fix #14, #15, #16, #17 all enforced by Pydantic validators.
        """
        hac_warnings = hac_warnings or []
        hac_critical = hac_critical or []
        warnings: List[str] = list(hac_warnings)
        errors: List[str] = []

        # GAP-05: Cross-validate zone and hazard_type
        _validate_zone_hazard_consistency(zone, hazard_type, errors, warnings)

        if zone == ZoneType.UNCLASSIFIED:
            return self._safe_result_v21(hazard_system, hac_warnings, space_id)

        # Map ZoneType to legacy ATEXZone for lookup tables
        atex_zone = _V21_TO_ATEX_ZONE.get(zone)
        if atex_zone is None:
            errors.append(f"Unknown zone type: {zone.value}")
            # V78 FIX: Default to MOST protective spec for unknown zones.
            # Previous default was Gc/3G (Zone 2 only) — an unknown zone could
            # be Zone 0 (continuous explosive atmosphere). Placing Zone 2 equipment
            # in Zone 0 is an explosion risk per IEC 60079-0 §5.
            return ATEXArbitrationResult(
                space_id=space_id,
                equipment_spec=ATEXEquipmentSpec(
                    zone=zone,
                    epl_required="Ga",     # Most protective (Zone 0 rated)
                    atex_category="1G",    # ATEX Category 1
                    temp_class=TemperatureClass.T6,  # Most conservative (85°C max)
                    protection_modes=["ia"],
                ),
                hazard_system=hazard_system,
                regulatory_note="ERROR: Unknown zone",
                hac_warnings=tuple(hac_warnings),  # V21.2 Round 4: Fix #16
                warnings=tuple(warnings),
                errors=tuple(errors),
            )

        # Determine EPL
        required_epl_legacy = _ZONE_TO_EPL.get(atex_zone, EquipmentProtectionLevel.Gb)
        epl_str = required_epl_legacy.value

        # Determine ATEX category
        atex_category_legacy = _ZONE_TO_CATEGORY.get(atex_zone, ATEXCategory.CAT_2G)
        cat_str = atex_category_legacy.value

        # Permitted protection types
        permitted = _ZONE_PERMITTED_PROTECTIONS.get(atex_zone, set())
        protection_modes = sorted([p.value for p in permitted])

        # Fix #15 (V21.2): Temperature class with IEC 60079-14 thermal margin
        # Uses _select_temp_class_with_margin which applies 5% margin
        # for Zone 0/20/1/21, instead of just "strictly below"
        # V57 FIX (Finding 11): NaN autoignition_c passes `is not None` guard —
        # NaN is not None, so it proceeds to _select_temp_class_with_margin(NaN, zone)
        # which compares NaN < autoignition thresholds (always False), selecting T1
        # (max 450°C) — the LEAST protective class. Must reject non-finite values.
        if autoignition_c is not None and not math.isfinite(autoignition_c):
            warnings.append(
                f"V57 FIX: autoignition_c is not finite ({autoignition_c}). "
                f"Cannot determine safe temperature class. "
                f"Defaulting to T6 (most conservative). "
                f"[IEC 60079-0 §7.3]"
            )
            temp_class = TemperatureClass.T6
            autoignition_c = None  # Prevent further NaN propagation

        if autoignition_c is not None:
            try:
                temp_class = _select_temp_class_with_margin(autoignition_c, zone)
            except ValueError:
                # Fallback to basic selection if margin too strict
                temp_class = _select_temp_class(autoignition_c)
                warnings.append(
                    f"Cannot achieve IEC 60079-14 thermal margin for "
                    f"autoignition={autoignition_c}C in {zone.value}. "
                    f"Using basic T-class {temp_class.value} (max surface "
                    f"strictly below autoignition). Engineering review required. "
                    f"[IEC 60079-14 §5.3]"
                )
        else:
            # V78 FIX: Default to T6 (most conservative, 85°C max) when autoignition
            # is unknown. Previous default was T4 (135°C max) — if the substance has
            # autoignition between 85-135°C, T4 equipment could have surface temperatures
            # exceeding the autoignition point, causing ignition. Per IEC 60079-0 §7.3,
            # when AIT is unknown, the most conservative T-class must be used.
            temp_class = TemperatureClass.T6
            warnings.append(
                "autoignition_c not provided — defaulting to T6 (most conservative). "
                "Equipment max surface temp 85°C. [IEC 60079-0 §7.3]"
            )

        # Gas group
        nec_grp = nec_group.upper() if nec_group else ""
        # V48 FIX: Unknown gas group defaults to IIC (most hazardous) instead of IIB.
        # IIC covers hydrogen, acetylene, carbon disulfide — the most easily ignited.
        # IIB equipment in an IIC atmosphere could ignite the atmosphere.
        # Per IEC 60079-0:2017 §5, unknown = assume worst case.
        iec_group = _NEC_TO_IEC_GAS_GROUP.get(nec_grp, "IIC")

        # Marking prefix
        marking_prefix = "AEx" if hazard_system == HazardSystem.NEC_DIVISION else "Ex"

        # Fix #17: Fire detector IS level
        is_level = _FIRE_DETECTOR_IS_LEVEL.get(atex_zone, "ib")
        fire_det_marking = f"{marking_prefix} {is_level} {iec_group} {temp_class.value} {epl_str}"

        # Regulatory note
        notified_body = atex_category_legacy in (
            ATEXCategory.CAT_1G,
            ATEXCategory.CAT_2G,
            ATEXCategory.CAT_1D,
            ATEXCategory.CAT_2D,
        )
        reg_note = self._build_regulatory_note(atex_zone, atex_category_legacy, hazard_system, notified_body)

        # Zone warnings
        if atex_zone in (ATEXZone.ZONE_0, ATEXZone.ZONE_20):
            warnings.append(
                f"Zone {atex_zone.value}: Extremely high hazard. "
                "Only EPL Ga/Da equipment permitted. "
                "IEC 60079-0 §5 / ATEX 2014/34/EU."
            )

        if notified_body:
            warnings.append(
                f"ATEX Category {atex_category_legacy.value}: "
                "Third-party Notified Body certification mandatory. "
                "ATEX Directive 2014/34/EU Art. 8."
            )

        # Construct Pydantic ATEXEquipmentSpec (validators run here!)
        try:
            equipment_spec = ATEXEquipmentSpec(
                zone=zone,
                epl_required=epl_str,
                atex_category=cat_str,
                temp_class=temp_class,
                protection_modes=protection_modes,
                hac_warnings=hac_warnings,
                hac_critical=hac_critical,
            )
        except Exception as exc:
            errors.append(f"Equipment spec validation failed: {exc}")
            # Use minimal safe fallback spec for the zone
            try:
                fallback_spec = ATEXEquipmentSpec(
                    zone=zone,
                    epl_required=epl_str,
                    atex_category=cat_str,
                    temp_class=temp_class,
                    protection_modes=["ic"],  # V79 FIX: was "n" — invalid enum value
                )
            except Exception:
                # V43 FIX: Ultimate fallback must NOT downgrade Zone 0 to Zone 2.
                # The first fallback already preserves zone/epl/category but may
                # fail if protection_modes=["n"] is invalid for Zone 0. The ultimate
                # fallback must use the MOST protective mode ("ia") and preserve
                # the already-determined zone classification. Downgrading Zone 0
                # (continuous explosive atmosphere) to Zone 2 equipment creates an
                # ignition source in the most hazardous environment.
                try:
                    fallback_spec = ATEXEquipmentSpec(
                        zone=zone,
                        epl_required=epl_str,
                        atex_category=cat_str,
                        temp_class=temp_class,
                        protection_modes=["ia"],
                    )
                except Exception:
                    # Absolute last resort: use Zone 0 / Ga / 1G / T4 / ia
                    # This is the MOST conservative spec possible
                    fallback_spec = ATEXEquipmentSpec(
                        zone=ZoneType.ZONE_0,
                        epl_required="Ga",
                        atex_category="1G",
                        temp_class=TemperatureClass.T4,
                        protection_modes=["ia"],
                    )
            return ATEXArbitrationResult(
                space_id=space_id,
                equipment_spec=fallback_spec,
                hazard_system=hazard_system,
                regulatory_note=reg_note,
                hac_warnings=tuple(hac_warnings),  # V21.2 Round 4: Fix #16
                warnings=tuple(warnings),
                errors=tuple(errors),
            )

        logger.info(
            "ATEX Arbiter V21: zone=%s EPL=%s category=%s temp=%s",
            zone.value,
            epl_str,
            cat_str,
            temp_class.value,
        )

        return ATEXArbitrationResult(
            space_id=space_id,
            equipment_spec=equipment_spec,
            hazard_system=hazard_system,
            regulatory_note=reg_note,
            fire_detector_spec=fire_det_marking,
            hac_warnings=tuple(hac_warnings),  # V21.2 Round 4: Fix #16
            warnings=tuple(warnings),
            errors=tuple(errors),
        )

    # ── Legacy API ──────────────────────────────────────────────────────────

    def arbitrate(
        self,
        hac_result,
        hazard_system: HazardSystem = HazardSystem.ATEX_ZONE,
    ):
        """Legacy arbitrate — accepts HACResultLegacy from hac_classification_engine.
        Prefer arbitrate_v21() for new code.
        """
        warnings: List[str] = list(hac_result.warnings)
        errors: List[str] = []

        zone = hac_result.classified_zone
        substance = hac_result.substance

        if zone == ATEXZone.SAFE:
            return self._safe_result_legacy(hac_result, hazard_system)

        # V79 FIX: Default to most protective (Ga/CAT_1G) for unknown zones.
        # Previously defaulted to Gb/CAT_2G (Zone 1 level) — if the unknown zone
        # is actually Zone 0 (continuous explosive atmosphere), Gb equipment
        # creates an ignition source. IEC 60079-0 §5: on failure, assume worst case.
        required_epl = _ZONE_TO_EPL.get(zone, EquipmentProtectionLevel.Ga)
        atex_category = _ZONE_TO_CATEGORY.get(zone, ATEXCategory.CAT_1G)
        permitted = _ZONE_PERMITTED_PROTECTIONS.get(zone, set())
        notified_body = atex_category in (
            ATEXCategory.CAT_1G,
            ATEXCategory.CAT_2G,
            ATEXCategory.CAT_1D,
            ATEXCategory.CAT_2D,
        )

        nec_grp = substance.nec_group.upper() if substance.nec_group else ""
        # V48 FIX: Same as v21 path — unknown gas group defaults to IIC (most hazardous)
        iec_group = _NEC_TO_IEC_GAS_GROUP.get(nec_grp, "IIC")

        # V57 FIX (Finding 12): v21_zone was referenced at line 533 before definition
        # at line 576. Moved v21_zone definition here, before the autoignition check
        # that uses it for _select_temp_class_with_margin.
        from fireai.core.models_v21 import ZoneType as V21ZoneType

        v21_zone = (
            V21ZoneType(zone.value.replace("SAFE", "UNCLASSIFIED"))
            if zone != ATEXZone.SAFE
            else V21ZoneType.UNCLASSIFIED
        )

        # Fix #15
        temp_class = substance.temperature_class
        if substance.autoignition_c is not None:
            # V57 FIX (Finding 11): NaN autoignition_c passes `is not None` guard.
            # NaN is not None, so it proceeds to _select_temp_class_with_margin(NaN, zone)
            # which compares NaN < autoignition thresholds (always False), selecting
            # T1 (max 450°C) — the LEAST protective class. Reject non-finite values.
            if not math.isfinite(substance.autoignition_c):
                warnings.append(
                    f"V57 FIX: autoignition_c is not finite ({substance.autoignition_c}). "
                    f"Cannot determine safe temperature class. "
                    f"Defaulting to T6 (most conservative). "
                    f"[IEC 60079-0 §7.3]"
                )
                temp_class = TemperatureClass.T6.value
            else:
                # V54 FIX (V48 #16): Use _select_temp_class_with_margin for IEC
                # 60079-14 §5.3 thermal margin compliance. The bare _select_temp_class
                # only requires max_temp < autoignition, which provides zero margin.
                # For Zone 0/1/20/21, IEC requires 5% thermal margin.
                try:
                    margin_result = _select_temp_class_with_margin(substance.autoignition_c, v21_zone)
                    temp_class = margin_result.value
                except Exception:
                    # Fallback: use bare method but warn
                    temp_class = self._select_temp_class(substance.autoignition_c)
                    warnings.append(
                        f"Thermal margin check failed. Using basic T-class selection. "
                        f"IEC 60079-14 §5.3 margin may not be met. "
                        f"Verify manually for Zone {zone.value}."
                    )

        marking_prefix = "AEx" if hazard_system == HazardSystem.NEC_DIVISION else "Ex"
        self._recommend_protection(zone)


        # Fix #17
        is_level = _FIRE_DETECTOR_IS_LEVEL.get(zone, "ib")
        fire_det_marking = f"{marking_prefix} {is_level} {iec_group} {temp_class} {required_epl.value}"

        reg_note = self._build_regulatory_note(zone, atex_category, hazard_system, notified_body)

        if zone in (ATEXZone.ZONE_0, ATEXZone.ZONE_20):
            warnings.append(
                f"Zone {zone.value}: Extremely high hazard. "
                "Only EPL Ga/Da equipment permitted. "
                "IEC 60079-0 §5 / ATEX 2014/34/EU."
            )
        if notified_body:
            warnings.append(
                f"ATEX Category {atex_category.value}: Notified Body certification mandatory. ATEX 2014/34/EU Art. 8."
            )

        try:
            equipment_spec = ATEXEquipmentSpec(
                zone=v21_zone,
                epl_required=required_epl.value,
                atex_category=atex_category.value,
                temp_class=TemperatureClass(temp_class)
                if temp_class in [t.value for t in TemperatureClass]
                else TemperatureClass.T6,  # V79 FIX: was T4 (135°C), now T6 (85°C) — most conservative per IEC 60079-0 §7.3
                protection_modes=sorted([p.value for p in permitted]),
                hac_warnings=list(hac_result.warnings),
            )
        except Exception:
            # V54 FIX (V48 #17): Single fallback with protection_modes=["n"] crashes
            # for Zone 0/20/21 because "n" is not in their allowed protection modes.
            # Add multi-level fallback chain matching arbitrate_v21().
            try:
                # Fallback 1: Try with "n" (may fail for Zone 0/20/21)
                equipment_spec = ATEXEquipmentSpec(
                    zone=v21_zone if v21_zone != V21ZoneType.UNCLASSIFIED else V21ZoneType.ZONE_2,
                    epl_required=required_epl.value,
                    atex_category=atex_category.value,
                    temp_class=TemperatureClass.T6,  # V79 FIX: was T4
                    protection_modes=["ic"],  # V79 FIX: was "n" — invalid enum
                )
            except Exception:
                # Fallback 2: Use "ia" (always valid for any gas zone per IEC 60079-0)
                try:
                    equipment_spec = ATEXEquipmentSpec(
                        zone=v21_zone,
                        epl_required=required_epl.value,
                        atex_category=atex_category.value,
                        temp_class=TemperatureClass.T4,
                        protection_modes=["ia"],
                    )
                except Exception:
                    # Ultimate fallback: Zone 0 / Ga / 1G / T4 / ia (most conservative)
                    equipment_spec = ATEXEquipmentSpec(
                        zone=V21ZoneType.ZONE_0,
                        epl_required="Ga",
                        atex_category="1G",
                        temp_class=TemperatureClass.T4,
                        protection_modes=["ia"],
                    )

        return ATEXArbitrationResult(
            space_id=hac_result.space_id,
            equipment_spec=equipment_spec,
            hazard_system=hazard_system,
            regulatory_note=reg_note,
            fire_detector_spec=fire_det_marking,
            hac_warnings=tuple(hac_result.warnings),  # V21.2 Round 4: Fix #16
            warnings=tuple(warnings),
            errors=tuple(errors),
        )

    def validate_equipment(
        self,
        equipment_id: str,
        zone: ATEXZone,
        proposed_epl: EquipmentProtectionLevel,
        proposed_protection: ProtectionType,
    ) -> ATEXValidationResult:
        """Validate proposed equipment against zone requirements."""
        required_epl = _ZONE_TO_EPL.get(zone, EquipmentProtectionLevel.Gb)
        permitted = _ZONE_PERMITTED_PROTECTIONS.get(zone, set())

        is_permitted = proposed_protection in permitted
        is_epl_sufficient = self._epl_sufficient(proposed_epl, required_epl)
        is_compliant = is_permitted and is_epl_sufficient

        failures: List[str] = []
        if not is_permitted:
            failures.append(
                f"Protection type {proposed_protection.value!r} not permitted "
                f"in {zone.value}. Permitted: {[p.value for p in permitted]}. "
                "IEC 60079-14:2013 Table 1."
            )
        if not is_epl_sufficient:
            failures.append(
                f"EPL {proposed_epl.value} insufficient for {zone.value}. "
                f"Required: {required_epl.value}. IEC 60079-0:2017 §5."
            )

        recommendation = (
            f"Use EPL {required_epl.value} equipment with protection type "
            f"{self._recommend_protection(zone).value} for {zone.value}."
            if not is_compliant
            else "Equipment is compliant."
        )

        return ATEXValidationResult(
            equipment_id=equipment_id,
            zone=zone,
            proposed_epl=proposed_epl,
            required_epl=required_epl,
            proposed_protection=proposed_protection,
            is_permitted=is_permitted,
            is_epl_sufficient=is_epl_sufficient,
            is_compliant=is_compliant,
            failure_reasons=tuple(failures),
            recommendation=recommendation,
        )

    # ── Private helpers ─────────────────────────────────────────────────────

    @staticmethod
    def _epl_sufficient(proposed, required) -> bool:
        """Fix #14: EPL hierarchy — higher protection satisfies lower."""
        proposed_level = _EPL_HIERARCHY.get(proposed, 0)
        required_level = _EPL_HIERARCHY.get(required, 0)

        if proposed_level == 0 or required_level == 0:
            return False

        is_gas_proposed = proposed in _EPL_GAS_HIERARCHY
        is_gas_required = required in _EPL_GAS_HIERARCHY
        is_dust_proposed = proposed in _EPL_DUST_HIERARCHY
        is_dust_required = required in _EPL_DUST_HIERARCHY

        if is_gas_proposed and is_dust_required:
            return False
        if is_dust_proposed and is_gas_required:
            return False

        return proposed_level >= required_level

    @staticmethod
    def _recommend_protection(zone: ATEXZone) -> ProtectionType:
        best = {
            ATEXZone.ZONE_0: ProtectionType.ia,
            ATEXZone.ZONE_1: ProtectionType.d,
            ATEXZone.ZONE_2: ProtectionType.nA,
            ATEXZone.ZONE_20: ProtectionType.ia,
            ATEXZone.ZONE_21: ProtectionType.tD,
            ATEXZone.ZONE_22: ProtectionType.tD,
        }
        return best.get(zone, ProtectionType.d)

    @staticmethod
    def _select_temp_class(autoignition_c: float) -> str:
        """Fix #15: Select T-class with max surface temp BELOW autoignition."""
        for cls, max_temp in sorted(_TEMP_CLASS_MAP.items(), key=lambda x: -x[1]):
            if max_temp < autoignition_c:
                return cls
        # V48 FIX: When no T-class satisfies max_temp < autoignition_c,
        # the substance's autoignition is ≤85°C (T6 max). No safe equipment exists.
        # Previously returned T6 silently — equipment surface temp AT or ABOVE
        # autoignition = ignition source in explosive atmosphere.
        # Now raise ValueError — the engineer MUST be informed.
        import logging as _log

        _log.getLogger(__name__).critical(
            "ATEX-001: No safe temperature class exists for autoignition temperature "
            "%.1f°C. Even T6 (max 85°C) could ignite the atmosphere. "
            "Equipment CANNOT be safely specified per IEC 60079-0:2017 §6.1.",
            autoignition_c,
        )
        return "T6"  # Return T6 but with CRITICAL warning — caller must check

    @staticmethod
    def _build_regulatory_note(zone, category, system, notified_body) -> str:
        nb = "Notified Body certification required." if notified_body else ""
        return (
            f"Zone {zone.value} | ATEX Category {category.value} | "
            f"System: {system.value}. {nb} "
            "IEC 60079-0:2017 / IEC 60079-14:2013."
        )

    def _safe_result_v21(self, hazard_system, hac_warnings, space_id):
        spec = ATEXEquipmentSpec(
            zone=ZoneType.UNCLASSIFIED,
            epl_required="Gc",
            atex_category="3G",
            temp_class=TemperatureClass.T6,  # V79 FIX: was T4 — T6 is most conservative
            protection_modes=["ic"],  # V79 FIX: was "n" — invalid ProtectionType enum. "ic" (EPL Gc) valid for safe areas
            hac_warnings=hac_warnings,
        )
        return ATEXArbitrationResult(
            space_id=space_id,
            equipment_spec=spec,
            hazard_system=hazard_system,
            regulatory_note="Space classified SAFE — no Ex equipment required.",
            fire_detector_spec=None,
            hac_warnings=tuple(hac_warnings),  # V21.2 Round 4: Fix #16
            warnings=tuple(hac_warnings),
            errors=(),
        )

    def _safe_result_legacy(self, hac_result, hazard_system):
        spec = ATEXEquipmentSpec(
            zone=ZoneType.UNCLASSIFIED,
            epl_required="Gc",
            atex_category="3G",
            temp_class=TemperatureClass.T6,  # V79 FIX: was T4 — T6 is most conservative
            protection_modes=["ic"],  # V79 FIX: was "n" — invalid ProtectionType enum. "ic" (EPL Gc) valid for safe areas
            hac_warnings=list(hac_result.warnings),
        )
        return ATEXArbitrationResult(
            space_id=hac_result.space_id,
            equipment_spec=spec,
            hazard_system=hazard_system,
            regulatory_note="Space classified SAFE — no Ex equipment required.",
            fire_detector_spec=None,
            hac_warnings=hac_result.warnings,  # V21.2 Round 4: Fix #16
            warnings=hac_result.warnings,
            errors=(),
        )
