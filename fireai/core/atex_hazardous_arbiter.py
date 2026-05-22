"""
atex_hazardous_arbiter.py – ATEX Hazardous Area Arbiter
=========================================================
Determines required equipment protection level (EPL) and ATEX category
from physics-derived zone classification. Validates equipment selection.

Standards:
  IEC 60079-0:2017     – General requirements for Ex equipment
  IEC 60079-14:2013    – Installation in explosive atmospheres
  IEC 60079-17:2013    – Inspection and maintenance
  ATEX Directive 2014/34/EU – Equipment categories
  EN 13463            – Non-electrical equipment in Ex atmospheres

Equipment Protection Levels (EPL):
  Ga / Da → Zone 0/20   (very high protection)
  Gb / Db → Zone 1/21   (high protection)
  Gc / Dc → Zone 2/22   (enhanced protection)

ATEX Categories:
  Cat 1G/1D → Zone 0/20  (Notified Body required)
  Cat 2G/2D → Zone 1/21  (Notified Body required)
  Cat 3G/3D → Zone 2/22  (self-certification possible)

V20.2 Fix #14 (CRITICAL): _epl_sufficient() had inverted comparison.
  _EPL_ORDER listed Gc at index 0 (lowest protection) and Ga at index 5
  (highest). The comparison `proposed >= required` meant Gc (index 0)
  could pass as sufficient for Ga (index 5). Fixed to use `<=` —
  proposed EPL must have index <= required (lower index = less protection
  needed? NO — the original ordering was wrong). Rewrote to use explicit
  protection level hierarchy where higher protection satisfies lower.

V20.2 Fix #15 (CRITICAL): _select_temp_class() selected WRONG T-class.
  When autoignition=180°C, it returned T3 (200°C max surface) which is
  DANGEROUS — equipment at 200°C can ignite a substance at 180°C!
  IEC 60079-0 §7.3: max surface temp must be < autoignition temp.
  Fixed to select T-class with max surface temp strictly below autoignition.

V20.2 Fix #16 (HIGH): arbitrate() dropped HAC warnings silently.
  Warnings from physics-based classification (e.g. hybrid mixture,
  MIE < 3mJ, flash point) were lost in the ATEX arbitration layer.
  Now propagated into final ATEXArbitrationResult.warnings.

V20.2 Fix #17 (HIGH): Fire detector Ex marking used 'ia' for ALL zones.
  Zone 1 permits 'ib' intrinsic safety (not just 'ia'). Zone 2 permits
  'ic'. Using 'ia' specification for Zone 2 is over-specified and
  unnecessarily expensive. Now selects appropriate IS level per zone.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Set, Tuple

from fireai.core.international_reg_selector import ATEXZone, HazardSystem
from fireai.core.hac_classification_engine import HACResult, SubstanceProperties

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class EquipmentProtectionLevel(str, Enum):
    """
    EPL per IEC 60079-0:2017 §5.
    Ga/Da = very high (Zone 0/20)
    Gb/Db = high (Zone 1/21)
    Gc/Dc = enhanced (Zone 2/22)
    """
    Ga = "Ga"   # Gas, very high
    Gb = "Gb"   # Gas, high
    Gc = "Gc"   # Gas, enhanced
    Da = "Da"   # Dust, very high
    Db = "Db"   # Dust, high
    Dc = "Dc"   # Dust, enhanced
    Ma = "Ma"   # Mining, very high
    Mb = "Mb"   # Mining, high


class ATEXCategory(str, Enum):
    """ATEX equipment categories (2014/34/EU Annex I)."""
    CAT_1G = "1G"   # Zone 0  – Notified Body mandatory
    CAT_2G = "2G"   # Zone 1  – Notified Body mandatory
    CAT_3G = "3G"   # Zone 2  – self-cert possible
    CAT_1D = "1D"   # Zone 20 – Notified Body mandatory
    CAT_2D = "2D"   # Zone 21 – Notified Body mandatory
    CAT_3D = "3D"   # Zone 22 – self-cert possible
    CAT_M1 = "M1"   # Mining, Category 1
    CAT_M2 = "M2"   # Mining, Category 2


class ProtectionType(str, Enum):
    """
    IEC 60079 protection concepts.
    """
    d   = "d"    # Flameproof enclosure (IEC 60079-1)
    e   = "e"    # Increased safety (IEC 60079-7)
    ia  = "ia"   # Intrinsic safety, level ia (IEC 60079-11)
    ib  = "ib"   # Intrinsic safety, level ib
    ic  = "ic"   # Intrinsic safety, level ic
    ma  = "ma"   # Encapsulation, level ma (IEC 60079-18)
    mb  = "mb"   # Encapsulation, level mb
    nA  = "nA"   # Non-sparking (IEC 60079-15)
    nC  = "nC"   # Sparking equipment in Zone 2
    nR  = "nR"   # Restricted breathing
    o   = "o"    # Oil immersion (IEC 60079-6)
    p   = "p"    # Pressurised (IEC 60079-2)
    q   = "q"    # Powder filling (IEC 60079-5)
    s   = "s"    # Special protection
    tD  = "tD"   # Dust protection by enclosure (IEC 60079-31)


class InstallationClass(str, Enum):
    """NEC installation class per NFPA 70 Art. 500."""
    CLASS_I   = "CLASS_I"
    CLASS_II  = "CLASS_II"
    CLASS_III = "CLASS_III"


# ---------------------------------------------------------------------------
# EPL / Zone mapping tables
# ---------------------------------------------------------------------------

# Zone → Required EPL (IEC 60079-0 Table 3)
_ZONE_TO_EPL: Dict[ATEXZone, EquipmentProtectionLevel] = {
    ATEXZone.ZONE_0:  EquipmentProtectionLevel.Ga,
    ATEXZone.ZONE_1:  EquipmentProtectionLevel.Gb,
    ATEXZone.ZONE_2:  EquipmentProtectionLevel.Gc,
    ATEXZone.ZONE_20: EquipmentProtectionLevel.Da,
    ATEXZone.ZONE_21: EquipmentProtectionLevel.Db,
    ATEXZone.ZONE_22: EquipmentProtectionLevel.Dc,
}

# Zone → ATEX Category (2014/34/EU)
_ZONE_TO_CATEGORY: Dict[ATEXZone, ATEXCategory] = {
    ATEXZone.ZONE_0:  ATEXCategory.CAT_1G,
    ATEXZone.ZONE_1:  ATEXCategory.CAT_2G,
    ATEXZone.ZONE_2:  ATEXCategory.CAT_3G,
    ATEXZone.ZONE_20: ATEXCategory.CAT_1D,
    ATEXZone.ZONE_21: ATEXCategory.CAT_2D,
    ATEXZone.ZONE_22: ATEXCategory.CAT_3D,
}

# Zone → permitted protection types (IEC 60079-14 Table 1)
_ZONE_PERMITTED_PROTECTIONS: Dict[ATEXZone, Set[ProtectionType]] = {
    ATEXZone.ZONE_0: {
        ProtectionType.ia, ProtectionType.ma,
    },
    ATEXZone.ZONE_1: {
        ProtectionType.d, ProtectionType.e, ProtectionType.ia,
        ProtectionType.ib, ProtectionType.ma, ProtectionType.mb,
        ProtectionType.o, ProtectionType.p, ProtectionType.q,
        ProtectionType.s,
    },
    ATEXZone.ZONE_2: {
        ProtectionType.d, ProtectionType.e, ProtectionType.ia,
        ProtectionType.ib, ProtectionType.ic, ProtectionType.ma,
        ProtectionType.mb, ProtectionType.nA, ProtectionType.nC,
        ProtectionType.nR, ProtectionType.o, ProtectionType.p,
        ProtectionType.q, ProtectionType.s,
    },
    ATEXZone.ZONE_20: {ProtectionType.ia, ProtectionType.ma, ProtectionType.tD},
    ATEXZone.ZONE_21: {
        ProtectionType.ia, ProtectionType.ib, ProtectionType.ma,
        ProtectionType.mb, ProtectionType.d, ProtectionType.p,
        ProtectionType.tD,
    },
    ATEXZone.ZONE_22: {
        ProtectionType.ia, ProtectionType.ib, ProtectionType.ic,
        ProtectionType.ma, ProtectionType.mb, ProtectionType.d,
        ProtectionType.p, ProtectionType.tD, ProtectionType.nA,
    },
}

# V20.2 Fix #14: EPL protection hierarchy — higher value = more protection
# An EPL is sufficient if its protection level >= required level.
# Gas and dust EPLs are separate hierarchies and cannot cross-substitute.
_EPL_GAS_HIERARCHY: Dict[EquipmentProtectionLevel, int] = {
    EquipmentProtectionLevel.Gc: 1,  # Enhanced
    EquipmentProtectionLevel.Gb: 2,  # High
    EquipmentProtectionLevel.Ga: 3,  # Very high
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

# All hierarchies combined for lookup
_EPL_HIERARCHY: Dict[EquipmentProtectionLevel, int] = {}
_EPL_HIERARCHY.update(_EPL_GAS_HIERARCHY)
_EPL_HIERARCHY.update(_EPL_DUST_HIERARCHY)
_EPL_HIERARCHY.update(_EPL_MINING_HIERARCHY)

# V20.2 Fix #17: Fire detector IS level per zone
# IEC 60079-14: Zone 0 → ia, Zone 1 → ib, Zone 2 → ic (for gas)
# Zone 20 → ia, Zone 21 → ib, Zone 22 → ic (for dust)
_FIRE_DETECTOR_IS_LEVEL: Dict[ATEXZone, str] = {
    ATEXZone.ZONE_0:  "ia",
    ATEXZone.ZONE_1:  "ib",
    ATEXZone.ZONE_2:  "ic",
    ATEXZone.ZONE_20: "ia",
    ATEXZone.ZONE_21: "ib",
    ATEXZone.ZONE_22: "ic",
}


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ATEXEquipmentSpec:
    """
    Required equipment specification for installation in a hazardous zone.
    IEC 60079-0 §7 / IEC 60079-14 §5.
    """
    zone:                ATEXZone
    required_epl:        EquipmentProtectionLevel
    atex_category:       ATEXCategory
    permitted_protections: Tuple[ProtectionType, ...]
    temperature_class:   str         # T1–T6
    gas_group:           str         # IIA, IIB, IIC (gas) / IIIA, IIIB, IIIC (dust)
    notified_body_required: bool
    marking_prefix:      str         # "Ex" or "AEx"
    full_marking:        str         # e.g. "Ex d IIC T4 Gb"
    installation_std:    str = "IEC 60079-14:2013"


@dataclass(frozen=True)
class ATEXValidationResult:
    """Result of validating proposed equipment against zone requirements."""
    equipment_id:        str
    zone:                ATEXZone
    proposed_epl:        EquipmentProtectionLevel
    required_epl:        EquipmentProtectionLevel
    proposed_protection: ProtectionType
    is_permitted:        bool
    is_epl_sufficient:   bool
    is_compliant:        bool
    failure_reasons:     Tuple[str, ...]
    recommendation:      str


@dataclass(frozen=True)
class ATEXArbitrationResult:
    """
    Complete ATEX arbitration result for a space.
    Physics-derived — no manual zone assignment.
    """
    space_id:            str
    hac_result:          HACResult
    equipment_spec:      ATEXEquipmentSpec
    hazard_system:       HazardSystem
    regulatory_note:     str
    fire_detector_spec:  Optional[str]  = None  # Ex marking for fire detector
    warnings:            Tuple[str, ...] = ()
    errors:              Tuple[str, ...] = ()

    @property
    def is_valid(self) -> bool:
        return len(self.errors) == 0

    @property
    def zone(self) -> ATEXZone:
        return self.hac_result.classified_zone


# ---------------------------------------------------------------------------
# NEC gas group → IEC group mapping
# ---------------------------------------------------------------------------

_NEC_TO_IEC_GAS_GROUP: Dict[str, str] = {
    "A": "IIC",   # Acetylene
    "B": "IIC",   # Hydrogen
    "C": "IIB",   # Ethylene
    "D": "IIA",   # Propane
    "E": "IIIC",  # Metal dust
    "F": "IIIB",  # Carbon black
    "G": "IIIA",  # Grain dust
}

_TEMP_CLASS_MAP: Dict[str, float] = {
    "T1": 450.0, "T2": 300.0, "T2A": 280.0, "T2B": 260.0,
    "T2C": 230.0, "T2D": 215.0, "T3": 200.0, "T3A": 180.0,
    "T3B": 165.0, "T3C": 160.0, "T4": 135.0, "T4A": 120.0,
    "T5": 100.0, "T6": 85.0,
}


# ---------------------------------------------------------------------------
# ATEX Arbiter
# ---------------------------------------------------------------------------

class ATEXHazardousArbiter:
    """
    Determines required equipment protection level and ATEX category
    from physics-derived HAC results.

    CRITICAL: This rewrite removes manual zone input dependency.
    All classification flows from HACClassificationEngine output.

    IEC 60079-0:2017 / IEC 60079-14:2013 / ATEX 2014/34/EU
    """

    def arbitrate(
        self,
        hac_result: HACResult,
        hazard_system: HazardSystem = HazardSystem.ATEX_ZONE,
    ) -> ATEXArbitrationResult:
        """
        Determine equipment requirements from physics-derived zone.

        Args:
            hac_result:    Output of HACClassificationEngine.classify()
            hazard_system: Target regulatory system (ATEX, IECEx, NEC, etc.)

        Returns:
            ATEXArbitrationResult with EPL, category, protection types.
        """
        zone = hac_result.classified_zone
        warnings: List[str] = []
        errors:   List[str] = []

        # V20.2 Fix #16: Propagate HAC warnings into arbitration
        warnings.extend(hac_result.warnings)

        if zone == ATEXZone.SAFE:
            return self._safe_result(hac_result, hazard_system)

        # Determine EPL
        required_epl = _ZONE_TO_EPL.get(zone, EquipmentProtectionLevel.Gb)

        # Determine ATEX category
        atex_category = _ZONE_TO_CATEGORY.get(zone, ATEXCategory.CAT_2G)

        # Permitted protection types
        permitted = _ZONE_PERMITTED_PROTECTIONS.get(zone, set())

        # Notified Body requirement
        notified_body = atex_category in (
            ATEXCategory.CAT_1G, ATEXCategory.CAT_2G,
            ATEXCategory.CAT_1D, ATEXCategory.CAT_2D,
        )

        # Gas group
        substance = hac_result.substance
        nec_grp = substance.nec_group.upper() if substance.nec_group else ""
        iec_group = _NEC_TO_IEC_GAS_GROUP.get(nec_grp, "IIB")

        # V20.2 Fix #15: Temperature class selection with safe margin
        temp_class = substance.temperature_class
        if substance.autoignition_c is not None:
            temp_class = self._select_temp_class(substance.autoignition_c)

        # Marking prefix
        if hazard_system == HazardSystem.NEC_DIVISION:
            marking_prefix = "AEx"
        else:
            marking_prefix = "Ex"

        # Recommend best practice protection type for this zone
        recommended_protection = self._recommend_protection(zone)

        # Build full Ex marking string
        full_marking = (
            f"{marking_prefix} {recommended_protection.value} "
            f"{iec_group} {temp_class} {required_epl.value}"
        )

        # V20.2 Fix #17: Fire detector Ex marking with appropriate IS level
        is_level = _FIRE_DETECTOR_IS_LEVEL.get(zone, "ib")
        fire_det_marking = (
            f"{marking_prefix} {is_level} {iec_group} {temp_class} {required_epl.value}"
        )

        # Regulatory note
        reg_note = self._build_regulatory_note(
            zone, atex_category, hazard_system, notified_body)

        # Warnings
        if zone in (ATEXZone.ZONE_0, ATEXZone.ZONE_20):
            warnings.append(
                f"Zone {zone.value}: Extremely high hazard. "
                "Only EPL Ga/Da equipment permitted. "
                "Intrinsic safety (ia) is the primary protection concept. "
                "IEC 60079-0 §5 / ATEX 2014/34/EU."
            )

        if notified_body:
            warnings.append(
                f"ATEX Category {atex_category.value}: "
                "Third-party Notified Body certification mandatory. "
                "ATEX Directive 2014/34/EU Art. 8."
            )

        equipment_spec = ATEXEquipmentSpec(
            zone=zone,
            required_epl=required_epl,
            atex_category=atex_category,
            permitted_protections=tuple(sorted(permitted, key=lambda p: p.value)),
            temperature_class=temp_class,
            gas_group=iec_group,
            notified_body_required=notified_body,
            marking_prefix=marking_prefix,
            full_marking=full_marking,
        )

        logger.info(
            "ATEX Arbiter: space=%s zone=%s EPL=%s category=%s marking=%s",
            hac_result.space_id, zone.value,
            required_epl.value, atex_category.value, full_marking,
        )

        return ATEXArbitrationResult(
            space_id=hac_result.space_id,
            hac_result=hac_result,
            equipment_spec=equipment_spec,
            hazard_system=hazard_system,
            regulatory_note=reg_note,
            fire_detector_spec=fire_det_marking,
            warnings=tuple(warnings),
            errors=tuple(errors),
        )

    def validate_equipment(
        self,
        equipment_id:        str,
        zone:                ATEXZone,
        proposed_epl:        EquipmentProtectionLevel,
        proposed_protection: ProtectionType,
    ) -> ATEXValidationResult:
        """
        Validate proposed equipment against zone requirements.
        IEC 60079-14:2013 §5.
        """
        required_epl = _ZONE_TO_EPL.get(zone, EquipmentProtectionLevel.Gb)
        permitted    = _ZONE_PERMITTED_PROTECTIONS.get(zone, set())

        is_permitted = proposed_protection in permitted
        is_epl_sufficient = self._epl_sufficient(proposed_epl, required_epl)
        is_compliant = is_permitted and is_epl_sufficient

        failures: List[str] = []
        if not is_permitted:
            failures.append(
                f"Protection type {proposed_protection.value!r} not permitted "
                f"in {zone.value}. "
                f"Permitted: {[p.value for p in permitted]}. "
                "IEC 60079-14:2013 Table 1."
            )
        if not is_epl_sufficient:
            failures.append(
                f"EPL {proposed_epl.value} insufficient for {zone.value}. "
                f"Required: {required_epl.value}. "
                "IEC 60079-0:2017 §5."
            )

        recommendation = (
            f"Use EPL {required_epl.value} equipment with protection type "
            f"{self._recommend_protection(zone).value} for {zone.value}."
            if not is_compliant else "Equipment is compliant."
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

    # -----------------------------------------------------------------------
    # Private helpers
    # -----------------------------------------------------------------------

    @staticmethod
    def _epl_sufficient(
        proposed: EquipmentProtectionLevel,
        required: EquipmentProtectionLevel,
    ) -> bool:
        """
        V20.2 Fix #14: EPL hierarchy — higher protection satisfies lower.
        
        Gas and dust EPLs are separate hierarchies:
          Gas:  Ga (3) > Gb (2) > Gc (1)
          Dust: Da (3) > Db (2) > Dc (1)
        
        Ga equipment CAN be used in Zone 1 (Gb) or Zone 2 (Gc) —
        it provides MORE protection than required.
        Gc equipment CANNOT be used in Zone 0 (Ga) — insufficient.
        
        Cross-substitution (gas EPL in dust zone or vice versa) is NOT
        permitted per IEC 60079-0 §5.2.
        """
        proposed_level = _EPL_HIERARCHY.get(proposed, 0)
        required_level = _EPL_HIERARCHY.get(required, 0)
        
        if proposed_level == 0 or required_level == 0:
            # Unknown EPL — fail safe
            return False
        
        # Check same hierarchy (gas vs dust vs mining)
        is_gas_proposed = proposed in _EPL_GAS_HIERARCHY
        is_gas_required = required in _EPL_GAS_HIERARCHY
        is_dust_proposed = proposed in _EPL_DUST_HIERARCHY
        is_dust_required = required in _EPL_DUST_HIERARCHY
        
        # Cross-substitution not permitted
        if is_gas_proposed and is_dust_required:
            return False
        if is_dust_proposed and is_gas_required:
            return False
        
        # Higher level (more protection) satisfies lower requirement
        return proposed_level >= required_level

    @staticmethod
    def _recommend_protection(zone: ATEXZone) -> ProtectionType:
        best = {
            ATEXZone.ZONE_0:  ProtectionType.ia,
            ATEXZone.ZONE_1:  ProtectionType.d,
            ATEXZone.ZONE_2:  ProtectionType.nA,
            ATEXZone.ZONE_20: ProtectionType.ia,
            ATEXZone.ZONE_21: ProtectionType.tD,
            ATEXZone.ZONE_22: ProtectionType.tD,
        }
        return best.get(zone, ProtectionType.d)

    @staticmethod
    def _select_temp_class(autoignition_c: float) -> str:
        """
        V20.2 Fix #15: Select T-class with max surface temp BELOW autoignition.
        
        IEC 60079-0 §7.3: equipment surface temperature must be less than
        the autoignition temperature of the gas/vapor/dust.
        
        OLD BUG: When autoignition=180°C, old code returned T3 (200°C max)
        which EXCEEDS the autoignition — equipment could IGNITE the substance.
        
        Fixed: selects T-class with max surface temp strictly below
        autoignition, with safety margin per IEC 60079-0 §7.3.
        """
        # Sort by max temp DESCENDING, find first T-class where max_temp < autoignition
        # This gives the highest (least restrictive) safe T-class
        for cls, max_temp in sorted(
            _TEMP_CLASS_MAP.items(), key=lambda x: -x[1]
        ):
            if max_temp < autoignition_c:
                return cls
        # If autoignition is below all T-class limits (extremely sensitive)
        # or equals the lowest T6 limit, return T6 (safest)
        # IEC 60079-0 §7.3: if no standard T-class fits, special measures needed
        return "T6"

    @staticmethod
    def _build_regulatory_note(
        zone: ATEXZone,
        category: ATEXCategory,
        system: HazardSystem,
        notified_body: bool,
    ) -> str:
        nb = "Notified Body certification required." if notified_body else ""
        return (
            f"Zone {zone.value} | ATEX Category {category.value} | "
            f"System: {system.value}. {nb} "
            "IEC 60079-0:2017 / IEC 60079-14:2013."
        )

    @staticmethod
    def _safe_result(
        hac_result: HACResult,
        hazard_system: HazardSystem,
    ) -> ATEXArbitrationResult:
        spec = ATEXEquipmentSpec(
            zone=ATEXZone.SAFE,
            required_epl=EquipmentProtectionLevel.Gc,
            atex_category=ATEXCategory.CAT_3G,
            permitted_protections=tuple(ProtectionType),
            temperature_class="T3",
            gas_group="IIA",
            notified_body_required=False,
            marking_prefix="Ex",
            full_marking="Non-Ex (SAFE zone — no Ex equipment required)",
        )
        return ATEXArbitrationResult(
            space_id=hac_result.space_id,
            hac_result=hac_result,
            equipment_spec=spec,
            hazard_system=hazard_system,
            regulatory_note="Space classified SAFE — no Ex equipment required.",
            fire_detector_spec=None,
            # V20.2 Fix #16: Propagate HAC warnings even for SAFE zones
            warnings=hac_result.warnings,
            errors=(),
        )
