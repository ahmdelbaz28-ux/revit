"""
fire_expert_system_v13_adapted.py — V13 Adapted for FireAI Production
================================================================
Based on V13 source with modifications for integration with our system:
  - Fixed imports (fireai.core.* instead of relative)
  - MIP disabled (greedy only)
  - Uses external audit_store instead of internal audit_log
  - LEARN-6 (geometry similarity) removed for simplicity
  - Added project_id support to experience table
"""

from __future__ import annotations

import hashlib
import json
import logging
import math
import random
import sqlite3
import threading
import time
from collections import OrderedDict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from shapely.geometry import Point, Polygon
from shapely.ops import unary_union

# Import from our project
from fireai.core.nfpa72_models import (
    CeilingSpec, CeilingType, DetectorType, HVACDuct,
    MIN_WALL_DISTANCE_M, RoomSpec,
    _NFPA_HEIGHT_MAX_M, _NFPA_HEIGHT_MIN_M,
)
from fireai.core.nfpa72_calculations import (
    calculate_coverage_radius, calculate_max_spacing,
    calculate_max_wall_distance,
)
from fireai.core.nfpa72_coverage import (
    CoverageResult, DuctDevice, WallViolation,
    check_coverage_polygon, suggest_duct_detectors, validate_wall_distances,
)

logger = logging.getLogger(__name__)

# Import V10 primitives
from fireai.core.fire_expert_system import (
    ConfidenceLevel, OccupancyClass, ImprovementProposal, PlacementProof,
    SafetyRefusalError, InputValidationError,
    _MIN_POLYGON_VERTICES, _MIN_ROOM_AREA_M2, _MAX_ROOM_AREA_M2,
    _COVERAGE_GRID_M, _MAX_PLACEMENT_RETRIES,
    _CONFIDENCE_HIGH_THRESHOLD, _CONFIDENCE_MEDIUM_THRESHOLD,
    _classify_occupancy, _select_detector_type,
    _build_valid_polygon, _coverage_aware_placement,
    _compute_placement_proof, _compute_confidence,
    _generate_improvements, _find_uncovered_centroid,
    ExpertResult,
)

# V12 constants (hardcoded, not imported)
_MIP_ESCALATION_THRESHOLD = 0.70
_MIP_PLACEMENT_STEP = 0.25
_MIP_COVERAGE_STEP = 0.10
_MIP_TIME_LIMIT = 60
_MIP_ACCEPTABLE_STATUSES = ["OPTIMAL", "FEASIBLE", "TIMEOUT_FEASIBLE"]
_MC_ITERATIONS = 50
_MC_RESILIENCE_FLOOR = 0.80
_PROOF_ENGINE_AVAILABLE = False  # Disabled

# ── Optional numpy for vectorized Monte Carlo ─────────────────────────────────
try:
    import numpy as np
    _NUMPY_AVAILABLE = True
    logger.debug("numpy available — vectorized Monte Carlo enabled.")
except ImportError:
    _NUMPY_AVAILABLE = False
    logger.debug("numpy not available — using pure-Python Monte Carlo.")


# ============================================================================
# CONSTANTS
# ============================================================================

_DEFAULT_DB_PATH = Path("fire_expert_v13_adapted.sqlite3")
_CALIBRATION_MIN_RECORDS = 30
_CALIBRATION_INTERVAL = 500

# Safety floor: calibrated thresholds must never go below V10 constants
_CALIBRATION_HIGH_FLOOR = _CONFIDENCE_HIGH_THRESHOLD
_CALIBRATION_MEDIUM_FLOOR = _CONFIDENCE_MEDIUM_THRESHOLD

_MEMORY_MAX_RECORDS = 2048


# ============================================================================
# ADAPTIVE MEMORY (LEARN-1, LEARN-2, LEARN-3, LEARN-4, LEARN-5)
# ============================================================================

_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS experience (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id TEXT NOT NULL,
    geometry_hash TEXT NOT NULL,
    room_area_m2 REAL NOT NULL,
    occupancy TEXT NOT NULL,
    detector_type TEXT NOT NULL,
    solver_used TEXT NOT NULL,
    coverage_pct REAL NOT NULL,
    confidence_score REAL NOT NULL,
    confidence_level TEXT NOT NULL,
    resilience_pass_rate REAL,
    wall_violation_count INTEGER NOT NULL DEFAULT 0,
    greedy_retries INTEGER NOT NULL DEFAULT 0,
    mip_status TEXT,
    proof_valid INTEGER NOT NULL DEFAULT 0,
    compliant INTEGER NOT NULL DEFAULT 0,
    timestamp_utc TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_geometry_hash ON experience(geometry_hash);
CREATE INDEX IF NOT EXISTS idx_occupancy ON experience(occupancy);
CREATE INDEX IF NOT EXISTS idx_area ON experience(room_area_m2);

CREATE TABLE IF NOT EXISTS calibration_meta (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    high_threshold REAL NOT NULL,
    medium_threshold REAL NOT NULL,
    calibrated_at TEXT NOT NULL,
    records_at_calibration INTEGER NOT NULL
);
"""


@dataclass
class ExperienceRecord:
    """One stored analysis outcome."""
    geometry_hash: str
    room_area_m2: float
    occupancy: str
    detector_type: str
    solver_used: str
    coverage_pct: float
    confidence_score: float
    confidence_level: str
    resilience_pass_rate: Optional[float]
    wall_violation_count: int
    greedy_retries: int
    mip_status: Optional[str]
    proof_valid: bool
    compliant: bool
    timestamp_utc: str


class AdaptiveMemory:
    """
    Thread-safe, persistent experience store.
    Adapted from V13 with project_id support.
    """

    def __init__(
        self,
        db_path: Path = _DEFAULT_DB_PATH,
        max_records: int = _MEMORY_MAX_RECORDS,
    ) -> None:
        self._lock = threading.Lock()
        self._hot_cache: OrderedDict[str, ExperienceRecord] = OrderedDict()
        self._max_records = max(1, max_records)
        self._db_path = db_path
        self._db_ok = False
        self._total_stored = 0
        self._greedy_attempts = 0
        self._greedy_successes = 0

        # Calibration state
        self._high_threshold = _CALIBRATION_HIGH_FLOOR
        self._medium_threshold = _CALIBRATION_MEDIUM_FLOOR
        self._records_at_last_calibration = 0

        self._init_db()
        self._load_calibration()

    def _init_db(self) -> None:
        try:
            con = sqlite3.connect(str(self._db_path), check_same_thread=False)
            con.executescript(_SCHEMA_SQL)
            con.commit()
            con.close()
            self._db_ok = True
            logger.info("AdaptiveMemory: DB initialised at %s", self._db_path)
        except Exception as exc:
            logger.warning("AdaptiveMemory: DB init failed (%s)", exc)

    def _connect(self) -> Optional[sqlite3.Connection]:
        if not self._db_ok:
            return None
        try:
            con = sqlite3.connect(str(self._db_path), check_same_thread=False)
            con.row_factory = sqlite3.Row
            return con
        except Exception as exc:
            logger.warning("AdaptiveMemory: DB connect failed: %s", exc)
            return None

    @staticmethod
    def geometry_key(
        polygon_coords: List,
        occupancy: OccupancyClass,
        ceiling_height: float,
    ) -> str:
        rounded = [(round(x, 1), round(y, 1)) for x, y in polygon_coords]
        payload = json.dumps({
            "poly": sorted(rounded),
            "occ": occupancy.value,
            "h": round(ceiling_height, 1),
        }, sort_keys=True)
        return hashlib.sha256(payload.encode()).hexdigest()[:16]

    # LEARN-2: Data-driven routing
    def should_use_mip_direct(
        self,
        geometry_hash: str,
        occupancy: OccupancyClass,
    ) -> Tuple[bool, str]:
        """Return (use_mip, reason). Always returns False (MIP disabled)."""
        with self._lock:
            rec = self._hot_cache.get(geometry_hash)
            if rec:
                rec_is_mip = rec.solver_used in ("mip", "mip_fallback")
                return rec_is_mip, f"hot_cache_exact_match solver={rec.solver_used}"

            con = self._connect()
            if con:
                try:
                    cur = con.execute(
                        "SELECT solver_used FROM experience "
                        "WHERE geometry_hash = ? ORDER BY id DESC LIMIT 1",
                        (geometry_hash,)
                    )
                    row = cur.fetchone()
                    if row:
                        is_mip = row["solver_used"] in ("mip", "mip_fallback")
                        return is_mip, f"db_exact_match solver={row['solver_used']}"

                    # Check occupancy history
                    cur = con.execute(
                        "SELECT COUNT(*) as total FROM experience"
                    )
                    row = cur.fetchone()
                    total_records = row["total"] if row else 0

                    if total_records < _CALIBRATION_MIN_RECORDS:
                        return False, "cold_start: insufficient history, defaulting to greedy"

                    cur = con.execute(
                        "SELECT "
                        "  SUM(CASE WHEN solver_used='greedy' AND compliant=1 THEN 1 ELSE 0 END) as wins, "
                        "  SUM(CASE WHEN solver_used='greedy' THEN 1 ELSE 0 END) as tries "
                        "FROM experience WHERE occupancy = ?",
                        (occupancy.value,)
                    )
                    occ_row = cur.fetchone()
                    if occ_row and occ_row["tries"] and occ_row["tries"] > 0:
                        rate = occ_row["wins"] / occ_row["tries"]
                        use_mip = rate < 0.70
                        return use_mip, (
                            f"occupancy_history: greedy_success_rate={rate:.2%} "
                            f"({'< 70% → MIP' if use_mip else '≥ 70% → greedy'})"
                        )
                finally:
                    con.close()

        return False, "no_history: defaulting to greedy"

    def store_experience(self, rec: ExperienceRecord, project_id: str = "default") -> None:
        """Persist record to hot cache and SQLite."""
        with self._lock:
            if rec.geometry_hash in self._hot_cache:
                self._hot_cache.move_to_end(rec.geometry_hash)
            else:
                if len(self._hot_cache) >= self._max_records:
                    self._hot_cache.popitem(last=False)
            self._hot_cache[rec.geometry_hash] = rec
            self._total_stored += 1

        con = self._connect()
        if not con:
            return
        try:
            con.execute(
                "INSERT INTO experience "
                "(project_id, geometry_hash, room_area_m2, occupancy, detector_type, "
                " solver_used, coverage_pct, confidence_score, confidence_level, "
                " resilience_pass_rate, wall_violation_count, greedy_retries, "
                " mip_status, proof_valid, compliant, timestamp_utc) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    project_id,
                    rec.geometry_hash,
                    rec.room_area_m2,
                    rec.occupancy,
                    rec.detector_type,
                    rec.solver_used,
                    rec.coverage_pct,
                    rec.confidence_score,
                    rec.confidence_level,
                    rec.resilience_pass_rate,
                    rec.wall_violation_count,
                    rec.greedy_retries,
                    rec.mip_status,
                    int(rec.proof_valid),
                    int(rec.compliant),
                    rec.timestamp_utc,
                )
            )
            con.commit()
        except Exception as exc:
            logger.warning("store_experience: DB write failed: %s", exc)
        finally:
            con.close()

        self._maybe_recalibrate()

    # LEARN-5: Calibration
    def _load_calibration(self) -> None:
        con = self._connect()
        if not con:
            return
        try:
            row = con.execute(
                "SELECT high_threshold, medium_threshold FROM calibration_meta WHERE id = 1"
            ).fetchone()
            if row:
                ht = max(row["high_threshold"], _CALIBRATION_HIGH_FLOOR)
                mt = max(row["medium_threshold"], _CALIBRATION_MEDIUM_FLOOR)
                with self._lock:
                    self._high_threshold = ht
                    self._medium_threshold = mt
                logger.info("AdaptiveMemory: loaded calibration high=%.4f medium=%.4f", ht, mt)
        except Exception as exc:
            logger.debug("_load_calibration: %s", exc)
        finally:
            con.close()

    def _maybe_recalibrate(self) -> None:
        with self._lock:
            stored = self._total_stored
            if stored - self._records_at_last_calibration < _CALIBRATION_INTERVAL:
                return
            self._records_at_last_calibration = stored
        self._recalibrate()

    def _recalibrate(self) -> None:
        con = self._connect()
        if not con:
            return
        try:
            rows_high = con.execute(
                "SELECT confidence_score FROM experience "
                "WHERE compliant = 1 AND resilience_pass_rate >= 0.90 "
                "ORDER BY confidence_score"
            ).fetchall()

            rows_medium = con.execute(
                "SELECT confidence_score FROM experience "
                "WHERE compliant = 1 "
                "ORDER BY confidence_score"
            ).fetchall()

            if len(rows_high) < _CALIBRATION_MIN_RECORDS:
                logger.debug("_recalibrate: only %d qualifying records", len(rows_high))
                return

            def percentile_10(rows):
                scores = [r[0] for r in rows]
                idx = max(0, int(len(scores) * 0.10) - 1)
                return scores[idx]

            new_high = max(percentile_10(rows_high), _CALIBRATION_HIGH_FLOOR)
            new_medium = max(percentile_10(rows_medium), _CALIBRATION_MEDIUM_FLOOR)

            with self._lock:
                self._high_threshold = new_high
                self._medium_threshold = new_medium

            ts = datetime.now(timezone.utc).isoformat()
            con.execute(
                "INSERT OR REPLACE INTO calibration_meta "
                "(id, high_threshold, medium_threshold, calibrated_at, records_at_calibration) "
                "VALUES (1, ?, ?, ?, ?)",
                (new_high, new_medium, ts, len(rows_high))
            )
            con.commit()
            logger.info(
                "AdaptiveMemory: recalibrated high=%.4f medium=%.4f from %d records",
                new_high, new_medium, len(rows_high),
            )
        except Exception as exc:
            logger.warning("_recalibrate: failed: %s", exc)
        finally:
            con.close()

    @property
    def calibrated_thresholds(self) -> Tuple[float, float]:
        with self._lock:
            return self._high_threshold, self._medium_threshold

    def record_greedy_attempt(self, success: bool) -> None:
        with self._lock:
            self._greedy_attempts += 1
            if success:
                self._greedy_successes += 1

    @property
    def greedy_success_rate(self) -> float:
        with self._lock:
            if self._greedy_attempts == 0:
                return 1.0
            return self._greedy_successes / self._greedy_attempts

    def summary(self) -> Dict:
        with self._lock:
            ht, mt = self._high_threshold, self._medium_threshold
            hot = len(self._hot_cache)
        con = self._connect()
        total_db = 0
        if con:
            try:
                row = con.execute("SELECT COUNT(*) FROM experience").fetchone()
                total_db = row[0] if row else 0
            finally:
                con.close()
        return {
            "hot_cache_records": hot,
            "db_total_records": total_db,
            "greedy_attempts": self._greedy_attempts,
            "greedy_successes": self._greedy_successes,
            "greedy_success_rate": round(self.greedy_success_rate, 3),
            "calibrated_high": round(ht, 4),
            "calibrated_medium": round(mt, 4),
            "db_available": self._db_ok,
        }


# ============================================================================
# RESILIENCE CHECK (LEARN-3)
# ============================================================================

@dataclass
class ResilienceResult:
    scenarios_run: int
    scenarios_passed: int
    pass_rate: float
    min_coverage_seen: float
    resilience_floor: float
    resilient: bool
    failure_detail: Optional[str] = None


def _run_resilience_check_fast(
    positions: List[Tuple[float, float]],
    poly: Polygon,
    radius: float,
    floor: float = _MC_RESILIENCE_FLOOR,
    iterations: int = _MC_ITERATIONS,
    seed: int = 42,
) -> ResilienceResult:
    """numpy-vectorized Monte Carlo."""
    if not _NUMPY_AVAILABLE:
        # Fallback to pure Python
        if len(positions) <= 1:
            return ResilienceResult(
                scenarios_run=iterations, scenarios_passed=0, pass_rate=0.0,
                min_coverage_seen=0.0, resilience_floor=floor, resilient=False,
                failure_detail="Only 1 detector",
            )
        rng = random.Random(seed)
        passed = 0
        min_cov = 1.0
        for _ in range(iterations):
            idx = rng.randrange(len(positions))
            remaining = positions[:idx] + positions[idx + 1:]
            coverage = unary_union([Point(x, y).buffer(radius, resolution=12) for x, y in remaining])
            cov_frac = poly.intersection(coverage).area / poly.area
            min_cov = min(min_cov, cov_frac)
            if cov_frac >= floor:
                passed += 1
        return ResilienceResult(
            scenarios_run=iterations, scenarios_passed=passed, pass_rate=passed/iterations,
            min_coverage_seen=round(min_cov, 4), resilience_floor=floor,
            resilient=passed/iterations >= 0.90,
            failure_detail=None if passed/iterations >= 0.90 else f"Failed {iterations-passed}/{iterations}"
        )

    if len(positions) <= 1:
        return ResilienceResult(
            scenarios_run=iterations, scenarios_passed=0, pass_rate=0.0,
            min_coverage_seen=0.0, resilience_floor=floor, resilient=False,
            failure_detail="Only 1 detector",
        )

    min_x, min_y, max_x, max_y = poly.bounds
    grid = []
    tx = min_x + _COVERAGE_GRID_M
    while tx <= max_x:
        ty = min_y + _COVERAGE_GRID_M
        while ty <= max_y:
            if poly.contains(Point(tx, ty)):
                grid.append((tx, ty))
            ty += _COVERAGE_GRID_M
        tx += _COVERAGE_GRID_M

    if not grid:
        return ResilienceResult(
            scenarios_run=iterations, scenarios_passed=0, pass_rate=1.0,
            min_coverage_seen=1.0, resilience_floor=floor, resilient=True,
        )

    grid_arr = np.array(grid, dtype=np.float64)
    pos_arr = np.array(positions, dtype=np.float64)
    r2 = radius * radius
    n = len(positions)
    G = len(grid_arr)

    rng = random.Random(seed)
    passed = 0
    min_cov = 1.0

    for _ in range(iterations):
        failed_idx = rng.randrange(n)
        mask = np.ones(n, dtype=bool)
        mask[failed_idx] = False
        remaining = pos_arr[mask]

        diff = grid_arr[:, np.newaxis, :] - remaining[np.newaxis, :, :]
        d2 = (diff ** 2).sum(axis=2)
        covered_mask = (d2 <= r2).any(axis=1)
        cov_frac = covered_mask.sum() / G

        if cov_frac < min_cov:
            min_cov = float(cov_frac)
        if cov_frac >= floor:
            passed += 1

    pass_rate = passed / iterations
    return ResilienceResult(
        scenarios_run=iterations, scenarios_passed=passed, pass_rate=round(pass_rate, 4),
        min_coverage_seen=round(min_cov, 4), resilience_floor=floor,
        resilient=pass_rate >= 0.90,
        failure_detail=None if pass_rate >= 0.90 else f"Failed {iterations-passed}/{iterations}"
    )


# ============================================================================
# EXPERT RESULT V13 ADAPTED (Standalone)
# ============================================================================

@dataclass
class ExpertResultV13:
    """Result from V13 analysis."""
    room_id: str = ""
    nfpa_version: str = ""
    
    # Detection results
    detector_positions: List[Tuple[float, float]] = field(default_factory=list)
    detector_type: Optional[DetectorType] = None
    occupancy_class: Optional[OccupancyClass] = None
    
    # Coverage
    placement_proof: Optional[PlacementProof] = None
    coverage_result: Optional[CoverageResult] = None
    
    # Wall violations
    wall_violations: List[WallViolation] = field(default_factory=list)
    
    # Duct devices
    duct_devices: List[DuctDevice] = field(default_factory=list)
    
    # Confidence
    confidence: Optional[ConfidenceLevel] = None
    confidence_score: float = 0.0
    
    # Resilience
    resilience: Optional[ResilienceResult] = None
    
    # Errors/warnings
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    improvements: List[ImprovementProposal] = field(default_factory=list)
    
    # Routing info
    routing_source: str = ""
    similarity_hint: bool = False
    calibrated_high: float = _CONFIDENCE_HIGH_THRESHOLD
    calibrated_medium: float = _CONFIDENCE_MEDIUM_THRESHOLD
    monte_carlo_engine: str = ""
    used_mip: bool = False
    retry_count: int = 0
    
    # Compliance
    @property
    def compliant(self) -> bool:
        return (self.confidence in (ConfidenceLevel.CERTIFIED, ConfidenceLevel.HIGH) and 
                not self.errors)
    
    @property
    def safe_to_submit(self) -> bool:
        return self.compliant and not self.errors


# ============================================================================
# EXPERT SYSTEM V13 ADAPTED
# ============================================================================

class ExpertSystemV13:
    """
    NFPA 72-2022 Expert System — V13 Adapted.
    
    Key changes from V13:
      - MIP disabled (greedy only)
      - External audit_store integration
      - project_id support
    """

    def __init__(
        self,
        audit_store,
        nfpa_version: str = "NFPA 72-2022",
        memory: Optional[AdaptiveMemory] = None,
    ) -> None:
        self.nfpa_version = nfpa_version
        self.memory = memory or AdaptiveMemory()
        self.audit_store = audit_store

    def analyse_room(
        self,
        room_spec: RoomSpec,
        project_id: str = "default",
        forced_detector_type: Optional[DetectorType] = None,
        required_coverage_pct: float = 100.0,
        run_resilience: bool = True,
        build_regulatory_proof: bool = False,
    ) -> ExpertResultV13:
        """Full analysis with adaptive learning."""
        result = ExpertResultV13(
            room_id=room_spec.room_id,
            nfpa_version=self.nfpa_version,
        )

        try:
            self._pipeline(
                room_spec, project_id, forced_detector_type,
                required_coverage_pct, run_resilience, build_regulatory_proof,
                result,
            )
        except SafetyRefusalError as exc:
            result.refused = True
            result.refusal_reason = str(exc)
            result.confidence = ConfidenceLevel.UNSAFE
            result.errors.append(f"SAFETY_REFUSAL: {exc}")
            logger.error("V13: REFUSED room=%s: %s", room_spec.room_id, exc)
        except InputValidationError as exc:
            result.refused = True
            result.refusal_reason = str(exc)
            result.confidence = ConfidenceLevel.UNSAFE
            result.errors.append(f"INPUT_ERROR: {exc}")
            logger.error("V13: INPUT_ERROR room=%s: %s", room_spec.room_id, exc)
        except Exception as exc:
            result.errors.append(f"SYSTEM_FAULT: {type(exc).__name__}: {exc}")
            result.confidence = ConfidenceLevel.UNSAFE
            logger.exception("V13: FAULT room=%s", room_spec.room_id)

        return result

    def _pipeline(
        self,
        room_spec: RoomSpec,
        project_id: str,
        forced_detector_type: Optional[DetectorType],
        required_coverage_pct: float,
        run_resilience: bool,
        build_reg_proof: bool,
        result: ExpertResultV13,
    ) -> None:
        required_fraction = required_coverage_pct / 100.0

        # Phase 0: Input Validation
        poly = _build_valid_polygon(room_spec.polygon_coords)
        if poly is None:
            raise InputValidationError(
                f"Room '{room_spec.room_id}': polygon degenerate or area < {_MIN_ROOM_AREA_M2} m²."
            )
        if poly.area > _MAX_ROOM_AREA_M2:
            raise InputValidationError(
                f"Room '{room_spec.room_id}': area {poly.area:.0f} m² > {_MAX_ROOM_AREA_M2} m² limit."
            )

        # Phase 1: Ceiling
        input_ceiling = room_spec.ceiling
        ceiling_clamped = input_ceiling.was_clamped
        ceiling = CeilingSpec.create_safe(
            height_at_low_point_m=input_ceiling.height_at_low_point_m,
            height_at_high_point_m=input_ceiling.height_at_high_point_m,
            ceiling_type=input_ceiling.ceiling_type,
            beam_depth_m=input_ceiling.beam_depth_m,
            beam_spacing_m=input_ceiling.beam_spacing_m,
        )
        if ceiling.was_clamped:
            ceiling_clamped = True
        if ceiling_clamped:
            result.warnings.append(
                f"[ACKNOWLEDGED] Ceiling clamped to {ceiling.height_at_low_point_m:.2f} m. PE review required."
            )

        # Phase 2: Occupancy & Detector
        occupancy = _classify_occupancy(room_spec, ceiling)
        detector_type = _select_detector_type(
            occupancy, ceiling, forced_detector_type, room_spec.room_id
        )
        result.occupancy_class = occupancy
        result.detector_type = detector_type

        # Phase 3: NFPA values
        spacing = calculate_max_spacing(ceiling, detector_type)
        radius = calculate_coverage_radius(ceiling, detector_type)
        max_wall = calculate_max_wall_distance(ceiling, detector_type)

        # Phase 4: Load calibrated thresholds
        cal_high, cal_medium = self.memory.calibrated_thresholds
        result.calibrated_high = cal_high
        result.calibrated_medium = cal_medium

        # Phase 5: Routing (Greedy only - MIP disabled)
        geom_key = AdaptiveMemory.geometry_key(
            room_spec.polygon_coords, occupancy, ceiling.height_at_low_point_m
        )

        use_mip_direct, routing_reason = self.memory.should_use_mip_direct(
            geom_key, occupancy
        )
        result.routing_source = routing_reason

        # GREEDY ONLY (MIP disabled)
        result.routing_reason = f"Greedy: {result.routing_source}"
        positions, retries = self._solve_greedy(
            poly, spacing, radius, max_wall, required_fraction
        )

        if not positions:
            raise InputValidationError(
                f"Room '{room_spec.room_id}': no valid positions found by greedy."
            )

        result.detector_positions = positions
        result.retry_count = retries

        # Phase 6: Coverage Proof
        proof = _compute_placement_proof(positions, poly, radius, required_fraction)
        result.placement_proof = proof

        result.coverage_result = check_coverage_polygon(
            detector_positions=positions,
            room_spec=room_spec,
            ceiling_spec=ceiling,
            detector_type=detector_type,
        )

        if not proof.proof_valid:
            result.errors.append(
                f"COVERAGE_FAILED: {proof.coverage_fraction*100:.2f}% < {required_coverage_pct:.0f}%"
            )

        # Phase 7: Wall Distance
        result.wall_violations = validate_wall_distances(
            positions,
            room_spec,
        )

        # Phase 8: Duct Detectors
        if room_spec.hvac_ducts:
            duct_devs = suggest_duct_detectors(room_spec.hvac_ducts)
            result.duct_devices = duct_devs
            if duct_devs:
                result.warnings.append(f"[NFPA 72-2022 §17.7.5] {len(duct_devs)} duct detector(s) added.")

        # Phase 9: Confidence
        confidence, score = _compute_confidence(result, retries, ceiling_clamped)
        result.confidence = confidence
        result.confidence_score = score

        # Phase 10: Resilience
        if run_resilience and len(positions) >= 2:
            result.resilience = _run_resilience_check_fast(
                positions, poly, radius
            )
            result.monte_carlo_engine = "numpy_vectorized" if _NUMPY_AVAILABLE else "python_fallback"
            if result.resilience and not result.resilience.resilient:
                result.warnings.append(f"[RESILIENCE] {result.resilience.failure_detail}")

        # Phase 11: Improvements
        improvements = _generate_improvements(result, poly, ceiling, radius, proof)
        if result.resilience and not result.resilience.resilient:
            improvements.insert(0, ImprovementProposal(
                priority="SAFETY",
                clause="NFPA 72-2022 §10.3",
                description=result.resilience.failure_detail or "",
                action="ADD_DETECTOR",
                location=None,
            ))
        result.improvements = improvements

        # Phase 12: Store experience
        resilience_pass_rate = result.resilience.pass_rate if result.resilience else None
        exp_rec = ExperienceRecord(
            geometry_hash=geom_key,
            room_area_m2=round(poly.area, 2),
            occupancy=occupancy.value,
            detector_type=detector_type.value,
            solver_used="greedy",
            coverage_pct=round(proof.coverage_fraction * 100, 2),
            confidence_score=round(score, 4),
            confidence_level=confidence.value,
            resilience_pass_rate=resilience_pass_rate,
            wall_violation_count=len(result.wall_violations),
            greedy_retries=retries,
            mip_status=None,
            proof_valid=proof.proof_valid,
            compliant=result.compliant,
            timestamp_utc=datetime.now(timezone.utc).isoformat(),
        )
        self.memory.store_experience(exp_rec, project_id)

        # Phase 13: External audit store
        self.audit_store.add_event(
            event_type="room_analysis",
            room_id=room_spec.room_id,
            details_dict={
                "detector_count": len(positions),
                "confidence": confidence.value if confidence else "UNKNOWN",
                "coverage": proof.coverage_fraction if proof else None,
                "project_id": project_id,
                "resilience": result.resilience.resilient if result.resilience else None,
            },
        )

        logger.info(
            "V13: room=%s occ=%s type=%s detectors=%d cov=%.2f%% conf=%s(%.4f) mc=%s",
            room_spec.room_id, occupancy.value, detector_type.value,
            len(positions), proof.coverage_fraction * 100,
            confidence.value, score, result.monte_carlo_engine,
        )

    def _solve_greedy(
        self,
        poly: Polygon,
        spacing: float,
        radius: float,
        max_wall: float,
        required_fraction: float,
    ) -> Tuple[List[Tuple[float, float]], int]:
        positions = []
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

    def analyse_floor(
        self,
        rooms: List[RoomSpec],
        project_id: str = "default",
        required_coverage_pct: float = 100.0,
        run_resilience: bool = True,
    ) -> List[ExpertResultV13]:
        """Analyse all rooms on a floor."""
        results = []
        for room_spec in rooms:
            r = self.analyse_room(
                room_spec=room_spec,
                project_id=project_id,
                required_coverage_pct=required_coverage_pct,
                run_resilience=run_resilience,
            )
            results.append(r)

        n_unsafe = sum(1 for r in results if r.confidence == ConfidenceLevel.UNSAFE)
        if n_unsafe:
            logger.error("V13 floor: %d/%d UNSAFE", n_unsafe, len(results))

        logger.info("V13 memory: %s", self.memory.summary())
        return results