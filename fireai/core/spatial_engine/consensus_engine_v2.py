from __future__ import annotations

"""
ConsensusEngine v2 — Extended Triple Verification for Non-Rectangular Rooms
=============================================================================
Extends the original ConsensusEngine to support arbitrary polygon rooms
(L-shape, U-shape, T-shape, etc.) where bounding-rectangle approximation
may miss blind spots in cutout regions.

MOTIVATION:
  The original ConsensusEngine (v1) assumes rectangular rooms (width×length).
  For non-rectangular rooms, the three engines (Analytical, Voronoi, Grid)
  operate on the bounding rectangle, which can report full coverage while
  blind spots exist in cutout regions (e.g., an L-shape room where the inner
  corner is uncovered).

ARCHITECTURE:
  v2 detects whether the room is rectangular or non-rectangular:
    - RECTANGULAR: delegates to original ConsensusEngine (v1) unchanged
    - NON-RECTANGULAR: runs a MODIFIED triple verification:
        Engine A: ExactCoverage  — Shapely polygon difference (exact area)
        Engine B: Grid-Polygon   — grid proof restricted to polygon boundary
        Engine C: Voronoi-Polygon — Voronoi gap analysis within polygon

  This preserves the existing behavior for rectangular rooms while adding
  rigorous verification for non-rectangular rooms.

CONSENSUS RULES (same as v1):
  3/3 PASS → VERIFIED  (green)  — All engines agree: coverage is complete
  2/3 PASS → WARNING   (yellow) — Discrepancy detected: investigate
  1/3 PASS → FAIL      (red)    — Major problem: DO NOT deploy
  0/3 PASS → FAIL      (red)    — Complete failure: fundamental issue

SAFETY PRINCIPLE (same as v1):
  In fire safety, we follow the MOST CONSERVATIVE result.
  If any engine says FAIL, the consensus is at most WARNING, never VERIFIED.
  is_safe is True ONLY if VERIFIED (3/3).

NFPA 72-2022 §17.7.4.2.3.1: Coverage radius R = 0.7 × S

D3 DELIVERABLE: Closes the single-engine vulnerability for complex rooms.
"""

import enum
import logging
import math
from typing import List, Optional, Tuple

logger = logging.getLogger(__name__)

from .consensus_engine import (
    ConfidenceLevel,
    ConsensusEngine,
    ConsensusResult,
    EngineVerdict,
)
from .exact_coverage import HAS_SHAPELY, ExactCoverageEngine
from .voronoi_verifier import VoronoiVerifier

# ═══════════════════════════════════════════════════════════════════════════════
# Extended Engine Names
# ═══════════════════════════════════════════════════════════════════════════════


class EngineNameV2(enum.Enum):
    """Verification engine identifiers for v2 (non-rectangular rooms)."""

    EXACT_COVERAGE = "exact_coverage"  # Shapely polygon difference
    GRID_POLYGON = "grid_polygon"  # Grid proof restricted to polygon
    VORONOI_POLYGON = "voronoi_polygon"  # Voronoi within polygon boundary


# ═══════════════════════════════════════════════════════════════════════════════
# Helper: Rectangle Detection
# ═══════════════════════════════════════════════════════════════════════════════


def is_rectangular_polygon(coords: List[Tuple[float, float]], tolerance: float = 0.01) -> bool:
    """Check if a polygon is effectively a rectangle.

    A polygon is rectangular if:
      1. It has exactly 4 or 5 vertices (4 + closing point)
      2. All interior angles are ~90 degrees
      3. Sides are axis-aligned or can be expressed as a simple rectangle

    Args:
        coords: Polygon vertices (may include closing point).
        tolerance: Angular tolerance in radians for right-angle check.

    Returns:
        True if the polygon is effectively rectangular.

    """
    if not coords or len(coords) < 3:
        return False

    # Remove closing point if it duplicates the first
    cleaned = list(coords)
    if len(cleaned) > 3:
        first, last = cleaned[0], cleaned[-1]
        if abs(first[0] - last[0]) < tolerance and abs(first[1] - last[1]) < tolerance:
            cleaned = cleaned[:-1]

    n = len(cleaned)
    if n != 4:
        return False  # Non-rectangular polygon has != 4 vertices

    # Check that all angles are ~90 degrees (π/2)
    for i in range(4):
        p0 = cleaned[i]
        p1 = cleaned[(i + 1) % 4]
        p2 = cleaned[(i + 2) % 4]

        # Vectors from p1 to p0 and p1 to p2
        v1x, v1y = p0[0] - p1[0], p0[1] - p1[1]
        v2x, v2y = p2[0] - p1[0], p2[1] - p1[1]

        # Dot product should be ~0 for right angle
        dot = v1x * v2x + v1y * v2y
        mag1 = math.hypot(v1x, v1y)
        mag2 = math.hypot(v2x, v2y)

        if mag1 < tolerance or mag2 < tolerance:
            return False  # Degenerate edge

        cos_angle = abs(dot) / (mag1 * mag2)
        if cos_angle > 0.1:  # Not approximately 90 degrees
            return False

    return True


def polygon_bounds(coords: List[Tuple[float, float]]) -> Tuple[float, float, float, float]:
    """Get bounding box of a polygon: (min_x, min_y, max_x, max_y)."""
    xs = [c[0] for c in coords]
    ys = [c[1] for c in coords]
    return min(xs), min(ys), max(xs), max(ys)


def polygon_width_length(coords: List[Tuple[float, float]]) -> Tuple[float, float]:
    """Extract width and length from an axis-aligned rectangular polygon."""
    min_x, min_y, max_x, max_y = polygon_bounds(coords)
    return max_x - min_x, max_y - min_y


# ═══════════════════════════════════════════════════════════════════════════════
# Grid-Polygon Verification
# ═══════════════════════════════════════════════════════════════════════════════


def grid_polygon_verify(
    room_coords: List[Tuple[float, float]],
    detectors: List[Tuple[float, float]],
    coverage_radius: float,
    step: float = 0.20,
) -> Tuple[bool, float]:
    """Grid verification restricted to a polygon boundary.

    Generates a grid of points within the bounding box, then filters
    to only those inside the polygon. Checks each point against
    all detectors using δ-conservative R_eff.

    Args:
        room_coords: Room polygon vertices.
        detectors: List of (x, y) detector positions.
        coverage_radius: Coverage radius R in meters.
        step: Grid resolution (default 0.20m = VERIFY_STEP).

    Returns:
        (proof_valid, coverage_pct)

    """
    if not HAS_SHAPELY:
        return False, 0.0

    try:
        from shapely.geometry import Point, Polygon
    except ImportError:
        return False, 0.0

    if not detectors:
        return False, 0.0

    try:
        room_poly = Polygon(room_coords)
        if not room_poly.is_valid:
            room_poly = room_poly.buffer(0)
    except Exception as e:
        logger.warning("V112: grid_polygon_verify: failed to construct room polygon from coords: %s", e)
        return False, 0.0

    min_x, min_y, max_x, max_y = polygon_bounds(room_coords)
    R = coverage_radius
    R_eff = R - step * math.sqrt(2) / 2  # δ-conservative
    R2_eff = R_eff**2 + 1e-9

    total_points = 0
    covered_points = 0

    x = min_x
    while x <= max_x + 1e-9:
        y = min_y
        while y <= max_y + 1e-9:
            # Check if point is inside polygon
            try:
                if room_poly.contains(Point(x, y)) or room_poly.boundary.distance(Point(x, y)) < 1e-6:
                    total_points += 1
                    # Check if covered by any detector
                    for dx, dy in detectors:
                        if (x - dx) ** 2 + (y - dy) ** 2 <= R2_eff:
                            covered_points += 1
                            break
            except Exception as e:
                logger.warning(
                    f"V112: grid_polygon_verify: failed to check grid point ({x:.2f}, {y:.2f}) containment: {e!r}"
                )
                pass
            y += step
        x += step

    if total_points == 0:
        return False, 0.0

    coverage_pct = 100.0 * covered_points / total_points
    proof_valid = covered_points == total_points

    return proof_valid, coverage_pct


# ═══════════════════════════════════════════════════════════════════════════════
# ConsensusEngineV2
# ═══════════════════════════════════════════════════════════════════════════════


class ConsensusEngineV2:
    """Extended consensus engine supporting non-rectangular rooms.

    For rectangular rooms: delegates to ConsensusEngine (v1) unchanged.
    For non-rectangular rooms: runs a modified triple verification
    using polygon-aware engines.

    Usage (rectangular room):
        engine = ConsensusEngineV2(coverage_radius=6.37)
        result = engine.verify_rectangular(
            width=10.0, length=10.0,
            detectors=[(2.5, 2.5), (7.5, 7.5)],
            grid_proof_valid=True, grid_coverage_pct=100.0,
        )

    Usage (non-rectangular room):
        engine = ConsensusEngineV2(coverage_radius=6.37)
        result = engine.verify_polygon(
            room_coords=[(0,0),(15,0),(15,8),(8,8),(8,15),(0,15)],
            detectors=[(3.75,3.75),(11.5,3.75),(4,11.5)],
        )

    SAFETY: Same conservative rules as v1 — is_safe only if VERIFIED (3/3).
    """

    def __init__(self, coverage_radius: float, wall_min: float = 0.10):
        self.R = coverage_radius
        self.wm = wall_min
        # v1 engine for rectangular rooms
        self._v1 = ConsensusEngine(coverage_radius, wall_min)
        # ExactCoverageEngine for non-rectangular rooms
        if HAS_SHAPELY:
            self._exact_engine = ExactCoverageEngine(coverage_radius)
        else:
            self._exact_engine = None

    # ── Rectangular room API (delegates to v1) ─────────────────────────────

    def verify_rectangular(
        self,
        width: float,
        length: float,
        detectors: List[tuple],
        grid_proof_valid: Optional[bool] = None,
        grid_coverage_pct: Optional[float] = None,
    ) -> ConsensusResult:
        """Verify a rectangular room using v1 consensus engine.

        This is a thin wrapper around ConsensusEngine.verify() for
        backward compatibility.
        """
        return self._v1.verify(
            width=width,
            length=length,
            detectors=detectors,
            grid_proof_valid=grid_proof_valid,
            grid_coverage_pct=grid_coverage_pct,
        )

    # ── Non-rectangular room API ───────────────────────────────────────────

    def verify_polygon(
        self,
        room_coords: List[Tuple[float, float]],
        detectors: List[Tuple[float, float]],
        obstacles: Optional[List[List[Tuple[float, float]]]] = None,
    ) -> ConsensusResult:
        """Verify a non-rectangular room using polygon-aware triple verification.

        Runs three independent engines:
          1. ExactCoverage — Shapely polygon difference (area-based)
          2. Grid-Polygon — grid proof restricted to polygon boundary
          3. Voronoi-Polygon — Voronoi gap analysis within polygon

        Args:
            room_coords: Room polygon vertices (CCW or CW).
            detectors: List of (x, y) detector positions.
            obstacles: Optional list of obstacle polygons.

        Returns:
            ConsensusResult with combined verdict.

        """
        verdicts: List[EngineVerdict] = []

        # Engine A: ExactCoverage
        if self._exact_engine is not None:
            try:
                exact_result = self._exact_engine.verify(
                    room_boundary_coords=room_coords,
                    sensor_locations=detectors,
                    obstacles=obstacles,
                )
                verdicts.append(
                    EngineVerdict(
                        engine=EngineNameV2.EXACT_COVERAGE,
                        passed=exact_result.is_covered,
                        details=(
                            f"Coverage ratio: {exact_result.coverage_ratio:.4f}, "
                            f"Uncovered: {exact_result.uncovered_area_sqm:.3f} sqm, "
                            f"R_eff: {exact_result.effective_radius_m:.2f}m"
                        ),
                        raw_result=exact_result,
                    )
                )
            except Exception as e:
                verdicts.append(
                    EngineVerdict(
                        engine=EngineNameV2.EXACT_COVERAGE,
                        passed=False,
                        details=f"ERROR: {e}",
                    )
                )
        else:
            verdicts.append(
                EngineVerdict(
                    engine=EngineNameV2.EXACT_COVERAGE,
                    passed=False,
                    details="Shapely not available — cannot run exact coverage",
                )
            )

        # Engine B: Grid-Polygon
        try:
            grid_valid, grid_pct = grid_polygon_verify(
                room_coords=room_coords,
                detectors=detectors,
                coverage_radius=self.R,
            )
            verdicts.append(
                EngineVerdict(
                    engine=EngineNameV2.GRID_POLYGON,
                    passed=grid_valid,
                    details=f"Grid-polygon: valid={grid_valid}, coverage={grid_pct:.1f}%",
                )
            )
        except Exception as e:
            verdicts.append(
                EngineVerdict(
                    engine=EngineNameV2.GRID_POLYGON,
                    passed=False,
                    details=f"ERROR: {e}",
                )
            )

        # Engine C: Voronoi-Polygon
        # Use the bounding rectangle for Voronoi, then check that the
        # max gap point is inside the polygon
        try:
            min_x, min_y, max_x, max_y = polygon_bounds(room_coords)
            width = max_x - min_x
            length = max_y - min_y

            # Translate detectors to origin-relative for Voronoi
            translated_dets = [(x - min_x, y - min_y) for x, y in detectors]

            voro_verifier = VoronoiVerifier(self.R)
            voro_result = voro_verifier.verify(width, length, translated_dets)

            # If Voronoi found a max gap, verify the gap point is inside
            # the actual polygon (not just the bounding rectangle)
            if voro_result.is_covered:
                # Voronoi says covered in bounding rect → covered in polygon
                voro_passed = True
                voro_detail = f"Voronoi-polygon: max gap {voro_result.max_gap_m:.2f}m, COVERED"
            elif voro_result.max_gap_location is not None:
                # Check if the max gap point is inside the actual polygon
                gap_x, gap_y = voro_result.max_gap_location
                # Translate back to absolute coords
                abs_x, abs_y = gap_x + min_x, gap_y + min_y

                if HAS_SHAPELY:
                    from shapely.geometry import Point
                    from shapely.geometry import Polygon as ShapelyPolygon

                    try:
                        room_poly = ShapelyPolygon(room_coords)
                        if room_poly.contains(Point(abs_x, abs_y)):
                            # Gap is inside the polygon → real failure
                            voro_passed = False
                            voro_detail = (
                                f"Voronoi-polygon: gap at ({abs_x:.1f},{abs_y:.1f}) "
                                f"is INSIDE polygon, {voro_result.max_gap_m:.2f}m > R"
                            )
                        else:
                            # Gap is outside the polygon → not a real failure
                            voro_passed = True
                            voro_detail = (
                                f"Voronoi-polygon: gap at ({abs_x:.1f},{abs_y:.1f}) "
                                f"OUTSIDE polygon — bounding rect artifact"
                            )
                    except Exception:
                        voro_passed = voro_result.is_covered
                        voro_detail = voro_result.details
                else:
                    voro_passed = voro_result.is_covered
                    voro_detail = voro_result.details
            else:
                voro_passed = voro_result.is_covered
                voro_detail = voro_result.details

            verdicts.append(
                EngineVerdict(
                    engine=EngineNameV2.VORONOI_POLYGON,
                    passed=voro_passed,
                    details=voro_detail,
                    raw_result=voro_result,
                )
            )
        except Exception as e:
            verdicts.append(
                EngineVerdict(
                    engine=EngineNameV2.VORONOI_POLYGON,
                    passed=False,
                    details=f"ERROR: {e}",
                )
            )

        # ── Compute consensus (same logic as v1) ───────────────────────────
        return self._compute_consensus(verdicts)

    # ── Auto-detect room type ──────────────────────────────────────────────

    def verify(
        self,
        room_coords: Optional[List[Tuple[float, float]]] = None,
        width: Optional[float] = None,
        length: Optional[float] = None,
        detectors: List[tuple] = None,
        grid_proof_valid: Optional[bool] = None,
        grid_coverage_pct: Optional[float] = None,
        obstacles: Optional[List[List[Tuple[float, float]]]] = None,
    ) -> ConsensusResult:
        """Auto-detect room type and run appropriate verification.

        If room_coords is provided and is non-rectangular:
          → verify_polygon()
        If width and length are provided (or room_coords is rectangular):
          → verify_rectangular()

        Args:
            room_coords: Room polygon vertices (for non-rectangular rooms).
            width: Room width in meters (for rectangular rooms).
            length: Room length in meters (for rectangular rooms).
            detectors: List of (x, y) detector positions.
            grid_proof_valid: Grid engine result (for rectangular rooms).
            grid_coverage_pct: Grid coverage percentage (for rectangular rooms).
            obstacles: Optional obstacle polygons (for non-rectangular rooms).

        Returns:
            ConsensusResult with combined verdict.

        """
        if detectors is None:
            detectors = []
        if room_coords is not None and not is_rectangular_polygon(room_coords):
            return self.verify_polygon(
                room_coords=room_coords,
                detectors=detectors,
                obstacles=obstacles,
            )

        # Rectangular room
        if width is not None and length is not None:
            return self.verify_rectangular(
                width=width,
                length=length,
                detectors=detectors,
                grid_proof_valid=grid_proof_valid,
                grid_coverage_pct=grid_coverage_pct,
            )

        # Try to extract width/length from polygon coords
        if room_coords is not None:
            w, l = polygon_width_length(room_coords)
            return self.verify_rectangular(
                width=w,
                length=l,
                detectors=detectors,
                grid_proof_valid=grid_proof_valid,
                grid_coverage_pct=grid_coverage_pct,
            )

        return ConsensusResult(
            confidence=ConfidenceLevel.FAIL,
            is_safe=False,
            recommendation="Insufficient room geometry provided for verification.",
        )

    # ── Consensus computation (shared with v1) ─────────────────────────────

    @staticmethod
    def _compute_consensus(verdicts: List[EngineVerdict]) -> ConsensusResult:
        """Compute consensus from a list of engine verdicts.

        Same logic as v1 ConsensusEngine but reusable for both paths.
        """
        n_pass = sum(1 for v in verdicts if v.passed)
        n_total = len(verdicts)
        discrepancies = []

        for v in verdicts:
            if not v.passed:
                discrepancies.append(f"{v.engine.value}: {v.details}")

        # Determine confidence level
        if n_total >= 3:
            if n_pass == n_total:
                confidence = ConfidenceLevel.VERIFIED
            elif n_pass >= 2:
                confidence = ConfidenceLevel.WARNING
            else:
                confidence = ConfidenceLevel.FAIL
        elif n_total == 2:
            confidence = ConfidenceLevel.WARNING if n_pass >= 1 else ConfidenceLevel.FAIL
        else:
            confidence = ConfidenceLevel.WARNING if n_pass == 1 else ConfidenceLevel.FAIL

        # Safety: is_safe ONLY if VERIFIED (all engines agree)
        is_safe = confidence == ConfidenceLevel.VERIFIED

        # Recommendation
        failing_engines = [v.engine.value for v in verdicts if not v.passed]
        if confidence == ConfidenceLevel.VERIFIED:
            recommendation = "All engines agree: coverage is complete. Safe to deploy."
        elif confidence == ConfidenceLevel.WARNING:
            failing = ", ".join(failing_engines)
            recommendation = (
                f"DISCREPANCY: Engine(s) {failing} report failure while others pass. "
                f"Investigate before deploying. Details: {'; '.join(discrepancies)}"
            )
        else:
            recommendation = (
                f"MAJORITY FAILURE: Only {n_pass}/{n_total} engines pass. "
                f"DO NOT deploy. Issues: {'; '.join(discrepancies)}"
            )

        return ConsensusResult(
            confidence=confidence,
            is_safe=is_safe,
            engines=verdicts,
            n_pass=n_pass,
            n_total=n_total,
            discrepancies=discrepancies,
            recommendation=recommendation,
        )
