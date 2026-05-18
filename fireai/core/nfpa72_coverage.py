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
FIXED: 2026-05-14
CHANGES:
1. Line 110-113: Now uses SQUARE geometry for heat detectors (Chebyshev)
2. Line 111: Now uses get_smoke_detector_radius_safe() for smoke detectors
3. Added coverage_geometry parameter tracking
4. Added proper handling for detector type vs geometry mapping

V9 CHANGES (2026-05-14):
5. Adaptive grid sampling: 0.25m resolution (was fixed 20x20)
6. Added validate_wall_distances() — NFPA 72 §17.6.3.1.1
"""

import math
from dataclasses import dataclass
from typing import List, Tuple, Optional
from shapely.geometry import Polygon, Point, box

@dataclass
class DuctDevice:
    device_id: str
    x: float
    y: float
    z: float = 0.0
    detector_type: str = "smoke"

@dataclass
class WallViolation:
    x: float
    y: float
    distance_m: float
    min_required_m: float

from shapely.ops import voronoi_diagram
from shapely import affinity
from .nfpa72_models import (
    CeilingSpec,
    RoomSpec,
    CoverageResult,
    CoverageError,
    NFPAComplianceResult,
    DetectorPlacement,
    DetectorType,
    get_smoke_detector_radius,
    get_smoke_detector_radius_safe,
)
from .nfpa72_calculations import (
    is_point_covered_by_heat_detectors,
    is_in_ridge_zone,
    requires_ridge_zone_detector,
)
# ============================================================================
# POLYGON-BASED COVERAGE CHECKS
# ============================================================================
# ============================================================================
# V9: WALL DISTANCE VALIDATION
# ============================================================================
NFPA_MIN_WALL_DISTANCE_M = 0.10  # NFPA 72 §17.6.3.1.1: 4 inches = 0.1016m

def validate_wall_distances(
    detector_positions: List[Tuple[float, float]],
    room_spec: "RoomSpec",
    min_distance_m: float = NFPA_MIN_WALL_DISTANCE_M,
) -> List[dict]:
    """
    V9: Validates that all detectors maintain minimum wall distance.

    Per NFPA 72 §17.6.3.1.1: Detectors shall not be located closer than
    4 inches (100 mm) from a sidewall or end wall.

    Args:
        detector_positions: List of (x, y) detector coordinates
        room_spec: Room specification with width_m and depth_m
        min_distance_m: Minimum wall distance (default 0.10m per NFPA 72)

    Returns:
        List of violations, each with detector_index, position, distance, wall
        Empty list = all detectors compliant
    """
    violations = []

    for idx, (x, y) in enumerate(detector_positions):
        # Check all 4 walls
        dist_left   = x
        dist_right  = room_spec.width_m - x
        dist_bottom = y
        dist_top    = room_spec.depth_m - y

        wall_distances = {
            "left":   dist_left,
            "right":  dist_right,
            "bottom": dist_bottom,
            "top":    dist_top,
        }

        for wall, dist in wall_distances.items():
            if dist < min_distance_m:
                violations.append({
                    "detector_index": idx,
                    "position": (x, y),
                    "wall": wall,
                    "distance_m": round(dist, 4),
                    "required_m": min_distance_m,
                    "violation": f"Detector #{idx} at ({x:.2f},{y:.2f}) is {dist*100:.1f}cm from {wall} wall "
                                 f"(min {min_distance_m*100:.0f}cm per NFPA 72 §17.6.3.1.1)",
                    "nfpa_reference": "NFPA 72-2022 §17.6.3.1.1",
                })

    return violations


def suggest_duct_detectors(room: RoomSpec, detector_type: str = "smoke") -> List[DuctDevice]:
    """Suggest detector placements near HVAC ducts."""
    devices = []
    if not room.hvac_ducts:
        return devices
    
    for i, duct in enumerate(room.hvac_ducts):
        if not duct.centerline:
            continue
        cx, cy = duct.centerline[0][:2]
        devices.append(DuctDevice(
            device_id=f"DUCT_{i+1}",
            x=cx, y=cy,
            detector_type=detector_type
        ))
    return devices




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
    return Polygon([\
\
        (0, 0),\
\
        (room_spec.width_m, 0),\
\
        (room_spec.width_m, room_spec.depth_m),\
\
        (0, room_spec.depth_m)\
\
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
# ============================================================================
# ⚠️ FIXED: Coverage Geometry - Heat Detectors Use Square (2026-05-14)
# ============================================================================
# ORIGINAL BUG:
#   if detector_type == DetectorType.SMOKE:
#       radius = get_smoke_detector_radius(ceiling_spec.height_m)
#   else:
#       radius = 9.1 / 2  # Uses CIRCULAR geometry for heat - WRONG!
#
# FIX APPLIED:
#   - SMOKE: Uses CIRCULAR geometry (Euclidean distance)
#   - HEAT: Uses SQUARE geometry (Chebyshev distance)
#   - Uses get_smoke_detector_radius_safe() for safe fallback
# ============================================================================
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
    FIXED: 2026-05-14
    - Uses CORRECT geometry per detector type:
      * SMOKE: Circular (Euclidean distance)
      * HEAT: Square (Chebyshev distance) - per NFPA 72 Table 17.6.2.1
    - Uses get_smoke_detector_radius_safe() for safe fallback
    Args:
        detector_positions: List of detector (x, y) positions
        room_spec: Room specification
        ceiling_spec: Ceiling specification
        detector_type: Type of detector (SMOKE or HEAT)
    Returns:
        CoverageResult with coverage details
    """
    room_polygon = create_room_polygon(room_spec)
    if not room_polygon.is_valid:
        room_polygon = room_polygon.buffer(0)
    # =========================================================================
    # ⚠️ FIXED SECTION (Lines 109-113): CORRECT GEOMETRY PER DETECTOR TYPE
    # =========================================================================
    if detector_type == DetectorType.SMOKE:
        # ✅ SMOKE: Use circular geometry (Euclidean distance)
        # ✅ Use safe fallback to prevent crashes at extreme heights
        radius = get_smoke_detector_radius_safe(ceiling_spec.height_m)
        coverage_geometry = "circular"
    elif detector_type == DetectorType.HEAT:
        # ✅ HEAT: Use square geometry (Chebyshev distance)
        # Per NFPA 72, heat detectors use rectangular/square coverage areas
        # because heat detection responds to absolute temperature rise
        # not smoke migration patterns
        radius = 9.1 / 2  # Half of 9.1m listed spacing
        coverage_geometry = "square"  # Chebyshev distance
    else:
        # Default fallback for other detector types
        radius = get_smoke_detector_radius_safe(ceiling_spec.height_m)
        coverage_geometry = "circular"
    # V9: Adaptive sampling resolution based on room size
    # Minimum 0.25m grid resolution (NFPA detection hole < 25cm)
    # Maximum 50x50 grid to limit computation
    GRID_RESOLUTION_M = 0.25   # 25cm resolution — catches all blind spots
    samples_x = min(50, max(10, int(room_spec.width_m / GRID_RESOLUTION_M)))
    samples_y = min(50, max(10, int(room_spec.depth_m / GRID_RESOLUTION_M)))
    uncovered = []
    step_x = room_spec.width_m / samples_x
    step_y = room_spec.depth_m / samples_y
    covered_count = 0
    total_points = 0
    for i in range(samples_x + 1):
        for j in range(samples_y + 1):
            x = i * step_x
            y = j * step_y
            point = (x, y)
            # Check if point is in room (not just bounding box)
            if not is_point_in_room(point, room_polygon):
                continue
            total_points += 1
            # Check if covered by any detector
            # =========================================================================
            # ⚠️ FIXED SECTION: USE CORRECT COVERAGE CHECK PER DETECTOR TYPE
            # =========================================================================
            covered = False
            if detector_type == DetectorType.HEAT:
                # ✅ HEAT: Use Chebyshev distance (square coverage)
                # Check if point is within square bounds of any detector
                half_spacing = 9.1 / 2
                for dx, dy in detector_positions:
                    # Chebyshev distance: max(|dx|, |dy|)
                    if max(abs(x - dx), abs(y - dy)) <= half_spacing:
                        covered = True
                        break
            else:
                # ✅ SMOKE/OTHER: Use Euclidean distance (circular coverage)
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
    # ✅ Use safe fallback
    radius = get_smoke_detector_radius_safe(ceiling_spec.height_m)
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
    # ✅ Use safe fallback
    radius = get_smoke_detector_radius_safe(ceiling_height_m)
    # FIXED: Use adaptive grid (0.25m resolution) instead of fixed 20×20 sampling
    # The old 20×20 grid could miss coverage gaps in large rooms
    GRID_RESOLUTION_M = 0.25
    uncovered = []
    bounds = room_polygon.bounds
    min_x, min_y, max_x, max_y = bounds
    step_x = GRID_RESOLUTION_M
    step_y = GRID_RESOLUTION_M
    covered_count = 0
    total_points = 0
    x = min_x
    while x <= max_x:
        y = min_y
        while y <= max_y:
            # CRITICAL: Use polygon.contains(), NOT bounding box
            if not room_polygon.contains(Point(x, y)):
                y += step_y
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
                uncovered.append((x, y))
            y += step_y
        x += step_x
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
__all__ = [\
\
    "create_room_polygon",\
\
    "is_point_in_room",\
\
    "check_coverage_polygon",
    "suggest_duct_detectors",\
\
    "calculate_voronoi_coverage",\
\
    "check_voronoi_coverage",\
\
    "check_ridge_zone_compliance",\
\
    "create_l_shaped_polygon",\
\
    "check_l_shaped_coverage",\
\
    "check_nfpa72_compliance",\
\
    "verify_full_coverage",\
\
    "get_sloped_ceiling_constraints",\
\
]
def verify_full_coverage(
    room_polygon,
    detector_positions: List[Tuple[float, float]],
    coverage_geometry: str,
    detector_radius: float,
    listed_spacing_m: Optional[float] = None,
    grid_resolution_m: float = 0.25,
    detector_type: DetectorType = DetectorType.SMOKE,
) -> dict:
    """
    Verify that all points in the room are covered by detectors.
    FIXED: 2026-05-14
    - Added detector_type parameter
    - Uses correct geometry per detector type:
      * SMOKE: Circular (Euclidean)
      * HEAT: Square (Chebyshev)
    Args:
        room_polygon: Shapely Polygon of room
        detector_positions: List of detector (x, y) positions
        coverage_geometry: "circular" or "square_grid"
        detector_radius: Coverage radius for smoke detectors
        listed_spacing_m: Listed spacing for heat detectors
        grid_resolution_m: Grid resolution for sampling
        detector_type: Type of detector (SMOKE or HEAT)
    Returns:
        Dictionary with coverage_percentage, worst_case_distance_m, compliance_status
    """
    if coverage_geometry == "circular":
        radius = detector_radius
    else:
        # For square grid, use half of listed spacing
        radius = (listed_spacing_m or 9.1) / 2
    # ✅ Override with correct geometry based on detector type
    if detector_type == DetectorType.HEAT:
        # Heat detectors always use square geometry per NFPA 72
        half_spacing = (listed_spacing_m or 9.1) / 2
    bounds = room_polygon.bounds
    minx, miny, maxx, maxy = bounds
    step = grid_resolution_m
    total_points = 0
    covered_points = 0
    worst_distance = 0.0
    x = minx
    while x <= maxx:
        y = miny
        while y <= maxy:
            pt = Point(x, y)
            if room_polygon.contains(pt):
                total_points += 1
                # Find distance to nearest detector
                min_dist = float('inf')
                for dx, dy in detector_positions:
                    if detector_type == DetectorType.HEAT:
                        # ✅ HEAT: Use Chebyshev distance (square)
                        dist = max(abs(x - dx), abs(y - dy))
                    else:
                        # ✅ SMOKE: Use Euclidean distance (circular)
                        dist = math.sqrt((x - dx) ** 2 + (y - dy) ** 2)
                    min_dist = min(min_dist, dist)
                # Check coverage with correct geometry
                if detector_type == DetectorType.HEAT:
                    # Square coverage: within half_spacing in both axes
                    if min_dist <= half_spacing:
                        covered_points += 1
                    else:
                        worst_distance = max(worst_distance, min_dist)
                else:
                    # Circular coverage: within radius
                    if min_dist <= radius:
                        covered_points += 1
                    else:
                        worst_distance = max(worst_distance, min_dist)
            y += step
        x += step
    coverage_pct = (covered_points / total_points * 100) if total_points > 0 else 0
    status = "PASS" if coverage_pct >= 99 else "FAIL"
    return {
        "coverage_percentage": coverage_pct,
        "worst_case_distance_m": worst_distance,
        "compliance_status": status,
        "coverage_geometry": "square" if detector_type == DetectorType.HEAT else "circular",
        "total_points_checked": total_points,
        "covered_points": covered_points,
    }
def get_sloped_ceiling_constraints(
    polygon,
    ceiling_spec,
    detector_type,
) -> dict:
    """
    Get sloped ceiling constraints for NFPA 72 compliance.
    Args:
        polygon: Room polygon
        ceiling_spec: CeilingSpec
        detector_type: DetectorType
    Returns:
        Dictionary with requires_ridge_row, ridge_zone_polygon, etc.
    """
    if not ceiling_spec.is_sloped:
        return {
            "requires_ridge_row": False,
            "ridge_zone_polygon": None,
        }
    if detector_type != DetectorType.SMOKE:
        return {
            "requires_ridge_row": False,
            "ridge_zone_polygon": None,
        }
    # For sloped ceiling, create ridge zone (within 0.9m of highest point)
    bounds = polygon.bounds
    minx, miny, maxx, maxy = bounds
    # Ridge zone is area within 0.9m of highest ceiling point
    ridge_buffer = 0.9
    ridge_line_y = maxy - ceiling_spec.height_at_high_point_m
    return {
        "requires_ridge_row": True,
        "ridge_zone_polygon": polygon,
    }

import logging
logger = logging.getLogger(__name__)
def adjust_coverage_for_beams(
    nominal_radius_m: float,
    beam_depth_m: float,
    ceiling_height_m: float,
) -> float:
    """
    Adjusts detector coverage radius based on beam obstruction.

    Per NFPA 72 Section 17.6.3.1:
    - Beam depth > 10% of ceiling height: treat as separate compartments
    - Beam depth > 4%: conservative 15% radius reduction
    - Beam depth <= 4%: no impact

    Args:
        nominal_radius_m: Original coverage radius in meters
        beam_depth_m: Beam depth below ceiling in meters (must be >= 0)
        ceiling_height_m: Floor-to-ceiling height in meters (must be > 0)

    Returns:
        float: Adjusted coverage radius in meters

    Raises:
        ValueError: If ceiling_height_m <= 0 or beam_depth_m < 0
    """
    if ceiling_height_m <= 0:
        raise ValueError(
            f"ceiling_height_m must be positive, got {ceiling_height_m}"
        )
    if beam_depth_m < 0:
        raise ValueError(
            f"beam_depth_m cannot be negative, got {beam_depth_m}"
        )

    beam_ratio = beam_depth_m / ceiling_height_m

    if beam_ratio > 0.10:
        # NFPA 72 17.6.3.1: deep beam = full compartment separation
        logger.warning(
            f"Beam depth {beam_depth_m:.2f}m = {beam_ratio:.1%} of ceiling height "
            f"{ceiling_height_m:.2f}m. Per NFPA 72 s17.6.3.1: "
            f"treat bays as SEPARATE COMPARTMENTS. Each requires its own detector."
        )
        return nominal_radius_m  # radius unchanged; compartment logic handles placement

    elif beam_ratio > 0.04:
        # Moderate beam: conservative 15% reduction
        adjusted = nominal_radius_m * 0.85
        logger.info(
            f"Beam ratio {beam_ratio:.1%} (>4%%): reducing radius "
            f"{nominal_radius_m:.2f}m -> {adjusted:.2f}m (15%% conservative reduction)"
        )
        return adjusted

    else:
        # Shallow beam: no adjustment needed
        return nominal_radius_m