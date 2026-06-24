"""international_reg_selector.py – International Regulatory Jurisdiction Selector
===============================================================================
Maps project location to the correct regulatory framework for hazardous area
classification. This is a LEGAL GATE — wrong jurisdiction = illegal design.

V21 Migration:
  - Pydantic RegSelectorResult replaces dataclass
  - UnknownCountryError RAISES instead of silently falling back to IECEx
  - Strict validation — no invalid jurisdiction can exist

Supported Frameworks:
  ATEX Zone System     (EU/EFTA)  – Directive 2014/34/EU, EN 60079
  IECEx Zone System    (Global)   – IEC 60079 series
  NEC Division System  (USA/MX)   – NFPA 70 Art. 500-506
  CEC Zone System      (Canada)   – CEC Section 18, CSA C22.1
  EFTA Zone System     (Norway, CH, IS, LI) – ATEX via EEA

Fix #1 (CRITICAL): Canada mapped to CEC_ZONE (not NEC_DIVISION) since 1998.
Fix #3 (HIGH):     Norway -> EFTA (not EU member).
Fix #4 (HIGH):     CLASS_III has NO IEC zone equivalent.
Fix #5 (MEDIUM):   +15 missing countries added.
Q3 (HIGH):         Unknown country raises UnknownCountryError (not silent warning).
"""

from __future__ import annotations

import logging
from enum import Enum
from typing import Dict, List, Optional, Tuple

from fireai.core.models_v21 import RegSelectorResult, RegulatoryFramework

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Enums — preserved for backward compatibility
# ---------------------------------------------------------------------------


class HazardSystem(str, Enum):
    NEC_DIVISION = "NEC_DIVISION"  # USA (NFPA 70 Art. 500-506)
    CEC_ZONE = "CEC_ZONE"  # Canada (CEC Section 18, CSA C22.1)
    ATEX_ZONE = "ATEX_ZONE"  # EU, UK (2014/34/EU, EN 60079)
    IECEX_ZONE = "IECEX_ZONE"  # Global (IEC 60079)
    AS_NZS_ZONE = "AS_NZS_ZONE"  # Australia, New Zealand
    GOST_ZONE = "GOST_ZONE"  # Russia, CIS (GOST R 51330)
    GB_ZONE = "GB_ZONE"  # China (GB 3836)


class JurisdictionRegion(str, Enum):
    USA = "USA"
    CANADA = "CANADA"
    EU = "EU"
    EFTA = "EFTA"
    UK = "UK"
    AUSTRALIA = "AUSTRALIA"
    NEW_ZEALAND = "NEW_ZEALAND"
    RUSSIA = "RUSSIA"
    KAZAKHSTAN = "KAZAKHSTAN"
    CHINA = "CHINA"
    JAPAN = "JAPAN"
    SOUTH_KOREA = "SOUTH_KOREA"
    BRAZIL = "BRAZIL"
    MIDDLE_EAST = "MIDDLE_EAST"
    INDIA = "INDIA"
    SOUTH_AFRICA = "SOUTH_AFRICA"
    ASEAN = "ASEAN"
    TURKEY = "TURKEY"
    NORTH_AFRICA = "NORTH_AFRICA"
    WEST_AFRICA = "WEST_AFRICA"
    SOUTH_AMERICA = "SOUTH_AMERICA"
    CENTRAL_ASIA = "CENTRAL_ASIA"
    GLOBAL = "GLOBAL"


class HazardClass(str, Enum):
    CLASS_I = "CLASS_I"  # Flammable gases/vapors (NEC Art. 501)
    CLASS_II = "CLASS_II"  # Combustible dust (NEC Art. 502)
    CLASS_III = "CLASS_III"  # Ignitable fibers (NEC Art. 503)
    GAS_VAPOR = "GAS_VAPOR"  # Zone 0/1/2 or Div 1/2
    DUST = "DUST"  # Zone 20/21/22 or Div 1/2


class NECDivision(str, Enum):
    DIVISION_1 = "DIVISION_1"
    DIVISION_2 = "DIVISION_2"


class ATEXZone(str, Enum):
    ZONE_0 = "ZONE_0"
    ZONE_1 = "ZONE_1"
    ZONE_2 = "ZONE_2"
    ZONE_20 = "ZONE_20"
    ZONE_21 = "ZONE_21"
    ZONE_22 = "ZONE_22"
    SAFE = "SAFE"


# ---------------------------------------------------------------------------
# Q3: UnknownCountryError — RAISES, never silently falls back
# ---------------------------------------------------------------------------


class UnknownCountryError(Exception):
    """FIXED Q3: Raised when country has no registered regulatory framework.
    Prevents exporting legally incorrect specifications.
    Criminal liability protection for life-safety systems.
    """

    def __init__(self, country_code: str):
        self.country_code = country_code
        super().__init__(
            f"Country '{country_code}' has no registered regulatory framework. "
            f"Cannot produce legal specifications without confirmed framework. "
            f"Add country to COUNTRY_FRAMEWORK_MAP or request engineer review. "
            f"[Life-safety systems: unknown framework = potential criminal liability]"
        )


# ---------------------------------------------------------------------------
# Country -> Framework mapping (Pydantic RegulatoryFramework)
# ---------------------------------------------------------------------------

# Complete country -> framework mapping
# Fix #5: +15 missing countries added
# Fix #3: Norway -> EFTA (not EU)
# Fix #1: Canada -> CEC_CANADA (Zone system since 1998)
COUNTRY_FRAMEWORK_MAP: Dict[str, RegulatoryFramework] = {
    # EU member states -> ATEX
    "DE": RegulatoryFramework.ATEX_EU,
    "FR": RegulatoryFramework.ATEX_EU,
    "GB": RegulatoryFramework.ATEX_EU,  # Post-Brexit UKEX (treated as ATEX)
    "IT": RegulatoryFramework.ATEX_EU,
    "ES": RegulatoryFramework.ATEX_EU,
    "NL": RegulatoryFramework.ATEX_EU,
    "BE": RegulatoryFramework.ATEX_EU,
    "PL": RegulatoryFramework.ATEX_EU,
    "SE": RegulatoryFramework.ATEX_EU,
    "DK": RegulatoryFramework.ATEX_EU,
    "FI": RegulatoryFramework.ATEX_EU,
    "AT": RegulatoryFramework.ATEX_EU,
    "PT": RegulatoryFramework.ATEX_EU,
    "CZ": RegulatoryFramework.ATEX_EU,
    "HU": RegulatoryFramework.ATEX_EU,
    "RO": RegulatoryFramework.ATEX_EU,
    "GR": RegulatoryFramework.ATEX_EU,
    "IE": RegulatoryFramework.ATEX_EU,
    # EFTA (not EU) — Fix #3
    "NO": RegulatoryFramework.EFTA,  # Norway: EEA but not EU
    "CH": RegulatoryFramework.EFTA,  # Switzerland
    "IS": RegulatoryFramework.EFTA,  # Iceland
    "LI": RegulatoryFramework.EFTA,  # Liechtenstein
    # NEC USA / Mexico
    "US": RegulatoryFramework.NEC_US,
    "MX": RegulatoryFramework.NEC_US,
    # CEC Canada — Fix #1
    "CA": RegulatoryFramework.CEC_CANADA,
    # IECEx international
    "AU": RegulatoryFramework.IECEX,
    "NZ": RegulatoryFramework.IECEX,
    "ZA": RegulatoryFramework.IECEX,
    "BR": RegulatoryFramework.IECEX,
    "JP": RegulatoryFramework.IECEX,
    "KR": RegulatoryFramework.IECEX,
    "CN": RegulatoryFramework.IECEX,
    "IN": RegulatoryFramework.IECEX,
    "RU": RegulatoryFramework.IECEX,
    "SA": RegulatoryFramework.IECEX,
    "AE": RegulatoryFramework.IECEX,
    "QA": RegulatoryFramework.IECEX,
    "KW": RegulatoryFramework.IECEX,
    # Fix #5: +15 missing countries
    "EG": RegulatoryFramework.IECEX,
    "NG": RegulatoryFramework.IECEX,
    "SG": RegulatoryFramework.IECEX,
    "MY": RegulatoryFramework.IECEX,
    "ID": RegulatoryFramework.IECEX,
    "TR": RegulatoryFramework.IECEX,
    "TH": RegulatoryFramework.IECEX,
    "PH": RegulatoryFramework.IECEX,
    "VN": RegulatoryFramework.IECEX,
    "PK": RegulatoryFramework.IECEX,
    "CO": RegulatoryFramework.IECEX,
    "AR": RegulatoryFramework.IECEX,
    "CL": RegulatoryFramework.IECEX,
    "IR": RegulatoryFramework.IECEX,
    "IL": RegulatoryFramework.IECEX,
    # Additional common names
    "USA": RegulatoryFramework.NEC_US,
    "CANADA": RegulatoryFramework.CEC_CANADA,
    "GERMANY": RegulatoryFramework.ATEX_EU,
    "FRANCE": RegulatoryFramework.ATEX_EU,
    "NORWAY": RegulatoryFramework.EFTA,
    "SWITZERLAND": RegulatoryFramework.EFTA,
    "ICELAND": RegulatoryFramework.EFTA,
    "AUSTRALIA": RegulatoryFramework.IECEX,
    "RUSSIA": RegulatoryFramework.IECEX,
    "CHINA": RegulatoryFramework.IECEX,
    "JAPAN": RegulatoryFramework.IECEX,
    "BRAZIL": RegulatoryFramework.IECEX,
    "INDIA": RegulatoryFramework.IECEX,
    "SAUDI ARABIA": RegulatoryFramework.IECEX,
    "UAE": RegulatoryFramework.IECEX,
    "EGYPT": RegulatoryFramework.IECEX,
    "IRAN": RegulatoryFramework.IECEX,
    "SINGAPORE": RegulatoryFramework.IECEX,
    "MALAYSIA": RegulatoryFramework.IECEX,
    "INDONESIA": RegulatoryFramework.IECEX,
    "TURKEY": RegulatoryFramework.IECEX,
    "TURKIYE": RegulatoryFramework.IECEX,
    "SOUTH AFRICA": RegulatoryFramework.IECEX,
    "SOUTH KOREA": RegulatoryFramework.IECEX,
}

_ZONE_SYSTEM = {
    RegulatoryFramework.ATEX_EU: "ZONE",
    RegulatoryFramework.IECEX: "ZONE",
    RegulatoryFramework.CEC_CANADA: "ZONE",  # Fix #1: Canada uses Zone since 1998
    RegulatoryFramework.EFTA: "ZONE",
    RegulatoryFramework.NEC_US: "DIVISION",
}

# Fix #2: Division-to-Zone conversion with hazard class distinction
# Fix #4: CLASS_III (fibers) has no IEC equivalent
_DIVISION_TO_ZONE: Dict[Tuple[str, str], Optional[str]] = {
    # Gas (CLASS_I)
    ("DIVISION_1", "CLASS_I"): "ZONE_1",
    ("DIVISION_2", "CLASS_I"): "ZONE_2",
    # Dust (CLASS_II) — separate from gas groups
    ("DIVISION_1", "CLASS_II"): "ZONE_21",
    ("DIVISION_2", "CLASS_II"): "ZONE_22",
    # CLASS_III (fibers): NO IEC EQUIVALENT — Fix #4
    ("DIVISION_1", "CLASS_III"): None,
    ("DIVISION_2", "CLASS_III"): None,
}

# Legacy dataclass-based RegulatoryFramework for backward compatibility
from dataclasses import dataclass as _dataclass


@_dataclass(frozen=True)
class RegulatoryFrameworkLegacy:
    """Legacy regulatory framework dataclass — for backward compatibility."""

    region: JurisdictionRegion
    system: HazardSystem
    primary_standard: str
    secondary_standards: Tuple[str, ...] = ()
    atex_directive: Optional[str] = None
    iec_standard: Optional[str] = None
    zone_based: bool = True
    requires_notified_body: bool = False
    equipment_marking: str = ""
    legal_note: str = ""


# Legacy framework definitions
_FRAMEWORKS: Dict[HazardSystem, RegulatoryFrameworkLegacy] = {
    HazardSystem.NEC_DIVISION: RegulatoryFrameworkLegacy(
        region=JurisdictionRegion.USA,
        system=HazardSystem.NEC_DIVISION,
        primary_standard="NFPA 70-2023 Art. 500-506",
        secondary_standards=(
            "OSHA 29 CFR 1910.307",
            "API RP 505",
            "NFPA 497 (Gas/Vapor)",
            "NFPA 499 (Dust)",
        ),
        zone_based=False,
        requires_notified_body=False,
        equipment_marking="AEx",
        legal_note="Division system. Equipment must be listed by NRTL.",
    ),
    HazardSystem.CEC_ZONE: RegulatoryFrameworkLegacy(
        region=JurisdictionRegion.CANADA,
        system=HazardSystem.CEC_ZONE,
        primary_standard="CEC Section 18 / CSA C22.1",
        secondary_standards=(
            "CEC Section 18 (Zone classification)",
            "CSA C22.2 No. 30",
            "CSA C22.2 No. 213",
        ),
        zone_based=True,
        requires_notified_body=False,
        equipment_marking="Ex",
        legal_note="Canada uses Zone classification per CEC Section 18 since 1998.",
    ),
    HazardSystem.ATEX_ZONE: RegulatoryFrameworkLegacy(
        region=JurisdictionRegion.EU,
        system=HazardSystem.ATEX_ZONE,
        primary_standard="EN 60079 series / IEC 60079",
        secondary_standards=(
            "ATEX Directive 2014/34/EU",
            "ATEX Directive 1999/92/EC",
            "EN 13463 (non-electrical)",
        ),
        atex_directive="2014/34/EU",
        iec_standard="IEC 60079-0",
        zone_based=True,
        requires_notified_body=True,
        equipment_marking="Ex",
        legal_note="Zone system. Category 1 equipment requires Notified Body.",
    ),
    HazardSystem.IECEX_ZONE: RegulatoryFrameworkLegacy(
        region=JurisdictionRegion.GLOBAL,
        system=HazardSystem.IECEX_ZONE,
        primary_standard="IEC 60079 series",
        secondary_standards=(
            "IEC 60079-10-1",
            "IEC 60079-10-2",
            "IEC 60079-14",
            "IEC 60079-17",
        ),
        iec_standard="IEC 60079-0",
        zone_based=True,
        requires_notified_body=False,
        equipment_marking="Ex",
        legal_note="IECEx scheme accepted in 50+ countries.",
    ),
    HazardSystem.AS_NZS_ZONE: RegulatoryFrameworkLegacy(
        region=JurisdictionRegion.AUSTRALIA,
        system=HazardSystem.AS_NZS_ZONE,
        primary_standard="AS/NZS 60079 series",
        secondary_standards=("AS/NZS 60079-10-1", "AS/NZS 60079-10-2"),
        iec_standard="IEC 60079-0",
        zone_based=True,
        requires_notified_body=False,
        equipment_marking="Ex",
        legal_note="AS/NZS 60079 mirrors IEC 60079.",
    ),
    HazardSystem.GOST_ZONE: RegulatoryFrameworkLegacy(
        region=JurisdictionRegion.RUSSIA,
        system=HazardSystem.GOST_ZONE,
        primary_standard="GOST R 51330 series",
        secondary_standards=("TR CU 012/2011", "PUE"),
        zone_based=True,
        requires_notified_body=True,
        equipment_marking="Ex (1ExG / 1ExD)",
        legal_note="Russia/CIS uses GOST R 51330. EAC Ex certification required.",
    ),
    HazardSystem.GB_ZONE: RegulatoryFrameworkLegacy(
        region=JurisdictionRegion.CHINA,
        system=HazardSystem.GB_ZONE,
        primary_standard="GB 3836 series",
        secondary_standards=("GB/T 3836.15", "GB 50058"),
        zone_based=True,
        requires_notified_body=True,
        equipment_marking="Ex (CNEx)",
        legal_note="China uses GB 3836. CNAS/CNEx certification required.",
    ),
}

# Country -> Region mapping (for legacy interface)
_COUNTRY_TO_REGION: Dict[str, JurisdictionRegion] = {
    "US": JurisdictionRegion.USA,
    "USA": JurisdictionRegion.USA,
    "UNITED STATES": JurisdictionRegion.USA,
    "CA": JurisdictionRegion.CANADA,
    "CANADA": JurisdictionRegion.CANADA,
    "DE": JurisdictionRegion.EU,
    "GERMANY": JurisdictionRegion.EU,
    "FR": JurisdictionRegion.EU,
    "FRANCE": JurisdictionRegion.EU,
    "IT": JurisdictionRegion.EU,
    "ITALY": JurisdictionRegion.EU,
    "ES": JurisdictionRegion.EU,
    "SPAIN": JurisdictionRegion.EU,
    "NL": JurisdictionRegion.EU,
    "NETHERLANDS": JurisdictionRegion.EU,
    "BE": JurisdictionRegion.EU,
    "BELGIUM": JurisdictionRegion.EU,
    "PL": JurisdictionRegion.EU,
    "POLAND": JurisdictionRegion.EU,
    "SE": JurisdictionRegion.EU,
    "SWEDEN": JurisdictionRegion.EU,
    "DK": JurisdictionRegion.EU,
    "DENMARK": JurisdictionRegion.EU,
    "FI": JurisdictionRegion.EU,
    "FINLAND": JurisdictionRegion.EU,
    "AT": JurisdictionRegion.EU,
    "AUSTRIA": JurisdictionRegion.EU,
    "PT": JurisdictionRegion.EU,
    "PORTUGAL": JurisdictionRegion.EU,
    "GR": JurisdictionRegion.EU,
    "GREECE": JurisdictionRegion.EU,
    "CZ": JurisdictionRegion.EU,
    "CZECH REPUBLIC": JurisdictionRegion.EU,
    "RO": JurisdictionRegion.EU,
    "ROMANIA": JurisdictionRegion.EU,
    "HU": JurisdictionRegion.EU,
    "HUNGARY": JurisdictionRegion.EU,
    "IE": JurisdictionRegion.EU,
    "IRELAND": JurisdictionRegion.EU,
    "NO": JurisdictionRegion.EFTA,
    "NORWAY": JurisdictionRegion.EFTA,
    "CH": JurisdictionRegion.EFTA,
    "SWITZERLAND": JurisdictionRegion.EFTA,
    "IS": JurisdictionRegion.EFTA,
    "ICELAND": JurisdictionRegion.EFTA,
    "LI": JurisdictionRegion.EFTA,
    "LIECHTENSTEIN": JurisdictionRegion.EFTA,
    "GB": JurisdictionRegion.UK,
    "UK": JurisdictionRegion.UK,
    "AU": JurisdictionRegion.AUSTRALIA,
    "AUSTRALIA": JurisdictionRegion.AUSTRALIA,
    "NZ": JurisdictionRegion.NEW_ZEALAND,
    "NEW ZEALAND": JurisdictionRegion.NEW_ZEALAND,
    "RU": JurisdictionRegion.RUSSIA,
    "RUSSIA": JurisdictionRegion.RUSSIA,
    "CN": JurisdictionRegion.CHINA,
    "CHINA": JurisdictionRegion.CHINA,
    "JP": JurisdictionRegion.JAPAN,
    "JAPAN": JurisdictionRegion.JAPAN,
    "KR": JurisdictionRegion.SOUTH_KOREA,
    "SOUTH KOREA": JurisdictionRegion.SOUTH_KOREA,
    "SG": JurisdictionRegion.ASEAN,
    "SINGAPORE": JurisdictionRegion.ASEAN,
    "MY": JurisdictionRegion.ASEAN,
    "MALAYSIA": JurisdictionRegion.ASEAN,
    "ID": JurisdictionRegion.ASEAN,
    "INDONESIA": JurisdictionRegion.ASEAN,
    "TH": JurisdictionRegion.ASEAN,
    "THAILAND": JurisdictionRegion.ASEAN,
    "PH": JurisdictionRegion.ASEAN,
    "PHILIPPINES": JurisdictionRegion.ASEAN,
    "VN": JurisdictionRegion.ASEAN,
    "VIETNAM": JurisdictionRegion.ASEAN,
    "TR": JurisdictionRegion.TURKEY,
    "TURKEY": JurisdictionRegion.TURKEY,
    "BR": JurisdictionRegion.BRAZIL,
    "BRAZIL": JurisdictionRegion.BRAZIL,
    "CO": JurisdictionRegion.SOUTH_AMERICA,
    "COLOMBIA": JurisdictionRegion.SOUTH_AMERICA,
    "AR": JurisdictionRegion.SOUTH_AMERICA,
    "ARGENTINA": JurisdictionRegion.SOUTH_AMERICA,
    "CL": JurisdictionRegion.SOUTH_AMERICA,
    "CHILE": JurisdictionRegion.SOUTH_AMERICA,
    "SA": JurisdictionRegion.MIDDLE_EAST,
    "SAUDI ARABIA": JurisdictionRegion.MIDDLE_EAST,
    "AE": JurisdictionRegion.MIDDLE_EAST,
    "UAE": JurisdictionRegion.MIDDLE_EAST,
    "QA": JurisdictionRegion.MIDDLE_EAST,
    "QATAR": JurisdictionRegion.MIDDLE_EAST,
    "KW": JurisdictionRegion.MIDDLE_EAST,
    "KUWAIT": JurisdictionRegion.MIDDLE_EAST,
    "IR": JurisdictionRegion.MIDDLE_EAST,
    "IRAN": JurisdictionRegion.MIDDLE_EAST,
    "IN": JurisdictionRegion.INDIA,
    "INDIA": JurisdictionRegion.INDIA,
    "PK": JurisdictionRegion.CENTRAL_ASIA,
    "PAKISTAN": JurisdictionRegion.CENTRAL_ASIA,
    "ZA": JurisdictionRegion.SOUTH_AFRICA,
    "SOUTH AFRICA": JurisdictionRegion.SOUTH_AFRICA,
    "EG": JurisdictionRegion.NORTH_AFRICA,
    "EGYPT": JurisdictionRegion.NORTH_AFRICA,
    "NG": JurisdictionRegion.WEST_AFRICA,
    "NIGERIA": JurisdictionRegion.WEST_AFRICA,
}

_REGION_TO_SYSTEM: Dict[JurisdictionRegion, HazardSystem] = {
    JurisdictionRegion.USA: HazardSystem.NEC_DIVISION,
    JurisdictionRegion.CANADA: HazardSystem.CEC_ZONE,
    JurisdictionRegion.EU: HazardSystem.ATEX_ZONE,
    JurisdictionRegion.EFTA: HazardSystem.ATEX_ZONE,
    JurisdictionRegion.UK: HazardSystem.ATEX_ZONE,
    JurisdictionRegion.AUSTRALIA: HazardSystem.AS_NZS_ZONE,
    JurisdictionRegion.NEW_ZEALAND: HazardSystem.AS_NZS_ZONE,
    JurisdictionRegion.RUSSIA: HazardSystem.GOST_ZONE,
    JurisdictionRegion.KAZAKHSTAN: HazardSystem.GOST_ZONE,
    JurisdictionRegion.CHINA: HazardSystem.GB_ZONE,
    JurisdictionRegion.JAPAN: HazardSystem.IECEX_ZONE,
    JurisdictionRegion.SOUTH_KOREA: HazardSystem.IECEX_ZONE,
    JurisdictionRegion.BRAZIL: HazardSystem.IECEX_ZONE,
    JurisdictionRegion.MIDDLE_EAST: HazardSystem.IECEX_ZONE,
    JurisdictionRegion.INDIA: HazardSystem.IECEX_ZONE,
    JurisdictionRegion.SOUTH_AFRICA: HazardSystem.IECEX_ZONE,
    JurisdictionRegion.ASEAN: HazardSystem.IECEX_ZONE,
    JurisdictionRegion.TURKEY: HazardSystem.IECEX_ZONE,
    JurisdictionRegion.NORTH_AFRICA: HazardSystem.IECEX_ZONE,
    JurisdictionRegion.WEST_AFRICA: HazardSystem.IECEX_ZONE,  # Nigeria, Ghana etc. use IECEx
    JurisdictionRegion.SOUTH_AMERICA: HazardSystem.IECEX_ZONE,
    JurisdictionRegion.CENTRAL_ASIA: HazardSystem.IECEX_ZONE,
    JurisdictionRegion.GLOBAL: HazardSystem.IECEX_ZONE,
}

# Zone <-> Division conversion maps (legacy)
DIVISION_TO_ZONE: Dict[Tuple[NECDivision, HazardClass], Optional[ATEXZone]] = {
    (NECDivision.DIVISION_1, HazardClass.CLASS_I): ATEXZone.ZONE_1,
    (NECDivision.DIVISION_2, HazardClass.CLASS_I): ATEXZone.ZONE_2,
    (NECDivision.DIVISION_1, HazardClass.CLASS_II): ATEXZone.ZONE_21,
    (NECDivision.DIVISION_2, HazardClass.CLASS_II): ATEXZone.ZONE_22,
    (NECDivision.DIVISION_1, HazardClass.GAS_VAPOR): ATEXZone.ZONE_1,
    (NECDivision.DIVISION_2, HazardClass.GAS_VAPOR): ATEXZone.ZONE_2,
    (NECDivision.DIVISION_1, HazardClass.DUST): ATEXZone.ZONE_21,
    (NECDivision.DIVISION_2, HazardClass.DUST): ATEXZone.ZONE_22,
    (NECDivision.DIVISION_1, HazardClass.CLASS_III): None,
    (NECDivision.DIVISION_2, HazardClass.CLASS_III): None,
}

ZONE_TO_DIVISION: Dict[ATEXZone, Tuple[NECDivision, HazardClass]] = {
    ATEXZone.ZONE_0: (NECDivision.DIVISION_1, HazardClass.CLASS_I),
    ATEXZone.ZONE_1: (NECDivision.DIVISION_1, HazardClass.CLASS_I),
    ATEXZone.ZONE_2: (NECDivision.DIVISION_2, HazardClass.CLASS_I),
    ATEXZone.ZONE_20: (NECDivision.DIVISION_1, HazardClass.CLASS_II),
    ATEXZone.ZONE_21: (NECDivision.DIVISION_1, HazardClass.CLASS_II),
    ATEXZone.ZONE_22: (NECDivision.DIVISION_2, HazardClass.CLASS_II),
}


# ---------------------------------------------------------------------------
# V21 resolve() — raises UnknownCountryError, no silent fallback
# ---------------------------------------------------------------------------


def resolve(country_code: str) -> RegSelectorResult:
    """Resolve regulatory framework for a country.

    RAISES UnknownCountryError if country not in database.
    Never silently falls back to IECEx.
    """
    code = country_code.upper().strip()
    if code not in COUNTRY_FRAMEWORK_MAP:
        raise UnknownCountryError(code)

    framework = COUNTRY_FRAMEWORK_MAP[code]
    warnings: List[str] = []

    if framework == RegulatoryFramework.EFTA:
        warnings.append(
            f"Country '{code}' is EFTA (not EU member). "
            f"ATEX 2014/34/EU applies via EEA Agreement. "
            f"Verify local transposition (e.g. Norway DSB regulations)."
        )

    return RegSelectorResult(
        country_code=code,
        framework=framework,
        zone_system=_ZONE_SYSTEM[framework],
        warnings=warnings,
    )


def convert_division_to_zone(
    division: str,
    hazard_class: str,
) -> str:
    """Fix #2: Convert NEC Division/Class to IEC Zone.
    hazard_class MUST be provided — CLASS_I(gas) != CLASS_II(dust).
    CLASS_III has NO IEC equivalent.

    Returns zone string or raises ValueError.
    """
    key = (division.upper(), hazard_class.upper())
    result = _DIVISION_TO_ZONE.get(key)

    if key not in _DIVISION_TO_ZONE:
        raise ValueError(
            f"Unknown division/class combination: {division}/{hazard_class}. "
            f"Valid: CLASS_I, CLASS_II, CLASS_III. [NFPA 70 Art. 500]"
        )
    if result is None:
        raise ValueError(
            "CLASS_III (combustible fibers) has NO IEC Zone equivalent. "
            "NFPA 70 Art. 503 only. Cannot convert to Zone system. "
            "[Fix #4]"
        )
    return result


# ---------------------------------------------------------------------------
# Legacy InternationalRegSelector class — backward compatible
# ---------------------------------------------------------------------------


@_dataclass(frozen=True)
class JurisdictionResult:
    """Result of jurisdiction resolution (legacy)."""

    country_input: str
    region: JurisdictionRegion
    framework: RegulatoryFrameworkLegacy
    equivalent_zone: Optional[ATEXZone] = None
    equivalent_division: Optional[NECDivision] = None
    warnings: Tuple[str, ...] = ()
    errors: Tuple[str, ...] = ()

    @property
    def is_valid(self) -> bool:
        return len(self.errors) == 0

    @property
    def system(self) -> HazardSystem:
        return self.framework.system


class InternationalRegSelector:
    """Resolves project country/region to the correct regulatory framework.

    This is a LEGAL GATE. Using the wrong system is a legal violation.

    V21: resolve_v21() uses Pydantic RegSelectorResult + raises on unknown.
    Legacy: resolve() still available with warning-based fallback.
    """

    def resolve_v21(self, country: str) -> RegSelectorResult:
        """V21 interface — raises UnknownCountryError on unknown country."""
        return resolve(country)

    def resolve(
        self,
        country: str,
        override_system: Optional[HazardSystem] = None,
    ) -> JurisdictionResult:
        """Legacy resolve — still uses warning-based fallback for unknown countries.
        Prefer resolve_v21() for new code.
        """
        key = country.upper().strip()
        region = _COUNTRY_TO_REGION.get(key, JurisdictionRegion.GLOBAL)
        system = _REGION_TO_SYSTEM.get(region, HazardSystem.IECEX_ZONE)

        warnings: List[str] = []
        errors: List[str] = []

        if region == JurisdictionRegion.GLOBAL:
            warnings.append(
                f"Country {country!r} not in jurisdiction database. "
                "Defaulting to IECEx Zone system. "
                "Verify local regulations before submission."
            )

        if region == JurisdictionRegion.EFTA:
            if key in ("NO", "NORWAY"):
                warnings.append(
                    "Norway uses ATEX via EEA agreement. Local regulator: DSB. Verify specific Norwegian requirements."
                )
            elif key in ("CH", "SWITZERLAND"):
                warnings.append(
                    "Switzerland uses EN 60079 / ATEX-compatible standards "
                    "via bilateral agreements, but is NOT in EU/EEA. "
                    "Equipment must comply with SEV/SUVI requirements."
                )

        if region == JurisdictionRegion.CANADA and override_system == HazardSystem.NEC_DIVISION:
            warnings.append(
                "LEGAL WARNING: Canada has mandated Zone classification per "
                "CEC Section 18 since 1998. Using NEC Division system is only "
                "permitted for EXISTING installations (CEC 18-002)."
            )

        if override_system is not None and override_system != system:
            if not (region == JurisdictionRegion.CANADA and override_system == HazardSystem.NEC_DIVISION):
                warnings.append(
                    f"System overridden from {system.value} to "
                    f"{override_system.value} for {country!r}. "
                    "LEGAL WARNING: ensure override is permitted by local AHJ."
                )
            system = override_system

        framework = _FRAMEWORKS.get(system, _FRAMEWORKS[HazardSystem.IECEX_ZONE])

        return JurisdictionResult(
            country_input=country,
            region=region,
            framework=framework,
            warnings=tuple(warnings),
            errors=tuple(errors),
        )

    def convert_zone_to_division(
        self,
        zone: ATEXZone,
        hazard_class: HazardClass = HazardClass.CLASS_I,
    ) -> Optional[NECDivision]:
        """Convert ATEX Zone to NEC Division equivalent."""
        mapping = ZONE_TO_DIVISION.get(zone)
        if mapping is None:
            return None
        div, mapped_class = mapping

        if mapped_class != hazard_class and hazard_class not in (HazardClass.CLASS_I, HazardClass.GAS_VAPOR):
            logger.warning(
                "Zone %s maps to %s/%s but requested hazard_class=%s. Verify equipment group compatibility.",
                zone.value,
                div.value,
                mapped_class.value,
                hazard_class.value,
            )
        return div

    def convert_division_to_zone(
        self,
        division: NECDivision,
        hazard_class: HazardClass = HazardClass.CLASS_I,
    ) -> Optional[ATEXZone]:
        """Convert NEC Division to ATEX Zone equivalent."""
        result = DIVISION_TO_ZONE.get((division, hazard_class))

        if result is None and hazard_class == HazardClass.CLASS_III:
            logger.warning(
                "CLASS_III (ignitable fibers, NFPA 70 Art. 503) has no IEC 60079 zone equivalent. Use NFPA 70 Art. 503."
            )

        return result

    def list_supported_countries(self) -> List[str]:
        return sorted(_COUNTRY_TO_REGION.keys())

    def get_framework(self, system: HazardSystem) -> RegulatoryFrameworkLegacy:
        return _FRAMEWORKS[system]
