"""
backend/routers/exports.py — DXF, Revit JSON, and IFC export endpoints.

These endpoints export the full project data in standard BIM/CAD formats:
  - DXF: Using ezdxf for AutoCAD-compatible output
  - Revit JSON: Structured JSON matching Revit API format
  - IFC: Using ifcopenshell for IFC4 compliance (if available)

LIFE-SAFETY NOTE: Exported data must be traceable. Each export includes
metadata about the project, export timestamp, and software version.
"""

from __future__ import annotations

import io
import json
from datetime import datetime, timezone
from urllib.parse import quote

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse

from backend.database import get_db

import logging

logger = logging.getLogger(__name__)


def _safe_filename(name: str) -> str:
    """Sanitize a project name for use in Content-Disposition headers.

    Prevents header injection by removing characters that could break
    the Content-Disposition header (quotes, semicolons, newlines, backslashes).
    This is a security-critical function — project names are user-controlled input.
    """
    # Remove characters that could break Content-Disposition headers
    safe = name.replace('"', "'").replace(';', '').replace('\n', '').replace('\r', '').replace('\\', '')
    # URL-encode any remaining special characters for extra safety
    return quote(safe, safe='-_.~')

router = APIRouter(prefix="/projects/{project_id}/export", tags=["exports"])


def _verify_project(project_id: str) -> dict:
    db = get_db()
    project = db.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


@router.get("/dxf")
async def export_dxf(project_id: str):
    """Export project as DXF (AutoCAD Drawing Exchange Format)."""
    project = _verify_project(project_id)
    db = get_db()
    devices = db.get_all_devices_for_project(project_id)
    connections = db.get_all_connections_for_project(project_id)

    try:
        import ezdxf
    except ImportError:
        raise HTTPException(
            status_code=503,
            detail={
                "success": False,
                "error": "DXF export unavailable: ezdxf package not installed",
                "install": "pip install ezdxf",
            },
        )

    doc = ezdxf.new("R2010")
    doc.header["$INSUNITS"] = 6  # Meters
    msp = doc.modelspace()

    # ── Project metadata as text ────────────────────────────────────────
    msp.add_text(
        f"FireAI Digital Twin Export - {project['name']}",
        dxfattribs={"height": 1.0, "insert": (0, 50)},
    )
    msp.add_text(
        f"Author: {project['author']} | Exported: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}",
        dxfattribs={"height": 0.5, "insert": (0, 48)},
    )

    # ── Draw devices as circles with labels ─────────────────────────────
    DEVICE_COLORS = {
        "smoke_detector": 3,    # Green
        "heat_detector": 1,     # Red
        "manual_pull": 5,      # Blue
        "notification": 6,     # Magenta
        "panel": 2,            # Yellow
        "module": 4,           # Cyan
    }

    for device in devices:
        x, y = device["x"], device["y"]
        cat = device["category"]
        color = DEVICE_COLORS.get(cat, 7)

        # Device symbol (circle)
        msp.add_circle(
            center=(x, y),
            radius=0.5,
            dxfattribs={"color": color},
        )

        # Device label
        msp.add_text(
            device["name"],
            dxfattribs={"height": 0.3, "insert": (x + 0.6, y + 0.3)},
        )

        # Device type annotation
        msp.add_text(
            f"{device['type']} ({cat})",
            dxfattribs={"height": 0.2, "insert": (x + 0.6, y - 0.1)},
        )

    # ── Draw connections as lines ───────────────────────────────────────
    device_map = {d["id"]: d for d in devices}

    for conn in connections:
        from_dev = device_map.get(conn["fromId"])
        to_dev = device_map.get(conn["toId"])
        if from_dev and to_dev:
            msp.add_line(
                start=(from_dev["x"], from_dev["y"]),
                end=(to_dev["x"], to_dev["y"]),
                dxfattribs={"color": 8},  # Grey for wiring
            )
            # Cable size annotation at midpoint
            mx = (from_dev["x"] + to_dev["x"]) / 2
            my = (from_dev["y"] + to_dev["y"]) / 2
            msp.add_text(
                conn["cableSize"],
                dxfattribs={"height": 0.15, "insert": (mx, my + 0.2)},
            )

    # ── Write DXF content ────────────────────────────────────────────────
    # ezdxf write() expects a text stream, not binary
    text_output = io.StringIO()
    doc.write(text_output)
    text_output.seek(0)
    dxf_bytes = text_output.getvalue().encode("utf-8")

    return StreamingResponse(
        io.BytesIO(dxf_bytes),
        media_type="application/dxf",
        headers={
            "Content-Disposition": f"attachment; filename=\"{_safe_filename(project['name'])}_export.dxf\""
        },
    )


@router.get("/revit")
async def export_revit(project_id: str):
    """Export project as Revit-compatible JSON."""
    project = _verify_project(project_id)
    db = get_db()
    devices = db.get_all_devices_for_project(project_id)
    connections = db.get_all_connections_for_project(project_id)

    revit_data = {
        "version": "1.0.0",
        "source": "FireAI Digital Twin",
        "exportDate": datetime.now(timezone.utc).isoformat(),
        "project": {
            "name": project["name"],
            "author": project["author"],
            "status": project["status"],
        },
        "elements": [
            {
                "elementId": d["id"],
                "name": d["name"],
                "category": d["category"],
                "type": d["type"],
                "location": {
                    "x": d["x"],
                    "y": d["y"],
                    "z": d["z"],
                    "rotation": d["rotation"],
                },
                "parameters": {
                    "voltage": d["voltage"],
                    "current": d["current"],
                    "load": d["load"],
                    **d.get("properties", {}),
                },
            }
            for d in devices
        ],
        "connections": [
            {
                "connectionId": c["id"],
                "fromElement": c["fromId"],
                "toElement": c["toId"],
                "cableSize": c["cableSize"],
                "length": c["length"],
                "type": c["type"],
            }
            for c in connections
        ],
        "metadata": {
            "totalElements": len(devices),
            "totalConnections": len(connections),
            "exportFormat": "revit_json",
        },
    }

    content = json.dumps(revit_data, indent=2)
    return StreamingResponse(
        io.BytesIO(content.encode("utf-8")),
        media_type="application/json",
        headers={
            "Content-Disposition": f"attachment; filename=\"{_safe_filename(project['name'])}_revit.json\""
        },
    )


@router.get("/ifc")
async def export_ifc(
    project_id: str,
    version: str = Query("IFC4", pattern="^(IFC2X3|IFC4)$"),
):
    """Export project as IFC (Industry Foundation Classes)."""
    project = _verify_project(project_id)
    db = get_db()
    devices = db.get_all_devices_for_project(project_id)
    connections = db.get_all_connections_for_project(project_id)

    try:
        import ifcopenshell
        import ifcopenshell.api
    except ImportError:
        # If ifcopenshell is not available, return a structured JSON
        # representation that documents the IFC structure
        ifc_fallback = {
            "note": "ifcopenshell not available. Returning IFC-structured JSON.",
            "version": version,
            "source": "FireAI Digital Twin",
            "exportDate": datetime.now(timezone.utc).isoformat(),
            "project": {
                "name": project["name"],
                "author": project["author"],
            },
            "ifcProducts": [
                {
                    "ifcType": "IfcBuildingElementProxy",
                    "name": d["name"],
                    "category": d["category"],
                    "type": d["type"],
                    "location": {"x": d["x"], "y": d["y"], "z": d["z"]},
                    "properties": d.get("properties", {}),
                }
                for d in devices
            ],
            "ifcRelations": [
                {
                    "ifcType": "IfcRelConnects",
                    "fromElement": c["fromId"],
                    "toElement": c["toId"],
                    "cableSize": c["cableSize"],
                    "length": c["length"],
                }
                for c in connections
            ],
        }
        content = json.dumps(ifc_fallback, indent=2)
        return StreamingResponse(
            io.BytesIO(content.encode("utf-8")),
            media_type="application/json",
            headers={
                "Content-Disposition": f"attachment; filename=\"{_safe_filename(project['name'])}_ifc.json\""
            },
        )

    # ── Full IFC export using ifcopenshell ──────────────────────────────
    try:
        schema = "IFC4" if version == "IFC4" else "IFC2X3"
        ifc_file = ifcopenshell.api.run("project.create_file")

        project_ifc = ifcopenshell.api.run(
            "root.create_entity",
            ifc_file,
            ifc_class="IfcProject",
            name=project["name"],
        )

        # Create basic spatial structure
        site = ifcopenshell.api.run(
            "root.create_entity", ifc_file, ifc_class="IfcSite"
        )
        building = ifcopenshell.api.run(
            "root.create_entity", ifc_file, ifc_class="IfcBuilding"
        )
        storey = ifcopenshell.api.run(
            "root.create_entity", ifc_file, ifc_class="IfcBuildingStorey"
        )

        ifcopenshell.api.run("aggregate.assign_object", ifc_file, product=site, relating_object=project_ifc)
        ifcopenshell.api.run("aggregate.assign_object", ifc_file, product=building, relating_object=site)
        ifcopenshell.api.run("aggregate.assign_object", ifc_file, product=storey, relating_object=building)

        # Add devices as building element proxies
        for device in devices:
            proxy = ifcopenshell.api.run(
                "root.create_entity",
                ifc_file,
                ifc_class="IfcBuildingElementProxy",
                name=device["name"],
            )
            ifcopenshell.api.run(
                "spatial.assign_container", ifc_file, product=proxy, relating_structure=storey
            )

        output = io.BytesIO()
        ifc_file.write(output)
        output.seek(0)

        return StreamingResponse(
            io.BytesIO(output.getvalue()),
            media_type="application/ifc",
            headers={
                "Content-Disposition": f"attachment; filename=\"{_safe_filename(project['name'])}.ifc\""
            },
        )
    except Exception as e:
        # V113 SECURITY: Never expose str(e) to client — may contain
        # server paths (/home/...), Python class names, internal state.
        # In a safety-critical system, this information helps attackers
        # craft targeted exploits. Log internally only.
        logger.error(f"IFC export failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="IFC export failed — an internal error occurred. Contact administrator.",
        )
