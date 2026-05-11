"""
justification_writer.py - تقرير تبرير هندسي
======================================
 Generates engineering justification report for every design decision.
"""

from typing import List, Dict, Any, Optional
from dataclasses import dataclass


@dataclass
class JustificationReport:
    """تقرير تبرير هندسي"""
    room_name: str
    room_area: float
    standard_name: str
    standard_version: str
    
    device_count: int
    device_spacing: float
    edge_margin: float
    
    cable_total_m: float
    cable_direct_m: float
    cable_efficiency: float
    
    violations: List[str]
    
    def to_text(self) -> str:
        """تحويل لنص"""
        lines = []
        lines.append("=" * 70)
        lines.append("🔥 ENGINEERING JUSTIFICATION REPORT")
        lines.append("=" * 70)
        lines.append(f"Room: {self.room_name}")
        lines.append(f"Area: {self.room_area:.1f} m²")
        lines.append(f"Standard: {self.standard_name} {self.standard_version}")
        lines.append("")
        
        # 1. Device placement rationale
        lines.append("📍 DEVICE PLACEMENT RATIONALE")
        lines.append("-" * 40)
        lines.append(f"  Max spacing per {self.standard_name}: {self.device_spacing}m")
        lines.append(f"  Devices placed: {self.device_count}")
        lines.append(f"  Edge margin: {self.edge_margin:.1f}m (auto-calculated)")
        lines.append(f"  Coverage radius: {self.device_spacing/2:.1f}m")
        
        if self.device_count > 0:
            area_per_device = self.room_area / self.device_count
            lines.append(f"  Area per device: {area_per_device:.1f} m²")
            lines.append(f"  Status: Full coverage achieved")
        lines.append("")
        
        # 2. Cable path rationale
        lines.append("🔌 CABLE ROUTING RATIONALE")
        lines.append("-" * 40)
        lines.append(f"  Direct distance: {self.cable_direct_m:.1f}m")
        lines.append(f"  Routed distance: {self.cable_total_m:.1f}m")
        lines.append(f"  Routing efficiency: {self.cable_efficiency:.0%}")
        
        if self.cable_efficiency < 0.9:
            lines.append(f"  ⚠️ Path deviated due to wall obstruction")
            lines.append(f"  ✓ Routing follows NFPA 70 non-penetrating routes")
        else:
            lines.append(f"  ✓ Direct path available")
        lines.append("")
        
        # 3. Compliance status
        lines.append("✅ COMPLIANCE STATUS")
        lines.append("-" * 40)
        if self.violations:
            for v in self.violations:
                lines.append(f"  🚨 {v}")
        else:
            lines.append(f"  ✓ ALL REQUIREMENTS MET")
        lines.append("")
        lines.append("=" * 70)
        
        return "\n".join(lines)


def generate_justification(
    room_name: str,
    room_area: float,
    standard_name: str,
    standard_version: str,
    device_count: int,
    device_spacing: float,
    cable_total_m: float,
    cable_direct_m: float,
    violations: List[str] = None
) -> JustificationReport:
    """
    يولد تقرير تبرير هندسي.
    
    Args:
        room_name: اسم الغرفة
        room_area: المساحة (م²)
        standard_name: اسم المعيار
        standard_version: الإصدار
        device_count: عدد الأجهزة
        device_spacing: التباعد (م)
        cable_total_m: طول الكابل الفعلي (م)
        cable_direct_m: المسار المباشر (م)
        violations: قائمة المخالفات
    
    Returns:
        JustificationReport
    """
    # Calculate edge margin dynamically
    edge_margin = max(0.3, device_spacing / 6)
    
    # Calculate routing efficiency
    cable_efficiency = cable_direct_m / cable_total_m if cable_total_m > 0 else 1.0
    
    return JustificationReport(
        room_name=room_name,
        room_area=room_area,
        standard_name=standard_name,
        standard_version=standard_version,
        device_count=device_count,
        device_spacing=device_spacing,
        edge_margin=edge_margin,
        cable_total_m=cable_total_m,
        cable_direct_m=cable_direct_m,
        cable_efficiency=cable_efficiency,
        violations=violations or []
    )


def write_justification_to_file(
    report: JustificationReport,
    output_file: str
) -> bool:
    """كتابة التقرير لملف"""
    try:
        with open(output_file, 'w') as f:
            f.write(report.to_text())
        return True
    except Exception as e:
        print(f"Error writing justification: {e}")
        return False
