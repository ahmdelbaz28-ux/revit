"""Strict geometry utilities."""

from __future__ import annotations

from typing import Dict, List, Sequence, Tuple


Point2D = Tuple[float, float]


class GeometryValidationError(ValueError):
    pass


def normalize_polygon(points):
    if points and points[0] == points[-1]:
        points = list(points[:-1])
    return [tuple(point) for point in points]


def signed_area(points):
    total = 0.0
    for index in range(len(points)):
        x1, y1 = points[index]
        x2, y2 = points[(index + 1) % len(points)]
        total += (x1 * y2) - (x2 * y1)
    return total / 2.0


def _orientation(a, b, c):
    return (b[1] - a[1]) * (c[0] - b[0]) - (b[0] - a[0]) * (c[1] - b[1])


def _on_segment(a, b, c):
    return (
        min(a[0], c[0]) <= b[0] <= max(a[0], c[0]) and
        min(a[1], c[1]) <= b[1] <= max(a[1], c[1])
    )


def _segments_intersect(p1, q1, p2, q2):
    o1 = _orientation(p1, q1, p2)
    o2 = _orientation(p1, q1, q2)
    o3 = _orientation(p2, q2, p1)
    o4 = _orientation(p2, q2, q1)

    if (o1 > 0 > o2 or o1 < 0 < o2) and (o3 > 0 > o4 or o3 < 0 < o4):
        return True

    if o1 == 0 and _on_segment(p1, p2, q1):
        return True
    if o2 == 0 and _on_segment(p1, q2, q1):
        return True
    if o3 == 0 and _on_segment(p2, p1, q2):
        return True
    if o4 == 0 and _on_segment(p2, q1, q2):
        return True

    return False


def validate_polygon(points):
    points = normalize_polygon(points)
    if len(points) < 3:
        raise GeometryValidationError("polygon must contain at least 3 points")
    if len(set(points)) < 3:
        raise GeometryValidationError("polygon points must include at least 3 unique points")

    segment_count = len(points)
    for i in range(segment_count):
        a1 = points[i]
        a2 = points[(i + 1) % segment_count]
        for j in range(i + 1, segment_count):
            if abs(i - j) <= 1 or (i == 0 and j == segment_count - 1):
                continue
            b1 = points[j]
            b2 = points[(j + 1) % segment_count]
            if _segments_intersect(a1, a2, b1, b2):
                raise GeometryValidationError("polygon must not self-intersect")

    if abs(signed_area(points)) < 1e-9:
        raise GeometryValidationError("polygon area must be non-zero")

    return points


def polygon_area(points):
    points = validate_polygon(points)
    return abs(signed_area(points))


def bounding_box(points):
    points = validate_polygon(points)
    xs = [point[0] for point in points]
    ys = [point[1] for point in points]
    return {
        "min_x": min(xs),
        "min_y": min(ys),
        "max_x": max(xs),
        "max_y": max(ys),
        "width_m": max(xs) - min(xs),
        "depth_m": max(ys) - min(ys),
    }
