"""
Validation Layer - Geometry Repair
==============================
Repairs common geometric issues in polygons.
"""

from shapely.geometry import Polygon
from validation.tolerance_model import ToleranceModel


def repair_self_intersection(polygon: Polygon) -> Polygon:
    """
    Repair self-intersecting polygon using buffer(0) technique.
    
    Args:
        polygon: Input polygon that may have self-intersections
        
    Returns:
        Repaired polygon (or original if already valid)
    """
    if polygon.is_valid:
        return polygon
    
    # buffer(0) heals self-intersections
    repaired = polygon.buffer(0)
    
    # If buffer produced multiple polygons, take the largest
    if repaired.is_empty:
        return polygon  # Cannot repair, return original
    
    if repaired.geom_type == 'MultiPolygon':
        # Get the largest polygon
        repaired = max(repaired.geoms, key=lambda p: p.area)
    elif not isinstance(repaired, Polygon):
        return polygon  # Cannot repair to polygon, return original
    
    if repaired.is_empty or repaired.area <= 0:
        return polygon
    
    return repaired


def repair_duplicate_points(polygon: Polygon, epsilon: float) -> Polygon:
    """
    Remove consecutive duplicate or near-duplicate points.
    
    Args:
        polygon: Input polygon
        epsilon: Maximum distance for points to be considered duplicates
        
    Returns:
        Polygon with duplicate points removed (or original if none found)
    """
    coords = list(polygon.exterior.coords)
    if len(coords) <= 3:
        return polygon
    
    new_coords = [coords[0]]
    
    for i in range(1, len(coords)):
        prev_point = new_coords[-1]
        curr_point = coords[i]
        
        # Calculate distance between consecutive points
        dx = curr_point[0] - prev_point[0]
        dy = curr_point[1] - prev_point[1]
        dist = (dx * dx + dy * dy) ** 0.5
        
        if dist > epsilon:
            new_coords.append(curr_point)
    
    # Ensure at least 3 points for valid polygon
    if len(new_coords) < 3:
        return polygon
    
    # Check if first and last are same (closed polygon)
    # Remove the duplicate closing point if very close to first
    if len(new_coords) > 3:
        first = new_coords[0]
        last = new_coords[-1]
        dx = first[0] - last[0]
        dy = first[1] - last[1]
        dist = (dx * dx + dy * dy) ** 0.5
        
        if dist < epsilon:
            new_coords = new_coords[:-1]
    
    return Polygon(new_coords)


def is_degenerate(polygon: Polygon, area_epsilon: float) -> bool:
    """
    Check if polygon is degenerate (zero or near-zero area).
    
    Args:
        polygon: Input polygon
        area_epsilon: Minimum acceptable area
        
    Returns:
        True if area < area_epsilon
    """
    return polygon.area < area_epsilon


def is_valid_polygon(polygon: Polygon) -> bool:
    """
    Check if polygon is valid and non-degenerate.
    
    Args:
        polygon: Input polygon
        
    Returns:
        True if valid and has positive area
    """
    return polygon.is_valid and polygon.area > 0


def repair_polygon(polygon: Polygon, tol: ToleranceModel) -> tuple[Polygon, bool]:
    """
    Full repair sequence for a polygon.
    
    Args:
        polygon: Input polygon
        tol: Tolerance model
        
    Returns:
        Tuple of (repaired_polygon, was_modified)
    """
    original = polygon
    modified = False
    
    # Step 1: Repair self-intersections
    repaired = repair_self_intersection(polygon)
    if repaired != polygon:
        modified = True
        polygon = repaired
    
    # Step 2: If still invalid, try buffer(0) again
    if not polygon.is_valid:
        repaired = polygon.buffer(0)
        if not repaired.is_empty and repaired.geom_type in ('Polygon', 'MultiPolygon'):
            if repaired.geom_type == 'MultiPolygon':
                repaired = max(repaired.geoms, key=lambda p: p.area)
            if repaired != original:
                modified = True
                polygon = repaired
    
    # Step 3: Remove duplicate points
    repaired = repair_duplicate_points(polygon, tol.linear_epsilon)
    if repaired != polygon:
        modified = True
        polygon = repaired
    
    return polygon, modified