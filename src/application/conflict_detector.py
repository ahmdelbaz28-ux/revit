"""
conflict_detector.py - محلل التعارضات
==============================
 Detects design conflicts and warnings.
"""

from typing import List, Dict, Tuple
from dataclasses import dataclass
import math


@dataclass
class Conflict:
    """تعارض في التصميم"""
    severity: str  # "WARNING" or "CRITICAL"
    device_id: int
    issue: str
    details: str
    recommendation: str


class ConflictDetector:
    """كاشف التعارضات"""
    
    # Minimum clearances
    AC_DIFFUSER_CLEARANCE = 1.0  # meters
    SPRINKLER_CLEARANCE = 0.5  # meters
    MAX_CABLE_LENGTH = 100.0  # meters (for voltage drop)
    MAX_CABLE_90_PERCENT = 90.0  # 90% of max
    
    def __init__(self, max_cable_per_loop: float = 100.0):
        self.max_cable_per_loop = max_cable_per_loop
    
    def check_device_conflicts(
        self,
        devices: List[Dict],
        obstacles: List[Tuple[float, float]] = None
    ) -> List[Conflict]:
        """فحص تعارضات الأجهزة"""
        conflicts = []
        obstacles = obstacles or []
        
        for device in devices:
            device_id = device.get('id', 0)
            pos = device.get('position', (0, 0))
            
            # Check distance to obstacles (AC diffusers, sprinklers, etc.)
            for obs in obstacles:
                dist = math.sqrt((pos[0] - obs[0])**2 + (pos[1] - obs[1])**2)
                
                if dist < self.AC_DIFFUSER_CLEARANCE:
                    conflicts.append(Conflict(
                        severity="WARNING",
                        device_id=device_id,
                        issue=f"Located {dist:.1f}m from AC Diffuser (Recommended: 1.0m)",
                        details=f"Clearance: {dist:.1f}m",
                        recommendation="Move device 1.0m away from AC unit"
                    ))
        
        return conflicts
    
    def check_cable_limits(
        self,
        cable_lengths: List[float],
        device_counts: List[int] = None
    ) -> List[Conflict]:
        """فحص حدود الكابلات"""
        conflicts = []
        
        for i, length in enumerate(cable_lengths):
            # Check voltage drop risk
            pct = (length / self.max_cable_per_loop) * 100
            
            if pct >= 100:
                conflicts.append(Conflict(
                    severity="CRITICAL",
                    device_id=i,
                    issue=f"Cable length {length:.0f}m exceeds limit",
                    details=f"{pct:.0f}% of max (voltage drop risk)",
                    recommendation="Relocate panel or add repeater"
                ))
            elif pct >= 90:
                conflicts.append(Conflict(
                    severity="WARNING",
                    device_id=i,
                    issue=f"Cable length {length:.0f}m at {pct:.0f}% of limit",
                    details=f"High risk of voltage drop",
                    recommendation="Consider moving panel closer"
                ))
        
        return conflicts
    
    def generate_report(
        self,
        device_conflicts: List[Conflict],
        cable_conflicts: List[Conflict]
    ) -> str:
        """توليد تقرير التعارضات"""
        lines = []
        
        all_conflicts = device_conflicts + cable_conflicts
        
        if not all_conflicts:
            return ""
        
        lines.append("\n⚠️  CONFLICT ANALYSIS:")
        lines.append("-" * 40)
        
        for c in all_conflicts:
            icons = "🚨" if c.severity == "CRITICAL" else "⚠️"
            lines.append(f"  {icons} Device #{c.device_id}: {c.issue}")
            if c.details:
                lines.append(f"     Details: {c.details}")
            lines.append(f"     [{c.recommendation}]")
        
        return "\n".join(lines)