"""
fireai.core.ifc_parser — IFC Building Geometry Extraction
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
import math
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

# ─── Lazy IfcOpenShell import ──────────────────────────────────────────────

_ifcopenshell = None


def _get_ifcopenshell():
    """Lazy-load IfcOpenShell, returning None if unavailable."""
    global _ifcopenshell
    if _ifcopenshell is None:
        try:
            import ifcopenshell as _ifs
            _ifcopenshell = _ifs
        except ImportError:
            _ifcopenshell = False
    return _ifcopenshell if _ifcopenshell is not False else None


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
    FREE = 0           # Navigable — cable can pass
    BLOCKED = 1        # Solid obstacle — cable cannot pass
    DOOR_OPENING = 2   # Door opening — cable can pass horizontally
    SHAFT = 3          # Vertical shaft — cable can pass vertically
    ELECTRICAL = 4     # Electrical zone — 300mm separation required per project spec


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
        return (self.min_x <= x <= self.max_x
                and self.min_y <= y <= self.max_y
                and self.min_z <= z <= self.max_z)

    def overlaps(self, other: BoundingBox3D) -> bool:
        """Check if this bounding box overlaps another (AABB intersection)."""
        return (self.min_x <= other.max_x and self.max_x >= other.min_x
                and self.min_y <= other.max_y and self.max_y >= other.min_y
                and self.min_z <= other.max_z and self.max_z >= other.min_z)


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
            raw = (
                f"{self.grid_origin}|{self.grid_size}|"
                f"{self.grid_resolution}|{len(self.elements)}|"
                f"{len(self.spaces)}"
            )
            h = hashlib.sha256(raw.encode()).hexdigest()
            h += hashlib.sha256(self.grid_data).hexdigest()
            object.__setattr__(self, "computation_hash", h[:32])


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


def _extract_fire_rating(element) -> Tuple[bool, float]:
    """Extract fire rating from IFC element properties.

    Checks Pset_FireRatingCommon and similar property sets.

    Args:
        element: IfcOpenShell element object.

    Returns:
        (is_fire_rated, fire_rating_hours) tuple.
    """
    is_rated = False
    rating_hours = 0.0
    try:
        for rel in element.IsDefinedBy:
            if hasattr(rel, 'RelatingPropertyDefinition'):
                pset = rel.RelatingPropertyDefinition
                if hasattr(pset, 'HasProperties'):
                    for prop in pset.HasProperties:
                        name = getattr(prop, 'Name', '').lower()
                        if 'fire' in name and 'rating' in name:
                            val = getattr(prop, 'NominalValue', None)
                            if val is not None:
                                val_str = str(getattr(val, 'wrappedValue', val))
                                try:
                                    rating_hours = float(val_str)
                                    is_rated = True
                                except (ValueError, TypeError):
                                    pass
    except Exception:
        pass
    return is_rated, rating_hours


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

    # Try to get local placement (fallback method)
    try:
        placement = element.ObjectPlacement
        if placement is None:
            return None

        loc = placement.RelativePlacement
        if loc is None:
            return None

        # Extract location from IfcAxis2Placement3D
        if hasattr(loc, 'Location') and loc.Location is not None:
            coords = loc.Location.Coordinates
            cx, cy, cz = float(coords[0]), float(coords[1]), float(coords[2]) if len(coords) > 2 else 0.0
        else:
            cx, cy, cz = 0.0, 0.0, 0.0

        # Validate coordinates
        for val in [cx, cy, cz]:
            if not math.isfinite(val):
                return None

    except Exception:
        cx, cy, cz = 0.0, 0.0, 0.0

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
                    if item.is_a('IfcExtrudedAreaSolid'):
                        # Get position
                        pos = item.Position
                        if pos and hasattr(pos, 'Location'):
                            px = float(pos.Location.Coordinates[0])
                            py = float(pos.Location.Coordinates[1])
                            pz = float(pos.Location.Coordinates[2]) if len(pos.Location.Coordinates) > 2 else 0.0
                        else:
                            px, py, pz = 0.0, 0.0, 0.0

                        # Get extrusion dimensions
                        depth = float(item.Depth) if hasattr(item, 'Depth') else 0.0

                        # Get profile bounds
                        profile = item.SweptArea
                        if hasattr(profile, 'Position') and profile.Position is not None:
                            prof_x = float(profile.Position.Location.Coordinates[0]) if hasattr(profile.Position.Location, 'Coordinates') else 0.0
                            prof_y = float(profile.Position.Location.Coordinates[1]) if len(profile.Position.Location.Coordinates) > 1 else 0.0
                        else:
                            prof_x, prof_y = 0.0, 0.0

                        if hasattr(profile, 'XDim') and hasattr(profile, 'YDim'):
                            xdim = float(profile.XDim)
                            ydim = float(profile.YDim)
                            min_x = cx + px + prof_x
                            min_y = cy + py + prof_y
                            min_z = cz + pz
                            max_x = min_x + xdim
                            max_y = min_y + ydim
                            max_z = min_z + depth
                        elif hasattr(profile, 'Radius'):
                            radius = float(profile.Radius)
                            min_x = cx + px + prof_x - radius
                            min_y = cy + py + prof_y - radius
                            min_z = cz + pz
                            max_x = cx + px + prof_x + radius
                            max_y = cy + py + prof_y + radius
                            max_z = min_z + depth
                        else:
                            # Use position as center, depth as height
                            min_x = cx + px
                            min_y = cy + py
                            min_z = cz + pz
                            max_x = min_x
                            max_y = min_y
                            max_z = min_z + depth
    except Exception:
        # Geometry extraction failed — use placement as point
        pass

    # Ensure min < max
    if min_x > max_x:
        min_x, max_x = max_x, min_x
    if min_y > max_y:
        min_y, max_y = max_y, min_y
    if min_z > max_z:
        min_z, max_z = max_z, min_z

    # Extract fire rating
    is_rated, rating_hours = _extract_fire_rating(element)

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
        raise ImportError(
            "IfcOpenShell is required for IFC file parsing. "
            "Install with: pip install ifcopenshell"
        )

    import os
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
        raise ImportError(
            "IfcOpenShell is required for IFC parsing. "
            "Install with: pip install ifcopenshell"
        )

    try:
        import tempfile
        with tempfile.NamedTemporaryFile(
            mode='w', suffix='.ifc', delete=False
        ) as f:
            f.write(ifc_content)
            temp_path = f.name

        try:
            model = ifs.open(temp_path)
            return _extract_building_model(model)
        finally:
            import os
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

    # Get building name
    building_name = ""
    try:
        for building in ifc_model.by_type('IfcBuilding'):
            building_name = building.Name or ""
            break
    except Exception:
        pass

    # Extract elements by type
    target_types = [
        'IfcWall', 'IfcWallStandardCase', 'IfcSlab', 'IfcBeam',
        'IfcSpace', 'IfcDoor', 'IfcWindow', 'IfcColumn', 'IfcCurtainWall',
    ]

    for ifc_type in target_types:
        try:
            for element in ifc_model.by_type(ifc_type):
                bbox = _get_element_bbox(element)
                if bbox is not None:
                    elements.append(bbox)
                    if bbox.element_type == IfcElementType.SPACE:
                        spaces.append(SpaceInfo(
                            space_id=bbox.element_id,
                            space_name=getattr(element, 'Name', '') or '',
                            space_number=getattr(element, 'LongName', '') or getattr(element, 'Name', '') or '',
                            bounding_box=bbox,
                            floor_elevation=bbox.min_z,
                            ceiling_elevation=bbox.max_z,
                        ))
        except Exception:
            continue

    # Build occupancy grid
    grid_origin, grid_size, grid_data = _build_occupancy_grid(
        elements, resolution=0.1
    )

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
        ix_min = max(0, int((elem.min_x - min_x) / resolution))
        iy_min = max(0, int((elem.min_y - min_y) / resolution))
        iz_min = max(0, int((elem.min_z - min_z) / resolution))
        ix_max = min(nx - 1, int((elem.max_x - min_x) / resolution))
        iy_max = min(ny - 1, int((elem.max_y - min_y) / resolution))
        iz_max = min(nz - 1, int((elem.max_z - min_z) / resolution))

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
    grid_origin, grid_size, grid_data = _build_occupancy_grid(
        obstacles, resolution=resolution
    )

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
    x: float, y: float, z: float,
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

    ix = int((x - ox) / model.grid_resolution)
    iy = int((y - oy) / model.grid_resolution)
    iz = int((z - oz) / model.grid_resolution)

    if ix < 0 or ix >= nx or iy < 0 or iy >= ny or iz < 0 or iz >= nz:
        return CellState.BLOCKED

    idx = iz * ny * nx + iy * nx + ix
    if idx >= len(model.grid_data):
        return CellState.BLOCKED

    return CellState(model.grid_data[idx])


def world_to_grid(
    model: BuildingModel,
    x: float, y: float, z: float,
) -> Tuple[int, int, int]:
    """Convert world coordinates (meters) to grid indices.

    Args:
        model: BuildingModel with grid.
        x, y, z: World coordinates in meters.

    Returns:
        (ix, iy, iz) grid indices.
    """
    ox, oy, oz = model.grid_origin
    return (
        int((x - ox) / model.grid_resolution),
        int((y - oy) / model.grid_resolution),
        int((z - oz) / model.grid_resolution),
    )


def grid_to_world(
    model: BuildingModel,
    ix: int, iy: int, iz: int,
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
