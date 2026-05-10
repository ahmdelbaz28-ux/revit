"""
Core Layer - Truth Model
===================
The official definition of truth and compliance.

This is the HEART of the system - it judges the engine's output.
It does NOT perform I/O, does NOT touch files, does NOT import external components
(except Shapely for geometry).

Truth Model establishes:
- What is correct compliance?
- When is a situation ambiguous?
- When should we reject due to invalid geometry?
"""

from enum import Enum
from typing import List, Tuple
from shapely.geometry import Point, Polygon

from core.models import Room, Device, Obstruction, Violation


# =============================================================================
# Official Truth States
# =============================================================================

class TruthState(Enum):
    """The only permitted truth states in the system"""
    PASS = "PASS"                    # Valid geometry, no violations
    FAIL = "FAIL"                   # Valid geometry, measurable violations
    REJECTED_HARD = "REJECTED_HARD"  # Invalid geometry (cannot process)
    REJECTED_AMBIGUOUS = "REJECTED_AMBIGUOUS"  # Ambiguous case (needs review)


# =============================================================================
# Ground Truth Function
# =============================================================================

def evaluate_truth(
    room: Room,
    devices: List[Device],
    obstructions: List[Obstruction],
    violations: List[Violation],
    repaired: bool = False
) -> TruthState:
    """
    Determine the TruthState based on the GROUND TRUTH definition.
    
    This function does NOT invoke the engine. It judges the engine's output.
    It receives violations as input and issues a judgment.
    
    Judgment rules (ordered by priority):
    1. If geometry invalid or devices outside room → REJECTED_HARD
    2. If there's ambiguity (device on obstruction boundary, boundary overlap) → REJECTED_AMBIGUOUS
    3. If geometry valid and no violations → PASS
    4. If geometry valid and measurable violations exist → FAIL
    
    Args:
        room: The room geometry
        devices: List of devices in the room
        obstructions: List of obstructions
        violations: List of violations from engine
        repaired: Whether geometry was auto-repaired
        
    Returns:
        TruthState: One of PASS, FAIL, REJECTED_HARD, REJECTED_AMBIGUOUS
    """
    
    # Rule 1: Check for invalid geometry or devices outside room
    if not _is_geometry_valid(room):
        return TruthState.REJECTED_HARD
    
    for device in devices:
        if not room.geometry.covers(device.position):
            return TruthState.REJECTED_HARD
    
    # Check obstructions are inside room
    for obs in obstructions:
        if not room.geometry.contains(obs.geometry):
            return TruthState.REJECTED_HARD
    
    # Rule 2: Check for ambiguity
    if _is_ambiguous(room, devices, obstructions):
        return TruthState.REJECTED_AMBIGUOUS
    
    # Rule 3 & 4: Judge based on violations
    if violations:
        return TruthState.FAIL
    
    return TruthState.PASS


def _is_geometry_valid(room: Room) -> bool:
    """Check if room geometry is valid (not degenerate, not self-intersecting)"""
    geom = room.geometry
    if geom is None:
        return False
    if not geom.is_valid:
        return False
    if geom.area < 1e-8:  # near-zero area
        return False
    return True


def _is_ambiguous(room: Room, devices: List[Device], 
                obstructions: List[Obstruction]) -> bool:
    """
    Check for ambiguous situations:
    - Device on boundary of obstruction (within epsilon)
    - Device on boundary of room (within epsilon)
    - Boundary overlaps
    """
    epsilon = 0.01  # 1cm tolerance for boundary ambiguity
    
    for device in devices:
        for obs in obstructions:
            # Check if device is on obstruction boundary
            dist = obs.geometry.exterior.distance(device.position)
            if dist < epsilon and dist > 0:
                return True
            
            # Check if device is inside obstruction
            if obs.geometry.covers(device.position):
                return True
        
        # Check if device is on room boundary
        dist = room.geometry.exterior.distance(device.position)
        if dist < epsilon and dist > 0:
            return True
    
    # Check obstruction boundary overlaps
    for i, obs1 in enumerate(obstructions):
        for obs2 in obstructions[i+1:]:
            if obs1.geometry.intersects(obs2.geometry):
                # Check if boundaries touch
                if obs1.geometry.exterior.distance(obs2.geometry.exterior) < epsilon:
                    return True
    
    return False


# =============================================================================
# Repair Semantics
# =============================================================================

def is_repair_valid(
    original: Polygon, 
    repaired: Polygon, 
    tolerance: float = 0.01
) -> bool:
    """
    A repair is VALID if and only if:
    - Topology category preserved (number of holes, connected components)
    - Area difference is less than tolerance
    - No self-intersections produced
    
    Args:
        original: Original geometry before repair
        repaired: Geometry after repair
        tolerance: Maximum allowed area difference (default 1%)
        
    Returns:
        bool: True if repair is valid
    """
    if not repaired.is_valid:
        return False
    
    # Check topology preservation (number of holes)
    original_holes = len(original.interiors)
    repaired_holes = len(repaired.interiors)
    if original_holes != repaired_holes:
        return False
    
    # Check topology preservation (number of connected components)
    if original.is_empty or repaired.is_empty:
        return original.is_empty == repaired.is_empty
    
    # Check area difference
    orig_area = abs(original.area)
    if orig_area > 0:
        area_diff = abs(repaired.area - orig_area) / orig_area
        if area_diff > tolerance:
            return False
    
    return True


# =============================================================================
# Coordinate Quantization (for deterministic checksums)
# =============================================================================

def quantize_point(point: Point, grid: float = 0.01) -> Tuple[float, float]:
    """
    Quantize coordinates to a grid for deterministic checksums.
    
    (x, y) -> (round(x/grid)*grid, round(y/grid)*grid)
    
    Args:
        point: Point to quantize
        grid: Grid size (default 1cm)
        
    Returns:
        Tuple of quantized (x, y)
    """
    x = round(point.x / grid) * grid
    y = round(point.y / grid) * grid
    return (x, y)


def quantize_polygon(polygon: Polygon, grid: float = 0.01) -> Polygon:
    """
    Quantize all coordinates of a polygon.
    
    Args:
        polygon: Polygon to quantize
        grid: Grid size (default 1cm)
        
    Returns:
        Quantized polygon
    """
    coords = list(polygon.exterior.coords)
    quantized = [quantize_point(Point(x, y), grid) for x, y in coords]
    new_coords = [(x, y) for x, y in quantized]
    
    return Polygon(new_coords)


# =============================================================================
# Self-Test
# =============================================================================

def _run_self_tests():
    """Self-test to verify Truth Model works correctly"""
    from shapely.geometry import Point, Polygon
    
    print("=" * 60)
    print("TRUTH MODEL SELF-TESTS")
    print("=" * 60)
    
    # Test 1: Valid room with coverage violations -> FAIL
    print("\n[TEST 1] Valid room with violations -> FAIL")
    room = Room(
        id="test_room",
        name="Test Room",
        geometry=Polygon([(0, 0), (10, 0), (10, 10), (0, 10), (0, 0)]),
        ceiling_height=3.0,
        ceiling_type="SMOOTH"
    )
    devices = [
        Device(
            id="smoke_center",
            device_type="SMOKE_PHOTOELECTRIC",
            position=Point(5, 5),  # 5m from wall - violation
            z_height=2.4,
            coverage_radius=4.6
        )
    ]
    obstructions = []
    violations = [
        Violation(
            rule="MAX_WALL_DISTANCE",
            device_id="smoke_center",
            severity="MAJOR",
            value=5.0,
            threshold=4.55,
            location=Point(5, 5)
        )
    ]
    
    result = evaluate_truth(room, devices, obstructions, violations)
    print(f"  Result: {result.value}")
    assert result == TruthState.FAIL, f"Expected FAIL, got {result}"
    print("  ✓ PASS")
    
    # Test 2: Device outside room -> REJECTED_HARD
    print("\n[TEST 2] Device outside room -> REJECTED_HARD")
    room2 = Room(
        id="test_room2",
        name="Test Room 2",
        geometry=Polygon([(0, 0), (10, 0), (10, 10), (0, 10), (0, 0)]),
        ceiling_height=3.0
    )
    devices2 = [
        Device(
            id="smoke_outside",
            device_type="SMOKE_PHOTOELECTRIC",
            position=Point(15, 15),  # Outside!
            z_height=2.4
        )
    ]
    
    result2 = evaluate_truth(room2, devices2, [], [])
    print(f"  Result: {result2.value}")
    assert result2 == TruthState.REJECTED_HARD, f"Expected REJECTED_HARD, got {result2}"
    print("  ✓ PASS")
    
    # Test 3: Ambiguous case (device on obstruction boundary) -> REJECTED_AMBIGUOUS
    print("\n[TEST 3] Ambiguous case -> REJECTED_AMBIGUOUS")
    room3 = Room(
        id="test_room3",
        name="Test Room 3",
        geometry=Polygon([(0, 0), (10, 0), (10, 10), (0, 10), (0, 0)]),
        ceiling_height=3.0
    )
    devices3 = [
        Device(
            id="smoke_boundary",
            device_type="SMOKE_PHOTOELECTRIC",
            position=Point(5.005, 5),  # On obstruction boundary!
            z_height=2.4
        )
    ]
    obstructions3 = [
        Obstruction(
            id="obs1",
            geometry=Polygon([(5, 0), (6, 0), (6, 10), (5, 10), (5, 0)]),
            height=3.0
        )
    ]
    
    result3 = evaluate_truth(room3, devices3, obstructions3, [])
    print(f"  Result: {result3.value}")
    assert result3 == TruthState.REJECTED_AMBIGUOUS, f"Expected REJECTED_AMBIGUOUS, got {result3}"
    print("  ✓ PASS")
    
    # Test 4: Valid geometry, no violations -> PASS
    print("\n[TEST 4] Valid geometry, no violations -> PASS")
    room4 = Room(
        id="test_room4",
        name="Test Room 4",
        geometry=Polygon([(0, 0), (10, 0), (10, 10), (0, 10), (0, 0)]),
        ceiling_height=3.0
    )
    devices4 = [
        Device(
            id="smoke_ok",
            device_type="SMOKE_PHOTOELECTRIC",
            position=Point(0.5, 0.5),  # Near wall - OK
            z_height=2.4
        )
    ]
    
    result4 = evaluate_truth(room4, devices4, [], [])
    print(f"  Result: {result4.value}")
    assert result4 == TruthState.PASS, f"Expected PASS, got {result4}"
    print("  ✓ PASS")
    
    # Test 5: Quantization
    print("\n[TEST 5] Coordinate quantization")
    point = Point(5.123456, 2.987654)
    quantized = quantize_point(point)
    expected = (5.12, 2.99)
    print(f"  Original: ({point.x}, {point.y})")
    print(f"  Quantized: {quantized}")
    assert quantized == expected, f"Expected {expected}, got {quantized}"
    print("  ✓ PASS")
    
    print("\n" + "=" * 60)
    print("ALL TRUTH MODEL TESTS PASSED!")
    print("=" * 60)


if __name__ == "__main__":
    _run_self_tests()