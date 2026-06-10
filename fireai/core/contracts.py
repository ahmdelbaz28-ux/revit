"""
FireAI Service Contracts — Versioned JSON Schemas
==================================================
Defines the data contracts between services.

Each contract is versioned so services can evolve independently.
Breaking changes require a new major version.

Extracted from consultant's microservices proposal —
useful even in monolithic mode for type safety and documentation.
"""

from __future__ import annotations
import math

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

# ============================================================================
# CONTRACT v1 — Shared Data Models
# ============================================================================

CONTRACT_VERSION = "v1"


class CeilingType(str, Enum):
    """NFPA 72 ceiling classifications.

    CONSOLIDATED: This enum is the canonical source. nfpa72_models.py
    CeilingType re-exports from here for backward compatibility.
    Includes all ceiling types from both original files.
    """

    FLAT = "FLAT"
    SLOPED = "SLOPED"
    BEAMED = "BEAMED"
    COFFERED = "COFFERED"
    DOMED = "DOMED"
    # Extended types from nfpa72_models.py for full compatibility
    SMOOTH = "SMOOTH"
    GABLE = "GABLE"
    SHED = "SHED"
    CORRIDOR = "CORRIDOR"
    TRUSS = "TRUSS"
    COMBUSTIBLE = "COMBUSTIBLE"


class ConfidenceLevel(str, Enum):
    """Confidence levels for analysis results."""

    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    UNKNOWN = "UNKNOWN"


class DetectorType(str, Enum):
    """NFPA 72 detector types.

    CONSOLIDATED: Includes all types from both contracts.py and
    nfpa72_models.py to prevent enum drift between modules.
    """

    SMOKE = "SMOKE"
    SMOKE_PHOTOELECTRIC = "SMOKE_PHOTOELECTRIC"
    SMOKE_IONIZATION = "SMOKE_IONIZATION"
    SMOKE_MULTI_CRITERIA = "SMOKE_MULTI_CRITERIA"
    HEAT = "HEAT"
    HEAT_FIXED = "HEAT_FIXED"
    HEAT_FIXED_TEMP = "HEAT_FIXED_TEMP"  # Alias: same category as HEAT_FIXED
    HEAT_RATE_OF_RISE = "HEAT_RATE_OF_RISE"
    HEAT_COMBINATION = "HEAT_COMBINATION"
    COMBINATION = "COMBINATION"
    SMOKE_HEAT_COMBINATION = "SMOKE_HEAT_COMBINATION"
    FLAME = "FLAME"
    GAS = "GAS"


# ============================================================================
# ParsedDrawing → Parser Service Output
# ============================================================================


@dataclass(frozen=True)
class ParsedDrawingContract:
    """Contract: Parser → Analyzer

    The parser service produces this from DXF/DWG/PDF/IFC files.
    The analyzer service consumes this as input.
    """

    contract_version: str = CONTRACT_VERSION
    source_file: str = ""
    source_sha256: str = ""
    file_type: str = ""
    rooms: List[Dict[str, Any]] = field(default_factory=list)
    layers: List[Dict[str, Any]] = field(default_factory=list)
    entities: List[Dict[str, Any]] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# ============================================================================
# RoomSpecification → Analyzer Service Input
# ============================================================================


@dataclass(frozen=True)
class CeilingSpecContract:
    """Ceiling specification per NFPA 72."""

    height_at_low_point_m: float
    height_at_high_point_m: float
    ceiling_type: CeilingType = CeilingType.FLAT


@dataclass(frozen=True)
class RoomSpecificationContract:
    """Contract: Analyzer Input

    The analyzer service receives this specification
    and produces a DetectorPlacementContract.
    """

    contract_version: str = CONTRACT_VERSION
    room_id: str = ""
    width_m: float = 0.0
    depth_m: float = 0.0
    occupancy_type: str = "office"
    ceiling_spec: Optional[CeilingSpecContract] = None
    polygon: List[tuple] = field(default_factory=list)
    detector_type: DetectorType = DetectorType.SMOKE_PHOTOELECTRIC

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        if self.ceiling_spec:
            d["ceiling_spec"] = asdict(self.ceiling_spec)
        return d


# ============================================================================
# DetectorPlacement → Analyzer Service Output
# ============================================================================


@dataclass(frozen=True)
class DetectorPlacementContract:
    """Contract: Analyzer → Compliance

    The analyzer produces detector positions.
    The compliance service verifies they meet NFPA 72.
    """

    contract_version: str = CONTRACT_VERSION
    room_id: str = ""
    detector_positions: List[tuple] = field(default_factory=list)
    detector_type: DetectorType = DetectorType.SMOKE_PHOTOELECTRIC
    coverage_fraction: float = 0.0
    compliant: bool = False
    confidence: ConfidenceLevel = ConfidenceLevel.UNKNOWN
    confidence_score: float = 0.0
    wall_violations: List[Dict[str, Any]] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# ============================================================================
# ComplianceReport → Compliance Service Output
# ============================================================================


@dataclass(frozen=True)
class ComplianceReportContract:
    """Contract: Compliance → Reporting

    The compliance service verifies detector placements
    and produces a compliance report.
    """

    contract_version: str = CONTRACT_VERSION
    room_id: str = ""
    nfpa_version: str = "NFPA 72-2022"
    compliant: bool = False
    spacing_compliant: bool = False
    coverage_compliant: bool = False
    wall_distance_compliant: bool = False
    coverage_fraction: float = 0.0
    violations: List[Dict[str, Any]] = field(default_factory=list)
    proof_certificate_hash: Optional[str] = None
    audit_event_hash: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# ============================================================================
# AuditEvent → All Services → Audit Service
# ============================================================================


@dataclass(frozen=True)
class AuditEventContract:
    """Contract: Any Service → Audit

    Every significant action across all services
    must emit an audit event.
    """

    contract_version: str = CONTRACT_VERSION
    event_type: str = ""
    source_service: str = ""
    room_id: str = ""
    details: Dict[str, Any] = field(default_factory=dict)
    timestamp_utc: str = ""
    previous_hash: str = "GENESIS"
    current_hash: str = ""
    signature: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# ============================================================================
# Feature Flags — Config Service
# ============================================================================


class PathwaySurvivabilityLevel(str, Enum):
    """NFPA 72-2022 §12.4 — Pathway Survivability Levels.

    Determines the minimum fire-resistance rating for fire alarm wiring
    based on building occupancy and evacuation strategy.  Lives depend
    on these cables remaining functional during a fire.

    Level 1: General-purpose wiring in fully sprinklered buildings.
             Cables may be FPL (unrated) in ordinary conduits.
    Level 2: 2-hour fire-resistance rating required.
             Either CI cable OR ordinary cable in 2-hour rated enclosure.
             Required for: partial evacuation, high-rise, voice evacuation.
    Level 3: 2-hour fire-resistance rating with CI cable IN 2-hour
             rated enclosure.  Highest protection level.
             Required for: staged evacuation in non-sprinklered buildings.
    """

    LEVEL_1 = "LEVEL_1"
    LEVEL_2 = "LEVEL_2"
    LEVEL_3 = "LEVEL_3"


class CableType(str, Enum):
    """NEC Article 760 — Fire alarm cable ratings.

    FPL:  Fire Power Limited — general use, no fire rating.
    FPLR: Fire Power Limited Riser — vertical shafts between floors.
    FPLP: Fire Power Limited Plenum — plenum/return-air spaces.
    CI:   Circuit Integrity — 2-hour fire-resistance rated (NFPA 72 §12.4.2).
    """

    FPL = "FPL"
    FPLR = "FPLR"
    FPLP = "FPLP"
    CI = "CI"


class OccupancyCategory(str, Enum):
    """Building occupancy classification for pathway survivability determination.

    Derived from NFPA 101 Life Safety Code and IBC occupancy groups.
    Determines which PathwaySurvivabilityLevel is required.
    """

    ASSEMBLY = "ASSEMBLY"  # IBC Group A — theatres, churches
    EDUCATIONAL = "EDUCATIONAL"  # IBC Group E — schools
    HEALTH_CARE = "HEALTH_CARE"  # IBC Group I-2 — hospitals
    RESIDENTIAL = "RESIDENTIAL"  # IBC Group R — hotels, apartments
    BUSINESS = "BUSINESS"  # IBC Group B — offices
    MERCANTILE = "MERCANTILE"  # IBC Group M — retail
    INDUSTRIAL = "INDUSTRIAL"  # IBC Group F — factories
    STORAGE = "STORAGE"  # IBC Group S — warehouses
    HIGH_RISE = "HIGH_RISE"  # Any building >23 m (75 ft) in height
    DETENTION = "DETENTION"  # IBC Group I-3 — prisons


class FeatureFlag(str, Enum):
    """Feature flags for toggling functionality per service.

    Read from config service (or environment variables in monolithic mode).
    """

    # Safety features (some currently DISABLED_BY_V8)
    SMOKE_SIMULATION = "SMOKE_SIMULATION"
    DIGITAL_TWIN_SYNC = "DIGITAL_TWIN_SYNC"
    SELF_LEARNING = "SELF_LEARNING"

    # Analysis features
    RESILIENCE_CHECK = "RESILIENCE_CHECK"
    PROOF_CERTIFICATE = "PROOF_CERTIFICATE"
    VORONOI_VERIFICATION = "VORONOI_VERIFICATION"

    # Integration features
    AUTOCAD_BRIDGE = "AUTOCAD_BRIDGE"
    REVIT_BRIDGE = "REVIT_BRIDGE"
    DIALUX_BRIDGE = "DIALUX_BRIDGE"


# Default feature flag states
DEFAULT_FEATURE_FLAGS: Dict[str, bool] = {
    FeatureFlag.SMOKE_SIMULATION: False,  # Disabled by V8
    FeatureFlag.DIGITAL_TWIN_SYNC: True,
    FeatureFlag.SELF_LEARNING: False,  # Disabled by V8
    FeatureFlag.RESILIENCE_CHECK: True,
    FeatureFlag.PROOF_CERTIFICATE: True,
    FeatureFlag.VORONOI_VERIFICATION: True,
    FeatureFlag.AUTOCAD_BRIDGE: True,
    FeatureFlag.REVIT_BRIDGE: True,
    FeatureFlag.DIALUX_BRIDGE: True,
}


def get_feature_flags() -> Dict[str, bool]:
    """Get current feature flag states.

    Reads from FIREAI_FEATURE_FLAGS env var (JSON) or uses defaults.
    Example: FIREAI_FEATURE_FLAGS='{"SMOKE_SIMULATION": true}'
    """
    import json
    import os

    flags = dict(DEFAULT_FEATURE_FLAGS)

    env_flags = os.environ.get("FIREAI_FEATURE_FLAGS")
    if env_flags:
        try:
            overrides = json.loads(env_flags)
            flags.update(overrides)
        except json.JSONDecodeError:
            pass

    return flags


def is_feature_enabled(flag: FeatureFlag) -> bool:
    """Check if a specific feature flag is enabled."""
    return get_feature_flags().get(flag, False)


# ============================================================================
# STRICT_ENGINEERING: Input Contract Validation
# ============================================================================
# Adapted from Elite Platform V2 contracts.py.
# Prevents injection of derived fields (area_m2, width_m, etc.) via API
# that could bypass calculation and report fake compliance data.

FORBIDDEN_DERIVED_FIELDS: tuple = (
    "area_m2",
    "area_sqm",
    "width_m",
    "depth_m",
    "centroid_x",
    "centroid_y",
    "coverage_pct",
    "detector_count",
    "is_compliant",
    "nfpa_valid",
    "proof_valid",
    # v2: spacing is derived from detector_type + ceiling_height per
    # NFPA 72 Table 17.6.3.1.1 — accepting it from input bypasses this lookup
    "spacing_m",
    "listed_spacing_m",
    "coverage_radius_m",
    # v2: these are computed from polygon, must not be supplied externally
    "perimeter_m",
    "min_wall_distance_m",
)
"""
Fields that MUST be computed internally — never accepted from external input.

Accepting these from an API payload would allow a caller to inject
fake values (e.g. area_m2=999, is_compliant=True) and bypass the
entire calculation pipeline.  In a life-safety system, this is
equivalent to forging a safety certificate.
"""


class ContractViolation(ValueError):
    """Raised when an input payload violates a strict contract rule."""

    pass


def validate_room_input(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Validate a room input payload before it enters the calculation pipeline.

    Checks:
      1. No forbidden derived fields are present (prevents data injection).
      2. Required fields are present and valid.
      3. Numeric fields are within physically plausible bounds.

    Args:
        payload: Raw dictionary from API / JSON / parser.

    Returns:
        The validated payload (unchanged if valid).

    Raises:
        ContractViolation: If any contract rule is violated.
    """
    if not isinstance(payload, dict):
        raise ContractViolation("Room input must be a dictionary")

    # 1. Reject derived fields — these MUST be computed, not supplied
    for field_name in FORBIDDEN_DERIVED_FIELDS:
        if field_name in payload:
            raise ContractViolation(
                f"Field '{field_name}' is derived internally and must not be "
                f"supplied in input. The system computes this value from the "
                f"polygon geometry to prevent data injection."
            )

    # 2. Required fields
    required = ("room_id", "polygon", "ceiling_height_m")
    for field_name in required:
        if field_name not in payload:
            raise ContractViolation(f"Missing required field: '{field_name}'")

    # 3. Validate room_id: non-empty, string, max 256 chars (DoS guard)
    room_id_val = payload.get("room_id")
    if not room_id_val or not isinstance(room_id_val, str):
        raise ContractViolation("room_id must be a non-empty string")
    if len(room_id_val) > 256:
        raise ContractViolation(
            f"room_id length {len(room_id_val)} exceeds 256-character limit. "
            "Oversized IDs can cause memory exhaustion in downstream indexing."
        )

    # 4. Validate polygon is a list of at least 3 points
    polygon = payload.get("polygon")
    if not isinstance(polygon, (list, tuple)) or len(polygon) < 3:
        raise ContractViolation(f"polygon must be a list of at least 3 points, got {type(polygon).__name__}")

    # 4a. Validate polygon points are numeric — prevents downstream crashes
    #     A polygon like [{"x": "abc"}] passes the len check but crashes
    #     when Shapely tries to compute area.
    coords = []
    for i, pt in enumerate(polygon):
        if isinstance(pt, (list, tuple)):
            if len(pt) < 2:
                raise ContractViolation(f"polygon point {i} must have at least 2 coordinates, got {len(pt)}")
            try:
                x_val = float(pt[0])
                y_val = float(pt[1])
            except (TypeError, ValueError):
                raise ContractViolation(f"polygon point {i} coordinates must be numeric, got {pt!r}")
            if not (math.isfinite(x_val) and math.isfinite(y_val)):
                raise ContractViolation(
                    f"polygon point {i} contains non-finite coordinate: ({x_val}, {y_val}). "
                    "NaN/Inf coordinates corrupt geometry calculations."
                )
            _MAX_COORD = 1_000_000.0  # 1000 km — physically impossible building
            if abs(x_val) > _MAX_COORD or abs(y_val) > _MAX_COORD:
                raise ContractViolation(
                    f"polygon point {i} coordinate ({x_val}, {y_val}) exceeds 1,000,000m limit. "
                    "Implausible coordinates indicate data corruption."
                )
            coords.append((x_val, y_val))
        elif isinstance(pt, dict):
            x_val = pt.get("x", pt.get("X"))
            y_val = pt.get("y", pt.get("Y"))
            if x_val is None or y_val is None:
                raise ContractViolation(f"polygon point {i} dict must have 'x' and 'y' keys, got {list(pt.keys())}")
            try:
                x_val = float(x_val)
                y_val = float(y_val)
            except (TypeError, ValueError):
                raise ContractViolation(f"polygon point {i} coordinates must be numeric, got x={x_val!r} y={y_val!r}")
            if not (math.isfinite(x_val) and math.isfinite(y_val)):
                raise ContractViolation(
                    f"polygon point {i} dict contains non-finite coordinate: ({x_val}, {y_val})."
                )
            _MAX_COORD = 1_000_000.0
            if abs(x_val) > _MAX_COORD or abs(y_val) > _MAX_COORD:
                raise ContractViolation(
                    f"polygon point {i} dict coordinate ({x_val}, {y_val}) exceeds 1,000,000m limit."
                )
            coords.append((x_val, y_val))
        else:
            raise ContractViolation(f"polygon point {i} must be a tuple/list or dict, got {type(pt).__name__}")

    # 4b. Polygon self-intersection check — prevents wrong area calculations.
    #     A self-intersecting polygon (e.g. figure-8) has ambiguous area
    #     and produces incorrect coverage results from Shapely. In a
    #     life-safety system, this means detectors could be placed based
    #     on wrong room geometry.
    try:
        from shapely.geometry import Polygon as ShapelyPolygon

        if len(coords) >= 3:
            shapely_poly = ShapelyPolygon(coords)
            if not shapely_poly.is_valid:
                # is_valid checks for self-intersection, ring orientation, etc.
                raise ContractViolation(
                    f"polygon is self-intersecting or otherwise invalid. "
                    f"Self-intersecting polygons produce wrong area calculations, "
                    f"which leads to incorrect detector counts. Fix the polygon geometry."
                )
    except ImportError:
        # V114 FIX: Shapely unavailable = geometric validation SKIPPED = potential danger.
        # Must warn, not silently pass. Self-intersecting polygons produce wrong
        # detector counts — a life-safety catastrophe.
        import logging as _logging

        _logging.getLogger(__name__).critical(
            "Shapely not available — polygon self-intersection validation SKIPPED. "
            "Self-intersecting polygons produce wrong area calculations and incorrect "
            "detector counts. Install Shapely for full geometric validation."
        )

    # 5. Validate ceiling_height_m is positive
    ceiling_height = payload.get("ceiling_height_m")
    try:
        h = float(ceiling_height)
        # V54 FIX: NaN/Inf bypass float comparisons (NaN > 30 = False, NaN <= 0 = False).
        # In a life-safety system, NaN entering the system means ALL downstream
        # safety checks are compromised. Block at the contract boundary.
        import math as _m

        if not _m.isfinite(h):
            raise ContractViolation(
                f"ceiling_height_m must be finite, got {h}. "
                f"NaN/Inf values bypass all downstream safety checks. "
                f"[NFPA 72 §17.6.3]"
            )
        if h <= 0 or h > 30:
            raise ContractViolation(f"ceiling_height_m must be > 0 and <= 30, got {h}")
    except (TypeError, ValueError):
        raise ContractViolation(f"ceiling_height_m must be a number, got {ceiling_height!r}")

    return payload


# ============================================================================
# STRICT_ENGINEERING: Loop Input Validation
# ============================================================================

# Forbidden derived fields for loop inputs
FORBIDDEN_LOOP_DERIVED_FIELDS: tuple = (
    "voltage_drop_v",
    "is_compliant",
    "max_distance_m",
)


def validate_loop_input(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Validate an SLC loop input payload before design.

    Checks:
      1. No forbidden derived fields (voltage_drop_v, is_compliant).
      2. Required fields: loop_id, device_count or devices list.
      3. Device count within NFPA 72 limits.
      4. Total length is positive.
      5. Cable specification is valid.

    Args:
        payload: Raw dictionary from API / config.

    Returns:
        The validated payload (unchanged if valid).

    Raises:
        ContractViolation: If any contract rule is violated.
    """
    if not isinstance(payload, dict):
        raise ContractViolation("Loop input must be a dictionary")

    # 1. Reject derived fields
    for field_name in FORBIDDEN_LOOP_DERIVED_FIELDS:
        if field_name in payload:
            raise ContractViolation(
                f"Field '{field_name}' is derived internally and must not be "
                f"supplied in input. Voltage drop and compliance are computed "
                f"from cable length, gauge, and current."
            )

    # 2. Required fields
    if "loop_id" not in payload:
        raise ContractViolation("Missing required field: 'loop_id'")

    # 3. Device count limits (NFPA 72 §21.2.2: max 250 per loop typically)
    device_count = payload.get("device_count") or len(payload.get("devices", []))
    if device_count and device_count > 250:
        raise ContractViolation(
            f"Loop has {device_count} devices — exceeds NFPA 72 §21.2.2 limit of 250 devices per SLC loop"
        )

    # 4. Total length must be positive if provided
    total_length = payload.get("total_length_m")
    if total_length is not None:
        try:
            l = float(total_length)
            if l < 0:
                raise ContractViolation(f"total_length_m must be >= 0, got {l}")
        except (TypeError, ValueError):
            raise ContractViolation(f"total_length_m must be a number, got {total_length!r}")

    # 5. Panel voltage validation
    panel_voltage = payload.get("panel_voltage_v", 24.0)
    try:
        v = float(panel_voltage)
        # V54 FIX: NaN/Inf panel voltage bypasses all voltage drop checks.
        import math as _m2

        if not _m2.isfinite(v):
            raise ContractViolation(
                f"panel_voltage_v must be finite, got {v}. "
                f"NaN/Inf bypass all voltage drop safety checks. [NFPA 72 §10.14]"
            )
        if v <= 0 or v > 48:
            raise ContractViolation(f"panel_voltage_v must be > 0 and <= 48, got {v}")
    except (TypeError, ValueError):
        raise ContractViolation(f"panel_voltage_v must be a number, got {panel_voltage!r}")

    return payload


__all__ = [
    "CONTRACT_VERSION",
    "CeilingType",
    "ConfidenceLevel",
    "DetectorType",
    "PathwaySurvivabilityLevel",
    "CableType",
    "OccupancyCategory",
    "FeatureFlag",
    "DEFAULT_FEATURE_FLAGS",
    "ParsedDrawingContract",
    "CeilingSpecContract",
    "RoomSpecificationContract",
    "DetectorPlacementContract",
    "ComplianceReportContract",
    "AuditEventContract",
    "get_feature_flags",
    "is_feature_enabled",
    # STRICT_ENGINEERING: Input validation
    "ContractViolation",
    "FORBIDDEN_DERIVED_FIELDS",
    "FORBIDDEN_LOOP_DERIVED_FIELDS",
    "validate_room_input",
    "validate_loop_input",
]
