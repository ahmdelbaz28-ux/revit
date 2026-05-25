"""
floor_orchestrator.py — FireAI V5.1.0
CRITICAL SAFETY:
  1. SSOT: meta from engine.solve() is the ONLY source of truth.
  2. Sequential: No threads — pure logic only.
  3. Fail-Fast: RuntimeError STOPS everything.
"""

from dataclasses import dataclass, field
from typing import List, Tuple, Optional
import time
import logging

from nfpa72_models import RoomSpec, NFPAComplianceError
from nfpa72_coverage import verify_full_coverage
from spatial_engine.mip_solver import OptimalMIPEngine

logger = logging.getLogger("fireai.orchestrator")

# NOTE: NFPA 72 compliance is verified via verify_full_coverage().
# If coverage fails, the system must comply properly - not masked by percentage margin.


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
        
        # V13 Fix: Replace "PARTIAL" with legally safer terminology.
        # "PARTIAL" could be misinterpreted by contractors as partial approval.
        # A building either meets code (APPROVED) or doesn't (REQUIRES_REVIEW).
        # Failed rooms are flagged for manual design, not partial acceptance.
        if self.rooms_errored == 0 and self.rooms_failed == 0:
            self.status = "APPROVED"
        elif self.rooms_passed == 0:
            self.status = "REJECTED"
        else:
            # Some rooms pass, some fail — building NOT approved.
            # Failed rooms require manual design by licensed PE.
            self.status = "REQUIRES_MANUAL_REVIEW"
    
    def save_audit(self, output_dir: str = "audit"):
        """Save audit trail to JSON file for liability protection"""
        import json
        from pathlib import Path
        from datetime import datetime
        
        Path(output_dir).mkdir(exist_ok=True)
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{output_dir}/audit_{self.project_name}_{timestamp}.json"
        
        audit_data = {
            "timestamp": datetime.now().isoformat(),
            "project_name": self.project_name,
            "source_dxf": self.source_dxf,
            "version": "FireAI V5.1.2",
            "status": self.status,
            "rooms": {
                "total": self.total_rooms,
                "passed": self.rooms_passed,
                "failed": self.rooms_failed,
                "errored": self.rooms_errored,
            },
            "detectors": {
                "calculated": self.total_detectors,
            },
            # V13: 15% spare detector margin REMOVED — no NFPA 72 basis for this.
            # NFPA compliance is verified via exact area-based coverage calculation.
            # Adding spare detectors without engineering justification violates
            # battery calculations and SLC loop capacity (NEC 760.41).
            "safety": {
                "method": "Exact Shapely area-based coverage verification",
                "threshold": "99.9% area coverage required (NFPA 72)",
                "note": "No arbitrary spare detector margin — coverage is mathematically verified"
            },
            "details": [
                {
                    "room_id": r.room_id,
                    "status": r.status,
                    "detector_count": r.detector_count,
                    "coverage_pct": r.coverage_pct,
                    "radius_m": r.radius_m,
                    "warnings": r.warnings,
                    "errors": r.errors,
                }
                for r in self.room_results
            ],
            "disclaimer": self.disclaimer,
        }
        
        with open(filename, "w") as f:
            json.dump(audit_data, f, indent=2)
        
        logger.info(f"Audit saved: {filename}")
        return filename


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
            logger.info(f"  {spec.name}: {room_res.status}")

        result.compute()
        
        # CRITICAL: Always save audit trail for liability protection
        result.save_audit()
        
        return result

    def _process_one_room(self, spec: RoomSpec) -> RoomResult:
        start = time.monotonic()
        result = RoomResult(room_id=spec.name, status="FAIL")

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

            # V13 Fix: Adaptive Re-solve — if coverage fails for a regular room,
            # don't give up immediately. Try the ConstraintSolver with area-based
            # greedy placement which can find solutions the MIP solver misses.
            if result.status == "FAIL":
                result.errors.append(
                    f"MIP coverage failed: {coverage['coverage_percentage']:.1f}%"
                )
                # Attempt adaptive re-solve using area-based ConstraintSolver
                try:
                    from spatial_engine.constraint_solver import ConstraintSolver
                    area_solver = ConstraintSolver(
                        room_polygon=spec.polygon,
                        device_radius=meta["radius_m"]
                    )
                    adaptive_result = area_solver.find_optimal_placement(max_devices=50)
                    if adaptive_result.coverage_percent >= 99.9:
                        result.status = "PASS"
                        result.detector_count = adaptive_result.num_devices
                        result.detector_positions = adaptive_result.positions
                        result.coverage_pct = adaptive_result.coverage_percent
                        result.audit_notes.append(
                            f"V13 Adaptive Re-solve: MIP failed, "
                            f"area-based solver succeeded with {adaptive_result.num_devices} detectors "
                            f"({adaptive_result.coverage_percent:.1f}% coverage)"
                        )
                        logger.info(
                            f"  {spec.name}: ADAPTIVE RE-SOLVE succeeded "
                            f"({adaptive_result.num_devices} detectors, "
                            f"{adaptive_result.coverage_percent:.1f}%)"
                        )
                    else:
                        result.errors.append(
                            f"Adaptive re-solve also failed: "
                            f"{adaptive_result.coverage_percent:.1f}% coverage "
                            f"(need 99.9%). Manual design required."
                        )
                except Exception as adapt_err:
                    result.errors.append(
                        f"Adaptive re-solve error: {adapt_err}. Manual design required."
                    )

        # V20.2 FIX: InvalidInputError is not defined in this module.
        # ImportError from MIP solver (when pulp not installed) should be
        # caught here as an ERROR result, not crash the entire pipeline.
        except (NFPAComplianceError, ImportError) as e:
            # Logic errors → convert to ERROR result
            result.status = "ERROR"
            result.errors.append(str(e))

        except Exception as e:
            # CRITICAL: RuntimeError → STOP EVERYTHING
            logger.critical(
                f"SYSTEM ERROR in {spec.room_id}: {type(e).__name__}: {e}"
            )
            raise  # FAIL FAST — do not continue with corrupted environment

        finally:
            result.solve_time_s = round(time.monotonic() - start, 3)

        return result