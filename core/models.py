"""
core/models.py — Universal BIM Data Model (domain layer)
=========================================================

Frozen dataclass models for the Universal Data Model (UDM). These classes
represent the *domain* objects that flow through parsers, the database
service, and the Digital Twin API.

WHY THIS FILE EXISTS
--------------------
Seven files across the codebase import from ``core.models``:
  - backend/db_service.py
  - backend/app.py
  - parsers/dwg_parser.py
  - parsers/rvt_parser.py
  - fireai/core/ci_benchmark.py

Previously, ``core/models.py`` did not exist, causing ``ImportError`` at
runtime.  The parsers worked around this with ``sys.path`` manipulation,
which is fragile and a safety risk.  This file provides the single source
of truth for these domain types.

DESIGN DECISIONS
----------------
- All classes are ``@dataclass(frozen=True)`` — immutability is mandatory
  for safety-critical engineering data.
- ``Point3D`` here is the *canonical* definition for the UDM domain.
  The ``qomn_conduit.types.Point3D`` and ``qomn_fire.core.types.Point3D``
  are separate because those modules have stricter validation (NaN/Inf
  rejection) and additional methods (distance_to, manhattan_to) that
  belong to their specific domains.
- Enums (ElementType, ChangeSource, ConflictType) are re-exported from
  ``backend.schemas`` to avoid duplication.  If ``backend.schemas`` is
  unavailable (e.g., standalone parser usage), fallback enums are defined.

NEC/NFPA REFERENCES
-------------------
- Point3D coordinates are in METRES (SI) — consistent with IFC/BIM.
- Geometry area/perimeter use the Shoelace formula for 2D projection.

Copyright (c) 2024-2026 FireAI Project. All rights reserved.
"""

from __future__ import annotations

import math
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


# ═══════════════════════════════════════════════════════════════════════════════
# ENUMERATIONS — re-export from backend.schemas if available, else define locally
# ═══════════════════════════════════════════════════════════════════════════════

try:
    from backend.schemas import ChangeSource as ChangeSource  # type: ignore[no-redef]
    from backend.schemas import ConflictType as ConflictType  # type: ignore[no-redef]
    from backend.schemas import ElementType as ElementType  # type: ignore[no-redef]
except ImportError:
    # Fallback for standalone usage (e.g., parsers without backend installed)
    from enum import Enum

    class ElementType(str, Enum):  # type: ignore[no-redef]
        WALL = "wall"
        DOOR = "door"
        WINDOW = "window"
        ROOM = "room"
        EQUIPMENT = "equipment"
        MECHANICAL = "mechanical"
        ELECTRICAL = "electrical"
        UNKNOWN = "unknown"

    class ChangeSource(str, Enum):  # type: ignore[no-redef]
        AUTOCAD = "autocad"
        REVIT = "revit"
        MANUAL = "manual"
        SYSTEM = "system"

    class ConflictType(str, Enum):  # type: ignore[no-redef]
        GEOMETRY_MISMATCH = "geometry_mismatch"
        PROPERTY_CONFLICT = "property_conflict"
        DELETION_CONFLICT = "deletion_conflict"
        TIMING_CONFLICT = "timing_conflict"


# ═══════════════════════════════════════════════════════════════════════════════
# GEOMETRY
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass(frozen=True)
class Point3D:
    """Immutable 3D point in the building coordinate system (SI metres).

    This is the UDM-domain Point3D. Other modules (qomn_conduit, qomn_fire)
    define their own Point3D with domain-specific validation and methods.
    """
    x: float
    y: float
    z: float = 0.0


@dataclass(frozen=True)
class Geometry:
    """Immutable polyline geometry with cached area and perimeter.

    Area and perimeter are computed on creation using the Shoelace formula
    (2D projection onto the XY plane). For open polylines, area is zero.

    Attributes:
        points: Ordered vertices of the polyline/polygon.
        polyline_closed: True if the last point connects back to the first.
        area: Computed area in square metres (0.0 for open polylines).
        perimeter: Computed perimeter in metres.
    """
    points: List[Point3D] = field(default_factory=list)
    polyline_closed: bool = False
    area: float = 0.0
    perimeter: float = 0.0

    def __post_init__(self) -> None:
        # Frozen dataclass — use object.__setattr__ to set computed fields
        if len(self.points) >= 3 and self.polyline_closed:
            object.__setattr__(self, 'area', self.calculate_area())
        if len(self.points) >= 2:
            object.__setattr__(self, 'perimeter', self.calculate_perimeter())

    def calculate_area(self) -> float:
        """Shoelace formula for polygon area (2D XY projection).

        Returns 0.0 for open polylines or fewer than 3 points.
        Reference: https://en.wikipedia.org/wiki/Shoelace_formula
        """
        pts = self.points
        if len(pts) < 3 or not self.polyline_closed:
            return 0.0
        n = len(pts)
        area = 0.0
        for i in range(n):
            j = (i + 1) % n
            area += pts[i].x * pts[j].y
            area -= pts[j].x * pts[i].y
        return abs(area) / 2.0

    def calculate_perimeter(self) -> float:
        """Sum of edge lengths (Euclidean distance between consecutive points).

        For closed polylines, includes the closing edge.
        """
        pts = self.points
        if len(pts) < 2:
            return 0.0
        perimeter = 0.0
        for i in range(len(pts) - 1):
            dx = pts[i + 1].x - pts[i].x
            dy = pts[i + 1].y - pts[i].y
            dz = pts[i + 1].z - pts[i].z
            perimeter += math.sqrt(dx * dx + dy * dy + dz * dz)
        if self.polyline_closed and len(pts) >= 3:
            dx = pts[0].x - pts[-1].x
            dy = pts[0].y - pts[-1].y
            dz = pts[0].z - pts[-1].z
            perimeter += math.sqrt(dx * dx + dy * dy + dz * dz)
        return perimeter


# ═══════════════════════════════════════════════════════════════════════════════
# SEMANTIC PROPERTIES
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class SemanticProperties:
    """Semantic metadata for a BIM element.

    Mutable because db_service.py updates properties in-place during
    merge operations. The element itself remains the authority on
    whether the data is consistent.

    Attributes:
        element_type: The kind of building element (wall, door, etc.).
        name: Human-readable element name.
        description: Optional description.
        material: Construction material (e.g., "concrete", "steel").
        fire_rating: Fire resistance rating (e.g., "2HR", "1HR").
        height: Element height in metres.
        width: Element width in metres.
        load_bearing: Whether the element carries structural load.
        layer: CAD/BIM layer name.
        revit_category: Revit category string.
    """
    element_type: Any  # ElementType enum or string
    name: str = ""
    description: Optional[str] = None
    material: Optional[str] = None
    fire_rating: Optional[str] = None
    height: Optional[float] = None
    width: Optional[float] = None
    load_bearing: bool = False
    layer: Optional[str] = None
    revit_category: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary for JSON storage/API response."""
        return {
            "element_type": self.element_type.value if hasattr(self.element_type, 'value') else str(self.element_type),
            "name": self.name,
            "description": self.description,
            "material": self.material,
            "fire_rating": self.fire_rating,
            "height": self.height,
            "width": self.width,
            "load_bearing": self.load_bearing,
            "layer": self.layer,
            "revit_category": self.revit_category,
        }


# ═══════════════════════════════════════════════════════════════════════════════
# RELATIONSHIP
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class Relationship:
    """A directed relationship between two UniversalElements.

    Mutable because db_service.py appends relationships to element lists.

    Attributes:
        from_element_id: Source element UUID.
        to_element_id: Target element UUID.
        relationship_type: Kind of relationship (e.g., "adjacent", "contains").
        is_parametric: Whether the relationship is parametrically driven.
        metadata: Optional arbitrary metadata dictionary.
        connection_id: Optional UUID for this relationship (set by db_service).
    """
    from_element_id: str = ""
    to_element_id: str = ""
    relationship_type: str = ""
    is_parametric: bool = False
    metadata: Optional[Dict[str, Any]] = None
    connection_id: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary for JSON storage/API response."""
        return {
            "from_element_id": self.from_element_id,
            "to_element_id": self.to_element_id,
            "relationship_type": self.relationship_type,
            "is_parametric": self.is_parametric,
            "metadata": self.metadata,
        }


# ═══════════════════════════════════════════════════════════════════════════════
# CONFLICT
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class Conflict:
    """A merge conflict between two data sources.

    Attributes:
        conflict_id: Unique identifier for this conflict.
        element_id: The element involved in the conflict.
        conflict_type: Kind of conflict (geometry mismatch, property conflict, etc.).
        source_a: First data source (e.g., "autocad").
        source_b: Second data source (e.g., "revit").
        change_a: Proposed change from source A.
        change_b: Proposed change from source B.
        resolution: How the conflict was resolved (None if unresolved).
        resolved: Whether the conflict has been resolved.
        timestamp: When the conflict was detected.
    """
    conflict_id: str = ""
    element_id: str = ""
    conflict_type: Any = ConflictType.GEOMETRY_MISMATCH  # ConflictType enum
    source_a: Optional[str] = None
    source_b: Optional[str] = None
    change_a: Optional[Dict[str, Any]] = None
    change_b: Optional[Dict[str, Any]] = None
    resolution: Optional[Dict[str, Any]] = None
    resolved: bool = False
    timestamp: Optional[datetime] = None


# ═══════════════════════════════════════════════════════════════════════════════
# UNIVERSAL ELEMENT
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class UniversalElement:
    """A universal BIM element in the Digital Twin data model.

    This is the core domain object that parsers (DWG, RVT) produce and
    that the UniversalDataModel stores. It is mutable because the database
    service updates relationships and properties in-place.

    SAFETY: All coordinates in Geometry.points are in metres (SI).

    Attributes:
        element_id: Unique identifier (UUID).
        properties: Semantic metadata (type, name, fire_rating, …).
        geometry: Optional polyline geometry.
        relationships: Directed edges to other elements.
        source_file: Origin file path (e.g., "floor_plan.dwg").
        last_modified_by: Who/what last changed this element.
        autocad_handle: AutoCAD entity handle (for DWG round-tripping).
        revit_element_id: Revit element ID (for RVT round-tripping).
        created_timestamp: When the element was first created.
        last_modified_timestamp: When the element was last modified.
        version: Incremented on each update (optimistic concurrency).
        is_deleted: Soft-delete flag.
        project_id: Optional project association.
    """
    element_id: str = ""
    properties: Optional[SemanticProperties] = None
    geometry: Optional[Geometry] = None
    relationships: List[Relationship] = field(default_factory=list)
    source_file: Optional[str] = None
    last_modified_by: Optional[str] = None
    autocad_handle: Optional[str] = None
    revit_element_id: Optional[int] = None
    created_timestamp: Optional[datetime] = None
    last_modified_timestamp: Optional[datetime] = None
    version: int = 0
    is_deleted: bool = False
    project_id: Optional[str] = None

    def __post_init__(self) -> None:
        if not self.element_id:
            object.__setattr__(self, 'element_id', str(uuid.uuid4()))
        if self.created_timestamp is None:
            object.__setattr__(self, 'created_timestamp', datetime.now(timezone.utc))
        if self.last_modified_timestamp is None:
            object.__setattr__(self, 'last_modified_timestamp', datetime.now(timezone.utc))

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary for JSON storage/API response."""
        result: Dict[str, Any] = {
            "element_id": self.element_id,
            "source_file": self.source_file,
            "last_modified_by": self.last_modified_by,
            "autocad_handle": self.autocad_handle,
            "revit_element_id": self.revit_element_id,
            "created_timestamp": self.created_timestamp.isoformat() if self.created_timestamp else None,
            "last_modified_timestamp": self.last_modified_timestamp.isoformat() if self.last_modified_timestamp else None,
            "version": self.version,
            "is_deleted": self.is_deleted,
            "project_id": self.project_id,
        }
        if self.properties:
            result["properties"] = self.properties.to_dict()
        if self.geometry:
            result["geometry"] = {
                "points": [{"x": p.x, "y": p.y, "z": p.z} for p in self.geometry.points],
                "polyline_closed": self.geometry.polyline_closed,
                "area": self.geometry.area,
                "perimeter": self.geometry.perimeter,
            }
        result["relationships"] = [r.to_dict() for r in self.relationships]
        return result
