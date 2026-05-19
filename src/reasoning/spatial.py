"""
reasoning/spatial.py
====================
Geometric reasoning utilities — distances, coverage, line-of-sight.
All inputs are in DRAWING units (mm by default); convert at the call site.
"""
from __future__ import annotations
import math
from dataclasses import dataclass
from typing import Iterable

import numpy as np


@dataclass
class Point:
    x: float; y: float
    def __iter__(self): yield self.x; yield self.y


def euclid(a, b) -> float:
    return math.hypot(a[0]-b[0], a[1]-b[1])


def pairwise_min_distance(points: list[tuple[float,float]]) -> list[tuple[int,int,float]]:
    """For each point, find its nearest neighbour. Returns (i, j, dist)."""
    if len(points) < 2: return []
    arr = np.asarray(points, dtype=np.float32)
    out = []
    for i, p in enumerate(arr):
        d = np.linalg.norm(arr - p, axis=1)
        d[i] = np.inf
        j = int(np.argmin(d))
        out.append((i, j, float(d[j])))
    return out


def max_gap_to_neighbour(points: list[tuple[float,float]]) -> float:
    """The largest gap between any point and its nearest neighbour.
    If this exceeds the code's max_spacing, layout is non-compliant."""
    if len(points) < 2: return float("inf")
    return max(d for _,_,d in pairwise_min_distance(points))


def uncovered_area_estimate(points: list[tuple[float,float]],
                            radius: float,
                            bounds: tuple[float,float,float,float],
                            grid: int = 200) -> float:
    """Monte-Carlo-ish grid sampling: fraction of room not within `radius` of any point.
    bounds = (x0,y0,x1,y1).
    """
    x0,y0,x1,y1 = bounds
    if not points: return 1.0
    xs = np.linspace(x0, x1, grid)
    ys = np.linspace(y0, y1, grid)
    X, Y = np.meshgrid(xs, ys)
    covered = np.zeros_like(X, dtype=bool)
    for px, py in points:
        covered |= ((X-px)**2 + (Y-py)**2 <= radius**2)
    return float(1.0 - covered.mean())


def polygon_area(poly: list[tuple[float,float]]) -> float:
    n = len(poly)
    if n < 3: return 0.0
    s = 0.0
    for i in range(n):
        x1,y1 = poly[i]; x2,y2 = poly[(i+1)%n]
        s += x1*y2 - x2*y1
    return abs(s)/2.0


def segment_intersects(a, b, c, d) -> bool:
    """Do segments a-b and c-d intersect? (used for line-of-sight blocking)."""
    def ccw(p,q,r): return (r[1]-p[1])*(q[0]-p[0]) > (q[1]-p[1])*(r[0]-p[0])
    return ccw(a,c,d) != ccw(b,c,d) and ccw(a,b,c) != ccw(a,b,d)


def has_line_of_sight(p1, p2, obstacles: Iterable[tuple]) -> bool:
    """obstacles: iterable of (x1,y1,x2,y2) wall segments."""
    for x1,y1,x2,y2 in obstacles:
        if segment_intersects(p1, p2, (x1,y1), (x2,y2)):
            return False
    return True


def travel_distance(start, target, walls) -> float:
    """Manhattan-ish proxy — for a real corridor graph use a routing engine.
    Here: if line-of-sight clear → euclidean; else → 1.4 × euclidean (heuristic)."""
    base = euclid(start, target)
    return base if has_line_of_sight(start, target, walls) else base * 1.4
