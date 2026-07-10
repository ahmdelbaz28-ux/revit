# NOSONAR
"""
marine/engine/fire_resistance.py — Fire Division Class Calculator
==================================================================
Implements the "Fire-Resistance" module from the marine agent prompt.

Computes required FireClass (A-60/A-30/A-15/A-0/B-15/B-0/C) for every
bulkhead and deck division on the ship, per SOLAS II-2/9.2 Table 9.1.

Outputs FireResistanceSpec objects ready for material selection, BOM
generation, and Revit family creation.
"""

from __future__ import annotations

from marine.core.constants import INSULATION_THICKNESS_MM
from marine.core.errors import FireClassAssignmentError
from marine.core.types import (
    FireClass,
    FireResistanceSpec,
    MarineZone,
)
from marine.solas.chapter_ii_2 import required_fire_class_between


# ─── Centralised insulation-material selection ───────────────────────────────
# BUGFIX v2: previously generate_division_specs returned "intumescent_board"
# for B-15, while select_insulation_material returned "intumescent_paint".
# Both code paths now share this single function.
def _pick_insulation_material(fire_class: FireClass,
                              ambient_humidity_pct: float = 75.0) -> str | None:
    """
    Pick insulation material for a fire class (single source of truth).

    Marine environments are high-humidity + salty — material must be
    moisture-resistant and non-combustible per SOLAS II-2/3.2.1.
    """
    if fire_class in (FireClass.A_0, FireClass.B_0, FireClass.C):
        return None
    if fire_class.value.startswith("A-"):
        # A-15/A-30/A-60: ceramic wool is marine standard.
        if ambient_humidity_pct > 90:
            return "marine_ceramic_wool_with_vapor_barrier"
        return "ceramic_wool"
    if fire_class == FireClass.B_15:
        return "intumescent_paint"
    return None


def generate_division_specs(  # NOSONAR — S3776: cognitive complexity is inherent to the safety-critical algorithm
    zones: list[MarineZone],
) -> list[FireResistanceSpec]:
    """
    Generate a FireResistanceSpec for every adjacent-zone pair.

    Iterates through all zone pairs where one zone's frame range is
    adjacent to another's, and computes the SOLAS-required FireClass.

    Args:
        zones: List of all MarineZone objects on the ship.

    Returns:
        List of FireResistanceSpec — one per division (bulkhead or deck).

    """
    specs: list[FireResistanceSpec] = []
    seen_pairs: set = set()

    for zone in zones:
        for adj_id in zone.adjacent_zones:
            pair = frozenset((zone.zone_id, adj_id))
            if pair in seen_pairs:
                continue
            seen_pairs.add(pair)

            adj = next((z for z in zones if z.zone_id == adj_id), None)
            if adj is None:
                continue

            try:
                required = required_fire_class_between(
                    zone.space_category, adj.space_category
                )
            except FireClassAssignmentError:
                # BUGFIX v2: previously `except Exception` mapped EVERY error
                # (including KeyboardInterrupt, MemoryError) to A-60 — both
                # overly broad AND over-specifying. Now we only catch the
                # specific error, and default to A-60 as a fail-safe for the
                # marine domain (steel bulkhead, no insulation gap).
                required = FireClass.A_60

            # Material selection: steel for A-class, non-combustible for B/C.
            if required.value.startswith("A-"):
                material = "steel"
                insulation = _pick_insulation_material(required)
                thickness = INSULATION_THICKNESS_MM.get(required.value, 0.0)
            elif required.value.startswith("B-"):
                material = "non_combustible_composite"
                insulation = _pick_insulation_material(required)
                thickness = 12.0 if required == FireClass.B_15 else 0.0
            else:
                material = "non_combustible"
                insulation = _pick_insulation_material(required)
                thickness = 0.0

            specs.append(FireResistanceSpec(
                division_id=f"DIV-{zone.zone_id}-{adj.zone_id}",
                from_zone=zone.zone_id,
                to_zone=adj.zone_id,
                required_class=required,
                material=material,
                insulation_material=insulation,
                insulation_thickness_mm=thickness,
                penetration_protected=True,
                standard_reference="SOLAS II-2/9.2 Table 9.1",
            ))

    return specs


def select_insulation_material(
    fire_class: FireClass,
    ambient_humidity_pct: float = 75.0,
) -> str:
    """
    Select insulation material based on fire class and environment.

    Public wrapper around _pick_insulation_material that returns a friendly
    string instead of None for the "no insulation required" case.
    """
    insulation = _pick_insulation_material(fire_class, ambient_humidity_pct)
    if insulation is None:
        return "none_required"
    return insulation


__all__ = [
    "generate_division_specs",
    "select_insulation_material",
]
