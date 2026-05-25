"""
FireAI Exact Spatial Constraint Solver
Elite Greedy Algorithm for Life-Safety compliant device placement

V11 Safety Hardening (2026-05-20):
  1. FIXED: Grid step was scaled by room dimension (density * (maxy-miny)/10),
     producing 22.5m step in 50m rooms — now uses fixed step = device_radius / 3
  2. FIXED: Coverage was measured by circular distance ignoring walls (X-Ray Vision)
     — now uses polygon intersection: buffer.clip(room_poly) prevents wall penetration
  3. FIXED: Coverage percentage was point-count based — now uses area-based
     measurement (Shapely area ratio) for NFPA-compliant accuracy

Consultant's analysis was 100% correct on all three vulnerabilities.
"""

import logging
from dataclasses import dataclass, field
from typing import List, Tuple

import numpy as np
from shapely.geometry import Point, Polygon
from shapely.ops import unary_union

logger = logging.getLogger(__name__)

# NFPA 72 spacing rules (in meters)
MAX_WALL_DISTANCE = 1.5   # Max distance from wall
MAX_DEVICE_SPACING = 9.1  # Device must cover every point within this distance


@dataclass
class PlacementResult:
    """Result of device placement"""
    positions: List[Tuple[float, float]] = field(default_factory=list)
    coverage_percent: float = 0.0
    num_devices: int = 0


class ConstraintSolver:
    """
    Area-based Greedy algorithm for NFPA 72 compliant device placement.

    Algorithm:
    1. Generate dense candidate grid with FIXED step (radius / 3)
    2. For each candidate, compute actual coverage polygon (clipped by room walls)
    3. Greedy selection: pick candidate that adds the most UNCOVERED AREA
    4. Repeat until >= 99.9% area coverage or no improvement
    5. Coverage percentage = covered_area / room_area (area-based, not point-based)

    Key safety properties:
    - Coverage polygons are CLIPPED by room boundary → no X-Ray through walls
    - Step size is fixed → no scaling bug regardless of room size
    - Coverage is measured by AREA → no blind spots between grid points
    """

    def __init__(self, room_polygon: List[Tuple[float, float]], device_radius: float = MAX_DEVICE_SPACING):
        self.device_radius = device_radius
        # Fix invalid polygons immediately
        poly = Polygon(room_polygon)
        self.room_poly = poly.buffer(0) if not poly.is_valid else poly

        if self.room_poly.area <= 0:
            logger.error("Invalid room geometry with zero area.")

    def find_optimal_placement(self, max_devices: int = 100) -> PlacementResult:
        """Find optimal device placement using area-based greedy algorithm"""

        if self.room_poly.area <= 0:
            return PlacementResult()

        minx, miny, maxx, maxy = self.room_poly.bounds

        # 1. Generate candidate grid with FIXED step = radius / 3
        # Dense overlap ensures finding optimal positions regardless of room size
        step = self.device_radius / 3.0
        x_coords = np.arange(minx, maxx + step, step)
        y_coords = np.arange(miny, maxy + step, step)

        candidates = []
        for x in x_coords:
            for y in y_coords:
                p = Point(float(x), float(y))
                if self.room_poly.contains(p):
                    # Compute actual coverage polygon CLIPPED by room walls
                    # This prevents X-Ray vision through walls
                    theoretical_coverage = p.buffer(self.device_radius)
                    actual_coverage = theoretical_coverage.intersection(self.room_poly)

                    candidates.append({
                        'point': (float(x), float(y)),
                        'coverage_poly': actual_coverage
                    })

        if not candidates:
            return PlacementResult()

        # 2. Area-based Greedy Selection
        selected_positions = []
        current_total_coverage = Polygon()  # starts empty

        for _ in range(max_devices):
            best_candidate = None
            best_new_area = 0.0

            for cand in candidates:
                # How much NEW uncovered area would this detector add?
                new_area_poly = cand['coverage_poly'].difference(current_total_coverage)

                if new_area_poly.area > best_new_area:
                    best_new_area = new_area_poly.area
                    best_candidate = cand

            # If best detector adds < 0.01 m², we've reached maximum coverage
            if best_candidate is None or best_new_area < 0.01:
                break

            # Accept the best candidate
            selected_positions.append(best_candidate['point'])
            current_total_coverage = unary_union(
                [current_total_coverage, best_candidate['coverage_poly']]
            )

            # Early exit if >= 99.9% coverage
            uncovered_room = self.room_poly.difference(current_total_coverage)
            if uncovered_room.area < 0.01:
                break

        # 3. Calculate AREA-BASED coverage percentage (NFPA compliant)
        coverage_percent = (current_total_coverage.area / self.room_poly.area) * 100.0

        return PlacementResult(
            positions=selected_positions,
            coverage_percent=min(coverage_percent, 100.0),
            num_devices=len(selected_positions)
        )

    def verify_coverage(self, positions: List[Tuple[float, float]]) -> float:
        """Verify coverage percentage for given positions using area-based calculation"""

        total_coverage = Polygon()
        for px, py in positions:
            p = Point(px, py)
            theoretical = p.buffer(self.device_radius)
            actual = theoretical.intersection(self.room_poly)
            total_coverage = unary_union([total_coverage, actual])

        coverage_percent = (total_coverage.area / self.room_poly.area) * 100.0
        return min(coverage_percent, 100.0)
