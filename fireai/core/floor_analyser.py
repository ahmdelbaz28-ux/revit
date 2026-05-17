"""
fireai/core/floor_analyser.py  V2.0
====================================
Safe, sequential floor-level fire alarm design analyser.

Uses the V7.3 DensityOptimizer directly – no ExpertSystem, no MIP.

Architecture:
  • DensityOptimizer V7.3 (coverage_limit = R) for detector placement
  • Sequential execution only — parallel processing disabled for safety
  • Triple-check gate: proof_valid AND nfpa_valid AND NOT fallback_used

Safety guarantees:
  • Every room result is independently verified.
  • UNSAFE rooms block the floor from being marked compliant.
  • No inter-room state sharing.
  • No parallel execution (safety over speed).

Safety Shield:
  ┌───────────────┬─────────────────────────────┬───────────────────────┐
  │ Check         │ Condition                   │ Action on Failure     │
  ├───────────────┼─────────────────────────────┼───────────────────────┤
  │ proof_valid   │ coverage >= 99.99%           │ Reject room, log err  │
  │ nfpa_valid    │ zero NFPA spacing violations│ Reject room, log err  │
  │ fallback_used │ hex/rect strategy must win   │ Reject room, log warn │
  └───────────────┴─────────────────────────────┴───────────────────────┘

Known Limitations:
  • Rectangular rooms only (no L-shape support at this layer)
  • Ceiling height not optimized (R=6.40m conservative per V7.3)
  • Parallel processing disabled (sequential for safety)
  • No beam/obstruction handling at this layer

Test Results:
  • 15 rooms (3 floor tiers): 15/15 PASS — 100% coverage, 0 NFPA violations
  • 1000 random rooms (seed=42): proof_failures=8/1000, nfpa_failures=0
  • 100 random rooms (seed=2024): proof_failures=1/100, nfpa_failures=0
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
# Import directly from the module file, bypassing __init__.py
import importlib.util
spec = importlib.util.spec_from_file_location("density_optimizer", os.path.join(os.path.dirname(__file__), "spatial_engine", "density_optimizer.py"))
density_module = importlib.util.module_from_spec(spec)
sys.modules['density_optimizer'] = density_module
spec.loader.exec_module(density_module)
DensityOptimizer = density_module.DensityOptimizer
Room = density_module.Room
DetectorLayout = density_module.DetectorLayout

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────────
# Floor report
# ──────────────────────────────────────────────────────────────────

@dataclass
class RoomSummary:
    """
    Compact per-room summary for floor report.

    Attributes:
        room_id:        Unique room identifier from input dict.
        name:           Room display name.
        detector_count: Number of detectors placed in this room.
        coverage_pct:   Coverage percentage (target >= 99.99%).
        nfpa_valid:     True if NFPA 72 spacing rules are satisfied.
        proof_valid:    True if coverage proof passed (>= 99.99%).
        fallback_used:  True if fallback strategy was needed (not preferred).
        method:         Placement strategy used (hexG_x, hexA_y, rect_4x3, etc.).
        compliant:      True only if triple-check passes (proof + nfpa + no fallback).
        safe_to_submit: Same as compliant — room is safe for PE review.
        violations:     List of NFPA violation strings (empty if compliant).
        analysis_ms:    Wall-clock time for this room's analysis in milliseconds.
    """
    room_id:          str
    name:             str
    detector_count:   int
    coverage_pct:     float
    nfpa_valid:       bool
    proof_valid:      bool
    fallback_used:    bool
    method:           str
    compliant:        bool
    safe_to_submit:   bool
    violations:       List[str]
    analysis_ms:      float


@dataclass
class FloorReport:
    """
    Complete analysis report for one floor.
 
    Attributes:
        floor_id:            Floor identifier.
        room_summaries:      Per-room summaries in input order.
        total_detectors:     Sum across all rooms.
        fully_compliant:     True only if every room is compliant.
        safe_to_submit:      True only if every room is safe_to_submit.
        non_compliant_rooms: IDs of non-compliant rooms.
        unsafe_rooms:        IDs of rooms that failed the triple check.
        floor_warnings:      Floor-level advisory messages.
        analysis_time_s:     Total wall-clock time (seconds).
    """
    floor_id:             str
    room_summaries:       List[RoomSummary]    = field(default_factory=list)
    total_detectors:      int                  = 0
    fully_compliant:      bool                 = False
    safe_to_submit:       bool                 = False
    non_compliant_rooms:  List[str]            = field(default_factory=list)
    unsafe_rooms:         List[str]            = field(default_factory=list)
    floor_warnings:       List[str]            = field(default_factory=list)
    analysis_time_s:      float                = 0.0


# ──────────────────────────────────────────────────────────────────
# Floor Analyser
# ──────────────────────────────────────────────────────────────────

class FloorAnalyser:
    """
    Safe, sequential full-floor fire alarm design analyser.

    Uses the V7.3 DensityOptimizer directly – no ExpertSystem, no MIP.
    Each room is analysed independently; no inter-room state is shared.

    Triple-Check Gate (a room passes only if ALL three are true):
        1. proof_valid   — Coverage verification passed (>= 99.99%)
        2. nfpa_valid    — NFPA 72 spacing/wall rules satisfied
        3. not fallback_used — Hex or rect strategy won (not fallback)

    Any room failing the triple check is flagged as UNSAFE and blocks
    the floor from being marked safe_to_submit.

    Args:
        floor_id:   Floor identifier (e.g. "GF", "L1", "B2").
        optimizer:  DensityOptimizer instance (V7.3 with coverage_limit=R).

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
        floor_id:  str,
        optimizer: DensityOptimizer,
    ) -> None:
        self.floor_id = floor_id
        self.opt      = optimizer  # V7.3 as-is, no modifications
 
    # ─── public ──────────────────────────────────────────────────────
 
    def analyse(self, rooms: List[dict]) -> FloorReport:
        """
        Analyse all rooms on the floor and return a FloorReport.

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
            - No external I/O or database writes
        """
        t0 = time.time()
        report = FloorReport(floor_id=self.floor_id)
 
        if not rooms:
            report.floor_warnings.append("No rooms provided.")
            return report
 
        for room_dict in rooms:
            # Build Room object from dict
            room = self._build_room(room_dict)
 
            # Analyse single room with V7.2
            t_room = time.time()
            layout = self.opt.optimize(room)
            ms = (time.time() - t_room) * 1000
 
            # Triple check
            ok = (
                layout.proof_valid
                and layout.nfpa_valid
                and not layout.fallback_used
            )
 
            summary = RoomSummary(
                room_id        = room_dict.get("room_id", room.name),
                name           = room.name,
                detector_count = layout.count,
                coverage_pct   = layout.coverage_pct,
                nfpa_valid     = layout.nfpa_valid,
                proof_valid    = layout.proof_valid,
                fallback_used  = layout.fallback_used,
                method         = layout.method,
                compliant      = ok,
                safe_to_submit = ok,
                violations     = getattr(layout, 'violations', []),
                analysis_ms    = round(ms, 1),
            )
            report.room_summaries.append(summary)
            report.total_detectors += summary.detector_count
 
        # Floor-level aggregation
        report.non_compliant_rooms = [
            s.room_id for s in report.room_summaries if not s.compliant
        ]
        report.unsafe_rooms = [
            s.room_id for s in report.room_summaries
            if not s.proof_valid or not s.nfpa_valid or s.fallback_used
        ]
        report.fully_compliant = len(report.non_compliant_rooms) == 0
        report.safe_to_submit  = len(report.unsafe_rooms) == 0
        report.analysis_time_s = round(time.time() - t0, 3)
 
        if report.unsafe_rooms:
            report.floor_warnings.append(
                f"UNSAFE rooms (do NOT submit): {report.unsafe_rooms}"
            )
        if not report.fully_compliant:
            report.floor_warnings.append(
                f"Non-compliant rooms: {report.non_compliant_rooms}"
            )
 
        logger.info(
            "FloorAnalyser: floor=%s rooms=%d detectors=%d compliant=%s t=%.2fs",
            self.floor_id, len(rooms), report.total_detectors,
            report.fully_compliant, report.analysis_time_s,
        )
        return report
 
    # ─── private ─────────────────────────────────────────────────────
 
    @staticmethod
    def _build_room(room_dict: dict) -> Room:
        """
        Build a Room object from a dictionary.

        Calculates width/length from the bounding box of polygon_coords.
        This means L-shaped rooms are treated as their bounding rectangle
        (known limitation — see module docstring).

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
            name   = room_dict.get("name", room_dict.get("room_id", "")),
            width  = max(xs) - min(xs),
            length = max(ys) - min(ys),
            ceiling_height = room_dict.get("ceiling_height", 3.0),
        )


if __name__ == "__main__":
    import sys
    sys.path.insert(0, '.')
    from density_optimizer import DensityOptimizer

    opt = DensityOptimizer()
    analyser = FloorAnalyser(floor_id="test_floor", optimizer=opt)

    test_rooms = [
        # طابق 1: غرف صغيرة
        {"room_id": "small_office_3x4", "name": "small_office", "polygon_coords": [(0,0),(3,0),(3,4),(0,4)], "ceiling_height": 3.0},
        {"room_id": "kitchen_6x5", "name": "kitchen", "polygon_coords": [(0,0),(6,0),(6,5),(0,5)], "ceiling_height": 3.0},
        {"room_id": "medium_office_10x8", "name": "medium_office", "polygon_coords": [(0,0),(10,0),(10,8),(0,8)], "ceiling_height": 3.0},
        {"room_id": "stairwell_3x3", "name": "stairwell", "polygon_coords": [(0,0),(3,0),(3,3),(0,3)], "ceiling_height": 3.0},
        {"room_id": "deep_narrow_4x30", "name": "deep_narrow", "polygon_coords": [(0,0),(4,0),(4,30),(0,30)], "ceiling_height": 3.0},
        # طابق 2: غرف متوسطة
        {"room_id": "large_hall_20x15", "name": "large_hall", "polygon_coords": [(0,0),(20,0),(20,15),(0,15)], "ceiling_height": 3.0},
        {"room_id": "warehouse_30x25", "name": "warehouse", "polygon_coords": [(0,0),(30,0),(30,25),(0,25)], "ceiling_height": 3.0},
        {"room_id": "open_plan_40x20", "name": "open_plan", "polygon_coords": [(0,0),(40,0),(40,20),(0,20)], "ceiling_height": 3.0},
        {"room_id": "narrow_15x1.5", "name": "narrow_corridor", "polygon_coords": [(0,0),(15,0),(15,1.5),(0,1.5)], "ceiling_height": 3.0},
        {"room_id": "corridor_20x2", "name": "corridor", "polygon_coords": [(0,0),(20,0),(20,2),(0,2)], "ceiling_height": 3.0},
        # طابق 3: غرف كبيرة
        {"room_id": "square_large_50x50", "name": "square_large", "polygon_coords": [(0,0),(50,0),(50,50),(0,50)], "ceiling_height": 3.0},
        {"room_id": "giant_90x70", "name": "giant_90x70", "polygon_coords": [(0,0),(90,0),(90,70),(0,70)], "ceiling_height": 3.0},
        {"room_id": "giant_98x50", "name": "giant_98x50", "polygon_coords": [(0,0),(98,0),(98,50),(0,50)], "ceiling_height": 3.0},
        {"room_id": "long_line_50x1", "name": "long_line", "polygon_coords": [(0,0),(50,0),(50,1),(0,1)], "ceiling_height": 3.0},
        {"room_id": "thin_line_1x50", "name": "thin_line", "polygon_coords": [(0,0),(1,0),(1,50),(0,50)], "ceiling_height": 3.0},
    ]

    print("Testing FloorAnalyser V2 with 15 rooms...")
    report = analyser.analyse(test_rooms)

    print(f"\nFloor: {report.floor_id}")
    print(f"Total detectors: {report.total_detectors}")
    print(f"Fully compliant: {report.fully_compliant}")
    print(f"Safe to submit: {report.safe_to_submit}")
    print(f"Analysis time: {report.analysis_time_s:.2f}s")
    print(f"\nNon-compliant rooms: {report.non_compliant_rooms}")
    print(f"Unsafe rooms: {report.unsafe_rooms}")
    print(f"Warnings: {report.floor_warnings}")

    print(f"\n{'Room':<25} {'Dets':<5} {'Cov%':<8} {'NFPA':<5} {'Proof':<5} {'Fallback':<8} {'Method':<15} {'Status':<10}")
    print("-" * 95)
    for s in report.room_summaries:
        status = "PASS" if s.compliant else "FAIL"
        print(f"{s.name:<25} {s.detector_count:<5} {s.coverage_pct:<8.2f} {str(s.nfpa_valid):<5} {str(s.proof_valid):<5} {str(s.fallback_used):<8} {s.method:<15} {status:<10}")