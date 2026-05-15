"""
PDF to RoomSpec Adapter (Robust Version with Boundary Filtering)
================================================================
Converts WallElement objects from GeometryExtractor to RoomSpec objects for NFPA engine.
- Gap closing for adjacent walls
- Polygon validation
- Discarded walls logging
- Outer boundary exclusion (critical for production)
- Noise filtering (small polygons)

Usage:
    from adapters.pdf_to_rooms_adapter import extract_rooms_from_walls, design_room_from_pdf
    
    walls = extractor.extract_walls()
    rooms, report = extract_rooms_from_walls(walls)
    
    # report contains: walls_used, walls_discarded, gaps_closed, rooms_created, etc.
"""

import sys
import os
import importlib.util
import logging
from dataclasses import dataclass, field
from typing import List, Tuple

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)) + "/..")

from shapely.geometry import LineString, Polygon as ShapelyPolygon
from shapely.ops import linemerge, polygonize

from nfpa72_models import RoomSpec, CeilingSpec, CeilingType, DetectorType
from nfpa72_coverage import check_coverage_polygon

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Constants
# WARNING: Gap closing disabled by default to prevent room fragmentation
# Set to > 0 to enable, but keep < 0.05 (5cm) max
GAP_CLOSURE_THRESHOLD = 0.0  # 0 = disabled - prevents opening doors/windows from being closed
MIN_ROOM_AREA_SQM = 1.0
MAX_ROOM_AREA_SQM = 200.0


@dataclass
class ExtractionReport:
    """Report containing detailed extraction statistics."""
    walls_input: int = 0
    walls_used: int = 0
    walls_discarded: int = 0
    gaps_closed: int = 0
    rooms_raw: int = 0  # Before filtering
    rooms_created: int = 0  # After filtering
    outer_boundary_excluded: bool = False
    small_polygons_filtered: int = 0
    large_polygons_filtered: int = 0
    final_room_count: int = 0
    validation_failures: List[str] = field(default_factory=list)
    discarded_walls_details: List[dict] = field(default_factory=list)


def _filter_valid_rooms(polygons: List[ShapelyPolygon], walls: List, lines: List[LineString]) -> Tuple[List[ShapelyPolygon], ExtractionReport]:
    """
    Filter polygons to keep only valid rooms:
    1. Exclude only the obvious outer boundary (single very large polygon at 100x larger than any room)
    2. Exclude tiny polygons (noise)
    3. Keep all normal rooms (including conference halls)
    """
    from dataclasses import asdict
    
    report = ExtractionReport(rooms_raw=len(polygons))
    
    if not polygons:
        return [], report
    
    # Sort by area
    sorted_polys = sorted(polygons, key=lambda p: p.area, reverse=True)
    filtered_polys = []
    
    for idx, poly in enumerate(sorted_polys):
        area = poly.area
        
        # Skip tiny polygons (noise)
        if area < MIN_ROOM_AREA_SQM:
            report.small_polygons_filtered += 1
            logger.debug(f"Filtered small polygon: area={area:.2f}sqm")
            continue
        
        # Exclude ONLY outer boundary:
        # - It's largest (idx==0)
        # - There's more than one polygon
        # - It's >100x larger than second (true boundary: ~9000sqm vs ~30sqm = 300x)
        if idx == 0 and len(sorted_polys) > 1:
            second_largest = sorted_polys[1].area
            # 100x threshold to avoid false positives on conference halls
            if area > second_largest * 100:
                report.outer_boundary_excluded = True
                logger.info(f"Excluded outer boundary: {area:.1f}sqm (vs {second_largest:.1f}sqm)")
                continue
        
        filtered_polys.append(poly)
    
    report.final_room_count = len(filtered_polys)
    logger.info(f"Filtered {len(polygons)} -> {len(filtered_polys)} rooms")
    
    return filtered_polys, report


def validate_room_polygon(poly, index: int) -> Tuple[bool, str]:
    """
    Validate that a polygon is suitable for room creation.
    
    Args:
        poly: Shapely Polygon object
        index: Room index for error messages
    
    Returns:
        Tuple of (is_valid, error_message)
    """
    if poly.is_empty:
        return False, f"Room {index}: Polygon is empty"
    
    if not poly.is_valid:
        try:
            poly = poly.buffer(0)
            if not poly.is_valid:
                return False, f"Room {index}: Invalid polygon (cannot be fixed)"
        except:
            return False, f"Room {index}: Invalid polygon"
    
    # Check for zero-length sides
    coords = list(poly.exterior.coords)
    for i in range(len(coords) - 1):
        p1 = coords[i]
        p2 = coords[i + 1]
        dist = ((p2[0] - p1[0])**2 + (p2[1] - p1[1])**2) ** 0.5
        if dist < 0.01:
            return False, f"Room {index}: Zero-length side detected"
    
    # Check for negative or zero area
    if poly.area < 0.01:
        return False, f"Room {index}: Area too small ({poly.area:.4f} sqm)"
    
    return True, ""


def close_gaps_in_lines(lines: List[LineString], threshold: float = GAP_CLOSURE_THRESHOLD) -> Tuple[List[LineString], int]:
    """
    Close small gaps between adjacent line segments (drawing errors only).
    WARNING: Don't close gaps > 80cm as these are likely doors/windows.
    """
    if len(lines) < 2:
        return lines, 0
    
    gaps_closed = 0
    modified_lines = list(lines)
    
    for i in range(len(modified_lines)):
        for j in range(i + 1, len(modified_lines)):
            line_i = modified_lines[i]
            line_j = modified_lines[j]
            
            if line_i.is_empty or line_j.is_empty:
                continue
            
            end_i = line_i.coords[-1]
            start_j = line_j.coords[0]
            dist = ((end_i[0] - start_j[0])**2 + (end_i[1] - start_j[1])**2) ** 0.5
            
            # WARNING: Don't close gaps > 0.8m (80cm) - these are real doors/windows
            if threshold < dist < 0.8:
                continue  # Skip - likely architectural opening
            
            if dist < threshold:
                new_coords = list(line_i.coords)[:-1] + list(line_j.coords)
                modified_lines[i] = LineString(new_coords)
                modified_lines[j] = LineString([])
                gaps_closed += 1
                break
    
    modified_lines = [l for l in modified_lines if not l.is_empty and len(l.coords) > 1]
    
    return modified_lines, gaps_closed


def extract_rooms_from_walls(walls: List, enable_gap_closing: bool = True) -> Tuple[List[RoomSpec], ExtractionReport]:
    """
    Convert WallElement objects to RoomSpec objects.
    Robust version with gap closing, validation, and boundary filtering.
    """
    report = ExtractionReport(walls_input=len(walls) if walls else 0)
    
    if not walls or len(walls) < 2:
        return [], report
    
    # Convert each wall (polygon) to LineString edges
    used_wall_indices = set()
    lines = []
    
    for wall_idx, wall in enumerate(walls):
        geometry = wall.geometry
        if len(geometry) < 2:
            report.discarded_walls_details.append({
                "index": wall_idx,
                "reason": "too_few_points",
                "points_count": len(geometry)
            })
            continue
        
        wall_lines = []
        for i in range(len(geometry)):
            p1 = geometry[i]
            p2 = geometry[(i + 1) % len(geometry)]
            line = LineString([p1, p2])
            wall_lines.append(line)
        
        lines.extend(wall_lines)
        used_wall_indices.add(wall_idx)
    
    if not lines:
        report.walls_used = 0
        return [], report
    
    report.walls_used = len(used_wall_indices)
    report.walls_discarded = len(walls) - len(used_wall_indices)
    
    for detail in report.discarded_walls_details:
        logger.warning(f"Wall {detail['index']} discarded: {detail['reason']}")
    
    # Optional: Gap closing (disabled by default to prevent room fragmentation)
    if enable_gap_closing and GAP_CLOSURE_THRESHOLD > 0:
        lines, gaps_closed = close_gaps_in_lines(lines, GAP_CLOSURE_THRESHOLD)
        report.gaps_closed = gaps_closed
        if gaps_closed > 0:
            logger.info(f"Closed {gaps_closed} gaps between walls")
    
    # Merge adjacent lines
    try:
        merged = linemerge(lines)
    except Exception as e:
        report.validation_failures.append(f"linemerge failed: {str(e)}")
        return [], report
    
    import logging
    
    # Polygonize to get closed rooms
    try:
        all_polygons = list(polygonize(merged))
    except Exception as e:
        report.validation_failures.append(f"polygonize failed: {str(e)}")
        return [], report
    
    
    report.rooms_raw = len(all_polygons)
    
    # Filter valid rooms (exclude outer boundary and noise)
    filtered_polygons, filter_report = _filter_valid_rooms(all_polygons, walls, lines)
    report.outer_boundary_excluded = filter_report.outer_boundary_excluded
    report.small_polygons_filtered = filter_report.small_polygons_filtered
    report.large_polygons_filtered = filter_report.large_polygons_filtered
    
    # Create RoomSpec for each filtered polygon
    rooms = []
    for idx, poly in enumerate(filtered_polygons):
        is_valid, error_msg = validate_room_polygon(poly, idx)
        
        if not is_valid:
            report.validation_failures.append(error_msg)
            logger.warning(error_msg)
            continue
        
        coords = list(poly.exterior.coords)[:-1]
        
        if len(coords) < 3:
            continue
        
        # Normalize coordinates to start from origin
        xs = [c[0] for c in coords]
        ys = [c[1] for c in coords]
        min_x, min_y = min(xs), min(ys)
        
        normalized_coords = [(x - min_x, y - min_y) for x, y in zip(xs, ys)]
        
        width = max(xs) - min(xs)
        depth = max(ys) - min(ys)
        
        if width < 0.5 or depth < 0.5:
            report.validation_failures.append(f"Room {idx}: dimensions too small ({width:.2f}x{depth:.2f}m)")
            continue
        
        ceiling_spec = CeilingSpec.create_safe(height_at_low_point_m=3.0)
        
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
    
    report.rooms_created = len(rooms)
    report.final_room_count = len(rooms)
    logger.info(f"Extraction complete: {report.rooms_created} rooms from {report.walls_input} walls")
    
    return rooms, report


def design_room_from_pdf(pdf_path: str, room_index: int = 0) -> dict:
    """
    Complete PDF to design pipeline.
    """
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
        return {"error": "No walls extracted from PDF", "room": None, "extraction_report": None}
    
    # Step 2: Convert to rooms with filtering
    rooms, report = extract_rooms_from_walls(walls, enable_gap_closing=True)
    
    if room_index >= len(rooms):
        return {
            "error": f"Room index {room_index} out of range",
            "room": None,
            "extraction_report": report
        }
    
    room = rooms[room_index]
    
    # Step 3: Place detectors
    ceiling_height = room.ceiling_spec.height_at_low_point_m
    
    if ceiling_height <= 3.0:
        radius = 4.1
    elif ceiling_height <= 4.3:
        radius = 4.6
    elif ceiling_height <= 6.1:
        radius = 5.2
    elif ceiling_height <= 7.6:
        radius = 5.8
    else:
        radius = 6.4
    
    spacing = radius
    margin = 0.3
    
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
        "extraction_report": report
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
    
    extractor = GeometryExtractor(
        pdf_path="test_data/hybrid/single_office.pdf",
        page_number=0
    )
    walls = extractor.extract_walls()
    
    print(f"=== Extracted {len(walls)} walls ===")
    
    rooms, report = extract_rooms_from_walls(walls, enable_gap_closing=True)
    
    print(f"\n=== EXTRACTION REPORT ===")
    print(f"Walls Input: {report.walls_input}")
    print(f"Walls Used: {report.walls_used}")
    print(f"Walls Discarded: {report.walls_discarded}")
    print(f"Gaps Closed: {report.gaps_closed}")
    print(f"Rooms Raw (before filtering): {report.rooms_raw}")
    print(f"Outer Boundary Excluded: {report.outer_boundary_excluded}")
    print(f"Small Polygons Filtered: {report.small_polygons_filtered}")
    print(f"Large Polygons Filtered: {report.large_polygons_filtered}")
    print(f"Final Rooms: {report.final_room_count}")
    
    print(f"\n=== Rooms ===")
    for room in rooms:
        print(f"  - {room.name}: {room.width_m:.2f}x{room.depth_m:.2f}m ({room.width_m * room.depth_m:.1f}sqm)")