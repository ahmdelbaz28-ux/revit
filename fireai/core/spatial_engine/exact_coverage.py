"""
fireai.core.spatial_engine.exact_coverage — Shapely-Based Exact Coverage
========================================================================

Implements the ExactCoverageEngine class that computes exact detector
coverage using Shapely geometric operations (polygon intersection).

V98 FIX: This module was previously missing, causing every pipeline run
to fall back to grid_estimate_fallback. With this module present, the
pipeline can achieve ExactCoverageEngine-level verification.

When Shapely is unavailable, falls back gracefully to grid sampling.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

try:
    from shapely.geometry import Point, Polygon as ShapelyPolygon
    HAS_SHAPELY = True
except ImportError:
    HAS_SHAPELY = False


@dataclass(frozen=True)
class CoverageResult:
    """Result from ExactCoverageEngine.verify()."""
    coverage_pct: float
    room_area_m2: float
    covered_area_m2: float
    is_compliant: bool
    method_used: str


class ExactCoverageEngine:
    """Exact coverage verification using Shapely polygon intersection.

    Computes the precise area of the room polygon that falls within
    the coverage radius of at least one detector, using Shapely's
    geometric intersection operations.

    Falls back to grid sampling when Shapely is not available.
    """

    def verify(
        self,
        polygon: List[Tuple[float, float]],
        detector_positions: List[Tuple[float, float]],
        coverage_radius_m: float,
        room_id: str = "",
    ) -> CoverageResult:
        """Verify exact coverage for a room.

        Args:
            polygon: Room boundary as list of (x, y) tuples.
            detector_positions: Detector positions as list of (x, y) tuples.
            coverage_radius_m: Coverage radius in meters (R = 0.7 × S).
            room_id: Room identifier for logging.

        Returns:
            CoverageResult with exact coverage metrics.
        """
        if not polygon or not detector_positions or coverage_radius_m <= 0:
            return CoverageResult(
                coverage_pct=0.0,
                room_area_m2=0.0,
                covered_area_m2=0.0,
                is_compliant=False,
                method_used="no_data",
            )

        if HAS_SHAPELY:
            return self._verify_shapely(polygon, detector_positions, coverage_radius_m)
        else:
            return self._verify_grid(polygon, detector_positions, coverage_radius_m)

    def _verify_shapely(
        self,
        polygon: List[Tuple[float, float]],
        detector_positions: List[Tuple[float, float]],
        coverage_radius_m: float,
    ) -> CoverageResult:
        """Exact coverage using Shapely polygon intersection."""
        room_poly = ShapelyPolygon(polygon)
        room_area = room_poly.area

        if room_area <= 0:
            return CoverageResult(
                coverage_pct=0.0,
                room_area_m2=0.0,
                covered_area_m2=0.0,
                is_compliant=False,
                method_used="shapely_invalid_room",
            )

        # Union of all detector coverage circles intersected with room
        covered = ShapelyPolygon()  # empty
        for x, y in detector_positions:
            circle = Point(x, y).buffer(coverage_radius_m, resolution=32)
            covered = covered.union(circle.intersection(room_poly))

        covered_area = covered.area
        coverage_pct = min(100.0, (covered_area / room_area) * 100.0)

        return CoverageResult(
            coverage_pct=round(coverage_pct, 4),
            room_area_m2=round(room_area, 4),
            covered_area_m2=round(covered_area, 4),
            is_compliant=coverage_pct >= 99.0,
            method_used="shapely_exact_intersection",
        )

    def _verify_grid(
        self,
        polygon: List[Tuple[float, float]],
        detector_positions: List[Tuple[float, float]],
        coverage_radius_m: float,
    ) -> CoverageResult:
        """Grid-based fallback coverage estimate."""
        xs = [p[0] for p in polygon]
        ys = [p[1] for p in polygon]
        min_x, max_x = min(xs), max(xs)
        min_y, max_y = min(ys), max(ys)

        # V98 FIX: Adaptive step for accuracy
        bbox_area = (max_x - min_x) * (max_y - min_y)
        step = min(0.25, coverage_radius_m / 10.0) if bbox_area <= 100.0 else min(0.5, coverage_radius_m / 5.0)

        r2 = coverage_radius_m * coverage_radius_m
        total = 0
        covered = 0

        y = min_y
        while y <= max_y:
            x = min_x
            while x <= max_x:
                if _point_in_polygon(x, y, polygon):
                    total += 1
                    for dx, dy in detector_positions:
                        if (x - dx) ** 2 + (y - dy) ** 2 <= r2:
                            covered += 1
                            break
                x += step
            y += step

        if total == 0:
            return CoverageResult(
                coverage_pct=0.0,
                room_area_m2=0.0,
                covered_area_m2=0.0,
                is_compliant=False,
                method_used="grid_no_points_in_room",
            )

        room_area_est = total * step * step
        covered_area_est = covered * step * step
        coverage_pct = min(100.0, 100.0 * covered / total)

        return CoverageResult(
            coverage_pct=round(coverage_pct, 4),
            room_area_m2=round(room_area_est, 4),
            covered_area_m2=round(covered_area_est, 4),
            is_compliant=coverage_pct >= 99.0,
            method_used="grid_estimate_fallback",
        )


def _point_in_polygon(x: float, y: float, polygon: List[Tuple[float, float]]) -> bool:
    """Ray casting algorithm for point-in-polygon test."""
    n = len(polygon)
    inside = False
    j = n - 1
    for i in range(n):
        xi, yi = polygon[i]
        xj, yj = polygon[j]
        if ((yi > y) != (yj > y)) and (x < (xj - xi) * (y - yi) / (yj - yi) + xi):
            inside = not inside
        j = i
    return inside
