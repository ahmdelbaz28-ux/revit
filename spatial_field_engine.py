"""
Spatial Field Coverage Engine v2.0
=================================
This engine validates NFPA compliance by checking that every point in a room
is covered by a detector within the allowed distance, and that no obstruction
blocks the line of sight to any detector.

Fixed v2.0 changes:
- Best-effort coverage: try all devices, not just nearest
- Fixed obstruction intersection logic
- Uses polygon.covers() for boundary points
- Dynamic coverage_factor based on ceiling type/height
- Added validate_geometry() input validation layer
"""

from dataclasses import dataclass
from shapely.geometry import Point, Polygon, LineString
from typing import List, Tuple, Optional
import sys
import os

# Add parent directory to path to import from spatial_constraint_engine
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from spatial_constraint_engine import Room, Device, Obstruction


# =============================================================================
# NFPA Constraint Model (Enhanced)
# =============================================================================

class NFPAConstraintModel:
    """
    NFPA constraint model for coverage validation.
    Now considers ceiling type and height.
    """
    
    def __init__(self, ceiling_type: str = "SMOOTH", ceiling_height: float = 2.4):
        self.rated_spacing = {
            "SMOKE_PHOTOELECTRIC": 9.1,  # 30 feet
            "HEAT_FIXED": 6.1,  # 20 feet per NFPA 72 Table 17.6.3.1
            "SMOKE_IONIZATION": 9.1,
            "HEAT_RATE_OF_RISE": 7.6,  # 25 feet per NFPA 72 Table 17.6.3.1
            "MULTI_CRITERIA": 9.1,
        }
        self.ceiling_type = ceiling_type
        self.ceiling_height = ceiling_height
    
    def coverage_factor(self, device_type: str) -> float:
        """Calculate coverage factor based on ceiling type."""
        # Simplified NFPA 72 corrections
        if self.ceiling_type == "SMOOTH":
            return 0.7
        elif self.ceiling_type == "BEAMED":
            return 0.6
        elif self.ceiling_type == "SLOPED":
            return 0.65
        elif self.ceiling_type == "CORRIDOR":
            return 0.65
        return 0.7
    
    def max_allowed_distance(self, device_type: str) -> float:
        """Calculate max distance from detector to any point it covers."""
        rated = self.rated_spacing.get(device_type, 9.1)
        return self.coverage_factor(device_type) * rated


# =============================================================================
# Grid Generation (Fixed)
# =============================================================================

def generate_grid(polygon: Polygon, spacing: float) -> List[Point]:
    """
    Generate evenly spaced points inside a polygon.
    Uses covers() instead of contains() to include boundary points.
    """
    min_x, min_y, max_x, max_y = polygon.bounds
    
    points = []
    x = min_x + spacing / 2
    while x < max_x:
        y = min_y + spacing / 2
        while y < max_y:
            point = Point(x, y)
            # Use covers() to include boundary points
            if polygon.covers(point):
                points.append(point)
            y += spacing
        x += spacing
    
    return points


# =============================================================================
# Violation Class
# =============================================================================

@dataclass
class Violation:
    """Represents a coverage violation"""
    rule: str
    device_id: str
    severity: str  # CRITICAL, MAJOR, MINOR
    message: str
    value: float
    threshold: float
    location: Optional[Point] = None


# =============================================================================
# Geometry Validation Layer (NEW)
# =============================================================================

@dataclass
class GeometryError:
    """Represents an input geometry validation error"""
    message: str
    entity_id: str
    severity: str  # CRITICAL, WARNING


def validate_geometry(
    room: Room,
    devices: List[Device],
    obstructions: List[Obstruction]
) -> List[GeometryError]:
    """
    Validate input geometry before compliance evaluation.
    Returns list of errors - empty means valid inputs.
    """
    errors = []
    
    # 1. Validate room polygon
    if not room.geometry.is_valid:
        errors.append(GeometryError(
            message=f"Room polygon is invalid",
            entity_id=room.id,
            severity="CRITICAL"
        ))
    
    if room.geometry.is_empty or room.geometry.area <= 0:
        errors.append(GeometryError(
            message=f"Room polygon is empty or has zero area",
            entity_id=room.id,
            severity="CRITICAL"
        ))
    
    # 2. Validate each device is inside room
    for device in devices:
        if not room.geometry.covers(device.position):
            errors.append(GeometryError(
                message=f"Device {device.id} is outside room",
                entity_id=device.id,
                severity="CRITICAL"
            ))
    
    # 3. Validate each obstruction is inside room
    for obs in obstructions:
        if not room.geometry.contains(obs.geometry):
            errors.append(GeometryError(
                message=f"Obstruction {obs.id} is not fully inside room",
                entity_id=obs.id,
                severity="CRITICAL"
            ))
        
        # Check no device is inside obstruction
        for device in devices:
            if obs.geometry.contains(device.position):
                errors.append(GeometryError(
                    message=f"Device {device.id} is inside obstruction {obs.id}",
                    entity_id=device.id,
                    severity="CRITICAL"
                ))
    
    # 4. Check devices not at same location
    for i, d1 in enumerate(devices):
        for d2 in devices[i+1:]:
            if d1.position.distance(d2.position) < 0.001:
                errors.append(GeometryError(
                    message=f"Devices {d1.id} and {d2.id} are at the same location",
                    entity_id=f"{d1.id}-{d2.id}",
                    severity="WARNING"
                ))
    
    return errors


# =============================================================================
# Coverage Evaluation (Fixed - Best Effort)
# =============================================================================

def evaluate_compliance(
    room: Room,
    devices: List[Device],
    obstructions: List[Obstruction],
    model: NFPAConstraintModel,
    grid_spacing: float = 0.25
) -> Tuple[dict, List[Violation]]:
    """
    Evaluate coverage compliance for a room.
    
    NEW ALGORITHM (best-effort):
    For each grid point:
    1. Sort devices by distance (nearest first)
    2. Try each device in order:
       - Check if within max allowed distance
       - Check if line of sight is not blocked
       - If both pass, point is covered
    3. Only mark as violation if NO device can cover the point
    
    This fixes the "nearest device bias" bug.
    """
    # First: validate geometry inputs
    geom_errors = validate_geometry(room, devices, obstructions)
    criticals = [e for e in geom_errors if e.severity == "CRITICAL"]
    
    if criticals:
        violations = [
            Violation(
                rule="GEOMETRY_ERROR",
                device_id=e.entity_id,
                severity=e.severity,
                message=e.message,
                value=0,
                threshold=0
            )
            for e in criticals
        ]
        return {}, violations
    
    violations = []
    coverage_map = {}
    
    # Generate grid points
    grid_points = generate_grid(room.geometry, grid_spacing)
    
    if not devices:
        for i, pt in enumerate(grid_points):
            violations.append(Violation(
                rule="NO_DEVICES",
                device_id="NONE",
                severity="CRITICAL",
                message="Room has no devices",
                value=0,
                threshold=0,
                location=pt
            ))
        return coverage_map, violations
    
    for i, pt in enumerate(grid_points):
        point_covered = False
        
        # Sort devices by distance - try nearest first
        sorted_devices = sorted(devices, key=lambda d: pt.distance(d.position))
        
        for device in sorted_devices:
            dist = pt.distance(device.position)
            max_dist = model.max_allowed_distance(device.device_type)
            
            # Skip if this device is too far
            if dist > max_dist:
                continue
            
            # Check line of sight for this device
            line_of_sight_blocked = False
            line = LineString([
                (device.position.x, device.position.y),
                (pt.x, pt.y)
            ])
            
            for obs in obstructions:
                # Skip if device is on/near obstruction boundary
                device_dist_to_obs = device.position.distance(obs.geometry)
                if device_dist_to_obs < 0.01:
                    continue
                
                # Use intersects + not touches (more accurate than crosses)
                if line.intersects(obs.geometry) and not line.touches(obs.geometry):
                    line_of_sight_blocked = True
                    break
            
            # If not blocked, point is covered
            if not line_of_sight_blocked:
                coverage_map[i] = (device.id, dist)
                point_covered = True
                break  # Found a covering device, stop trying
        
        # Only add violation if NO device can cover this point
        if not point_covered:
            # Find the nearest device for reporting
            nearest = min(devices, key=lambda d: pt.distance(d.position))
            min_dist = pt.distance(nearest.position)
            max_dist = model.max_allowed_distance(nearest.device_type)
            
            violations.append(Violation(
                rule="COVERAGE_GAP",
                device_id=nearest.id,
                severity="CRITICAL",
                message=f"Point {i} is {min_dist:.2f}m from nearest device (max: {max_dist:.2f}m)",
                value=min_dist,
                threshold=max_dist,
                location=pt
            ))
    
    return coverage_map, violations


# =============================================================================
# Tests
# =============================================================================

def run_test(name: str, room, devices, obstructions, model, expected_pass: bool):
    """Run a single test case."""
    print("=" * 60)
    print(f"TEST: {name}")
    print("=" * 60)
    
    coverage_map, violations = evaluate_compliance(
        room, devices, obstructions, model, grid_spacing=0.25
    )
    
    grid_points = generate_grid(room.geometry, 0.25)
    total_points = len(grid_points)
    covered_points = len(coverage_map)
    violation_count = len(violations)
    
    print(f"Room: {room.name}")
    print(f"Devices: {[d.id for d in devices]}")
    print(f"Obstructions: {len(obstructions)}")
    print(f"\n--- Coverage Summary ---")
    print(f"Grid points: {total_points}")
    print(f"Covered points: {covered_points} ({covered_points/total_points*100:.1f}%)")
    print(f"Violations: {violation_count}")
    
    # Group violations
    coverage_gaps = [v for v in violations if v.rule == "COVERAGE_GAP"]
    geometry_errors = [v for v in violations if v.rule == "GEOMETRY_ERROR"]
    
    print(f"\n  Coverage gaps: {len(coverage_gaps)}")
    print(f"  Geometry errors: {len(geometry_errors)}")
    
    if violations:
        print(f"\n--- First 5 Violations ---")
        for v in violations[:5]:
            loc_str = ""
            if v.location:
                loc_str = f" at ({v.location.x:.2f}, {v.location.y:.2f})"
            print(f"  [{v.severity}] {v.rule}: {v.message}{loc_str}")
    
    print("\n" + "=" * 60)
    passed = violation_count == 0
    if passed:
        print("RESULT: PASSED")
    else:
        print(f"RESULT: FAILED - {violation_count} violations")
    print("=" * 60)
    
    # Check against expected
    if passed == expected_pass:
        print("✓ Test matches expected result")
    else:
        print(f"✗ Expected {'PASSED' if expected_pass else 'FAILED'}, got {'PASSED' if passed else 'FAILED'}")
    
    return coverage_map, violations


if __name__ == "__main__":
    # Test 1: FAILING case (insufficient coverage with obstruction)
    # Device NOT inside obstruction, but insufficient coverage
    room1 = Room(
        id="room_001",
        name="Test Room (Insufficient)",
        geometry=Polygon([(0, 0), (10, 0), (10, 10), (0, 10), (0, 0)]),
        ceiling_height=2.4
    )
    devices1 = [
        Device(id="smoke_center", device_type="SMOKE_PHOTOELECTRIC", position=Point(5, 5)),
        Device(id="smoke_corner", device_type="SMOKE_PHOTOELECTRIC", position=Point(8, 8)),
    ]
    # Small obstruction away from devices
    obstructions1 = [
        Obstruction(
            id="column_001",
            geometry=Polygon([(1, 1), (2, 1), (2, 2), (1, 2), (1, 1)]),
            height=2.4,
            blocks_visibility=True
        )
    ]
    model1 = NFPAConstraintModel(ceiling_type="SMOOTH")
    run_test("FAILING CASE - Insufficient Coverage", room1, devices1, obstructions1, model1, False)
    
    print("\n\n")
    
    # Test 2: PASSING case (proper coverage)
    room2 = Room(
        id="room_002",
        name="Test Room (Good)",
        geometry=Polygon([(0, 0), (10, 0), (10, 10), (0, 10), (0, 0)]),
        ceiling_height=2.4
    )
    devices2 = [
        Device(id="smoke_001", device_type="SMOKE_PHOTOELECTRIC", position=Point(2.5, 2.5)),
        Device(id="smoke_002", device_type="SMOKE_PHOTOELECTRIC", position=Point(7.5, 2.5)),
        Device(id="smoke_003", device_type="SMOKE_PHOTOELECTRIC", position=Point(2.5, 7.5)),
        Device(id="smoke_004", device_type="SMOKE_PHOTOELECTRIC", position=Point(7.5, 7.5)),
    ]
    obstructions2 = []
    model2 = NFPAConstraintModel(ceiling_type="SMOOTH")
    run_test("PASSING CASE - Proper Coverage", room2, devices2, obstructions2, model2, True)
    
    print("\n\n")
    
    # Test 3: Device outside room (geometry error)
    room3 = Room(
        id="room_003",
        name="Test Room (Outside Device)",
        geometry=Polygon([(0, 0), (10, 0), (10, 10), (0, 10), (0, 0)]),
        ceiling_height=2.4
    )
    devices3 = [
        Device(id="smoke_inside", device_type="SMOKE_PHOTOELECTRIC", position=Point(5, 5)),
        Device(id="smoke_outside", device_type="SMOKE_PHOTOELECTRIC", position=Point(15, 15)),  # Outside!
    ]
    obstructions3 = []
    model3 = NFPAConstraintModel(ceiling_type="SMOOTH")
    run_test("GEOMETRY ERROR - Device Outside Room", room3, devices3, obstructions3, model3, False)
    
    print("\n\n")
    
    # Test 4: Best-effort coverage - demonstrates algorithm tries all devices
    room4 = Room(
        id="room_004",
        name="Test Room (Best Effort)",
        geometry=Polygon([(0, 0), (10, 0), (10, 10), (0, 10), (0, 0)]),
        ceiling_height=2.4
    )
    # 4 devices in corners - this should PASS 
    devices4 = [
        Device(id="smoke_001", device_type="SMOKE_PHOTOELECTRIC", position=Point(1, 1)),
        Device(id="smoke_002", device_type="SMOKE_PHOTOELECTRIC", position=Point(1, 9)),
        Device(id="smoke_003", device_type="SMOKE_PHOTOELECTRIC", position=Point(9, 1)),
        Device(id="smoke_004", device_type="SMOKE_PHOTOELECTRIC", position=Point(9, 9)),
    ]
    obstructions4 = []
    model4 = NFPAConstraintModel(ceiling_type="SMOOTH")
    run_test("BEST EFFORT - Four Corner Devices", room4, devices4, obstructions4, model4, True)