"""
Geometry Adapter — Infrastructure Layer
====================================
Converts JSON/List polygons to Shapely geometries for ComplianceOracle.

This adapter is the bridge between:
- Layer 2 (Application): JSON polygons from generate_report.py
- Layer 4 (Validation): ComplianceOracle expecting Shapely objects
"""

from shapely.geometry import Polygon, Point
from typing import List, Tuple


def json_polygon_to_shapely(polygon_json: List[List[float]]) -> Polygon:
    """
    Convert JSON polygon [[x1,y1], [x2,y2], ...] to Shapely Polygon.
    Fixes self-intersecting polygons automatically.
    
    Args:
        polygon_json: List of [x, y] coordinates
        
    Returns:
        Shapely Polygon
        
    Raises:
        ValueError: If polygon has < 3 points or is invalid
    """
    if len(polygon_json) < 3:
        raise ValueError(f"Polygon must have >= 3 points, got {len(polygon_json)}")
    
    # Ensure we have at least 4 points (closed polygon)
    # If last point == first, remove the duplicate
    coords = [(float(p[0]), float(p[1])) for p in polygon_json]
    if coords[0] == coords[-1]:
        coords = coords[:-1]
    
    # Create polygon
    poly = Polygon(coords)
    
    # Fix invalid polygons (self-intersecting, holes, etc.)
    if not poly.is_valid:
        poly = poly.buffer(0)
    
    if not poly.is_valid:
        raise ValueError(f"Polygon invalid even after buffer(0): {polygon_json}")
    
    return poly


def coordinate_to_shapely_point(x: float, y: float, z: float = 0.0) -> Point:
    """
    Convert x,y,z coordinates to Shapely Point (2D for Oracle).
    
    Args:
        x: X coordinate
        y: Y coordinate  
        z: Z coordinate (ignored - Oracle uses 2D)
        
    Returns:
        Shapely Point (2D)
    """
    return Point(float(x), float(y))


def calculate_polygon_area(polygon_json: List[List[float]]) -> float:
    """
    Calculate area in square meters from JSON polygon.
    
    Args:
        polygon_json: List of [x, y] coordinates
        
    Returns:
        Area in square meters
    """
    poly = json_polygon_to_shapely(polygon_json)
    return poly.area


def calculate_polygon_perimeter(polygon_json: List[List[float]]) -> float:
    """
    Calculate perimeter in meters from JSON polygon.
    
    Args:
        polygon_json: List of [x, y] coordinates
        
    Returns:
        Perimeter in meters
    """
    poly = json_polygon_to_shapely(polygon_json)
    return poly.length


def is_point_inside_polygon(x: float, y: float, polygon_json: List[List[float]]) -> bool:
    """
    Check if a point is inside the polygon.
    
    Args:
        x: X coordinate
        y: Y coordinate
        polygon_json: List of [x, y] coordinates
        
    Returns:
        True if point is inside or on boundary
    """
    poly = json_polygon_to_shapely(polygon_json)
    point = Point(float(x), float(y))
    return poly.contains(point) or poly.touches(point)


def apply_obstructions(room_polygon: Polygon, obstructions: List) -> Polygon:
    """
    Subtract obstructions from room polygon to get effective coverage area.
    
    Args:
        room_polygon: The original room polygon
        obstructions: List of obstruction polygons (columns, ducts, etc.)
        
    Returns:
        Effective room polygon with obstructions subtracted
    """
    if not obstructions:
        return room_polygon
    
    result = room_polygon
    for obs in obstructions:
        try:
            # Subtract the obstruction
            result = result.difference(obs)
        except Exception:
            # If subtraction fails, keep original
            continue
    
    return result