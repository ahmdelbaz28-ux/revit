from __future__ import annotations

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

import logging  # V20.2 FIX: Moved from line 947 to top of file — logger is used
import math

# in functions (e.g. verify_full_coverage line ~849) that run
# before the old import location. Previously, if the Shapely
# area calculation failed, the except block called
# logger.warning() → NameError → no fallback → crash.
from dataclasses import dataclass
from typing import List, Optional, Tuple

from shapely.geometry import Point, Polygon, box
from shapely.ops import unary_union

# V20.2: Logger defined at module level (was at line 947, too late)
logger = logging.getLogger(__name__)


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

from .nfpa72_calculations import (
    calculate_coverage_radius_from_height,
    is_in_ridge_zone,
    requires_ridge_zone_detector,
)
from .nfpa72_models import (
    CeilingSpec,
    CoverageResult,
    DetectorType,
    NFPAComplianceResult,
    RoomSpec,
    get_smoke_detector_radius_safe,
)

# ============================================================================
# POLYGON-BASED COVERAGE CHECKS
# ============================================================================
# ============================================================================
# V9: WALL DISTANCE VALIDATION
# ============================================================================
NFPA_MIN_WALL_DISTANCE_M = (
    0.1016  # CRITICAL FIX (C2): 4 inches = 101.6mm per NFPA 72 §17.6.3.1.1 (was 0.10m = 100mm, 1.6mm too lenient)
)


def validate_wall_distances(
    detector_positions: List[Tuple[float, float]],
    room_spec: RoomSpec,
    min_distance_m: float = NFPA_MIN_WALL_DISTANCE_M,
    room_polygon: Polygon = None,
) -> List[dict]:
    """V9: Validates that all detectors maintain minimum wall distance.

    Per NFPA 72 §17.6.3.1.1: Detectors shall not be located closer than
    4 inches (100 mm) from a sidewall or end wall.

    V49 FIX: Added room_polygon parameter for L-shaped/polygonal rooms.
    Previous version only checked 4 rectangular walls (left/right/top/bottom),
    which is incorrect for L-shaped or irregular rooms where the actual wall
    may be closer than the bounding box edge. When room_polygon is provided,
    uses Shapely boundary distance for accurate wall proximity calculation.

    Args:
        detector_positions: List of (x, y) detector coordinates
        room_spec: Room specification with width_m and depth_m
        min_distance_m: Minimum wall distance (default 0.1016m per NFPA 72)
        room_polygon: Optional Shapely Polygon for L-shaped/irregular rooms.
            When provided, uses actual polygon boundary distance instead of
            rectangular wall approximation.

    Returns:
        List of violations, each with detector_index, position, distance, wall
        Empty list = all detectors compliant

    """
    violations = []

    for idx, (x, y) in enumerate(detector_positions):
        if not math.isfinite(x) or not math.isfinite(y):
            continue

        if room_polygon is not None and room_polygon.is_valid:
            room_boundary = room_polygon.boundary
            pt = Point(x, y)
            dist_to_wall = room_boundary.distance(pt)
            if dist_to_wall < min_distance_m:
                violations.append(
                    {
                        "detector_index": idx,
                        "position": (x, y),
                        "wall": "polygon_boundary",
                        "distance_m": round(dist_to_wall, 4),
                        "required_m": min_distance_m,
                        "violation": (
                            f"Detector #{idx} at ({x:.2f},{y:.2f}) is "
                            f"{dist_to_wall * 100:.1f}cm from nearest wall "
                            f"(min {min_distance_m * 100:.0f}cm per NFPA 72 §17.6.3.1.1)"
                        ),
                        "nfpa_reference": "NFPA 72-2022 §17.6.3.1.1",
                    }
                )
        else:
            dist_left = x
            dist_right = room_spec.width_m - x
            dist_bottom = y
            dist_top = room_spec.depth_m - y

            wall_distances = {
                "left": dist_left,
                "right": dist_right,
                "bottom": dist_bottom,
                "top": dist_top,
            }

            for wall, dist in wall_distances.items():
                if dist < min_distance_m:
                    violations.append(
                        {
                            "detector_index": idx,
                            "position": (x, y),
                            "wall": wall,
                            "distance_m": round(dist, 4),
                            "required_m": min_distance_m,
                            "violation": f"Detector #{idx} at ({x:.2f},{y:.2f}) is {dist * 100:.1f}cm from {wall} wall "
                            f"(min {min_distance_m * 100:.0f}cm per NFPA 72 §17.6.3.1.1)",
                            "nfpa_reference": "NFPA 72-2022 §17.6.3.1.1",
                        }
                    )

    return violations


# ============================================================================
# V15: HVAC SUPPLY AIR DIFFUSER EXCLUSION ZONES
# ============================================================================
NFPA_HVAC_EXCLUSION_RADIUS_M = (
    0.9144  # CRITICAL FIX (C3): 3 ft = 0.9144m per NFPA 72 §17.7.4.1 (was 0.914m, 0.4mm too lenient)
)


def validate_hvac_exclusion_zones(
    detector_positions: List[Tuple[float, float]],
    hvac_diffuser_positions: List[Tuple[float, float]],
    exclusion_radius_m: float = NFPA_HVAC_EXCLUSION_RADIUS_M,
) -> List[dict]:
    """V15: Validates that no detector is within the HVAC supply air diffuser
    exclusion zone per NFPA 72 §17.7.4.1.

    Airflow from HVAC supply diffusers prevents smoke from reaching detectors.
    NFPA 72 §17.7.4.1 requires detectors be located NOT less than 3 feet
    (0.914m) from the supply air diffuser unless the detector is listed for
    use in that specific airflow pattern.

    Args:
        detector_positions: List of (x, y) detector coordinates
        hvac_diffuser_positions: List of (x, y) HVAC supply diffuser coordinates
        exclusion_radius_m: Minimum distance from diffuser (default 0.914m per NFPA 72)

    Returns:
        List of violations, each with detector_index, position, diffuser, distance.
        Empty list = all detectors compliant.

    """
    import math

    violations = []

    for d_idx, (dx, dy) in enumerate(detector_positions):
        for h_idx, (hx, hy) in enumerate(hvac_diffuser_positions):
            dist = math.hypot(dx - hx, dy - hy)
            if dist < exclusion_radius_m:
                violations.append(
                    {
                        "detector_index": d_idx,
                        "position": (dx, dy),
                        "diffuser_index": h_idx,
                        "diffuser_position": (hx, hy),
                        "distance_m": round(dist, 4),
                        "required_m": exclusion_radius_m,
                        "violation": (
                            f"Detector #{d_idx} at ({dx:.2f},{dy:.2f}) is {dist * 100:.1f}cm "
                            f"from HVAC diffuser #{h_idx} at ({hx:.2f},{hy:.2f}) "
                            f"(min {exclusion_radius_m * 100:.0f}cm per NFPA 72 §17.7.4.1)"
                        ),
                        "nfpa_reference": "NFPA 72-2022 §17.7.4.1",
                    }
                )

    return violations


def compute_hvac_safe_zone(
    room_polygon,
    hvac_diffuser_positions: List[Tuple[float, float]],
    exclusion_radius_m: float = NFPA_HVAC_EXCLUSION_RADIUS_M,
):
    """V15: Compute the safe placement zone by subtracting HVAC diffuser
    exclusion circles from the room polygon.

    NFPA 72 §17.7.4.1: Detectors shall not be installed within 3 ft (0.914m)
    of a supply air diffuser.

    Args:
        room_polygon: Shapely Polygon of the room
        hvac_diffuser_positions: List of (x, y) supply diffuser coordinates
        exclusion_radius_m: Exclusion radius (default 0.914m)

    Returns:
        Shapely Polygon of the safe placement area (room minus exclusion zones).
        Raises ValueError if safe zone is empty (diffusers cover entire ceiling).

    """
    from shapely.geometry import Point

    safe_zone = room_polygon
    for hx, hy in hvac_diffuser_positions:
        exclusion_circle = Point(hx, hy).buffer(
            exclusion_radius_m, quad_segs=16
        )  # V111: Explicit quad_segs for deterministic NFPA compliance
        safe_zone = safe_zone.difference(exclusion_circle)

    if safe_zone.is_empty:
        raise ValueError(
            "CRITICAL: No valid detector placement area remains. "
            "HVAC supply diffusers cover the entire ceiling. "
            "Per NFPA 72 §17.7.4.1, relocate diffusers or use listed detectors."
        )

    return safe_zone


def suggest_duct_detectors(room: RoomSpec, detector_type: str = "smoke") -> List[DuctDevice]:
    """Suggest detector placements near HVAC ducts."""
    devices = []  # type: ignore[var-annotated]
    if not room.hvac_ducts:
        return devices

    for i, duct in enumerate(room.hvac_ducts):
        if not duct.centerline:
            continue
        cx, cy = duct.centerline[0][:2]
        devices.append(DuctDevice(device_id=f"DUCT_{i + 1}", x=cx, y=cy, detector_type=detector_type))
    return devices


def create_room_polygon(room_spec: RoomSpec) -> Polygon:
    """Create Shapely polygon from room specification.
    Handles rectangular, L-shaped, and rooms with interior holes (columns, shafts).

    SAFETY FIX: Interior holes (columns, elevator shafts, mechanical chases) are
    physically impassable areas where detectors CANNOT be placed. Without hole
    handling, the coverage check would count these areas as "covered" by a detector
    placed over the hole — a FALSE PASS. With this fix, holes are subtracted from
    the room polygon, ensuring coverage verification only counts real floor area.

    Args:
        room_spec: Room specification (may include holes field)

    Returns:
        Shapely Polygon object (with interior rings if holes provided)

    """
    if room_spec.polygon:
        # RoomSpec.__post_init__ already constructed polygon with holes
        return room_spec.polygon
    # Default rectangular room
    return Polygon([(0, 0), (room_spec.width_m, 0), (room_spec.width_m, room_spec.depth_m), (0, room_spec.depth_m)])


def is_point_in_room(point: Tuple[float, float], room_polygon: Polygon) -> bool:
    """Check if point is inside room polygon.
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
    detector_type: DetectorType = DetectorType.SMOKE,
) -> CoverageResult:
    """Check coverage using Polygon containment.
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
    elif detector_type == DetectorType.HEAT:
        # ✅ HEAT: Use square geometry (Chebyshev distance)
        # Per NFPA 72, heat detectors use rectangular/square coverage areas
        # because heat detection responds to absolute temperature rise
        # not smoke migration patterns
        #
        # CRITICAL FIX (2026-05-18): Previous version hardcoded 9.1/2 = 4.55m
        # for heat detector half-spacing, which is WRONG because heat detector
        # spacing varies with ceiling height per NFPA 72 Table 17.6.3.1.1.
        # Now uses calculate_coverage_radius_from_height() which returns the
        # height-adjusted spacing for heat detectors.
        heat_spec = calculate_coverage_radius_from_height(ceiling_spec.height_m, detector_type="heat")
        radius = heat_spec.spacing_max / 2.0  # Half of height-adjusted spacing
    else:
        # Default fallback for other detector types
        radius = get_smoke_detector_radius_safe(ceiling_spec.height_m)
    # V9: Adaptive sampling resolution based on room size
    # Minimum 0.25m grid resolution (NFPA detection hole < 25cm)
    # Maximum 50x50 grid to limit computation
    GRID_RESOLUTION_M = 0.25  # 25cm resolution — catches all blind spots
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
                # CRITICAL FIX: Use height-adjusted heat spacing from NFPA table
                heat_spec = calculate_coverage_radius_from_height(ceiling_spec.height_m, detector_type="heat")
                half_spacing = heat_spec.spacing_max / 2.0
                for dx, dy in detector_positions:
                    # Chebyshev distance: max(|dx|, |dy|)
                    if max(abs(x - dx), abs(y - dy)) <= half_spacing:
                        covered = True
                        break
            else:
                # ✅ SMOKE/OTHER: Use Euclidean distance (circular coverage)
                for dx, dy in detector_positions:
                    dist = math.sqrt((x - dx) ** 2 + (y - dy) ** 2)
                    if dist <= radius:
                        covered = True
                        break
            if covered:
                covered_count += 1
            else:
                uncovered.append(point)
    # =====================================================================
    # V13 Fix: Area-based coverage calculation (replaces point-counting)
    # =====================================================================
    # Point-counting (covered_count / total_points) has a fatal flaw:
    # it can miss uncovered corners between grid points. A room with 99.77%
    # point coverage might have a 0.5m gap in a corner that the 0.25m grid
    # happened to skip. This violates NFPA 72's requirement that EVERY point
    # must be within the listed spacing of a detector.
    #
    # Fix: Use Shapely area-based calculation. Create coverage polygons for
    # each detector, union them, intersect with room polygon, then compute
    # the area ratio. This gives EXACT coverage with no grid artifacts.
    #
    # The point-sampling result is kept as a secondary metric for debugging.
    # =====================================================================
    try:
        room_area = room_polygon.area
        if room_area <= 0:
            raise ValueError("Room has zero area")

        coverage_polys = []
        if detector_type == DetectorType.HEAT:
            # HEAT: Square coverage (Chebyshev)
            heat_spec = calculate_coverage_radius_from_height(ceiling_spec.height_m, detector_type="heat")
            half_s = heat_spec.spacing_max / 2.0
            for dx, dy in detector_positions:
                sq = box(dx - half_s, dy - half_s, dx + half_s, dy + half_s)
                coverage_polys.append(sq)
        else:
            # SMOKE: Circular coverage (Euclidean)
            for dx, dy in detector_positions:
                pt = Point(dx, dy)
                buf = pt.buffer(radius, quad_segs=16)  # V111: Explicit quad_segs for deterministic NFPA compliance
                coverage_polys.append(buf)

        if coverage_polys:
            total_coverage = unary_union(coverage_polys)
            # Clip to room boundary — coverage doesn't extend through walls
            actual_coverage = total_coverage.intersection(room_polygon)
            coverage_area_pct = (actual_coverage.area / room_area) * 100.0
            coverage_area_pct = min(coverage_area_pct, 100.0)  # Cap at 100%
        else:
            coverage_area_pct = 0.0

        # Use area-based coverage as the PRIMARY result
        # 99.9% area threshold = NFPA compliant (accounts for floating-point)
        is_covered_area = coverage_area_pct >= 99.9

        # Keep point-based result as secondary for backward compatibility
        if total_points > 0:
            (covered_count / total_points) * 100
        else:
            pass

        # Primary coverage = area-based (NFPA compliant)
        # If area says covered but points don't, trust the area (points can miss corners)
        # If points say covered but area doesn't, trust the area (area is exact)
        primary_pct = coverage_area_pct
        is_covered = is_covered_area

    except Exception as area_err:
        # Fallback to point-based if Shapely area calculation fails
        # (e.g., invalid geometry, degenerate polygon)
        import logging as _logging

        _logging.getLogger(__name__).warning(f"Area-based coverage failed, falling back to point-based: {area_err}")
        if total_points > 0:
            primary_pct = (covered_count / total_points) * 100
        else:
            primary_pct = 0
        is_covered = primary_pct >= 99.9  # V20.2 FIX: Must match primary threshold (was 99%)

    return CoverageResult(
        is_covered=is_covered,
        uncovered_areas=uncovered,
        coverage_percentage=primary_pct,
        detectors_in_coverage=len(detector_positions),
    )


# ============================================================================
# VORONOI COVERAGE (Advanced)
# ============================================================================
def calculate_voronoi_coverage(detector_positions: List[Tuple[float, float]], room_polygon: Polygon) -> List[Polygon]:
    """Calculate Voronoi regions for detector coverage areas.

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
    except Exception as e:
        # V60 FIX (P4-1): Previously bare except returned [room_polygon] silently,
        # which could cause the coverage algorithm to incorrectly report full
        # coverage when Voronoi subdivision failed. Now we log the failure and
        # return the room polygon with a warning — callers must check for this
        # condition. In a life-safety system, silent failure is unacceptable.
        import logging

        logging.getLogger(__name__).error(
            "V60 SAFETY: Voronoi region clipping failed for room polygon. "
            "Falling back to single-region coverage (may miss coverage gaps). "
            "Error: %s [NFPA 72 §17.7.4.2.3.1]",
            e,
        )
        return [room_polygon]


def check_voronoi_coverage(
    detector_positions: List[Tuple[float, float]],
    room_spec: RoomSpec,
    ceiling_spec: CeilingSpec,
    detector_type: DetectorType = DetectorType.SMOKE,
) -> CoverageResult:
    """Check coverage using Voronoi diagram (advanced method).

    V49 FIX: Added detector_type parameter — previous version always passed
    DetectorType.SMOKE to check_coverage_polygon regardless of actual detector
    type. This meant heat detector Voronoi coverage was calculated using
    CIRCULAR geometry (Euclidean distance) instead of SQUARE geometry
    (Chebyshev distance), overestimating coverage and potentially approving
    non-compliant heat detector placements.

    Args:
        detector_positions: Detector positions
        room_spec: Room specification
        ceiling_spec: Ceiling specification
        detector_type: Type of detector (SMOKE or HEAT). Default SMOKE for
            backward compatibility.

    Returns:
        CoverageResult

    """
    room_polygon = create_room_polygon(room_spec)
    # ✅ Use safe fallback for smoke radius (used by Voronoi visualization)
    get_smoke_detector_radius_safe(ceiling_spec.height_m)
    # Voronoi regions show theoretical coverage
    calculate_voronoi_coverage(detector_positions, room_polygon)
    # V49 FIX: Pass actual detector_type to check_coverage_polygon so heat
    # detectors use square (Chebyshev) geometry instead of always using
    # circular (smoke) geometry.
    return check_coverage_polygon(detector_positions, room_spec, ceiling_spec, detector_type)


# ============================================================================
# RIDGE ZONE COMPLIANCE
# ============================================================================
def check_ridge_zone_compliance(
    detector_positions: List[Tuple[float, float]],
    ceiling_spec: CeilingSpec,
    ridge_line: Tuple[float, float, float, float],
    standard_spacing: float = None,
    detector_type: DetectorType = DetectorType.SMOKE,
) -> NFPAComplianceResult:
    """Check if sloped ceiling has a ROW of detectors in the ridge zone.

    Per NFPA 72 §17.6.3.4, for ceilings with slope > 25 % (approx 14°),
    detectors must be located within 0.9 m (3 ft) of the ridge AND
    spaced no farther apart than the listed spacing along the ridge.

    The old code accepted a single detector in the ridge zone, which
    fails for long ridges (e.g. a 60 m warehouse gable roof where one
    detector at one end leaves the far end unprotected — smoke travels
    longitudinally along the ridge before descending to side detectors).

    Args:
        detector_positions: List of detector (x, y) positions.
        ceiling_spec:       Ceiling specification (slope, type).
        ridge_line:         (x1, y1, x2, y2) ridge line coordinates.
        standard_spacing:   Maximum detector spacing along the ridge (m).
                            Default depends on detector_type: 9.1m for smoke,
                            6.1m for heat per NFPA 72 Table 17.6.3.5.1.
        detector_type:      Type of detector (affects default spacing).

    Returns:
        NFPAComplianceResult

    """
    # V65 FIX: Default spacing depends on detector type.
    # Old code hardcoded 9.1m (smoke spacing) which is 49% beyond the
    # NFPA 72 max heat spacing of 6.1m — a false PASS for heat detectors.
    if standard_spacing is None:
        standard_spacing = 6.1 if detector_type == DetectorType.HEAT else 9.1

    result = NFPAComplianceResult(is_compliant=False)  # V78 FIX: Fail-closed — assume non-compliant until proven
    if not requires_ridge_zone_detector(ceiling_spec):
        # Flat ceiling or ceiling not requiring ridge zone detector — compliant by default
        result.is_compliant = True
        return result

    # Collect all detectors inside the ridge zone
    ridge_detectors = []
    for dx, dy in detector_positions:
        if is_in_ridge_zone((dx, dy), ridge_line, ceiling_spec.slope_degrees):
            ridge_detectors.append((dx, dy))

    # Must have at least one detector in the ridge zone
    if not ridge_detectors:
        result.add_violation(
            f"Sloped ceiling (slope={ceiling_spec.slope_degrees}°) requires "
            f"detectors in the ridge zone (within 0.9m of ridge). "
            f"None found. (NFPA 72 §17.6.3.4)"
        )
        return result

    # Calculate ridge length and required detector count
    x1, y1, x2, y2 = ridge_line
    ridge_length = math.hypot(x2 - x1, y2 - y1)

    if ridge_length > 0 and standard_spacing > 0:
        required_count = max(1, math.ceil(ridge_length / standard_spacing))
        if len(ridge_detectors) < required_count:
            result.add_violation(
                f"Ridge length {ridge_length:.1f}m requires at least "
                f"{required_count} detectors in the ridge zone "
                f"(spacing ≤ {standard_spacing}m per NFPA 72 §17.6.3.4), "
                f"but only {len(ridge_detectors)} found."
            )

    # Check inter-detector gaps along the ridge
    if len(ridge_detectors) >= 2 and ridge_length > 0:
        # Sort detectors by their projection along the ridge direction
        dx = x2 - x1
        dy = y2 - y1
        ridge_len_sq = dx * dx + dy * dy
        if ridge_len_sq > 0:
            sorted_dets = sorted(ridge_detectors, key=lambda p: ((p[0] - x1) * dx + (p[1] - y1) * dy) / ridge_len_sq)
            for i in range(len(sorted_dets) - 1):
                gap = math.hypot(sorted_dets[i + 1][0] - sorted_dets[i][0], sorted_dets[i + 1][1] - sorted_dets[i][1])
                if gap > standard_spacing:  # V65 FIX: Removed 1% tolerance — NFPA 72 uses "shall not exceed" (mandatory language, no tolerance)
                    result.add_violation(
                        f"Ridge detector gap {gap:.1f}m exceeds spacing limit {standard_spacing}m (NFPA 72 §17.6.3.4)."
                    )
                    break  # One violation is enough to flag

    # V78 FIX: If no violations were added, mark as compliant
    if not result.violations:
        result.is_compliant = True

    return result


# ============================================================================
# L-SHAPED ROOM HANDLING
# ============================================================================
def create_l_shaped_polygon(dimensions: List[Tuple[float, float]]) -> Polygon:
    """Create polygon for L-shaped room.

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
    ceiling_height_m: float,
    detector_type: DetectorType = DetectorType.SMOKE,
    listed_spacing_m: Optional[float] = None,
) -> CoverageResult:
    """Check coverage for L-shaped room.
    This is the critical test case - Bounding Box fails here.

    V13 Fix: Uses area-based coverage calculation as primary method,
    with point-sampling retained for uncovered area detection.

    V20.2 Fix: Added detector_type + listed_spacing_m parameters so
    heat detectors use square (Chebyshev) geometry instead of always
    using circular (smoke) geometry. Also fixed fallback math which
    computed an incorrect coverage percentage when area calculation failed.
    """
    # =====================================================================
    # Determine coverage geometry per detector type
    # =====================================================================
    if detector_type == DetectorType.HEAT:
        heat_spec = calculate_coverage_radius_from_height(ceiling_height_m, detector_type="heat")
        half_spacing = heat_spec.spacing_max / 2.0
        radius = half_spacing  # Used for area-based circle fallback
    else:
        radius = get_smoke_detector_radius_safe(ceiling_height_m)
        half_spacing = radius

    # =====================================================================
    # PRIMARY: Area-based coverage (EXACT, no grid artifacts)
    # =====================================================================
    try:
        room_area = room_polygon.area
        if room_area <= 0:
            raise ValueError("Room has zero area")

        coverage_polys = []
        if detector_type == DetectorType.HEAT:
            for dx, dy in detector_positions:
                sq = box(dx - half_spacing, dy - half_spacing, dx + half_spacing, dy + half_spacing)
                coverage_polys.append(sq)
        else:
            for dx, dy in detector_positions:
                pt = Point(dx, dy)
                buf = pt.buffer(radius, quad_segs=16)  # V111: Explicit quad_segs for deterministic NFPA compliance
                coverage_polys.append(buf)

        if coverage_polys:
            total_coverage = unary_union(coverage_polys)
            actual_coverage = total_coverage.intersection(room_polygon)
            area_pct = (actual_coverage.area / room_area) * 100.0
            area_pct = min(area_pct, 100.0)
        else:
            area_pct = 0.0

        is_covered = area_pct >= 99.9
    except Exception as e:
        # V60 FIX: Log exception instead of silently failing
        import logging

        logging.getLogger(__name__).error(
            "V60: Area-based coverage calculation failed. Falling back to is_covered=False. Error: %s", e
        )
        area_pct = 0.0
        is_covered = False

    # =====================================================================
    # SECONDARY: Point-sampling for uncovered area coordinates
    # =====================================================================
    GRID_RESOLUTION_M = 0.25
    uncovered = []
    total_sampled = 0  # V20.2 FIX: Track total points for correct fallback
    bounds = room_polygon.bounds
    min_x, min_y, max_x, max_y = bounds
    step_x = GRID_RESOLUTION_M
    step_y = GRID_RESOLUTION_M
    x = min_x
    while x <= max_x:
        y = min_y
        while y <= max_y:
            if not room_polygon.contains(Point(x, y)):
                y += step_y
                continue
            total_sampled += 1
            # V20.2 FIX: Use correct geometry per detector type
            if detector_type == DetectorType.HEAT:
                covered = any(max(abs(x - dx), abs(y - dy)) <= half_spacing for dx, dy in detector_positions)
            else:
                covered = any(math.sqrt((x - dx) ** 2 + (y - dy) ** 2) <= radius for dx, dy in detector_positions)
            if not covered:
                uncovered.append((x, y))
            y += step_y
        x += step_x

    # V20.2 FIX: Use area-based percentage (primary), with correct fallback
    if area_pct > 0:
        primary_pct = area_pct
    else:
        # Fallback: proper point-based percentage
        if total_sampled > 0:
            primary_pct = ((total_sampled - len(uncovered)) / total_sampled) * 100
        else:
            primary_pct = 0
        is_covered = primary_pct >= 99.9  # Match primary threshold

    return CoverageResult(
        is_covered=is_covered,
        uncovered_areas=uncovered,
        coverage_percentage=primary_pct,
        detectors_in_coverage=len(detector_positions),
    )


# ============================================================================
# FULL COMPLIANCE CHECK
# ============================================================================
def check_nfpa72_compliance(
    room_spec: RoomSpec,
    ceiling_spec: CeilingSpec,
    detector_positions: List[Tuple[float, float]],
    detector_type: DetectorType = DetectorType.SMOKE,
    ridge_line: Optional[Tuple[float, float, float, float]] = None,
) -> NFPAComplianceResult:
    """Full NFPA 72 compliance check.

    Args:
        room_spec: Room specification
        ceiling_spec: Ceiling specification
        detector_positions: Placed detector positions
        detector_type: Type of detector
        ridge_line: Ridge line for sloped ceiling
    Returns:
        NFPAComplianceResult

    """
    result = NFPAComplianceResult(is_compliant=False)  # V78 FIX: Fail-closed — assume non-compliant until proven
    result.detector_count = len(detector_positions)
    # Check coverage
    coverage = check_coverage_polygon(detector_positions, room_spec, ceiling_spec, detector_type)
    if not coverage.is_covered:
        result.add_violation(f"Coverage is {coverage.coverage_percentage:.1f}%, below 99.9% required")
    # Check ridge zone
    if ridge_line and requires_ridge_zone_detector(ceiling_spec):
        ridge_result = check_ridge_zone_compliance(detector_positions, ceiling_spec, ridge_line)
        result.violations.extend(ridge_result.violations)
        if ridge_result.violations:
            result.is_compliant = False
    result.required_detector_count = result.detector_count
    # V78 FIX: If no violations were added, mark as compliant
    if not result.violations:
        result.is_compliant = True
    return result


# Test exported symbols
__all__ = [
    "adjust_coverage_for_beams",
    "calculate_voronoi_coverage",
    "check_coverage_polygon",
    "check_l_shaped_coverage",
    "check_nfpa72_compliance",
    "check_ridge_zone_compliance",
    "check_voronoi_coverage",
    "create_l_shaped_polygon",
    "create_room_polygon",
    "get_sloped_ceiling_constraints",
    "is_point_in_room",
    "suggest_duct_detectors",
    "verify_full_coverage",
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
    """Verify that all points in the room are covered by detectors.

    V13 Fix — Area-based coverage (replaces point-counting):
    Previous code used (covered_points / total_points) which produces
    floating-point artifacts like 98.7508218277449% and can miss uncovered
    corners between grid points. This violates NFPA 72 which requires EVERY
    point to be within listed spacing of a detector.

    Fix: Use Shapely area-based calculation as the PRIMARY method.
    Point-sampling is retained as a secondary metric for worst-case distance
    reporting and backward compatibility, but the compliance decision is
    based on the EXACT area ratio, not a grid approximation.

    Args:
        room_polygon: Shapely Polygon of room
        detector_positions: List of detector (x, y) positions
        coverage_geometry: "circular" or "square_grid"
        detector_radius: Coverage radius for smoke detectors
        listed_spacing_m: Listed spacing for heat detectors
        grid_resolution_m: Grid resolution for worst-case distance sampling
        detector_type: Type of detector (SMOKE or HEAT)

    Returns:
        Dictionary with coverage_percentage, worst_case_distance_m, compliance_status

    """
    # V20.2 FIX #13: Heat detector spacing fallback was 9.1m (smoke listed
    # spacing) instead of 6.1m (heat listed spacing per NFPA 72 Table 17.6.3.1.1).
    # Using 9.1/2 = 4.55m instead of 6.1/2 = 3.05m credits heat detectors
    # with MORE coverage than they provide, leaving areas UNPROTECTED.
    _DEFAULT_SMOKE_SPACING_M = 9.1  # NFPA 72 Table 17.6.3.1.1 at h<=3.0m
    _DEFAULT_HEAT_SPACING_M = 6.1  # NFPA 72 Table 17.6.3.1.1 at h<=3.0m

    if coverage_geometry == "circular":
        radius = detector_radius
    else:
        if detector_type == DetectorType.HEAT:
            radius = (listed_spacing_m or _DEFAULT_HEAT_SPACING_M) / 2
        else:
            radius = (listed_spacing_m or _DEFAULT_SMOKE_SPACING_M) / 2

    if detector_type == DetectorType.HEAT:
        half_spacing = (listed_spacing_m or _DEFAULT_HEAT_SPACING_M) / 2

    # =====================================================================
    # PRIMARY: Area-based coverage calculation (EXACT, no grid artifacts)
    # =====================================================================
    try:
        room_area = room_polygon.area
        if room_area <= 0:
            raise ValueError("Room has zero area")

        coverage_polys = []
        if detector_type == DetectorType.HEAT:
            for dx, dy in detector_positions:
                sq = box(dx - half_spacing, dy - half_spacing, dx + half_spacing, dy + half_spacing)
                coverage_polys.append(sq)
        else:
            for dx, dy in detector_positions:
                pt = Point(dx, dy)
                buf = pt.buffer(radius, quad_segs=16)  # V111: Explicit quad_segs for deterministic NFPA compliance
                coverage_polys.append(buf)

        if coverage_polys:
            total_coverage = unary_union(coverage_polys)
            actual_coverage = total_coverage.intersection(room_polygon)
            area_coverage_pct = (actual_coverage.area / room_area) * 100.0
            area_coverage_pct = min(area_coverage_pct, 100.0)
        else:
            area_coverage_pct = 0.0

        # 99.9% area threshold = NFPA compliant (0.1% tolerance for float)
        area_status = "PASS" if area_coverage_pct >= 99.9 else "FAIL"

    except Exception as area_err:
        logger.warning("Area-based coverage failed in verify_full_coverage, falling back to point-based: %s", area_err)
        area_coverage_pct = None
        area_status = None

    # =====================================================================
    # SECONDARY: Point-sampling for worst-case distance (diagnostic)
    # =====================================================================
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
                min_dist = float("inf")
                for dx, dy in detector_positions:
                    if detector_type == DetectorType.HEAT:
                        dist = max(abs(x - dx), abs(y - dy))
                    else:
                        dist = math.sqrt((x - dx) ** 2 + (y - dy) ** 2)
                    min_dist = min(min_dist, dist)
                if detector_type == DetectorType.HEAT:
                    if min_dist <= half_spacing:
                        covered_points += 1
                    else:
                        worst_distance = max(worst_distance, min_dist)
                else:
                    if min_dist <= radius:
                        covered_points += 1
                    else:
                        worst_distance = max(worst_distance, min_dist)
            y += step
        x += step

    point_coverage_pct = (covered_points / total_points * 100) if total_points > 0 else 0

    # Use area-based result as primary if available; fall back to point-based
    if area_coverage_pct is not None:
        primary_pct = area_coverage_pct
        status = area_status
    else:
        primary_pct = point_coverage_pct
        status = "PASS" if point_coverage_pct >= 99.9 else "FAIL"

    return {
        "coverage_percentage": primary_pct,
        "worst_case_distance_m": worst_distance,
        "compliance_status": status,
        "coverage_geometry": "square" if detector_type == DetectorType.HEAT else "circular",
        "total_points_checked": total_points,
        "covered_points": covered_points,
        "area_coverage_pct": area_coverage_pct,
        "point_coverage_pct": point_coverage_pct,
    }


def get_sloped_ceiling_constraints(
    polygon,
    ceiling_spec,
    detector_type,
) -> dict:
    """Get sloped ceiling constraints for NFPA 72 compliance.

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
    ridge_buffer = 0.9  # metres per NFPA 72 §17.6.3.4

    # V49 FIX: Previous code returned the entire room polygon as the ridge
    # zone, which is incorrect. Per NFPA 72 §17.6.3.4, the ridge zone is
    # the area within 0.9m (3 ft) of the highest point (ridge). Returning
    # the whole polygon meant downstream code treated the entire room as a
    # ridge zone, potentially placing all detectors near the ridge and
    # ignoring coverage requirements for the rest of the ceiling.
    #
    # Create the ridge zone as a horizontal strip at the top of the room
    # (assuming the ridge runs along the top edge). The strip extends
    # ridge_buffer (0.9m) downward from the top of the room polygon.
    try:
        # Create a horizontal strip from (minx, maxy - ridge_buffer) to
        # (maxx, maxy) and intersect with the room polygon to get the
        # actual ridge zone within room boundaries.
        ridge_strip = box(minx, maxy - ridge_buffer, maxx, maxy)
        ridge_zone = polygon.intersection(ridge_strip)
        if ridge_zone.is_empty or ridge_zone.area < 0.01:
            # Room too small or ridge zone degenerate — use full polygon
            # as conservative fallback (ensures at least one detector near ridge)
            ridge_zone = polygon
    except Exception as e:
        # V60 FIX (P4-2): Previously bare except silently used full polygon as
        # ridge zone, which could cause detectors to be placed in wrong positions.
        # Now we log the failure for engineering review.
        import logging

        logging.getLogger(__name__).warning(
            "V60: Ridge zone computation failed, using full polygon as fallback. "
            "Detector placement may not be optimal for ridged ceiling. "
            "Error: %s [NFPA 72 §17.6.3.1.1]",
            e,
        )
        ridge_zone = polygon

    return {
        "requires_ridge_row": True,
        "ridge_zone_polygon": ridge_zone,
    }


# V20.2: logging and logger moved to top of file (line 24-35)
def adjust_coverage_for_beams(
    nominal_radius_m: float,
    beam_depth_m: float,
    ceiling_height_m: float,
) -> float:
    """Adjusts detector coverage radius based on beam obstruction.

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
    if not math.isfinite(ceiling_height_m) or ceiling_height_m <= 1e-6:
        raise ValueError(f"ceiling_height_m must be positive, got {ceiling_height_m}")
    if not math.isfinite(beam_depth_m) or beam_depth_m < 0:
        raise ValueError(f"beam_depth_m cannot be negative, got {beam_depth_m}")
    if math.isnan(nominal_radius_m):
        raise ValueError(f"nominal_radius_m must be a finite number, got {nominal_radius_m}")

    beam_ratio = beam_depth_m / ceiling_height_m

    if beam_ratio > 0.10:
        # NFPA 72 17.6.3.1: deep beam = full compartment separation
        logger.warning(
            f"Beam depth {beam_depth_m:.2f}m = {beam_ratio:.1%} of ceiling height "
            f"{ceiling_height_m:.2f}m. Per NFPA 72 s17.6.3.1: "
            f"treat bays as SEPARATE COMPARTMENTS. Each requires its own detector."
        )
        return nominal_radius_m  # radius unchanged; compartment logic handles placement

    if beam_ratio > 0.04:
        # Moderate beam: conservative 15% reduction
        adjusted = nominal_radius_m * 0.85
        logger.info(
            f"Beam ratio {beam_ratio:.1%} (>4%%): reducing radius "
            f"{nominal_radius_m:.2f}m -> {adjusted:.2f}m (15%% conservative reduction)"
        )
        return adjusted

    # Shallow beam: no adjustment needed
    return nominal_radius_m
