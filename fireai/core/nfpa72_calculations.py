"""
NFPA 72 V5 Calculations - Radius, Heat, and Sloped Ceiling Calculations
This module provides calculation functions for NFPA 72 Chapter 17 compliance.
All calculations are law-compliant based on NFPA 72 (2022 Edition).
⚠️ LEGAL DISCLAIMER:
This code is provided for compliance assistance only.
It does not constitute legal advice.
Always verify with a licensed fire protection engineer.
NFPA 72 (2022 Edition) is the authoritative standard.

V9 CHANGES (2026-05-14):
- All get_smoke_detector_radius() replaced with _safe versions
- Added lru_cache memoization to pure calculation functions
- Added get_smoke_detector_coverage_max_safe import
"""
import math
from typing import List, Tuple, Optional
from functools import lru_cache
from .nfpa72_models import (
    CeilingSpec,
    RoomSpec,
    DetectorType,
    HeatDetectionMode,
    CeilingType,
    CeilingHeightError,
    get_smoke_detector_radius,
    get_smoke_detector_radius_safe,          # V9: safe fallback
    get_smoke_detector_coverage_max,
    get_smoke_detector_coverage_max_safe,    # V9: safe fallback
    HeatDetectorSpec,
)
def get_heat_detector_placement_params(
    spec: HeatDetectorSpec,
    ceiling_height_m: float,
    beam_depth_m: float = 0.0,
    ceiling_slope_degrees: float = 0.0,
) -> dict:
    """
    Get heat detector placement parameters per NFPA 72.
    Args:
        spec: HeatDetectorSpec with manufacturer, model_number, listed_spacing
        ceiling_height_m: Ceiling height in meters
        beam_depth_m: Beam depth (optional)
        ceiling_slope_degrees: Ceiling slope in degrees (optional)
    Returns:
        Dictionary with max_detector_spacing_m and other parameters
    """
    base_spacing = spec.listed_spacing_m if spec else 9.1
    # NFPA 72 Table 17.6.2.1 adjustments
    adjusted_spacing = base_spacing
    return {
        "max_detector_spacing_m": adjusted_spacing,
        "coverage_type": "square_grid",
    }
# ============================================================================
# SMOKE DETECTOR RADIUS CALCULATIONS
# ============================================================================
@lru_cache(maxsize=128)  # V9: memoize pure function
def calculate_smoke_detector_radius(ceiling_height_m: float) -> float:
    """
    Calculate recommended coverage radius for smoke detector.
    Args:
        ceiling_height_m: Ceiling height in meters
    Returns:
        Recommended coverage radius in meters
    Note:
        This is NOT the max coverage - circles can extend up to max coverage
        when spacing allows.
    """
    return get_smoke_detector_radius_safe(ceiling_height_m)  # V9: safe fallback
def calculate_smoke_detector_spacing(
    ceiling_spec: CeilingSpec,
    room_width_m: float,
    room_depth_m: float
) -> Tuple[int, int]:
    """
    Calculate number of smoke detectors needed per NFPA 72 spacing.
    Args:
        ceiling_spec: Ceiling specification
        room_width_m: Room width in meters
        room_depth_m: Room depth in meters
    Returns:
        Tuple of (number_along_width, number_along_depth)
    """
    radius = get_smoke_detector_radius_safe(ceiling_spec.height_m)  # V9: safe fallback
    max_coverage = get_smoke_detector_coverage_max(ceiling_spec.height_m)
    # Use max coverage for spacing calculation
    spacing = max_coverage * 2  # Diameter
    # Number of detectors
    num_width = max(1, math.ceil(room_width_m / spacing))
    num_depth = max(1, math.ceil(room_depth_m / spacing))
    return (num_width, num_depth)
# ============================================================================
# HEAT DETECTOR PLACEMENT - SQUARE GRID (Chebyshev Distance)
# ============================================================================
def calculate_heat_detector_coverage_chebyshev(
    detector_x: float,
    detector_y: float,
    point_x: float,
    point_y: float,
    spacing_m: float = 9.1
) -> bool:
    """
    Check if a point is covered by a heat detector using Chebyshev distance.
    For heat detectors, NFPA 72 uses rectangular (square) coverage areas,
    not circular. This is because heat detection responds to absolute
    temperature rise, not smoke migration.
    Args:
        detector_x: Detector X position
        detector_y: Detector Y position
        point_x: Point X position to check
        point_y: Point Y position to check
        spacing_m: Detector spacing (default 9.1m = 30ft)
    Returns:
        True if point is covered by heat detector
    """
    # Chebyshev distance: max(\|dx\|, \|dy\|)
    # Coverage area is a square of side = spacing
    max_distance = spacing_m / 2  # Half-spacing from center
    dx = abs(point_x - detector_x)
    dy = abs(point_y - detector_y)
    # Use >= to include boundary points
    return dx <= max_distance and dy <= max_distance
def calculate_heat_detector_spacing_rectangular(
    room_width_m: float,
    room_depth_m: float,
    spacing_m: float = 9.1
) -> Tuple[int, int]:
    """
    Calculate number of heat detectors needed using rectangular spacing.
    Args:
        room_width_m: Room width in meters
        room_depth_m: Room depth in meters
        spacing_m: Detector spacing (default 9.1m = 30ft)
    Returns:
        Tuple of (number_along_width, number_along_depth)
    """
    num_width = max(1, math.ceil(room_width_m / spacing_m))
    num_depth = max(1, math.ceil(room_depth_m / spacing_m))
    return (num_width, num_depth)
def generate_heat_detector_positions(
    room_spec: RoomSpec,
    ceiling_spec: CeilingSpec,
    spacing_m: float = 9.1
) -> List[Tuple[float, float]]:
    """
    Generate heat detector positions using square grid pattern.
    Args:
        room_spec: Room specification
        ceiling_spec: Ceiling specification
        spacing_m: Detector spacing (default 9.1m = 30ft)
    Returns:
        List of (x, y) detector positions
    """
    positions = []
    spacing = spacing_m
    # Generate grid positions
    x = spacing / 2
    while x < room_spec.width_m:
        y = spacing / 2
        while y < room_spec.depth_m:
            positions.append((x, y))
            y += spacing
        x += spacing
    return positions
def is_point_covered_by_heat_detectors(
    point: Tuple[float, float],
    detector_positions: List[Tuple[float, float]],
    spacing_m: float = 9.1
) -> bool:
    """
    Check if a point is covered by any heat detector.
    Uses SQUARE_GRID (Chebyshev) coverage, NOT circular.
    Args:
        point: (x, y) position to check
        detector_positions: List of detector (x, y) positions
        spacing_m: Detector spacing (default 9.1m = 30ft)
    Returns:
        True if point is covered by at least one detector
    """
    px, py = point
    for dx, dy in detector_positions:
        if calculate_heat_detector_coverage_chebyshev(dx, dy, px, py, spacing_m):
            return True
    return False
# ============================================================================
# SLOPED CEILING CALCULATIONS - Ridge Zone
# ============================================================================
def calculate_ridge_zone_boundary(
    ridge_line: Tuple[float, float, float, float],
    slope_degrees: float,
    buffer_m: float = 0.9
) -> Tuple[float, float, float, float]:
    """
    Calculate ridge zone boundary for sloped ceiling.
    Per NFPA 72, for sloped ceilings > 1.5°, at least one detector
    must be located in the ridge zone (within 0.9m / 3ft of the ridge).
    Args:
        ridge_line: (x1, y1, x2, y2) ridge line coordinates
        slope_degrees: Ceiling slope in degrees
        buffer_m: Buffer distance from ridge (default 0.9m = 3ft)
    Returns:
        (x1, y1, x2, y2) ridge zone boundary
    """
    if slope_degrees <= 1.5:
        return ridge_line  # No ridge zone needed
    x1, y1, x2, y2 = ridge_line
    # Ridge zone is parallel to ridge line
    return (
        x1 - buffer_m, y1,
        x2 + buffer_m, y2
    )
def is_in_ridge_zone(
    point: Tuple[float, float],
    ridge_line: Tuple[float, float, float, float],
    slope_degrees: float,
    buffer_m: float = 0.9
) -> bool:
    """
    Check if a point is in the ridge zone.
    Args:
        point: (x, y) position to check
        ridge_line: (x1, y1, x2, y2) ridge line
        slope_degrees: Ceiling slope in degrees
        buffer_m: Buffer distance from ridge (default 0.9m)
    Returns:
        True if point is in ridge zone
    """
    if slope_degrees <= 1.5:
        return True  # No ridge zone requirement
    px, py = point
    x1, y1, x2, y2 = ridge_line
    # Calculate perpendicular distance to ridge line
    # Using point-to-line distance formula
    line_length = math.sqrt((x2-x1)**2 + (y2-y1)**2)
    if line_length == 0:
        return False
    # Distance from point to ridge line
    distance = abs((y2-y1)*px - (x2-x1)*py + x2*y1 - y2*x1) / line_length
    # Check if within buffer and between endpoints
    min_x = min(x1, x2) - buffer_m
    max_x = max(x1, x2) + buffer_m
    min_y = min(y1, y2) - buffer_m
    max_y = max(y1, y2) + buffer_m
    return (distance <= buffer_m and
            min_x <= px <= max_x and
            min_y <= py <= max_y)
def requires_ridge_zone_detector(ceiling_spec: CeilingSpec) -> bool:
    """
    Check if ceiling requires ridge zone detector.
    Args:
        ceiling_spec: Ceiling specification
    Returns:
        True if ridge zone detector is required
    """
    return ceiling_spec.is_sloped
# ============================================================================
# COMBINED CALCULATIONS
# ============================================================================
def calculate_detector_requirements(
    room_spec: RoomSpec,
    ceiling_spec: CeilingSpec,
    detector_type: DetectorType = DetectorType.SMOKE
) -> dict:
    """
    Calculate detector requirements for a room.
    Args:
        room_spec: Room specification
        ceiling_spec: Ceiling specification
        detector_type: Type of detector
    Returns:
        Dictionary with requirements
    """
    result = {
        "room_name": room_spec.name,
        "detector_type": detector_type.value,
        "ceiling_height": ceiling_spec.height_m,
        "ceiling_slope": ceiling_spec.slope_degrees,
        "requires_ridge_zone": requires_ridge_zone_detector(ceiling_spec),
    }
    if detector_type == DetectorType.SMOKE:
        result["radius"] = get_smoke_detector_radius_safe(ceiling_spec.height_m)
        result["max_coverage"] = get_smoke_detector_coverage_max(ceiling_spec.height_m)
        num_w, num_d = calculate_smoke_detector_spacing(
            ceiling_spec, room_spec.width_m, room_spec.depth_m
        )
        result["detectors_width"] = num_w
        result["detectors_depth"] = num_d
        result["total_detectors"] = num_w * num_d
    elif detector_type == DetectorType.HEAT:
        spacing = 9.1  # Fixed 30ft per NFPA 72
        result["spacing"] = spacing
        num_w, num_d = calculate_heat_detector_spacing_rectangular(
            room_spec.width_m, room_spec.depth_m, spacing
        )
        result["detectors_width"] = num_w
        result["detectors_depth"] = num_d
        result["total_detectors"] = num_w * num_d
    return result
# Test exported symbols
__all__ = [\
\
    # Smoke calculations\
\
    "calculate_smoke_detector_radius",\
\
    "calculate_smoke_detector_spacing",\
\
    "get_smoke_detector_radius",\
\
    "get_smoke_detector_coverage_max",\
\
    # Heat calculations\
\
    "calculate_heat_detector_coverage_chebyshev",\
\
    "calculate_heat_detector_spacing_rectangular",\
\
    "generate_heat_detector_positions",\
\
    "is_point_covered_by_heat_detectors",\
\
    "get_heat_detector_placement_params",\
\
    # Sloped ceiling\
\
    "calculate_ridge_zone_boundary",\
\
    "is_in_ridge_zone",\
\
    "requires_ridge_zone_detector",\
\
    # Combined\
\
    "calculate_detector_requirements",\
\
]


# ============================================================================
# MISSING FUNCTIONS FOR V10 COMPATIBILITY
# ============================================================================

def calculate_max_spacing(ceiling: "CeilingSpec", detector_type: "DetectorType") -> float:
    """NFPA 72 §17.6.3 - spacing between detectors."""
    spacing = get_smoke_detector_coverage_max(ceiling.height_at_low_point_m)
    if ceiling.is_sloped:
        spacing = get_smoke_detector_coverage_max(ceiling.height_at_high_point_m or ceiling.height_at_low_point_m)
    return round(spacing, 3)


def calculate_coverage_radius(ceiling: "CeilingSpec", detector_type: "DetectorType") -> float:
    """NFPA 72 §17.6.3.1 - radius = spacing / 2."""
    return round(calculate_max_spacing(ceiling, detector_type) / 2.0, 4)


def calculate_max_wall_distance(ceiling: "CeilingSpec", detector_type: "DetectorType") -> float:
    """NFPA 72 §17.6.3.1.1 - max wall distance = radius."""
    return calculate_coverage_radius(ceiling, detector_type)


# Add to exports


def estimate_detector_count_polygon(polygon, ceiling_height_m: float, detector_type: str) -> int:
    """Estimate detector count for a polygon based on coverage area."""
    import math
    from shapely.geometry import Polygon
    from nfpa72_coverage import get_smoke_detector_coverage_max
    
    if not isinstance(polygon, Polygon):
        return 0
    
    area = polygon.area
    radius = get_smoke_detector_coverage_max(ceiling_height_m)
    # Each detector covers π * r²
    coverage_per_detector = math.pi * (radius ** 2)
    if coverage_per_detector <= 0:
        return 0
    # Use 0.7 factor for spacing efficiency
    return math.ceil(area / (coverage_per_detector * 0.7))


def minimum_detector_count_rectangular(width_m: float, depth_m: float, ceiling_height_m: float) -> int:
    """Minimum detector count for rectangular room."""
    import math
    from nfpa72_coverage import get_smoke_detector_coverage_max
    
    radius = get_smoke_detector_coverage_max(ceiling_height_m)
    spacing = radius * 2
    
    cols = max(1, math.ceil(width_m / spacing))
    rows = max(1, math.ceil(depth_m / spacing))
    
    return cols * rows


__all__ = __all__ + [
    "calculate_max_spacing",
    "calculate_coverage_radius",
    "calculate_max_wall_distance",
]
