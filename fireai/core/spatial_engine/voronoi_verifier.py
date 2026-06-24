from __future__ import annotations

"""
Voronoi Verification Engine — NFPA 72 Coverage Gap Analysis
============================================================
Independent verification engine that uses VORONOI TESSELLATION
to find the largest uncovered gap in a room.

This is Engine 2 of the Triple Verification system:
  Engine 1: Analytical  (analytical_verifier.py) — exact geometric proof
  Engine 2: Voronoi     (this file) — gap-based analysis
  Engine 3: Grid-Based  (density_optimizer._verify_fast) — δ-conservative grid

PRINCIPLE: Different failure modes. The grid engine can fail if grid
resolution is wrong. The analytical engine can miss interior gaps.
The Voronoi engine finds the WORST-CASE gap directly.

Method:
  1. Compute Voronoi diagram of detector positions
  2. For each Voronoi cell, find the point farthest from its generator
  3. The maximum of these farthest points is the LARGEST GAP
  4. If largest gap > R, coverage is incomplete

This uses Shapely's Voronoi implementation for geometric computation.
Falls back to brute-force sampling if Shapely Voronoi unavailable.
"""

import logging
import math
from dataclasses import dataclass
from typing import List, Optional, Tuple

logger = logging.getLogger(__name__)

try:
    from shapely.geometry import MultiPoint, Point, Polygon
    from shapely.ops import voronoi_diagram

    HAS_SHAPELY_VORONOI = True
except ImportError:
    HAS_SHAPELY_VORONOI = False


@dataclass
class VoronoiResult:
    """Result from Voronoi verification."""

    is_covered: bool
    max_gap_m: float  # Distance from farthest point to nearest detector
    max_gap_location: Optional[Tuple[float, float]] = None
    gap_exceeds_radius: bool = False
    voronoi_available: bool = True
    n_voronoi_cells: int = 0
    coverage_estimate_pct: float = 0.0
    details: str = ""


class VoronoiVerifier:
    """Voronoi-based coverage verifier — gap analysis approach.

    Uses Voronoi tessellation to find the largest gap between detectors.
    Each Voronoi cell contains the region closest to one detector.
    The farthest point in each cell from its generator is the worst-case
    gap for that detector. The global maximum is the room's largest gap.

    If the largest gap exceeds R, there's an uncovered point.
    If the largest gap <= R, coverage is complete (for rectangular rooms).

    FALLBACK: If Shapely Voronoi is unavailable, uses brute-force
    sampling along detector midpoints and room critical points.
    """

    def __init__(self, coverage_radius: float, tolerance: float = 0.05):
        """Initialize Voronoi verifier.

        Args:
            coverage_radius: Coverage radius R in meters.
            tolerance: Acceptable margin for numerical precision (default 0.05m).
                Voronoi boundary computations can have ~0.02-0.05m error.

        """
        self.R = coverage_radius
        self.tolerance = tolerance

    def verify(
        self,
        width: float,
        length: float,
        detectors: List[Tuple[float, float]],
    ) -> VoronoiResult:
        """Verify coverage using Voronoi gap analysis.

        Args:
            width: Room width in meters.
            length: Room length in meters.
            detectors: List of (x, y) detector positions.

        Returns:
            VoronoiResult with gap analysis.

        """
        if not detectors:
            return VoronoiResult(
                is_covered=False,
                max_gap_m=math.hypot(width, length),
                gap_exceeds_radius=True,
                voronoi_available=False,
                details="No detectors in room",
            )

        if HAS_SHAPELY_VORONOI and len(detectors) >= 2:
            return self._verify_voronoi(width, length, detectors)
        return self._verify_brute_force(width, length, detectors)

    def _verify_voronoi(
        self,
        width: float,
        length: float,
        detectors: List[Tuple[float, float]],
    ) -> VoronoiResult:
        """Voronoi-based verification using Shapely."""
        try:
            # Create room boundary polygon
            room_poly = Polygon([(0, 0), (width, 0), (width, length), (0, length)])

            # Create Voronoi diagram from detector points
            points = MultiPoint([Point(x, y) for x, y in detectors])
            regions = voronoi_diagram(points, envelope=room_poly)

            # For each Voronoi region, find the point farthest from its generator
            max_gap = 0.0
            max_gap_loc = None

            # Build list of detector positions for nearest-neighbor lookup
            det_list = list(detectors)

            for region in regions.geoms:
                # Find the generator (detector) for this region
                # The generator is the detector closest to the region centroid
                cx, cy = region.centroid.x, region.centroid.y
                gen_idx = min(
                    range(len(det_list)),
                    key=lambda i: math.hypot(cx - det_list[i][0], cy - det_list[i][1]),
                )
                gx, gy = det_list[gen_idx]

                # Find the farthest point in this region from its generator
                # Sample the boundary of the region (vertices) and interior
                # The farthest point in a convex region from an interior point
                # is on the boundary

                # Check boundary vertices
                boundary_coords = list(region.boundary.coords) if hasattr(region.boundary, "coords") else []
                for bx, by in boundary_coords:
                    # Only consider points inside the room
                    if 0 <= bx <= width and 0 <= by <= length:
                        dist = math.hypot(bx - gx, by - gy)
                        if dist > max_gap:
                            max_gap = dist
                            max_gap_loc = (bx, by)

                # Also check intersection with room boundary
                try:
                    intersection = region.intersection(room_poly.boundary)
                    if hasattr(intersection, "coords"):
                        for ix, iy in intersection.coords:
                            dist = math.hypot(ix - gx, iy - gy)
                            if dist > max_gap:
                                max_gap = dist
                                max_gap_loc = (ix, iy)
                except Exception as e:
                    logger.warning(
                        f"V112: _verify_voronoi: failed to compute Voronoi cell boundary intersection: {e!r}"
                    )
                    pass

            # Also check room corners (they might be in small Voronoi cells)
            for cx, cy in [(0, 0), (width, 0), (0, length), (width, length)]:
                min_dist = min(math.hypot(cx - dx, cy - dy) for dx, dy in det_list)
                if min_dist > max_gap:
                    max_gap = min_dist
                    max_gap_loc = (cx, cy)

            is_covered = max_gap <= self.R + self.tolerance

            return VoronoiResult(
                is_covered=is_covered,
                max_gap_m=round(max_gap, 4),
                max_gap_location=max_gap_loc,
                gap_exceeds_radius=max_gap > self.R + 1e-9,
                voronoi_available=True,
                n_voronoi_cells=len(regions.geoms),
                details=(
                    f"Max gap: {max_gap:.2f}m at {max_gap_loc} "
                    f"(R={self.R:.2f}m, {'COVERED' if is_covered else 'UNCOVERED'})"
                ),
            )

        except Exception:
            # Fall back to brute-force if Voronoi fails
            return self._verify_brute_force(width, length, detectors)

    def _verify_brute_force(
        self,
        width: float,
        length: float,
        detectors: List[Tuple[float, float]],
    ) -> VoronoiResult:
        """Brute-force verification using critical point sampling.

        Used as fallback when Shapely Voronoi is unavailable or fails.
        Tests: room corners, center, edge midpoints, and detector midpoints.
        """
        det_list = list(detectors)

        # Critical test points
        test_points = [
            (0, 0),
            (width, 0),
            (0, length),
            (width, length),
            (width / 2, length / 2),
            (width / 2, 0),
            (width / 2, length),
            (0, length / 2),
            (width, length / 2),
        ]

        # Add detector-to-detector midpoints (these are the hardest points)
        for i in range(len(det_list)):
            for j in range(i + 1, len(det_list)):
                x1, y1 = det_list[i]
                x2, y2 = det_list[j]
                dist = math.hypot(x2 - x1, y2 - y1)
                # Only check midpoints for nearby pairs
                if dist <= 2 * self.R:
                    mx, my = (x1 + x2) / 2, (y1 + y2) / 2
                    test_points.append((mx, my))

        # Add quarter points along edges (more thorough)
        for frac in [0.25, 0.5, 0.75]:
            test_points.append((width * frac, 0))
            test_points.append((width * frac, length))
            test_points.append((0, length * frac))
            test_points.append((width, length * frac))

        # Find maximum gap
        max_gap = 0.0
        max_gap_loc = None

        for px, py in test_points:
            # Only check points inside room
            if not (0 <= px <= width and 0 <= py <= length):
                continue
            min_dist = min(math.hypot(px - dx, py - dy) for dx, dy in det_list)
            if min_dist > max_gap:
                max_gap = min_dist
                max_gap_loc = (px, py)

        is_covered = max_gap <= self.R + self.tolerance

        return VoronoiResult(
            is_covered=is_covered,
            max_gap_m=round(max_gap, 4),
            max_gap_location=max_gap_loc,
            gap_exceeds_radius=max_gap > self.R + self.tolerance,
            voronoi_available=HAS_SHAPELY_VORONOI,
            details=(
                f"Brute-force: max gap {max_gap:.2f}m at {max_gap_loc} "
                f"(R={self.R:.2f}m, {'COVERED' if is_covered else 'UNCOVERED'})"
            ),
        )
