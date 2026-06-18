"""
marine/engine/zone_mapper.py — Marine Zone Division Engine
============================================================
Implements the "Zone-Mapper" module from the marine agent prompt.

Divides the ship into fire-protection zones per SOLAS II-2/2.2 (main
vertical zones ≤40m). Produces MarineZone objects ready for the
detector_selector, fire_resistance, and extinguishment engines.

The mapper takes a list of space rectangles (from a GA plan) and:
    1. Groups them into main vertical zones (≤40m length)
    2. Assigns SOLAS space categories (machinery, accommodation, etc.)
    3. Computes escape-route adjacency
    4. Returns MarineZone objects with all metadata
"""

from __future__ import annotations

import math
from typing import List, Tuple

from marine.core.constants import MAX_MAIN_VERTICAL_ZONE_LENGTH_M
from marine.core.types import (
    ComplianceResult, MarineZone, ShipProject, SpaceCategory,
)

# Frame spacing: typical merchant vessel has ~600 mm between frames.
_FRAMES_PER_METER = 0.6


def divide_into_main_vertical_zones(
    ship_length_m: float,
    ship: ShipProject,
    deck_count: int = 1,
) -> List[MarineZone]:
    """Divide a ship into SOLAS-compliant main vertical zones (MVZs).

    SOLAS II-2/2.2.1: MVZ length ≤ 40 m. The ship is sliced longitudinally
    into N segments where N = ceil(length / 40).

    Args:
        ship_length_m: Length between perpendiculars (LBP) in metres.
        ship: Ship project (for small-craft exemption).
        deck_count: Number of decks to generate zones for.

    Returns:
        List of MarineZone objects — one per MVZ × deck.
    """
    if ship.is_small_craft:
        # NFPA 302 craft: single zone, no MVZ division.
        return [MarineZone(
            zone_id="MVZ-01",
            name="Single craft zone (NFPA 302)",
            space_category=SpaceCategory.ACCOMMODATION,
            deck="main",
            frame_start=0, frame_end=int(ship_length_m / 0.6),
            area_m2=ship_length_m * 4.0,  # assume 4m beam
            height_m=2.2,
        )]

    n_zones = max(1, math.ceil(ship_length_m / MAX_MAIN_VERTICAL_ZONE_LENGTH_M))
    # Cap each zone length strictly at 40m to ensure SOLAS compliance even
    # with frame-rounding. Excess length propagates to an additional zone.
    zone_length_m = min(ship_length_m / n_zones, MAX_MAIN_VERTICAL_ZONE_LENGTH_M)
    zones: List[MarineZone] = []

    for deck_idx in range(deck_count):
        deck_name = "main" if deck_idx == 0 else f"deck_{deck_idx + 1}"
        for mvz_idx in range(n_zones):
            zone_id = f"MVZ-{mvz_idx + 1:02d}-{deck_name}"
            # Assign category based on longitudinal position:
            #   - Forward 1/3  → accommodation / control
            #   - Middle 1/3   → machinery (engine room typically aft-midships)
            #   - Aft 1/3      → cargo / machinery
            pos = mvz_idx / max(1, n_zones - 1)
            if pos < 0.33:
                cat = SpaceCategory.ACCOMMODATION
            elif pos < 0.66:
                cat = SpaceCategory.MACHINERY_SPACE_A
            else:
                cat = SpaceCategory.CARGO_SPACE if not ship.is_passenger_ship \
                    else SpaceCategory.ACCOMMODATION

            # Beam ~ 0.15 * length as typical merchant vessel.
            beam_m = max(4.0, ship_length_m * 0.15)

            # Cap frame count so zone length stays ≤ 40 m (frame spacing 0.6 m).
            # 40 m / 0.6 m = 66.67 → max 66 frames per zone.
            max_frames_per_zone = int(MAX_MAIN_VERTICAL_ZONE_LENGTH_M / _FRAMES_PER_METER)
            start_frame = int(mvz_idx * zone_length_m / _FRAMES_PER_METER)
            end_frame = min(
                start_frame + max_frames_per_zone,
                int(ship_length_m / _FRAMES_PER_METER),
            )
            actual_length_m = (end_frame - start_frame) * _FRAMES_PER_METER

            zones.append(MarineZone(
                zone_id=zone_id,
                name=f"Main Vertical Zone {mvz_idx + 1} ({deck_name})",
                space_category=cat,
                deck=deck_name,
                frame_start=start_frame,
                frame_end=end_frame,
                area_m2=round(actual_length_m * beam_m, 1),
                height_m=2.5,
                adjacent_zones=tuple(
                    f"MVZ-{n + 1:02d}-{deck_name}"
                    for n in (mvz_idx - 1, mvz_idx + 1)
                    if 0 <= n < n_zones
                ),
            ))

    return zones


def assign_space_categories(
    zones: List[MarineZone],
    space_label_map: dict,
) -> List[MarineZone]:
    """Override auto-assigned categories with explicit labels from GA plan.

    Args:
        zones: Pre-divided zones (output of divide_into_main_vertical_zones).
        space_label_map: {zone_id: SpaceCategory} overrides.

    Returns:
        Updated list of MarineZone objects with corrected categories.
    """
    updated = []
    for z in zones:
        if z.zone_id in space_label_map:
            new_cat = space_label_map[z.zone_id]
            # Reconstruct the frozen dataclass with new category.
            updated.append(MarineZone(
                zone_id=z.zone_id, name=z.name, space_category=new_cat,
                deck=z.deck, frame_start=z.frame_start, frame_end=z.frame_end,
                area_m2=z.area_m2, height_m=z.height_m,
                adjacent_zones=z.adjacent_zones,
            ))
        else:
            updated.append(z)
    return updated


def compute_escape_route_adjacency(zones: List[MarineZone]) -> ComplianceResult:
    """Ensure every non-open-deck zone has ≥1 adjacent zone for escape.

    Per SOLAS II-2/13.3.2: every space must have a means of escape to
    open deck. Adjacency is computed from frame ranges.
    """
    result = ComplianceResult(compliant=True, standard_reference="SOLAS II-2/13")
    for z in zones:
        if z.space_category == SpaceCategory.OPEN_DECK:
            continue
        if not z.adjacent_zones:
            result.add_finding(
                f"Zone {z.zone_id} ({z.name}) has no adjacent zones — "
                f"escape-route path to open deck is impossible."
            )
    return result


__all__ = [
    "divide_into_main_vertical_zones",
    "assign_space_categories",
    "compute_escape_route_adjacency",
]
