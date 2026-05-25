"""
core/engineering_router.py
============================
NEC/NFPA-compliant cable routing engine for FireAI.

Uses a visibility graph + A* algorithm for obstacle-aware cable routing
that respects:
  - NEC bend radius constraints
  - Maximum cable run lengths
  - Conduit type constraints
  - Clearance from obstacles (walls, HVAC, sprinklers, etc.)
  - Line-of-sight checking with clearance buffers

Replaces the simpler Manhattan router in bridges/output_bridge.py
for production-grade routing.

Usage:
    from core.engineering_router import EngineeringRouter, RoutingObstacle

    router = EngineeringRouter()

    # Add obstacles
    router.add_obstacle(RoutingObstacle(
        obstacle_type="wall",
        x=5.0, y=0.0, width=0.2, height=10.0
    ))

    # Route cable
    path = router.route(start=(1.0, 2.0), end=(9.0, 2.0))
    for waypoint in path:
        print(waypoint)
"""

from __future__ import annotations

import heapq
import logging
import math
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Set, Tuple

from core.production_config import get_production_config

log = logging.getLogger(__name__)

# Try Shapely for geometry
try:
    from shapely.geometry import Polygon as ShapelyPolygon, Point as ShapelyPoint
    from shapely.geometry import LineString as ShapelyLineString
    from shapely.ops import unary_union
    SHAPELY_AVAILABLE = True
except ImportError:
    SHAPELY_AVAILABLE = False


# ════════════════════════════════════════════════════════════════════════════
# Obstacle Types
# ════════════════════════════════════════════════════════════════════════════

class ObstacleType(str, Enum):
    """Types of routing obstacles in a building."""
    WALL = "wall"
    HVAC = "hvac"
    SPRINKLER = "sprinkler"
    STAIRWELL = "stairwell"
    BEAM = "beam"
    LIGHT_FIXTURE = "light"
    COLUMN = "column"
    DOOR = "door"
    ELEVATOR = "elevator"
    SHAFT = "shaft"
    CUSTOM = "custom"


# ════════════════════════════════════════════════════════════════════════════
# Routing Obstacle
# ════════════════════════════════════════════════════════════════════════════

@dataclass
class RoutingObstacle:
    """
    An obstacle in the routing space.

    Defined as an axis-aligned bounding box (AABB) with a type,
    which determines the required clearance.

    Attributes
    ----------
    obstacle_type : ObstacleType or str
        Type of obstacle (determines clearance).
    x, y : float
        Bottom-left corner of the AABB (metres).
    width, height : float
        Dimensions of the AABB (metres).
    clearance : float, optional
        Override clearance in mm. If None, uses ProductionConfig defaults.
    passable : bool
        Whether cable can cross this obstacle (default: False).
    """
    obstacle_type: str
    x: float
    y: float
    width: float
    height: float
    clearance: Optional[float] = None
    passable: bool = False

    def __post_init__(self):
        if isinstance(self.obstacle_type, ObstacleType):
            self.obstacle_type = self.obstacle_type.value

    @property
    def bounds(self) -> Tuple[float, float, float, float]:
        """Return (minx, miny, maxx, maxy)."""
        return (self.x, self.y, self.x + self.width, self.y + self.height)

    def expanded_bounds(self, clearance_m: float) -> Tuple[float, float, float, float]:
        """Return bounds expanded by clearance."""
        minx, miny, maxx, maxy = self.bounds
        return (minx - clearance_m, miny - clearance_m,
                maxx + clearance_m, maxy + clearance_m)

    def to_shapely(self) -> Optional[ShapelyPolygon]:
        """Convert to Shapely polygon."""
        if not SHAPELY_AVAILABLE:
            return None
        minx, miny, maxx, maxy = self.bounds
        return ShapelyPolygon([
            (minx, miny), (maxx, miny), (maxx, maxy), (minx, maxy)
        ])

    def to_shapely_with_clearance(self, clearance_m: float) -> Optional[ShapelyPolygon]:
        """Convert to Shapely polygon expanded by clearance."""
        if not SHAPELY_AVAILABLE:
            return None
        minx, miny, maxx, maxy = self.expanded_bounds(clearance_m)
        return ShapelyPolygon([
            (minx, miny), (maxx, miny), (maxx, maxy), (minx, maxy)
        ])


# ════════════════════════════════════════════════════════════════════════════
# Routing Constraint
# ════════════════════════════════════════════════════════════════════════════

@dataclass
class RoutingConstraint:
    """
    Constraints for cable routing.

    Attributes
    ----------
    bend_radius_mm : float
        Minimum bend radius in mm.
    max_cable_length_m : float
        Maximum cable run before junction box.
    clearance_mm : float
        Default minimum clearance from obstacles.
    conduit_type : str
        Type of conduit (EMT, RMC, IMC, FMC, PVC, LFMC).
    vertical_penalty : float
        Cost multiplier for vertical runs (not used in 2D).
    cross_corridor_penalty : float
        Cost multiplier for paths crossing corridors.
    """
    bend_radius_mm: float = 300.0
    max_cable_length_m: float = 300.0
    clearance_mm: float = 50.0
    conduit_type: str = "EMT"
    vertical_penalty: float = 1.5
    cross_corridor_penalty: float = 2.0

    @staticmethod
    def from_production_config() -> RoutingConstraint:
        """Create constraints from ProductionConfig defaults."""
        cfg = get_production_config()
        return RoutingConstraint(
            bend_radius_mm=cfg.routing_bend_radius,
            max_cable_length_m=cfg.routing_max_cable_length,
            clearance_mm=cfg.routing_clearance,
            conduit_type=cfg.routing_conduit_type,
            vertical_penalty=cfg.routing_vertical_penalty,
            cross_corridor_penalty=cfg.routing_cross_corridor_penalty,
        )


# ════════════════════════════════════════════════════════════════════════════
# Route Result
# ════════════════════════════════════════════════════════════════════════════

@dataclass
class RouteResult:
    """
    Result of a cable routing operation.

    Attributes
    ----------
    waypoints : list of (x, y) tuples
        Ordered list of waypoints along the cable path.
    total_length_m : float
        Total cable length in metres.
    num_bends : int
        Number of direction changes in the path.
    max_segment_m : float
        Length of the longest straight segment.
    obstacles_avoided : int
        Number of obstacles the route avoids.
    valid : bool
        Whether the route meets all constraints.
    violations : list of str
        Any constraint violations found.
    """
    waypoints: List[Tuple[float, float]] = field(default_factory=list)
    total_length_m: float = 0.0
    num_bends: int = 0
    max_segment_m: float = 0.0
    obstacles_avoided: int = 0
    valid: bool = True
    violations: List[str] = field(default_factory=list)


# ════════════════════════════════════════════════════════════════════════════
# Engineering Router
# ════════════════════════════════════════════════════════════════════════════

class EngineeringRouter:
    """
    NEC/NFPA-compliant cable routing engine.

    Uses visibility graph + A* for obstacle-aware routing:
      1. Build a visibility graph from obstacle corners and route endpoints
      2. Find shortest path using A* with constraint-aware cost function
      3. Validate the path against NEC/NFPA constraints
      4. Post-process to add bend points and ensure clearance

    Falls back to Manhattan routing when no obstacles are present.
    """

    def __init__(self, constraints: RoutingConstraint = None):
        """
        Initialize the router.

        Parameters
        ----------
        constraints : RoutingConstraint, optional
            Routing constraints. Defaults to ProductionConfig values.
        """
        self.constraints = constraints or RoutingConstraint.from_production_config()
        self.obstacles: List[RoutingObstacle] = []
        self._obstacle_polys: List = []  # Shapely polygons with clearance
        self._cfg = get_production_config()
        # V31: Cached visibility-graph nodes for route_multi() reuse.
        # Invalidated whenever obstacles change (add/clear).
        self._vg_corner_nodes: Optional[List[Tuple[float, float]]] = None

    def add_obstacle(self, obstacle: RoutingObstacle):
        """Add an obstacle to the routing space."""
        self.obstacles.append(obstacle)
        # Pre-compute Shapely polygon with clearance
        clearance_m = self._get_clearance_m(obstacle) / 1000.0
        if SHAPELY_AVAILABLE:
            poly = obstacle.to_shapely_with_clearance(clearance_m)
            self._obstacle_polys.append(poly)
        # V31: Invalidate cached corner nodes
        self._vg_corner_nodes = None

    def add_obstacles(self, obstacles: List[RoutingObstacle]):
        """Add multiple obstacles."""
        for obs in obstacles:
            self.add_obstacle(obs)

    def clear_obstacles(self):
        """Remove all obstacles."""
        self.obstacles.clear()
        self._obstacle_polys.clear()
        # V31: Invalidate cached corner nodes
        self._vg_corner_nodes = None

    def route(self, start: Tuple[float, float],
              end: Tuple[float, float]) -> RouteResult:
        """
        Route a cable from start to end, avoiding obstacles.

        Parameters
        ----------
        start : (x, y) tuple
            Start point in metres.
        end : (x, y) tuple
            End point in metres.

        Returns
        -------
        RouteResult
            The routing result with waypoints and validation.
        """
        # No obstacles → direct Manhattan route
        if not self.obstacles:
            return self._manhattan_route(start, end)

        # Check direct line of sight
        if self._has_line_of_sight(start, end):
            result = RouteResult(
                waypoints=[start, end],
                total_length_m=math.hypot(end[0] - start[0], end[1] - start[1]),
                num_bends=0,
                max_segment_m=math.hypot(end[0] - start[0], end[1] - start[1]),
            )
            return self._validate_route(result)

        # Build visibility graph and find path via A*
        path = self._find_path_astar(start, end)
        if path:
            result = self._path_to_route_result(path)
            return self._validate_route(result)

        # Fallback: Manhattan routing
        log.warning("A* routing failed, falling back to Manhattan routing")
        return self._manhattan_route(start, end)

    def route_multi(self, points: List[Tuple[float, float]],
                    panel_pos: Tuple[float, float] = None) -> List[RouteResult]:
        """
        Route cables between multiple points using nearest-neighbour ordering.

        Parameters
        ----------
        points : list of (x, y) tuples
            Device positions in metres.
        panel_pos : (x, y) tuple, optional
            Panel position. If provided, routes start and end at panel.

        Returns
        -------
        list of RouteResult
            One RouteResult per segment.
        """
        if not points:
            return []

        # Nearest-neighbour ordering
        ordered = self._nearest_neighbour_order(points, panel_pos)

        # Route each segment
        results = []
        prev = panel_pos or ordered[0]

        for pt in ordered:
            if pt == prev:
                continue
            result = self.route(prev, pt)
            results.append(result)
            prev = pt

        # Return to panel
        if panel_pos and prev != panel_pos:
            result = self.route(prev, panel_pos)
            results.append(result)

        return results

    def _has_line_of_sight(self, start: Tuple[float, float],
                           end: Tuple[float, float]) -> bool:
        """
        Check if there is a clear line of sight between two points.

        A line of sight is clear if no obstacle polygon (with clearance)
        intersects the line segment.

        V14 Fix — Crosses vs Intersects:
        Previous code used ``line.crosses(poly)`` which returns False when
        the line segment is ENTIRELY inside the obstacle (e.g., both start
        and end are within the clearance zone of an elevator shaft).  In
        that scenario ``crosses`` reports a clear path even though the cable
        would run straight through the obstruction — a life-safety routing
        failure.

        Fix: Use ``line.intersects(poly) and not line.touches(poly)``.
        ``intersects`` catches every case (crossing, within, overlapping).
        ``touches`` is excluded so that a cable running along the clearance
        boundary (tangent) is still permitted — the clearance is already
        baked into the expanded polygon.
        """
        if SHAPELY_AVAILABLE and self._obstacle_polys:
            line = ShapelyLineString([start, end])
            for poly in self._obstacle_polys:
                if poly and line.intersects(poly) and not line.touches(poly):
                    return False
            return True

        # Fallback: check each obstacle AABB
        clearance_m = self.constraints.clearance_mm / 1000.0
        for obs in self.obstacles:
            if self._line_intersects_aabb(start, end,
                                          obs.expanded_bounds(clearance_m)):
                return False
        return True

    def _find_path_astar(self, start: Tuple[float, float],
                         end: Tuple[float, float]) -> Optional[List[Tuple[float, float]]]:
        """
        Find a path from start to end using A* on a visibility graph.

        The visibility graph is built from:
          - Start and end points
          - Expanded obstacle corner vertices (with clearance offset)

        Returns the path as a list of (x, y) waypoints, or None.
        """
        # V31: Build or reuse cached corner nodes (same obstacles → same corners)
        if self._vg_corner_nodes is None:
            corner_nodes: List[Tuple[float, float]] = []
            clearance_m = self.constraints.clearance_mm / 1000.0
            for obs in self.obstacles:
                # Add expanded corner points as potential waypoints
                minx, miny, maxx, maxy = obs.expanded_bounds(clearance_m)
                # Offset corners slightly outward
                offset = clearance_m * 0.5
                corners = [
                    (minx - offset, miny - offset),
                    (maxx + offset, miny - offset),
                    (maxx + offset, maxy + offset),
                    (minx - offset, maxy + offset),
                ]
                for corner in corners:
                    # Only add if not inside an obstacle
                    if not self._point_in_any_obstacle(corner):
                        corner_nodes.append(corner)
            self._vg_corner_nodes = corner_nodes
        # Visibility graph nodes = route endpoints + cached obstacle corners
        nodes = [start, end] + self._vg_corner_nodes

        # Build adjacency: edge exists if line of sight is clear
        adjacency: Dict[int, List[Tuple[int, float]]] = {i: [] for i in range(len(nodes))}

        for i in range(len(nodes)):
            for j in range(i + 1, len(nodes)):
                if self._has_line_of_sight(nodes[i], nodes[j]):
                    dist = math.hypot(nodes[j][0] - nodes[i][0],
                                      nodes[j][1] - nodes[i][1])
                    # Apply cost penalties
                    cost = dist * self._segment_cost_factor(nodes[i], nodes[j])
                    adjacency[i].append((j, cost))
                    adjacency[j].append((i, cost))

        # A* search
        def heuristic(node_idx):
            nx, ny = nodes[node_idx]
            ex, ey = end
            return math.hypot(ex - nx, ey - ny)

        # Priority queue: (f_score, counter, node_idx)
        counter = 0
        open_set = [(heuristic(0), counter, 0)]
        came_from: Dict[int, int] = {}
        g_score: Dict[int, float] = {0: 0.0}
        closed: Set[int] = set()

        while open_set:
            f, _, current = heapq.heappop(open_set)

            if current == 1:  # End node
                # Reconstruct path
                path = [nodes[current]]
                while current in came_from:
                    current = came_from[current]
                    path.append(nodes[current])
                path.reverse()
                return path

            if current in closed:
                continue
            closed.add(current)

            for neighbor, edge_cost in adjacency[current]:
                if neighbor in closed:
                    continue
                tentative_g = g_score[current] + edge_cost
                if tentative_g < g_score.get(neighbor, float('inf')):
                    came_from[neighbor] = current
                    g_score[neighbor] = tentative_g
                    f_score = tentative_g + heuristic(neighbor)
                    counter += 1
                    heapq.heappush(open_set, (f_score, counter, neighbor))

        return None  # No path found

    def _segment_cost_factor(self, p1: Tuple[float, float],
                             p2: Tuple[float, float]) -> float:
        """
        Compute cost multiplier for a segment based on routing constraints.

        Applies penalties for crossing near certain obstacle types.
        
        V12 Fix — Midpoint Cost Bypass:
        Previous code only checked the MIDPOINT of the segment against obstacles.
        A 50m cable running alongside an elevator shaft could have its midpoint
        in a safe zone, receiving NO penalty despite 90% of the cable being
        in the danger zone. This undermined the A* algorithm's cost function.
        
        Fix: Use Shapely LineString.intersection() to check the ENTIRE segment
        against obstacle clearance zones. If ANY part of the segment passes
        through the penalty zone, the penalty is applied.
        """
        cost = 1.0

        if SHAPELY_AVAILABLE:
            # V12 Fix: Check ENTIRE segment, not just midpoint
            segment_line = ShapelyLineString([p1, p2])
            
            for i, obs in enumerate(self.obstacles):
                if obs.passable:
                    # Check if the segment intersects this obstacle's penalty zone
                    # Use the pre-computed obstacle polygon with clearance
                    if i < len(self._obstacle_polys) and self._obstacle_polys[i]:
                        if segment_line.intersects(self._obstacle_polys[i]):
                            if obs.obstacle_type in ("stairwell", "elevator", "shaft"):
                                cost *= self.constraints.vertical_penalty
                            elif obs.obstacle_type == "hvac":
                                cost *= 1.2  # Slight penalty for HVAC proximity
        else:
            # Fallback when Shapely is not available: check midpoint AND quarter-points
            # This is less accurate than Shapely intersection but better than midpoint-only
            check_points = [
                ((p1[0] + p2[0]) / 2, (p1[1] + p2[1]) / 2),  # midpoint
                ((3*p1[0] + p2[0]) / 4, (3*p1[1] + p2[1]) / 4),  # quarter
                ((p1[0] + 3*p2[0]) / 4, (p1[1] + 3*p2[1]) / 4),  # three-quarter
            ]
            
            for obs in self.obstacles:
                if obs.passable:
                    for pt in check_points:
                        if self._point_near_obstacle(pt, obs):
                            if obs.obstacle_type in ("stairwell", "elevator", "shaft"):
                                cost *= self.constraints.vertical_penalty
                            elif obs.obstacle_type == "hvac":
                                cost *= 1.2
                            break  # One penalty per obstacle is enough

        return cost

    def _point_near_obstacle(self, point: Tuple[float, float],
                             obs: RoutingObstacle,
                             factor: float = 2.0) -> bool:
        """Check if a point is near an obstacle (within 2x clearance)."""
        clearance_m = self._get_clearance_m(obs) / 1000.0 * factor
        minx, miny, maxx, maxy = obs.expanded_bounds(clearance_m)
        return minx <= point[0] <= maxx and miny <= point[1] <= maxy

    def _point_in_any_obstacle(self, point: Tuple[float, float]) -> bool:
        """Check if a point is inside any obstacle (with clearance)."""
        if SHAPELY_AVAILABLE and self._obstacle_polys:
            sp = ShapelyPoint(point)
            for poly in self._obstacle_polys:
                if poly and sp.within(poly):
                    return True
            return False

        # Fallback
        clearance_m = self.constraints.clearance_mm / 1000.0
        for obs in self.obstacles:
            minx, miny, maxx, maxy = obs.expanded_bounds(clearance_m)
            if minx <= point[0] <= maxx and miny <= point[1] <= maxy:
                return True
        return False

    @staticmethod
    def _line_intersects_aabb(p1: Tuple[float, float],
                               p2: Tuple[float, float],
                               aabb: Tuple[float, float, float, float]) -> bool:
        """
        Check if a line segment intersects an AABB using parametric clipping.

        Uses the Liang-Barsky algorithm.
        """
        minx, miny, maxx, maxy = aabb
        dx = p2[0] - p1[0]
        dy = p2[1] - p1[1]

        p = [-dx, dx, -dy, dy]
        q = [p1[0] - minx, maxx - p1[0], p1[1] - miny, maxy - p1[1]]

        t0, t1 = 0.0, 1.0
        for i in range(4):
            if abs(p[i]) < 1e-12:
                if q[i] < 0:
                    return False
            else:
                t = q[i] / p[i]
                if p[i] < 0:
                    t0 = max(t0, t)
                else:
                    t1 = min(t1, t)
                if t0 > t1:
                    return False

        return True

    def _manhattan_route(self, start: Tuple[float, float],
                         end: Tuple[float, float]) -> RouteResult:
        """
        Simple Manhattan (L-shaped) routing fallback.
        Routes horizontal first, then vertical.
        """
        mid = (end[0], start[1])
        waypoints = [start, mid, end]

        # If start and end share x or y, simplify
        if abs(start[0] - end[0]) < 0.001:
            waypoints = [start, end]
        elif abs(start[1] - end[1]) < 0.001:
            waypoints = [start, end]

        total = sum(math.hypot(waypoints[i+1][0] - waypoints[i][0],
                               waypoints[i+1][1] - waypoints[i][1])
                    for i in range(len(waypoints) - 1))

        bends = len(waypoints) - 2
        max_seg = max(
            math.hypot(waypoints[i+1][0] - waypoints[i][0],
                       waypoints[i+1][1] - waypoints[i][1])
            for i in range(len(waypoints) - 1)
        )

        result = RouteResult(
            waypoints=waypoints,
            total_length_m=round(total, 4),
            num_bends=bends,
            max_segment_m=round(max_seg, 4),
        )
        return self._validate_route(result)

    def _path_to_route_result(self, path: List[Tuple[float, float]]) -> RouteResult:
        """Convert a path of waypoints to a RouteResult."""
        total = 0.0
        max_seg = 0.0
        for i in range(len(path) - 1):
            seg = math.hypot(path[i+1][0] - path[i][0],
                             path[i+1][1] - path[i][1])
            total += seg
            max_seg = max(max_seg, seg)

        result = RouteResult(
            waypoints=path,
            total_length_m=round(total, 4),
            num_bends=max(0, len(path) - 2),
            max_segment_m=round(max_seg, 4),
            obstacles_avoided=len(self.obstacles),
        )
        return result

    def _validate_route(self, result: RouteResult) -> RouteResult:
        """Validate a route against NEC/NFPA constraints."""
        violations = []

        # Check max cable length
        if result.total_length_m > self.constraints.max_cable_length_m:
            violations.append(
                f"Cable length {result.total_length_m:.1f}m exceeds max "
                f"{self.constraints.max_cable_length_m}m (NEC)"
            )

        # Check bend radius (approximate: check angle at each waypoint)
        for i in range(1, len(result.waypoints) - 1):
            angle = self._compute_turn_angle(
                result.waypoints[i-1], result.waypoints[i], result.waypoints[i+1]
            )
            if angle < 90:  # Sharp turn
                min_radius = self.constraints.bend_radius_mm / 1000.0
                violations.append(
                    f"Sharp turn ({angle:.0f}°) at waypoint {i} — "
                    f"may violate min bend radius {self.constraints.bend_radius_mm}mm"
                )

        # Check clearance from obstacles
        clearance_m = self.constraints.clearance_mm / 1000.0
        for obs in self.obstacles:
            if obs.passable:
                continue
            for i in range(len(result.waypoints) - 1):
                if self._line_intersects_aabb(
                    result.waypoints[i], result.waypoints[i+1],
                    obs.expanded_bounds(clearance_m * 0.5)  # Reduced for segment check
                ):
                    violations.append(
                        f"Route segment {i} too close to {obs.obstacle_type} "
                        f"obstacle (clearance {self.constraints.clearance_mm}mm)"
                    )
                    break  # One violation per obstacle is enough

        result.violations = violations
        result.valid = len(violations) == 0
        return result

    @staticmethod
    def _compute_turn_angle(p1, p2, p3) -> float:
        """Compute the turn angle at p2 between p1-p2-p3 in degrees."""
        v1 = (p1[0] - p2[0], p1[1] - p2[1])
        v2 = (p3[0] - p2[0], p3[1] - p2[1])

        dot = v1[0] * v2[0] + v1[1] * v2[1]
        cross = v1[0] * v2[1] - v1[1] * v2[0]

        angle = math.degrees(math.atan2(abs(cross), dot))
        return angle

    @staticmethod
    def _nearest_neighbour_order(points: List[Tuple[float, float]],
                                  start: Tuple[float, float] = None) -> List[Tuple[float, float]]:
        """Order points using nearest-neighbour heuristic."""
        if not points:
            return []

        remaining = list(points)
        ordered = []
        current = start or remaining[0]

        if start and start in remaining:
            remaining.remove(start)

        while remaining:
            nearest = min(remaining, key=lambda p:
                          math.hypot(p[0] - current[0], p[1] - current[1]))
            ordered.append(nearest)
            remaining.remove(nearest)
            current = nearest

        return ordered

    def _get_clearance_m(self, obs: RoutingObstacle) -> float:
        """Get clearance for an obstacle in mm."""
        if obs.clearance is not None:
            return obs.clearance
        return self._cfg.obstacle_clearance(obs.obstacle_type)


# ════════════════════════════════════════════════════════════════════════════
# Self-test
# ════════════════════════════════════════════════════════════════════════════

def _self_test():
    """Run self-test for EngineeringRouter."""
    print("=" * 60)
    print("Engineering Router — Self-Test")
    print("=" * 60)

    # ── Basic routing (no obstacles) ──
    router = EngineeringRouter()
    result = router.route(start=(0.0, 0.0), end=(10.0, 5.0))
    assert len(result.waypoints) >= 2, "Should have at least 2 waypoints"
    assert result.total_length_m > 0, "Should have positive length"
    assert result.valid, f"Route should be valid: {result.violations}"
    print(f"  No-obstacle route: {result.waypoints}, length={result.total_length_m:.2f}m")
    print("  [PASS] Basic routing without obstacles")

    # ── Manhattan routing (horizontal/vertical) ──
    result2 = router.route(start=(0.0, 0.0), end=(10.0, 0.0))
    assert abs(result2.total_length_m - 10.0) < 0.01, "Straight line should be 10m"
    print("  [PASS] Straight line routing")

    # ── Routing with obstacles ──
    router2 = EngineeringRouter()
    wall = RoutingObstacle(
        obstacle_type="wall",
        x=4.5, y=-1.0, width=0.2, height=12.0  # Vertical wall blocking path
    )
    router2.add_obstacle(wall)

    result3 = router2.route(start=(0.0, 5.0), end=(10.0, 5.0))
    assert len(result3.waypoints) >= 2, "Should find a path"
    print(f"  Obstacle route: {len(result3.waypoints)} waypoints, "
          f"length={result3.total_length_m:.2f}m")
    print("  [PASS] Routing with obstacles")

    # ── Line of sight check ──
    los_clear = router2._has_line_of_sight((0.0, 5.0), (3.0, 5.0))
    assert los_clear, "Should have LOS before wall"
    los_blocked = router2._has_line_of_sight((0.0, 5.0), (10.0, 5.0))
    assert not los_blocked, "Should NOT have LOS through wall"
    print("  [PASS] Line-of-sight checking")

    # ── Obstacle type clearances ──
    cfg = get_production_config()
    assert cfg.obstacle_clearance("sprinkler") == 450.0, "Sprinkler clearance"
    assert cfg.obstacle_clearance("hvac") == 150.0, "HVAC clearance"
    print("  [PASS] Obstacle type clearances")

    # ── Routing constraints ──
    rc = RoutingConstraint.from_production_config()
    assert rc.bend_radius_mm == 300.0, "Default bend radius"
    assert rc.max_cable_length_m == 300.0, "Default max cable length"
    assert rc.conduit_type == "EMT", "Default conduit type"
    print("  [PASS] Routing constraints from ProductionConfig")

    # ── Multi-point routing ──
    router3 = EngineeringRouter()
    points = [(2.0, 2.0), (8.0, 2.0), (5.0, 8.0)]
    results = router3.route_multi(points, panel_pos=(0.0, 0.0))
    assert len(results) >= 3, "Should have segments for all devices + return"
    total_cable = sum(r.total_length_m for r in results)
    print(f"  Multi-point: {len(results)} segments, total={total_cable:.2f}m")
    print("  [PASS] Multi-point routing")

    # ── Route validation ──
    router4 = EngineeringRouter(constraints=RoutingConstraint(max_cable_length_m=5.0))
    long_result = router4.route(start=(0.0, 0.0), end=(20.0, 0.0))
    assert not long_result.valid, "Should violate max cable length"
    assert any("exceeds max" in v for v in long_result.violations), \
        f"Expected max length violation: {long_result.violations}"
    print("  [PASS] Route validation (max length violation)")

    # ── AABB intersection ──
    assert EngineeringRouter._line_intersects_aabb(
        (0, 0), (10, 10), (4, 4, 6, 6)), "Should intersect"
    assert not EngineeringRouter._line_intersects_aabb(
        (0, 0), (2, 2), (5, 5, 8, 8)), "Should not intersect"
    print("  [PASS] AABB intersection detection")

    # ── Turn angle computation ──
    angle = EngineeringRouter._compute_turn_angle((0, 0), (5, 0), (5, 5))
    assert abs(angle - 90.0) < 1.0, f"90° turn expected, got {angle}"
    angle2 = EngineeringRouter._compute_turn_angle((0, 0), (5, 0), (10, 0))
    assert abs(angle2 - 180.0) < 1.0, f"180° straight expected, got {angle2}"
    print("  [PASS] Turn angle computation")

    print("\n" + "=" * 60)
    print("Engineering Router Self-Test: PASS")
    print("=" * 60)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    _self_test()
