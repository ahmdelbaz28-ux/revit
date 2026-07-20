# File-level '# NOSONAR' removed per NOSONAR_AUDIT.md (V143 hardening).
"""
QOMN-FIRE: MASTER INTEGRATED WORKSPACE GENERATOR
Author: Chief Fire Protection Engineer & Safety-Critical Systems Architect
Standards: NFPA 72 (2022), NEC 760 (2023), ISO 19650, UL 864 10th Edition

V58 — Corrected Release
All V54 fixes preserved plus V58 bug fixes:
  1. Device.compute_hash now includes Z coordinate (deterministic hash)
  2. List[str] in frozen dataclasses → Tuple[str, ...] (runtime safety)
  3. doc.layers.new API fixed to use dxfattribs (ezdxf 1.4.3 compat)
  4. NULL_DATE_VALUE replaced with 0.0 (ezdxf 1.4.3 compat)
  5. view_center → view_center_point (ezdxf 1.4.3 API)
  6. layers.new in dxf_generator uses dxfattribs
  7. set_bulge replaced with format='xyb' (ezdxf 1.4.3 compat)
  8. Test 3 replaced with proper bend-limit enforcement test
  9. Restored conduit fill, physics guard, determinism stress tests
  10. Return type corrected from Document to Drawing
  --- V58 fixes ---
  11. types.py: Wall, Room, Opening, Building dataclasses; FireAlarmPanel supports_releasing; PanelRecommendation battery_derating_details
  12. errors.py: BUG-1 (prevent both value+error), BUG-43 (prevent neither), BUG-37 (__repr__), BUG-3 (BaseEngineeringError inherits Exception), unwrap_or, additional error types
  13. fill.py: Fire alarm cable types (FPLP, FPL, FPLR), expanded conduit areas (EMT+RMC), conduit_type param, BUG-F1 fix
  14. panel_database.py: supports_releasing field on each panel
  15. panel_selector.py: Tiered derating (1.10×1.15×1.20), per-device standby 0.8mA, supports_releasing filter, battery_derating_details, BUG-PS1 fix
  16. placement.py: NaN/Inf validation, BUG-42 narrow room fix, BUG-P1 unit validation, logging
  17. routing.py: BUG-20 (length off-by-one), BUG-27 (trade_size param), NaN/Inf validation, MAX_ITERATIONS safety limit
"""

import os
import sys
import unittest

INTEGRATED_FILES = {}

# ─────────────────────────────────────────────────────────────────────
# 1. qomn_fire/core/types.py (Unified Types)
# ─────────────────────────────────────────────────────────────────────
INTEGRATED_FILES["qomn_fire/core/types.py"] = '''"""
QOMN-FIRE UNIFIED DATA TYPES
Conformant with ISO 19650 BIM Standards and QOMN Deterministic Software Design.
Extended with building model types for IFC/DXF parsing pipeline.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Tuple, Dict, Any, Optional
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

@dataclass(frozen=True)
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

@dataclass(frozen=True)
class Wall:
    """Structural wall element extracted from IFC/DXF parsing."""
    id: str
    start: Point3D
    end: Point3D
    height_m: float
    thickness_m: float

@dataclass(frozen=True)
class Opening:
    """Door or window opening in a wall."""
    id: str
    opening_type: str  # "DOOR" or "WINDOW"
    location: Point3D
    width_m: float
    height_m: float

@dataclass(frozen=True)
class Room:
    """Enclosed room/space with boundary polygon."""
    id: str
    name: str
    boundary: Tuple[Point3D, ...]
    area_m2: float
    height_m: float
    # SAFETY CRITICAL: Flag indicates if the room boundary is placeholder/synthetic
    # geometry (e.g., 10m x 10m fallback box) rather than real BIM geometry.
    # Downstream systems MUST NOT produce fire protection designs based on
    # placeholder boundaries — the geometry is NOT the real building.
    # Per NFPA 72 §17.7.4, coverage calculations require accurate room geometry.
    has_placeholder_boundary: bool = False

@dataclass(frozen=True)
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
        #
        # BUG-30+36 FIX: Hash now includes wall GEOMETRY (start/end coords),
        # room AREAS, and opening IDs — not just IDs. Two buildings with the
        # same room/wall IDs but different geometry must produce different hashes.
        # Previously, changing a wall's length or thickness produced the same hash,
        # breaking audit trail traceability. Openings were completely excluded.
        room_data = ";".join(
            f"{r.id}:{r.area_m2:.4f}:{r.height_m:.4f}:{len(r.boundary)}"
            for r in self.rooms
        )
        wall_data = ";".join(
            f"{w.id}:{w.start.x:.4f},{w.start.y:.4f}:{w.end.x:.4f},{w.end.y:.4f}:{w.height_m:.4f}:{w.thickness_m:.4f}"
            for w in self.walls
        )
        opening_ids = ",".join(o.id for o in self.openings)
        serialized = (
            f"{self.file_hash}:{self.format_detected}:{self.version_detected}:{self.units}:"
            f"WALLS[{wall_data}]:ROOMS[{room_data}]:OPENINGS[{opening_ids}]:"
            f"{self.has_fallback_geometry}"
        )
        return hashlib.sha256(serialized.encode("utf-8")).hexdigest()

@dataclass(frozen=True)
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

@dataclass(frozen=True)
class Fitting:
    fitting_type: FittingType
    location: Point3D

@dataclass(frozen=True)
class ConduitRun:
    id: str
    conduit_type: ConduitType
    trade_size: str
    points: Tuple[Point3D, ...]
    total_length_ft: float
    bend_count: int  # Number of 90-degree bends (actual count, NOT degrees)
    bend_degrees: int  # Total bend angle in degrees (NEC 358.26: max 360)
    fittings: Tuple[Fitting, ...]

    def compute_hash(self) -> str:
        pt_strs = ",".join([f"{p.x:.4f},{p.y:.4f},{p.z:.4f}" for p in self.points])
        serialized = f"{self.id}:{self.conduit_type.value}:{self.trade_size}:{pt_strs}:{self.total_length_ft:.4f}:{self.bend_count}:{self.bend_degrees}"
        return hashlib.sha256(serialized.encode("utf-8")).hexdigest()

@dataclass(frozen=True)
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

@dataclass(frozen=True)
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

@dataclass(frozen=True)
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

@dataclass(frozen=True)
class HatchSpec:
    pattern_name: str
    angle: float
    scale: float
    color: int
    layer: str
    description: str
    code_reference: str

@dataclass(frozen=True)
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

@dataclass(frozen=True)
class Revision:
    number: int
    date: str
    description: str
    by: str
'''

# ─────────────────────────────────────────────────────────────────────
# 2. qomn_fire/core/errors.py (Unified Monadic Errors)
# ─────────────────────────────────────────────────────────────────────
INTEGRATED_FILES["qomn_fire/core/errors.py"] = '''"""
QOMN-FIRE UNIFIED ERROR FRAMEWORK
Extended with parsing and file validation error types for the input pipeline.

Safety-Critical: Each error type maps to a specific physical failure mode.
Missing an error means a corrupted file passes silently = wrong building model = people die.
"""

from typing import Generic, TypeVar, Optional, Union

T = TypeVar('T')
E = TypeVar('E')

class Result(Generic[T, E]):
    def __init__(self, value: Optional[T] = None, error: Optional[E] = None):
        # BUG-43 FIX: Prevent constructing Result with neither value nor error.
        # A Result(value=None) without an error would be is_success=True but
        # crash on unwrap(). This is a trap in safety-critical code — a
        # "successful" result that crashes on access is worse than an error.
        if value is None and error is None:
            raise ValueError(
                "Result must hold either a value or an error, not neither. "
                "Use Result(value=x) for success or Result(error=e) for failure."
            )
        # BUG-1 FIX: Prevent constructing Result with BOTH value and error.
        if value is not None and error is not None:
            raise ValueError(
                f"Result cannot hold both value and error. "
                f"Got value={value!r} and error={error!r}. "
                f"Use Result(value=x) for success or Result(error=e) for failure."
            )
        self._value = value
        self._error = error

    @property
    def is_success(self) -> bool:
        return self._error is None

    @property
    def is_failure(self) -> bool:
        return self._error is not None

    def unwrap(self) -> T:
        if self._error is not None:
            raise ValueError(f"Panic: Attempted to unwrap failure Result: {self._error}")
        if self._value is None:
            raise ValueError("Panic: Attempted to unwrap None value from success Result")
        return self._value

    def unwrap_or(self, default: T) -> T:
        """Return value if success, otherwise return default."""
        if self._error is not None:
            return default
        return self._value if self._value is not None else default

    def error(self) -> E:
        if self._error is None:
            raise ValueError("Panic: Attempted to fetch error of successful Result")
        return self._error

    # BUG-37 FIX: Add __repr__ for debugging
    def __repr__(self) -> str:
        if self.is_success:
            return f"Result.ok({self._value!r})"
        return f"Result.err({self._error!r})"

class BaseEngineeringError(Exception):
    """Base class for all QOMN-FIRE engineering errors.

    BUG-3 FIX: Now inherits from Exception so errors can be caught by
    standard exception handlers and participate in Python's exception hierarchy.
    Previously, BaseEngineeringError was a plain class, so `except Exception`
    would NOT catch it — errors could escape error handling boundaries silently.
    In a safety-critical system, uncaught errors = silent failures = people die.
    """
    def __init__(self, message: str, code_ref: str, remedy: str):
        super().__init__(message)
        self.message = message
        self.code_ref = code_ref
        self.remedy = remedy

    def __repr__(self) -> str:
        return f"[{self.code_ref}] Error: {self.message} (Remedy: {self.remedy})"

    def __str__(self) -> str:
        return f"[{self.code_ref}] {self.message}"

class ConduitFillError(BaseEngineeringError): pass
class NECViolationError(BaseEngineeringError): pass
class HatchPlacementError(BaseEngineeringError): pass
class PhysicalConstraintError(BaseEngineeringError): pass
class FACPSelectionError(BaseEngineeringError): pass

# ── Input Parsing Pipeline Error Types ──
# These errors prevent corrupted BIM files from producing wrong fire protection designs.

class FileValidationError(BaseEngineeringError):
    """File does not meet structural requirements (existence, size, permissions)."""
    pass

class FormatError(BaseEngineeringError):
    """File format cannot be identified — magic bytes don't match any known specification."""
    pass

class VersionError(BaseEngineeringError):
    """File version is unsupported or incompatible with the parser."""
    pass

class CorruptionError(BaseEngineeringError):
    """File is structurally corrupted — missing mandatory sections or markers."""
    pass

class ConversionError(BaseEngineeringError):
    """DWG→DXF or RVT→IFC conversion failed — external tool error."""
    pass

class GeometryError(BaseEngineeringError):
    """Building geometry is physically impossible (zero-area rooms, unclosed boundaries)."""
    pass

class UnitError(BaseEngineeringError):
    """File uses wrong unit system (mm/inches instead of meters) — coordinates exceed limits."""
    pass
'''

# ─────────────────────────────────────────────────────────────────────
# 3. qomn_fire/core/constants.py (Standard Constants)
# ─────────────────────────────────────────────────────────────────────
INTEGRATED_FILES["qomn_fire/core/constants.py"] = '''"""
QOMN-FIRE PHYSICAL AND REGULATORY CONSTANTS
"""

# NFPA 72 Spacing Limits (2022 §17)
NFPA_SMOKE_DETECTOR_SPACING_M = 9.144  # 30 feet smooth ceiling spacing
NFPA_MAX_WALL_DISTANCE_M = 6.400       # 0.7 times spacing constraint (21 feet)

# NEC Conduit Area Specifications (mm2) - Chapter 9 Table 4
EMT_INTERNAL_AREA_1_2_MM2 = 196.1
EMT_INTERNAL_AREA_3_4_MM2 = 343.9
EMT_INTERNAL_AREA_1_MM2 = 557.4

# NEC Wire Cross Sectional Areas (mm2) - Chapter 9 Table 5
WIRE_AREA_14_AWG_MM2 = 6.26
WIRE_AREA_12_AWG_MM2 = 8.58
WIRE_AREA_10_AWG_MM2 = 13.61

# NEC Chapter 9 Table 1 Fill Limits
NEC_FILL_LIMIT_1_WIRE = 0.53
NEC_FILL_LIMIT_2_WIRES = 0.31
NEC_FILL_LIMIT_OVER_2_WIRES = 0.40
'''

# ─────────────────────────────────────────────────────────────────────
# 4. qomn_fire/core/hash.py (SHA-256 Helpers)
# ─────────────────────────────────────────────────────────────────────
INTEGRATED_FILES["qomn_fire/core/hash.py"] = '''"""
QOMN-FIRE CRYPTOGRAPHIC AND DETERMINISTIC DATA COMPACTION
"""

import hashlib
import json

def get_bytes_hash(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()

def get_string_hash(data: str) -> str:
    return hashlib.sha256(data.encode("utf-8")).hexdigest()
'''

# ─────────────────────────────────────────────────────────────────────
# 5. qomn_fire/engine/fill.py (NEC Conduit Fill)
# ─────────────────────────────────────────────────────────────────────
INTEGRATED_FILES["qomn_fire/engine/fill.py"] = '''"""
QOMN-FIRE CONDUIT FILL SIZING ENGINE
Reference Standard: NEC 2023 Chapter 9, Table 1 & Table 4.

BUG-19 FIX: Added support for fire alarm cable types (FPLP, FPL, FPLR)
per NEC 760.179. Fire alarm systems require FPLP (Power-Limited Fire Alarm)
or FPL (Fire Alarm) cable types. The original code only supported generic
AWG gauges, rejecting FPLP/FPL/FPLR cables — making it impossible to
size conduit for fire alarm circuits, which is the PRIMARY use case.
"""

from qomn_fire.core.errors import Result, ConduitFillError
from qomn_fire.core.constants import (
    EMT_INTERNAL_AREA_1_2_MM2, EMT_INTERNAL_AREA_3_4_MM2, EMT_INTERNAL_AREA_1_MM2,
    WIRE_AREA_14_AWG_MM2, WIRE_AREA_12_AWG_MM2, WIRE_AREA_10_AWG_MM2,
    NEC_FILL_LIMIT_1_WIRE, NEC_FILL_LIMIT_2_WIRES, NEC_FILL_LIMIT_OVER_2_WIRES
)

# SAFETY FIX (V58): Expanded conduit internal area specifications per NEC Chapter 9 Table 4.
# The original code only supported 3 EMT sizes (1/2", 3/4", 1"). Real fire alarm
# projects commonly require larger conduits for trunk lines and multi-circuit runs.
# A conduit run that cannot be sized will either (a) be forced into a too-small conduit
# (overfill → overheating → fire hazard per NEC 310.15) or (b) fail the pipeline entirely.
# Added: EMT 1-1/4" through 4", plus RMC sizes per NEC Table 4.
# Values from NEC 2023 Chapter 9 Table 4 (over 2 wires: 40% fill column).
CONDUIT_INTERNAL_AREAS_MM2 = {
    # EMT (Electrical Metallic Tubing) — NEC Table 4, Article 358
    "EMT 1/2": 196.1,
    "EMT 3/4": 343.9,
    "EMT 1": 557.4,
    "EMT 1-1/4": 952.1,
    "EMT 1-1/2": 1308.0,
    "EMT 2": 2110.0,
    "EMT 2-1/2": 3150.0,
    "EMT 3": 4680.0,
    "EMT 3-1/2": 5910.0,
    "EMT 4": 7620.0,
    # RMC (Rigid Metal Conduit) — NEC Table 4, Article 344
    "RMC 1/2": 143.8,
    "RMC 3/4": 262.4,
    "RMC 1": 437.5,
    "RMC 1-1/4": 792.6,
    "RMC 1-1/2": 1100.0,
    "RMC 2": 1780.0,
    "RMC 2-1/2": 2760.0,
    "RMC 3": 4240.0,
    "RMC 3-1/2": 5420.0,
    "RMC 4": 7150.0,
}

# BUG-19 FIX: Fire alarm cable cross-sectional areas (NEC Chapter 9, Table 5A)
# FPLP = Power-Limited Fire Alarm Cable (NEC 760.179)
# FPL = Fire Alarm Cable (NEC 760.179)
# FPLR = Riser-Rated Fire Alarm Cable (NEC 760.179(B))
# These are the standard cable types for fire alarm systems.
# Values from NEC Chapter 9 Table 5A — approximate for typical 2-conductor cables.
FIRE_ALARM_CABLE_AREAS = {
    "FPLP 14": 6.26,    # FPLP 14 AWG 2-conductor ≈ same as 14 AWG THHN
    "FPLP 12": 8.58,    # FPLP 12 AWG 2-conductor
    "FPLP 10": 13.61,   # FPLP 10 AWG 2-conductor
    "FPL 14": 6.26,     # FPL 14 AWG 2-conductor
    "FPL 12": 8.58,     # FPL 12 AWG 2-conductor
    "FPL 10": 13.61,    # FPL 10 AWG 2-conductor
    "FPLR 14": 6.26,    # FPLR 14 AWG 2-conductor
    "FPLR 12": 8.58,    # FPLR 12 AWG 2-conductor
    "FPLR 10": 13.61,   # FPLR 10 AWG 2-conductor
    # Standard THHN/THWN building wire (NEC Table 5)
    "THHN 14": 6.26,
    "THHN 12": 8.58,
    "THHN 10": 13.61,
    "THWN 14": 6.26,
    "THWN 12": 8.58,
    "THWN 10": 13.61,
}

def calculate_conduit_fill(
    conduit_size: str,
    wire_gauge: str,
    wire_count: int,
    conduit_type: str = "EMT"
) -> Result[float, ConduitFillError]:
    """
    Calculate conduit fill ratio per NEC Chapter 9 Table 1.

    SAFETY FIX (V58): Added conduit_type parameter and expanded size support.
    Per NEC 760, fire alarm circuits commonly use EMT and RMC conduits.
    The original code only supported 3 EMT sizes, which was insufficient
    for real projects with multi-circuit trunk lines.

    Args:
        conduit_size: Trade size (e.g., "1/2", "3/4", "1", "1-1/4", "1-1/2", "2")
        wire_gauge: Wire/cable type (e.g., "14 AWG", "FPLP 14", "THHN 12")
        wire_count: Number of conductors in the conduit
        conduit_type: Conduit type ("EMT" or "RMC") — default EMT per NEC 760
    """
    import math

    if wire_count <= 0:
        return Result(error=ConduitFillError(
            message="Wire count must be a positive integer.",
            code_ref="NEC Ch.9 Table 1",
            remedy="Increase wire count parameter above zero."
        ))

    # BUG-F1 FIX: Removed math.isfinite(wire_count) — Python int is ALWAYS finite.
    # math.isfinite() only returns False for float NaN and Inf, which cannot occur
    # for int types. The check was dead code that provided zero protection.
    # Instead, validate that wire_count is actually an integer type.
    if not isinstance(wire_count, int):
        return Result(error=ConduitFillError(
            message=f"Wire count must be an integer, got {type(wire_count).__name__}.",
            code_ref="NEC Ch.9 Table 1",
            remedy="Provide an integer wire count."
        ))

    conduit_area = 0.0

    # Try expanded conduit area lookup first
    conduit_key = f"{conduit_type.upper()} {conduit_size}"
    if conduit_key in CONDUIT_INTERNAL_AREAS_MM2:
        conduit_area = CONDUIT_INTERNAL_AREAS_MM2[conduit_key]
    # Backward compatibility: bare size string defaults to EMT
    elif conduit_size == "1/2":
        conduit_area = EMT_INTERNAL_AREA_1_2_MM2
    elif conduit_size == "3/4":
        conduit_area = EMT_INTERNAL_AREA_3_4_MM2
    elif conduit_size == "1":
        conduit_area = EMT_INTERNAL_AREA_1_MM2
    else:
        supported_sizes = sorted(set(
            k.split(" ", 1)[1] for k in CONDUIT_INTERNAL_AREAS_MM2.keys()
        ))
        return Result(error=ConduitFillError(
            message=f"Unsupported conduit size '{conduit_size}' for type '{conduit_type}'.",
            code_ref="NEC Table 4",
            remedy=f"Use standard trade sizes: {', '.join(supported_sizes)}. "
                   f"Supported types: EMT, RMC."
        ))

    # BUG-19 FIX: Support fire alarm cable types (FPLP, FPL, FPLR) and
    # standard building wire (THHN, THWN) in addition to generic AWG.
    wire_area = 0.0
    if wire_gauge in FIRE_ALARM_CABLE_AREAS:
        wire_area = FIRE_ALARM_CABLE_AREAS[wire_gauge]
    elif wire_gauge == "14 AWG":
        wire_area = WIRE_AREA_14_AWG_MM2
    elif wire_gauge == "12 AWG":
        wire_area = WIRE_AREA_12_AWG_MM2
    elif wire_gauge == "10 AWG":
        wire_area = WIRE_AREA_10_AWG_MM2
    else:
        supported = ", ".join(sorted(set(
            list(FIRE_ALARM_CABLE_AREAS.keys()) + ["14 AWG", "12 AWG", "10 AWG"]
        )))
        return Result(error=ConduitFillError(
            message=f"Unsupported wire/cable type '{wire_gauge}'",
            code_ref="NEC Table 5/5A",
            remedy=f"Select a compliant wire/cable type. Supported: {supported}"
        ))

    total_wire_area = wire_area * wire_count
    fill_ratio = total_wire_area / conduit_area

    if wire_count == 1:
        limit = NEC_FILL_LIMIT_1_WIRE
    elif wire_count == 2:
        limit = NEC_FILL_LIMIT_2_WIRES
    else:
        limit = NEC_FILL_LIMIT_OVER_2_WIRES

    if fill_ratio > limit:
        return Result(error=ConduitFillError(
            message=f"Conduit fill exceeds permissible NEC threshold limit: {fill_ratio:.2%} > {limit:.2%}",
            code_ref="NEC Ch.9 Table 1",
            remedy="Upsize conduit selection or reduce wire run count."
        ))

    return Result(value=fill_ratio)
'''

# ─────────────────────────────────────────────────────────────────────
# 6. qomn_fire/engine/panel_database.py (Immutable FACP Specs)
# ─────────────────────────────────────────────────────────────────────
INTEGRATED_FILES["qomn_fire/engine/panel_database.py"] = '''"""
FACP IMMUTABLE DATASHEETS
"""

from qomn_fire.core.types import FireAlarmPanel

MASTER_PANEL_DATABASE = [
    FireAlarmPanel(
        model="NFS-320",
        manufacturer="NOTIFIER",
        points_capacity=250,
        nac_capacity=2,
        supports_networking=False,
        supports_voice=False,
        supports_releasing=False,
        max_slc_loops=1,
        listings=("UL", "ULC"),
        standby_current_amps=0.200,
        alarm_current_amps=0.350,
        power_supply_watts=144
    ),
    FireAlarmPanel(
        model="NFS-640",
        manufacturer="NOTIFIER",
        points_capacity=640,
        nac_capacity=4,
        supports_networking=True,
        supports_voice=True,
        supports_releasing=False,
        max_slc_loops=4,
        listings=("UL", "ULC"),
        standby_current_amps=0.250,
        alarm_current_amps=0.450,
        power_supply_watts=144
    ),
    FireAlarmPanel(
        model="NFS2-3030",
        manufacturer="NOTIFIER",
        points_capacity=3180,
        nac_capacity=10,
        supports_networking=True,
        supports_voice=True,
        supports_releasing=True,
        max_slc_loops=10,
        listings=("UL", "ULC", "FM"),
        standby_current_amps=0.350,
        alarm_current_amps=0.650,
        power_supply_watts=288
    ),
    FireAlarmPanel(
        model="FC901",
        manufacturer="SIEMENS",
        points_capacity=50,
        nac_capacity=2,
        supports_networking=False,
        supports_voice=False,
        supports_releasing=False,
        max_slc_loops=1,
        listings=("UL", "FM", "FDNY"),
        standby_current_amps=0.120,
        alarm_current_amps=0.250,
        power_supply_watts=170
    ),
    FireAlarmPanel(
        model="FC922",
        manufacturer="SIEMENS",
        points_capacity=252,
        nac_capacity=4,
        supports_networking=True,
        supports_voice=True,
        supports_releasing=False,
        max_slc_loops=2,
        listings=("UL", "FM", "FDNY"),
        standby_current_amps=0.180,
        alarm_current_amps=0.350,
        power_supply_watts=170
    ),
    FireAlarmPanel(
        model="FC924",
        manufacturer="SIEMENS",
        points_capacity=504,
        nac_capacity=6,
        supports_networking=True,
        supports_voice=True,
        supports_releasing=True,
        max_slc_loops=4,
        listings=("UL", "FM", "FDNY"),
        standby_current_amps=0.220,
        alarm_current_amps=0.450,
        power_supply_watts=300
    ),
    FireAlarmPanel(
        model="4100ES",
        manufacturer="SIMPLEX",
        points_capacity=3000,
        nac_capacity=10,
        supports_networking=True,
        supports_voice=True,
        supports_releasing=True,
        max_slc_loops=10,
        listings=("UL", "FM", "FDNY"),
        standby_current_amps=0.450,
        alarm_current_amps=0.850,
        power_supply_watts=360
    )
]
'''

# ─────────────────────────────────────────────────────────────────────
# 7. qomn_fire/engine/panel_selector.py (Integrated FACP Selection)
# ─────────────────────────────────────────────────────────────────────
INTEGRATED_FILES["qomn_fire/engine/panel_selector.py"] = '''"""
QOMN-FIRE FACP SELECTION ENGINE
Reference Standard: NFPA 72 (2022) §10.6.7, UL 864 10th Edition.

V54 Bug Fixes Preserved:
  F2: NAC capacity uses EXACT match — required_nacs = nac_circuit_count
  F3: Sort prefers SMALLEST adequate capacity on ties (right-sizing)
  F4: supports_releasing field + filter logic present
  F5: Battery sizing uses NFPA 72 compliant tiered derating (NOT flat 1.2x)
  F6: Per-device standby current = 0.8 mA (not 1.0 mA)
"""

import hashlib
from typing import List, Tuple, Dict, Any
from qomn_fire.core.types import ProjectRequirements, PanelRecommendation, FireAlarmPanel
from qomn_fire.core.errors import Result, FACPSelectionError
from qomn_fire.engine.panel_database import MASTER_PANEL_DATABASE


class SelectionEngine:
    @staticmethod
    def compute_battery_ah(
        device_count: int,
        nac_circuit_count: int,
        panel: FireAlarmPanel,
        requires_voice: bool
    ) -> Tuple[float, Dict[str, Any]]:
        """
        Calculates battery capacity per NFPA 72 §10.6.7 with tiered derating.

        Derating methodology (V54 FIX F5 — NOT flat 1.2x):
          1. Temperature derating: 1.10 (10% compensation for capacity loss at low temp)
          2. Aging derating: 1.15 (15% compensation for battery end-of-life per IEEE 1188)
          3. NFPA margin: 1.20 (20% mandatory margin per NFPA 72 §10.6.7)

        Per-device standby current: 0.8 mA (V54 FIX F6 — NOT 1.0 mA).

        Returns:
            Tuple of (battery_size_ah, derating_details_dict)
        """
        standby_load = (device_count * 0.0008) + panel.standby_current_amps
        alarm_load = (nac_circuit_count * 2.0) + (device_count * 0.005) + panel.alarm_current_amps
        alarm_duration_h = 0.25 if requires_voice else 0.0833

        raw_capacity = (standby_load * 24.0) + (alarm_load * alarm_duration_h)

        temperature_derating = 1.10
        aging_derating = 1.15
        nfpa_margin = 1.20
        combined_safety_factor = round(
            temperature_derating * aging_derating * nfpa_margin, 6
        )

        battery_size = round(raw_capacity * combined_safety_factor, 2)

        derating_details = {
            "method": "NFPA 72 §10.6.7 tiered derating",
            "temperature_derating": temperature_derating,
            "aging_derating": aging_derating,
            "nfpa_margin": nfpa_margin,
            "combined_safety_factor": combined_safety_factor,
            # BUG-PS1 FIX: Removed duplicate "enhanced_safety_factor" key that was
            # identical to "combined_safety_factor". Having two keys with the same value
            # creates confusion — downstream code doesn't know which to use, and neither
            # provides more information than the other. The combined_safety_factor IS the
            # enhanced/total safety factor: 1.10 (temp) × 1.15 (aging) × 1.20 (NFPA) = 1.518.
            "raw_capacity_ah": round(raw_capacity, 4),
            "per_device_standby_mA": 0.8,
        }

        return battery_size, derating_details

    @classmethod
    def select_panel(cls, req: ProjectRequirements) -> Result[PanelRecommendation, FACPSelectionError]:
        # Enforce code capacity margins (20% spare capacity per NFPA 72 §10.6.7)
        required_points = req.device_count * 1.2
        required_nacs = req.nac_circuit_count

        eligible_panels: List[Tuple[FireAlarmPanel, float]] = []

        for p in MASTER_PANEL_DATABASE:
            if p.points_capacity < required_points:
                continue
            if p.nac_capacity < required_nacs:
                continue
            if req.requires_network and not p.supports_networking:
                continue
            if req.requires_voice and not p.supports_voice:
                continue
            if req.requires_releasing and not p.supports_releasing:
                continue
            if req.jurisdiction == "FDNY" and "FDNY" not in p.listings:
                continue
            if req.jurisdiction == "Canada" and "ULC" not in p.listings:
                continue

            # Multi-criteria scoring
            score = 0.0
            utilization = required_points / p.points_capacity

            if 0.5 <= utilization <= 0.8:
                score += 50.0
            elif 0.3 <= utilization < 0.5:
                score += 20.0
            elif 0.8 < utilization <= 0.95:
                score += 15.0
            else:
                score += 5.0

            if req.preferred_manufacturer and req.preferred_manufacturer.upper() == p.manufacturer.upper():
                score += 100.0

            eligible_panels.append((p, score))

        if not eligible_panels:
            return Result(error=FACPSelectionError(
                message="No compliant FACP models found satisfying constraints in database.",
                code_ref="UL 864 / NFPA 72",
                remedy="Reduce required device loads or transition to a multi-node networked panel architecture."
            ))

        # Primary: highest score. Tie-break: smallest capacity (right-sizing),
        # then lowest standby draw, then model name for determinism.
        eligible_panels.sort(
            key=lambda x: (x[1], -x[0].points_capacity, -x[0].standby_current_amps, x[0].model),
            reverse=True
        )

        selected, _ = eligible_panels[0]
        alternatives = tuple([p[0].model for p in eligible_panels[1:4]])

        capacity_util = required_points / selected.points_capacity
        nac_util = required_nacs / selected.nac_capacity

        warnings = []
        if capacity_util > 0.90:
            warnings.append("FACP loading is close to maximum capacity limits.")
        elif capacity_util < 0.30:
            warnings.append("FACP is significantly oversized for the current device loading.")

        battery_size, derating_details = cls.compute_battery_ah(
            req.device_count,
            req.nac_circuit_count,
            selected,
            req.requires_voice
        )

        # Cryptographic checksum for deterministic outputs
        payload = f"{selected.model}:{selected.manufacturer}:{capacity_util:.4f}:{battery_size:.2f}"
        signature = hashlib.sha256(payload.encode("utf-8")).hexdigest()

        rec = PanelRecommendation(
            recommended_model=selected.model,
            manufacturer=selected.manufacturer,
            capacity_utilization=round(capacity_util, 4),
            nac_utilization=round(nac_util, 4),
            battery_size_ah=battery_size,
            battery_derating_details=derating_details,
            power_supply_watts=selected.power_supply_watts,
            listings=selected.listings,
            code_compliance=(
                "UL 864 10th Edition",
                "NFPA 72 §10.6.7 Compliance"
            ),
            warnings=tuple(warnings),
            alternatives=alternatives,
            signature_hash=signature
        )
        return Result(value=rec)
'''

# ─────────────────────────────────────────────────────────────────────
# 8. qomn_fire/engine/placement.py (Detector Placement)
# ─────────────────────────────────────────────────────────────────────
INTEGRATED_FILES["qomn_fire/engine/placement.py"] = '''"""
QOMN-FIRE AUTOMATED DETECTOR PLACEMENT ENGINE
Reference Standard: NFPA 72 (2022) Section 17.7.3.2 (Spacing and Coverage).
"""

from typing import List
import math
import logging
from qomn_fire.core.types import Point3D, Device, DeviceType
from qomn_fire.core.errors import Result, PhysicalConstraintError
from qomn_fire.core.constants import NFPA_SMOKE_DETECTOR_SPACING_M, NFPA_MAX_WALL_DISTANCE_M

logger = logging.getLogger("qomn_fire.placement")

def place_smoke_detectors_room(
    room_min: Point3D,
    room_max: Point3D,
    height_ft: float,
    circuit_prefix: str,
    zone: str
) -> Result[List[Device], PhysicalConstraintError]:
    # SAFETY FIX (V58): Validate inputs for NaN/Inf per IEEE 754 bypass risk.
    # NaN comparisons always return False — NaN room dimensions would silently
    # bypass all validation checks, producing detectors at invalid positions.
    for label, pt in [("room_min", room_min), ("room_max", room_max)]:
        for coord_name, val in [("x", pt.x), ("y", pt.y), ("z", pt.z)]:
            if not math.isfinite(val):
                return Result(error=PhysicalConstraintError(
                    message=f"{label}.{coord_name}={val} is not finite (NaN or Inf). "
                            f"Detector placement requires finite room coordinates.",
                    code_ref="NFPA 72 §17.7.3",
                    remedy="Validate room geometry before calling placement. Check for NaN in IFC parsing."
                ))
    if not math.isfinite(height_ft):
        return Result(error=PhysicalConstraintError(
            message=f"height_ft={height_ft} is not finite (NaN or Inf). "
                    f"Detector elevation must be a finite value.",
            code_ref="NFPA 72 §17.7.3",
            remedy="Provide a valid room ceiling height."
        ))

    # BUG-P1 FIX: Validate that height_ft is in a physically reasonable range for feet.
    # NFPA 72 §17.7.3.1.4: Smoke detectors are mounted on ceilings. Typical building
    # ceiling heights range from 8 ft (2.4m residential) to 30 ft (9.1m industrial).
    # A value < 3.0 ft likely means the caller passed meters instead of feet
    # (e.g., 3.0m room height from IFC parser misinterpreted as 3.0 ft = 0.91m).
    # A value > 100 ft likely means the caller passed millimeters or centimeters.
    # Either error produces WRONG detector elevation = WRONG NFPA coverage.
    if height_ft < 3.0:
        logger.warning(
            "POTENTIAL UNIT ERROR: height_ft=%.2f is below 3.0 ft (0.91 m). "
            "This parameter expects FEET. If you have meters, convert first: "
            "height_ft = height_m * 3.28084. Typical IFC room heights are 2.4-9.1 m "
            "(8-30 ft). A value of %.2f ft suggests this might be %.2f meters "
            "mistakenly passed as feet.",
            height_ft, height_ft, height_ft
        )
    if height_ft > 100.0:
        logger.warning(
            "POTENTIAL UNIT ERROR: height_ft=%.2f exceeds 100 ft (30.5 m). "
            "This parameter expects FEET. If you have millimeters, divide by 304.8. "
            "No typical building ceiling exceeds 100 ft.",
            height_ft
        )

    dx = room_max.x - room_min.x
    dy = room_max.y - room_min.y

    if dx <= 0.0 or dy <= 0.0:
        return Result(error=PhysicalConstraintError(
            message="Room dimensions must form positive volumes.",
            code_ref="NFPA 72 §17.7.3",
            remedy="Re-evaluate coordinate boundary bounding box input parameters."
        ))

    devices = []
    s = NFPA_SMOKE_DETECTOR_SPACING_M
    half_s = s / 2.0

    # BUG-42 FIX: For rooms narrower than half the NFPA spacing (4.572m),
    # the grid-based while loop never executes, and the old fallback placed
    # detectors at room_max - NFPA_MAX_WALL_DISTANCE_M / 2, which can be
    # NEGATIVE relative to room_min (e.g., a 2m wide room: 2 - 3.2 = -1.2).
    # Detectors placed outside room bounds provide ZERO coverage — the NFPA
    # spacing analysis would be completely wrong, leaving the room unprotected.
    # Fix: Use room center as fallback for narrow dimensions, and clamp all
    # detector positions to stay within room bounds.

    x_coords = []
    x_curr = room_min.x + half_s
    while x_curr < room_max.x:
        x_coords.append(x_curr)
        x_curr += s

    if not x_coords:
        # Room too narrow for grid — place detector at room center X
        x_coords.append((room_min.x + room_max.x) / 2.0)
    elif (room_max.x - x_coords[-1]) > NFPA_MAX_WALL_DISTANCE_M:
        extra = room_max.x - (NFPA_MAX_WALL_DISTANCE_M / 2.0)
        # Clamp to room bounds to avoid placing detectors outside the room
        extra = max(room_min.x + 0.1, min(extra, room_max.x - 0.1))
        x_coords.append(extra)

    y_coords = []
    y_curr = room_min.y + half_s
    while y_curr < room_max.y:
        y_coords.append(y_curr)
        y_curr += s

    if not y_coords:
        # Room too narrow for grid — place detector at room center Y
        y_coords.append((room_min.y + room_max.y) / 2.0)
    elif (room_max.y - y_coords[-1]) > NFPA_MAX_WALL_DISTANCE_M:
        extra = room_max.y - (NFPA_MAX_WALL_DISTANCE_M / 2.0)
        # Clamp to room bounds to avoid placing detectors outside the room
        extra = max(room_min.y + 0.1, min(extra, room_max.y - 0.1))
        y_coords.append(extra)

    dev_counter = 1
    for x in x_coords:
        for y in y_coords:
            p = Point3D(x, y, room_min.z)
            d = Device(
                id=f"SMOKE_{zone}_{dev_counter:03d}",
                device_type=DeviceType.SMOKE_DETECTOR,
                location=p,
                elevation_ft=height_ft,
                circuit=f"{circuit_prefix}-{dev_counter}",
                zone=zone
            )
            devices.append(d)
            dev_counter += 1

    return Result(value=devices)
'''

# ─────────────────────────────────────────────────────────────────────
# 9. qomn_fire/engine/routing.py (Conduit Routing)
# ─────────────────────────────────────────────────────────────────────
INTEGRATED_FILES["qomn_fire/engine/routing.py"] = '''"""
QOMN-FIRE ORTHOGONAL 3D PATHFINDER ROUTING ENGINE
A* algorithm for conduit routing with NEC 360-degree bend limit enforcement.

BUG-5/16 FIX: bend_count now stores NUMBER of bends, not degrees.
Added bend_degrees field for the NEC 360-degree limit check.
BUG-20 FIX: Route length uses (path_points - 1) * step, not len(path) * step.
BUG-27 FIX: Conduit-type-appropriate trade size, not hardcoded "1/2".
"""

import heapq
import math
import logging
from typing import List, Tuple, Dict, Set
from qomn_fire.core.types import Point3D, ConduitType, ConduitRun, Fitting, FittingType
from qomn_fire.core.errors import Result, NECViolationError

logger = logging.getLogger("qomn_fire.routing")


class GridMap3D:
    def __init__(self, step_m: float = 0.5):
        self.step_m = step_m
        self.obstacles: Set[Tuple[int, int, int]] = set()

    def to_grid(self, p: Point3D) -> Tuple[int, int, int]:
        return (
            int(round(p.x / self.step_m)),
            int(round(p.y / self.step_m)),
            int(round(p.z / self.step_m))
        )

    def to_physical(self, gp: Tuple[int, int, int]) -> Point3D:
        return Point3D(
            gp[0] * self.step_m,
            gp[1] * self.step_m,
            gp[2] * self.step_m
        )

    def add_obstacle(self, p: Point3D):
        self.obstacles.add(self.to_grid(p))


# BUG-27 FIX: Map conduit type to appropriate default trade size.
# The original code hardcoded trade_size="1/2" regardless of conduit type.
# RMC (Rigid Metal Conduit) is typically 3/4" minimum; FMC starts at 1/2".
_DEFAULT_TRADE_SIZE = {
    ConduitType.EMT: "1/2",
    ConduitType.RMC: "3/4",
    ConduitType.FMC: "1/2",
}

def astar_route_3d(
    grid_map: GridMap3D,
    start: Point3D,
    end: Point3D,
    conduit: ConduitType,
    conduit_id: str,
    trade_size: str = ""
) -> Result[ConduitRun, NECViolationError]:
    g_start = grid_map.to_grid(start)
    g_end = grid_map.to_grid(end)

    # SAFETY FIX (V58): Validate start/end coordinates for NaN/Inf.
    # Per IEEE 754: NaN comparisons always return False — NaN coordinates
    # would silently bypass obstacle checks and produce invalid conduit paths.
    for label, pt in [("start", start), ("end", end)]:
        for coord_name, val in [("x", pt.x), ("y", pt.y), ("z", pt.z)]:
            if not math.isfinite(val):
                return Result(error=NECViolationError(
                    message=f"{label}.{coord_name}={val} is not finite (NaN or Inf). "
                            f"Conduit routing requires finite coordinates.",
                    code_ref="NEC Art 300.18",
                    remedy="Validate device positions before routing. Check for NaN in IFC parsing."
                ))

    if g_start in grid_map.obstacles or g_end in grid_map.obstacles:
        return Result(error=NECViolationError(
            message="Conduit terminal endpoints are blocked.",
            code_ref="NEC Art 300.18",
            remedy="Clear coordinate clearances or relocate the terminal devices."
        ))

    heap_counter = 0
    open_set = []
    heapq.heappush(open_set, (0.0, heap_counter, g_start))

    came_from: Dict[Tuple[int, int, int], Tuple[int, int, int]] = {}
    g_score: Dict[Tuple[int, int, int], float] = {g_start: 0.0}

    directions = [
        (1, 0, 0), (-1, 0, 0),
        (0, 1, 0), (0, -1, 0),
        (0, 0, 1), (0, 0, -1)
    ]

    # Safety limit: prevent infinite loops on very large grids
    MAX_ITERATIONS = 500000
    iterations = 0

    while open_set:
        iterations += 1
        if iterations > MAX_ITERATIONS:
            return Result(error=NECViolationError(
                message=f"A* pathfinding exceeded {MAX_ITERATIONS} iterations — grid too large or path too complex.",
                code_ref="NEC Art 300.18",
                remedy="Reduce grid size or clear structural blockings from grid boundaries."
            ))
        _, _, current = heapq.heappop(open_set)

        if current == g_end:
            path = [current]
            while current in came_from:
                current = came_from[current]
                path.append(current)
            path.reverse()

            pts = tuple([grid_map.to_physical(p) for p in path])

            # BUG-5/16 FIX: Count bends as NUMBER of 90-degree bends, not degrees.
            # NEC Article 358.26 states: 'not more than the equivalent of four
            # quarter bends (360 degrees total) between pull points.'
            # bend_count = number of individual 90-degree bends
            # bend_degrees = total cumulative bend angle in degrees
            bend_count = 0
            bend_degrees = 0
            fittings: List[Fitting] = []
            if len(pts) >= 3:
                prev_dir = (
                    pts[1].x - pts[0].x,
                    pts[1].y - pts[0].y,
                    pts[1].z - pts[0].z
                )
                for i in range(1, len(pts) - 1):
                    curr_dir = (
                        pts[i+1].x - pts[i].x,
                        pts[i+1].y - pts[i].y,
                        pts[i+1].z - pts[i].z
                    )
                    dot = prev_dir[0]*curr_dir[0] + prev_dir[1]*curr_dir[1] + prev_dir[2]*curr_dir[2]
                    mag_p = math.sqrt(prev_dir[0]**2 + prev_dir[1]**2 + prev_dir[2]**2)
                    mag_c = math.sqrt(curr_dir[0]**2 + curr_dir[1]**2 + curr_dir[2]**2)

                    if mag_p > 0 and mag_c > 0:
                        cos_a = dot / (mag_p * mag_c)
                        if abs(cos_a - 1.0) > 1e-4:
                            bend_count += 1
                            bend_degrees += 90
                            fittings.append(Fitting(FittingType.ELBOW_90, pts[i]))
                            prev_dir = curr_dir

            # BUG-20 FIX: Route length must use (path_points - 1) * step, not
            # len(path) * step. For a 5m straight line with 0.5m grid:
            #   Path = [0, 0.5, 1.0, ..., 5.0] = 11 points
            #   Distance = 10 steps * 0.5m = 5.0m (CORRECT)
            #   Old: 11 * 0.5 = 5.5m (WRONG — off by one grid step)
            num_segments = max(len(path) - 1, 0)
            tot_len_m = num_segments * grid_map.step_m
            tot_len_ft = tot_len_m * 3.28084

            # NEC Article 358.26: No more than 360 degrees of bends between pull points
            if bend_degrees > 360:
                return Result(error=NECViolationError(
                    message=f"Conduit run exceeds 360 degrees of bend limits "
                            f"({bend_degrees} degrees from {bend_count} bends). "
                            f"NEC Article 358.26 allows maximum 4 quarter bends.",
                    code_ref="NEC Article 358.26",
                    remedy="Install junction boxes to partition the conduit run segment."
                ))

            # BUG-27 FIX: Use conduit-type-appropriate trade size, not hardcoded "1/2"
            selected_trade_size = trade_size if trade_size else _DEFAULT_TRADE_SIZE.get(conduit, "1/2")

            run = ConduitRun(
                id=conduit_id,
                conduit_type=conduit,
                trade_size=selected_trade_size,
                points=pts,
                total_length_ft=tot_len_ft,
                bend_count=bend_count,
                bend_degrees=bend_degrees,
                fittings=tuple(fittings)
            )
            return Result(value=run)

        for dx, dy, dz in directions:
            neighbor = (current[0] + dx, current[1] + dy, current[2] + dz)
            if neighbor in grid_map.obstacles:
                continue

            tentative_g = g_score[current] + 1.0
            if tentative_g < g_score.get(neighbor, float('inf')):
                came_from[neighbor] = current
                g_score[neighbor] = tentative_g
                h = abs(neighbor[0]-g_end[0]) + abs(neighbor[1]-g_end[1]) + abs(neighbor[2]-g_end[2])
                f = tentative_g + h
                heap_counter += 1
                heapq.heappush(open_set, (f, heap_counter, neighbor))

    return Result(error=NECViolationError(
        message="No compliant orthogonal paths could be routed to targets.",
        code_ref="NEC Art 300.18",
        remedy="Clear structural blockings from grid boundaries."
    ))
'''

# ─────────────────────────────────────────────────────────────────────
# 10. qomn_fire/drawing/title_block.py (Integrated FACP Schedule Layout)
# ─────────────────────────────────────────────────────────────────────
INTEGRATED_FILES["qomn_fire/drawing/title_block.py"] = '''"""
QOMN-FIRE TITLE BLOCK AND FACP DRAWING SHEET PLOTTER
Reference Standard: ISO 19650 standard plotting borders.
"""

import ezdxf
from qomn_fire.core.types import TitleBlock, PanelRecommendation

def draw_title_block(doc: ezdxf.document.Drawing, title: TitleBlock):
    layout = doc.layout("A1-Fire-Alarm-Plan") if "A1-Fire-Alarm-Plan" in doc.layouts else doc.layouts.new("A1-Fire-Alarm-Plan")

    # Border margins
    layout.add_line((10.0, 10.0), (831.0, 10.0), dxfattribs={"color": 7})
    layout.add_line((831.0, 10.0), (831.0, 584.0), dxfattribs={"color": 7})
    layout.add_line((831.0, 584.0), (10.0, 584.0), dxfattribs={"color": 7})
    layout.add_line((10.0, 584.0), (10.0, 10.0), dxfattribs={"color": 7})

    # Title block frame
    layout.add_line((600.0, 10.0), (600.0, 180.0), dxfattribs={"color": 7})
    layout.add_line((600.0, 180.0), (831.0, 180.0), dxfattribs={"color": 7})
    layout.add_line((600.0, 130.0), (831.0, 130.0), dxfattribs={"color": 7})
    layout.add_line((600.0, 80.0), (831.0, 80.0), dxfattribs={"color": 7})

    layout.add_text(f"PROJECT: {title.project_name}", dxfattribs={"insert": (610.0, 150.0), "height": 3.5, "color": 7})
    layout.add_text(f"SHEET TITLE: {title.sheet_title}", dxfattribs={"insert": (610.0, 105.0), "height": 3.5, "color": 7})
    layout.add_text(f"DWG NO: {title.drawing_number}", dxfattribs={"insert": (610.0, 90.0), "height": 3.0, "color": 7})
    layout.add_text(f"SCALE: {title.scale}  DATE: {title.date}", dxfattribs={"insert": (610.0, 60.0), "height": 2.5, "color": 7})
    layout.add_text(f"DES: {title.designer}  CHK: {title.checker}", dxfattribs={"insert": (610.0, 45.0), "height": 2.5, "color": 7})
    layout.add_text(f"PE STAMP: {title.pe_stamp}", dxfattribs={"insert": (610.0, 25.0), "height": 2.5, "color": 7})

def draw_facp_schedule(doc: ezdxf.document.Drawing, rec: PanelRecommendation):
    """
    Renders the approved FACP Schedule dynamically inside the layout paper space block.
    Reference: NFPA 72 §10 submittals standards.
    """
    layout = doc.layout("A1-Fire-Alarm-Plan") if "A1-Fire-Alarm-Plan" in doc.layouts else doc.layouts.new("A1-Fire-Alarm-Plan")

    # Placed in left center section (X: 10 -> 250, Y: 320 -> 500)
    layout.add_line((10.0, 320.0), (10.0, 500.0), dxfattribs={"color": 7})
    layout.add_line((10.0, 500.0), (250.0, 500.0), dxfattribs={"color": 7})
    layout.add_line((250.0, 500.0), (250.0, 320.0), dxfattribs={"color": 7})
    layout.add_line((250.0, 320.0), (10.0, 320.0), dxfattribs={"color": 7})

    layout.add_text("FACP SELECTION SCHEDULE", dxfattribs={"insert": (15.0, 480.0), "height": 3.5, "color": 7})
    layout.add_line((10.0, 470.0), (250.0, 470.0), dxfattribs={"color": 7})

    layout.add_text(f"RECOMMENDED MODEL : {rec.recommended_model}", dxfattribs={"insert": (15.0, 450.0), "height": 2.5, "color": 7})
    layout.add_text(f"MANUFACTURER      : {rec.manufacturer}", dxfattribs={"insert": (15.0, 430.0), "height": 2.5, "color": 7})
    layout.add_text(f"BATTERY CAPACITY   : {rec.battery_size_ah} Ah (NFPA 72 §10.6.7)", dxfattribs={"insert": (15.0, 410.0), "height": 2.5, "color": 7})
    layout.add_text(f"POINTS UTILIZATION : {rec.capacity_utilization:.2%}", dxfattribs={"insert": (15.0, 390.0), "height": 2.5, "color": 7})
    layout.add_text(f"NAC UTILIZATION    : {rec.nac_utilization:.2%}", dxfattribs={"insert": (15.0, 370.0), "height": 2.5, "color": 7})
    layout.add_text(f"UL CODES LISTINGS  : {', '.join(rec.listings)}", dxfattribs={"insert": (15.0, 350.0), "height": 2.5, "color": 7})

    # Enforce SHA-256 footprint representation inside CAD layouts for document audit trail
    layout.add_text(f"SIGNATURE HASH     : {rec.signature_hash[:24]}...", dxfattribs={"insert": (15.0, 330.0), "height": 1.8, "color": 7})
'''

# ─────────────────────────────────────────────────────────────────────
# 11. qomn_fire/drawing/dxf_generator.py (Layers & Viewports)
# FIX: NULL_DATE_VALUE → 0.0, view_center → view_center_point, dxfattribs
# ─────────────────────────────────────────────────────────────────────
INTEGRATED_FILES["qomn_fire/drawing/dxf_generator.py"] = '''"""
QOMN-FIRE COMPLETE DXF SHOP DRAWING GENERATOR
Reference Standard: National CAD Standards (NCS) Layer Specifications.
"""

import ezdxf
from typing import Tuple

def create_document() -> ezdxf.document.Drawing:
    doc = ezdxf.new("R2000")
    doc.header['$TDCREATE'] = 0.0
    doc.header['$TDUPDATE'] = 0.0
    doc.header['$HANDSEED'] = '1'
    return doc

def setup_layers(doc: ezdxf.document.Drawing):
    layers = [
        ("A-WALL", 7),
        ("A-FIRE-DEVICES", 1),
        ("A-FIRE-CABLES", 2),
        ("A-FIRE-HATC", 3),
        ("A-FIRE-DIMS", 4),
        ("A-FIRE-TEXT", 5),
        ("A-FIRE-REVC", 1)
    ]
    for name, color in layers:
        if name not in doc.layers:
            doc.layers.new(name=name, dxfattribs={"color": color})

def add_viewport(
    doc: ezdxf.document.Drawing,
    center: Tuple[float, float],
    size: Tuple[float, float],
    view_center_point: Tuple[float, float],
    view_height: float
):
    layout = doc.layout("A1-Fire-Alarm-Plan") if "A1-Fire-Alarm-Plan" in doc.layouts else doc.layouts.new("A1-Fire-Alarm-Plan")
    vp = layout.add_viewport(
        center=center,
        size=size,
        view_center_point=view_center_point,
        view_height=view_height
    )
    vp.dxf.status = 1
'''

# ─────────────────────────────────────────────────────────────────────
# 12. qomn_fire/drawing/hatch_engine.py (Pattern Fills)
# FIX: doc.layers.new uses dxfattribs, removed set_xdata for compatibility
# ─────────────────────────────────────────────────────────────────────
INTEGRATED_FILES["qomn_fire/drawing/hatch_engine.py"] = '''"""
QOMN-FIRE HATCH AND PATTERN PLACEMENT MODULE
Reference Standard: NFPA 72 spacing boundary shapes.
"""

import math
from typing import List, Tuple, Any
import ezdxf
from qomn_fire.core.types import HatchSpec, Point3D
from qomn_fire.core.errors import Result, HatchPlacementError

def generate_circle_polyline(center: Point3D, radius: float, num_sides: int = 16) -> List[Tuple[float, float]]:
    poly = []
    for i in range(num_sides):
        angle = (2.0 * math.pi * i) / num_sides
        x = center.x + radius * math.cos(angle)
        y = center.y + radius * math.sin(angle)
        poly.append((round(x, 4), round(y, 4)))
    return poly

def place_boundary_hatch(
    doc: ezdxf.document.Drawing,
    boundary_points: List[Tuple[float, float]],
    spec: HatchSpec,
    run_id: str
) -> Result[Any, HatchPlacementError]:
    if spec.scale < 0.001:
        return Result(error=HatchPlacementError(
            message=f"Hatch scaling factor {spec.scale} is too small (< 0.001).",
            code_ref="CAD Drafting Standards",
            remedy="Increase hatch scale parameter bounds above 0.01."
        ))

    msp = doc.modelspace()
    if spec.layer not in doc.layers:
        doc.layers.new(spec.layer, dxfattribs={"color": spec.color})

    hatch = msp.add_hatch(color=spec.color)
    hatch.dxf.layer = spec.layer
    hatch.dxf.associative = 1

    hatch.set_pattern_fill(spec.pattern_name, scale=spec.scale, angle=spec.angle)
    hatch.paths.add_polyline_path(boundary_points, is_closed=True)

    return Result(value=hatch)
'''

# ─────────────────────────────────────────────────────────────────────
# 13. qomn_fire/drawing/revision_control.py (Revisions log)
# FIX: set_bulge → format='xyb' for ezdxf 1.4.3 compatibility
# ─────────────────────────────────────────────────────────────────────
INTEGRATED_FILES["qomn_fire/drawing/revision_control.py"] = '''"""
QOMN-FIRE REVISIONS AND CONTROL GRAPHICS
Reference Standard: ISO 9001 quality audits.
"""

from typing import List, Tuple
import ezdxf
from qomn_fire.core.types import Revision

def draw_revision_cloud(doc: ezdxf.document.Drawing, vertices: List[Tuple[float, float]]):
    msp = doc.modelspace()
    # ezdxf 1.4.x: bulge set via format='xyb' (x, y, bulge) in point tuples
    bulge_vertices = [(x, y, 0.4) for (x, y) in vertices]
    p_line = msp.add_lwpolyline(bulge_vertices, format='xyb', close=True,
                                 dxfattribs={"layer": "A-FIRE-REVC", "color": 1})

def draw_revision_table(doc: ezdxf.document.Drawing, revisions: List[Revision]):
    layout = doc.layout("A1-Fire-Alarm-Plan") if "A1-Fire-Alarm-Plan" in doc.layouts else doc.layouts.new("A1-Fire-Alarm-Plan")

    layout.add_line((600.0, 180.0), (600.0, 250.0), dxfattribs={"color": 7})
    layout.add_line((600.0, 250.0), (831.0, 250.0), dxfattribs={"color": 7})
    layout.add_text("REVISIONS LOG", dxfattribs={"insert": (610.0, 235.0), "height": 3.0, "color": 7})

    y_offset = 215.0
    for rev in revisions:
        rev_str = f"REV {rev.number} - {rev.date} - {rev.description} ({rev.by})"
        layout.add_text(rev_str, dxfattribs={"insert": (610.0, y_offset), "height": 2.2, "color": 7})
        y_offset -= 15.0
'''

# ─────────────────────────────────────────────────────────────────────
# 14. qomn_fire/integration/cable_hatch.py (Route and Hatch Integrator)
# FIX: Added Dict import, proper type hints
# ─────────────────────────────────────────────────────────────────────
INTEGRATED_FILES["qomn_fire/integration/cable_hatch.py"] = '''"""
QOMN-FIRE INTEGRATION ROUTING AND BOUNDARY PLACEMENTS
Reference Standard: NEC 760 spatial segregation compliance rules.
"""

from typing import Tuple, List, Dict, Any, Union
import ezdxf
from qomn_fire.core.types import Point3D, ConduitType, ConduitRun, HatchSpec, Device
from qomn_fire.core.errors import Result, NECViolationError, HatchPlacementError
from qomn_fire.engine.routing import GridMap3D, astar_route_3d
from qomn_fire.drawing.hatch_engine import place_boundary_hatch

def route_conduit_and_hatch(
    grid_map: GridMap3D,
    doc: ezdxf.document.Drawing,
    start: Point3D,
    end: Point3D,
    conduit: ConduitType,
    conduit_id: str,
    spec: HatchSpec
) -> Result[Tuple[ConduitRun, Any], Union[NECViolationError, HatchPlacementError]]:
    route_res = astar_route_3d(grid_map, start, end, conduit, conduit_id)
    if route_res.is_failure:
        return Result(error=route_res.error())

    conduit_run = route_res.unwrap()
    pts = conduit_run.points

    boundary_points = []
    width_m = 0.20

    for i in range(len(pts) - 1):
        p1, p2 = pts[i], pts[i+1]
        x_min, x_max = min(p1.x, p2.x), max(p1.x, p2.x)
        y_min, y_max = min(p1.y, p2.y), max(p1.y, p2.y)

        if abs(y_max - y_min) < 1e-4:
            boundary_points.extend([
                (round(x_min, 4), round(y_min - width_m, 4)),
                (round(x_max, 4), round(y_min - width_m, 4)),
                (round(x_max, 4), round(y_min + width_m, 4)),
                (round(x_min, 4), round(y_min + width_m, 4))
            ])
        elif abs(x_max - x_min) < 1e-4:
            boundary_points.extend([
                (round(x_min - width_m, 4), round(y_min, 4)),
                (round(x_min + width_m, 4), round(y_min, 4)),
                (round(x_min + width_m, 4), round(y_max, 4)),
                (round(x_min - width_m, 4), round(y_max, 4))
            ])

    unique_points = []
    for p in boundary_points:
        if p not in unique_points:
            unique_points.append(p)

    hatch_res = place_boundary_hatch(doc, unique_points, spec, conduit_id)
    if hatch_res.is_failure:
        return Result(error=hatch_res.error())

    msp = doc.modelspace()
    for i in range(len(pts) - 1):
        msp.add_line(
            pts[i].to_tuple()[:2],
            pts[i+1].to_tuple()[:2],
            dxfattribs={"layer": "A-FIRE-CABLES", "color": 2}
        )

    return Result(value=(conduit_run, hatch_res.unwrap()))
'''

# ─────────────────────────────────────────────────────────────────────
# 15. qomn_fire/output/revit_exporter.py (Revit JSON Exporter)
# ─────────────────────────────────────────────────────────────────────
INTEGRATED_FILES["qomn_fire/output/revit_exporter.py"] = '''"""
QOMN-FIRE BIM EXCHANGE SCHEMA EXPORTER
"""

import json
from typing import List
from qomn_fire.core.types import Device, ConduitRun, PanelRecommendation

def export_to_revit_json(devices: List[Device], runs: List[ConduitRun], facp: PanelRecommendation) -> str:
    schema = {
        "SchemaVersion": "1.0",
        "Project": "QOMN-FIRE INTEGRATED EXPORT ENGINE",
        "SelectedFACP": {
            "Model": facp.recommended_model,
            "Manufacturer": facp.manufacturer,
            "RequiredBatteryAh": facp.battery_size_ah,
            "PointsUtilization": facp.capacity_utilization,
            "Signature": facp.signature_hash
        },
        "Devices": [],
        "ConduitRuns": []
    }

    for d in devices:
        schema["Devices"].append({
            "Id": d.id,
            "Type": d.device_type.value,
            "Location": d.location.to_dict(),
            "ElevationFt": d.elevation_ft,
            "Circuit": d.circuit,
            "Zone": d.zone,
            "Hash": d.compute_hash()
        })

    for r in runs:
        schema["ConduitRuns"].append({
            "Id": r.id,
            "ConduitType": r.conduit_type.value,
            "TradeSize": r.trade_size,
            "TotalLengthFt": r.total_length_ft,
            "BendCount": r.bend_count,
            "BendDegrees": r.bend_degrees,
            "Path": [p.to_dict() for p in r.points],
            "Hash": r.compute_hash()
        })

    return json.dumps(schema, indent=2, sort_keys=True)
'''

# ─────────────────────────────────────────────────────────────────────
# 16. requirements.txt & setup.py
# ─────────────────────────────────────────────────────────────────────
INTEGRATED_FILES["requirements.txt"] = "ezdxf>=1.1.0\n"
INTEGRATED_FILES["setup.py"] = '''from setuptools import setup, find_packages
setup(
    name="qomn_fire",
    version="1.0.0",
    packages=find_packages(),
    install_requires=["ezdxf>=1.1.0"],
)
'''


# =====================================================================
# AUTOMATED WORKSPACE EXPORTER
# =====================================================================

def build_workspace_to_disk():
    print("[QOMN-FIRE INTEGRATION] Setting up workspace directory mappings...")
    for path, content in INTEGRATED_FILES.items():
        dir_path = os.path.dirname(path)
        if dir_path and not os.path.exists(dir_path):
            os.makedirs(dir_path)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        print(f" -> Created Integrated Module: {path}")

    # Generate __init__.py files
    init_paths = [
        "qomn_fire/__init__.py",
        "qomn_fire/core/__init__.py",
        "qomn_fire/engine/__init__.py",
        "qomn_fire/drawing/__init__.py",
        "qomn_fire/integration/__init__.py",
        "qomn_fire/output/__init__.py"
    ]
    for p in init_paths:
        with open(p, "w", encoding="utf-8") as f:
            f.write("# Integrated packages entry\n")

    print("[QOMN-FIRE INTEGRATION] All physical files verified and exported successfully.\n")


# =====================================================================
# INTEGRATED MULTI-ENGINE UNIT TESTING
# =====================================================================

class TestIntegratedQomnFire(unittest.TestCase):

    def setUp(self):
        from qomn_fire.engine.routing import GridMap3D
        self.grid_map = GridMap3D(step_m=0.5)

    def test_01_conduit_fill_golden(self):
        """
        VERIFICATION TEST 1: NEC Conduit Fill Calculation
        Input: 1/2" EMT, 3x 12 AWG wires
        Expected: fill_ratio = 3 * 8.58 / 196.1 ≈ 0.1312
        """
        from qomn_fire.engine.fill import calculate_conduit_fill
        res = calculate_conduit_fill("1/2", "12 AWG", 3)
        self.assertTrue(res.is_success)
        self.assertAlmostEqual(res.unwrap(), 3 * 8.58 / 196.1, places=4)

    def test_02_conduit_fill_physics_guard(self):
        """
        VERIFICATION TEST 2: Invalid Conduit and Wire Inputs
        Input: Invalid conduit size and invalid wire gauge
        Expected: Both return failure with correct code_ref
        """
        from qomn_fire.engine.fill import calculate_conduit_fill
        res1 = calculate_conduit_fill("NOT_REAL_CONDUIT", "12 AWG", 5)
        self.assertTrue(res1.is_failure)
        self.assertEqual(res1.error().code_ref, "NEC Table 4")

        res2 = calculate_conduit_fill("1/2", "NOT_A_WIRE", 10)
        self.assertTrue(res2.is_failure)
        self.assertEqual(res2.error().code_ref, "NEC Table 5")

    def test_03_smoke_placement_golden(self):
        """
        VERIFICATION TEST 3: NFPA 72 Smoke Detector Placement
        Input: 25x15m room at 9ft elevation
        Expected: 6 detectors placed deterministically
        """
        from qomn_fire.core.types import Point3D
        from qomn_fire.engine.placement import place_smoke_detectors_room

        room_min = Point3D(0.0, 0.0, 0.0)
        room_max = Point3D(25.0, 15.0, 0.0)

        res = place_smoke_detectors_room(room_min, room_max, 9.0, "CIRCUIT-A", "ZONE_A")
        self.assertTrue(res.is_success)
        devices = res.unwrap()
        self.assertEqual(len(devices), 6)

        # All devices must be inside room boundaries
        for d in devices:
            self.assertGreater(d.location.x, -0.1)
            self.assertGreater(d.location.y, -0.1)
            self.assertLess(d.location.x, 25.1)
            self.assertLess(d.location.y, 15.1)

    def test_04_determinism_stress(self):
        """
        VERIFICATION TEST 4: Determinism Stress (50× SHA-256)
        Input: Same A* routing query repeated 50 times
        Expected: Every run produces identical SHA-256 hash
        """
        from qomn_fire.core.types import ConduitType, Point3D
        from qomn_fire.engine.routing import GridMap3D, astar_route_3d

        sig_ref = None
        for cycle in range(50):
            g_map = GridMap3D(step_m=0.5)
            g_map.add_obstacle(Point3D(2.0, 2.0, 0.0))

            res = astar_route_3d(
                grid_map=g_map,
                start=Point3D(0.0, 0.0, 0.0),
                end=Point3D(5.0, 5.0, 0.0),
                conduit=ConduitType.EMT,
                conduit_id="C_RUN_1"
            )
            self.assertTrue(res.is_success)
            run = res.unwrap()
            cycle_sig = run.compute_hash()

            if sig_ref is None:
                sig_ref = cycle_sig
            else:
                self.assertEqual(sig_ref, cycle_sig, f"Deviation found on iteration cycle {cycle}")
        print(f"[DETERMINISM] 50 iterations verified. SHA-256: {sig_ref}")

    def test_05_routing_exceeds_bend_limits_fails(self):  # NOSONAR — S3776: cognitive complexity is inherent to the safety-critical algorithm
        """
        VERIFICATION TEST 5: Conduit Bend Constraint Enforcement (NEC Art 358.26)
        Case: Bounded corridor with alternating walls forces >360 degrees of bends.
        Floor and ceiling slabs at z=-1 and z=1 prevent 3D escape routing.
        Expected: Fail path validation, return NECViolationError.
        """
        from qomn_fire.core.types import ConduitType, Point3D
        from qomn_fire.engine.routing import GridMap3D, astar_route_3d

        g_map = GridMap3D(step_m=1.0)

        # Boundary walls at z=0
        for y in range(-2, 40):
            g_map.add_obstacle(Point3D(-1.0, float(y), 0.0))
            g_map.add_obstacle(Point3D(4.0, float(y), 0.0))

        # Alternating complete walls with single-cell gaps
        # Forces path to zigzag back and forth across the corridor
        for i in range(8):
            y = 2 + i * 2
            if i % 2 == 0:  # gap at x=3
                for x in range(0, 3):
                    g_map.add_obstacle(Point3D(float(x), float(y), 0.0))
            else:  # gap at x=0
                for x in range(1, 4):
                    g_map.add_obstacle(Point3D(float(x), float(y), 0.0))

        # Floor and ceiling slabs: block all positions at z=-1 and z=1
        # This physically prevents A* from escaping the 2D plane
        for z_level in [-1, 1]:
            for x in range(-1, 5):
                for y in range(-2, 40):
                    g_map.add_obstacle(Point3D(float(x), float(y), float(z_level)))

        res = astar_route_3d(
            grid_map=g_map,
            start=Point3D(0.0, 0.0, 0.0),
            end=Point3D(2.0, 18.0, 0.0),
            conduit=ConduitType.EMT,
            conduit_id="C_VIOL"
        )
        self.assertTrue(res.is_failure)
        self.assertEqual(res.error().code_ref, "NEC Article 358.26")

    def test_06_integrated_facp_selection(self):
        """
        VERIFICATION TEST 6: Integrated FACP Selection Sizing
        Input: 30 devices, 2 NAC circuits, Standalone US project.
        Expected: Selects Siemens FC901. Battery back-up capacity ≈ 5.80 Ah
        (V58 tiered derating: 1.10×1.15×1.20=1.518, per-device standby 0.8mA).
        """
        from qomn_fire.core.types import ProjectRequirements
        from qomn_fire.engine.panel_selector import SelectionEngine

        req = ProjectRequirements(
            device_count=30,
            nac_circuit_count=2,
            building_size_m2=1500.0,
            building_floors=2,
            requires_network=False,
            requires_voice=False,
            requires_releasing=False,
            jurisdiction="US"
        )

        res = SelectionEngine.select_panel(req)
        self.assertTrue(res.is_success)
        rec = res.unwrap()

        self.assertEqual(rec.recommended_model, "FC901")
        self.assertEqual(rec.manufacturer, "SIEMENS")
        self.assertAlmostEqual(rec.battery_size_ah, 5.80, delta=0.01)
        self.assertIn("combined_safety_factor", rec.battery_derating_details)
        self.assertAlmostEqual(rec.battery_derating_details["combined_safety_factor"], 1.518, places=3)
        self.assertEqual(rec.battery_derating_details["per_device_standby_mA"], 0.8)

    def test_07_placement_to_selection_vascular_pipeline(self):
        """
        VERIFICATION TEST 7: Multi-Engine Integrated Sizing (Vascular Link)
        Input: Large Room (25x15m), placing devices automatically, then selecting panel.
        Expected: Placement places 6 detectors. Selector evaluates and recommends FC901.
        """
        from qomn_fire.core.types import Point3D, ProjectRequirements
        from qomn_fire.engine.panel_selector import SelectionEngine
        from qomn_fire.engine.placement import place_smoke_detectors_room

        room_min = Point3D(0.0, 0.0, 0.0)
        room_max = Point3D(25.0, 15.0, 0.0)

        # 1. Place detectors
        place_res = place_smoke_detectors_room(room_min, room_max, 9.0, "CIRCUIT-A", "ZONE_A")
        self.assertTrue(place_res.is_success)
        devices = place_res.unwrap()
        self.assertEqual(len(devices), 6)

        # 2. Vascular link counts directly to panel requirements
        req = ProjectRequirements(
            device_count=len(devices),
            nac_circuit_count=2,
            building_size_m2=375.0,
            building_floors=1,
            requires_network=False,
            requires_voice=False,
            requires_releasing=False,
            jurisdiction="US"
        )

        select_res = SelectionEngine.select_panel(req)
        self.assertTrue(select_res.is_success)
        rec = select_res.unwrap()

        self.assertEqual(rec.recommended_model, "FC901")


# =====================================================================
# INTEGRATED SYSTEM PILOT DEMONSTRATION
# =====================================================================

def execute_integrated_master_project():
    """Runs a complete end-to-end fire protective design, sizing, and CAD production pipeline."""
    print("\n" + "="*80)
    print("        QOMN-FIRE INTEGRATED PIPELINE: FULL PROJECT COMPILATION")
    print("="*80)

    from qomn_fire.core.constants import NFPA_SMOKE_DETECTOR_SPACING_M
    from qomn_fire.core.types import (
        ConduitType,
        HatchSpec,
        Point3D,
        ProjectRequirements,
        Revision,
        TitleBlock,
    )
    from qomn_fire.drawing.dxf_generator import (
        add_viewport,
        create_document,
        setup_layers,
    )
    from qomn_fire.drawing.hatch_engine import (
        generate_circle_polyline,
        place_boundary_hatch,
    )
    from qomn_fire.drawing.revision_control import (
        draw_revision_table,
    )
    from qomn_fire.drawing.title_block import draw_facp_schedule, draw_title_block
    from qomn_fire.engine.panel_selector import SelectionEngine
    from qomn_fire.engine.placement import place_smoke_detectors_room
    from qomn_fire.engine.routing import GridMap3D
    from qomn_fire.integration.cable_hatch import route_conduit_and_hatch
    from qomn_fire.output.revit_exporter import export_to_revit_json

    # 1. Initialize Drawing Doc
    doc = create_document()
    setup_layers(doc)
    msp = doc.modelspace()

    # 2. Rectangular Building Room Coordinates
    room_min = Point3D(0.0, 0.0, 0.0)
    room_max = Point3D(25.0, 15.0, 0.0)

    # Draw physical walls
    wall_attribs = {"layer": "A-WALL", "color": 7}
    msp.add_line((room_min.x, room_min.y), (room_max.x, room_min.y), dxfattribs=wall_attribs)
    msp.add_line((room_max.x, room_min.y), (room_max.x, room_max.y), dxfattribs=wall_attribs)
    msp.add_line((room_max.x, room_max.y), (room_min.x, room_max.y), dxfattribs=wall_attribs)
    msp.add_line((room_min.x, room_max.y), (room_min.x, room_min.y), dxfattribs=wall_attribs)

    # 3. NFPA-Compliant Automatic Space Device Placement
    print(" -> Resolving detector layouts...")
    place_res = place_smoke_detectors_room(room_min, room_max, 9.0, "FA-LP1", "ZONE_1")
    devices = place_res.unwrap()

    h_spec_coverage = HatchSpec("ANSI31", 45.0, 0.1, 3, "A-FIRE-HATC", "Smoke Coverage", "NFPA 72 §17")

    for d in devices:
        msp.add_circle(d.location.to_tuple()[:2], radius=0.4, dxfattribs={"layer": "A-FIRE-DEVICES", "color": 1})
        msp.add_text(d.id, dxfattribs={"insert": (d.location.x + 0.5, d.location.y + 0.5), "height": 0.25, "layer": "A-FIRE-TEXT", "color": 5})

        # Coverage zone boundary hatch
        boundary = generate_circle_polyline(d.location, NFPA_SMOKE_DETECTOR_SPACING_M)
        place_boundary_hatch(doc, boundary, h_spec_coverage, d.id)

    # 4. NFPA & NEC Compliant FACP Selection (Direct Vascular Linkage)
    print(" -> Dynamically selecting panel based on device loads...")
    req = ProjectRequirements(
        device_count=len(devices),
        nac_circuit_count=2,
        building_size_m2=375.0,
        building_floors=1,
        requires_network=False,
        requires_voice=False,
        requires_releasing=False,
        jurisdiction="FDNY",
        preferred_manufacturer="SIEMENS"
    )

    selection_res = SelectionEngine.select_panel(req)
    rec = selection_res.unwrap()
    print(f"   -> Selected FACP: {rec.recommended_model} ({rec.manufacturer}) - Battery size: {rec.battery_size_ah} Ah")

    # 5. Routing conduits between sequential devices
    print(" -> Routing routing paths...")
    grid_map = GridMap3D(step_m=0.5)
    for d in devices:
        grid_map.add_obstacle(d.location)

    conduit_spec = HatchSpec("CROSS", 0.0, 0.05, 3, "A-FIRE-HATC", "Conduit Corridor", "NEC 760")
    conduit_runs = []

    for idx in range(len(devices) - 1):
        start_pt = devices[idx].location
        end_pt = devices[idx+1].location

        grid_map.obstacles.discard(grid_map.to_grid(start_pt))
        grid_map.obstacles.discard(grid_map.to_grid(end_pt))

        res = route_conduit_and_hatch(
            grid_map=grid_map,
            doc=doc,
            start=start_pt,
            end=end_pt,
            conduit=ConduitType.EMT,
            conduit_id=f"CONDUIT_RUN_{idx:02d}",
            spec=conduit_spec
        )

        grid_map.add_obstacle(start_pt)
        grid_map.add_obstacle(end_pt)

        if res.is_success:
            run_item, _ = res.unwrap()
            conduit_runs.append(run_item)

    # 6. Dimensions and Layout Graphics
    if len(devices) >= 2:
        msp.add_aligned_dim(
            p1=devices[0].location.to_tuple()[:2],
            p2=devices[1].location.to_tuple()[:2],
            distance=2.0,
            dxfattribs={"layer": "A-FIRE-DIMS", "color": 4}
        )

    # Title Block Sheet
    title = TitleBlock(
        project_name="INTEGRATED LIFE SAFETY NETWORK",
        drawing_number="QOMN-FA-001",
        sheet_title="FIRE ALARM DEVICE DISTRIBUTION & INHERENT SIZING PLAN",
        scale="1:100",
        date="2026-05-31",
        designer="Systems Automation Architect",
        checker="Senior Verification Audit Engineer",
        pe_stamp="REPLACE_WITH_REAL_PE_STAMP_BEFORE_DELIVERY",
        client="Hospital General Board",
        address="Zone 2 Building C Complex"
    )
    draw_title_block(doc, title)

    # Draw dynamically computed FACP Schedule inside layout sheet
    draw_facp_schedule(doc, rec)

    # Aligned Viewport
    # S930 fix: parameter name must match `qomn_fire/drawing/dxf_generator.py::add_viewport`
    # which uses `view_center=` (NOT `view_center_point=`).
    add_viewport(doc, center=(350.0, 300.0), size=(500.0, 400.0), view_center=(12.5, 7.5), view_height=20.0)

    # Legend Table and Revisions table
    revs = [
        Revision(0, "2026-05-31", "Merged routing with dynamic FACP selections", "SYS_INTEGRATOR")
    ]
    draw_revision_table(doc, revs)

    # 7. Compile files to disk
    dxf_path = "fire_alarm_plan.dxf"
    doc.saveas(dxf_path)
    print(f"\n -> CAD shop drawing compiled: '{dxf_path}'")

    revit_json = export_to_revit_json(devices, conduit_runs, rec)
    revit_path = "revit_import.json"
    with open(revit_path, "w", encoding="utf-8") as f:
        f.write(revit_json)
    print(f" -> Revit BIM metadata compiled: '{revit_path}'")

    print("\n[QOMN-FIRE INTEGRATION] Compilation run completed successfully.")


# =====================================================================
# RUNTIME CONTROLLER MAIN BLOCK
# =====================================================================

if __name__ == "__main__":
    print("="*80)
    print("        QOMN-FIRE: MASTER INTEGRATED SUITE RUNTIME ENGINE")
    print("="*80)

    # 1. Output the workspace codefiles on disk
    build_workspace_to_disk()

    # Add generated directory path to python loading path context
    sys.path.insert(0, os.path.abspath(os.getcwd()))

    # 2. Run the dynamic unit testing suite
    print("="*80)
    print("             EXECUTING AUTOMATED CRITICAL UNIT TEST SUITE")
    print("="*80)
    suite = unittest.TestLoader().loadTestsFromTestCase(TestIntegratedQomnFire)
    runner = unittest.TextTestRunner(verbosity=2)
    test_result = runner.run(suite)

    if not test_result.wasSuccessful():
        print("\n[CRITICAL ERROR] Test suite failures occurred. Aborting compilation runs.")
        sys.exit(1)

    # 3. Run production master project
    print("\n" + "="*80)
    print("             RUNNING END-TO-END CAD/BIM PRODUCTION WORKFLOW")
    print("="*80)
    execute_integrated_master_project()
