"""
marine/core/constants.py — Engineering Constants for Marine Fire Safety
========================================================================
Single source of truth for all numerical constants. These values come
directly from the cited standards — DO NOT modify them without checking
the referenced regulation.

References:
    [SOLAS]   IMO SOLAS Chapter II-2 (2024 consolidated edition)
    [FSS]     IMO FSS Code (Fire Safety Systems Code) Chapter 9
    [IEC502]  IEC 60092-502:1999 — Tankers electrical installations
    [IEC504]  IEC 60092-504 — Ships carrying dangerous goods
    [ISO15370] ISO 15370:2001 — Thermal alarms for passenger ships
    [MSC1165] IMO MSC.1/Circ.1165 — Water mist fire-extinguishing systems
    [MSC1316] IMO MSC.1/Circ.1316 — CO2 total flooding guidelines
    [MSC1318] IMO MSC.1/Circ.1318 — CO2 maintenance guidelines
    [LR]      Lloyd's Register Rules for Fire Protection, Detection & Extinguishment

"""

from __future__ import annotations

# ─── SOLAS II-2 Main Vertical Zone Constraints ──────────────────────────────

# SOLAS II-2/2.2.1: Main vertical zones shall not exceed 40m in length.
# Larger zones require equivalent fire-protection measures (LR rules).
MAX_MAIN_VERTICAL_ZONE_LENGTH_M = 40.0

# SOLAS II-2/2.2.1.1: Passenger ships carrying >36 passengers have a STRICTER
# limit of 24m for main vertical zone length. The previous code applied 40m
# uniformly — over-specifying for cargo ships but UNDER-specifying for large
# passenger ships (cruise, ferries). Now distinguished correctly.
MAX_PASSENGER_MVZ_LENGTH_M = 24.0
PASSENGER_MVZ_PAX_THRESHOLD = 36  # >36 passengers triggers the 24m rule

# SOLAS II-2/13.3.2: Minimum width of escape routes.
MIN_ESCAPE_ROUTE_WIDTH_MM = 700.0  # 700 mm

# SOLAS II-2/13.3.4: Minimum headroom on escape routes.
MIN_ESCAPE_ROUTE_HEIGHT_MM = 2000.0  # 2.0 m

# SOLAS II-2/13.3.2.1: Maximum distance from any point to a stairway.
MAX_DISTANCE_TO_STAIRWAY_M = 15.0  # 15 m for ships >36 passengers

# SOLAS II-2/13.3.2.1: Two means of escape required for spaces >50 m²
MIN_AREA_REQUIRING_TWO_ESCAPES_M2 = 50.0

# ─── Ship Geometry ───────────────────────────────────────────────────────────
# Typical merchant-vessel frame spacing (one frame every ~600 mm).
# Naming fix: this is METERS PER FRAME (i.e. one frame occupies 0.6 m of
# ship length), NOT frames per meter. The legacy `_FRAMES_PER_METER = 0.6`
# constant is preserved for backwards-compat in solas/zone_mapper but new
# code should prefer this correctly-named constant.
SHIP_FRAME_SPACING_M = 0.6


# ─── Fire Division Class Requirements (SOLAS II-2 Table 9.1) ────────────────

# Required FireClass for bulkheads separating adjacent space categories.
# Tuple key: (from_category, to_category). Missing → consult SOLAS table.
SOLAS_FIRE_DIVISION_MATRIX = {
    # Machinery to machinery → A-60
    ("machinery_a", "machinery_a"): "A-60",
    # Machinery to control station → A-60
    ("machinery_a", "control_station"): "A-60",
    # Machinery to escape route → A-60
    ("machinery_a", "escape_route"): "A-60",
    # Machinery to accommodation → A-60
    ("machinery_a", "accommodation"): "A-60",
    # Machinery to cargo space → A-60
    ("machinery_a", "cargo_space"): "A-60",
    # Machinery to service major (galley) → A-60
    ("machinery_a", "service_major"): "A-60",
    # Machinery to service minor → A-60
    ("machinery_a", "service_minor"): "A-60",
    # Machinery to machinery other → A-60
    ("machinery_a", "machinery_other"): "A-60",
    # Machinery to tank space → A-60
    ("machinery_a", "tank_space"): "A-60",
    # Machinery to empty space → A-0
    ("machinery_a", "empty_space"): "A-0",
    # Machinery to open deck → A-0
    ("machinery_a", "open_deck"): "A-0",

    # Cargo to accommodation → A-60
    ("cargo_space", "accommodation"): "A-60",
    # Cargo to escape route → A-60
    ("cargo_space", "escape_route"): "A-60",
    # Cargo to control station → A-30
    ("cargo_space", "control_station"): "A-30",
    # Cargo to service minor → A-30
    ("cargo_space", "service_minor"): "A-30",
    # Cargo to service major → A-60
    ("cargo_space", "service_major"): "A-60",
    # Cargo to machinery other → A-60
    ("cargo_space", "machinery_other"): "A-60",
    # Cargo to tank space → A-60
    ("cargo_space", "tank_space"): "A-60",
    # Cargo to empty space → A-0
    ("cargo_space", "empty_space"): "A-0",
    # Cargo to open deck → A-0
    ("cargo_space", "open_deck"): "A-0",

    # Accommodation to escape route → B-15 (passenger ships) or B-0
    ("accommodation", "escape_route"): "B-15",
    # Control station to accommodation → A-30
    ("control_station", "accommodation"): "A-30",
    # Control station to escape route → A-30
    ("control_station", "escape_route"): "A-30",
    # Control station to service minor → A-30
    ("control_station", "service_minor"): "A-30",
    # Control station to service major → A-60
    ("control_station", "service_major"): "A-60",
    # Control station to machinery other → A-30
    ("control_station", "machinery_other"): "A-30",
    # Control station to tank space → A-60
    ("control_station", "tank_space"): "A-60",
    # Control station to empty space → A-0
    ("control_station", "empty_space"): "A-0",
    # Control station to open deck → A-0
    ("control_station", "open_deck"): "A-0",

    # Escape route to service minor → B-15
    ("escape_route", "service_minor"): "B-15",
    # Escape route to service major → A-60
    ("escape_route", "service_major"): "A-60",
    # Escape route to machinery other → A-30
    ("escape_route", "machinery_other"): "A-30",
    # Escape route to tank space → A-60
    ("escape_route", "tank_space"): "A-60",
    # Escape route to empty space → A-0
    ("escape_route", "empty_space"): "A-0",
    # Escape route to open deck → A-0
    ("escape_route", "open_deck"): "A-0",

    # Service minor to service major → A-30
    ("service_minor", "service_major"): "A-30",
    # Service minor to machinery other → A-30
    ("service_minor", "machinery_other"): "A-30",
    # Service minor to tank space → A-60
    ("service_minor", "tank_space"): "A-60",
    # Service minor to empty space → A-0
    ("service_minor", "empty_space"): "A-0",
    # Service minor to open deck → A-0
    ("service_minor", "open_deck"): "A-0",

    # Service major to machinery other → A-30
    ("service_major", "machinery_other"): "A-30",
    # Service major to tank space → A-60
    ("service_major", "tank_space"): "A-60",
    # Service major to empty space → A-0
    ("service_major", "empty_space"): "A-0",
    # Service major to open deck → A-0
    ("service_major", "open_deck"): "A-0",

    # Machinery other to machinery other → A-30
    ("machinery_other", "machinery_other"): "A-30",
    # Machinery other to tank space → A-60
    ("machinery_other", "tank_space"): "A-60",
    # Machinery other to empty space → A-0
    ("machinery_other", "empty_space"): "A-0",
    # Machinery other to open deck → A-0
    ("machinery_other", "open_deck"): "A-0",

    # Tank space to tank space → A-60
    ("tank_space", "tank_space"): "A-60",
    # Tank space to empty space → A-0
    ("tank_space", "empty_space"): "A-0",
    # Tank space to open deck → A-0
    ("tank_space", "open_deck"): "A-0",

    # Open deck to anything → A-0 minimum
    ("open_deck", "accommodation"): "A-0",
    ("open_deck", "machinery_a"): "A-0",
    ("open_deck", "cargo_space"): "A-0",
    ("open_deck", "escape_route"): "A-0",
    ("open_deck", "service_minor"): "A-0",
    ("open_deck", "service_major"): "A-0",
    ("open_deck", "control_station"): "A-0",
    ("open_deck", "machinery_other"): "A-0",
    ("open_deck", "tank_space"): "A-0",
    ("open_deck", "empty_space"): "A-0",
    ("open_deck", "open_deck"): "A-0",

    # Empty space to anything → A-0 (cofferdams/voids have no rating)
    ("empty_space", "accommodation"): "A-0",
    ("empty_space", "escape_route"): "A-0",
    ("empty_space", "service_minor"): "A-0",
    ("empty_space", "empty_space"): "A-0",
}

# Insulation thickness for A-class divisions (typical values, ceramic wool).
# Actual thickness depends on the certified product — these are reference.
INSULATION_THICKNESS_MM = {
    "A-0": 0.0,
    "A-15": 25.0,
    "A-30": 40.0,
    "A-60": 75.0,   # typical ceramic-wool thickness for 60-min rating
}


# ─── IEC 60092-502 Detector Coverage ────────────────────────────────────────

# FSS Code Chapter 9 Table 9.1: Maximum detector spacing per type.
# Values in m² per detector (ceiling-mounted, max height 12 m).
DETECTOR_COVERAGE_M2 = {
    "heat_fixed": 37.0,         # 37 m² per FSS 9.2.3
    "heat_ror": 37.0,           # Same as fixed-temperature
    "smoke_ion": 74.0,          # 74 m² — typical for photoelectric
    "smoke_photo": 74.0,        # 74 m²
    "smoke_duct": None,         # One per duct (no coverage area)
    "flame_uv": 250.0,          # UV flame detector coverage depends on height
    "flame_ir": 300.0,
    "flame_uv_ir": 200.0,       # Combined — more selective, smaller area
    "co": 50.0,                 # CO sensors in accommodation
    "multicriteria": 84.0,      # Combined smoke+heat → larger area
    "linear_heat": None,        # Linear cable — per-run, not per-area
    "aspirating": 500.0,        # ASD high-sensitivity → larger area
}

# Maximum ceiling height for standard detector spacing (FSS 9.2.2).
# Above this height, reduced coverage or alternative detection required.
MAX_DETECTOR_CEILING_HEIGHT_M = 12.0

# IEC 60092-502: Detector placement distance from bulkheads (corners).
MAX_DISTANCE_FROM_BULKHEAD_M = 5.3   # half of spacing radius
MAX_DETECTOR_SPACING_M = 10.6        # Smoke detector max spacing per FSS 9.2.4

# Heat detector activation temperatures (IEC 60092-502 §4.4).
HEAT_DETECTOR_RATED_TEMPS_C = {
    "low": 54.0,    # Accommodation, control rooms
    "medium": 78.0, # Engine rooms, galleys
    "high": 107.0,  # Drying rooms, hot machinery spaces
}


# ─── Water Mist System (IMO MSC.1/Circ.1165) ────────────────────────────────

# MSC.1/Circ.1165: Minimum design concentration for water mist.
WATER_MIST_DESIGN_DENSITY_MM_PER_MIN = 5.0  # 5 mm/min (engine rooms)

# Minimum discharge time for water mist systems.
WATER_MIST_MIN_DISCHARGE_TIME_MIN = 30.0    # 30 minutes continuous

# Maximum droplet size (DV0.99) for water mist — <1000 microns.
WATER_MIST_MAX_DROPLET_MICRONS = 1000.0


# ─── CO2 Total Flooding System (IMO MSC.1/Circ.1316) ────────────────────────

# MSC.1/Circ.1316: Minimum CO2 design concentrations by cargo class.
CO2_DESIGN_CONCENTRATION_PCT = {
    "engine_room": 35.0,        # 35% by volume
    "cargo_hold_general": 30.0, # 30%
    "cargo_hold_dangerous": 45.0, # 45% for IMDG Class 1/5
    "pump_room": 45.0,          # 45% (flammable liquids)
    "paint_store": 40.0,        # 40%
}

# CO2 discharge time — must reach 95% of design concentration within 2 min.
CO2_MAX_DISCHARGE_TIME_MIN = 2.0

# CO2 hold (soak) time — minimum 20 min per MSC.1/Circ.1316 §4.5.
CO2_MIN_HOLD_TIME_MIN = 20.0

# CO2 gas constant and density at 20°C (engineering reference).
CO2_GAS_DENSITY_KG_PER_M3 = 1.98  # at 20°C, 1 atm
CO2_SPECIFIC_VOLUME_M3_PER_KG = 0.51  # 1/density


# ─── Foam Systems ───────────────────────────────────────────────────────────

# Low-expansion foam for cargo tank deck (SOLAS II-2/10.8).
FOAM_LOW_EXPANSION_RATIO = 12.0   # 12:1
FOAM_LOW_APPLICATION_RATE_LPM_PER_M2 = 4.0  # 4 L/min/m²
FOAM_LOW_MIN_DISCHARGE_TIME_MIN = 15.0

# High-expansion foam for engine rooms (SOLAS II-2/10.7).
FOAM_HIGH_EXPANSION_RATIO = 1000.0   # 1000:1
FOAM_HIGH_DISCHARGE_RATE_M3_PER_MIN = 1.0  # 1 m³/min per m² of deck
FOAM_HIGH_MIN_FILL_TIME_MIN = 10.0   # Fill the space in ≤10 min

# AFFF for helidecks (CAP 437 + ICAO Annex 14).
AFFF_APPLICATION_RATE_LPM_PER_M2 = 2.5  # 2.5 L/min/m²
AFFF_DISCHARGE_TIME_MIN = 5.0


# ─── Sprinkler Systems (SOLAS II-2/8 + FSS Ch. 14) ─────────────────────────

# Sprinkler design density for accommodation spaces.
SPRINKLER_DESIGN_DENSITY_MM_PER_MIN = 5.0   # 5 mm/min (light hazard)

# Maximum coverage per sprinkler head (accommodation).
SPRINKLER_MAX_COVERAGE_M2 = 12.0

# Sprinkler activation temperature.
SPRINKLER_RATED_TEMP_C = 68.0    # 68°C (red bulb)


# ─── Inert Gas System (SOLAS II-2/4.5.5 + FSS Ch. 15) ──────────────────────

# Inert gas oxygen content — must be ≤8% by volume in cargo tanks.
INERT_GAS_MAX_O2_PCT = 8.0

# Inert gas system capacity — 1.25 × maximum discharge rate.
INERT_GAS_CAPACITY_FACTOR = 1.25


# ─── Ship Electrical (IEC 60092 series) ────────────────────────────────────

# IEC 60092-301: Standard shipboard voltages.
SHIP_MAIN_VOLTAGE_V = 440.0       # 3-phase AC
SHIP_EMERGENCY_VOLTAGE_V = 230.0  # Single-phase or 3-phase
SHIP_LOW_VOLTAGE_V = 24.0         # DC for control circuits

# IEC 60092-502: Insulation monitoring requirements.
INSULATION_MONITOR_THRESHOLD_KOHM = 100.0  # Alarm at <100 kΩ

# SOLAS II-2/5.1.3: Fire-detection system must have ≥30 min UPS autonomy.
FIRE_SYSTEM_UPS_MIN_AUTONOMY_MIN = 30.0

# IEC 60092-504: Hazardous-area Zone 0/1/2 definitions.
HAZARDOUS_ZONE_DEFINITIONS = {
    "zone_0": "Continuous presence of flammable gas (>1000 h/year)",
    "zone_1": "Likely presence during normal operation (10–1000 h/year)",
    "zone_2": "Unlikely presence, short duration (<10 h/year)",
}


# ─── ISO 15370 Thermal Alarms ───────────────────────────────────────────────

# ISO 15370: Thermal alarm response temperatures.
THERMAL_ALARM_RESPONSE_C = {
    "thermal_a": 70.0,   # ±5°C — for low-ambient areas
    "thermal_b": 90.0,   # ±5°C — for warmer areas
}

# Maximum spacing of thermal alarms in escape routes.
THERMAL_ALARM_MAX_SPACING_M = 10.0


# ─── NFPA 302 (Small Craft) ─────────────────────────────────────────────────

# NFPA 302-2020 §6.2: Required portable extinguishers by vessel length.
NFPA302_PORTABLE_EXTINGUISHERS = {
    # (length_feet, min_rating, type)
    (0, 26): (5, "B:C"),       # <26 ft: 1× 5-B:C
    (26, 40): (10, "B:C"),     # 26–40 ft: 2× 5-B:C or 1× 10-B:C
    (40, 65): (20, "B:C"),     # 40–65 ft: 2× 10-B:C or 1× 20-B:C
    (65, 999): (40, "B:C"),    # >65 ft: 2× 20-B:C or fixed system
}

# NFPA 302 §7.4: Fixed fire-extinguishing system required for galley.
NFPA302_GALLEY_FIXED_SYSTEM_REQUIRED = True
NFPA302_GALLEY_FIXED_AGENT = "dry_chemical"  # or AFFF/CO2


# ─── Lloyd's Register (LR) Additional Rules ─────────────────────────────────

# LR Rules Part 6: Fire-detection system response time.
LR_MAX_DETECTOR_RESPONSE_S = 30.0   # Within 30 s of fire start

# LR Rules: Maximum number of detectors per addressable loop.
LR_MAX_DETECTORS_PER_LOOP = 200

# LR Rules: Redundancy for fire mains.
LR_FIRE_MAIN_REDUNDANCY = 2  # 2 independent fire pumps
