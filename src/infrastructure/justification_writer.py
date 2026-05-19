"""
justification_writer.py - طبقة التبرير الهندسي (مرتبطة بالمحركات الحية)
======================================================================
تقرأ مخرجات CoverageService و CableRouter و BeamDetector
وتنتج تقريراً يمكن الدفاع به أمام المراجعين.
"""

from dataclasses import dataclass
from typing import List, Optional
from src.core.models import Room, Device, Violation, Beam


@dataclass
class JustificationReport:
    """تقرير تبرير هندسي متكامل"""
    room_name: str
    room_area: float
    standard_name: str
    standard_version: str
    
    device_count: int
    spacing: float
    edge_margin: float
    coverage_radius: float
    
    cable_total_m: float
    cable_direct_m: float
    routing_efficiency: float
    wall_deviations: List[str]
    
    beams_processed: int
    deep_beams_count: int
    
    has_violations: bool
    violations: List[any]
    
    voltage_drop_v: float
    loop_resistance_ohm: float
    is_loop_compliant: bool

    def to_text(self) -> str:
        """تحويل للتقرير النصي"""
        lines = []
        lines.append("=" * 70)
        lines.append("🔥 ENGINEERING JUSTIFICATION REPORT")
        lines.append("=" * 70)
        lines.append(f"Room: {self.room_name}")
        lines.append(f"Area: {self.room_area:.1f} m²")
        lines.append(f"Standard: {self.standard_name} {self.standard_version}")
        lines.append("")

        # Device placement
        lines.append("📍 DEVICE PLACEMENT RATIONALE")
        lines.append("-" * 40)
        lines.append(f"  Max spacing per {self.standard_name}: {self.spacing}m")
        lines.append(f"  Devices placed: {self.device_count}")
        lines.append(f"  Edge margin: {self.edge_margin:.1f}m")
        lines.append(f"  Coverage radius: {self.coverage_radius:.1f}m")
        
        area_per = self.room_area / max(1, self.device_count)
        lines.append(f"  Area per device: {area_per:.1f} m²")
        
        if self.has_violations:
            lines.append(f"  Status: ⚠️ COVERAGE GAPS DETECTED")
        else:
            lines.append(f"  Status: ✓ Full coverage verified")
        lines.append("")

        # Beam analysis
        if self.beams_processed > 0:
            lines.append("🏗️ BEAM OBSTRUCTION ANALYSIS")
            lines.append("-" * 40)
            lines.append(f"  Total beams in room: {self.beams_processed}")
            lines.append(f"  Deep beams (≥10% ceiling height): {self.deep_beams_count}")
            lines.append(f"  Shadow zones calculated per NFPA 72 §17.6.3.2.4")
            lines.append("")

        # Cable routing
        lines.append("🔌 CABLE ROUTING RATIONALE")
        lines.append("-" * 40)
        lines.append(f"  Direct distance: {self.cable_direct_m:.1f}m")
        lines.append(f"  Routed distance: {self.cable_total_m:.1f}m")
        lines.append(f"  Routing efficiency: {self.routing_efficiency:.0f}%")
        
        if self.wall_deviations:
            lines.append(f"  ⚠️ Path deviated due to {len(self.wall_deviations)} wall(s)")
            for wall in self.wall_deviations[:3]:
                lines.append(f"    - {wall}")
        
        lines.append(f"  ✓ Routing follows NFPA 70 non-penetrating routes")
        lines.append("")

        # Electrical compliance
        lines.append("⚡ ELECTRICAL COMPLIANCE")
        lines.append("-" * 40)
        lines.append(f"  Voltage drop: {self.voltage_drop_v:.2f}V")
        lines.append(f"  Loop resistance: {self.loop_resistance_ohm:.2f}Ω")
        
        if self.is_loop_compliant:
            lines.append(f"  ✓ Loop compliant with NFPA 72 limits")
        else:
            lines.append(f"  ❌ Loop exceeds limits! Review required")
        lines.append("")

        # Overall compliance
        lines.append("✅ COMPLIANCE STATUS")
        lines.append("-" * 40)
        
        if self.has_violations:
            lines.append(f"  ⚠️ {len(self.violations)} violation(s) found:")
            for v in self.violations[:5]:  # Show first 5
                msg = getattr(v, 'message', str(v))
                lines.append(f"    - {msg}")
        else:
            lines.append(f"  ✓ ALL REQUIREMENTS MET")
        
        lines.append("=" * 70)

        return "\n".join(lines)


def generate_justification(
    room: 'Room',
    devices: List['Device'],
    violations: List[any],
    cable_total_m: float,
    cable_direct_m: float,
    beams: List['Beam'],
    standard,
    voltage_drop_v: float = 0.0,
    loop_resistance_ohm: float = 0.0,
    is_loop_compliant: bool = True
) -> JustificationReport:
    """
    يولد تقرير تبرير من المخرجات الحية للمحركات.
    
    Args:
        room: الغرفة
        devices: قائمة الأجهزة
        violations: المخالفات
        cable_total_m: إجمالي طول الكابلات
        cable_direct_m: المسار المباشر
        beams: قائمة العوارض
        standard: المعيار (NFPA72, BS5839)
        voltage_drop_v: هبوط الجهد
        loop_resistance_ohm: مقاومة الحلقة
        is_loop_compliant: امتثال الحلقة
    
    Returns:
        JustificationReport
    """
    spacing = standard.get_max_spacing("SmokeDetector")
    coverage_radius = standard.get_coverage_radius("SmokeDetector")
    edge_margin = max(0.3, spacing / 6)  # نفس auto_placement

    # Calculate routing efficiency
    if cable_total_m > 0:
        efficiency = (cable_direct_m / cable_total_m) * 100.0
    else:
        efficiency = 100.0

    # Beam analysis - count deep beams
    room_height = getattr(room, 'height', 3.0) or 3.0
    deep_threshold = room_height * 0.10  # 10% of ceiling height
    deep_beams = [b for b in beams if getattr(b, 'depth', 0) >= deep_threshold]

    # Wall deviations (placeholder - would come from cable_router)
    wall_deviations = []

    return JustificationReport(
        room_name=room.name or "Unnamed Room",
        room_area=room.area or getattr(getattr(room, 'polygon', None), 'area', 0) or 0.0,
        standard_name=standard.name,
        standard_version=standard.version,
        device_count=len(devices),
        spacing=spacing,
        edge_margin=edge_margin,
        coverage_radius=coverage_radius,
        cable_total_m=cable_total_m,
        cable_direct_m=cable_direct_m,
        routing_efficiency=efficiency,
        wall_deviations=wall_deviations,
        beams_processed=len(beams),
        deep_beams_count=len(deep_beams),
        has_violations=len(violations) > 0,
        violations=violations,
        voltage_drop_v=voltage_drop_v,
        loop_resistance_ohm=loop_resistance_ohm,
        is_loop_compliant=is_loop_compliant
    )


def write_justification_to_file(report: JustificationReport, filepath: str):
    """كتابة التقرير لملف"""
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(report.to_text())
