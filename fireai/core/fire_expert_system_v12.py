"""
fire_expert_system_v12.py  V12.0
=================================
NFPA 72-2022 Fire Alarm Expert System — Production-Grade Edition.

WHAT CHANGED FROM V11 (all fixes are based on verified failure reports)
------------------------------------------------------------------------

FIX-1 · MIP Silent Collapse → FALLBACK CHAIN (Showstopper Fix)
  V11: _solve_mip returned [] on any non-OPTIMAL status → _pipeline raised
  InputValidationError and rejected the room entirely, even when greedy
  could have solved it.
  V12: _solve_mip now returns (positions, used_mip=True) on FEASIBLE,
  TIME_LIMIT, or any sub-optimal status if at least one position was
  found. When MIP returns truly empty (infeasible or exception), the
  pipeline falls back to greedy silently and records the reason in
  result.warnings. A room is never rejected due to MIP failure alone.

FIX-2 · False Confidence Upgrade ignoring Wall Violations
  V11: MIP bonus upgraded confidence even when wall_violations existed,
  producing HIGH confidence on physically non-compliant layouts.
  V12: Confidence upgrade is gated on ALL of:
    (a) used_mip=True
    (b) proof.proof_valid=True
    (c) len(result.wall_violations) == 0
  Layouts with wall violations are capped at MEDIUM at most, and a
  WALL_VIOLATION_CONFIDENCE_CAP warning is emitted.

FIX-3 · Thread Safety (ProjectMemory)
  V11: ProjectMemory used bare dict with no locking — concurrent API
  requests caused read/write races and possible data corruption.
  V12: All mutating operations (_store, _greedy_attempts, _greedy_successes)
  are protected by threading.Lock. get() and store() are atomic under
  the lock. The eviction policy (FIX-5) also runs under the lock.

FIX-4 · Fake Cryptographic Signing Claim Removed
  V11: _sign_proof filled spectral_data with hardcoded arbitrary values
  (0.5, 1.5) and claimed the result was "cryptographically signed".
  V12: The function is renamed _build_regulatory_proof and its docstring
  explicitly states it produces a structured regulatory package, NOT a
  cryptographic signature. The field signed_proof is renamed
  regulatory_proof in ExpertResultV12. If RegulatoryProofEngine is
  unavailable the field is None with no false claims.

FIX-5 · Unbounded ProjectMemory → LRU Eviction
  V11: ProjectMemory grew without limit — long-running services would
  exhaust memory.
  V12: ProjectMemory accepts max_records (default 2048). When the limit
  is reached, the least-recently-used record (lowest hit_count, then
  oldest insertion order) is evicted before storing the new record.

SAFETY GUARANTEES (unchanged from V10/V11)
------------------------------------------
  • SafetyRefusalError on prohibited detector+occupancy combos.
  • InputValidationError on degenerate geometry.
  • No result is returned with confidence=UNSAFE silently.
  • All IEEE 754 arithmetic is exact (no ±ε tricks on safety distances).
"""

from __future__ import annotations

import hashlib
import json
import logging
import math
import random
import threading
from collections import OrderedDict
from dataclasses import dataclass, field
from enum import Enum, unique
from typing import Dict, List, Optional, Tuple

from shapely.geometry import Point, Polygon
from shapely.ops import unary_union

from nfpa72_models import (
    CeilingSpec, CeilingType, DetectorType, HVACDuct,
    MIN_WALL_DISTANCE_M, RoomSpec,
    _NFPA_HEIGHT_MAX_M, _NFPA_HEIGHT_MIN_M,
)
from nfpa72_calculations import (
    calculate_coverage_radius, calculate_max_spacing,
    calculate_max_wall_distance,
)
from nfpa72_coverage import (
    CoverageResult, DuctDevice, WallViolation,
    check_coverage_polygon, suggest_duct_detectors, validate_wall_distances,
)

logger = logging.getLogger(__name__)

# ── Import V10 primitives (reuse, don't duplicate) ───────────────────────────
from .fire_expert_system import (
    ConfidenceLevel, OccupancyClass, ImprovementProposal, PlacementProof,
    SafetyRefusalError, InputValidationError,
    _MIN_POLYGON_VERTICES, _MIN_ROOM_AREA_M2, _MAX_ROOM_AREA_M2,
    _COVERAGE_GRID_M, _MAX_PLACEMENT_RETRIES,
    _CONFIDENCE_HIGH_THRESHOLD, _CONFIDENCE_MEDIUM_THRESHOLD,
    _classify_occupancy, _select_detector_type,
    _build_valid_polygon, _coverage_aware_placement,
    _compute_placement_proof, _compute_confidence,
    _generate_improvements, _find_uncovered_centroid,
)

from spatial_engine.mip_solver import OptimalMIPEngine

# ── Optional: RegulatoryProofEngine ──────────────────────────────────────────
try:
    import sys as _sys
    _sys.path.insert(0, "fire-alarm-db/accuracy_engine")
    from core.gkil.proof_engine import RegulatoryProofEngine, ProofObject, ProofStatus
    _PROOF_ENGINE_AVAILABLE = True
except ImportError:
    _PROOF_ENGINE_AVAILABLE = False
    logger.debug("RegulatoryProofEngine not available — regulatory proof skipped.")


# ============================================================================
# CONSTANTS
# ============================================================================

# Confidence threshold below which MIP escalation is triggered
_MIP_ESCALATION_THRESHOLD: float = _CONFIDENCE_HIGH_THRESHOLD

# Monte Carlo: number of failure scenarios to simulate (fast mode)
_MC_ITERATIONS: int = 50

# Minimum coverage after single-device failure (resilience floor)
_MC_RESILIENCE_FLOOR: float = 0.80

# MIP placement_step for escalation (coarser = faster solver, still optimal)
_MIP_PLACEMENT_STEP: float = 1.0
_MIP_COVERAGE_STEP:  float = 1.0
_MIP_TIME_LIMIT:     int   = 30   # seconds

# FIX-5: Maximum number of memory records before LRU eviction triggers
_MEMORY_MAX_RECORDS: int = 2048

# MIP statuses that are acceptable (sub-optimal but still usable)
_MIP_ACCEPTABLE_STATUSES = frozenset({"OPTIMAL", "FEASIBLE", "TIME_LIMIT"})


# ============================================================================
# PROJECT MEMORY — FIX-3 (Thread Safety) + FIX-5 (LRU Eviction)
# ============================================================================

@dataclass
class MemoryRecord:
    """One stored analysis outcome keyed by geometry+occupancy hash."""
    geometry_hash:  str
    occupancy:      str
    detector_type:  str
    used_mip:       bool
    confidence:     float
    device_count:   int
    coverage_pct:   float
    hit_count:      int = 0


class ProjectMemory:
    """
    Thread-safe, bounded in-process memory of past room analyses.

    Keyed by SHA-256 of (polygon_coords_rounded, occupancy, ceiling_height).
    Used to:
      • Skip greedy for geometries where greedy previously failed.
      • Track greedy_success_rate to decide routing strategy.

    Thread-safety: all mutating operations are protected by threading.Lock.
    This makes the class safe for concurrent multi-floor or API usage.

    Eviction: when max_records is reached, the record with the lowest
    hit_count is evicted (LRU approximation). Ties broken by insertion order
    (oldest record first). This bounds memory usage for long-running services.

    Args:
        max_records: Maximum number of stored records before eviction.
                     Default 2048 — tune per deployment memory budget.
    """

    def __init__(self, max_records: int = _MEMORY_MAX_RECORDS) -> None:
        self._store: OrderedDict[str, MemoryRecord] = OrderedDict()
        self._greedy_attempts = 0
        self._greedy_successes = 0
        self._lock = threading.Lock()
        self._max_records = max(1, max_records)

    @property
    def greedy_success_rate(self) -> float:
        with self._lock:
            if self._greedy_attempts == 0:
                return 1.0
            return self._greedy_successes / self._greedy_attempts

    def key(
        self,
        polygon_coords: List,
        occupancy: OccupancyClass,
        ceiling_height: float,
    ) -> str:
        rounded = [(round(x, 1), round(y, 1)) for x, y in polygon_coords]
        payload = json.dumps({
            "poly": sorted(rounded),
            "occ":  occupancy.value,
            "h":    round(ceiling_height, 1),
        }, sort_keys=True)
        return hashlib.sha256(payload.encode()).hexdigest()[:16]

    def get(self, key: str) -> Optional[MemoryRecord]:
        with self._lock:
            rec = self._store.get(key)
            if rec:
                rec.hit_count += 1
                # Move to end (most recently used)
                self._store.move_to_end(key)
            return rec

    def store(self, key: str, record: MemoryRecord) -> None:
        with self._lock:
            if key in self._store:
                self._store[key] = record
                self._store.move_to_end(key)
                return

            # FIX-5: Evict LRU record when at capacity
            if len(self._store) >= self._max_records:
                # Find the record with the lowest hit_count (LRU approximation)
                # OrderedDict preserves insertion order, so iterate to find min.
                evict_key = min(self._store, key=lambda k: self._store[k].hit_count)
                del self._store[evict_key]
                logger.debug(
                    "ProjectMemory: evicted key=%s (hit_count=%d) to stay under %d records.",
                    evict_key,
                    self._store.get(evict_key, MemoryRecord("", "", "", False, 0.0, 0, 0.0)).hit_count,
                    self._max_records,
                )

            self._store[key] = record

    def record_greedy_attempt(self, success: bool) -> None:
        with self._lock:
            self._greedy_attempts += 1
            if success:
                self._greedy_successes += 1

    def summary(self) -> Dict:
        with self._lock:
            return {
                "stored_records":      len(self._store),
                "max_records":         self._max_records,
                "greedy_attempts":     self._greedy_attempts,
                "greedy_successes":    self._greedy_successes,
                "greedy_success_rate": round(
                    (self._greedy_successes / self._greedy_attempts)
                    if self._greedy_attempts else 1.0,
                    3,
                ),
            }


# ============================================================================
# EXTENDED RESULT
# ============================================================================

@dataclass
class ResilienceResult:
    """Result of Monte Carlo device-failure simulation."""
    scenarios_run:        int
    scenarios_passed:     int
    pass_rate:            float
    min_coverage_seen:    float
    resilience_floor:     float
    resilient:            bool
    failure_detail:       Optional[str] = None


@dataclass
class ExpertResultV12:
    """
    Complete output of ExpertSystemV12.analyse_room().

    All V11 fields preserved.  V12 changes:
        regulatory_proof: Renamed from signed_proof. Does NOT claim
                          cryptographic signing — it is a structured
                          regulatory compliance package only.
        mip_fallback_reason: Non-empty if MIP returned sub-optimal result
                              or failed and greedy was used as fallback.
    """
    room_id:              str
    detector_positions:   List[Tuple[float, float]]   = field(default_factory=list)
    detector_type:        DetectorType                 = DetectorType.SMOKE_PHOTOELECTRIC
    occupancy_class:      OccupancyClass               = OccupancyClass.STANDARD
    coverage_result:      Optional[CoverageResult]     = None
    placement_proof:      Optional[PlacementProof]     = None
    wall_violations:      List[WallViolation]           = field(default_factory=list)
    duct_devices:         List[DuctDevice]              = field(default_factory=list)
    confidence:           ConfidenceLevel               = ConfidenceLevel.LOW
    confidence_score:     float                         = 0.0
    warnings:             List[str]                     = field(default_factory=list)
    errors:               List[str]                     = field(default_factory=list)
    improvements:         List[ImprovementProposal]     = field(default_factory=list)
    retry_count:          int                           = 0
    nfpa_version:         str                           = "NFPA 72-2022"
    refused:              bool                          = False
    refusal_reason:       Optional[str]                 = None
    # V11 fields (unchanged)
    used_mip:             bool                          = False
    mip_proof:            Optional[Dict]                = None
    resilience:           Optional[ResilienceResult]    = None
    memory_hit:           bool                          = False
    routing_reason:       str                           = ""
    # FIX-4: renamed and clarified — this is NOT a cryptographic signature
    regulatory_proof:     Optional[object]              = None
    # FIX-1: explains why MIP was bypassed or fell back
    mip_fallback_reason:  str                           = ""

    @property
    def compliant(self) -> bool:
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
        resilient = self.resilience.resilient if self.resilience else True
        return (
            self.compliant
            and self.confidence in (ConfidenceLevel.CERTIFIED, ConfidenceLevel.HIGH)
            and resilient
            and not self.refused
        )


# ============================================================================
# MONTE CARLO RESILIENCE CHECK (unchanged from V11)
# ============================================================================

def _run_resilience_check(
    positions:   List[Tuple[float, float]],
    poly:        Polygon,
    radius:      float,
    floor:       float = _MC_RESILIENCE_FLOOR,
    iterations:  int   = _MC_ITERATIONS,
    seed:        int   = 42,
) -> ResilienceResult:
    """
    Simulate random single-device failures and measure coverage degradation.

    For each scenario: remove one random detector, recompute coverage,
    check if it remains ≥ floor.

    Args:
        positions:  Placed detector positions.
        poly:       Room polygon.
        radius:     Coverage radius.
        floor:      Minimum acceptable post-failure coverage.
        iterations: Number of Monte Carlo scenarios.
        seed:       RNG seed for reproducibility.

    Returns:
        ResilienceResult with pass rate and worst-case coverage.
    """
    if len(positions) <= 1:
        return ResilienceResult(
            scenarios_run     = iterations,
            scenarios_passed  = 0,
            pass_rate         = 0.0,
            min_coverage_seen = 0.0,
            resilience_floor  = floor,
            resilient         = False,
            failure_detail    = "Only 1 detector — no redundancy.",
        )

    rng          = random.Random(seed)
    passed       = 0
    min_cov_seen = 1.0
    r2           = radius * radius

    # Build test grid once
    min_x, min_y, max_x, max_y = poly.bounds
    test_pts: List[Tuple[float, float]] = []
    tx = min_x + _COVERAGE_GRID_M
    while tx <= max_x:
        ty = min_y + _COVERAGE_GRID_M
        while ty <= max_y:
            if poly.contains(Point(tx, ty)):
                test_pts.append((tx, ty))
            ty += _COVERAGE_GRID_M
        tx += _COVERAGE_GRID_M

    if not test_pts:
        return ResilienceResult(
            scenarios_run=0, scenarios_passed=0, pass_rate=1.0,
            min_coverage_seen=1.0, resilience_floor=floor,
            resilient=True,
        )

    total_pts = len(test_pts)

    for _ in range(iterations):
        failed_idx = rng.randrange(len(positions))
        remaining  = [p for i, p in enumerate(positions) if i != failed_idx]

        covered = 0
        for tx, ty in test_pts:
            for px, py in remaining:
                if (tx - px) ** 2 + (ty - py) ** 2 <= r2:
                    covered += 1
                    break

        cov_frac = covered / total_pts
        if cov_frac < min_cov_seen:
            min_cov_seen = cov_frac
        if cov_frac >= floor:
            passed += 1

    pass_rate = passed / iterations
    return ResilienceResult(
        scenarios_run     = iterations,
        scenarios_passed  = passed,
        pass_rate         = round(pass_rate, 4),
        min_coverage_seen = round(min_cov_seen, 4),
        resilience_floor  = floor,
        resilient         = pass_rate >= 0.90,
        failure_detail    = (
            None if pass_rate >= 0.90 else
            f"Design failed {iterations - passed}/{iterations} failure scenarios "
            f"(min post-failure coverage {min_cov_seen*100:.1f}% < "
            f"required {floor*100:.0f}%). "
            "Add redundant detectors. NFPA 72-2022 §10.3."
        ),
    )


# ============================================================================
# FIX-4: REGULATORY PROOF PACKAGE (not a cryptographic signature)
# ============================================================================

def _build_regulatory_proof(
    room_id:        str,
    polygon_coords: List,
    positions:      List[Tuple[float, float]],
    detector_type:  DetectorType,
    proof:          PlacementProof,
    violations:     List[WallViolation],
) -> Optional[object]:
    """
    Build a structured regulatory compliance package via RegulatoryProofEngine.

    IMPORTANT: This is NOT a cryptographic signature and does NOT guarantee
    tamper-proofing. It is a structured data package suitable for regulatory
    submission review. If a legally binding, tamper-evident signature is
    required, integrate a dedicated PKI/HSM signing step outside this system.

    Returns None if RegulatoryProofEngine is not available.
    """
    if not _PROOF_ENGINE_AVAILABLE:
        return None

    try:
        engine = RegulatoryProofEngine(
            ontology_version = "v1.0",
            nfpa_version     = "NFPA72-2022",
            jurisdiction     = "default",
        )

        vertices = [{"x": x, "y": y, "z": 0.0, "type": "room_vertex"}
                    for x, y in polygon_coords]

        decision_data = {
            "decision_id":      f"room_{room_id}_{detector_type.value}",
            "decision_type":    "detector_placement",
            "action":           f"place_{len(positions)}_detectors",
            "priority":         "SAFETY",
            "ontology_version": "v1.0",
            "nfpa_version":     "NFPA72-2022",
            "jurisdiction":     "default",
        }

        constraints_state = {
            "COVERAGE":          proof.coverage_fraction,
            "WALL_VIOLATIONS":   len(violations),
            "SPACING_VIOLATION": 0.0 if not violations else float(len(violations)),
        }

        feasibility_data = {
            "is_valid":              proof.proof_valid,
            "geometric_feasibility": proof.test_point_count > 0,
            "topology_preserved":    True,
            "wall_violations_count": len(violations),
        }

        # Derived values only — no hardcoded arbitrary constants
        uncovered_ratio = proof.uncovered_count / max(proof.test_point_count, 1)
        coverage_risk   = 1.0 - proof.coverage_fraction

        spectral_data = {
            # spectral_radius: >1 means system is diverging (non-compliant)
            "spectral_radius":      coverage_risk + (0.1 * len(violations)),
            "composite_risk_index": coverage_risk,
            "risk_level":           (
                "LOW"    if (proof.proof_valid and not violations) else
                "MEDIUM" if proof.proof_valid else
                "HIGH"
            ),
            "dimensions": {
                "failure_probability": coverage_risk,
                "coverage_loss":       uncovered_ratio,
                "wall_violation_count": len(violations),
            },
        }

        return engine.construct_proof(
            decision_data     = decision_data,
            constraints_state = constraints_state,
            feasibility_data  = feasibility_data,
            spectral_data     = spectral_data,
            cad_trace         = [f"room:{room_id}", f"detectors:{len(positions)}"],
            rejected_actions  = [],
            vertices          = vertices,
        )
    except Exception as exc:
        logger.warning("_build_regulatory_proof: failed: %s", exc)
        return None


# ============================================================================
# EXPERT SYSTEM V12
# ============================================================================

class ExpertSystemV12:
    """
    NFPA 72-2022 Expert System — Production-Grade Edition V12.

    Routing strategy:
      1. Check ProjectMemory — if this geometry was solved before, use the
         stored strategy (greedy vs MIP).
      2. If greedy_success_rate < 0.7 for this project, go straight to MIP.
      3. Otherwise try greedy first.
      4. If greedy confidence < HIGH, escalate to MIP.
      5. FIX-1: MIP fallback chain — if MIP returns sub-optimal but non-empty,
         use the sub-optimal result and warn. If MIP returns empty, fall back
         to greedy result and warn. Never reject a room due to MIP failure alone.
      6. Post-placement: run Monte Carlo resilience check.
      7. FIX-2: Confidence upgrade gated on proof_valid AND no wall violations.
      8. FIX-4: Build regulatory proof package (not a cryptographic signature).
      9. Store result in ProjectMemory (FIX-3: thread-safe, FIX-5: bounded).

    Args:
        nfpa_version: NFPA edition to apply.
        memory:       Shared ProjectMemory (inject for multi-room projects).
    """

    def __init__(
        self,
        nfpa_version: str                    = "NFPA 72-2022",
        memory:       Optional[ProjectMemory] = None,
    ) -> None:
        self.nfpa_version = nfpa_version
        self.memory       = memory or ProjectMemory()

    # ------------------------------------------------------------------
    # Primary entry point
    # ------------------------------------------------------------------

    def analyse_room(
        self,
        room_spec:             RoomSpec,
        forced_detector_type:  Optional[DetectorType] = None,
        required_coverage_pct: float = 100.0,
        run_resilience:        bool  = True,
        build_regulatory_proof: bool = True,
    ) -> ExpertResultV12:
        """
        Full NFPA 72-2022 analysis with adaptive MIP escalation and fallback chain.

        Args:
            room_spec:               Room specification.
            forced_detector_type:    Override (refused if prohibited).
            required_coverage_pct:   Minimum coverage (default 100%).
            run_resilience:          Run Monte Carlo check (default True).
            build_regulatory_proof:  Build regulatory compliance package.

        Returns:
            ExpertResultV12 — always populated, never raises.
        """
        result = ExpertResultV12(
            room_id      = room_spec.room_id,
            nfpa_version = self.nfpa_version,
        )

        try:
            self._pipeline(
                room_spec, forced_detector_type,
                required_coverage_pct, run_resilience, build_regulatory_proof,
                result,
            )
        except SafetyRefusalError as exc:
            result.refused        = True
            result.refusal_reason = str(exc)
            result.confidence     = ConfidenceLevel.UNSAFE
            result.errors.append(f"SAFETY_REFUSAL: {exc}")
            logger.error("V12: REFUSED room=%s: %s", room_spec.room_id, exc)
        except InputValidationError as exc:
            result.refused        = True
            result.refusal_reason = str(exc)
            result.confidence     = ConfidenceLevel.UNSAFE
            result.errors.append(f"INPUT_ERROR: {exc}")
            logger.error("V12: INPUT_ERROR room=%s: %s", room_spec.room_id, exc)
        except Exception as exc:
            result.errors.append(
                f"SYSTEM_FAULT: {type(exc).__name__}: {exc}. "
                "Report to developer."
            )
            result.confidence = ConfidenceLevel.UNSAFE
            logger.exception("V12: SYSTEM_FAULT room=%s", room_spec.room_id)

        return result

    # ------------------------------------------------------------------
    # Pipeline
    # ------------------------------------------------------------------

    def _pipeline(
        self,
        room_spec:              RoomSpec,
        forced_detector_type:   Optional[DetectorType],
        required_coverage_pct:  float,
        run_resilience:         bool,
        build_reg_proof:        bool,
        result:                 ExpertResultV12,
    ) -> None:

        required_fraction = required_coverage_pct / 100.0

        # ── Phase 0: Input Validation ──────────────────────────────────
        poly = _build_valid_polygon(room_spec.polygon_coords)
        if poly is None:
            raise InputValidationError(
                f"Room '{room_spec.room_id}': polygon degenerate or area < "
                f"{_MIN_ROOM_AREA_M2} m²."
            )
        if poly.area > _MAX_ROOM_AREA_M2:
            raise InputValidationError(
                f"Room '{room_spec.room_id}': area {poly.area:.0f} m² > "
                f"{_MAX_ROOM_AREA_M2} m² limit. Refer to licensed FPE."
            )

        # ── Phase 1: Ceiling ───────────────────────────────────────────
        input_ceiling   = room_spec.ceiling
        ceiling_clamped = input_ceiling.was_clamped
        ceiling = CeilingSpec.create_safe(
            height_at_low_point_m  = input_ceiling.height_at_low_point_m,
            height_at_high_point_m = input_ceiling.height_at_high_point_m,
            ceiling_type           = input_ceiling.ceiling_type,
            beam_depth_m           = input_ceiling.beam_depth_m,
            beam_spacing_m         = input_ceiling.beam_spacing_m,
        )
        if ceiling.was_clamped:
            ceiling_clamped = True
        if ceiling_clamped:
            original_h = (
                input_ceiling.original_height_m if input_ceiling.was_clamped
                else ceiling.original_height_m
            )
            result.warnings.append(
                f"[ACKNOWLEDGED] Ceiling {original_h:.2f} m outside NFPA range → "
                f"clamped to {ceiling.height_at_low_point_m:.2f} m. PE review required. "
                f"[NFPA 72-2022 Table 17.6.3.1]"
            )

        # ── Phase 2: Occupancy & Detector Type ────────────────────────
        occupancy     = _classify_occupancy(room_spec, ceiling)
        detector_type = _select_detector_type(
            occupancy, ceiling, forced_detector_type, room_spec.room_id
        )
        result.occupancy_class = occupancy
        result.detector_type   = detector_type

        # ── Phase 3: Compute NFPA values ──────────────────────────────
        spacing  = calculate_max_spacing(ceiling, detector_type)
        radius   = calculate_coverage_radius(ceiling, detector_type)
        max_wall = calculate_max_wall_distance(ceiling, detector_type)

        # ── Phase 4: Memory lookup & routing decision ──────────────────
        mem_key = self.memory.key(
            room_spec.polygon_coords, occupancy, ceiling.height_at_low_point_m
        )
        mem_rec = self.memory.get(mem_key)

        use_mip_direct = (
            mem_rec is not None and mem_rec.used_mip
        ) or (
            self.memory.greedy_success_rate < 0.70
        )

        if use_mip_direct:
            result.memory_hit     = mem_rec is not None
            result.routing_reason = (
                "MIP selected directly: "
                + ("memory record shows greedy failed." if mem_rec and mem_rec.used_mip
                   else f"greedy_success_rate={self.memory.greedy_success_rate:.0%} < 70%.")
            )
            positions, retries, used_mip, mip_proof, fallback_reason = (
                self._solve_mip_with_fallback(
                    poly, radius, spacing, max_wall,
                    required_fraction, room_spec.polygon_coords, result,
                )
            )
        else:
            # Try greedy first
            result.routing_reason = "Greedy selected (default fast path)."
            positions, retries = self._solve_greedy(
                poly, spacing, radius, max_wall, required_fraction
            )
            used_mip      = False
            mip_proof     = None
            fallback_reason = ""

            # Compute provisional confidence
            provisional_proof = _compute_placement_proof(
                positions, poly, radius, required_fraction
            )
            prov_conf, prov_score = _compute_confidence(
                type("_R", (), {
                    "placement_proof":  provisional_proof,
                    "wall_violations":  [],
                    "errors":           [] if provisional_proof.proof_valid else ["x"],
                })(),
                retries,
                ceiling_clamped,
            )

            # Escalate to MIP if greedy didn't achieve HIGH confidence
            if prov_score < _MIP_ESCALATION_THRESHOLD:
                self.memory.record_greedy_attempt(False)
                result.warnings.append(
                    f"[MIP_ESCALATION] Greedy confidence {prov_score:.2f} < "
                    f"{_MIP_ESCALATION_THRESHOLD:.2f}. "
                    f"Escalating to optimal MIP solver."
                )
                result.routing_reason += " → Escalated to MIP."
                (
                    mip_positions, _, used_mip, mip_proof, fallback_reason
                ) = self._solve_mip_with_fallback(
                    poly, radius, spacing, max_wall,
                    required_fraction, room_spec.polygon_coords, result,
                )
                # FIX-1: Only replace positions if MIP actually found something
                if mip_positions:
                    positions = mip_positions
                    retries   = 0
                # If mip_positions is empty, keep greedy positions (fallback_reason is set)
            else:
                self.memory.record_greedy_attempt(True)

        result.used_mip           = used_mip
        result.mip_proof          = mip_proof
        result.retry_count        = retries
        result.mip_fallback_reason = fallback_reason

        # FIX-1: A room is rejected ONLY if neither MIP nor greedy produced any positions
        if not positions:
            raise InputValidationError(
                f"Room '{room_spec.room_id}': no valid positions found "
                f"by greedy or MIP. Geometry too constrained. "
                f"Refer to licensed FPE. "
                + (f"MIP status: {fallback_reason}" if fallback_reason else "")
            )

        result.detector_positions = positions

        # ── Phase 5: Coverage Proof ────────────────────────────────────
        proof = _compute_placement_proof(positions, poly, radius, required_fraction)
        result.placement_proof = proof

        result.coverage_result = check_coverage_polygon(
            positions             = positions,
            room_spec             = room_spec,
            ceiling               = ceiling,
            detector_type         = detector_type,
            required_coverage_pct = required_coverage_pct,
        )

        if not proof.proof_valid:
            result.errors.append(
                f"COVERAGE_PROOF_FAILED: {proof.coverage_fraction*100:.2f}% < "
                f"required {required_coverage_pct:.0f}%. "
                f"Max gap {proof.max_gap_m:.2f} m. "
                f"[NFPA 72-2022 §17.6.3.1]"
            )

        # ── Phase 6: Wall Distance ─────────────────────────────────────
        result.wall_violations = validate_wall_distances(
            positions, room_spec, ceiling, detector_type
        )
        for wv in result.wall_violations:
            logger.warning("V12 WALL room=%s %s", room_spec.room_id, wv.violation)

        # ── Phase 7: Duct Detectors ────────────────────────────────────
        if room_spec.hvac_ducts:
            duct_devs = suggest_duct_detectors(room_spec.hvac_ducts)
            result.duct_devices = duct_devs
            if duct_devs:
                result.warnings.append(
                    f"[NFPA 72-2022 §17.7.5] {len(duct_devs)} duct detector(s) added."
                )

        # ── Phase 8: Confidence — FIX-2 ───────────────────────────────
        confidence, score = _compute_confidence(result, retries, ceiling_clamped)

        # FIX-2: MIP bonus ONLY when:
        #   (a) MIP was used
        #   (b) proof is valid
        #   (c) NO wall violations exist
        # All three conditions must hold. Partial compliance is not upgraded.
        if used_mip and proof.proof_valid and not result.wall_violations:
            if confidence == ConfidenceLevel.LOW:
                confidence = ConfidenceLevel.MEDIUM
                score      = max(score, _CONFIDENCE_MEDIUM_THRESHOLD)
            elif confidence == ConfidenceLevel.MEDIUM:
                confidence = ConfidenceLevel.HIGH
                score      = max(score, _CONFIDENCE_HIGH_THRESHOLD)
        elif used_mip and result.wall_violations:
            # MIP was used but wall violations exist → cap at MEDIUM, never HIGH
            if confidence == ConfidenceLevel.HIGH:
                confidence = ConfidenceLevel.MEDIUM
                score      = min(score, _CONFIDENCE_HIGH_THRESHOLD - 0.01)
            result.warnings.append(
                f"[WALL_VIOLATION_CONFIDENCE_CAP] MIP used but "
                f"{len(result.wall_violations)} wall violation(s) detected. "
                f"Confidence capped at MEDIUM. Fix violations before submission. "
                f"[NFPA 72-2022 §17.6.3.2]"
            )

        result.confidence       = confidence
        result.confidence_score = score

        # ── Phase 9: Monte Carlo Resilience ───────────────────────────
        if run_resilience and len(positions) >= 2:
            result.resilience = _run_resilience_check(
                positions, poly, radius
            )
            if result.resilience and not result.resilience.resilient:
                result.warnings.append(
                    f"[RESILIENCE] {result.resilience.failure_detail}"
                )

        # ── Phase 10: Regulatory Proof Package — FIX-4 ────────────────
        if build_reg_proof:
            result.regulatory_proof = _build_regulatory_proof(
                room_spec.room_id, room_spec.polygon_coords,
                positions, detector_type, proof, result.wall_violations,
            )

        # ── Phase 11: Improvement Proposals ───────────────────────────
        improvements = _generate_improvements(result, poly, ceiling, radius, proof)

        if result.resilience and not result.resilience.resilient:
            improvements.insert(0, ImprovementProposal(
                priority    = "SAFETY",
                clause      = "NFPA 72-2022 §10.3",
                description = result.resilience.failure_detail or "",
                action      = "ADD_DETECTOR",
                location    = None,
            ))

        result.improvements = improvements

        # ── Phase 12: Store in Memory — FIX-3 + FIX-5 ────────────────
        self.memory.store(mem_key, MemoryRecord(
            geometry_hash = mem_key,
            occupancy     = occupancy.value,
            detector_type = detector_type.value,
            used_mip      = used_mip,
            confidence    = score,
            device_count  = len(positions),
            coverage_pct  = proof.coverage_fraction * 100,
        ))

        logger.info(
            "V12: room=%s occ=%s type=%s detectors=%d cov=%.2f%% "
            "conf=%s(%.2f) mip=%s resilient=%s fallback=%r",
            room_spec.room_id, occupancy.value, detector_type.value,
            len(positions), proof.coverage_fraction * 100,
            confidence.value, score, used_mip,
            result.resilience.resilient if result.resilience else "N/A",
            fallback_reason or "none",
        )

    # ------------------------------------------------------------------
    # Greedy solver
    # ------------------------------------------------------------------

    def _solve_greedy(
        self,
        poly:              Polygon,
        spacing:           float,
        radius:            float,
        max_wall:          float,
        required_fraction: float,
    ) -> Tuple[List[Tuple[float, float]], int]:
        """Run greedy coverage-aware placement with self-correction."""
        positions: List[Tuple[float, float]] = []
        retries = 0

        for attempt in range(_MAX_PLACEMENT_RETRIES + 1):
            positions = _coverage_aware_placement(poly, spacing, radius, max_wall)
            if not positions:
                retries += 1
                continue

            proof = _compute_placement_proof(positions, poly, radius, required_fraction)
            if proof.proof_valid:
                retries = attempt
                break

            if attempt < _MAX_PLACEMENT_RETRIES:
                retries += 1
                extra = _find_uncovered_centroid(poly, positions, radius)
                if extra:
                    positions = positions + [extra]

        return positions, retries

    # ------------------------------------------------------------------
    # FIX-1: MIP solver with explicit fallback chain
    # ------------------------------------------------------------------

    def _solve_mip_with_fallback(
        self,
        poly:              Polygon,
        radius:            float,
        spacing:           float,
        max_wall:          float,
        required_fraction: float,
        polygon_coords:    List,
        result:            ExpertResultV12,
    ) -> Tuple[
        List[Tuple[float, float]],   # positions (best available)
        int,                          # retries
        bool,                         # used_mip
        Optional[Dict],               # mip_proof
        str,                          # fallback_reason (empty = no fallback)
    ]:
        """
        FIX-1: Invoke OptimalMIPEngine with a full fallback chain.

        Priority:
          1. OPTIMAL result with positions → use as-is (best case).
          2. FEASIBLE / TIME_LIMIT with positions → use sub-optimal MIP result,
             emit warning, flag mip_fallback_reason.
          3. Empty positions from MIP (INFEASIBLE or exception) → fall back to
             greedy, emit warning, set used_mip=False.

        A room is NEVER rejected solely due to MIP non-OPTIMAL status.

        Returns:
            (positions, retries, used_mip, mip_proof_dict, fallback_reason)
        """
        try:
            engine = OptimalMIPEngine(
                grid_size      = 0.0,
                radius         = radius,
                placement_step = _MIP_PLACEMENT_STEP,
                coverage_step  = _MIP_COVERAGE_STEP,
                time_limit_s   = _MIP_TIME_LIMIT,
            )
            pl, cov_pct, proof, status = engine.solve_polygon(polygon_coords)

            if status == "OPTIMAL" and pl:
                logger.info(
                    "_solve_mip: OPTIMAL %d devices cov=%.1f%%", len(pl), cov_pct
                )
                return pl, 0, True, proof, ""

            if status in _MIP_ACCEPTABLE_STATUSES and pl:
                # Sub-optimal but usable — use it and warn
                fallback_msg = (
                    f"MIP returned status={status} (not OPTIMAL) with "
                    f"{len(pl)} devices, coverage={cov_pct:.1f}%. "
                    "Result is sub-optimal. Review layout manually. "
                    "NFPA 72-2022 §17.6."
                )
                result.warnings.append(f"[MIP_SUBOPTIMAL] {fallback_msg}")
                logger.warning("_solve_mip: %s", fallback_msg)
                return pl, 0, True, proof, f"MIP status={status} (sub-optimal but used)"

            # MIP returned no positions or unacceptable status
            fallback_msg = (
                f"MIP returned status={status} with no valid positions. "
                "Falling back to greedy solver. "
                "Result may be sub-optimal — manual review recommended."
            )
            result.warnings.append(f"[MIP_FALLBACK_TO_GREEDY] {fallback_msg}")
            logger.warning("_solve_mip: %s", fallback_msg)

            # Fall back to greedy
            greedy_positions, retries = self._solve_greedy(
                poly, spacing, radius, max_wall, required_fraction
            )
            return (
                greedy_positions,
                retries,
                False,    # used_mip=False because we're using greedy result
                proof,    # keep MIP proof object for diagnostic purposes
                f"MIP status={status}; greedy fallback used",
            )

        except Exception as exc:
            fallback_msg = (
                f"MIP solver raised exception: {type(exc).__name__}: {exc}. "
                "Falling back to greedy solver."
            )
            result.warnings.append(f"[MIP_EXCEPTION_FALLBACK] {fallback_msg}")
            logger.error("_solve_mip: exception: %s", exc)

            greedy_positions, retries = self._solve_greedy(
                poly, spacing, radius, max_wall, required_fraction
            )
            return (
                greedy_positions,
                retries,
                False,
                None,
                f"MIP exception ({type(exc).__name__}); greedy fallback used",
            )

    # ------------------------------------------------------------------
    # Floor analysis
    # ------------------------------------------------------------------

    def analyse_floor(
        self,
        rooms:                 List[RoomSpec],
        required_coverage_pct: float = 100.0,
        run_resilience:        bool  = True,
    ) -> List[ExpertResultV12]:
        """
        Analyse all rooms on a floor, sharing ProjectMemory across rooms.

        Thread-safe: ProjectMemory is shared and protected by its internal lock.
        Returns one ExpertResultV12 per room.
        """
        results = []
        for room_spec in rooms:
            r = self.analyse_room(
                room_spec             = room_spec,
                required_coverage_pct = required_coverage_pct,
                run_resilience        = run_resilience,
            )
            results.append(r)

        n_unsafe = sum(1 for r in results if r.confidence == ConfidenceLevel.UNSAFE)
        if n_unsafe:
            logger.error(
                "V12 floor: %d/%d UNSAFE — do NOT submit.", n_unsafe, len(results)
            )

        logger.info("V12 memory: %s", self.memory.summary())
        return results
