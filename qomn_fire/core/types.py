"""
QOMN-FIRE UNIFIED DATA TYPES
Conformant with ISO 19650 BIM Standards and QOMN Deterministic Software Design.
Extended with building model types for IFC/DXF parsing pipeline.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Tuple, List, Dict, Any, Optional, Union
import hashlib

class DeviceType(Enum):
    SMOKE_DETECTOR = "SMOKE_DETECTOR"
    HEAT_DETECTOR = "HEAT_DETECTOR"
    MANUAL_PULL_STATION = "MANUAL_PULL_STATION"
    HORN_STROBE = "HORN_STROBE"

class ConduitType(Enum):
    EMT = "EMT"  # Electrical Metallic Tubing (NEC Art. 358)
    RMC = "RMC"  # Rigid Metal Conduit (NEC Art. 344)
    FMC = "FMC"  # Flexible Metal Conduit (NEC Art. 348)

class FittingType(Enum):
    ELBOW_90 = "ELBOW_90"
    TEE = "TEE"
    COUPLING = "COUPLING"

@dataclass(frozen=True, slots=True)
class Point3D:
    x: float
    y: float
    z: float = 0.0

    def __post_init__(self):
        object.__setattr__(self, 'x', round(float(self.x), 4))
        object.__setattr__(self, 'y', round(float(self.y), 4))
        object.__setattr__(self, 'z', round(float(self.z), 4))

    def to_tuple(self) -> Tuple[float, float, float]:
        return (self.x, self.y, self.z)

    def to_dict(self) -> Dict[str, float]:
        return {"X": self.x, "Y": self.y, "Z": self.z}

@dataclass(frozen=True, slots=True)
class Wall:
    """Structural wall element extracted from IFC/DXF parsing."""
    id: str
    start: Point3D
    end: Point3D
    height_m: float
    thickness_m: float

@dataclass(frozen=True, slots=True)
class Opening:
    """Door or window opening in a wall."""
    id: str
    opening_type: str  # "DOOR" or "WINDOW"
    location: Point3D
    width_m: float
    height_m: float

@dataclass(frozen=True, slots=True)
class Room:
    """Enclosed room/space with boundary polygon."""
    id: str
    name: str
    boundary: Tuple[Point3D, ...]
    area_m2: float
    height_m: float

@dataclass(frozen=True, slots=True)
class Building:
    """Top-level building model containing all parsed geometric elements."""
    file_hash: str
    format_detected: str
    version_detected: str
    units: str  # Expected "METERS"
    walls: Tuple[Wall, ...]
    rooms: Tuple[Room, ...]
    openings: Tuple[Opening, ...]
    # BUG-9 FIX: Flag indicates if the building model contains fallback/placeholder
    # geometry rather than real parsed geometry. Downstream systems MUST check this
    # flag — fire protection design based on fallback geometry is INVALID.
    # If True, the building model should be treated as unvalidated and the
    # user must provide a properly parsed BIM file.
    has_fallback_geometry: bool = False

    def compute_hash(self) -> str:
        # BUG FIX: Original hash only included COUNT of rooms/walls,
        # not their IDs or data. Two buildings with 1 room each but
        # different room IDs produced the SAME hash — broken traceability.
        # Now includes room IDs and wall IDs for deterministic differentiation.
        # Also includes has_fallback_geometry flag — a building with fallback
        # geometry is fundamentally different from one with real geometry.
        room_ids = ",".join(r.id for r in self.rooms)
        wall_ids = ",".join(w.id for w in self.walls)
        serialized = f"{self.file_hash}:{self.format_detected}:{self.version_detected}:{self.units}:{len(self.walls)}:{wall_ids}:{len(self.rooms)}:{room_ids}:{self.has_fallback_geometry}"
        return hashlib.sha256(serialized.encode("utf-8")).hexdigest()

@dataclass(frozen=True, slots=True)
class Device:
    id: str
    device_type: DeviceType
    location: Point3D
    elevation_ft: float
    circuit: str
    zone: str

    def compute_hash(self) -> str:
        serialized = f"{self.id}:{self.device_type.value}:{self.location.x:.4f},{self.location.y:.4f},{self.location.z:.4f}:{self.elevation_ft}:{self.circuit}:{self.zone}"
        return hashlib.sha256(serialized.encode("utf-8")).hexdigest()

@dataclass(frozen=True, slots=True)
class Fitting:
    fitting_type: FittingType
    location: Point3D

@dataclass(frozen=True, slots=True)
class ConduitRun:
    id: str
    conduit_type: ConduitType
    trade_size: str
    points: Tuple[Point3D, ...]
    total_length_ft: float
    bend_count: int
    fittings: Tuple[Fitting, ...]

    def compute_hash(self) -> str:
        pt_strs = ",".join([f"{p.x:.4f},{p.y:.4f},{p.z:.4f}" for p in self.points])
        serialized = f"{self.id}:{self.conduit_type.value}:{self.trade_size}:{pt_strs}:{self.total_length_ft:.4f}:{self.bend_count}"
        return hashlib.sha256(serialized.encode("utf-8")).hexdigest()

@dataclass(frozen=True, slots=True)
class FireAlarmPanel:
    model: str
    manufacturer: str
    points_capacity: int
    nac_capacity: int
    supports_networking: bool
    supports_voice: bool
    supports_releasing: bool
    max_slc_loops: int
    listings: Tuple[str, ...]
    standby_current_amps: float
    alarm_current_amps: float
    power_supply_watts: int

@dataclass(frozen=True, slots=True)
class ProjectRequirements:
    device_count: int
    nac_circuit_count: int
    building_size_m2: float
    building_floors: int
    requires_network: bool
    requires_voice: bool
    requires_releasing: bool
    jurisdiction: str
    preferred_manufacturer: Optional[str] = None

@dataclass(frozen=True, slots=True)
class PanelRecommendation:
    recommended_model: str
    manufacturer: str
    capacity_utilization: float
    nac_utilization: float
    battery_size_ah: float
    battery_derating_details: Dict[str, Any]
    power_supply_watts: int
    listings: Tuple[str, ...]
    code_compliance: Tuple[str, ...]
    warnings: Tuple[str, ...]
    alternatives: Tuple[str, ...]
    signature_hash: str

@dataclass(frozen=True, slots=True)
class HatchSpec:
    pattern_name: str
    angle: float
    scale: float
    color: int
    layer: str
    description: str
    code_reference: str

@dataclass(frozen=True, slots=True)
class TitleBlock:
    project_name: str
    drawing_number: str
    sheet_title: str
    scale: str
    date: str
    designer: str
    checker: str
    pe_stamp: str
    client: str
    address: str

@dataclass(frozen=True, slots=True)
class Revision:
    number: int
    date: str
    description: str
    by: str
