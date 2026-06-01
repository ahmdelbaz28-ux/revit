"""
backend/routers/qomn.py — QOMN-FIRE Engineering Kernel REST API
================================================================
REST endpoints for the QOMN-FIRE deterministic engineering kernel.

ENDPOINTS:
  POST /api/qomn/smoke-spacing       — NFPA 72 smoke detector spacing
  POST /api/qomn/heat-spacing        — NFPA 72 heat detector spacing
  POST /api/qomn/battery             — NFPA 72 battery capacity
  POST /api/qomn/voltage-drop        — NEC voltage drop calculation
  POST /api/qomn/place-detectors     — Full room detector placement
  POST /api/qomn/place-duct          — Duct detector placement
  GET  /api/qomn/audit               — Export audit log (AHJ access)
  GET  /api/qomn/physics-guards      — List all physics guard limits
  POST /api/qomn/golden-tests        — Run golden test suite

All responses include:
  - computation_hash (IEEE-754 deterministic)
  - nfpa_section (code reference)
  - formula (exact formula used)
  - layer3_validated (post-computation verification status)

STANDARDS:
  NFPA 72-2022 — All fire alarm calculations
  NEC 2023     — All electrical calculations
  QOMN Specification §3 — System architecture
"""

from __future__ import annotations

import logging
import threading
from typing import Any, Dict, List, NoReturn, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

router = APIRouter(tags=["qomn"])

# Module-level kernel instance (stateful audit log per server session)
_kernel = None
_kernel_lock = threading.Lock()


def _get_kernel():
    """Lazy-initialize QOMNKernel singleton with thread-safe double-checked locking.

    V58 FIX (BUG #7): Added threading.Lock for thread safety. Previously,
    two concurrent requests could both see _kernel is None and create
    separate instances, splitting the audit trail.
    """
    global _kernel
    if _kernel is None:
        with _kernel_lock:
            if _kernel is None:  # double-checked locking
                from fireai.core.qomn_kernel import QOMNKernel
                _kernel = QOMNKernel()
    return _kernel


# ── Request Models ────────────────────────────────────────────────────────────

class SmokeSpacingRequest(BaseModel):
    """Input for smoke detector spacing calculation."""
    ceiling_height_m: float = Field(
        ..., gt=0, le=18.288,
        description="Ceiling height in meters [0+, ≤18.288m per NFPA 72 §17.7.3.2.4]"
    )


class HeatSpacingRequest(BaseModel):
    """Input for heat detector spacing calculation."""
    ceiling_height_m:      float = Field(..., gt=0, le=18.288)
    area_per_detector_m2:  float = Field(
        ..., gt=0,
        description="Coverage area per detector in m² [NFPA 72 §17.6.3.1]"
    )


class BatteryRequest(BaseModel):
    """Input for battery capacity calculation per NFPA 72 §10.6.7.2.1."""
    standby_load_a:  float = Field(..., ge=0, description="Standby current in Amperes")
    alarm_load_a:    float = Field(..., ge=0, description="Alarm current in Amperes")
    standby_hours:   float = Field(24.0, gt=0, le=96, description="Standby hours (default 24h)")
    alarm_minutes:   float = Field(5.0,  gt=0, le=60, description="Alarm minutes (default 5min)")
    safety_factor:   float = Field(1.25, ge=1.0, description="Safety factor (default 1.25 = 25%)")
    efficiency:      float = Field(0.80, gt=0, le=1.0, description="Discharge efficiency")


class VoltageDropRequest(BaseModel):
    """Input for voltage drop calculation per NEC Chapter 9, Table 8."""
    current_a:        float = Field(..., gt=0, description="Circuit current in Amperes")
    length_m:         float = Field(..., gt=0, description="One-way circuit length in meters")
    # V65 FIX: Validate AWG gauge against NEC Table 8 valid sizes.
    # An invalid gauge could produce incorrect voltage drop — in a fire alarm
    # system, underestimated voltage drop means devices may not operate.
    awg_gauge:        str   = Field(
        "14",
        pattern=r"^(18|16|14|12|10|8|6|4|3|2|1|1/0|2/0|3/0|4/0|250|300|350|400|500)$",
        description="Wire gauge per NEC Table 8 (18, 16, 14, 12, 10, 8, 6, 4, 3, 2, 1, 1/0, 2/0, 3/0, 4/0, 250, 300, 350, 400, 500)"
    )
    supply_voltage_v: float = Field(24.0, gt=0, description="Supply voltage (default 24VDC)")
    max_drop_pct:     float = Field(10.0, gt=0, le=50, description="Max allowable drop %")


class RoomRequest(BaseModel):
    """Room specification for detector placement."""
    room_id:          str   = Field(..., description="Unique room identifier")
    width_m:          float = Field(..., gt=0, description="Room width in meters")
    length_m:         float = Field(..., gt=0, description="Room length in meters")
    ceiling_height_m: float = Field(..., gt=0, le=18.288, description="Ceiling height in meters")
    ceiling_type:     str   = Field("flat", description="flat|sloped|peaked|beam|coffered")
    occupancy_type:   str   = Field("business", description="NFPA 101 occupancy type")
    detector_type:    str   = Field("smoke", description="smoke|heat|duct|beam|aspirating")
    is_sleeping_area: bool  = Field(False, description="True → 177 cd strobes (NFPA 72 §18.5.5.7)")
    slope_degrees:    float = Field(0.0, ge=0, le=45, description="Ceiling slope in degrees")
    exit_doors:       List[Dict[str, float]] = Field(
        default_factory=list,
        description="Exit doors: [{x_m, y_m, door_width_m}]"
    )


class DuctDetectorRequest(BaseModel):
    """Duct detector placement request."""
    duct_id:        str   = Field(..., description="Duct identifier")
    width_m:        float = Field(..., gt=0, description="Duct width in meters")
    height_m:       float = Field(..., gt=0, description="Duct height in meters")
    velocity_m_s:   float = Field(
        ..., gt=0,
        description="Air velocity in m/s [0.305–15.24 per NFPA 72 §17.7.4.2.2]"
    )


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("/qomn/smoke-spacing")
async def compute_smoke_spacing(req: SmokeSpacingRequest):
    """Compute smoke detector spacing per NFPA 72 Table 17.6.3.1.

    Runs full Layer 0→L1→L2→L3→L4 pipeline:
      L0: Physics guard (ceiling height 0+, ≤18.288m)
      L1: NFPA 72 Table 17.6.3.1 lookup
      L2: IEEE-754 deterministic computation
      L3: Result validation against code bounds
      L4: Audit log entry

    Returns listed spacing, coverage radius, wall distance, and
    IEEE-754 computation hash for cross-platform verification.
    """
    try:
        from fireai.core.qomn_kernel import PhysicsGuardError
        kernel = _get_kernel()
        result = kernel.smoke_detector_spacing(req.ceiling_height_m)
        return {"success": True, "data": result}
    except Exception as exc:
        _handle_error(exc)


@router.post("/qomn/heat-spacing")
async def compute_heat_spacing(req: HeatSpacingRequest):
    """Compute heat detector spacing per NFPA 72 §17.6.3.1.

    Formula: S = 0.7 × √A  Maximum: 15.24m (50 ft)

    V58 FIX (BUG #2): Now routes through kernel with full L0→L4 pipeline
    (previously called compute_heat_detector_spacing directly, bypassing
    L3 validation and L4 audit).
    """
    try:
        kernel = _get_kernel()
        result = kernel.heat_detector_spacing(req.ceiling_height_m, req.area_per_detector_m2)
        return {"success": True, "data": result}
    except Exception as exc:
        _handle_error(exc)


@router.post("/qomn/battery")
async def compute_battery(req: BatteryRequest):
    """Compute battery capacity per NFPA 72 §10.6.7.2.1.

    Formula: Ah = (I_sb×T_sb + I_al×T_al) / efficiency × safety_factor
    Default: 24h standby + 5min alarm, 25% safety factor, 80% efficiency.
    """
    try:
        kernel = _get_kernel()
        result = kernel.battery_capacity(
            req.standby_load_a,
            req.alarm_load_a,
            standby_hours    = req.standby_hours,
            alarm_minutes    = req.alarm_minutes,
            safety_factor    = req.safety_factor,
            discharge_efficiency = req.efficiency,
        )
        return {"success": True, "data": result}
    except Exception as exc:
        _handle_error(exc)


@router.post("/qomn/voltage-drop")
async def compute_voltage_drop(req: VoltageDropRequest):
    """Compute circuit voltage drop per NEC Chapter 9, Table 8.

    Formula: V_drop = 2 × I × L × R_per_m  (DC round-trip)
    Resistance values from NEC 2023 Table 8 (copper, stranded, 75°C).
    """
    try:
        kernel = _get_kernel()
        result = kernel.voltage_drop(
            req.current_a, req.length_m, req.awg_gauge,
            req.supply_voltage_v, req.max_drop_pct,
        )
        return {"success": True, "data": result}
    except Exception as exc:
        _handle_error(exc)


@router.post("/qomn/place-detectors")
async def place_detectors(req: RoomRequest):
    """Place fire alarm detectors in a room per NFPA 72-2022.

    Full placement pipeline:
      1. Compute spacing per Table 17.6.3.1 (smoke) or §17.6.3.1 (heat)
      2. Hex-grid placement with wall distance constraints
      3. Beam obstruction check (§17.7.3.2.7)
      4. Pull station placement (§17.15)
      5. Notification appliance placement (Chapter 18)
      6. Coverage verification (§17.5)

    Returns placed devices, coverage %, NFPA violations, and audit hash.
    """
    try:
        from fireai.core.device_placement import (
            DetectorPlacementEngine, RoomSpec, CeilingType,
            DetectorType, OccupancyType, ExitDoor
        )

        # Map string enums to Python enums
        ceiling_map = {
            "flat": CeilingType.FLAT, "sloped": CeilingType.SLOPED,
            "peaked": CeilingType.PEAKED, "beam": CeilingType.BEAM,
            "coffered": CeilingType.COFFERED, "open_joist": CeilingType.OPEN_JOIST,
        }
        det_map = {
            "smoke": DetectorType.SMOKE, "heat": DetectorType.HEAT,
            "duct": DetectorType.DUCT, "beam": DetectorType.BEAM,
            "aspirating": DetectorType.ASPIRATING, "multi": DetectorType.MULTI,
        }
        occ_map = {
            "assembly": OccupancyType.ASSEMBLY, "business": OccupancyType.BUSINESS,
            "educational": OccupancyType.EDUCATIONAL, "health_care": OccupancyType.HEALTH_CARE,
            "residential": OccupancyType.RESIDENTIAL, "mercantile": OccupancyType.MERCANTILE,
            "industrial": OccupancyType.INDUSTRIAL, "storage": OccupancyType.STORAGE,
            "high_hazard": OccupancyType.HIGH_HAZARD,
        }

        exit_doors = [
            ExitDoor(
                x_m=d.get("x_m", 0.0),
                y_m=d.get("y_m", 0.0),
                door_width_m=d.get("door_width_m", 0.914),
            )
            for d in req.exit_doors
        ]

        room = RoomSpec(
            room_id          = req.room_id,
            width_m          = req.width_m,
            length_m         = req.length_m,
            ceiling_height_m = req.ceiling_height_m,
            ceiling_type     = ceiling_map.get(req.ceiling_type, CeilingType.FLAT),
            occupancy_type   = occ_map.get(req.occupancy_type, OccupancyType.BUSINESS),
            detector_type    = det_map.get(req.detector_type, DetectorType.SMOKE),
            is_sleeping_area = req.is_sleeping_area,
            slope_degrees    = req.slope_degrees,
            exit_doors       = exit_doors,
        )

        engine = DetectorPlacementEngine(_get_kernel())
        result = engine.place_detectors(room)

        # Serialize to dict
        return {
            "success": True,
            "data": {
                "room_id": result.room_id,
                "detector_count":     len(result.detectors),
                "pull_station_count": len(result.pull_stations),
                "notification_count": len(result.notification_appliances),
                "coverage_pct":       result.coverage_pct,
                "beam_sections":      result.beam_sections,
                "is_fully_compliant": result.is_fully_compliant,
                "violations":         result.violations,
                "nfpa_references":    result.nfpa_references,
                "computation_hash":   result.computation_hash,
                "detectors": [
                    {
                        "device_id":      d.device_id,
                        "device_type":    d.device_type,
                        "x_m":            d.x_m,
                        "y_m":            d.y_m,
                        "z_m":            d.z_m,
                        "spacing_m":      d.spacing_used_m,
                        "radius_m":       d.radius_m,
                        "nfpa_section":   d.nfpa_section,
                    }
                    for d in result.detectors
                ],
                "pull_stations": [
                    {
                        "device_id": p.device_id,
                        "x_m": p.x_m, "y_m": p.y_m, "z_m": p.z_m,
                        "nfpa_section": p.nfpa_section,
                    }
                    for p in result.pull_stations
                ],
                "notification_appliances": [
                    {
                        "device_id": n.device_id,
                        "x_m": n.x_m, "y_m": n.y_m, "z_m": n.z_m,
                        "candela": n.candela, "is_combo": n.is_combo,
                        "nfpa_section": n.nfpa_section,
                    }
                    for n in result.notification_appliances
                ],
            }
        }
    except Exception as exc:
        _handle_error(exc)


@router.post("/qomn/place-duct")
async def place_duct_detector(req: DuctDetectorRequest):
    """Compute duct detector placement per NFPA 72 §17.7.4.

    Air velocity must be 0.305–15.24 m/s (60–3000 fpm).
    Number of detectors depends on duct width.
    """
    try:
        from fireai.core.device_placement import place_duct_detector, DuctDetectorSpec
        spec = DuctDetectorSpec(
            duct_id      = req.duct_id,
            width_m      = req.width_m,
            height_m     = req.height_m,
            velocity_m_s = req.velocity_m_s,
        )
        result = place_duct_detector(spec)
        return {"success": True, "data": result}
    except Exception as exc:
        _handle_error(exc)


@router.get("/qomn/audit")
async def get_audit_log():
    """Export full QOMN audit log for AHJ review.

    Per QOMN Specification §3 Layer 4:
    'AHJ can access without vendor cooperation'

    Returns all computation records with:
      - timestamp, input, formula_ref, output, result_hash, layer3_passed
      - chain_hash for tamper detection
    """
    kernel = _get_kernel()
    audit  = kernel.get_audit_log()
    is_valid = kernel.verify_audit_integrity()
    return {
        "success":         True,
        "chain_valid":     is_valid,
        "data":            audit,
    }


@router.get("/qomn/physics-guards")
async def get_physics_guards():
    """Return all physics guard limits with code references.

    Per QOMN Specification §3 Layer 0.
    """
    from fireai.core.qomn_kernel import (
        NFPA72_SMOKE_MAX_SPACING_M, NFPA72_HEAT_MAX_SPACING_M,
        NFPA72_PULL_STATION_HEIGHT_M, NFPA72_NAC_MIN_CD, NFPA72_NAC_SLEEPING_MIN_CD,
    )
    return {
        "success": True,
        "data": {
            "area_per_detector": {
                "max_m2": 232.26, "max_ft2": 2500,
                "code_ref": "NFPA 72-2022 §17.7.3.2.1",
            },
            "ceiling_height": {
                "min_m": 0.001, "max_m": 18.288, "max_ft": 60,
                "code_ref": "NFPA 72-2022 §17.7.3.2.4",
            },
            "smoke_max_spacing": {
                "max_m": NFPA72_SMOKE_MAX_SPACING_M, "max_ft": 30,
                "code_ref": "NFPA 72-2022 §17.7.3.2.1",
            },
            "heat_max_spacing": {
                "max_m": NFPA72_HEAT_MAX_SPACING_M, "max_ft": 50,
                "code_ref": "NFPA 72-2022 §17.6.3.1",
            },
            "pull_station_height": {
                "height_m": NFPA72_PULL_STATION_HEIGHT_M, "height_in": 48,
                "code_ref": "NFPA 72-2022 §17.15.7",
            },
            "nac_min_cd": {
                "min_cd": NFPA72_NAC_MIN_CD,
                "code_ref": "NFPA 72-2022 §18.5.3.1",
            },
            "nac_sleeping_min_cd": {
                "min_cd": NFPA72_NAC_SLEEPING_MIN_CD,
                "code_ref": "NFPA 72-2022 §18.5.5.7",
            },
            "efficiency_max": {
                "max": 1.0, "code_ref": "Physics (conservation of energy)",
            },
            "wire_current": {
                "standard": "NEC 2023 §310.16",
                "note": "Never exceed ampacity for selected AWG gauge",
            },
            "duct_velocity": {
                "min_m_s": 0.305, "max_m_s": 15.24,
                "min_fpm": 60,    "max_fpm": 3000,
                "code_ref": "NFPA 72-2022 §17.7.4.2.2",
            },
        }
    }


@router.post("/qomn/golden-tests")
async def run_golden_tests():
    """Run QOMN golden test suite per QOMN Specification §9.

    Verified against NFPA 72 Handbook examples and NEC worked examples.
    All results must match expected values exactly (IEEE-754 deterministic).

    Returns pass/fail for each golden test case.
    """
    from fireai.core.qomn_kernel import (
        compute_smoke_detector_spacing, compute_heat_detector_spacing,
        compute_battery_capacity_ah, compute_voltage_drop
    )

    results = []
    all_pass = True

    def _test(name: str, actual: float, expected: float, tolerance: float, ref: str):
        nonlocal all_pass
        passed = abs(actual - expected) <= tolerance
        if not passed:
            all_pass = False
        results.append({
            "test":     name,
            "actual":   actual,
            "expected": expected,
            "tolerance": tolerance,
            "passed":   passed,
            "ref":      ref,
        })

    # Golden Test 1: Smoke spacing at h=3.048m (10 ft) → 9.144m (30 ft)
    r1 = compute_smoke_detector_spacing(3.048)
    _test(
        "NFPA72_smoke_h10ft",
        r1["listed_spacing_m"], 9.144, 0.001,
        "NFPA 72-2022 Table 17.6.3.1 row h≤10ft"
    )

    # Golden Test 2: Coverage radius = 0.7 × spacing
    _test(
        "NFPA72_coverage_radius_factor",
        r1["coverage_radius_m"], 0.7 * 9.144, 1e-9,
        "NFPA 72-2022 §17.7.4.2.3.1"
    )

    # Golden Test 3: Heat spacing S = 0.7 × √A for A = 50 m²
    r3 = compute_heat_detector_spacing(3.0, 50.0)
    expected_heat = min(0.7 * (50.0 ** 0.5), 15.24)
    _test(
        "NFPA72_heat_spacing_50m2",
        r3["spacing_m"], expected_heat, 1e-6,
        "NFPA 72-2022 §17.6.3.1"
    )

    # Golden Test 4: Battery — 0.5A standby 24h + 3.0A alarm 5min → check formula
    r4 = compute_battery_capacity_ah(0.5, 3.0)
    ah_manual = ((0.5 * 24 + 3.0 * (5/60)) / 0.80) * 1.25
    _test(
        "NFPA72_battery_capacity",
        r4["required_ah"], ah_manual, 1e-6,
        "NFPA 72-2022 §10.6.7.2.1"
    )

    # Golden Test 5: Voltage drop 2.5A, 100m, AWG14, 24V
    r5 = compute_voltage_drop(2.5, 100, "14", 24.0)
    expected_vd = 2.0 * 2.5 * 100 * (8.19 / 1000)
    _test(
        "NEC_voltage_drop_AWG14_100m",
        r5["voltage_drop_v"], expected_vd, 1e-6,
        "NEC 2023 Chapter 9, Table 8"
    )

    # Golden Test 6: Physics guard — negative area MUST raise
    guard_raised = False
    try:
        from fireai.core.qomn_kernel import guard_area_m2
        guard_area_m2(-1.0)
    except Exception:
        guard_raised = True
    results.append({
        "test":    "physics_guard_negative_area",
        "actual":  "raised" if guard_raised else "NOT_RAISED",
        "expected": "raised",
        "passed":  guard_raised,
        "ref":     "QOMN Specification §3 Layer 0",
    })
    if not guard_raised:
        all_pass = False

    # Golden Test 7: Physics guard — efficiency > 1.0 MUST raise
    eff_raised = False
    try:
        from fireai.core.qomn_kernel import guard_efficiency
        guard_efficiency(1.01)
    except Exception:
        eff_raised = True
    results.append({
        "test":    "physics_guard_efficiency_over_100pct",
        "actual":  "raised" if eff_raised else "NOT_RAISED",
        "expected": "raised",
        "passed":  eff_raised,
        "ref":     "QOMN Specification §3 Layer 0 / Physics",
    })
    if not eff_raised:
        all_pass = False

    passed_count = sum(1 for r in results if r["passed"])
    return {
        "success":       all_pass,
        "all_passed":    all_pass,
        "passed_count":  passed_count,
        "total_count":   len(results),
        "results":       results,
    }


# ── Error Handler ─────────────────────────────────────────────────────────────

def _handle_error(exc: Exception) -> NoReturn:
    """Convert QOMN kernel exceptions to HTTP responses.

    V58 FIX (BUG #17): Return type changed from None to NoReturn since
    this function always raises HTTPException.

    H-3 FIX: Never expose str(exc) to the client on HTTP 500 errors.
    Python's str(Exception) can include file paths, variable names,
    database connection strings, and internal implementation details.
    In a fire protection system, this information could help attackers
    understand the system internals and craft targeted exploits.
    Detailed errors are logged server-side; clients get generic messages.
    """
    from fireai.core.qomn_kernel import PhysicsGuardError, ComputationError, ValidationError
    if isinstance(exc, PhysicsGuardError):
        raise HTTPException(
            status_code=422,
            detail={
                "error":     "PHYSICS_GUARD_REJECTION",
                "field":     exc.field,
                "value":     str(exc.value),
                "reason":    exc.reason,
                "code_ref":  exc.code_ref,
                "action":    "Review input values. Consult licensed FPE if limits are unclear.",
            }
        )
    if isinstance(exc, (ComputationError, ValidationError)):
        # H-3 FIX: Log the full error server-side, return generic message to client
        logger.error("QOMN computation/validation error: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=500,
            detail={
                "error":  "COMPUTATION_VALIDATION_FAILURE",
                "detail": "An internal computation error occurred. Check input values or contact the engineering team.",
                "action": "Report this to the engineering team with input values.",
            }
        )
    if isinstance(exc, ValueError):
        # M-2 FIX: Sanitize ValueError messages — Shapely/geometry errors
        # can expose coordinates and internal variable names
        logger.warning("QOMN ValueError: %s", exc)
        raise HTTPException(
            status_code=422,
            detail={
                "error": "INVALID_INPUT",
                "detail": "Input values are invalid. Please check all parameters and try again.",
            }
        )
    # H-3 FIX: Never expose str(exc) to client on unexpected errors
    logger.error("QOMN kernel unexpected error: %s", exc, exc_info=True)
    raise HTTPException(
        status_code=500,
        detail={
            "error": "INTERNAL_ERROR",
            "detail": "An unexpected error occurred. The engineering team has been notified.",
        }
    )
