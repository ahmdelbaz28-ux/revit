"""
QOMN-FIRE ORTHOGONAL 3D PATHFINDER ROUTING ENGINE
A* algorithm for conduit routing with NEC 360-degree bend limit enforcement.

BUG-5/16 FIX: bend_count now stores NUMBER of bends, not degrees.
Added bend_degrees field for the NEC 360-degree limit check.
BUG-20 FIX: Route length uses (path_points - 1) * step, not len(path) * step.
BUG-27 FIX: Conduit-type-appropriate trade size, not hardcoded "1/2".
"""

import heapq
import math
import logging
from typing import List, Tuple, Dict, Set
from qomn_fire.core.types import Point3D, ConduitType, ConduitRun, Fitting, FittingType
from qomn_fire.core.errors import Result, NECViolationError

logger = logging.getLogger("qomn_fire.routing")


class GridMap3D:
    def __init__(self, step_m: float = 0.5):
        self.step_m = step_m
        self.obstacles: Set[Tuple[int, int, int]] = set()

    def to_grid(self, p: Point3D) -> Tuple[int, int, int]:
        return (
            int(round(p.x / self.step_m)),
            int(round(p.y / self.step_m)),
            int(round(p.z / self.step_m))
        )

    def to_physical(self, gp: Tuple[int, int, int]) -> Point3D:
        return Point3D(
            gp[0] * self.step_m,
            gp[1] * self.step_m,
            gp[2] * self.step_m
        )

    def add_obstacle(self, p: Point3D):
        self.obstacles.add(self.to_grid(p))


# BUG-27 FIX: Map conduit type to appropriate default trade size.
# The original code hardcoded trade_size="1/2" regardless of conduit type.
# RMC (Rigid Metal Conduit) is typically 3/4" minimum; FMC starts at 1/2".
_DEFAULT_TRADE_SIZE = {
    ConduitType.EMT: "1/2",
    ConduitType.RMC: "3/4",
    ConduitType.FMC: "1/2",
}

def astar_route_3d(
    grid_map: GridMap3D,
    start: Point3D,
    end: Point3D,
    conduit: ConduitType,
    conduit_id: str,
    trade_size: str = ""
) -> Result[ConduitRun, NECViolationError]:
    g_start = grid_map.to_grid(start)
    g_end = grid_map.to_grid(end)

    # SAFETY FIX (V58): Validate start/end coordinates for NaN/Inf.
    # Per IEEE 754: NaN comparisons always return False — NaN coordinates
    # would silently bypass obstacle checks and produce invalid conduit paths.
    for label, pt in [("start", start), ("end", end)]:
        for coord_name, val in [("x", pt.x), ("y", pt.y), ("z", pt.z)]:
            if not math.isfinite(val):
                return Result(error=NECViolationError(
                    message=f"{label}.{coord_name}={val} is not finite (NaN or Inf). "
                            f"Conduit routing requires finite coordinates.",
                    code_ref="NEC Art 300.18",
                    remedy="Validate device positions before routing. Check for NaN in IFC parsing."
                ))

    if g_start in grid_map.obstacles or g_end in grid_map.obstacles:
        return Result(error=NECViolationError(
            message="Conduit terminal endpoints are blocked.",
            code_ref="NEC Art 300.18",
            remedy="Clear coordinate clearances or relocate the terminal devices."
        ))

    heap_counter = 0
    open_set = []
    heapq.heappush(open_set, (0.0, heap_counter, g_start))

    came_from: Dict[Tuple[int, int, int], Tuple[int, int, int]] = {}
    g_score: Dict[Tuple[int, int, int], float] = {g_start: 0.0}

    directions = [
        (1, 0, 0), (-1, 0, 0),
        (0, 1, 0), (0, -1, 0),
        (0, 0, 1), (0, 0, -1)
    ]

    # Safety limit: prevent infinite loops on very large grids
    MAX_ITERATIONS = 500000
    iterations = 0

    while open_set:
        iterations += 1
        if iterations > MAX_ITERATIONS:
            return Result(error=NECViolationError(
                message=f"A* pathfinding exceeded {MAX_ITERATIONS} iterations — grid too large or path too complex.",
                code_ref="NEC Art 300.18",
                remedy="Reduce grid size or clear structural blockings from grid boundaries."
            ))
        _, _, current = heapq.heappop(open_set)

        if current == g_end:
            path = [current]
            while current in came_from:
                current = came_from[current]
                path.append(current)
            path.reverse()

            pts = tuple([grid_map.to_physical(p) for p in path])

            # BUG-5/16 FIX: Count bends as NUMBER of 90-degree bends, not degrees.
            # NEC Article 358.26 states: 'not more than the equivalent of four
            # quarter bends (360 degrees total) between pull points.'
            # bend_count = number of individual 90-degree bends
            # bend_degrees = total cumulative bend angle in degrees
            bend_count = 0
            bend_degrees = 0
            fittings: List[Fitting] = []
            if len(pts) >= 3:
                prev_dir = (
                    pts[1].x - pts[0].x,
                    pts[1].y - pts[0].y,
                    pts[1].z - pts[0].z
                )
                for i in range(1, len(pts) - 1):
                    curr_dir = (
                        pts[i+1].x - pts[i].x,
                        pts[i+1].y - pts[i].y,
                        pts[i+1].z - pts[i].z
                    )
                    dot = prev_dir[0]*curr_dir[0] + prev_dir[1]*curr_dir[1] + prev_dir[2]*curr_dir[2]
                    mag_p = math.sqrt(prev_dir[0]**2 + prev_dir[1]**2 + prev_dir[2]**2)
                    mag_c = math.sqrt(curr_dir[0]**2 + curr_dir[1]**2 + curr_dir[2]**2)

                    if mag_p > 0 and mag_c > 0:
                        cos_a = dot / (mag_p * mag_c)
                        if abs(cos_a - 1.0) > 1e-4:
                            bend_count += 1
                            bend_degrees += 90
                            fittings.append(Fitting(FittingType.ELBOW_90, pts[i]))
                            prev_dir = curr_dir

            # BUG-20 FIX: Route length must use (path_points - 1) * step, not
            # len(path) * step. For a 5m straight line with 0.5m grid:
            #   Path = [0, 0.5, 1.0, ..., 5.0] = 11 points
            #   Distance = 10 steps * 0.5m = 5.0m (CORRECT)
            #   Old: 11 * 0.5 = 5.5m (WRONG — off by one grid step)
            num_segments = max(len(path) - 1, 0)
            tot_len_m = num_segments * grid_map.step_m
            tot_len_ft = tot_len_m * 3.28084

            # NEC Article 358.26: No more than 360 degrees of bends between pull points
            if bend_degrees > 360:
                return Result(error=NECViolationError(
                    message=f"Conduit run exceeds 360 degrees of bend limits "
                            f"({bend_degrees} degrees from {bend_count} bends). "
                            f"NEC Article 358.26 allows maximum 4 quarter bends.",
                    code_ref="NEC Article 358.26",
                    remedy="Install junction boxes to partition the conduit run segment."
                ))

            # BUG-27 FIX: Use conduit-type-appropriate trade size, not hardcoded "1/2"
            selected_trade_size = trade_size if trade_size else _DEFAULT_TRADE_SIZE.get(conduit, "1/2")

            run = ConduitRun(
                id=conduit_id,
                conduit_type=conduit,
                trade_size=selected_trade_size,
                points=pts,
                total_length_ft=tot_len_ft,
                bend_count=bend_count,
                bend_degrees=bend_degrees,
                fittings=tuple(fittings)
            )
            return Result(value=run)

        for dx, dy, dz in directions:
            neighbor = (current[0] + dx, current[1] + dy, current[2] + dz)
            if neighbor in grid_map.obstacles:
                continue

            tentative_g = g_score[current] + 1.0
            if tentative_g < g_score.get(neighbor, float('inf')):
                came_from[neighbor] = current
                g_score[neighbor] = tentative_g
                h = abs(neighbor[0]-g_end[0]) + abs(neighbor[1]-g_end[1]) + abs(neighbor[2]-g_end[2])
                f = tentative_g + h
                heap_counter += 1
                heapq.heappush(open_set, (f, heap_counter, neighbor))

    return Result(error=NECViolationError(
        message="No compliant orthogonal paths could be routed to targets.",
        code_ref="NEC Art 300.18",
        remedy="Clear structural blockings from grid boundaries."
    ))
