from math import sqrt
from shapely.geometry import Polygon, Point
from typing import List, Tuple

def coverage_radius(device_type: str) -> float:
    return {"smoke": 7.5, "heat": 6.0}.get(device_type, 7.5)

def points_covered_by_candidate(candidate: tuple, uncovered_points: list, device_type: str = "smoke") -> int:
    radius = coverage_radius(device_type)
    count = 0
    for point in uncovered_points:
        dist = sqrt((candidate[0] - point[0])**2 + (candidate[1] - point[1])**2)
        if dist <= radius:
            count += 1
    return count

def greedy_coverage_selection(candidates: list, polygon_coords: list, device_type: str = "smoke", min_coverage: float = 0.90) -> list:
    poly = Polygon(polygon_coords)
    if not poly.is_valid or poly.is_empty:
        return []

    minx, miny, maxx, maxy = poly.bounds
    sample_points = []
    step = 1.0
    x = minx
    while x <= maxx:
        y = miny
        while y <= maxy:
            p = Point(x, y)
            if poly.contains(p):
                sample_points.append((x, y))
            y += step
        x += step

    total_points = len(sample_points)
    if total_points == 0:
        return []

    uncovered = set(range(total_points))
    selected_candidates = []

    while len(uncovered) > total_points * (1 - min_coverage):
        best_candidate = None
        best_covered = 0

        for c in candidates:
            radius = coverage_radius(device_type)
            covered = 0
            for idx in uncovered:
                point = sample_points[idx]
                dist = sqrt((c[0] - point[0])**2 + (c[1] - point[1])**2)
                if dist <= radius:
                    covered += 1

            if covered > best_covered:
                best_covered = covered
                best_candidate = c

        if best_candidate is None or best_covered == 0:
            break

        selected_candidates.append({"x": best_candidate[0], "y": best_candidate[1], "type": device_type})

        radius = coverage_radius(device_type)
        to_remove = set()
        for idx in uncovered:
            point = sample_points[idx]
            dist = sqrt((best_candidate[0] - point[0])**2 + (best_candidate[1] - point[1])**2)
            if dist <= radius:
                to_remove.add(idx)
        uncovered -= to_remove

    return selected_candidates