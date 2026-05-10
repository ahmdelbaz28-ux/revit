"""
Spatial Field Coverage Engine
============================
This engine validates NFPA compliance by checking that every point in a room
is covered by a detector within the allowed distance, and that no obstruction
blocks the line of sight to any detector.

Instead of checking detector spacing, this validates COVERAGE - every point in the room
must be within range of at least one detector.
"""

from dataclasses import dataclass, field
from shapely.geometry import Point, Polygon, LineString
from typing import List, Tuple, Optional
import sys
import os

# Add parent directory to path to import from spatial_constraint_engine
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from spatial_constraint_engine import Room, Device, Obstruction


# =============================================================================
# NFPA Constraint Model
# =============================================================================

class NFPAConstraintModel:
    """
    NFPA constraint model for coverage validation.
    Defines rated spacing and coverage factor for each device type.
    """
    
    def __init__(self):
        self.rated_spacing = {
            "SMOKE_PHOTOELECTRIC": 9.1,  # 30 feet
            "HEAT_FIXED": 15.2,  # 50 feet
            "SMOKE_IONIZATION": 9.1,
            "HEAT_RATE_OF_RISE": 15.2,
            "MULTI_CRITERIA": 9.1,
        }
        self.coverage_factor = 0.7  # 70% of rated spacing
    
    def max_allowed_distance(self, device_type: str) -> float:
        """Calculate max distance from detector to any point it covers."""
        rated = self.rated_spacing.get(device_type, 9.1)
        return self.coverage_factor * rated


# =============================================================================
# Grid Generation
# =============================================================================

def generate_grid(polygon: Polygon, spacing: float) -> List[Point]:
    """
    Generate evenly spaced points inside a polygon.
    
    Args:
        polygon: The room boundary polygon
        spacing: Distance between grid points
        
    Returns:
        List of points inside the polygon
    """
    min_x, min_y, max_x, max_y = polygon.bounds
    
    points = []
    x = min_x + spacing / 2
    while x < max_x:
        y = min_y + spacing / 2
        while y < max_y:
            point = Point(x, y)
            if polygon.contains(point):
                points.append(point)
            y += spacing
        x += spacing
    
    return points


# =============================================================================
# Violation Class (Enhanced)
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
    location: Optional[Point] = None  # NEW: point where violation occurred


# =============================================================================
# Coverage Evaluation
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
    
    For each grid point in the room:
    1. Find nearest device (shortest Euclidean distance)
    2. If distance > max_allowed_distance: add COVERAGE_GAP violation
    3. Else, check if any obstruction blocks the line to the device
    
    Args:
        room: Room geometry
        devices: List of devices in the room
        obstructions: List of obstructions
        model: NFPA constraint model
        grid_spacing: Spacing between grid points (default 0.25m)
        
    Returns:
        Tuple of (CoverageMap, violations list)
        CoverageMap: {point_index: (device_id, distance)}
    """
    violations = []
    coverage_map = {}
    
    # Generate grid points
    grid_points = generate_grid(room.geometry, grid_spacing)
    
    if not devices:
        # No devices = complete failure
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
        # Find nearest device
        nearest_device = None
        min_distance = float('inf')
        
        for device in devices:
            dist = pt.distance(device.position)
            if dist < min_distance:
                min_distance = dist
                nearest_device = device
        
        if nearest_device is None:
            continue
            
        # Check max allowed distance
        max_dist = model.max_allowed_distance(nearest_device.device_type)
        
        if min_distance > max_dist:
            # Point not covered - COVERAGE GAP
            violations.append(Violation(
                rule="COVERAGE_GAP",
                device_id=nearest_device.id,
                severity="CRITICAL",
                message=f"Point {i} is {min_distance:.2f}m from nearest device (max: {max_dist:.2f}m)",
                value=min_distance,
                threshold=max_dist,
                location=pt
            ))
            continue  # Skip obstruction check for uncovered points
        
        # Check obstructions (line of sight)
        # The device might be ON the obstruction boundary, so we need to check
        # if obstruction is actually BETWEEN device and point
        line = LineString([
            (nearest_device.position.x, nearest_device.position.y),
            (pt.x, pt.y)
        ])
        
        for obs in obstructions:
            # Skip if device is on/near obstruction boundary (distance ≈ 0)
            device_dist_to_obs = nearest_device.position.distance(obs.geometry)
            if device_dist_to_obs < 0.01:
                continue  # Device is on/near obstruction - can't be blocked
            
            # Check proper crossing - the line must actually cross through the interior
            if line.crosses(obs.geometry):
                violations.append(Violation(
                    rule="OBSTRUCTION_BLOCKS_POINT",
                    device_id=nearest_device.id,
                    severity="MAJOR",
                    message=f"Obstruction {obs.id} blocks line of sight to point {i}",
                    value=min_distance,
                    threshold=max_dist,
                    location=pt
                ))
                break  # One obstruction is enough
        
        # Record in coverage map
        coverage_map[i] = (nearest_device.id, min_distance)
    
    return coverage_map, violations


# =============================================================================
# Test
# =============================================================================

def run_test():
    """Test the coverage field engine."""
    print("=" * 60)
    print("Spatial Field Coverage Engine - Test Run")
    print("=" * 60)
    
    # Create room: 10m x 10m
    room = Room(
        id="room_001",
        name="Test Room",
        geometry=Polygon([(0, 0), (10, 0), (10, 10), (0, 10), (0, 0)]),
        ceiling_height=2.4
    )
    
    # Create 2 devices: one in center (5,5), one at (8,8)
    devices = [
        Device(id="smoke_center", device_type="SMOKE_PHOTOELECTRIC", position=Point(5, 5)),
        Device(id="smoke_corner", device_type="SMOKE_PHOTOELECTRIC", position=Point(8, 8)),
    ]
    
    # Create obstruction: column in middle
    obstructions = [
        Obstruction(
            id="column_001",
            geometry=Polygon([(4.5, 4.5), (5.5, 4.5), (5.5, 5.5), (4.5, 5.5), (4.5, 4.5)]),
            height=2.4,
            blocks_visibility=True
        )
    ]
    
    # Create constraint model
    model = NFPAConstraintModel()
    max_dist = model.max_allowed_distance("SMOKE_PHOTOELECTRIC")
    print(f"Max allowed distance: {max_dist}m (coverage_factor: {model.coverage_factor})")
    
    # Run evaluation
    coverage_map, violations = evaluate_compliance(
        room, devices, obstructions, model, grid_spacing=0.25
    )
    
    # Summarize
    grid_points = generate_grid(room.geometry, 0.25)
    total_points = len(grid_points)
    covered_points = len(coverage_map)
    violation_count = len(violations)
    
    print(f"\n--- Coverage Summary ---")
    print(f"Grid points: {total_points}")
    print(f"Covered points: {covered_points} ({covered_points/total_points*100:.1f}%)")
    print(f"Violations: {violation_count}")
    
    # Group violations by type
    coverage_gaps = [v for v in violations if v.rule == "COVERAGE_GAP"]
    obstructions = [v for v in violations if v.rule == "OBSTRUCTION_BLOCKS_POINT"]
    
    print(f"\n  Coverage gaps: {len(coverage_gaps)}")
    print(f"  Obstruction violations: {len(obstructions)}")
    
    # Print violations with locations
    if violations:
        print(f"\n--- Violations (showing first 5) ---")
        for v in violations[:5]:
            loc_str = ""
            if v.location:
                loc_str = f" at ({v.location.x:.2f}, {v.location.y:.2f})"
            print(f"  [{v.severity}] {v.rule}: {v.message}{loc_str}")
    
    print("\n" + "=" * 60)
    if coverage_gaps:
        print("RESULT: FAILED - Coverage gaps detected")
    elif obstructions:
        print("RESULT: FAILED - Obstruction violations detected")
    else:
        print("RESULT: PASSED - Full coverage")
    print("=" * 60)
    
    return coverage_map, violations


if __name__ == "__main__":
    # Test 1: FAILING case (insufficient coverage)
    print("\n" + "=" * 60)
    print("TEST 1: FAILING CASE (Insufficient Coverage)")
    print("=" * 60)
    run_test()
    
    # Test 2: PASSING case (proper detector placement)
    print("\n" + "=" * 60)
    print("TEST 2: PASSING CASE (Proper Coverage)")
    print("=" * 60)
    
    # Create room: 10m x 10m
    room2 = Room(
        id="room_002",
        name="Good Room",
        geometry=Polygon([(0, 0), (10, 0), (10, 10), (0, 10), (0, 0)]),
        ceiling_height=2.4
    )
    
    # Create 4 detectors in proper grid layout (5m apart)
    devices2 = [
        Device(id="smoke_001", device_type="SMOKE_PHOTOELECTRIC", position=Point(2.5, 2.5)),
        Device(id="smoke_002", device_type="SMOKE_PHOTOELECTRIC", position=Point(7.5, 2.5)),
        Device(id="smoke_003", device_type="SMOKE_PHOTOELECTRIC", position=Point(2.5, 7.5)),
        Device(id="smoke_004", device_type="SMOKE_PHOTOELECTRIC", position=Point(7.5, 7.5)),
    ]
    
    # No obstructions
    obstructions2 = []
    
    # Run evaluation
    model2 = NFPAConstraintModel()
    coverage_map2, violations2 = evaluate_compliance(
        room2, devices2, obstructions2, model2, grid_spacing=0.25
    )
    
    # Summarize
    grid_points2 = generate_grid(room2.geometry, 0.25)
    total_points2 = len(grid_points2)
    covered_points2 = len(coverage_map2)
    violation_count2 = len(violations2)
    
    print(f"Room: {room2.name}")
    print(f"Devices: {[d.id for d in devices2]}")
    print(f"Obstructions: {len(obstructions2)}")
    print(f"\n--- Coverage Summary ---")
    print(f"Grid points: {total_points2}")
    print(f"Covered points: {covered_points2} ({covered_points2/total_points2*100:.1f}%)")
    print(f"Violations: {violation_count2}")
    
    print("\n" + "=" * 60)
    if violation_count2 == 0:
        print("RESULT: PASSED - Full coverage!")
    else:
        print(f"RESULT: FAILED - {violation_count2} violations")
    print("=" * 60)