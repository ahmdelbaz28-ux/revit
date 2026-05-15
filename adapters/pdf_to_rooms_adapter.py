"""
PDF to RoomSpec Adapter
======================
Converts WallElement objects from GeometryExtractor to RoomSpec objects for NFPA engine.
Complete PDF → Design pipeline for fire detection coverage.
"""

import sys
import os
import importlib.util
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)) + "/..")

from typing import List, Tuple
from shapely.geometry import LineString, Polygon as ShapelyPolygon
from shapely.ops import linemerge, polygonize

from nfpa72_models import RoomSpec, CeilingSpec, CeilingType, DetectorType
from nfpa72_coverage import check_coverage_polygon


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
        
        # Normalize coordinates to start from origin
        xs = [c[0] for c in coords]
        ys = [c[1] for c in coords]
        min_x, min_y = min(xs), min(ys)
        
        # Shift coordinates to origin
        normalized_coords = [(x - min_x, y - min_y) for x, y in zip(xs, ys)]
        
        width = max(xs) - min(xs)
        depth = max(ys) - min(ys)
        
        if width < 0.5 or depth < 0.5:  # Skip tiny rooms
            continue
        
        # Create CeilingSpec with default height
        ceiling_spec = CeilingSpec.create_safe(height_at_low_point_m=3.0)
        
        # Create RoomSpec with normalized polygon
        room = RoomSpec(
            name=f"room_{idx + 1}",
            width_m=width,
            depth_m=depth,
            height_m=ceiling_spec.height_at_low_point_m,
            polygon=ShapelyPolygon(normalized_coords),
            ceiling_spec=ceiling_spec,
            occupancy_type="office"
        )
        rooms.append(room)
    
    return rooms


def design_room_from_pdf(pdf_path: str, room_index: int = 0) -> dict:
    """
    Complete PDF to design pipeline: extract walls → create room → place detectors → verify coverage.
    
    Args:
        pdf_path: Path to PDF file
        room_index: Index of room to design (default: 0)
    
    Returns:
        dict with: room, detector_positions, detector_count, coverage_pct, is_compliant, violations
    """
    import math
    
    # Import GeometryExtractor directly
    spec = importlib.util.spec_from_file_location(
        "geometry_extractor",
        os.path.join(os.path.dirname(__file__), "..", "parsers", "geometry_extractor.py")
    )
    geometry_extractor = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(geometry_extractor)
    GeometryExtractor = geometry_extractor.GeometryExtractor
    
    # Step 1: Extract walls
    extractor = GeometryExtractor(pdf_path, page_number=0)
    walls = extractor.extract_walls()
    
    if not walls:
        return {"error": "No walls extracted from PDF", "room": None}
    
    # Step 2: Convert to rooms
    rooms = extract_rooms_from_walls(walls)
    
    if room_index >= len(rooms):
        return {"error": f"Room index {room_index} out of range", "room": None}
    
    room = rooms[room_index]
    
    # Step 3: Place detectors using simple grid placement
    # Calculate NFPA-compliant spacing based on ceiling height
    ceiling_height = room.ceiling_spec.height_at_low_point_m
    
    # Get coverage radius based on NFPA 72 Table 17.6.3.2
    if ceiling_height <= 3.0:
        radius = 4.1  # 10-14 ft
    elif ceiling_height <= 4.3:
        radius = 4.6  # 14-20 ft
    elif ceiling_height <= 6.1:
        radius = 5.2  # 20-25 ft
    elif ceiling_height <= 7.6:
        radius = 5.8  # 25-30 ft
    else:
        radius = 6.4  # 30-50 ft
    
    spacing = radius  # Use radius as spacing for better coverage
    margin = 0.3  # Edge margin
    
    # Simple grid placement - cover entire room
    detector_positions = []
    room_width = room.width_m
    room_depth = room.depth_m
    
    y = margin
    row = 0
    while y < room_depth - margin:
        x = margin + (spacing / 2 if row % 2 == 1 else margin)
        while x < room_width - margin:
            detector_positions.append((round(x, 2), round(y, 2)))
            x += spacing
        y += spacing
        row += 1
    
    detector_count = len(detector_positions)
    
    # Step 4: Verify coverage
    result = check_coverage_polygon(
        detector_positions, room, room.ceiling_spec, DetectorType.SMOKE
    )
    
    return {
        "room": room,
        "detector_positions": detector_positions,
        "detector_count": detector_count,
        "coverage_pct": result.coverage_percentage,
        "is_compliant": result.is_covered,
        "violations": result.violations if hasattr(result, 'violations') else [],
    }


if __name__ == "__main__":
    # Test with sample data
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