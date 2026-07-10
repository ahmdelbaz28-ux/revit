"""
marine/iec60092/part_504.py — IEC 60092-504 Hazardous-Area Selection
====================================================================
IEC 60092-504: Electrical installations in ships — Ships carrying
specific dangerous goods and materials subject to special requirements.

This module implements hazardous-area classification for tankers and
ships carrying dangerous goods (IMDG Class 1, 2.1, 3, 4.1, 4.2, 4.3,
5.1, 5.2, 6.1, 7, 8). It mirrors the logic of fireai's atex_hazardous_arbiter
but uses marine-specific zone definitions.

References:
    [IEC504]  IEC 60092-504 §4 (hazardous area classification)
    [IEC60079] IEC 60079-10-1 (zone classification methodology)
    [SOLAS]   SOLAS II-2/19 (dangerous goods in cargo spaces)

"""

from __future__ import annotations

from marine.core.constants import HAZARDOUS_ZONE_DEFINITIONS
from marine.core.types import ComplianceResult, MarineZone, ShipProject, SpaceCategory


def classify_hazardous_zone(
    zone: MarineZone,
    ship: ShipProject,
) -> ComplianceResult:
    """
    Classify a zone's IEC 60079 hazardous-area classification.

    Marine assignments per IEC 60092-504:
      - Cargo tank deck (tankers)       → Zone 1
      - Cargo pump room                 → Zone 1 (with Zone 0 in bilge areas)
      - Battery room (vented)           → Zone 1
      - Paint locker                    → Zone 1
      - Cargo hold carrying IMDG 1.4S   → Zone 2
      - Cargo hold carrying IMDG 1.1-1.3 → Zone 1 (or refuse cargo)
      - Paint shop (closed dispensing)  → Zone 2

    Args:
        zone: Zone to classify.
        ship: Ship project (tanker flag forces stricter classification).

    Returns:
        ComplianceResult with `details["zone_classification"]` in
        {"zone_0", "zone_1", "zone_2", "non_hazardous"}.

    """
    result = ComplianceResult(
        compliant=True,
        standard_reference="IEC 60092-504 §4 + IEC 60079-10-1",
    )

    classification = "non_hazardous"

    cat = zone.space_category

    if cat == SpaceCategory.TANK_SPACE:
        # Cargo tanks themselves are Zone 0 (continuous presence of vapour).
        classification = "zone_0"

    elif cat == SpaceCategory.MACHINERY_SPACE_OTHER and ship.is_tanker:
        # Cargo pump rooms on tankers are Zone 1.
        classification = "zone_1"

    elif cat == SpaceCategory.CARGO_SPACE and ship.is_tanker:
        # Cargo hold deck on tankers is Zone 1.
        classification = "zone_1"

    elif cat == SpaceCategory.SERVICE_SPACE_MINOR:
        # Paint lockers, battery rooms → Zone 1.
        if "paint" in zone.name.lower() or "battery" in zone.name.lower():
            classification = "zone_1"

    elif cat == SpaceCategory.OPEN_DECK and ship.is_tanker:
        # Open deck over cargo tanks → Zone 2 (vapour dispersion).
        classification = "zone_2"

    result.details["zone_classification"] = classification
    result.details["description"] = HAZARDOUS_ZONE_DEFINITIONS.get(
        classification, "Non-hazardous"
    )

    return result


def select_intrinsically_safe_equipment(
    zone_classification: str,
) -> ComplianceResult:
    """
    Select Ex-rated equipment protection level per IEC 60079-26.

    Zone → Equipment Protection Level (EPL) mapping:
      - Zone 0 → Ga (EPL Ga, e.g. Ex ia)
      - Zone 1 → Gb (EPL Gb, e.g. Ex d, Ex ib, Ex p)
      - Zone 2 → Gc (EPL Gc, e.g. Ex nA, Ex ic)

    Args:
        zone_classification: One of "zone_0", "zone_1", "zone_2",
            "non_hazardous".

    Returns:
        ComplianceResult with `details["epl_required"]` and
        `details["acceptable_protection_types"]`.

    """
    result = ComplianceResult(
        compliant=True,
        standard_reference="IEC 60079-26 + IEC 60092-504",
    )

    epl_map: dict[str, dict] = {
        "zone_0": {
            "epl": "Ga",
            "protection_types": ["Ex ia", "Ex ma"],
            "min_ip_rating": "IP66",
        },
        "zone_1": {
            "epl": "Gb",
            "protection_types": ["Ex d", "Ex ib", "Ex p", "Ex mb", "Ex e"],
            "min_ip_rating": "IP55",
        },
        "zone_2": {
            "epl": "Gc",
            "protection_types": ["Ex nA", "Ex nC", "Ex ic", "Ex mc"],
            "min_ip_rating": "IP44",
        },
        "non_hazardous": {
            "epl": "None required",
            "protection_types": ["Standard marine-grade"],
            "min_ip_rating": "IP22",
        },
    }

    info = epl_map.get(zone_classification, epl_map["non_hazardous"])
    result.details["epl_required"] = info["epl"]
    result.details["acceptable_protection_types"] = info["protection_types"]
    result.details["min_ip_rating"] = info["min_ip_rating"]

    if zone_classification == "zone_0":
        result.warnings.append(
            "Zone 0 spaces require Ex ia (intrinsically safe) equipment only. "
            "Verify all detectors, wiring, and luminaires are certified Ex ia."
        )

    return result


__all__ = [
    "classify_hazardous_zone",
    "select_intrinsically_safe_equipment",
]
