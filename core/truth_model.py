"""
Core Layer - Truth Model
========================
This module contains only constraint definitions and utilities.
Decision logic has been moved inside ComplianceOracle.

This module provides:
- geometry validation utilities
- coordinate quantization
- repair semantics
- constraint helpers

AUTHORITATIVE: The decision logic (TruthState, evaluate_truth) has been moved 
to ComplianceOracle as private methods. Do NOT use evaluate_truth from here.
"""

from enum import Enum
from typing import List, Tuple
from shapely.geometry import Point, Polygon

from core.models import Room, Device, Obstruction, Violation


# =============================================================================
# Only utility classes remain (constraint definitions)
# =============================================================================

class TruthState(Enum):
    """DEPRECATED: Decision logic moved to ComplianceOracle"""
    PASS = "PASS"                    # Valid geometry, no violations
    FAIL = "FAIL"                   # Valid geometry, measurable violations
    REJECTED_HARD = "REJECTED_HARD"  # Invalid geometry (cannot process)
    REJECTED_AMBIGUOUS = "REJECTED_AMBIGUOUS"  # Ambiguous case (needs review)


# =============================================================================
# Geometry Validation (utility only)
# =============================================================================

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
    """
    x = round(point.x / grid) * grid
    y = round(point.y / grid) * grid
    return (x, y)


def quantize_polygon(polygon: Polygon, grid: float = 0.01) -> Polygon:
    """
    Quantize all coordinates of a polygon.
    """
    coords = list(polygon.exterior.coords)
    quantized = [quantize_point(Point(x, y), grid) for x, y in coords]
    new_coords = [(x, y) for x, y in quantized]
    return Polygon(new_coords)