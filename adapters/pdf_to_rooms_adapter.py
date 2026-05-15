"""
PDF to RoomSpec Adapter
======================
Converts WallElement objects from GeometryExtractor to RoomSpec objects for NFPA engine.
"""

import sys
import os
import importlib.util
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)) + "/..")

from typing import List, Tuple
from shapely.geometry import LineString, Polygon as ShapelyPolygon
from shapely.ops import linemerge, polygonize

from nfpa72_models import RoomSpec, CeilingSpec, CeilingType


def extract_rooms_from_walls(walls: List) -> List[RoomSpec]:
    """
    Convert WallElement objects to RoomSpec objects using shapely polygonize.
    
    Args:
        walls: List of WallElement objects from GeometryExtractor
        
    Returns:
        List of RoomSpec objects representing enclosed rooms
    """
    if not walls or len(walls) < 3:
        return []
    
    # Convert each wall (polygon) to LineString edges
    lines = []
    for wall in walls:
        geometry = wall.geometry
        if len(geometry) < 2:
            continue
        
        # Create LineString from polygon edges
        for i in range(len(geometry)):
            p1 = geometry[i]
            p2 = geometry[(i + 1) % len(geometry)]
            line = LineString([p1, p2])
            lines.append(line)
    
    if not lines:
        return []
    
    # Merge adjacent lines
    try:
        merged = linemerge(lines)
    except Exception:
        return []
    
    # Polygonize to get closed rooms
    try:
        polygons = list(polygonize(merged))
    except Exception:
        return []
    
    # Create RoomSpec for each polygon
    rooms = []
    for idx, poly in enumerate(polygons):
        if not poly.is_valid or poly.is_empty:
            continue
        
        coords = list(poly.exterior.coords)[:-1]  # Remove closing point
        
        if len(coords) < 3:
            continue
        
        # Calculate bounding box for width/depth
        xs = [c[0] for c in coords]
        ys = [c[1] for c in coords]
        width = max(xs) - min(xs)
        depth = max(ys) - min(ys)
        
        if width < 0.5 or depth < 0.5:  # Skip tiny rooms
            continue
        
        # Create CeilingSpec with default height
        ceiling_spec = CeilingSpec.create_safe(height_at_low_point_m=3.0)
        
        # Create RoomSpec
        room = RoomSpec(
            name=f"room_{idx + 1}",
            width_m=width,
            depth_m=depth,
            height_m=ceiling_spec.height_at_low_point_m,
            polygon=ShapelyPolygon(coords),
            ceiling_spec=ceiling_spec,
            occupancy_type="office"
        )
        rooms.append(room)
    
    return rooms


if __name__ == "__main__":
    # Test with sample data - import directly to avoid __init__.py chain
    import sys
    import os
    
    # Direct import bypassing __init__.py
    spec = importlib.util.spec_from_file_location(
        "geometry_extractor",
        os.path.join(os.path.dirname(__file__), "..", "parsers", "geometry_extractor.py")
    )
    geometry_extractor = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(geometry_extractor)
    GeometryExtractor = geometry_extractor.GeometryExtractor
    
    # Extract walls from PDF
    extractor = GeometryExtractor(
        pdf_path="test_data/hybrid/single_office.pdf",
        page_number=0
    )
    walls = extractor.extract_walls()
    
    print(f"Extracted {len(walls)} walls")
    
    # Convert to rooms
    rooms = extract_rooms_from_walls(walls)
    
    print(f"Created {len(rooms)} rooms")
    
    for room in rooms:
        print(f"  - {room.name}: {room.width_m}x{room.depth_m}m")