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

from dataclasses import dataclass, field, asdict
from typing import List, Optional, Dict, Any
from enum import Enum


# ============================================================================
# CONTRACT v1 — Shared Data Models
# ============================================================================

CONTRACT_VERSION = "v1"


class CeilingType(str, Enum):
    """NFPA 72 ceiling classifications."""
    FLAT = "FLAT"
    SLOPED = "SLOPED"
    BEAMED = "BEAMED"
    COFFERED = "COFFERED"
    DOMED = "DOMED"


class ConfidenceLevel(str, Enum):
    """Confidence levels for analysis results."""
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    UNKNOWN = "UNKNOWN"


class DetectorType(str, Enum):
    """NFPA 72 detector types."""
    SMOKE_PHOTOELECTRIC = "SMOKE_PHOTOELECTRIC"
    SMOKE_IONIZATION = "SMOKE_IONIZATION"
    HEAT_FIXED = "HEAT_FIXED"
    HEAT_RATE_OF_RISE = "HEAT_RATE_OF_RISE"
    COMBINATION = "COMBINATION"


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
    FeatureFlag.SMOKE_SIMULATION: False,      # Disabled by V8
    FeatureFlag.DIGITAL_TWIN_SYNC: True,
    FeatureFlag.SELF_LEARNING: False,          # Disabled by V8
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

    # 3. Validate room_id is non-empty
    if not payload.get("room_id"):
        raise ContractViolation("room_id must be a non-empty string")

    # 4. Validate polygon is a list of at least 3 points
    polygon = payload.get("polygon")
    if not isinstance(polygon, (list, tuple)) or len(polygon) < 3:
        raise ContractViolation(
            f"polygon must be a list of at least 3 points, got {type(polygon).__name__}"
        )

    # 5. Validate ceiling_height_m is positive
    ceiling_height = payload.get("ceiling_height_m")
    try:
        h = float(ceiling_height)
        if h <= 0 or h > 30:
            raise ContractViolation(
                f"ceiling_height_m must be > 0 and <= 30, got {h}"
            )
    except (TypeError, ValueError):
        raise ContractViolation(
            f"ceiling_height_m must be a number, got {ceiling_height!r}"
        )

    return payload


__all__ = [
    "CONTRACT_VERSION",
    "CeilingType",
    "ConfidenceLevel",
    "DetectorType",
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
    "validate_room_input",
]
