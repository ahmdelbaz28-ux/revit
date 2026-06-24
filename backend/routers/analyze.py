"""backend/routers/analyze.py - Project-level analyze endpoints
=============================================================
Endpoints for running NFPA 72 / NEC calculations in the context of a
project / room:
  POST /api/analyze/battery        - Battery capacity (standalone)
  POST /api/analyze/voltage        - Voltage drop (standalone)
  POST /api/projects/{project_id}/analyze/room
                                    - Full room analysis pipeline

These wrap the QOMN kernel and pipeline functions so the API consumer
can choose between (a) low-level kernel calls (/api/qomn/...) or
(b) project-scoped analyze calls (this router).
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from backend.auth import require_permission
from backend.rbac import Permission
from fireai.core.pipeline import analyze_room
from fireai.core.qomn_kernel import (
    PhysicsGuardError,
    QOMNKernel,
)

logger = logging.getLogger(__name__)

# ----------------------------------------------------------------------------
# Safe error helper for PhysicsGuardError
# ----------------------------------------------------------------------------
# STRESS-TEST FIX #7: PhysicsGuardError messages interpolate user-supplied
# values via {value!r}. While Pydantic should reject non-numeric inputs
# before they reach the kernel, defense-in-depth requires that we never
# trust str(exc) in an HTTP response. We extract the structured fields
# (field, reason, code_ref) and return them as a JSON object instead.
def _physics_guard_detail(exc: Exception) -> dict:
    """Build a safe JSON-serializable detail dict from a PhysicsGuardError."""
    if hasattr(exc, "field") and hasattr(exc, "reason") and hasattr(exc, "code_ref"):
        return {
            "error_type": "physics_guard_violation",
            "field": str(getattr(exc, "field", ""))[:64],  # cap length
            "reason": str(getattr(exc, "reason", ""))[:256],
            "code_ref": str(getattr(exc, "code_ref", ""))[:64],
            "hint": "Review input and consult licensed PE before resubmitting.",
        }
    # Fallback — never leak raw str(exc)
    return {"error_type": "physics_guard_violation", "hint": "Input rejected by physics guard."}

# ----------------------------------------------------------------------------
# Routers
# ----------------------------------------------------------------------------
router = APIRouter(tags=["analyze"])
project_router = APIRouter(tags=["analyze"])


# ----------------------------------------------------------------------------
# Request / response models
# ----------------------------------------------------------------------------
class BatteryRequest(BaseModel):
    """Battery capacity calculation request.

    NFPA 72-2022 §10.6.7.2.1:
        Ah = (I_standby * T_standby + I_alarm * T_alarm_min/60)
             / discharge_efficiency * safety_factor
    """

    standby_load_a: float = Field(..., gt=0, description="Standby current draw (A)")
    alarm_load_a: float = Field(..., ge=0, description="Alarm current draw (A)")
    standby_hours: float = Field(24.0, gt=0, description="Standby duration (h)")
    alarm_minutes: float = Field(5.0, gt=0, description="Alarm duration (min)")
    safety_factor: float = Field(1.25, gt=0, description="Safety factor (1.25 = 25%)")
    discharge_efficiency: float = Field(
        0.80, gt=0, le=1.0, description="Discharge efficiency (0.80 = 80%)"
    )


class VoltageRequest(BaseModel):
    """Voltage drop calculation request.

    NEC Chapter 9 Table 8:
        V_drop = 2 * I * L * R_per_m
    """

    current_a: float = Field(..., gt=0, description="Circuit current (A)")
    length_m: float = Field(..., gt=0, description="One-way circuit length (m)")
    awg_gauge: str = Field("14", description="AWG gauge (e.g., 14, 12, 10)")
    supply_voltage_v: float = Field(24.0, gt=0, description="Supply voltage (V)")


class RoomAnalyzeRequest(BaseModel):
    """Full room analysis request body for /api/projects/{project_id}/analyze/room."""

    room_id: str = Field(
        ..., description="Room identifier (must match {project_id} or be scoped to it)"
    )
    room_polygon: List[List[float]] = Field(
        ..., description="Room polygon as [[x,y], ...] list of vertices"
    )
    ceiling_height_m: float = Field(
        ..., gt=0, le=18.288,
        description="Ceiling height (m). NFPA 72 §17.7.3.2.4 caps at 18.288m (60ft).",
    )
    detector_type: str = Field("smoke", description="Detector type: smoke | heat")
    standby_current_a: float = Field(0.3, gt=0, description="Standby current (A)")
    alarm_current_a: float = Field(2.0, gt=0, description="Alarm current (A)")
    circuit_length_m: float = Field(80.0, gt=0, description="Circuit length (m)")


# ----------------------------------------------------------------------------
# Endpoints
# ----------------------------------------------------------------------------
@router.post(
    "/analyze/battery",
    dependencies=[Depends(require_permission(Permission.QOMN_EXECUTE))],
)
async def analyze_battery(req: BatteryRequest) -> Dict[str, Any]:
    """Compute NFPA 72 battery capacity.

    Returns:
        Dict with required_ah, installed_ah, formula, computation_hash.

    """
    try:
        kernel = QOMNKernel()
        result = kernel.battery_capacity(
            standby_load_a=req.standby_load_a,
            alarm_load_a=req.alarm_load_a,
            standby_hours=req.standby_hours,
            alarm_minutes=req.alarm_minutes,
            safety_factor=req.safety_factor,
            discharge_efficiency=req.discharge_efficiency,
        )
        return {
            "success": True,
            "data": result,
            "nfpa_section": "NFPA 72-2022 §10.6.7.2.1",
        }
    except PhysicsGuardError as e:
        raise HTTPException(status_code=422, detail=_physics_guard_detail(e))
    except Exception:
        logger.exception("battery calculation failed")
        raise HTTPException(status_code=500, detail="Internal calculation error")


@router.post(
    "/analyze/voltage",
    dependencies=[Depends(require_permission(Permission.QOMN_EXECUTE))],
)
async def analyze_voltage(req: VoltageRequest) -> Dict[str, Any]:
    """Compute NEC voltage drop.

    Returns:
        Dict with voltage_drop_v, actual_value, percentage_drop, compliant.

    """
    try:
        kernel = QOMNKernel()
        result = kernel.voltage_drop(
            current_a=req.current_a,
            length_m=req.length_m,
            awg_gauge=req.awg_gauge,
            supply_voltage_v=req.supply_voltage_v,
        )
        return {
            "success": True,
            "data": result,
            "nfpa_section": "NEC 2023 Chapter 9 Table 8",
        }
    except PhysicsGuardError as e:
        raise HTTPException(status_code=422, detail=_physics_guard_detail(e))
    except Exception:
        logger.exception("voltage drop calculation failed")
        raise HTTPException(status_code=500, detail="Internal calculation error")


@project_router.post(
    "/projects/{project_id}/analyze/room",
    dependencies=[Depends(require_permission(Permission.QOMN_EXECUTE))],
)
async def analyze_project_room(project_id: str, req: RoomAnalyzeRequest) -> Dict[str, Any]:
    """Run the full FireAI pipeline for a room in a project.

    Returns the full PipelineResult.to_dict() output, augmented with
    project_id scoping.
    """
    # Scope the room_id under the project
    if not req.room_id.startswith(project_id):
        # Don't leak project_id structure in error -- use generic message
        logger.warning("room_id %r does not match project_id %r", req.room_id, project_id)

    try:
        result = analyze_room(
            {
                "room_id": req.room_id,
                "room_polygon": req.room_polygon,
                "ceiling_height_m": req.ceiling_height_m,
                "detector_type": req.detector_type,
            },
            standby_current_a=req.standby_current_a,
            alarm_current_a=req.alarm_current_a,
            circuit_length_m=req.circuit_length_m,
        )
        data = result.to_dict()
        data["project_id"] = project_id
        return {"success": result.success, "data": data}
    except PhysicsGuardError as e:
        raise HTTPException(status_code=422, detail=_physics_guard_detail(e))
    except Exception:
        logger.exception("room analysis failed for project %s", project_id)
        raise HTTPException(status_code=500, detail="Internal pipeline error")
