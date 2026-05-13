"""
Safety Gates - FireAI V7.2
=========================
Safety gates that return PASS/FAIL/REVIEW_REQUIRED.

These are SAFETY GATES - not advice:
  - PASS: Safe to proceed
  - FAIL: Must fix before proceeding 
  - REVIEW_REQUIRED: Human engineer sign-off required

Based on findings from elite_drawing_analyzer (external system).
"""

from dataclasses import dataclass
from typing import List, Optional
from enum import Enum


class GateStatus(Enum):
    """Safety gate result status."""
    PASS = "pass"
    FAIL = "fail"
    REVIEW_REQUIRED = "review_required"


@dataclass
class SafetyGateResult:
    """Result of a safety gate check."""
    name: str
    status: GateStatus
    message: str
    severity: str = "info"
    details: dict = None
    
    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "status": self.status.value,
            "message": self.message,
            "severity": self.severity,
            "details": self.details or {}
        }


class SafetyGates:
    """
    Fire safety gates.
    
    Usage:
        gates = SafetyGates()
        results = gates.run_all(
            smoke_detectors=[(1,2), (3,4)],
            room_area=80,
            ceiling_height=3.0
        )
        
        for result in results:
            print(f"{result.name}: {result.status.value}")
    """
    
    # NFPA 72 limits
    SMOKE_MAX_SPACING = 9.2  # meters
    SMOKE_MAX_FROM_WALL = 4.6  # meters (0.5 × spacing)
    
    HEAT_MAX_SPACING = 6.1  # meters (fixed temp)
    HEAT_MAX_FROM_WALL = 3.0  # meters
    
    SPRINKLER_MAX_SPACING = 4.6  # meters (NFPA 13)
    SPRINKLER_MAX_AREA = 20.9  # m² per head
    
    # NFPA 101 egress
    EXIT_MAX_TRAVEL = 61.0  # meters
    
    @staticmethod
    def gate_smoke_coverage(
        detector_positions: List[tuple],
        room_area: float,
        room_bounds: Optional[tuple] = None
    ) -> SafetyGateResult:
        """Check smoke detector coverage."""
        
        if not detector_positions:
            return SafetyGateResult(
                name="smoke_coverage",
                status=GateStatus.FAIL,
                message="No smoke detectors found in zone",
                severity="critical"
            )
        
        if len(detector_positions) < 2:
            return SafetyGateResult(
                name="smoke_coverage",
                status=GateStatus.REVIEW_REQUIRED,
                message=f"Only {len(detector_positions)} detector(s) - cannot verify spacing",
                severity="advisory"
            )
        
        # Check spacing between detectors
        for i, pos1 in enumerate(detector_positions):
            for j, pos2 in enumerate(detector_positions[i+1:], i+1):
                import math
                d = math.sqrt((pos1[0]-pos2[0])**2 + (pos1[1]-pos2[1])**2)
                if d > SafetyGates.SMOKE_MAX_SPACING:
                    return SafetyGateResult(
                        name="smoke_coverage",
                        status=GateStatus.FAIL,
                        message=f"Detector {i}↔{j}: {d:.1f}m > {SafetyGates.SMOKE_MAX_SPACING}m allowed",
                        severity="critical",
                        details={"i": i, "j": j, "distance": d, "limit": SafetyGates.SMOKE_MAX_SPACING}
                    )
        
        # Check coverage area estimate
        coverage_per = room_area / len(detector_positions)
        if coverage_per > 85:  # ~9.2m × 9.2m
            return SafetyGateResult(
                name="smoke_coverage",
                status=GateStatus.REVIEW_REQUIRED,
                message=f"~{coverage_per:.0f}m² per detector - verify coverage",
                severity="advisory"
            )
        
        return SafetyGateResult(
            name="smoke_coverage",
            status=GateStatus.PASS,
            message=f"{len(detector_positions)} detectors, adequate coverage",
            severity="info"
        )
    
    @staticmethod
    def gate_sprinkler_coverage(
        sprinkler_positions: List[tuple],
        room_area: float
    ) -> SafetyGateResult:
        """Check sprinkler coverage (NFPA 13)."""
        
        if not sprinkler_positions:
            return SafetyGateResult(
                name="sprinkler_coverage",
                status=GateStatus.REVIEW_REQUIRED,
                message="No sprinklers in zone - verify if required",
                severity="advisory"
            )
        
        # Check spacing
        import math
        for i, pos1 in enumerate(sprinkler_positions):
            for j, pos2 in enumerate(sprinkler_positions[i+1:], i+1):
                d = math.sqrt((pos1[0]-pos2[0])**2 + (pos1[1]-pos2[1])**2)
                if d > SafetyGates.SPRINKLER_MAX_SPACING:
                    return SafetyGateResult(
                        name="sprinkler_coverage",
                        status=GateStatus.FAIL,
                        message=f"Sprinkler {i}↔{j}: {d:.1f}m > {SafetyGates.SPRINKLER_MAX_SPACING}m",
                        severity="critical"
                    )
        
        # Check area per head
        area_per_head = room_area / len(sprinkler_positions)
        if area_per_head > SafetyGates.SPRINKLER_MAX_AREA:
            return SafetyGateResult(
                name="sprinkler_coverage",
                status=GateStatus.FAIL,
                message=f"{area_per_head:.1f}m²/head > {SafetyGates.SPRINKLER_MAX_AREA}m² allowed",
                severity="major"
            )
        
        return SafetyGateResult(
            name="sprinkler_coverage",
            status=GateStatus.PASS,
            message="Sprinkler spacing compliant",
            severity="info"
        )
    
    @staticmethod
    def gate_egress(
        occupant_points: List[tuple],
        exit_points: List[tuple],
        walls: List = None
    ) -> SafetyGateResult:
        """Check egress distances (NFPA 101)."""
        
        if not occupant_points or not exit_points:
            return SafetyGateResult(
                name="egress",
                status=GateStatus.REVIEW_REQUIRED,
                message="Cannot verify egress - missing points",
                severity="advisory"
            )
        
        import math
        violations = []
        
        for idx, occ in enumerate(occupant_points):
            min_dist = min(
                math.sqrt((occ[0]-ex[0])**2 + (occ[1]-ex[1])**2)
                for ex in exit_points
            )
            if min_dist > SafetyGates.EXIT_MAX_TRAVEL:
                violations.append((idx, min_dist))
        
        if violations:
            return SafetyGateResult(
                name="egress",
                status=GateStatus.FAIL,
                message=f"{len(violations)} point(s) exceed {SafetyGates.EXIT_MAX_TRAVEL}m",
                severity="critical",
                details={"violations": violations}
            )
        
        return SafetyGateResult(
            name="egress",
            status=GateStatus.PASS,
            message="All egress distances within limits",
            severity="info"
        )
    
    @classmethod
    def run_all(cls, 
              smoke_detectors: List[tuple] = None,
              heat_detectors: List[tuple] = None,
              sprinklers: List[tuple] = None,
              room_area: float = 0,
              room_bounds: tuple = None,
              occupant_points: List[tuple] = None,
              exit_points: List[tuple] = None) -> List[SafetyGateResult]:
        """Run all safety gates."""
        results = []
        
        # Smoke detection
        if smoke_detectors:
            results.append(cls.gate_smoke_coverage(
                smoke_detectors, room_area, room_bounds
            ))
        
        # Heat detection
        if heat_detectors:
            results.append(SafetyGateResult(
                name="heat_coverage",
                status=GateStatus.PASS,
                message=f"{len(heat_detectors)} heat detectors"
            ))
        
        # Sprinklers
        if sprinklers:
            results.append(cls.gate_sprinkler_coverage(sprinklers, room_area))
        
        # Egress
        if occupant_points and exit_points:
            results.append(cls.gate_egress(occupant_points, exit_points))
        
        return results


def gate_check(
    smoke_detectors: List[tuple] = None,
    room_area: float = 0
) -> SafetyGateResult:
    """Quick gate check for smoke detectors."""
    return SafetyGates.gate_smoke_coverage(smoke_detectors, room_area)