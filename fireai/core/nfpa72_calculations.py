"""NFPA 72 V5 Calculations - Radius, Heat, and Sloped Ceiling Calculations
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
from __future__ import annotations

import math
from dataclasses import dataclass
from functools import lru_cache
from typing import Any, Dict, List, Literal, Optional, Tuple

from .nfpa72_models import (
    CeilingSpec,
    DetectorType,
    HeatDetectorSpec,
    HVACDuct,
    RoomSpec,
    get_smoke_detector_coverage_max,
    get_smoke_detector_radius,
    get_smoke_detector_radius_safe,  # V9: safe fallback
)


def get_heat_detector_placement_params(
    spec: HeatDetectorSpec,
    ceiling_height_m: float,
    beam_depth_m: float = 0.0,
    ceiling_slope_degrees: float = 0.0,
) -> dict:
    """Get heat detector placement parameters per NFPA 72.

    Args:
        spec: HeatDetectorSpec with manufacturer, model_number, listed_spacing
        ceiling_height_m: Ceiling height in meters
        beam_depth_m: Beam depth (optional)
        ceiling_slope_degrees: Ceiling slope in degrees (optional)

    Returns:
        Dictionary with max_detector_spacing_m and other parameters

    """
    # CRITICAL FIX: Use spec.FIXED_SPACING_M (6.1m), NOT spec.listed_spacing_m (doesn't exist).
    # Also add ceiling height adjustments per NFPA 72 Table 17.6.2.1.
    # V65 FIX: spec=None indicates missing detector specification — this is a
    # data error upstream, not a valid default case. Silently defaulting to 6.1m
    # could approve a design with undefined detector specs (Rule 12: safety-first).
    if spec is None:
        raise ValueError(
            "HeatDetectorSpec is required — cannot compute placement without "
            "detector specification. A None spec indicates missing data in the "
            "Revit model that must be resolved before design review."
        )
    base_spacing = spec.FIXED_SPACING_M
    # NFPA 72 Table 17.6.2.1: Reduce spacing for ceiling heights > 3.0m
    adjusted_spacing = base_spacing
    if ceiling_height_m > 3.0:
        # Height-adjusted reduction: use the heat spacing from NFPA 72 Table 17.6.3.1.1
        # This table is in nfpa72_calculations.py's _NFPA72_TABLE_17_6_3_1_1
        from .nfpa72_calculations import _NFPA72_TABLE_17_6_3_1_1
        for h_max, _, heat_spacing in _NFPA72_TABLE_17_6_3_1_1:
            if ceiling_height_m <= h_max:
                adjusted_spacing = heat_spacing
                break
        else:
            # Beyond table: use conservative fallback
            adjusted_spacing = 3.50  # matches _NFPA72_HEAT_SPACING_FALLBACK
    return {
        "max_detector_spacing_m": adjusted_spacing,
        "coverage_type": "square_grid",
    }
# ============================================================================
# SMOKE DETECTOR RADIUS CALCULATIONS
# ============================================================================
@lru_cache(maxsize=128)  # V9: memoize pure function
def calculate_smoke_detector_radius(ceiling_height_m: float) -> float:
    """Calculate recommended coverage radius for smoke detector.

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
    """Calculate number of smoke detectors needed per NFPA 72 spacing.

    Args:
        ceiling_spec: Ceiling specification
        room_width_m: Room width in meters
        room_depth_m: Room depth in meters
    Returns:
        Tuple of (number_along_width, number_along_depth)

    """
    radius = get_smoke_detector_radius_safe(ceiling_spec.height_m)  # V9: safe fallback
    # CRITICAL FIX: Use the listed spacing S, NOT max_coverage * 2.
    # max_coverage is the extended coverage radius (5.5m at h=3.0m), NOT the spacing.
    # Using 2×max_coverage = 11.0m exceeds the NFPA 72 listed spacing of 9.1m by 21%.
    # The correct spacing S comes from calculate_max_spacing() which uses R/0.7.
    spacing = radius / 0.7  # S = R / 0.7 (reverse of R = 0.7 × S)
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
    spacing_m: float = 6.1
) -> bool:
    """Check if a point is covered by a heat detector using Chebyshev distance.
    For heat detectors, NFPA 72 uses rectangular (square) coverage areas,
    not circular. This is because heat detection responds to absolute
    temperature rise, not smoke migration.

    Args:
        detector_x: Detector X position
        detector_y: Detector Y position
        point_x: Point X position to check
        point_y: Point Y position to check
        spacing_m: Detector spacing (default 6.1m = 20ft per NFPA 72 Table 17.6.3.5.1)
                   CRITICAL FIX: Was 9.1m (smoke spacing), now 6.1m (heat listed spacing).
                   Callers should use calculate_coverage_radius_from_height() for
                   height-adjusted spacing at high ceilings.

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
    spacing_m: float = 6.1
) -> Tuple[int, int]:
    """Calculate number of heat detectors needed using rectangular spacing.

    Args:
        room_width_m: Room width in meters
        room_depth_m: Room depth in meters
        spacing_m: Detector spacing (default 6.1m = 20ft per NFPA 72 Table 17.6.3.5.1)
                   CRITICAL FIX: Was 9.1m (smoke spacing), now 6.1m (heat listed spacing).

    Returns:
        Tuple of (number_along_width, number_along_depth)

    """
    num_width = max(1, math.ceil(room_width_m / spacing_m))
    num_depth = max(1, math.ceil(room_depth_m / spacing_m))
    return (num_width, num_depth)
def generate_heat_detector_positions(
    room_spec: RoomSpec,
    ceiling_spec: CeilingSpec,
    spacing_m: float = None
) -> List[Tuple[float, float]]:
    """Generate heat detector positions using square grid pattern.
    CRITICAL FIX: Now applies NFPA 72 height-adjusted spacing for heat detectors.
    At high ceilings, heat detector spacing MUST be reduced per Table 17.6.3.5.1.

    Args:
        room_spec: Room specification
        ceiling_spec: Ceiling specification
        spacing_m: Detector spacing. If None, uses height-adjusted spacing from
                   calculate_coverage_radius_from_height(). Default 6.1m at h≤3.0m.

    Returns:
        List of (x, y) detector positions

    """
    if spacing_m is None:
        # Apply NFPA 72 height-adjusted spacing for heat detectors
        heat_spec = calculate_coverage_radius_from_height(
            ceiling_spec.height_m, detector_type="heat"
        )
        spacing = heat_spec.spacing_max
    else:
        spacing = spacing_m
    positions = []
    # V79 FIX: Replaced while-loop with count-based placement.
    # The while-loop used `x < room_spec.width_m` which skipped the last
    # detector row when x fell at or past the boundary. E.g., room 15m × 15m
    # with spacing 6.1m: while-loop places 2×2=4 detectors (x=3.05, 9.15 only;
    # 15.25 > 15 → stops), but ceil(15/6.1)=3 per axis → 9 detectors needed.
    # The far wall at 15m is 5.85m from nearest detector, exceeding NFPA 72
    # §17.6.3.1.1 wall distance limit of S/2 = 3.05m.
    num_w = max(1, math.ceil(room_spec.width_m / spacing))
    num_d = max(1, math.ceil(room_spec.depth_m / spacing))
    for col in range(num_w):
        if num_w > 1:
            x = spacing / 2 + col * (room_spec.width_m - spacing) / (num_w - 1)
        else:
            x = room_spec.width_m / 2
        for row in range(num_d):
            if num_d > 1:
                y = spacing / 2 + row * (room_spec.depth_m - spacing) / (num_d - 1)
            else:
                y = room_spec.depth_m / 2
            positions.append((round(x, 4), round(y, 4)))
    return positions
def is_point_covered_by_heat_detectors(
    point: Tuple[float, float],
    detector_positions: List[Tuple[float, float]],
    spacing_m: float = 6.1
) -> bool:
    """Check if a point is covered by any heat detector.
    Uses SQUARE_GRID (Chebyshev) coverage, NOT circular.

    Args:
        point: (x, y) position to check
        detector_positions: List of detector (x, y) positions
        spacing_m: Detector spacing (default 6.1m = 20ft per NFPA 72 Table 17.6.3.5.1)
                   CRITICAL FIX: Was 9.1m (smoke spacing), now 6.1m (heat listed spacing).

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
    """Calculate ridge zone boundary for sloped ceiling.
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
    # V65 FIX: Ridge zone must extend buffer_m PERPENDICULAR to the ridge line,
    # not just along x-axis. The old code only adjusted x-coordinates,
    # which is correct only for horizontal ridges. For diagonal/vertical
    # ridges, the buffer zone was completely wrong — detectors could be
    # placed outside the actual ridge zone per NFPA 72 §17.6.3.4.
    dx = x2 - x1
    dy = y2 - y1
    length = math.sqrt(dx * dx + dy * dy)
    if length == 0:
        return ridge_line  # Degenerate ridge
    # Perpendicular unit vector (rotated 90°)
    nx = -dy / length
    ny = dx / length
    # Return two parallel lines offset by buffer_m on each side
    # Format: (line1_x1, line1_y1, line1_x2, line1_y2)
    return (
        x1 + nx * buffer_m, y1 + ny * buffer_m,
        x2 + nx * buffer_m, y2 + ny * buffer_m
    )
def is_in_ridge_zone(
    point: Tuple[float, float],
    ridge_line: Tuple[float, float, float, float],
    slope_degrees: float,
    buffer_m: float = 0.9
) -> bool:
    """Check if a point is in the ridge zone.

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
    """Check if ceiling requires ridge zone detector.

    Args:
        ceiling_spec: Ceiling specification
    Returns:
        True if ridge zone detector is required

    """
    # V65 FIX: NFPA 72 §17.6.3.4 requires ridge zone detectors only when
    # slope exceeds 25% (approximately 14°). Old code triggered for ANY
    # slope, even 2° — overly conservative but more importantly contradicts
    # the standard, causing confusion during AHJ review.
    return ceiling_spec.is_sloped and getattr(ceiling_spec, 'slope_degrees', 0) > 14.0
# ============================================================================
# COMBINED CALCULATIONS
# ============================================================================
def calculate_detector_requirements(
    room_spec: RoomSpec,
    ceiling_spec: CeilingSpec,
    detector_type: DetectorType = DetectorType.SMOKE
) -> dict:
    """Calculate detector requirements for a room.

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
        # CRITICAL FIX: Was hardcoded 9.1m (smoke spacing). Now uses
        # NFPA 72 height-adjusted spacing from Table 17.6.3.5.1.
        # At h≤3.0m: 6.1m (20ft), reducing at higher ceilings.
        heat_spec = calculate_coverage_radius_from_height(
            ceiling_spec.height_m, detector_type="heat"
        )
        spacing = heat_spec.spacing_max
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

def calculate_max_spacing(ceiling: CeilingSpec, detector_type: DetectorType) -> float:
    """NFPA 72 §17.6.3 - spacing between detectors.

    CRITICAL FIX: This now returns the actual LISTED SPACING (S) from NFPA 72
    Table 17.6.3.1.1, NOT the coverage radius.  The old version incorrectly
    called get_smoke_detector_coverage_max() which returns a radius, not spacing.
    """
    # Use the module-level import (already imported from .nfpa72_models at top of file)
    # CRITICAL: Do NOT use bare import `from nfpa72_models import` here — that resolves
    # to the stale root-level copy which still has R=S/2 (4.55m) instead of R=0.7×S (6.37m).
    # V65 FIX: height_at_low_point_m may not exist on flat ceilings — use getattr
    # fallback to height_m (the standard flat-ceiling attribute).
    low_height = getattr(ceiling, 'height_at_low_point_m', None)
    if low_height is None:
        low_height = getattr(ceiling, 'height_m', 3.0)  # Conservative default
    radius = get_smoke_detector_radius_safe(low_height)
    spacing = radius / 0.7  # Reverse R = 0.7 × S → S = R / 0.7
    if ceiling.is_sloped:
        high_height = getattr(ceiling, 'height_at_high_point_m', None)
        if high_height is not None:
            radius_high = get_smoke_detector_radius_safe(high_height)
            spacing = min(spacing, radius_high / 0.7)
    return round(spacing, 3)


def calculate_coverage_radius(ceiling: CeilingSpec, detector_type: DetectorType) -> float:
    """NFPA 72 §17.7.4.2.3.1 - coverage radius R = 0.7 × S.

    The coverage radius R = 0.7 × S is the distance from a detector to the
    farthest point in its coverage cell on a square grid at spacing S.
    This is NOT the same as the wall distance (S/2 per §17.6.3.1.1).

    DISTINCTION (DO NOT CONFUSE):
    - Coverage radius R = 0.7 × S: Used for verifying every point on the
      ceiling is within R of a detector. For smoke at h<=3m: R = 6.37m.
    - Wall distance = S/2: Maximum distance from a detector to the nearest
      wall. For smoke at h<=3m: wall_dist = 4.55m.
    - These are DIFFERENT quantities. R > wall_dist because the diagonal
      of a square (0.707×S) is longer than half its side (0.5×S).

    HISTORICAL NOTE: An earlier version used S/2 for coverage radius, which
    was overly conservative (rejected compliant layouts). The 0.7 factor is
    the correct NFPA 72 interpretation for square grid coverage verification.
    """
    spacing = calculate_max_spacing(ceiling, detector_type)
    return round(spacing * 0.7, 4)


def calculate_max_wall_distance(ceiling: CeilingSpec, detector_type: DetectorType) -> float:
    """NFPA 72 §17.6.3.1.1 - max wall distance = S/2 (half the listed spacing).

    CRITICAL FIX: Previous version incorrectly returned the coverage radius
    R = 0.7 × S instead of the wall distance S/2. Per NFPA 72 §17.6.3.1.1,
    detectors shall be located not more than half the listed spacing from
    any wall. This is S/2, NOT the coverage radius R.

    For smoke at h≤3.0m: S=9.1m → wall distance = S/2 = 4.55m (NOT R=6.37m).
    """
    spacing = calculate_max_spacing(ceiling, detector_type)
    return round(spacing / 2.0, 4)


# Add to exports


def estimate_detector_count_polygon(polygon, ceiling_height_m: float, detector_type: str) -> int:
    """Estimate detector count for a polygon based on coverage area."""
    import math

    from shapely.geometry import Polygon
    # CRITICAL: Use module-level import (already from .nfpa72_models) — bare import
    # would resolve to stale root copy with wrong values.

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
    """Minimum detector count for rectangular room.

    CRITICAL FIX (Issue #10): Previous version used `get_smoke_detector_coverage_max()
    * 2` as spacing, which equals 5.5 * 2 = 11.0m at h=3.0m. This exceeds the
    NFPA 72 listed spacing of 9.1m by 21%, causing FEWER detectors to be
    computed than required — a life-safety gap in fire detection coverage.

    The correct spacing S comes from NFPA 72 Table 17.6.3.1.1 and is
    computed via calculate_coverage_radius_from_height(), which already
    applies height-adjusted reductions for higher ceilings.
    """
    import math
    # CRITICAL: Use module-level import (already from .nfpa72_models) — bare import
    # would resolve to stale root copy with wrong values.

    # Use the height-adjusted listed spacing from NFPA 72 Table 17.6.3.1.1,
    # NOT max_coverage * 2 (which is 21% too large at h=3.0m).
    spec = calculate_coverage_radius_from_height(ceiling_height_m, detector_type="smoke")
    spacing = spec.spacing_max  # 9.1m at h≤3.0m, reducing at higher ceilings

    cols = max(1, math.ceil(width_m / spacing))
    rows = max(1, math.ceil(depth_m / spacing))

    return cols * rows


__all__ = __all__ + [
    "calculate_max_spacing",
    "calculate_coverage_radius",
    "calculate_max_wall_distance",
    # Phase 7 — Variable Coverage Radius
    "CoverageSpec",
    "DetectorTypeSimple",
    "calculate_coverage_radius_from_height",
    "get_ceiling_height_warnings",
]


# ============================================================================
# PHASE 7: Variable Coverage Radius — NFPA 72-2022 Table 17.6.3.1.1
# ============================================================================

DetectorTypeSimple = Literal["smoke", "heat"]

# NFPA 72-2022 Table 17.6.3.1.1 — Height-Adjusted Detector Spacing
# =====================================================================
# V127: Import from single source of truth (fireai/constants/__init__.py)
# to eliminate divergent duplicate tables across the codebase.
# Previously, this was a hardcoded copy that could drift from the canonical values.
#
# IMPORTANT: This table stores ADJUSTED SPACING (S), NOT S/2 and NOT radius.
#
# NFPA 72 §17.6.3.1.1 defines the maximum detector spacing for each
# ceiling height bracket. As ceiling height increases, smoke has more
# time to disperse before reaching the detector, so the adjusted spacing
# DECREASES, requiring more detectors per unit area.
#
# The coverage radius R is derived from the adjusted spacing S via the
# 0.7S rule (NFPA 72 §17.7.4.2.3.1): R = 0.7 × S. This ensures that
# when detectors are placed on a square grid at spacing S, the circular
# coverage areas overlap to cover all points including grid corners.
#
# CRITICAL FIX (2026-05-18): Previous version incorrectly stored S/2
# values and called them "radius". This caused DensityOptimizer to
# receive R = S/2 = 4.55m instead of R = 0.7S = 6.37m at h=3.0m,
# resulting in over-conservative placement (too many detectors).
#
# (ceiling_height_max_meters, smoke_adjusted_spacing_m, heat_adjusted_spacing_m)
# V128: Import from CANONICAL single source of truth (fireai/constants/nfpa72.py)
# to eliminate divergent duplicate tables across the codebase.
# Previously, this was imported via fireai.constants (which had its own duplicates).
# Now imports directly from the authoritative nfpa72.py module.
from fireai.constants.nfpa72 import (
    COMBINED_HEIGHT_SPACING_TABLE as _CANONICAL_HEIGHT_TABLE,
)

_NFPA72_TABLE_17_6_3_1_1 = list(_CANONICAL_HEIGHT_TABLE)

_NFPA72_ABSOLUTE_MAX_HEIGHT = 12.2

# Fallback ADJUSTED SPACING for heights above 12.2m (beyond NFPA table).
# V130 FIX: Smoke fallback = 9.10m (flat per §17.7.3.2.3, NO height reduction).
# Heat fallback = 3.50m (conservative extrapolation from Table 17.6.3.5.1).
# Coverage radius will be computed as R = 0.7 * spacing_fallback.
_NFPA72_SMOKE_SPACING_FALLBACK = 9.10  # → R = 6.37m (flat per §17.7.3.2.3)
_NFPA72_HEAT_SPACING_FALLBACK  = 3.50  # → R = 2.45m

# Legacy aliases (deprecated — use spacing fallback constants above)
# These preserve backward compatibility for code that reads these constants.
_NFPA72_SMOKE_FALLBACK = round(0.7 * _NFPA72_SMOKE_SPACING_FALLBACK, 2)  # 6.37m (V130: was 3.64m)
_NFPA72_HEAT_FALLBACK  = round(0.7 * _NFPA72_HEAT_SPACING_FALLBACK, 2)   # 2.45m


@dataclass(frozen=True)
class CoverageSpec:
    """Structured coverage specification from NFPA 72 Table 17.6.3.1.1.

    The coverage radius R is computed from the height-adjusted spacing S
    via the NFPA 72 0.7S rule: R = 0.7 × S. This ensures that when
    detectors are placed on a square grid at spacing S, the circular
    coverage areas (radius R) overlap to cover all points including
    the corners of the grid.

    Attributes:
        radius: Coverage radius in meters (R = 0.7 × spacing).
            This is the radius of the circular coverage area used by
            DensityOptimizer for detector placement and coverage
            verification. NOT the same as wall_distance_max.
        height: Ceiling height used for the calculation.
        detector_type: "smoke" or "heat".
        area: Coverage area = pi * radius^2 (m^2).
        spacing_max: Height-adjusted maximum spacing between detectors (meters).
            This is the S value from NFPA 72 Table 17.6.3.1.1.
        wall_distance_max: Maximum distance from wall to nearest detector (meters).
            Equal to S/2 per NFPA 72 §17.6.3.1.1. NOT the coverage radius.
            Previously confused with radius (S/2 was called "radius" — now fixed).
        nfpa_ref: NFPA 72 table reference string.
        warning: Optional warning for out-of-range heights.

    """

    radius: float
    height: float
    detector_type: DetectorTypeSimple
    area: float
    spacing_max: float
    wall_distance_max: float = 0.0
    nfpa_ref: str = "NFPA 72-2022 Table 17.6.3.1.1"
    warning: Optional[str] = None


def calculate_coverage_radius_from_height(
    ceiling_height: float,
    detector_type: DetectorTypeSimple = "smoke",
) -> CoverageSpec:
    """Calculate coverage radius from ceiling height per NFPA 72 Table 17.6.3.1.1.

    Higher ceilings produce SMALLER adjusted spacings (more detectors) because
    smoke disperses more before reaching the detector — NFPA 72 §17.6.3.1.1.

    The coverage radius R is computed from the height-adjusted spacing S
    via the NFPA 72 0.7S rule: R = 0.7 × S.

    CRITICAL FIX (2026-05-18): Previous version incorrectly returned S/2
    as the "radius". S/2 is the MAXIMUM WALL DISTANCE, NOT the coverage
    radius. The correct coverage radius is R = 0.7 × S. This fix aligns
    calculate_coverage_radius_from_height() with DensityOptimizer's
    DETECTOR_RADIUS = 0.7 × MAX_SPACING_M = 6.37m (using S=9.1m, not 9.144m).

    Args:
        ceiling_height: Ceiling height in meters.
        detector_type: "smoke" or "heat".

    Returns:
        CoverageSpec with:
          - radius: Coverage radius R = 0.7 × adjusted_spacing (meters)
          - spacing_max: Height-adjusted spacing S (meters)
          - wall_distance_max: Maximum wall distance S/2 (meters)
          - area: Coverage area pi × R^2 (m^2)

    Raises:
        TypeError: If ceiling_height is None.
        ValueError: If ceiling_height is negative.

    """
    # Fix 1: Protect against None
    if ceiling_height is None:
        raise TypeError("ceiling_height must be a float, got None.")

    # V114 FIX: NaN bypasses `<= 0` guard (NaN <= 0 → False in IEEE 754).
    # A NaN ceiling height poisons every downstream Shapely geometry operation
    # and produces NaN spacing/radius/coverage — rooms appear "compliant" because
    # NaN comparisons always return False. Must use isfinite() BEFORE comparison.
    if not isinstance(ceiling_height, (int, float)) or not math.isfinite(ceiling_height):
        raise ValueError(
            f"ceiling_height must be a finite number, got {ceiling_height!r}. "
            f"NaN/Inf values bypass safety guards and corrupt all downstream calculations."
        )

    if ceiling_height <= 0:
        raise ValueError(f"ceiling_height {ceiling_height}m must be positive.")

    warning: Optional[str] = None

    if ceiling_height > _NFPA72_ABSOLUTE_MAX_HEIGHT:
        # Use conservative fallback spacing for heights beyond the table
        spacing = (
            _NFPA72_SMOKE_SPACING_FALLBACK
            if detector_type.lower() == "smoke"
            else _NFPA72_HEAT_SPACING_FALLBACK
        )
        radius = round(0.7 * spacing, 2)
        wall_dist = round(spacing / 2.0, 2)
        warning = (
            f"Ceiling height {ceiling_height}m exceeds NFPA 72 table max "
            f"({_NFPA72_ABSOLUTE_MAX_HEIGHT}m). Conservative spacing {spacing}m "
            f"(R={radius}m) applied — AHJ review required."
        )
        return CoverageSpec(
            radius=radius,
            height=ceiling_height,
            detector_type=detector_type,
            area=round(math.pi * radius ** 2, 2),
            spacing_max=round(spacing, 2),
            wall_distance_max=wall_dist,
            nfpa_ref="NFPA 72-2022 Table 17.6.3.1.1 — extrapolated beyond 12.2m",
            warning=warning,
        )

    for h_max, smoke_spacing, heat_spacing in _NFPA72_TABLE_17_6_3_1_1:
        if ceiling_height <= h_max:
            # V130 FIX: Smoke detectors use FLAT 9.1m per NFPA 72 §17.7.3.2.3.
            # NO height-based spacing reduction for smoke detectors.
            # The 1%/ft reduction (Table 17.6.3.5.1) applies to HEAT detectors ONLY.
            spacing = smoke_spacing if detector_type.lower() == "smoke" else heat_spacing
            radius = round(0.7 * spacing, 2)          # R = 0.7 × S (coverage radius)
            wall_dist = round(spacing / 2.0, 2)        # S/2 (max wall distance)
            if ceiling_height > 9.1:
                warning = "High-bay space — consider beam smoke detectors per NFPA 72 §17.7."
            return CoverageSpec(
                radius=radius,
                height=ceiling_height,
                detector_type=detector_type,
                area=round(math.pi * radius ** 2, 2),
                spacing_max=round(spacing, 2),
                wall_distance_max=wall_dist,
                warning=warning,
            )

    # exactly 12.2m — use last table entry
    # V130 FIX: Smoke = flat 9.1m per §17.7.3.2.3; Heat = 3.70m per Table 17.6.3.5.1
    spacing = _NFPA72_SMOKE_SPACING_FALLBACK if detector_type.lower() == "smoke" else 3.70
    radius = round(0.7 * spacing, 2)
    wall_dist = round(spacing / 2.0, 2)
    return CoverageSpec(
        radius=radius,
        height=ceiling_height,
        detector_type=detector_type,
        area=round(math.pi * radius ** 2, 2),
        spacing_max=round(spacing, 2),
        wall_distance_max=wall_dist,
    )


def get_ceiling_height_warnings(height: float) -> list[str]:
    """Get validation warnings for a ceiling height.

    Returns a list of warning strings. Empty list means no warnings.
    Non-throwing alternative to validate_ceiling_height (which raises).

    Args:
        height: Ceiling height in meters.

    Returns:
        List of warning strings.

    """
    # V79 FIX: NaN height produces empty warnings list (all comparisons False).
    # An empty list appears "valid" to downstream code, hiding data corruption.
    if not isinstance(height, (int, float)) or not math.isfinite(height):
        return [f"Height {height!r} is not a finite number — cannot validate."]
    warnings = []
    if height < 2.1:
        warnings.append(f"Height {height}m below habitable minimum (2.1m).")
    if height > _NFPA72_ABSOLUTE_MAX_HEIGHT:
        warnings.append(f"Height {height}m exceeds NFPA 72 table — consult AHJ.")
    if height > 9.1:
        warnings.append("High-bay: consider beam detectors per NFPA 72 §17.7.")
    return warnings


# ---------------------------------------------------------------------------
# Beam pocket correction  (NFPA 72 §17.6.3.6)
# ---------------------------------------------------------------------------

_BEAM_POCKET_DEPTH_FRACTION: float = 0.10  # 10 % of ceiling height threshold


def beam_pocket_correction_factor(
    beam_depth_m: float,
    ceiling_height_m: float,
) -> float:
    """Return spacing reduction factor when beams subdivide a ceiling.

    NFPA 72 §17.6.3.6: if beam depth > 10 % of ceiling height, spacing
    within each beam pocket is limited to the pocket width.

    Args:
        beam_depth_m:    Exposed beam depth from ceiling soffit (metres).
        ceiling_height_m: Ceiling height (metres).

    Returns:
        Factor in (0, 1] by which rated spacing should be multiplied.

    """
    # V65 FIX: Add NaN/Inf input guards per V114 pattern.
    # NaN beam_depth or ceiling_height would propagate silently through
    # the calculation, producing NaN correction factor → NaN spacing →
    # zero detectors placed in beam pockets.
    if not math.isfinite(beam_depth_m) or beam_depth_m < 0:
        raise ValueError(
            f"beam_depth_m must be finite non-negative, got {beam_depth_m!r}. "
            f"NaN/Inf inputs in beam pocket calculation produce NaN spacing."
        )
    if not math.isfinite(ceiling_height_m) or ceiling_height_m <= 0:
        raise ValueError(
            f"ceiling_height_m must be finite positive, got {ceiling_height_m!r}. "
            f"Zero/negative ceiling height is physically invalid."
        )
    depth_fraction = beam_depth_m / ceiling_height_m
    if depth_fraction <= _BEAM_POCKET_DEPTH_FRACTION:
        return 1.0
    # Linear reduction: beyond 10 % depth the factor decreases proportionally
    excess = depth_fraction - _BEAM_POCKET_DEPTH_FRACTION
    return max(0.25, 1.0 - excess * 2.0)


# ---------------------------------------------------------------------------
# Corridor spacing  (NFPA 72 §17.6.3.3)
# ---------------------------------------------------------------------------

def calculate_corridor_spacing(
    ceiling: CeilingSpec,
    detector_type: DetectorType,
    corridor_width_m: float,
) -> float:
    """NFPA 72 §17.6.3.3 — detector spacing for corridors (width ≤ 3 m).

    Detectors in narrow corridors may use the corridor width in the
    coverage radius calculation, allowing larger along-corridor spacing.

    Args:
        ceiling:          Validated ceiling specification.
        detector_type:    Detector type.
        corridor_width_m: Corridor clear width in metres.

    Returns:
        Maximum allowable along-corridor spacing in metres.

    """
    # V79 FIX: Validate corridor_width_m for NaN/Inf.
    # NaN corridor_width_m >= 3.0 → False, then NaN propagates through
    # half_width and math.sqrt, producing NaN spacing → NaN detector positions.
    if not math.isfinite(corridor_width_m) or corridor_width_m <= 0:
        raise ValueError(f"corridor_width_m must be finite positive, got {corridor_width_m!r}")
    base = calculate_max_spacing(ceiling, detector_type)
    if corridor_width_m >= 3.0:
        return base
    # §17.6.3.3: Spacing = 2 × √(R² − (W/2)²)   where R = coverage radius = 0.7×S
    # CRITICAL FIX: Use coverage radius R = 0.7 × S, NOT S/2.
    # Previous code used base/2.0 (S/2 = 4.55m) instead of 0.7×S (6.37m).
    # NFPA 72 §17.7.4.2.3.1 defines the coverage radius as R = 0.7×S.
    rated_radius = base * 0.7  # R = 0.7 × S (coverage radius, not S/2)
    half_width   = corridor_width_m / 2.0
    if rated_radius <= half_width:
        return base
    along = 2.0 * math.sqrt(rated_radius**2 - half_width**2)
    return round(min(along, base), 3)


# ---------------------------------------------------------------------------
# Duct detector spacing  (NFPA 72 §17.7.5)
# ---------------------------------------------------------------------------

_DUCT_DETECTOR_MAX_SPACING_M: float = 10.0  # NFPA 72 §17.7.5.4.2


def calculate_duct_detector_positions(
    duct: HVACDuct,
    max_spacing_m: float = _DUCT_DETECTOR_MAX_SPACING_M,
) -> List[Tuple[float, float]]:
    """Compute required detector positions along an HVAC duct centreline.

    NFPA 72 §17.7.5.4.2 requires detectors at intervals ≤ 10 m along
    supply air ducts where the duct cross-section exceeds 0.09 m².

    Args:
        duct:          HVACDuct descriptor.
        max_spacing_m: Maximum allowable detector spacing along duct (metres).

    Returns:
        List of (x, y) detector positions along the centreline.

    """
    centreline = duct.centerline
    if len(centreline) < 2:
        return [tuple(centreline[0])] if centreline else []

    # Build cumulative arc lengths along centreline
    arc_lengths: List[float] = [0.0]
    for i in range(1, len(centreline)):
        x0, y0 = centreline[i - 1]
        x1, y1 = centreline[i]
        arc_lengths.append(arc_lengths[-1] + math.hypot(x1 - x0, y1 - y0))

    total_length = arc_lengths[-1]
    if total_length <= 0:
        return [tuple(centreline[0])]

    num_intervals = math.ceil(total_length / max_spacing_m)
    positions: List[Tuple[float, float]] = []

    for k in range(num_intervals):
        target = (k + 0.5) * (total_length / num_intervals)  # midpoint of each interval
        # Interpolate along centreline
        for i in range(1, len(arc_lengths)):
            if arc_lengths[i] >= target:
                seg_start_len = arc_lengths[i - 1]
                seg_end_len   = arc_lengths[i]
                seg_len       = seg_end_len - seg_start_len
                t = (target - seg_start_len) / seg_len if seg_len > 0 else 0.0
                x0, y0 = centreline[i - 1]
                x1, y1 = centreline[i]
                x = x0 + t * (x1 - x0)
                y = y0 + t * (y1 - y0)
                positions.append((round(x, 4), round(y, 4)))
                break

    return positions


# ---------------------------------------------------------------------------
# Voltage drop check  (NFPA 72 §10.14)
# ---------------------------------------------------------------------------

def check_voltage_drop(
    supply_voltage_v: float,
    load_current_a: float,
    cable_resistance_ohm_per_m: float,
    cable_length_m: float,
    max_drop_fraction: float = 0.10,
) -> Dict[str, float]:
    """Check that voltage drop along a cable run does not exceed the limit.

    V78 FIX: Changed default from 0.15 (15%) to 0.10 (10%). 15% does not
    correspond to any NFPA 72 section. NFPA 72 §27.4.1.2 limits PLFA circuits
    (SLC/IDC) to 10% drop. NFPA 72 §10.6.4 allows NAC circuits up to 20%.
    The 10% default is the more restrictive and commonly applicable limit.
    For NAC circuits, callers should pass max_drop_fraction=0.20.

    NFPA 72 §10.6.4 requires that the voltage at the most remote device must
    be within the device's listed voltage range.

    Args:
        supply_voltage_v:          Nominal supply voltage (V).
        load_current_a:            Total load current on the run (A).
        cable_resistance_ohm_per_m: Cable resistance per unit length (Ω/m).
        cable_length_m:            One-way cable length (m).
        max_drop_fraction:         Maximum allowable voltage drop as fraction
                                   of supply (default 0.10 = 10 %).
                                   NFPA 72 §27.4.1.2 limits PLFA circuits to 10%.
                                   NFPA 72 §10.6.4 allows NAC circuits up to 20%.

    Returns:
        Dict with keys:
            drop_v       : Calculated voltage drop (V).
            drop_fraction: Drop as fraction of supply.
            compliant    : True if drop ≤ max_drop_fraction.

    """
    # V114 FIX: Input validation — NaN/Inf and negative values produce
    # false compliance (e.g., negative cable_length_m → negative drop → compliant).
    # Must validate ALL parameters before computation per agent.md Rule 5.
    for name, val in [
        ("supply_voltage_v", supply_voltage_v),
        ("load_current_a", load_current_a),
        ("cable_resistance_ohm_per_m", cable_resistance_ohm_per_m),
        ("cable_length_m", cable_length_m),
        ("max_drop_fraction", max_drop_fraction),
    ]:
        if not isinstance(val, (int, float)) or not math.isfinite(val):
            raise ValueError(
                f"{name} must be a finite number, got {val!r}. "
                f"NaN/Inf values corrupt voltage drop calculations — "
                f"NFPA 72 §10.14 compliance cannot be verified."
            )
    if supply_voltage_v <= 0:
        raise ValueError(f"supply_voltage_v must be positive, got {supply_voltage_v}")
    if cable_length_m < 0:
        raise ValueError(f"cable_length_m must be non-negative, got {cable_length_m}")
    if cable_resistance_ohm_per_m < 0:
        raise ValueError(f"cable_resistance_ohm_per_m must be non-negative, got {cable_resistance_ohm_per_m}")
    if load_current_a < 0:
        raise ValueError(f"load_current_a must be non-negative, got {load_current_a}")
    if max_drop_fraction <= 0 or max_drop_fraction > 1:
        raise ValueError(f"max_drop_fraction must be in (0, 1], got {max_drop_fraction}")

    total_resistance = cable_resistance_ohm_per_m * cable_length_m * 2  # return path
    drop_v           = load_current_a * total_resistance
    drop_fraction    = drop_v / supply_voltage_v if supply_voltage_v > 0 else float("inf")
    return {
        "drop_v":        round(drop_v, 4),
        "drop_fraction": round(drop_fraction, 6),
        "compliant":     drop_fraction <= max_drop_fraction,
    }


# ---------------------------------------------------------------------------
# Battery standby calculation  (NFPA 72 §10.6.7)
# ---------------------------------------------------------------------------

def required_battery_capacity_ah(
    standby_current_a: float,
    alarm_current_a: float,
    standby_hours: float = 24.0,
    alarm_minutes: float = 5.0,
    safety_factor: float = 1.20,
) -> float:
    """Calculate required battery capacity for a fire alarm control unit.

    NFPA 72 §10.6.7.2.1: 24 h standby + 5 min alarm (for most occupancies).

    Args:
        standby_current_a:  Quiescent load current (AMPS).
        alarm_current_a:    Full-alarm load current (AMPS).
        standby_hours:      Required standby duration (hours, minimum 24 per §10.6.7.2.1).
        alarm_minutes:      Required alarm duration (minutes).
        safety_factor:      Multiplier for aging and temperature (default 1.20).

    Returns:
        Required battery capacity in ampere-hours (Ah).

    V78 FIX: Changed parameter names from _ma to _a (Amps) for consistency
    with all other battery functions: voltage_drop.calculate_battery_backup(),
    battery_aging_derating.size_battery(), nfpa72_engine.calculate_battery().
    Using mA was a 1000× confusion trap — passing 0.5A as standby_current_ma
    computed 0.012 Ah instead of 12 Ah, potentially leaving a building without
    alarm during power outage.

    """
    # V114 FIX: Input validation — NaN/Inf and negative/zero values produce
    # impossible battery capacities (e.g., safety_factor=0 → 0 Ah → no battery).
    for name, val in [
        ("standby_current_a", standby_current_a),
        ("alarm_current_a", alarm_current_a),
        ("standby_hours", standby_hours),
        ("alarm_minutes", alarm_minutes),
        ("safety_factor", safety_factor),
    ]:
        if not isinstance(val, (int, float)) or not math.isfinite(val):
            raise ValueError(
                f"{name} must be a finite number, got {val!r}. "
                f"NaN/Inf values corrupt battery capacity calculations — "
                f"NFPA 72 §10.6.7 compliance cannot be verified."
            )
    if standby_current_a < 0:
        raise ValueError(f"standby_current_a must be non-negative, got {standby_current_a}")
    if alarm_current_a < 0:
        raise ValueError(f"alarm_current_a must be non-negative, got {alarm_current_a}")
    if standby_hours < 24.0:
        raise ValueError(
            f"standby_hours={standby_hours}h < 24h violates NFPA 72 §10.6.7.2.1 "
            f"(minimum 24h standby). Use battery_aging_derating.size_battery() "
            f"for proper handling."
        )
    if alarm_minutes <= 0:
        raise ValueError(f"alarm_minutes must be positive, got {alarm_minutes}")
    if safety_factor < 1.0:
        raise ValueError(f"safety_factor must be >= 1.0, got {safety_factor} — below 1.0 undersizes battery")

    standby_ah = standby_current_a * standby_hours
    alarm_ah   = alarm_current_a * (alarm_minutes / 60.0)
    return round((standby_ah + alarm_ah) * safety_factor, 3)


# ============================================================================
# AWG WIRE GAUGE TABLES — NEC/NFPA 70
# ============================================================================
# Resistance values from NEC Chapter 9, Table 8 (copper at 75 °C).
# V51 FIX: Corrected to NEC Table 8 DC resistance at 75°C (stranded copper).
# Old values for AWG 14/12/10 were ~18% too low (20°C values, unsafe direction).
# AWG 18/16 are solid in Table 8; all others are stranded (Class B).

AWG_RESISTANCE_TABLE: Dict[int, Dict[str, float]] = {
    # AWG: {"ohm_per_1000ft": R, "ohm_per_m": R/304.8, "metric_mm2": area, "ampacity_75c": A}
    18: {"ohm_per_1000ft": 7.770, "ohm_per_m": 0.02549, "metric_mm2": 0.823, "ampacity_75c": 14},
    16: {"ohm_per_1000ft": 4.890, "ohm_per_m": 0.01604, "metric_mm2": 1.31,  "ampacity_75c": 18},
    14: {"ohm_per_1000ft": 3.070, "ohm_per_m": 0.01007, "metric_mm2": 2.08,  "ampacity_75c": 20},
    12: {"ohm_per_1000ft": 1.930, "ohm_per_m": 0.00633, "metric_mm2": 3.31,  "ampacity_75c": 25},
    10: {"ohm_per_1000ft": 1.210, "ohm_per_m": 0.00397, "metric_mm2": 5.26,  "ampacity_75c": 35},
}

# Available AWG gauges for auto-selection (smallest to largest)
# V131 FIX: NEC Article 760.71 and NFPA 72 §27.4.1 require minimum AWG 14
# for fire alarm circuit wiring. AWG 18 and 16 are NOT permitted for FA circuits.
# They remain in AWG_RESISTANCE_TABLE for reference/lookup but are excluded from
# auto-selection to prevent dangerously thin wire from being specified.
_FA_MIN_AWG: int = 14  # Minimum AWG permitted for fire alarm circuits per NEC 760.71
AWG_GAUGES: List[int] = sorted(
    [g for g in AWG_RESISTANCE_TABLE if g >= _FA_MIN_AWG],
    reverse=True
)  # [14, 12, 10]

# ============================================================================
# NAC DEVICE CURRENT DRAW — NFPA 72 §18.5 + Manufacturer Data
# ============================================================================
# Typical steady-state and inrush currents for common notification appliances.
# Inrush factor: strobes draw 2-3× their rated current during the first
# 50-200 ms of activation.  For voltage drop calculations under alarm
# conditions (NFPA 72 §10.14.1), inrush must be considered.

DEVICE_CURRENT_DRAW: Dict[str, Dict[str, float]] = {
    # device_type: {"steady_a": steady-state, "inrush_a": peak inrush, "inrush_factor": multiplier}
    "strobe_15cd":       {"steady_a": 0.15, "inrush_a": 0.38, "inrush_factor": 2.5},
    "strobe_30cd":       {"steady_a": 0.22, "inrush_a": 0.55, "inrush_factor": 2.5},
    "strobe_60cd":       {"steady_a": 0.35, "inrush_a": 0.88, "inrush_factor": 2.5},
    "strobe_75cd":       {"steady_a": 0.45, "inrush_a": 1.13, "inrush_factor": 2.5},
    "horn":              {"steady_a": 0.25, "inrush_a": 0.50, "inrush_factor": 2.0},
    "horn_strobe_15cd":  {"steady_a": 0.40, "inrush_a": 1.00, "inrush_factor": 2.5},
    "horn_strobe_30cd":  {"steady_a": 0.47, "inrush_a": 1.18, "inrush_factor": 2.5},
    "speaker_4w_70v":    {"steady_a": 0.057, "inrush_a": 0.057, "inrush_factor": 1.0},
    "speaker_8w_70v":    {"steady_a": 0.114, "inrush_a": 0.114, "inrush_factor": 1.0},
    "bell_6in":          {"steady_a": 0.15, "inrush_a": 0.30, "inrush_factor": 2.0},
    "bell_10in":         {"steady_a": 0.25, "inrush_a": 0.50, "inrush_factor": 2.0},
}

# Maximum NAC circuit current (typical panel limit)
NAC_MAX_CURRENT_A: float = 3.0

# Minimum voltage at the most remote device (NFPA 72 §10.14.1)
# For 24 VDC systems, the typical minimum operating voltage is 16 VDC.
DEVICE_MIN_OPERATING_VOLTAGE_V: float = 16.0


# ---------------------------------------------------------------------------
# Inrush Current Calculation — NFPA 72 §10.14.1
# ---------------------------------------------------------------------------

def calculate_inrush_current(
    device_type: str,
    quantity: int,
) -> Dict[str, float]:
    """Calculate steady-state and inrush (worst-case) current for NAC devices.

    NFPA 72 §10.14.1 requires that voltage at the most remote device be
    sufficient "under alarm conditions."  When multiple strobes activate
    simultaneously, their combined inrush current can cause a momentary
    voltage sag that drops below the device minimum operating voltage,
    causing devices at the end of the circuit to fail to operate.

    This is a REAL safety issue: a hotel fire where 50 strobes activate
    at once can cause the inrush current to sag the voltage below 16 VDC
    at the last device, meaning NO visual alarm in that room.

    Args:
        device_type: Key in DEVICE_CURRENT_DRAW (e.g. "strobe_15cd").
        quantity: Number of devices on the circuit.

    Returns:
        Dict with:
            steady_total_a:     Total steady-state current (A).
            inrush_total_a:     Total peak inrush current (A).
            inrush_factor:      Peak-to-steady multiplier.
            device_type:        Echo of input device_type.
            quantity:           Echo of input quantity.

    """
    spec = DEVICE_CURRENT_DRAW.get(device_type)
    if spec is None:
        # V65 FIX: Unknown device type — log warning instead of silent default.
        # Old code silently used 0.25A/0.63A which could significantly underestimate
        # actual current draw for high-current devices (e.g., 110cd strobes at 0.45A).
        # This could lead to NAC circuit overload or voltage sag at remote devices.
        import logging
        logger = logging.getLogger(__name__)
        logger.warning(
            f"Unknown device type '{device_type}' — using conservative defaults "
            f"(0.25A steady / 0.63A inrush). VERIFY actual current draw with "
            f"manufacturer datasheet. Incorrect current assumptions can cause "
            f"devices to fail during alarm (NFPA 72 §10.14.1)."
        )
        return {  # type: ignore[dict-item]
            "steady_total_a": 0.25 * quantity,
            "inrush_total_a": 0.63 * quantity,
            "inrush_factor": 2.5,
            "device_type": device_type,  # type: ignore[dict-item]
            "quantity": quantity,
        }

    steady = spec["steady_a"] * quantity
    inrush = spec["inrush_a"] * quantity
    return {  # type: ignore[dict-item]
        "steady_total_a": round(steady, 4),
        "inrush_total_a": round(inrush, 4),
        "inrush_factor": spec["inrush_factor"],
        "device_type": device_type,  # type: ignore[dict-item]
        "quantity": quantity,
    }


# ---------------------------------------------------------------------------
# NAC Circuit Loading — NFPA 72 §18.5
# ---------------------------------------------------------------------------

def calculate_nac_loading(
    devices: List[Dict[str, Any]],
    panel_voltage_v: float = 24.0,
) -> Dict[str, Any]:
    """Calculate total NAC circuit loading for mixed device types.

    Aggregates steady-state and inrush currents across all devices on a
    single NAC circuit, then checks against the 3 A panel limit.

    Args:
        devices: List of dicts, each with:
            - "device_type": key in DEVICE_CURRENT_DRAW
            - "quantity": count of that device type
        panel_voltage_v: Panel nominal voltage (default 24 VDC).

    Returns:
        Dict with:
            steady_total_a:   Total steady-state current (A).
            inrush_total_a:   Total peak inrush current (A).
            within_panel_limit: True if steady_total <= NAC_MAX_CURRENT_A.
            device_details:   Per-type breakdown.
            warnings:         Advisory messages.

    """
    steady_total = 0.0
    inrush_total = 0.0
    details: List[Dict[str, Any]] = []
    warnings: List[str] = []

    for dev in devices:
        dtype = dev.get("device_type", "horn")
        qty = dev.get("quantity", 1)
        result = calculate_inrush_current(dtype, qty)
        steady_total += result["steady_total_a"]
        inrush_total += result["inrush_total_a"]
        details.append(result)

    within_limit = steady_total <= NAC_MAX_CURRENT_A

    if not within_limit:
        warnings.append(
            f"NAC circuit overloaded: {steady_total:.2f} A > {NAC_MAX_CURRENT_A:.1f} A limit. "
            f"Split into multiple NAC circuits or reduce device count."
        )

    if inrush_total > NAC_MAX_CURRENT_A * 1.5:
        warnings.append(
            f"High inrush current ({inrush_total:.2f} A) may cause voltage sag "
            f"at remote devices. Verify voltage drop under inrush conditions."
        )

    return {
        "steady_total_a": round(steady_total, 4),
        "inrush_total_a": round(inrush_total, 4),
        "within_panel_limit": within_limit,
        "device_details": details,
        "warnings": warnings,
        "nfpa_reference": "NFPA 72 §18.5 / §10.14.1",
    }


# ---------------------------------------------------------------------------
# Automatic AWG Wire Gauge Selection — NEC Art. 760 + NFPA 72 §10.14
# ---------------------------------------------------------------------------

def auto_select_awg(
    supply_voltage_v: float,
    load_current_a: float,
    cable_length_m: float,
    max_drop_fraction: float = 0.10,
    min_device_voltage_v: float = 16.0,
) -> Dict[str, Any]:
    """Automatically select the smallest AWG wire gauge that satisfies voltage drop.

    Evaluates each AWG gauge from smallest permitted (14) to largest (10), and
    returns the first gauge where the voltage at the most remote device stays
    above min_device_voltage_v under both steady-state and the specified max
    drop fraction.

    This bridges the gap between check_voltage_drop() (which requires manual
    resistance input) and generate_cable_boq() (which had no AWG sizing).
    Now BOQ generation can call auto_select_awg() to determine the correct
    wire gauge for each circuit.

    Args:
        supply_voltage_v: Panel supply voltage (V), typically 24 VDC.
        load_current_a:   Total circuit load current (A).
        cable_length_m:   One-way cable length (m).
        max_drop_fraction: Maximum allowable voltage drop as fraction (default 0.10).
                         NFPA 72 §27.4.1.2 limits PLFA circuits to 10%.
        min_device_voltage_v: Minimum device operating voltage (default 16 VDC).

    Returns:
        Dict with:
            selected_awg:     Chosen AWG gauge (int), or None if none works.
            resistance_ohm_per_m: Resistance of selected gauge.
            voltage_at_device: Voltage at most remote device (V).
            drop_v:           Voltage drop (V).
            drop_fraction:    Drop as fraction of supply.
            compliant:        True if voltage at device >= min_device_voltage_v.
            all_candidates:   Results for every gauge evaluated.

    """
    all_candidates: List[Dict[str, Any]] = []
    selected = None

    for awg in AWG_GAUGES:
        entry = AWG_RESISTANCE_TABLE[awg]
        r_per_m = entry["ohm_per_m"]

        # Check voltage drop using existing function
        vd = check_voltage_drop(
            supply_voltage_v=supply_voltage_v,
            load_current_a=load_current_a,
            cable_resistance_ohm_per_m=r_per_m,
            cable_length_m=cable_length_m,
            max_drop_fraction=max_drop_fraction,
        )

        voltage_at_device = supply_voltage_v - vd["drop_v"]
        compliant = (
            vd["compliant"]
            and voltage_at_device >= min_device_voltage_v
        )

        candidate = {
            "awg": awg,
            "resistance_ohm_per_m": r_per_m,
            "metric_mm2": entry["metric_mm2"],
            "ampacity_75c": entry["ampacity_75c"],
            "drop_v": vd["drop_v"],
            "drop_fraction": vd["drop_fraction"],
            "voltage_at_device": round(voltage_at_device, 4),
            "compliant": compliant,
        }
        all_candidates.append(candidate)

        # Select first compliant gauge (largest AWG = smallest wire)
        if compliant and selected is None:
            selected = candidate

    if selected is None:
        return {
            "selected_awg": None,
            "resistance_ohm_per_m": None,
            "voltage_at_device": None,
            "drop_v": None,
            "drop_fraction": None,
            "compliant": False,
            "all_candidates": all_candidates,
            "error": (
                f"No AWG gauge satisfies voltage drop constraint "
                f"(supply={supply_voltage_v}V, load={load_current_a}A, "
                f"length={cable_length_m}m, max_drop={max_drop_fraction*100:.0f}%). "
                f"Reduce circuit length or split into multiple circuits."
            ),
        }

    return {
        "selected_awg": selected["awg"],
        "resistance_ohm_per_m": selected["resistance_ohm_per_m"],
        "voltage_at_device": selected["voltage_at_device"],
        "drop_v": selected["drop_v"],
        "drop_fraction": selected["drop_fraction"],
        "compliant": True,
        "all_candidates": all_candidates,
    }
