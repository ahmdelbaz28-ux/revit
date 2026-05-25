from shapely.geometry import Polygon, Point
from typing import List, Tuple

def generate_candidates(polygon_coords: List[Tuple[float, float]], step: float = 3.0) -> List[Tuple[float, float]]:
    poly = Polygon(polygon_coords)
    if not poly.is_valid or poly.is_empty:
        return []

    minx, miny, maxx, maxy = poly.bounds
    candidates = []

    x = minx + step/2
    while x <= maxx:
        y = miny + step/2
        while y <= maxy:
            p = Point(x, y)
            if poly.contains(p):
                candidates.append((x, y))
            y += step
        x += step

    return candidates

def generate_edge_candidates(polygon_coords: List[Tuple[float, float]], spacing: float = 2.0) -> List[Tuple[float, float]]:
    candidates = []
    for i in range(len(polygon_coords)):
        p1 = polygon_coords[i]
        p2 = polygon_coords[(i + 1) % len(polygon_coords)]
        dx = p2[0] - p1[0]
        dy = p2[1] - p1[1]
        length = ((dx**2 + dy**2) ** 0.5)
        if length == 0:
            continue
        num_steps = max(1, int(length / spacing))
        for j in range(num_steps + 1):
            t = j / num_steps
            candidates.append((p1[0] + t * dx, p1[1] + t * dy))
    return candidates

def generate_corridor_candidates(polygon_coords: List[Tuple[float, float]], spacing: float = 7.0) -> List[Tuple[float, float]]:
    xs = [p[0] for p in polygon_coords]
    ys = [p[1] for p in polygon_coords]
    min_x, max_x = min(xs), max(xs)
    min_y, max_y = min(ys), max(ys)
    candidates = []

    if (max_x - min_x) > (max_y - min_y):
        y_center = (min_y + max_y) / 2
        x = min_x + spacing/2
        while x <= max_x:
            candidates.append((x, y_center))
            x += spacing
    else:
        x_center = (min_x + max_x) / 2
        y = min_y + spacing/2
        while y <= max_y:
            candidates.append((x_center, y))
            y += spacing

    return candidates