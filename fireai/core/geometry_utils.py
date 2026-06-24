"""geometry_utils.py — Computational Geometry for FireAI
=====================================================
Point-in-polygon, polygon area, centroid, bounds, convex hull,
grid generation, and polygon constructors.

Supports L-shape, U-shape, and any rectilinear/non-convex polygon.
Zero external dependencies — pure Python.

NFPA 72 References:
  - Table 17.6.3.1.1: Coverage radius by ceiling height
  - Section 17.6.3.1.1: Min wall distance 0.10m (4 inches)
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import List, Optional, Sequence, Tuple

Point = Tuple[float, float]
Polygon = List[Point]


# ─────────────────────────────────────────────
# Core Primitives
# ─────────────────────────────────────────────


def _ensure_closed(poly: Polygon) -> Polygon:
    """Return polygon with first vertex appended as last (if not already closed)."""
    if poly[0] != poly[-1]:
        return poly + [poly[0]]
    return poly


def shoelace_area(poly: Polygon) -> float:
    """Signed area via Shoelace formula.
    Positive -> CCW, Negative -> CW.
    """
    n = len(poly)
    if n < 3:
        return 0.0
    s = 0.0
    for i in range(n):
        x0, y0 = poly[i]
        x1, y1 = poly[(i + 1) % n]
        s += (x0 * y1) - (x1 * y0)
    return s / 2.0


def polygon_area(poly: Polygon) -> float:
    """Absolute area — always positive."""
    return abs(shoelace_area(poly))


def polygon_centroid(poly: Polygon) -> Point:
    """True geometric centroid via Shoelace.
    Falls back to arithmetic mean for degenerate polygons.
    """
    n = len(poly)
    if n == 0:
        raise ValueError("Empty polygon.")
    if n == 1:
        return poly[0]

    signed = shoelace_area(poly)
    if abs(signed) < 1e-10:
        # Degenerate — arithmetic mean
        cx = sum(p[0] for p in poly) / n
        cy = sum(p[1] for p in poly) / n
        return (cx, cy)

    cx = cy = 0.0
    for i in range(n):
        x0, y0 = poly[i]
        x1, y1 = poly[(i + 1) % n]
        cross = x0 * y1 - x1 * y0
        cx += (x0 + x1) * cross
        cy += (y0 + y1) * cross

    factor = 1.0 / (6.0 * signed)
    return (cx * factor, cy * factor)


def polygon_bounds(poly: Polygon) -> Tuple[float, float, float, float]:
    """Returns (min_x, min_y, max_x, max_y)."""
    xs = [p[0] for p in poly]
    ys = [p[1] for p in poly]
    return min(xs), min(ys), max(xs), max(ys)


def polygon_perimeter(poly: Polygon) -> float:
    """Total perimeter length of the polygon."""
    n = len(poly)
    total = 0.0
    for i in range(n):
        x0, y0 = poly[i]
        x1, y1 = poly[(i + 1) % n]
        total += math.hypot(x1 - x0, y1 - y0)
    return total


# ─────────────────────────────────────────────
# Point-in-Polygon  (Ray Casting + Edge Cases)
# ─────────────────────────────────────────────


def point_in_polygon(
    point: Point,
    poly: Polygon,
    include_boundary: bool = True,
    tolerance: float = 1e-9,
) -> bool:
    """Ray casting algorithm with robust boundary handling.

    Args:
        point:            (x, y) to test.
        poly:             Polygon vertices (open or closed).
        include_boundary: True -> points on edges/vertices return True.
        tolerance:        Numerical epsilon for boundary detection.

    Returns:
        True if point is inside or on boundary (per include_boundary).

    """
    px, py = point
    poly = _ensure_closed(poly)
    n = len(poly) - 1  # last == first

    # -- Fast bounding-box rejection --
    min_x, min_y, max_x, max_y = polygon_bounds(poly[:-1])
    if not (min_x - tolerance <= px <= max_x + tolerance and min_y - tolerance <= py <= max_y + tolerance):
        return False

    # -- Boundary check --
    if include_boundary:
        for i in range(n):
            if _point_on_segment(point, poly[i], poly[i + 1], tolerance):
                return True

    # -- Ray casting (horizontal ray -> +x) --
    inside = False
    for i in range(n):
        x0, y0 = poly[i]
        x1, y1 = poly[i + 1]

        # Skip horizontal edges
        if abs(y1 - y0) < tolerance:
            continue

        # Check if ray crosses this edge
        if min(y0, y1) < py <= max(y0, y1):
            x_intersect = x0 + (py - y0) * (x1 - x0) / (y1 - y0)
            if px < x_intersect:
                inside = not inside

    return inside


def _point_on_segment(
    p: Point,
    a: Point,
    b: Point,
    tol: float = 1e-9,
) -> bool:
    """True if p lies on segment [a, b]."""
    px, py = p
    ax, ay = a
    bx, by = b

    # Cross product — collinearity test
    cross = abs((bx - ax) * (py - ay) - (by - ay) * (px - ax))
    if cross > tol * max(1.0, math.hypot(bx - ax, by - ay)):
        return False

    # Dot product — within segment bounds
    if not (min(ax, bx) - tol <= px <= max(ax, bx) + tol and min(ay, by) - tol <= py <= max(ay, by) + tol):
        return False

    return True


def points_in_polygon(
    points: Sequence[Point],
    poly: Polygon,
    include_boundary: bool = True,
) -> List[bool]:
    """Test multiple points against the same polygon.
    Batch wrapper — not a NumPy-vectorised implementation.
    """
    closed = _ensure_closed(poly)
    polygon_bounds(closed[:-1])
    return [point_in_polygon(p, closed, include_boundary) for p in points]


# ─────────────────────────────────────────────
# Polygon Validation
# ─────────────────────────────────────────────


@dataclass
class ValidationResult:
    valid: bool
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)


def validate_polygon(poly: Polygon, min_area: float = 0.01) -> ValidationResult:
    """Validate polygon integrity: minimum vertices, no duplicates,
    no self-intersection, minimum area.

    V11 Enhancement (Consultant #5 Criticism #4 - partially accepted):
      - Added non-consecutive duplicate vertex detection (not just consecutive)
      - Added near-duplicate vertex warning (within 0.05m)
    """
    errors: List[str] = []
    warnings: List[str] = []

    if len(poly) < 3:
        errors.append(f"Polygon has {len(poly)} vertices - minimum is 3.")
        return ValidationResult(False, errors, warnings)

    # Duplicate consecutive vertices
    for i in range(len(poly)):
        a = poly[i]
        b = poly[(i + 1) % len(poly)]
        if math.hypot(b[0] - a[0], b[1] - a[1]) < 1e-9:
            errors.append(f"Duplicate consecutive vertices at index {i}: {a}.")

    # V11: Non-consecutive near-duplicate vertices (within 0.05m)
    # These cause numerical instability in algorithms and should be simplified.
    near_dup_threshold = 0.05  # 5cm
    for i in range(len(poly)):
        for j in range(i + 2, len(poly)):
            if j == (i + len(poly) - 1) % len(poly):
                continue  # Skip first-last pair (they're adjacent via closure)
            dist = math.hypot(poly[j][0] - poly[i][0], poly[j][1] - poly[i][1])
            if dist < near_dup_threshold and dist > 1e-9:
                warnings.append(
                    f"Near-duplicate vertices at index {i} and {j}: "
                    f"distance={dist:.4f}m < {near_dup_threshold}m. "
                    f"Consider simplification."
                )

    # Self-intersection (O(n^2) - acceptable for room-scale polygons)
    n = len(poly)
    for i in range(n):
        for j in range(i + 2, n):
            if j == (i + n - 1) % n:
                continue
            if _segments_intersect(poly[i], poly[(i + 1) % n], poly[j], poly[(j + 1) % n]):
                errors.append(f"Self-intersection between edge {i}->{(i + 1) % n} and edge {j}->{(j + 1) % n}.")

    area = polygon_area(poly)
    if area < min_area:
        errors.append(f"Area {area:.4f}m2 is below minimum {min_area}m2.")

    if len(poly) > 50:
        warnings.append(f"Polygon has {len(poly)} vertices - consider simplification.")

    if polygon_perimeter(poly) > 500:
        warnings.append("Perimeter > 500m - verify units are in metres.")

    # Shapely-based self-intersection check (more robust than O(n²) pure Python).
    # Falls back to the existing _segments_intersect check if Shapely unavailable.
    try:
        from shapely.geometry import Polygon as ShapelyPolygon

        shapely_poly = ShapelyPolygon(poly)
        if not shapely_poly.is_valid:
            # Shapely's is_valid catches self-intersection, ring orientation,
            # and other geometric issues that the O(n²) check may miss.
            explanation = (
                shapely_poly.explain_validity if hasattr(shapely_poly, "explain_validity") else "unknown reason"
            )
            errors.append(
                f"Polygon is invalid per Shapely: {explanation}. "
                f"Self-intersecting polygons produce wrong area calculations, "
                f"which leads to incorrect detector counts."
            )
    except ImportError:
        # V114 FIX: Shapely unavailable = geometric validation INCOMPLETE.
        # The O(n²) segment intersection check above does NOT catch all
        # self-intersection cases. Must warn, not silently pass.
        import logging as _logging

        _logging.getLogger(__name__).warning(
            "Shapely not available — polygon is_valid check SKIPPED. "
            "The segment intersection check above may miss some self-intersection "
            "cases. Install Shapely for full geometric validation."
        )

    return ValidationResult(not errors, errors, warnings)


def _segments_intersect(p1: Point, p2: Point, p3: Point, p4: Point) -> bool:
    """True if segment p1-p2 properly intersects p3-p4."""

    def cross2d(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

    d1 = cross2d(p3, p4, p1)
    d2 = cross2d(p3, p4, p2)
    d3 = cross2d(p1, p2, p3)
    d4 = cross2d(p1, p2, p4)

    # Proper intersection: segments straddle each other
    if ((d1 > 0 > d2) or (d2 > 0 > d1)) and ((d3 > 0 > d4) or (d4 > 0 > d3)):
        return True

    # Collinear overlap check
    if abs(d1) < 1e-10 and abs(d2) < 1e-10 and abs(d3) < 1e-10 and abs(d4) < 1e-10:
        for a, b, c in [
            (p1, p2, p3),
            (p1, p2, p4),
            (p3, p4, p1),
            (p3, p4, p2),
        ]:
            if (
                min(a[0], b[0]) - 1e-9 <= c[0] <= max(a[0], b[0]) + 1e-9
                and min(a[1], b[1]) - 1e-9 <= c[1] <= max(a[1], b[1]) + 1e-9
            ):
                return True

    # Endpoint-on-endpoint (tangent intersection)
    if abs(d1) < 1e-10 and _point_on_segment(p1, p3, p4):
        return True
    if abs(d2) < 1e-10 and _point_on_segment(p2, p3, p4):
        return True
    if abs(d3) < 1e-10 and _point_on_segment(p3, p1, p2):
        return True
    if abs(d4) < 1e-10 and _point_on_segment(p4, p1, p2):
        return True

    return False


# ─────────────────────────────────────────────
# Polygon Winding & Orientation
# ─────────────────────────────────────────────


def is_clockwise(poly: Polygon) -> bool:
    """True if polygon vertices are in clockwise order."""
    return shoelace_area(poly) < 0


def ensure_ccw(poly: Polygon) -> Polygon:
    """Returns polygon with CCW orientation (required for NFPA grid scanning)."""
    if is_clockwise(poly):
        return list(reversed(poly))
    return poly


# ─────────────────────────────────────────────
# Polygon Constructors
# ─────────────────────────────────────────────


def rect_polygon(width: float, height: float, origin: Point = (0, 0)) -> Polygon:
    """Create a rectangular polygon (CCW order).

    Args:
        width:  Rectangle width (x-axis).
        height: Rectangle height (y-axis).
        origin: Bottom-left corner (default (0,0)).

    Returns:
        List of 4 vertices in CCW order.

    Raises:
        ValueError: If width or height is not positive.

    """
    if width <= 0:
        raise ValueError(f"Width must be positive, got {width}")
    if height <= 0:
        raise ValueError(f"Height must be positive, got {height}")
    x0, y0 = origin
    return [
        (x0, y0),
        (x0 + width, y0),
        (x0 + width, y0 + height),
        (x0, y0 + height),
    ]


def l_shape_polygon(width: float, height: float, cut_w: float, cut_h: float) -> Polygon:
    """Create an L-shaped polygon (CCW order).
    Cutout is from the top-right corner.

    Args:
        width:  Full width of the bounding rectangle.
        height: Full height of the bounding rectangle.
        cut_w:  Width of the cutout rectangle.
        cut_h:  Height of the cutout rectangle.

    Returns:
        6-vertex polygon in CCW order.

    Raises:
        ValueError: If cutout exceeds bounds.

    Examples:
        >>> l_shape_polygon(6, 4, 2, 2)
        [(0,0), (6,0), (6,2), (4,2), (4,4), (0,4)]

    """
    if cut_w > width:
        raise ValueError(f"Cutout width {cut_w} exceeds total width {width}")
    if cut_h > height:
        raise ValueError(f"Cutout height {cut_h} exceeds total height {height}")
    return [
        (0, 0),
        (width, 0),
        (width, height - cut_h),
        (width - cut_w, height - cut_h),
        (width - cut_w, height),
        (0, height),
    ]


# ─────────────────────────────────────────────
# Grid Generation Inside Polygon
# ─────────────────────────────────────────────


def grid_points_in_polygon(
    poly: Polygon,
    step: float = 0.5,
    margin: float = 0.0,
) -> List[Point]:
    """Generate a regular grid of points inside the polygon, useful for
    coverage verification and detector candidate generation.

    The grid starts at (min_x + margin, min_y + margin) and steps
    through the bounding box, keeping only points that fall inside
    the polygon (with margin offset from boundary).

    Args:
        poly:   Polygon vertices (open or closed).
        step:   Grid spacing in metres. Must be > 0.
        margin: Inset from the polygon boundary in metres.
                Use 0.10 for NFPA 72 §17.6.3.1.1 wall distance compliance.

    Returns:
        List of (x, y) points inside the polygon.

    Raises:
        ValueError: If step <= 0 or margin < 0.

    """
    if step <= 0:
        raise ValueError(f"Step must be positive, got {step}")
    if margin < 0:
        raise ValueError(f"Margin must be non-negative, got {margin}")

    min_x, min_y, max_x, max_y = polygon_bounds(poly)

    # Apply margin: shift grid start/end inward
    x_start = min_x + margin
    y_start = min_y + margin
    x_end = max_x - margin
    y_end = max_y - margin

    if x_start >= x_end or y_start >= y_end:
        return []  # Margin too large — no valid grid points

    points: List[Point] = []
    x = x_start
    while x <= x_end + 1e-9:
        y = y_start
        while y <= y_end + 1e-9:
            p = (round(x, 10), round(y, 10))
            if point_in_polygon(p, poly, include_boundary=True):
                points.append(p)
            y += step
        x += step

    return points


# ─────────────────────────────────────────────
# Shape Classification
# ─────────────────────────────────────────────


def is_rectangular(poly: Polygon, tolerance: float = 0.05) -> bool:
    """Check if a polygon is effectively rectangular (axis-aligned).

    A polygon is rectangular if:
      - It has exactly 4 vertices.
      - Its area equals the bounding rectangle area (within tolerance).
      - All edges are axis-aligned (horizontal or vertical).

    This is used by FloorAnalyser to determine whether a room can be
    handled by the rectangular DensityOptimizer directly, or needs
    polygon-aware placement (bounding rect + filter).

    Args:
        poly:       Polygon vertices (open or closed).
        tolerance:  Relative tolerance for area comparison (default 5%).

    Returns:
        True if the polygon is effectively rectangular.

    Examples:
        >>> is_rectangular([(0,0), (6,0), (6,4), (0,4)])
        True
        >>> is_rectangular([(0,0), (6,0), (6,2), (4,2), (4,4), (0,4)])
        False

    """
    # Strip closing vertex if duplicated
    clean = list(poly)
    if len(clean) > 1 and clean[0] == clean[-1]:
        clean = clean[:-1]

    if len(clean) != 4:
        return False

    # Compare polygon area to bounding rectangle area
    poly_area = polygon_area(clean)
    min_x, min_y, max_x, max_y = polygon_bounds(clean)
    bbox_area = (max_x - min_x) * (max_y - min_y)

    if bbox_area < 1e-10:
        return False

    ratio = poly_area / bbox_area
    if abs(ratio - 1.0) > tolerance:
        return False

    # All edges must be axis-aligned (horizontal or vertical)
    for i in range(4):
        x0, y0 = clean[i]
        x1, y1 = clean[(i + 1) % 4]
        dx = abs(x1 - x0)
        dy = abs(y1 - y0)
        # One of dx, dy must be ~0 (axis-aligned edge)
        if dx > 1e-6 and dy > 1e-6:
            return False

    return True


def bounding_rect_dimensions(poly: Polygon) -> Tuple[float, float, float, float]:
    """Compute bounding rectangle dimensions and origin from a polygon.

    Returns the width, length (height), and origin (bottom-left corner)
    of the axis-aligned bounding rectangle that encloses the polygon.

    This is used by FloorAnalyser to convert non-rectangular room
    polygons into (width, length) for the DensityOptimizer, which
    only handles rectangular rooms.

    Args:
        poly: Polygon vertices (open or closed).

    Returns:
        (width, height, origin_x, origin_y) of the bounding rectangle.

    Examples:
        >>> bounding_rect_dimensions([(0,0), (6,0), (6,2), (4,2), (4,4), (0,4)])
        (6.0, 4.0, 0.0, 0.0)

    """
    min_x, min_y, max_x, max_y = polygon_bounds(poly)
    return (max_x - min_x, max_y - min_y, min_x, min_y)


# ─────────────────────────────────────────────
# Convex Hull  (Andrew's Monotone Chain)
# ─────────────────────────────────────────────


def convex_hull_2d(points: Sequence[Point]) -> Polygon:
    """Compute the convex hull of a set of 2D points.
    Uses Andrew's Monotone Chain algorithm. O(n log n).

    Useful for:
      - Minimum bounding circle calculation
      - Simplifying complex polygons for quick overlap tests
      - Determining room shape characteristics

    Args:
        points: Sequence of (x, y) points.

    Returns:
        Convex hull as a CCW polygon (open — first != last).

    Raises:
        ValueError: If fewer than 3 non-collinear points are provided.

    """
    pts = sorted(set(points))  # Remove duplicates and sort by (x, y)
    if len(pts) <= 1:
        return list(pts)

    def _cross(o: Point, a: Point, b: Point) -> float:
        """2D cross product of vectors OA and OB. Positive = CCW turn."""
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

    # Build lower hull
    lower: List[Point] = []
    for p in pts:
        while len(lower) >= 2 and _cross(lower[-2], lower[-1], p) <= 0:
            lower.pop()
        lower.append(p)

    # Build upper hull
    upper: List[Point] = []
    for p in reversed(pts):
        while len(upper) >= 2 and _cross(upper[-2], upper[-1], p) <= 0:
            upper.pop()
        upper.append(p)

    # Remove last point of each half (it's repeated)
    hull = lower[:-1] + upper[:-1]

    if len(hull) < 3:
        raise ValueError(f"Cannot compute convex hull: only {len(hull)} unique hull vertices (points may be collinear)")

    return hull


# ─────────────────────────────────────────────
# Room Geometry Sanitization (V11 - Consultant #5 Criticism #4)
# ─────────────────────────────────────────────


@dataclass
class SanitizeResult:
    """Result from room geometry sanitization."""

    coords: List[Point]
    was_modified: bool = False
    modifications: List[str] = field(default_factory=list)
    rejected: bool = False
    rejection_reason: Optional[str] = None


def sanitize_room_geometry(coords: List[Point], min_area: float = 1.0) -> SanitizeResult:
    """Sanitize room geometry from Revit before processing.

    Revit models frequently contain geometry errors that, if passed
    directly to the coverage engine, produce incorrect results that
    appear valid. This function acts as a gate, rejecting or cleaning
    geometry before it enters FireAI.

    V11 Enhancement (Consultant #5 Criticism #4 - partially accepted):
      The existing code already had:
        - Min area check (1.0m2) in floor_analyser.py
        - Self-intersection repair (buffer(0)) in floor_analyser.py
        - Duplicate detection in validate_polygon()
      This function adds:
        - Simplification of near-duplicate vertices (0.05m tolerance)
        - MultiPolygon rejection (disconnected rooms)
        - Zero/negative area check AFTER cleaning
        - Centralized sanitization (replacing scattered checks)

    Args:
        coords: Room polygon vertices from Revit.
        min_area: Minimum acceptable room area in sqm.
            Default 1.0 sqm — rooms below this are likely Revit
            modeling errors (shafts, column pockets, etc.).

    Returns:
        SanitizeResult with:
          - coords: Cleaned coordinates (if not rejected)
          - was_modified: True if any changes were made
          - modifications: List of changes applied
          - rejected: True if room should be rejected entirely
          - rejection_reason: Why the room was rejected

    Examples:
        >>> result = sanitize_room_geometry([(0,0),(10,0),(10,8),(0,8)])
        >>> result.rejected
        False
        >>> result.coords
        [(0,0), (10,0), (10,8), (0,8)]

    """
    modifications: List[str] = []
    was_modified = False

    # Basic input validation
    if not coords or len(coords) < 3:
        return SanitizeResult(
            coords=coords,
            rejected=True,
            rejection_reason=f"Room has {len(coords) if coords else 0} vertices - minimum is 3.",
        )

    # Try Shapely-based sanitization (more robust)
    try:
        from shapely.geometry import Polygon as ShapelyPolygon

        poly = ShapelyPolygon(coords)

        # 1. Auto-repair self-intersecting polygons (common Revit error)
        if not poly.is_valid:
            poly = poly.buffer(0)
            modifications.append("Auto-repaired self-intersecting polygon (buffer(0))")
            was_modified = True
            if not poly.is_valid:
                return SanitizeResult(
                    coords=coords,
                    rejected=True,
                    rejection_reason="Room geometry is corrupted - auto-repair failed.",
                )

        # 2. Reject MultiPolygon (disconnected rooms must be analyzed separately)
        if poly.geom_type == "MultiPolygon":
            return SanitizeResult(
                coords=coords,
                rejected=True,
                rejection_reason=(
                    "Room is a MultiPolygon (disconnected parts). Each part must be analyzed as a separate room."
                ),
            )

        # 3. Check minimum area (likely Revit shaft or modeling error)
        if poly.area < min_area:
            return SanitizeResult(
                coords=coords,
                rejected=True,
                rejection_reason=(
                    f"Room area {poly.area:.2f} sqm is below minimum {min_area} sqm. "
                    f"Likely a Revit modeling error (shaft, column pocket, etc.)."
                ),
            )

        # 4. Simplify near-duplicate vertices (0.05m tolerance)
        #    Removes vertices that are very close together, which cause
        #    numerical instability in placement algorithms.
        original_n = len(poly.exterior.coords) - 1  # -1 for closing vertex
        simplified = poly.simplify(0.05, preserve_topology=True)
        simplified_n = len(simplified.exterior.coords) - 1

        if simplified_n < original_n:
            removed = original_n - simplified_n
            modifications.append(
                f"Simplified {removed} near-duplicate vertex/vertices ({original_n} -> {simplified_n})"
            )
            was_modified = True
            poly = simplified

        # 5. Validate the simplified polygon
        if not poly.is_valid or poly.area <= 0:
            return SanitizeResult(
                coords=coords,
                rejected=True,
                rejection_reason="Room geometry became invalid after simplification.",
            )

        # Return cleaned coordinates
        clean_coords = [(round(x, 6), round(y, 6)) for x, y in list(poly.exterior.coords)[:-1]]

        return SanitizeResult(
            coords=clean_coords,
            was_modified=was_modified,
            modifications=modifications,
        )

    except ImportError:
        # Shapely not available - fall back to basic pure-Python validation
        modifications.append("Shapely not available - using basic validation only")

        # Check for duplicate consecutive vertices
        clean = list(coords)
        i = 0
        while i < len(clean):
            next_i = (i + 1) % len(clean)
            if math.hypot(clean[next_i][0] - clean[i][0], clean[next_i][1] - clean[i][1]) < 1e-9:
                clean.pop(next_i if next_i < len(clean) else i)
                modifications.append(f"Removed duplicate vertex at index {i}")
                was_modified = True
            else:
                i += 1

        # Check area
        area = polygon_area(clean)
        if area < min_area:
            return SanitizeResult(
                coords=coords,
                rejected=True,
                rejection_reason=f"Room area {area:.2f} sqm below minimum {min_area} sqm.",
            )

        return SanitizeResult(
            coords=clean if was_modified else coords,
            was_modified=was_modified,
            modifications=modifications,
        )
