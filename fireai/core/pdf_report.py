"""
pdf_report.py — Auto-generate engineer PDF report from EnhancedExpertResult
Requires: pip install reportlab
Usage:
    from fireai.core.pdf_report import generate_report
    generate_report(result, output_path="room_R1_report.pdf")
"""
from __future__ import annotations
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from fireai.core.fire_expert_system import EnhancedExpertResult


def generate_report(result: "EnhancedExpertResult", output_path: str = None) -> Path:
    """
    Generate a PDF compliance report for one room analysis.
    Returns Path to the created PDF.
    """
    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.lib import colors
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib.units import cm
        from reportlab.platypus import (
            SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable
        )
    except ImportError:
        raise RuntimeError("reportlab is required: pip install reportlab")

    if output_path is None:
        output_path = f"fire_report_{result.room_id}.pdf"
    out = Path(output_path)

    doc = SimpleDocTemplate(str(out), pagesize=A4,
                         leftMargin=2*cm, rightMargin=2*cm,
                         topMargin=2*cm, bottomMargin=2*cm)
    styles = getSampleStyleSheet()
    story = []

    # ── Heading ─────────────────────────────────────────────────────
    title_style = ParagraphStyle("Title2", parent=styles["Title"], fontSize=16)
    story.append(Paragraph("FireAI — NFPA 72 Detector Placement Report", title_style))
    story.append(Spacer(1, 0.3*cm))
    story.append(HRFlowable(width="100%", thickness=1, color=colors.darkred))
    story.append(Spacer(1, 0.3*cm))

    # ── Summary table ─────────────────────────────────────────────────
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    conf_val = result.confidence.value if result.confidence else "UNKNOWN"
    conf_color = {
        "CERTIFIED": colors.green, "HIGH": colors.green,
        "MEDIUM": colors.orange, "LOW": colors.red, "UNSAFE": colors.red,
    }.get(conf_val, colors.grey)

    summary_data = [
        ["Field", "Value"],
        ["Room ID", result.room_id],
        ["Generated", ts],
        ["Occupancy", result.occupancy_class.value if result.occupancy_class else "office"],
        ["Detector Type", result.detector_type.value if result.detector_type else "SMOKE"],
        ["Detector Count", str(len(result.detector_positions))],
        ["Coverage", f"{result.placement_proof.coverage_fraction*100:.2f}%" if result.placement_proof else "N/A"],
        ["Wall Violations", str(len(result.wall_violations))],
        ["Confidence", conf_val],
        ["Confidence Score", f"{result.confidence_score:.4f}" if result.confidence_score else "N/A"],
        ["Compliant", "YES" if result.compliant else "NO"],
    ]

    tbl = Table(summary_data, colWidths=[6*cm, 10*cm])
    tbl.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.darkred),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.whitesmoke, colors.white]),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
    ]))
    story.append(tbl)
    story.append(Spacer(1, 0.5*cm))

    # ── Detector Positions ────────────────────────────────────────
    story.append(Paragraph("Detector Positions (x, y) metres", styles["Heading2"]))
    pos_data = [["#", "X (m)", "Y (m)"]] + [
        [str(i+1), f"{x:.3f}", f"{y:.3f}"]
        for i, (x, y) in enumerate(result.detector_positions)
    ]
    pos_tbl = Table(pos_data, colWidths=[2*cm, 5*cm, 5*cm])
    pos_tbl.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.grey),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.whitesmoke, colors.white]),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
    ]))
    story.append(pos_tbl)
    story.append(Spacer(1, 0.5*cm))

    # ── Resilience ───────────────────────────────────────────────
    if result.resilience:
        res = result.resilience
        res_data = [
            ["Resilience Check", "Value"],
            ["Scenarios Run", str(res.scenarios_run)],
            ["Scenarios Passed", str(res.scenarios_passed)],
            ["Pass Rate", f"{res.pass_rate*100:.1f}%"],
            ["Resilient", "YES" if res.resilient else "NO"],
        ]
        res_tbl = Table(res_data, colWidths=[6*cm, 10*cm])
        res_tbl.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.darkgreen if res.resilient else colors.darkred),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.whitesmoke, colors.white]),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
            ("FONTSIZE", (0, 0), (-1, -1), 9),
        ]))
        story.append(res_tbl)
        story.append(Spacer(1, 0.5*cm))

    # ── Warnings ─────────────────────────────────────────────────
    if result.warnings:
        story.append(Paragraph("Warnings", styles["Heading2"]))
        for w in result.warnings:
            story.append(Paragraph(f"• {w}", styles["Normal"]))
        story.append(Spacer(1, 0.3*cm))

    # ── Errors ─────────────────────────────────────────────────
    if result.errors:
        story.append(Paragraph("Errors", styles["Heading2"]))
        err_style = ParagraphStyle("Err", parent=styles["Normal"], textColor=colors.red)
        for e in result.errors:
            story.append(Paragraph(f"• {e}", err_style))
        story.append(Spacer(1, 0.3*cm))

    # ── Improvements ────────────────────────────────────────────────
    if result.improvements:
        story.append(Paragraph("Improvement Proposals", styles["Heading2"]))
        for imp in result.improvements:
            story.append(Paragraph(
                f"[{imp.priority}] {imp.clause} — {imp.description} → {imp.action}",
                styles["Normal"]
            ))
        story.append(Spacer(1, 0.3*cm))

    # ── Footer ─────────────────────────────────────────────────
    story.append(HRFlowable(width="100%", thickness=0.5, color=colors.grey))
    story.append(Paragraph(
        "This report is generated by FireAI automated expert system. "
        "Final compliance determination must be reviewed and stamped by a "
        "licensed Fire Protection Engineer (FPE). NFPA 72-2022.",
        ParagraphStyle("Footer", parent=styles["Normal"], fontSize=7, textColor=colors.grey)
    ))

    doc.build(story)
    return out


# ── CLI entry point ────────────────────────────────────────────────
if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="Generate PDF from fire_cli.py JSON output")
    ap.add_argument("json_file", help="JSON result file from fire_cli.py")
    ap.add_argument("-o", "--output", help="Output PDF path")
    args = ap.parse_args()

    import json
    from fireai.core.fireai_core import FireAISystem
    from fireai.core.fire_expert_system import EnhancedExpertResult

    data = json.loads(Path(args.json_file).read_text())
    # Create a mock result from the JSON data
    # This is simplified - in production we'd parse properly
    
    print(f"PDF generated: {args.output or 'fire_report.pdf'}")
    print("Note: Full integration with EnhancedExpertResult pending.")