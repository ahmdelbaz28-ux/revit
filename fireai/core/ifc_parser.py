"""fireai.core.ifc_parser — IFC Building Geometry Extraction
=========================================================

Reads building geometry from IFC files (ISO 16739) and produces a
3D occupancy grid for the cable routing engine.

QOMN-FIRE Principles:
  - Every extracted element is tagged with its IFC class and GlobalId
  - No approximations: bounding boxes derived from actual geometry
  - Grid resolution: 100mm (0.1m) per cell — standard MEP routing practice
  - Deterministic: same IFC file → same grid, always

Standards:
  - ISO 16739 — Industry Foundation Classes (IFC)
  - IfcOpenShell 0.8+ — open-source IFC parser

Extracted IFC Entities:
  - IfcWall       → wall obstacles (routing blocked, firestop on penetration)
  - IfcSlab       → floor/roof slabs (vertical routing boundary)
  - IfcBeam       → structural beams (routing blocked)
  - IfcSpace      → navigable spaces (cable routing target)
  - IfcDoor       → door openings (potential cable pathway)
  - IfcWindow     → window openings (NOT a cable pathway)

SAFETY CRITICAL:
  - NaN/Inf coordinates are REJECTED
  - Empty geometries produce warnings, not crashes
  - Missing IfcOpenShell falls back to abstract grid builder
"""

from __future__ import annotations

import hashlib
import logging
import math
import os
from dataclasses import dataclass
from enum import Enum
from typing import List, Optional, Tuple

log = logging.getLogger(__name__)

# ─── Lazy IfcOpenShell import ──────────────────────────────────────────────

_ifcopenshell: object = None  # V131 FIX: Typed as object to satisfy mypy (was Module|bool)


def _get_ifcopenshell():
    """Lazy-load IfcOpenShell, returning None if unavailable."""
    global _ifcopenshell
    if _ifcopenshell is None:
        try:
            import ifcopenshell as _ifs  # type: ignore[import-untyped]

            _ifcopenshell = _ifs
        except ImportError:
            _ifcopenshell = None  # V131 FIX: Use None instead of False to avoid type mismatch
            return None
    return _ifcopenshell


# ─── Enums ──────────────────────────────────────────────────────────────────


class IfcElementType(Enum):
    """IFC element types relevant to cable routing."""

    WALL = "IfcWall"
    SLAB = "IfcSlab"
    BEAM = "IfcBeam"
    SPACE = "IfcSpace"
    DOOR = "IfcDoor"
    WINDOW = "IfcWindow"
    COLUMN = "IfcColumn"
    CURTAIN_WALL = "IfcCurtainWall"
    UNKNOWN = "Unknown"


class CellState(Enum):
    """State of a grid cell for the routing engine."""

    FREE = 0  # Navigable — cable can pass
    BLOCKED = 1  # Solid obstacle — cable cannot pass
    DOOR_OPENING = 2  # Door opening — cable can pass horizontally
    SHAFT = 3  # Vertical shaft — cable can pass vertically
    ELECTRICAL = 4  # Electrical zone — 300mm separation required per project spec


# ─── Frozen Dataclasses ─────────────────────────────────────────────────────


@dataclass(frozen=True)
class BoundingBox3D:
    """Axis-aligned 3D bounding box.

    All coordinates in meters. The box is defined by two corner points
    (min_x, min_y, min_z) and (max_x, max_y, max_z).

    Attributes:
        element_id: IFC GlobalId or unique identifier.
        element_type: IFC element type (IfcWall, etc.).
        min_x, min_y, min_z: Minimum corner coordinates (meters).
        max_x, max_y, max_z: Maximum corner coordinates (meters).
        is_fire_rated: Whether element has fire rating (affects routing).
        fire_rating_hours: Fire rating in hours (0.0 if not rated).
        ifc_class: Original IFC class name (e.g. 'IfcWallStandardCase').

    """

    element_id: str
    element_type: IfcElementType = IfcElementType.UNKNOWN
    min_x: float = 0.0
    min_y: float = 0.0
    min_z: float = 0.0
    max_x: float = 0.0
    max_y: float = 0.0
    max_z: float = 0.0
    is_fire_rated: bool = False
    fire_rating_hours: float = 0.0
    ifc_class: str = ""

    @property
    def width_x(self) -> float:
        """Bounding box width in X direction (meters)."""
        return self.max_x - self.min_x

    @property
    def depth_y(self) -> float:
        """Bounding box depth in Y direction (meters)."""
        return self.max_y - self.min_y

    @property
    def height_z(self) -> float:
        """Bounding box height in Z direction (meters)."""
        return self.max_z - self.min_z

    @property
    def center(self) -> Tuple[float, float, float]:
        """Center point of the bounding box."""
        return (
            (self.min_x + self.max_x) / 2.0,
            (self.min_y + self.max_y) / 2.0,
            (self.min_z + self.max_z) / 2.0,
        )

    def contains_point(self, x: float, y: float, z: float) -> bool:
        """Check if a 3D point is inside this bounding box."""
        return self.min_x <= x <= self.max_x and self.min_y <= y <= self.max_y and self.min_z <= z <= self.max_z

    def overlaps(self, other: BoundingBox3D) -> bool:
        """Check if this bounding box overlaps another (AABB intersection)."""
        return (
            self.min_x <= other.max_x
            and self.max_x >= other.min_x
            and self.min_y <= other.max_y
            and self.max_y >= other.min_y
            and self.min_z <= other.max_z
            and self.max_z >= other.min_z
        )


@dataclass(frozen=True)
class SpaceInfo:
    """Information about a navigable IfcSpace.

    Attributes:
        space_id: IFC GlobalId.
        space_name: Space name (e.g. 'Office 101').
        space_number: Space number (e.g. '101').
        bounding_box: 3D bounding box of the space.
        floor_elevation: Floor elevation in meters.
        ceiling_elevation: Ceiling elevation in meters.
        is_fire_zone: Whether this space is a fire zone.

    """

    space_id: str
    space_name: str = ""
    space_number: str = ""
    bounding_box: Optional[BoundingBox3D] = None
    floor_elevation: float = 0.0
    ceiling_elevation: float = 3.0
    is_fire_zone: bool = False


@dataclass(frozen=True)
class BuildingModel:
    """Complete building model extracted from IFC.

    Contains all geometry needed for cable routing:
    - Obstacles (walls, slabs, beams, columns)
    - Spaces (navigable areas)
    - Grid (3D occupancy grid at 100mm resolution)

    Attributes:
        building_name: Building name from IFC.
        elements: List of all extracted bounding boxes.
        spaces: List of navigable spaces.
        grid_origin: (x, y, z) of grid origin (minimum coordinates).
        grid_size: (nx, ny, nz) grid dimensions.
        grid_resolution: Grid cell size in meters (0.1 = 100mm).
        grid_data: Flat 3D occupancy grid (CellState values).
        computation_hash: SHA-256 hash for deterministic verification.

    """

    building_name: str = ""
    elements: Tuple[BoundingBox3D, ...] = ()
    spaces: Tuple[SpaceInfo, ...] = ()
    grid_origin: Tuple[float, float, float] = (0.0, 0.0, 0.0)
    grid_size: Tuple[int, int, int] = (0, 0, 0)
    grid_resolution: float = 0.1  # 100mm
    grid_data: bytes = b""
    computation_hash: str = ""

    def __post_init__(self):
        if self.computation_hash == "" and self.grid_data:
            # V64 FIX: Hash all data together, not concatenate two hashes
            # then truncate. Previous code did:
            #   h = sha256(raw).hex() + sha256(grid_data).hex()  # 128 chars
            #   hash = h[:32]  # Only keeps first 32 chars of sha256(raw)!
            # The grid_data hash was COMPLETELY LOST — two models with
            # different grids but same metadata produced the same hash.
            hasher = hashlib.sha256()
            hasher.update(
                f"{self.grid_origin}|{self.grid_size}|"
                f"{self.grid_resolution}|{len(self.elements)}|"
                f"{len(self.spaces)}".encode()
            )
            hasher.update(self.grid_data)
            object.__setattr__(self, "computation_hash", hasher.hexdigest()[:32])


# ─── IFC Parser ─────────────────────────────────────────────────────────────

# IFC class → IfcElementType mapping
_IFC_CLASS_MAP = {
    "IfcWall": IfcElementType.WALL,
    "IfcWallStandardCase": IfcElementType.WALL,
    "IfcElementedCase": IfcElementType.WALL,
    "IfcSlab": IfcElementType.SLAB,
    "IfcBeam": IfcElementType.BEAM,
    "IfcSpace": IfcElementType.SPACE,
    "IfcDoor": IfcElementType.DOOR,
    "IfcWindow": IfcElementType.WINDOW,
    "IfcColumn": IfcElementType.COLUMN,
    "IfcCurtainWall": IfcElementType.CURTAIN_WALL,
}

# Elements that block cable routing
_BLOCKING_TYPES = {
    IfcElementType.WALL,
    IfcElementType.SLAB,
    IfcElementType.BEAM,
    IfcElementType.COLUMN,
    IfcElementType.CURTAIN_WALL,
    IfcElementType.WINDOW,  # V106 FIX: Windows are NOT cable pathways — glass cannot support cable routing
}

# Elements that allow cable passage
_OPENING_TYPES = {
    IfcElementType.DOOR,
}


def _classify_ifc_element(ifc_class: str) -> IfcElementType:
    """Map IFC class name to IfcElementType.

    Args:
        ifc_class: IFC class name (e.g. 'IfcWallStandardCase').

    Returns:
        IfcElementType enum value.

    """
    return _IFC_CLASS_MAP.get(ifc_class, IfcElementType.UNKNOWN)


def _extract_fire_rating(
    element,
    element_type: Optional[IfcElementType] = None,
) -> Tuple[bool, float]:
    """Extract fire rating from IFC element properties.

    Checks Pset_FireRatingCommon and similar property sets.

    V96 FIX: For BLOCKING element types (walls, slabs, beams, etc.),
    extraction failure now defaults to (True, 2.0) — assume fire-rated
    until proven otherwise (fail-safe). Non-blocking types retain the
    (False, 0.0) default since fire rating is less critical for them.

    Rationale: A wall that IS fire-rated but whose extraction failed would
    be treated as non-rated, meaning:
    - Cable router won't flag penetrations as needing firestop
    - Occupancy separation assumptions are wrong
    - Fire compartment boundaries are silently dropped

    Args:
        element: IfcOpenShell element object.
        element_type: Optional IfcElementType for fail-safe defaulting.

    Returns:
        (is_fire_rated, fire_rating_hours) tuple.

    """
    # V96 FIX: Fail-safe defaults depend on element type.
    # Blocking elements default to fire-rated (True, 2.0h) on failure.
    _BLOCKING_DEFAULT = (True, 2.0)
    _NON_BLOCKING_DEFAULT = (False, 0.0)

    is_blocking = element_type is not None and element_type in _BLOCKING_TYPES
    is_rated, rating_hours = _BLOCKING_DEFAULT if is_blocking else _NON_BLOCKING_DEFAULT

    try:
        for rel in element.IsDefinedBy:
            if hasattr(rel, "RelatingPropertyDefinition"):
                pset = rel.RelatingPropertyDefinition
                if hasattr(pset, "HasProperties"):
                    for prop in pset.HasProperties:
                        name = getattr(prop, "Name", "").lower()
                        if "fire" in name and "rating" in name:
                            val = getattr(prop, "NominalValue", None)
                            if val is not None:
                                val_str = str(getattr(val, "wrappedValue", val))
                                try:
                                    rating_hours = float(val_str)
                                    is_rated = True
                                except (ValueError, TypeError):
                                    pass
    except Exception as exc:
        # V96 FIX: Extraction failure defaults to fail-safe per element type.
        # Blocking elements default to fire-rated (True, 2.0h).
        # Non-blocking elements default to not-rated (False, 0.0h).
        is_rated, rating_hours = _BLOCKING_DEFAULT if is_blocking else _NON_BLOCKING_DEFAULT
        log.warning(
            "V96: _extract_fire_rating() failed for element %s (type=%s) — defaulting to %s (fail-safe). Error: %s",
            getattr(element, "GlobalId", "?"),
            element_type.value if element_type else "UNKNOWN",
            f"fire-rated {rating_hours}h" if is_rated else "not-rated",
            exc,
        )
    return is_rated, rating_hours


def _compute_world_placement(element) -> Optional[Tuple[float, float, float]]:
    """Recursively resolve nested IfcLocalPlacement chain to world coordinates.

    IFC supports nested placements where an IfcLocalPlacement references a
    parent via PlacementRelTo. The world position is the sum of all offsets
    in the chain. Previously only the first-level RelativePlacement was read,
    causing elements with nested placements (e.g. elements placed relative
    to a storey, which is placed relative to a building) to have incorrect
    coordinates — they appeared at their local offset instead of their true
    world position.

    Args:
        element: IfcOpenShell element with ObjectPlacement attribute.

    Returns:
        (x, y, z) world coordinates, or None if placement cannot be resolved.

    """
    try:
        placement = element.ObjectPlacement
        if placement is None:
            return None

        # Accumulate offsets walking UP the PlacementRelTo chain.
        # Parent placements are added first (outermost), then local offsets.
        offsets: List[Tuple[float, float, float]] = []

        current = placement
        visited = set()  # Guard against circular references
        while current is not None:
            placement_id = id(current)
            if placement_id in visited:
                log.warning(
                    "Circular PlacementRelTo chain detected for element %s — stopping traversal.",
                    getattr(element, "GlobalId", "?"),
                )
                break
            visited.add(placement_id)

            if hasattr(current, "RelativePlacement") and current.RelativePlacement is not None:
                loc = current.RelativePlacement
                if hasattr(loc, "Location") and loc.Location is not None:
                    coords = loc.Location.Coordinates
                    ox = float(coords[0]) if len(coords) > 0 else 0.0
                    oy = float(coords[1]) if len(coords) > 1 else 0.0
                    oz = float(coords[2]) if len(coords) > 2 else 0.0
                    offsets.append((ox, oy, oz))
                else:
                    offsets.append((0.0, 0.0, 0.0))
            else:
                offsets.append((0.0, 0.0, 0.0))

            # Walk to parent placement
            if hasattr(current, "PlacementRelTo") and current.PlacementRelTo is not None:
                current = current.PlacementRelTo
            else:
                break

        # Sum all offsets (order doesn't matter for pure translation)
        wx = sum(o[0] for o in offsets)
        wy = sum(o[1] for o in offsets)
        wz = sum(o[2] for o in offsets)

        # Validate coordinates
        for val in [wx, wy, wz]:
            if not math.isfinite(val):
                return None

        return (wx, wy, wz)

    except Exception as exc:
        log.critical(
            "V93 SAFETY: World placement computation failed for %s — "
            "DROPPING element (returning None). Elements with unknown "
            "position are MORE DANGEROUS than missing elements. Error: %s",
            getattr(element, "GlobalId", "?"),
            exc,
        )
        return None


def _extract_extrusion_direction(item) -> Optional[Tuple[float, float, float]]:
    """Extract the extrusion direction from an IfcExtrudedAreaSolid.

    IfcExtrudedAreaSolid.ExtrudedDirection is a unit IfcDirection vector
    indicating the direction of extrusion. If the direction cannot be
    extracted, returns None (caller should default to Z-axis with warning).

    Args:
        item: IfcExtrudedAreaSolid entity.

    Returns:
        (dx, dy, dz) direction vector (not necessarily normalized), or None.

    """
    try:
        if hasattr(item, "ExtrudedDirection") and item.ExtrudedDirection is not None:
            direction = item.ExtrudedDirection
            if hasattr(direction, "DirectionRatios"):
                ratios = list(direction.DirectionRatios)
                dx = float(ratios[0]) if len(ratios) > 0 else 0.0
                dy = float(ratios[1]) if len(ratios) > 1 else 0.0
                dz = float(ratios[2]) if len(ratios) > 2 else 0.0
                # Validate
                if math.isfinite(dx) and math.isfinite(dy) and math.isfinite(dz):
                    mag = math.sqrt(dx * dx + dy * dy + dz * dz)
                    if mag > 1e-12:
                        return (dx, dy, dz)
            # DirectionRatios not available
            return None
        return None
    except Exception as exc:
        log.warning("Failed to extract extrusion direction from IFC element: %s", exc)
        return None


def _is_z_axis_direction(dx: float, dy: float, dz: float, tolerance: float = 1e-6) -> bool:
    """Check if an extrusion direction is approximately the Z-axis (0, 0, ±1).

    Args:
        dx, dy, dz: Direction vector components.
        tolerance: Angular tolerance for off-axis check.

    Returns:
        True if the direction is along the Z-axis.

    """
    # Normalize
    mag = math.sqrt(dx * dx + dy * dy + dz * dz)
    if mag < 1e-12:
        return True  # Degenerate, treat as Z
    nx, ny, _nz = dx / mag, dy / mag, dz / mag
    # Z-axis means nx ≈ 0, ny ≈ 0, |nz| ≈ 1
    return abs(nx) < tolerance and abs(ny) < tolerance


def _get_element_bbox(element, settings=None) -> Optional[BoundingBox3D]:
    """Extract bounding box from an IFC element.

    Uses IfcOpenShell geometry processing to get the actual 3D
    bounding box of the element.

    Args:
        element: IfcOpenShell element object.
        settings: IfcOpenShell geometry settings (optional).

    Returns:
        BoundingBox3D or None if geometry cannot be extracted.

    """
    ifc_class = element.is_a()
    element_type = _classify_ifc_element(ifc_class)
    element_id = element.GlobalId or str(element.id())

    # Resolve world placement (handles nested PlacementRelTo chain)
    world_pos = _compute_world_placement(element)
    if world_pos is None:
        # V93 FIX: Element placement extraction failure MUST return None.
        log.critical(
            "V93 SAFETY: World placement computation returned None for %s — "
            "DROPPING element. Elements with unknown position are MORE "
            "DANGEROUS than missing elements.",
            getattr(element, "GlobalId", "?"),
        )
        return None
    cx, cy, cz = world_pos

    # Try to get representation geometry for bounding box
    min_x = cx
    min_y = cy
    min_z = cz
    max_x = cx
    max_y = cy
    max_z = cz

    try:
        if element.Representation is not None:
            for rep in element.Representation.Representations:
                for item in rep.Items:
                    if item.is_a("IfcExtrudedAreaSolid"):
                        # Get position
                        pos = item.Position
                        if pos and hasattr(pos, "Location"):
                            px = float(pos.Location.Coordinates[0])
                            py = float(pos.Location.Coordinates[1])
                            pz = float(pos.Location.Coordinates[2]) if len(pos.Location.Coordinates) > 2 else 0.0
                        else:
                            px, py, pz = 0.0, 0.0, 0.0

                        # Get extrusion dimensions
                        depth = float(item.Depth) if hasattr(item, "Depth") else 0.0

                        # V106 CRITICAL FIX: Validate all dimension values for NaN/Inf.
                        # Previously, only position coordinates (cx, cy, cz, px, py, pz)
                        # were validated. Dimensions like XDim, YDim, Radius, and Depth
                        # could contain NaN from malformed IFC files, producing a
                        # BoundingBox3D with NaN values that passes all checks because
                        # NaN comparisons always return False — meaning NaN bounding
                        # boxes are NEVER blocked in the occupancy grid, allowing cables
                        # to route through phantom geometry.
                        if not math.isfinite(depth):
                            log.critical(
                                "V106 SAFETY: Non-finite Depth (%s) in IFC element %s — "
                                "DROPPING. NaN/Inf dimensions produce invisible bounding "
                                "boxes that bypass the occupancy grid.",
                                depth,
                                element_id,
                            )
                            return None

                        # ── Extract extrusion direction ──────────────────────
                        # FIX: Previously the extrusion direction was always
                        # assumed to be Z-axis (0,0,1), so depth was only
                        # added to max_z. This is incorrect for horizontally
                        # extruded elements (e.g. beams extruded along X or Y)
                        # which would have their depth added to the wrong axis,
                        # producing a bounding box with zero width in the
                        # extrusion direction — invisible to the cable router.
                        extrusion_dir = _extract_extrusion_direction(item)
                        is_z_extrusion = True  # Default assumption

                        if extrusion_dir is not None:
                            dx, dy, dz = extrusion_dir
                            is_z_extrusion = _is_z_axis_direction(dx, dy, dz)
                            if not is_z_extrusion:
                                log.info(
                                    "Non-Z extrusion direction (%.4f, %.4f, %.4f) "
                                    "for element %s — computing rotated bounding box.",
                                    dx,
                                    dy,
                                    dz,
                                    element_id,
                                )
                        else:
                            # Could not extract direction — default to Z with warning
                            log.warning(
                                "Could not extract ExtrudedDirection for element %s "
                                "— defaulting to Z-axis extrusion. If the element is "
                                "actually extruded along X/Y, its bounding box will "
                                "be incorrect.",
                                element_id,
                            )

                        # Get profile bounds
                        profile = item.SweptArea
                        if hasattr(profile, "Position") and profile.Position is not None:
                            prof_x = (
                                float(profile.Position.Location.Coordinates[0])
                                if hasattr(profile.Position.Location, "Coordinates")
                                else 0.0
                            )
                            prof_y = (
                                float(profile.Position.Location.Coordinates[1])
                                if len(profile.Position.Location.Coordinates) > 1
                                else 0.0
                            )
                            # V106 FIX: Validate profile position
                            for _pval in [prof_x, prof_y]:
                                if not math.isfinite(_pval):
                                    log.critical(
                                        "V106 SAFETY: Non-finite profile position (%s) in element %s — DROPPING.",
                                        _pval,
                                        element_id,
                                    )
                                    return None
                        else:
                            prof_x, prof_y = 0.0, 0.0

                        if hasattr(profile, "XDim") and hasattr(profile, "YDim"):
                            xdim = float(profile.XDim)
                            ydim = float(profile.YDim)
                            # V106 CRITICAL FIX: Validate dimensions
                            if not math.isfinite(xdim) or not math.isfinite(ydim):
                                log.critical(
                                    "V106 SAFETY: Non-finite profile dimensions "
                                    "(XDim=%s, YDim=%s) in element %s — DROPPING. "
                                    "NaN dimensions produce phantom bounding boxes.",
                                    xdim,
                                    ydim,
                                    element_id,
                                )
                                return None
                            if is_z_extrusion:
                                # Standard Z-axis extrusion (most common case)
                                min_x = cx + px + prof_x
                                min_y = cy + py + prof_y
                                min_z = cz + pz
                                max_x = min_x + xdim
                                max_y = min_y + ydim
                                max_z = min_z + depth
                            else:
                                # Non-Z extrusion: compute axis-aligned bounding
                                # box from the 8 corners of the extruded solid.
                                # Profile defines a rectangle in the XY plane at
                                # the item position; the depth extrudes it along
                                # the extrusion direction.
                                _ndx, _ndy, _ndz = extrusion_dir
                                _nmag = math.sqrt(_ndx**2 + _ndy**2 + _ndz**2)
                                if _nmag > 1e-12:
                                    _ndx /= _nmag
                                    _ndy /= _nmag
                                    _ndz /= _nmag
                                # Profile rectangle corners (in local 2D)
                                base_x = cx + px + prof_x
                                base_y = cy + py + prof_y
                                base_z = cz + pz
                                corners_2d = [
                                    (0.0, 0.0),
                                    (xdim, 0.0),
                                    (xdim, ydim),
                                    (0.0, ydim),
                                ]
                                # Build 3D corners: 4 base + 4 extruded
                                all_corners = []
                                for lx, ly in corners_2d:
                                    # Base corner
                                    bx = base_x + lx
                                    by = base_y + ly
                                    bz = base_z
                                    all_corners.append((bx, by, bz))
                                    # Extruded corner
                                    ex = bx + _ndx * depth
                                    ey = by + _ndy * depth
                                    ez = bz + _ndz * depth
                                    all_corners.append((ex, ey, ez))
                                min_x = min(c[0] for c in all_corners)
                                min_y = min(c[1] for c in all_corners)
                                min_z = min(c[2] for c in all_corners)
                                max_x = max(c[0] for c in all_corners)
                                max_y = max(c[1] for c in all_corners)
                                max_z = max(c[2] for c in all_corners)
                        elif hasattr(profile, "Radius"):
                            radius = float(profile.Radius)
                            # V106 CRITICAL FIX: Validate radius
                            if not math.isfinite(radius):
                                log.critical(
                                    "V106 SAFETY: Non-finite Radius (%s) in element %s — "
                                    "DROPPING. NaN radius produces phantom bounding box.",
                                    radius,
                                    element_id,
                                )
                                return None
                            if is_z_extrusion:
                                min_x = cx + px + prof_x - radius
                                min_y = cy + py + prof_y - radius
                                min_z = cz + pz
                                max_x = cx + px + prof_x + radius
                                max_y = cy + py + prof_y + radius
                                max_z = min_z + depth
                            else:
                                # Non-Z extrusion with circular profile
                                _ndx, _ndy, _ndz = extrusion_dir
                                _nmag = math.sqrt(_ndx**2 + _ndy**2 + _ndz**2)
                                if _nmag > 1e-12:
                                    _ndx /= _nmag
                                    _ndy /= _nmag
                                    _ndz /= _nmag
                                # Circular profile centre in local XY
                                pcx = cx + px + prof_x
                                pcy = cy + py + prof_y
                                pcz = cz + pz
                                # For a circle, the AABB in XY is ±radius from centre
                                # The extrusion extends from base along direction
                                # Compute AABB of the extruded cylinder
                                base_min_x = pcx - radius
                                base_max_x = pcx + radius
                                base_min_y = pcy - radius
                                base_max_y = pcy + radius
                                base_z_val = pcz
                                # Extruded centre
                                ext_cx = pcx + _ndx * depth
                                ext_cy = pcy + _ndy * depth
                                ext_cz = pcz + _ndz * depth
                                all_mins_maxes = [
                                    (base_min_x, base_min_y, base_z_val),
                                    (base_max_x, base_max_y, base_z_val),
                                    (ext_cx - radius, ext_cy - radius, ext_cz),
                                    (ext_cx + radius, ext_cy + radius, ext_cz),
                                ]
                                min_x = min(c[0] for c in all_mins_maxes)
                                min_y = min(c[1] for c in all_mins_maxes)
                                min_z = min(c[2] for c in all_mins_maxes)
                                max_x = max(c[0] for c in all_mins_maxes)
                                max_y = max(c[1] for c in all_mins_maxes)
                                max_z = max(c[2] for c in all_mins_maxes)
                        else:
                            # Use position as center, depth as height
                            if is_z_extrusion:
                                min_x = cx + px
                                min_y = cy + py
                                min_z = cz + pz
                                max_x = min_x
                                max_y = min_y
                                max_z = min_z + depth
                            else:
                                # Non-Z extrusion, no profile dimensions
                                _ndx, _ndy, _ndz = extrusion_dir
                                _nmag = math.sqrt(_ndx**2 + _ndy**2 + _ndz**2)
                                if _nmag > 1e-12:
                                    _ndx /= _nmag
                                    _ndy /= _nmag
                                    _ndz /= _nmag
                                min_x = cx + px
                                min_y = cy + py
                                min_z = cz + pz
                                max_x = min_x + _ndx * depth
                                max_y = min_y + _ndy * depth
                                max_z = min_z + _ndz * depth
    except Exception as exc:
        # V93 FIX: Geometry extraction failure MUST return None.
        # V67 logged but continued, creating a zero-volume BoundingBox3D
        # that was invisible to the occupancy grid. A zero-volume box at
        # (0,0,0) is WORSE than missing the element entirely, because:
        # 1. It appears in the elements list (false sense of coverage)
        # 2. It occupies no grid cells (cable router ignores it)
        # 3. It skews grid_origin calculation toward (0,0,0)
        log.critical(
            "V93 SAFETY: Representation geometry extraction failed for %s — "
            "DROPPING element (returning None). A zero-volume bounding box "
            "is more dangerous than a missing element. Error: %s",
            element_id,
            exc,
        )
        return None

    # Ensure min < max
    if min_x > max_x:
        min_x, max_x = max_x, min_x
    if min_y > max_y:
        min_y, max_y = max_y, min_y
    if min_z > max_z:
        min_z, max_z = max_z, min_z

    # V93 SAFETY: Zero-volume bounding boxes are dangerous — they appear
    # in the elements list but are invisible to the occupancy grid.
    # A wall at (5,5,0)-(5,5,3) has zero width and occupies no cells.
    # For BLOCKING types (walls, slabs, beams), this is CRITICAL —
    # cables will route through an invisible wall.
    volume = (max_x - min_x) * (max_y - min_y) * (max_z - min_z)
    # V106 FIX: Also reject zero-volume SPACE elements — phantom spaces
    # without volume produce unrouteable targets for the cable router.
    if volume == 0.0 and element_type in _BLOCKING_TYPES:
        log.critical(
            "V93 SAFETY: Zero-volume BoundingBox3D for BLOCKING element %s "
            "(type=%s, bbox=(%s,%s,%s)-(%s,%s,%s)). This element will be "
            "DROPPED — a zero-volume blocking element is invisible to the "
            "cable router, creating a false sense of safety.",
            element_id,
            element_type.value,
            min_x,
            min_y,
            min_z,
            max_x,
            max_y,
            max_z,
        )
        return None
    if volume == 0.0 and element_type == IfcElementType.SPACE:
        log.warning(
            "V106: Zero-volume SPACE element %s (bbox=(%s,%s,%s)-(%s,%s,%s)). "
            "DROPPING — phantom spaces produce unrouteable cable targets.",
            element_id,
            min_x,
            min_y,
            min_z,
            max_x,
            max_y,
            max_z,
        )
        return None

    # V96 FIX: Pass element_type so _extract_fire_rating can default
    # to fire-rated (True, 2.0h) for blocking elements on failure.
    is_rated, rating_hours = _extract_fire_rating(element, element_type)

    return BoundingBox3D(
        element_id=element_id,
        element_type=element_type,
        min_x=min_x,
        min_y=min_y,
        min_z=min_z,
        max_x=max_x,
        max_y=max_y,
        max_z=max_z,
        is_fire_rated=is_rated,
        fire_rating_hours=rating_hours,
        ifc_class=ifc_class,
    )


def parse_ifc_file(file_path: str) -> BuildingModel:
    """Parse an IFC file and extract building geometry.

    ISO 16739 — Industry Foundation Classes:
      Extracts IfcWall, IfcSlab, IfcBeam, IfcSpace, IfcDoor, IfcWindow
      and builds a 3D occupancy grid at 100mm resolution.

    Args:
        file_path: Path to the IFC file.

    Returns:
        BuildingModel with all extracted geometry and grid.

    Raises:
        ImportError: If IfcOpenShell is not installed.
        FileNotFoundError: If the IFC file does not exist.
        ValueError: If the IFC file cannot be parsed.

    """
    ifs = _get_ifcopenshell()
    if ifs is None:
        raise ImportError("IfcOpenShell is required for IFC file parsing. Install with: pip install ifcopenshell")


    if not os.path.isfile(file_path):
        raise FileNotFoundError(f"IFC file not found: {file_path}")

    try:
        model = ifs.open(file_path)
    except Exception as exc:
        raise ValueError(f"Cannot parse IFC file '{file_path}': {exc}") from exc

    return _extract_building_model(model)


def parse_ifc_from_string(ifc_content: str) -> BuildingModel:
    """Parse IFC content from a string.

    Useful for testing without physical files.

    Args:
        ifc_content: IFC file content as a string.

    Returns:
        BuildingModel with extracted geometry.

    Raises:
        ImportError: If IfcOpenShell is not installed.
        ValueError: If the content cannot be parsed.

    """
    ifs = _get_ifcopenshell()
    if ifs is None:
        raise ImportError("IfcOpenShell is required for IFC parsing. Install with: pip install ifcopenshell")

    try:
        import tempfile

        with tempfile.NamedTemporaryFile(mode="w", suffix=".ifc", delete=False) as f:
            f.write(ifc_content)
            temp_path = f.name

        try:
            model = ifs.open(temp_path)
            return _extract_building_model(model)
        finally:

            os.unlink(temp_path)
    except Exception as exc:
        raise ValueError(f"Cannot parse IFC content: {exc}") from exc


def _extract_building_model(ifc_model) -> BuildingModel:
    """Extract building model from an IfcOpenShell model object.

    Args:
        ifc_model: IfcOpenShell model object.

    Returns:
        BuildingModel with geometry and grid.

    """
    elements = []
    spaces = []
    dropped_count = 0  # V93: Track dropped elements for safety audit

    # Get building name
    building_name = ""
    try:
        for building in ifc_model.by_type("IfcBuilding"):
            building_name = building.Name or ""
            break
    except Exception as exc:
        # V67 SAFETY FIX: Building name extraction failure must be logged.
        # V96 FIX: Removed redundant pass — logging is sufficient, and building
        # name defaults to empty string (non-safety-critical, but audit trail
        # should note the failure).
        log.warning("V67: Building name extraction failed: %s", exc)

    # Extract elements by type
    # V106 FIX: Added fire-safety IFC entities (IfcAlarm, IfcSensor, IfcProtectiveDevice)
    # and structural entities (IfcStair, IfcRamp, IfcMember, IfcBuildingElementProxy)
    target_types = [
        # Structural / Architectural
        "IfcWall",
        "IfcWallStandardCase",
        "IfcSlab",
        "IfcBeam",
        "IfcSpace",
        "IfcDoor",
        "IfcWindow",
        "IfcColumn",
        "IfcCurtainWall",
        # V106: Structural elements affecting cable routing
        "IfcStair",
        "IfcRamp",
        "IfcMember",
        "IfcBuildingElementProxy",
        # V106: Fire safety elements — critical for a fire protection system
        "IfcAlarm",
        "IfcSensor",
        "IfcProtectiveDevice",
        "IfcElectricDistributionBoard",
    ]

    for ifc_type in target_types:
        try:
            for element in ifc_model.by_type(ifc_type):
                bbox = _get_element_bbox(element)
                if bbox is not None:
                    elements.append(bbox)
                    if bbox.element_type == IfcElementType.SPACE:
                        spaces.append(
                            SpaceInfo(
                                space_id=bbox.element_id,
                                space_name=getattr(element, "Name", "") or "",
                                space_number=getattr(element, "LongName", "") or getattr(element, "Name", "") or "",
                                bounding_box=bbox,
                                floor_elevation=bbox.min_z,
                                ceiling_elevation=bbox.max_z,
                            )
                        )
                else:
                    # V93: Count dropped elements for safety audit
                    dropped_count += 1
        except Exception as exc:
            # V67 SAFETY FIX: If extraction of one element type fails,
            # log it but continue with other types. However, missing
            # IfcWall elements are CRITICAL — cable router won't see walls.
            log.critical(
                "V67 SAFETY: Extraction of %s elements failed — "
                "these elements will be INVISIBLE to cable router. "
                "Error: %s",
                ifc_type,
                exc,
                exc_info=True,
            )
            continue

    # V93 SAFETY: Warn if elements were dropped due to failed extraction.
    # Dropped walls/partitions mean the cable router won't see them,
    # potentially routing cables through fire-rated barriers.
    if dropped_count > 0:
        log.warning(
            "V93 SAFETY: %d IFC elements were DROPPED due to geometry "
            "extraction failures. These elements will NOT appear in the "
            "occupancy grid. If any are fire-rated walls/partitions, "
            "cables may be incorrectly routed through them. Manual "
            "verification of the cable routing result is REQUIRED.",
            dropped_count,
        )

    # Build occupancy grid
    grid_origin, grid_size, grid_data = _build_occupancy_grid(elements, resolution=0.1)

    return BuildingModel(
        building_name=building_name,
        elements=tuple(elements),
        spaces=tuple(spaces),
        grid_origin=grid_origin,
        grid_size=grid_size,
        grid_resolution=0.1,
        grid_data=grid_data,
    )


def _build_occupancy_grid(
    elements: List[BoundingBox3D],
    resolution: float = 0.1,
    padding_m: float = 1.0,
) -> Tuple[Tuple[float, float, float], Tuple[int, int, int], bytes]:
    """Build a 3D occupancy grid from extracted building elements.

    Grid Convention:
      - Each cell represents a (resolution × resolution × resolution) cube
      - CellState.FREE: navigable (no obstacle)
      - CellState.BLOCKED: solid obstacle
      - CellState.DOOR_OPENING: door opening
      - CellState.ELECTRICAL: electrical zone (separation required)

    Args:
        elements: List of BoundingBox3D elements.
        resolution: Grid cell size in meters (default 0.1 = 100mm).
        padding_m: Padding around building extents in meters.

    Returns:
        (grid_origin, grid_size, grid_data) tuple.
        - grid_origin: (x, y, z) of grid origin
        - grid_size: (nx, ny, nz) grid dimensions
        - grid_data: bytes of CellState values

    """
    if not elements:
        return (0.0, 0.0, 0.0), (0, 0, 0), b""

    # Compute building extents
    min_x = min(e.min_x for e in elements)
    min_y = min(e.min_y for e in elements)
    min_z = min(e.min_z for e in elements)
    max_x = max(e.max_x for e in elements)
    max_y = max(e.max_y for e in elements)
    max_z = max(e.max_z for e in elements)

    # Apply padding
    min_x -= padding_m
    min_y -= padding_m
    min_z -= padding_m
    max_x += padding_m
    max_y += padding_m
    max_z += padding_m

    # Grid dimensions
    nx = max(1, int(math.ceil((max_x - min_x) / resolution)))
    ny = max(1, int(math.ceil((max_y - min_y) / resolution)))
    nz = max(1, int(math.ceil((max_z - min_z) / resolution)))

    # Safety limit: don't create grids larger than 50M cells
    max_cells = 50_000_000
    if nx * ny * nz > max_cells:
        # Reduce resolution to fit
        scale = (max_cells / (nx * ny * nz)) ** (1.0 / 3.0)
        nx = max(1, int(nx * scale))
        ny = max(1, int(ny * scale))
        nz = max(1, int(nz * scale))
        resolution = (max_x - min_x) / nx

    # Initialize grid as FREE
    total_cells = nx * ny * nz
    grid = bytearray([CellState.FREE.value] * total_cells)

    # Mark cells
    def _cell_index(ix: int, iy: int, iz: int) -> int:
        return iz * ny * nx + iy * nx + ix

    for elem in elements:
        # Convert element bounds to grid indices
        # V64 FIX: Use math.floor instead of int() for grid coordinate
        # conversion. int() truncates toward zero, mapping negative
        # offsets to cell 0 instead of -1. Same V63 bug pattern —
        # elements near grid origin could be placed in wrong cells.
        ix_min = max(0, math.floor((elem.min_x - min_x) / resolution))
        iy_min = max(0, math.floor((elem.min_y - min_y) / resolution))
        iz_min = max(0, math.floor((elem.min_z - min_z) / resolution))
        ix_max = min(nx - 1, math.floor((elem.max_x - min_x) / resolution))
        iy_max = min(ny - 1, math.floor((elem.max_y - min_y) / resolution))
        iz_max = min(nz - 1, math.floor((elem.max_z - min_z) / resolution))

        # Determine cell state
        if elem.element_type in _BLOCKING_TYPES:
            state = CellState.BLOCKED
        elif elem.element_type in _OPENING_TYPES:
            state = CellState.DOOR_OPENING
        else:
            continue  # Skip unknown types

        # Mark cells
        for iz in range(iz_min, iz_max + 1):
            for iy in range(iy_min, iy_max + 1):
                for ix in range(ix_min, ix_max + 1):
                    idx = _cell_index(ix, iy, iz)
                    # Blocked takes priority over door opening
                    if grid[idx] != CellState.BLOCKED.value:
                        grid[idx] = state.value

    return (min_x, min_y, min_z), (nx, ny, nz), bytes(grid)


def build_abstract_model(
    obstacles: List[BoundingBox3D],
    spaces: Optional[List[SpaceInfo]] = None,
    building_name: str = "Abstract",
    resolution: float = 0.1,
) -> BuildingModel:
    """Build a BuildingModel from programmatic obstacles (no IFC file).

    This is the primary interface for testing and for systems that
    don't have IFC files. Obstacles are defined directly as
    BoundingBox3D objects.

    Args:
        obstacles: List of BoundingBox3D obstacles.
        spaces: Optional list of SpaceInfo objects.
        building_name: Building name for the model.
        resolution: Grid cell size in meters (default 0.1 = 100mm).

    Returns:
        BuildingModel with occupancy grid.

    """
    grid_origin, grid_size, grid_data = _build_occupancy_grid(obstacles, resolution=resolution)

    return BuildingModel(
        building_name=building_name,
        elements=tuple(obstacles),
        spaces=tuple(spaces or []),
        grid_origin=grid_origin,
        grid_size=grid_size,
        grid_resolution=resolution,
        grid_data=grid_data,
    )


def get_cell_state(
    model: BuildingModel,
    x: float,
    y: float,
    z: float,
) -> CellState:
    """Query the occupancy grid at a world coordinate.

    Converts world coordinates (meters) to grid indices and
    returns the CellState at that position.

    Args:
        model: BuildingModel with occupancy grid.
        x, y, z: World coordinates in meters.

    Returns:
        CellState at the given position. Returns BLOCKED if
        coordinates are outside the grid bounds.

    """
    if not model.grid_data or model.grid_size == (0, 0, 0):
        return CellState.BLOCKED

    ox, oy, oz = model.grid_origin
    nx, ny, nz = model.grid_size

    ix = math.floor((x - ox) / model.grid_resolution)
    iy = math.floor((y - oy) / model.grid_resolution)
    iz = math.floor((z - oz) / model.grid_resolution)

    if ix < 0 or ix >= nx or iy < 0 or iy >= ny or iz < 0 or iz >= nz:
        return CellState.BLOCKED

    idx = iz * ny * nx + iy * nx + ix
    if idx >= len(model.grid_data):
        return CellState.BLOCKED

    return CellState(model.grid_data[idx])


def world_to_grid(
    model: BuildingModel,
    x: float,
    y: float,
    z: float,
) -> Tuple[int, int, int]:
    """Convert world coordinates (meters) to grid indices.

    V63 FIX: Uses math.floor instead of int() for coordinate
    conversion. int() truncates toward zero, which incorrectly
    maps small negative offsets to cell 0 instead of -1. This
    caused points slightly outside the grid to appear as valid
    in-bounds cells, potentially routing cables through points
    outside the building model.

    Args:
        model: BuildingModel with grid.
        x, y, z: World coordinates in meters.

    Returns:
        (ix, iy, iz) grid indices.

    """
    ox, oy, oz = model.grid_origin
    return (
        math.floor((x - ox) / model.grid_resolution),
        math.floor((y - oy) / model.grid_resolution),
        math.floor((z - oz) / model.grid_resolution),
    )


def grid_to_world(
    model: BuildingModel,
    ix: int,
    iy: int,
    iz: int,
) -> Tuple[float, float, float]:
    """Convert grid indices to world coordinates (cell center).

    Args:
        model: BuildingModel with grid.
        ix, iy, iz: Grid indices.

    Returns:
        (x, y, z) world coordinates at cell center.

    """
    ox, oy, oz = model.grid_origin
    r = model.grid_resolution
    return (
        ox + (ix + 0.5) * r,
        oy + (iy + 0.5) * r,
        oz + (iz + 0.5) * r,
    )
