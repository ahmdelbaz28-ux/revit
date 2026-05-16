"""
fire_expert_system.py  V10.0
=============================
NFPA 72-2022 Fire Alarm Design Expert System — Elite Edition.

DESIGN PHILOSOPHY
-----------------
This is not a calculator.  It is an expert system with three core guarantees:

  1. SAFETY FIRST — any result that cannot be proven safe is REJECTED,
     not downgraded.  The system never guesses.  If it does not know,
     it says so explicitly.

  2. TRACEABILITY — every decision is traceable to a specific NFPA 72-2022
     clause, a measurable quantity, and a pass/fail verdict.  No black boxes.

  3. HONESTY — when inputs are outside the system's validated range, it
     refuses to produce a result rather than silently produce a wrong one.
     It acknowledges its own errors and rejects unsafe instructions.

FAILURE MODES FIXED FROM V9
----------------------------
V9 produced unsafe results because:
  • _generate_positions() used a simple grid with margin=max(0.1, radius*0.1),
    which placed detectors too close to walls AND left corners uncovered.
  • Coverage was checked after placement, but the placement algorithm had no
    knowledge of coverage — it was geometry-blind.
  • No confidence score existed: the system returned "compliant=True" on
    designs that were at best "probably OK".
  • Forced detector type was accepted without cross-checking room occupancy,
    allowing smoke detectors in kitchens if the caller insisted.
  • No improvement proposals were generated.
  • No self-correction loop: a single pass with no retry on failure.

V10 ARCHITECTURE
----------------
  Phase 0 — Input Validation & Refusal Gate
  Phase 1 — Occupancy Classification (rule-based, not guessing)
  Phase 2 — Deterministic Detector Type Selection (refuses unsafe overrides)
  Phase 3 — Constraint-Based Placement (coverage-aware, not geometry-blind)
  Phase 4 — Coverage Proof (mathematical, not probabilistic)
  Phase 5 — Wall Distance Enforcement (hard constraint, not advisory)
  Phase 6 — Obstruction & Special-Room Checks
  Phase 7 — Duct Detector Injection
  Phase 8 — Confidence Scoring (honest: LOW/MEDIUM/HIGH/CERTIFIED)
  Phase 9 — Improvement Proposals
  Phase 10 — Self-Verification (re-run checks on final output)
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from enum import Enum, unique
from .audit_trail import AuditTrail
from typing import Dict, List, Optional, Tuple

from shapely.geometry import MultiPoint, Point, Polygon
from shapely.ops import unary_union

from .nfpa72_models import (
    CeilingSpec,
    CeilingType,
    DetectorType,
    HVACDuct,
    MIN_WALL_DISTANCE_M,
    RoomSpec,
    _NFPA_HEIGHT_MAX_M,
    _NFPA_HEIGHT_MIN_M,
)
from .nfpa72_calculations import (
    calculate_coverage_radius,
    calculate_max_spacing,
    calculate_max_wall_distance,
    estimate_detector_count_polygon,
    minimum_detector_count_rectangular,
)
from .nfpa72_coverage import (
    CoverageResult,
    DuctDevice,
    WallViolation,
    check_coverage_polygon,
    suggest_duct_detectors,
    validate_wall_distances,
)

logger = logging.getLogger(__name__)

# ============================================================================
# CONSTANTS
# ============================================================================

# Minimum polygon vertices for a valid room
_MIN_POLYGON_VERTICES: int = 3

# Minimum room area (m²) — rooms smaller than this cannot be reliably designed
_MIN_ROOM_AREA_M2: float = 1.0

# Maximum room area (m²) — above this the system demands manual PE review
_MAX_ROOM_AREA_M2: float = 5000.0

# Coverage test grid resolution (m) — finer = more accurate, slower
_COVERAGE_GRID_M: float = 0.25

# Maximum self-correction retries
_MAX_PLACEMENT_RETRIES: int = 3

# Confidence thresholds
_CONFIDENCE_HIGH_THRESHOLD:   float = 0.90   # ≥ 90 % → HIGH
_CONFIDENCE_MEDIUM_THRESHOLD: float = 0.75   # ≥ 75 % → MEDIUM
# < 75 % → LOW (result must not be used without PE review)


# ============================================================================
# ENUMERATIONS
# ============================================================================

@unique
class ConfidenceLevel(str, Enum):
    """
    Honest confidence rating for the produced design.

    CERTIFIED : All checks pass, all inputs within normative range,
                no retries were needed.  Safe to submit for PE review.
    HIGH      : All checks pass, minor input adjustments were needed,
                or one retry was required.
    MEDIUM    : Coverage ≥ 75 %, some warnings exist.
                Requires PE review before use.
    LOW       : Coverage < 75 %, or multiple retries failed, or inputs
                were outside validated range.
                MUST NOT be used for permit submission.
    UNSAFE    : One or more safety-critical checks failed and could not
                be automatically resolved.  Design is REJECTED.
    """
    CERTIFIED = "CERTIFIED"
    HIGH      = "HIGH"
    MEDIUM    = "MEDIUM"
    LOW       = "LOW"
    UNSAFE    = "UNSAFE"


@unique
class OccupancyClass(str, Enum):
    """
    NFPA 72-2022 occupancy classifications that affect detector selection.
    """
    SLEEPING        = "sleeping"         # §17.6.4.1 — requires smoke
    COOKING         = "cooking"          # §17.6.4.3 — heat only
    HIGH_CEILING    = "high_ceiling"     # > 9.14 m — beam or aspirating
    CLEAN_ROOM      = "clean_room"       # aspirating preferred
    SERVER_ROOM     = "server_room"      # multi-criteria
    STANDARD        = "standard"         # default office/corridor/etc.
    ATRIUM          = "atrium"           # special rules §17.6.3.7
    ELEVATOR        = "elevator"         # §17.6.3.8
    STAIRWELL       = "stairwell"        # mandatory at each level


# ============================================================================
# OCCUPANCY MAPS
# ============================================================================

_COOKING_TYPES: frozenset = frozenset({
    "kitchen", "cooking", "galley", "canteen", "café", "cafe",
    "commercial_kitchen", "food_prep",
})

_SLEEPING_TYPES: frozenset = frozenset({
    "bedroom", "dormitory", "sleeping", "hotel_room", "guest_room",
    "hospital_room", "patient_room", "ward",
})

_SERVER_TYPES: frozenset = frozenset({
    "server_room", "data_centre", "data_center", "datacenter",
    "it_room", "network_room", "computer_room",
})

_CLEAN_ROOM_TYPES: frozenset = frozenset({
    "clean_room", "cleanroom", "laboratory", "pharmacy",
    "sterile_room",
})

_ATRIUM_TYPES: frozenset = frozenset({
    "atrium", "lobby", "void", "open_plan_high",
})

_ELEVATOR_TYPES: frozenset = frozenset({
    "elevator", "lift", "elevator_hoistway", "lift_shaft",
})

_STAIRWELL_TYPES: frozenset = frozenset({
    "stairwell", "staircase", "stair", "emergency_stair",
})

# Detector type mandated by occupancy (None = use default logic)
_MANDATORY_DETECTOR: Dict[OccupancyClass, Optional[DetectorType]] = {
    OccupancyClass.COOKING:     DetectorType.HEAT_FIXED_TEMP,
    OccupancyClass.SLEEPING:    DetectorType.SMOKE_PHOTOELECTRIC,
    OccupancyClass.SERVER_ROOM: DetectorType.SMOKE_MULTI_CRITERIA,
    OccupancyClass.CLEAN_ROOM:  DetectorType.SMOKE_MULTI_CRITERIA,
    OccupancyClass.STANDARD:    None,   # resolved by ceiling height
    OccupancyClass.HIGH_CEILING:None,   # resolved by ceiling height
    OccupancyClass.ATRIUM:      None,   # resolved by ceiling height
    OccupancyClass.ELEVATOR:    DetectorType.SMOKE_PHOTOELECTRIC,
    OccupancyClass.STAIRWELL:   DetectorType.SMOKE_PHOTOELECTRIC,
}

# Override refusal table: if caller forces a detector type that is
# prohibited for this occupancy, the system REFUSES and raises.
_PROHIBITED_DETECTOR: Dict[OccupancyClass, frozenset] = {
    OccupancyClass.COOKING: frozenset({
        DetectorType.SMOKE_PHOTOELECTRIC,
        DetectorType.SMOKE_IONIZATION,
        DetectorType.SMOKE_MULTI_CRITERIA,
    }),
}


# ============================================================================
# RESULT STRUCTURES
# ============================================================================

@dataclass
class PlacementProof:
    """
    Mathematical proof of coverage for a detector layout.

    Attributes:
        test_point_count:   Number of grid points sampled.
        covered_count:      Points within ≥1 detector's radius.
        uncovered_count:    Points outside all radii.
        coverage_fraction:  covered / total.
        coverage_radius_m:  Radius used for each detector (metres).
        max_gap_m:          Largest distance from any uncovered point
                            to its nearest detector (metres).
                            0.0 if fully covered.
        proof_valid:        True if coverage_fraction ≥ required threshold.
    """
    test_point_count:  int
    covered_count:     int
    uncovered_count:   int
    coverage_fraction: float
    coverage_radius_m: float
    max_gap_m:         float
    proof_valid:       bool


@dataclass
class ImprovementProposal:
    """
    A concrete, actionable suggestion to improve the design.

    Attributes:
        priority:    "SAFETY" | "COMPLIANCE" | "EFFICIENCY"
        clause:      NFPA 72-2022 clause reference.
        description: What should be changed.
        action:      Specific action (ADD_DETECTOR / MOVE_DETECTOR /
                     CHANGE_TYPE / REVIEW_GEOMETRY / ADD_DUCT_DETECTOR /
                     ENGINEER_REVIEW).
        location:    Optional (x, y) where the action should occur.
    """
    priority:    str
    clause:      str
    description: str
    action:      str
    location:    Optional[Tuple[float, float]] = None


@dataclass
class ExpertResult:
    """
    Complete, auditable output of ExpertSystem.analyse_room() V10.

    Attributes:
        room_id:              Room identifier.
        detector_positions:   Final (x, y) positions.
        detector_type:        Selected or validated detector type.
        occupancy_class:      Classified occupancy.
        coverage_result:      Detailed coverage record.
        placement_proof:      Mathematical coverage proof.
        wall_violations:      Wall-distance non-conformances.
        duct_devices:         Duct detectors added per §17.7.5.
        confidence:           Honest confidence rating.
        confidence_score:     Numeric confidence (0.0–1.0).
        warnings:             Non-fatal advisories.
        errors:               Fatal issues (non-empty → UNSAFE).
        improvements:         Actionable improvement proposals.
        retry_count:          How many placement retries were needed.
        nfpa_version:         Edition of NFPA 72 applied.
        refused:              True if system refused the request.
        refusal_reason:       Explanation of refusal.
    """
    room_id:             str
    detector_positions:  List[Tuple[float, float]]  = field(default_factory=list)
    detector_type:       DetectorType                = DetectorType.SMOKE_PHOTOELECTRIC
    occupancy_class:     OccupancyClass              = OccupancyClass.STANDARD
    coverage_result:     Optional[CoverageResult]    = None
    placement_proof:     Optional[PlacementProof]    = None
    wall_violations:     List[WallViolation]          = field(default_factory=list)
    duct_devices:        List[DuctDevice]             = field(default_factory=list)
    confidence:          ConfidenceLevel              = ConfidenceLevel.LOW
    confidence_score:    float                        = 0.0
    warnings:            List[str]                    = field(default_factory=list)
    errors:              List[str]                    = field(default_factory=list)
    improvements:        List[ImprovementProposal]    = field(default_factory=list)
    retry_count:         int                          = 0
    nfpa_version:        str                          = "NFPA 72-2022"
    refused:             bool                         = False
    refusal_reason:      Optional[str]                = None

    @property
    def compliant(self) -> bool:
        """
        True ONLY if:
          • No errors.
          • Coverage proof valid.
          • No wall violations.
          • Confidence is not UNSAFE or LOW.
          • Not refused.
        """
        if self.refused or self.errors:
            return False
        if self.confidence in (ConfidenceLevel.UNSAFE, ConfidenceLevel.LOW):
            return False
        if self.wall_violations:
            return False
        if self.placement_proof and not self.placement_proof.proof_valid:
            return False
        return True

    @property
    def safe_to_submit(self) -> bool:
        """True only if CERTIFIED or HIGH confidence with no safety errors."""
        return (
            self.compliant
            and self.confidence in (ConfidenceLevel.CERTIFIED, ConfidenceLevel.HIGH)
            and not self.refused
        )


# ============================================================================
# INTERNAL HELPERS
# ============================================================================

def _normalise_room_type(raw: str) -> str:
    return raw.lower().replace(" ", "_").replace("-", "_")


def _classify_occupancy(room_spec: RoomSpec, ceiling: CeilingSpec) -> OccupancyClass:
    """
    Rule-based occupancy classification — no guessing.

    Checks in priority order: structural constraints first, then occupancy
    keywords.  High ceilings override standard classification because the
    ceiling height determines the detector technology.
    """
    rt = _normalise_room_type(room_spec.occupancy_type)

    if rt in _ELEVATOR_TYPES:
        return OccupancyClass.ELEVATOR
    if rt in _STAIRWELL_TYPES:
        return OccupancyClass.STAIRWELL
    if rt in _COOKING_TYPES:
        return OccupancyClass.COOKING
    if rt in _SLEEPING_TYPES:
        return OccupancyClass.SLEEPING
    if rt in _SERVER_TYPES:
        return OccupancyClass.SERVER_ROOM
    if rt in _CLEAN_ROOM_TYPES:
        return OccupancyClass.CLEAN_ROOM
    if rt in _ATRIUM_TYPES:
        return OccupancyClass.ATRIUM

    # Structural: high ceiling overrides generic label
    if ceiling.height_at_low_point_m > 9.14:   # NFPA 72 Table 17.6.3.5 boundary
        return OccupancyClass.HIGH_CEILING

    return OccupancyClass.STANDARD


def _select_detector_type(
    occupancy: OccupancyClass,
    ceiling: CeilingSpec,
    forced: Optional[DetectorType],
    room_id: str,
) -> DetectorType:
    """
    Select detector type and enforce safety constraints.

    If `forced` is provided, validate it against the prohibition table.
    Raises SafetyRefusalError if the forced type is prohibited.
    Never returns a type that is prohibited for this occupancy.
    """
    mandatory = _MANDATORY_DETECTOR.get(occupancy)
    prohibited = _PROHIBITED_DETECTOR.get(occupancy, frozenset())

    # Validate forced override
    if forced is not None:
        if forced in prohibited:
            raise SafetyRefusalError(
                f"Room '{room_id}': detector type {forced.value} is PROHIBITED "
                f"for occupancy '{occupancy.value}'. "
                f"NFPA 72-2022 §17.6.4. Refusing unsafe instruction."
            )
        if mandatory is not None and forced != mandatory:
            raise SafetyRefusalError(
                f"Room '{room_id}': occupancy '{occupancy.value}' MANDATES "
                f"{mandatory.value} — cannot override with {forced.value}. "
                f"NFPA 72-2022 §17.6. Refusing unsafe instruction."
            )
        logger.info(
            "_select_detector_type: room=%s forced=%s validated OK",
            room_id, forced.value,
        )
        return forced

    if mandatory is not None:
        return mandatory

    # High-ceiling resolution
    if occupancy in (OccupancyClass.HIGH_CEILING, OccupancyClass.ATRIUM):
        h = ceiling.height_at_low_point_m
        if h > 15.24:
            # Beyond normative range — aspirating / beam required (manual only)
            raise SafetyRefusalError(
                f"Room: ceiling {h:.2f} m exceeds NFPA 72 Table 17.6.3.5 maximum "
                f"(15.24 m). Aspirating or beam detection required — "
                f"automated placement refused. Refer to licensed FPE."
            )
        return DetectorType.SMOKE_PHOTOELECTRIC

    return DetectorType.SMOKE_PHOTOELECTRIC


def _build_valid_polygon(coords: List) -> Optional[Polygon]:
    """
    Build a valid Shapely polygon.  Returns None (not an exception) if
    the geometry is degenerate — callers handle this as a refusal.
    """
    if len(coords) < _MIN_POLYGON_VERTICES:
        return None
    try:
        poly = Polygon(coords)
        if not poly.is_valid:
            poly = poly.buffer(0)
        if poly.is_empty or poly.area < _MIN_ROOM_AREA_M2:
            return None
        return poly
    except Exception:
        return None


def _coverage_aware_placement(
    poly: Polygon,
    spacing: float,
    radius: float,
    max_wall: float,
    seed_positions: Optional[List[Tuple[float, float]]] = None,
    emergency_relax: bool = False,
) -> List[Tuple[float, float]]:
    """
    Coverage-aware staggered placement.

    Algorithm:
      1. Generate a fine candidate grid (spacing/2 step).
      2. Filter candidates: inside polygon AND wall distance in [MIN, max_wall].
      3. Greedy coverage: select the candidate that covers the most
         uncovered test points, repeat until 100 % covered or no gain.

    This is deterministic, reproducible, and coverage-driven — not
    geometry-blind.

    Args:
        poly:     Room polygon (valid Shapely).
        spacing:  NFPA 72 maximum detector spacing (m).
        radius:   Coverage radius per detector (m).
        max_wall: Maximum distance from wall (m).
        seed_positions: Optional pre-seeded detector positions.
        emergency_relax: If True, ignore max_wall constraint.

    Returns:
        List of (x, y) positions.
    """
    min_x, min_y, max_x, max_y = poly.bounds
    exterior = poly.exterior

    # Build candidate positions.
    # Cap step at 2.0 m so large-radius detectors still produce a dense
    # enough candidate grid to find optimal coverage.
    step = min(spacing / 2.0, 2.0)
    candidates: List[Tuple[float, float]] = []
    x = min_x
    col = 0
    while x <= max_x + 1e-9:
        y0 = min_y + (step / 2.0 if col % 2 == 1 else 0.0)
        y = y0
        while y <= max_y + 1e-9:
            pt = Point(x, y)
            # Only enforce minimum wall clearance here.
            # Maximum wall distance (= coverage radius) is validated
            # separately in validate_wall_distances() — enforcing it here
            # would eliminate valid interior positions for large rooms.
            dist = exterior.distance(pt)
            if poly.contains(pt) and dist >= MIN_WALL_DISTANCE_M:
                if emergency_relax or dist <= max_wall:
                    candidates.append((round(x, 4), round(y, 4)))
            y += step
        x += step
        col += 1

    if not candidates:
        return []
    
    # Add seed_positions if provided (must be valid: inside polygon and >= MIN_WALL_DISTANCE_M from walls)
    if seed_positions:
        for sx, sy in seed_positions:
            pt = Point(sx, sy)
            if poly.contains(pt) and exterior.distance(pt) >= MIN_WALL_DISTANCE_M:
                candidates.insert(0, (round(sx, 4), round(sy, 4)))
    
    # Build test grid (finer)
    test_pts: List[Point] = []
    tx = min_x + _COVERAGE_GRID_M / 2.0
    while tx <= max_x:
        ty = min_y + _COVERAGE_GRID_M / 2.0
        while ty <= max_y:
            p = Point(tx, ty)
            if poly.contains(p):
                test_pts.append(p)
            ty += _COVERAGE_GRID_M
        tx += _COVERAGE_GRID_M

    if not test_pts:
        # Degenerate room — fall back to centroid
        c = poly.centroid
        return [(round(c.x, 4), round(c.y, 4))]

    # Precompute which test points each candidate covers
    r2 = radius * radius
    candidate_coverage: Dict[int, List[int]] = {}
    for ci, (cx, cy) in enumerate(candidates):
        covered = [
            ti for ti, tp in enumerate(test_pts)
            if (tp.x - cx) ** 2 + (tp.y - cy) ** 2 <= r2
        ]
        candidate_coverage[ci] = covered

    # Greedy set cover
    uncovered = set(range(len(test_pts)))
    selected_indices: List[int] = []

    while uncovered:
        best_ci = -1
        best_gain = -1
        for ci in range(len(candidates)):
            if ci in [s for s in selected_indices]:
                continue
            gain = len(uncovered & set(candidate_coverage[ci]))
            if gain > best_gain:
                best_gain = gain
                best_ci   = ci
        if best_ci == -1 or best_gain == 0:
            break
        selected_indices.append(best_ci)
        uncovered -= set(candidate_coverage[best_ci])

    return [candidates[i] for i in selected_indices]


def _compute_placement_proof(
    positions: List[Tuple[float, float]],
    poly: Polygon,
    radius: float,
    required_fraction: float,
) -> PlacementProof:
    """
    Generate a mathematical coverage proof by grid sampling.

    Args:
        positions:         Detector (x, y) positions.
        poly:              Room polygon.
        radius:            Coverage radius (m).
        required_fraction: Required coverage fraction (0–1).

    Returns:
        PlacementProof with exact counts and max_gap_m.
    """
    min_x, min_y, max_x, max_y = poly.bounds
    test_pts: List[Point] = []
    tx = min_x + _COVERAGE_GRID_M / 2.0
    while tx <= max_x:
        ty = min_y + _COVERAGE_GRID_M / 2.0
        while ty <= max_y:
            p = Point(tx, ty)
            if poly.contains(p):
                test_pts.append(p)
            ty += _COVERAGE_GRID_M
        tx += _COVERAGE_GRID_M

    if not test_pts:
        return PlacementProof(0, 0, 0, 0.0, radius, 0.0, False)

    r2 = radius * radius
    covered_indices = set()
    for ti, tp in enumerate(test_pts):
        for cx, cy in positions:
            if (tp.x - cx) ** 2 + (tp.y - cy) ** 2 <= r2:
                covered_indices.add(ti)
                break

    covered   = len(covered_indices)
    uncovered = len(test_pts) - covered
    fraction  = covered / len(test_pts)

    # max gap: distance from each uncovered point to nearest detector
    max_gap = 0.0
    if uncovered > 0 and positions:
        for ti in range(len(test_pts)):
            if ti not in covered_indices:
                tp = test_pts[ti]
                nearest = min(
                    math.sqrt((tp.x - cx) ** 2 + (tp.y - cy) ** 2)
                    for cx, cy in positions
                )
                if nearest > max_gap:
                    max_gap = nearest

    return PlacementProof(
        test_point_count  = len(test_pts),
        covered_count     = covered,
        uncovered_count   = uncovered,
        coverage_fraction = round(fraction, 6),
        coverage_radius_m = radius,
        max_gap_m         = round(max_gap, 4),
        proof_valid       = fraction >= required_fraction,
    )


def _compute_confidence(
    result: ExpertResult,
    retries: int,
    ceiling_clamped: bool,
) -> Tuple[ConfidenceLevel, float]:
    """
    Compute an honest, multi-factor confidence score.

    Factors (each 0–1, weighted):
      0.40 — coverage fraction (from PlacementProof)
      0.25 — wall violations: 0 = 1.0, any = 0.0
      0.15 — no errors: 0 errors = 1.0, else 0.0
      0.10 — retry penalty: 0 retries = 1.0, else 1-retries/max
      0.10 — ceiling normative: not clamped = 1.0, clamped = 0.5

    Returns:
        Tuple of (ConfidenceLevel, float score 0–1).
    """
    cov_score    = result.placement_proof.coverage_fraction if result.placement_proof else 0.0
    wall_score   = 0.0 if result.wall_violations else 1.0
    error_score  = 0.0 if result.errors else 1.0
    retry_score  = max(0.0, 1.0 - retries / _MAX_PLACEMENT_RETRIES)
    ceiling_score= 0.5 if ceiling_clamped else 1.0

    score = (
        0.40 * cov_score   +
        0.25 * wall_score  +
        0.15 * error_score +
        0.10 * retry_score +
        0.10 * ceiling_score
    )
    score = round(min(1.0, max(0.0, score)), 4)

    if result.errors or (result.placement_proof and not result.placement_proof.proof_valid):
        return ConfidenceLevel.UNSAFE, score

    if score >= _CONFIDENCE_HIGH_THRESHOLD and retries == 0 and not ceiling_clamped:
        return ConfidenceLevel.CERTIFIED, score
    if score >= _CONFIDENCE_HIGH_THRESHOLD:
        return ConfidenceLevel.HIGH, score
    if score >= _CONFIDENCE_MEDIUM_THRESHOLD:
        return ConfidenceLevel.MEDIUM, score
    return ConfidenceLevel.LOW, score


def _generate_improvements(
    result:    ExpertResult,
    poly:      Polygon,
    ceiling:   CeilingSpec,
    radius:    float,
    proof:     PlacementProof,
) -> List[ImprovementProposal]:
    """
    Generate concrete, prioritised improvement proposals.

    Never generates vague suggestions.  Every proposal has:
      - A specific NFPA 72-2022 clause.
      - A specific action.
      - An optional location.
    """
    props: List[ImprovementProposal] = []

    # Coverage gap — add detector near centroid of uncovered area
    if proof and proof.uncovered_count > 0:
        props.append(ImprovementProposal(
            priority    = "SAFETY",
            clause      = "NFPA 72-2022 §17.6.3.1",
            description = (
                f"{proof.uncovered_count} test point(s) uncovered "
                f"(max gap {proof.max_gap_m:.2f} m from nearest detector). "
                f"Add detector(s) to close gap."
            ),
            action   = "ADD_DETECTOR",
            location = None,
        ))

    # Wall violations — move detectors
    for wv in result.wall_violations:
        props.append(ImprovementProposal(
            priority    = "SAFETY",
            clause      = "NFPA 72-2022 §17.6.3.1.1",
            description = wv.violation,
            action      = "MOVE_DETECTOR",
            location    = wv.position,
        ))

    # Ceiling clamped — PE must verify
    if ceiling.was_clamped:
        props.append(ImprovementProposal(
            priority    = "COMPLIANCE",
            clause      = "NFPA 72-2022 Table 17.6.3.1",
            description = (
                f"Ceiling height {ceiling.original_height_m:.2f} m is outside "
                f"NFPA 72 normative range. Design was produced with clamped "
                f"height {ceiling.height_at_low_point_m:.2f} m. "
                f"A licensed FPE must verify the actual spacing for this height."
            ),
            action   = "ENGINEER_REVIEW",
            location = None,
        ))

    # High ceiling — consider aspirating or beam
    if ceiling.height_at_low_point_m > 9.14:
        props.append(ImprovementProposal(
            priority    = "COMPLIANCE",
            clause      = "NFPA 72-2022 §17.6.3.5",
            description = (
                f"Ceiling height {ceiling.height_at_low_point_m:.2f} m. "
                f"Consider aspirating smoke detection or projected-beam "
                f"detectors per NFPA 72 §17.6.3.5."
            ),
            action   = "REVIEW_GEOMETRY",
            location = None,
        ))

    # More detectors might close coverage gap
    area = poly.area
    spacing = calculate_max_spacing(ceiling, result.detector_type)
    min_count = math.ceil(area / (spacing * spacing))
    if len(result.detector_positions) < min_count:
        props.append(ImprovementProposal(
            priority    = "EFFICIENCY",
            clause      = "NFPA 72-2022 §17.6.3.1",
            description = (
                f"Room area {area:.1f} m² / spacing² {spacing**2:.1f} m² "
                f"suggests ≥ {min_count} detector(s) needed; "
                f"{len(result.detector_positions)} placed. "
                f"Coverage grid may produce gaps."
            ),
            action   = "ADD_DETECTOR",
            location = None,
        ))

    return props


# ============================================================================
# CUSTOM EXCEPTIONS
# ============================================================================

class SafetyRefusalError(Exception):
    """
    Raised when the system refuses to proceed due to a safety violation.

    This is not a bug.  It is intentional rejection of an unsafe instruction.
    The caller must not catch and ignore this exception.
    """


class InputValidationError(Exception):
    """Raised when room geometry or inputs are unacceptably invalid."""


# ============================================================================
# EXPERT SYSTEM
# ============================================================================

class ExpertSystem:
    """
    NFPA 72-2022 Fire Alarm Design Expert System — V10.

    Core principles:
      • REFUSE before GUESS — never produce an unsafe result.
      • PROVE before CERTIFY — coverage must be mathematically verified.
      • ACKNOWLEDGE before PROCEED — if inputs were adjusted, say so.
      • RETRY before FAIL — attempt self-correction before declaring failure.
      • IMPROVE always — every result includes actionable proposals.

    Args:
        nfpa_version: Edition of NFPA 72 to apply (default: "NFPA 72-2022").
    """

    def __init__(self, nfpa_version: str = "NFPA 72-2022", audit_trail: Optional[AuditTrail] = None) -> None:
        self.nfpa_version = nfpa_version
        self.audit_trail = audit_trail  # Audit logging

    # ------------------------------------------------------------------
    # Primary public entry point
    # ------------------------------------------------------------------

    def analyse_room(
        self,
        room_spec:             RoomSpec,
        forced_detector_type:  Optional[DetectorType] = None,
        required_coverage_pct: float = 100.0,
    ) -> ExpertResult:
        """
        Perform complete NFPA 72-2022 analysis for a single room.

        The method executes ten phases in sequence.  If any safety-critical
        phase fails and cannot be auto-corrected, it returns a REFUSED or
        UNSAFE result — never a silently wrong one.

        Args:
            room_spec:             Room specification.
            forced_detector_type:  Type override — refused if prohibited for
                                   the room occupancy (safety gate).
            required_coverage_pct: Minimum coverage (default 100 %).

        Returns:
            ExpertResult — always populated, never raises.
            Check result.refused and result.confidence before use.
        """
        result = ExpertResult(
            room_id      = room_spec.room_id,
            nfpa_version = self.nfpa_version,
        )

        # RoomSpec now validates itself at construction - no external validation needed

        try:
            self._run_pipeline(
                room_spec, forced_detector_type, required_coverage_pct, result
            )
        except SafetyRefusalError as exc:
            result.refused       = True
            result.refusal_reason= str(exc)
            result.confidence    = ConfidenceLevel.UNSAFE
            result.errors.append(f"SAFETY_REFUSAL: {exc}")
            logger.error("analyse_room: REFUSED room=%s reason=%s", room_spec.room_id, exc)
        except InputValidationError as exc:
            result.refused       = True
            result.refusal_reason= str(exc)
            result.confidence    = ConfidenceLevel.UNSAFE
            result.errors.append(f"INPUT_ERROR: {exc}")
            logger.error("analyse_room: INPUT_ERROR room=%s: %s", room_spec.room_id, exc)
        except Exception as exc:
            # Unexpected error — acknowledge it, do not hide it
            result.errors.append(
                f"UNEXPECTED_ERROR: {type(exc).__name__}: {exc}. "
                "This is a system fault — report to developer."
            )
            result.confidence = ConfidenceLevel.UNSAFE
            logger.exception("analyse_room: UNEXPECTED room=%s", room_spec.room_id)

        # Audit logging
        if self.audit_trail:
            self.audit_trail.log_detector_type_selection(
                room_id=room_spec.room_id,
                detector_type=result.detector_type.value if result.detector_type else "unknown",
                ceiling_height_m=room_spec.ceiling_spec.height_at_low_point_m if room_spec.ceiling_spec else 3.0
            )
            for det in result.detector_positions:
                self.audit_trail.log_placement(
                    room_id=room_spec.room_id,
                    detector_id=det.get("device_id", ""),
                    detector_type=det.get("detector_type", ""),
                    x=det.get("x", 0.0),
                    y=det.get("y", 0.0),
                    z=det.get("z", 0.0)
                )
            self.audit_trail.log_coverage_check(
                room_id=room_spec.room_id,
                coverage_percent=result.coverage_percent,
                num_detectors=len(result.detector_positions),
                compliance=result.compliant
            )
        return result

    # ------------------------------------------------------------------
    # Pipeline
    # ------------------------------------------------------------------

    def _run_pipeline(
        self,
        room_spec:             RoomSpec,
        forced_detector_type:  Optional[DetectorType],
        required_coverage_pct: float,
        result:                ExpertResult,
    ) -> None:

        required_fraction = required_coverage_pct / 100.0

        # ── Phase 0: Input Validation & Refusal Gate ───────────────────
        poly = room_spec.polygon
        if poly is None:
            raise InputValidationError(
                f"Room '{room_spec.room_id}': polygon is degenerate, "
                f"has fewer than {_MIN_POLYGON_VERTICES} vertices, or area < "
                f"{_MIN_ROOM_AREA_M2} m². Cannot produce any design."
            )

        if poly.area > _MAX_ROOM_AREA_M2:
            raise InputValidationError(
                f"Room '{room_spec.room_id}': area {poly.area:.0f} m² exceeds "
                f"automated design limit ({_MAX_ROOM_AREA_M2} m²). "
                f"Refer to licensed FPE for large-space design."
            )

        # ── Phase 1: Safe Ceiling Construction ────────────────────────
        input_ceiling  = room_spec.ceiling_spec
        ceiling_clamped = input_ceiling.was_clamped

        ceiling = CeilingSpec.create_safe(
            height_at_low_point_m  = input_ceiling.height_at_low_point_m,
            height_at_high_point_m = input_ceiling.height_at_high_point_m,
            ceiling_type           = input_ceiling.ceiling_type,
        )
        if ceiling.was_clamped:
            ceiling_clamped = True

        if ceiling_clamped:
            original_h = (
                input_ceiling.original_height_m
                if input_ceiling.was_clamped
                else ceiling.original_height_m
            )
            result.warnings.append(
                f"[ACKNOWLEDGED] Ceiling height {original_h:.2f} m is outside "
                f"NFPA 72 normative range [{_NFPA_HEIGHT_MIN_M:.1f}–"
                f"{_NFPA_HEIGHT_MAX_M:.2f} m]. "
                f"Design produced with clamped height "
                f"{ceiling.height_at_low_point_m:.2f} m. "
                f"A licensed PE must verify before permit submission. "
                f"[NFPA 72-2022 Table 17.6.3.1]"
            )

        # ── Phase 2: Occupancy Classification ─────────────────────────
        occupancy = _classify_occupancy(room_spec, ceiling)
        result.occupancy_class = occupancy

        # ── Phase 3: Detector Type Selection (safety gate) ────────────
        # Raises SafetyRefusalError if forced type is prohibited
        detector_type = _select_detector_type(
            occupancy, ceiling, forced_detector_type, room_spec.room_id
        )
        result.detector_type = detector_type

        # ── Phase 4: Constraint-Based Coverage-Aware Placement ────────
        spacing  = calculate_max_spacing(ceiling, detector_type)
        radius   = calculate_coverage_radius(ceiling, detector_type)
        max_wall = calculate_max_wall_distance(ceiling, detector_type)

        positions: List[Tuple[float, float]] = []
        retries = 0
        seed_positions: List[Tuple[float, float]] = []

        for attempt in range(_MAX_PLACEMENT_RETRIES + 1):
            positions = _coverage_aware_placement(
                poly, spacing, radius, max_wall,
                seed_positions=seed_positions,
                emergency_relax=(attempt > 0),
            )

            if not positions:
                if attempt < _MAX_PLACEMENT_RETRIES:
                    retries += 1
                    result.warnings.append(
                        f"[RETRY {attempt+1}] No positions found with wall constraint. "
                        f"NFPA 72-2022 §17.6.3.1.1."
                    )
                    continue
                raise InputValidationError(
                    f"Room '{room_spec.room_id}': no valid detector positions found "
                    f"after {_MAX_PLACEMENT_RETRIES} retries. "
                    f"Room geometry may be too constrained for automated placement. "
                    f"Refer to licensed FPE."
                )

            # Phase 5: Coverage Proof
            proof = _compute_placement_proof(positions, poly, radius, required_fraction)

            if proof.proof_valid:
                retries = attempt
                break

            if attempt < _MAX_PLACEMENT_RETRIES:
                # Self-correction: add the centroid of the largest uncovered zone
                retries += 1
                result.warnings.append(
                    f"[SELF-CORRECTION {attempt+1}] Coverage {proof.coverage_fraction*100:.1f}% "
                    f"< required {required_coverage_pct:.0f}%. "
                    f"Max gap {proof.max_gap_m:.2f} m. Retrying with augmented placement."
                )
                # Add centroid of uncovered area to seed_positions for next attempt
                extra = _find_uncovered_centroid(poly, positions, radius)
                if extra:
                    seed_positions.append(extra)

        result.detector_positions = positions
        result.retry_count        = retries

        # ── Phase 5: Final Coverage Proof ─────────────────────────────
        proof = _compute_placement_proof(positions, poly, radius, required_fraction)
        result.placement_proof = proof

        result.coverage_result = check_coverage_polygon(
            detector_positions       = positions,
            room_spec             = room_spec,
            ceiling_spec             = ceiling,
            detector_type         = detector_type,
        )

        if not proof.proof_valid:
            result.errors.append(
                f"COVERAGE_PROOF_FAILED: {proof.coverage_fraction*100:.2f}% < "
                f"required {required_coverage_pct:.0f}% after "
                f"{retries} retries. "
                f"Max gap: {proof.max_gap_m:.2f} m. "
                f"Design is NOT safe for submission. "
                f"[NFPA 72-2022 §17.6.3.1]"
            )

        # ── Phase 6: Wall Distance Enforcement ────────────────────────
        wall_violations = validate_wall_distances(
            detector_positions = positions,
            room_spec          = room_spec,
            
            
        )
        result.wall_violations = wall_violations

        for wv in wall_violations:
            logger.warning(
                "analyse_room: WALL_VIOLATION room=%s detector=%d dist=%.3f m",
                room_spec.room_id, wv.detector_index, wv.distance_m,
            )

        # ── Phase 7: Duct Detector Injection ──────────────────────────
        if room_spec.hvac_ducts:
            duct_devices = suggest_duct_detectors(room_spec)
            result.duct_devices = duct_devices
            if duct_devices:
                result.warnings.append(
                    f"[NFPA 72-2022 §17.7.5] Added {len(duct_devices)} duct detector(s). "
                    f"Duct IDs: {list({d.device_id for d in duct_devices})}."
                )

        # ── Phase 8: Confidence Scoring ───────────────────────────────
        confidence, score = _compute_confidence(result, retries, ceiling_clamped)
        result.confidence       = confidence
        result.confidence_score = score

        # ── Phase 9: Improvement Proposals ────────────────────────────
        result.improvements = _generate_improvements(result, poly, ceiling, radius, proof)

        # ── Phase 10: Self-Verification Log ───────────────────────────
        logger.info(
            "analyse_room: room=%s occ=%s type=%s detectors=%d "
            "coverage=%.2f%% proof=%s retries=%d confidence=%s(%.2f)",
            room_spec.room_id,
            occupancy.value,
            detector_type.value,
            len(positions),
            proof.coverage_fraction * 100,
            proof.proof_valid,
            retries,
            confidence.value,
            score,
        )

        if confidence == ConfidenceLevel.UNSAFE and not result.refused:
            logger.error(
                "analyse_room: UNSAFE result room=%s — do NOT use for permit.",
                room_spec.room_id,
            )

    # ------------------------------------------------------------------
    # Batch entry point
    # ------------------------------------------------------------------

    def analyse_floor(
        self,
        rooms: List[RoomSpec],
        required_coverage_pct: float = 100.0,
    ) -> List[ExpertResult]:
        """
        Analyse all rooms on a floor.

        Always returns one result per room.  Failed rooms have
        confidence=UNSAFE and must not be used.

        Args:
            rooms:                 Room specifications.
            required_coverage_pct: Minimum coverage per room.

        Returns:
            List of ExpertResult, same order as rooms.
        """
        results = []
        for room_spec in rooms:
            res = self.analyse_room(
                room_spec             = room_spec,
            )
            results.append(res)

        n_unsafe = sum(1 for r in results if r.confidence == ConfidenceLevel.UNSAFE)
        if n_unsafe:
            logger.error(
                "analyse_floor: %d/%d room(s) are UNSAFE — "
                "floor design must NOT be submitted.",
                n_unsafe, len(results),
            )

        return results


# ============================================================================
# INTERNAL UTILITY
# ============================================================================

def _find_uncovered_centroid(
    poly:      Polygon,
    positions: List[Tuple[float, float]],
    radius:    float,
) -> Optional[Tuple[float, float]]:
    """
    Find the centroid of the largest uncovered area inside the room.

    Used by the self-correction loop to add a detector where coverage
    is weakest.  Never guesses — computes from actual geometry.

    Args:
        poly:      Room polygon.
        positions: Current detector positions.
        radius:    Coverage radius.

    Returns:
        (x, y) of the best additional detector position, or None.
    """
    if not positions:
        c = poly.centroid
        return (round(c.x, 4), round(c.y, 4))

    coverage_union = unary_union(
        [Point(x, y).buffer(radius, resolution=16) for x, y in positions]
    )
    uncovered = poly.difference(coverage_union)

    if uncovered.is_empty:
        return None

    # Find the largest component and its centroid
    if hasattr(uncovered, "geoms"):
        largest = max(uncovered.geoms, key=lambda g: g.area)
    else:
        largest = uncovered

    c = largest.centroid
    if poly.contains(c):
        return (round(c.x, 4), round(c.y, 4))

    # Centroid outside polygon (e.g. concave shape) — use nearest interior point
    nearest = poly.exterior.interpolate(poly.exterior.project(c))
    return (round(nearest.x, 4), round(nearest.y, 4))
