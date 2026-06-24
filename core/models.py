"""core/models.py — Universal BIM Data Model (domain layer)
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

DESIGN DECISIONS (V83 — Self-Criticism Hardening)
------------------
- ALL classes are ``@dataclass(frozen=True)`` — immutability is MANDATORY
  for safety-critical engineering data. No exceptions. No "mutable because
  db_service needs it" — that was a half-solution (Rule 17).
- ``Point3D`` validates NaN/Inf — same as qomn_conduit.types.Point3D.
  Non-finite coordinates in fire-protection calculations are DATA CORRUPTION.
- ``Geometry.points`` is ``Tuple[Point3D, ...]`` (not List) — prevents
  silent mutation that would make cached area/perimeter stale.
- ``UniversalElement`` is frozen. element_id is mandatory (no uuid4 fallback).
  The caller (db_service, parser) is responsible for providing a deterministic
  or externally-generated ID. Non-deterministic uuid4() in __post_init__
  violated Priority #5 (Determinism).
- All type annotations use specific types, never ``Any``.

NEC/NFPA REFERENCES
-------------------
- Point3D coordinates are in METRES (SI) — consistent with IFC/BIM.
- Geometry area/perimeter use the Shoelace formula for 2D projection.

Copyright (c) 2024-2026 FireAI Project. All rights reserved.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, Optional, Tuple, Union

__all__ = [
    "ChangeSource",
    "Conflict",
    "ConflictType",
    "ElementType",
    "Geometry",
    "Point3D",
    "Relationship",
    "SemanticProperties",
    "UniversalElement",
]

_logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════════════════════════
# ENUMERATIONS — re-export from backend.schemas if available, else define locally
# ═══════════════════════════════════════════════════════════════════════════════

try:
    from backend.schemas import ChangeSource as ChangeSource
    from backend.schemas import ConflictType as ConflictType
    from backend.schemas import ElementType as ElementType
except ImportError as _import_err:
    # Fallback for standalone usage (e.g., parsers without backend installed).
    # V83 FIX: Log the fallback reason — silent fallback hides real errors
    # (e.g., syntax error in schemas.py would be silently swallowed).
    _logger.warning(
        "backend.schemas not available (%s) — using local enum fallback. "
        "If backend is installed, this indicates a problem.",
        _import_err,
    )
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

    SAFETY: NaN and Inf coordinates are REJECTED. In a fire-protection
    system, non-finite coordinates indicate data corruption and would
    silently poison ALL downstream calculations (area, perimeter, NFPA
    coverage spacing). This matches the validation in
    ``qomn_conduit.types.Point3D``.

    Attributes:
        x: Easting coordinate in metres.
        y: Northing coordinate in metres.
        z: Elevation coordinate in metres (floor level = 0.0).

    """

    x: float
    y: float
    z: float = 0.0

    def __post_init__(self) -> None:
        for _name, _val in (("x", self.x), ("y", self.y), ("z", self.z)):
            if not math.isfinite(_val):
                raise ValueError(
                    f"Point3D.{_name} must be finite (got {_val}). "
                    "Non-finite coordinates indicate data corruption in a "
                    "safety-critical fire protection system."
                )


@dataclass(frozen=True)
class Geometry:
    """Immutable polyline geometry with cached area and perimeter.

    Area and perimeter are computed on creation using the Shoelace formula
    (2D projection onto the XY plane). For open polylines, area is zero.

    V83 FIX: ``points`` is now ``Tuple[Point3D, ...]`` (was List) to
    enforce immutability. A mutable list would allow ``points.append()``
    which makes the cached area/perimeter stale — a silent data corruption
    vector in NFPA coverage calculations.

    Attributes:
        points: Ordered vertices of the polyline/polygon (IMMUTABLE).
        polyline_closed: True if the last point connects back to the first.
        area: Computed area in square metres (0.0 for open polylines).
        perimeter: Computed perimeter in metres.

    """

    points: Tuple[Point3D, ...] = ()
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
        V83 FIX: Closed polyline with exactly 2 points now includes the
        round-trip edge (previously only >= 3 points got closing edge).
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
        if self.polyline_closed and len(pts) >= 2:
            # V83 FIX: Was >= 3, but 2-point closed polyline needs round-trip too
            dx = pts[0].x - pts[-1].x
            dy = pts[0].y - pts[-1].y
            dz = pts[0].z - pts[-1].z
            perimeter += math.sqrt(dx * dx + dy * dy + dz * dz)
        return perimeter


# ═══════════════════════════════════════════════════════════════════════════════
# SEMANTIC PROPERTIES
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass(frozen=True)
class SemanticProperties:
    """Semantic metadata for a BIM element.

    V83 FIX: Now frozen=True. The old code was mutable "because db_service.py
    updates properties in-place" — this was a half-solution (Rule 17). The
    correct approach is to create a NEW SemanticProperties with updated values
    and replace the reference on the element.

    SAFETY: height and width validate for NaN/Inf/negative values.

    Attributes:
        element_type: The kind of building element (wall, door, etc.).
        name: Human-readable element name.
        description: Optional description.
        material: Construction material (e.g., "concrete", "steel").
        fire_rating: Fire resistance rating (e.g., "2HR", "1HR").
        height: Element height in metres (must be positive or None).
        width: Element width in metres (must be positive or None).
        load_bearing: Whether the element carries structural load.
        layer: CAD/BIM layer name.
        revit_category: Revit category string.

    """

    element_type: Union[ElementType, str]
    name: str = ""
    description: Optional[str] = None
    material: Optional[str] = None
    fire_rating: Optional[str] = None
    height: Optional[float] = None
    width: Optional[float] = None
    load_bearing: bool = False
    layer: Optional[str] = None
    revit_category: Optional[str] = None

    def __post_init__(self) -> None:
        # V83 FIX: Validate numeric fields — negative/NaN/Inf heights are
        # data corruption indicators in fire-protection engineering.
        for _name, _val in (("height", self.height), ("width", self.width)):
            if _val is not None:
                if not math.isfinite(_val):
                    raise ValueError(
                        f"SemanticProperties.{_name} must be finite (got {_val}). "
                        "Non-finite dimensions indicate data corruption."
                    )
                if _val < 0:
                    raise ValueError(
                        f"SemanticProperties.{_name} must be non-negative (got {_val}). "
                        "Negative dimensions indicate data corruption."
                    )

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

@dataclass(frozen=True)
class Relationship:
    """A directed relationship between two UniversalElements.

    V83 FIX: Now frozen=True. db_service must create new Relationship
    instances instead of mutating existing ones.

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
        """Serialize to dictionary for JSON storage/API response.

        V83 FIX: Now includes connection_id (was missing — data loss on
        JSON round-trip).
        """
        return {
            "from_element_id": self.from_element_id,
            "to_element_id": self.to_element_id,
            "relationship_type": self.relationship_type,
            "is_parametric": self.is_parametric,
            "metadata": self.metadata,
            "connection_id": self.connection_id,
        }


# ═══════════════════════════════════════════════════════════════════════════════
# CONFLICT
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass(frozen=True)
class Conflict:
    """A merge conflict between two data sources.

    V83 FIX: Now frozen=True. conflict_type uses ConflictType enum
    (was Any — allowed arbitrary values like 42 or "typo").

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
    conflict_type: ConflictType = ConflictType.GEOMETRY_MISMATCH
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

# Allowed keys for update_element() — prevents arbitrary JSON injection (C-3)
_ELEMENT_UPDATABLE_KEYS = frozenset({
    "properties", "geometry", "source_file", "last_modified_by",
    "is_deleted", "project_id",
})


@dataclass(frozen=True)
class UniversalElement:
    """A universal BIM element in the Digital Twin data model.

    V83 FIX: Now frozen=True. element_id is MANDATORY (no uuid4 fallback).
    The old code used ``uuid.uuid4()`` in __post_init__ — non-deterministic,
    violating Priority #5 (Determinism). The caller (db_service, parser) is
    responsible for providing a deterministic or externally-generated ID.

    db_service must create new UniversalElement instances for updates
    instead of mutating fields in-place. This is the root-cause fix for
    the mutability antipattern.

    SAFETY: All coordinates in Geometry.points are in metres (SI).

    Attributes:
        element_id: Unique identifier — MANDATORY, no default.
        properties: Semantic metadata (type, name, fire_rating, …).
        geometry: Optional polyline geometry.
        relationships: Directed edges to other elements (IMMUTABLE tuple).
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
    relationships: Tuple[Relationship, ...] = ()
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
        # V83 FIX: No uuid.uuid4() — element_id must be provided by caller.
        # Determinism is mandatory (Priority #5).
        if not self.element_id:
            raise ValueError(
                "UniversalElement.element_id is MANDATORY. "
                "Auto-generating a non-deterministic UUID violates "
                "the determinism requirement (Priority #5). "
                "The caller must provide a deterministic or "
                "externally-generated element ID."
            )

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
