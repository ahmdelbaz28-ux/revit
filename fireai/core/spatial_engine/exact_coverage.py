from __future__ import annotations

"""
ExactCoverageEngine — Shapely-Based Polygon Coverage Verification
=================================================================
VERIFICATION-ONLY engine for non-rectangular rooms (L-shape, U-shape,
arbitrary polygons). NOT a replacement for the Triple Verification
system — this is a SUPPLEMENTARY engine for rooms where bounding-
rectangle approximation may miss blind spots in cutout regions.

Rationale (Consultant #5 Criticism #1 — partially accepted):
  The existing Triple Verification (Analytical + Voronoi + Grid) is
  excellent for rectangular rooms. However, for non-rectangular rooms,
  the current approach uses bounding rectangle + filter, which can
  leave blind spots in cutout regions. This engine uses Shapely's
  exact polygon difference to verify coverage on the ACTUAL room
  geometry.

  REJECTED as replacement for Triple Verification because:
    - This engine only checks area coverage, not wall distance (S/2)
    - Does not check inter-detector spacing (S)
    - No mathematical proof (δ-conservative) — uses area threshold
    - Triple Verification provides stronger guarantees for rect rooms

  ACCEPTED as supplementary verifier for non-rect rooms because:
    - Exact polygon difference catches cutout blind spots
    - 2% safety factor on radius is already consistent with
      COVERAGE_SAFETY_FACTOR in density_optimizer.py
    - Complements the polygon verifier (greedy set cover) in V6.0

NFPA 72-2022 §17.7.4.2.3.1: Coverage radius R = 0.7 × S
"""

import logging
import math
from dataclasses import dataclass, field
from typing import Any, List, Optional, Tuple

logger = logging.getLogger(__name__)

try:
    from shapely.geometry import Point, Polygon
    from shapely.ops import unary_union

    HAS_SHAPELY = True
except ImportError:
    HAS_SHAPELY = False

# V30 B3: Shapely 2.x fast union path
try:
    from shapely import union_all  # Shapely 2.x fast path

    _HAS_UNION_ALL = True
except ImportError:
    _HAS_UNION_ALL = False


@dataclass
class ExactCoverageResult:
    """Result from exact polygon coverage verification."""

    is_covered: bool = False
    coverage_ratio: float = 0.0
    uncovered_area_sqm: float = 0.0
    room_area_sqm: float = 0.0
    effective_radius_m: float = 0.0
    n_sensors: int = 0
    room_shape_valid: bool = False  # V112: FAIL-SAFE — room shape not valid until verified
    warnings: List[str] = field(default_factory=list)
    details: str = ""


class ExactCoverageEngine:
    """Exact polygon-based coverage verifier for non-rectangular rooms.

    Uses Shapely's polygon difference to find uncovered areas.
    Applies a 2% safety factor on coverage radius consistent with
    COVERAGE_SAFETY_FACTOR in density_optimizer.py.

    Usage:
        engine = ExactCoverageEngine(coverage_radius_m=6.37)
        result = engine.verify(
            room_boundary_coords=[(0,0),(10,0),(10,8),(0,8)],
            sensor_locations=[(2.5,2.5), (7.5,2.5), (5.0,6.0)],
        )
        if result.is_covered:
            print("Exact coverage: PASS")
        else:
            print(f"Blind spot: {result.uncovered_area_sqm:.2f} sqm uncovered")

    LIMITATIONS (important):
        - Only checks AREA coverage, not NFPA 72 wall distance (S/2)
        - Only checks AREA coverage, not inter-detector spacing (S)
        - Does NOT replace the Triple Verification system
        - For rectangular rooms, the Triple Verification is superior
          (mathematical proof with δ-conservative bounds)
        - This engine is specifically for NON-RECTANGULAR rooms where
          bounding-rectangle approximation may miss cutout regions

    SAFETY FACTOR:
        The 2% reduction on coverage radius is defense-in-depth.
        It accounts for:
          - Minor obstructions not modeled in Revit
          - Smoke stratification at detector height
          - Manufacturing tolerances in detector sensitivity
          - This matches COVERAGE_SAFETY_FACTOR = 0.98 in
            density_optimizer.py
    """

    # Tolerance for "negligible" uncovered area (sqm).
    # Areas below this threshold are considered numerical artifacts
    # from Shapely's floating-point geometry operations.
    # 0.001 sqm = 10cm × 10cm — far too small for a person to occupy.
    AREA_TOLERANCE_SQM = 0.001

    # V30 B3: Circle polygon approximation segments
    # 16 segments sufficient for NFPA verification accuracy while reducing
    # polygon vertex count 4× (was 64 in original via Point.buffer default).
    _CIRCLE_SEGS = 16

    def __init__(self, coverage_radius_m: float):
        """Initialize with coverage radius.

        Args:
            coverage_radius_m: NFPA 72 coverage radius R in meters.
                For smoke at h≤3.0m: R = 0.7 × 9.1 = 6.37m.

        """
        if coverage_radius_m <= 0:
            raise ValueError(f"Coverage radius must be positive, got {coverage_radius_m}")
        # 2% safety factor — matches density_optimizer.COVERAGE_SAFETY_FACTOR
        self.effective_radius = coverage_radius_m * 0.98
        self.nominal_radius = coverage_radius_m
        # V30 B3: Store nominal radius for analytical bypass comparison
        self._coverage_radius_m = coverage_radius_m

    def verify(
        self,
        room_boundary_coords: List[Tuple[float, float]],
        sensor_locations: List[Tuple[float, float]],
        obstacles: Optional[List[List[Tuple[float, float]]]] = None,
        analytical_passed: bool = False,  # V30 B3: skip flag
    ) -> ExactCoverageResult:
        """Verify coverage using exact polygon difference.

        V30 B3: Added analytical_passed parameter. If the lightweight
        AnalyticalVerifier already returned proof_valid=True, we skip
        the expensive Shapely union entirely (returns 100% immediately).
        This avoids expensive polygon ops for the common passing case.

        Args:
            room_boundary_coords: Room polygon vertices (CCW or CW).
            sensor_locations: List of (x, y) sensor positions.
            obstacles: Optional list of obstacle polygons (columns, beams).
            analytical_passed: If True, skip Shapely ops and return 100%.

        Returns:
            ExactCoverageResult with coverage analysis.

        """
        if not HAS_SHAPELY:
            return ExactCoverageResult(
                is_covered=False,
                coverage_ratio=0.0,
                room_shape_valid=False,
                warnings=["Shapely not available — cannot verify exact coverage"],
                details="REQUIRES_SHAPELY",
            )

        if not sensor_locations:
            return ExactCoverageResult(
                is_covered=False,
                coverage_ratio=0.0,
                uncovered_area_sqm=0.0,
                n_sensors=0,
                room_shape_valid=True,
                details="No sensors provided",
            )

        # ── V30 B3 fast path: skip Shapely if analytical already passed ──
        if analytical_passed:
            return ExactCoverageResult(
                is_covered=True,
                coverage_ratio=1.0,
                uncovered_area_sqm=0.0,
                n_sensors=len(sensor_locations),
                room_shape_valid=True,
                details="analytical_bypass",
            )

        # Build room polygon
        try:
            room_poly = Polygon(room_boundary_coords)
        except Exception as e:
            return ExactCoverageResult(
                is_covered=False,
                room_shape_valid=False,
                warnings=[f"Invalid room geometry: {e}"],
                details="ROOM_GEOMETRY_ERROR",
            )

        # Auto-repair self-intersecting polygons (common from Revit)
        if not room_poly.is_valid:
            room_poly = room_poly.buffer(0)
            if not room_poly.is_valid:
                return ExactCoverageResult(
                    is_covered=False,
                    room_shape_valid=False,
                    warnings=["Room geometry is corrupted — cannot auto-repair"],
                    details="ROOM_GEOMETRY_CORRUPTED",
                )

        # Reject MultiPolygon rooms (should be handled as separate rooms)
        if room_poly.geom_type == "MultiPolygon":
            return ExactCoverageResult(
                is_covered=False,
                room_shape_valid=False,
                warnings=[
                    "Room is a MultiPolygon (disconnected parts). Each part must be analyzed as a separate room."
                ],
                details="MULTIPOLYGON_REJECTED",
            )

        room_area = room_poly.area
        if room_area <= 0:
            return ExactCoverageResult(
                is_covered=False,
                room_shape_valid=False,
                warnings=["Room area is zero or negative"],
                details="ZERO_AREA",
            )

        # Subtract obstacles from room area
        if obstacles:
            for obs_coords in obstacles:
                try:
                    obs_poly = Polygon(obs_coords)
                    if obs_poly.is_valid and room_poly.intersects(obs_poly):
                        room_poly = room_poly.difference(obs_poly)
                except Exception as e:
                    logger.warning("V112: verify_with_obstacles: failed to subtract obstacle polygon: %s", e)
                    pass  # Skip invalid obstacles

        # Build sensor coverage circles using effective radius (2% safety)
        # V30 B3: Use fewer segments (16 vs default 64) — sufficient for NFPA accuracy
        sensor_areas = []
        for loc in sensor_locations:
            try:
                sensor_circle = Point(loc).buffer(self.effective_radius, quad_segs=self._CIRCLE_SEGS)
                # Only keep the portion inside the room
                clipped = sensor_circle.intersection(room_poly)
                if not clipped.is_empty:
                    sensor_areas.append(clipped)
            except Exception as e:
                logger.warning(
                    f"V112: verify_with_obstacles: failed to build sensor coverage circle at loc={loc!r}: {e!r}"
                )
                continue

        # V76 CRIT-09 FIX: Recompute room_area AFTER obstacle subtraction.
        # Previously, room_area was captured at line 220 BEFORE obstacles were
        # subtracted from room_poly (lines 230-238). This caused coverage_ratio
        # to be inflated by the obstacle area. Example: room 200m² with 50m²
        # obstacles and 5m² uncovered reported (200-5)/200=97.5% instead of
        # correct (150-5)/150=96.7%. Near the 99.9% threshold, this inflation
        # could cause a false PASS — room signed off as protected when it's not.
        room_area = room_poly.area
        if room_area <= 0:
            return ExactCoverageResult(
                is_covered=False,
                coverage_ratio=0.0,
                room_area_sqm=0.0,
                effective_radius_m=self.effective_radius,
                n_sensors=len(sensor_locations),
                room_shape_valid=True,
                warnings=["Room area is zero after obstacle subtraction"],
                details="ZERO_AREA_AFTER_OBSTACLES",
            )

        if not sensor_areas:
            return ExactCoverageResult(
                is_covered=False,
                coverage_ratio=0.0,
                uncovered_area_sqm=room_area,
                room_area_sqm=room_area,
                effective_radius_m=self.effective_radius,
                n_sensors=len(sensor_locations),
                room_shape_valid=True,
                details="No sensor coverage intersects room",
            )

        # Union all sensor coverage areas
        # V30 B3: Use union_all() (Shapely 2.x GEOS-native) when available
        # — 3-5× faster than unary_union() for non-overlapping circles.
        try:
            total_coverage_poly = self._fast_union(sensor_areas)
        except Exception as e:
            return ExactCoverageResult(
                is_covered=False,
                coverage_ratio=0.0,
                room_area_sqm=room_area,
                effective_radius_m=self.effective_radius,
                n_sensors=len(sensor_locations),
                room_shape_valid=True,
                warnings=[f"Coverage union failed: {e}"],
                details="COVERAGE_UNION_ERROR",
            )

        # Compute uncovered area (room minus sensor coverage)
        try:
            uncovered_area_poly = room_poly.difference(total_coverage_poly)
            uncovered_area = uncovered_area_poly.area
        except Exception as e:
            return ExactCoverageResult(
                is_covered=False,
                coverage_ratio=0.0,
                room_area_sqm=room_area,
                effective_radius_m=self.effective_radius,
                n_sensors=len(sensor_locations),
                room_shape_valid=True,
                warnings=[f"Coverage difference failed: {e}"],
                details="COVERAGE_DIFF_ERROR",
            )

        # Coverage ratio
        covered_area = room_area - uncovered_area
        coverage_ratio = covered_area / room_area if room_area > 0 else 0.0

        # Determine if covered (uncovered area below tolerance)
        is_covered = uncovered_area <= self.AREA_TOLERANCE_SQM

        # Build warnings
        warnings = []
        if uncovered_area > self.AREA_TOLERANCE_SQM:
            warnings.append(
                f"Blind spot detected: {uncovered_area:.3f} sqm uncovered "
                f"(tolerance: {self.AREA_TOLERANCE_SQM} sqm). "
                f"Coverage ratio: {coverage_ratio:.4f}"
            )

        # Details
        details = (
            f"Room area: {room_area:.2f} sqm, "
            f"Uncovered: {uncovered_area:.3f} sqm, "
            f"Coverage: {coverage_ratio:.4f}, "
            f"R_eff: {self.effective_radius:.2f}m (2% safety), "
            f"Sensors: {len(sensor_locations)}, "
            f"Result: {'COVERED' if is_covered else 'BLIND_SPOT'}"
        )

        return ExactCoverageResult(
            is_covered=is_covered,
            coverage_ratio=round(coverage_ratio, 6),
            uncovered_area_sqm=round(uncovered_area, 6),
            room_area_sqm=round(room_area, 2),
            effective_radius_m=self.effective_radius,
            n_sensors=len(sensor_locations),
            room_shape_valid=True,
            warnings=warnings,
            details=details,
        )

    @staticmethod
    def _fast_union(geoms: list) -> Any:
        """V55 B3: Union list of geometries using the fastest available method.

        Auto-selects strategy based on geometry count:
          <= 5:  Sequential reduce (minimal overhead)
          <= 50: union_all() (Shapely 2.x GEOS-native bulk op)
          > 50:  Hierarchical spatial chunking (bounds complexity)

        Falls back to unary_union() when union_all is unavailable.
        """
        if not geoms:
            return Polygon()
        if len(geoms) == 1:
            return geoms[0]

        n = len(geoms)

        # Small sets: sequential reduce — minimal overhead
        if n <= 5:
            result = geoms[0]
            for g in geoms[1:]:
                result = result.union(g)
            return result

        # Medium sets: bulk union
        if n <= 50:
            if _HAS_UNION_ALL:
                return union_all(geoms)
            return unary_union(geoms)

        # V55: Large sets — hierarchical spatial chunking
        # Divide into spatial chunks, union each, then union chunk results.
        # Bounds worst-case complexity of individual union operations.
        chunk_size = max(8, int(math.sqrt(n)))
        chunk_results = []
        for start in range(0, n, chunk_size):
            chunk = geoms[start : start + chunk_size]
            if _HAS_UNION_ALL:
                chunk_results.append(union_all(chunk))
            else:
                chunk_results.append(unary_union(chunk))

        # Final union of chunk results
        if _HAS_UNION_ALL:
            return union_all(chunk_results)
        return unary_union(chunk_results)

    def verify_with_obstacles(
        self,
        room_boundary_coords: List[Tuple[float, float]],
        sensor_locations: List[Tuple[float, float]],
        obstacle_coords_list: List[List[Tuple[float, float]]],
    ) -> ExactCoverageResult:
        """Convenience method for rooms with interior obstacles.

        Args:
            room_boundary_coords: Room polygon vertices.
            sensor_locations: List of (x, y) sensor positions.
            obstacle_coords_list: List of obstacle polygons.

        Returns:
            ExactCoverageResult with obstacle-aware coverage analysis.

        """
        return self.verify(
            room_boundary_coords=room_boundary_coords,
            sensor_locations=sensor_locations,
            obstacles=obstacle_coords_list,
        )
