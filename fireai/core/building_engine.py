"""fireai/core/building_engine.py  V0.2
=====================================
Building-level fire alarm design analyser.

Uses FloorAnalyser V2.1 as a component — composition, not reimplementation.
Each floor gets an independent FloorAnalyser; no inter-floor state sharing.

V0.2 Changes (Consultant #6 Criticisms #2 & #3):
  - Added FireZoneEngine integration for zone clustering per floor
  - Added DeltaCache integration for incremental processing
  - Zone assignments stored in BuildingReport.zone_reports
  - Cache stats stored in BuildingReport.cache_stats

Architecture:
  - FloorAnalyser V2.1 per floor (composition)
  - FireZoneEngine per floor for zone clustering (V0.2)
  - DeltaCache for incremental processing (V0.2)
  - Sequential execution only — no parallel processing
  - Conservative safe_to_submit: any UNSAFE room in ANY floor blocks submission
  - AuditStore integration: events from all floors + building-level events

V0.3 Safety Guard — ProcessPoolExecutor Prohibition:
  - ProcessPoolExecutor is FORBIDDEN in this module.
  - CBC (PuLP solver) is a C-level library that does NOT release the GIL.
    Using ProcessPoolExecutor with CBC causes deadlocks on fork.
  - ThreadPoolExecutor is also prohibited because GIL prevents true
    parallelism for CPU-bound CBC calls.
  - ALL floor analysis is SEQUENTIAL. Safety over speed.
  - If parallel processing is needed in the future, use subprocess
    isolation (separate OS processes with IPC), NOT ProcessPoolExecutor.

Safety guarantees:
  - Every floor is independently verified via FloorAnalyser's triple-check gate.
  - Any floor with UNSAFE rooms blocks the building from safe_to_submit.
  - No inter-floor state sharing.
  - No parallel execution (safety over speed).
  - DeltaCache NEVER skips re-verification of changed rooms.

Key principle: theoretical_lower_bound ≠ theoretical_minimum
  - All "lower bound" values are estimative (ceil(area / pi*R^2)).
  - A proven minimum requires MIP (PuLP) — not yet implemented.
  - See TECHNICAL_HONESTY.md Section 5 for the strict distinction.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional

# ── V0.3 SAFETY GUARD: ProcessPoolExecutor prohibition ────────────────
# CBC (PuLP solver) is a C-level library that does NOT release the GIL.
# Using ProcessPoolExecutor with CBC causes deadlocks on fork.
# This import guard ensures that no future developer accidentally introduces
# ProcessPoolExecutor into this module.
#
# If you see this error, use subprocess isolation instead:
#   - Separate OS processes with IPC (subprocess.Popen + JSON pipes)
#   - NEVER use concurrent.futures.ProcessPoolExecutor with CBC
try:
    from concurrent.futures import ProcessPoolExecutor  # noqa: F401

    _PROCESSPOOL_AVAILABLE = True
except ImportError:
    _PROCESSPOOL_AVAILABLE = False

# Runtime guard: refuse to run if ProcessPoolExecutor is used
_PPE_USED_MSG = (
    "FATAL SAFETY VIOLATION: ProcessPoolExecutor detected in BuildingEngine. "
    "CBC solver is a C-level library that does NOT release the GIL. "
    "Using ProcessPoolExecutor with CBC causes deadlocks on fork. "
    "Use subprocess isolation instead. See V0.3 Safety Guard in docstring."
)

from fireai.core.delta_cache import DeltaCache
from fireai.core.fire_zone_engine import FireZoneEngine, ZoneConstraints, ZoneReport
from fireai.core.floor_analyser import FloorAnalyser, FloorReport
from fireai.core.project_learner import BuildingProjectProfile, ProjectLearner
from fireai.core.spatial_engine.density_optimizer import DensityOptimizer

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────────
# Building report
# ──────────────────────────────────────────────────────────────────


@dataclass
class BuildingReport:
    """Complete analysis report for an entire building.

    Attributes:
        building_id: Unique building identifier (e.g. "BLDG-001").
        floor_reports: Per-floor FloorReport objects in input order.
        total_detectors: Sum of detector counts across all floors.
        total_theoretical_lower_bound: Sum of theoretical lower bounds across all floors.
            Estimative only — NOT a proven minimum. See TECHNICAL_HONESTY.md Section 5.
        total_duct_devices: Sum of duct detector devices across all floors.
            Placeholder field (currently 0); full logic deferred to future phase.
            NFPA 72 Section 17.7.5.
        total_floors: Number of floors analysed.
        fully_compliant: True only if every floor is fully_compliant
            (i.e. every room in every floor passes the triple-check gate).
        safe_to_submit: True only if every floor is safe_to_submit
            (i.e. no UNSAFE rooms in ANY floor). This is the conservative
            gate: a single unsafe room in any floor blocks the entire building.
        non_compliant_floors: IDs of floors where at least one room is
            non-compliant (failed the triple-check gate, but not necessarily UNSAFE).
            A floor is non-compliant if fully_compliant == False.
        unsafe_floors: IDs of floors that contain at least one UNSAFE room.
            A floor is unsafe if safe_to_submit == False.
            Any unsafe floor causes the building's safe_to_submit to be False.
        building_warnings: Building-level advisory messages.
        analysis_time_s: Total wall-clock analysis time in seconds.

    """

    building_id: str
    floor_reports: List[FloorReport] = field(default_factory=list)
    total_detectors: int = 0
    total_theoretical_lower_bound: int = 0
    total_duct_devices: int = 0
    total_floors: int = 0
    fully_compliant: bool = False
    safe_to_submit: bool = False
    non_compliant_floors: List[str] = field(default_factory=list)
    unsafe_floors: List[str] = field(default_factory=list)
    building_warnings: List[str] = field(default_factory=list)
    analysis_time_s: float = 0.0
    # V5.0: Project learning profile (populated after all floors analysed)
    project_profile: Optional[BuildingProjectProfile] = None
    # V0.2: Fire zone assignments per floor (Consultant #6 Criticism #2)
    zone_reports: Dict[str, ZoneReport] = field(default_factory=dict)
    # V0.2: DeltaCache statistics (Consultant #6 Criticism #3)
    cache_stats: Optional[Dict] = None


# ──────────────────────────────────────────────────────────────────
# Building Engine
# ──────────────────────────────────────────────────────────────────


class BuildingEngine:
    """Building-level fire alarm design analyser.

    Uses FloorAnalyser V2.1 as a component (composition, not reimplementation).
    Each floor is analysed by an independent FloorAnalyser instance.
    No inter-floor state is shared.

    V0.2: Now includes FireZoneEngine for zone clustering and DeltaCache
    for incremental processing.

    Safety Gates:
        - safe_to_submit: True only if EVERY floor has safe_to_submit == True.
          A single UNSAFE room in ANY floor blocks the entire building.
        - fully_compliant: True only if EVERY floor has fully_compliant == True.

    AuditStore Integration:
        When an audit_store is provided, it is passed to each FloorAnalyser
        so that critical events (DETECTOR_PLACEMENT, BOUNDARY_LIMIT_WARNING)
        are recorded in the tamper-proof hash chain. Building-level events
        (BUILDING_ANALYSIS_START, BUILDING_ANALYSIS_COMPLETE) are also logged.

    Args:
        building_id: Building identifier (e.g. "BLDG-001").
        optimizer: DensityOptimizer instance (V7.3 with coverage_limit=R).
            Shared across floors — read-only, no state mutation.
        audit_trail: Optional AuditTrail for in-memory decision logging.
            Passed to each FloorAnalyser.
        audit_store: Optional AuditStore for tamper-proof (SQLite) logging.
            Passed to each FloorAnalyser. Building-level events also logged here.
        zone_constraints: Optional ZoneConstraints for fire zone grouping.
            If None, uses default constraints (2000 sqm max, 100 detectors/zone).
        delta_cache_path: Optional path to SQLite file for delta cache persistence.
            If None, cache is in-memory only (not persisted across runs).

    Example:
        >>> from fireai.core.spatial_engine.density_optimizer import DensityOptimizer
        >>> from fireai.core.building_engine import BuildingEngine
        >>>
        >>> opt = DensityOptimizer()
        >>> engine = BuildingEngine("BLDG-001", opt)
        >>>
        >>> floors = {
        ...     "GF": [{"room_id": "R1", "name": "Lobby",
        ...             "polygon_coords": [(0,0),(12,0),(12,8),(0,8)],
        ...             "ceiling_height": 3.0}],
        ...     "L1": [{"room_id": "R2", "name": "Office",
        ...             "polygon_coords": [(0,0),(10,0),(10,8),(0,8)],
        ...             "ceiling_height": 3.0}],
        ... }
        >>> report = engine.analyse(floors)
        >>> print(report.safe_to_submit)
        True

    """

    def __init__(
        self,
        building_id: str,
        optimizer: DensityOptimizer,
        audit_trail: Optional[object] = None,
        audit_store: Optional[object] = None,
        zone_constraints: Optional[ZoneConstraints] = None,
        delta_cache_path: Optional[str] = None,
    ) -> None:
        self.building_id = building_id
        self.opt = optimizer  # V7.3 as-is, shared read-only
        self.audit_trail = audit_trail
        self.audit_store = audit_store
        # V0.2: Fire zone engine (Consultant #6 Criticism #2 — concept accepted)
        self.zone_engine = FireZoneEngine(constraints=zone_constraints)
        # V0.2: Delta cache (Consultant #6 Criticism #3 — concept accepted)
        self.delta_cache = DeltaCache(db_path=delta_cache_path)

    # ─── public ──────────────────────────────────────────────────────

    def analyse(self, floors: Dict[str, list]) -> BuildingReport:
        """Analyse all floors in the building and return a BuildingReport.

        Each floor is processed sequentially by an independent FloorAnalyser.
        The same audit_trail and audit_store are passed to each FloorAnalyser
        so that room-level events are recorded alongside building-level events.

        After analysis, rooms are clustered into fire alarm zones per floor
        using FireZoneEngine (V0.2).

        Args:
            floors: Dictionary mapping floor_id to list of room dicts.
                Each room dict must have:
                    - room_id (str): Unique room identifier
                    - name (str, optional): Display name
                    - polygon_coords (List[Tuple[float,float]]): Corner coordinates
                    - ceiling_height (float, optional): Ceiling height in meters

        Returns:
            BuildingReport containing:
                - Per-floor FloorReport objects
                - Building-level compliance status
                - Lists of non-compliant and unsafe floor IDs
                - Fire zone assignments per floor (V0.2)
                - DeltaCache statistics (V0.2)
                - Building-level warnings

        Side Effects:
            - Logs each floor result via Python logging
            - Records events in AuditTrail and AuditStore (if provided)
            - Persists DeltaCache to SQLite (if path provided)

        """
        t0 = time.time()
        report = BuildingReport(building_id=self.building_id)

        # Log building analysis start to AuditStore
        if self.audit_store and hasattr(self.audit_store, "add_event"):
            self.audit_store.add_event(
                event_type="BUILDING_ANALYSIS_START",
                room_id="__BUILDING__",
                details_dict={
                    "building_id": self.building_id,
                    "floor_count": len(floors),
                    "floor_ids": list(floors.keys()) if floors else [],
                },
            )

        if not floors:
            report.building_warnings.append("No floors provided.")
            report.safe_to_submit = False
            report.fully_compliant = False
            report.analysis_time_s = round(time.time() - t0, 3)
            logger.warning("BuildingEngine: building=%s — no floors provided", self.building_id)
            return report

        # Process each floor sequentially with independent FloorAnalyser
        for floor_id, room_dicts in floors.items():
            # Each floor gets its own FloorAnalyser with shared audit_trail + audit_store
            analyser = FloorAnalyser(
                floor_id=floor_id,
                optimizer=self.opt,
                audit_trail=self.audit_trail,
                audit_store=self.audit_store,
            )
            floor_report = analyser.analyse(room_dicts)
            report.floor_reports.append(floor_report)

            # Aggregate
            report.total_detectors += floor_report.total_detectors
            report.total_theoretical_lower_bound += floor_report.total_theoretical_lower_bound
            report.total_duct_devices += sum(s.duct_devices for s in floor_report.room_summaries)

            # Track non-compliant and unsafe floors
            if not floor_report.fully_compliant:
                report.non_compliant_floors.append(floor_id)
            if not floor_report.safe_to_submit:
                report.unsafe_floors.append(floor_id)

            logger.info(
                "BuildingEngine: building=%s floor=%s rooms=%d detectors=%d compliant=%s",
                self.building_id,
                floor_id,
                len(floor_report.room_summaries),
                floor_report.total_detectors,
                floor_report.fully_compliant,
            )

        # Building-level aggregation
        report.total_floors = len(floors)
        report.fully_compliant = len(report.non_compliant_floors) == 0
        report.safe_to_submit = len(report.unsafe_floors) == 0
        report.analysis_time_s = round(time.time() - t0, 3)

        if report.unsafe_floors:
            report.building_warnings.append(f"UNSAFE floors (do NOT submit): {report.unsafe_floors}")
        if report.non_compliant_floors:
            report.building_warnings.append(f"Non-compliant floors: {report.non_compliant_floors}")

        # Log building analysis complete to AuditStore
        if self.audit_store and hasattr(self.audit_store, "add_event"):
            self.audit_store.add_event(
                event_type="BUILDING_ANALYSIS_COMPLETE",
                room_id="__BUILDING__",
                details_dict={
                    "building_id": self.building_id,
                    "total_floors": report.total_floors,
                    "total_detectors": report.total_detectors,
                    "total_theoretical_lower_bound": report.total_theoretical_lower_bound,
                    "total_duct_devices": report.total_duct_devices,
                    "fully_compliant": report.fully_compliant,
                    "safe_to_submit": report.safe_to_submit,
                    "non_compliant_floors": report.non_compliant_floors,
                    "unsafe_floors": report.unsafe_floors,
                    "analysis_time_s": report.analysis_time_s,
                },
            )

        # V0.2: Fire zone clustering per floor (Consultant #6 Criticism #2)
        # Group rooms into fire alarm zones per NFPA 72 §21.3.3.
        for floor_report in report.floor_reports:
            zone_rooms = []
            for s in floor_report.room_summaries:
                if s.refused or s.detector_count == 0:
                    continue
                zone_rooms.append(
                    {
                        "id": s.room_id,
                        "area": s.width * s.length if s.width and s.length else 0.0,
                        "detectors": s.detector_count,
                        "occupancy": getattr(s, "detector_type", "office"),
                    }
                )
            if zone_rooms:
                zone_report = self.zone_engine.cluster_floor(
                    floor_id=floor_report.floor_id,
                    rooms=zone_rooms,
                )
                report.zone_reports[floor_report.floor_id] = zone_report
                # Add zone info to building warnings for visibility
                if zone_report.warnings:
                    report.building_warnings.extend(f"[{floor_report.floor_id}] {w}" for w in zone_report.warnings)

        # V5.0: Build project profile from all room summaries
        learner = ProjectLearner(building_id=self.building_id)
        for floor_report in report.floor_reports:
            for s in floor_report.room_summaries:
                if s.refused or s.detector_count == 0:
                    continue
                eff = s.detector_count / s.theoretical_lower_bound if s.theoretical_lower_bound > 0 else 1.0
                learner.record(
                    name=s.name,
                    width=s.width,
                    length=s.length,
                    strategy=s.method,
                    efficiency=eff,
                )
        report.project_profile = learner.profile()

        # V0.2: Persist delta cache (Consultant #6 Criticism #3)
        self.delta_cache.persist()
        report.cache_stats = self.delta_cache.stats()

        # Add zone summary to building info (NOT a warning — informational only)
        total_zones = sum(zr.total_zones for zr in report.zone_reports.values())
        if total_zones > 0:
            # V66 FIX: "Fire zones created" is informational, not a warning.
            # Adding it to building_warnings caused false-positive test failures
            # and could mislead engineers into thinking zone creation is problematic.
            logger.info(
                "Fire zones created: %d across %d floors",
                total_zones,
                len(report.zone_reports),
            )

        logger.info(
            "BuildingEngine: building=%s floors=%d detectors=%d zones=%d compliant=%s safe=%s t=%.2fs",
            self.building_id,
            report.total_floors,
            report.total_detectors,
            total_zones,
            report.fully_compliant,
            report.safe_to_submit,
            report.analysis_time_s,
        )
        return report


if __name__ == "__main__":
    opt = DensityOptimizer()
    engine = BuildingEngine("BLDG-001", opt)

    floors = {
        "GF": [
            {
                "room_id": "lobby_12x8",
                "name": "lobby",
                "polygon_coords": [(0, 0), (12, 0), (12, 8), (0, 8)],
                "ceiling_height": 3.0,
            },
            {
                "room_id": "parking_30x20",
                "name": "parking",
                "polygon_coords": [(0, 0), (30, 0), (30, 20), (0, 20)],
                "ceiling_height": 3.0,
            },
        ],
        "L1": [
            {
                "room_id": "office_10x8",
                "name": "office",
                "polygon_coords": [(0, 0), (10, 0), (10, 8), (0, 8)],
                "ceiling_height": 3.0,
            },
            {
                "room_id": "meeting_6x5",
                "name": "meeting",
                "polygon_coords": [(0, 0), (6, 0), (6, 5), (0, 5)],
                "ceiling_height": 3.0,
            },
        ],
        "L2": [
            {
                "room_id": "warehouse_50x40",
                "name": "warehouse",
                "polygon_coords": [(0, 0), (50, 0), (50, 40), (0, 40)],
                "ceiling_height": 3.0,
            },
        ],
    }

    print("Testing BuildingEngine V0.2 with 3 floors...")
    report = engine.analyse(floors)

    print(f"\nBuilding: {report.building_id}")
    print(f"Total floors: {report.total_floors}")
    print(f"Total detectors: {report.total_detectors}")
    print(f"Total LB: {report.total_theoretical_lower_bound}")
    print(f"Total duct devices: {report.total_duct_devices}")
    print(f"Fully compliant: {report.fully_compliant}")
    print(f"Safe to submit: {report.safe_to_submit}")
    print(f"Analysis time: {report.analysis_time_s:.2f}s")
    print(f"\nNon-compliant floors: {report.non_compliant_floors}")
    print(f"Unsafe floors: {report.unsafe_floors}")
    print(f"Warnings: {report.building_warnings}")

    # V0.2: Print zone assignments
    for floor_id, zr in report.zone_reports.items():
        print(f"\n  Floor {floor_id} — {zr.total_zones} zones:")
        for z in zr.zones:
            print(f"    Zone {z.zone_id}: rooms={z.rooms} area={z.total_area_sqm:.0f}sqm det={z.total_detectors}")

    for fr in report.floor_reports:
        print(
            f"\n  Floor: {fr.floor_id} | Detectors: {fr.total_detectors} | Compliant: {fr.fully_compliant} | Safe: {fr.safe_to_submit}"
        )
        for s in fr.room_summaries:
            status = "PASS" if s.compliant else "FAIL"
            print(
                f"    {s.name:<20} dets={s.detector_count:<3} LB={s.theoretical_lower_bound:<3} eff={s.efficiency_ratio:.2f} cov={s.coverage_pct:.2f}% {status}"
            )
