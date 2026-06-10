"""
floor_orchestrator.py — FireAI V20.2 with Audit Integration
CRITICAL SAFETY:
  1. SSOT: meta from engine.solve() is the ONLY source of truth.
  2. Sequential: No threads — pure logic only.
  3. Fail-Fast: RuntimeError STOPS everything.
"""

import logging
import time
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

from .audit_trail import AuditTrail
from .nfpa72_coverage import verify_full_coverage
from .nfpa72_models import NFPAComplianceError, RoomSpec
from .spatial_engine.density_optimizer import DETECTOR_RADIUS, MAX_SPACING_M, DensityOptimizer, Room


# CRITICAL FIX: InvalidInputError was caught but never imported or defined.
# Define it locally to prevent NameError at runtime.
class InvalidInputError(ValueError):
    """Raised when room input is invalid."""

    pass


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
        "This report is produced by FireAI V20.2. "
        "It MUST be reviewed by a licensed fire protection engineer. "
        "All calculations reference NFPA 72 (2022 Edition)."
    )

    def compute(self):
        self.rooms_passed = sum(1 for r in self.room_results if r.status == "PASS")
        self.rooms_failed = sum(1 for r in self.room_results if r.status == "FAIL")
        self.rooms_errored = sum(1 for r in self.room_results if r.status == "ERROR")
        self.total_detectors = sum(r.detector_count for r in self.room_results)
        self.total_time_s = sum(r.solve_time_s for r in self.room_results)

        # V50 FIX: Guard against empty room list producing false APPROVED.
        # If no rooms were processed (e.g., empty DXF, parser failure), the
        # building should NOT be marked as APPROVED — no rooms were actually
        # verified. An empty "APPROVED" report is a false compliance claim.
        if self.total_rooms == 0:
            self.status = "ERROR"
        # V13 Fix: Replace "PARTIAL" with legally safer terminology.
        # "PARTIAL" could be misinterpreted by contractors as partial approval.
        # A building either meets code (APPROVED) or doesn't (REQUIRES_REVIEW).
        # V76 HIGH-03 FIX: Added ERROR status for all-errored buildings.
        # When every room has status ERROR, the building was NOT analyzed —
        # labeling it "REJECTED" implies analysis found non-compliance, which
        # is misleading. "ERROR" correctly signals the system failed to process.
        elif self.rooms_errored == 0 and self.rooms_failed == 0:
            self.status = "APPROVED"
        elif self.rooms_errored > 0 and self.rooms_passed == 0 and self.rooms_failed == 0:
            self.status = "ERROR"
        elif self.rooms_passed == 0:
            self.status = "REJECTED"
        else:
            self.status = "REQUIRES_MANUAL_REVIEW"

        # V50 FIX: Validate room count integrity — if passed+failed+errored
        # doesn't equal total, some rooms have unrecognized status strings.
        # This guards against future code changes that introduce new statuses
        # without updating this method.
        counted = self.rooms_passed + self.rooms_failed + self.rooms_errored
        if counted != self.total_rooms and self.total_rooms > 0:
            import logging

            logging.getLogger(__name__).error(
                f"Room count mismatch: {counted} counted vs {self.total_rooms} total. "
                f"Some rooms have unrecognized status — downgrading to ERROR."
            )
            self.status = "ERROR"

    def save_audit(self, output_dir: str = "audit"):
        """Save audit trail to JSON file for liability protection"""
        import json
        import re
        from datetime import datetime, timezone
        from pathlib import Path

        Path(output_dir).mkdir(exist_ok=True)

        # V FIX: Sanitize project_name to prevent path traversal.
        # In a life-safety system, audit trail integrity is paramount.
        # An attacker could inject "../../etc/crontab" as project_name
        # to write arbitrary files, or overwrite previous audit trails
        # to cover up compliance failures.
        safe_name = re.sub(r'[^A-Za-z0-9_\-]', '_', self.project_name)
        if safe_name != self.project_name:
            logger.warning(f"project_name sanitized for path safety: '{self.project_name}' -> '{safe_name}'")

        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")  # V54 FIX (AUDIT-012): UTC
        filename = f"{output_dir}/audit_{safe_name}_{timestamp}.json"

        # V FIX: Verify resolved path stays within output_dir (path traversal guard)
        resolved_path = Path(filename).resolve()
        resolved_dir = Path(output_dir).resolve()
        if not str(resolved_path).startswith(str(resolved_dir)):
            logger.critical(f"Path traversal blocked: '{filename}' resolves outside '{output_dir}'")
            filename = f"{output_dir}/audit_SANITIZED_{timestamp}.json"

        audit_data = {
            "timestamp": datetime.now(timezone.utc).isoformat(),  # V54 FIX (AUDIT-012): UTC
            "project_name": self.project_name,
            "source_dxf": self.source_dxf,
            "version": "FireAI V20.2",
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
            "safety": {
                "method": "Exact Shapely area-based coverage verification",
                "threshold": "99.9% area coverage required (NFPA 72)",
                "note": "No arbitrary spare detector margin — coverage is mathematically verified",
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

    def process(self, room_specs: List[RoomSpec], project_name: str = "", source_dxf: str = "") -> FloorResult:
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
                    detector_type=spec.detector_type.value if spec.detector_type else "UNKNOWN",
                    coverage_pct=room_res.coverage_pct,
                    positions=room_res.detector_positions,
                )

        result.compute()

        # CRITICAL: Always save audit trail for liability protection
        result.save_audit()

        return result

    def _process_one_room(self, spec: RoomSpec) -> RoomResult:
        start = time.monotonic()
        result = RoomResult(room_id=spec.name, status="FAIL")

        # V111 CRITICAL: Skip rooms with unresolved geometry.
        # Running NFPA analysis on fabricated geometry produces FALSE compliance
        # results — a building could be signed off as "protected" when it is NOT.
        if getattr(spec, "geometry_unresolved", False):
            import logging

            logging.getLogger(__name__).critical(
                "Room '%s' has unresolved geometry — SKIPPING NFPA analysis. "
                "Compliance results would be INVALID. "
                "Resolve IFC geometry before running analysis.",
                spec.name,
            )
            result.status = "REQUIRES_MANUAL_REVIEW"
            # V76 HIGH-02 FIX: Changed result.violations to result.errors.
            # RoomResult dataclass has no 'violations' field — only 'errors: List[str]'.
            # Dynamic attribute would be invisible to serialization and downstream checks.
            result.errors.append(
                "IFC_GEOMETRY_UNRESOLVED (CRITICAL): "
                f"Room '{spec.name}' has no valid geometry — "
                "NFPA analysis cannot proceed. "
                "Resolve IFC geometry extraction before analysis."
            )
            return result

        try:
            # [1] NEW Engine for every room — no shared state
            # Use DensityOptimizer V6 with hexagonal placement strategies
            # CRITICAL FIX: RoomSpec has depth_m not length_m,
            # and ceiling_spec not ceiling_height_m.
            # V65 FIX: Silently defaulting to 3.0m ceiling when ceiling_spec is None
            # is a life-safety defect. A 12m warehouse with missing ceiling data would
            # get 9.1m spacing instead of ~5.2m — 40% fewer detectors than required.
            # The system must fail loudly rather than silently approve unsafe designs.
            if spec.ceiling_spec is None:
                result = RoomResult(
                    room_id=spec.name,
                    status="ERROR",
                    errors=[f"Room '{spec.name}' has no ceiling specification — cannot compute NFPA 72 detector placement. All rooms require ceiling height data."],
                )
                # V76 HIGH-01 FIX: Removed call to self._log_room_result() which
                # does not exist — would raise AttributeError, crashing entire building
                # analysis when any room has missing ceiling spec. The result is already
                # an ERROR RoomResult and will be returned to process() for logging.
                return result
            ceiling_h = spec.ceiling_spec.height_at_low_point_m
            room_data = Room(name=spec.name, width=spec.width_m, length=spec.depth_m, ceiling_height=ceiling_h)
            # CRITICAL FIX: Use height-adjusted coverage radius per NFPA 72
            # Table 17.6.3.1.1. Previously, DensityOptimizer always used R=6.37m
            # (S=9.1m at h≤3.0m) regardless of ceiling height, which overestimates
            # coverage at higher ceilings — a life-safety defect.
            # V46 FIX: Try relative import first (standard within fireai.core package),
            # fall back to absolute import (when module loaded via alternate path by pytest).
            try:
                from .nfpa72_calculations import calculate_coverage_radius_from_height
            except ImportError:
                from fireai.core.nfpa72_calculations import calculate_coverage_radius_from_height
            det_type = (
                spec.detector_type.value if hasattr(spec.detector_type, "value") else str(spec.detector_type or "SMOKE")
            )
            try:
                cov_spec = calculate_coverage_radius_from_height(ceiling_h, det_type)
                height_radius = cov_spec.radius
                height_spacing = cov_spec.spacing_max
            except Exception as e:
                # V60 FIX (P4-3): Log failure instead of silently falling back.
                # Previously, if calculate_coverage_radius_from_height failed for
                # any reason, the code silently used MAX_SPACING_M and DETECTOR_RADIUS
                # which could be wrong for the ceiling height (e.g., using 9.1m spacing
                # for a 15m ceiling that requires 5.2m spacing per NFPA 72 Table 17.6.3.1.1).
                import logging

                logging.getLogger(__name__).warning(
                    "V60: calculate_coverage_radius_from_height failed for ceiling_h=%.1f, "
                    "det_type=%s. Falling back to MAX_SPACING_M/DETECTOR_RADIUS which may "
                    "not be correct for this ceiling height. Error: %s "
                    "[NFPA 72 §17.6.3.1.1]",
                    ceiling_h,
                    det_type,
                    e,
                )
                height_radius = None
                height_spacing = None
            optimizer = DensityOptimizer(
                max_spacing=height_spacing if height_spacing else MAX_SPACING_M,
                radius=height_radius if height_radius else DETECTOR_RADIUS,
            )
            layout = optimizer.optimize(room_data)

            # [2] Build result from layout
            positions = layout.detectors
            count = layout.count

            # V50 FIX: Use correct coverage geometry per detector type.
            # Heat detectors use square/Chebyshev geometry per NFPA 72 Table 17.6.2.1.
            # Previous code hardcoded "circular" for ALL detector types, causing
            # heat detector coverage to be verified with wrong geometry.
            from fireai.core.nfpa72_models import DetectorType as _DT

            is_heat = spec.detector_type == _DT.HEAT if hasattr(spec, "detector_type") else False
            coverage_geom = "square_grid" if is_heat else "circular"

            # Verify coverage
            coverage = verify_full_coverage(
                room_polygon=spec.polygon,
                detector_positions=positions,
                coverage_geometry=coverage_geom,
                detector_radius=optimizer.R,
                listed_spacing_m=optimizer.max_spacing,
                grid_resolution_m=self.grid_res,
                detector_type=spec.detector_type if hasattr(spec, "detector_type") else _DT.SMOKE,
            )

            # [3] Build result from layout + coverage
            result.status = "PASS" if coverage["compliance_status"] == "PASS" else "FAIL"
            result.radius_m = optimizer.R
            result.spacing_m = optimizer.max_spacing
            result.geometry = coverage_geom  # V50: was hardcoded "circular"
            result.detector_count = count
            result.detector_positions = positions
            result.coverage_pct = coverage["coverage_percentage"]
            result.worst_case_distance_m = coverage["worst_case_distance_m"]

            if result.status == "FAIL":
                result.errors.append(f"Coverage failed: {coverage['coverage_percentage']}%")

                # V13 Fix: Adaptive Re-solve — if DensityOptimizer coverage fails,
                # try the ConstraintSolver with area-based greedy placement.
                # This mirrors the adaptive re-solve in core/floor_orchestrator.py
                # (which uses OptimalMIPEngine) and provides the same safety net here.
                try:
                    from .spatial_engine.constraint_solver import ConstraintSolver

                    area_solver = ConstraintSolver(room_polygon=spec.polygon, device_radius=optimizer.R)
                    adaptive_result = area_solver.find_optimal_placement(max_devices=50)
                    if adaptive_result.coverage_percent >= 99.9:
                        result.status = "PASS"
                        result.detector_count = adaptive_result.num_devices
                        result.detector_positions = adaptive_result.positions
                        result.coverage_pct = adaptive_result.coverage_percent
                        result.audit_notes.append(
                            f"V13 Adaptive Re-solve: DensityOptimizer failed, "
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
                    result.errors.append(f"Adaptive re-solve error: {adapt_err}. Manual design required.")

        except (NFPAComplianceError, InvalidInputError, ValueError) as e:
            # Logic errors → convert to ERROR result
            result.status = "ERROR"
            result.errors.append(str(e))

        except Exception as e:
            # CRITICAL: RuntimeError → STOP EVERYTHING
            logger.critical(f"SYSTEM ERROR in {spec.room_id}: {type(e).__name__}: {e}")
            raise  # FAIL FAST — do not continue with corrupted environment

        finally:
            result.solve_time_s = round(time.monotonic() - start, 3)

        return result
