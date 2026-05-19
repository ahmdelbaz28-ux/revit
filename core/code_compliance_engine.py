"""
code_compliance_engine.py — FireAI V5.3.0 Guardian
Enforces NFPA 70 (NEC) and NFPA 72 separation distances.

SAFETY-CRITICAL: Ensures detectors don't violate electrical clearances.
"""

import logging
from shapely.geometry import Point, Polygon
from typing import List, Tuple, Dict, Optional
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger("fireai.compliance")


# ════════════════════════════════════════════════════════════════════════════
# COMPLIANCE ENUMS
# ════════════════════════════════════════════════════════════════════════════

class ViolationSeverity(Enum):
    """Severity levels for violations."""
    RED = "red"          # Must fix - life safety
    YELLOW = "yellow"   # Should fix - code
    INFO = "info"       # Advisory


# ════════════════════════════════════════════════════════════════════════════
# DATA CLASSES
# ════════════════════════════════════════════════════════════════════════════

@dataclass
class Violation:
    """
    Code violation detected.
    
    Each violation includes:
    - Code reference (NEC/NFPA section)
    - Severity level
    - Suggested fix
    """
    location: Tuple[float, float]
    description: str
    code_reference: str  # e.g., "NEC 110.26"
    severity: ViolationSeverity
    min_required: float = 0.0
    actual_distance: float = 0.0

    def __str__(self) -> str:
        return f"[{self.severity.value.upper()}] {self.description} ({self.code_reference})"


@dataclass
class ComplianceReport:
    """Summary of compliance check."""
    room_id: str
    is_compliant: bool
    violations: List[Violation] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    
    @property
    def critical_violations(self) -> List[Violation]:
        return [v for v in self.violations if v.severity == ViolationSeverity.RED]
    
    @property
    def warning_violations(self) -> List[Violation]:
        return [v for v in self.violations if v.severity == ViolationSeverity.YELLOW]


# ════════════════════════════════════════════════════════════════════════════
# COMPLIANCE ENGINE
# ════════════════════════════════════════════════════════════════════════════

class CodeComplianceEngine:
    """
    Enforces NEC and NFPA 72 separation distances.
    
    NEC TABLE 110.26 MINIMUM SEPARATIONS:
        - Cable trays: 1.0m (39 in)
        - Conduits: 0.5m (19.7 in)  
        - Junction boxes: 1.2m (47 in)
        - Panels: 1.0m (39 in)
        
    NFPA 72 17.7.4.3:
        - Detectors must be 4 in (10cm) from ceiling on smooth ceiling
        - 4-12 in (10-30cm) mounting height
        
    Usage:
        engine = CodeComplianceEngine()
        report = engine.check_compliance(
            detector_positions=[(1.0, 2.0), (3.0, 4.0)],
            obstructions=obstructions,
            ceiling_info=ceiling
        )
        
        if not report.is_compliant:
            for v in report.violations:
                print(v)
    """
    
    # NEC Table 110.26 minimum distances (meters)
    MIN_DISTANCES = {
        "cable_tray": 1.0,
        "conduit": 0.5,
        "junction_box": 1.2,
        "panel": 1.0,
        "busway": 1.0,
        "wireway": 0.5,
    }
    
    # NFPA 72 detector requirements
    DETECTOR_MOUNTING = {
        "min_from_ceiling": 0.10,  # 10cm = 4 inches
        "max_from_ceiling": 0.30,  # 30cm = 12 inches
    }
    
    # NEC 300.22 regarding plenum spaces
    PLENUM_RULES = {
        "no_conduits_in_plenum_unless_listed": True,
        "cable_tray_in_plenum": "permitted_if_listed",
    }

    def check_compliance(
        self,
        detector_positions: List[Tuple[float, float]],
        obstructions: List,
        ceiling_info,
    ) -> ComplianceReport:
        """
        Check if detector positions comply with NEC/NFPA.
        
        Args:
            detector_positions: List of (x, y) coordinates
            obstructions: List of ElectricalObstruction objects
            ceiling_info: CeilingInfo object
            
        Returns:
            ComplianceReport with any violations
        """
        violations = []
        warnings = []
        
        for pos in detector_positions:
            point = Point(pos[0], pos[1])
            
            # Check each obstruction
            for obs in obstructions:
                if not obs.polygon:
                    continue
                    
                # Check if detector is inside obstruction
                if obs.polygon.contains(point):
                    violations.append(Violation(
                        location=pos,
                        description=f"Detector at {pos} INSIDE {obs.element_type.value}",
                        code_reference="NEC 110.26",
                        severity=ViolationSeverity.RED,
                        min_required=obs.get_min_separation(),
                        actual_distance=0.0
                    ))
                    continue
                    
                # Calculate distance
                dist = obs.polygon.distance(point)
                min_dist = obs.get_min_separation()
                
                if dist < min_dist:
                    severity = ViolationSeverity.RED if dist < min_dist * 0.5 else ViolationSeverity.YELLOW
                    violations.append(Violation(
                        location=pos,
                        description=f"Detector at {pos} too close to {obs.element_type.value}",
                        code_reference="NEC 110.26",
                        severity=severity,
                        min_required=min_dist,
                        actual_distance=dist
                    ))
                    
        # Check ceiling mounting height
        if ceiling_info:
            # Check if detector height is valid per ceiling type
            if ceiling_info.structure_type.value == "suspended":
                warnings.append(
                    "SUSPENDED CEILING: Ensure detector is listed for plenum use"
                )
                
            # Check beam pocket reduction
            if ceiling_info.structure_type.value == "beam_pocket":
                warnings.append(
                    f"BEAM POCKET: Coverage reduced by {(1 - ceiling_info.get_coverage_reduction()) * 100:.0f}%"
                )
                
        is_compliant = len([v for v in violations if v.severity == ViolationSeverity.RED]) == 0
        
        return ComplianceReport(
            room_id="",
            is_compliant=is_compliant,
            violations=violations,
            warnings=warnings
        )

    def check_distance_between_detectors(
        self,
        positions: List[Tuple[float, float]],
        max_spacing: float = 9.2
    ) -> List[Violation]:
        """
        Check minimum spacing between detectors (NFPA 72 17.7.3).
        
        Default max spacing: 9.2m (30ft) for smoke detectors
        """
        violations = []
        
        for i, pos1 in enumerate(positions):
            for pos2 in positions[i+1:]:
                # Calculate distance
                dx = pos1[0] - pos2[0]
                dy = pos1[1] - pos2[1]
                dist = (dx**2 + dy**2) ** 0.5
                
                if dist < max_spacing * 0.5:  # Too close
                    violations.append(Violation(
                        location=pos1,
                        description=f"Detectors too close: {dist:.2f}m (min {max_spacing * 0.5:.1f}m)",
                        code_reference="NFPA 72 17.7.3",
                        severity=ViolationSeverity.YELLOW,
                        min_required=max_spacing * 0.5,
                        actual_distance=dist
                    ))
                    
        return violations


# ════════════════════════════════════════════════════════════════════════════
# NEC SPECIFIC CHECKS
# ════════════════════════════════════════════════════════════════════════════

class NECCompliance:
    """
    National Electrical Code specific checks.
    """
    
    # Table 110.26 conditions for service equipment
    WORKING_SPACE = {
        "minimum_depth": 0.9,  # 36 inches for 100-200A
        "minimum_width": 0.75,  # 30 inches
        "minimum_height": 2.0,  # 78 inches
    }
    
    # Conductor fill (NEC Chapter 9)
    MAX_CONDUCTOR_FILL = {
        "40%": 40,  # # of conductors
        "31%": 31, 
        "40%": 40,
    }

    def check_panel_clearance(
        self,
        panel_location: Point,
        detector_positions: List[Point],
    ) -> bool:
        """Check panel has required working space."""
        for pos in detector_positions:
            dist = panel_location.distance(pos)
            if dist < self.WORKING_SPACE["minimum_depth"]:
                return False
        return True


# ════════════════════════════════════════════════════════════════════════════
# CONVENIENCE FUNCTION
# ════════════════════════════════════════════════════════════════════════════

def check_compliance(
    detector_positions: List[Tuple[float, float]],
    obstructions: List,
    ceiling_info,
) -> ComplianceReport:
    """Quick compliance check."""
    engine = CodeComplianceEngine()
    return engine.check_compliance(detector_positions, obstructions, ceiling_info)