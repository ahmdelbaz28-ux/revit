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

from marine.core.constants import (
    AFFF_APPLICATION_RATE_LPM_PER_M2,
    AFFF_DISCHARGE_TIME_MIN,
    CO2_DESIGN_CONCENTRATION_PCT,
    CO2_GAS_DENSITY_KG_PER_M3,
    CO2_MAX_DISCHARGE_TIME_MIN,
    CO2_MIN_HOLD_TIME_MIN,
    FOAM_HIGH_EXPANSION_RATIO,
    FOAM_HIGH_MIN_FILL_TIME_MIN,
    FOAM_LOW_APPLICATION_RATE_LPM_PER_M2,
    FOAM_LOW_MIN_DISCHARGE_TIME_MIN,
    INERT_GAS_CAPACITY_FACTOR,
    INERT_GAS_MAX_O2_PCT,
    SPRINKLER_DESIGN_DENSITY_MM_PER_MIN,
    SPRINKLER_MAX_COVERAGE_M2,
    WATER_MIST_DESIGN_DENSITY_MM_PER_MIN,
    WATER_MIST_MIN_DISCHARGE_TIME_MIN,
)
from marine.core.errors import ExtinguishingDesignError
from marine.core.types import (
    ComplianceResult,
    ExtinguishingDesign,
    ExtinguishingSystem,
    MarineZone,
    ShipProject,
    SpaceCategory,
)


def select_system_for_zone(
    zone: MarineZone, ship: ShipProject,
) -> ComplianceResult:
    """
    Select the optimal extinguishing system for a marine zone.

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
    """
    Size a water-mist system per IMO MSC.1/Circ.1165.

    Design:
      - Application density: 5 mm/min (engine rooms)
      - Discharge time: ≥30 min continuous
      - Max droplet size: 1000 microns (DV0.99)
      - Nozzle spacing per maker's certified pattern
    """
    # Guard against nonsensical inputs (would otherwise return a design with
    # 0 volume / 0 agent and a phantom "1 nozzle").
    if zone.area_m2 <= 0 or zone.height_m <= 0:
        raise ExtinguishingDesignError(
            f"Cannot size water mist for zone {zone.zone_id}: "
            f"area_m2={zone.area_m2}, height_m={zone.height_m} must be >0."
        )

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
    """
    Size a CO2 total-flooding system per IMO MSC.1/Circ.1316.

    Design:
      - Concentration: 35% (engine rooms), 30% (cargo), 45% (dangerous)
      - Discharge time: ≤2 min (reach 95% of design concentration)
      - Hold (soak) time: ≥20 min

    CO2 quantity formula (MSC.1/Circ.1316 §4.4):
        Volume method:
            M = V × C / (100 - C) × ρ × SF
          where V=volume, C=concentration, ρ=CO2 density, SF=safety factor.

        Alternative method (MSC.1/Circ.1316 §4.4.2 — "free gas" formula):
            M_alt = V / 0.75   (kg, ≈1.33 kg per m³ of net volume)

    The standard REQUIRES the larger of the two results to be installed.

    BUGFIX (v2): Previously the safety factor was hardcoded to 1.0 with a
    comment "safety factor included" — but 1.0 is no safety factor at all,
    under-supplying CO2 by ~25%. Now uses SF=1.10 (conservative) and
    returns the larger of the two methods.
    """
    # Guard against nonsensical inputs (zone with zero/negative geometry).
    if zone.area_m2 <= 0 or zone.height_m <= 0:
        raise ExtinguishingDesignError(
            f"Cannot size CO2 system for zone {zone.zone_id}: "
            f"area_m2={zone.area_m2}, height_m={zone.height_m} must be >0."
        )

    volume_m3 = zone.area_m2 * zone.height_m
    concentration = CO2_DESIGN_CONCENTRATION_PCT.get(hazard_key, 35.0)
    # Safety factor: 1.10 (10% margin — MSC.1/Circ.1316 allows 1.0–1.5; we
    # use 1.10 as a conservative baseline; manufacturers may increase).
    SAFETY_FACTOR = 1.10

    # Method 1: Volume/concentration formula.
    co2_volume_m3 = volume_m3 * concentration / (100.0 - concentration)
    co2_mass_method1_kg = co2_volume_m3 * CO2_GAS_DENSITY_KG_PER_M3 * SAFETY_FACTOR

    # Method 2: MSC.1/Circ.1316 §4.4.2 alternative (free-gas formula).
    # 1 kg CO2 ≈ 0.75 m³ free gas at STP → need V/0.75 kg for full flood.
    co2_mass_method2_kg = volume_m3 / 0.75

    # Install the LARGER quantity (standard requires this).
    co2_mass_kg = max(co2_mass_method1_kg, co2_mass_method2_kg)
    method_used = "volume" if co2_mass_method1_kg >= co2_mass_method2_kg else "free_gas"

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
        standard_reference=f"IMO MSC.1/Circ.1316 ({method_used} method, SF={SAFETY_FACTOR})",
    )


def size_foam_low_expansion(zone: MarineZone) -> ExtinguishingDesign:
    """Size low-expansion foam for cargo tank deck per SOLAS II-2/10.8."""
    if zone.area_m2 <= 0:
        raise ExtinguishingDesignError(
            f"Cannot size foam system for zone {zone.zone_id}: "
            f"area_m2={zone.area_m2} must be >0."
        )
    flow_lpm = zone.area_m2 * FOAM_LOW_APPLICATION_RATE_LPM_PER_M2
    agent_litres = flow_lpm * FOAM_LOW_MIN_DISCHARGE_TIME_MIN
    # Foam concentrate = 3% of foam solution, density ~1.05 kg/L (AFFF).
    # The previous implementation used 1.0 kg/L, under-estimating by 5%.
    FOAM_CONCENTRATE_DENSITY_KG_PER_L = 1.05
    concentrate_kg = agent_litres * 0.03 * FOAM_CONCENTRATE_DENSITY_KG_PER_L

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


def size_foam_high_expansion(zone: MarineZone) -> ExtinguishingDesign:
    """
    Size high-expansion foam for engine rooms per SOLAS II-2/10.7.

    High-expansion foam (1000:1 expansion ratio) totally floods the machinery
    space via foam generators suspended from the deck head. Design rules per
    FSS Code Ch. 13 §2.4:
      - Discharge rate: ≥1 m³/min per m² of deck area (FSS 13.2.4.2)
      - Fill time: ≤10 min for the entire protected space (SOLAS II-2/10.7.2)
      - Expansion ratio: typically 1000:1 (range 500:1–1000:1 per FSS 13.2.2)
    """
    if zone.area_m2 <= 0 or zone.height_m <= 0:
        raise ExtinguishingDesignError(
            f"Cannot size high-expansion foam for zone {zone.zone_id}: "
            f"area_m2={zone.area_m2}, height_m={zone.height_m} must be >0."
        )

    # Total foam volume needed = volume of protected space.
    protected_volume_m3 = zone.area_m2 * zone.height_m
    # Generator capacity: must fill the volume within FOAM_HIGH_MIN_FILL_TIME_MIN.
    generator_capacity_m3_per_min = protected_volume_m3 / FOAM_HIGH_MIN_FILL_TIME_MIN
    # Foam solution needed = generator capacity ÷ expansion ratio × fill time.
    foam_solution_litres = (generator_capacity_m3_per_min * 1000.0
                            / FOAM_HIGH_EXPANSION_RATIO
                            * FOAM_HIGH_MIN_FILL_TIME_MIN)
    # Concentrate = 3% of foam solution, density ~1.05 kg/L.
    FOAM_CONCENTRATE_DENSITY_KG_PER_L = 1.05
    concentrate_kg = foam_solution_litres * 0.03 * FOAM_CONCENTRATE_DENSITY_KG_PER_L
    # Generators: one per ~50 m² of deck (typical manufacturer rule).
    nozzles = max(2, math.ceil(zone.area_m2 / 50.0))

    return ExtinguishingDesign(
        system_type=ExtinguishingSystem.FOAM_HIGH,
        protected_zone=zone.zone_id,
        protected_volume_m3=round(protected_volume_m3, 1),
        agent_quantity_kg=round(concentrate_kg, 1),
        design_concentration_pct=3.0,
        discharge_time_s=int(FOAM_HIGH_MIN_FILL_TIME_MIN * 60),
        hold_time_min=FOAM_HIGH_MIN_FILL_TIME_MIN,
        nozzles=nozzles,
        pipe_length_m=round(zone.area_m2 ** 0.5 * 4, 1),
        standard_reference="SOLAS II-2/10.7 + FSS Ch. 13 §2.4",
    )


def size_afff(zone: MarineZone) -> ExtinguishingDesign:
    """
    Size AFFF system for helidecks per CAP 437 + ICAO Annex 14.

    AFFF (Aqueous Film-Forming Foam) is the standard extinguishing agent for
    helidecks on offshore installations and ships with helicopter operations.
    Design rules:
      - Application rate: ≥2.5 L/min/m² (CAP 437 §6.3)
      - Discharge time: ≥5 min at design rate
      - Concentrate proportion: 3% (typical AFFF)
    """
    if zone.area_m2 <= 0:
        raise ExtinguishingDesignError(
            f"Cannot size AFFF system for zone {zone.zone_id}: "
            f"area_m2={zone.area_m2} must be >0."
        )
    flow_lpm = zone.area_m2 * AFFF_APPLICATION_RATE_LPM_PER_M2
    foam_solution_litres = flow_lpm * AFFF_DISCHARGE_TIME_MIN
    FOAM_CONCENTRATE_DENSITY_KG_PER_L = 1.05
    concentrate_kg = foam_solution_litres * 0.03 * FOAM_CONCENTRATE_DENSITY_KG_PER_L
    nozzles = max(2, math.ceil(zone.area_m2 / 25.0))  # 1 nozzle per ~25 m²

    return ExtinguishingDesign(
        system_type=ExtinguishingSystem.AFFF,
        protected_zone=zone.zone_id,
        protected_volume_m3=0.0,  # Deck protection, not volume
        agent_quantity_kg=round(concentrate_kg, 1),
        design_concentration_pct=3.0,
        discharge_time_s=int(AFFF_DISCHARGE_TIME_MIN * 60),
        hold_time_min=AFFF_DISCHARGE_TIME_MIN,
        nozzles=nozzles,
        pipe_length_m=round(zone.area_m2 ** 0.5 * 3, 1),
        standard_reference="CAP 437 §6.3 + ICAO Annex 14",
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


def size_inert_gas(
    zone: MarineZone,
    cargo_discharge_rate_m3_per_hr: float = 250.0,
    inert_gas_o2_pct: float = 4.0,
) -> ExtinguishingDesign:
    """
    Size inert-gas system per SOLAS II-2/4.5.5 + FSS Ch. 15.

    Two distinct engineering quantities must be computed:

    1. IG generator CAPACITY (m³/hr) — sized to 1.25 × max cargo discharge
       rate per SOLAS II-2/4.5.5.1. This is independent of tank volume.
       Default cargo_discharge_rate = 250 m³/hr (typical medium tanker).

    2. Purge VOLUME (m³) — the volume of IG needed to reduce tank O₂ from
       21% to ≤8%. Using the ideal-gas purge formula:
           V_ig = V_tank × ln(21 / 8) / (1 - O₂_ig / 8)
       where O₂_ig is the oxygen content of the inert gas (typically 3-5%
       for flue-gas IG, ~0% for N₂ generators). With O₂_ig=4%:
           V_ig = V_tank × ln(2.625) / (1 - 0.5) ≈ 1.93 × V_tank

    BUGFIX (v2): The previous implementation used the simplistic
    `V × (21-8)/(100-8)` formula (which assumes IG has 0% O₂ and uses a
    linear — not logarithmic — purge model), under-estimating IG volume
    by ~14×. It also returned a constant `discharge_time_s = 2880` for
    any zone because capacity was computed as `ig_volume × 1.25` (units:
    m³, not m³/hr). Now capacity is sourced from the cargo discharge
    rate per SOLAS, and discharge time scales correctly with volume.

    Args:
        zone: Tank zone to inert.
        cargo_discharge_rate_m3_per_hr: Maximum cargo discharge rate (m³/hr).
            IG capacity = 1.25 × this value per SOLAS II-2/4.5.5.1.
        inert_gas_o2_pct: O₂ content of the inert gas itself. Flue-gas IG
            typically 3-5%, N₂ generators <1%. Default 4.0 (typical flue gas).

    Returns:
        ExtinguishingDesign with capacity-derived discharge time.

    """
    if zone.area_m2 <= 0 or zone.height_m <= 0:
        raise ExtinguishingDesignError(
            f"Cannot size inert gas system for zone {zone.zone_id}: "
            f"area_m2={zone.area_m2}, height_m={zone.height_m} must be >0."
        )
    if cargo_discharge_rate_m3_per_hr <= 0:
        raise ExtinguishingDesignError(
            f"cargo_discharge_rate_m3_per_hr must be > 0 (got "
            f"{cargo_discharge_rate_m3_per_hr})."
        )
    if not 0.0 <= inert_gas_o2_pct < INERT_GAS_MAX_O2_PCT:
        raise ExtinguishingDesignError(
            f"inert_gas_o2_pct must be in [0, {INERT_GAS_MAX_O2_PCT}) "
            f"(got {inert_gas_o2_pct})."
        )

    volume_m3 = zone.area_m2 * zone.height_m

    # IG generator capacity (m³/hr) — SOLAS II-2/4.5.5.1.
    capacity_m3_per_hr = cargo_discharge_rate_m3_per_hr * INERT_GAS_CAPACITY_FACTOR

    # Purge volume needed to displace tank atmosphere from 21% → ≤8% O₂.
    # ln(21/8) = 0.965; (1 - O₂_ig/8) approaches 1.0 for low-O₂ IG.
    purge_volume_m3 = volume_m3 * math.log(21.0 / INERT_GAS_MAX_O2_PCT) \
        / (1.0 - inert_gas_o2_pct / INERT_GAS_MAX_O2_PCT)

    # Discharge time to deliver the purge volume at generator capacity.
    discharge_time_s = round(purge_volume_m3 / capacity_m3_per_hr * 3600.0, 0)

    return ExtinguishingDesign(
        system_type=ExtinguishingSystem.INERT_GAS,
        protected_zone=zone.zone_id,
        protected_volume_m3=round(volume_m3, 1),
        agent_quantity_kg=0.0,  # IG is generated onboard, not stored
        design_concentration_pct=INERT_GAS_MAX_O2_PCT,
        discharge_time_s=discharge_time_s,
        hold_time_min=0.0,
        nozzles=max(1, math.ceil(zone.area_m2 / 100.0)),
        pipe_length_m=round(zone.area_m2 ** 0.5 * 3, 1),
        standard_reference=(
            f"SOLAS II-2/4.5.5 + FSS Ch. 15 "
            f"(capacity={capacity_m3_per_hr:.0f} m³/hr, purge={purge_volume_m3:.0f} m³)"
        ),
    )


def size_system(
    zone: MarineZone, ship: ShipProject,
) -> ExtinguishingDesign:
    """
    Top-level: select + size the appropriate extinguishing system.

    Routes to the correct sizer based on the auto-selected system. Raises
    ExtinguishingDesignError if no fixed system is required for the zone.
    """
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
    if system == ExtinguishingSystem.FOAM_HIGH:
        return size_foam_high_expansion(zone)
    if system == ExtinguishingSystem.AFFF:
        return size_afff(zone)
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
    "select_system_for_zone",
    "size_afff",
    "size_co2_total_flooding",
    "size_foam_high_expansion",
    "size_foam_low_expansion",
    "size_inert_gas",
    "size_sprinkler",
    "size_system",
    "size_water_mist",
]
