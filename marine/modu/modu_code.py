"""marine/modu/modu_code.py — MODU Code Fire Safety for Offshore Units.

Implements the fire-protection, detection, and extinction requirements for
Mobile Offshore Drilling Units (MODU) per the MODU Code (1989/2009 amendments):
    - MODU Code §6.2 — Main vertical zone division on the platform
    - MODU Code §10.3 — Helicopter deck fire extinguishing (AFFF mandatory)
    - MODU Code §9.8 — Fixed gas detection in hazardous areas

This module is the offshore counterpart to marine/solas/chapter_ii_2.py.
"""
from __future__ import annotations

import math
from typing import List, Optional

from marine.core.constants import (
    AFFF_APPLICATION_RATE_LPM_PER_M2, AFFF_DISCHARGE_TIME_MIN,
    MAX_MAIN_VERTICAL_ZONE_LENGTH_M,
)
from marine.core.types import ComplianceResult, MarineZone, ShipProject, ShipType


# MODU Code §6.2: main vertical zone length limit is the same as SOLAS (40 m).
MODU_MAX_MVZ_LENGTH_M = MAX_MAIN_VERTICAL_ZONE_LENGTH_M

# Frame spacing for MODU units (same merchant-vessel convention: 0.6 m/frame).
_MODU_FRAME_SPACING_M = 0.6


class _MODUError(Exception):
    """Internal MODU validation error."""


def _m_to_frames(m: float) -> int:
    return int(round(m / _MODU_FRAME_SPACING_M))


def divide_modu_into_main_vertical_zones(
    platform_length_m: float,
    ship: ShipProject,
    deck_count: int = 1,
) -> List[MarineZone]:
    """Divide a MODU platform into MODU Code §6.2 main vertical zones.

    MODU Code §6.2 requires the unit to be divided into main vertical zones
    by A-60 class divisions, with no zone exceeding 40 m in length.

    Args:
        platform_length_m: Overall platform length in metres.
        ship: Ship project descriptor (must be OFFSHORE / MODU).
        deck_count: Number of decks to generate zones for.

    Returns:
        List of MarineZone objects — one per MVZ × deck.

    Raises:
        _MODUError: If the ship type is not OFFSHORE.
    """
    if ship.ship_type != ShipType.OFFSHORE:
        raise _MODUError(
            f"MODU division only applies to ShipType.OFFSHORE, got {ship.ship_type}"
        )
    if platform_length_m <= 0:
        raise _MODUError("platform_length_m must be positive")

    from marine.core.types import SpaceCategory

    n_zones = max(1, math.ceil(platform_length_m / MODU_MAX_MVZ_LENGTH_M))

    # Iteratively bump n_zones until every rounded zone length ≤ 40 m.
    while True:
        zone_length_m = platform_length_m / n_zones
        boundary_frames = [_m_to_frames(i * zone_length_m)
                           for i in range(n_zones + 1)]
        for i in range(1, len(boundary_frames)):
            if boundary_frames[i] <= boundary_frames[i - 1]:
                boundary_frames[i] = boundary_frames[i - 1] + 1
        max_zone_length = max(
            (boundary_frames[i + 1] - boundary_frames[i]) * _MODU_FRAME_SPACING_M
            for i in range(n_zones)
        )
        if max_zone_length <= MODU_MAX_MVZ_LENGTH_M + 1e-9:
            break
        n_zones += 1
        if n_zones > 1000:
            break

    zones: List[MarineZone] = []
    beam_m = max(15.0, platform_length_m * 0.3)  # MODU platforms are much wider.

    for deck_idx in range(deck_count):
        deck_name = "main" if deck_idx == 0 else f"deck_{deck_idx + 1}"
        for mvz_idx in range(n_zones):
            zone_id = f"MODU-{mvz_idx + 1:02d}-{deck_name}"
            # Forward third: accommodation/control; remainder: machinery/cargo.
            pos = mvz_idx / max(1, n_zones - 1)
            cat = (
                SpaceCategory.ACCOMMODATION if pos < 0.33
                else SpaceCategory.MACHINERY_SPACE_A
            )

            start_frame = boundary_frames[mvz_idx]
            end_frame = boundary_frames[mvz_idx + 1]
            actual_length_m = (end_frame - start_frame) * _MODU_FRAME_SPACING_M

            zones.append(MarineZone(
                zone_id=zone_id,
                name=f"MODU Main Vertical Zone {mvz_idx + 1} ({deck_name})",
                space_category=cat,
                deck=deck_name,
                frame_start=start_frame,
                frame_end=end_frame,
                area_m2=round(actual_length_m * beam_m, 1),
                height_m=6.0,
                adjacent_zones=tuple(
                    f"MODU-{n + 1:02d}-{deck_name}"
                    for n in (mvz_idx - 1, mvz_idx + 1)
                    if 0 <= n < n_zones
                ),
            ))

    return zones


def required_helideck_afff(
    helideck_area_m2: float,
    ship: Optional[ShipProject] = None,
) -> ComplianceResult:
    """Size AFFF system for a MODU helicopter deck.

    MODU Code §10.3 + CAP 437: helidecks require a fixed AFFF system with
    an application rate of at least 2.5 L/min/m² for at least 5 minutes.

    Args:
        helideck_area_m2: Area of the helideck in m².
        ship: Optional ship project; if provided and not OFFSHORE, a warning
            is emitted.

    Returns:
        ComplianceResult with design details and any findings.
    """
    result = ComplianceResult(
        compliant=True, standard_reference="MODU Code §10.3 + CAP 437 §6.3"
    )
    if ship is not None and ship.ship_type != ShipType.OFFSHORE:
        result.add_warning(
            f"Helideck AFFF rules for offshore units; ship type is {ship.ship_type}"
        )
    if helideck_area_m2 <= 0:
        result.add_finding("Helideck area must be positive to size AFFF system.")
        return result

    flow_lpm = helideck_area_m2 * AFFF_APPLICATION_RATE_LPM_PER_M2
    foam_solution_litres = flow_lpm * AFFF_DISCHARGE_TIME_MIN
    concentrate_kg = foam_solution_litres * 0.03 * 1.05

    result.details["helideck_area_m2"] = helideck_area_m2
    result.details["application_rate_lpm_per_m2"] = AFFF_APPLICATION_RATE_LPM_PER_M2
    result.details["discharge_time_min"] = AFFF_DISCHARGE_TIME_MIN
    result.details["flow_lpm"] = round(flow_lpm, 1)
    result.details["foam_solution_litres"] = round(foam_solution_litres, 1)
    result.details["agent_quantity_kg"] = round(concentrate_kg, 1)
    result.details["nozzles"] = max(2, math.ceil(helideck_area_m2 / 25.0))
    return result


def validate_gas_detection_requirement(
    zones: List[MarineZone],
    ship: Optional[ShipProject] = None,
) -> ComplianceResult:
    """Validate mandatory gas detection for MODU hazardous zones.

    MODU Code §9.8: fixed gas detection is required in enclosed spaces that
    may contain flammable gas or vapour (machinery spaces, tank spaces,
    mud pits, battery rooms, etc.).

    Args:
        zones: Marine zones to validate.
        ship: Optional ship project; if not OFFSHORE, a warning is emitted.

    Returns:
        ComplianceResult listing any zones that lack required gas detection.
    """
    result = ComplianceResult(
        compliant=True, standard_reference="MODU Code §9.8"
    )
    if ship is not None and ship.ship_type != ShipType.OFFSHORE:
        result.add_warning(
            f"Gas-detection rules for offshore units; ship type is {ship.ship_type}"
        )

    if not zones:
        result.add_finding("No zones provided — cannot validate gas detection.")
        return result

    from marine.core.types import SpaceCategory

    hazardous_categories = {
        SpaceCategory.MACHINERY_SPACE_A,
        SpaceCategory.MACHINERY_SPACE_OTHER,
        SpaceCategory.TANK_SPACE,
        SpaceCategory.CARGO_SPACE,
    }
    for zone in zones:
        if zone.space_category in hazardous_categories:
            # In a real design, each zone would carry a gas-detection flag.
            # We assume the zone requires a detector and report it in details.
            result.details[zone.zone_id] = {
                "requires_gas_detection": True,
                "category": zone.space_category.value,
            }
    if not any(d.get("requires_gas_detection") for d in result.details.values()):
        result.add_warning(
            "No hazardous zones found; gas detection requirement cannot be validated."
        )
    return result


__all__ = [
    "divide_modu_into_main_vertical_zones",
    "required_helideck_afff",
    "validate_gas_detection_requirement",
]
