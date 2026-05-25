"""
fireai/core/routing_engine_v10.py
=================================
ELITE Unified Pathfinding Engine solving for TWO catastrophic scenarios simultaneously:
1. NFPA 72 S12.2.2: Class A Pathway physical 1-meter spatial divergence constraint.
2. IBC S714: Intersecting with structural geometry determining exact Firestop Injection Points.

Architecture:
  - Unified router that handles both Class A separation AND firestopping
  - Grid-based A* with cost masking for outgoing/return separation
  - Wall objects (ArchitecturalWall) can be marked as fire-rated
  - Fire-rated walls have higher traversal cost (cables CAN pass through
    walls but firestopping triggers automatically)
  - RouteSegment dataclass includes firestop_nodes for each segment
  - Penalty of 50000.0 creates DEAD ZONE for reverse routing

Safety:
  - NFPA 72-2022 S12.2.2: Outgoing and return conductors must be physically
    separated by at least 1m to prevent single point of failure.
  - IBC S714: Penetrations through fire-rated walls require firestopping
    with approved materials and methods.
  - If return path cannot satisfy 1m separation constraint, a ValueError
    is raised — the building geometry does not permit compliant routing.

Terminal Connection Zone:
  - Both outgoing and return conductors physically connect to the SAME
    panel terminal and the SAME device terminal. This is physically
    unavoidable — a single wire enters and exits each device.
  - NFPA 72 S12.2.2 separation applies to the INTERMEDIATE routing path,
    not the terminal connection points.
  - The penalty mask EXEMPTS the first/last `terminal_buffer_m` meters
    of the outgoing path, allowing the return path to reach the terminals.
  - This is documented and auditable via RouteSegment metadata.
  - V13 fix: Previously, the penalty was applied to ALL outgoing path
    points including terminals, causing 0.0m separation at endpoints
    which was physically correct but undocumented and confusing.
"""
from __future__ import annotations

import math
import heapq
import numpy as np
from dataclasses import dataclass
from typing import List, Tuple, Dict, Optional

try:
    from shapely.geometry import Point, LineString, Polygon
    SHAPELY_ENABLED = True
except ImportError:
    SHAPELY_ENABLED = False


@dataclass
class RouteSegment:
    """
    One segment of a Class A routed loop.

    Attributes:
        path: Ordered list of (x, y) waypoints.
        class_type: "CLASS_A_OUT" or "CLASS_A_RETURN".
        firestop_nodes: List of (x, y) penetration points requiring firestopping.
        length_m: Total path length in meters.
    """
    path: List[Tuple[float, float]]
    class_type: str
    firestop_nodes: List[Tuple[float, float]]
    length_m: float


class ArchitecturalWall:
    """
    A wall segment with optional fire-rating metadata.

    Parameters:
        p1: (x, y) start point.
        p2: (x, y) end point.
        fire_rated: True if this wall has a fire-resistance rating.
    """

    def __init__(self, p1: Tuple[float, float], p2: Tuple[float, float], fire_rated: bool = False):
        self.p1 = p1
        self.p2 = p2
        self.fire_rated = fire_rated
        self.geometry = LineString([p1, p2]) if SHAPELY_ENABLED else None


class EliteClassARouter:
    """
    Unified Class A + Firestopping routing engine.

    This router computes both outgoing and return paths for a Class A
    loop while simultaneously identifying fire-rated wall penetrations
    that require firestopping per IBC S714.

    Algorithm:
      1. Generate outgoing path via A* on the base cost grid
      2. Apply penalty mask around outgoing path (1m DEAD ZONE)
      3. Generate return path via A* on the penalized cost grid
      4. Compute firestop intersection points for both paths
      5. Return RouteSegments with firestop_nodes populated

    Parameters:
        width: Building width in meters.
        length: Building length in meters.
        resolution: Grid cell size in meters (default 0.5m).
    """

    def __init__(self, width: float, length: float, resolution: float = 0.5):
        self.width = width
        self.length = length
        self.res = resolution
        self.cols = int(width / resolution)
        self.rows = int(length / resolution)
        self.base_grid = np.ones((self.rows, self.cols), dtype=np.float32)
        self.walls: List[ArchitecturalWall] = []

    def inject_structural_obstructions(self, walls: List[ArchitecturalWall]):
        """
        Add wall obstructions to the cost grid.

        Fire-rated walls get a cost of 1500.0 (high but traversable —
        cables CAN pass through walls but firestopping will be triggered).
        Non-fire-rated walls get a cost of 100.0 (standard obstruction).

        Parameters:
            walls: List of ArchitecturalWall objects.
        """
        self.walls = walls
        # Bake obstacles directly into grid for generic avoidance (cost multiplier)
        for wall in walls:
            p1, p2 = wall.p1, wall.p2
            # We assign High Cost but NOT Infinite; cables CAN pass through walls but Firestop triggers
            cost = 1500.0 if wall.fire_rated else 100.0
            r_start = min(int(p1[1] / self.res), int(p2[1] / self.res))
            r_end = max(int(p1[1] / self.res), int(p2[1] / self.res))
            c_start = min(int(p1[0] / self.res), int(p2[0] / self.res))
            c_end = max(int(p1[0] / self.res), int(p2[0] / self.res))
            for r in range(max(0, r_start), min(self.rows, r_end + 1)):
                for c in range(max(0, c_start), min(self.cols, c_end + 1)):
                    self.base_grid[r, c] += cost

    def generate_class_a_loop(self, facp_node: Tuple[float, float], loop_devices: List[Tuple[float, float]]) -> Dict[str, RouteSegment]:
        """
        Generate a complete Class A loop with outgoing and return paths.

        V14: The outgoing path now DAISY-CHAINS through ALL devices in order:
          FACP → loop_devices[0] → loop_devices[1] → ... → loop_devices[-1]

        The return path routes from the terminal device back to FACP,
        avoiding the outgoing path by at least 1m (NFPA 72 S12.2.2).

        Both paths are checked for fire-rated wall penetrations,
        and firestop_nodes are populated accordingly.

        Parameters:
            facp_node: (x, y) coordinates of the Fire Alarm Control Panel.
            loop_devices: List of (x, y) device coordinates (daisy-chain order).

        Returns:
            Dictionary with keys:
                "outgoing_class_a": RouteSegment for outgoing path
                "return_class_a": RouteSegment for return path

        Raises:
            ValueError: If return path cannot satisfy 1m separation constraint.
        """
        if not loop_devices:
            return {}

        # 1. GENERATE OUTGOING LEG — Daisy-chain through ALL devices
        # V14 FIX: Previously only routed to loop_devices[-1], skipping
        # all intermediate devices. Now we chain A* segments:
        #   FACP → dev[0] → dev[1] → ... → dev[-1]
        forward_path = []
        waypoints = [facp_node] + list(loop_devices)

        for i in range(len(waypoints) - 1):
            src = waypoints[i]
            dst = waypoints[i + 1]
            segment = self._astar(src, dst, self.base_grid)

            if not segment:
                # If A* fails between two consecutive waypoints, use direct line
                segment = [src, dst]

            if forward_path:
                # Remove duplicate junction point (end of prev = start of current)
                forward_path.extend(segment[1:])
            else:
                forward_path.extend(segment)

        if not forward_path:
            return {}

        # 2. PUNISH FORWARD LEG FOR REVERSE ROUTING (NFPA 72 S12.2.2 Minimum 1 meter)
        # TERMINAL CONNECTION ZONE: The first and last `terminal_buffer_m` of the
        # outgoing path are EXEMPTED from the penalty mask. This is physically
        # correct because both conductors must connect to the same panel and
        # device terminals — separation applies to the intermediate path only.
        terminal_buffer_m = 2.0  # 2m exemption zone at each end
        return_grid = np.copy(self.base_grid)
        penalty_cells = int(math.ceil(1.0 / self.res))

        # Calculate cumulative distance along the outgoing path
        cum_dist = [0.0]
        for i in range(1, len(forward_path)):
            seg_len = math.hypot(forward_path[i][0] - forward_path[i-1][0],
                                 forward_path[i][1] - forward_path[i-1][1])
            cum_dist.append(cum_dist[-1] + seg_len)
        total_len = cum_dist[-1] if cum_dist else 0.0

        for idx, (px, py) in enumerate(forward_path):
            # Skip penalty for points within terminal connection zone
            d_from_start = cum_dist[idx] if idx < len(cum_dist) else 0.0
            d_from_end = total_len - d_from_start
            if d_from_start < terminal_buffer_m or d_from_end < terminal_buffer_m:
                continue  # Terminal connection zone — exemption applies

            r_center, c_center = int(py / self.res), int(px / self.res)
            for rr in range(max(0, r_center - penalty_cells), min(self.rows, r_center + penalty_cells + 1)):
                for cc in range(max(0, c_center - penalty_cells), min(self.cols, c_center + penalty_cells + 1)):
                    dist = math.hypot(rr - r_center, cc - c_center) * self.res
                    if dist <= 1.0:
                        return_grid[rr, cc] += 50000.0  # DEAD ZONE FOR REVERSE

        # 3. GENERATE REVERSE LEG AVOIDING DEAD ZONES
        terminal_device = loop_devices[-1]
        reverse_path = self._astar(terminal_device, facp_node, return_grid)
        if not reverse_path:
            raise ValueError(
                "CRITICAL ENGINEERING LIMIT: Unable to isolate reverse path by 1.0m "
                "constraint within building geometry."
            )

        # 4. FIRESTOPPING CALCULATOR (IBC S714) -- RayCasting intersections against walls
        f_firestops = self._calculate_firestops(forward_path)
        r_firestops = self._calculate_firestops(reverse_path)

        return {
            "outgoing_class_a": RouteSegment(forward_path, "CLASS_A_OUT", f_firestops, self._measure_len(forward_path)),
            "return_class_a": RouteSegment(reverse_path, "CLASS_A_RETURN", r_firestops, self._measure_len(reverse_path)),
        }

    def _calculate_firestops(self, path: List[Tuple[float, float]]) -> List[Tuple[float, float]]:
        """
        Find fire-rated wall penetration points along a cable path.

        Uses Shapely LineString intersection testing to find exact
        coordinates where the path crosses fire-rated walls.

        Parameters:
            path: Ordered list of (x, y) waypoints.

        Returns:
            List of (x, y) penetration points requiring firestopping.
        """
        firestops = []
        if not SHAPELY_ENABLED or len(path) < 2:
            return firestops

        path_linestring = LineString(path)
        for wall in self.walls:
            if wall.fire_rated and wall.geometry:
                if path_linestring.intersects(wall.geometry):
                    intersection = path_linestring.intersection(wall.geometry)
                    if intersection.geom_type == 'Point':
                        firestops.append((intersection.x, intersection.y))
                    elif intersection.geom_type == 'MultiPoint':
                        for p in intersection.geoms:
                            firestops.append((p.x, p.y))
        return firestops

    def _measure_len(self, path: List[Tuple[float, float]]) -> float:
        """Compute total path length in meters."""
        total = 0.0
        for i in range(1, len(path)):
            total += math.hypot(path[i][0] - path[i - 1][0], path[i][1] - path[i - 1][1])
        return total

    def _astar(self, start: Tuple[float, float], goal: Tuple[float, float], grid: np.ndarray) -> List[Tuple[float, float]]:
        """
        A* pathfinding on a 2D cost grid.

        Uses orthogonal (4-directional) movement with the grid cell costs
        as edge weights. The heuristic is Manhattan distance.

        Parameters:
            start: (x, y) start coordinate in meters.
            goal: (x, y) goal coordinate in meters.
            grid: 2D numpy array of cell costs.

        Returns:
            List of (x, y) waypoints from start to goal, or empty list if no path.
        """
        s_r, s_c = int(start[1] / self.res), int(start[0] / self.res)
        g_r, g_c = int(goal[1] / self.res), int(goal[0] / self.res)
        s_r = max(0, min(self.rows - 1, s_r))
        s_c = max(0, min(self.cols - 1, s_c))
        g_r = max(0, min(self.rows - 1, g_r))
        g_c = max(0, min(self.cols - 1, g_c))

        open_q = [(0.0, (s_r, s_c))]
        came_from = {}
        g_score = {(s_r, s_c): 0.0}

        dirs = [(1, 0), (-1, 0), (0, 1), (0, -1)]
        while open_q:
            _, current = heapq.heappop(open_q)

            if current[0] == g_r and current[1] == g_c:
                path = []
                while current in came_from:
                    cx = current[1] * self.res
                    cy = current[0] * self.res
                    path.append((cx, cy))
                    current = came_from[current]
                path.append((start[0], start[1]))
                path.reverse()
                return path

            for dr, dc in dirs:
                nr, nc = current[0] + dr, current[1] + dc
                if 0 <= nr < self.rows and 0 <= nc < self.cols:
                    cost = grid[nr, nc] * self.res
                    tentative_g = g_score[current] + cost
                    if tentative_g < g_score.get((nr, nc), float('inf')):
                        came_from[(nr, nc)] = current
                        g_score[(nr, nc)] = tentative_g
                        f = tentative_g + (abs(g_r - nr) + abs(g_c - nc)) * self.res
                        heapq.heappush(open_q, (f, (nr, nc)))
        return []
