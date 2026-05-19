"""
floor_orchestrator.py — FireAI V10 with Audit Integration
CRITICAL SAFETY:
  1. SSOT: meta from engine.solve() is the ONLY source of truth.
  2. Sequential: No threads — pure logic only.
  3. Fail-Fast: RuntimeError STOPS everything.
"""

from dataclasses import dataclass, field
from typing import List, Tuple, Optional
import time
import logging

from .audit_trail import AuditTrail
from .nfpa72_models import RoomSpec, NFPAComplianceError
from .nfpa72_coverage import verify_full_coverage
from .spatial_engine.density_optimizer import DensityOptimizer, Room

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
        
        if self.rooms_errored == 0 and self.rooms_failed == 0:
            self.status = "PASS"
        elif self.rooms_passed == 0:
            self.status = "FAIL"
        else:
            self.status = "PARTIAL"
    
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
            # NOTE: Safety margin removed - NFPA 72 compliance via verify_full_coverage()
            # Uncomment to enable:
            # "with_safety_margin": math.ceil(self.total_detectors * 1.15),
            "safety": {
                "note": "NFPA 72 compliance verified via verify_full_coverage()"
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

    def __init__(self, grid_res: float = 0.25, audit_trail: Optional[AuditTrail] = None):
        self.grid_res = grid_res
        self.audit_trail = audit_trail

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
            
            # Log each room to audit trail if available
            if self.audit_trail:
                self.audit_trail.log_placement(
                    room_id=spec.room_id,
                    detector_count=room_res.detector_count,
                    detector_type=room_res.detector_type,
                    coverage_pct=room_res.coverage_percentage,
                    positions=room_res.detector_positions
                )

        result.compute()
        
        # CRITICAL: Always save audit trail for liability protection
        result.save_audit()
        
        return result

    def _process_one_room(self, spec: RoomSpec) -> RoomResult:
        start = time.monotonic()
        result = RoomResult(room_id=spec.name, status="FAIL")

        try:
            # [1] NEW Engine for every room — no shared state
            # Use DensityOptimizer V6 with hexagonal placement strategies
            room_data = Room(
                name=spec.name,
                width=spec.width_m,
                length=spec.length_m,
                ceiling_height=spec.ceiling_height_m or 3.0
            )
            optimizer = DensityOptimizer()
            layout = optimizer.optimize(room_data)

            # [2] Build result from layout
            positions = layout.detectors
            count = layout.count

            # Verify coverage
            coverage = verify_full_coverage(
                room_polygon=spec.polygon,
                detector_positions=positions,
                coverage_geometry="circular",
                detector_radius=optimizer.R,
                listed_spacing_m=optimizer.max_spacing,
                grid_resolution_m=self.grid_res,
            )

            # [3] Build result from layout + coverage
            result.status = "PASS" if coverage["compliance_status"] == "PASS" else "FAIL"
            result.radius_m = optimizer.R
            result.spacing_m = optimizer.max_spacing
            result.geometry = "circular"
            result.detector_count = count
            result.detector_positions = positions
            result.coverage_pct = coverage["coverage_percentage"]
            result.worst_case_distance_m = coverage["worst_case_distance_m"]

            if result.status == "FAIL":
                result.errors.append(
                    f"Coverage failed: {coverage['coverage_percentage']}%"
                )

        except (NFPAComplianceError, InvalidInputError) as e:
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