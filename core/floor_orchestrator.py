"""
floor_orchestrator.py — FireAI V5.1.0
CRITICAL SAFETY:
  1. SSOT: meta from engine.solve() is the ONLY source of truth.
  2. Sequential: No threads — PuLP is not thread-safe.
  3. Fail-Fast: RuntimeError from PuLP/Shapely STOPS everything.
"""

from dataclasses import dataclass, field
from typing import List, Tuple, Optional
import time
import logging

from nfpa72_models import RoomSpec, NFPAComplianceError
from nfpa72_coverage import verify_full_coverage
from spatial_engine.mip_solver import OptimalMIPEngine

logger = logging.getLogger("fireai.orchestrator")


@dataclass
class RoomResult:
    room_id: str
    status: str
    radius_m: Optional[float] = None
    spacing_m: Optional[float] = None
    geometry: Optional[str] = None
    detector_count: int = 0
    detector_positions: List[Tuple[float, float]] = field(default_factory=list)
    coverage_pct: float = 0.0
    worst_case_distance_m: float = 0.0
    solve_time_s: float = 0.0
    warnings: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    audit_notes: List[str] = field(default_factory=list)


@dataclass
class FloorResult:
    project_name: str
    source_dxf: str
    total_rooms: int
    room_results: List[RoomResult] = field(default_factory=list)
    rooms_passed: int = 0
    rooms_failed: int = 0
    rooms_errored: int = 0
    total_detectors: int = 0
    total_time_s: float = 0.0
    status: str = "UNKNOWN"
    disclaimer: str = (
        "This report is produced by FireAI V5.1.0. "
        "It MUST be reviewed by a licensed fire protection engineer. "
        "All calculations reference NFPA 72 (2022 Edition)."
    )

    def compute(self):
        self.rooms_passed = sum(1 for r in self.room_results if r.status == "PASS")
        self.rooms_failed = sum(1 for r in self.room_results if r.status == "FAIL")
        self.rooms_errored = sum(1 for r in self.room_results if r.status == "ERROR")
        self.total_detectors = sum(r.detector_count for r in self.room_results)
        self.total_time_s = sum(r.solve_time_s for r in self.room_results)
        if self.rooms_errored == 0 and self.rooms_failed == 0:
            self.status = "PASS"
        elif self.rooms_passed == 0:
            self.status = "FAIL"
        else:
            self.status = "PARTIAL"


class FloorOrchestrator:
    """
    CRITICAL RULES:
    1. New Engine for EVERY room.
    2. meta from engine.solve() is SSOT.
    3. RuntimeError FAILS FAST — stops everything.
    """

    def __init__(self, grid_res: float = 0.25):
        self.grid_res = grid_res

    def process(self, room_specs: List[RoomSpec],
                project_name: str = "", source_dxf: str = "") -> FloorResult:
        logger.info(f"Processing: {project_name} ({len(room_specs)} rooms)")

        result = FloorResult(
            project_name=project_name,
            source_dxf=source_dxf,
            total_rooms=len(room_specs),
        )

        for spec in room_specs:
            room_res = self._process_one_room(spec)
            result.room_results.append(room_res)
            logger.info(f"  {spec.room_id}: {room_res.status}")

        result.compute()
        return result

    def _process_one_room(self, spec: RoomSpec) -> RoomResult:
        start = time.monotonic()
        result = RoomResult(room_id=spec.room_id, status="FAIL")

        try:
            # [1] NEW Engine for every room — no shared state
            engine = OptimalMIPEngine(spec)

            # [2] Solve — SSOT from meta
            positions, count, ok, meta = engine.solve()

            if not ok:
                result.errors.append("MIP Solver failed to find optimal solution")
                result.solve_time_s = round(time.monotonic() - start, 3)
                return result

            # [3] Verify coverage — using meta ONLY (SSOT)
            coverage = verify_full_coverage(
                room_polygon=spec.polygon,
                detector_positions=positions,
                coverage_geometry=meta["coverage_geometry"],
                detector_radius=meta["radius_m"],
                listed_spacing_m=meta["spacing_m"],
                grid_resolution_m=self.grid_res,
            )

            # [4] Build result from meta + coverage
            result.status = "PASS" if coverage["compliance_status"] == "PASS" else "FAIL"
            result.radius_m = meta["radius_m"]
            result.spacing_m = meta["spacing_m"]
            result.geometry = meta["coverage_geometry"]
            result.detector_count = count
            result.detector_positions = positions
            result.coverage_pct = coverage["coverage_percentage"]
            result.worst_case_distance_m = coverage["worst_case_distance_m"]
            result.audit_notes = meta.get("audit_notes", [])

            if result.status == "FAIL":
                result.errors.append(
                    f"Coverage failed: {coverage['coverage_percentage']}%"
                )

        except (NFPAComplianceError, InvalidInputError) as e:
            # Logic errors → convert to ERROR result
            result.status = "ERROR"
            result.errors.append(str(e))

        except Exception as e:
            # CRITICAL: RuntimeError from PuLP/Shapely → STOP EVERYTHING
            logger.critical(
                f"SYSTEM ERROR in {spec.room_id}: {type(e).__name__}: {e}"
            )
            raise  # FAIL FAST — do not continue with corrupted environment

        finally:
            result.solve_time_s = round(time.monotonic() - start, 3)

        return result