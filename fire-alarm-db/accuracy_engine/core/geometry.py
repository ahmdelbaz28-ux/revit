from shapely.geometry import Polygon, Point, MultiPoint
from typing import List, Tuple

def create_polygon(coords: List[Tuple[float, float]]) -> Polygon:
    return Polygon(coords)

def is_point_inside(poly: Polygon, point: Tuple[float, float]) -> bool:
    return poly.contains(Point(point))

def clip_points_to_polygon(points: List[Tuple[float, float]], poly: Polygon) -> List[Tuple[float, float]]:
    return [p for p in points if poly.contains(Point(p))]

def smart_grid(poly: Polygon, step: float = 5.0) -> List[Tuple[float, float]]:
    minx, miny, maxx, maxy = poly.bounds
    points = []
    x = minx
    while x <= maxx:
        y = miny
        while y <= maxy:
            p = Point(x, y)
            if poly.contains(p):
                points.append((x, y))
            y += step
        x += step
    return points

def coverage_radius(device_type: str) -> float:
    return {"smoke": 7.5, "heat": 6.0}.get(device_type, 7.5)

def distance(p1: Tuple[float, float], p2: Tuple[float, float]) -> float:
    from math import sqrt
    return sqrt((p1[0]-p2[0])**2 + (p1[1]-p2[1])**2)