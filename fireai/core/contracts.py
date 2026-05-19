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
]
