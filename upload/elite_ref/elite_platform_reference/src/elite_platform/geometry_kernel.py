"""Polygon-first geometry kernel."""

from __future__ import annotations

import math
from typing import Dict, Iterable, List, Sequence, Tuple

from .models import Point2D, RoomGeometry


def _signed_area(points: Sequence[Point2D]) -> float:
    total = 0.0
    for i in range(len(points)):
        x1, y1 = points[i]
        x2, y2 = points[(i + 1) % len(points)]
        total += (x1 * y2) - (x2 * y1)
    return total / 2.0


def validate_polygon(points: Sequence[Point2D]) -> None:
    if len(points) < 3:
        raise ValueError("polygon must contain at least 3 points")
    if abs(_signed_area(points)) < 1e-9:
        raise ValueError("polygon area is zero")
    for point in points:
        if len(point) != 2:
            raise ValueError("each polygon point must be 2D")


def polygon_area(points: Sequence[Point2D]) -> float:
    validate_polygon(points)
    return abs(_signed_area(points))


def bounding_box(points: Sequence[Point2D]) -> Dict[str, float]:
    validate_polygon(points)
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    return {
        "min_x": min(xs),
        "min_y": min(ys),
        "max_x": max(xs),
        "max_y": max(ys),
        "width_m": max(xs) - min(xs),
        "depth_m": max(ys) - min(ys),
    }


def centroid(points: Sequence[Point2D]) -> Point2D:
    validate_polygon(points)
    area_component = _signed_area(points)
    factor = 1.0 / (6.0 * area_component)
    cx = 0.0
    cy = 0.0
    for i in range(len(points)):
        x1, y1 = points[i]
        x2, y2 = points[(i + 1) % len(points)]
        cross = (x1 * y2) - (x2 * y1)
        cx += (x1 + x2) * cross
        cy += (y1 + y2) * cross
    return (cx * factor, cy * factor)


def point_in_polygon(point: Point2D, polygon: Sequence[Point2D]) -> bool:
    validate_polygon(polygon)
    x, y = point
    inside = False
    j = len(polygon) - 1
    for i in range(len(polygon)):
        xi, yi = polygon[i]
        xj, yj = polygon[j]
        intersects = ((yi > y) != (yj > y)) and (
            x < (xj - xi) * (y - yi) / ((yj - yi) or 1e-12) + xi
        )
        if intersects:
            inside = not inside
        j = i
    return inside


def derive_room_metrics(room: RoomGeometry) -> Dict[str, float]:
    box = bounding_box(room.polygon)
    return {
        "area_m2": polygon_area(room.polygon),
        "width_m": box["width_m"],
        "depth_m": box["depth_m"],
        "centroid_x": centroid(room.polygon)[0],
        "centroid_y": centroid(room.polygon)[1],
        "ceiling_height_m": room.ceiling_height_m,
    }


def candidate_points(room: RoomGeometry, spacing_m: float) -> List[Point2D]:
    if spacing_m <= 0:
        raise ValueError("spacing_m must be positive")
    box = bounding_box(room.polygon)
    points = []
    y = box["min_y"] + spacing_m / 2.0
    while y < box["max_y"]:
        x = box["min_x"] + spacing_m / 2.0
        while x < box["max_x"]:
            point = (round(x, 4), round(y, 4))
            if point_in_polygon(point, room.polygon):
                points.append(point)
            x += spacing_m
        y += spacing_m
    if not points:
        points.append(centroid(room.polygon))
    return points
