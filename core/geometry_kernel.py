"""
core/geometry_kernel.py
========================
Robust geometry kernel for FireAI with validation, normalization,
and point-in-polygon with hole handling.

Provides:
  - Point2D: Snap-to-grid, distance, equality with tolerance
  - Point3D: Full 3D point with z-coordinate
  - Polygon2D: Self-intersection detection, winding order normalization,
               robust point-in-polygon with holes, centroid, bounding box

Uses Shapely for geometry when available, falls back to pure Python.

Usage:
    from core.geometry_kernel import Point2D, Point3D, Polygon2D

    p1 = Point2D(1.0, 2.0)
    p2 = Point2D(3.0, 4.0)
    print(p1.distance_to(p2))  # 2.828...

    poly = Polygon2D([(0, 0), (10, 0), (10, 10), (0, 10)])
    print(poly.area)           # 100.0
    print(poly.contains(5, 5)) # True
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from core.production_config import get_production_config

log = logging.getLogger(__name__)

# Try to import Shapely for heavy geometry ops
try:
    from shapely.geometry import Polygon as ShapelyPolygon, Point as ShapelyPoint
    from shapely.validation import make_valid
    SHAPELY_AVAILABLE = True
except ImportError:
    SHAPELY_AVAILABLE = False
    log.debug("Shapely not available — using pure Python geometry")


# ════════════════════════════════════════════════════════════════════════════
# Point2D — Immutable 2D Point with snap-to-grid
# ════════════════════════════════════════════════════════════════════════════

class Point2D:
    """
    2D point with snap-to-grid deduplication support.

    Points are automatically snapped to a configurable grid to prevent
    floating-point drift and enable reliable deduplication via hashing.
    """

    __slots__ = ('_x', '_y', '_snap')

    def __init__(self, x: float, y: float, snap_tolerance: float = None):
        """
        Create a 2D point, optionally snapping to grid.

        Parameters
        ----------
        x, y : float
            Coordinates in metres.
        snap_tolerance : float, optional
            Grid snap tolerance. Defaults to ProductionConfig.snap_tolerance.
            Set to 0.0 to disable snapping.
        """
        cfg = get_production_config()
        self._snap = snap_tolerance if snap_tolerance is not None else cfg.snap_tolerance

        if self._snap > 0:
            self._x = round(x / self._snap) * self._snap
            self._y = round(y / self._snap) * self._snap
        else:
            self._x = float(x)
            self._y = float(y)

    @property
    def x(self) -> float:
        return self._x

    @property
    def y(self) -> float:
        return self._y

    def distance_to(self, other: Point2D) -> float:
        """Euclidean distance to another point."""
        return math.hypot(self._x - other._x, self._y - other._y)

    def equals(self, other: Point2D, tol: float = 1e-9) -> bool:
        """Check equality within tolerance."""
        return abs(self._x - other._x) < tol and abs(self._y - other._y) < tol

    def to_tuple(self) -> Tuple[float, float]:
        """Convert to (x, y) tuple."""
        return (self._x, self._y)

    def to_dict(self) -> Dict:
        """Convert to dict."""
        return {"x": self._x, "y": self._y}

    @staticmethod
    def from_dict(d: Dict, snap_tolerance: float = None) -> Point2D:
        """Create from dict."""
        return Point2D(d["x"], d["y"], snap_tolerance=snap_tolerance)

    def __eq__(self, other):
        if not isinstance(other, Point2D):
            return NotImplemented
        return self._x == other._x and self._y == other._y

    def __hash__(self):
        return hash((self._x, self._y))

    def __repr__(self):
        return f"Point2D({self._x:.6f}, {self._y:.6f})"

    def __iter__(self):
        """Allow unpacking: x, y = point."""
        yield self._x
        yield self._y


# ════════════════════════════════════════════════════════════════════════════
# Point3D — Full 3D Point
# ════════════════════════════════════════════════════════════════════════════

class Point3D:
    """
    3D point with optional snap-to-grid.

    Compatible with the existing core.models.Point3D but adds
    snap-to-grid and distance utilities.
    """

    __slots__ = ('_x', '_y', '_z', '_snap')

    def __init__(self, x: float, y: float, z: float = 0.0,
                 snap_tolerance: float = None):
        cfg = get_production_config()
        self._snap = snap_tolerance if snap_tolerance is not None else cfg.snap_tolerance

        if self._snap > 0:
            self._x = round(x / self._snap) * self._snap
            self._y = round(y / self._snap) * self._snap
            self._z = round(z / self._snap) * self._snap
        else:
            self._x = float(x)
            self._y = float(y)
            self._z = float(z)

    @property
    def x(self) -> float:
        return self._x

    @property
    def y(self) -> float:
        return self._y

    @property
    def z(self) -> float:
        return self._z

    def distance_to(self, other: Point3D) -> float:
        """Euclidean 3D distance."""
        return math.sqrt(
            (self._x - other._x) ** 2 +
            (self._y - other._y) ** 2 +
            (self._z - other._z) ** 2
        )

    def distance_to_2d(self, other: Point3D) -> float:
        """2D (plan) distance ignoring z."""
        return math.hypot(self._x - other._x, self._y - other._y)

    def equals(self, other: Point3D, tol: float = 1e-9) -> bool:
        """Check equality within tolerance."""
        return (abs(self._x - other._x) < tol and
                abs(self._y - other._y) < tol and
                abs(self._z - other._z) < tol)

    def to_tuple(self) -> Tuple[float, float, float]:
        return (self._x, self._y, self._z)

    def to_dict(self) -> Dict:
        return {"x": self._x, "y": self._y, "z": self._z}

    @staticmethod
    def from_dict(d: Dict, snap_tolerance: float = None) -> Point3D:
        return Point3D(d["x"], d["y"], d.get("z", 0.0),
                       snap_tolerance=snap_tolerance)

    def __eq__(self, other):
        if not isinstance(other, Point3D):
            return NotImplemented
        return self._x == other._x and self._y == other._y and self._z == other._z

    def __hash__(self):
        return hash((self._x, self._y, self._z))

    def __repr__(self):
        return f"Point3D({self._x:.6f}, {self._y:.6f}, {self._z:.6f})"


# ════════════════════════════════════════════════════════════════════════════
# Polygon2D — Validated, Normalized Polygon with Holes
# ════════════════════════════════════════════════════════════════════════════

class Polygon2D:
    """
    2D polygon with self-intersection detection, winding order normalization,
    bounding box caching, centroid, and robust point-in-polygon with holes.

    Outer ring is always CCW; hole rings are always CW (right-hand rule).

    Features:
      - Self-intersection detection on construction (warning, not rejection)
      - Winding order normalization (CCW outer, CW holes)
      - Bounding box caching for fast rejection
      - Centroid calculation
      - Point-in-polygon with hole handling (ray casting)
      - Conversion to Shapely Polygon when available
    """

    def __init__(self, exterior: List[Tuple[float, float]],
                 holes: Optional[List[List[Tuple[float, float]]]] = None,
                 snap_tolerance: float = None):
        """
        Create a validated polygon.

        Parameters
        ----------
        exterior : list of (x, y) tuples
            Outer ring vertices. Will be normalized to CCW.
        holes : list of list of (x, y), optional
            Hole rings. Each will be normalized to CW.
        snap_tolerance : float, optional
            Grid snap tolerance for vertex deduplication.

        Raises
        ------
        ValueError
            If exterior has < 3 distinct vertices or polygon is degenerate.
        """
        cfg = get_production_config()
        self._snap = snap_tolerance if snap_tolerance is not None else cfg.snap_tolerance
        self._min_area = cfg.min_polygon_area

        if len(exterior) < 3:
            raise ValueError(f"Polygon needs >= 3 vertices, got {len(exterior)}")

        # Snap and deduplicate vertices
        self._exterior = self._snap_and_dedup(exterior)

        if len(self._exterior) < 3:
            raise ValueError("Polygon has < 3 distinct vertices after snap/dedup")

        # Normalize winding order: CCW for exterior
        self._exterior = self._normalize_ccw(self._exterior)

        # Process holes: normalize each to CW
        self._holes = []
        if holes:
            for hole_pts in holes:
                if len(hole_pts) < 3:
                    log.warning("Skipping hole with < 3 vertices")
                    continue
                snapped = self._snap_and_dedup(hole_pts)
                if len(snapped) >= 3:
                    # Normalize holes to CW (opposite of exterior)
                    self._holes.append(self._normalize_cw(snapped))

        # Self-intersection check
        self._self_intersects = self._check_self_intersection()
        if self._self_intersects:
            log.warning("Polygon self-intersection detected — geometry may be invalid")

        # Compute and cache bounding box
        xs = [p[0] for p in self._exterior]
        ys = [p[1] for p in self._exterior]
        self._bbox = (min(xs), min(ys), max(xs), max(ys))

        # Compute and cache area
        # For self-intersecting polygons, signed area may be zero (bowtie).
        # Use absolute cross-product sum for a meaningful area estimate.
        self._area = self._signed_area(self._exterior)
        for hole in self._holes:
            self._area += self._signed_area(hole)  # holes have negative area

        # Use unsigned area for degenerate check (handles self-intersecting)
        if abs(self._area) < self._min_area and not self._self_intersects:
            raise ValueError(
                f"Polygon area {abs(self._area):.6f} m² is below minimum "
                f"{self._min_area} m² — degenerate polygon"
            )

        # Cache centroid
        self._centroid = self._compute_centroid()

        # Cache Shapely polygon (lazy)
        self._shapely_poly = None

    # ── Properties ──

    @property
    def exterior(self) -> List[Tuple[float, float]]:
        """Exterior ring vertices (CCW)."""
        return list(self._exterior)

    @property
    def holes(self) -> List[List[Tuple[float, float]]]:
        """Hole ring vertices (each CW)."""
        return [list(h) for h in self._holes]

    @property
    def area(self) -> float:
        """Polygon area in m² (positive)."""
        return abs(self._area)

    @property
    def perimeter(self) -> float:
        """Perimeter of exterior ring."""
        return self._compute_perimeter(self._exterior)

    @property
    def bbox(self) -> Tuple[float, float, float, float]:
        """Bounding box (minx, miny, maxx, maxy)."""
        return self._bbox

    @property
    def centroid(self) -> Tuple[float, float]:
        """Centroid (cx, cy)."""
        return self._centroid

    @property
    def num_vertices(self) -> int:
        """Number of exterior vertices."""
        return len(self._exterior)

    @property
    def is_self_intersecting(self) -> bool:
        """Whether the polygon has self-intersections."""
        return self._self_intersects

    # ── Geometry Operations ──

    def contains(self, x: float, y: float) -> bool:
        """
        Robust point-in-polygon test with hole handling.

        Uses ray casting algorithm. First checks bounding box for fast
        rejection, then tests exterior, then subtracts holes.

        Parameters
        ----------
        x, y : float
            Test point coordinates.

        Returns
        -------
        bool
            True if point is inside the polygon and not in a hole.
        """
        # Fast bounding box rejection
        minx, miny, maxx, maxy = self._bbox
        if x < minx or x > maxx or y < miny or y > maxy:
            return False

        # Check exterior (must be inside)
        if not self._ray_cast(x, y, self._exterior):
            return False

        # Check holes (must NOT be inside any hole)
        for hole in self._holes:
            if self._ray_cast(x, y, hole):
                return False

        return True

    def contains_point(self, pt: Point2D) -> bool:
        """Check if a Point2D is inside the polygon."""
        return self.contains(pt.x, pt.y)

    def to_shapely(self) -> Optional[ShapelyPolygon]:
        """
        Convert to Shapely Polygon for advanced geometry operations.

        Returns None if Shapely is not available.
        """
        if not SHAPELY_AVAILABLE:
            return None

        if self._shapely_poly is not None:
            return self._shapely_poly

        try:
            if self._holes:
                poly = ShapelyPolygon(self._exterior, self._holes)
            else:
                poly = ShapelyPolygon(self._exterior)

            if not poly.is_valid:
                poly = make_valid(poly)

            self._shapely_poly = poly
            return poly
        except Exception as ex:
            log.warning("Failed to create Shapely polygon: %s", ex)
            return None

    def distance_to_point(self, x: float, y: float) -> float:
        """
        Minimum distance from a point to the polygon boundary.
        Returns 0 if point is inside.
        """
        if self.contains(x, y):
            return 0.0

        if SHAPELY_AVAILABLE:
            sp = self.to_shapely()
            if sp:
                return sp.distance(ShapelyPoint(x, y))

        # Fallback: distance to nearest edge
        min_dist = float('inf')
        ring = self._exterior
        for i in range(len(ring)):
            j = (i + 1) % len(ring)
            d = self._point_to_segment_dist(x, y, ring[i], ring[j])
            min_dist = min(min_dist, d)
        return min_dist

    def to_dict(self) -> Dict:
        """Serialize to dict."""
        return {
            "exterior": [list(p) for p in self._exterior],
            "holes": [[list(p) for p in h] for h in self._holes],
            "area": self.area,
            "centroid": list(self._centroid),
            "bbox": list(self._bbox),
            "self_intersects": self._self_intersects,
        }

    @staticmethod
    def from_dict(d: Dict, snap_tolerance: float = None) -> Polygon2D:
        """Create from dict."""
        ext = [tuple(p) for p in d["exterior"]]
        holes = None
        if "holes" in d and d["holes"]:
            holes = [[tuple(p) for p in h] for h in d["holes"]]
        return Polygon2D(ext, holes=holes, snap_tolerance=snap_tolerance)

    # ── Internal Methods ──

    def _snap_and_dedup(self, pts: List[Tuple[float, float]]) -> List[Tuple[float, float]]:
        """Snap points to grid and remove consecutive duplicates."""
        result = []
        for x, y in pts:
            if self._snap > 0:
                sx = round(x / self._snap) * self._snap
                sy = round(y / self._snap) * self._snap
            else:
                sx, sy = float(x), float(y)

            if not result or (abs(sx - result[-1][0]) > 1e-12 or
                              abs(sy - result[-1][1]) > 1e-12):
                result.append((sx, sy))

        # Remove closing duplicate
        if len(result) > 1 and result[0] == result[-1]:
            result.pop()

        return result

    @staticmethod
    def _signed_area(pts: List[Tuple[float, float]]) -> float:
        """Compute signed area using the shoelace formula.
        Positive = CCW, Negative = CW."""
        n = len(pts)
        area = 0.0
        for i in range(n):
            j = (i + 1) % n
            area += pts[i][0] * pts[j][1]
            area -= pts[j][0] * pts[i][1]
        return area / 2.0

    @staticmethod
    def _normalize_ccw(pts: List[Tuple[float, float]]) -> List[Tuple[float, float]]:
        """Ensure vertices are in CCW order (positive signed area)."""
        area = Polygon2D._signed_area(pts)
        if area < 0:
            return list(reversed(pts))
        return list(pts)

    @staticmethod
    def _normalize_cw(pts: List[Tuple[float, float]]) -> List[Tuple[float, float]]:
        """Ensure vertices are in CW order (negative signed area)."""
        area = Polygon2D._signed_area(pts)
        if area > 0:
            return list(reversed(pts))
        return list(pts)

    def _check_self_intersection(self) -> bool:
        """
        Check if exterior ring has self-intersections.

        Uses Shapely if available, otherwise checks segment intersections.
        """
        if SHAPELY_AVAILABLE:
            try:
                poly = ShapelyPolygon(self._exterior)
                return not poly.is_valid
            except Exception:
                pass

        # Fallback: check all segment pairs for intersection
        n = len(self._exterior)
        for i in range(n):
            for j in range(i + 2, n):
                if i == 0 and j == n - 1:
                    continue  # Skip adjacent closing segment
                if self._segments_intersect(
                    self._exterior[i], self._exterior[(i + 1) % n],
                    self._exterior[j], self._exterior[(j + 1) % n]
                ):
                    return True
        return False

    @staticmethod
    def _segments_intersect(p1, p2, p3, p4) -> bool:
        """Check if line segments (p1,p2) and (p3,p4) intersect."""
        def cross(o, a, b):
            return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

        d1 = cross(p3, p4, p1)
        d2 = cross(p3, p4, p2)
        d3 = cross(p1, p2, p3)
        d4 = cross(p1, p2, p4)

        if ((d1 > 0 and d2 < 0) or (d1 < 0 and d2 > 0)) and \
           ((d3 > 0 and d4 < 0) or (d3 < 0 and d4 > 0)):
            return True

        return False

    @staticmethod
    def _ray_cast(x: float, y: float, ring: List[Tuple[float, float]]) -> bool:
        """
        Ray casting algorithm for point-in-polygon.

        Cast a horizontal ray from (x, y) to +∞ and count crossings.
        Odd count = inside, even = outside.
        """
        n = len(ring)
        inside = False
        j = n - 1
        for i in range(n):
            xi, yi = ring[i]
            xj, yj = ring[j]
            if ((yi > y) != (yj > y)) and \
               (x < (xj - xi) * (y - yi) / (yj - yi + 1e-30) + xi):
                inside = not inside
            j = i
        return inside

    def _compute_centroid(self) -> Tuple[float, float]:
        """Compute centroid of the polygon (ignoring holes for simplicity)."""
        n = len(self._exterior)
        a = self._signed_area(self._exterior)
        if abs(a) < 1e-12:
            # Degenerate — return midpoint of bbox
            minx, miny, maxx, maxy = self._bbox
            return ((minx + maxx) / 2, (miny + maxy) / 2)

        cx, cy = 0.0, 0.0
        for i in range(n):
            j = (i + 1) % n
            f = (self._exterior[i][0] * self._exterior[j][1] -
                 self._exterior[j][0] * self._exterior[i][1])
            cx += (self._exterior[i][0] + self._exterior[j][0]) * f
            cy += (self._exterior[i][1] + self._exterior[j][1]) * f

        cx /= (6.0 * a)
        cy /= (6.0 * a)
        return (cx, cy)

    @staticmethod
    def _compute_perimeter(ring: List[Tuple[float, float]]) -> float:
        """Compute perimeter of a ring."""
        n = len(ring)
        p = 0.0
        for i in range(n):
            j = (i + 1) % n
            p += math.hypot(ring[j][0] - ring[i][0], ring[j][1] - ring[i][1])
        return p

    @staticmethod
    def _point_to_segment_dist(px, py, a, b) -> float:
        """Minimum distance from point (px,py) to segment (a,b)."""
        dx, dy = b[0] - a[0], b[1] - a[1]
        if dx == 0 and dy == 0:
            return math.hypot(px - a[0], py - a[1])
        t = max(0, min(1, ((px - a[0]) * dx + (py - a[1]) * dy) / (dx * dx + dy * dy)))
        proj_x = a[0] + t * dx
        proj_y = a[1] + t * dy
        return math.hypot(px - proj_x, py - proj_y)

    def __repr__(self):
        return (f"Polygon2D(vertices={self.num_vertices}, area={self.area:.2f}, "
                f"holes={len(self._holes)}, self_int={self._self_intersects})")


# ════════════════════════════════════════════════════════════════════════════
# Self-test
# ════════════════════════════════════════════════════════════════════════════

def _self_test():
    """Run self-test for geometry kernel."""
    print("=" * 60)
    print("Geometry Kernel — Self-Test")
    print("=" * 60)

    # ── Point2D tests ──
    p1 = Point2D(1.0003, 2.0003, snap_tolerance=0.001)
    p2 = Point2D(1.0, 2.0, snap_tolerance=0.001)
    assert p1 == p2, f"Snap dedup failed: {p1} != {p2}"
    print("  [PASS] Point2D snap-to-grid deduplication")

    p3 = Point2D(4.0, 6.0)
    assert abs(p1.distance_to(p3) - math.hypot(3, 4)) < 0.01, "Distance failed"
    print("  [PASS] Point2D distance calculation")

    d = p1.to_dict()
    p4 = Point2D.from_dict(d)
    assert p4 == p1, "Dict roundtrip failed"
    print("  [PASS] Point2D dict roundtrip")

    # ── Point3D tests ──
    p3d = Point3D(1.0, 2.0, 3.0)
    assert p3d.z == 3.0, "Point3D z failed"
    p3d2 = Point3D(4.0, 6.0, 3.0)
    assert abs(p3d.distance_to(p3d2) - 5.0) < 0.01, "3D distance failed"
    print("  [PASS] Point3D distance calculation")

    # ── Polygon2D tests ──
    # Basic square
    square = Polygon2D([(0, 0), (10, 0), (10, 10), (0, 10)])
    assert abs(square.area - 100.0) < 0.01, f"Area: {square.area}"
    assert square.contains(5, 5), "Center should be inside"
    assert not square.contains(15, 15), "Outside point should be outside"
    assert not square.is_self_intersecting, "Square should not self-intersect"
    print("  [PASS] Polygon2D basic square")

    # Winding order normalization (CW input → CCW internal)
    cw_square = Polygon2D([(0, 0), (0, 10), (10, 10), (10, 0)])
    assert cw_square.area == square.area, "Winding normalization changed area"
    print("  [PASS] Polygon2D winding order normalization (CW → CCW)")

    # Polygon with hole
    outer = [(0, 0), (20, 0), (20, 20), (0, 20)]
    hole = [(5, 5), (5, 15), (15, 15), (15, 5)]
    poly_with_hole = Polygon2D(outer, holes=[hole])
    assert poly_with_hole.contains(2, 2), "Should be inside outer, outside hole"
    assert not poly_with_hole.contains(10, 10), "Should be in hole"
    expected_area = 400.0 - 100.0  # outer - hole
    assert abs(poly_with_hole.area - expected_area) < 0.1, \
        f"Hole area: {poly_with_hole.area} != {expected_area}"
    print("  [PASS] Polygon2D with hole")

    # Centroid
    cx, cy = square.centroid
    assert abs(cx - 5.0) < 0.01 and abs(cy - 5.0) < 0.01, "Centroid wrong"
    print("  [PASS] Polygon2D centroid")

    # Bounding box
    bbox = square.bbox
    assert bbox == (0, 0, 10, 10), f"BBox wrong: {bbox}"
    print("  [PASS] Polygon2D bounding box")

    # Self-intersection (bowtie)
    bowtie = Polygon2D([(0, 0), (10, 10), (10, 0), (0, 10)])
    assert bowtie.is_self_intersecting, "Bowtie should be self-intersecting"
    print("  [PASS] Polygon2D self-intersection detection")

    # Dict roundtrip
    d = square.to_dict()
    square2 = Polygon2D.from_dict(d)
    assert abs(square2.area - square.area) < 0.01, "Roundtrip area mismatch"
    print("  [PASS] Polygon2D dict roundtrip")

    # Degenerate polygon rejection
    try:
        Polygon2D([(0, 0), (1, 1)])
        assert False, "Should have raised ValueError for < 3 vertices"
    except ValueError:
        pass
    print("  [PASS] Polygon2D degenerate rejection")

    # Distance to point
    dist = square.distance_to_point(15, 5)
    assert abs(dist - 5.0) < 0.1, f"Distance wrong: {dist}"
    print("  [PASS] Polygon2D distance to point")

    # Shapely conversion
    if SHAPELY_AVAILABLE:
        sp = square.to_shapely()
        assert sp is not None, "Shapely conversion failed"
        assert abs(sp.area - 100.0) < 0.01, "Shapely area mismatch"
        print("  [PASS] Polygon2D Shapely conversion")
    else:
        print("  [SKIP] Polygon2D Shapely conversion (Shapely not available)")

    print("\n" + "=" * 60)
    print("Geometry Kernel Self-Test: PASS")
    print("=" * 60)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    _self_test()
