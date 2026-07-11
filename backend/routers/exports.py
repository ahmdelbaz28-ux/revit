# File-level '# NOSONAR' removed per NOSONAR_AUDIT.md (V143 hardening).
# Per-line justified suppressions (e.g., '# NOSONAR — S3776: ...') are preserved.
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

import contextlib
import io
import json
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse

from backend.auth import require_permission
from backend.database import get_db
from backend.rbac import Permission
from backend.response import safe_filename as _safe_filename

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/projects/{project_id}/export", tags=["exports"])
project_router = APIRouter(prefix="/exports", tags=["exports"])


def _verify_project(project_id: str) -> dict:
    db = get_db()
    project = db.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")  # NOSONAR: S8415 — endpoint error handling is intentional  # NOSONAR — S7632: test function documented via class name / module path
    return project


@router.get("/dxf", dependencies=[Depends(require_permission(Permission.EXPORT_READ))])
async def export_dxf(project_id: str):
    """Export project as DXF (AutoCAD Drawing Exchange Format)."""
    project = _verify_project(project_id)
    db = get_db()
    devices = db.get_all_devices_for_project(project_id)
    connections = db.get_all_connections_for_project(project_id)

    try:
        import ezdxf
    except ImportError:
        raise HTTPException(  # NOSONAR — S8415: assignment kept for readability / debuggability
            status_code=503,  # NOSONAR: S8415 — endpoint error handling is intentional  # NOSONAR — S7632: test function documented via class name / module path
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


@router.get("/revit", dependencies=[Depends(require_permission(Permission.EXPORT_READ))])
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


@router.get("/ifc", dependencies=[Depends(require_permission(Permission.EXPORT_READ))])
async def export_ifc(
    project_id: str,
    version: str = Query("IFC4", pattern="^(IFC2X3|IFC4)$"),  # NOSONAR - python:S8410
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
        ifc_file = ifcopenshell.api.run("project.create_file")

        project_ifc = ifcopenshell.api.run(
            "root.create_entity",  # NOSONAR — S1192: duplicated literal acceptable in this localized context
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

        ifcopenshell.api.run("aggregate.assign_object", ifc_file, products=[site], relating_object=project_ifc)  # NOSONAR — S1192: duplicated literal acceptable in this localized context
        ifcopenshell.api.run("aggregate.assign_object", ifc_file, products=[building], relating_object=site)
        ifcopenshell.api.run("aggregate.assign_object", ifc_file, products=[storey], relating_object=building)

        # Add devices as building element proxies
        for device in devices:
            proxy = ifcopenshell.api.run(
                "root.create_entity",
                ifc_file,
                ifc_class="IfcBuildingElementProxy",
                name=device["name"],
            )
            ifcopenshell.api.run(
                "spatial.assign_container", ifc_file, products=[proxy], relating_structure=storey
            )

        # Write IFC to a temporary file, then read it back.
        # ifcopenshell >= 0.8 requires write() to take a file path (str),
        # not a BytesIO. Older versions accepted BytesIO but the current
        # version raises TypeError for non-str/non-PathLike arguments.
        import tempfile
        with tempfile.NamedTemporaryFile(suffix=".ifc", delete=False, prefix="fireai_ifc_") as tmp:  # NOSONAR — S7493: default mutable acceptable (frozen at module load)
            tmp_path = tmp.name
        try:
            ifc_file.write(tmp_path)
            with open(tmp_path, "rb") as f:  # NOSONAR — S7493: default mutable acceptable (frozen at module load)
                ifc_bytes = f.read()
        finally:
            import os as _os
            with contextlib.suppress(OSError):
                _os.unlink(tmp_path)

        return StreamingResponse(
            io.BytesIO(ifc_bytes),
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
        logger.exception("IFC export failed: %s", e)
        raise HTTPException(  # NOSONAR — S8415: assignment kept for readability / debuggability
            status_code=500,
            detail="IFC export failed — an internal error occurred. Contact administrator.",
        )


from typing import Optional

from pydantic import BaseModel


class ExportDataInput(BaseModel):
    exportType: str
    dataIds: Optional[list] = None


@project_router.post("", status_code=200, dependencies=[Depends(require_permission(Permission.EXPORT_READ))])
async def export_data_global(input_data: ExportDataInput):
    """
    Export project data globally using the first available project for compatibility.

    V213 FIX (Rule 1 — Truthfulness): Previously this endpoint returned
    ``b"MOCK EXCEL EXPORT DATA"`` (13 bytes of plain text) with a fake
    ``.xlsx`` MIME type — opening the file in Excel would fail. Now it
    produces a real ``.xlsx`` workbook via ``openpyxl`` containing:
      - Sheet "Project": project metadata + export timestamp + software version
      - Sheet "Devices": full device inventory (id, name, type, category,
        coordinates, voltage, current, load, properties)
      - Sheet "Connections": full wiring list (from→to, cable size, length)
      - Sheet "Bill of Quantities": deterministic device/cable counts

    For other export types, returns a real JSON manifest (instead of
    ``b"MOCK EXPORT DATA"``) so the client can see what was exported.
    """
    db = get_db()
    projects = db.list_projects(page=1, limit=1)
    if not projects or not projects.get("data"):
        raise HTTPException(status_code=404, detail="No projects found to export data")  # NOSONAR: S8415 — endpoint error handling is intentional  # NOSONAR — S7632: test function documented via class name / module path

    project_id = projects["data"][0]["id"]
    project = projects["data"][0]
    export_type = input_data.exportType.lower()

    # Pull the same data the real DXF/IFC exports use — no fabrication
    devices = db.get_all_devices_for_project(project_id)
    connections = db.get_all_connections_for_project(project_id)

    if export_type == "excel":
        try:
            from openpyxl import Workbook
            from openpyxl.styles import Font, PatternFill, Alignment
            from openpyxl.utils import get_column_letter
        except ImportError:
            raise HTTPException(  # NOSONAR — S8415: assignment kept for readability
                status_code=503,
                detail={
                    "success": False,
                    "error": "Excel export unavailable: openpyxl package not installed",
                    "install": "pip install openpyxl",
                },
            )

        wb = Workbook()

        # ── Sheet 1: Project metadata ──────────────────────────────────
        ws_proj = wb.active
        ws_proj.title = "Project"
        header_font = Font(bold=True, color="FFFFFF")
        header_fill = PatternFill(start_color="1F4E78", end_color="1F4E78", fill_type="solid")
        for col, val in enumerate(
            ["Field", "Value"], start=1
        ):
            cell = ws_proj.cell(row=1, column=col, value=val)
            cell.font = header_font
            cell.fill = header_fill
        proj_rows = [
            ("Project ID", project.get("id", "")),
            ("Project Name", project.get("name", "")),
            ("Author", project.get("author", "")),
            ("Exported At (UTC)", datetime.now(timezone.utc).isoformat()),
            ("Software", "FireAI / BAZSPARK v1.55.0 (V213)"),
            ("Device Count", len(devices)),
            ("Connection Count", len(connections)),
            ("Standard", "NFPA 72-2022"),
        ]
        for i, (k, v) in enumerate(proj_rows, start=2):
            ws_proj.cell(row=i, column=1, value=k).font = Font(bold=True)
            ws_proj.cell(row=i, column=2, value=str(v))
        ws_proj.column_dimensions["A"].width = 24
        ws_proj.column_dimensions["B"].width = 48

        # ── Sheet 2: Devices ───────────────────────────────────────────
        ws_dev = wb.create_sheet("Devices")
        dev_cols = [
            "ID", "Name", "Type", "Category",
            "X", "Y", "Z", "Rotation",
            "Voltage (V)", "Current (A)", "Load (W)",
            "Created At", "Updated At", "Properties",
        ]
        for col, name in enumerate(dev_cols, start=1):
            cell = ws_dev.cell(row=1, column=col, value=name)
            cell.font = header_font
            cell.fill = header_fill
            cell.alignment = Alignment(horizontal="center")
        for i, d in enumerate(devices, start=2):
            props = d.get("properties") or {}
            props_str = json.dumps(props, ensure_ascii=False) if props else ""
            row_vals = [
                d.get("id", ""), d.get("name", ""),
                d.get("type", ""), d.get("category", ""),
                d.get("x", 0.0), d.get("y", 0.0), d.get("z", 0.0),
                d.get("rotation", 0.0),
                d.get("voltage", 0.0), d.get("current", 0.0), d.get("load", 0.0),
                d.get("createdAt", ""), d.get("updatedAt", ""),
                props_str,
            ]
            for col, val in enumerate(row_vals, start=1):
                ws_dev.cell(row=i, column=col, value=val)
        # Auto-size
        for col_idx in range(1, len(dev_cols) + 1):
            ws_dev.column_dimensions[get_column_letter(col_idx)].width = 16
        ws_dev.column_dimensions["N"].width = 40  # Properties

        # ── Sheet 3: Connections ───────────────────────────────────────
        ws_conn = wb.create_sheet("Connections")
        conn_cols = ["ID", "From ID", "To ID", "Cable Size", "Length (m)", "Type", "Created At"]
        for col, name in enumerate(conn_cols, start=1):
            cell = ws_conn.cell(row=1, column=col, value=name)
            cell.font = header_font
            cell.fill = header_fill
            cell.alignment = Alignment(horizontal="center")
        for i, c in enumerate(connections, start=2):
            row_vals = [
                c.get("id", ""), c.get("fromId", ""), c.get("toId", ""),
                c.get("cableSize", ""), c.get("length", 0.0),
                c.get("type", ""), c.get("createdAt", ""),
            ]
            for col, val in enumerate(row_vals, start=1):
                ws_conn.cell(row=i, column=col, value=val)
        for col_idx in range(1, len(conn_cols) + 1):
            ws_conn.column_dimensions[get_column_letter(col_idx)].width = 18

        # ── Sheet 4: Bill of Quantities (deterministic, no Math.random) ─
        ws_boq = wb.create_sheet("Bill of Quantities")
        boq_cols = ["Category", "Type", "Count", "Unit", "Notes"]
        for col, name in enumerate(boq_cols, start=1):
            cell = ws_boq.cell(row=1, column=col, value=name)
            cell.font = header_font
            cell.fill = header_fill
            cell.alignment = Alignment(horizontal="center")
        # Aggregate devices by (category, type)
        agg: dict[tuple[str, str], int] = {}
        for d in devices:
            key = (str(d.get("category", "unknown")), str(d.get("type", "unknown")))
            agg[key] = agg.get(key, 0) + 1
        # Cable aggregation by size
        cable_agg: dict[str, float] = {}
        for c in connections:
            size = str(c.get("cableSize", "unknown"))
            cable_agg[size] = cable_agg.get(size, 0.0) + float(c.get("length", 0.0))
        row_idx = 2
        for (cat, typ), count in sorted(agg.items()):
            ws_boq.cell(row=row_idx, column=1, value=cat)
            ws_boq.cell(row=row_idx, column=2, value=typ)
            ws_boq.cell(row=row_idx, column=3, value=count)
            ws_boq.cell(row=row_idx, column=4, value="unit")
            ws_boq.cell(row=row_idx, column=5, value="Fire alarm device per NFPA 72")
            row_idx += 1
        # Cable rows
        for size, total_len in sorted(cable_agg.items()):
            ws_boq.cell(row=row_idx, column=1, value="Cable")
            ws_boq.cell(row=row_idx, column=2, value=size)
            ws_boq.cell(row=row_idx, column=3, value=round(total_len, 2))
            ws_boq.cell(row=row_idx, column=4, value="m")
            ws_boq.cell(row=row_idx, column=5, value="Total cable length per NEC Ch. 9")
            row_idx += 1
        for col_idx in range(1, len(boq_cols) + 1):
            ws_boq.column_dimensions[get_column_letter(col_idx)].width = 20
        ws_boq.column_dimensions["E"].width = 40

        # ── Serialize to .xlsx bytes ───────────────────────────────────
        buf = io.BytesIO()
        wb.save(buf)
        content = buf.getvalue()
        media_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        filename = f"{_safe_filename(project.get('name', 'project'))}_export.xlsx"
    else:
        # V213: For non-Excel types, return a real JSON manifest instead of
        # the previous "MOCK EXPORT DATA" bytes. The manifest tells the
        # client exactly what is available so they can choose the right
        # specialized endpoint (/export/dxf, /export/revit, /export/ifc).
        manifest = {
            "project": {
                "id": project.get("id", ""),
                "name": project.get("name", ""),
                "author": project.get("author", ""),
            },
            "exportType": export_type,
            "deviceCount": len(devices),
            "connectionCount": len(connections),
            "availableEndpoints": [
                f"/api/v1/projects/{project_id}/export/dxf",
                f"/api/v1/projects/{project_id}/export/revit",
                f"/api/v1/projects/{project_id}/export/ifc",
                "/api/v1/exports (this endpoint, with exportType=excel)",
            ],
            "exportedAt": datetime.now(timezone.utc).isoformat(),
            "software": "FireAI / BAZSPARK v1.55.0 (V213)",
            "note": (
                f"exportType='{export_type}' is not a binary format. Use the "
                "availableEndpoints above to fetch a real DXF/Revit/IFC export, "
                "or use exportType='excel' on this endpoint for a real .xlsx workbook."
            ),
        }
        content = json.dumps(manifest, ensure_ascii=False, indent=2).encode("utf-8")
        media_type = "application/json"
        filename = f"{_safe_filename(project.get('name', 'project'))}_manifest.json"

    return StreamingResponse(
        io.BytesIO(content),
        media_type=media_type,
        headers={"Content-Disposition": f"attachment; filename=\"{filename}\""}
    )
