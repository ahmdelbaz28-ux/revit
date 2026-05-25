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
    
    # NFPA 72 limits — FIXED: 9.1m = exactly 30ft (was 9.2m)
    SMOKE_MAX_SPACING = 9.1  # meters (30 feet per NFPA 72 Table 17.6.3.1.1)
    SMOKE_MAX_FROM_WALL = 4.55  # meters (9.1 / 2 = S/2)
    
    HEAT_MAX_SPACING = 6.1  # meters (fixed temp, 20ft per NFPA 72)
    HEAT_MAX_FROM_WALL = 3.05  # meters (6.1 / 2)
    
    # NFPA 13 Sprinkler (Light Hazard)
    SPRINKLER_MAX_SPACING = 4.6  # meters
    SPRINKLER_MAX_AREA = 20.9  # m² per head
    
    # For testing - use actual coordinates
    def _check_sprinkler_spacing(self, positions, room_area):
        """Helper to check sprinkler spacing."""
        import math
        for i, pos1 in enumerate(positions):
            for j, pos2 in enumerate(positions[i+1:], i+1):
                d = math.sqrt((pos1[0]-pos2[0])**2 + (pos1[1]-pos2[1])**2)
                if d > self.SPRINKLER_MAX_SPACING:
                    return False, d
        return True, 0
    
    # NFPA 101 Egress
    EXIT_MAX_TRAVEL = 61.0  # meters (sprinklered business)
    MAX_COMMON_PATH = 30.5  # meters
    MAX_DEAD_END = 15.2  # meters
    
    @staticmethod
    def gate_smoke_coverage(
        detector_positions: List[tuple],
        room_area: float,
        room_bounds: Optional[tuple] = None,
        ceiling_height: float = 3.0
    ) -> SafetyGateResult:
        """Check smoke detector coverage - CORRECTED formula."""
        
        if not detector_positions:
            return SafetyGateResult(
                name="smoke_coverage",
                status=GateStatus.FAIL,
                message="No smoke detectors found in zone",
                severity="critical"
            )
        
        # CRITICAL: Check ceiling height
        if ceiling_height > 3.7:
            return SafetyGateResult(
                name="smoke_coverage",
                status=GateStatus.REVIEW_REQUIRED,
                message=f"Ceiling {ceiling_height}m > 3.7m - verify detector type",
                severity="critical"
            )
        
        # CRITICAL: Use CIRCLE area, not square!
        import math
        # CRITICAL FIX (2026-05-22): Was SMOKE_MAX_SPACING / 2 = 4.55m (S/2 = wall distance).
        # NFPA 72 §17.7.4.2.3.1 defines coverage radius as R = 0.7 × S, NOT S/2.
        radius = 0.7 * SafetyGates.SMOKE_MAX_SPACING  # R = 0.7 × 9.1 = 6.37m
        coverage_per_detector = math.pi * radius ** 2  # 127.5m² per NFPA 72 §17.7.4.2.3.1
        
        # Check spacing between detectors
        for i, pos1 in enumerate(detector_positions):
            for j, pos2 in enumerate(detector_positions[i+1:], i+1):
                d = math.sqrt((pos1[0]-pos2[0])**2 + (pos1[1]-pos2[1])**2)
                if d > SafetyGates.SMOKE_MAX_SPACING:
                    return SafetyGateResult(
                        name="smoke_coverage",
                        status=GateStatus.FAIL,
                        message=f"Detector {i}↔{j}: {d:.1f}m > {SafetyGates.SMOKE_MAX_SPACING}m allowed",
                        severity="critical",
                        details={"i": i, "j": j, "distance": d, "limit": SafetyGates.SMOKE_MAX_SPACING}
                    )
        
        # Check coverage area - CRITICAL: use CIRCLE not square
        # Room area / circle coverage = number needed
        detectors_needed = max(1, math.ceil(room_area / coverage_per_detector))
        detectors_provided = len(detector_positions)
        
        if detectors_provided < detectors_needed:
            return SafetyGateResult(
                name="smoke_coverage",
                status=GateStatus.FAIL,
                message=f"Need {detectors_needed} detectors for {room_area}m² (have {detectors_provided})",
                severity="critical",
                details={"needed": detectors_needed, "provided": detectors_provided, "area": room_area}
            )
        
        return SafetyGateResult(
            name="smoke_coverage",
            status=GateStatus.PASS,
            message=f"{detectors_provided} detectors, {coverage_per_detector:.1f}m² coverage each",
            severity="info"
        )
    
    @staticmethod
    def gate_heat_coverage(
        heat_detectors: List[tuple],
        room_area: float = 0,
        room_bounds: tuple = None,
    ) -> SafetyGateResult:
        """Check heat detector coverage per NFPA 72 Table 17.6.3.1.1.
        
        V20.2 FIX: Previously heat detectors were always PASS with no validation.
        Now validates spacing (6.1m at h≤3.0m) and area coverage using
        SQUARE (Chebyshev) geometry, consistent with NFPA 72 heat detector rules.
        """
        import math
        
        if not heat_detectors:
            return SafetyGateResult(
                name="heat_coverage",
                status=GateStatus.REVIEW_REQUIRED,
                message="No heat detectors found in zone — verify if required",
                severity="advisory"
            )
        
        # Check spacing between heat detectors (SQUARE grid — Chebyshev distance)
        for i, pos1 in enumerate(heat_detectors):
            for j, pos2 in enumerate(heat_detectors[i+1:], i+1):
                # Heat detectors use Chebyshev (max of |dx|, |dy|) not Euclidean
                d = max(abs(pos1[0] - pos2[0]), abs(pos1[1] - pos2[1]))
                if d > SafetyGates.HEAT_MAX_SPACING:
                    return SafetyGateResult(
                        name="heat_coverage",
                        status=GateStatus.FAIL,
                        message=(
                            f"Heat detector {i}↔{j}: Chebyshev distance {d:.1f}m "
                            f"> {SafetyGates.HEAT_MAX_SPACING}m allowed "
                            f"per NFPA 72 Table 17.6.3.1.1"
                        ),
                        severity="critical",
                        details={"i": i, "j": j, "distance": d,
                                 "limit": SafetyGates.HEAT_MAX_SPACING}
                    )
        
        # Check area per detector (SQUARE coverage area = S²)
        coverage_per_detector = SafetyGates.HEAT_MAX_SPACING ** 2  # 6.1² = 37.2m²
        if room_area > 0:
            detectors_needed = math.ceil(room_area / coverage_per_detector)
            detectors_provided = len(heat_detectors)
            if detectors_provided < detectors_needed:
                return SafetyGateResult(
                    name="heat_coverage",
                    status=GateStatus.FAIL,
                    message=(
                        f"Need {detectors_needed} heat detectors for {room_area}m² "
                        f"(have {detectors_provided}) per NFPA 72 Table 17.6.3.1.1"
                    ),
                    severity="critical",
                    details={"needed": detectors_needed, "provided": detectors_provided,
                             "area": room_area}
                )
        
        # Check wall distance
        if room_bounds:
            width, depth = room_bounds[0], room_bounds[1]
            for idx, pos in enumerate(heat_detectors):
                dist_to_wall = min(pos[0], width - pos[0], pos[1], depth - pos[1])
                if dist_to_wall > SafetyGates.HEAT_MAX_FROM_WALL:
                    return SafetyGateResult(
                        name="heat_coverage",
                        status=GateStatus.FAIL,
                        message=(
                            f"Heat detector {idx}: {dist_to_wall:.1f}m from wall "
                            f"> {SafetyGates.HEAT_MAX_FROM_WALL}m allowed "
                            f"per NFPA 72 §17.6.3.1.1"
                        ),
                        severity="major",
                        details={"detector": idx, "distance": dist_to_wall,
                                 "limit": SafetyGates.HEAT_MAX_FROM_WALL}
                    )
        
        return SafetyGateResult(
            name="heat_coverage",
            status=GateStatus.PASS,
            message=(
                f"{len(heat_detectors)} heat detectors, "
                f"{coverage_per_detector:.1f}m² coverage each "
                f"(square grid per NFPA 72 Table 17.6.3.1.1)"
            ),
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
        
        # CRITICAL: Must have exits defined!
        if not exit_points:
            return SafetyGateResult(
                name="egress",
                status=GateStatus.FAIL,
                message="CRITICAL: No exits defined in drawing - CANNOT verify egress",
                severity="critical"
            )
        
        if not occupant_points:
            return SafetyGateResult(
                name="egress",
                status=GateStatus.REVIEW_REQUIRED,
                message="No occupant points defined - cannot verify",
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
        
        # Heat detection — V20.2 FIX: Was always PASS with no validation.
        # Now validates spacing per NFPA 72 Table 17.6.3.1.1 (6.1m at h≤3.0m).
        if heat_detectors:
            results.append(cls.gate_heat_coverage(
                heat_detectors, room_area, room_bounds
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