"""
backend/routers/mining.py — Mining fire protection API endpoints.

V214: Exposes the fireai.mining module via HTTP endpoints:
  POST /api/v1/mining/methane-check        — Classify methane hazard
  POST /api/v1/mining/ventilation-check    — Check MSHA ventilation compliance
  POST /api/v1/mining/co-check             — Classify CO hazard
  POST /api/v1/mining/conveyor-suppression — Design suppression system
  POST /api/v1/mining/compliance-report    — Full MSHA compliance report
  GET  /api/v1/mining/standards            — List supported standards
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from backend.auth import require_permission
from backend.rbac import Permission

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/mining", tags=["mining"])


# ── Request Models ─────────────────────────────────────────────────────────


class MethaneCheckRequest(BaseModel):
    """Request for methane hazard classification."""
    concentration_pct: float = Field(..., ge=0, le=100, description="CH4 % by volume")
    location: str = Field("working_face", description="Mine location")


class VentilationCheckRequest(BaseModel):
    """Request for MSHA ventilation compliance check."""
    airflow_m3_s: float = Field(..., ge=0, description="Airflow in m³/s")
    location_type: str = Field("working_face", description="working_face, last_open_crosscut, or belt_entry")
    cross_sectional_area_m2: float | None = Field(None, description="For velocity check")


class CoCheckRequest(BaseModel):
    """Request for CO hazard classification."""
    co_ppm: float = Field(..., ge=0, description="CO in ppm")


class ConveyorSuppressionRequest(BaseModel):
    """Request for conveyor suppression system design."""
    belt_length_m: float = Field(..., ge=0)
    belt_width_m: float = Field(..., ge=0)
    belt_speed_m_s: float = Field(0.0, ge=0)
    has_fire_resistant_belt: bool = True
    number_of_drives: int = Field(1, ge=1)
    number_of_tail_pieces: int = Field(1, ge=1)
    has_take_up: bool = True


class ComplianceReportRequest(BaseModel):
    """Request for full MSHA compliance report."""
    mine_name: str
    section_name: str
    methane_pct: float = Field(0.0, ge=0)
    co_ppm: float = Field(0.0, ge=0)
    airflow_m3_s: float = Field(0.0, ge=0)
    ventilation_location: str = "working_face"
    conveyor_length_m: float = Field(0.0, ge=0)
    conveyor_width_m: float = Field(0.0, ge=0)
    has_fire_resistant_belt: bool = True


# ── Endpoints ──────────────────────────────────────────────────────────────


@router.get("/standards")
async def list_standards():
    """List supported mining fire protection standards."""
    return {
        "success": True,
        "standards": [
            {"code": "NFPA 120-2022", "title": "Fire Prevention and Control in Coal Mines"},
            {"code": "NFPA 122-2022", "title": "Fire Prevention in Metal/Nonmetal Mining"},
            {"code": "MSHA 30 CFR Part 75", "title": "Underground Coal Mine Safety Standards"},
            {"code": "IEC 60079-10-1", "title": "Hazardous Area Classification (methane/dust)"},
        ],
    }


@router.post("/methane-check", dependencies=[Depends(require_permission(Permission.ELEMENT_READ))])
async def methane_check(request: MethaneCheckRequest):
    """Classify methane concentration per MSHA 30 CFR §75.323."""
    try:
        from fireai.mining.core.methane_calculator import MSHA_THRESHOLDS, MethaneCalculator

        hazard = MethaneCalculator.classify_hazard(request.concentration_pct)
        is_explosive = MethaneCalculator.is_in_explosive_range(request.concentration_pct)
        distance_to_lel = MethaneCalculator.distance_to_lel(request.concentration_pct)

        return {
            "success": True,
            "concentration_pct": request.concentration_pct,
            "hazard_level": hazard,
            "is_in_explosive_range": is_explosive,
            "distance_to_lel_pct": round(distance_to_lel, 3),
            "location": request.location,
            "standard": "MSHA 30 CFR §75.323",
            "thresholds": MSHA_THRESHOLDS,
        }
    except ImportError as e:
        raise HTTPException(status_code=503, detail=f"Mining module not available: {e}")
    except Exception as e:
        logger.exception("Methane check failed: %s", e)
        raise HTTPException(status_code=500, detail="Methane check failed")


@router.post("/ventilation-check", dependencies=[Depends(require_permission(Permission.ELEMENT_READ))])
async def ventilation_check(request: VentilationCheckRequest):
    """Check MSHA ventilation compliance per 30 CFR §75.326-327."""
    try:
        from fireai.mining.core.ventilation_calculator import VentilationCalculator

        is_compliant, violations = VentilationCalculator.check_msha_compliance(
            request.airflow_m3_s,
            request.location_type,
            request.cross_sectional_area_m2,
        )

        velocity = None
        if request.cross_sectional_area_m2 and request.cross_sectional_area_m2 > 0:
            velocity = VentilationCalculator.air_velocity(
                request.airflow_m3_s, request.cross_sectional_area_m2
            )

        return {
            "success": True,
            "airflow_m3_s": request.airflow_m3_s,
            "location_type": request.location_type,
            "is_compliant": is_compliant,
            "violations": violations,
            "velocity_m_s": round(velocity, 3) if velocity else None,
            "standard": "MSHA 30 CFR §75.326-327",
        }
    except ImportError as e:
        raise HTTPException(status_code=503, detail=f"Mining module not available: {e}")
    except Exception as e:
        logger.exception("Ventilation check failed: %s", e)
        raise HTTPException(status_code=500, detail="Ventilation check failed")


@router.post("/co-check", dependencies=[Depends(require_permission(Permission.ELEMENT_READ))])
async def co_check(request: CoCheckRequest):
    """Classify CO concentration per MSHA 30 CFR §75.351."""
    try:
        from fireai.mining.core.conveyor_fire import (
            CO_ALERT_PPM,
            CO_EVACUATE_PPM,
            CO_IMMINENT_PPM,
            CO_WITHDRAW_PPM,
            ConveyorFireAnalyzer,
        )

        hazard = ConveyorFireAnalyzer.classify_co_hazard(request.co_ppm)

        return {
            "success": True,
            "co_ppm": request.co_ppm,
            "hazard_level": hazard,
            "thresholds": {
                "alert_ppm": CO_ALERT_PPM,
                "evacuate_ppm": CO_EVACUATE_PPM,
                "withdraw_ppm": CO_WITHDRAW_PPM,
                "imminent_ppm": CO_IMMINENT_PPM,
            },
            "standard": "MSHA 30 CFR §75.351",
        }
    except ImportError as e:
        raise HTTPException(status_code=503, detail=f"Mining module not available: {e}")
    except Exception as e:
        logger.exception("CO check failed: %s", e)
        raise HTTPException(status_code=500, detail="CO check failed")


@router.post("/conveyor-suppression", dependencies=[Depends(require_permission(Permission.ELEMENT_READ))])
async def conveyor_suppression(request: ConveyorSuppressionRequest):
    """Design conveyor belt fire suppression per NFPA 120 §8.4."""
    try:
        from fireai.mining.core.conveyor_fire import ConveyorFireAnalyzer, ConveyorSpec

        spec = ConveyorSpec(
            belt_length_m=request.belt_length_m,
            belt_width_m=request.belt_width_m,
            belt_speed_m_s=request.belt_speed_m_s,
            has_fire_resistant_belt=request.has_fire_resistant_belt,
            number_of_drives=request.number_of_drives,
            number_of_tail_pieces=request.number_of_tail_pieces,
            has_take_up=request.has_take_up,
        )
        design = ConveyorFireAnalyzer.design_suppression_system(spec)

        return {
            "success": True,
            "design": {
                "number_of_nozzle_groups": design.number_of_nozzle_groups,
                "water_flow_rate_lpm": design.water_flow_rate_lpm,
                "water_duration_min": design.water_duration_min,
                "total_water_volume_l": design.total_water_volume_l,
                "nozzle_locations": design.nozzle_locations,
                "is_compliant": design.is_compliant,
                "violations": design.violations,
            },
            "standard": "NFPA 120-2022 §8.4 + MSHA 30 CFR §75.1108",
        }
    except ImportError as e:
        raise HTTPException(status_code=503, detail=f"Mining module not available: {e}")
    except Exception as e:
        logger.exception("Conveyor suppression design failed: %s", e)
        raise HTTPException(status_code=500, detail="Conveyor suppression design failed")


@router.post("/compliance-report", dependencies=[Depends(require_permission(Permission.REPORT_GENERATE))])
async def compliance_report(request: ComplianceReportRequest):
    """Generate full MSHA + NFPA 120 compliance report."""
    try:
        from fireai.mining.core.msha_compliance import MSHAComplianceChecker
        from fireai.mining.output.msha_report import generate_msha_report

        report = MSHAComplianceChecker.full_compliance_report(
            mine_name=request.mine_name,
            section_name=request.section_name,
            methane_pct=request.methane_pct,
            co_ppm=request.co_ppm,
            airflow_m3_s=request.airflow_m3_s,
            ventilation_location=request.ventilation_location,
            conveyor_length_m=request.conveyor_length_m,
            conveyor_width_m=request.conveyor_width_m,
            has_fire_resistant_belt=request.has_fire_resistant_belt,
        )

        markdown = generate_msha_report(report, "markdown")

        return {
            "success": True,
            "overall_status": report.overall_status,
            "checks": [
                {
                    "rule_id": c.rule_id,
                    "standard": c.standard,
                    "description": c.description,
                    "status": c.status,
                    "details": c.details,
                    "remediation": c.remediation,
                }
                for c in report.checks
            ],
            "markdown_report": markdown,
        }
    except ImportError as e:
        raise HTTPException(status_code=503, detail=f"Mining module not available: {e}")
    except Exception as e:
        logger.exception("Compliance report failed: %s", e)
        raise HTTPException(status_code=500, detail="Compliance report generation failed")
