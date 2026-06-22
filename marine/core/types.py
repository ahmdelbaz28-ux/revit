"""
marine/core/types.py — Domain Types for Marine Fire Safety
===========================================================
Single source of truth for all marine-related data structures. Every
engine, integration, and router imports from here — no duplicate
definitions anywhere.

Standards mapped:
    - SOLAS II-2 ship types          → ShipType
    - SOLAS II-2 fire divisions      → FireClass
    - IEC 60092-502 detector types   → DetectorType
    - IMO MSC.1/Circ.1316/1165       → ExtinguishingSystem
    - ISO 15370 thermal alarms       → ThermalAlarmClass
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple


# ─── Ship Classification (SOLAS II-2 / IMO) ─────────────────────────────────

class ShipType(str, Enum):
    """SOLAS ship-type classification per SOLAS Ch. II-2/2.2.

    The ship type drives the applicable fire-protection ruleset:
      - PASSENGER  → SOLAS II-2 Part D (special passenger rules)
      - CARGO      → SOLAS II-2 Part C (cargo ship rules)
      - TANKER     → SOLAS II-2 Part C + IEC 60092-502 (tanker-specific)
      - OFFSHORE   → MODU Code (Mobile Offshore Drilling Units)
      - SMALL_CRAFT → NFPA 302 (replaces SOLAS for <24m load line craft)
    """
    PASSENGER = "passenger"        # >12 passengers (SOLAS II-2 Part D)
    CARGO = "cargo"                # General cargo ships (SOLAS II-2 Part C)
    TANKER = "tanker"              # Oil/chemical/gas carriers (IEC 60092-502)
    OFFSHORE = "offshore"          # MODU — Mobile Offshore Drilling Units
    SMALL_CRAFT = "small_craft"    # <24m load line — NFPA 302 applies


class ShipService(str, Enum):
    """Ship service category — refines ShipType for rule selection."""
    CONTAINER = "container"
    BULK_CARRIER = "bulk_carrier"
    RO_RO = "ro_ro"               # Roll-on/roll-off
    GAS_CARRIER = "gas_carrier"   # LNG/LPG
    CHEMICAL_TANKER = "chemical_tanker"
    OIL_TANKER = "oil_tanker"
    FPSO = "fpso"                 # Floating Production Storage Offloading
    PASSENGER_FERRY = "passenger_ferry"
    CRUISE = "cruise"
    MODU = "modu"                 # Mobile Offshore Drilling Unit
    WORKBOAT = "workboat"         # <24m, NFPA 302
    YACHT = "yacht"               # <24m, NFPA 302


# ─── Fire Divisions (SOLAS II-2 Reg. 9) ─────────────────────────────────────

class FireClass(str, Enum):
    """SOLAS II-2/9.2 fire division classification.

    "A" class divisions (steel/equivalent + insulation):
      - A-60: 60 minutes insulation (engine rooms, cargo spaces, galleys)
      - A-30: 30 minutes
      - A-15: 15 minutes
      - A-0:  steel without insulation

    "B" class divisions (non-combustible materials):
      - B-15: 15 minutes integrity (passenger corridor bulkheads)
      - B-0:  non-combustible, no rating

    "C" class divisions: non-combustible, no fire rating.
    """
    A_60 = "A-60"
    A_30 = "A-30"
    A_15 = "A-15"
    A_0 = "A-0"
    B_15 = "B-15"
    B_0 = "B-0"
    C = "C"

    @property
    def insulation_minutes(self) -> int:
        """Return required insulation time in minutes (0 for A-0, B-0, C)."""
        mapping = {
            FireClass.A_60: 60, FireClass.A_30: 30, FireClass.A_15: 15,
            FireClass.A_0: 0, FireClass.B_15: 15, FireClass.B_0: 0,
            FireClass.C: 0,
        }
        return mapping[self]


class SpaceCategory(str, Enum):
    """SOLAS II-2 space categories for fire-rating assignment.

    Per SOLAS II-2 Table 9.1 — the matrix of required fire divisions
    between adjacent spaces. The categories drive FireClass selection.
    """
    CONTROL_STATION = "control_station"            # Wheelhouse, radio room
    ESCAPE_ROUTE = "escape_route"                   # Corridors, stairways
    ACCOMMODATION = "accommodation"                 # Cabins, mess rooms
    SERVICE_SPACE_MINOR = "service_minor"           # Linen lockers, pantries
    SERVICE_SPACE_MAJOR = "service_major"           # Galleys, main laundries
    CARGO_SPACE = "cargo_space"                     # Hold, tank deck
    MACHINERY_SPACE_A = "machinery_a"               # Contains main propulsion
    MACHINERY_SPACE_OTHER = "machinery_other"       # Auxiliary machinery
    TANK_SPACE = "tank_space"                       # Cargo/ballast/fuel tanks
    EMPTY_SPACE = "empty_space"                     # Cofferdams, voids
    OPEN_DECK = "open_deck"


# ─── Fire Detection (IEC 60092-502 / FSS Code Ch. 9) ────────────────────────

class DetectorType(str, Enum):
    """Marine fire detector types per IEC 60092-502 and FSS Code Ch. 9.

    Selection rules:
      - Heat detectors   → engine rooms, galleys, drying rooms (high ambient)
      - Smoke detectors  → accommodation, corridors, escape routes
      - Flame detectors  → open decks, pump rooms (UV/IR for hydrocarbon fires)
      - CO detectors     → accommodation (early warning for smouldering fires)
      - Multi-criteria   → high-value spaces (combine 2+ sensor types)
    """
    HEAT_FIXED = "heat_fixed"               # Fixed temperature (e.g. 57°C, 78°C)
    HEAT_RATE_OF_RISE = "heat_ror"          # Rate-of-rise (8.3°C/min per FSS 9.2.1)
    SMOKE_IONIZATION = "smoke_ion"          # Ionization smoke (legacy)
    SMOKE_PHOTOELECTRIC = "smoke_photo"     # Photoelectric (modern standard)
    SMOKE_DUCT = "smoke_duct"               # Duct smoke detection (HVAC)
    FLAME_UV = "flame_uv"                   # Ultraviolet flame
    FLAME_IR = "flame_ir"                   # Infrared flame
    FLAME_UV_IR = "flame_uv_ir"             # Combined UV/IR (hydrocarbon)
    CO = "co"                               # Carbon monoxide
    MULTICRITERIA = "multicriteria"         # Combined heat+smoke+CO
    LINEAR_HEAT = "linear_heat"             # Linear heat detection cable
    ASPIRATING = "aspirating"               # ASD — high-sensitivity sampling


class AlarmLevel(str, Enum):
    """SOLAS II-2/5 alarm action levels."""
    FAULT = "fault"             # Detector fault (open/short circuit)
    PRE_ALARM = "pre_alarm"     # Early warning (engineer action only)
    ALARM = "alarm"             # Muster alarm (general evacuation)
    ACTION = "action"           # Triggers extinguishment (CO2 release, etc.)


# ─── Extinguishing Systems (IMO MSC.1/Circ.1316/1165) ───────────────────────

class ExtinguishingSystem(str, Enum):
    """Marine fixed fire-extinguishing systems per SOLAS II-2/10.

    Selection by space + hazard:
      - WATER_MIST      → machinery spaces, accommodation (MSC.1/Circ.1165)
      - CO2_TOTAL       → cargo holds, engine rooms (MSC.1/Circ.1316)
      - FOAM_LOW        → cargo tank deck (low-expansion foam)
      - FOAM_HIGH       → flight decks, engine rooms (high-expansion)
      - AFFF            → helidecks, flammable liquid spills
      - DRY_CHEMICAL    → small hazards, galley hoods
      - SPRINKLER       → accommodation (SOLAS II-2/8)
      - INERT_GAS       → cargo tanks (IG system — tankers)
    """
    WATER_MIST = "water_mist"
    CO2_TOTAL = "co2_total"
    FOAM_LOW = "foam_low"
    FOAM_HIGH = "foam_high"
    AFFF = "afff"
    DRY_CHEMICAL = "dry_chemical"
    SPRINKLER = "sprinkler"
    INERT_GAS = "inert_gas"


class FireHazardClass(str, Enum):
    """NFPA 10 + marine fire hazard classification."""
    A = "A"  # Ordinary combustibles (wood, paper, textiles)
    B = "B"  # Flammable liquids (oil, fuel, paint)
    C = "C"  # Energized electrical equipment
    D = "D"  # Combustible metals (magnesium, titanium)
    K = "K"  # Cooking oils and fats (galley)


# ─── Thermal Alarms (ISO 15370) ─────────────────────────────────────────────

class ThermalAlarmClass(str, Enum):
    """ISO 15370 thermal alarm classes for passenger-ship escape routes."""
    CLASS_A = "thermal_a"   # Responds at 70°C ± 5°C
    CLASS_B = "thermal_b"   # Responds at 90°C ± 5°C


# ─── Core Data Structures ────────────────────────────────────────────────────

@dataclass(frozen=True)
class ShipProject:
    """Top-level marine project descriptor.

    Captures the ship identity and classification that drives rule
    selection across all engines. Created once per project; passed
    immutably to every engine function.
    """
    project_id: str
    ship_name: str
    imo_number: Optional[str] = None        # 7-digit IMO ship number
    ship_type: ShipType = ShipType.CARGO
    service: ShipService = ShipService.BULK_CARRIER
    length_overall_m: float = 0.0           # LOA in metres
    gross_tonnage: float = 0.0              # GT
    passenger_capacity: int = 0             # >12 → SOLAS passenger rules
    flag_state: str = ""                    # For flag-state requirements
    classification_society: str = "LR"      # LR, DNV, BV, ABS, etc.
    build_date: Optional[str] = None        # YYYY-MM-DD (keel-lay date)

    @property
    def is_passenger_ship(self) -> bool:
        """Per SOLAS II-2/2.2: a ship carrying more than 12 passengers."""
        return self.ship_type == ShipType.PASSENGER or self.passenger_capacity > 12

    @property
    def is_tanker(self) -> bool:
        return self.ship_type == ShipType.TANKER

    @property
    def is_small_craft(self) -> bool:
        """NFPA 302 applies if length < 24m OR explicitly small_craft."""
        return self.ship_type == ShipType.SMALL_CRAFT or self.length_overall_m < 24.0


@dataclass(frozen=True)
class MarineZone:
    """A fire-protection zone per SOLAS II-2 main-vertical-zone concept.

    SOLAS II-2/2.2: "Main vertical zones" — the ship is divided into
    vertical zones by A-60 class bulkheads, not more than 40m apart,
    to contain fire within one zone.
    """
    zone_id: str
    name: str
    space_category: SpaceCategory
    deck: str                                # e.g. "A-deck", "engine-room"
    frame_start: int                         # Ship frame number (forward)
    frame_end: int                           # Ship frame number (aft)
    area_m2: float                           # Floor area in m²
    height_m: float                          # Deck head height
    required_fire_class: FireClass = FireClass.A_60
    hazard_class: FireHazardClass = FireHazardClass.A
    ventilation_rate_ach: float = 0.0        # Air changes per hour
    has_escape_route: bool = True
    escape_route_count: int = 1              # SOLAS II-2/13.3.2 escape-route count
    max_distance_to_stairway_m: Optional[float] = None  # SOLAS II-2/13.3.2.1
    shape_polygon: Optional[List[Tuple[float, float]]] = None  # Zone footprint (m)
    adjacent_zones: Tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class DetectorPlacement:
    """Result of detector-selector engine: one detector's placement."""
    detector_id: str
    zone_id: str
    detector_type: DetectorType
    position_xyz_mm: Tuple[float, float, float]   # mm from ship origin
    coverage_m2: float
    rated_temp_c: Optional[float] = None           # For HEAT_FIXED
    sensitivity: Optional[str] = None              # For SMOKE_PHOTO etc.
    mounting_height_m: float = 3.0
    standard_reference: str = "IEC 60092-502 §4"


@dataclass(frozen=True)
class FireResistanceSpec:
    """Specification of a fire division (bulkhead or deck)."""
    division_id: str
    from_zone: str
    to_zone: str
    required_class: FireClass
    material: str                                # "steel", "non-combustible"
    insulation_material: Optional[str] = None    # "ceramic wool", "A-60 board"
    insulation_thickness_mm: float = 0.0
    penetration_protected: bool = True           # Cable/pipe penetrations
    standard_reference: str = "SOLAS II-2/9.2"


@dataclass(frozen=True)
class ExtinguishingDesign:
    """Result of extinguishment engine for one protected space."""
    system_type: ExtinguishingSystem
    protected_zone: str
    protected_volume_m3: float
    agent_quantity_kg: float                     # CO2 mass, water mist L/min
    design_concentration_pct: float              # % by volume
    discharge_time_s: float                      # Seconds to reach concentration
    hold_time_min: float                         # Required soak time
    nozzles: int
    pipe_length_m: float
    standard_reference: str = "IMO MSC.1/Circ.1316"


@dataclass(frozen=True)
class AlarmLogicNode:
    """Node in the alarm logic tree (PLC/DCS programmable logic)."""
    node_id: str
    trigger_detector: str                        # Detector ID
    zone_id: str
    alarm_level: AlarmLevel
    action_outputs: Tuple[str, ...]              # e.g. ("horn_z3", "release_co2")
    delay_s: float = 0.0
    interlocks: Tuple[str, ...] = field(default_factory=tuple)
    standard_reference: str = "SOLAS II-2/5 + IEC 60092-502"


@dataclass(frozen=True)
class ShipElectricalSpec:
    """Marine electrical system specification per IEC 60092 series.

    Covers power supply for fire-detection/alarm/extinguishing systems
    with mandatory redundancy and UPS per SOLAS II-2/5.1.3.
    """
    main_supply_voltage: float = 440.0           # V AC (IEC 60092-301)
    emergency_supply_voltage: float = 230.0      # V AC
    ups_capacity_ah: float = 0.0                 # Battery capacity (Ah)
    ups_autonomy_min: float = 30.0               # SOLAS: ≥30 min for fire systems
    redundancy_level: int = 2                    # 1=main, 2=main+emergency, 3=+UPS
    insulation_monitoring: bool = True           # IEC 60092-504 mandatory
    standard_reference: str = "IEC 60092-502 + SOLAS II-2/5.1.3"


# ─── Validation Result ───────────────────────────────────────────────────────

@dataclass
class ComplianceResult:
    """Generic compliance-check result returned by every engine."""
    compliant: bool
    findings: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    standard_reference: str = ""
    details: Dict[str, Any] = field(default_factory=dict)

    def add_finding(self, msg: str) -> None:
        self.findings.append(msg)
        self.compliant = False

    def add_warning(self, msg: str) -> None:
        self.warnings.append(msg)
