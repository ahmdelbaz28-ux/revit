"""
marine/iso15370/thermal_alarms.py — ISO 15370 Thermal Alarms.

ISO 15370: Ships and marine technology — Thermal alarms for passenger ships.
Provides thermal-alarm spacing and temperature-class selection for escape
routes on passenger ships carrying >36 passengers.

Scope (ISO 15370 §1):
    - Passenger ships carrying >36 passengers
    - Escape routes (corridors, stairways) only
    - NOT applicable to: cargo ships, machinery spaces, accommodation cabins,
      or any space that is not an escape route on a passenger ship.

v2 BUGFIXES:
    - `int(area/spacing²)` truncated instead of ceil → under-counted alarms
      by 1 whenever area wasn't a perfect multiple of 100 m².
    - Spacing formula was area-based; ISO 15370 specifies LINEAR spacing
      along the route length. Now accepts `route_length_m` and uses ceil.
    - No scope check: any zone (engine room, cargo hold) was accepted.
      Now validates passenger-ship + escape-route preconditions.
"""
from __future__ import annotations

import math

from marine.core.constants import (
    THERMAL_ALARM_MAX_SPACING_M,
)
from marine.core.types import (
    ComplianceResult,
    MarineZone,
    ShipProject,
    SpaceCategory,
    ThermalAlarmClass,
)


def select_thermal_alarm_class(ambient_temp_c: float) -> ThermalAlarmClass:
    """
    Pick Class A (70°C) or B (90°C) based on ambient temperature.

    ISO 15370 §6.2:
      - Class A: 70°C ±5°C — for low-ambient areas (escape routes exposed
        to weather, lifeboat embarkation decks)
      - Class B: 90°C ±5°C — for warmer areas (heated escape routes,
        engine-room-adjacent corridors)
    """
    if ambient_temp_c < 40:
        return ThermalAlarmClass.CLASS_A
    return ThermalAlarmClass.CLASS_B


def calculate_thermal_alarm_count(
    zone: MarineZone,
    ship: ShipProject | None = None,
    route_length_m: float | None = None,
) -> ComplianceResult:
    """
    Calculate thermal alarms needed in a passenger-ship escape route.

    ISO 15370 §6.4: alarms are spaced at most THERMAL_ALARM_MAX_SPACING_M
    (10 m) ALONG the escape route, not by floor area. The previous
    implementation used an area-based formula (`area / spacing²`) which
    under-counted long narrow corridors.

    Two call modes:
      1. Pass `route_length_m` explicitly → uses linear spacing.
      2. Pass `zone` only → falls back to area-based estimate using the
         zone's effective width (`sqrt(area_m2)`) as a corridor-width proxy.

    Args:
        zone: Zone to design detection for.
        ship: Optional ShipProject — if provided, validates that the ship
            is a passenger ship with >36 pax (ISO 15370 scope).
        route_length_m: Length of the escape route through the zone, in
            metres. If None, derived from `sqrt(zone.area_m2)`.

    Returns:
        ComplianceResult with `details["alarm_count"]`.

    """
    result = ComplianceResult(
        compliant=True, standard_reference="ISO 15370 §6.4",
    )

    # Scope check: ISO 15370 applies ONLY to passenger-ship escape routes
    # carrying >36 passengers.
    if ship is not None:
        if not ship.is_passenger_ship:
            result.add_finding(
                f"ISO 15370 does not apply to non-passenger ships "
                f"(ship_type={ship.ship_type.value})."
            )
            return result
        if ship.passenger_capacity <= 36:
            result.add_finding(
                f"ISO 15370 requires passenger_capacity > 36 "
                f"(got {ship.passenger_capacity})."
            )
            return result
    if zone.space_category != SpaceCategory.ESCAPE_ROUTE:
        result.add_finding(
            f"Zone {zone.zone_id} ({zone.space_category.value}) is not an "
            f"escape route — ISO 15370 only applies to escape routes."
        )
        return result

    # Determine effective route length.
    if route_length_m is None:
        # Fallback: derive from area assuming a square corridor footprint.
        # This is a rough estimate — production designs should pass the
        # actual route length from the GA plan.
        route_length_m = math.sqrt(zone.area_m2) if zone.area_m2 > 0 else 0.0
        result.warnings.append(
            "route_length_m not provided — using sqrt(area_m2) as estimate. "
            "Pass the actual route length from the GA plan for accuracy."
        )

    # Linear spacing: alarms every 10 m, +1 for the start of the route.
    # BUGFIX v2: previously used int(area / spacing²) which truncated
    # (1.5 → 1, missing 1 alarm). math.ceil ensures rounding up.
    if route_length_m <= 0:
        count = 1  # at least one alarm even for very short routes
    else:
        count = max(1, math.ceil(route_length_m / THERMAL_ALARM_MAX_SPACING_M) + 1)

    result.details["alarm_count"] = count
    result.details["route_length_m"] = round(route_length_m, 2)
    result.details["max_spacing_m"] = THERMAL_ALARM_MAX_SPACING_M
    result.details["formula"] = (
        f"ceil({route_length_m:.1f} / {THERMAL_ALARM_MAX_SPACING_M}) + 1 = {count}"
    )
    return result


__all__ = ["calculate_thermal_alarm_count", "select_thermal_alarm_class"]
