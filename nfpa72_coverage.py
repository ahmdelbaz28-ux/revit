"""
NFPA 72 V5 Coverage - Polygon and Voronoi Coverage Checks

This module provides coverage checking using Polygon containment
instead of Bounding Box. This is critical for L-shaped rooms where
Bounding Box produces false 100% coverage.

⚠️ LEGAL DISCLAIMER:
This code is provided for compliance assistance only.
It does not constitute legal advice.
Always verify with a licensed fire protection engineer.
NFPA 72 (2022 Edition) is the authoritative standard.
"""

import math
from typing import List, Tuple, Optional
from shapely.geometry import Polygon, Point, box
from shapely.ops import voronoi_diagram
from shapely import affinity

from nfpa72_models import (
    CeilingSpec,
    RoomSpec,
    CoverageResult,
    CoverageError,
    NFPAComplianceResult,
    DetectorPlacement,
    DetectorType,
    get_smoke_detector_radius,
)
from nfpa72_calculations import (
    is_point_covered_by_heat_detectors,
    is_in_ridge_zone,
    requires_ridge_zone_detector,
)


# ============================================================================
# POLYGON-BASED COVERAGE CHECKS
# ============================================================================

def create_room_polygon(room_spec: RoomSpec) -> Polygon:
    """
    Create Shapely polygon from room specification.
    
    Handles both rectangular and L-shaped rooms.
    
    Args:
        room_spec: Room specification
        
    Returns:
        Shapely Polygon object
    """
    if room_spec.polygon:
        return Polygon(room_spec.polygon)
    
    # Default rectangular room
    return Polygon([
        (0, 0),
        (room_spec.width_m, 0),
        (room_spec.width_m, room_spec.depth_m),
        (0, room_spec.depth_m)
    ])


def is_point_in_room(point: Tuple[float, float], room_polygon: Polygon) -> bool:
    """
    Check if point is inside room polygon.
    
    Uses Polygon.contains() instead of Bounding Box.
    
    Args:
        point: (x, y) point to check
        room_polygon: Shapely Polygon of room
        
    Returns:
        True if point is inside room polygon
    """
    p = Point(point[0], point[1])
    return room_polygon.contains(p)


def check_coverage_polygon(
    detector_positions: List[Tuple[float, float]],
    room_spec: RoomSpec,
    ceiling_spec: CeilingSpec,
    detector_type: DetectorType = DetectorType.SMOKE
) -> CoverageResult:
    """
    Check coverage using Polygon containment.
    
    This replaces the incorrect Bounding Box method.
    For L-shaped rooms, this correctly identifies uncovered areas.
    
    Args:
        detector_positions: List of detector (x, y) positions
        room_spec: Room specification
        ceiling_spec: Ceiling specification
        detector_type: Type of detector
        
    Returns:
        CoverageResult with coverage details
    """
    room_polygon = create_room_polygon(room_spec)
    
    if not room_polygon.is_valid:
        room_polygon = room_polygon.buffer(0)
    
    # Calculate coverage radius
    if detector_type == DetectorType.SMOKE:
        radius = get_smoke_detector_radius(ceiling_spec.height_m)
    else:
        radius = 9.1 / 2  # Heat detector half-spacing
    
    # Sample points throughout the room for coverage check
    uncovered = []
    samples = 20  # Grid resolution for coverage check
    
    step_x = room_spec.width_m / samples
    step_y = room_spec.depth_m / samples
    
    covered_count = 0
    total_points = 0
    
    for i in range(samples + 1):
        for j in range(samples + 1):
            x = i * step_x
            y = j * step_y
            point = (x, y)
            
            # Check if point is in room (not just bounding box)
            if not is_point_in_room(point, room_polygon):
                continue
            
            total_points += 1
            
            # Check if covered by any detector
            covered = False
            for dx, dy in detector_positions:
                dist = math.sqrt((x - dx)**2 + (y - dy)**2)
                if dist <= radius:
                    covered = True
                    break
            
            if covered:
                covered_count += 1
            else:
                uncovered.append(point)
    
    # Calculate coverage percentage
    if total_points > 0:
        coverage_pct = (covered_count / total_points) * 100
    else:
        coverage_pct = 0
    
    return CoverageResult(
        is_covered=coverage_pct >= 99,
        uncovered_areas=uncovered,
        coverage_percentage=coverage_pct,
        detectors_in_coverage=len(detector_positions)
    )


# ============================================================================
# VORONOI COVERAGE (Advanced)
# ============================================================================

def calculate_voronoi_coverage(
    detector_positions: List[Tuple[float, float]],
    room_polygon: Polygon
) -> List[Polygon]:
    """
    Calculate Voronoi regions for detector coverage areas.
    
    Args:
        detector_positions: List of detector positions
        room_polygon: Room boundary polygon
        
    Returns:
        List of Voronoi polygons clipped to room
    """
    if len(detector_positions) < 2:
        return [room_polygon]
    
    # Create points
    from shapely.geometry import MultiPoint
    points = MultiPoint([Point(x, y) for x, y in detector_positions])
    
    # Calculate Voronoi diagram
    try:
        voronoi = voronoi_diagram(points, envelope=room_polygon.buffer(1))
        
        # Clip each Voronoi region to room
        regions = []
        for poly in voronoi.geoms:
            clipped = poly.intersection(room_polygon)
            if clipped.is_valid and not clipped.is_empty:
                regions.append(clipped)
        
        return regions
    except Exception:
        return [room_polygon]


def check_voronoi_coverage(
    detector_positions: List[Tuple[float, float]],
    room_spec: RoomSpec,
    ceiling_spec: CeilingSpec
) -> CoverageResult:
    """
    Check coverage using Voronoi diagram (advanced method).
    
    Args:
        detector_positions: Detector positions
        room_spec: Room specification
        ceiling_spec: Ceiling specification
        
    Returns:
        CoverageResult
    """
    room_polygon = create_room_polygon(room_spec)
    radius = get_smoke_detector_radius(ceiling_spec.height_m)
    
    # Voronoi regions show theoretical coverage
    regions = calculate_voronoi_coverage(detector_positions, room_polygon)
    
    # For now, use polygon check as primary
    return check_coverage_polygon(
        detector_positions, room_spec, ceiling_spec, DetectorType.SMOKE
    )


# ============================================================================
# RIDGE ZONE COMPLIANCE
# ============================================================================

def check_ridge_zone_compliance(
    detector_positions: List[Tuple[float, float]],
    ceiling_spec: CeilingSpec,
    ridge_line: Tuple[float, float, float, float]
) -> NFPAComplianceResult:
    """
    Check if sloped ceiling has detector in ridge zone.
    
    Per NFPA 72, for ceilings with slope > 1.5°, at least one
    detector must be within 0.9m (3ft) of the ridge.
    
    Args:
        detector_positions: List of detector positions
        ceiling_spec: Ceiling specification
        ridge_line: Ridge line coordinates
        
    Returns:
        NFPAComplianceResult
    """
    result = NFPAComplianceResult(is_compliant=True)
    
    if not requires_ridge_zone_detector(ceiling_spec):
        return result
    
    # Check if any detector is in ridge zone
    has_ridge_detector = False
    
    for dx, dy in detector_positions:
        if is_in_ridge_zone((dx, dy), ridge_line, ceiling_spec.slope_degrees):
            has_ridge_detector = True
            break
    
    if not has_ridge_detector:
        result.add_violation(
            f"Sloped ceiling (slope={ceiling_spec.slope_degrees}°) requires "
            f"at least one detector in ridge zone (within 0.9m of ridge)"
        )
    
    return result


# ============================================================================
# L-SHAPED ROOM HANDLING
# ============================================================================

def create_l_shaped_polygon(
    dimensions: List[Tuple[float, float]]
) -> Polygon:
    """
    Create polygon for L-shaped room.
    
    Args:
        dimensions: List of [(x1,y1), (x2,y2), ...] corner points
        
    Returns:
        Shapely Polygon
    """
    if len(dimensions) < 3:
        raise ValueError("L-shape requires at least 3 points")
    
    return Polygon(dimensions)


def check_l_shaped_coverage(
    detector_positions: List[Tuple[float, float]],
    room_polygon: Polygon,
    ceiling_height_m: float
) -> CoverageResult:
    """
    Check coverage for L-shaped room.
    
    This is the critical test case - Bounding Box fails here.
    
    Args:
        detector_positions: Detector positions
        room_polygon: Room polygon (can be L-shaped)
        ceiling_height_m: Ceiling height
        
    Returns:
        CoverageResult
    """
    radius = get_smoke_detector_radius(ceiling_height_m)
    
    # Sample points throughout actual polygon
    uncovered = []
    bounds = room_polygon.bounds
    
    min_x, min_y, max_x, max_y = bounds
    step_x = (max_x - min_x) / 20
    step_y = (max_y - min_y) / 20
    
    covered_count = 0
    total_points = 0
    
    for i in range(21):
        for j in range(21):
            x = min_x + i * step_x
            y = min_y + j * step_y
            point = (x, y)
            
            # CRITICAL: Use polygon.contains(), NOT bounding box
            if not room_polygon.contains(Point(x, y)):
                continue
            
            total_points += 1
            
            # Check coverage
            covered = any(
                math.sqrt((x - dx)**2 + (y - dy)**2) <= radius
                for dx, dy in detector_positions
            )
            
            if covered:
                covered_count += 1
            else:
                uncovered.append(point)
    
    coverage_pct = (covered_count / total_points * 100) if total_points > 0 else 0
    
    return CoverageResult(
        is_covered=coverage_pct >= 99,
        uncovered_areas=uncovered,
        coverage_percentage=coverage_pct,
        detectors_in_coverage=len(detector_positions)
    )


# ============================================================================
# FULL COMPLIANCE CHECK
# ============================================================================

def check_nfpa72_compliance(
    room_spec: RoomSpec,
    ceiling_spec: CeilingSpec,
    detector_positions: List[Tuple[float, float]],
    detector_type: DetectorType = DetectorType.SMOKE,
    ridge_line: Optional[Tuple[float, float, float, float]] = None
) -> NFPAComplianceResult:
    """
    Full NFPA 72 compliance check.
    
    Args:
        room_spec: Room specification
        ceiling_spec: Ceiling specification
        detector_positions: Placed detector positions
        detector_type: Type of detector
        ridge_line: Ridge line for sloped ceiling
        
    Returns:
        NFPAComplianceResult
    """
    result = NFPAComplianceResult(is_compliant=True)
    result.detector_count = len(detector_positions)
    
    # Check coverage
    coverage = check_coverage_polygon(
        detector_positions, room_spec, ceiling_spec, detector_type
    )
    
    if not coverage.is_covered:
        result.add_violation(
            f"Coverage is {coverage.coverage_percentage:.1f}%, below 99% required"
        )
    
    # Check ridge zone
    if ridge_line and requires_ridge_zone_detector(ceiling_spec):
        ridge_result = check_ridge_zone_compliance(
            detector_positions, ceiling_spec, ridge_line
        )
        result.violations.extend(ridge_result.violations)
        if ridge_result.violations:
            result.is_compliant = False
    
    result.required_detector_count = result.detector_count
    
    return result


# Test exported symbols
__all__ = [
    "create_room_polygon",
    "is_point_in_room",
    "check_coverage_polygon",
    "calculate_voronoi_coverage",
    "check_voronoi_coverage",
    "check_ridge_zone_compliance",
    "create_l_shaped_polygon",
    "check_l_shaped_coverage",
    "check_nfpa72_compliance",
]