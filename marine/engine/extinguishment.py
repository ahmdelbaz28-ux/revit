"""
marine/engine/extinguishment.py — Extinguishing System Sizing
===============================================================
Implements the "Extinguishment" module from the marine agent prompt.

Sizes water-mist, CO2, foam, AFFF, dry-chemical, sprinkler, and inert-gas
systems per:
    - IMO MSC.1/Circ.1165 (water mist)
    - IMO MSC.1/Circ.1316 (CO2 total flooding)
    - SOLAS II-2/10 (general requirements)
    - SOLAS II-2/8 (sprinklers in accommodation)
    - FSS Code Ch. 14 (sprinkler design)
"""

from __future__ import annotations

import math
from typing import List

from marine.core.constants import (
    AFFF_APPLICATION_RATE_LPM_PER_M2, AFFF_DISCHARGE_TIME_MIN,
    CO2_DESIGN_CONCENTRATION_PCT, CO2_GAS_DENSITY_KG_PER_M3,
    CO2_MAX_DISCHARGE_TIME_MIN, CO2_MIN_HOLD_TIME_MIN,
    FOAM_HIGH_DISCHARGE_RATE_M3_PER_MIN, FOAM_HIGH_EXPANSION_RATIO,
    FOAM_HIGH_MIN_FILL_TIME_MIN, FOAM_LOW_APPLICATION_RATE_LPM_PER_M2,
    FOAM_LOW_EXPANSION_RATIO, FOAM_LOW_MIN_DISCHARGE_TIME_MIN,
    INERT_GAS_CAPACITY_FACTOR, INERT_GAS_MAX_O2_PCT,
    SPRINKLER_DESIGN_DENSITY_MM_PER_MIN, SPRINKLER_MAX_COVERAGE_M2,
    SPRINKLER_RATED_TEMP_C, WATER_MIST_DESIGN_DENSITY_MM_PER_MIN,
    WATER_MIST_MAX_DROPLET_MICRONS, WATER_MIST_MIN_DISCHARGE_TIME_MIN,
)
from marine.core.types import (
    ComplianceResult, ExtinguishingDesign, ExtinguishingSystem,
    FireHazardClass, MarineZone, ShipProject, SpaceCategory,
)
from marine.core.errors import ExtinguishingDesignError


def select_system_for_zone(
    zone: MarineZone, ship: ShipProject,
) -> ComplianceResult:
    """Select the optimal extinguishing system for a marine zone.

    Decision matrix (per SOLAS II-2/10):
      - Machinery A → water_mist OR co2_total (operator choice)
      - Machinery Other → water_mist
      - Cargo space → co2_total (≥2000 GT)
      - Galley (service major) → dry_chemical (galley hood)
      - Tank space (tankers) → inert_gas + foam_low
      - Open deck (tankers) → foam_low (cargo tank deck)
      - Accommodation (passenger ships) → sprinkler
      - Other → no fixed system (portable only)
    """
    result = ComplianceResult(compliant=True, standard_reference="SOLAS II-2/10")

    cat = zone.space_category
    if cat == SpaceCategory.MACHINERY_SPACE_A:
        # Default: water_mist (less hazardous to personnel than CO2).
        selected = ExtinguishingSystem.WATER_MIST
    elif cat == SpaceCategory.MACHINERY_SPACE_OTHER:
        selected = ExtinguishingSystem.WATER_MIST
    elif cat == SpaceCategory.CARGO_SPACE and ship.gross_tonnage > 2000:
        selected = ExtinguishingSystem.CO2_TOTAL
    elif cat == SpaceCategory.SERVICE_SPACE_MAJOR:
        selected = ExtinguishingSystem.DRY_CHEMICAL
    elif cat == SpaceCategory.TANK_SPACE and ship.is_tanker:
        selected = ExtinguishingSystem.INERT_GAS
    elif cat == SpaceCategory.OPEN_DECK and ship.is_tanker:
        selected = ExtinguishingSystem.FOAM_LOW
    elif cat == SpaceCategory.ACCOMMODATION and ship.is_passenger_ship:
        selected = ExtinguishingSystem.SPRINKLER
    else:
        result.details["system"] = None
        result.details["note"] = "No fixed system required — portable only."
        return result

    result.details["system"] = selected.value
    return result


def size_water_mist(zone: MarineZone) -> ExtinguishingDesign:
    """Size a water-mist system per IMO MSC.1/Circ.1165.

    Design:
      - Application density: 5 mm/min (engine rooms)
      - Discharge time: ≥30 min continuous
      - Max droplet size: 1000 microns (DV0.99)
      - Nozzle spacing per maker's certified pattern
    """
    volume_m3 = zone.area_m2 * zone.height_m
    flow_lpm = zone.area_m2 * WATER_MIST_DESIGN_DENSITY_MM_PER_MIN * 1.0  # mm/min ≈ L/m²/min
    # Nozzles: assume each covers ~9 m² (typical water-mist nozzle).
    nozzles = max(1, math.ceil(zone.area_m2 / 9.0))
    pipe_length_m = nozzles * 6.0  # rough: 6 m of pipe per nozzle

    return ExtinguishingDesign(
        system_type=ExtinguishingSystem.WATER_MIST,
        protected_zone=zone.zone_id,
        protected_volume_m3=round(volume_m3, 1),
        agent_quantity_kg=round(flow_lpm * WATER_MIST_MIN_DISCHARGE_TIME_MIN, 0),  # L ≈ kg
        design_concentration_pct=0.0,  # Water mist uses density, not %
        discharge_time_s=WATER_MIST_MIN_DISCHARGE_TIME_MIN * 60,
        hold_time_min=WATER_MIST_MIN_DISCHARGE_TIME_MIN,
        nozzles=nozzles,
        pipe_length_m=round(pipe_length_m, 1),
        standard_reference="IMO MSC.1/Circ.1165",
    )


def size_co2_total_flooding(
    zone: MarineZone, hazard_key: str = "engine_room",
) -> ExtinguishingDesign:
    """Size a CO2 total-flooding system per IMO MSC.1/Circ.1316.

    Design:
      - Concentration: 35% (engine rooms), 30% (cargo), 45% (dangerous)
      - Discharge time: ≤2 min (reach 95% of design concentration)
      - Hold (soak) time: ≥20 min

    CO2 quantity formula:
        M = V × C / (100 - C) × ρ × SF
      where V=volume, C=concentration, ρ=CO2 density, SF=1.0–1.5 safety.
    """
    volume_m3 = zone.area_m2 * zone.height_m
    concentration = CO2_DESIGN_CONCENTRATION_PCT.get(hazard_key, 35.0)
    # Volume of CO2 needed (at design concentration):
    co2_volume_m3 = volume_m3 * concentration / (100.0 - concentration)
    co2_mass_kg = co2_volume_m3 * CO2_GAS_DENSITY_KG_PER_M3 * 1.0  # safety factor included

    # Nozzles: typically 1 per 25 m² of deck area.
    nozzles = max(2, math.ceil(zone.area_m2 / 25.0))
    pipe_length_m = nozzles * 8.0  # avg 8 m pipe per nozzle (overhead distribution)

    return ExtinguishingDesign(
        system_type=ExtinguishingSystem.CO2_TOTAL,
        protected_zone=zone.zone_id,
        protected_volume_m3=round(volume_m3, 1),
        agent_quantity_kg=round(co2_mass_kg, 1),
        design_concentration_pct=concentration,
        discharge_time_s=CO2_MAX_DISCHARGE_TIME_MIN * 60,
        hold_time_min=CO2_MIN_HOLD_TIME_MIN,
        nozzles=nozzles,
        pipe_length_m=round(pipe_length_m, 1),
        standard_reference="IMO MSC.1/Circ.1316",
    )


def size_foam_low_expansion(zone: MarineZone) -> ExtinguishingDesign:
    """Size low-expansion foam for cargo tank deck per SOLAS II-2/10.8."""
    flow_lpm = zone.area_m2 * FOAM_LOW_APPLICATION_RATE_LPM_PER_M2
    agent_litres = flow_lpm * FOAM_LOW_MIN_DISCHARGE_TIME_MIN
    # Foam concentrate = 3% of foam solution.
    concentrate_kg = agent_litres * 0.03

    return ExtinguishingDesign(
        system_type=ExtinguishingSystem.FOAM_LOW,
        protected_zone=zone.zone_id,
        protected_volume_m3=0.0,  # Deck protection, not volume
        agent_quantity_kg=round(concentrate_kg, 1),
        design_concentration_pct=3.0,
        discharge_time_s=FOAM_LOW_MIN_DISCHARGE_TIME_MIN * 60,
        hold_time_min=FOAM_LOW_MIN_DISCHARGE_TIME_MIN,
        nozzles=max(2, math.ceil(zone.area_m2 / 50.0)),
        pipe_length_m=round(zone.area_m2 ** 0.5 * 4, 1),
        standard_reference="SOLAS II-2/10.8 + FSS Ch. 13",
    )


def size_sprinkler(zone: MarineZone) -> ExtinguishingDesign:
    """Size sprinkler system per SOLAS II-2/8 + FSS Code Ch. 14."""
    heads = max(1, math.ceil(zone.area_m2 / SPRINKLER_MAX_COVERAGE_M2))
    flow_lpm = zone.area_m2 * SPRINKLER_DESIGN_DENSITY_MM_PER_MIN

    return ExtinguishingDesign(
        system_type=ExtinguishingSystem.SPRINKLER,
        protected_zone=zone.zone_id,
        protected_volume_m3=round(zone.area_m2 * zone.height_m, 1),
        agent_quantity_kg=round(flow_lpm * 30.0, 0),  # 30 min supply
        design_concentration_pct=0.0,
        discharge_time_s=30 * 60,
        hold_time_min=30.0,
        nozzles=heads,
        pipe_length_m=round(heads * 4.0, 1),
        standard_reference="SOLAS II-2/8 + FSS Ch. 14",
    )


def size_inert_gas(zone: MarineZone) -> ExtinguishingDesign:
    """Size inert-gas system per SOLAS II-2/4.5.5 + FSS Ch. 15."""
    volume_m3 = zone.area_m2 * zone.height_m
    # IG capacity: reduce O2 to ≤8% (from 21%).
    ig_volume_m3 = volume_m3 * (21.0 - INERT_GAS_MAX_O2_PCT) / (100 - INERT_GAS_MAX_O2_PCT)
    capacity_m3_per_hr = ig_volume_m3 * INERT_GAS_CAPACITY_FACTOR

    return ExtinguishingDesign(
        system_type=ExtinguishingSystem.INERT_GAS,
        protected_zone=zone.zone_id,
        protected_volume_m3=round(volume_m3, 1),
        agent_quantity_kg=0.0,  # IG is generated onboard, not stored
        design_concentration_pct=INERT_GAS_MAX_O2_PCT,
        discharge_time_s=round(ig_volume_m3 / capacity_m3_per_hr * 3600, 0),
        hold_time_min=0.0,
        nozzles=max(1, math.ceil(zone.area_m2 / 100.0)),
        pipe_length_m=round(zone.area_m2 ** 0.5 * 3, 1),
        standard_reference="SOLAS II-2/4.5.5 + FSS Ch. 15",
    )


def size_system(
    zone: MarineZone, ship: ShipProject,
) -> ExtinguishingDesign:
    """Top-level: select + size the appropriate extinguishing system."""
    sel = select_system_for_zone(zone, ship)
    sys_str = sel.details.get("system")
    if sys_str is None:
        raise ExtinguishingDesignError(
            f"No fixed extinguishing system required for zone {zone.zone_id}."
        )
    system = ExtinguishingSystem(sys_str)
    if system == ExtinguishingSystem.WATER_MIST:
        return size_water_mist(zone)
    if system == ExtinguishingSystem.CO2_TOTAL:
        hazard = "engine_room" if zone.space_category == SpaceCategory.MACHINERY_SPACE_A else "cargo_hold_general"
        return size_co2_total_flooding(zone, hazard)
    if system == ExtinguishingSystem.FOAM_LOW:
        return size_foam_low_expansion(zone)
    if system == ExtinguishingSystem.SPRINKLER:
        return size_sprinkler(zone)
    if system == ExtinguishingSystem.INERT_GAS:
        return size_inert_gas(zone)
    # Dry chemical (galley) — minimal sizing.
    return ExtinguishingDesign(
        system_type=ExtinguishingSystem.DRY_CHEMICAL,
        protected_zone=zone.zone_id,
        protected_volume_m3=round(zone.area_m2 * zone.height_m, 1),
        agent_quantity_kg=12.0,  # typical 12 kg ABC dry chem for galley hood
        design_concentration_pct=0.0,
        discharge_time_s=30,
        hold_time_min=0.0,
        nozzles=1,
        pipe_length_m=2.0,
        standard_reference="SOLAS II-2/10.6 (galley hood)",
    )


__all__ = [
    "select_system_for_zone", "size_water_mist", "size_co2_total_flooding",
    "size_foam_low_expansion", "size_sprinkler", "size_inert_gas",
    "size_system",
]
