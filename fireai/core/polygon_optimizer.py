"""fireai/core/polygon_optimizer.py  V1.0
======================================
True polygon support for non-rectangular rooms.

Integrates Greedy Set Cover placement with FireAI's existing
DensityOptimizer for rectangular rooms. For non-rectangular rooms
(L-shape, U-shape, T-shape, arbitrary polygon), uses interior grid
placement with NFPA 72 spacing audit.

Architecture:
  - Rectangular polygon -> delegate to DensityOptimizer V7.3 (proven)
  - Non-rectangular     -> Greedy Set Cover on interior grid + NFPA audit
  - Duct analysis via existing duct_detector module

DO NOT modify DensityOptimizer, FloorAnalyser, or BuildingEngine.

NFPA 72 References:
  - Section 17.6.3 — smoke detector coverage
  - Section 17.7.4.2.3.1 — 0.7S rule (R = 0.7 * max_spacing)
  - Table 17.6.3.1.1 — ceiling height / coverage radius
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass, field
from typing import List, Literal, Optional, Tuple

from fireai.core.geometry_utils import (
    bounding_rect_dimensions,
    is_rectangular,
    point_in_polygon,
)
from fireai.core.nfpa72_calculations import (
    CoverageSpec,
    calculate_coverage_radius_from_height,
)
from fireai.core.spatial_engine.density_optimizer import (
    DETECTOR_RADIUS,
    MAX_SPACING_M,
    DensityOptimizer,
    Room,
)

# ── Polygon Room model ──────────────────────────────────────


@dataclass
class PolygonRoom:
    """Room model for polygon-based rooms (including rectangular).

    Attributes:
        room_id:        Unique room identifier.
        polygon:        Corner coordinates as list of (x, y) tuples.
        ceiling_height: Ceiling height in metres (default 3.0).
        detector_type:  Detector type string (default "smoke").
        ducts:          Optional list of duct specification dicts.
        name:           Display name (default same as room_id).

    """

    room_id: str
    polygon: List[Tuple[float, float]]
    ceiling_height: float = 3.0
    detector_type: str = "smoke"
    ducts: List[dict] = field(default_factory=list)
    name: str = ""

    def __post_init__(self):
        if not self.name:
            self.name = self.room_id

    @classmethod
    def from_rect(
        cls,
        room_id: str,
        width: float,
        length: float,
        origin: Tuple[float, float] = (0.0, 0.0),
        ceiling_height: float = 3.0,
        detector_type: str = "smoke",
    ) -> PolygonRoom:
        """Create a rectangular PolygonRoom from dimensions."""
        ox, oy = origin
        return cls(
            room_id=room_id,
            polygon=[(ox, oy), (ox + width, oy), (ox + width, oy + length), (ox, oy + length)],
            ceiling_height=ceiling_height,
            detector_type=detector_type,
        )

    @classmethod
    def from_l_shape(
        cls,
        room_id: str,
        total_width: float,
        total_length: float,
        cutout_width: float,
        cutout_length: float,
        cutout_corner: str = "NE",
        origin: Tuple[float, float] = (0.0, 0.0),
        ceiling_height: float = 3.0,
        detector_type: str = "smoke",
    ) -> PolygonRoom:
        """Create an L-shaped PolygonRoom from dimensions and cutout."""
        ox, oy = origin
        tw, tl = total_width, total_length
        cw, cl = cutout_width, cutout_length

        corners = {
            "NE": [
                (ox, oy),
                (ox + tw, oy),
                (ox + tw, oy + tl - cl),
                (ox + tw - cw, oy + tl - cl),
                (ox + tw - cw, oy + tl),
                (ox, oy + tl),
            ],
            "NW": [
                (ox, oy),
                (ox + tw, oy),
                (ox + tw, oy + tl),
                (ox + cw, oy + tl),
                (ox + cw, oy + tl - cl),
                (ox, oy + tl - cl),
            ],
            "SE": [
                (ox, oy),
                (ox + tw - cw, oy),
                (ox + tw - cw, oy + cl),
                (ox + tw, oy + cl),
                (ox + tw, oy + tl),
                (ox, oy + tl),
            ],
            "SW": [(ox, oy), (ox + tw, oy), (ox + tw, oy + tl), (ox, oy + tl), (ox, oy + cl), (ox + cw, oy + cl)],
        }
        return cls(
            room_id=room_id,
            polygon=corners[cutout_corner.upper()],
            ceiling_height=ceiling_height,
            detector_type=detector_type,
        )


# ── Output model ─────────────────────────────────────────────


@dataclass
class PolygonRoomSummary:
    """Result summary for a polygon room analysis.

    Attributes:
        room_id:        Room identifier.
        detector_type:  Detector type used.
        polygon:        Original polygon coordinates.
        detectors:      Detector positions as (x, y) tuples.
        count:          Number of detectors placed.
        coverage_pct:   Coverage percentage on polygon interior grid.
        proof_valid:    True if coverage >= 99.99% and NFPA audit passes.
        nfpa_valid:     True if NFPA 72 spacing rules are satisfied.
        wall_violations: Number of detectors outside the polygon.
        method:         Placement method ("rectangular" or "greedy_polygon").
        spacing_violations: List of NFPA spacing violation descriptions.
        coverage_radius: Coverage radius used (metres).
        ceiling_height: Ceiling height (metres).
        nfpa_table_ref: NFPA 72 table reference for radius.
        radius_warning: Warning about radius if ceiling out of range.
        analysis_ms:    Wall-clock analysis time in milliseconds.
        duct_devices:   List of duct detector results.
        duct_warnings:  List of duct analysis warnings.

    """

    room_id: str
    detector_type: str
    polygon: List[Tuple[float, float]]
    detectors: List[Tuple[float, float]]
    count: int
    coverage_pct: float
    proof_valid: bool
    nfpa_valid: bool
    wall_violations: int
    method: str
    spacing_violations: List[str] = field(default_factory=list)
    coverage_radius: float = DETECTOR_RADIUS
    ceiling_height: Optional[float] = None
    nfpa_table_ref: str = "NFPA 72-2022 Table 17.6.3.1.1"
    radius_warning: Optional[str] = None
    analysis_ms: float = 0.0
    duct_devices: List = field(default_factory=list)
    duct_warnings: List[str] = field(default_factory=list)


# ── Internal helpers ─────────────────────────────────────────


def _generate_interior_grid(
    polygon: List[Tuple[float, float]],
    spacing: float,
) -> List[Tuple[float, float]]:
    """Return all grid points that lie strictly inside *polygon*."""
    xs = [p[0] for p in polygon]
    ys = [p[1] for p in polygon]
    min_x, max_x = min(xs), max(xs)
    min_y, max_y = min(ys), max(ys)

    points: List[Tuple[float, float]] = []
    x = min_x + spacing / 2.0
    while x < max_x:
        y = min_y + spacing / 2.0
        while y < max_y:
            pt = (round(x, 4), round(y, 4))
            if point_in_polygon(pt, polygon):
                points.append(pt)
            y += spacing
        x += spacing
    return points


def _greedy_set_cover(
    interior_points: List[Tuple[float, float]],
    polygon: List[Tuple[float, float]],
    radius: float,
) -> List[Tuple[float, float]]:
    """Greedy Set Cover placement on polygon interior.

    Candidate positions = interior_points.
    Each candidate covers all interior_points within *radius*.
    Greedily pick the candidate that covers the most uncovered points
    until all points are covered.
    """
    if not interior_points:
        return []

    r2 = radius * radius

    # Pre-compute coverage sets (index-based for speed)
    n = len(interior_points)
    coverage: List[List[int]] = []
    for _ci, cand in enumerate(interior_points):
        covered = [i for i, pt in enumerate(interior_points) if (pt[0] - cand[0]) ** 2 + (pt[1] - cand[1]) ** 2 <= r2]
        coverage.append(covered)

    uncovered = set(range(n))
    chosen: List[Tuple[float, float]] = []

    while uncovered:
        # Pick candidate with maximum overlap with uncovered set
        best_ci = max(
            range(len(interior_points)),
            key=lambda ci: len(uncovered.intersection(coverage[ci])),
        )
        chosen.append(interior_points[best_ci])
        uncovered -= set(coverage[best_ci])

    return chosen


def _coverage_percentage(
    detectors: List[Tuple[float, float]],
    interior_points: List[Tuple[float, float]],
    radius: float,
) -> float:
    """Compute coverage percentage of detectors on interior grid points."""
    if not interior_points:
        return 100.0
    r2 = radius * radius
    covered = sum(
        1 for pt in interior_points if any((pt[0] - d[0]) ** 2 + (pt[1] - d[1]) ** 2 <= r2 for d in detectors)
    )
    return round(100.0 * covered / len(interior_points), 4)


def _count_wall_violations(
    detectors: List[Tuple[float, float]],
    polygon: List[Tuple[float, float]],
) -> int:
    """Count detectors that fall outside the polygon."""
    return sum(1 for d in detectors if not point_in_polygon(d, polygon))


def _audit_nfpa_spacing(
    detectors: List[Tuple[float, float]],
    max_spacing: float = MAX_SPACING_M,
) -> List[str]:
    """Check NFPA 72 spacing between adjacent detectors.

    For each detector, verify that the nearest neighbor is within
    max_spacing. Returns list of violation descriptions.

    NFPA 72 §17.6.3 — inter-detector spacing must not exceed max_spacing.
    """
    if len(detectors) <= 1:
        return []

    violations: List[str] = []
    max_gap = 0.0
    for i, (x1, y1) in enumerate(detectors):
        min_dist = float("inf")
        for j, (x2, y2) in enumerate(detectors):
            if i == j:
                continue
            min_dist = min(min_dist, math.hypot(x1 - x2, y1 - y2))
        max_gap = max(max_gap, min_dist)

    if max_gap > max_spacing * 1.01:
        violations.append(f"Max inter-detector spacing {max_gap:.2f}m > S={max_spacing:.2f}m (NFPA 72 §17.6.3)")
    return violations


# ── Main optimizer ───────────────────────────────────────────


class PolygonDensityOptimizer:
    """Polygon-aware detector placement optimizer.

    Strategy:
        - Rectangular polygon -> delegate to DensityOptimizer V7.3 (proven).
        - Non-rectangular     -> Greedy Set Cover on interior grid
                                 + NFPA 72 spacing audit.

    This is a standalone tool. It does NOT modify DensityOptimizer,
    FloorAnalyser, or BuildingEngine.

    Usage
    -----
        from fireai.core.polygon_optimizer import PolygonDensityOptimizer, PolygonRoom

        room = PolygonRoom.from_l_shape(
            room_id="L1",
            total_width=20, total_length=15,
            cutout_width=8, cutout_length=6,
            cutout_corner="NE",
            ceiling_height=3.0,
        )
        opt = PolygonDensityOptimizer()
        result = opt.optimize_polygon(room)
        print(f"Count={result.count}, Coverage={result.coverage_pct}%, "
              f"Valid={result.proof_valid}, Method={result.method}")
    """

    # Grid resolution: fraction of radius used as interior grid spacing
    GRID_FRACTION = 0.5

    def __init__(self) -> None:
        self._rect_optimizer = DensityOptimizer()

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    def optimize_polygon(self, room: PolygonRoom) -> PolygonRoomSummary:
        """Optimise detector placement for a polygon room.

        Args:
            room: PolygonRoom with polygon, ceiling_height, detector_type.

        Returns:
            PolygonRoomSummary with detectors, coverage, compliance info.

        """
        t0 = time.time()

        # Calculate NFPA 72 coverage radius from ceiling height
        cov_det_type: Literal['smoke', 'heat'] = "heat" if "heat" in room.detector_type.lower() else "smoke"
        spec = calculate_coverage_radius_from_height(room.ceiling_height, cov_det_type)
        radius = spec.radius

        if is_rectangular(room.polygon):
            summary = self._optimize_rectangular(room, radius, spec)
        else:
            summary = self._optimize_greedy(room, radius, spec)

        # Populate common fields
        summary.coverage_radius = radius
        summary.ceiling_height = room.ceiling_height
        summary.nfpa_table_ref = spec.nfpa_ref
        summary.radius_warning = spec.warning
        summary.analysis_ms = round((time.time() - t0) * 1000, 1)

        # Duct analysis (optional, uses existing duct_detector module)
        if room.ducts:
            self._inject_duct_analysis(room, summary)

        return summary

    # ------------------------------------------------------------------
    # Rectangular path - delegate to DensityOptimizer V7.3
    # ------------------------------------------------------------------

    def _optimize_rectangular(
        self,
        room: PolygonRoom,
        radius: float,
        spec: CoverageSpec,
    ) -> PolygonRoomSummary:
        """Delegate rectangular rooms to the proven DensityOptimizer."""
        width, length, min_x, min_y = bounding_rect_dimensions(room.polygon)
        rect_room = Room(
            name=room.name,
            width=width,
            length=length,
            ceiling_height=room.ceiling_height,
        )
        layout = self._rect_optimizer.optimize(rect_room, coverage_radius=radius)

        # Translate detectors back to polygon coordinate space
        translated = [(round(x + min_x, 4), round(y + min_y, 4)) for x, y in layout.detectors]

        return PolygonRoomSummary(
            room_id=room.room_id,
            detector_type=room.detector_type,
            polygon=room.polygon,
            detectors=translated,
            count=layout.count,
            coverage_pct=layout.coverage_pct,
            proof_valid=layout.proof_valid,
            nfpa_valid=layout.nfpa_valid,
            wall_violations=layout.wall_violations,
            method="rectangular",
            spacing_violations=[],
        )

    # ------------------------------------------------------------------
    # Non-rectangular path - Greedy Set Cover + NFPA audit
    # ------------------------------------------------------------------

    def _optimize_greedy(
        self,
        room: PolygonRoom,
        radius: float,
        spec: CoverageSpec,
    ) -> PolygonRoomSummary:
        """Greedy Set Cover placement for non-rectangular polygons.

        1. Generate interior grid points within the polygon
        2. Run greedy set cover to select detector positions
        3. Verify coverage on the interior grid
        4. Audit NFPA 72 inter-detector spacing
        5. Check wall violations (detectors outside polygon)
        """
        spacing = radius * self.GRID_FRACTION
        interior_pts = _generate_interior_grid(room.polygon, spacing)

        detectors = _greedy_set_cover(interior_pts, room.polygon, radius)

        cov_pct = _coverage_percentage(detectors, interior_pts, radius)
        wall_viol = _count_wall_violations(detectors, room.polygon)
        spacing_violations = _audit_nfpa_spacing(detectors)

        # Proof is valid only if:
        # 1. Coverage >= 99.99%
        # 2. No wall violations (all detectors inside polygon)
        # 3. NFPA spacing rules are satisfied
        nfpa_valid = len(spacing_violations) == 0
        proof_valid = cov_pct >= 99.99 and wall_viol == 0 and nfpa_valid

        return PolygonRoomSummary(
            room_id=room.room_id,
            detector_type=room.detector_type,
            polygon=room.polygon,
            detectors=detectors,
            count=len(detectors),
            coverage_pct=cov_pct,
            proof_valid=proof_valid,
            nfpa_valid=nfpa_valid,
            wall_violations=wall_viol,
            method="greedy_polygon",
            spacing_violations=spacing_violations,
        )

    # ------------------------------------------------------------------
    # Duct analysis (optional)
    # ------------------------------------------------------------------

    def _inject_duct_analysis(
        self,
        room: PolygonRoom,
        summary: PolygonRoomSummary,
    ) -> None:
        """Run duct detector analysis using the existing duct_detector module.

        Uses the correct API: analyse_ducts(ducts: List[DuctSpec]).
        Converts dict entries to DuctSpec if needed.
        """
        try:
            from fireai.core.duct_detector import (
                DuctSpec,
                analyse_ducts,
            )
        except ImportError:
            summary.duct_warnings.append("duct_detector module not available")
            return

        # Convert dicts to DuctSpec if needed
        duct_specs: list[DuctSpec] = []  # type: ignore[arg-type]
        for d in room.ducts:
            if isinstance(d, DuctSpec):
                duct_specs.append(d)
            elif isinstance(d, dict):
                try:
                    duct_specs.append(DuctSpec(**d))
                except TypeError:
                    summary.duct_warnings.append(f"Invalid duct spec: {d}")
            else:
                summary.duct_warnings.append(f"Duct entry must be DuctSpec or dict, got {type(d).__name__}")

        if not duct_specs:
            return

        results = analyse_ducts(duct_specs)  # type: ignore[arg-type]
        all_warnings = [w for r in results for w in r.warnings]

        summary.duct_devices = results
        summary.duct_warnings = all_warnings
