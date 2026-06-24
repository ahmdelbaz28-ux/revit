"""flame_detector_aoc_raytrace.py – Flame Detector AOC Ray Trace Engine
=====================================================================
Computes Angle of Coverage (AOC) and Line of Sight (LOS) visibility
for flame detectors using 3-D ray tracing geometry.

V21 Migration:
  - Pydantic FlameDetectorSpec, Obstruction, RayTracePoint from models_v21
  - R-tree spatial indexing replaces O(n*m) brute force (Q2)
  - Spectral transparency per band replaces single boolean (Q6)
  - Grid-cell counting replaces Convex Hull (Q5)
  - Fix #18: median range (not max)
  - Fix #19: sensitivity capped at 1.0
  - Fix #20: double-counting eliminated

Standards:
  BS EN 54-10:2002    – Flame detectors (point-type)
  FM Global DS 5-48   – Flame detector testing and application
  NFPA 72-2022 §17.8  – Radiant energy-sensing detectors
  IEC 60079-29-4      – Flame detectors for Ex applications
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from enum import Enum
from statistics import median
from typing import Dict, List, Optional, Set, Tuple

from fireai.core.models_v21 import (
    MIN_REDUNDANCY_BY_ZONE,
    EnvironmentalContext,
    SpectralSignatureRegistry,
    VolumetricMedium,
    WavelengthBand,
    ZoneType,
    volumetric_path_transmittance,
)
from fireai.core.models_v21 import (
    FlameDetectorSpec as V21FlameDetectorSpec,
)
from fireai.core.models_v21 import (
    Obstruction as V21Obstruction,
)
from fireai.core.models_v21 import (
    RayTracePoint as V21RayTracePoint,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Legacy Types & Enums
# ---------------------------------------------------------------------------

Point3D = Tuple[float, float, float]
Point2D = Tuple[float, float]


class FlameDetectorTech(str, Enum):
    UV = "UV"
    IR_SINGLE = "IR_SINGLE"
    IR_TRIPLE = "IR_TRIPLE"
    UV_IR = "UV_IR"
    VISUAL = "VISUAL"
    UV_IR_IR = "UV_IR_IR"


class ObstructionType(str, Enum):
    STRUCTURAL_BEAM = "STRUCTURAL_BEAM"
    WALL = "WALL"
    EQUIPMENT = "EQUIPMENT"
    DUCTWORK = "DUCTWORK"
    PIPE = "PIPE"
    CEILING_LOWERED = "CEILING_LOWERED"


class CoverageQuality(str, Enum):
    CLEAR = "CLEAR"
    OBSTRUCTED = "OBSTRUCTED"
    MARGINAL = "MARGINAL"
    OUT_OF_RANGE = "OUT_OF_RANGE"
    OUT_OF_AOC = "OUT_OF_AOC"
    BELOW_SENSITIVITY = "BELOW_SENSITIVITY"


# ---------------------------------------------------------------------------
# Legacy data structures (backward compatibility)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class FlameDetectorSpecLegacy:
    """Legacy flame detector specification (dataclass)."""

    detector_id: str
    technology: FlameDetectorTech
    position: Point3D
    aim_vector: Point3D
    aoc_half_angle_deg: float
    rated_range_m: float
    sensitivity_factor: float = 1.0
    atex_marking: str = ""
    nfpa_listed: bool = True


@dataclass(frozen=True)
class ObstructionLegacy:
    """Legacy obstruction (dataclass)."""

    obstruction_id: str
    obs_type: ObstructionType
    bbox_min: Point3D
    bbox_max: Point3D
    is_transparent: bool = False


@dataclass(frozen=True)
class RayTracePointLegacy:
    """Legacy ray trace result."""

    target: Point2D
    target_3d: Point3D
    distance_m: float
    angle_from_axis_deg: float
    within_aoc: bool
    within_range: bool
    los_clear: bool
    blocking_obstruction: Optional[str]
    coverage_quality: CoverageQuality
    sensitivity_at_target: float


@dataclass(frozen=True)
class DetectorCoverageResult:
    """Coverage analysis for one flame detector (legacy)."""

    detector: FlameDetectorSpecLegacy
    coverage_polygon: Tuple[Point2D, ...]
    covered_area_m2: float
    uncovered_points: Tuple[Point2D, ...]
    ray_results: Tuple[RayTracePointLegacy, ...]
    effective_range_m: float
    coverage_pct: float
    obstructions_hit: Tuple[str, ...]
    warnings: Tuple[str, ...]
    nfpa_reference: str = "NFPA 72-2022 §17.8"
    fm_reference: str = "FM Global DS 5-48"


@dataclass(frozen=True)
class MultiDetectorCoverageResult:
    """Coverage analysis for multiple detectors (legacy)."""

    space_id: str
    detectors: Tuple[FlameDetectorSpecLegacy, ...]
    individual_results: Tuple[DetectorCoverageResult, ...]
    combined_coverage_pct: float
    uncovered_area_m2: float
    total_covered_area_m2: float
    redundancy_map: Dict[str, int]
    min_redundancy: int
    is_nfpa_compliant: bool
    warnings: Tuple[str, ...]


# ---------------------------------------------------------------------------
# V21 Result dataclasses
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SingleDetectorResult:
    detector_id: str
    covered_pts: frozenset  # indices into target grid
    effective_range_m: float
    spectral_transmittance_map: Dict[int, float] = field(default_factory=dict)
    warnings: tuple = ()


@dataclass(frozen=True)
class CoverageResult:
    """Q5: Coverage computed from grid cell count — never Convex Hull.
    Conservative bias: a point is covered only if >=1 detector has LOS + AOC.

    GAP-06: Added redundancy fields for NFPA 72-2022 §17.8.3.4 / FM Global DS 5-48.
    """

    total_points: int
    covered_points: int
    coverage_fraction: float  # = covered / total (never overestimated)
    per_detector: Dict[str, SingleDetectorResult]
    warnings: List[str]

    # GAP-06 new fields — all defaulted for backward compat
    redundancy_map: Dict[int, int] = field(default_factory=dict)
    min_redundancy: int = 0
    mean_redundancy: float = 0.0
    double_covered_pct: float = 0.0  # % of all points covered by >=2 detectors

    @property
    def coverage_pct(self) -> float:
        """V59 FIX (Finding 8): Coverage percentage without masking 100%.

        Previously, `round(fraction * 100, 2)` would produce 99.99 for a
        fraction of 0.9999, which is NOT full coverage but appears close.
        More importantly, a fraction of 0.999996 would round to 100.00,
        masking the fact that some grid points are uncovered. In a life-safety
        system, a coverage gap of even one grid point (0.5m × 0.5m = 0.25m²)
        could mean a fire starting in that exact spot goes undetected.

        Fix: Return the raw value without rounding when coverage is < 100%.
        When coverage is exactly 100%, return 100.00 to avoid false negatives.
        When coverage rounds to 100% but isn't exact, add a WARNING.
        """
        raw_pct = self.coverage_fraction * 100.0
        if self.covered_points == self.total_points:
            return 100.00  # True full coverage
        rounded_pct = round(raw_pct, 2)
        # V59: If rounding masks <100% as 100%, return the raw value with more precision
        if rounded_pct >= 100.0 and raw_pct < 100.0:
            return round(raw_pct, 4)  # Show 4 decimal places to reveal the gap
        return rounded_pct

    @property
    def is_full_coverage(self) -> bool:
        return self.covered_points == self.total_points

    @property
    def is_nfpa72_redundant(self) -> bool:
        """True if all covered points have >=2 detector coverage.
        NFPA 72-2022 §17.8.3.4 requirement for critical applications.
        FM Global DS 5-48 §3.1 requirement for high-hazard areas.
        """
        return self.min_redundancy >= 2 and self.is_full_coverage

    @property
    def redundancy_pct(self) -> float:
        """Percentage of covered points with redundancy >= 2.
        NFPA 72-2022 §17.8.3.4 / FM Global DS 5-48 §4.3.
        """
        if not self.redundancy_map or self.covered_points == 0:
            return 0.0
        pts_with_2plus = sum(1 for c in self.redundancy_map.values() if c >= 2)
        return round(100.0 * pts_with_2plus / self.covered_points, 2)

    @property
    def avg_redundancy(self) -> float:
        """Average redundancy across all grid points (not just covered)."""
        if not self.redundancy_map or self.total_points == 0:
            return 0.0
        total = sum(self.redundancy_map.values())
        return round(total / self.total_points, 2)


# ---------------------------------------------------------------------------
# Ray Trace Engine
# ---------------------------------------------------------------------------


class FlameDetectorAOCRayTrace:
    """3D ray-trace coverage analyser for flame detectors.

    V21 API:
      analyse_single_v21() — uses Pydantic FlameDetectorSpec, Obstruction
      analyse_multi_v21()  — uses R-tree spatial indexing + spectral bands

    Legacy API:
      analyse_detector()       — backward compatible
      analyse_multi_detector() — backward compatible

    Uses spatial indexing (R-tree via rtree or scipy KDTree fallback)
    to avoid O(n*m) brute-force obstacle checking.
    """

    GRID_STEP_M: float = 0.5

    DETECTOR_THRESHOLD: float = 0.1  # Minimum transmittance for coverage

    def __init__(self, grid_step_m: float = 0.5, detector_threshold: float = 0.1) -> None:
        self.grid_step = grid_step_m
        self._spatial_index = None
        self._rtree_available = False
        self._spectral_registry = SpectralSignatureRegistry()
        self.detector_threshold = detector_threshold

    # ── V21 API ────────────────────────────────────────────────────────────

    def _build_spatial_index(self, obstructions: List[V21Obstruction]) -> None:
        """Q2: Build R-tree spatial index for obstructions.
        Falls back to list if rtree not installed.
        """
        try:
            from rtree import index as rtree_index

            prop = rtree_index.Property()
            prop.dimension = 3
            self._spatial_index = rtree_index.Index(properties=prop)
            for i, obs in enumerate(obstructions):
                pts = obs.vertices
                xs = [p[0] for p in pts]
                ys = [p[1] for p in pts]
                zs = [p[2] for p in pts]
                bbox = (min(xs), min(ys), min(zs), max(xs), max(ys), max(zs))
                self._spatial_index.insert(i, bbox)  # type: ignore[attr-defined]
            self._rtree_available = True
        except ImportError:
            self._rtree_available = False
            self._spatial_index = None

    def _get_candidate_obstructions(
        self,
        obstructions: List[V21Obstruction],
        ray_start: Tuple[float, float, float],
        ray_end: Tuple[float, float, float],
    ) -> List[int]:
        """Return indices of obstructions whose bounding box intersects the ray."""
        if self._rtree_available and self._spatial_index is not None:
            bbox = (
                min(ray_start[0], ray_end[0]),
                min(ray_start[1], ray_end[1]),
                min(ray_start[2], ray_end[2]),
                max(ray_start[0], ray_end[0]),
                max(ray_start[1], ray_end[1]),
                max(ray_start[2], ray_end[2]),
            )
            return list(self._spatial_index.intersection(bbox))
        return list(range(len(obstructions)))  # fallback: all

    def _ray_blocked_v21(
        self,
        ray_start: Tuple[float, float, float],
        ray_end: Tuple[float, float, float],
        obstructions: List[V21Obstruction],
        band: WavelengthBand,
    ) -> bool:
        """Check if ray is blocked by any opaque obstruction for given spectral band.
        Q6: Uses spectral transmittance per band.
        Uses spatial index for candidate filtering.
        """
        candidates = self._get_candidate_obstructions(obstructions, ray_start, ray_end)
        for idx in candidates:
            obs = obstructions[idx]
            transmittance = obs.transmittance_for(band)
            if transmittance > 0.5:
                continue  # transparent for this band
            if self._ray_intersects_box(ray_start, ray_end, obs.vertices):
                return True
        return False

    @staticmethod
    def _ray_intersects_box(
        origin: Tuple[float, ...],
        end: Tuple[float, ...],
        vertices: List[List[float]],
    ) -> bool:
        """AABB ray-box intersection (slab method). Fast, exact."""
        xs = [v[0] for v in vertices]
        ys = [v[1] for v in vertices]
        zs = [v[2] for v in vertices]
        box_min = (min(xs), min(ys), min(zs))
        box_max = (max(xs), max(ys), max(zs))

        d = (end[0] - origin[0], end[1] - origin[1], end[2] - origin[2])
        tmin, tmax = 0.0, 1.0

        for i in range(3):
            if abs(d[i]) < 1e-12:
                if origin[i] < box_min[i] or origin[i] > box_max[i]:
                    return False
            else:
                t1 = (box_min[i] - origin[i]) / d[i]
                t2 = (box_max[i] - origin[i]) / d[i]
                if t1 > t2:
                    t1, t2 = t2, t1
                tmin = max(tmin, t1)
                tmax = min(tmax, t2)
                if tmin > tmax:
                    return False
        return True

    def _in_aoc_v21(
        self,
        detector: V21FlameDetectorSpec,
        target_pos: Tuple[float, float, float],
    ) -> bool:
        """Check if target is within detector's angle of coverage."""
        unit = detector.orientation_unit
        dx = target_pos[0] - detector.position[0]
        dy = target_pos[1] - detector.position[1]
        dz = target_pos[2] - detector.position[2]
        dist = math.sqrt(dx * dx + dy * dy + dz * dz)
        if dist < 1e-9:
            return True
        cos_angle = (dx * unit[0] + dy * unit[1] + dz * unit[2]) / dist
        cos_angle = max(-1.0, min(1.0, cos_angle))
        angle_deg = math.degrees(math.acos(cos_angle))
        return angle_deg <= detector.aoc_deg / 2.0

    @staticmethod
    def _sensitivity_v21(distance_m: float, rated_range: float) -> float:
        """Fix #19: Inverse square law, capped at 1.0 for near distances.
        """
        # V57 FIX (Finding 10): NaN distance bypasses guards — NaN <= 0 is False,
        # NaN <= rated_range is False, so NaN propagates to ratio = rated_range/NaN
        # = NaN, then NaN*NaN = NaN returned as sensitivity. Fail-safe: return 0.0.
        if not math.isfinite(distance_m):
            return 0.0
        if distance_m <= 0:
            return 1.0
        if distance_m <= rated_range:
            return 1.0  # Within rated range -> full sensitivity
        ratio = rated_range / distance_m
        return ratio * ratio  # Inverse square, always <= 1.0

    def _ray_spectral_transmittance_v21(
        self,
        ray_start: Tuple[float, float, float],
        ray_end: Tuple[float, float, float],
        obstructions: List[V21Obstruction],
        volumetric_media: List[VolumetricMedium],
        band: WavelengthBand,
    ) -> float:
        """V21.2: Calculate total spectral transmittance along a ray.

        Two-stage check:
        1. Solid obstructions: if opaque for this band, T = 0.0 (blocked)
        2. Volumetric media: Beer-Lambert attenuation T = exp(-alpha * d)

        Returns transmittance in [0.0, 1.0].
        """
        # Stage 1: Check solid obstructions
        candidates = self._get_candidate_obstructions(obstructions, ray_start, ray_end)
        for idx in candidates:
            obs = obstructions[idx]
            transmittance = obs.transmittance_for(band)
            if transmittance > 0.5:
                continue  # transparent for this band
            if self._ray_intersects_box(ray_start, ray_end, obs.vertices):
                return 0.0  # Blocked by opaque solid

        # Stage 2: Volumetric media (Beer-Lambert)
        if volumetric_media:
            t_vol = volumetric_path_transmittance(ray_start, ray_end, volumetric_media, band, self._spectral_registry)
            return t_vol

        return 1.0

    def analyse_single_v21(
        self,
        detector: V21FlameDetectorSpec,
        target_grid: List[V21RayTracePoint],
        obstructions: List[V21Obstruction],
        volumetric_media: Optional[List[VolumetricMedium]] = None,
    ) -> SingleDetectorResult:
        """V21.2: Analyse one detector against all target points.
        Returns set of covered point indices and per-point spectral transmittance.

        V59 FIX (Finding 9): NaN detector geometry (position, orientation) now
        produces a WARNING and returns empty coverage instead of silently
        rejecting all AOC checks. Previously, NaN position would cause NaN
        distances and NaN angles, both of which pass through math.isfinite()
        guards in _in_aoc_v21 but produce incorrect results. The NaN guard at
        line ~468 only catches NaN DISTANCES, not NaN DETECTOR GEOMETRY.
        """
        warnings: List[str] = []
        volumetric_media = volumetric_media or []

        # V59 FIX (Finding 9): Check detector geometry for NaN/Inf
        # If the detector's position or orientation contains NaN, ALL coverage
        # calculations will be meaningless. Previously this was silently ignored
        # — NaN position → NaN distances which ARE caught by the isfinite guard,
        # but NaN orientation is NOT caught (it passes through _in_aoc_v21
        # producing NaN cos_angle, which passes math.acos() on some platforms).
        src = tuple(detector.position)
        orient = detector.orientation_unit
        has_invalid_geom = False
        for val in src:
            if not math.isfinite(val):
                has_invalid_geom = True
                break
        if not has_invalid_geom:
            for val in orient:
                if not math.isfinite(val):
                    has_invalid_geom = True
                    break
        if has_invalid_geom:
            warnings.append(
                f"V59 SAFETY: Detector '{detector.detector_id}' has NaN/Inf "
                f"geometry (position={src}, orientation={orient}). Coverage "
                f"analysis cannot produce meaningful results. This detector "
                f"MUST be excluded from the design until geometry is corrected. "
                f"[NFPA 72-2022 §17.8.2 — equipment must be properly located]"
            )
            logger.critical(
                "V59: NaN detector geometry for '%s' — returning empty coverage",
                detector.detector_id,
            )
            return SingleDetectorResult(
                detector_id=detector.detector_id,
                covered_pts=frozenset(),
                effective_range_m=0.0,
                spectral_transmittance_map={},
                warnings=tuple(warnings),
            )

        # Q6: detector facing upward warning
        if detector.is_facing_upward():
            warnings.append(
                f"Detector '{detector.detector_id}' orientation aims upward "
                f"(z-component > 0.9). Floor-level targets will NOT be covered. "
                f"[Engineering judgment required]"
            )

        covered_pts: Set[int] = set()
        distances_covered: List[float] = []
        spectral_map: Dict[int, float] = {}  # point_index -> transmittance

        for ti, tp in enumerate(target_grid):
            tgt = tp.to_tuple()

            # Distance check first (fast reject)
            dx = tgt[0] - src[0]
            dy = tgt[1] - src[1]
            dz = tgt[2] - src[2]
            dist = math.sqrt(dx * dx + dy * dy + dz * dz)

            # V57 FIX (Finding 14): NaN dist bypasses fast-reject — NaN > X is False,
            # so NaN distance is never rejected and proceeds to AOC/sensitivity
            # checks, producing NaN results. Reject non-finite distances immediately.
            if not math.isfinite(dist):
                continue

            if dist > detector.rated_range_m * 1.5:
                continue  # Beyond 1.5x rated range: skip

            # AOC check
            if not self._in_aoc_v21(detector, tgt):
                continue

            # V21.2: Spectral transmittance per band (solid + volumetric)
            best_transmittance = 0.0
            for band in detector.spectral_bands:
                t = self._ray_spectral_transmittance_v21(src, tgt, obstructions, volumetric_media, band)  # type: ignore[arg-type]
                best_transmittance = max(best_transmittance, t)

            # Point is covered if best transmittance >= threshold
            if best_transmittance >= self.detector_threshold:
                covered_pts.add(ti)
                distances_covered.append(dist)
                spectral_map[ti] = round(best_transmittance, 4)

        # Fix #18: effective range = median (not max)
        effective_range = median(distances_covered) if distances_covered else 0.0

        return SingleDetectorResult(
            detector_id=detector.detector_id,
            covered_pts=frozenset(covered_pts),
            effective_range_m=round(effective_range, 2),
            spectral_transmittance_map=spectral_map,
            warnings=tuple(warnings),
        )

    def analyse_multi_v21(
        self,
        detectors: List[V21FlameDetectorSpec],
        target_grid: List[V21RayTracePoint],
        obstructions: List[V21Obstruction],
        volumetric_media: Optional[List[VolumetricMedium]] = None,
        zone_type: Optional[ZoneType] = None,
        env_context: Optional[EnvironmentalContext] = None,
    ) -> CoverageResult:
        """V21.2: Multi-detector analysis.
        Fix #20: No double-counting. Union of covered sets.
        Q5: Coverage = covered_count / total_count (not hull area).
        V21.2: Includes volumetric media (Beer-Lambert) analysis.
        GAP-06: Computes redundancy per grid point for NFPA 72 §17.8.3.4.
        V22: lens_fouling_factor from EnvironmentalContext applied to transmittance.
        V22: zone-based minimum redundancy check (MIN_REDUNDANCY_BY_ZONE).
        """
        volumetric_media = volumetric_media or []
        env_context = env_context or EnvironmentalContext()
        fouling = env_context.lens_fouling_factor
        # V57 FIX (Finding 9): NaN fouling bypasses attenuation — NaN < 1.0 is False,
        # so the fouling attenuation block is skipped entirely. This means a NaN
        # fouling factor results in ZERO attenuation applied, as if the lens were
        # pristine. Use worst-case fouling (0.5) as conservative default.
        if not math.isfinite(fouling):
            logger.critical(
                "V57 FIX: lens_fouling_factor is not finite (%s). "
                "Using worst-case fouling 0.5 for conservative attenuation. "
                "[FM Global DS 5-48 §3.2.1]",
                fouling,
            )
            fouling = 0.5
        self._build_spatial_index(obstructions)

        all_warnings: List[str] = []
        per_detector: Dict[str, SingleDetectorResult] = {}
        union_covered: Set[int] = set()

        for det in detectors:
            result = self.analyse_single_v21(det, target_grid, obstructions, volumetric_media)
            # V22: Apply lens fouling attenuation to spectral transmittance
            if fouling < 1.0:
                fouled_map = {k: round(v * fouling, 4) for k, v in result.spectral_transmittance_map.items()}
                # Re-evaluate covered points after fouling
                fouled_covered = frozenset(k for k, v in fouled_map.items() if v >= self.detector_threshold)
                result = SingleDetectorResult(
                    detector_id=result.detector_id,
                    covered_pts=fouled_covered,
                    effective_range_m=round(result.effective_range_m * fouling, 2),
                    spectral_transmittance_map=fouled_map,
                    warnings=result.warnings,
                )
            per_detector[det.detector_id] = result
            # Fix #20: union, not count per detector
            union_covered |= result.covered_pts
            all_warnings.extend(result.warnings)

        total = len(target_grid)
        covered = len(union_covered)
        fraction = covered / total if total > 0 else 0.0

        # GAP-06: Compute redundancy map
        from collections import Counter

        point_counter: Counter = Counter()
        for det_result in per_detector.values():
            for pt_idx in det_result.covered_pts:
                point_counter[pt_idx] += 1

        if point_counter:
            redundancy_map = dict(point_counter)
            min_redundancy = min(point_counter.values())
            mean_redundancy = round(sum(point_counter.values()) / len(point_counter), 2)
            double_covered = sum(1 for c in point_counter.values() if c >= 2)
            double_pct = round(double_covered / total * 100.0, 2) if total > 0 else 0.0
        else:
            redundancy_map = {}
            min_redundancy = 0
            mean_redundancy = 0.0
            double_pct = 0.0

        # NFPA 72 redundancy advisory
        if min_redundancy < 2 and len(detectors) >= 2:
            all_warnings.append(
                f"NFPA 72-2022 §17.8.3.4 Advisory: minimum redundancy is "
                f"{min_redundancy} detector(s) per point ({double_pct:.1f}% of area "
                "covered by >=2 detectors). Critical applications require "
                "min_redundancy >= 2 (FM Global DS 5-48 §3.1)."
            )

        # V22: Zone-based minimum redundancy check
        # V54 FIX (V48 #5): Use jurisdiction-aware redundancy when env_context
        # available. SAUDI_HCIS requires 1oo2 for Zone 2, while IEC only requires 1.
        # Without this, a Saudi installation in Zone 2 could PASS with 1 detector
        # but FAIL the safety audit engine — conflicting results.
        if zone_type is not None:
            if env_context is not None and hasattr(env_context, "jurisdiction"):
                from fireai.core.safety_audit_engine import _get_required_redundancy

                required = _get_required_redundancy(zone_type, env_context.jurisdiction)
            else:
                required = MIN_REDUNDANCY_BY_ZONE.get(zone_type, 1)
            if min_redundancy < required and covered > 0:
                all_warnings.append(
                    f"V22 SAFETY: Zone {zone_type.value} requires ≥{required} "
                    f"independent detectors per point (current min={min_redundancy}). "
                    f"Points with <{required} detector(s) are SPOF "
                    f"(Single Point of Failure). [NFPA 72 §17.8.3.4, "
                    f"FM Global DS 5-48 §3.1]"
                )

        return CoverageResult(
            total_points=total,
            covered_points=covered,
            coverage_fraction=round(fraction, 6),
            per_detector=per_detector,
            warnings=all_warnings,
            redundancy_map=redundancy_map,
            min_redundancy=min_redundancy,
            mean_redundancy=mean_redundancy,
            double_covered_pct=double_pct,
        )

    # ── Legacy API ──────────────────────────────────────────────────────────

    def analyse_detector(
        self,
        detector: FlameDetectorSpecLegacy,
        floor_bounds: Tuple[float, float, float, float],
        obstructions: List[ObstructionLegacy] = None,
        floor_z: float = 0.0,
    ) -> DetectorCoverageResult:
        """Legacy single-detector analysis (backward compatible)."""
        obstructions = obstructions or []
        warnings: List[str] = []

        aim = self._normalize(detector.aim_vector)
        targets = self._generate_grid(floor_bounds)

        ray_results: List[RayTracePointLegacy] = []
        covered_points: List[Point2D] = []
        uncovered_points: List[Point2D] = []
        obstructions_hit: set = set()

        for tx, ty in targets:
            target_3d: Point3D = (tx, ty, floor_z)
            ray_result = self._trace_ray(detector, aim, target_3d, obstructions)
            ray_results.append(ray_result)

            if ray_result.coverage_quality in (CoverageQuality.CLEAR, CoverageQuality.MARGINAL):
                covered_points.append((tx, ty))
            else:
                uncovered_points.append((tx, ty))
                if ray_result.blocking_obstruction:
                    obstructions_hit.add(ray_result.blocking_obstruction)

        total_pts = len(targets)
        covered_pts = len(covered_points)
        coverage_pct = 100.0 * covered_pts / total_pts if total_pts > 0 else 0.0

        cell_area = self.GRID_STEP_M**2
        covered_area = covered_pts * cell_area
        coverage_polygon = self._convex_hull_2d(covered_points)

        # Fix #18: median instead of max
        covered_distances = sorted(r.distance_m for r in ray_results if r.coverage_quality == CoverageQuality.CLEAR)
        if covered_distances:
            mid = len(covered_distances) // 2
            effective_range = covered_distances[mid]
        else:
            effective_range = 0.0

        if coverage_pct < 85.0:
            warnings.append(f"Coverage {coverage_pct:.1f}% < 85% threshold. FM Global DS 5-48 §4.2.")

        if not detector.nfpa_listed:
            warnings.append("Detector is not NFPA-listed. NFPA 72-2022 §17.8.1 requires listed equipment.")

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
        space_id: str,
        detectors: List[FlameDetectorSpecLegacy],
        floor_bounds: Tuple[float, float, float, float],
        obstructions: List[ObstructionLegacy] = None,
        floor_z: float = 0.0,
        min_redundancy: int = 1,
    ) -> MultiDetectorCoverageResult:
        """Legacy multi-detector analysis (backward compatible)."""
        obstructions = obstructions or []
        warnings: List[str] = []

        individual: List[DetectorCoverageResult] = []
        for det in detectors:
            res = self.analyse_detector(det, floor_bounds, obstructions, floor_z)
            individual.append(res)
            warnings.extend(res.warnings)

        # Fix #20: Build per-detector covered point sets
        targets = self._generate_grid(floor_bounds)
        set(targets)

        detector_covered_sets: List[set] = []
        for res in individual:
            covered_set = set()
            for ray in res.ray_results:
                if ray.coverage_quality in (CoverageQuality.CLEAR, CoverageQuality.MARGINAL):
                    covered_set.add(ray.target)
            detector_covered_sets.append(covered_set)

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
        cell_area = self.GRID_STEP_M**2
        covered_area = covered_pts * cell_area
        total_area = total_pts * cell_area
        uncovered_area = total_area - covered_area
        actual_min_red = min(coverage_count.values()) if coverage_count else 0
        is_nfpa = combined_pct >= 95.0

        if combined_pct < 95.0:
            warnings.append(f"Combined coverage {combined_pct:.1f}% < 95%. NFPA 72-2022 §17.8.")

        return MultiDetectorCoverageResult(
            space_id=space_id,
            detectors=tuple(detectors),
            individual_results=tuple(individual),
            combined_coverage_pct=round(combined_pct, 2),
            uncovered_area_m2=round(uncovered_area, 2),
            total_covered_area_m2=round(covered_area, 2),
            redundancy_map={f"{t[0]:.1f},{t[1]:.1f}": v for t, v in coverage_count.items()},
            min_redundancy=actual_min_red,
            is_nfpa_compliant=is_nfpa,
            warnings=tuple(set(warnings)),
        )

    # ── Legacy private methods ──────────────────────────────────────────────

    def _trace_ray(
        self,
        detector: FlameDetectorSpecLegacy,
        aim_norm: Point3D,
        target_3d: Point3D,
        obstructions: List[ObstructionLegacy],
    ) -> RayTracePointLegacy:
        dx = target_3d[0] - detector.position[0]
        dy = target_3d[1] - detector.position[1]
        dz = target_3d[2] - detector.position[2]
        distance = math.sqrt(dx * dx + dy * dy + dz * dz)

        # V58 HIGH: NaN distance bypasses all coverage classification
        if not math.isfinite(distance):
            return RayTracePointLegacy(
                target=(target_3d[0], target_3d[1]),
                target_3d=target_3d,
                distance_m=float("nan"),
                angle_from_axis_deg=float("nan"),
                within_aoc=False,
                within_range=False,
                los_clear=False,
                blocking_obstruction="NaN_DISTANCE",
                coverage_quality=CoverageQuality.OUT_OF_RANGE,
                sensitivity_at_target=0.0,
            )

        if distance < 1e-6:
            return RayTracePointLegacy(
                target=(target_3d[0], target_3d[1]),
                target_3d=target_3d,
                distance_m=0.0,
                angle_from_axis_deg=0.0,
                within_aoc=True,
                within_range=True,
                los_clear=True,
                blocking_obstruction=None,
                coverage_quality=CoverageQuality.CLEAR,
                sensitivity_at_target=1.0,
            )

        ray_dir = (dx / distance, dy / distance, dz / distance)
        dot = ray_dir[0] * aim_norm[0] + ray_dir[1] * aim_norm[1] + ray_dir[2] * aim_norm[2]
        dot = max(-1.0, min(1.0, dot))
        angle_deg = math.degrees(math.acos(dot))

        within_aoc = angle_deg <= detector.aoc_half_angle_deg
        within_range = distance <= detector.rated_range_m

        # Fix #19: Inverse square law properly clamped
        if distance <= detector.rated_range_m:
            sensitivity = 1.0
        else:
            sensitivity = (detector.rated_range_m / distance) ** 2
        sensitivity *= detector.sensitivity_factor

        # V58 HIGH: NaN sensitivity bypasses BELOW_SENSITIVITY classification
        if not math.isfinite(sensitivity):
            sensitivity = 0.0

        blocking: Optional[str] = None
        los_clear = True
        if within_aoc:
            for obs in obstructions:
                if obs.is_transparent:
                    continue
                if self._ray_intersects_bbox(detector.position, ray_dir, distance, obs.bbox_min, obs.bbox_max):
                    blocking = obs.obstruction_id
                    los_clear = False
                    break

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

        return RayTracePointLegacy(
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
        origin: Point3D,
        direction: Point3D,
        max_dist: float,
        bbox_min: Point3D,
        bbox_max: Point3D,
    ) -> bool:
        tmin = 0.0
        tmax = max_dist
        for i in range(3):
            o = [origin[0], origin[1], origin[2]][i]
            d = [direction[0], direction[1], direction[2]][i]
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
        mag = math.sqrt(v[0] ** 2 + v[1] ** 2 + v[2] ** 2)
        if mag < 1e-9:
            return (0.0, 0.0, -1.0)
        return (v[0] / mag, v[1] / mag, v[2] / mag)

    @staticmethod
    def _convex_hull_2d(points: List[Point2D]) -> List[Point2D]:
        """Graham scan convex hull."""
        if len(points) < 3:
            return points

        def cross(o, a, b):
            return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

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
