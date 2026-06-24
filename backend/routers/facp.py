"""backend/routers/facp.py — FACP Selection & Compliance REST API
================================================================
REST endpoints for the Fire Alarm Control Panel selection engine.

ENDPOINTS:
  POST /api/facp/select      — Select optimal FACP for project requirements
  POST /api/facp/verify      — Verify compliance of a panel recommendation
  POST /api/facp/schedule    — Generate DXF schedule table
  POST /api/facp/spec        — Generate CSI specification (Section 28 31 11)
  GET  /api/facp/panels      — List all available panels in the database

STANDARDS:
  NFPA 72-2022 SS10.6.10 — FACP selection and listing requirements
  NFPA 72-2022 SS10.6.7  — Battery backup capacity
  UL 864 10th Edition    — Control unit listing requirements
  CSFM                   — California State Fire Marshal listing
  FDNY COA               — New York City Certificate of Approval

SAFETY NOTE:
  FACP selection is a SAFETY-CRITICAL operation. Selecting a non-compliant
  panel for a fire alarm system could result in:
  - Failure to detect/notify during a fire event
  - Insufficient battery capacity for 24h standby + alarm duration
  - Non-releasing panel selected for suppression systems (NFPA 72 SS21.7)
  - AHJ rejection of the fire alarm system design

  All selection results include a cryptographic signature hash for
  deterministic verification and audit trail purposes.
"""

from __future__ import annotations

import logging
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from backend.auth import require_permission
from backend.rbac import Permission

logger = logging.getLogger(__name__)

router = APIRouter(tags=["facp"])

# ── Request/Response Models ──────────────────────────────────────────────────

class FACPSelectionRequest(BaseModel):
    """Input for FACP panel selection.

    All fields map to facp_system.panel_selector.ProjectRequirements.
    """

    device_count: int = Field(
        ..., gt=0,
        description="Total number of addressable devices (detectors, modules, etc.)"
    )
    nac_circuit_count: int = Field(
        ..., gt=0,
        description="Number of Notification Appliance Circuits required"
    )
    building_size_m2: float = Field(
        ..., gt=0,
        description="Total building floor area in square meters"
    )
    building_floors: int = Field(
        ..., gt=0,
        description="Number of building floors"
    )
    requires_network: bool = Field(
        False,
        description="True if panels must be networked across multiple locations"
    )
    requires_voice: bool = Field(
        False,
        description="True if voice evacuation is required (affects alarm duration: 15min vs 5min per NFPA 72 SS10.6.7)"
    )
    requires_releasing: bool = Field(
        False,
        description="True if panel must support releasing service for suppression systems (NFPA 72 SS21.7)"
    )
    jurisdiction: str = Field(
        "US",
        description="Jurisdiction code: US, Canada, FDNY, etc."
    )
    preferred_manufacturer: Optional[str] = Field(
        None,
        description="Preferred FACP manufacturer (e.g., NOTIFIER, SIEMENS, SIMPLEX)"
    )
    min_temperature_c: float = Field(
        20.0, ge=-40.0, le=60.0,
        description="Minimum ambient temperature for battery derating per NFPA 72 SS10.6.7"
    )


class FACPVerificationRequest(BaseModel):
    """Input for FACP compliance verification.

    Accepts the same ProjectRequirements plus a PanelRecommendation
    to verify compliance against UL/FDNY/NFPA rules.
    """

    device_count: int = Field(..., gt=0)
    nac_circuit_count: int = Field(..., gt=0)
    building_size_m2: float = Field(..., gt=0)
    building_floors: int = Field(..., gt=0)
    requires_network: bool = False
    requires_voice: bool = False
    requires_releasing: bool = False
    jurisdiction: str = "US"
    preferred_manufacturer: Optional[str] = None
    min_temperature_c: float = Field(20.0, ge=-40.0, le=60.0)
    # Panel recommendation fields to verify
    recommended_model: str = Field(..., description="Model name of the panel to verify")
    manufacturer: str = Field(..., description="Manufacturer of the panel")
    capacity_utilization: float = Field(..., ge=0.0, le=1.0)
    nac_utilization: float = Field(..., ge=0.0, le=1.0)
    battery_size_ah: float = Field(..., gt=0)
    battery_derating_method: str = Field(
        ..., description="Battery sizing method used (must not be '1.2x' flat)"
    )


class FACPScheduleRequest(BaseModel):
    """Input for DXF schedule table generation."""

    recommended_model: str = Field(..., description="Panel model from selection result")
    manufacturer: str = Field(..., description="Panel manufacturer")
    capacity_utilization: float = Field(..., ge=0.0, le=1.0)
    nac_utilization: float = Field(..., ge=0.0, le=1.0)
    battery_size_ah: float = Field(..., gt=0)
    battery_derating_method: str = Field(...)
    power_supply_watts: int = Field(..., gt=0)
    listings: List[str] = Field(default_factory=list)
    signature_hash: str = Field(..., description="Cryptographic signature from selection")
    quantity: int = Field(1, gt=0, le=100, description="Number of panels (for schedule)")


class FACPSpecRequest(BaseModel):
    """Input for CSI specification generation."""

    device_count: int = Field(..., gt=0)
    nac_circuit_count: int = Field(..., gt=0)
    building_size_m2: float = Field(..., gt=0)
    building_floors: int = Field(..., gt=0)
    requires_network: bool = False
    requires_voice: bool = False
    requires_releasing: bool = False
    jurisdiction: str = "US"
    recommended_model: str = Field(...)
    manufacturer: str = Field(...)
    capacity_utilization: float = Field(..., ge=0.0, le=1.0)
    nac_utilization: float = Field(..., ge=0.0, le=1.0)
    battery_size_ah: float = Field(..., gt=0)
    battery_derating_method: str = Field(...)
    power_supply_watts: int = Field(..., gt=0)
    listings: List[str] = Field(default_factory=list)
    signature_hash: str = Field(...)


# ── Helper: Safe FACP module import ──────────────────────────────────────────

_facp_available: Optional[bool] = None


def _check_facp_available() -> bool:
    """Check if facp_system package is available.

    SAFETY: If the FACP module is not available, endpoints must return 503
    (Service Unavailable) rather than 500 (Internal Server Error).
    A 503 clearly indicates a missing dependency, while a 500 could be
    misinterpreted as a computation error — which would be deceptive
    in a safety-critical system per agent.md Anti-Deception Directive.
    """
    global _facp_available
    if _facp_available is None:
        try:
            from facp_system.panel_database import MASTER_PANEL_DATABASE  # noqa: F401
            from facp_system.panel_output import OutputGenerator  # noqa: F401
            from facp_system.panel_selector import SelectionEngine  # noqa: F401
            from facp_system.panel_verifier import ComplianceVerifier  # noqa: F401
            _facp_available = True
            logger.info("FACP system modules loaded successfully")
        except ImportError as e:
            _facp_available = False
            logger.error(
                "FACP system modules not available: %s. "
                "FACP endpoints will return 503. "
                "Ensure facp_system/ package is in the Python path.",
                e,
            )
    return _facp_available


def _require_facp():
    """Raise 503 if FACP modules are not available."""
    if not _check_facp_available():
        raise HTTPException(
            status_code=503,
            detail={
                "error": "FACP_SERVICE_UNAVAILABLE",
                "detail": (
                    "FACP selection engine is not available. "
                    "The facp_system package could not be imported. "
                    "Check server logs for import errors."
                ),
                "action": "Ensure facp_system/ is installed and in the Python path.",
            },
        )


# ── Endpoints ────────────────────────────────────────────────────────────────

@router.post("/facp/select", dependencies=[Depends(require_permission(Permission.FACP_MANAGE))])
async def select_facp(req: FACPSelectionRequest):
    """Select optimal FACP for project requirements.

    Runs the deterministic selection algorithm from
    facp_system.panel_selector.SelectionEngine with:
      - Points capacity filtering (1.2x margin per NFPA best practice)
      - NAC capacity filtering (exact match — V54 FIX F2)
      - Releasing service filter (V54 FIX F4)
      - Jurisdiction listing checks (UL, ULC, FDNY, FM)
      - NFPA 72 SS10.6.7 battery sizing with temperature/aging/Peukert derating
      - Cryptographic signature hash for audit trail

    Returns the recommended panel, alternatives, battery sizing details,
    and compliance listings.
    """
    _require_facp()

    try:
        from facp_system.panel_selector import ProjectRequirements, SelectionEngine

        project_req = ProjectRequirements(
            device_count=req.device_count,
            nac_circuit_count=req.nac_circuit_count,
            building_size_m2=req.building_size_m2,
            building_floors=req.building_floors,
            requires_network=req.requires_network,
            requires_voice=req.requires_voice,
            requires_releasing=req.requires_releasing,
            jurisdiction=req.jurisdiction,
            preferred_manufacturer=req.preferred_manufacturer,
            min_temperature_c=req.min_temperature_c,
        )

        recommendation = SelectionEngine.select_panel(project_req)

        return {
            "success": True,
            "data": {
                "recommended_model": recommendation.recommended_model,
                "manufacturer": recommendation.manufacturer,
                "capacity_utilization": recommendation.capacity_utilization,
                "nac_utilization": recommendation.nac_utilization,
                "battery_size_ah": recommendation.battery_size_ah,
                "battery_derating_details": recommendation.battery_derating_details,
                "power_supply_watts": recommendation.power_supply_watts,
                "listings": recommendation.listings,
                "code_compliance": recommendation.code_compliance,
                "warnings": recommendation.warnings,
                "alternatives": recommendation.alternatives,
                "signature_hash": recommendation.signature_hash,
                "nfpa_reference": "NFPA 72-2022 SS10.6.10, SS10.6.7",
                "ul_reference": "UL 864 10th Edition",
            },
        }
    except ValueError as exc:
        # No compliant panels found
        logger.warning("FACP selection failed: %s", exc)
        raise HTTPException(
            status_code=422,
            detail={
                "error": "NO_COMPLIANT_PANEL",
                "detail": str(exc),
                "action": (
                    "Relax design requirements or expand the panel database. "
                    "Consider splitting the system into multiple networked panels."
                ),
            },
        )
    except Exception as exc:
        logger.error("FACP selection unexpected error: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=500,
            detail={
                "error": "INTERNAL_ERROR",
                "detail": "An unexpected error occurred during FACP selection.",
            },
        )


@router.post("/facp/verify", dependencies=[Depends(require_permission(Permission.FACP_MANAGE))])
async def verify_facp(req: FACPVerificationRequest):
    """Verify compliance of a panel recommendation.

    Runs programmatic compliance checks from
    facp_system.panel_verifier.ComplianceVerifier:
      - UL 864 listing validation
      - Battery safety margin check (NFPA 72 SS10.6.10)
      - Voice evacuation capability check
      - FDNY Certificate of Approval check
      - Releasing service verification (V54 FIX F4)
      - Battery derating method verification (V54 FIX F5)

    Returns a list of violations (empty = compliant).
    """
    _require_facp()

    try:
        from facp_system.panel_selector import PanelRecommendation, ProjectRequirements
        from facp_system.panel_verifier import ComplianceVerifier

        project_req = ProjectRequirements(
            device_count=req.device_count,
            nac_circuit_count=req.nac_circuit_count,
            building_size_m2=req.building_size_m2,
            building_floors=req.building_floors,
            requires_network=req.requires_network,
            requires_voice=req.requires_voice,
            requires_releasing=req.requires_releasing,
            jurisdiction=req.jurisdiction,
            preferred_manufacturer=req.preferred_manufacturer,
            min_temperature_c=req.min_temperature_c,
        )

        # Reconstruct PanelRecommendation from request
        recommendation = PanelRecommendation(
            recommended_model=req.recommended_model,
            manufacturer=req.manufacturer,
            capacity_utilization=req.capacity_utilization,
            nac_utilization=req.nac_utilization,
            battery_size_ah=req.battery_size_ah,
            battery_derating_details={"method": req.battery_derating_method},
            power_supply_watts=0,  # Not needed for verification
            listings=[],  # Populated from database by verifier
            code_compliance=[],
            warnings=[],
            alternatives=[],
            signature_hash="",
        )

        violations = ComplianceVerifier.verify_national_code_rules(
            project_req, recommendation
        )

        is_compliant = len(violations) == 0

        return {
            "success": True,
            "data": {
                "is_compliant": is_compliant,
                "violations": violations,
                "violation_count": len(violations),
                "nfpa_reference": "NFPA 72-2022 SS10.6.10",
                "ul_reference": "UL 864 10th Edition",
            },
        }
    except Exception as exc:
        logger.error("FACP verification error: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=500,
            detail={
                "error": "INTERNAL_ERROR",
                "detail": "An unexpected error occurred during FACP compliance verification.",
            },
        )


@router.post("/facp/schedule", dependencies=[Depends(require_permission(Permission.FACP_MANAGE))])
async def generate_facp_schedule(req: FACPScheduleRequest):
    """Generate DXF schedule table for the selected FACP.

    Produces a formatted text table suitable for CAD viewport placement
    in the fire alarm plan drawings. Includes:
      - Model number and quantity
      - Manufacturer
      - Power supply rating
      - Points and NAC utilization
      - Battery size with derating method
      - Regulatory listings
      - Cryptographic signature hash
    """
    _require_facp()

    try:
        from facp_system.panel_output import OutputGenerator
        from facp_system.panel_selector import PanelRecommendation

        recommendation = PanelRecommendation(
            recommended_model=req.recommended_model,
            manufacturer=req.manufacturer,
            capacity_utilization=req.capacity_utilization,
            nac_utilization=req.nac_utilization,
            battery_size_ah=req.battery_size_ah,
            battery_derating_details={"method": req.battery_derating_method},
            power_supply_watts=req.power_supply_watts,
            listings=req.listings,
            code_compliance=[],
            warnings=[],
            alternatives=[],
            signature_hash=req.signature_hash,
        )

        schedule_text = OutputGenerator.generate_dxf_schedule(
            recommendation, qty=req.quantity
        )

        return {
            "success": True,
            "data": {
                "schedule": schedule_text,
                "format": "text_table",
                "model": req.recommended_model,
                "quantity": req.quantity,
            },
        }
    except Exception as exc:
        logger.error("FACP schedule generation error: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=500,
            detail={
                "error": "INTERNAL_ERROR",
                "detail": "An unexpected error occurred during schedule generation.",
            },
        )


@router.post("/facp/spec", dependencies=[Depends(require_permission(Permission.FACP_MANAGE))])
async def generate_facp_spec(req: FACPSpecRequest):
    """Generate CSI specification (Section 28 31 11) for the selected FACP.

    Produces a ready-to-print specification paragraph for fire protection
    construction bids, including:
      - System overview with panel model and capabilities
      - Design metrics (point capacity, battery, power supply)
      - Code certification and listings
      - Releasing service requirements (if applicable)

    Reference: CSI MasterFormat 28 31 11 — Fire Alarm Control Panels
    """
    _require_facp()

    try:
        from facp_system.panel_output import OutputGenerator
        from facp_system.panel_selector import PanelRecommendation, ProjectRequirements

        project_req = ProjectRequirements(
            device_count=req.device_count,
            nac_circuit_count=req.nac_circuit_count,
            building_size_m2=req.building_size_m2,
            building_floors=req.building_floors,
            requires_network=req.requires_network,
            requires_voice=req.requires_voice,
            requires_releasing=req.requires_releasing,
            jurisdiction=req.jurisdiction,
        )

        recommendation = PanelRecommendation(
            recommended_model=req.recommended_model,
            manufacturer=req.manufacturer,
            capacity_utilization=req.capacity_utilization,
            nac_utilization=req.nac_utilization,
            battery_size_ah=req.battery_size_ah,
            battery_derating_details={"method": req.battery_derating_method},
            power_supply_watts=req.power_supply_watts,
            listings=req.listings,
            code_compliance=[],
            warnings=[],
            alternatives=[],
            signature_hash=req.signature_hash,
        )

        csi_spec = OutputGenerator.generate_csi_specification(
            project_req, recommendation
        )

        # Also generate alternatives table
        alternatives_table = OutputGenerator.generate_alternatives_table(recommendation)

        return {
            "success": True,
            "data": {
                "csi_specification": csi_spec,
                "alternatives_table": alternatives_table,
                "section": "28 31 11",
                "format": "CSI MasterFormat",
            },
        }
    except Exception as exc:
        logger.error("FACP spec generation error: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=500,
            detail={
                "error": "INTERNAL_ERROR",
                "detail": "An unexpected error occurred during specification generation.",
            },
        )


@router.get("/facp/panels", dependencies=[Depends(require_permission(Permission.FACP_READ))])
async def list_available_panels():
    """List all FACP panels in the database with full specifications.

    Returns the complete panel database for manual review and
    engineering judgment. Each panel includes:
      - Model, manufacturer
      - Points capacity, NAC capacity, SLC loops
      - Networking, voice, releasing capabilities
      - Regulatory listings (UL, ULC, FM, FDNY)
      - Standby and alarm current draw
      - Power supply wattage

    SAFETY: This endpoint is read-only (GET) and does not require
    API key authentication. It provides reference data only.
    """
    _require_facp()

    try:
        from facp_system.panel_database import MASTER_PANEL_DATABASE

        panels = []
        for p in MASTER_PANEL_DATABASE:
            panels.append({
                "model": p.model,
                "manufacturer": p.manufacturer,
                "points_capacity": p.points_capacity,
                "nac_capacity": p.nac_capacity,
                "supports_networking": p.supports_networking,
                "supports_voice": p.supports_voice,
                "supports_releasing": p.supports_releasing,
                "max_slc_loops": p.max_slc_loops,
                "listings": p.listings,
                "standby_current_amps": p.standby_current_amps,
                "alarm_current_amps": p.alarm_current_amps,
                "power_supply_watts": p.power_supply_watts,
            })

        return {
            "success": True,
            "data": {
                "panels": panels,
                "total_count": len(panels),
                "manufacturers": list({p.manufacturer for p in MASTER_PANEL_DATABASE}),
                "standards": [
                    "NFPA 72-2022 SS10.6.10",
                    "UL 864 10th Edition",
                    "CSFM",
                    "FDNY COA",
                ],
            },
        }
    except Exception as exc:
        logger.error("FACP panel listing error: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=500,
            detail={
                "error": "INTERNAL_ERROR",
                "detail": "An unexpected error occurred while listing panels.",
            },
        )
