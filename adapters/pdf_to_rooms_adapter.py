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

# Try to import PyMuPDF for text extraction
try:
    import fitz
    HAS_FITZ = True
except ImportError:
    HAS_FITZ = False
    logger.warning("PyMuPDF (fitz) not installed - room name extraction disabled")

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
def extract_text_from_polygon(polygon: ShapelyPolygon, page, scale: float = 1.0) -> str:
    """
    Extract text found inside a polygon bounds from PDF page.
    
    Args:
        polygon: Shapely polygon defining room boundary
        page: PyMuPDF page object
        scale: Coordinate scale factor (PDF to model units)
    
    Returns:
        str: Best text found inside polygon, or empty string if none found
    """
    if not HAS_FITZ or polygon is None or page is None:
        return ""
    
    try:
        # Get polygon bounds
        min_x, min_y, max_x, max_y = polygon.bounds
        
        # Convert to PDF coordinates (flip Y axis)
        pdf_min_y = page.rect.height - max_y / scale
        pdf_max_y = page.rect.height - min_y / scale
        pdf_min_x = min_x / scale
        pdf_max_x = max_x / scale
        
        # Check each text block
        text_candidates = []
        for block in page.get_text("blocks"):
            if len(block) >= 5:
                # block = [x0, y0, x1, y1, text, ...]
                bx0, by0, bx1, by1 = block[0], block[1], block[2], block[3]
                text = block[4].strip()
                
                if not text:
                    continue
                
                # Check if text is within polygon bounds
                # Allow some margin
                margin = 0.1
                if (pdf_min_x - margin <= bx0 and bx1 <= pdf_max_x + margin and
                    pdf_min_y - margin <= by0 and by1 <= pdf_max_y + margin):
                    # Calculate center distance to prefer center text
                    center_x = (bx0 + bx1) / 2
                    center_y = (by0 + by1) / 2
                    poly_center_x = (pdf_min_x + pdf_max_x) / 2
                    poly_center_y = (pdf_min_y + pdf_max_y) / 2
                    dist = ((center_x - poly_center_x)**2 + (center_y - poly_center_y)**2)**0.5
                    
                    # Score: prefer larger text, closer to center
                    score = len(text) / (1.0 + dist * 0.1)
                    text_candidates.append((score, text))
        
        if text_candidates:
            # Return highest scoring text
            text_candidates.sort(reverse=True, key=lambda x: x[0])
            return text_candidates[0][1]
        
        return ""
        
    except Exception as e:
        logger.debug(f"Text extraction failed: {e}")
        return ""


def extract_rooms_from_pdf(pdf_path: str) -> Tuple[List[ShapelyPolygon], any]:
    """
    Extract room polygons directly from PDF with text extraction.
    
    Args:
        pdf_path: Path to PDF file
    
    Returns:
        Tuple of (polygons, pdf_page) for room extraction
    """
    if not HAS_FITZ:
        return [], None
    
    try:
        doc = fitz.open(pdf_path)
        page = doc[0]  # First page
        
        # Reuse existing wall extraction logic
        from parsers.geometry_extractor import GeometryExtractor
        extractor = GeometryExtractor(pdf_path)
        walls = extractor.extract_walls()
        
        polygons, report = extract_rooms_from_walls(walls)
        
        # Extract text for each room
        for poly in polygons:
            text = extract_text_from_polygon(poly, page)
            if text:
                logger.info(f"Found room text: '{text}'")
        
        doc.close()
        return polygons, page
        
    except Exception as e:
        logger.warning(f"PDF text extraction failed: {e}")
        return [], None


def select_safe_detector_type(room_name: str, room_type_guess: str = "office") -> DetectorType:
    """
    NFPA 72-2022 Compliant Detector Selection Logic.
    MUST be called before any placement logic.
    
    Args:
        room_name: Name of the room (used for keyword matching)
        room_type_guess: Fallback occupancy type if name matching fails
    
    Returns:
        DetectorType: Appropriate detector type based on NFPA 72
    """
    name_lower = room_name.lower() if room_name else ""
    type_lower = room_type_guess.lower() if room_type_guess else ""
    
    # Use both room_name AND room_type_guess for keyword matching
    search_text = name_lower + " " + type_lower
    
    # 1. KITCHENS / COOKING AREAS (NO SMOKE DETECTORS ALLOWED)
    # NFPA 72 §17.6.4: Smoke detectors shall not be installed in cooking areas.
    kitchen_keywords = ['kitchen', 'cook', 'pantry', 'galley', 'canteen', 'cafeteria']
    if any(kw in search_text for kw in kitchen_keywords):
        logger.info(f"Room '{room_name}' ({room_type_guess}): Using HEAT detector (kitchen/cooking)")
        return DetectorType.HEAT_FIXED_TEMP
    
    # 2. SERVER ROOMS / DATA CENTERS (HIGH SENSITIVITY REQUIRED)
    server_keywords = ['server', 'data center', 'it room', 'network', 'telecom', 'idf', 'mdf']
    if any(kw in search_text for kw in server_keywords):
        logger.info(f"Room '{room_name}' ({room_type_guess}): Using MULTI-CRITERIA detector (server)")
        return DetectorType.SMOKE_HEAT_COMBINATION
    
    # 3. GARAGES / PARKING
    garage_keywords = ['garage', 'parking', 'car park', 'vehicle']
    if any(kw in search_text for kw in garage_keywords):
        logger.info(f"Room '{room_name}' ({room_type_guess}): Using HEAT detector (garage/parking)")
        return DetectorType.HEAT_FIXED_TEMP
    
    # 4. WAREHOUSES / STORAGE
    warehouse_keywords = ['warehouse', 'storage', 'stock', 'inventory', 'loading']
    if any(kw in search_text for kw in warehouse_keywords):
        logger.info(f"Room '{room_name}' ({room_type_guess}): Using HEAT detector (warehouse)")
        return DetectorType.HEAT_RATE_OF_RISE
    
    # 5. OFFICES / ADMINISTRATIVE AREAS (USE SMOKE DETECTORS)
    # Smoke detectors are appropriate for offices - smoke appears before heat
    office_keywords = ['office', 'admin', 'administrative', 'desk', 'workroom', 'conference', 'meeting']
    if any(kw in search_text for kw in office_keywords):
        logger.info(f"Room '{room_name}' ({room_type_guess}): Using SMOKE detector (office/administrative)")
        return DetectorType.SMOKE
    
    # 6. CONSERVATIVE DEFAULT: Unknown = Unknown (no detectors)
    # When we can't determine room type, don't place detectors
    logger.warning(f"Room '{room_name}' ({room_type_guess}): Unknown type - no detectors placed")
    # Try HEAT for unknown but warn
    return DetectorType.HEAT


def guess_room_type(room_name: str) -> str:
    """
    Infer room type from room name using keyword matching.
    
    Args:
        room_name: Name of the room (may contain text labels from PDF)
    
    Returns:
        str: Inferred occupancy type
    """
    name_lower = room_name.lower() if room_name else ""
    
    # Skip if it's a generic auto-generated name
    if name_lower.startswith("room_") or name_lower == "unknown":
        return "office"  # Default when no info
    
    # Kitchen / Cooking areas
    kitchen_keywords = ["kitchen", "cook", "pantry", "galley", "canteen", "cafeteria", "مطبخ"]
    if any(kw in name_lower for kw in kitchen_keywords):
        return "kitchen"
    
    # Server / Data center
    server_keywords = ["server", "data center", "it room", "network", "telecom", "idf", "mdf", "خادم"]
    if any(kw in name_lower for kw in server_keywords):
        return "server_room"
    
    # Corridor / Hallway
    corridor_keywords = ["corridor", "hallway", "hall", "passage", "ممر", " corridor"]
    if any(kw in name_lower for kw in corridor_keywords):
        return "corridor"
    
    # Bedroom
    bedroom_keywords = ["bedroom", "bed", "sleeping", " dorm", "غرفه نوم"]
    if any(kw in name_lower for kw in bedroom_keywords):
        return "bedroom"
    
    # Bathroom
    bathroom_keywords = ["bathroom", "bath", "toilet", "washroom", "حمام"]
    if any(kw in name_lower for kw in bathroom_keywords):
        return "bathroom"
    
    # Garage / Parking
    garage_keywords = ["garage", "parking", "car park", "مكر"]
    if any(kw in name_lower for kw in garage_keywords):
        return "garage"
    
    # Warehouse / Storage
    warehouse_keywords = ["warehouse", "storage", "stock", "مستودع"]
    if any(kw in name_lower for kw in warehouse_keywords):
        return "warehouse"
    
    # Default
    return "office"


def validate_and_guess_type_detailed(
    room_name: str,
    polygon: ShapelyPolygon,
    has_windows: bool = True,
    adjacent_rooms: list = None
) -> dict:
    """
    Contextual validation - detect contradictions between name and physical properties.
    
    This implements the "Reasonable Doubt Policy":
    - If name contradicts physical properties, flag for MANUAL_REVIEW
    - Default to fail-safe (HEAT) when uncertain
    
    Args:
        room_name: Name from PDF or guessed
        polygon: Room geometry
        has_windows: Does room have windows (from PDF analysis)
        adjacent_rooms: List of adjacent room names
    
    Returns:
        dict with: detector_type, requires_review, warnings, confidence
    """
    name_lower = room_name.lower() if room_name else ""
    area_sqm = polygon.area
    adjacent = [r.lower() for r in (adjacent_rooms or [])]
    
    warnings = []
    requires_review = False
    
    # Get base type from name
    base_type = guess_room_type(room_name)
    
    # ====== CONTEXTUAL CHECKS ======
    
    # Check 1: Server room size (should be < 50 sqm typically)
    if "server" in name_lower and area_sqm > 50:
        warnings.append(f"Large server room ({area_sqm:.0f} sqm) - atypical")
        requires_review = True
    
    # Check 2: Office without windows (atypical)
    if "office" in name_lower and not has_windows:
        warnings.append("Office without windows - possibly storage/electrical")
        requires_review = True
    
    # Check 3: Bedroom near wet areas
    if "bedroom" in name_lower or "bed" in name_lower:
        has_nearby_wet = any(wet in adjacent for wet in ["bath", "kitchen", "toilet", "wc"])
        if has_nearby_wet:
            warnings.append("Bedroom adjacent to wet area - verify occupancy")
            requires_review = True
    
    # Check 4: Large storage (>= 50 sqm needs review - warehouses are typically open plan)
    if "storage" in name_lower and area_sqm >= 50:
        warnings.append(f"Large storage ({area_sqm:.0f} sqm) - verify purpose")
        requires_review = True
    

    # ====== SIZE-BASED FAIL-SAFE (applies to ALL rooms) ======

    # Large rooms (> 75 sqm) without windows need review
    if area_sqm > 75 and not has_windows:
        warnings.append(f"Large room ({area_sqm:.0f} sqm) without windows - verify purpose")
        requires_review = True

    # Very small rooms (< 5 sqm) need review - may be closets
    if area_sqm < 5:
        warnings.append(f"Tiny room ({area_sqm:.1f} sqm) - verify occupancy")
        requires_review = True
    # Check 5: Kitchen named "Office" near water
    if "office" in name_lower and any(wet in adjacent for wet in ["kitchen", "pantry"]):
        warnings.append("Office adjacent to kitchen - verify no cooking")
        requires_review = True
    
    # ====== DETERMINE DETECTOR TYPE ======
    
    if requires_review:
        # When uncertain: FAIL-SAFE default to HEAT
        detector_type = "heat_fixed_temp"  # Fail-safe
        confidence = "LOW"
    else:
        # Use normal mapping - pass both room_name and occupancy_type
        detector_type = select_safe_detector_type(room_name, room.occupancy_type).value
        confidence = "HIGH"
    
    return {
        "detector_type": detector_type,
        "requires_review": requires_review,
        "warnings": warnings,
        "confidence": confidence,
        "base_occupancy": base_type,
        "area_sqm": area_sqm
    }


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
    large_rooms_flagged: List[dict] = field(default_factory=list)
    validation_failures: List[dict] = field(default_factory=list)
    discarded_walls_details: List[dict] = field(default_factory=list)


def _filter_valid_rooms(polygons: List[ShapelyPolygon], walls: List, lines: List[LineString]) -> Tuple[List[ShapelyPolygon], ExtractionReport]:
    """
    Filter polygons to keep only valid rooms:
    1. Exclude ONLY outer boundary (>100x larger than second)
    2. Exclude tiny polygons (noise)
    3. Flag large/outlier rooms for PE review (no deletion!)
    """
    import statistics
    
    report = ExtractionReport(rooms_raw=len(polygons))
    
    if not polygons:
        return [], report
    
    sorted_polys = sorted(polygons, key=lambda p: p.area, reverse=True)
    filtered_polys = []
    
    # Robust baseline using median (more stable than average)
    areas = [p.area for p in polygons]
    median_area = statistics.median(areas) if areas else 0.0
    
    for idx, poly in enumerate(sorted_polys):
        area = poly.area
        
        # Skip tiny polygons (noise)
        if area < MIN_ROOM_AREA_SQM:
            report.small_polygons_filtered += 1
            logger.debug(f"Filtered small polygon: area={area:.2f}sqm")
            continue
        
        # Exclude ONLY outer boundary (>100x larger than second)
        if idx == 0 and len(sorted_polys) > 1:
            second_largest = sorted_polys[1].area
            if area > second_largest * 100:
                report.outer_boundary_excluded = True
                logger.info(f"Excluded outer boundary: {area:.1f}sqm (vs {second_largest:.1f}sqm)")
                continue
        
        # FLAG outliers - any statistically large or absolutely large space
        # No deletion - only warning for PE review
        is_outlier = (area > median_area * 10) or (area > 1000.0)
        if is_outlier:
            ratio = round(area / median_area, 1) if median_area else None
            report.large_rooms_flagged.append({
                "index": idx,
                "area_m2": round(area, 1),
                "median_m2": round(median_area, 1),
                "ratio": ratio,
                "reason": "outlier_large_space",
            })
            logger.warning(
                f"⚠️ Large space #{idx}: {area:.1f}m² "
                f"(median={median_area:.1f}m², ratio={ratio}x) — "
                f"MANUAL REVIEW REQUIRED"
            )
        
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
        except Exception as e:
            return False, f"Room {index}: Invalid polygon ({e})"
    
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


def extract_rooms_from_walls(walls: List, enable_gap_closing: bool = True, pdf_path: str = None) -> Tuple[List[RoomSpec], ExtractionReport]:
    """
    Convert WallElement objects to RoomSpec objects.
    Robust version with gap closing, validation, and boundary filtering.
    
    Args:
        walls: List of WallElement objects
        enable_gap_closing: Enable gap closing (default False)
        pdf_path: Optional PDF path for text extraction
    """
    report = ExtractionReport(walls_input=len(walls) if walls else 0)
    pdf_page = None
    text_found = False
    
    # Open PDF for text extraction if available
    if pdf_path and HAS_FITZ:
        try:
            doc = fitz.open(pdf_path)
            pdf_page = doc[0]
            logger.info(f"Opened PDF for text extraction: {pdf_path}")
        except Exception as e:
            logger.warning(f"Could not open PDF: {e}")
    
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
            # تسجيل قسري في التقرير الرسمي - لا سماح بالصمت
            report.validation_failures.append({
                "room_index": idx,
                "reason": error_msg,
                "coordinates": str(poly.exterior.coords) if poly and hasattr(poly, 'exterior') else "N/A"
            })
            logger.warning(f"Room rejected: {error_msg}")
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
            # تسجيل قسري في التقرير الرسمي - لا سماح بالصمت
            report.validation_failures.append({
                "room_index": idx,
                "reason": f"dimensions too small ({width:.2f}x{depth:.2f}m)",
                "coordinates": str(poly.exterior.coords) if poly and hasattr(poly, 'exterior') else "N/A"
            })
            logger.warning(f"Room rejected: dimensions too small ({width:.2f}x{depth:.2f}m)")
            continue
        
        ceiling_spec = CeilingSpec.create_safe(height_at_low_point_m=3.0)
        
        # Try to extract room name from PDF text
        room_label = None
        if pdf_page:
            room_label = extract_text_from_polygon(poly, pdf_page)
            if room_label:
                text_found = True
                logger.info(f"Room {idx}: extracted name '{room_label}'")
        
        # Use extracted name or fallback to generic
        if not room_label:
            room_label = f"room_{idx + 1}"
        
        room = RoomSpec(
            name=room_label,
            width_m=width,
            depth_m=depth,
            height_m=ceiling_spec.height_at_low_point_m,
            polygon=ShapelyPolygon(normalized_coords),
            ceiling_spec=ceiling_spec,
            occupancy_type=guess_room_type(room_label)
        )
        rooms.append(room)
    
    report.rooms_created = len(rooms)
    report.final_room_count = len(rooms)
    logger.info(f"Extraction complete: {report.rooms_created} rooms from {report.walls_input} walls")
    
    # WARNING if no text was found - PE review mandatory
    if pdf_path and not text_found:
        logger.warning("NO TEXT FOUND IN ROOMS - DEFAULTING TO OFFICE/SMOKE. PE REVIEW MANDATORY.")
        report.validation_failures.append({
            "room_index": -1,
            "reason": "NO_TEXT_FOUND_IN_PDF - PE_REVIEW_MANDATORY",
            "coordinates": "N/A"
        })
    
    return rooms, report


def _extract_room_label_from_pdf(pdf_path: str, polygon_bounds: tuple) -> str:
    """
    Extract room label from PDF text that falls within polygon bounds.
    
    Args:
        pdf_path: Path to PDF file
        polygon_bounds: (minx, miny, maxx, maxy) bounds
    
    Returns:
        str: Room label if found, empty string otherwise
    """
    try:
        import fitz
    except ImportError:
        return ""
    
    try:
        doc = fitz.open(pdf_path)
        page = doc[0]
        
        # Get all text with positions
        texts = page.get_text('words')
        
        if not texts:
            return ""
        
        minx, miny, maxx, maxy = polygon_bounds
        
        # Look for text inside the polygon bounds
        # Use a relaxed bounds (text center inside polygon)
        for t in texts:
            x0, y0, x1, y1, text = t[:5]
            # Check if text center is within bounds
            cx = (x0 + x1) / 2
            cy = (y0 + y1) / 2
            
            if minx < cx < maxx and miny < cy < maxy:
                # Clean the text - remove numbers and common prefixes
                text = text.strip()
                if text and not text.isdigit():
                    # Skip common non-room labels
                    lower = text.lower()
                    if lower in ['fireai', 'test', 'scale', 'area', 'n', 'area:']:
                        continue
                    return text
        
        return ""
    except Exception:
        return ""


def design_room_from_pdf(pdf_path: str, room_index: int = 0) -> dict:
    """
    Complete PDF to design pipeline.
    
    Now extracts room labels from PDF text when available.
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

    # ====== ENHANCE: Extract room names from PDF text ======
    poly = room.polygon
    bbox = poly.bounds
    
    room_label = _extract_room_label_from_pdf(pdf_path, bbox)
    
    if room_label:
        old_name = room.name
        room.name = room_label
        room.occupancy_type = guess_room_type(room_label)
        logger.info(f"Room named from PDF: '{old_name}' → '{room_label}'")
    
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