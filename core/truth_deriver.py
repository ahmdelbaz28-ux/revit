"""
Core Truth Deriver - Independent NFPA Coverage Calculator
===================================================
This module computes NFPA coverage INDEPENDENTLY from spatial_field_engine.py.
It serves as the "second computational reference" to verify the engine.

NO imports from spatial_field_engine, evaluate_compliance, or SpatialValidator.
NO I/O, NO ifcopenshell.
"""

import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dataclasses import dataclass
from shapely.geometry import Point, Polygon, LineString
from typing import List, Tuple

from core.models import Room, Device, Obstruction, Violation


# =============================================================================
# TruthViolation (Independent, not derived from Violation)
# =============================================================================

@dataclass(frozen=True)
class TruthViolation:
    """Independent violation from the Truth Deriver"""
    point: Point  # Location of uncovered point
    nearest_device_id: str
    distance: float
    threshold: float


# =============================================================================
# Independent Grid Generation (logically copied, not imported)
# =============================================================================

def generate_truth_grid(polygon: Polygon, spacing: float) -> List[Point]:
    """
    Generate evenly spaced points inside a polygon.
    Uses covers() instead of contains() to include boundary points.
    
    Independent implementation - NOT imported from spatial_field_engine.
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
# NFPA Constraint Model (Independent copy)
# =============================================================================

class NFPAConstraintModel:
    """NFPA constraint model - independent copy"""
    
    def __init__(self, ceiling_type: str = "SMOOTH", ceiling_height: float = 2.4):
        self.rated_spacing = {
            "SMOKE_PHOTOELECTRIC": 9.1,  # 30 feet
            "HEAT_FIXED": 15.2,  # 50 feet
            "SMOKE_IONIZATION": 9.1,
            "HEAT_RATE_OF_RISE": 15.2,
            "MULTI_CRITERIA": 9.1,
        }
        self.ceiling_type = ceiling_type
        self.ceiling_height = ceiling_height
    
    def max_allowed_distance(self, device_type: str) -> float:
        """Maximum allowed distance for a given device type"""
        # For coverage, we use the full spacing as the max distance
        # because a point needs to be within this distance from any device
        return self.rated_spacing.get(device_type, 9.1)


# =============================================================================
# Independent Truth Derivation
# =============================================================================

def derive_truth(
    room: Room,
    devices: List[Device],
    obstructions: List[Obstruction],
    model: NFPAConstraintModel,
    grid_spacing: float = 0.25
) -> List[TruthViolation]:
    """
    Compute NFPA coverage COMPLETELY INDEPENDENTLY from the engine.
    
    Independent algorithm:
    1. Generate grid points covering the room
    2. For each point:
       a. Find all devices within max_allowed_distance
       b. Sort by distance (nearest first)
       c. Check line of sight (ray casting) for obstructions:
          - Create LineString between device and point
          - Check that ray does NOT intersect any obstruction
          - If device is adjacent to obstruction (distance < 0.01), ignore that obstruction
       d. If device found with correct distance and open line of sight -> covered
       e. If none found -> record TruthViolation with (point, nearest_device_id, distance, threshold)
    3. Return list of TruthViolations
    
    Does NOT call evaluate_compliance or SpatialValidator.
    """
    violations: List[TruthViolation] = []
    
    # Step 1: Generate grid points
    grid_points = generate_truth_grid(room.geometry, grid_spacing)
    
    if not grid_points:
        return violations
    
    # Step 2: Check each point
    for pt in grid_points:
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
                point_covered = True
                break  # Found a covering device, stop trying
        
        # Only add violation if NO device can cover this point
        if not point_covered:
            # Find the nearest device for reporting
            nearest = min(devices, key=lambda d: pt.distance(d.position))
            min_dist = pt.distance(nearest.position)
            max_dist = model.max_allowed_distance(nearest.device_type)
            
            violations.append(TruthViolation(
                point=pt,
                nearest_device_id=nearest.id,
                distance=min_dist,
                threshold=max_dist
            ))
    
    return violations


# =============================================================================
# Comparison Function
# =============================================================================

def compare_truths(
    engine_violations: List[Violation],
    truth_violations: List[TruthViolation],
    location_tolerance: float = 0.01
) -> dict:
    """
    Compare engine violations with Truth Deriver violations.
    
    Returns:
    - matched: Number of violations matching in location and type
    - missing_in_engine: Truth violations not detected by engine
    - extra_in_engine: Engine violations not in truth
    - summary: "CONSISTENT" | "DIVERGENT" | "PARTIAL"
    """
    matched = 0
    missing_in_engine = []
    extra_in_engine = []
    
    # Match engine violations to truth violations
    for tv in truth_violations:
        found = False
        for ev in engine_violations:
            if ev.device_id == tv.nearest_device_id:
                # Check location proximity
                if ev.location is not None:
                    dist = ev.location.distance(tv.point)
                    if dist <= location_tolerance:
                        found = True
                        break
        if found:
            matched += 1
        else:
            missing_in_engine.append(tv)
    
    # Check for extra engine violations
    for ev in engine_violations:
        if ev.location is None:
            extra_in_engine.append(ev)
            continue
        
        found = False
        for tv in truth_violations:
            dist = ev.location.distance(tv.point)
            if dist <= location_tolerance:
                found = True
                break
        if not found:
            extra_in_engine.append(ev)
    
    # Determine summary
    if not truth_violations and not engine_violations:
        summary = "CONSISTENT"
    elif not missing_in_engine and not extra_in_engine:
        summary = "CONSISTENT"
    elif not missing_in_engine and len(extra_in_engine) <= 2:
        summary = "PARTIAL"  # Allow minor differences
    else:
        summary = "DIVERGENT"
    
    return {
        "matched": matched,
        "missing_in_engine": len(missing_in_engine),
        "extra_in_engine": len(extra_in_engine),
        "truth_count": len(truth_violations),
        "engine_count": len(engine_violations),
        "summary": summary
    }


# =============================================================================
# Self-Test
# =============================================================================

def _run_self_test():
    from shapely.geometry import Point, Polygon
    from spatial_field_engine import evaluate_compliance
    
    print("=" * 60)
    print("INDEPENDENT TRUTH VERIFICATION TEST")
    print("=" * 60)
    
    # Create test room - 10m x 10m
    room = Room(
        id="test_room",
        name="Test Room",
        geometry=Polygon([(0, 0), (10, 0), (10, 10), (0, 10), (0, 0)]),
        ceiling_height=3.0,
        ceiling_type="SMOOTH"
    )
    
    # Two devices: one in center (5,5), one at (8,8)
    devices = [
        Device(
            id="smoke_1",
            device_type="SMOKE_PHOTOELECTRIC",
            position=Point(5, 5),
            z_height=2.4,
            coverage_radius=4.6
        ),
        Device(
            id="smoke_2",
            device_type="SMOKE_PHOTOELECTRIC",
            position=Point(8, 8),
            z_height=2.4,
            coverage_radius=4.6
        )
    ]
    
    # Obstruction at (1,1) to (2,2)
    obstructions = [
        Obstruction(
            id="obs_wall",
            geometry=Polygon([(1, 1), (2, 1), (2, 2), (1, 2), (1, 1)]),
            height=3.0,
            blocks_visibility=True
        )
    ]
    
    model = NFPAConstraintModel()
    
    # Get truth violations (independent)
    print("\n[1] Running Truth Deriver (independent)...")
    truth_violations = derive_truth(room, devices, obstructions, model)
    print(f"  Truth violations found: {len(truth_violations)}")
    
    # Get engine violations
    print("\n[2] Running Engine (spatial_field_engine)...")
    _, engine_violations = evaluate_compliance(room, devices, obstructions, model)
    print(f"  Engine violations found: {len(engine_violations)}")
    
    # Compare
    print("\n[3] Comparing results...")
    comparison = compare_truths(engine_violations, truth_violations)
    
    print(f"\n  Truth count:   {comparison['truth_count']}")
    print(f"  Engine count:  {comparison['engine_count']}")
    print(f"  Matched:      {comparison['matched']}")
    print(f"  Missing:     {comparison['missing_in_engine']}")
    print(f"  Extra:       {comparison['extra_in_engine']}")
    print(f"  Summary:     {comparison['summary']}")
    
    print("\n" + "=" * 60)
    
    if comparison['summary'] == "CONSISTENT":
        print("✓ INDEPENDENT TRUTH VERIFIED")
    else:
        print(f"✗ DIVERGENCE DETECTED: {comparison['summary']}")
    print("=" * 60)


if __name__ == "__main__":
    _run_self_test()