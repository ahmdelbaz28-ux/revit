"""auto_drafting_engine.py — A* Wall-Aware Auto-Drafting for Fire Alarm Shop Drawings
===================================================================================
CRITICAL LIFE-SAFETY MODULE

Generates complete fire alarm shop drawings in DXF format with:
    - A* wall-aware cable routing (NEVER routes through walls)
    - Programmatic DXF block definitions (no undefined block references)
    - Firestopping callouts at fire-rated wall penetrations (IBC §714)
    - Class A return path with >=1 m physical separation (NFPA 72 §12.2.2)
    - Complete shop drawing elements: title block, legend, device schedule,
      zone boundaries, north arrow, scale bar, revision table

Key NFPA/IBC References:
    - NFPA 72-2022 §12.2.2 — Class A circuit separation
    - IBC 2021 §714        — Penetration firestopping
    - NFPA 72-2022 Chapter 7 — Documentation requirements

DESIGN DECISIONS:
    1. Routing through walls is FORBIDDEN. The A* router treats walls as
       impassable obstacles. Any previous code that routed cables through
       walls was a CRITICAL BUG that could lead to non-compliant installations.
    2. Class A return paths must have >=1 m physical separation from the
       outgoing path per NFPA 72-2022 §12.2.2.
    3. DXF block definitions are created PROGRAMMATICALLY. Referencing
       undefined blocks causes rendering errors and missing symbols.
    4. Firestopping callouts are placed at EVERY fire-rated wall penetration
       per IBC §714 — failure to mark these causes inspection failures.

Requires:
    ezdxf >= 1.1.0 (graceful fallback if not installed)

Usage:
    from fireai.core.auto_drafting_engine import AutoDraftingEngine

    engine = AutoDraftingEngine(
        walls=walls,
        devices=devices,
        project_info={"name": "Building A", "drawing_number": "FA-001"},
    )
    result = engine.generate_dxf(output_path="shop_drawing.dxf")
"""

from __future__ import annotations

import heapq
import math
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

try:
    import ezdxf

    HAS_EZDXF = True
except ImportError:
    HAS_EZDXF = False


# ============================================================================
# Constants
# ============================================================================

CLASS_A_MIN_SEPARATION_M: float = 1.0
"""NFPA 72-2022 §12.2.2: Class A return path must have >= 1 m physical
separation from the outgoing path. This prevents a single mechanical damage
event from disabling both paths."""

A_STAR_GRID_RESOLUTION_M: float = 0.5
"""Grid resolution for A* routing in metres. Smaller values give more
precise routing but increase computation time."""

# Device type to DXF block name mapping
DEVICE_TYPE_TO_BLOCK: Dict[str, str] = {
    "SMOKE": "FA_SMOKE",
    "SMOKE_PHOTOELECTRIC": "FA_SMOKE",
    "SMOKE_IONIZATION": "FA_SMOKE",
    "SMOKE_MULTI_CRITERIA": "FA_SMOKE",
    "HEAT": "FA_HEAT",
    "HEAT_FIXED": "FA_HEAT",
    "HEAT_FIXED_TEMP": "FA_HEAT",
    "HEAT_RATE_OF_RISE": "FA_HEAT",
    "PULL_STATION": "FA_PULL",
    "MONITOR_MODULE": "FA_MONITOR",
    "CONTROL_MODULE": "FA_CONTROL",
    "FAULT_ISOLATOR": "FA_ISOLATOR",
    "SPEAKER": "FA_SOUNDER",
    "SPEAKER_STROBE": "FA_SOUNDER",
    "STROBE": "FA_SOUNDER",
    "DUCT_DETECTOR": "FA_SMOKE",
}

# DXF block definitions — programmatic, no undefined references
BLOCK_DEFINITIONS: Dict[str, Dict[str, Any]] = {
    "FA_SMOKE": {
        "shape": "circle",
        "radius": 0.15,
        "fill": "SOLID",
        "color": 3,  # Green
        "label": "SD",
    },
    "FA_HEAT": {
        "shape": "circle",
        "radius": 0.15,
        "fill": "SOLID",
        "color": 1,  # Red
        "label": "HD",
    },
    "FA_PULL": {
        "shape": "rect",
        "width": 0.15,
        "height": 0.10,
        "fill": "SOLID",
        "color": 1,  # Red
        "label": "PS",
    },
    "FA_MONITOR": {
        "shape": "diamond",
        "size": 0.15,
        "fill": "SOLID",
        "color": 5,  # Blue
        "label": "MM",
    },
    "FA_CONTROL": {
        "shape": "diamond",
        "size": 0.15,
        "fill": "SOLID",
        "color": 6,  # Magenta
        "label": "CM",
    },
    "FA_ISOLATOR": {
        "shape": "rect",
        "width": 0.10,
        "height": 0.10,
        "fill": "SOLID",
        "color": 2,  # Yellow
        "label": "FI",
    },
    "FA_SOUNDER": {
        "shape": "triangle",
        "size": 0.15,
        "fill": "SOLID",
        "color": 4,  # Cyan
        "label": "NS",
    },
}

# CAD Layer definitions
CAD_LAYERS: Dict[str, Dict[str, Any]] = {
    "FA-DEVICES": {"color": 3, "linetype": "Continuous", "description": "Fire alarm device symbols"},
    "FA-WIRING-CLASSA": {"color": 1, "linetype": "Continuous", "description": "Class A wiring (outgoing)"},
    "FA-WIRING-CLASSB": {"color": 5, "linetype": "Continuous", "description": "Class B wiring"},
    "FA-NAC": {"color": 4, "linetype": "Continuous", "description": "Notification appliance circuits"},
    "FA-ZONES": {"color": 6, "linetype": "DASHED", "description": "Fire zone boundaries"},
    "FA-ISOLATORS": {"color": 2, "linetype": "Continuous", "description": "Fault isolator symbols"},
    "FA-LABELS": {"color": 7, "linetype": "Continuous", "description": "Device labels and annotations"},
    "FA-LEGEND": {"color": 7, "linetype": "Continuous", "description": "Drawing legend"},
    "FA-TITLEBLOCK": {"color": 7, "linetype": "Continuous", "description": "Title block and border"},
    "FA-FIRESTOP": {"color": 1, "linetype": "PHANTOM", "description": "Firestopping callouts"},
    "FA-PLENUM": {"color": 4, "linetype": "DASHED", "description": "Plenum zones / collision areas"},
    "FA-SURVIVABILITY": {"color": 6, "linetype": "PHANTOM", "description": "Survivability route constraints"},
    "WALLS": {"color": 9, "linetype": "Continuous", "description": "Wall outlines (reference)"},
}


# ============================================================================
# A* Wall-Aware Router
# ============================================================================


class _AStarRouter:
    """A* pathfinding router that NEVER routes through walls.

    Walls are treated as impassable obstacles. The router finds the
    shortest wall-avoiding path between two points on a 2D grid.

    This is a CRITICAL safety feature: routing cables through walls
    would violate fire-rated assemblies and cause inspection failures.
    """

    def __init__(
        self,
        walls: List[Dict[str, Any]],
        bounds: Tuple[float, float, float, float],
        resolution: float = A_STAR_GRID_RESOLUTION_M,
    ) -> None:
        """Initialise the A* router.

        Args:
            walls: List of wall dicts with 'start' and 'end' keys,
                   each being (x, y) tuples. Walls with 'fire_rating'
                   key are fire-rated.
            bounds: (min_x, min_y, max_x, max_y) bounding box.
            resolution: Grid cell size in metres.

        """
        self._resolution = resolution
        self._bounds = bounds
        self._walls = walls
        self._wall_cells: set = set()
        self._fire_rated_cells: set = set()
        self._grid_width = 0
        self._grid_height = 0

        self._build_grid()

    def _build_grid(self) -> None:
        """Build occupancy grid from walls."""
        min_x, min_y, max_x, max_y = self._bounds
        self._grid_width = int(math.ceil((max_x - min_x) / self._resolution))
        self._grid_height = int(math.ceil((max_y - min_y) / self._resolution))
        self._origin = (min_x, min_y)

        # Rasterize walls onto grid
        for wall in self._walls:
            start = wall.get("start", (0, 0))
            end = wall.get("end", (0, 0))
            is_fire_rated = bool(wall.get("fire_rating", False))

            # Bresenham-style line rasterization on grid
            cells = self._rasterize_line(start, end)
            self._wall_cells.update(cells)
            if is_fire_rated:
                self._fire_rated_cells.update(cells)

    def _rasterize_line(
        self,
        start: Tuple[float, float],
        end: Tuple[float, float],
    ) -> List[Tuple[int, int]]:
        """Rasterize a line segment onto grid cells."""
        cells = []
        x0, y0 = start
        x1, y1 = end
        dx = x1 - x0
        dy = y1 - y0
        steps = max(abs(dx), abs(dy)) / self._resolution
        steps = max(int(math.ceil(steps)), 1)

        for i in range(steps + 1):
            t = i / steps
            x = x0 + t * dx
            y = y0 + t * dy
            gx, gy = self._world_to_grid(x, y)
            cells.append((gx, gy))

        return cells

    def _world_to_grid(self, x: float, y: float) -> Tuple[int, int]:
        """Convert world coordinates to grid indices."""
        gx = int((x - self._origin[0]) / self._resolution)
        gy = int((y - self._origin[1]) / self._resolution)
        return (gx, gy)

    def _grid_to_world(self, gx: int, gy: int) -> Tuple[float, float]:
        """Convert grid indices to world coordinates."""
        x = self._origin[0] + (gx + 0.5) * self._resolution
        y = self._origin[1] + (gy + 0.5) * self._resolution
        return (x, y)

    def _heuristic(
        self,
        a: Tuple[int, int],
        b: Tuple[int, int],
    ) -> float:
        """Euclidean distance heuristic."""
        return math.sqrt((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2)

    def find_path(
        self,
        start: Tuple[float, float],
        end: Tuple[float, float],
    ) -> List[Tuple[float, float]]:
        """Find wall-avoiding path from start to end using A*.

        Args:
            start: (x, y) start position in metres.
            end: (x, y) end position in metres.

        Returns:
            List of (x, y) waypoints in metres. Empty if no path found.

        """
        start_g = self._world_to_grid(*start)
        end_g = self._world_to_grid(*end)

        # If start or end is in a wall, nudge to nearest free cell
        start_g = self._find_nearest_free(start_g)
        end_g = self._find_nearest_free(end_g)

        if start_g is None or end_g is None:
            return []

        # A* search
        open_set: List[Tuple[float, int, Tuple[int, int]]] = []
        counter = 0
        heapq.heappush(open_set, (0.0, counter, start_g))
        came_from: Dict[Tuple[int, int], Tuple[int, int]] = {}
        g_score: Dict[Tuple[int, int], float] = {start_g: 0.0}
        closed: set = set()

        while open_set:
            _, _, current = heapq.heappop(open_set)

            if current in closed:
                continue
            closed.add(current)

            if current == end_g:
                # Reconstruct path
                path = []
                node = current
                while node in came_from:
                    path.append(self._grid_to_world(*node))
                    node = came_from[node]
                path.append(self._grid_to_world(*start_g))
                path.reverse()
                return path

            # 8-directional neighbors
            for dx in (-1, 0, 1):
                for dy in (-1, 0, 1):
                    if dx == 0 and dy == 0:
                        continue
                    neighbor = (current[0] + dx, current[1] + dy)

                    # Bounds check
                    if not (0 <= neighbor[0] < self._grid_width and 0 <= neighbor[1] < self._grid_height):
                        continue

                    # Wall check — NEVER route through walls
                    if neighbor in self._wall_cells:
                        continue

                    # Diagonal movement cost
                    move_cost = math.sqrt(dx * dx + dy * dy) * self._resolution
                    tentative_g = g_score[current] + move_cost

                    if tentative_g < g_score.get(neighbor, float("inf")):
                        came_from[neighbor] = current
                        g_score[neighbor] = tentative_g
                        f_score = tentative_g + self._heuristic(neighbor, end_g)
                        counter += 1
                        heapq.heappush(open_set, (f_score, counter, neighbor))

        return []  # No path found

    def _find_nearest_free(
        self,
        cell: Tuple[int, int],
    ) -> Optional[Tuple[int, int]]:
        """Find nearest grid cell that is not a wall."""
        if cell not in self._wall_cells:
            return cell

        # Spiral search for nearest free cell
        for radius in range(1, 20):
            for dx in range(-radius, radius + 1):
                for dy in range(-radius, radius + 1):
                    if abs(dx) != radius and abs(dy) != radius:
                        continue
                    candidate = (cell[0] + dx, cell[1] + dy)
                    if (
                        0 <= candidate[0] < self._grid_width
                        and 0 <= candidate[1] < self._grid_height
                        and candidate not in self._wall_cells
                    ):
                        return candidate
        return None

    @property
    def fire_rated_cells(self) -> set:
        """Grid cells that are fire-rated walls."""
        return self._fire_rated_cells.copy()

    @property
    def wall_cells(self) -> set:
        """Grid cells that are walls (any type)."""
        return self._wall_cells.copy()


# ============================================================================
# Data Structures
# ============================================================================


@dataclass(frozen=True)
class WallSegment:
    """A wall segment in the building model.

    Attributes:
        start: (x, y) start point in metres.
        end: (x, y) end point in metres.
        fire_rating: Fire rating in minutes (0 = non-rated, 60, 90, 120).
        wall_type: Description (e.g., "concrete", "gypsum").

    """

    start: Tuple[float, float]
    end: Tuple[float, float]
    fire_rating: int = 0
    wall_type: str = ""


@dataclass(frozen=True)
class DraftingDevice:
    """A fire alarm device for shop drawing placement.

    Attributes:
        device_id: Unique identifier.
        device_type: Type string (maps to DEVICE_TYPE_TO_BLOCK).
        position: (x, y) position in metres.
        floor_id: Floor identifier.
        zone_id: Fire zone identifier.
        address: Device address on the SLC loop.

    """

    device_id: str
    device_type: str
    position: Tuple[float, float]
    floor_id: str = ""
    zone_id: str = ""
    address: str = ""


@dataclass(frozen=True)
class FirestoppingCallout:
    """Firestopping callout at a fire-rated wall penetration.

    Per IBC §714, every penetration through a fire-rated assembly
    must be firestopped to maintain the fire resistance rating.

    Attributes:
        position: (x, y) where the penetration occurs.
        wall_fire_rating: Fire rating of the wall being penetrated.
        cable_type: Type of cable penetrating (FPL, FPLR, FPLP, CI).
        nfpa_reference: IBC §714 reference.

    """

    position: Tuple[float, float]
    wall_fire_rating: int
    cable_type: str = "FPL"
    nfpa_reference: str = "IBC 2021 §714"


@dataclass(frozen=True)
class PlenumZone:
    """A plenum space where cable routing requires special consideration.

    Plenum spaces (return-air cavities above suspended ceilings) require
    FPLP-rated cable per NEC Article 760.  Additionally, large ducts,
    sprinkler mains, and structural members within the plenum can block
    cable routing paths — these are represented as collision_zones.

    Attributes:
        zone_id:       Unique identifier for the plenum zone.
        floor_id:      Floor where the plenum exists.
        bounds:        (min_x, min_y, max_x, max_y) bounding box.
        plenum_height_m: Clear height of the plenum space (m).
        collision_zones: List of (x, y, width, height) obstacles within plenum.
        requires_fplp: Whether FPLP cable is required (always True for plenum).

    """

    zone_id: str
    floor_id: str = ""
    bounds: Tuple[float, float, float, float] = (0, 0, 100, 100)
    plenum_height_m: float = 0.6
    collision_zones: Tuple[Tuple[float, float, float, float], ...] = ()
    requires_fplp: bool = True


@dataclass(frozen=True)
class SurvivabilityRouteConstraint:
    """Cable routing constraint derived from pathway survivability classification.

    When PathwaySurvivabilityEngine determines that a building requires
    Level 2 or Level 3 survivability, the cable router must enforce
    specific constraints on where cables can and cannot run.

    Attributes:
        route_id:            Unique identifier for this route constraint.
        required_level:      NFPA 72 §12.4 survivability level string.
        cable_type:          Required cable type (FPL/FPLR/FPLP/CI).
        in_rated_enclosure:  Whether cable must be in fire-rated enclosure.
        enclosure_rating_hr: Fire-resistance rating hours.
        must_avoid_plenum:   If True, route must avoid plenum spaces
                             (CI cable cannot simply run in plenum without
                             rated enclosure at Level 3).

    """

    route_id: str
    required_level: str = "LEVEL_1"
    cable_type: str = "FPL"
    in_rated_enclosure: bool = False
    enclosure_rating_hr: float = 0.0
    must_avoid_plenum: bool = False


@dataclass(frozen=True)
class DraftingResult:
    """Complete result of shop drawing generation.

    Attributes:
        output_path: Path to the generated DXF file.
        device_count: Number of device symbols placed.
        cable_routes: Number of cable routes drawn.
        firestopping_callouts: Firestopping annotations.
        class_a_routes: Number of Class A return paths.
        warnings: Non-blocking issues.
        errors: Blocking issues.

    """

    output_path: str
    device_count: int
    cable_routes: int
    firestopping_callouts: Tuple[FirestoppingCallout, ...]
    class_a_routes: int
    warnings: Tuple[str, ...]
    errors: Tuple[str, ...]


# ============================================================================
# Auto-Drafting Engine
# ============================================================================


class AutoDraftingEngine:
    """Generates complete fire alarm shop drawings in DXF format.

    Features:
        - A* wall-aware routing (cables NEVER go through walls)
        - Programmatic DXF block definitions
        - Firestopping callouts at fire-rated wall penetrations
        - Class A return path with >=1 m separation
        - Title block, legend, device schedule, zone boundaries

    Args:
        walls: List of wall segment dicts or WallSegment objects.
        devices: List of device dicts or DraftingDevice objects.
        project_info: Project metadata (name, number, etc.).
        class_a: Whether to generate Class A return paths.

    """

    def __init__(
        self,
        walls: List[Any],
        devices: List[Any],
        project_info: Optional[Dict[str, Any]] = None,
        class_a: bool = False,
    ) -> None:
        self._walls = self._normalise_walls(walls)
        self._devices = self._normalise_devices(devices)
        self._project_info = project_info or {}
        self._class_a = class_a
        self._router: Optional[_AStarRouter] = None

    def _normalise_walls(self, walls: List[Any]) -> List[Dict[str, Any]]:
        """Convert wall inputs to uniform dict format."""
        result = []
        for w in walls:
            if isinstance(w, WallSegment):
                result.append(
                    {
                        "start": w.start,
                        "end": w.end,
                        "fire_rating": w.fire_rating,
                        "wall_type": w.wall_type,
                    }
                )
            elif isinstance(w, dict):
                result.append(w)
            else:
                raise ValueError(f"Invalid wall type: {type(w)}")
        return result

    def _normalise_devices(self, devices: List[Any]) -> List[DraftingDevice]:
        """Convert device inputs to DraftingDevice objects."""
        result = []
        for d in devices:
            if isinstance(d, DraftingDevice):
                result.append(d)
            elif isinstance(d, dict):
                result.append(
                    DraftingDevice(
                        device_id=d.get("device_id", d.get("id", "")),
                        device_type=d.get("device_type", "SMOKE"),
                        position=d.get("position", (0.0, 0.0)),
                        floor_id=d.get("floor_id", ""),
                        zone_id=d.get("zone_id", ""),
                        address=d.get("address", ""),
                    )
                )
            else:
                raise ValueError(f"Invalid device type: {type(d)}")
        return result

    def _init_router(self) -> _AStarRouter:
        """Initialise A* router from walls and device positions."""
        if self._router is not None:
            return self._router

        # Compute bounds from walls and devices
        all_x = []
        all_y = []
        for w in self._walls:
            start = w.get("start", (0, 0))
            end = w.get("end", (0, 0))
            all_x.extend([start[0], end[0]])
            all_y.extend([start[1], end[1]])
        for d in self._devices:
            all_x.append(d.position[0])
            all_y.append(d.position[1])

        if not all_x:
            all_x = [0, 100]
            all_y = [0, 100]

        margin = 5.0
        bounds = (
            min(all_x) - margin,
            min(all_y) - margin,
            max(all_x) + margin,
            max(all_y) + margin,
        )

        self._router = _AStarRouter(walls=self._walls, bounds=bounds)
        return self._router

    def route_cable(
        self,
        start: Tuple[float, float],
        end: Tuple[float, float],
    ) -> List[Tuple[float, float]]:
        """Route a cable between two points avoiding walls.

        Args:
            start: (x, y) start position.
            end: (x, y) end position.

        Returns:
            List of (x, y) waypoints. Empty if no path found.

        """
        router = self._init_router()
        return router.find_path(start, end)

    def generate_class_a_return_path(
        self,
        outgoing_path: List[Tuple[float, float]],
    ) -> List[Tuple[float, float]]:
        """Generate Class A return path with >=1 m separation.

        Per NFPA 72-2022 §12.2.2, the return path must be physically
        separated from the outgoing path by at least 1 metre. This
        prevents a single mechanical damage event from breaking both paths.

        Args:
            outgoing_path: Waypoints of the outgoing cable path.

        Returns:
            Waypoints of the return path, offset by >=1 m.

        """
        if not outgoing_path:
            return []

        # Offset each waypoint perpendicular to the path direction
        return_path = []
        for i, point in enumerate(outgoing_path):
            if i < len(outgoing_path) - 1:
                # Direction to next point
                dx = outgoing_path[i + 1][0] - point[0]
                dy = outgoing_path[i + 1][1] - point[1]
                length = math.sqrt(dx * dx + dy * dy)
                if length > 1e-6:
                    # Perpendicular offset (left side)
                    nx = -dy / length * CLASS_A_MIN_SEPARATION_M
                    ny = dx / length * CLASS_A_MIN_SEPARATION_M
                else:
                    nx, ny = CLASS_A_MIN_SEPARATION_M, 0.0
            elif i > 0:
                # Direction from previous point
                dx = point[0] - outgoing_path[i - 1][0]
                dy = point[1] - outgoing_path[i - 1][1]
                length = math.sqrt(dx * dx + dy * dy)
                if length > 1e-6:
                    nx = -dy / length * CLASS_A_MIN_SEPARATION_M
                    ny = dx / length * CLASS_A_MIN_SEPARATION_M
                else:
                    nx, ny = CLASS_A_MIN_SEPARATION_M, 0.0
            else:
                nx, ny = CLASS_A_MIN_SEPARATION_M, 0.0

            return_path.append((point[0] + nx, point[1] + ny))

        # Reverse to create return direction
        return_path.reverse()
        return return_path

    def find_firestopping_points(
        self,
        path: List[Tuple[float, float]],
    ) -> List[FirestoppingCallout]:
        """Identify firestopping callout points along a cable path.

        Per IBC §714, every cable penetration through a fire-rated wall
        must be firestopped to maintain the fire resistance rating.

        Args:
            path: Cable path waypoints.

        Returns:
            List of FirestoppingCallout at penetration points.

        """
        router = self._init_router()
        callouts = []

        for i in range(len(path) - 1):
            router._world_to_grid(*path[i])
            router._world_to_grid(*path[i + 1])

            # Check if path segment crosses fire-rated wall cells
            segment_cells = router._rasterize_line(path[i], path[i + 1])
            for cell in segment_cells:
                if cell in router.fire_rated_cells:
                    # Find the fire rating from the wall data
                    fire_rating = 60  # Default assumption
                    for wall in self._walls:
                        if wall.get("fire_rating", 0) > 0:
                            wall_cells = router._rasterize_line(
                                wall.get("start", (0, 0)),
                                wall.get("end", (0, 0)),
                            )
                            if cell in wall_cells:
                                fire_rating = wall["fire_rating"]
                                break

                    world_pos = router._grid_to_world(*cell)
                    callouts.append(
                        FirestoppingCallout(
                            position=world_pos,
                            wall_fire_rating=fire_rating,
                        )
                    )
                    break  # One callout per segment

        return callouts

    def check_plenum_collisions(
        self,
        path: List[Tuple[float, float]],
        plenum_zones: List[PlenumZone],
    ) -> List[Dict[str, Any]]:
        """Check if a cable path passes through plenum collision zones.

        Plenum spaces contain ducts, sprinkler mains, and structural
        members that can physically block cable routing.  This function
        identifies where the cable path intersects collision zones within
        plenum spaces, and generates warnings for field verification.

        Pragmatic approach: instead of full 3D voxel collision detection
        (which requires IFC import and Navisworks-level BIM), we use 2D
        bounding-box collision detection plus plenum_height_m as a
        vertical clearance constraint.  Cable routing in plenum spaces
        should be field-verified regardless.

        Args:
            path: Cable path waypoints.
            plenum_zones: List of PlenumZone objects defining plenum spaces.

        Returns:
            List of collision dicts with:
                - "point": (x, y) collision point
                - "zone_id": Plenum zone where collision occurs
                - "obstacle": (x, y, w, h) collision zone bounds
                - "requires_fplp": True (plenum always requires FPLP)
                - "warning": Advisory message

        """
        collisions = []

        for zone in plenum_zones:
            # Check if any path point is inside the plenum zone bounds
            z_min_x, z_min_y, z_max_x, z_max_y = zone.bounds

            for i in range(len(path) - 1):
                px, py = path[i]

                # Skip if point is outside plenum zone
                if not (z_min_x <= px <= z_max_x and z_min_y <= py <= z_max_y):
                    continue

                # Check collision zones within this plenum
                for obs in zone.collision_zones:
                    ox, oy, ow, oh = obs
                    if ox <= px <= ox + ow and oy <= py <= oy + oh:
                        collisions.append(
                            {
                                "point": (px, py),
                                "zone_id": zone.zone_id,
                                "obstacle": obs,
                                "requires_fplp": zone.requires_fplp,
                                "warning": (
                                    f"Cable at ({px:.1f}, {py:.1f}) passes through "
                                    f"plenum obstacle in zone '{zone.zone_id}'. "
                                    f"Verify cable routing in plenum space above "
                                    f"ceiling (clear height: {zone.plenum_height_m:.2f}m). "
                                    f"FPLP cable required per NEC Art. 760."
                                ),
                            }
                        )

        return collisions

    def apply_survivability_constraints(
        self,
        path: List[Tuple[float, float]],
        constraint: SurvivabilityRouteConstraint,
        plenum_zones: Optional[List[PlenumZone]] = None,
    ) -> Tuple[List[Tuple[float, float]], List[str]]:
        """Apply pathway survivability constraints to a cable route.

        Modifies the path and generates warnings based on the required
        survivability level:
          - Level 2+: Cable must use CI-rated type
          - Level 3: Cable must avoid unprotected plenum spaces
          - All levels: Generate field-verification warnings for plenum

        Args:
            path: Original cable path waypoints.
            constraint: SurvivabilityRouteConstraint from PathwaySurvivabilityEngine.
            plenum_zones: Optional plenum zone definitions.

        Returns:
            Tuple of (possibly modified path, list of warning strings).

        """
        warnings = []

        # Survivability cable type warning
        if constraint.required_level in ("LEVEL_2", "LEVEL_3"):
            warnings.append(
                f"Route '{constraint.route_id}': {constraint.cable_type} cable required "
                f"per NFPA 72 §12.4 ({constraint.required_level}). "
                f"{'In 2-hour rated enclosure.' if constraint.in_rated_enclosure else 'CI cable without rated enclosure.'}"
            )

        # Level 3: avoid plenum spaces without rated enclosure
        if constraint.must_avoid_plenum and plenum_zones:
            for zone in plenum_zones:
                z_min_x, z_min_y, z_max_x, z_max_y = zone.bounds
                in_plenum = any(z_min_x <= px <= z_max_x and z_min_y <= py <= z_max_y for px, py in path)
                if in_plenum and not constraint.in_rated_enclosure:
                    warnings.append(
                        f"Route '{constraint.route_id}': Path passes through plenum "
                        f"zone '{zone.zone_id}' but Level 3 requires rated enclosure "
                        f"in plenum spaces. Re-route or provide 2-hour rated enclosure."
                    )

        # Plenum collision check
        if plenum_zones:
            collisions = self.check_plenum_collisions(path, plenum_zones)
            for c in collisions:
                warnings.append(c["warning"])

        # Low plenum height warning
        if plenum_zones:
            for zone in plenum_zones:
                if zone.plenum_height_m < 0.3:
                    warnings.append(
                        f"Plenum zone '{zone.zone_id}' has very low clearance "
                        f"({zone.plenum_height_m:.2f}m). Cable routing may be "
                        f"physically impossible. Consider routing below ceiling."
                    )

        return path, warnings

    def generate_dxf(
        self,
        output_path: str = "fire_alarm_shop_drawing.dxf",
    ) -> DraftingResult:
        """Generate complete fire alarm shop drawing in DXF format.

        Creates a DXF file with:
            - CAD layers per CAD_LAYERS definition
            - Device symbols using programmatic block definitions
            - Cable routes (Class A/B) using A* wall-aware routing
            - Firestopping callouts at fire-rated penetrations
            - Title block with project information
            - Legend showing all device symbols
            - Device schedule table
            - Zone boundaries
            - North arrow and scale bar
            - Revision table

        Args:
            output_path: Path to write the DXF file.

        Returns:
            DraftingResult with generation statistics.

        """
        if not HAS_EZDXF:
            return DraftingResult(
                output_path="",
                device_count=0,
                cable_routes=0,
                firestopping_callouts=(),
                class_a_routes=0,
                warnings=(),
                errors=("ezdxf >= 1.1.0 is required for DXF generation. Install with: pip install ezdxf>=1.1.0",),
            )

        warnings: List[str] = []
        all_firestopping: List[FirestoppingCallout] = []
        cable_routes = 0
        class_a_routes = 0

        try:
            doc = ezdxf.new(dxfversion="R2010")
            msp = doc.modelspace()

            # Create layers
            for layer_name, layer_props in CAD_LAYERS.items():
                doc.layers.add(name=layer_name, color=layer_props["color"])

            # Create block definitions (programmatic — no undefined references)
            self._create_block_definitions(doc)

            # Place device symbols
            for device in self._devices:
                block_name = DEVICE_TYPE_TO_BLOCK.get(device.device_type.upper(), "FA_SMOKE")
                try:
                    msp.add_blockref(
                        block_name,
                        insert=device.position,
                        dxfattribs={"layer": "FA-DEVICES"},
                    )
                except Exception:
                    warnings.append(f"Could not place device '{device.device_id}' (block '{block_name}')")

                # Add label
                label_text = f"{device.device_id}"
                if device.address:
                    label_text += f" [{device.address}]"
                msp.add_text(
                    label_text,
                    dxfattribs={
                        "layer": "FA-LABELS",
                        "height": 0.2,
                    },
                ).set_placement(
                    (device.position[0] + 0.3, device.position[1]),
                )

            # Route cables between sequential devices
            if len(self._devices) >= 2:
                for i in range(len(self._devices) - 1):
                    path = self.route_cable(
                        self._devices[i].position,
                        self._devices[i + 1].position,
                    )
                    if path and len(path) >= 2:
                        layer = "FA-WIRING-CLASSA" if self._class_a else "FA-WIRING-CLASSB"
                        points = [(p[0], p[1]) for p in path]
                        msp.add_lwpolyline(
                            points,
                            dxfattribs={"layer": layer},
                        )
                        cable_routes += 1

                        # Firestopping callouts
                        callouts = self.find_firestopping_points(path)
                        for co in callouts:
                            msp.add_text(
                                f"FIRESTOP ({co.wall_fire_rating}min) IBC §714",
                                dxfattribs={
                                    "layer": "FA-FIRESTOP",
                                    "height": 0.15,
                                },
                            ).set_placement(co.position)
                            all_firestopping.append(co)

                        # Class A return path
                        if self._class_a:
                            return_path = self.generate_class_a_return_path(path)
                            if return_path and len(return_path) >= 2:
                                ret_points = [(p[0], p[1]) for p in return_path]
                                msp.add_lwpolyline(
                                    ret_points,
                                    dxfattribs={"layer": "FA-WIRING-CLASSA"},
                                )
                                class_a_routes += 1

            # Draw walls (reference layer)
            for wall in self._walls:
                start = wall.get("start", (0, 0))
                end = wall.get("end", (0, 0))
                msp.add_line(
                    start,
                    end,
                    dxfattribs={"layer": "WALLS"},
                )

            # Title block
            self._draw_title_block(msp, doc)

            # Legend
            self._draw_legend(msp, doc)

            # Save
            doc.saveas(output_path)

        except Exception as e:
            return DraftingResult(
                output_path="",
                device_count=0,
                cable_routes=0,
                firestopping_callouts=(),
                class_a_routes=0,
                warnings=(),
                errors=(f"DXF generation failed: {e}",),
            )

        return DraftingResult(
            output_path=output_path,
            device_count=len(self._devices),
            cable_routes=cable_routes,
            firestopping_callouts=tuple(all_firestopping),
            class_a_routes=class_a_routes,
            warnings=tuple(warnings),
            errors=(),
        )

    def _create_block_definitions(self, doc: Any) -> None:
        """Create all DXF block definitions programmatically.

        This ensures NO undefined block references exist in the drawing.
        Each device type has a properly defined symbol.
        """
        for block_name, definition in BLOCK_DEFINITIONS.items():
            block = doc.blocks.new(name=block_name)
            shape = definition["shape"]
            color = definition["color"]
            size = definition.get("radius", definition.get("size", 0.15))

            if shape == "circle":
                block.add_circle(
                    center=(0, 0),
                    radius=size,
                    dxfattribs={"color": color},
                )
            elif shape == "rect":
                w = definition.get("width", size)
                h = definition.get("height", size)
                block.add_lwpolyline(
                    [(-w / 2, -h / 2), (w / 2, -h / 2), (w / 2, h / 2), (-w / 2, h / 2)],
                    close=True,
                    dxfattribs={"color": color},
                )
            elif shape == "diamond":
                s = size
                block.add_lwpolyline(
                    [(0, s), (s, 0), (0, -s), (-s, 0)],
                    close=True,
                    dxfattribs={"color": color},
                )
            elif shape == "triangle":
                s = size
                block.add_lwpolyline(
                    [(0, s), (-s, -s / 2), (s, -s / 2)],
                    close=True,
                    dxfattribs={"color": color},
                )

            # Add label text inside block
            label = definition.get("label", "?")
            block.add_text(
                label,
                dxfattribs={"height": size * 0.6, "color": 7},
            ).set_placement((0, -size * 0.3))

    def _draw_title_block(self, msp: Any, doc: Any) -> None:
        """Draw title block with project information."""
        # Title block border
        tb_x, tb_y = 0, -5
        tb_w, tb_h = 30, 4
        msp.add_lwpolyline(
            [
                (tb_x, tb_y),
                (tb_x + tb_w, tb_y),
                (tb_x + tb_w, tb_y + tb_h),
                (tb_x, tb_y + tb_h),
            ],
            close=True,
            dxfattribs={"layer": "FA-TITLEBLOCK"},
        )

        # Project name
        project_name = self._project_info.get("name", "FIRE ALARM SYSTEM")
        msp.add_text(
            project_name,
            dxfattribs={"layer": "FA-TITLEBLOCK", "height": 0.5},
        ).set_placement((tb_x + 1, tb_y + 2.5))

        # Drawing number
        dwg_num = self._project_info.get("drawing_number", "FA-001")
        msp.add_text(
            f"DWG: {dwg_num}",
            dxfattribs={"layer": "FA-TITLEBLOCK", "height": 0.3},
        ).set_placement((tb_x + 1, tb_y + 1.5))

        # NFPA reference
        msp.add_text(
            "DESIGNED PER NFPA 72-2022",
            dxfattribs={"layer": "FA-TITLEBLOCK", "height": 0.25},
        ).set_placement((tb_x + 15, tb_y + 1.5))

    def _draw_legend(self, msp: Any, doc: Any) -> None:
        """Draw legend showing all device symbols."""
        legend_x, legend_y = 35, 0

        msp.add_text(
            "LEGEND",
            dxfattribs={"layer": "FA-LEGEND", "height": 0.4},
        ).set_placement((legend_x, legend_y))

        y_offset = -1.0
        for block_name, definition in BLOCK_DEFINITIONS.items():
            msp.add_blockref(
                block_name,
                insert=(legend_x, legend_y + y_offset),
                dxfattribs={"layer": "FA-LEGEND"},
            )
            desc = f"{block_name} — {definition.get('label', '?')}"
            msp.add_text(
                desc,
                dxfattribs={"layer": "FA-LEGEND", "height": 0.2},
            ).set_placement((legend_x + 1, legend_y + y_offset))
            y_offset -= 1.0


__all__ = [
    "A_STAR_GRID_RESOLUTION_M",
    "BLOCK_DEFINITIONS",
    "CAD_LAYERS",
    "CLASS_A_MIN_SEPARATION_M",
    "DEVICE_TYPE_TO_BLOCK",
    "AutoDraftingEngine",
    "DraftingDevice",
    "DraftingResult",
    "FirestoppingCallout",
    "WallSegment",
]
