"""
Minimal Spatial Constraint Engine for Fire Safety Compliance
=========================================================
⚠️ DEPRECATED: This file is a legacy standalone implementation.
For production use, prefer the canonical implementations in:
    fireai.core.nfpa72_models
    fireai.core.nfpa72_calculations
    fireai.core.nfpa72_coverage

This file is retained ONLY for backward compatibility with the validation
layer (validation/transformation_governor.py, validation/unit_coercion.py,
validation/spatial_normalizer.py) and will be migrated in a future bridge.

Implements ONE simple rule:
"Distance from detector to nearest wall must not exceed max_spacing_between_detectors / 2"

This validates NFPA 72 coverage principle using Shapely for spatial geometry.

CRITICAL FIX (2026-05-18):
- Heat detector spacing: Fixed from stale 9.1m default to height-adjusted values
  per NFPA 72 Table 17.6.3.1.1 (6.1m at h≤3.0m)
- Heat MAX_WALL_DISTANCE: Fixed from stale 7.6m to correct 3.05m (6.1/2)
- Added deprecation notice pointing to canonical package
"""

from dataclasses import dataclass
from shapely.geometry import Point, Polygon, LineString
from shapely.ops import unary_union
from typing import List, Optional
import math


# =============================================================================
# NODE DEFINITIONS (Semantic Graph Layer)
# =============================================================================

@dataclass
class Room:
    """Room node in the semantic graph"""
    id: str
    name: str
    geometry: Polygon  # WKT polygon representation
    ceiling_height: float  # meters
    ceiling_type: str = "SMOOTH"  # SMOOTH, BEAMED, SLOPED, CORRIDOR
    
    @property
    def area(self) -> float:
        return self.geometry.area
    
    @property
    def boundary(self) -> Polygon:
        return self.geometry
    
    def get_walls(self) -> List[LineString]:
        """Extract wall lines from room polygon"""
        coords = list(self.geometry.exterior.coords)
        walls = []
        for i in range(len(coords) - 1):
            p1 = (coords[i][0], coords[i][1])
            p2 = (coords[i+1][0], coords[i+1][1])
            walls.append(LineString([p1, p2]))
        return walls


@dataclass
class Device:
    """Detector/Device node in the semantic graph"""
    id: str
    device_type: str  # SMOKE_PHOTOELECTRIC, HEAT_FIXED, etc.
    position: Point  # x, y coordinates
    z_height: float = 2.4  # mounting height in meters
    
    # Coverage parameters (simplified - real NFPA has complex cone)
    coverage_radius: float = 4.6  # meters (NFPA 72 default for smooth ceiling)
    
    def get_coverage_zone(self) -> Polygon:
        """Get coverage area as polygon (simplified circle)"""
        return self.position.buffer(self.coverage_radius)


@dataclass
class Obstruction:
    """Obstruction node - blocks device coverage"""
    id: str
    geometry: Polygon  # obstruction footprint
    height: float  # height from floor
    blocks_visibility: bool = True


@dataclass  
class NFPAStandard:
    """Standard reference node"""
    code: str  # NFPA72, BS5839, etc.
    edition: str
    spacing_rules: dict  # {device_type: max_spacing_meters}


# =============================================================================
# CONSTRAINT LAYER (Spatial Rules)
# =============================================================================

class NFPA72Spacings:
    """NFPA 72 spacing constants - these are the constraints"""
    
    # Maximum spacing between detectors (meters) for smooth ceiling
    # NOTE: These are DEFAULT spacings at h≤3.0m. For variable height-adjusted
    # spacings, use fireai.core.nfpa72_calculations.calculate_coverage_radius_from_height()
    DETECTOR_MAX_SPACING = {
        "SMOKE_PHOTOELECTRIC": 9.1,  # 30 feet — NFPA 72 Table 17.6.3.1.1 at h≤3.0m
        "SMOKE_IONIZATION": 9.1,
        "HEAT_FIXED": 6.1,  # 20 feet per NFPA 72 Table 17.6.3.1.1 at h≤3.0m
        "HEAT_RATE_OF_RISE": 6.1,  # 20 feet per NFPA 72 Table 17.6.3.1.1 at h≤3.0m
        "MULTI_CRITERIA": 9.1,
    }
    
    # Maximum wall distance = S/2 per NFPA 72 §17.6.3.1.1
    # NOTE: This is S/2 (half spacing), NOT the coverage radius R = 0.7×S.
    # For coverage radius, use get_smoke_detector_radius_safe() from canonical package.
    MAX_WALL_DISTANCE = {
        "SMOKE_PHOTOELECTRIC": 4.55,  # S/2 = 9.1/2 (wall distance, NOT coverage radius)
        "HEAT_FIXED": 3.05,  # S/2 = 6.1/2 (wall distance per NFPA 72 §17.6.3.1.1)
    }
    
    # Coverage radius R = 0.7 × S per NFPA 72 §17.7.4.2.3.1
    # Used for area coverage checks, NOT for wall distance
    COVERAGE_RADIUS = {
        "SMOKE_PHOTOELECTRIC": 6.37,  # R = 0.7 × 9.1 (coverage radius)
        "HEAT_FIXED": 4.27,  # R = 0.7 × 6.1 (coverage radius for circular model)
    }
    
    @classmethod
    def get_max_spacing(cls, device_type: str) -> float:
        return cls.DETECTOR_MAX_SPACING.get(device_type, 9.1)
    
    @classmethod
    def get_max_wall_distance(cls, device_type: str) -> float:
        return cls.MAX_WALL_DISTANCE.get(device_type, cls.get_max_spacing(device_type) / 2)
    
    @classmethod
    def get_coverage_radius(cls, device_type: str) -> float:
        """Get coverage radius R = 0.7 × S per NFPA 72 §17.7.4.2.3.1."""
        return cls.COVERAGE_RADIUS.get(device_type, 0.7 * cls.get_max_spacing(device_type))


# =============================================================================
# EVALUATION ENGINE (Graph Traversal + Constraint Checking)
# =============================================================================

@dataclass
class Violation:
    """Represents a constraint violation"""
    rule: str
    device_id: str
    severity: str  # CRITICAL, MAJOR, MINOR
    message: str
    value: float
    threshold: float


class SpatialValidator:
    """
    Traverses the semantic graph and evaluates spatial constraints.
    This is the EXECUTION ENGINE.
    """
    
    def __init__(self, standard: NFPAStandard):
        self.standard = standard
        self.violations: List[Violation] = []
    
    def validate_room(self, room: Room, devices: List[Device], 
                   obstructions: Optional[List[Obstruction]] = None) -> List[Violation]:
        """
        Main evaluation function - validates all devices in a room.
        
        Returns list of violations found.
        """
        self.violations = []
        
        # Phase 1: Check wall distance constraint
        self._check_wall_distance(room, devices)
        
        # Phase 2: Check device-to-device spacing
        self._check_device_spacing(room, devices)
        
        # Phase 3: Check obstruction interference
        if obstructions:
            self._check_obstructions(room, devices, obstructions)
        
        return self.violations
    
    def _check_wall_distance(self, room: Room, devices: List[Device]):
        """
        Rule: Distance from any detector to nearest wall must not exceed
              MAX_WALL_DISTANCE for its device type.
        """
        for device in devices:
            max_wall = NFPA72Spacings.get_max_wall_distance(device.device_type)
            
            # Find minimum distance to any wall
            min_distance = float('inf')
            for wall in room.get_walls():
                dist = wall.distance(device.position)
                min_distance = min(min_distance, dist)
            
            if min_distance > max_wall:
                self.violations.append(Violation(
                    rule="MAX_WALL_DISTANCE",
                    device_id=device.id,
                    severity="MAJOR",
                    message=f"Detector {device.id} is {min_distance:.2f}m from wall (max: {max_wall}m)",
                    value=min_distance,
                    threshold=max_wall
                ))
    
    def _check_device_spacing(self, room: Room, devices: List[Device]):
        """
        Rule: No two detectors of the same type should exceed max spacing.
        """
        for i, dev1 in enumerate(devices):
            for dev2 in devices[i+1:]:
                # Only check same type (simplified)
                if dev1.device_type != dev2.device_type:
                    continue
                
                max_spacing = NFPA72Spacings.get_max_spacing(dev1.device_type)
                distance = dev1.position.distance(dev2.position)
                
                if distance > max_spacing:
                    self.violations.append(Violation(
                        rule="MAX_DETECTOR_SPACING",
                        device_id=f"{dev1.id}-{dev2.id}",
                        severity="CRITICAL",
                        message=f"Detectors {dev1.id} and {dev2.id} are {distance:.2f}m apart (max: {max_spacing}m)",
                        value=distance,
                        threshold=max_spacing
                    ))
    
    def _check_obstructions(self, room: Room, devices: List[Device],
                          obstructions: List[Obstruction]):
        """
        Rule: No obstruction should block detector coverage zone.
        
        If an obstruction is within coverage radius and blocks visibility,
        it's a violation.
        """
        for device in devices:
            coverage = device.get_coverage_zone()
            
            for obs in obstructions:
                # Check if obstruction intersects coverage
                if coverage.intersects(obs.geometry):
                    # More complex: check if it truly blocks (3D would use z_height)
                    overlap_area = coverage.intersection(obs.geometry).area
                    overlap_pct = (overlap_area / coverage.area) * 100
                    
                    if overlap_pct > 10:  # More than 10% blocked
                        self.violations.append(Violation(
                            rule="OBSTRUCTION_BLOCKING",
                            device_id=device.id,
                            severity="MAJOR",
                            message=f"Obstruction {obs.id} blocks {overlap_pct:.1f}% of {device.id} coverage",
                            value=overlap_pct,
                            threshold=10.0
                        ))


# =============================================================================
# EXECUTION EXAMPLE
# =============================================================================

def run_example():
    """
    This is the test case you asked for:
    - 10x10 room
    - 2 detectors
    - 1 obstruction (column in middle)
    """
    print("=" * 60)
    print("NFPA 72 Spatial Constraint Engine - Test Run")
    print("=" * 60)
    
    # Create room: 10m x 10m square
    room = Room(
        id="room_001",
        name="Living Room",
        geometry=Polygon([(0, 0), (10, 0), (10, 10), (0, 10), (0, 0)]),
        ceiling_height=2.4,
        ceiling_type="SMOOTH"
    )
    print(f"Room: {room.name}, Area: {room.area}m²")
    
    # Create 2 smoke detectors - one in corner, one in middle (WRONG placement)
    devices = [
        Device(id="smoke_001", device_type="SMOKE_PHOTOELECTRIC", position=Point(0.5, 0.5)),
        Device(id="smoke_002", device_type="SMOKE_PHOTOELECTRIC", position=Point(5, 5)),
    ]
    print(f"Devices: {[d.id for d in devices]}")
    
    # Create obstruction: column in middle
    obstructions = [
        Obstruction(
            id="column_001",
            geometry=Polygon([(4.5, 4.5), (5.5, 4.5), (5.5, 5.5), (4.5, 5.5), (4.5, 4.5)]),
            height=2.4,
            blocks_visibility=True
        )
    ]
    print(f"Obstructions: {[o.id for o in obstructions]}")
    
    # Run validation
    standard = NFPAStandard(code="NFPA72", edition="2025", spacing_rules={})
    validator = SpatialValidator(standard)
    violations = validator.validate_room(room, devices, obstructions)
    
    print(f"\nViolations Found: {len(violations)}")
    for v in violations:
        print(f"  [{v.severity}] {v.rule}: {v.message}")
    
    print("\n" + "=" * 60)
    if violations:
        print("RESULT: FAILED - NFPA violations detected")
    else:
        print("RESULT: PASSED - Room complies with NFPA 72")
    print("=" * 60)
    
    return violations


if __name__ == "__main__":
    run_example()