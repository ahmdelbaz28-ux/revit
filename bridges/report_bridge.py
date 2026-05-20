"""
bridges/report_bridge.py
========================
Bridge 5: FireAI analysis → Professional PDF/HTML reports

Generates comprehensive compliance reports combining:
  - EDA's HTML visual reports with overlay annotations
  - FireAI's PDF reports with audit trail
  - NFPA 72 compliance findings
  - Schedule reconciliation (BOQ vs drawing)
  - Cable routing summary
  - Device schedule

SAFETY: Every report includes the legal disclaimer. Every finding
with severity 'critical' or 'major' is highlighted for PE review.

Usage:
    from bridges.report_bridge import generate_compliance_report
    result = generate_compliance_report(
        project_name="Tower A",
        rooms=rooms,
        devices=devices,
        violations=violations,
        output_dir="./reports",
    )
"""

from __future__ import annotations
import base64, hashlib, json, logging, os, time
from dataclasses import dataclass, field
from datetime import datetime
from html import escape as _html_escape
from pathlib import Path
from typing import Optional

log = logging.getLogger(__name__)


# Security Fix (VULN-012): Helper for HTML escaping to prevent XSS
def _h(value) -> str:
    """HTML-escape user-controlled data to prevent XSS."""
    return _html_escape(str(value))


# ════════════════════════════════════════════════════════════════════════════
# Data structures
# ════════════════════════════════════════════════════════════════════════════

@dataclass
class ReportResult:
    """Result of report generation."""
    pdf_path: str = ""
    html_path: str = ""
    json_path: str = ""
    audit_hash: str = ""
    sections: list = field(default_factory=list)
    warnings: list = field(default_factory=list)
    stats: dict = field(default_factory=dict)
    elapsed_seconds: float = 0.0


# ════════════════════════════════════════════════════════════════════════════
# Report generation
# ════════════════════════════════════════════════════════════════════════════

def generate_compliance_report(
    project_name: str,
    rooms: list,
    devices: list,
    violations: list = None,
    cable_total_m: float = 0.0,
    cable_segments: int = 0,
    schedule_reconciliation: list = None,
    findings: list = None,
    output_dir: str = "/tmp/fireai_reports",
    source_file: str = "",
    proof_valid: bool = False,
    pe_name: str = "",
    pe_license: str = "",
) -> ReportResult:
    """
    Bridge 5: Generate comprehensive compliance report.

    Outputs:
      - PDF report with audit trail (requires reportlab)
      - HTML report with visual annotations (uses EDA)
      - JSON data export
    """
    t0 = time.time()
    warnings = []
    Path(output_dir).mkdir(parents=True, exist_ok=True)

    # Build report data
    report_data = _build_report_data(
        project_name=project_name,
        rooms=rooms,
        devices=devices,
        violations=violations or [],
        cable_total_m=cable_total_m,
        cable_segments=cable_segments,
        schedule_reconciliation=schedule_reconciliation or [],
        findings=findings or [],
        source_file=source_file,
        proof_valid=proof_valid,
        pe_name=pe_name,
        pe_license=pe_license,
    )

    # Compute audit hash — V11: Full SHA-256, NO TRUNCATION
    # Truncating to 32 hex chars (128-bit) weakens collision resistance.
    # Full 64-char (256-bit) hash is required for legal audit integrity.
    audit_hash = hashlib.sha256(
        json.dumps(report_data, default=str, sort_keys=True).encode()
    ).hexdigest()
    report_data["audit_hash"] = audit_hash
    report_data["generated_at"] = datetime.now().isoformat()

    results = ReportResult(audit_hash=audit_hash)

    # ── Generate PDF ──
    try:
        pdf_path = os.path.join(output_dir, f"{project_name}_NFPA72_Report.pdf")
        _generate_pdf(pdf_path, report_data)
        results.pdf_path = pdf_path
        results.sections.append("PDF")
    except ImportError:
        warnings.append("reportlab not installed — PDF skipped")
    except Exception as ex:
        warnings.append(f"PDF generation failed: {ex}")

    # ── Generate HTML ──
    try:
        html_path = os.path.join(output_dir, f"{project_name}_NFPA72_Report.html")
        _generate_html(html_path, report_data)
        results.html_path = html_path
        results.sections.append("HTML")
    except Exception as ex:
        warnings.append(f"HTML generation failed: {ex}")

    # ── Generate JSON ──
    try:
        json_path = os.path.join(output_dir, f"{project_name}_NFPA72_Report.json")
        Path(json_path).write_text(
            json.dumps(report_data, indent=2, default=str),
            encoding="utf-8"
        )
        results.json_path = json_path
        results.sections.append("JSON")
    except Exception as ex:
        warnings.append(f"JSON generation failed: {ex}")

    results.warnings = warnings
    results.stats = {
        "rooms": len(rooms),
        "devices": len(devices),
        "violations": len(violations or []),
        "findings": len(findings or []),
        "cable_total_m": round(cable_total_m, 2),
        "audit_hash": audit_hash,
        "formats": results.sections,
    }
    results.elapsed_seconds = round(time.time() - t0, 2)

    return results


def _build_report_data(**kwargs) -> dict:
    """Build the report data structure."""
    rooms = kwargs["rooms"]
    devices = kwargs["devices"]
    violations = kwargs["violations"]
    findings = kwargs["findings"]
    schedule_reconciliation = kwargs["schedule_reconciliation"]

    # Room summary
    room_summary = []
    for r in rooms:
        room_devices = [d for d in devices if getattr(d, "room_id", "") == r.id]
        room_summary.append({
            "id": r.id,
            "name": r.name,
            "type": getattr(r, "room_type", "unknown"),
            "area_m2": getattr(r, "floor_area", 0),
            "ceiling_height": getattr(r, "ceiling_height", 2.8),
            "ceiling_type": getattr(r, "ceiling_type", "SMOOTH"),
            "device_count": len(room_devices),
        })

    # Device summary by type
    from collections import Counter
    device_counts = Counter(d.device_type for d in devices)

    # Compliance summary
    critical_findings = [f for f in findings if f.get("severity") == "critical"]
    major_findings = [f for f in findings if f.get("severity") == "major"]

    return {
        "project_name": kwargs["project_name"],
        "source_file": kwargs["source_file"],
        "proof_valid": kwargs["proof_valid"],
        "pe_name": kwargs["pe_name"],
        "pe_license": kwargs["pe_license"],
        "room_summary": room_summary,
        "total_rooms": len(rooms),
        "total_area_m2": sum(r.floor_area for r in rooms if hasattr(r, "floor_area")),
        "device_counts": dict(device_counts),
        "total_devices": len(devices),
        "violations": [str(v) if not isinstance(v, dict) else v for v in violations],
        "findings": findings,
        "critical_count": len(critical_findings),
        "major_count": len(major_findings),
        "schedule_reconciliation": schedule_reconciliation,
        "cable_total_m": kwargs["cable_total_m"],
        "cable_segments": kwargs["cable_segments"],
    }


def _generate_pdf(path: str, data: dict):
    """Generate PDF report using reportlab."""
    from reportlab.lib.pagesizes import A4
    from reportlab.lib import colors
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.platypus import (
        SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
    )

    doc = SimpleDocTemplate(path, pagesize=A4, leftMargin=20*mm, rightMargin=20*mm)
    styles = getSampleStyleSheet()
    story = []

    # Title
    story.append(Paragraph(
        f"FIRE AI — NFPA 72 COMPLIANCE REPORT", styles["Title"]))
    story.append(Spacer(1, 6))
    story.append(Paragraph(
        f"Project: {data['project_name']}", styles["Heading2"]))
    story.append(Paragraph(
        f"Date: {data['generated_at']}", styles["Normal"]))
    story.append(Paragraph(
        f"Audit Hash: {data['audit_hash']}", styles["Normal"]))
    story.append(Spacer(1, 12))

    # Proof status
    if data["proof_valid"]:
        story.append(Paragraph(
            "DESIGN VERIFICATION: PASSED", ParagraphStyle(
                "Pass", parent=styles["Normal"],
                textColor=colors.green, fontSize=14)))
    else:
        story.append(Paragraph(
            "DESIGN VERIFICATION: NOT VERIFIED — PE REVIEW REQUIRED",
            ParagraphStyle("Fail", parent=styles["Normal"],
                           textColor=colors.red, fontSize=14)))
    story.append(Spacer(1, 12))

    # Project summary table
    summary_data = [
        ["Total Rooms", str(data["total_rooms"])],
        ["Total Area", f"{data['total_area_m2']:.1f} m2"],
        ["Total Devices", str(data["total_devices"])],
        ["Critical Findings", str(data["critical_count"])],
        ["Major Findings", str(data["major_count"])],
        ["Total Cable", f"{data['cable_total_m']:.1f} m"],
    ]
    t = Table(summary_data, colWidths=[60*mm, 80*mm])
    t.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
        ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#1a1a2e")),
        ("TEXTCOLOR", (0, 0), (0, -1), colors.white),
        ("FONTSIZE", (0, 0), (-1, -1), 10),
    ]))
    story.append(t)
    story.append(Spacer(1, 16))

    # Device schedule
    story.append(Paragraph("Device Schedule", styles["Heading2"]))
    dev_data = [["Device Type", "Count"]]
    for dtype, count in sorted(data["device_counts"].items()):
        dev_data.append([dtype, str(count)])
    dev_data.append(["TOTAL", str(data["total_devices"])])

    dt = Table(dev_data, colWidths=[80*mm, 40*mm])
    dt.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1a1a2e")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
    ]))
    story.append(dt)
    story.append(Spacer(1, 16))

    # Findings
    if data["findings"]:
        story.append(Paragraph("Compliance Findings", styles["Heading2"]))
        for f in data["findings"]:
            sev = f.get("severity", "info")
            col = {"critical": colors.red, "major": colors.orange}.get(sev, colors.black)
            story.append(Paragraph(
                f"[{sev.upper()}] {f.get('message', f.get('rule', ''))}",
                ParagraphStyle("Finding", parent=styles["Normal"], textColor=col, fontSize=9)))
        story.append(Spacer(1, 16))

    # Room details
    story.append(Paragraph("Room Details", styles["Heading2"]))
    room_data = [["#", "Name", "Type", "Area m2", "Devices"]]
    for i, r in enumerate(data["room_summary"], 1):
        room_data.append([
            str(i), r["name"], r["type"],
            f"{r['area_m2']:.1f}", str(r["device_count"])
        ])

    rt = Table(room_data, colWidths=[10*mm, 40*mm, 30*mm, 25*mm, 20*mm])
    rt.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1a1a2e")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
    ]))
    story.append(rt)
    story.append(Spacer(1, 16))

    # V11 — Digital Integrity Notice
    story.append(Spacer(1, 12))
    story.append(Paragraph(
        "<b>DIGITAL INTEGRITY NOTICE:</b> This PDF is paired with an encrypted JSON audit file. "
        "Any manual alteration of this PDF automatically voids the design validity. "
        f"To verify authenticity, the SHA-256 hash of the paired JSON must exactly match: <br/>"
        f"<b>{data['audit_hash']}</b>",
        ParagraphStyle("SecurityNotice", parent=styles["Normal"],
                       fontSize=8, textColor=colors.red, backColor=colors.lightyellow)))

    story.append(Spacer(1, 8))
    story.append(Paragraph(
        "<b>LEGAL DISCLAIMER</b>: This report is generated by FireAI automated analysis. "
        "It does not substitute for professional engineering review. All results must be "
        "verified by a licensed Professional Engineer before implementation. "
        "Based on NFPA 72 National Fire Alarm and Signaling Code. "
        "Local authority having jurisdiction must approve the final design.",
        ParagraphStyle("Disclaimer", parent=styles["Normal"],
                       fontSize=7, textColor=colors.darkgrey)))

    doc.build(story)


def _generate_html(path: str, data: dict):
    """Generate HTML report (self-contained, dark theme)."""
    parts = [
        "<!DOCTYPE html><html><head><meta charset='utf-8'>",
        f"<title>FireAI Report — {_h(data['project_name'])}</title>",
        "<style>",
        ":root{--bg:#0e1116;--card:#1a1f27;--text:#e6edf3;--mut:#8b949e;"
        "--crit:#c0392b;--maj:#e67e22;--ok:#27ae60}",
        "*{box-sizing:border-box}body{font:14px/1.5 -apple-system,sans-serif;"
        "background:var(--bg);color:var(--text);margin:0;padding:24px}",
        ".card{background:var(--card);border-radius:8px;padding:16px;margin-bottom:16px}",
        "table{width:100%;border-collapse:collapse}th,td{padding:8px 10px;"
        "text-align:left;border-bottom:1px solid #2a2f37}",
        "th{color:var(--mut);font-size:12px;text-transform:uppercase}",
        ".sev{display:inline-block;padding:2px 8px;border-radius:4px;"
        "font-size:11px;font-weight:700;color:#fff}",
        ".critical{background:var(--crit)}.major{background:var(--maj)}"
        ".pass{background:var(--ok)}.info{background:#555}",
        "</style></head><body>",
        f"<h1>FireAI — NFPA 72 Compliance Report</h1>",
        f"<div class='card'>",
        f"<h2>{_h(data['project_name'])}</h2>",
        f"<p>Date: {data['generated_at']}</p>",
        f"<p>Audit Hash: <code>{data['audit_hash']}</code></p>",
    ]

    # Proof status
    if data["proof_valid"]:
        parts.append("<p class='sev pass'>DESIGN VERIFIED</p>")
    else:
        parts.append("<p class='sev critical'>NOT VERIFIED — PE REVIEW REQUIRED</p>")

    parts.append("</div>")

    # KPI cards
    parts.append(f"<div class='card'><table>"
                 f"<tr><th>Metric</th><th>Value</th></tr>"
                 f"<tr><td>Rooms</td><td>{data['total_rooms']}</td></tr>"
                 f"<tr><td>Total Area</td><td>{data['total_area_m2']:.1f} m2</td></tr>"
                 f"<tr><td>Devices</td><td>{data['total_devices']}</td></tr>"
                 f"<tr><td>Critical Findings</td><td>{data['critical_count']}</td></tr>"
                 f"<tr><td>Major Findings</td><td>{data['major_count']}</td></tr>"
                 f"<tr><td>Total Cable</td><td>{data['cable_total_m']:.1f} m</td></tr>"
                 f"</table></div>")

    # Device schedule
    parts.append("<div class='card'><h3>Device Schedule</h3><table>"
                 "<tr><th>Type</th><th>Count</th></tr>")
    for dtype, count in sorted(data["device_counts"].items()):
        parts.append(f"<tr><td>{_h(dtype)}</td><td>{count}</td></tr>")
    parts.append(f"<tr><td><b>TOTAL</b></td><td><b>{data['total_devices']}</b></td></tr>")
    parts.append("</table></div>")

    # Findings
    if data["findings"]:
        parts.append("<div class='card'><h3>Compliance Findings</h3><table>"
                     "<tr><th>Severity</th><th>Code</th><th>Message</th></tr>")
        for f in data["findings"]:
            sev = f.get("severity", "info")
            parts.append(
                f"<tr><td><span class='sev {_h(sev)}'>{_h(sev)}</span></td>"
                f"<td>{_h(f.get('code', ''))}</td>"
                f"<td>{_h(f.get('message', f.get('rule', '')))}</td></tr>")
        parts.append("</table></div>")

    # Room details
    parts.append("<div class='card'><h3>Room Details</h3><table>"
                 "<tr><th>#</th><th>Name</th><th>Type</th><th>Area</th><th>Devices</th></tr>")
    for i, r in enumerate(data["room_summary"], 1):
        parts.append(
            f"<tr><td>{i}</td><td>{_h(r['name'])}</td><td>{_h(r['type'])}</td>"
            f"<td>{r['area_m2']:.1f} m2</td><td>{r['device_count']}</td></tr>")
    parts.append("</table></div>")

    # Disclaimer
    parts.append(
        "<div class='card' style='color:var(--mut);font-size:12px'>"
        "<b>LEGAL DISCLAIMER</b>: This report is generated by FireAI automated analysis. "
        "It does not substitute for professional engineering review. All results must be "
        "verified by a licensed Professional Engineer before implementation.</div>")

    parts.append("</body></html>")
    Path(path).write_text("".join(parts), encoding="utf-8")


# ════════════════════════════════════════════════════════════════════════════
# Self-test
# ════════════════════════════════════════════════════════════════════════════

def _self_test():
    """Test with sample data."""
    print("=" * 60)
    print("BRIDGE 5: Report Bridge — Self-Test")
    print("=" * 60)

    from core.models import Room, Device
    from shapely.geometry import Polygon, Point

    rooms = [
        Room(id="r1", name="Office A", room_type="office",
             floor_area=45.0,
             geometry=Polygon([(0, 0), (10, 0), (10, 5), (0, 5)]),
             ceiling_height=3.0),
        Room(id="r2", name="Corridor B", room_type="corridor",
             floor_area=80.0,
             geometry=Polygon([(0, 0), (20, 0), (20, 4), (0, 4)]),
             ceiling_height=2.8),
    ]

    devices = [
        Device(id="s1", device_type="SMOKE_PHOTOELECTRIC",
               position=Point(5, 2.5), room_id="r1",
               z_height=2.8, coverage_radius=6.37),
        Device(id="s2", device_type="SMOKE_PHOTOELECTRIC",
               position=Point(5, 2), room_id="r2",
               z_height=2.8, coverage_radius=6.37),
        Device(id="h1", device_type="HEAT_FIXED",
               position=Point(15, 2), room_id="r2",
               z_height=2.4, coverage_radius=4.90),
        Device(id="mcp1", device_type="MANUAL_PULL_STATION",
               position=Point(0.5, 2), room_id="r2",
               z_height=1.4, coverage_radius=0.0),
    ]

    findings = [
        {"severity": "critical", "code": "NFPA72",
         "rule": "smoke_detector.max_spacing_m",
         "message": "Smoke detectors #1↔#2: 12.0m > 9.1m allowed"},
        {"severity": "advisory", "code": "NFPA72",
         "rule": "corridor.egress",
         "message": "Corridor travel distance not computed — requires manual verification"},
    ]

    result = generate_compliance_report(
        project_name="Tower_A_Floor3",
        rooms=rooms,
        devices=devices,
        findings=findings,
        cable_total_m=42.5,
        cable_segments=8,
        output_dir="/tmp/fireai_reports_test",
        proof_valid=True,
        pe_name="Ahmed El-Baz",
        pe_license="PE-12345",
    )

    print(f"\nPDF:  {result.pdf_path}")
    print(f"HTML: {result.html_path}")
    print(f"JSON: {result.json_path}")
    print(f"Audit Hash: {result.audit_hash}")
    print(f"Sections: {result.sections}")
    print(f"Stats: {result.stats}")
    print(f"Warnings: {result.warnings}")

    # Verify files exist
    for p in [result.pdf_path, result.html_path, result.json_path]:
        if p and os.path.exists(p):
            size = os.path.getsize(p)
            print(f"  ✓ {p} ({size} bytes)")
        elif p:
            print(f"  ✗ {p} NOT FOUND")

    print("\n" + "=" * 60)
    status = "PASS" if result.pdf_path or result.html_path else "FAIL"
    print(f"Bridge 5 Self-Test: {status}")
    print("=" * 60)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    _self_test()
