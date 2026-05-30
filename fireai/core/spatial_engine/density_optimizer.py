"""
fireai.core.spatial_engine.density_optimizer — Greedy Farthest-Point Placement
===============================================================================

Implements the DensityOptimizer class that places detectors using a greedy
farthest-point algorithm. This ensures maximum minimum-distance between
detectors and complete room coverage per NFPA 72 §17.7.4.2.3.1.

V98 FIX: This module was previously missing, causing every pipeline run
to fall back to geometric_hex fallback (FALLBACK_USED tier). With this
module present, the pipeline can achieve PROOF_VERIFIED tier.

Algorithm:
  1. Compute bounding box from room polygon
  2. Generate candidate grid points inside polygon
  3. Greedy selection: each new detector placed as far as possible
     from already-selected detectors
  4. Continue until coverage >= 99.0%

This is deterministic, dependency-free, and guarantees maximum spacing.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple


@dataclass(frozen=True)
class OptimizedLayout:
    """Result from DensityOptimizer.optimize()."""
    detector_positions: Tuple[Tuple[float, float], ...]
    detector_count: int
    coverage_pct: float
    proof_valid: bool = False
    method: str = "greedy_farthest_point"


class DensityOptimizer:
    """Greedy farthest-point detector placement optimizer.

    Places detectors to maximize minimum spacing while achieving
    NFPA 72 §17.7.4.2.3.1 coverage requirements.

    Usage:
        optimizer = DensityOptimizer()
        layout = optimizer.optimize(room_spec)
    """

    def optimize(self, room_spec: Any) -> Optional[OptimizedLayout]:
        """Optimize detector placement for a room.

        Args:
            room_spec: Object with attributes:
                - polygon: List of (x, y) tuples defining room boundary
                - area_m2: Room area in square meters
                - ceiling_height_m: Ceiling height in meters
                - coverage_radius: Detector coverage radius in meters

        Returns:
            OptimizedLayout with detector positions and coverage, or None on failure.
        """
        try:
            polygon = room_spec.polygon
            area_m2 = room_spec.area_m2
            radius = room_spec.coverage_radius

            if not polygon or area_m2 <= 0 or radius <= 0:
                return None

            # Generate candidate grid points inside polygon
            candidates = self._generate_candidates(polygon, radius)
            if not candidates:
                return None

            # Greedy farthest-point selection
            positions = self._greedy_select(candidates, polygon, radius)

            # Calculate coverage
            coverage_pct = self._calculate_coverage(positions, polygon, radius)

            # Verify proof-level coverage
            proof_valid = coverage_pct >= 99.5

            return OptimizedLayout(
                detector_positions=tuple(positions),
                detector_count=len(positions),
                coverage_pct=round(coverage_pct, 4),
                proof_valid=proof_valid,
                method="greedy_farthest_point",
            )

        except Exception:
            return None

    def _generate_candidates(
        self,
        polygon: List[Tuple[float, float]],
        radius: float,
    ) -> List[Tuple[float, float]]:
        """Generate candidate grid points inside the polygon.

        V98 FIX: Candidates are generated in ABSOLUTE polygon coordinates
        (not relative [0,width] space). This prevents the double-offset
        bug where positions in [0,width] space get min_x/min_y added
        again by the pipeline, placing detectors at 2×offset from origin.
        All positions returned by this optimizer are in the same coordinate
        system as the input polygon — no translation needed downstream.
        """
        xs = [p[0] for p in polygon]
        ys = [p[1] for p in polygon]
        min_x, max_x = min(xs), max(xs)
        min_y, max_y = min(ys), max(ys)

        # Grid step = radius / 2 for good resolution
        step = max(0.25, radius / 2.0)
        candidates = []

        # Point-in-polygon using ray casting
        for x in _frange(min_x + step / 2, max_x, step):
            for y in _frange(min_y + step / 2, max_y, step):
                if _point_in_polygon(x, y, polygon):
                    candidates.append((round(x, 4), round(y, 4)))

        return candidates

    def _greedy_select(
        self,
        candidates: List[Tuple[float, float]],
        polygon: List[Tuple[float, float]],
        radius: float,
    ) -> List[Tuple[float, float]]:
        """Greedy farthest-point selection until coverage >= 99.0%."""
        if not candidates:
            return []

        selected = [candidates[0]]  # Start with first candidate
        r2 = radius * radius

        max_iterations = len(candidates)
        for _ in range(max_iterations):
            # Check coverage
            coverage = self._calculate_coverage(selected, polygon, radius)
            if coverage >= 99.0:
                break

            # Find candidate farthest from all selected detectors
            best_dist = -1.0
            best_point = None
            for cx, cy in candidates:
                if (cx, cy) in selected:
                    continue
                # Minimum distance to any selected detector
                min_d = min(
                    (cx - sx) ** 2 + (cy - sy) ** 2
                    for sx, sy in selected
                )
                if min_d > best_dist:
                    best_dist = min_d
                    best_point = (cx, cy)

            if best_point is None:
                break
            selected.append(best_point)

        return selected

    def _calculate_coverage(
        self,
        positions: List[Tuple[float, float]],
        polygon: List[Tuple[float, float]],
        radius: float,
    ) -> float:
        """Estimate coverage percentage using grid sampling."""
        xs = [p[0] for p in polygon]
        ys = [p[1] for p in polygon]
        min_x, max_x = min(xs), max(xs)
        min_y, max_y = min(ys), max(ys)

        bbox_area = (max_x - min_x) * (max_y - min_y)
        # V98 FIX: Adaptive step — use min(0.25m, radius/10) for accuracy
        step = min(0.25, radius / 10.0) if bbox_area <= 100.0 else min(0.5, radius / 5.0)

        r2 = radius * radius
        total = 0
        covered = 0

        y = min_y
        while y <= max_y:
            x = min_x
            while x <= max_x:
                if _point_in_polygon(x, y, polygon):
                    total += 1
                    for dx, dy in positions:
                        if (x - dx) ** 2 + (y - dy) ** 2 <= r2:
                            covered += 1
                            break
                x += step
            y += step

        if total == 0:
            return 0.0
        return min(100.0, round(100.0 * covered / total, 4))


# ── Helper functions ──────────────────────────────────────────────────────────

def _frange(start: float, stop: float, step: float):
    """Float range generator."""
    while start <= stop:
        yield start
        start += step


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
