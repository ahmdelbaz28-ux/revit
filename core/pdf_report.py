"""
FireAI PDF Report Generator
=============================
Professional PDF reports with audit trail.

Requires: pip install reportlab
"""

import io
from datetime import datetime
from typing import Dict, List, Optional
from dataclasses import asdict

try:
    from reportlab.lib.pagesizes import A4
    from reportlab.lib import colors
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.platypus import (
        SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
        PageBreak, Image
    )
    from reportlab.lib.units import mm, inch
    REPORTLAB_AVAILABLE = True
except ImportError:
    REPORTLAB_AVAILABLE = False


class PDFReportGenerator:
    """
    Professional PDF report generator.
    
    Creates compliant reports with:
        - Project summary
        - Room table
        - Device listing
        - Violations
        - Audit trail hash
        - Legal disclaimer
        
    Usage:
        generator = PDFReportGenerator()
        pdf_bytes = generator.generate(
            project_name="Tower A",
            rooms=rooms,
            devices={"Smoke Detector": 5},
            violations=["Coverage gap in Room 101"]
        )
        
        # Save or send
        with open("report.pdf", "wb") as f:
            f.write(pdf_bytes)
    """
    
    PAGE_SIZE = A4
    MARGIN = 20 * mm
    
    COLORS = {
        "primary": colors.HexColor("#1a1a2e"),
        "accent": colors.HexColor("#e94560"),
        "success": colors.HexColor("#2ecc71"),
        "warning": colors.HexColor("#f39c12"),
        "danger": colors.HexColor("#e74c3c"),
        "light": colors.HexColor("#f5f5f5"),
    }

    def __init__(self):
        self.styles = getSampleStyleSheet()
        self._setup_styles()
        
    def _setup_styles(self):
        """Setup custom styles."""
        self.title_style = ParagraphStyle(
            "Title",
            parent=self.styles["Title"],
            fontSize=18,
            textColor=self.COLORS["primary"],
            spaceAfter=12,
        )
        
        self.heading_style = ParagraphStyle(
            "Heading",
            parent=self.styles["Heading2"],
            fontSize=12,
            textColor=self.COLORS["primary"],
            spaceAfter=8,
            spaceBefore=12,
        )
        
        self.normal_style = ParagraphStyle(
            "Normal",
            parent=self.styles["Normal"],
            fontSize=10,
            textColor=colors.black,
            spaceAfter=6,
        )
        
    def generate(
        self,
        project_name: str,
        rooms: List[Dict],
        devices: Dict,
        violations: List[Dict] = None,
        audit_hash: str = None,
        file_name: str = None,
    ) -> bytes:
        """
        Generate PDF report.
        
        Args:
            project_name: Name of project
            rooms: List of room dicts with name, area, devices
            devices: Dict of device_type -> count
            violations: List of violation dicts
            audit_hash: Hash for audit trail
            file_name: Original file name
            
        Returns:
            PDF as bytes
        """
        if not REPORTLAB_AVAILABLE:
            raise ImportError("reportlab not installed: pip install reportlab")
            
        buffer = io.BytesIO()
        doc = SimpleDocTemplate(
            buffer,
            pagesize=self.PAGE_SIZE,
            leftMargin=self.MARGIN,
            rightMargin=self.MARGIN,
            topMargin=self.MARGIN,
            bottomMargin=self.MARGIN,
        )
        
        story = []
        
        # Title
        story.append(Paragraph(
            "🔥 FIRE AI - SYSTEM ANALYSIS REPORT",
            self.title_style
        ))
        story.append(Spacer(1, 12))
        
        # Project info
        story.extend(self._build_project_info(
            project_name, file_name, rooms, devices
        ))
        
        # Room table
        story.extend(self._build_room_table(rooms))
        
        # Device table
        story.extend(self._build_device_table(devices))
        
        # Violations
        if violations:
            story.extend(self._build_violations(violations))
            
        # Audit trail
        if audit_hash:
            story.extend(self._build_audit_section(audit_hash))
            
        # Disclaimer
        story.extend(self._build_disclaimer())
        
        # Build PDF
        doc.build(story)
        
        return buffer.getvalue()
        
    def _build_project_info(
        self, 
        project_name: str,
        file_name: str,
        rooms: List[Dict],
        devices: Dict
    ) -> List:
        """Build project info section."""
        elements = []
        
        data = [
            ["Project:", project_name or "Unknown"],
            ["Date:", datetime.now().strftime("%Y-%m-%d %H:%M")],
            ["File:", file_name or "N/A"],
            ["Total Rooms:", str(len(rooms))],
            ["Total Devices:", str(sum(devices.values()) if devices else 0)],
        ]
        
        table = Table(data, colWidths=[50*mm, 120*mm])
        table.setStyle(TableStyle([
            ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
            ("FONTNAME", (1, 0), (1, -1), "Helvetica"),
            ("FONTSIZE", (0, 0), (-1, -1), 10),
            ("TEXTCOLOR", (0, 0), (0, -1), self.COLORS["primary"]),
            ("TEXTCOLOR", (1, 0), (1, -1), colors.black),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
            ("BOX", (0, 0), (-1, -1), 1, colors.black),
            ("BACKGROUND", (0, 0), (0, -1), self.COLORS["light"]),
        ]))
        
        elements.append(table)
        elements.append(Spacer(1, 20))
        
        return elements
        
    def _build_room_table(self, rooms: List[Dict]) -> List:
        """Build room table."""
        elements = []
        
        elements.append(Paragraph("📋 Room Summary", self.heading_style))
        elements.append(Spacer(1, 6))
        
        if not rooms:
            elements.append(Paragraph("No rooms detected.", self.normal_style))
            return elements
            
        data = [["#", "Room Name", "Area (m²)", "Devices", "Coverage"]]
        
        for i, room in enumerate(rooms[:20], 1):  # Max 20
            area = room.get("floor_area", room.get("area", 0))
            devices_count = room.get("device_count", room.get("devices", 0))
            coverage = "✅" if area < 80 else "⚠️"
            
            data.append([
                str(i),
                room.get("name", f"Room {i}"),
                f"{area:.1f}",
                str(devices_count),
                coverage
            ])
            
        table = Table(data, colWidths=[15*mm, 60*mm, 30*mm, 25*mm, 25*mm])
        table.setStyle(TableStyle([
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 9),
            ("TEXTCOLOR", (0, 0), (-1, -1), colors.black),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
            ("BOX", (0, 0), (-1, -1), 1, colors.black),
            ("BACKGROUND", (0, 0), (-1, 0), self.COLORS["primary"]),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ]))
        
        elements.append(table)
        elements.append(Spacer(1, 20))
        
        return elements
        
    def _build_device_table(self, devices: Dict) -> List:
        """Build device table."""
        elements = []
        
        elements.append(Paragraph("🔧 Required Devices", self.heading_style))
        elements.append(Spacer(1, 6))
        
        if not devices:
            elements.append(Paragraph("No devices required.", self.normal_style))
            return elements
            
        data = [["Device Type", "Required", "Coverage", "Notes"]]
        
        for dtype, count in devices.items():
            coverage = f"{(count * 9.2):.1f}m²" if count else "N/A"
            notes = "Per NFPA 72" if "Detector" in dtype else ""
            
            data.append([dtype, str(count), coverage, notes])
            
        table = Table(data, colWidths=[60*mm, 30*mm, 30*mm, 50*mm])
        table.setStyle(TableStyle([
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 9),
            ("TEXTCOLOR", (0, 0), (-1, -1), colors.black),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
            ("BOX", (0, 0), (-1, -1), 1, colors.black),
            ("BACKGROUND", (0, 0), (-1, 0), self.COLORS["primary"]),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("ALIGN", (1, 0), (1, -1), "CENTER"),
        ]))
        
        elements.append(table)
        elements.append(Spacer(1, 20))
        
        return elements
        
    def _build_violations(self, violations: List[Dict]) -> List:
        """Build violations section."""
        elements = []
        
        elements.append(Paragraph("⚠️ Violations & Warnings", self.heading_style))
        elements.append(Spacer(1, 6))
        
        for v in violations:
            desc = v.get("description", "Unknown violation")
            severity = v.get("severity", "")
            
            color = self.COLORS["danger"] if severity == "HIGH" else self.COLORS["warning"]
            
            elements.append(Paragraph(
                f"• {desc}",
                ParagraphStyle(
                    "Violation",
                    fontSize=10,
                    textColor=color,
                )
            ))
            
        elements.append(Spacer(1, 20))
        
        return elements
        
    def _build_audit_section(self, audit_hash: str) -> List:
        """Build audit trail section."""
        elements = []
        
        elements.append(Paragraph("📋 Audit Trail", self.heading_style))
        elements.append(Spacer(1, 6))
        
        elements.append(Paragraph(
            f"Audit Hash: <b>{audit_hash[:16]}</b>",
            self.normal_style
        ))
        elements.append(Paragraph(
            f"Generated: {datetime.now().isoformat()}",
            self.normal_style
        ))
        elements.append(Spacer(1, 20))
        
        return elements
        
    def _build_disclaimer(self) -> List:
        """Build legal disclaimer."""
        elements = []
        
        disclaimer = """
        <b>LEGAL DISCLAIMER</b><br/><br/>
        This report is generated by Fire AI automated analysis system and is intended
        as a preliminary assessment tool only. It does not substitute for professional
        engineering design, review, or approval. All results should be verified by a
        licensed professional engineer before implementation. The system analysis is
        based on provided drawings and does not account for field conditions.<br/><br/>
        <b>NFPA 72 Compliance:</b> Results are based on NFPA 72 National Fire Alarm and
        Signaling Code. Actual compliance should be verified per local codes and
        authority having jurisdiction.
        """
        
        elements.append(Paragraph(
            disclaimer,
            ParagraphStyle(
                "Disclaimer",
                fontSize=8,
                textColor=colors.darkgrey,
                spaceBefore=30,
            )
        ))
        
        return elements


# ════════════════════════════════════════════════════════════════════
# CONVENIENCE FUNCTION
# ════════════════════════════════════════════════════════════════════

def generate_report(
    project_name: str,
    rooms: List[Dict],
    devices: Dict,
    violations: List[Dict] = None,
    audit_hash: str = None,
    file_name: str = None,
) -> bytes:
    """Generate PDF report."""
    generator = PDFReportGenerator()
    return generator.generate(
        project_name=project_name,
        rooms=rooms,
        devices=devices,
        violations=violations,
        audit_hash=audit_hash,
        file_name=file_name,
    )


# ════════════════════════════════════════════════════════════════════
# TEST
# ════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    print("Testing PDF Generator...")
    
    rooms = [
        {"name": "Room 101", "floor_area": 25.0, "device_count": 1},
        {"name": "Room 102", "floor_area": 40.0, "device_count": 2},
        {"name": "Lobby", "floor_area": 60.0, "device_count": 3},
    ]
    
    devices = {"Smoke Detector": 6, "Heat Detector": 2, "Pull Station": 2}
    
    violations = [
        {"description": "Coverage gap in Room 103", "severity": "HIGH"},
    ]
    
    try:
        pdf = generate_report(
            project_name="Tower A - Floor 3",
            rooms=rooms,
            devices=devices,
            violations=violations,
            audit_hash="abc123def456",
            file_name="floor_plan.dxf"
        )
        
        with open("/tmp/fireai_report.pdf", "wb") as f:
            f.write(pdf)
            
        print("✅ PDF Generated: /tmp/fireai_report.pdf")
        print(f"   Size: {len(pdf)} bytes")
        
    except ImportError as e:
        print(f"⚠️  Install reportlab: {e}")
    except Exception as e:
        print(f"❌ Error: {e}")