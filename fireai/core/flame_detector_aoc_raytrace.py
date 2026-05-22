"""
flame_detector_aoc_raytrace.py – Flame Detector AOC Ray Trace Engine
======================================================================
Computes Angle of Coverage (AOC) and Line of Sight (LOS) visibility
for flame detectors using 3-D ray tracing geometry.

Without this module, flame detector placement is geometrically blind —
no visibility analysis, no obstruction detection, no coverage proof.

Standards:
  BS EN 54-10:2002    – Flame detectors (point-type)
  FM Global DS 5-48   – Flame detector testing and application
  ISA TR84.00.07      – Safety instrumented systems (SIS) guidance
  NFPA 72-2022 §17.8  – Radiant energy-sensing detectors
  IEC 60079-29-4      – Flame detectors for Ex applications

V20.2 Fix #18 (CRITICAL): effective_range_m used max() of covered
  distances instead of a meaningful statistic. A single distant point
  made effective_range = rated_range even when 99% of coverage was at
  half that distance. Changed to median for representative value.

V20.2 Fix #19 (HIGH): Inverse square law sensitivity was computed as
  (rated_range/distance)^2, but this exceeds 1.0 for distances < rated_range,
  which is physically wrong. Clamped to [0, 1.0] properly.

V20.2 Fix #20 (HIGH): analyse_multi_detector() had double-counting bug
  in coverage calculation. For each target point, it iterated ALL
  detectors and ALL individual results, counting a point as covered
  multiple times. Rewrote with per-detector covered set intersection.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------

Point3D = Tuple[float, float, float]     # (x, y, z) metres
Point2D = Tuple[float, float]            # (x, y) metres


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class FlameDetectorTech(str, Enum):
    """Flame detector technology (affects spectral response)."""
    UV          = "UV"          # Ultraviolet
    IR_SINGLE   = "IR_SINGLE"   # Single IR
    IR_TRIPLE   = "IR_TRIPLE"   # Multi-spectrum IR (MSIR)
    UV_IR       = "UV_IR"       # UV/IR combined
    VISUAL      = "VISUAL"      # Video-based
    UV_IR_IR    = "UV_IR_IR"    # UV+2IR (highest immunity to false alarms)


class ObstructionType(str, Enum):
    STRUCTURAL_BEAM  = "STRUCTURAL_BEAM"
    WALL             = "WALL"
    EQUIPMENT        = "EQUIPMENT"
    DUCTWORK         = "DUCTWORK"
    PIPE             = "PIPE"
    CEILING_LOWERED  = "CEILING_LOWERED"


class CoverageQuality(str, Enum):
    """LOS quality per FM Global DS 5-48."""
    CLEAR             = "CLEAR"       # Full LOS, within rated distance
    OBSTRUCTED        = "OBSTRUCTED"  # LOS blocked by obstruction
    MARGINAL          = "MARGINAL"    # LOS clear but near boundary
    OUT_OF_RANGE      = "OUT_OF_RANGE"  # Beyond rated distance
    OUT_OF_AOC        = "OUT_OF_AOC"   # Outside detector cone angle
    BELOW_SENSITIVITY = "BELOW_SENSITIVITY"  # Inverse square loss too high


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class FlameDetectorSpec:
    """
    Specification of a flame detector for ray trace analysis.
    BS EN 54-10:2002 / FM Global DS 5-48.
    """
    detector_id:      str
    technology:       FlameDetectorTech
    position:         Point3D         # (x, y, z) metres
    aim_vector:       Point3D         # Unit vector of detector aim direction
    aoc_half_angle_deg: float         # Half-angle of cone (°), typically 45–60°
    rated_range_m:    float           # Maximum rated detection distance (m)
    sensitivity_factor: float = 1.0  # 1.0 = standard; <1 = reduced sensitivity
    # ATEX rating for hazardous area
    atex_marking:     str = ""        # e.g. "Ex ia IIC T4 Gb"
    nfpa_listed:      bool = True


@dataclass(frozen=True)
class Obstruction:
    """A 3-D obstruction that may block flame detector LOS."""
    obstruction_id: str
    obs_type:       ObstructionType
    # Bounding box: two corner points (min, max)
    bbox_min:       Point3D
    bbox_max:       Point3D
    is_transparent: bool = False   # Smoke/glass — may not block UV/IR


@dataclass(frozen=True)
class RayTracePoint:
    """
    Result of tracing a single ray from detector to a target point.
    """
    target:           Point2D
    target_3d:        Point3D
    distance_m:       float
    angle_from_axis_deg: float
    within_aoc:       bool
    within_range:     bool
    los_clear:        bool
    blocking_obstruction: Optional[str]   # obstruction_id if blocked
    coverage_quality: CoverageQuality
    sensitivity_at_target: float          # 0–1 (inverse square factor)


@dataclass(frozen=True)
class DetectorCoverageResult:
    """
    Complete coverage analysis for one flame detector.
    """
    detector:         FlameDetectorSpec
    coverage_polygon: Tuple[Point2D, ...]  # Boundary of covered floor area
    covered_area_m2:  float
    uncovered_points: Tuple[Point2D, ...]  # Points that failed LOS
    ray_results:      Tuple[RayTracePoint, ...]
    effective_range_m: float    # Actual range accounting for obstructions
    coverage_pct:     float     # % of target area covered
    obstructions_hit: Tuple[str, ...]  # IDs of obstructions that blocked rays
    warnings:         Tuple[str, ...]
    nfpa_reference:   str = "NFPA 72-2022 §17.8"
    fm_reference:     str = "FM Global DS 5-48"


@dataclass(frozen=True)
class MultiDetectorCoverageResult:
    """Coverage analysis for a set of flame detectors covering one space."""
    space_id:          str
    detectors:         Tuple[FlameDetectorSpec, ...]
    individual_results: Tuple[DetectorCoverageResult, ...]
    combined_coverage_pct: float
    uncovered_area_m2: float
    total_covered_area_m2: float
    redundancy_map:    Dict[str, int]   # point → # detectors covering it
    min_redundancy:    int              # minimum coverage count across space
    is_nfpa_compliant: bool
    warnings:          Tuple[str, ...]


# ---------------------------------------------------------------------------
# Ray trace engine
# ---------------------------------------------------------------------------

class FlameDetectorAOCRayTrace:
    """
    Computes flame detector coverage using 3-D ray tracing.

    Algorithm:
      1. Generate a grid of target points on the floor plane
      2. For each target point, trace a ray from detector to target
      3. Check if target is within AOC cone (angle from aim axis)
      4. Check ray against all obstruction bounding boxes
      5. Apply inverse square law for sensitivity at distance
      6. Build coverage polygon from passing target points

    BS EN 54-10:2002 / FM Global DS 5-48 / NFPA 72-2022 §17.8
    """

    # Grid resolution for coverage calculation
    GRID_STEP_M: float = 0.5

    def analyse_detector(
        self,
        detector:     FlameDetectorSpec,
        floor_bounds: Tuple[float, float, float, float],  # (min_x, min_y, max_x, max_y)
        obstructions: List[Obstruction] = None,
        floor_z:      float = 0.0,
    ) -> DetectorCoverageResult:
        """
        Compute coverage for a single flame detector.

        Args:
            detector:     Flame detector specification with position and AOC.
            floor_bounds: (min_x, min_y, max_x, max_y) of the floor area.
            obstructions: List of 3-D obstructions.
            floor_z:      Z coordinate of the floor plane (metres).

        Returns:
            DetectorCoverageResult with coverage polygon and statistics.

        NFPA 72-2022 §17.8 / BS EN 54-10:2002 / FM Global DS 5-48.
        """
        obstructions = obstructions or []
        warnings: List[str] = []

        # Normalize aim vector
        aim = self._normalize(detector.aim_vector)

        # Generate target grid
        targets = self._generate_grid(floor_bounds)

        ray_results: List[RayTracePoint] = []
        covered_points: List[Point2D] = []
        uncovered_points: List[Point2D] = []
        obstructions_hit: set = set()

        for tx, ty in targets:
            target_3d: Point3D = (tx, ty, floor_z)
            ray_result = self._trace_ray(
                detector, aim, target_3d, obstructions)
            ray_results.append(ray_result)

            if ray_result.coverage_quality == CoverageQuality.CLEAR:
                covered_points.append((tx, ty))
            elif ray_result.coverage_quality == CoverageQuality.MARGINAL:
                covered_points.append((tx, ty))
                warnings.append(
                    f"Marginal LOS to ({tx:.1f}, {ty:.1f}): "
                    f"distance {ray_result.distance_m:.1f}m, "
                    f"angle {ray_result.angle_from_axis_deg:.1f}°"
                )
            else:
                uncovered_points.append((tx, ty))
                if ray_result.blocking_obstruction:
                    obstructions_hit.add(ray_result.blocking_obstruction)

        total_pts = len(targets)
        covered_pts = len(covered_points)
        coverage_pct = 100.0 * covered_pts / total_pts if total_pts > 0 else 0.0

        # Estimate covered area
        cell_area = self.GRID_STEP_M ** 2
        covered_area = covered_pts * cell_area

        # Coverage polygon (convex hull approximation)
        coverage_polygon = self._convex_hull_2d(covered_points)

        # V20.2 Fix #18: Use MEDIAN instead of MAX for effective range
        # max() gives a misleadingly high range from a single distant point
        # median() represents the typical coverage distance
        covered_distances = sorted(
            r.distance_m for r in ray_results
            if r.coverage_quality == CoverageQuality.CLEAR
        )
        if covered_distances:
            mid = len(covered_distances) // 2
            effective_range = covered_distances[mid]
        else:
            effective_range = 0.0

        if coverage_pct < 85.0:
            warnings.append(
                f"Coverage {coverage_pct:.1f}% < 85% threshold. "
                "Review detector position/orientation. "
                "FM Global DS 5-48 §4.2."
            )

        if not detector.nfpa_listed:
            warnings.append(
                "Detector is not NFPA-listed. "
                "NFPA 72-2022 §17.8.1 requires listed equipment."
            )

        return DetectorCoverageResult(
            detector=detector,
            coverage_polygon=tuple(coverage_polygon),
            covered_area_m2=round(covered_area, 2),
            uncovered_points=tuple(uncovered_points),
            ray_results=tuple(ray_results),
            effective_range_m=round(effective_range, 2),
            coverage_pct=round(coverage_pct, 2),
            obstructions_hit=tuple(obstructions_hit),
            warnings=tuple(warnings),
        )

    def analyse_multi_detector(
        self,
        space_id:     str,
        detectors:    List[FlameDetectorSpec],
        floor_bounds: Tuple[float, float, float, float],
        obstructions: List[Obstruction] = None,
        floor_z:      float = 0.0,
        min_redundancy: int = 1,
    ) -> MultiDetectorCoverageResult:
        """
        Analyse coverage for multiple flame detectors covering one space.
        Checks overlap, redundancy, and combined coverage.

        V20.2 Fix #20: Rewrote coverage combination to avoid double-counting.
        Each target point is now counted once per detector that covers it,
        using a set of covered grid points per detector.

        NFPA 72-2022 §17.8 / FM Global DS 5-48 / ISA TR84.00.07.
        """
        obstructions = obstructions or []
        warnings: List[str] = []

        individual: List[DetectorCoverageResult] = []
        for det in detectors:
            res = self.analyse_detector(det, floor_bounds, obstructions, floor_z)
            individual.append(res)
            warnings.extend(res.warnings)

        # V20.2 Fix #20: Build per-detector covered point sets
        targets = self._generate_grid(floor_bounds)
        target_set = set(targets)
        
        # For each detector, build set of covered target points
        detector_covered_sets: List[set] = []
        for res in individual:
            covered_set = set()
            for ray in res.ray_results:
                if ray.coverage_quality in (CoverageQuality.CLEAR, CoverageQuality.MARGINAL):
                    covered_set.add(ray.target)
            detector_covered_sets.append(covered_set)

        # Count how many detectors cover each target point
        coverage_count: Dict[Point2D, int] = {}
        for t in targets:
            count = 0
            for det_covered in detector_covered_sets:
                if t in det_covered:
                    count += 1
            coverage_count[t] = count

        covered_pts = sum(1 for v in coverage_count.values() if v >= min_redundancy)
        total_pts = len(targets)
        combined_pct = 100.0 * covered_pts / total_pts if total_pts > 0 else 0.0
        cell_area = self.GRID_STEP_M ** 2
        covered_area = covered_pts * cell_area
        total_area = total_pts * cell_area
        uncovered_area = total_area - covered_area
        actual_min_red = min(coverage_count.values()) if coverage_count else 0

        is_nfpa = combined_pct >= 95.0

        if combined_pct < 95.0:
            warnings.append(
                f"Combined coverage {combined_pct:.1f}% < 95%. "
                "Add detectors or reposition. NFPA 72-2022 §17.8."
            )
        if actual_min_red < min_redundancy:
            warnings.append(
                f"Minimum redundancy {actual_min_red} < required {min_redundancy}. "
                "ISA TR84.00.07 SIL compliance may be affected."
            )

        return MultiDetectorCoverageResult(
            space_id=space_id,
            detectors=tuple(detectors),
            individual_results=tuple(individual),
            combined_coverage_pct=round(combined_pct, 2),
            uncovered_area_m2=round(uncovered_area, 2),
            total_covered_area_m2=round(covered_area, 2),
            redundancy_map={f"{t[0]:.1f},{t[1]:.1f}": v
                            for t, v in coverage_count.items()},
            min_redundancy=actual_min_red,
            is_nfpa_compliant=is_nfpa,
            warnings=tuple(set(warnings)),
        )

    # -----------------------------------------------------------------------
    # Private ray-trace methods
    # -----------------------------------------------------------------------

    def _trace_ray(
        self,
        detector:     FlameDetectorSpec,
        aim_norm:     Point3D,
        target_3d:    Point3D,
        obstructions: List[Obstruction],
    ) -> RayTracePoint:
        dx = target_3d[0] - detector.position[0]
        dy = target_3d[1] - detector.position[1]
        dz = target_3d[2] - detector.position[2]
        distance = math.sqrt(dx*dx + dy*dy + dz*dz)

        if distance < 1e-6:
            return RayTracePoint(
                target=(target_3d[0], target_3d[1]),
                target_3d=target_3d,
                distance_m=0.0,
                angle_from_axis_deg=0.0,
                within_aoc=True, within_range=True,
                los_clear=True, blocking_obstruction=None,
                coverage_quality=CoverageQuality.CLEAR,
                sensitivity_at_target=1.0,
            )

        # Direction from detector to target (unit vector)
        ray_dir = (dx/distance, dy/distance, dz/distance)

        # Angle from aim axis
        dot = (ray_dir[0]*aim_norm[0] +
               ray_dir[1]*aim_norm[1] +
               ray_dir[2]*aim_norm[2])
        dot = max(-1.0, min(1.0, dot))
        angle_deg = math.degrees(math.acos(dot))

        within_aoc   = angle_deg <= detector.aoc_half_angle_deg
        within_range = distance   <= detector.rated_range_m

        # V20.2 Fix #19: Inverse square law properly clamped
        # Sensitivity = (rated_range / distance)^2, but clamped to [0, 1.0]
        # At rated_range distance: sensitivity = 1.0 (design point)
        # At closer distances: sensitivity = 1.0 (not higher — detector
        #   doesn't get MORE sensitive, it's just designed for that range)
        # At further distances: sensitivity drops per inverse square
        if distance <= detector.rated_range_m:
            sensitivity = 1.0
        else:
            sensitivity = (detector.rated_range_m / distance) ** 2
        sensitivity *= detector.sensitivity_factor

        # Obstruction check
        blocking: Optional[str] = None
        los_clear = True
        if within_aoc:
            for obs in obstructions:
                if obs.is_transparent:
                    continue
                if self._ray_intersects_bbox(
                    detector.position, ray_dir, distance,
                    obs.bbox_min, obs.bbox_max
                ):
                    blocking  = obs.obstruction_id
                    los_clear = False
                    break

        # Determine quality
        if not within_aoc:
            quality = CoverageQuality.OUT_OF_AOC
        elif not within_range:
            quality = CoverageQuality.OUT_OF_RANGE
        elif not los_clear:
            quality = CoverageQuality.OBSTRUCTED
        elif sensitivity < 0.25:
            quality = CoverageQuality.BELOW_SENSITIVITY
        elif angle_deg > detector.aoc_half_angle_deg * 0.85:
            quality = CoverageQuality.MARGINAL
        else:
            quality = CoverageQuality.CLEAR

        return RayTracePoint(
            target=(target_3d[0], target_3d[1]),
            target_3d=target_3d,
            distance_m=round(distance, 3),
            angle_from_axis_deg=round(angle_deg, 2),
            within_aoc=within_aoc,
            within_range=within_range,
            los_clear=los_clear,
            blocking_obstruction=blocking,
            coverage_quality=quality,
            sensitivity_at_target=round(sensitivity, 4),
        )

    @staticmethod
    def _ray_intersects_bbox(
        origin:   Point3D,
        direction: Point3D,
        max_dist: float,
        bbox_min: Point3D,
        bbox_max: Point3D,
    ) -> bool:
        """
        Slab method ray–AABB intersection test.
        Returns True if ray intersects bounding box within max_dist.
        """
        tmin = 0.0
        tmax = max_dist

        for i in range(3):
            o  = [origin[0], origin[1], origin[2]][i]
            d  = [direction[0], direction[1], direction[2]][i]
            mn = [bbox_min[0], bbox_min[1], bbox_min[2]][i]
            mx = [bbox_max[0], bbox_max[1], bbox_max[2]][i]

            if abs(d) < 1e-9:
                if o < mn or o > mx:
                    return False
            else:
                t1 = (mn - o) / d
                t2 = (mx - o) / d
                if t1 > t2:
                    t1, t2 = t2, t1
                tmin = max(tmin, t1)
                tmax = min(tmax, t2)
                if tmin > tmax:
                    return False

        return tmin <= tmax

    def _generate_grid(
        self,
        bounds: Tuple[float, float, float, float],
    ) -> List[Point2D]:
        min_x, min_y, max_x, max_y = bounds
        pts: List[Point2D] = []
        x = min_x + self.GRID_STEP_M / 2.0
        while x < max_x:
            y = min_y + self.GRID_STEP_M / 2.0
            while y < max_y:
                pts.append((x, y))
                y += self.GRID_STEP_M
            x += self.GRID_STEP_M
        return pts

    @staticmethod
    def _normalize(v: Point3D) -> Point3D:
        mag = math.sqrt(v[0]**2 + v[1]**2 + v[2]**2)
        if mag < 1e-9:
            return (0.0, 0.0, -1.0)
        return (v[0]/mag, v[1]/mag, v[2]/mag)

    @staticmethod
    def _convex_hull_2d(points: List[Point2D]) -> List[Point2D]:
        """Graham scan convex hull. Returns hull vertices."""
        if len(points) < 3:
            return points

        def cross(o, a, b):
            return (a[0]-o[0])*(b[1]-o[1]) - (a[1]-o[1])*(b[0]-o[0])

        pts = sorted(set(points))
        lower: List[Point2D] = []
        for p in pts:
            while len(lower) >= 2 and cross(lower[-2], lower[-1], p) <= 0:
                lower.pop()
            lower.append(p)
        upper: List[Point2D] = []
        for p in reversed(pts):
            while len(upper) >= 2 and cross(upper[-2], upper[-1], p) <= 0:
                upper.pop()
            upper.append(p)
        return lower[:-1] + upper[:-1]
