"""
qomn_conduit.router — Orthogonal A* Conduit Path Router
========================================================

Routes conduit runs between two points through a 3D building model,
honouring obstacles and physical clearance constraints.

ALGORITHM: Orthogonal A* (6-direction movement: X±, Y±, Z±)
HEURISTIC: Manhattan distance — provably admissible for orthogonal grids
COST:      segment_length + bend_penalty + elevation_penalty

CONSTRAINTS:
  - Conduit OD clearance from obstacle surfaces: 25mm (NEC 300.4)
  - Electrical conduit separation: 300mm (NEC 760.24 / project spec)
  - No more than 360° cumulative bends (NEC 358.26/352.26/344.24)

Reference: NEC 300.4, 358.26, 760.24; NFPA 72-2022 §12.2.
"""

from __future__ import annotations

import heapq
import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from qomn_conduit.errors import PhysicsError, RoutingError
from qomn_conduit.types import (
    ConduitType, FittingType, Point3D, Result, RoutePath, TradeSize,
)

# ─────────────────────────────────────────────────────────────────────────────
# Routing cost constants — tuned for fire alarm conduit
# ─────────────────────────────────────────────────────────────────────────────

# Extra path length cost added per 90° bend (metres)
_BEND_PENALTY_M: float = 0.50        # 500mm per bend direction change

# Extra cost per metre of elevation gain (metres cost per metre rise)
_ELEVATION_PENALTY_M_PER_M: float = 2.0

# Obstacle clearance radius (metres) — NEC 300.4 physical protection
_OBSTACLE_CLEARANCE_M: float = 0.025   # 25mm

# Electrical conduit separation (metres) — NEC 760.24 / project spec
_ELECTRICAL_CLEARANCE_M: float = 0.300  # 300mm

# Maximum A* iterations before declaring no path
_MAX_ITERATIONS: int = 500_000


# ─────────────────────────────────────────────────────────────────────────────
# Grid-aligned obstacle model (axis-aligned bounding box)
# ─────────────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class BoundingBox:
    """
    Axis-aligned bounding box for obstacle representation.

    All coordinates in metres. Inclusive bounds (a point exactly on
    the surface IS inside the box for clearance purposes).

    Attributes:
        x_min, y_min, z_min: Lower corner.
        x_max, y_max, z_max: Upper corner.
        is_electrical:        If True, applies _ELECTRICAL_CLEARANCE_M.
        label:                Human-readable identifier for debugging.
    """
    x_min: float
    y_min: float
    z_min: float
    x_max: float
    y_max: float
    z_max: float
    is_electrical: bool = False
    label: str = "obstacle"

    def __post_init__(self) -> None:
        if self.x_min > self.x_max or self.y_min > self.y_max or self.z_min > self.z_max:
            raise ValueError(
                f"BoundingBox {self.label!r}: min > max in at least one axis. "
                "All min coordinates must be ≤ max coordinates."
            )

    @property
    def clearance_m(self) -> float:
        """Required clearance from this obstacle surface in metres."""
        return _ELECTRICAL_CLEARANCE_M if self.is_electrical else _OBSTACLE_CLEARANCE_M

    def expanded(self) -> "BoundingBox":
        """Return box expanded by clearance_m on all sides."""
        c = self.clearance_m
        return BoundingBox(
            x_min=self.x_min - c, y_min=self.y_min - c, z_min=self.z_min - c,
            x_max=self.x_max + c, y_max=self.y_max + c, z_max=self.z_max + c,
            is_electrical=self.is_electrical, label=self.label,
        )

    def contains(self, p: Point3D) -> bool:
        """True if point p is inside or on the boundary of this box."""
        return (
            self.x_min <= p.x <= self.x_max
            and self.y_min <= p.y <= self.y_max
            and self.z_min <= p.z <= self.z_max
        )

    def __repr__(self) -> str:
        return (
            f"BoundingBox({self.label!r} "
            f"[{self.x_min:.2f},{self.x_max:.2f}]"
            f"×[{self.y_min:.2f},{self.y_max:.2f}]"
            f"×[{self.z_min:.2f},{self.z_max:.2f}])"
        )


# ─────────────────────────────────────────────────────────────────────────────
# A* node
# ─────────────────────────────────────────────────────────────────────────────

@dataclass(order=False)
class _AStarNode:
    """Priority queue node for A* search."""
    f_cost: float         # g + h
    g_cost: float         # cost from start
    point: Point3D        # current grid position
    parent: Optional["_AStarNode"]
    direction: Optional[Tuple[int, int, int]]  # last move direction
    bend_count: int       # bends accumulated from start

    def __lt__(self, other: "_AStarNode") -> bool:
        return self.f_cost < other.f_cost

    def __repr__(self) -> str:
        return f"_AStarNode(f={self.f_cost:.3f}, {self.point!r})"


# ─────────────────────────────────────────────────────────────────────────────
# Public router
# ─────────────────────────────────────────────────────────────────────────────

class ConduitRouter:
    """
    Orthogonal A* router for physical conduit runs.

    Finds the shortest NEC-compliant path between two points in a building,
    honouring obstacle clearances and bend count limits.

    Algorithm: orthogonal A* with Manhattan heuristic.
    Deterministic: same input always produces same output.

    Reference: NEC 300.4, 358.26; NFPA 72-2022 §12.2.
    """

    def __init__(
        self,
        obstacles: Optional[List[BoundingBox]] = None,
        grid_resolution: float = 0.10,
    ) -> None:
        """
        Initialise the router.

        Args:
            obstacles:       List of bounding boxes to avoid.
            grid_resolution: Grid step size in metres. Default 100mm.
        """
        if not math.isfinite(grid_resolution) or grid_resolution <= 0.0:
            raise ValueError(
                f"grid_resolution={grid_resolution} must be positive finite. "
                "Typical value: 0.10 (100mm = conduit fitting precision)."
            )
        self._obstacles: List[BoundingBox] = list(obstacles or [])
        self._expanded: List[BoundingBox] = [o.expanded() for o in self._obstacles]
        self._res = grid_resolution

    def add_obstacle(self, obstacle: BoundingBox) -> None:
        """Add an obstacle and its expanded clearance zone."""
        self._obstacles.append(obstacle)
        self._expanded.append(obstacle.expanded())

    def _is_blocked(self, p: Point3D) -> bool:
        """True if point p is inside any obstacle clearance zone."""
        return any(box.contains(p) for box in self._expanded)

    def _snap(self, p: Point3D) -> Point3D:
        """Snap a point to the nearest grid node."""
        r = self._res
        return Point3D(
            x=round(p.x / r) * r,
            y=round(p.y / r) * r,
            z=round(p.z / r) * r,
        )

    def _point_key(self, p: Point3D) -> Tuple[int, int, int]:
        """Convert point to integer grid coordinates for dict keys."""
        r = self._res
        return (
            round(p.x / r),
            round(p.y / r),
            round(p.z / r),
        )

    # Six orthogonal directions: ±X, ±Y, ±Z
    _DIRECTIONS: List[Tuple[int, int, int]] = [
        (1, 0, 0), (-1, 0, 0),
        (0, 1, 0), (0, -1, 0),
        (0, 0, 1), (0, 0, -1),
    ]

    def route(
        self,
        start: Point3D,
        end: Point3D,
        conduit_type: ConduitType = ConduitType.EMT,
        trade_size: TradeSize = TradeSize.HALF_INCH,
    ) -> "Result[RoutePath, RoutingError | PhysicsError]":
        """
        Find shortest NEC-compliant conduit path from start to end.

        Uses orthogonal A* with Manhattan distance heuristic.
        Heuristic is ADMISSIBLE: Manhattan distance ≤ actual path length
        for any orthogonal grid, guaranteeing optimal path.

        Args:
            start:        Start point (metres). Snapped to grid.
            end:          End point (metres). Snapped to grid.
            conduit_type: For NEC reference citations and bend radius.
            trade_size:   For clearance sizing.

        Returns:
            Result.ok(RoutePath) — valid path found.
            Result.err(RoutingError) — no path exists.
            Result.err(PhysicsError) — non-finite coordinates.

        Reference: NEC 300.4 (clearance), 358.26 (bend limit).
        """
        # ── Input validation ─────────────────────────────────────────────────

        for name, pt in (("start", start), ("end", end)):
            for ax, v in (("x", pt.x), ("y", pt.y), ("z", pt.z)):
                if not math.isfinite(v):
                    return Result.err(PhysicsError(
                        message=f"{name}.{ax}={v} is not finite.",
                        remediation="All coordinates must be finite numbers.",
                    ))

        # ── Snap start/end to grid ────────────────────────────────────────────

        s = self._snap(start)
        e = self._snap(end)

        if self._point_key(s) == self._point_key(e):
            return Result.ok(RoutePath(
                waypoints=(s, e),
                total_length_m=0.0,
                bend_count=0,
                elevation_change_m=abs(e.z - s.z),
            ))

        if self._is_blocked(s):
            return Result.err(RoutingError(
                start=repr(start), end=repr(end),
                reason=(
                    f"Start point {start!r} is inside an obstacle clearance zone. "
                    "Move the conduit start point outside all obstacles."
                ),
            ))
        if self._is_blocked(e):
            return Result.err(RoutingError(
                start=repr(start), end=repr(end),
                reason=(
                    f"End point {end!r} is inside an obstacle clearance zone. "
                    "Move the conduit end point outside all obstacles."
                ),
            ))

        # ── A* search ────────────────────────────────────────────────────────

        open_heap: List[_AStarNode] = []
        g_costs: Dict[Tuple[int, int, int], float] = {}

        start_node = _AStarNode(
            f_cost=s.manhattan_to(e),
            g_cost=0.0,
            point=s,
            parent=None,
            direction=None,
            bend_count=0,
        )
        heapq.heappush(open_heap, start_node)
        g_costs[self._point_key(s)] = 0.0

        iterations = 0
        found: Optional[_AStarNode] = None

        while open_heap and iterations < _MAX_ITERATIONS:
            iterations += 1
            current = heapq.heappop(open_heap)
            cur_key = self._point_key(current.point)

            # Accept the node only if its g_cost matches the best known
            if current.g_cost > g_costs.get(cur_key, math.inf) + 1e-9:
                continue

            # Goal test
            if cur_key == self._point_key(e):
                found = current
                break

            # Expand neighbours — 6 orthogonal directions
            for dx, dy, dz in self._DIRECTIONS:
                nx = current.point.x + dx * self._res
                ny = current.point.y + dy * self._res
                nz = current.point.z + dz * self._res
                neighbour = Point3D(nx, ny, nz)

                if self._is_blocked(neighbour):
                    continue

                nkey = self._point_key(neighbour)
                step_dir = (dx, dy, dz)

                # Step cost = grid resolution (orthogonal = constant step)
                step_cost = self._res

                # Bend penalty: direction changed from last move
                is_bend = (
                    current.direction is not None
                    and step_dir != current.direction
                )
                if is_bend:
                    step_cost += _BEND_PENALTY_M

                # Elevation penalty: upward movement
                if dz > 0:
                    step_cost += _ELEVATION_PENALTY_M_PER_M * self._res

                new_g = current.g_cost + step_cost
                new_bends = current.bend_count + (1 if is_bend else 0)

                if new_g < g_costs.get(nkey, math.inf):
                    g_costs[nkey] = new_g
                    h = neighbour.manhattan_to(e)
                    node = _AStarNode(
                        f_cost=new_g + h,
                        g_cost=new_g,
                        point=neighbour,
                        parent=current,
                        direction=step_dir,
                        bend_count=new_bends,
                    )
                    heapq.heappush(open_heap, node)

        if found is None:
            return Result.err(RoutingError(
                start=repr(start), end=repr(end),
                reason=(
                    f"No valid path found after {iterations} iterations. "
                    "The obstacle layout may completely block the route, "
                    "or the grid resolution may be too coarse."
                ),
            ))

        # ── Reconstruct path ─────────────────────────────────────────────────

        waypoints: List[Point3D] = []
        node: Optional[_AStarNode] = found
        while node is not None:
            waypoints.append(node.point)
            node = node.parent
        waypoints.reverse()

        # Simplify: merge collinear segments (same direction consecutive)
        simplified = _simplify_waypoints(waypoints)

        total_length = sum(
            simplified[i].distance_to(simplified[i + 1])
            for i in range(len(simplified) - 1)
        )
        bends = max(0, len(simplified) - 2)
        elevation_change = abs(simplified[-1].z - simplified[0].z)

        return Result.ok(RoutePath(
            waypoints=tuple(simplified),
            total_length_m=total_length,
            bend_count=bends,
            elevation_change_m=elevation_change,
        ))


def _simplify_waypoints(waypoints: List[Point3D]) -> List[Point3D]:
    """
    Merge consecutive collinear points into straight segments.

    Deterministic: same input always produces same output.
    """
    if len(waypoints) <= 2:
        return list(waypoints)

    result: List[Point3D] = [waypoints[0]]

    for i in range(1, len(waypoints) - 1):
        prev = result[-1]
        curr = waypoints[i]
        nxt = waypoints[i + 1]

        d1 = (
            _sign(curr.x - prev.x),
            _sign(curr.y - prev.y),
            _sign(curr.z - prev.z),
        )
        d2 = (
            _sign(nxt.x - curr.x),
            _sign(nxt.y - curr.y),
            _sign(nxt.z - curr.z),
        )

        if d1 != d2:
            result.append(curr)

    result.append(waypoints[-1])
    return result


def _sign(x: float) -> int:
    """Return -1, 0, or 1 for the sign of x."""
    if x > 0:
        return 1
    if x < 0:
        return -1
    return 0


# ─────────────────────────────────────────────────────────────────────────────
# Module-level convenience function matching the spec API
# ─────────────────────────────────────────────────────────────────────────────

def orthogonal_astar(
    start: Point3D,
    end: Point3D,
    obstacles: Optional[List[BoundingBox]] = None,
    grid_resolution: float = 0.10,
    conduit_type: ConduitType = ConduitType.EMT,
    trade_size: TradeSize = TradeSize.HALF_INCH,
) -> "Result[RoutePath, RoutingError | PhysicsError]":
    """
    Route a conduit run using orthogonal A* pathfinding.

    Convenience wrapper around ConduitRouter.route().

    Args:
        start:           Start point in metres.
        end:             End point in metres.
        obstacles:       List of BoundingBox obstacles (walls, beams, etc.).
        grid_resolution: Grid step size (metres). Default 0.10.
        conduit_type:    For NEC reference and bend sizing.
        trade_size:      Nominal trade size.

    Returns:
        Result.ok(RoutePath) — valid orthogonal path.
        Result.err(RoutingError) — no valid path exists.
        Result.err(PhysicsError) — invalid coordinates.

    Reference: NEC 300.4 (physical protection), 358.26 (bend limit).
    """
    router = ConduitRouter(
        obstacles=obstacles or [],
        grid_resolution=grid_resolution,
    )
    return router.route(start, end, conduit_type, trade_size)
