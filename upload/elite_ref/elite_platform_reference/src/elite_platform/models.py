"""Canonical engineering models for the elite platform reference."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple


Point2D = Tuple[float, float]


@dataclass(frozen=True)
class RoomGeometry:
    room_id: str
    name: str
    floor_id: str
    polygon: List[Point2D]
    ceiling_height_m: float
    use_type: str = "general"


@dataclass(frozen=True)
class DetectorPlacement:
    detector_id: str
    room_id: str
    x: float
    y: float
    z: float
    detector_type: str
    coverage_radius_m: float


@dataclass(frozen=True)
class RuleDecision:
    rule_id: str
    rule_version: str
    outcome: str
    rationale: str
    inputs_hash: str


@dataclass(frozen=True)
class RoomAnalysisRecord:
    room: RoomGeometry
    detectors: List[DetectorPlacement]
    rule_decisions: List[RuleDecision] = field(default_factory=list)
    metadata: Dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class BuildingSnapshot:
    snapshot_id: str
    revision_id: str
    created_at: str
    source_system: str
    room_records: List[RoomAnalysisRecord]
    source_model_id: Optional[str] = None


@dataclass(frozen=True)
class DriftRecord:
    room_id: str
    drift_type: str
    details: Dict[str, object]
