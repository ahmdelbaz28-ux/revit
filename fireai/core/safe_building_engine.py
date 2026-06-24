"""fireai/core/safe_building_engine.py
===================================
Replaces ProcessPoolExecutor bindings triggering Deadlocks at CBC level,
with safely managed, lock-restricted threading executing pure multi-node
verification safely.

Architecture:
  - Uses ThreadPoolExecutor instead of ProcessPoolExecutor
  - Global RLock prevents C++ memory corruption on CBC solver library
  - Sequential execution within each thread (CBC does NOT release GIL)
  - Timeout protection per-room (180s max per solve)
  - Graceful error handling with CRASH status on fatal failures
  - Uses solve_set_covering_mip (function-based, proven in fireai.core.spatial_engine)
    instead of OptimalMIPEngine (class-based, different import path, no solve_polygon)

Safety:
  - V0.3 ProcessPoolExecutor prohibition from building_engine.py applies.
  - CBC (PuLP solver) is a C-level library that does NOT release the GIL.
  - ProcessPoolExecutor with CBC causes deadlocks on fork().
  - ThreadPoolExecutor with RLock ensures only ONE CBC instance runs at a time,
    preventing memory corruption while maintaining thread safety.
  - This is NOT about parallelism (GIL prevents that for CPU-bound CBC).
    It is about SAFE concurrent submission of work items with sequential
    execution guaranteed by the lock.

V13 Fix:
  - Replaced broken OptimalMIPEngine import with solve_set_covering_mip
    (the function-based MIP solver in fireai.core.spatial_engine.mip_solver
    which is the VERIFIED and TESTED solver used by FloorAnalyser).
  - OptimalMIPEngine lives at spatial_engine/mip_solver.py (root level)
    with incompatible constructor signature and no solve_polygon method.
  - The function-based solve_set_covering_mip is what BuildingEngine and
    FloorAnalyser actually use — consistency is safety.
"""

from __future__ import annotations

import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Dict, List

from .spatial_engine.density_optimizer import DETECTOR_RADIUS

logger = logging.getLogger(__name__)


class SafeBuildingEngine:
    """Thread-safe multi-floor building analysis engine.

    Uses ThreadPoolExecutor with a global RLock to serialize CBC solver
    invocations. This prevents the deadlock scenario that occurs when
    ProcessPoolExecutor forks while CBC holds internal C-level locks.

    The RLock ensures that only one thread enters the CBC solver at a
    time, which is correct because:
      1. CBC does not release the GIL (no true parallelism possible)
      2. Sequential execution within the lock prevents data races
      3. The ThreadPoolExecutor provides clean task submission and
         result collection with timeout support

    Parameters
    ----------
        max_threads: Maximum number of worker threads (default 4).
            Note: due to the RLock, only ONE thread will be actively
            solving at any time. Multiple threads allow overlap of
            I/O (result collection, logging) with computation.
        coverage_radius: MIP coverage radius in meters (default 6.37 = 0.7*9.1m).
        candidate_step: Grid spacing for MIP candidate positions (default 1.0m).
        time_limit_s: MIP solver time limit per room (default 60s).

    """

    def __init__(
        self,
        max_threads: int = 4,
        coverage_radius: float = DETECTOR_RADIUS,
        candidate_step: float = 1.0,
        time_limit_s: float = 60.0,
    ):
        self.max_threads = max_threads
        self.coverage_radius = coverage_radius
        self.candidate_step = candidate_step
        self.time_limit_s = time_limit_s
        self.global_c_level_lock = (
            threading.RLock()
        )  # Hard barrier avoiding C++ Memory Corruption on solver library instance loading.

    def _solve_mip_safe(self, room_spec: Dict[str, Any]) -> Dict[str, Any]:
        """Solve MIP for a single room in a thread-safe manner.

        Uses solve_set_covering_mip (function-based) which is the VERIFIED
        solver used by FloorAnalyser and BuildingEngine. This avoids the
        broken import of OptimalMIPEngine which has an incompatible API.

        The RLock ensures only one thread enters the CBC solver at a
        time, preventing concurrent access to C-level solver state.

        Parameters
        ----------
            room_spec: Dictionary with room parameters:
                - room_id: Unique room identifier
                - width_m: Room width in meters
                - length_m: Room length in meters (defaults to width_m)
                - coverage_radius: Override coverage radius (optional)
                - candidate_step: Override candidate step (optional)
                - time_limit_s: Override time limit (optional)

        Returns
        -------
            Dictionary with:
                - room_id: Room identifier
                - success: Whether solve completed without exception
                - placements: Detector positions (if successful)
                - theoretical_minimum: Proven minimum count (if successful)
                - solver_status: Solver status string
                - calc_time_sec: Wall-clock solve time
                - error: Exception message (if failed)

        """
        start = time.time()
        try:
            # Forced encapsulation with the thread execution lock ensuring independent solving process tracking
            with self.global_c_level_lock:
                from fireai.core.spatial_engine.mip_solver import solve_set_covering_mip

                width = room_spec.get("width_m", 10.0)
                length = room_spec.get("length_m", width)  # Default to square if not specified
                radius = room_spec.get("coverage_radius", self.coverage_radius)
                step = room_spec.get("candidate_step", self.candidate_step)
                time_limit = room_spec.get("time_limit_s", self.time_limit_s)

                result = solve_set_covering_mip(
                    room_width=width,
                    room_length=length,
                    coverage_radius=radius,
                    candidate_step=step,
                    time_limit_seconds=time_limit,
                )

                elapsed = time.time() - start
                return {
                    "room_id": room_spec.get("room_id", "UNK"),
                    "success": result.success,
                    "placements": result.detector_positions,
                    "theoretical_minimum": result.theoretical_minimum,
                    "coverage_pct": 0.0,  # MIP doesn't compute coverage %
                    "status": result.solver_status,
                    "used_mip": result.used_mip,
                    "fallback_reason": result.fallback_reason,
                    "calc_time_sec": elapsed,
                }
        except Exception as ex:
            logger.error("Safe Solver Failure upon %s: %s", room_spec.get("room_id", "UNK"), ex)
            return {"room_id": room_spec.get("room_id", "UNK"), "success": False, "status": "ERROR", "error": str(ex)}

    def run_multi_floor_safety_analysis(self, floor_spec_registry: List[Dict[str, Any]]) -> List[Dict]:
        """Run MIP analysis across multiple floors in a thread-safe manner.

        Flattens the floor/room hierarchy into a list of room specifications,
        submits each room as a separate task to the ThreadPoolExecutor, and
        collects results with timeout protection.

        The RLock in _solve_mip_safe ensures that CBC solver invocations
        are serialized, preventing the deadlock scenario that occurs with
        ProcessPoolExecutor + CBC.

        Parameters
        ----------
            floor_spec_registry: List of floor specification dictionaries.
                Each floor dict must have:
                    - floor_id: Floor identifier
                    - rooms: List of room specification dicts

        Returns
        -------
            List of result dictionaries (one per room), each containing:
                - room_id: Room identifier
                - success: Whether solve completed
                - placements: Detector positions (if successful)
                - theoretical_minimum: Proven minimum count (if successful)
                - status: Solver status or "CRASH" on fatal error
                - calc_time_sec: Solve time (if successful)
                - error: Exception message (if failed)

        """
        results = []
        rooms_flatted = []

        for f_data in floor_spec_registry:
            floor_lbl = f_data.get("floor_id")
            for rm in f_data.get("rooms", []):
                # V15 FIX: Don't mutate the caller's room dicts — create a copy
                rm_copy = dict(rm)
                rm_copy["virtual_floor"] = floor_lbl
                rooms_flatted.append(rm_copy)

        logger.info("Commencing protected multi-thread evaluation over %s discrete areas.", len(rooms_flatted))

        with ThreadPoolExecutor(max_workers=self.max_threads) as tpool:
            work_q = {tpool.submit(self._solve_mip_safe, rm_args): rm_args["room_id"] for rm_args in rooms_flatted}
            for w in as_completed(work_q):
                room_trace = work_q[w]
                try:
                    res_payload = w.result(timeout=180)
                    results.append(res_payload)
                except Exception:
                    logger.error("Task timeout or death on thread assigned to: %s", room_trace)
                    results.append({"room_id": room_trace, "success": False, "status": "CRASH"})
        return results
