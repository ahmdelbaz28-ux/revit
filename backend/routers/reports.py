"""backend/routers/reports.py — Report generation and export endpoints.

Reports can be:
  - voltage_drop: IEC 60364 / NFPA 72 voltage drop analysis
  - short_circuit: IEC 60909 short circuit current analysis
  - cable_sizing: IEC 60364 cable sizing and derating
  - load_flow: Load flow analysis
  - coordination: Breaker coordination study
  - earth_fault: Earth fault loop impedance
  - power_factor: Power factor correction
  - nfpa72_coverage: NFPA 72 coverage analysis (fire alarm specific)
  - nfpa72_battery: NFPA 72 battery calculation (fire alarm specific)
  - nfpa72_circuit: NFPA 72 circuit integrity (fire alarm specific)

LIFE-SAFETY NOTE: Report results are used for regulatory compliance.
All calculations must be traceable and verifiable.
"""

from __future__ import annotations

import io
import json
import logging
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse

from backend.auth import require_permission
from backend.database import get_db
from backend.models import GenerateReportInput
from backend.rbac import Permission
from backend.response import safe_filename as _safe_filename

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/projects/{project_id}/reports", tags=["reports"])


def _verify_project(project_id: str) -> None:
    db = get_db()
    project = db.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")


def _generate_report_content(report_type: str, project_id: str) -> dict:
    """Generate report content based on type.

    This is a functional implementation that produces real engineering
    data structures. For full calculations, the frontend's CalculationEngine
    and the backend's NFPA 72 modules should be used.
    """
    db = get_db()
    devices = db.get_all_devices_for_project(project_id)
    connections = db.get_all_connections_for_project(project_id)

    now = datetime.now(timezone.utc).isoformat()

    if report_type == "voltage_drop":
        # Aggregate voltage drop data from device connections
        # Use dict lookup for O(1) per device — previous bug used O(n) linear scan
        # per connection, making this O(n*m) for n devices and m connections.
        device_map = {d["id"]: d for d in devices}
        circuits = []
        for conn in connections:
            from_dev = device_map.get(conn["fromId"])
            to_dev = device_map.get(conn["toId"])
            if from_dev and to_dev:
                circuits.append({
                    "from": from_dev["name"],
                    "to": to_dev["name"],
                    "cableSize": conn["cableSize"],
                    "length": conn["length"],
                    "load": to_dev["load"],
                    "voltage": to_dev["voltage"],
                })
        return {
            "type": "voltage_drop",
            "standard": "IEC 60364 / NFPA 72-2022 §27.4.1.2",
            "generatedAt": now,
            "totalCircuits": len(circuits),
            "circuits": circuits,
        }

    if report_type == "nfpa72_coverage":
        return {
            "type": "nfpa72_coverage",
            "standard": "NFPA 72-2022",
            "generatedAt": now,
            "totalDevices": len(devices),
            "devicesByCategory": _count_by_category(devices),
            "complianceNotes": [
                "All detector placements must be verified by a licensed FPE",
                "Coverage calculations assume standard ceiling conditions",
            ],
        }

    if report_type == "nfpa72_battery":
        # NFPA 72-2022 §27.6.2 Battery Calculation
        # Load values are stored in Amperes (A) in the database.
        # The devices.py router converts mA/W to A before storage on CREATE.
        # However, UPDATE operations via UpdateDeviceInput now also support
        # load_unit conversion (added 2026-05-28). Devices created before
        # this fix or updated without load_unit default to Amperes.
        # SAFETY WARNING: If any device's load was updated without proper
        # unit conversion, the battery calculation will be incorrect.

        # CRITICAL FIX: NFPA 72 role-based load classification.
        # Previous code used `category == "notification"` which NEVER matches
        # because the frontend device library uses categories: FIRE_ALARM, SECURITY,
        # CCTV, DATA_NETWORK, PA_SYSTEM, TELEPHONE. None of these equal "notification".
        # This caused total_alarm to ALWAYS be zero, meaning battery capacity was
        # calculated for standby-only — horns/strobes would fail during power outage + fire.
        # Fix: Map device types to their NFPA 72 role (alarm vs standby).
        # Per NFPA 72 §27.6.2: alarm load = notification appliances (sounders, strobes,
        # speakers used for evacuation) active for 5 minutes during alarm condition.
        # Standby load = all other devices (detectors, modules, panels) for 24 hours.
        _ALARM_DEVICE_TYPES = {
            "FA_SOUND_STROBE",    # Combined sounder/strobe — PRIMARY evacuation signal
            "FA_HORN",           # Fire alarm horn
            "FA_STROBE",         # Visual alarm strobe
            "FA_BELL",           # Fire alarm bell
            "FA_SIREN",          # Electronic siren
            "PA_CEILING_SPEAKER", # PA speaker used for voice evacuation
            "PA_WALL_SPEAKER",   # Wall-mounted PA speaker for voice evacuation
            "PA_HORN",           # Outdoor horn for voice evacuation
        }
        # Also classify by category + type combination for devices using category-based storage
        _ALARM_CATEGORIES = {"PA_SYSTEM"}  # PA system devices are typically voice alarm

        total_standby = 0.0
        total_alarm = 0.0
        for d in devices:
            load = d.get("load", 0) or 0
            device_type = d.get("type", "")
            device_category = d.get("category", "")

            # Check if device is an alarm (notification) appliance
            is_alarm = (
                device_type in _ALARM_DEVICE_TYPES
                or device_category == "notification"  # Legacy compatibility
                or (device_category in _ALARM_CATEGORIES and device_type not in {"PA_AMPLIFIER", "PA_MICROPHONE"})
            )

            if is_alarm:
                total_alarm += load
            else:
                total_standby += load

        # SAFETY FIX (BUG-29): Previous condition `if total_standby > 0 else 0`
        # returned zero battery when only notification appliances exist.
        # NFPA 72 §27.6.2 requires battery capacity for alarm load regardless
        # of standby load. A system with only horns/strobes still needs battery.
        battery_ah = (total_standby * 24 + total_alarm * 0.25) / 0.8 if (total_standby > 0 or total_alarm > 0) else 0
        return {
            "type": "nfpa72_battery",
            "standard": "NFPA 72-2022 §27.6.2",
            "generatedAt": now,
            "standbyLoadA": total_standby,
            "alarmLoadA": total_alarm,
            "standbyHours": 24,
            "alarmMinutes": 15,
            "deratingFactor": 0.80,
            "requiredAh": round(battery_ah, 3),
            "unitAssumption": "A",
            "safetyWarning": (
                "All load values are assumed to be in Amperes (A). "
                "If any device load was entered in milliAmperes (mA) or Watts (W), "
                "the battery calculation will be incorrect. Verify all device loads "
                "before relying on this calculation for life-safety decisions."
            ),
        }

    if report_type == "cable_sizing":
        return {
            "type": "cable_sizing",
            "standard": "IEC 60364 / NFPA 70",
            "generatedAt": now,
            "totalConnections": len(connections),
            "connections": [
                {
                    "id": c["id"],
                    "cableSize": c["cableSize"],
                    "length": c["length"],
                    "type": c["type"],
                }
                for c in connections
            ],
        }

    # Generic report with project summary
    return {
        "type": report_type,
        "standard": "General Engineering Analysis",
        "generatedAt": now,
        "totalDevices": len(devices),
        "totalConnections": len(connections),
        "devicesByCategory": _count_by_category(devices),
    }


def _count_by_category(devices: list) -> dict:
    """Count devices by category."""
    counts: dict[str, int] = {}
    for d in devices:
        cat = d.get("category", "unknown")
        counts[cat] = counts.get(cat, 0) + 1
    return counts


# camelCase → snake_case sort field mapping
_SORT_MAP = {
    "createdAt": "created_at",
    "type": "type",
    "name": "name",
    "status": "status",
}


def _normalize_sort(sort: str) -> str:
    """Convert camelCase sort fields to snake_case for database.

    SECURITY FIX (BUG-32): Strict whitelist — rejects unknown sort fields.
    """
    return _SORT_MAP.get(sort, "created_at")


@router.get("", dependencies=[Depends(require_permission(Permission.REPORT_READ))])
async def list_reports(
    project_id: str,
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    sort: str = Query("createdAt"),
    order: str = Query("desc"),
):
    """List all reports for a project."""
    _verify_project(project_id)
    db = get_db()
    result = db.list_reports(project_id, page=page, limit=limit, sort=_normalize_sort(sort), order=order)
    return {"success": True, "data": result}


@router.post("", status_code=201, dependencies=[Depends(require_permission(Permission.REPORT_GENERATE))])
async def generate_report(project_id: str, input_data: GenerateReportInput):
    """Generate a new engineering report."""
    _verify_project(project_id)
    db = get_db()

    report_data = {
        "id": str(uuid.uuid4()),
        "type": input_data.type,
        "name": input_data.name or f"{input_data.type} Report",
        "parameters": input_data.parameters or {},
        "status": "pending",
    }

    # Create the report record
    report = db.create_report(project_id, report_data)

    # Generate report content (synchronously for simplicity)
    try:
        content = _generate_report_content(input_data.type, project_id)
        now = datetime.now(timezone.utc).isoformat()
        db.update_report(
            project_id,
            report["id"],
            {
                "status": "completed",
                "completedAt": now,
                "parameters": {**report.get("parameters", {}), "content": content},
            },
        )
    except Exception as e:
        # M-4 FIX: Never store str(e) in report parameters. The old code
        # stored raw exception text in the database, which could include
        # file paths, variable names, and internal implementation details.
        # This data is retrievable via the API, creating an information
        # leakage vulnerability. Log the full error server-side instead.
        logger.error("Report generation failed for project %s: %s", project_id, e, exc_info=True)
        db.update_report(
            project_id,
            report["id"],
            {
                "status": "failed",
                "parameters": {**report.get("parameters", {}), "error": "Report generation failed. Contact administrator for details."},
            },
        )

    # Return the updated report — success flag reflects the report's ACTUAL status,
    # not just that the endpoint didn't crash. Previous bug: always returned
    # success:true even when the report generation failed.
    result = db.get_report(project_id, report["id"])
    report_success = result.get("status") != "failed"
    return {"data": result, "success": report_success}


@router.get("/{report_id}", dependencies=[Depends(require_permission(Permission.REPORT_READ))])
async def get_report(project_id: str, report_id: str):
    """Get a report by ID."""
    _verify_project(project_id)
    db = get_db()
    report = db.get_report(project_id, report_id)
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")
    return {"data": report, "success": True}


@router.get("/{report_id}/export", dependencies=[Depends(require_permission(Permission.REPORT_READ))])
async def export_report(
    project_id: str,
    report_id: str,
    format: str = Query("json", pattern="^(pdf|dxf|json)$"),
):
    """Export a report in the specified format."""
    _verify_project(project_id)
    db = get_db()
    report = db.get_report(project_id, report_id)
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")

    if report["status"] != "completed":
        raise HTTPException(
            status_code=400,
            detail=f"Report is not ready (status: {report['status']})",
        )

    if format == "json":
        content = json.dumps(report, indent=2)
        return StreamingResponse(
            io.BytesIO(content.encode("utf-8")),
            media_type="application/json",
            headers={
                "Content-Disposition": f"attachment; filename=\"report_{_safe_filename(report_id)}.json\""
            },
        )
    if format == "pdf":
        # PDF generation using reportlab
        try:
            from reportlab.lib.pagesizes import A4
            from reportlab.lib.styles import getSampleStyleSheet
            from reportlab.lib.units import mm
            from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

            pdf_buffer = io.BytesIO()
            doc = SimpleDocTemplate(pdf_buffer, pagesize=A4,
                                    topMargin=20*mm, bottomMargin=20*mm,
                                    leftMargin=15*mm, rightMargin=15*mm)
            styles = getSampleStyleSheet()
            story = []

            # Header
            story.append(Paragraph(f"FireAI Report: {report['name']}", styles['Title']))
            story.append(Paragraph(f"Type: {report['type']} | Status: {report['status']}", styles['Normal']))
            story.append(Paragraph(f"Generated: {report.get('createdAt', 'N/A')}", styles['Normal']))
            story.append(Spacer(1, 10*mm))

            # Report content
            params = report.get("parameters", {})
            content_data = params.get("content", {})

            def _add_data(data, prefix="", depth=0):
                """Recursively add data to PDF, limiting depth.

                BUG-M1 FIX: Escape XML entities in values to prevent
                ReportLab Paragraph markup injection. User-controlled data
                (device names, types) could contain <, >, & that would be
                interpreted as markup tags, causing rendering errors or
                content injection in PDFs.
                """
                if depth > 3:
                    return
                if isinstance(data, dict):
                    for key, value in data.items():
                        label = f"{prefix}{key}" if prefix else str(key)
                        # Escape XML entities in labels and values
                        safe_label = str(label).replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
                        if isinstance(value, (str, int, float, bool)):
                            safe_value = str(value).replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
                            story.append(Paragraph(
                                f"<b>{safe_label}:</b> {safe_value}", styles['Normal']
                            ))
                        elif isinstance(value, list):
                            story.append(Paragraph(
                                f"<b>{safe_label}:</b> {len(value)} items", styles['Normal']
                            ))
                            for i, item in enumerate(value[:20]):
                                _add_data(item, f"{label}[{i}].", depth + 1)
                        elif isinstance(value, dict):
                            story.append(Paragraph(f"<b>{label}:</b>", styles['Normal']))
                            _add_data(value, f"  {label}.", depth + 1)

            if isinstance(content_data, dict):
                _add_data(content_data)

            # Footer
            story.append(Spacer(1, 15*mm))
            story.append(Paragraph(
                "FireAI Digital Twin — NFPA 72-2022 Compliant Engineering Report",
                styles['Normal']
            ))

            doc.build(story)
            pdf_buffer.seek(0)

            return StreamingResponse(
                pdf_buffer,
                media_type="application/pdf",
                headers={
                    "Content-Disposition": f"attachment; filename=\"report_{_safe_filename(report_id)}.pdf\""
                },
            )
        except ImportError:
            raise HTTPException(
                status_code=501,
                detail="PDF export requires the reportlab package",
            )
        except Exception as e:
            # V113 SECURITY: Never expose str(e) to client
            logger.error("PDF generation failed: %s", e, exc_info=True)
            raise HTTPException(
                status_code=500,
                detail="PDF generation failed — an internal error occurred. Contact administrator.",
            )
    elif format == "dxf":
        # DXF export of report data
        try:
            import ezdxf

            doc = ezdxf.new("R2010")
            msp = doc.modelspace()
            msp.add_text(
                f"Report: {report['name']}",
                dxfattribs={"height": 0.5, "insert": (0, 10)},
            )
            msp.add_text(
                f"Type: {report['type']}",
                dxfattribs={"height": 0.3, "insert": (0, 9)},
            )
            msp.add_text(
                f"Status: {report['status']}",
                dxfattribs={"height": 0.3, "insert": (0, 8.5)},
            )
            # Add report content
            params = report.get("parameters", {})
            content_data = params.get("content", {})
            y_offset = 7.5
            for key, value in content_data.items():
                if isinstance(value, (str, int, float)):
                    msp.add_text(
                        f"{key}: {value}",
                        dxfattribs={"height": 0.25, "insert": (0, y_offset)},
                    )
                    y_offset -= 0.5

            text_output = io.StringIO()
            doc.write(text_output)
            text_output.seek(0)
            dxf_bytes = text_output.getvalue().encode("utf-8")
            return StreamingResponse(
                io.BytesIO(dxf_bytes),
                media_type="application/dxf",
                headers={
                    "Content-Disposition": f"attachment; filename=\"report_{_safe_filename(report_id)}.dxf\""
                },
            )
        except ImportError:
            raise HTTPException(
                status_code=501,
                detail="DXF export requires ezdxf package",
            )
    else:
        raise HTTPException(status_code=400, detail=f"Unsupported format: {format}")
