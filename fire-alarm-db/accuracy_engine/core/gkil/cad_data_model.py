from dataclasses import dataclass, field
from typing import List, Dict, Tuple, Optional, Any
from enum import Enum


class CADEntityType(Enum):
    WALL = "wall"
    DOOR = "door"
    DETECTOR = "detector"
    PANEL = "panel"
    CABLE_PATH = "cable_path"
    ZONE = "zone"


@dataclass
class CADVertex:
    vertex_id: str
    x: float
    y: float
    z: float
    entity_type: CADEntityType
    properties: Dict[str, Any] = field(default_factory=dict)
    spectral_metadata: Dict[str, float] = field(default_factory=dict)


@dataclass
class CADEdge:
    edge_id: str
    from_vertex: str
    to_vertex: str
    edge_type: str
    length: float
    properties: Dict[str, Any] = field(default_factory=dict)


@dataclass
class CADConstraint:
    constraint_id: str
    constraint_type: str
    source_rule: str
    NFPA_reference: str
    severity: str
    target_entities: List[str]
    constraint_function: str
    parameters: Dict[str, Any] = field(default_factory=dict)


@dataclass
class CADZone:
    zone_id: str
    zone_name: str
    vertices: List[str]
    properties: Dict[str, Any] = field(default_factory=dict)
    spectral_risk: float = 0.0
    stability_index: float = 0.0


@dataclass
class CADGraph:
    graph_id: str
    project_name: str
    vertices: List[CADVertex]
    edges: List[CADEdge]
    constraints: List[CADConstraint]
    zones: List[CADZone]
    metadata: Dict[str, Any] = field(default_factory=dict)