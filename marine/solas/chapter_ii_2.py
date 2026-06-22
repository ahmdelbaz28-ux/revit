"""
marine/solas/chapter_ii_2.py — IMO SOLAS Chapter II-2 Compliance Engine
========================================================================
Implements the fire-protection, fire-detection, and fire-extinction
requirements of SOLAS Chapter II-2 (Construction — Fire Protection,
Fire Detection, and Fire Extinction), 2024 consolidated edition.

This is the marine counterpart to ``fireai/validation/compliance_engine.py``
(which targets NFPA 72 for buildings).

Coverage:
    - Main vertical zone division (II-2/2.2)
    - Fire division classification (II-2/9.2 + Table 9.1)
    - Escape-route geometry (II-2/13)
    - Detection requirements per space category (II-2/7)
    - Extinguishing requirements per space category (II-2/10)

References:
    [SOLAS] IMO SOLAS Ch. II-2 (2024)
    [FSS]   IMO FSS Code Ch. 9 (fire detection) & Ch. 14 (sprinklers)
"""

from __future__ import annotations

from typing import List

from marine.core.constants import (
    INSULATION_THICKNESS_MM,
    MAX_DISTANCE_TO_STAIRWAY_M,
    MAX_MAIN_VERTICAL_ZONE_LENGTH_M,
    MAX_PASSENGER_MVZ_LENGTH_M,
    MIN_AREA_REQUIRING_TWO_ESCAPES_M2,
    MIN_ESCAPE_ROUTE_HEIGHT_MM,
    MIN_ESCAPE_ROUTE_WIDTH_MM,
    PASSENGER_MVZ_PAX_THRESHOLD,
    SHIP_FRAME_SPACING_M,
    SOLAS_FIRE_DIVISION_MATRIX,
)
from marine.core.types import (
    ComplianceResult,
    FireClass,
    MarineZone,
    ShipProject,
    ShipType,
    SpaceCategory,
)
from marine.core.errors import FireClassAssignmentError, SOLASComplianceError


# ─── Main Vertical Zone Validation ──────────────────────────────────────────

def validate_main_vertical_zones(
    zones: List[MarineZone],
    ship: ShipProject,
) -> ComplianceResult:
    """Validate ship is divided into proper main vertical zones.

    SOLAS II-2/2.2.1: Main vertical zones shall not exceed 40 m in length.
    Passenger ships (>36 passengers) MUST have main vertical zones;
    cargo ships may use horizontal zones as alternative.

    Args:
        zones: All MarineZone objects on the ship.
        ship: Ship project descriptor.

    Returns:
        ComplianceResult with findings for each violation.
    """
    result = ComplianceResult(
        compliant=True, standard_reference="SOLAS II-2/2.2.1"
    )

    if not zones:
        result.add_finding("No zones provided — cannot validate MVZ division.")
        return result

    # Small craft → NFPA 302 applies, SOLAS MVZ rules do not.
    if ship.is_small_craft:
        result.warnings.append(
            "Small craft (<24m LOA) — SOLAS MVZ rules do not apply. "
            "Apply NFPA 302 instead."
        )
        return result

    # Group zones by deck section and check max span.
    # Each zone has frame_start/frame_end — we check the delta.
    # BUGFIX v2: SOLAS II-2/2.2.1.1 mandates a STRICTER limit of 24 m for
    # passenger ships carrying >36 passengers. The previous code applied
    # 40 m uniformly, under-protecting large cruise ships and ferries.
    is_large_passenger = (
        ship.is_passenger_ship
        and ship.passenger_capacity > PASSENGER_MVZ_PAX_THRESHOLD
    )
    mvz_max_m = (
        MAX_PASSENGER_MVZ_LENGTH_M if is_large_passenger
        else MAX_MAIN_VERTICAL_ZONE_LENGTH_M
    )
    for zone in zones:
        zone_length_m = _frames_to_meters(zone.frame_end - zone.frame_start)
        # Tolerance of 0.5 m for frame-rounding (frame spacing ~0.6 m).
        if zone_length_m > mvz_max_m + 0.5:
            rule = (
                f"SOLAS II-2/2.2.1.1 (passenger >{PASSENGER_MVZ_PAX_THRESHOLD} pax)"
                if is_large_passenger else "SOLAS II-2/2.2.1"
            )
            result.add_finding(
                f"Zone {zone.zone_id} ({zone.name}) spans {zone_length_m:.1f} m, "
                f"exceeding {rule} max of {mvz_max_m} m. "
                f"Split into additional MVZs with A-60 bulkheads."
            )
        result.details[zone.zone_id] = {
            "length_m": round(zone_length_m, 2),
            "within_limit": zone_length_m <= mvz_max_m,
            "applied_limit_m": mvz_max_m,
        }

    # Passenger ships >36 passengers require MVZs by II-2/2.2.2.
    if ship.is_passenger_ship and ship.passenger_capacity > 36:
        mvz_count = sum(
            1 for z in zones if z.space_category != SpaceCategory.OPEN_DECK
        )
        if mvz_count < 2:
            result.add_finding(
                f"Passenger ship with {ship.passenger_capacity} passengers "
                f"requires ≥2 main vertical zones per SOLAS II-2/2.2.2. "
                f"Found {mvz_count}."
            )

    return result


# ─── Fire Division Classification (SOLAS II-2/9.2 Table 9.1) ────────────────

def required_fire_class_between(
    from_category: SpaceCategory,
    to_category: SpaceCategory,
) -> FireClass:
    """Determine required FireClass for a division between two space categories.

    Implements SOLAS II-2/9.2 Table 9.1 (the "fire division matrix").
    The matrix specifies the minimum class for bulkheads/decks separating
    adjacent spaces of given categories.

    Args:
        from_category: Space category on one side of the division.
        to_category: Space category on the other side.

    Returns:
        Required FireClass (A-60, A-30, A-15, A-0, B-15, B-0, or C).

    Raises:
        FireClassAssignmentError: If the combination is not in the matrix.
    """
    key = (from_category.value, to_category.value)

    # Try direct lookup.
    class_str = SOLAS_FIRE_DIVISION_MATRIX.get(key)
    if class_str is None:
        # Try reversed (matrix is symmetric).
        rev_key = (to_category.value, from_category.value)
        class_str = SOLAS_FIRE_DIVISION_MATRIX.get(rev_key)

    if class_str is None:
        # Default: A-60 for any unlisted combination involving machinery
        # or cargo spaces; A-0 otherwise; B-0 for accommodation-only pairs.
        cats = {from_category, to_category}
        if SpaceCategory.MACHINERY_SPACE_A in cats or \
           SpaceCategory.CARGO_SPACE in cats:
            class_str = "A-60"
        elif SpaceCategory.MACHINERY_SPACE_OTHER in cats:
            class_str = "A-30"
        elif SpaceCategory.CONTROL_STATION in cats:
            class_str = "A-30"
        elif cats <= {SpaceCategory.ACCOMMODATION, SpaceCategory.SERVICE_SPACE_MINOR,
                      SpaceCategory.ESCAPE_ROUTE}:
            class_str = "B-15"  # Passenger ships; B-0 for cargo ships
        elif SpaceCategory.OPEN_DECK in cats:
            class_str = "A-0"
        else:
            raise FireClassAssignmentError(
                f"Cannot determine FireClass for division between "
                f"{from_category.value} and {to_category.value}. "
                f"Add explicit rule to SOLAS_FIRE_DIVISION_MATRIX."
            )

    return FireClass(class_str)


def validate_fire_divisions(
    zones: List[MarineZone],
    division_specs: List,
) -> ComplianceResult:
    """Validate each fire division meets its required class.

    Args:
        zones: List of MarineZone objects.
        division_specs: List of FireResistanceSpec objects (from_zone, to_zone,
            required_class, insulation_thickness_mm, etc.).

    Returns:
        ComplianceResult listing any under-rated divisions.
    """
    result = ComplianceResult(
        compliant=True, standard_reference="SOLAS II-2/9.2 Table 9.1"
    )
    zone_map = {z.zone_id: z for z in zones}

    for spec in division_specs:
        from_zone = zone_map.get(spec.from_zone)
        to_zone = zone_map.get(spec.to_zone)
        if not from_zone or not to_zone:
            result.add_finding(
                f"Division {spec.division_id}: missing zone reference "
                f"({spec.from_zone} → {spec.to_zone})."
            )
            continue

        # Look up the SOLAS-required class for this space pair.
        try:
            solas_required = required_fire_class_between(
                from_zone.space_category, to_zone.space_category
            )
        except FireClassAssignmentError as e:
            result.add_finding(f"Division {spec.division_id}: {e}")
            continue

        # Check the spec meets or exceeds the required class.
        if not _fire_class_meets_or_exceeds(spec.required_class, solas_required):
            result.add_finding(
                f"Division {spec.division_id} ({spec.from_zone} → {spec.to_zone}): "
                f"specified class {spec.required_class.value} is below SOLAS "
                f"requirement {solas_required.value}."
            )

        # Check insulation thickness if A-class with insulation.
        if spec.required_class.value.startswith("A-") and \
           spec.required_class != FireClass.A_0:
            required_thickness = INSULATION_THICKNESS_MM.get(
                spec.required_class.value, 0.0
            )
            if spec.insulation_thickness_mm < required_thickness:
                result.add_finding(
                    f"Division {spec.division_id}: insulation thickness "
                    f"{spec.insulation_thickness_mm} mm below required "
                    f"{required_thickness} mm for {spec.required_class.value}."
                )

        # Check penetration protection (cable transits, pipe sleeves).
        if spec.required_class.value.startswith("A-") and not spec.penetration_protected:
            result.add_finding(
                f"Division {spec.division_id}: A-class division has unprotected "
                f"penetrations — violates SOLAS II-2/9.3.1."
            )

    return result


# ─── Escape Route Geometry (SOLAS II-2/13) ──────────────────────────────────

def validate_escape_routes(zones: List[MarineZone]) -> ComplianceResult:
    """Validate escape-route geometry per SOLAS II-2/13.

    Rules checked:
      - Every space has ≥1 means of escape (II-2/13.3.2)
      - Spaces >50 m² have ≥2 means of escape (II-2/13.3.2.1)
      - Escape route width ≥700 mm (II-2/13.3.2)
      - Escape route headroom ≥2000 mm (II-2/13.3.4)
      - Max distance to stairway ≤15 m (passenger ships >36 pax, II-2/13.3.2.1)

    Args:
        zones: List of MarineZone objects.

    Returns:
        ComplianceResult listing each violation.
    """
    result = ComplianceResult(
        compliant=True, standard_reference="SOLAS II-2/13.3"
    )

    for zone in zones:
        # Skip open decks and empty spaces — no escape-route requirements.
        if zone.space_category in (
            SpaceCategory.OPEN_DECK, SpaceCategory.EMPTY_SPACE
        ):
            continue

        # Rule 1: every space has ≥1 escape route.
        if not zone.has_escape_route:
            result.add_finding(
                f"Zone {zone.zone_id} ({zone.name}): no escape route defined. "
                f"SOLAS II-2/13.3.2 requires ≥1 means of escape."
            )

        # Rule 2: spaces >50 m² require ≥2 escape routes.
        if zone.area_m2 > MIN_AREA_REQUIRING_TWO_ESCAPES_M2:
            if zone.escape_route_count < 2:
                result.warnings.append(
                    f"Zone {zone.zone_id} ({zone.name}): area {zone.area_m2} m² "
                    f"exceeds {MIN_AREA_REQUIRING_TWO_ESCAPES_M2} m² but only "
                    f"{zone.escape_route_count} escape route(s) defined. "
                    f"SOLAS II-2/13.3.2.1 requires ≥2 independent escape routes."
                )
            else:
                result.details[zone.zone_id] = {
                    "escape_route_count": zone.escape_route_count,
                    "status": "ok",
                }

        # Rule 3: max distance to stairway (passenger ships >36 pax).
        if zone.max_distance_to_stairway_m is not None:
            if zone.max_distance_to_stairway_m > MAX_DISTANCE_TO_STAIRWAY_M:
                result.add_finding(
                    f"Zone {zone.zone_id} ({zone.name}): max distance to stairway "
                    f"{zone.max_distance_to_stairway_m} m exceeds SOLAS limit "
                    f"{MAX_DISTANCE_TO_STAIRWAY_M} m (II-2/13.3.2.1)."
                )
            else:
                result.details.setdefault(zone.zone_id, {})[
                    "max_distance_to_stairway_m"
                ] = zone.max_distance_to_stairway_m

    return result


# ─── Detection Requirements per Space (SOLAS II-2/7) ────────────────────────

def required_detection_for_space(
    category: SpaceCategory,
    ship: ShipProject,
) -> ComplianceResult:
    """Determine required fire-detection coverage for a space category.

    SOLAS II-2/7 mandates fixed fire-detection systems in:
      - Accommodation spaces (smoke detectors)
      - Service spaces (smoke + heat for galleys)
      - Machinery spaces (heat + flame detectors)
      - Cargo spaces (smoke/heat per cargo type)
      - Control stations (smoke detectors)
      - Escape routes (smoke detectors in corridors, stairways)

    Args:
        category: Space category to check.
        ship: Ship project (drives passenger-ship-specific rules).

    Returns:
        ComplianceResult with required detector types in details.
    """
    result = ComplianceResult(
        compliant=True,
        standard_reference="SOLAS II-2/7 + FSS Code Ch. 9",
    )

    detection_required = {
        SpaceCategory.CONTROL_STATION: ["smoke_photo"],
        SpaceCategory.ESCAPE_ROUTE: ["smoke_photo"],
        SpaceCategory.ACCOMMODATION: ["smoke_photo"],
        SpaceCategory.SERVICE_SPACE_MINOR: ["smoke_photo"],
        SpaceCategory.SERVICE_SPACE_MAJOR: ["smoke_photo", "heat_fixed"],
        SpaceCategory.CARGO_SPACE: ["smoke_duct", "heat_ror"],
        SpaceCategory.MACHINERY_SPACE_A: ["heat_fixed", "flame_uv_ir", "smoke_photo"],
        SpaceCategory.MACHINERY_SPACE_OTHER: ["heat_fixed", "smoke_photo"],
        SpaceCategory.TANK_SPACE: [],   # Tanks use level alarms, not fire detection
        SpaceCategory.EMPTY_SPACE: [],
        SpaceCategory.OPEN_DECK: [],    # Open decks use manual + flame for special cargo
    }

    required = detection_required.get(category, [])
    result.details["required_detectors"] = required
    result.details["detection_required"] = len(required) > 0

    if not required and category not in (
        SpaceCategory.TANK_SPACE, SpaceCategory.EMPTY_SPACE,
        SpaceCategory.OPEN_DECK,
    ):
        result.add_warning(
            f"No detection requirement defined for {category.value} — "
            f"verify against current SOLAS amendments."
        )

    # Passenger ships: additional detection in escape routes.
    if ship.is_passenger_ship and category == SpaceCategory.ESCAPE_ROUTE:
        result.details["required_detectors"].append("co")
        result.warnings.append(
            "Passenger ship escape routes should include CO detectors "
            "for early smouldering-fire warning (ISO 15370)."
        )

    return result


# ─── Extinguishing Requirements per Space (SOLAS II-2/10) ───────────────────

def required_extinguishing_for_space(
    category: SpaceCategory,
    ship: ShipProject,
) -> ComplianceResult:
    """Determine required fixed extinguishing system for a space.

    SOLAS II-2/10 mandates fixed fire-extinguishing systems for:
      - Machinery spaces (Type A): water mist OR CO2 (II-2/10.4)
      - Cargo spaces: CO2 (or equivalent) for cargo ships >2000 GT
      - Paint/flammable lockers: CO2 or dry chemical
      - Galley hoods: wet chemical or dry chemical
      - Cargo tank deck (tankers): foam (low expansion)
      - Helidecks (if fitted): AFFF or dry chemical

    Args:
        category: Space category.
        ship: Ship project.

    Returns:
        ComplianceResult listing required systems.
    """
    result = ComplianceResult(
        compliant=True,
        standard_reference="SOLAS II-2/10",
    )

    extinguishing_required = {
        SpaceCategory.MACHINERY_SPACE_A: ["water_mist", "co2_total"],
        SpaceCategory.MACHINERY_SPACE_OTHER: ["water_mist"],
        # BUGFIX v2: SOLAS II-2/10.7.1.1 requires fixed extinguishing in
        # cargo spaces of PASSENGER ships regardless of GT, and for cargo
        # ships only when GT > 2000. The previous code applied the >2000
        # GT rule uniformly — passenger ships with GT=0 (default!) got
        # nothing, violating SOLAS II-2/10.7.1.1.
        SpaceCategory.CARGO_SPACE: (
            ["co2_total"]
            if (ship.is_passenger_ship or ship.gross_tonnage > 2000)
            else []
        ),
        SpaceCategory.SERVICE_SPACE_MAJOR: ["dry_chemical"],  # Galley hood
        SpaceCategory.CONTROL_STATION: [],   # Portable only
        SpaceCategory.ESCAPE_ROUTE: [],
        SpaceCategory.ACCOMMODATION: ["sprinkler"] if ship.is_passenger_ship else [],
        SpaceCategory.SERVICE_SPACE_MINOR: [],
        SpaceCategory.TANK_SPACE: ["inert_gas", "foam_low"] if ship.is_tanker else [],
        SpaceCategory.EMPTY_SPACE: [],
        SpaceCategory.OPEN_DECK: ["foam_low"] if ship.is_tanker else [],
    }

    required = extinguishing_required.get(category, [])
    result.details["required_systems"] = required
    result.details["fixed_required"] = len(required) > 0

    if not required:
        result.details["note"] = (
            "Portable extinguishers only — no fixed system required."
        )

    return result


# ─── Helpers ────────────────────────────────────────────────────────────────

def _frames_to_meters(frames: int) -> float:
    """Convert ship frame count to meters (approximate)."""
    return abs(frames) * SHIP_FRAME_SPACING_M


def _fire_class_meets_or_exceeds(provided: FireClass, required: FireClass) -> bool:
    """Check if a provided FireClass meets or exceeds the required class.

    Hierarchy (descending protection level):
        A-60 > A-30 > A-15 > A-0 > B-15 > B-0 > C

    A higher tier always satisfies a lower-tier requirement (e.g. A-60
    satisfies an A-30 requirement, but A-15 does NOT satisfy A-30).
    """
    hierarchy = [
        FireClass.A_60, FireClass.A_30, FireClass.A_15, FireClass.A_0,
        FireClass.B_15, FireClass.B_0, FireClass.C,
    ]
    return hierarchy.index(provided) <= hierarchy.index(required)


# ─── Public API ─────────────────────────────────────────────────────────────

__all__ = [
    "validate_main_vertical_zones",
    "required_fire_class_between",
    "validate_fire_divisions",
    "validate_escape_routes",
    "required_detection_for_space",
    "required_extinguishing_for_space",
]
