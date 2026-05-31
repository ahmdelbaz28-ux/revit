"""
QOMN-FIRE CORE DATA TYPES
Conformant with ISO 19650 BIM Standards and QOMN Deterministic Software Design.
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
    EMT = "EMT"
    RMC = "RMC"
    FMC = "FMC"

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
class Device:
    id: str
    device_type: DeviceType
    location: Point3D
    elevation_ft: float
    circuit: str
    zone: str

    def compute_hash(self) -> str:
        serialized = f"{self.id}:{self.device_type.value}:{self.location.x},{self.location.y},{self.location.z}:{self.elevation_ft}:{self.circuit}:{self.zone}"
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
class Legend:
    pattern_name: str
    description: str
    code_reference: str

@dataclass(frozen=True, slots=True)
class Revision:
    number: int
    date: str
    description: str
    by: str
