"""fireai/core/floor_analyser.py  V3.0
====================================
Safe, sequential floor-level fire alarm design analyser.

Uses the V7.3 DensityOptimizer directly - no ExpertSystem.
MIP (PuLP) available as optional verifier — never replaces greedy placement.
Scenario verification (FirePhysics) available as optional verifier.

V3.0 Changes:
  - Added scenario verification: _run_scenario_verification()
  - Added use_scenarios parameter to FloorAnalyser constructor
  - Added scenario_* fields to RoomSummary (5 new fields)
  - Added scenario_non_compliant_rooms and scenario_safe_to_submit to FloorReport
  - Scenario verification is VERIFIER only — does not modify placement
  - If scenarios fail, room gets scenario_pass=False and warning
  - SCENARIO_DETECTION_FAIL warning when detection time > NFPA limit
  - SCENARIO_BLIND_SPOT warning when significant blind spots found
  - Occupancy-aware fire load from scenario_engine.get_fire_load()
  - Full integration: coverage + detection time + audit in one pipeline
  - Backward compatible: use_scenarios=False (default) = zero change

V2.3 Changes:
  - Added MIP verification path: _try_mip_verification()
  - Added mip_proven_optimal_count, mip_solve_time_s, mip_status to RoomSummary
  - Added use_mip parameter to FloorAnalyser constructor
  - Added MIP_OPTIMALITY_GAP warning when MIP proves fewer detectors suffice
  - MIP is VERIFIER only — greedy always places actual detectors

V2.4 Changes:
  - Coverage radius now calculated dynamically from NFPA 72 Table 17.6.3.1.1
  - Uses calculate_coverage_radius_from_height(ceiling_height, detector_type) → CoverageSpec
  - CoverageSpec provides: radius, area, spacing_max, nfpa_ref, warning
  - Heat detector support: smaller radii per NFPA 72 Table 17.6.3.1.1
  - RoomSummary now tracks: coverage_radius_used, ceiling_height, radius_warning, nfpa_table_ref
  - DetectorLayout now tracks: ceiling_height, detector_type_simple, radius_warning, nfpa_table_ref
  - LOW_CEILING_WARNING updated: references NFPA 72 Table 17.6.3.1.1
  - MIP verification uses layout.coverage_radius instead of self.opt.R

V2.2 Changes:
  - Added refused, refusal_reason, used_mip fields to RoomSummary
  - Added _check_safety_refusal() for NFPA 72 §17.6.4 detector/room validation
  - Added LOW_CEILING_WARNING when ceiling_height < 3.0m (R=6.40m not conservative)

V2.1 Changes:
  - Added theoretical_lower_bound and efficiency_ratio to RoomSummary
  - Added detector_type and duct_devices fields to RoomSummary
  - Added warnings list to RoomSummary
  - Added BOUNDARY_LIMIT live warning when coverage > 99.9% but proof_valid=False
  - Added optional AuditTrail integration

Architecture:
  - DensityOptimizer V7.3 (coverage_limit = R) for detector placement — FROZEN
  - Coverage radius R is now dynamic: calculate_smoke_detector_radius(ceiling_height)
  - MIP Solver (PuLP) as optional verifier — never replaces greedy
  - Scenario Engine (FirePhysics) as optional verifier — NFPA 72 §17.7.3
  - Sequential execution only - parallel processing disabled for safety
  - Triple-check gate: proof_valid AND nfpa_valid AND NOT fallback_used
  - Scenario gate (optional): all_scenarios_pass AND no significant blind spots

MIP Verification (V2.3):
  When use_mip=True and PuLP is available, FloorAnalyser runs MIP Set Covering
  ILP after greedy placement. MIP proves the minimum detector count on a
  candidate grid. This count is stored in mip_proven_optimal_count.
  MIP positions are NOT NFPA-verified — they are never stored in RoomSummary.
  If MIP proves fewer detectors than greedy, an MIP_OPTIMALITY_GAP warning
  is emitted for PE review.

Safety guarantees:
  - Every room result is independently verified.
  - UNSAFE rooms block the floor from being marked compliant.
  - No inter-room state sharing.
  - No parallel execution (safety over speed).

Safety Shield:
  +-------------------+-----------------------------------+-----------------------+
  | Check             | Condition                         | Action on Failure     |
  +-------------------+-----------------------------------+-----------------------+
  | proof_valid       | coverage >= 99.99%                | Reject room, log err  |
  | nfpa_valid        | zero NFPA spacing violations      | Reject room, log err  |
  | fallback_used     | hex/rect strategy must win        | Reject room, log warn |
  | scenario_pass     | all scenarios detect within 60s   | Mark unsafe, warn (V3)|
  | scenario_blind_ok | no significant blind spots        | Mark unsafe, warn (V3)|
  +-------------------+-----------------------------------+-----------------------+

  Note: scenario_pass and scenario_blind_ok only apply when use_scenarios=True.

Known Limitations:
  - Rectangular rooms only (no L-shape support at this layer)
  - Coverage radius now dynamic from NFPA 72 Table 17.6.3.1.1
  - Parallel processing disabled (sequential for safety)
  - No beam/obstruction handling at this layer

Test Results:
  - 15 rooms (3 floor tiers): 15/15 PASS - 100% coverage, 0 NFPA violations
  - 1000 random rooms (seed=42): proof_failures=8/1000, nfpa_failures=0
  - 100 random rooms (seed=2024): proof_failures=1/100, nfpa_failures=0
  - 10 realistic rooms: 10/10 PASS - 100% coverage, 0 NFPA violations
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import List, Literal, Optional

from fireai.core.geometry_utils import (
    grid_points_in_polygon,
    is_rectangular,
    point_in_polygon,
    polygon_area,
    sanitize_room_geometry,
)
from fireai.core.nfpa72_calculations import (
    calculate_coverage_radius_from_height,
)
from fireai.core.nfpa72_technology_dispatcher import (
    DetectorTechnology,
    dispatch_detector_technology,
)
from fireai.core.sensor_physics_advisor import SensorPhysicsAdvisor
from fireai.core.spatial_engine.density_optimizer import (
    DETECTOR_RADIUS,
    DensityOptimizer,
    DetectorLayout,
    Room,
)

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────────
# Floor report
# ──────────────────────────────────────────────────────────────────


@dataclass
class RoomSummary:
    """Compact per-room summary for floor report.

    Attributes:
        room_id:        Unique room identifier from input dict.
        name:           Room display name.
        detector_count: Number of detectors placed in this room.
        detector_type:  Detector type used (e.g. "smoke_photoelectric").
        coverage_pct:   Coverage percentage (target >= 99.99%).
        nfpa_valid:     True if NFPA 72 spacing rules are satisfied.
        proof_valid:    True if coverage proof passed (>= 99.99%).
        fallback_used:  True if fallback strategy was needed (not preferred).
        method:         Placement strategy used (hexG_x, hexA_y, rect_4x3, etc.).
        compliant:      True only if triple-check passes (proof + nfpa + no fallback).
        safe_to_submit: Same as compliant - room is safe for PE review.
        violations:     List of NFPA violation strings (empty if compliant).
        warnings:       List of advisory warnings (including BOUNDARY_LIMIT).
        theoretical_lower_bound: Estimative minimum detector count (NOT proven).
        efficiency_ratio: theoretical_lower_bound / detector_count (closer to 1.0 = better).
        duct_devices:   Number of duct smoke detectors (populated by _inject_duct_analysis).
                        Remains 0 if room has no ducts or is refused.
        refused:        True if room was refused (safety rule violation).
        refusal_reason: Human-readable reason for refusal, or None.
        used_mip:       True if MIP verification was run and succeeded.
        mip_proven_optimal_count: Minimum detector count proven by MIP on candidate grid.
                        None if MIP not run or failed. See TECHNICAL_HONESTY.md §5.
        mip_solve_time_s: MIP solve time in seconds, or None.
        mip_status:     MIP solver status string, or None.
        analysis_ms:    Wall-clock time for this room's analysis in milliseconds.

    Scenario Verification fields (V3.0, only populated when use_scenarios=True):
        scenario_pass:      True if ALL scenarios detect within NFPA 72 §17.7.3 limit.
                            None if scenario verification was not run.
        scenario_fail_count: Number of scenarios that failed detection time check.
        scenario_worst_time_s: Worst (slowest) detection time across all scenarios.
                            None if not run or no detections.
        scenario_blind_spots: Total blind spots across all scenarios.
        scenario_battery_ms: Wall-clock time for scenario verification in ms.
                            0.0 if not run.

    """

    room_id: str
    name: str
    detector_count: int
    detector_type: str = "smoke_photoelectric"
    coverage_pct: float = 0.0
    nfpa_valid: bool = False
    proof_valid: bool = False
    fallback_used: bool = False
    method: str = ""
    compliant: bool = False
    safe_to_submit: bool = False
    violations: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    theoretical_lower_bound: int = 0
    efficiency_ratio: float = 0.0
    duct_devices: int = 0
    refused: bool = False
    refusal_reason: Optional[str] = None
    used_mip: bool = False
    mip_proven_optimal_count: Optional[int] = None
    mip_solve_time_s: Optional[float] = None
    mip_status: Optional[str] = None
    analysis_ms: float = 0.0
    # Phase 7: Variable Coverage Radius tracking fields
    coverage_radius_used: float = DETECTOR_RADIUS  # V20.2 FIX: was stale 6.40; correct R=0.7×9.1=6.37 at h≤3.0m
    ceiling_height: Optional[float] = None
    radius_warning: Optional[str] = None
    nfpa_table_ref: str = "NFPA 72-2022 Table 17.6.3.1.1"
    # V3.0: Scenario verification fields
    scenario_pass: Optional[bool] = None
    scenario_fail_count: int = 0
    scenario_worst_time_s: Optional[float] = None
    scenario_blind_spots: int = 0
    scenario_battery_ms: float = 0.0
    # V3.1: Duct detector fields
    duct_results: List = field(default_factory=list)
    duct_warnings: List[str] = field(default_factory=list)
    # V4.0: Non-rectangular room support
    shape_type: str = "rectangular"  # "rectangular", "l_shape", "polygon"
    polygon_coords: Optional[List] = None  # original polygon for non-rectangular rooms
    # V5.0: Room dimensions for project learning (bounding rectangle)
    width: float = 0.0  # bounding rectangle width (metres)
    length: float = 0.0  # bounding rectangle length (metres)
    # V6.0: Polygon verifier (Greedy Set Cover) — verification only
    polygon_verifier_count: Optional[int] = None  # detectors from Greedy Set Cover on actual polygon
    polygon_verifier_method: Optional[str] = None  # "greedy_polygon" or None
    polygon_verifier_ms: float = 0.0  # verifier runtime in ms
    polygon_optimality_gap: bool = False  # True if greedy polygon proves fewer detectors


@dataclass
class FloorReport:
    """Complete analysis report for one floor.

    Attributes:
        floor_id:            Floor identifier.
        room_summaries:      Per-room summaries in input order.
        total_detectors:     Sum across all rooms.
        total_theoretical_lower_bound: Sum of theoretical lower bounds.
        fully_compliant:     True only if every room is compliant.
        safe_to_submit:      True only if every room is safe_to_submit.
        non_compliant_rooms: IDs of non-compliant rooms.
        unsafe_rooms:        IDs of rooms that failed the triple check.
        floor_warnings:      Floor-level advisory messages.
        analysis_time_s:     Total wall-clock time (seconds).

    """

    floor_id: str
    room_summaries: List[RoomSummary] = field(default_factory=list)
    total_detectors: int = 0
    total_theoretical_lower_bound: int = 0
    fully_compliant: bool = False
    safe_to_submit: bool = False
    non_compliant_rooms: List[str] = field(default_factory=list)
    unsafe_rooms: List[str] = field(default_factory=list)
    floor_warnings: List[str] = field(default_factory=list)
    analysis_time_s: float = 0.0
    # V3.0: Scenario verification aggregation
    scenario_non_compliant_rooms: List[str] = field(default_factory=list)
    # V114 FIX: Fail-safe — must be consistent with safe_to_submit=False
    scenario_safe_to_submit: bool = False
    # V3.1: Duct detector aggregation
    total_duct_devices: int = 0


# ──────────────────────────────────────────────────────────────────


class FloorAnalyser:
    """Safe, sequential full-floor fire alarm design analyser.

    Uses the V7.3 DensityOptimizer directly - no ExpertSystem.
    Optional MIP verification (use_mip=True) proves optimality after greedy.
    Each room is analysed independently; no inter-room state is shared.

    Triple-Check Gate (a room passes only if ALL three are true):
        1. proof_valid   - Coverage verification passed (>= 99.99%)
        2. nfpa_valid    - NFPA 72 spacing/wall rules satisfied
        3. not fallback_used - Hex or rect strategy won (not fallback)

    Safety Refusal (_check_safety_refusal):
        Before analysis, each room is checked for NFPA 72 safety rules.
        Currently enforces: smoke detectors are prohibited in kitchens
        (NFPA 72 §17.6.4). Refused rooms get refused=True and
        refusal_reason with the NFPA reference. No placement is attempted.

    Live Warning (BOUNDARY_LIMIT):
        When coverage > 99.9% but proof_valid=False, a warning is
        added to room warnings and logged to AuditTrail (if provided).
        This represents the known 0.8% boundary condition.

    Live Warning (LOW_CEILING):
        When ceiling_height < 3.0m (below NFPA 72 normative range),
        a LOW_CEILING_WARNING is added. The radius is clamped to
        the 3.0m bracket value (R=6.37m, 0.7×S where S=9.1m) for safety.
        PE review is required for heights outside normative range.

    Args:
        floor_id:   Floor identifier (e.g. "GF", "L1", "B2").
        optimizer:  DensityOptimizer instance (V7.3 with coverage_limit=R).
        audit_trail: Optional AuditTrail for in-memory decision logging.
        audit_store: Optional AuditStore for tamper-proof (SQLite) logging.
                     Critical events (BOUNDARY_LIMIT warnings, placements)
                     are written here when provided.
        use_mip:    If True, run MIP Set Covering ILP as verifier after greedy.
                    Requires PuLP. MIP results are verification only — never
                    replace greedy placement. Default False.
        mip_candidate_step: Grid spacing for MIP candidate positions (meters).
                    Default 1.0m. Smaller = more accurate but slower.
        mip_time_limit: Time limit for MIP solver per room (seconds). Default 10.0.

    Example:
        >>> from fireai.core.spatial_engine.density_optimizer import DensityOptimizer
        >>> from fireai.core.floor_analyser import FloorAnalyser
        >>>
        >>> opt = DensityOptimizer()
        >>> analyser = FloorAnalyser("floor_1", opt)
        >>>
        >>> rooms = [
        ...     {"room_id": "R1", "name": "Office",
        ...      "polygon_coords": [(0,0),(10,0),(10,8),(0,8)],
        ...      "ceiling_height": 3.0},
        ... ]
        >>> report = analyser.analyse(rooms)
        >>> print(report.safe_to_submit)
        True

    """

    def __init__(
        self,
        floor_id: str,
        optimizer: DensityOptimizer,
        audit_trail: Optional[object] = None,
        audit_store: Optional[object] = None,
        use_mip: bool = False,
        mip_candidate_step: float = 1.0,
        mip_time_limit: float = 10.0,
        use_scenarios: bool = False,
        scenario_time_step: float = 1.0,
        scenario_skip_blind: bool = True,
        use_polygon_verifier: bool = False,
        room_timeout_s: float = 60.0,
    ) -> None:
        self.floor_id = floor_id
        self.opt = optimizer  # V7.3 as-is, no modifications
        self.audit_trail = audit_trail
        self.audit_store = audit_store
        self.use_mip = use_mip
        self.mip_candidate_step = mip_candidate_step
        self.mip_time_limit = mip_time_limit
        # V3.0: Scenario verification
        self.use_scenarios = use_scenarios
        self.scenario_time_step = scenario_time_step
        self.scenario_skip_blind = scenario_skip_blind  # skip blind scan for speed
        # V6.0: Polygon verifier (Greedy Set Cover)
        self.use_polygon_verifier = use_polygon_verifier
        # V11: Per-room timeout (Consultant #5 Criticism #3 - timeout concept accepted)
        # If a room analysis takes longer than this, flag it for manual review.
        # NOT using ProcessPoolExecutor - sequential execution is maintained for safety.
        self.room_timeout_s = room_timeout_s
        # V12: Sensor Physics Advisor (Consultant #6 Criticism #1 — advisory concept accepted)
        # Provides warnings for extreme ceiling/slope conditions where
        # point detectors may be insufficient (beam detectors recommended).
        self.sensor_advisor = SensorPhysicsAdvisor()

    # ─── public ──────────────────────────────────────────────────────

    def analyse(self, rooms: List[dict]) -> FloorReport:
        """Analyse all rooms on the floor and return a FloorReport.

        Processes rooms sequentially (no parallelism) and applies the
        triple-check gate to each room independently.

        Args:
            rooms: List of room dicts. Each dict must have:
                - room_id (str): Unique room identifier
                - name (str, optional): Display name
                - polygon_coords (List[Tuple[float,float]]): Corner coordinates
                - ceiling_height (float, optional): Ceiling height in meters

        Returns:
            FloorReport containing:
                - Per-room summaries with detector counts, coverage, compliance
                - Floor-level compliance status (fully_compliant, safe_to_submit)
                - Lists of non-compliant and unsafe room IDs
                - Advisory warnings for any failures

        Side Effects:
            - Logs each room result via Python logging
            - Records decisions in AuditTrail (if provided)
            - No external I/O or database writes

        """
        t0 = time.time()
        report = FloorReport(floor_id=self.floor_id)

        if not rooms:
            report.floor_warnings.append("No rooms provided.")
            return report

        for room_dict in rooms:
            # ─── V11: Centralized geometry sanitization ───
            # (Replaces scattered V7.3.1 inline checks with sanitize_room_geometry)
            # Handles: min area, self-intersection repair, MultiPolygon rejection,
            # near-duplicate vertex simplification, and corrupted geometry.
            polygon_coords = room_dict.get("polygon_coords", [])
            if polygon_coords:
                sanitize_result = sanitize_room_geometry(polygon_coords, min_area=1.0)
                if sanitize_result.rejected:
                    room_name = room_dict.get("name", room_dict.get("room_id", ""))
                    summary = RoomSummary(
                        room_id=room_dict.get("room_id", room_name),
                        name=room_name,
                        detector_count=0,
                        detector_type=room_dict.get("detector_type", "smoke_photoelectric"),
                        coverage_pct=0.0,
                        nfpa_valid=False,
                        proof_valid=False,
                        fallback_used=False,
                        method="rejected_geometry",
                        compliant=False,
                        safe_to_submit=False,
                        violations=[f"GEOMETRY_REJECTED: {sanitize_result.rejection_reason}"],
                        warnings=[f"REJECTED: {sanitize_result.rejection_reason}"],
                        theoretical_lower_bound=0,
                        efficiency_ratio=0.0,
                        duct_devices=0,
                        refused=True,
                        refusal_reason=sanitize_result.rejection_reason,
                        used_mip=False,
                        analysis_ms=0.0,
                    )
                    report.room_summaries.append(summary)
                    report.unsafe_rooms.append(room_dict.get("room_id", room_name))
                    continue
                if sanitize_result.was_modified:
                    # Use cleaned coordinates
                    room_dict = dict(room_dict)  # copy to avoid mutating original
                    room_dict["polygon_coords"] = sanitize_result.coords
                    polygon_coords = sanitize_result.coords
                    logger.info(
                        "Room %s: Geometry sanitized: %s",
                        room_dict.get("room_id", room_dict.get("name", "")),
                        "; ".join(sanitize_result.modifications),
                    )

            # ─── Safety refusal check (NFPA 72 §17.6.4) ───
            room_type = room_dict.get("room_type", "")
            detector_type = room_dict.get("detector_type", "smoke_photoelectric")
            is_refused, refusal_reason = self._check_safety_refusal(room_type, detector_type)

            if is_refused:
                # Refused room: no placement attempted
                room_name = room_dict.get("name", room_dict.get("room_id", ""))
                room_warnings = [f"SAFETY_REFUSAL: {refusal_reason}"]
                summary = RoomSummary(
                    room_id=room_dict.get("room_id", room_name),
                    name=room_name,
                    detector_count=0,
                    detector_type=detector_type,
                    coverage_pct=0.0,
                    nfpa_valid=False,
                    proof_valid=False,
                    fallback_used=False,
                    method="refused",
                    compliant=False,
                    safe_to_submit=False,
                    violations=[refusal_reason],
                    warnings=room_warnings,
                    theoretical_lower_bound=0,
                    efficiency_ratio=0.0,
                    duct_devices=0,
                    refused=True,
                    refusal_reason=refusal_reason,
                    used_mip=False,
                    analysis_ms=0.0,
                )
                report.room_summaries.append(summary)
                continue

            # Build Room object from dict
            room = self._build_room(room_dict)

            # ─── V4.0: Non-rectangular room detection ─────────────────────────
            polygon_coords = room_dict.get("polygon_coords", [])
            is_non_rect = polygon_coords and len(polygon_coords) >= 3 and not is_rectangular(polygon_coords)
            shape_type = "rectangular"
            if is_non_rect:
                # Classify shape by vertex count for user-friendly labelling
                nv = len(polygon_coords)
                if polygon_coords[0] == polygon_coords[-1]:
                    nv -= 1  # strip closing vertex
                shape_type = "l_shape" if nv == 6 else "polygon"

            # Calculate NFPA 72 coverage radius from ceiling height
            # Phase 7: Use CoverageSpec with structured NFPA 72 Table 17.6.3.1.1
            ceiling_h = room_dict.get("ceiling_height", 3.0)
            # Fix 5: Protect against None ceiling_height
            if ceiling_h is None:
                ceiling_h = 3.0
            # Fix 6: detector_type with safe default
            det_type_str = room_dict.get("detector_type", "smoke_photoelectric")
            # Map FloorAnalyser detector types to CoverageSpec types
            cov_det_type: Literal["smoke", "heat"] = "heat" if "heat" in det_type_str.lower() else "smoke"
            spec = calculate_coverage_radius_from_height(ceiling_h, cov_det_type)
            radius = spec.radius

            # Analyse single room with V7.3 + dynamic radius
            t_room = time.time()
            layout = self.opt.optimize(room, coverage_radius=radius)
            ms = (time.time() - t_room) * 1000

            # ─── V11: Per-room timeout warning ───
            # (Consultant #5 Criticism #3 - timeout concept accepted, ProcessPoolExecutor rejected)
            # Sequential execution is maintained for safety. If a room takes too long,
            # flag it for manual review rather than using process isolation.
            room_time_s = ms / 1000.0
            if room_time_s > self.room_timeout_s:
                timeout_msg = (
                    f"ROOM_TIMEOUT: Room analysis took {room_time_s:.1f}s, "
                    f"exceeding timeout limit {self.room_timeout_s:.0f}s. "
                    f"Possible infinite loop in fallback algorithm. "
                    f"Manual design review required."
                )
                room_warnings = list(layout.warnings) if layout.warnings else []
                room_warnings.append(timeout_msg)
                logger.warning("Room %s: %s", room.name, timeout_msg)

                # Log to AuditStore if available
                if self.audit_store and hasattr(self.audit_store, "add_event"):
                    self.audit_store.add_event(
                        event_type="ROOM_TIMEOUT_WARNING",
                        room_id=room_dict.get("room_id", room.name),
                        details_dict={
                            "analysis_time_s": round(room_time_s, 3),
                            "timeout_limit_s": self.room_timeout_s,
                            "note": "Room analysis exceeded timeout. Possible infinite loop. Manual design required.",
                        },
                    )

            # ─── V4.0: Filter detectors for non-rectangular rooms ─────────────
            filtered_count = 0
            if is_non_rect:
                filtered_count = self._filter_polygon_detectors(
                    layout,
                    polygon_coords,
                    radius,
                )

            # Triple check
            ok = layout.proof_valid and layout.nfpa_valid and not layout.fallback_used

            # BOUNDARY_LIMIT + LOW_CEILING live warnings
            room_warnings = list(layout.warnings) if layout.warnings else []

            # V4.0: Non-rectangular room warning
            if is_non_rect:
                poly_area = polygon_area(polygon_coords)
                bbox_w, bbox_h = room.width, room.length
                bbox_area = bbox_w * bbox_h
                approx_msg = (
                    f"NON_RECTANGULAR_SHAPE: Room shape is {shape_type} "
                    f"(area={poly_area:.1f}m²). Placement used bounding rectangle "
                    f"({bbox_w:.1f}m × {bbox_h:.1f}m = {bbox_area:.1f}m²). "
                    f"{filtered_count} detector(s) filtered from cutout region. "
                    f"Coverage verified on actual polygon. PE review recommended."
                )
                room_warnings.append(approx_msg)
                logger.info("Room %s: %s", room.name, approx_msg)

            # Phase 7: Add CoverageSpec warning to layout and room warnings
            # Fix 7: Use direct assignment, not add_warning()
            if spec.warning:
                layout.radius_warning = spec.warning
                layout.nfpa_table_ref = spec.nfpa_ref
                room_warnings.append(spec.warning)
            layout.detector_type_simple = cov_det_type

            # LOW_CEILING_WARNING: ceiling below NFPA 72 normative range
            if ceiling_h < 3.0:
                low_msg = (
                    f"LOW_CEILING_WARNING: Ceiling height {ceiling_h:.1f}m < 3.0m "
                    f"(below NFPA 72 normative range). "
                    f"Using conservative R={radius:.2f}m from NFPA 72 Table 17.6.3.1.1. "
                    f"PE review required for heights outside normative range."
                )
                room_warnings.append(low_msg)
                logger.warning("Room %s: %s", room.name, low_msg)

                # Log to AuditStore if available
                if self.audit_store and hasattr(self.audit_store, "add_event"):
                    self.audit_store.add_event(
                        event_type="LOW_CEILING_WARNING",
                        room_id=room_dict.get("room_id", room.name),
                        details_dict={
                            "ceiling_height_m": ceiling_h,
                            "radius_used_m": radius,
                            "nfpa_table_reference": "Table 17.6.3.1.1",  # V20.2 FIX: was wrong 17.6.3.2
                            "note": "Height below NFPA 72 range — using conservative radius. PE review required.",
                        },
                    )

            # ─── V12: Sensor Physics Advisory (Consultant #6 Criticism #1) ───
            # Advisory warnings for extreme ceiling/slope conditions.
            # Does NOT modify calculations — only adds recommendations.
            # The actual coverage radius is already height-adjusted per
            # NFPA 72 Table 17.6.3.1.1 (see calculate_coverage_radius_from_height).
            sensor_advisory = self.sensor_advisor.advise_room_dict(room_dict)
            if sensor_advisory.severity in ("WARNING", "CRITICAL"):
                for rec in sensor_advisory.recommendations:
                    room_warnings.append(rec)
                    logger.log(
                        logging.WARNING if sensor_advisory.severity == "WARNING" else logging.CRITICAL,
                        "Room %s: %s",
                        room.name,
                        rec,
                    )

                # Log to AuditStore if available
                if self.audit_store and hasattr(self.audit_store, "add_event"):
                    self.audit_store.add_event(
                        event_type=f"SENSOR_ADVISORY_{sensor_advisory.severity}",
                        room_id=room_dict.get("room_id", room.name),
                        details_dict={
                            "severity": sensor_advisory.severity,
                            "beam_detector_recommended": sensor_advisory.beam_detector_recommended,
                            "performance_based_design": sensor_advisory.performance_based_design,
                            "recommendations": sensor_advisory.recommendations,
                            "nfpa_references": sensor_advisory.nfpa_references,
                        },
                    )

            # ─── V13: Technology Dispatcher (Consultant #7) ───
            # Automatic detector technology selection based on ceiling
            # height and slope. This goes BEYOND advisory — it selects
            # the appropriate detector technology for the room.
            tech_decision = dispatch_detector_technology(room_dict)
            if tech_decision.technology != DetectorTechnology.POINT_SMOKE:
                # Non-point detector required — add technology decision to warnings
                room_warnings.append(
                    f"TECHNOLOGY_DISPATCH: {tech_decision.technology.value} selected "
                    f"for ceiling h={tech_decision.ceiling_height_m:.1f}m "
                    f"slope={tech_decision.slope_degrees:.1f}°. "
                    f"Reason: {tech_decision.reason}"
                )
                logger.warning(
                    "Room %s: TECHNOLOGY_DISPATCH → %s (h=%.1fm, slope=%.1f°)",
                    room.name,
                    tech_decision.technology.value,
                    tech_decision.ceiling_height_m,
                    tech_decision.slope_degrees,
                )
                # Log to AuditStore
                if self.audit_store and hasattr(self.audit_store, "add_event"):
                    self.audit_store.add_event(
                        event_type=f"TECHNOLOGY_DISPATCH_{tech_decision.technology.value}",
                        room_id=room_dict.get("room_id", room.name),
                        details_dict={
                            "technology": tech_decision.technology.value,
                            "ceiling_height_m": tech_decision.ceiling_height_m,
                            "slope_degrees": tech_decision.slope_degrees,
                            "spacing_m": tech_decision.spacing_m,
                            "ridge_zone_required": tech_decision.ridge_zone_required,
                            "reason": tech_decision.reason,
                            "nfpa_references": tech_decision.nfpa_references,
                            "warnings": tech_decision.warnings,
                        },
                    )
            # Add economic warnings from dispatcher even for point detectors
            for tw in tech_decision.warnings:
                if tw not in room_warnings:
                    room_warnings.append(tw)
                    logger.info("Room %s: %s", room.name, tw)

            if not layout.proof_valid and layout.coverage_pct > 99.9:
                boundary_msg = (
                    f"BOUNDARY_LIMIT: Coverage {layout.coverage_pct:.2f}% exceeds 99.9% "
                    f"but grid verification at step=0.20m could not confirm 100%. "
                    f"This is a known limitation (0.8% of rooms). PE review recommended."
                )
                room_warnings.append(boundary_msg)
                logger.warning("Room %s: %s", room.name, boundary_msg)

                # Log to AuditTrail if available
                if self.audit_trail and hasattr(self.audit_trail, "log_boundary_limit_warning"):
                    self.audit_trail.log_boundary_limit_warning(
                        room_id=room_dict.get("room_id", room.name),
                        coverage_pct=layout.coverage_pct,
                    )

                # Log to AuditStore (tamper-proof) if available
                if self.audit_store and hasattr(self.audit_store, "add_event"):
                    self.audit_store.add_event(
                        event_type="BOUNDARY_LIMIT_WARNING",
                        room_id=room_dict.get("room_id", room.name),
                        details_dict={
                            "coverage_pct": layout.coverage_pct,
                            "proof_valid": False,
                            "grid_resolution_m": 0.20,
                            "note": "Coverage > 99.9% but proof_valid=False. Known 0.8% limitation. PE review recommended.",
                        },
                    )

            # Log placement to AuditTrail if available
            if self.audit_trail and hasattr(self.audit_trail, "log_placement"):
                self.audit_trail.log_placement(
                    room_id=room_dict.get("room_id", room.name),
                    detector_count=layout.count,
                    detector_type=det_type_str,  # V20.2 FIX: was hardcoded "smoke_photoelectric"
                    coverage_pct=layout.coverage_pct,
                    positions=layout.detectors,
                )

            # Log placement to AuditStore (tamper-proof) if available
            if self.audit_store and hasattr(self.audit_store, "add_event"):
                self.audit_store.add_event(
                    event_type="DETECTOR_PLACEMENT",
                    room_id=room_dict.get("room_id", room.name),
                    details_dict={
                        "detector_count": layout.count,
                        "detector_type": det_type_str,  # V20.2 FIX: was hardcoded "smoke_photoelectric"
                        "coverage_pct": layout.coverage_pct,
                        "nfpa_valid": layout.nfpa_valid,
                        "proof_valid": layout.proof_valid,
                        "method": layout.method,
                        "theoretical_lower_bound": layout.theoretical_lower_bound,
                        "efficiency_ratio": round(layout.efficiency_ratio, 4),
                    },
                )

            summary = RoomSummary(
                room_id=room_dict.get("room_id", room.name),
                name=room.name,
                detector_count=layout.count,
                detector_type=det_type_str,
                coverage_pct=layout.coverage_pct,
                nfpa_valid=layout.nfpa_valid,
                proof_valid=layout.proof_valid,
                fallback_used=layout.fallback_used,
                method=layout.method,
                compliant=ok,
                safe_to_submit=ok,
                violations=getattr(layout, "violations", []),
                warnings=room_warnings,
                theoretical_lower_bound=layout.theoretical_lower_bound,
                efficiency_ratio=layout.efficiency_ratio,
                duct_devices=0,  # Populated by _inject_duct_analysis
                refused=False,
                refusal_reason=None,
                used_mip=False,
                mip_proven_optimal_count=None,
                mip_solve_time_s=None,
                mip_status=None,
                analysis_ms=round(ms, 1),
                # Phase 7: Variable Coverage Radius tracking
                coverage_radius_used=radius,
                ceiling_height=ceiling_h,
                radius_warning=spec.warning,
                nfpa_table_ref=spec.nfpa_ref,
                # V4.0: Non-rectangular room tracking
                shape_type=shape_type,
                polygon_coords=polygon_coords if is_non_rect else None,
                # V5.0: Room dimensions for project learning
                width=room.width,
                length=room.length,
            )

            # ─── MIP verification (optional) ───
            if self.use_mip:
                self._try_mip_verification(room, layout, summary)

            # ─── Scenario verification (optional, V3.0) ───
            if self.use_scenarios:
                self._run_scenario_verification(
                    room_dict,
                    layout,
                    summary,
                    ceiling_h,
                    det_type_str,
                )

            # ─── Duct detector analysis (V3.1) ───────────────────────────
            self._inject_duct_analysis(room_dict, summary)

            # ─── Polygon verifier (V6.0) — Greedy Set Cover ──────────────
            if self.use_polygon_verifier and is_non_rect:
                self._run_polygon_verifier(polygon_coords, layout, summary)

            report.room_summaries.append(summary)
            report.total_detectors += summary.detector_count
            report.total_theoretical_lower_bound += summary.theoretical_lower_bound
            report.total_duct_devices += summary.duct_devices

        # Floor-level aggregation
        report.non_compliant_rooms = [s.room_id for s in report.room_summaries if not s.compliant]
        report.unsafe_rooms = [
            s.room_id for s in report.room_summaries if not s.proof_valid or not s.nfpa_valid or s.fallback_used
        ]
        report.fully_compliant = len(report.non_compliant_rooms) == 0
        report.safe_to_submit = len(report.unsafe_rooms) == 0

        # V3.0: Scenario verification aggregation
        if self.use_scenarios:
            report.scenario_non_compliant_rooms = [s.room_id for s in report.room_summaries if s.scenario_pass is False]
            report.scenario_safe_to_submit = len(report.scenario_non_compliant_rooms) == 0

        report.analysis_time_s = round(time.time() - t0, 3)

        if report.unsafe_rooms:
            report.floor_warnings.append(f"UNSAFE rooms (do NOT submit): {report.unsafe_rooms}")
        if not report.fully_compliant:
            report.floor_warnings.append(f"Non-compliant rooms: {report.non_compliant_rooms}")

        # V3.0: Scenario warnings at floor level
        if self.use_scenarios and report.scenario_non_compliant_rooms:
            report.floor_warnings.append(
                f"SCENARIO_NON_COMPLIANT rooms (detection time > NFPA 72 §17.7.3): "
                f"{report.scenario_non_compliant_rooms}"
            )

        logger.info(
            "FloorAnalyser: floor=%s rooms=%d detectors=%d compliant=%s t=%.2fs",
            self.floor_id,
            len(rooms),
            report.total_detectors,
            report.fully_compliant,
            report.analysis_time_s,
        )
        return report

    # ─── private ─────────────────────────────────────────────────────

    def _try_mip_verification(
        self,
        room: Room,
        layout: DetectorLayout,
        summary: RoomSummary,
    ) -> None:
        """Run MIP Set Covering ILP as verification after greedy placement.

        MIP proves the minimum detector count on a candidate grid.
        This is VERIFICATION ONLY — greedy placement is always used.
        MIP positions are NOT NFPA-verified and are never stored in RoomSummary.

        If MIP proves fewer detectors than greedy, an MIP_OPTIMALITY_GAP
        warning is added for PE review.

        Updates summary fields in-place:
          - used_mip, mip_proven_optimal_count, mip_solve_time_s, mip_status

        Args:
            room:    Room object with width, length, ceiling_height.
            layout:  DetectorLayout from greedy (DensityOptimizer V7.3).
            summary: RoomSummary to update with MIP verification results.

        """
        try:
            from fireai.core.spatial_engine.mip_solver import (
                PULP_AVAILABLE,
                solve_set_covering_mip,
            )
        except ImportError:
            summary.mip_status = "mip_solver_import_failed"
            logger.warning("Room %s: MIP solver module not importable", room.name)
            return

        if not PULP_AVAILABLE:
            summary.mip_status = "pulp_not_installed"
            return

        mip_result = solve_set_covering_mip(
            room_width=room.width,
            room_length=room.length,
            coverage_radius=layout.coverage_radius,  # Actual radius used for placement
            candidate_step=self.mip_candidate_step,
            time_limit_seconds=self.mip_time_limit,
        )

        if mip_result.success:
            summary.used_mip = True
            summary.mip_proven_optimal_count = mip_result.theoretical_minimum
            summary.mip_solve_time_s = round(mip_result.solve_time_seconds, 3)
            summary.mip_status = mip_result.solver_status

            # Log MIP verification to AuditStore if available
            if self.audit_store and hasattr(self.audit_store, "add_event"):
                self.audit_store.add_event(
                    event_type="MIP_VERIFICATION",
                    room_id=summary.room_id,
                    details_dict={
                        "mip_proven_optimal_count": mip_result.theoretical_minimum,
                        "greedy_count": layout.count,
                        "gap": layout.count - mip_result.theoretical_minimum,
                        "candidate_step_m": self.mip_candidate_step,
                        "solve_time_s": round(mip_result.solve_time_seconds, 3),
                        "solver_status": mip_result.solver_status,
                    },
                )

            # Golden warning: MIP proves fewer detectors suffice on candidate grid
            if mip_result.theoretical_minimum < layout.count:
                gap_msg = (
                    f"MIP_OPTIMALITY_GAP: MIP proves {mip_result.theoretical_minimum} detectors "
                    f"sufficient on candidate grid (step={self.mip_candidate_step}m), "
                    f"but greedy placed {layout.count}. "
                    f"PE review recommended for potential reduction."
                )
                summary.warnings.append(gap_msg)
                logger.info("Room %s: %s", room.name, gap_msg)
            else:
                logger.info(
                    "Room %s: MIP confirms greedy count %d is optimal on candidate grid",
                    room.name,
                    layout.count,
                )
        else:
            summary.used_mip = False
            summary.mip_status = mip_result.fallback_reason or mip_result.solver_status
            logger.info(
                "Room %s: MIP verification skipped — %s",
                room.name,
                summary.mip_status,
            )

    # ------------------------------------------------------------------
    def _filter_polygon_detectors(
        self,
        layout: DetectorLayout,
        polygon_coords: list,
        radius: float,
    ) -> int:
        """Filter detectors that fall outside a non-rectangular polygon (V4.0).

        DensityOptimizer places detectors on the bounding rectangle. For
        L-shaped or other non-rectangular rooms, some detectors may land
        in the cutout region. This method removes those detectors and
        re-verifies coverage on the actual polygon grid.

        Updates layout in-place:
          - layout.detectors: filtered to polygon interior
          - layout.coverage_pct: re-verified on actual polygon
          - layout.proof_valid: updated based on new coverage

        Args:
            layout:         DetectorLayout from DensityOptimizer (bounding rect).
            polygon_coords: Original polygon coordinates from room_dict.
            radius:         Coverage radius used for placement.

        Returns:
            Number of detectors filtered (removed from cutout region).

        """
        original_count = len(layout.detectors)

        # Filter detectors that are inside the actual polygon
        filtered_dets = [
            (x, y) for (x, y) in layout.detectors if point_in_polygon((x, y), polygon_coords, include_boundary=True)
        ]
        removed = original_count - len(filtered_dets)

        if removed > 0:
            layout.detectors = filtered_dets

        # Re-verify coverage on actual polygon grid
        targets = grid_points_in_polygon(polygon_coords, step=0.50, margin=0.0)
        if targets and filtered_dets:
            R2 = radius * radius + 1e-9
            covered = sum(
                1 for (tx, ty) in targets if any((tx - dx) ** 2 + (ty - dy) ** 2 <= R2 for (dx, dy) in filtered_dets)
            )
            layout.coverage_pct = round(100.0 * covered / len(targets), 4)
            layout.proof_valid = covered >= len(targets) * 0.9999
        elif not targets:
            layout.coverage_pct = 100.0
            layout.proof_valid = True

        return removed

    # ------------------------------------------------------------------
    def _run_polygon_verifier(
        self,
        polygon_coords: list,
        layout: DetectorLayout,
        summary: RoomSummary,
    ) -> None:
        """Run Greedy Set Cover verifier on a non-rectangular polygon (V6.0).

        This is VERIFICATION ONLY — it never replaces the actual placement.
        The verifier proves how many detectors suffice on the actual polygon
        interior grid. If it proves fewer than the bounding-rectangle approach,
        a POLYGON_OPTIMALITY_GAP warning is emitted for PE review.

        This follows the same pattern as MIP verification (V2.3):
          - Verifier runs after greedy placement
          - Results are informational only
          - Warning emitted if gap is detected
          - No placement is ever modified

        Updates summary fields in-place:
          - polygon_verifier_count, polygon_verifier_method,
            polygon_verifier_ms, polygon_optimality_gap
        """
        try:
            from fireai.core.polygon_optimizer import (
                PolygonDensityOptimizer,
                PolygonRoom,
            )
        except ImportError:
            logger.debug(
                "Room %s: polygon_optimizer not importable — skipping verifier",
                summary.name,
            )
            return

        t0 = time.time()
        try:
            poly_room = PolygonRoom(
                room_id=summary.room_id,
                polygon=polygon_coords,
                ceiling_height=summary.ceiling_height or 3.0,
                detector_type=summary.detector_type,
                name=summary.name,
            )
            poly_opt = PolygonDensityOptimizer()
            poly_summary = poly_opt.optimize_polygon(poly_room)
            ms = (time.time() - t0) * 1000

            summary.polygon_verifier_count = poly_summary.count
            summary.polygon_verifier_method = poly_summary.method
            summary.polygon_verifier_ms = round(ms, 1)

            # If polygon verifier proves fewer detectors suffice
            if poly_summary.count < summary.detector_count:
                summary.polygon_optimality_gap = True
                gap_msg = (
                    f"POLYGON_OPTIMALITY_GAP: Greedy Set Cover on actual polygon "
                    f"proves {poly_summary.count} detectors sufficient "
                    f"(method={poly_summary.method}), "
                    f"but bounding-rectangle approach placed {summary.detector_count}. "
                    f"PE review recommended for potential reduction."
                )
                summary.warnings.append(gap_msg)
                logger.info("Room %s: %s", summary.name, gap_msg)

            # Log to AuditStore if available
            if self.audit_store and hasattr(self.audit_store, "add_event"):
                self.audit_store.add_event(
                    event_type="POLYGON_VERIFICATION",
                    room_id=summary.room_id,
                    details_dict={
                        "polygon_verifier_count": poly_summary.count,
                        "bounding_rect_count": summary.detector_count,
                        "gap": summary.detector_count - poly_summary.count,
                        "verifier_method": poly_summary.method,
                        "verifier_coverage_pct": poly_summary.coverage_pct,
                        "verifier_proof_valid": poly_summary.proof_valid,
                        "verifier_nfpa_valid": poly_summary.nfpa_valid,
                        "verifier_ms": round(ms, 1),
                    },
                )

        except Exception as exc:
            logger.warning(
                "Room %s: polygon verifier failed — %s",
                summary.name,
                exc,
            )

    # ------------------------------------------------------------------
    def _inject_duct_analysis(
        self,
        room_dict: dict,
        summary: RoomSummary,
    ) -> None:
        """Run duct detector analysis for a room (V3.1).

        If the room_dict contains a 'ducts' key with a list of duct
        specifications, this method analyses each duct per NFPA 72 §17.7.5
        and populates summary.duct_results, summary.duct_devices, and
        summary.duct_warnings.

        If no ducts are specified, duct_devices remains 0 (default).

        Args:
            room_dict: Room dictionary (must have optional 'ducts' key).
            summary:   RoomSummary to update with duct results.

        """
        try:
            from fireai.core.duct_detector import (
                DuctSpec,
                analyse_ducts,
                total_duct_detectors,
            )
        except ImportError:
            logger.debug(
                "Room %s: duct_detector not importable — skipping duct analysis",
                summary.name,
            )
            return

        # Support multiple key names for compatibility with different models:
        # - "ducts" (simple key used by FloorAnalyser room dicts)
        # - "hvac_ducts" (used by nfpa72_models.RoomSpec.hvac_ducts property)
        # - "hvac_duct_list" (used by nfpa72_models.RoomSpec.hvac_duct_list field)
        raw_ducts = room_dict.get("ducts") or room_dict.get("hvac_ducts") or room_dict.get("hvac_duct_list") or []
        if not raw_ducts:
            return

        # Convert dicts to DuctSpec if needed
        duct_specs = []
        for d in raw_ducts:
            if isinstance(d, DuctSpec):
                duct_specs.append(d)
            elif isinstance(d, dict):
                try:
                    duct_specs.append(DuctSpec(**d))
                except TypeError:
                    logger.warning(
                        "Room %s: invalid duct spec %s — skipping",
                        summary.name,
                        d,
                    )
            else:
                logger.warning(
                    "Room %s: duct entry must be DuctSpec or dict, got %s",
                    summary.name,
                    type(d).__name__,
                )

        if not duct_specs:
            return

        results = analyse_ducts(duct_specs)
        all_warnings = [w for r in results for w in r.warnings]

        summary.duct_results = results
        summary.duct_devices = total_duct_detectors(results)
        summary.duct_warnings = all_warnings

        # Log to AuditStore if available
        if self.audit_store and hasattr(self.audit_store, "add_event"):
            self.audit_store.add_event(
                event_type="DUCT_DETECTOR_ANALYSIS",
                room_id=summary.room_id,
                details_dict={
                    "ducts_analysed": len(duct_specs),
                    "duct_devices": summary.duct_devices,
                    "exempt_ducts": sum(1 for r in results if r.exempt),
                    "nfpa_ref": "NFPA 72-2022 §17.7.5",
                },
            )

        logger.info(
            "Room %s: duct analysis ducts=%d devices=%d exempt=%d",
            summary.name,
            len(duct_specs),
            summary.duct_devices,
            sum(1 for r in results if r.exempt),
        )

    def _run_scenario_verification(
        self,
        room_dict: dict,
        layout: DetectorLayout,
        summary: RoomSummary,
        ceiling_h: float,
        det_type_str: str,
    ) -> None:
        """Run fire scenario verification after detector placement (V3.0).

        Tests the placed detector layout against standard NFPA 72 §17.7.3
        fire scenarios. This is VERIFICATION ONLY — it does not modify
        the placement. If any scenario fails, the room is marked with
        scenario_pass=False and a warning is added.

        Uses scenario_engine.ScenarioRunner + ScenarioLibrary.
        Fire load is determined from room occupancy type via
        scenario_engine.get_fire_load().

        Updates summary fields in-place:
          - scenario_pass, scenario_fail_count, scenario_worst_time_s,
            scenario_blind_spots, scenario_battery_ms

        Args:
            room_dict:    Room dictionary with polygon_coords and optional occupancy.
            layout:       DetectorLayout from DensityOptimizer.
            summary:      RoomSummary to update with scenario results.
            ceiling_h:    Ceiling height in metres.
            det_type_str: Detector type string (e.g. "smoke_photoelectric").

        """
        try:
            from fireai.core.scenario_engine import (
                ScenarioLibrary,
                ScenarioRunner,
                get_fire_load,
            )
        except ImportError:
            summary.scenario_pass = None
            logger.warning(
                "Room %s: scenario_engine not importable — skipping scenario verification",
                summary.name,
            )
            return

        t_sc = time.perf_counter()

        # Extract room polygon and occupancy
        polygon = room_dict.get("polygon_coords", [])
        if not polygon or len(polygon) < 3:
            summary.scenario_pass = None
            logger.warning(
                "Room %s: no valid polygon for scenario verification",
                summary.name,
            )
            return

        occupancy = room_dict.get("room_type", room_dict.get("occupancy", "office"))
        fire_load = get_fire_load(occupancy)

        # Build standard scenario battery (no blind spot scan — too expensive)
        scenarios = ScenarioLibrary.all_scenarios(polygon, ceiling_h, fire_load)

        # Run battery
        runner = ScenarioRunner(time_step_s=self.scenario_time_step)
        battery = runner.run_battery(
            detector_positions=layout.detectors,
            room_polygon=polygon,
            scenarios=scenarios,
            detector_type_str=det_type_str,
        )

        # Aggregate results
        fail_count = battery.fail_count
        worst_time = battery.worst_detection_time_s
        total_blind = battery.total_blind_spots

        scenario_pass = battery.all_pass

        elapsed_ms = (time.perf_counter() - t_sc) * 1000.0

        # Update summary
        summary.scenario_pass = scenario_pass
        summary.scenario_fail_count = fail_count
        summary.scenario_worst_time_s = worst_time
        summary.scenario_blind_spots = total_blind
        summary.scenario_battery_ms = round(elapsed_ms, 1)

        # Warnings
        if not scenario_pass:
            fail_msg = (
                f"SCENARIO_DETECTION_FAIL: {fail_count}/{len(scenarios)} scenario(s) "
                f"failed NFPA 72 §17.7.3 detection time limit. "
                f"Worst detection time: {worst_time:.1f}s (limit 60s). "
                f"Layout may need additional detectors or repositioning. "
                f"PE review required."
            )
            summary.warnings.append(fail_msg)
            logger.warning("Room %s: %s", summary.name, fail_msg)

        if total_blind > 0:
            blind_msg = (
                f"SCENARIO_BLIND_SPOT: {total_blind} blind spot(s) detected "
                f"across all scenarios. Points where no detector responds "
                f"within NFPA 72 §17.7.3 limit. PE review recommended."
            )
            summary.warnings.append(blind_msg)
            logger.info("Room %s: %s", summary.name, blind_msg)

        # Log to AuditStore if available
        if self.audit_store and hasattr(self.audit_store, "add_event"):
            self.audit_store.add_event(
                event_type="SCENARIO_VERIFICATION",
                room_id=summary.room_id,
                details_dict={
                    "scenarios_run": len(scenarios),
                    "scenario_pass": scenario_pass,
                    "fail_count": fail_count,
                    "worst_detection_time_s": worst_time,
                    "total_blind_spots": total_blind,
                    "fire_load_mj_m2": fire_load,
                    "occupancy": occupancy,
                    "compute_ms": round(elapsed_ms, 1),
                    "nfpa_clause": "NFPA 72-2022 §17.7.3",
                },
            )

        logger.info(
            "Room %s: scenario verification pass=%s fail=%d worst=%.1fs blind=%d t=%.0fms",
            summary.name,
            scenario_pass,
            fail_count,
            worst_time or 0.0,
            total_blind,
            elapsed_ms,
        )

    @staticmethod
    def _check_safety_refusal(room_type: str, detector_type: str) -> tuple:
        """Validate room_type + detector_type combination against NFPA 72 safety rules.

        This is a simple rule-based check — NOT an ExpertSystem.
        It enforces clear NFPA 72 prohibitions that must not be violated
        regardless of placement quality.

        Current rules:
            - kitchen + smoke_photoelectric → REFUSED (NFPA 72 §17.6.4)
              Smoke detectors are prohibited in kitchens due to nuisance alarms
              from cooking. Heat detectors must be used instead.

        Args:
            room_type:     Room type string (e.g. "kitchen", "office", "server_room").
            detector_type: Detector type string (e.g. "smoke_photoelectric", "heat_fixed").

        Returns:
            Tuple of (is_refused: bool, reason: str).
            If is_refused is True, reason contains the NFPA reference.
            If is_refused is False, reason is empty string.

        """
        # NFPA 72 §17.6.4: Smoke detectors shall not be installed in kitchens
        room_lower = room_type.lower().strip()
        det_lower = detector_type.lower().strip()

        if room_lower == "kitchen" and "smoke" in det_lower:
            return (
                True,
                f"PROHIBITED: Smoke detector ({detector_type}) in kitchen. "
                f"NFPA 72 §17.6.4 prohibits smoke detectors in kitchens due to "
                f"nuisance alarms from cooking. Use heat detector instead.",
            )

        return (False, "")

    @staticmethod
    def _build_room(room_dict: dict) -> Room:
        """Build a Room object from a dictionary.

        Calculates width/length from the bounding box of polygon_coords.
        This means L-shaped rooms are treated as their bounding rectangle
        (known limitation - see module docstring).

        Args:
            room_dict: Dictionary with keys:
                - polygon_coords: List of (x, y) corner tuples
                - name (optional): Room name
                - room_id (optional): Fallback for name
                - ceiling_height (optional, default 3.0m)

        Returns:
            Room object with computed width, length, and ceiling_height.

        """
        coords = room_dict["polygon_coords"]
        xs = [p[0] for p in coords]
        ys = [p[1] for p in coords]

        return Room(
            name=room_dict.get("name", room_dict.get("room_id", "")),
            width=max(xs) - min(xs),
            length=max(ys) - min(ys),
            ceiling_height=room_dict.get("ceiling_height", 3.0),
        )


if __name__ == "__main__":
    import sys

    sys.path.insert(0, ".")
    from density_optimizer import DensityOptimizer  # type: ignore[no-redef]

    opt = DensityOptimizer()
    analyser = FloorAnalyser(floor_id="test_floor", optimizer=opt)

    test_rooms = [
        {
            "room_id": "small_office_3x4",
            "name": "small_office",
            "polygon_coords": [(0, 0), (3, 0), (3, 4), (0, 4)],
            "ceiling_height": 3.0,
        },
        {
            "room_id": "kitchen_6x5",
            "name": "kitchen",
            "polygon_coords": [(0, 0), (6, 0), (6, 5), (0, 5)],
            "ceiling_height": 3.0,
        },
        {
            "room_id": "medium_office_10x8",
            "name": "medium_office",
            "polygon_coords": [(0, 0), (10, 0), (10, 8), (0, 8)],
            "ceiling_height": 3.0,
        },
        {
            "room_id": "stairwell_3x3",
            "name": "stairwell",
            "polygon_coords": [(0, 0), (3, 0), (3, 3), (0, 3)],
            "ceiling_height": 3.0,
        },
        {
            "room_id": "deep_narrow_4x30",
            "name": "deep_narrow",
            "polygon_coords": [(0, 0), (4, 0), (4, 30), (0, 30)],
            "ceiling_height": 3.0,
        },
        {
            "room_id": "large_hall_20x15",
            "name": "large_hall",
            "polygon_coords": [(0, 0), (20, 0), (20, 15), (0, 15)],
            "ceiling_height": 3.0,
        },
        {
            "room_id": "warehouse_30x25",
            "name": "warehouse",
            "polygon_coords": [(0, 0), (30, 0), (30, 25), (0, 25)],
            "ceiling_height": 3.0,
        },
        {
            "room_id": "open_plan_40x20",
            "name": "open_plan",
            "polygon_coords": [(0, 0), (40, 0), (40, 20), (0, 20)],
            "ceiling_height": 3.0,
        },
        {
            "room_id": "narrow_15x1.5",
            "name": "narrow_corridor",
            "polygon_coords": [(0, 0), (15, 0), (15, 1.5), (0, 1.5)],
            "ceiling_height": 3.0,
        },
        {
            "room_id": "corridor_20x2",
            "name": "corridor",
            "polygon_coords": [(0, 0), (20, 0), (20, 2), (0, 2)],
            "ceiling_height": 3.0,
        },
        {
            "room_id": "square_large_50x50",
            "name": "square_large",
            "polygon_coords": [(0, 0), (50, 0), (50, 50), (0, 50)],
            "ceiling_height": 3.0,
        },
        {
            "room_id": "giant_90x70",
            "name": "giant_90x70",
            "polygon_coords": [(0, 0), (90, 0), (90, 70), (0, 70)],
            "ceiling_height": 3.0,
        },
        {
            "room_id": "giant_98x50",
            "name": "giant_98x50",
            "polygon_coords": [(0, 0), (98, 0), (98, 50), (0, 50)],
            "ceiling_height": 3.0,
        },
        {
            "room_id": "long_line_50x1",
            "name": "long_line",
            "polygon_coords": [(0, 0), (50, 0), (50, 1), (0, 1)],
            "ceiling_height": 3.0,
        },
        {
            "room_id": "thin_line_1x50",
            "name": "thin_line",
            "polygon_coords": [(0, 0), (1, 0), (1, 50), (0, 50)],
            "ceiling_height": 3.0,
        },
    ]

    print("Testing FloorAnalyser V2.3 with 15 rooms...")
    report = analyser.analyse(test_rooms)

    print(f"\nFloor: {report.floor_id}")
    print(f"Total detectors: {report.total_detectors}")
    print(f"Total theoretical lower bound: {report.total_theoretical_lower_bound}")
    print(f"Fully compliant: {report.fully_compliant}")
    print(f"Safe to submit: {report.safe_to_submit}")
    print(f"Analysis time: {report.analysis_time_s:.2f}s")
    print(f"\nNon-compliant rooms: {report.non_compliant_rooms}")
    print(f"Unsafe rooms: {report.unsafe_rooms}")
    print(f"Warnings: {report.floor_warnings}")

    print(
        f"\n{'Room':<25} {'Dets':<5} {'LB':<4} {'Eff':<6} {'Cov%':<8} {'NFPA':<5} {'Proof':<5} {'Fallback':<8} {'Method':<15} {'Status':<10}"
    )
    print("-" * 105)
    for s in report.room_summaries:
        status = "PASS" if s.compliant else "FAIL"
        print(
            f"{s.name:<25} {s.detector_count:<5} {s.theoretical_lower_bound:<4} {s.efficiency_ratio:<6.2f} {s.coverage_pct:<8.2f} {s.nfpa_valid!s:<5} {s.proof_valid!s:<5} {s.fallback_used!s:<8} {s.method:<15} {status:<10}"
        )
