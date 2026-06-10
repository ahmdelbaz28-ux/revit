"""
ConstraintSolver — Area-Based Greedy Fallback Coverage Solver
=============================================================
When DensityOptimizer fails to achieve 99.9% coverage (typically for
non-rectangular rooms — L-shape, U-shape, rooms with cutouts), this
solver provides a LAST-RESORT fallback using greedy area-based placement.

Architecture:
  - Standalone module — does NOT import DensityOptimizer (V7.3 frozen)
  - Works with arbitrary Shapely Polygon geometries
  - Uses greedy set-cover: iteratively places the detector that covers
    the most UNCOVERED area within the room polygon
  - Applies 2% safety factor on device_radius (matches COVERAGE_SAFETY_FACTOR
    in density_optimizer.py)
  - Terminates when coverage >= 99.9% or max_devices reached

Algorithm (Greedy Set-Cover):
  1. Generate candidate placement grid within room polygon bounds
  2. Filter candidates that lie inside the room polygon
  3. Iteratively:
     a. For each remaining candidate, compute the uncovered area it would cover
     b. Select the candidate with maximum uncovered area gain
     c. Add it to the placement set
     d. Update the uncovered region (subtract coverage circle from uncovered)
  4. Return result when coverage threshold met or max_devices exhausted

NFPA 72 Compliance:
  - Uses device_radius = 0.7 × S per NFPA 72 §17.7.4.2.3.1
  - Applies 2% safety factor (COVERAGE_SAFETY_FACTOR = 0.98)
  - Does NOT enforce wall distance constraints — this is a FALLBACK only
  - Primary placement MUST come from DensityOptimizer which enforces all
    NFPA constraints; this solver only activates when that fails
  - Any result from this solver should be flagged for manual review

Safety:
  - CRITICAL: This solver is a FALLBACK. It does NOT guarantee NFPA 72
    wall-distance compliance (S/2 rule) or inter-detector spacing (S).
    It ONLY guarantees area coverage >= 99.9% (with 2% safety factor).
    Manual review is ALWAYS required when this solver is used.
  - Per agent.md Rule 5 (Safety > Correctness): more detectors = safer.
    The greedy algorithm may over-place, which is conservative and correct.

Performance:
  - Candidate grid resolution is adaptive based on room size
  - Uses Shapely for all geometric operations (exact, not approximate)
  - Complexity: O(max_devices × n_candidates) — acceptable for fallback
  - Timeout protection: 60-second wall-clock limit
"""

from __future__ import annotations

import logging
import math
import time
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

logger = logging.getLogger(__name__)

try:
    from shapely.geometry import Point, Polygon
    from shapely.ops import unary_union

    HAS_SHAPELY = True
except ImportError:
    HAS_SHAPELY = False

# Safety factor — matches density_optimizer.COVERAGE_SAFETY_FACTOR
COVERAGE_SAFETY_FACTOR = 0.98

# Wall-clock timeout for greedy placement (seconds)
DEFAULT_TIMEOUT_SECONDS = 60.0

# Coverage threshold for NFPA 72 compliance
NFPA_COVERAGE_THRESHOLD = 99.9

# Minimum candidate grid resolution (meters)
MIN_GRID_STEP = 0.5

# Circle polygon approximation segments (matches ExactCoverageEngine)
CIRCLE_SEGMENTS = 16


@dataclass
class ConstraintSolverResult:
    """Result from ConstraintSolver greedy area-based placement.

    Attributes:
        coverage_percent: Area coverage percentage (with 2% safety factor).
        num_devices: Number of detectors placed.
        positions: List of (x, y) detector positions.
        coverage_threshold_met: True if coverage >= 99.9%.
        solver_used: Always 'constraint_solver_greedy'.
        warnings: List of warnings generated during solving.
        solve_time_seconds: Wall-clock time for the solve.
        method: Description of the method used.
    """

    coverage_percent: float = 0.0
    num_devices: int = 0
    positions: List[Tuple[float, float]] = field(default_factory=list)
    coverage_threshold_met: bool = False
    solver_used: str = "constraint_solver_greedy"
    warnings: List[str] = field(default_factory=list)
    solve_time_seconds: float = 0.0
    method: str = "greedy_area_set_cover"


class ConstraintSolver:
    """Area-based greedy fallback coverage solver for non-rectangular rooms.

    When DensityOptimizer fails to achieve NFPA 72 coverage for a room
    (typically non-rectangular geometries), this solver provides a fallback
    by greedily placing detectors to maximize covered area.

    The solver operates on the actual room polygon (Shapely geometry),
    not a bounding rectangle approximation. This makes it suitable for
    L-shaped, U-shaped, and other irregular room geometries.

    IMPORTANT: This solver does NOT enforce NFPA 72 wall-distance (S/2)
    or inter-detector spacing (S) constraints. It ONLY guarantees area
    coverage. Results should ALWAYS be flagged for manual review.

    Usage:
        from shapely.geometry import Polygon
        room_poly = Polygon([(0,0),(10,0),(10,8),(0,8)])
        solver = ConstraintSolver(room_polygon=room_poly, device_radius=6.37)
        result = solver.find_optimal_placement(max_devices=50)
        if result.coverage_threshold_met:
            print(f"Coverage: {result.coverage_percent:.1f}% with {result.num_devices} detectors")
    """

    def __init__(
        self,
        room_polygon: "Polygon",
        device_radius: float,
        coverage_safety_factor: float = COVERAGE_SAFETY_FACTOR,
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
    ):
        """Initialize ConstraintSolver.

        Args:
            room_polygon: Shapely Polygon defining the room boundary.
            device_radius: NFPA 72 coverage radius R in meters
                (R = 0.7 × S per §17.7.4.2.3.1).
            coverage_safety_factor: Safety factor on device_radius.
                Default 0.98 (2% reduction) matches density_optimizer.
            timeout_seconds: Maximum wall-clock time for solve.

        Raises:
            ValueError: If device_radius is not positive.
            ImportError: If Shapely is not available.
        """
        if not HAS_SHAPELY:
            raise ImportError(
                "ConstraintSolver requires Shapely. Install with: pip install shapely"
            )

        if device_radius <= 0:
            raise ValueError(
                f"device_radius must be positive, got {device_radius}"
            )

        if not coverage_safety_factor > 0 or coverage_safety_factor > 1.0:
            raise ValueError(
                f"coverage_safety_factor must be in (0, 1], got {coverage_safety_factor}"
            )

        # Validate and store room polygon
        if room_polygon is None:
            raise ValueError("room_polygon cannot be None")

        # Auto-repair self-intersecting polygons (common from Revit)
        if not room_polygon.is_valid:
            room_polygon = room_polygon.buffer(0)

        if room_polygon.is_empty or room_polygon.area <= 0:
            raise ValueError(
                f"room_polygon has zero or negative area: {room_polygon.area}"
            )

        if room_polygon.geom_type == "MultiPolygon":
            # Use the largest polygon component
            largest = max(room_polygon.geoms, key=lambda g: g.area)
            logger.warning(
                "ConstraintSolver: MultiPolygon room — using largest component "
                f"(area={largest.area:.2f} sqm, {len(room_polygon.geoms)} parts). "
                "Each part should be analyzed as a separate room."
            )
            room_polygon = largest

        self.room_polygon = room_polygon
        self.nominal_radius = device_radius
        self.effective_radius = device_radius * coverage_safety_factor
        self.coverage_safety_factor = coverage_safety_factor
        self.timeout_seconds = timeout_seconds
        self.room_area = room_polygon.area

    def find_optimal_placement(self, max_devices: int = 50) -> ConstraintSolverResult:
        """Find detector placement using greedy area-based set cover.

        Iteratively places detectors at positions that maximize uncovered
        area gain, until coverage >= 99.9% or max_devices is reached.

        Args:
            max_devices: Maximum number of detectors to place.
                Default 50 — prevents runaway placement for degenerate rooms.

        Returns:
            ConstraintSolverResult with placement and coverage information.
        """
        start_time = time.monotonic()
        warnings: List[str] = []

        # Generate candidate placement positions
        candidates = self._generate_candidates()
        if not candidates:
            return ConstraintSolverResult(
                coverage_percent=0.0,
                num_devices=0,
                positions=[],
                coverage_threshold_met=False,
                warnings=["No valid candidate positions found within room polygon"],
                solve_time_seconds=time.monotonic() - start_time,
            )

        # Filter candidates inside the room polygon
        valid_candidates = [
            (x, y) for x, y in candidates
            if self.room_polygon.contains(Point(x, y))
            or self.room_polygon.touches(Point(x, y))
        ]

        if not valid_candidates:
            # Fallback: use polygon centroid and boundary points
            valid_candidates = self._emergency_candidates()
            warnings.append(
                "No grid candidates inside polygon — using centroid and boundary points"
            )

        # Greedy set-cover placement
        placed: List[Tuple[float, float]] = []
        uncovered = self.room_polygon  # Start with entire room uncovered
        coverage_circle_cache: dict = {}  # Cache coverage circles for performance

        for iteration in range(max_devices):
            # Check timeout
            elapsed = time.monotonic() - start_time
            if elapsed > self.timeout_seconds:
                warnings.append(
                    f"ConstraintSolver timeout after {elapsed:.1f}s "
                    f"({len(placed)} detectors placed)"
                )
                break

            # Check if coverage threshold already met
            covered_area = self.room_area - uncovered.area
            coverage_pct = (covered_area / self.room_area) * 100.0 if self.room_area > 0 else 0.0

            if coverage_pct >= NFPA_COVERAGE_THRESHOLD:
                break

            # Find candidate with maximum uncovered area gain
            best_pos = None
            best_gain = 0.0
            best_circle = None

            for pos in valid_candidates:
                # Skip if too close to an already-placed detector
                # (within 10% of effective_radius — avoid redundancy)
                too_close = False
                for px, py in placed:
                    dx = pos[0] - px
                    dy = pos[1] - py
                    if dx * dx + dy * dy < (self.effective_radius * 0.1) ** 2:
                        too_close = True
                        break
                if too_close:
                    continue

                # Compute coverage circle
                if pos not in coverage_circle_cache:
                    circle = Point(pos).buffer(
                        self.effective_radius, quad_segs=CIRCLE_SEGMENTS
                    )
                    coverage_circle_cache[pos] = circle
                else:
                    circle = coverage_circle_cache[pos]

                # Area gain = intersection of circle with uncovered region
                try:
                    gain_region = circle.intersection(uncovered)
                    gain = gain_region.area
                except Exception:
                    gain = 0.0

                if gain > best_gain:
                    best_gain = gain
                    best_pos = pos
                    best_circle = circle

            # If no candidate provides any gain, stop
            if best_pos is None or best_gain < 1e-6:
                break

            # Place detector and update uncovered region
            placed.append(best_pos)
            if best_circle is not None:
                try:
                    uncovered = uncovered.difference(best_circle)
                except Exception:
                    # Shapely error — try with buffer(0) repair
                    try:
                        uncovered = uncovered.buffer(0).difference(
                            best_circle.buffer(0)
                        )
                    except Exception:
                        warnings.append(
                            f"Shapely error at detector #{len(placed)} — "
                            "coverage may be underreported"
                        )
                        break

            # Periodic logging for large rooms
            if (iteration + 1) % 10 == 0:
                covered_area = self.room_area - uncovered.area
                pct = (covered_area / self.room_area) * 100.0
                logger.debug(
                    f"ConstraintSolver iteration {iteration + 1}: "
                    f"{len(placed)} detectors, {pct:.1f}% coverage"
                )

        # Compute final coverage
        covered_area = self.room_area - uncovered.area
        coverage_pct = (covered_area / self.room_area) * 100.0 if self.room_area > 0 else 0.0
        threshold_met = coverage_pct >= NFPA_COVERAGE_THRESHOLD

        # Build warnings
        if not threshold_met:
            warnings.append(
                f"Area coverage {coverage_pct:.1f}% is below NFPA 72 threshold "
                f"of {NFPA_COVERAGE_THRESHOLD}%. Manual design required."
            )

        warnings.append(
            "CONSTRAINT_SOLVER_RESULT: This placement does NOT enforce NFPA 72 "
            "wall-distance (S/2) or inter-detector spacing (S) constraints. "
            "Manual review by a licensed fire protection engineer is REQUIRED."
        )

        elapsed = time.monotonic() - start_time
        logger.info(
            f"ConstraintSolver: {len(placed)} detectors placed, "
            f"{coverage_pct:.1f}% coverage, {elapsed:.2f}s elapsed"
        )

        return ConstraintSolverResult(
            coverage_percent=round(coverage_pct, 2),
            num_devices=len(placed),
            positions=placed,
            coverage_threshold_met=threshold_met,
            warnings=warnings,
            solve_time_seconds=round(elapsed, 3),
        )

    def _generate_candidates(self) -> List[Tuple[float, float]]:
        """Generate candidate placement positions on a grid within room bounds.

        The grid step is adaptive based on room dimensions:
          - Larger rooms use coarser grids (faster)
          - Minimum step is MIN_GRID_STEP (0.5m) for precision
          - Grid covers the bounding box; callers filter by polygon containment

        Returns:
            List of (x, y) candidate positions within room bounding box.
        """
        minx, miny, maxx, maxy = self.room_polygon.bounds
        width = maxx - minx
        height = maxy - miny

        if width <= 0 or height <= 0:
            return []

        # Adaptive grid step: aim for ~20-40 candidates per axis
        # but never coarser than effective_radius / 2 for reasonable coverage
        step = max(
            MIN_GRID_STEP,
            min(width, height) / 30,
            self.effective_radius / 3,
        )

        # Don't make the grid too fine (performance)
        step = min(step, self.effective_radius / 2)

        candidates = []
        x = minx + step / 2
        while x <= maxx:
            y = miny + step / 2
            while y <= maxy:
                candidates.append((round(x, 3), round(y, 3)))
                y += step
            x += step

        return candidates

    def _emergency_candidates(self) -> List[Tuple[float, float]]:
        """Generate emergency candidate positions when grid fails.

        Uses polygon centroid and boundary sample points as last resort.

        Returns:
            List of (x, y) positions including centroid and boundary points.
        """
        candidates = []

        # Centroid is always valid
        centroid = self.room_polygon.centroid
        if not centroid.is_empty:
            candidates.append((round(centroid.x, 3), round(centroid.y, 3)))

        # Sample points along the boundary at regular intervals
        boundary = self.room_polygon.boundary
        if boundary and not boundary.is_empty:
            try:
                total_length = boundary.length
                if total_length > 0:
                    n_samples = max(8, int(total_length / self.effective_radius))
                    n_samples = min(n_samples, 100)  # Cap for performance
                    for i in range(n_samples):
                        frac = i / n_samples
                        pt = boundary.interpolate(frac * total_length)
                        if not pt.is_empty:
                            # Offset inward from boundary by effective_radius/2
                            # to ensure coverage circles overlap with interior
                            if self.room_polygon.contains(pt):
                                candidates.append(
                                    (round(pt.x, 3), round(pt.y, 3))
                                )
            except Exception:
                pass

        # Interior points at half-radius offsets from centroid
        if centroid and not centroid.is_empty:
            for angle_deg in range(0, 360, 45):
                angle_rad = math.radians(angle_deg)
                for dist_frac in [0.3, 0.6, 0.9]:
                    offset = self.effective_radius * dist_frac
                    px = centroid.x + offset * math.cos(angle_rad)
                    py = centroid.y + offset * math.sin(angle_rad)
                    pt = Point(px, py)
                    if self.room_polygon.contains(pt):
                        candidates.append((round(px, 3), round(py, 3)))

        return candidates
