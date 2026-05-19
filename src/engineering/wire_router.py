"""
engineering/wire_router.py
==========================
A* grid routing for actual cable paths — obstacle avoidance, preferred
corridors, bend penalties.

Inputs:
  - occupancy_grid: 2-D uint8 (0=free, 255=blocked walls/columns)
  - preferred_mask: 2-D uint8 (0=normal, 255=cable tray / corridor)
  - start, goal: (row, col)

Returns the routed path as list[(row,col)] plus length in cells.
"""
from __future__ import annotations
import heapq, math
from dataclasses import dataclass
import numpy as np


@dataclass
class RoutedPath:
    path: list             # list[(row, col)]
    length_cells: float
    length_m:    float
    bends:       int
    cells_in_preferred: int

def route_cable(occupancy_grid: np.ndarray,
                preferred_mask: np.ndarray | None,
                start: tuple[int,int],
                goal:  tuple[int,int],
                cell_size_m: float = 0.1,
                cost_blocked: float = 1e9,
                cost_free:    float = 1.0,
                cost_preferred: float = 0.4,
                bend_penalty:   float = 0.2,
                ) -> RoutedPath | None:
    H, W = occupancy_grid.shape
    if not _in_bounds(start, H, W) or not _in_bounds(goal, H, W): return None
    if occupancy_grid[goal] == 255: return None

    pref = preferred_mask if preferred_mask is not None else np.zeros_like(occupancy_grid)

    # 8-connected grid
    dirs = [(-1,0),(1,0),(0,-1),(0,1),(-1,-1),(-1,1),(1,-1),(1,1)]

    def heur(a, b):
        dr = abs(a[0]-b[0]); dc = abs(a[1]-b[1])
        return (dr+dc) + (math.sqrt(2)-2)*min(dr,dc)

    open_pq = [(heur(start, goal), 0.0, start, None)]
    came = {}
    g = {start: 0.0}
    parent_dir = {}

    while open_pq:
        _, gc, cur, prev_d = heapq.heappop(open_pq)
        if cur == goal:
            return _reconstruct(came, cur, occupancy_grid, pref, cell_size_m)
        if gc > g.get(cur, float('inf')): continue
        for d in dirs:
            nb = (cur[0]+d[0], cur[1]+d[1])
            if not _in_bounds(nb, H, W): continue
            if occupancy_grid[nb] == 255: continue
            step = math.sqrt(2) if d[0] and d[1] else 1.0
            c = cost_preferred if pref[nb] == 255 else cost_free
            move_cost = step * c
            if prev_d is not None and d != prev_d:
                move_cost += bend_penalty
            new_g = gc + move_cost
            if new_g < g.get(nb, float('inf')):
                g[nb] = new_g; came[nb] = cur; parent_dir[nb] = d
                f = new_g + heur(nb, goal)
                heapq.heappush(open_pq, (f, new_g, nb, d))
    return None


def _in_bounds(p, H, W): return 0 <= p[0] < H and 0 <= p[1] < W


def _reconstruct(came, end, occ, pref, cell_size):
    path = [end]
    while end in came:
        end = came[end]; path.append(end)
    path.reverse()
    # metrics
    length = 0.0; bends = 0; in_pref = 0
    prev_d = None
    for i in range(1, len(path)):
        a, b = path[i-1], path[i]
        d = (b[0]-a[0], b[1]-a[1])
        length += math.sqrt(2) if d[0] and d[1] else 1.0
        if prev_d is not None and d != prev_d: bends += 1
        prev_d = d
        if pref[b] == 255: in_pref += 1
    return RoutedPath(path, length, round(length*cell_size, 2),
                      bends, in_pref)
