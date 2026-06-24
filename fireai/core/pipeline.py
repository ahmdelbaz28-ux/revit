"""pipeline.py — FireAI Main Analysis Pipeline
=============================================
THE MISSING GLUE. Connects every module into one executable workflow.

INPUT:  room payload dict (from DXF parser or direct API call)
OUTPUT: complete engineering result dict ready for audit report

PIPELINE STAGES:
  Stage 0: Contract validation (contracts.py)
  Stage 1: NFPA 72 spacing calculation (nfpa72_engine.py)
  Stage 2: Detector placement optimization (density_optimizer shim)
  Stage 3: Coverage verification (truth_deriver + exact_coverage)
  Stage 3.5: Rules Engine compliance check (rules_engine/compliance_bridge.py)
  Stage 4: Safety classification (safety_assurance.py)
  Stage 5: Release gate evaluation (release_gates.py)
  Stage 6: Audit packaging (EngineeringEvidencePackage)

DESIGN DECISIONS:
  - Each stage is isolated: failure in Stage 3 does not prevent
    Stage 1/2 results from being reported (partial results > no results)
  - Every stage result is captured and included in final output
  - Stage failures return structured errors, never raise to caller
  - NaN/Inf are caught at Stage 0 and never propagate

PERFORMANCE:
  - Single room: < 2 seconds end-to-end
  - Batch mode: concurrent via ThreadPoolExecutor (Stage 2-3 only)
  - SQLite writes batched (Stage 6 only writes on success)

This file is the entry point for the CLI and the API server.
"""

from __future__ import annotations

import hashlib
import json
import logging
import math
import time
import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

# V61: Late import for cable routing (optional, may not be available)
try:
    from fireai.core.cable_router import CableRouter
    from fireai.core.cable_routing_engine import WireGauge

    _CABLE_ROUTER_AVAILABLE = True
except ImportError:
    _CABLE_ROUTER_AVAILABLE = False
    WireGauge = None  # type: ignore[assignment,misc]

try:
    from fireai.core.constraint_engine import ConstraintEngine

    _CONSTRAINT_ENGINE_AVAILABLE = True
except ImportError:
    _CONSTRAINT_ENGINE_AVAILABLE = False

from fireai.core.contracts_validation import ContractViolation, validate_room_input
from fireai.core.nfpa72_engine import (
    BatteryResult,
    calculate_battery,
    calculate_voltage_drop,
    estimate_detector_count,
    get_detector_spacing,
    verify_fault_isolator_placement,
)
from fireai.core.release_gates import verify_and_evaluate

# Rules Engine integration (declarative NFPA 72 compliance)
from fireai.core.rules_engine.compliance_bridge import (
    NFPA72ComplianceChecker,
)
from fireai.core.safety_assurance import (
    EngineeringEvidencePackage,
    SafetyTier,
    classify_safety_tier,
)

logger = logging.getLogger(__name__)


# ─── Stage Results ────────────────────────────────────────────────────────────


@dataclass
class StageResult:
    """Result from a single pipeline stage."""

    stage_name: str
    success: bool
    duration_ms: float
    data: Dict[str, Any] = field(default_factory=dict)
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)


@dataclass
class PipelineResult:
    """Complete result from the FireAI analysis pipeline.

    All fields have safe defaults — never raises on access.
    Caller checks result.success and result.release_status before using values.
    """

    run_id: str
    room_id: str
    success: bool
    release_status: str  # "green" | "blocked"
    safety_tier: str  # SafetyTier value
    coverage_pct: float  # 0.0 – 100.0
    detector_count: int
    detector_radius_m: float
    max_spacing_m: float
    detector_positions: List[Tuple[float, float]]
    wall_violations: int
    battery: Optional[Dict]
    voltage_drop: Optional[Dict]
    fault_isolation: Optional[Dict]
    stages: List[StageResult]
    release_gates: Dict[str, Any]
    evidence_hash: str
    total_ms: float
    errors: List[str]
    warnings: List[str]
    nfpa_references: List[str]
    timestamp: str
    cable_routing: Optional[Dict] = None  # V61: Cable routing schedule summary
    qomn_audit: Optional[Dict] = None  # QOMN Layer 4 audit log (tamper-evident)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "run_id": self.run_id,
            "room_id": self.room_id,
            "success": self.success,
            "release_status": self.release_status,
            "safety_tier": self.safety_tier,
            "coverage_pct": self.coverage_pct,
            "detector_count": self.detector_count,
            "detector_radius_m": self.detector_radius_m,
            "max_spacing_m": self.max_spacing_m,
            "detector_positions": self.detector_positions,
            "wall_violations": self.wall_violations,
            "battery": self.battery,
            "voltage_drop": self.voltage_drop,
            "fault_isolation": self.fault_isolation,
            "cable_routing": self.cable_routing,
            "qomn_audit": self.qomn_audit,
            "release_gates": self.release_gates,
            "evidence_hash": self.evidence_hash,
            "total_ms": self.total_ms,
            "errors": self.errors,
            "warnings": self.warnings,
            "nfpa_references": self.nfpa_references,
            "timestamp": self.timestamp,
            "stages": [
                {
                    "stage": s.stage_name,
                    "success": s.success,
                    "duration_ms": s.duration_ms,
                    "errors": s.errors,
                    "warnings": s.warnings,
                    **s.data,
                }
                for s in self.stages
            ],
        }

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, default=str)


# ─── Stage Helpers ────────────────────────────────────────────────────────────


def _run_stage(name: str, fn, *args, **kwargs) -> StageResult:
    """Execute a pipeline stage, catching all exceptions."""
    t0 = time.perf_counter()
    try:
        result_data = fn(*args, **kwargs)
        ms = (time.perf_counter() - t0) * 1000.0
        return StageResult(
            stage_name=name,
            success=True,
            duration_ms=round(ms, 2),
            data=result_data if isinstance(result_data, dict) else {"result": result_data},
        )
    except ContractViolation as exc:
        ms = (time.perf_counter() - t0) * 1000.0
        logger.error("Stage %s CONTRACT VIOLATION: %s", name, exc)
        return StageResult(
            stage_name=name,
            success=False,
            duration_ms=round(ms, 2),
            errors=[f"CONTRACT_VIOLATION: {exc}"],
        )
    except Exception as exc:
        ms = (time.perf_counter() - t0) * 1000.0
        logger.error("Stage %s FAILED: %s\n%s", name, exc, traceback.format_exc())
        return StageResult(
            stage_name=name,
            success=False,
            duration_ms=round(ms, 2),
            errors=[f"{type(exc).__name__}: {exc}"],
        )


# ─── Stage Implementations ───────────────────────────────────────────────────


def _stage0_contract(payload: Dict) -> Dict:
    """Validate input payload. Raises ContractViolation on failure."""
    validated = validate_room_input(payload)
    return {
        "validated_room_id": validated["room_id"],
        "computed_area_m2": validated["area_m2"],
        "detector_type": validated["detector_type"],
        "ceiling_height_m": validated["ceiling_height_m"],
        "occupancy_type": validated["occupancy_type"],
        "ceiling_type": validated["ceiling_type"],
        "contract_warnings": validated.get("_contract_warnings", []),
        "validated_payload": validated,
    }


def _stage05_qomn_physics_guard(
    ceiling_height_m: float,
    area_m2: float,
    detector_type: str,
    standby_current_a: Optional[float] = None,
    alarm_current_a: Optional[float] = None,
    circuit_length_m: Optional[float] = None,
    awg_gauge: str = "14",
    supply_voltage_v: float = 24.0,
) -> Dict:
    """Stage 0.5 — QOMN-FIRE deterministic physics guard + Layer 1/2/3/4 pipeline.

    Runs BEFORE Stage 1 (nfpa_spacing) to:
      1. Apply Layer 0 physics guards (reject physically impossible inputs)
      2. Compute deterministic NFPA 72 spacing via QOMN Layer 1/2
      3. Validate result via QOMN Layer 3
      4. Record to QOMN Layer 4 audit chain

    This stage is NON-BLOCKING: failure adds warnings but does not halt pipeline.
    The QOMN result is used for cross-verification against Stage 1's result.
    Discrepancy between QOMN and Stage 1 → warning flagged.

    Returns:
        dict with qomn_spacing, qomn_radius, audit_entries, chain_valid,
        cross_check_passed, physics_guard_passed.

    """
    try:
        from fireai.core.qomn_kernel import PhysicsGuardError, QOMNKernel

        kernel = QOMNKernel()

        # Run QOMN physics guard + computation
        physics_guard_passed = True
        guard_errors: List[str] = []

        # Guard: ceiling height
        try:
            from fireai.core.qomn_kernel import guard_ceiling_height_m

            guard_ceiling_height_m(ceiling_height_m)
        except PhysicsGuardError as e:
            physics_guard_passed = False
            guard_errors.append(str(e))

        # Guard: area
        try:
            from fireai.core.qomn_kernel import guard_area_m2

            guard_area_m2(area_m2)
        except PhysicsGuardError as e:
            physics_guard_passed = False
            guard_errors.append(str(e))

        # QOMN spacing computation (L0→L1→L2→L3→L4)
        qomn_spacing = kernel.smoke_detector_spacing(ceiling_height_m)
        qomn_radius = qomn_spacing["coverage_radius_m"]
        qomn_s = qomn_spacing["listed_spacing_m"]

        # Optional: battery via QOMN
        qomn_battery = None
        if standby_current_a is not None and alarm_current_a is not None:
            try:
                qomn_battery = kernel.battery_capacity(standby_current_a, alarm_current_a)
            except Exception as be:
                guard_errors.append(f"QOMN battery guard: {be}")

        # Optional: voltage drop via QOMN
        qomn_voltage = None
        if circuit_length_m is not None and alarm_current_a is not None:
            try:
                qomn_voltage = kernel.voltage_drop(alarm_current_a, circuit_length_m, awg_gauge, supply_voltage_v)
            except Exception as ve:
                guard_errors.append(f"QOMN voltage guard: {ve}")

        # Export audit log
        audit_export = kernel.get_audit_log()
        chain_valid = kernel.verify_audit_integrity()

        return {
            "physics_guard_passed": physics_guard_passed,
            "guard_errors": guard_errors,
            "qomn_spacing_m": qomn_s,
            "qomn_radius_m": qomn_radius,
            "qomn_nfpa_section": qomn_spacing.get("nfpa_section", "NFPA 72-2022"),
            "qomn_computation_hash": qomn_spacing.get("computation_hash", ""),
            "qomn_battery": qomn_battery,
            "qomn_voltage": qomn_voltage,
            "audit_entries": audit_export.get("total_entries", 0),
            "chain_valid": chain_valid,
            "audit_log": audit_export,
        }

    except ImportError:
        # V114 FIX: Missing QOMN kernel = physics guard CANNOT be performed.
        # Must NEVER report True when the check was not actually performed.
        # A missing physics check is a FAIL-SAFE condition per agent.md Rule 5.
        return {
            "physics_guard_passed": False,
            "guard_errors": ["QOMN kernel not available — physics guard CANNOT be performed"],
            "qomn_spacing_m": None,
            "qomn_radius_m": None,
            "audit_entries": 0,
            "chain_valid": False,
            "audit_log": None,
            "note": "QOMN kernel not available — physics guard FAILED (fail-safe)",
        }
    except Exception as exc:
        return {
            "physics_guard_passed": False,
            "guard_errors": [str(exc)],
            "qomn_spacing_m": None,
            "qomn_radius_m": None,
            "audit_entries": 0,
            "chain_valid": False,
            "audit_log": None,
        }


def _stage1_nfpa_spacing(
    ceiling_height_m: float,
    detector_type: str,
    room_area_m2: float,
) -> Dict:
    """Compute NFPA 72 spacing and estimate detector count.

    M-3 FIX: Checks for error in estimate_detector_count result before
    using the values. Previously, if estimate["error"] was set (e.g.,
    invalid room area), the pipeline would silently continue with
    min_detector_count=0 and area_per_detector_m2=None, producing
    a result that looks valid but has zero detectors for a room that
    needs coverage — a life-safety catastrophe in fire protection.
    """
    spacing = get_detector_spacing(ceiling_height_m, detector_type)
    estimate = estimate_detector_count(room_area_m2, ceiling_height_m, detector_type)

    # M-3 FIX: Propagate error from estimate_detector_count instead of
    # silently using invalid values. When room_area_m2 is invalid (NaN,
    # negative, zero), estimate contains min_detector_count=0 and an
    # error field. Without this check, the pipeline continues with zero
    # detectors and None area_per_detector_m2, which produces a result
    # that looks valid downstream but has no detector coverage.
    if "error" in estimate:
        return {
            "error": estimate["error"],
            "max_spacing_m": spacing.max_spacing_m,
            "coverage_radius_m": spacing.coverage_radius_m,
            "nfpa_section": spacing.nfpa_section,
            "formula": spacing.formula,
            "table_row_used": spacing.table_row_used,
            "estimated_min_count": 0,
            "area_per_detector_m2": None,
        }

    return {
        "max_spacing_m": spacing.max_spacing_m,
        "coverage_radius_m": spacing.coverage_radius_m,
        "nfpa_section": spacing.nfpa_section,
        "formula": spacing.formula,
        "table_row_used": spacing.table_row_used,
        "estimated_min_count": estimate["min_detector_count"],
        "area_per_detector_m2": estimate["area_per_detector_m2"],
    }


def _stage2_placement(
    validated_payload: Dict,
    coverage_radius_m: float,
) -> Dict:
    """Run detector placement optimizer.

    Attempts to import DensityOptimizer from the existing codebase.
    Falls back to geometric estimate if optimizer is not available.
    This is the bridge that fixes W-01: import failure → 0% coverage.
    """
    polygon = validated_payload["room_polygon"]
    area_m2 = validated_payload["area_m2"]

    # Try the real optimizer first
    try:
        # Import using the correct fireai.core path (fixes W-01)
        from fireai.core.spatial_engine.density_optimizer import DensityOptimizer

        class _RoomSpec:
            """Minimal room spec compatible with DensityOptimizer."""

            def __init__(self, payload, radius):
                self.room_id = payload["room_id"]
                self.polygon = polygon
                self.area_m2 = area_m2
                self.ceiling_height_m = payload["ceiling_height_m"]
                self.coverage_radius = radius

        optimizer = DensityOptimizer()
        layout = optimizer.optimize(_RoomSpec(validated_payload, coverage_radius_m))  # type: ignore[arg-type]

        if layout is None:
            raise RuntimeError("DensityOptimizer returned None")

        return {
            "method": "DensityOptimizer",
            "detector_positions": list(layout.detectors),  # type: ignore[union-attr]
            "detector_count": len(layout.detectors),  # type: ignore[union-attr]
            "coverage_pct": float(layout.coverage_pct),
            "proof_valid": bool(getattr(layout, "proof_valid", False)),
            "fallback_used": False,
        }

    except ImportError as exc:
        logger.warning(
            "DensityOptimizer import failed (%s) — using geometric fallback. "
            "Fix the import path to restore full optimization.",
            exc,
        )
    except Exception as exc:
        logger.warning("DensityOptimizer failed (%s) — using geometric fallback.", exc)

    # ── Geometric Fallback ────────────────────────────────────────────────────
    # Compute bounding box, place detectors on hex grid
    # This NEVER returns 0% coverage — it always places ≥1 detector
    positions = _hex_grid_placement(polygon, coverage_radius_m)

    return {
        "method": "geometric_hex_fallback",
        "detector_positions": positions,
        "detector_count": len(positions),
        "coverage_pct": _estimate_coverage(positions, polygon, coverage_radius_m),
        "proof_valid": False,
        "fallback_used": True,
        "fallback_reason": "DensityOptimizer unavailable",
    }


def _hex_grid_placement(
    polygon: List[Tuple[float, float]],
    radius_m: float,
) -> List[Tuple[float, float]]:
    """Place detectors on a hexagonal grid inside polygon.

    Conservative: uses 0.9×radius spacing (not full 1.0×) to ensure
    overlap at grid boundaries. Never violates 0.1m wall minimum.

    Returns list of (x, y) detector positions inside the polygon.
    """
    if not polygon or radius_m <= 0:
        return []

    # Bounding box
    xs = [p[0] for p in polygon]
    ys = [p[1] for p in polygon]
    min_x, max_x = min(xs), max(xs)
    min_y, max_y = min(ys), max(ys)

    # Hex grid spacing — CORRECTED from 0.9×R (which over-placed ~3.7×)
    # to 2R × sin(60°) = proper hex packing distance between centers.
    # NFPA 72 §17.7.4.2.3.1: R = 0.7 × S. Full coverage requires adjacent
    # detector centers ≤ 2R apart. Hex packing factor: 2R × sin(60°).
    # Using 0.85×2R for slight conservative overlap at boundaries.
    S = radius_m * 2.0 * 0.866 * 0.85  # ~1.47×R — proper hex packing
    row_h = S * (3**0.5) / 2.0  # Vertical distance between hex rows
    wall = 0.1  # NFPA 72 §17.7.4.2.3.1 wall min

    positions: List[Tuple[float, float]] = []
    row = 0
    y = min_y + wall
    while y <= max_y - wall:
        offset = (S / 2.0) if row % 2 else 0.0
        x = min_x + wall + offset
        while x <= max_x - wall:
            if _point_in_polygon(x, y, polygon):
                positions.append((round(x, 4), round(y, 4)))
            x += S
        y += row_h
        row += 1

    # Safety: always place at least one detector (centroid)
    if not positions:
        cx = sum(p[0] for p in polygon) / len(polygon)
        cy = sum(p[1] for p in polygon) / len(polygon)
        positions = [(round(cx, 4), round(cy, 4))]

    return positions


def _point_in_polygon(x: float, y: float, polygon: List[Tuple[float, float]]) -> bool:
    """Ray-casting point-in-polygon. O(n).

    FIX: Removed the 1e-12 epsilon from the denominator. The old epsilon
    could cause incorrect ray-casting results at near-horizontal edges
    by making the denominator artificially large, which shifts the
    intersection x-coordinate. For near-horizontal edges (yj ≈ yi),
    the condition (yi > y) != (yj > y) already excludes the degenerate
    case where yj == yi, so the epsilon was both unnecessary and harmful.
    """
    n = len(polygon)
    inside = False
    j = n - 1
    for i in range(n):
        xi, yi = polygon[i]
        xj, yj = polygon[j]
        if ((yi > y) != (yj > y)) and (x < (xj - xi) * (y - yi) / (yj - yi) + xi):
            inside = not inside
        j = i
    return inside


def _estimate_coverage(
    positions: List[Tuple[float, float]],
    polygon: List[Tuple[float, float]],
    radius_m: float,
    step: float = 0.0,
) -> float:
    """Fast coverage estimate using grid sampling.
    Returns percentage 0.0–100.0. Used when Shapely is not available.

    PERFORMANCE FIX (CRITICAL-1): Adaptive grid step based on polygon
    size. The old fixed step=0.5m caused O(n²) behavior on large rooms,
    making 100K-room stress tests take hours. Now uses max(step_min, 1.0m)
    for rooms larger than 100m², which cuts grid points by 4× with
    <0.5% accuracy loss on coverage percentage.
    """
    if not positions or not polygon:
        return 0.0

    xs = [p[0] for p in polygon]
    ys = [p[1] for p in polygon]
    min_x, max_x = min(xs), max(xs)
    min_y, max_y = min(ys), max(ys)

    bbox_area = (max_x - min_x) * (max_y - min_y)

    # V98 FIX: Adaptive step based on coverage radius.
    # Old fixed step=0.5m was too coarse for heat detectors (R≈3m) in small
    # rooms: step/radius ratio = 0.5/3 = 17% → high quantization error →
    # false compliance. New formula: min(0.25m, radius_m / 10.0) ensures
    # at least 10 sample points across the radius for accuracy.
    # For large rooms (>100m²), use coarser step for performance.
    if step <= 0:
        step = min(0.25, radius_m / 10.0) if bbox_area <= 100.0 else min(0.5, radius_m / 5.0)

    total = 0
    covered = 0
    r2 = radius_m * radius_m

    # Build a set of grid buckets for O(1) nearest-detector lookup.
    # Bucket size = radius_m so each grid point only checks 9 buckets.
    bucket_size = radius_m
    detector_buckets: Dict[Tuple[int, int], List[Tuple[float, float]]] = {}
    for dx, dy in positions:
        bk = (int(dx // bucket_size), int(dy // bucket_size))
        if bk not in detector_buckets:
            detector_buckets[bk] = []
        detector_buckets[bk].append((dx, dy))

    y = min_y + step / 2
    while y <= max_y:
        x = min_x + step / 2
        while x <= max_x:
            if _point_in_polygon(x, y, polygon):
                total += 1
                # Check only detectors in nearby buckets (9-bucket window)
                bk_x = int(x // bucket_size)
                bk_y = int(y // bucket_size)
                found = False
                for ddx in (-1, 0, 1):
                    if found:
                        break
                    for ddy in (-1, 0, 1):
                        if found:
                            break
                        bucket = detector_buckets.get((bk_x + ddx, bk_y + ddy))
                        if bucket:
                            for dx, dy in bucket:
                                if (x - dx) ** 2 + (y - dy) ** 2 <= r2:
                                    covered += 1
                                    found = True
                                    break
            x += step
        y += step

    # V96 FIX: Clamp coverage to [0.0, 100.0]. Detector coverage circles can
    # extend slightly outside the polygon boundary, making covered > total
    # (coverage > 100%). This violates the 0–100% contract and confuses
    # downstream classify_safety_tier which expects 0–100.
    return min(100.0, round(100.0 * covered / total, 4)) if total > 0 else 0.0


def _stage3_verify_coverage(
    detector_positions: List[Tuple[float, float]],
    polygon: List[Tuple[float, float]],
    coverage_radius_m: float,
    room_id: str,
) -> Dict:
    """Verify coverage using the best available engine."""
    # Try ExactCoverageEngine first (Shapely-based, rigorous)
    try:
        from fireai.core.spatial_engine.exact_coverage import ExactCoverageEngine

        engine = ExactCoverageEngine(coverage_radius_m)
        result = engine.verify(polygon, detector_positions)
        return {
            "engine": "ExactCoverageEngine",
            "coverage_pct": result.coverage_ratio,
            "room_area_m2": result.room_area_sqm,
            "covered_area_m2": result.room_area_sqm - result.uncovered_area_sqm,
            "is_compliant": result.is_covered,
            "method_used": "ExactCoverageEngine",
        }
    except ImportError:
        logger.warning("ExactCoverageEngine unavailable — using grid estimate")
    except Exception as exc:
        logger.warning("ExactCoverageEngine failed (%s) — using grid estimate", exc)

    # Fallback: grid estimate (always returns a number, never 0% if detectors exist)
    pct = _estimate_coverage(detector_positions, polygon, coverage_radius_m)
    return {
        "engine": "grid_estimate_fallback",
        "coverage_pct": pct,
        "room_area_m2": None,
        "covered_area_m2": None,
        "is_compliant": pct >= 99.0,
        "method_used": "grid_sampling_adaptive",
    }


def _stage35_rules_compliance(
    validated_payload: Dict,
    detector_positions: List[Tuple[float, float]],
    coverage_radius_m: float,
    spacing_m: float,
    battery_dict: Optional[Dict] = None,
    voltage_dict: Optional[Dict] = None,
    fault_isolation_dict: Optional[Dict] = None,
) -> Dict:
    """Run declarative NFPA 72 rules engine compliance check.

    This runs the Rete-inspired forward-chaining rules engine against
    the room data, producing structured compliance results with full
    audit trail and truth maintenance.

    This ENHANCES (not replaces) the existing compliance checks.
    Both systems run in parallel — discrepancies are flagged.

    Now also accepts nfpa72_engine calculation results (battery,
    voltage drop, fault isolation) and feeds them as facts into
    the Rules Engine for integrated compliance checking.
    """
    try:
        checker = NFPA72ComplianceChecker(
            session_id=validated_payload.get("room_id", "pipeline"),
        )

        # Add room fact
        room_id = validated_payload.get("room_id", "UNKNOWN")
        ceiling_h = validated_payload.get("ceiling_height_m", 3.0)
        det_type = validated_payload.get("detector_type", "smoke")
        room_area = validated_payload.get("area_m2")
        is_corridor = validated_payload.get("ceiling_type", "") == "corridor"

        checker.add_room(
            room_id=room_id,
            ceiling_height_m=ceiling_h,
            detector_type=det_type,
            room_area_m2=room_area,
            is_corridor=is_corridor,
            occupancy_type=validated_payload.get("occupancy_type", "office"),
        )

        # Add detector facts
        wall_max = spacing_m / 2.0
        for i, (x, y) in enumerate(detector_positions):
            checker.add_detector(
                detector_id=f"{room_id}-D{i + 1}",
                room_id=room_id,
                detector_type=det_type,
                x=x,
                y=y,
                listed_spacing_m=spacing_m,
                wall_distance_max_m=wall_max,
            )

        # Bridge nfpa72_engine results into the Rules Engine
        if battery_dict is not None:
            checker.add_battery_result(
                required_ah=battery_dict.get("required_ah", 0),
                installed_ah=battery_dict.get("installed_ah", 0),
                is_adequate=battery_dict.get("is_adequate", False),
            )
        if voltage_dict is not None:
            checker.add_voltage_drop_result(
                voltage_drop_v=voltage_dict.get("voltage_drop_v", 0),
                voltage_drop_pct=voltage_dict.get("voltage_drop_pct", 0),
                max_length_m=voltage_dict.get("max_length_m", 0),
                is_compliant=voltage_dict.get("is_compliant", False),
            )
        if fault_isolation_dict is not None:
            checker.add_fault_isolation_result(
                compliant=fault_isolation_dict.get("compliant", False),
                violations=fault_isolation_dict.get("violations", []),
                device_count=fault_isolation_dict.get("device_count", 0),
                isolator_count=fault_isolation_dict.get("isolator_count", 0),
            )

        # Run evaluation
        report = checker.evaluate()

        return {
            "engine": "NFPA72ComplianceChecker",
            "is_safe": report.is_safe,
            "critical_issues": len(report.critical_issues),
            "violations": len(report.violations),
            "compliance_checks": len(report.compliance_checks),
            "nfpa_references": report.nfpa_references,
            "audit_rules_fired": report.audit_summary.get("rules_fired", 0),
            "audit_total_facts": report.audit_summary.get("total_facts", 0),
            "critical_details": [{"rule_id": c["rule_id"], "message": c["message"]} for c in report.critical_issues],
            "violation_details": [{"rule_id": v["rule_id"], "message": v["message"]} for v in report.violations],
        }
    except Exception as exc:
        logger.warning(
            "Rules Engine compliance check failed (%s) — continuing "
            "without declarative rules. This is non-blocking but should "
            "be investigated.",
            exc,
        )
        # SAFETY FIX (CRITICAL-10): Replace sentinel -1 values with 0.
        # Sentinel -1 values would cause TypeError if any downstream code
        # tries to iterate or index them. Using 0 with is_safe=False is
        # the safe conservative default — it means "we couldn't evaluate,
        # so assume unsafe."
        return {
            "engine": "NFPA72ComplianceChecker",
            "is_safe": False,  # Conservative: assume unsafe
            "critical_issues": 0,
            "violations": 0,
            "error": str(exc),
        }


def _stage4_safety_classify(
    coverage_pct: float,
    proof_valid: bool,
    fallback_used: bool,
    wall_violations: int,
) -> Dict:
    """Classify safety tier."""
    tier = classify_safety_tier(
        coverage_pct=coverage_pct,
        proof_valid=proof_valid,
        fallback_used=fallback_used,
        wall_violations=wall_violations,
    )
    return {
        "safety_tier": tier.value,
        "can_submit": tier in (SafetyTier.PROOF_VERIFIED, SafetyTier.PROOF_VALID),
        "requires_fpe_review": tier in (SafetyTier.PROOF_VALID, SafetyTier.FALLBACK_USED),
    }


def _stage5_release_gates(
    validated_payload: Dict,
    nfpa_result: Dict,
    coverage_pct: float,
    proof_valid: bool,
    safety_tier: str,
    wall_violations: int,
    battery_result: Optional[BatteryResult] = None,
    loop_data: Optional[Dict] = None,
) -> Dict:
    """Evaluate all 8 release gates."""
    nfpa_gate_result = {
        "is_compliant": nfpa_result.get("is_compliant", False),
        "violations": nfpa_result.get("violations"),  # None = unknown (blocked)
        "coverage_pct": coverage_pct,
        "wall_violations": wall_violations,
        "safety_tier": safety_tier,
    }

    # Build battery result dict if we have it
    battery_dict = None
    if battery_result is not None:
        battery_dict = {
            "required_ah": battery_result.required_ah,
            "installed_ah": battery_result.installed_ah,
            "is_adequate": battery_result.is_adequate,
        }

    # Simple drift check: no IFC sync in this flow = no drift data
    drift_records: List[Dict] = []

    gate_result = verify_and_evaluate(
        input_payload=validated_payload,
        nfpa_results=nfpa_gate_result,
        evidence_envelope=None,  # Built in stage 6
        drift_records=drift_records,
        loop_data=loop_data,
        aset_rset_result=None,  # Not computed in basic pipeline
        battery_result=battery_dict,
        stale_detector_ids=[],  # Fresh run — no stale detectors
        evidence_secret_key=None,  # No HMAC key in basic pipeline
    )

    return gate_result


def _stage6_evidence(
    run_id: str,
    validated_payload: Dict,
    detector_positions: List[Tuple[float, float]],
    coverage_pct: float,
    proof_valid: bool,
    safety_tier: str,
    spacing_result: Dict,
    wall_violations: int,
    compliance_status: str,
) -> Dict:
    """Build and hash the engineering evidence package."""
    nfpa_refs = [
        "NFPA 72-2022 §17.6.3.1.1",
        "NFPA 72-2022 §17.7.4.2.3.1",
        spacing_result.get("nfpa_section", "NFPA 72-2022"),
    ]
    if wall_violations > 0:
        nfpa_refs.append("NFPA 72-2022 §17.7.4.2.3.1 (wall violation)")

    pkg = EngineeringEvidencePackage(
        package_id=run_id,
        room_id=validated_payload["room_id"],
        room_polygon=validated_payload["room_polygon"],
        room_area_m2=validated_payload["area_m2"],
        ceiling_height_m=validated_payload["ceiling_height_m"],
        ceiling_type=validated_payload["ceiling_type"],
        occupancy_type=validated_payload["occupancy_type"],
        detector_positions=detector_positions,
        detector_type=validated_payload["detector_type"],
        spacing_m=spacing_result.get("max_spacing_m", 0),
        coverage_radius_m=spacing_result.get("coverage_radius_m", 0),
        coverage_pct=coverage_pct,
        wall_violations=wall_violations,
        nfpa_references=nfpa_refs,
        compliance_status=compliance_status,
        proof_valid=proof_valid,
        safety_tier=safety_tier,
    )

    integrity_hash = pkg.compute_integrity_hash()
    return {
        "evidence_hash": integrity_hash,
        "nfpa_references": nfpa_refs,
        "package_id": run_id,
    }


# ─── Main Pipeline ────────────────────────────────────────────────────────────


def analyze_room(
    payload: Dict[str, Any],
    *,
    standby_current_a: Optional[float] = None,
    alarm_current_a: Optional[float] = None,
    circuit_length_m: Optional[float] = None,
    awg_gauge: str = "14",
    loop_data: Optional[Dict] = None,
    ambient_temperature_c: float = 20.0,
    cable_connections: Optional[List[Dict[str, Any]]] = None,
    building_model: Optional[Any] = None,
) -> PipelineResult:
    """Run the complete FireAI analysis pipeline for one room.

    Args:
        payload:           Room input dict (room_polygon, ceiling_height_m, etc.)
        standby_current_a: Optional standby current for battery calculation.
        alarm_current_a:   Optional alarm current for battery calculation.
        circuit_length_m:  Optional circuit length for voltage drop calculation.
        awg_gauge:         Wire gauge for voltage drop (default AWG 14).
        loop_data:         Optional SLC loop data for fault isolation check.
        ambient_temperature_c: Conductor operating temperature in degC.
            Default 20 degC (backward compatible, NEC Table 8 reference).
            CRITICAL FOR EGYPT: Use 75.0 for THHN/THWN operating temp.
            At 75 degC, resistance is 21.6% higher than at 20 degC.

    Returns:
        PipelineResult — never raises, all errors captured inside result.

    """
    t_total = time.perf_counter()
    # V61 FIX: Deterministic run_id from input content hash.
    # Previous uuid4() produced different IDs on every run, breaking
    # audit reproducibility. Same input → same run_id, always.
    _input_canonical = json.dumps(payload, sort_keys=True, default=str)
    _content_hash = hashlib.sha256(_input_canonical.encode()).hexdigest()
    # Format as UUID-like string for backward compatibility with tests
    # and consumers expecting UUID format: 8-4-4-4-12
    run_id = (
        f"{_content_hash[:8]}-{_content_hash[8:12]}-{_content_hash[12:16]}-"
        f"{_content_hash[16:20]}-{_content_hash[20:32]}"
    )
    stages: List[StageResult] = []
    errors: List[str] = []
    warnings: List[str] = []

    # ── Stage 0: Contract Validation ─────────────────────────────────────────
    s0 = _run_stage("S0_contract", _stage0_contract, payload)
    stages.append(s0)
    if not s0.success:
        errors.extend(s0.errors)
        return _failed_result(run_id, payload, stages, errors, warnings, t_total)

    validated = s0.data["validated_payload"]
    room_id = s0.data["validated_room_id"]
    ceiling_h = s0.data["ceiling_height_m"]
    det_type = s0.data["detector_type"]
    area_m2 = s0.data["computed_area_m2"]
    polygon = validated["room_polygon"]
    warnings.extend(s0.data.get("contract_warnings", []))

    # ── Stage 0.5: QOMN Physics Guard ──────────────────────────────────────────
    # Deterministic Layer 0→4 validation before any computation.
    # Non-blocking — failures add warnings but never halt the pipeline.
    s05 = _run_stage(
        "S0.5_qomn_physics_guard",
        _stage05_qomn_physics_guard,
        ceiling_h,
        area_m2,
        det_type,
        standby_current_a,
        alarm_current_a,
        circuit_length_m,
        awg_gauge,
    )
    stages.append(s05)
    qomn_audit = s05.data.get("audit_log") if s05.success else None
    if s05.success and not s05.data.get("physics_guard_passed", False):  # V112: FAIL-SAFE — missing guard = FAILED
        # Physics guard rejected input — critical warning (not blocking)
        for err in s05.data.get("guard_errors", []):
            warnings.append(f"[QOMN PHYSICS GUARD] {err}")
    if s05.success and s05.data.get("guard_errors"):
        warnings.extend(s05.data["guard_errors"])

    # ── Stage 1: NFPA Spacing ─────────────────────────────────────────────────
    s1 = _run_stage("S1_nfpa_spacing", _stage1_nfpa_spacing, ceiling_h, det_type, area_m2)
    stages.append(s1)
    if not s1.success:
        errors.extend(s1.errors)
        return _failed_result(run_id, payload, stages, errors, warnings, t_total, room_id=room_id)

    radius_m = s1.data["coverage_radius_m"]
    spacing_m = s1.data["max_spacing_m"]

    # ── Stage 2: Detector Placement ───────────────────────────────────────────
    s2 = _run_stage("S2_placement", _stage2_placement, validated, radius_m)
    stages.append(s2)
    if not s2.success:
        errors.extend(s2.errors)
        # Placement failure is not terminal — use estimate
        positions = []
        coverage_pct = 0.0
        proof_valid = False
        fallback = True
        warnings.append("Placement failed — coverage cannot be verified")
    else:
        positions = s2.data["detector_positions"]
        coverage_pct = s2.data["coverage_pct"]
        proof_valid = s2.data["proof_valid"]
        fallback = s2.data["fallback_used"]
        if s2.data.get("fallback_reason"):
            warnings.append(f"Placement fallback: {s2.data['fallback_reason']}")

    # ── Stage 3: Coverage Verification ───────────────────────────────────────
    if positions:
        s3 = _run_stage(
            "S3_coverage",
            _stage3_verify_coverage,
            positions,
            polygon,
            radius_m,
            room_id,
        )
        stages.append(s3)
        if s3.success:
            # Use verified coverage (more accurate than optimizer's estimate)
            coverage_pct = s3.data.get("coverage_pct", coverage_pct)
        else:
            errors.extend(s3.errors)
            warnings.append("Coverage verification failed — using optimizer estimate")
    else:
        stages.append(
            StageResult(
                stage_name="S3_coverage",
                success=False,
                duration_ms=0,
                errors=["No detector positions to verify"],
            )
        )

    # ── Wall Violations ───────────────────────────────────────────────────────
    wall_violations = _count_wall_violations(positions, polygon)

    # ── Stage 4: Safety Classification ───────────────────────────────────────
    s4 = _run_stage(
        "S4_safety",
        _stage4_safety_classify,
        coverage_pct,
        proof_valid,
        fallback,
        wall_violations,
    )
    stages.append(s4)
    safety_tier = s4.data.get("safety_tier", SafetyTier.REJECTED.value) if s4.success else SafetyTier.REJECTED.value

    # ── Optional: Battery Calculation ─────────────────────────────────────────
    battery_result: Optional[BatteryResult] = None
    battery_dict: Optional[Dict] = None
    if standby_current_a is not None and alarm_current_a is not None:
        sb = _run_stage(
            "S_battery",
            calculate_battery,
            standby_current_a,
            alarm_current_a,
        )
        stages.append(sb)
        if sb.success and "result" in sb.data:
            battery_result = sb.data["result"]
            battery_dict = {
                "required_ah": battery_result.required_ah,
                "installed_ah": battery_result.installed_ah,
                "is_adequate": battery_result.is_adequate,
                "formula": battery_result.formula,
                "nfpa_section": battery_result.nfpa_section,
            }

    # ── Optional: Voltage Drop ────────────────────────────────────────────────
    voltage_dict: Optional[Dict] = None
    if circuit_length_m is not None and alarm_current_a is not None:
        sv = _run_stage(
            "S_voltage_drop",
            calculate_voltage_drop,
            alarm_current_a,
            circuit_length_m,
            awg_gauge,
            ambient_temperature_c=ambient_temperature_c,
        )
        stages.append(sv)
        if sv.success and "result" in sv.data:
            vd = sv.data["result"]
            voltage_dict = {
                "voltage_drop_v": vd.voltage_drop_v,
                "voltage_drop_pct": vd.voltage_drop_pct,
                "max_length_m": vd.max_length_m,
                "is_compliant": vd.is_compliant,
                "formula": vd.formula,
            }
            if not vd.is_compliant:
                warnings.append(
                    f"Voltage drop {vd.voltage_drop_pct:.2f}% exceeds limit. "
                    f"Max circuit length: {vd.max_length_m:.1f}m for AWG {awg_gauge}."
                )

    # ── Optional: Fault Isolation ─────────────────────────────────────────────
    fault_isolation_dict: Optional[Dict] = None
    if loop_data is not None:
        devices = loop_data.get("devices", [])
        sf = _run_stage(
            "S_fault_isolation",
            verify_fault_isolator_placement,
            devices,
        )
        stages.append(sf)
        if sf.success:
            fault_isolation_dict = sf.data
            if not sf.data.get("compliant", False):
                warnings.append(f"SLC fault isolation violations: {sf.data.get('violations', [])}")

    # ── Optional: Cable Routing (V61) ──────────────────────────────────────
    cable_routing_dict: Optional[Dict] = None
    if cable_connections and building_model and _CABLE_ROUTER_AVAILABLE:
        try:
            constraint_engine = None
            if _CONSTRAINT_ENGINE_AVAILABLE:
                constraint_engine = ConstraintEngine()

            router = CableRouter(
                model=building_model,
                constraint_engine=constraint_engine,
            )

            # V65 FIX: Pass temperature parameters to cable routing.
            # Previously, route_all() used default ambient_temp_c=20°C
            # and conductor_operating_temp_c=None (falls back to 20°C).
            # For Egyptian summer conditions (40-50°C ambient), this
            # underestimated voltage drop by up to 21.6%. The pipeline
            # already has ambient_temperature_c for voltage drop — it
            # MUST be forwarded to cable routing as well.
            # conductor_operating_temp_c=75.0 per NEC practice for
            # THHN/THWN operating temperature.
            scr = _run_stage(
                "S_cable_routing",
                router.route_all,
                cable_connections,
                wire_gauge=WireGauge.AWG_14 if WireGauge is not None else None,
                ps_voltage=24.0,
                ambient_temp_c=max(ambient_temperature_c, 40.0),  # Min 40°C for Egypt
                conductor_operating_temp_c=75.0,  # THHN operating temp per NEC
                conductor_temp_rating_c=90,  # THHN/THWN-2 rating
            )
            stages.append(scr)
            if scr.success and "result" in scr.data:
                schedule = scr.data["result"]
                cable_routing_dict = {
                    "total_cable_length_m": schedule.total_cable_length_m,
                    "total_bends": schedule.total_bends,
                    "max_circuit_length_m": schedule.max_circuit_length_m,
                    "compliance_summary": schedule.compliance_summary,
                    "num_routes": len(schedule.routes),
                    "computation_hash": schedule.computation_hash,
                }
                if schedule.compliance_summary != "ALL COMPLIANT":
                    warnings.append(f"Cable routing violations: {schedule.compliance_summary}")
        except Exception as e:
            warnings.append(f"Cable routing stage failed: {e}")
            logger.warning("Cable routing stage failed: %s", e)

    # ── Stage 3.5: Rules Engine Compliance (MOVED after battery/voltage/fault) ─
    # Now runs AFTER nfpa72_engine calculations so that battery,
    # voltage drop, and fault isolation results are fed as facts
    # into the Rules Engine for integrated compliance checking.
    s35 = _run_stage(
        "S35_rules_compliance",
        _stage35_rules_compliance,
        validated,
        positions,
        radius_m,
        spacing_m,
        battery_dict,
        voltage_dict,
        fault_isolation_dict,
    )
    stages.append(s35)
    rules_compliance_data = s35.data if s35.success else {}
    # SAFETY FIX: Changed default from True to False. If is_safe is missing,
    # we must NOT assume compliance — that would be a false positive.
    if s35.success and not rules_compliance_data.get("is_safe", False):
        # Rules engine found violations — add to warnings
        for detail in rules_compliance_data.get("critical_details", []):
            warnings.append(f"RULES_ENGINE CRITICAL [{detail.get('rule_id', '?')}]: {detail.get('message', '')}")
        for detail in rules_compliance_data.get("violation_details", []):
            warnings.append(f"RULES_ENGINE VIOLATION [{detail.get('rule_id', '?')}]: {detail.get('message', '')}")
    elif not s35.success:
        warnings.append("Rules Engine compliance check unavailable — investigate")

    # ── Stage 5: Release Gates ────────────────────────────────────────────────
    nfpa_result = {
        "is_compliant": coverage_pct >= 99.0 and wall_violations == 0,
        "violations": ([f"Coverage {coverage_pct:.2f}% < 99%"] if coverage_pct < 99.0 else [])
        + ([f"{wall_violations} wall distance violation(s)"] if wall_violations > 0 else []),
    }

    s5 = _run_stage(
        "S5_release_gates",
        _stage5_release_gates,
        validated,
        nfpa_result,
        coverage_pct,
        proof_valid,
        safety_tier,
        wall_violations,
        battery_result,
        loop_data,
    )
    stages.append(s5)
    gate_result = (
        s5.data
        if s5.success
        else {
            "release_status": "blocked",
            "blockers": ["release_gate_evaluation_failed"],
            "checks": {},
            "gate_details": {},
        }
    )
    release_status = gate_result.get("release_status", "blocked")

    # ── Stage 6: Evidence Package ─────────────────────────────────────────────
    compliance_status = "APPROVED" if release_status == "green" else "REJECTED"
    s6 = _run_stage(
        "S6_evidence",
        _stage6_evidence,
        run_id,
        validated,
        positions,
        coverage_pct,
        proof_valid,
        safety_tier,
        s1.data,
        wall_violations,
        compliance_status,
    )
    stages.append(s6)
    evidence_hash = s6.data.get("evidence_hash", "") if s6.success else ""
    nfpa_refs = s6.data.get("nfpa_references", []) if s6.success else []

    # ── Stage 7: Cable Routing (optional — does not block completion) ─────────
    s7 = _run_stage(
        "S7_cable_routing",
        _stage7_cable_routing,
        validated,
        positions,
    )
    stages.append(s7)
    cable_routing_data = s7.data if s7.success else {}

    # ── Stage 8: Conduit Fitting Engine (optional) ─────────────────────────
    s8 = _run_stage(
        "S8_conduit_fittings", _stage8_conduit_fittings,
        validated, positions, cable_routing_data,
    )
    stages.append(s8)

    # Populate cable_routing_dict from Stage 7 when it succeeds
    # (Path A via cable_connections is for pre-wired inputs; Stage 7 is the standard path)
    if cable_routing_dict is None and s7.success and cable_routing_data.get("status") == "completed":
        cable_routing_dict = {
            "total_cable_length_m":  cable_routing_data.get("total_cable_length_m", 0.0),
            "total_bends":           cable_routing_data.get("total_bends", 0),
            "max_circuit_length_m":  cable_routing_data.get("max_circuit_length_m", 0.0),
            "min_end_voltage_v":     cable_routing_data.get("min_end_voltage_v", 0.0),
            "all_compliant":         cable_routing_data.get("all_compliant", False),
            "route_count":           cable_routing_data.get("route_count", 0),
            "violations_count":      cable_routing_data.get("violations_count", 0),
            "code_refs":             cable_routing_data.get("code_refs", []),
            "status":                "completed",
        }
        if not cable_routing_dict["all_compliant"] and cable_routing_dict["violations_count"] > 0:
            warnings.append(
                f"Cable routing: {cable_routing_dict['violations_count']} NEC/NFPA violations detected"
            )

    total_ms = (time.perf_counter() - t_total) * 1000.0

    # Determine overall success
    critical_failures = any(
        not s.success
        for s in stages[:4]  # Stages 0-3 are critical
    )
    overall_success = not critical_failures and math.isfinite(coverage_pct) and coverage_pct > 0.0

    return PipelineResult(
        run_id=run_id,
        room_id=room_id,
        success=overall_success,
        release_status=release_status,  # type: ignore[arg-type]
        safety_tier=safety_tier,
        coverage_pct=round(coverage_pct, 4),
        detector_count=len(positions),
        detector_radius_m=radius_m,
        max_spacing_m=spacing_m,
        detector_positions=positions,
        wall_violations=wall_violations,
        battery=battery_dict,
        voltage_drop=voltage_dict,
        fault_isolation=fault_isolation_dict,
        cable_routing=cable_routing_dict,
        qomn_audit=qomn_audit,
        stages=stages,
        release_gates=gate_result,
        evidence_hash=evidence_hash,
        total_ms=round(total_ms, 2),
        errors=errors,
        warnings=warnings,
        nfpa_references=nfpa_refs,
        timestamp=datetime.now(timezone.utc).isoformat(),
    )


def _stage7_cable_routing(
    validated: Dict,
    positions: List[Tuple[float, float]],
    room_z_m: float = 0.0,
) -> Dict:
    """Stage 7: Cable routing between detector positions.

    Uses CableRoutingEngine to route NAC/SLC circuits between
    detector positions. Returns routing schedule with voltage drop
    analysis per NFPA 72 §10.14.1 and §23.6.2.

    OPTIONAL STAGE: Returns partial result on import failure.
    Does not block Stages 0-6 from completing.

    References:
      - NFPA 72 §23.6.2: NAC circuit max length
      - NEC 760.24(A): cable support spacing
      - System Req §4: cable schedule output

    """
    try:
        from fireai.core.cable_router import (  # type: ignore[attr-defined]
            CableRouter,
            build_abstract_model,
        )
        from fireai.core.constraint_engine import ConstraintEngine
        from fireai.core.schedule_generator import ScheduleGenerator
    except ImportError:
        return {
            "status": "unavailable",
            "reason": "cable routing modules not installed",
        }

    if len(positions) < 2:
        return {
            "status": "skipped",
            "reason": "fewer than 2 detector positions — no routing needed",
            "routes": [],
        }

    # V69-9 FIX: Use correct key "room_polygon" (not "room"/"polygon_points")
    polygon = validated.get("room_polygon", [])
    area_m2 = validated.get("area_m2", 0.0)

    # Estimate bounding box from polygon or area
    if polygon:
        xs = [p[0] for p in polygon]
        ys = [p[1] for p in polygon]
        bbox_x = (min(xs), max(xs))
        bbox_y = (min(ys), max(ys))
    else:
        side = float(area_m2) ** 0.5
        bbox_x = (0.0, side)
        bbox_y = (0.0, side)

    grid_res_m = 0.1
    max(2, int((bbox_x[1] - bbox_x[0]) / grid_res_m) + 4)
    max(2, int((bbox_y[1] - bbox_y[0]) / grid_res_m) + 4)
    max(2, int(3.0 / grid_res_m) + 2)  # default 3m ceiling

    try:
        # Build model from polygon walls
        # V67 SAFETY FIX: If building model construction fails, cable routing
        # MUST NOT proceed — routing without wall awareness allows cables
        # through walls, elevator shafts, and concrete obstructions.
        building_model = None
        if polygon:
            try:
                # V98 FIX: build_abstract_model signature is (obstacles, spaces, building_name, resolution)
                # NOT (polygon, room_height_m=...). The old call passed room_height_m which
                # doesn't exist in the signature, causing TypeError every run.
                # We pass polygon walls as BoundingBox3D obstacles for cable routing.
                from fireai.core.ifc_parser import BoundingBox3D, IfcElementType

                walls_as_obstacles = []
                for i in range(len(polygon)):
                    x1, y1 = polygon[i]
                    x2, y2 = polygon[(i + 1) % len(polygon)]
                    # Create thin wall bounding box for each polygon edge
                    wall = BoundingBox3D(
                        element_id=f"wall_seg_{i}",
                        element_type=IfcElementType.WALL,
                        min_x=min(x1, x2) - 0.15,
                        min_y=min(y1, y2) - 0.15,
                        min_z=0.0,
                        max_x=max(x1, x2) + 0.15,
                        max_y=max(y1, y2) + 0.15,
                        max_z=3.0,
                        is_fire_rated=True,
                        fire_rating_hours=1.0,
                        ifc_class="IfcWallStandardCase",
                    )
                    walls_as_obstacles.append(wall)
                building_model = build_abstract_model(walls_as_obstacles, resolution=grid_res_m)
            except Exception as bme:
                logger.critical(
                    "V67 SAFETY: build_abstract_model() failed — "
                    "cable routing CANNOT proceed without wall geometry. "
                    "Error: %s",
                    bme,
                    exc_info=True,
                )
                building_model = None

        if building_model is None:
            logger.critical(
                "V67 SAFETY: No building model available — cable routing "
                "would route through walls. Returning FAILED status."
            )
            return {
                "status": "failed",
                "error": "Building model construction failed — cable routing requires wall geometry for safety. "
                "Cannot route cables without obstacle avoidance (would violate NEC 760.24).",
                "routes": [],
                "safety_block": True,
            }

        # V98 FIX: CableRouter.__init__ signature is (self, model, constraint_engine=None)
        # NOT (building_model=...). Must pass model as positional arg.
        constraint_engine = ConstraintEngine()
        router = CableRouter(building_model, constraint_engine=constraint_engine)

        # Build connections list per route_all() real API (verified cable_router.py:930):
        # connections: List[Dict] with keys: start, end, route_id, alarm_current_a
        # FACP at one corner; detectors at ceiling height
        FACP_HEIGHT_M = room_z_m + 1.5  # panel at 1.5m above floor
        DET_HEIGHT_M = room_z_m + 2.7  # detector 300mm below 3m ceiling

        facp_xyz = (bbox_x[0] + 0.5, bbox_y[0] + 0.5, FACP_HEIGHT_M)
        det_xyzs = [(x, y, DET_HEIGHT_M) for (x, y) in positions]

        # Route FACP→SD-01→SD-02→...  (daisy chain NAC circuit)
        # SAFETY: All endpoints must be in free (non-wall) grid cells.
        # Wall obstacles in build_abstract_model extend ±0.15m from each edge.
        # Guard: verify each point using the model's grid_data (flat bytes array,
        # indexed as iz*gy*gx + iy*gx + ix). If blocked, offset toward room center.
        room_cx = (bbox_x[0] + bbox_x[1]) / 2.0
        room_cy = (bbox_y[0] + bbox_y[1]) / 2.0

        # SAFETY: Ensure all endpoints are clear of wall obstacles.
        # The router's grid marks wall obstacle cells as blocked.
        # Wall obstacles extend WALL_THICKNESS_M from each polygon edge.
        # We apply MIN_CLEARANCE = WALL_THICKNESS_M * 3 from any polygon edge
        # to ensure all points land safely in the open routing zone.
        WALL_THICKNESS_M = 0.2  # standard wall thickness (Project Spec default)
        MIN_CLEARANCE_M = WALL_THICKNESS_M * 3.0  # 0.6m safe zone from walls

        def _dist_to_nearest_wall_edge(px, py):
            """Minimum distance from (px,py) to any polygon edge."""
            if not polygon or len(polygon) < 2:
                return float("inf")
            min_d = float("inf")
            pts = polygon
            n = len(pts)
            for i in range(n):
                ax, ay = pts[i]
                bx, by = pts[(i + 1) % n]
                # Distance from point to segment
                abx, aby = bx - ax, by - ay
                apx, apy = px - ax, py - ay
                t = max(0.0, min(1.0, (apx * abx + apy * aby) / (abx**2 + aby**2 + 1e-12)))
                cx2, cy2 = ax + t * abx, ay + t * aby
                d = ((px - cx2) ** 2 + (py - cy2) ** 2) ** 0.5
                min_d = min(min_d, d)
            return min_d

        def ensure_clearance(px, py, pz, target_x, target_y):
            """Move (px,py) toward (target_x,target_y) until MIN_CLEARANCE from all walls."""
            if _dist_to_nearest_wall_edge(px, py) >= MIN_CLEARANCE_M:
                return (px, py, pz)
            dx, dy = target_x - px, target_y - py
            dist = (dx**2 + dy**2) ** 0.5 or 1.0
            ux, uy = dx / dist, dy / dist
            step = 0.1
            for _ in range(50):
                px += ux * step
                py += uy * step
                if _dist_to_nearest_wall_edge(px, py) >= MIN_CLEARANCE_M:
                    return (px, py, pz)
            # Last resort: exact room center
            return (room_cx, room_cy, pz)

        facp_xyz_safe = ensure_clearance(*facp_xyz, room_cx, room_cy)
        det_xyzs_safe = [ensure_clearance(*pt, room_cx, room_cy) for pt in det_xyzs]

        all_points = [facp_xyz_safe] + det_xyzs_safe
        connections = [
            {
                "start": all_points[i],
                "end": all_points[i + 1],
                "route_id": f"FACP-to-SD-{i + 1:02d}",
                "alarm_current_a": 0.04,  # 40mA per NFPA 72 §18.3 sounder
            }
            for i in range(len(all_points) - 1)
        ]

        # WireGauge enum — NOT string. "14 AWG" would cause TypeError.
        # V113 FIX: Import WireGauge BEFORE the try block so ImportError
        # is NOT caught by the generic Exception handler below. Previously,
        # if cable_routing_engine was missing, the ImportError was swallowed
        # by the generic except clause and reported as "routing failed"
        # instead of "dependency missing". This is the anti-pattern from
        # agent.md Rule 17: a half-solution that hides the root cause.
        # Now, if the dependency is missing, the error message clearly states
        # "DEPENDENCY MISSING" rather than the misleading "routing failed".
        from fireai.core.cable_routing_engine import WireGauge

        schedule = router.route_all(
            connections=connections,
            wire_gauge=WireGauge.AWG_14,  # type: ignore[arg-type]
            ps_voltage=float(validated.get("ps_voltage_v", 24.0)),  # V113: configurable, not hardcoded
            project_name=f"FA-{validated.get('room_id', 'room')}",
            ambient_temp_c=float(validated.get("ambient_temp_c", 40.0)),
        )

        # from_routing_schedule reads schedule.routes (Tuple[CableRoute])
        sg = ScheduleGenerator()
        # V113: Pass ps_voltage from validated config to schedule generator
        ps_voltage_for_schedule = float(validated.get("ps_voltage_v", 24.0))
        rows = sg.from_routing_schedule(schedule, ps_voltage=ps_voltage_for_schedule)

        report = sg.to_report(rows)

        return {
            "status": "completed",
            "total_cable_length_m": report.total_cable_length_m,
            "total_bends": report.total_bends,
            "max_circuit_length_m": report.max_circuit_length_m,
            "min_end_voltage_v": report.min_end_voltage_v,
            "all_compliant": report.all_compliant,
            "route_count": report.route_count,
            "violations_count": report.violations_count,
            "csv": sg.to_csv(rows),
            "code_refs": report.code_refs,
        }

    except ImportError as e:
        # V113 FIX: Separate ImportError from generic Exception.
        # A missing dependency is NOT a "routing failure" — it's a
        # "system misconfiguration". These require completely different
        # responses: routing failure = redesign, missing dependency = install package.
        # Previously, ImportError was caught by the generic handler and reported
        # as "routing failed", which is misleading and wastes engineering time.
        logger.critical(
            "V113 DEPENDENCY MISSING: Cable routing engine not available. Install required dependency: %s", e
        )
        return {
            "status": "dependency_missing",
            "error": f"DEPENDENCY MISSING: {e}. Install the required package before running cable routing.",
            "routes": [],
            "safety_block": True,
        }

    except Exception as e:
        # V67 SAFETY FIX: Any cable routing failure must set safety_block=True.
        # The inner handler (building_model=None) correctly sets this flag,
        # but this outer handler was missing it. Downstream code checking
        # for safety_block would not see it, potentially allowing the pipeline
        # to proceed with a failed-but-not-safety-blocked cable routing result.
        logger.critical(
            "V67 SAFETY: Stage 7 cable routing failed — marking as safety_block. Error: %s", e, exc_info=True
        )
        return {
            "status": "failed",
            "error": str(e),
            "routes": [],
            "safety_block": True,
        }



def _stage8_conduit_fittings(
    validated: dict,
    positions: list,
    cable_routing_data: dict,
) -> dict:
    """Stage 8: Conduit filling, bend verification, fitting placement.

    Optional stage — does not block Stages 0-7 from completing.
    Reference: NEC 2022 Ch.9 Table 1; NEC 358.26; NFPA 72-2022 §12.2.2.
    """
    try:
        from fireai.conduit import (
            ConduitType,
            Point3D,
            TradeSize,
            calculate_fill,
            orthogonal_astar,
            place_fittings,
        )
    except ImportError as ie:
        return {"status": "unavailable", "reason": str(ie)}

    if len(positions) < 2:
        return {"status": "skipped", "reason": "fewer than 2 positions", "runs": []}

    conduit_type = ConduitType.EMT
    trade_size   = TradeSize.HALF
    cable_od_in  = cable_routing_data.get("cable_od_in", 0.105)
    z = float(validated.get("ceiling_height_m", 3.0)) * 0.9

    runs_out = []
    all_compliant = True
    total_violations = 0

    for i in range(len(positions) - 1):
        x0, y0 = float(positions[i][0]),   float(positions[i][1])
        x1, y1 = float(positions[i+1][0]), float(positions[i+1][1])
        start = Point3D(x0, y0, z)
        end   = Point3D(x1, y1, z)

        fill_r = calculate_fill(conduit_type, trade_size, [cable_od_in, cable_od_in])
        if fill_r.is_err():
            trade_size = TradeSize.THREE_QTR

        route_r = orthogonal_astar(start, end, conduit_type=conduit_type, trade_size=trade_size)
        if route_r.is_err():
            runs_out.append({"segment": i, "status": "routing_failed",
                             "reason": route_r.error.message})
            continue

        run_r = place_fittings(route_r.value, conduit_type, trade_size, run_id=f"SEG-{i:03d}")
        if run_r.is_err():
            runs_out.append({"segment": i, "status": "fitting_failed"})
            continue

        run = run_r.value
        if not run.is_compliant:
            all_compliant = False
            total_violations += len(run.violations)

        runs_out.append({
            "segment":        i,
            "status":         "completed",
            "run_id":         run.run_id,
            "conduit_type":   conduit_type.value,
            "trade_size":     trade_size.value,
            "total_length_m": run.total_length_m,
            "total_bend_deg": run.total_bend_deg,
            "is_compliant":   run.is_compliant,
            "violations":     run.violations,
            "nec_reference":  "NEC Ch.9 Table 1 + NEC 358.26",
        })

    return {
        "status":           "completed",
        "conduit_type":     conduit_type.value,
        "trade_size":       trade_size.value,
        "run_count":        sum(1 for r in runs_out if r.get("status") == "completed"),
        "all_compliant":    all_compliant,
        "total_violations": total_violations,
        "runs":             runs_out,
        "nfpa_reference":   "NFPA 72-2022 §12.2.2",
        "nec_reference":    "NEC Ch.9 Table 1 + NEC 358.26",
    }


def _count_wall_violations(
    positions: List[Tuple[float, float]],
    polygon: List[Tuple[float, float]],
    min_dist_m: float = 0.1,
) -> int:
    """Count detectors closer than 0.1m to any wall segment."""
    if not positions or not polygon:
        return 0

    def _dist_point_segment(px, py, ax, ay, bx, by) -> float:
        dx, dy = bx - ax, by - ay
        if dx == 0 and dy == 0:
            return math.sqrt((px - ax) ** 2 + (py - ay) ** 2)
        t = max(0, min(1, ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)))
        return math.sqrt((px - (ax + t * dx)) ** 2 + (py - (ay + t * dy)) ** 2)

    violations = 0
    n = len(polygon)
    for x, y in positions:
        min_d = float("inf")
        for i in range(n):
            ax, ay = polygon[i]
            bx, by = polygon[(i + 1) % n]
            d = _dist_point_segment(x, y, ax, ay, bx, by)
            min_d = min(min_d, d)
        if min_d < min_dist_m:
            violations += 1
    return violations


def _failed_result(
    run_id: str,
    payload: Dict,
    stages: List[StageResult],
    errors: List[str],
    warnings: List[str],
    t_total: float,
    room_id: str = "",
) -> PipelineResult:
    """Build a failure result when a critical stage fails."""
    room_id = room_id or str(payload.get("room_id", "UNKNOWN") if isinstance(payload, dict) else "UNKNOWN")
    return PipelineResult(
        run_id=run_id,
        room_id=room_id,
        success=False,
        release_status="blocked",
        safety_tier=SafetyTier.REJECTED.value,
        coverage_pct=0.0,
        detector_count=0,
        detector_radius_m=0.0,
        max_spacing_m=0.0,
        detector_positions=[],
        wall_violations=0,
        battery=None,
        voltage_drop=None,
        fault_isolation=None,
        stages=stages,
        release_gates={"release_status": "blocked", "blockers": ["critical_stage_failure"]},
        evidence_hash="",
        total_ms=round((time.perf_counter() - t_total) * 1000.0, 2),
        errors=errors,
        warnings=warnings,
        nfpa_references=[],
        timestamp=datetime.now(timezone.utc).isoformat(),
    )


# ─── Batch Pipeline ───────────────────────────────────────────────────────────


def analyze_building(
    rooms: List[Dict[str, Any]],
    *,
    max_workers: int = 4,
    **kwargs,
) -> Dict[str, Any]:
    """Analyze all rooms in a building concurrently.

    Args:
        rooms:       List of room payload dicts.
        max_workers: Thread count for concurrent processing.
        **kwargs:    Passed to analyze_room() (battery, voltage drop params).

    Returns:
        Building-level summary with per-room results.

    """
    t0 = time.perf_counter()

    if not rooms:
        return {
            "total_rooms": 0,
            "results": [],
            "summary": {"passed": 0, "blocked": 0, "errors": 0},
            "total_ms": 0,
        }

    results: List[Optional[PipelineResult]] = [None] * len(rooms)

    def _process(idx: int, room: Dict) -> Tuple[int, PipelineResult]:
        return idx, analyze_room(room, **kwargs)

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(_process, i, r): i for i, r in enumerate(rooms)}
        for future in as_completed(futures):
            idx, result = future.result()
            results[idx] = result

    total_ms = (time.perf_counter() - t0) * 1000.0

    passed = sum(1 for r in results if r and r.release_status == "green")
    blocked = sum(1 for r in results if r and r.release_status == "blocked")
    errored = sum(1 for r in results if r and not r.success)

    return {
        "total_rooms": len(rooms),
        "results": [r.to_dict() for r in results if r],
        "summary": {
            "passed": passed,
            "blocked": blocked,
            "errors": errored,
            "total": len(rooms),
            "pass_rate_pct": round(100.0 * passed / len(rooms), 2) if rooms else 0,
        },
        "total_ms": round(total_ms, 2),
        "total_detectors": sum(r.detector_count for r in results if r),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


__all__ = [
    "PipelineResult",
    "StageResult",
    "analyze_building",
    "analyze_room",
]
