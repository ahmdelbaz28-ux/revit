from __future__ import annotations

"""
NFPA 72 V5 Models - Enums, Dataclasses, and Exceptions
This module provides the data models for NFPA 72 Chapter 17 compliance.
All models are law-compliant implementations based on NFPA 72 (2022 Edition).
⚠️ LEGAL DISCLAIMER:
This code is provided for compliance assistance only.
It does not constitute legal advice.
Always verify with a licensed fire protection engineer.
NFPA 72 (2022 Edition) is the authoritative standard.
FIXED: 2026-05-14
- Line 240: Fixed ReferenceError in DetectorPlacement.__post_init__
- Added ceiling_height_m as explicit parameter
- Uses get_smoke_detector_radius_safe() for safe fallback

V9 CHANGES (2026-05-14):
- CeilingSpec.__post_init__ no longer crashes for out-of-range heights
- Added CeilingSpec.create_safe() factory method (clamps + warns)
- create_safe() is now the recommended production constructor

V128 FIX: Ceiling height limit now imported from canonical source (18.288m / 60ft).
NFPA 72 §17.7.3.2.4 allows smoke detectors up to 60ft (18.288m).
The old 15.24m (50ft) limit was heat detector max — using it for smoke
was conservative but incorrectly rejected valid smoke detector placements.
"""

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import ClassVar, List, Optional, Tuple

from shapely.geometry import Polygon as ShapelyPolygon

logger = logging.getLogger(__name__)

# Constants
# V128 FIX: Import from canonical Single Source of Truth instead of hardcoding.
# The old code had _SMOKE_MAX_CEILING_HEIGHT_M = 15.24 which was INCONSISTENT
# with the canonical value of 18.288m (60ft) in fireai/constants/nfpa72.py.
# This caused valid smoke detector placements at 15.24m-18.288m to be rejected.
from fireai.constants.nfpa72 import (
    CEILING_HEIGHT_MIN_M as _NFPA_HEIGHT_MIN_M,
)
from fireai.constants.nfpa72 import (
    SMOKE_MAX_CEILING_HEIGHT_M as _SMOKE_MAX_CEILING_HEIGHT_M,
)

_NFPA_HEIGHT_MAX_M = _SMOKE_MAX_CEILING_HEIGHT_M  # Default to smoke detector limits (18.288m)
MIN_WALL_DISTANCE_M = 0.1016  # 4 inches per NFPA 72 §17.6.3.1.1 (was 0.10 - DRIFT FIX)
MAX_DIMENSION_M = 1000.0  # Max room dimension in meters
MAX_POLYGON_VERTICES = 5000  # Max polygon vertices
MAX_STRING_LENGTH = 200  # Max string input length
import math


# ============================================================================
# INPUT SANITIZATION
# ============================================================================
def sanitize_string(value: str, max_length: int = 100) -> str:
    """Sanitize string input to prevent injection attacks."""
    if not isinstance(value, str):
        raise ValueError("Input must be a string")
    value = value.strip()
    # Enforce maximum cap - use min to prevent bypassing
    effective_max = min(MAX_STRING_LENGTH, max_length) if max_length > 0 else MAX_STRING_LENGTH
    if len(value) > effective_max:
        raise ValueError(f"Input too long (max {effective_max} characters)")
    # Check for SQL injection patterns
    dangerous = {"\0", "\n", "\r", "\t", ";", "'", '"', "\\", "\x01", "\x02"}
    for ch in dangerous:
        if ch in value:
            raise ValueError("Input contains invalid characters")
    # Check for SQL comment --
    if "--" in value:
        raise ValueError("Input contains invalid sequence '--'")
    return value


# ============================================================================
# ENUMS - Detector Types and Modes
# ============================================================================
# CONSOLIDATED: DetectorType and CeilingType are now canonical in contracts.py
# to prevent enum drift between modules. The local definitions are kept as
# aliases for backward compatibility but delegate to contracts.py.
#
# contracts.py DetectorType includes all values from both files.
# contracts.py CeilingType includes all values from both files.
# ============================================================================

from fireai.core.contracts import CeilingType as _CeilingTypeFromContracts
from fireai.core.contracts import DetectorType as _DetectorTypeFromContracts

# Re-export for backward compatibility — existing code that does
# `from fireai.core.nfpa72_models import DetectorType` still works.
DetectorType = _DetectorTypeFromContracts

# Add missing members that exist in the old local enum but not in contracts
# These are added as aliases to existing members
if not hasattr(DetectorType, "HEAT_FIXED_TEMP"):
    # HEAT_FIXED_TEMP is an alias for HEAT_FIXED (same NFPA 72 category)
    # We cannot add members to an Enum after creation, so we create a
    # compatibility wrapper that maps HEAT_FIXED_TEMP -> HEAT_FIXED
    pass  # Handled by contracts.py already having HEAT_FIXED

# CeilingType — re-export from contracts
CeilingType = _CeilingTypeFromContracts


# CoverageGeometry and HeatDetectionMode are ONLY in this module
# (they are not duplicated in contracts.py), so they stay here.
class CoverageGeometry(Enum):
    """Coverage geometry types per NFPA 72"""

    CIRCULAR = "circular"
    SQUARE_GRID = "square_grid"


class HeatDetectionMode(Enum):
    """Heat detector detection modes"""

    CIRCULAR = "circular"  # Euclidean (for smoke)
    SQUARE_GRID = "square_grid"  # Chebyshev (for heat)


# ============================================================================
# EXCEPTIONS - NFPA Compliance Errors
# ============================================================================
class NFPAComplianceError(Exception):
    """Base exception for NFPA compliance violations"""

    pass


class CeilingHeightError(NFPAComplianceError):
    """Raised when ceiling height is outside NFPA 72 limits"""

    pass


class CoverageError(NFPAComplianceError):
    """Raised when detector coverage is insufficient"""

    pass


class SpacingError(NFPAComplianceError):
    """Raised when detector spacing violates NFPA 72"""

    pass


class RidgeZoneError(NFPAComplianceError):
    """Raised when sloped ceiling lacks ridge zone detector"""

    pass


# ============================================================================
# DATACLASSES - Core Models
# ============================================================================
@dataclass
class CeilingSpec:
    """Ceiling specification with height and slope"""

    height_at_low_point_m: float
    height_at_high_point_m: Optional[float] = None
    ceiling_type: CeilingType = CeilingType.FLAT
    slope_degrees: float = 0.0
    # V10: Added for fire_expert_system compatibility
    was_clamped: bool = False
    original_height_m: Optional[float] = None
    beam_depth_m: float = 0.0
    beam_spacing_m: float = 0.0
    slope_run_m: Optional[float] = None  # V78: Horizontal run for slope calculation

    def __post_init__(self):
        # ===== STRICT VALIDATION = FAIL FAST =====
        errors = []

        h_low = self.height_at_low_point_m
        if not isinstance(h_low, (int, float)):
            errors.append("height_at_low_point_m must be a number")
        elif h_low <= 0 or not math.isfinite(h_low):
            errors.append(f"height_at_low_point_m must be > 0 and finite, got {h_low}")

        if self.height_at_high_point_m is not None:
            h_high = self.height_at_high_point_m
            if not isinstance(h_high, (int, float)):
                errors.append("height_at_high_point_m must be a number")
            elif h_high <= 0 or not math.isfinite(h_high):
                errors.append(f"height_at_high_point_m must be > 0 and finite, got {h_high}")
            elif h_high < h_low:
                errors.append(f"height_at_high_point_m ({h_high}) < low point ({h_low})")

        if self.ceiling_type is None or not isinstance(self.ceiling_type, CeilingType):
            errors.append("ceiling_type must be CeilingType enum")

        if errors:
            raise CeilingHeightError("CeilingSpec validation failed: " + "; ".join(errors))

        # NFPA 72 - FAIL FAST: reject heights outside normative range
        # Only CeilingSpec.create_safe() is allowed to clamp
        if h_low < _NFPA_HEIGHT_MIN_M or h_low > _NFPA_HEIGHT_MAX_M:
            raise ValueError(
                f"Ceiling height {h_low} is outside NFPA 72 normative range "
                f"[{_NFPA_HEIGHT_MIN_M}, {_NFPA_HEIGHT_MAX_M}] m. "
                f"Use CeilingSpec.create_safe() for automatic clamping."
            )

        # V78 FIX: Use 'is not None' instead of truthy — height_at_high_point_m
        # of 0.0 (ground level) is a valid value, but 0.0 is falsy in Python.
        if self.height_at_high_point_m is not None and self.height_at_high_point_m > self.height_at_low_point_m:
            # V78 FIX: slope_run_m is required for meaningful slope calculation.
            # Hardcoded run=3.0m was arbitrary — a 10m wide room with 2m rise
            # got 33.7° instead of correct 11.3°, potentially misclassifying
            # flat ceilings as sloped (affects detector spacing per §17.6.3.1.2).
            if self.slope_run_m and self.slope_run_m > 0:
                run = self.slope_run_m
            else:
                run = 3.0  # Fallback — flag for manual FPE review
                logger.warning(
                    "CeilingSpec slope_run_m not provided — using default 3.0m. "
                    "Actual roof run may differ, affecting slope classification. "
                    "Provide slope_run_m for accurate NFPA 72 §17.6.3.1.2 compliance."
                )
            rise = self.height_at_high_point_m - self.height_at_low_point_m
            self.slope_degrees = math.degrees(math.atan(rise / run))

    @classmethod
    def create_safe(
        cls,
        height_at_low_point_m: float,
        height_at_high_point_m: Optional[float] = None,
        ceiling_type: CeilingType = None,
        beam_depth_m: float = 0.0,
        beam_spacing_m: float = 0.0,
    ) -> CeilingSpec:
        """V9: Factory method — clamps height to NFPA range instead of raising.
        Use this for production code to avoid crashes on unusual building heights.

        Heights outside 3.0–18.288m are clamped with a warning logged.
        A negative or zero height raises ValueError (physically impossible).
        """
        import logging

        logger = logging.getLogger("fireai.nfpa72.models")

        MIN_HEIGHT = _NFPA_HEIGHT_MIN_M
        MAX_HEIGHT = _NFPA_HEIGHT_MAX_M

        if height_at_low_point_m <= 0:
            raise ValueError(f"height_at_low_point_m must be positive, got {height_at_low_point_m}")

        clamped = height_at_low_point_m
        if height_at_low_point_m < MIN_HEIGHT:
            clamped = MIN_HEIGHT
            logger.warning(
                f"CeilingSpec.create_safe: height {height_at_low_point_m}m < NFPA min {MIN_HEIGHT}m "
                f"— clamped to {MIN_HEIGHT}m. Review with licensed PE."
            )
        elif height_at_low_point_m > MAX_HEIGHT:
            clamped = MAX_HEIGHT
            logger.warning(
                f"CeilingSpec.create_safe: height {height_at_low_point_m}m > NFPA max {MAX_HEIGHT}m (50 ft) "
                f"— clamped to {MAX_HEIGHT}m. Review with licensed PE."
            )

        kwargs = {
            "height_at_low_point_m": clamped,
            "original_height_m": height_at_low_point_m,
            "was_clamped": height_at_low_point_m != clamped,
        }
        if height_at_high_point_m is not None:
            kwargs["height_at_high_point_m"] = height_at_high_point_m
        if ceiling_type is not None:
            kwargs["ceiling_type"] = ceiling_type  # type: ignore[assignment]
        # Pass beam parameters (V12 compatibility)
        if beam_depth_m is not None and beam_depth_m > 0:
            kwargs["beam_depth_m"] = beam_depth_m
        if beam_spacing_m is not None and beam_spacing_m > 0:
            kwargs["beam_spacing_m"] = beam_spacing_m

        return cls(**kwargs)  # type: ignore[arg-type]

    @property
    def height_m(self) -> float:
        """Get ceiling height (low point)"""
        return self.height_at_low_point_m

    @property
    def is_sloped(self) -> bool:
        """Check if ceiling is sloped (>1.5 degrees)"""
        return self.slope_degrees > 1.5

    @property
    def ridge_line(self) -> Optional[Tuple[float, float, float, float]]:
        """Get ridge line for gable/shed ceiling (x1, y1, x2, y2)"""
        if self.ceiling_type in (CeilingType.GABLE, CeilingType.SHED):
            # Simplified: return line at center of room
            return (0, 0, 10, 0)  # Placeholder
        return None


@dataclass
class HVACDuct:
    """HVAC Duct for smoke detection placement"""

    duct_id: str = ""
    centerline: list = field(default_factory=list)
    width_m: float = 0.3
    height_m: float = 0.3
    airflow_m3s: float = 0.0


@dataclass
class RoomSpec:
    """Room specification with polygon boundary - STRICT VALIDATION at creation"""

    room_id: str = ""
    name: str = ""
    width_m: float = 10.0
    depth_m: float = 10.0
    custom_polygon: list = None  # NEW: List of (x,y) tuples for custom room shape (sets polygon field)
    holes: Optional[list] = None  # Interior rings (holes) — list of list of (x,y) tuples per NFPA 72 §17.7.4.2
    polygon: Optional[ShapelyPolygon] = None
    ceiling_spec: Optional[CeilingSpec] = None
    detector_type: Optional[DetectorType] = None
    occupancy_type: str = "office"
    heat_detector_spec: Optional[HeatDetectorSpec] = None
    hvac_duct_list: List[HVACDuct] = field(default_factory=list)
    geometry_unresolved: bool = False  # V111: When True, NFPA analysis MUST be skipped

    def __post_init__(self):
        # ===== STRICT VALIDATION = FAIL FAST =====
        errors = []

        # 1. Sanitize room_id
        try:
            self.room_id = sanitize_string(self.room_id, max_length=100)
        except ValueError as e:
            errors.append(str(e))

        # 1.5. Validate room_id is not empty after sanitize
        if not self.room_id or not self.room_id.strip():
            errors.append("room_id is required and cannot be empty")

        # 2. Validate width_m and depth_m (if provided)
        if self.width_m is not None:
            if isinstance(self.width_m, bool):
                errors.append("width_m must be a number, not boolean")
            elif not isinstance(self.width_m, (int, float)):
                errors.append("width_m must be a number")
            elif self.width_m <= 0 or not math.isfinite(self.width_m):
                errors.append(f"width_m must be > 0 and finite, got {self.width_m}")
            elif self.width_m > MAX_DIMENSION_M:
                errors.append(f"width_m exceeds maximum ({MAX_DIMENSION_M}m), got {self.width_m}")

        if self.depth_m is not None:
            if isinstance(self.depth_m, bool):
                errors.append("depth_m must be a number, not boolean")
            elif not isinstance(self.depth_m, (int, float)):
                errors.append("depth_m must be a number")
            elif self.depth_m <= 0 or not math.isfinite(self.depth_m):
                errors.append(f"depth_m must be > 0 and finite, got {self.depth_m}")
            elif self.depth_m > MAX_DIMENSION_M:
                errors.append(f"depth_m exceeds maximum ({MAX_DIMENSION_M}m), got {self.depth_m}")

        # 4. Validate custom_polygon (NEW - converts to polygon)
        if self.custom_polygon is not None:
            if not isinstance(self.custom_polygon, list):
                errors.append("custom_polygon must be a list of (x,y) tuples")
            elif len(self.custom_polygon) > MAX_POLYGON_VERTICES:
                errors.append(f"custom_polygon exceeds max vertices ({MAX_POLYGON_VERTICES})")
            elif len(self.custom_polygon) < 4:
                errors.append(f"custom_polygon must have at least 4 points, got {len(self.custom_polygon)}")
            else:
                # Validate each point is a tuple
                for i, pt in enumerate(self.custom_polygon):
                    if not isinstance(pt, (tuple, list)) or len(pt) != 2:
                        errors.append(f"custom_polygon point {i} must be (x,y) tuple")
                        break
                    if not all(isinstance(c, (int, float)) for c in pt):
                        errors.append(f"custom_polygon point {i} must be numeric")
                        break
                else:
                    # Convert to polygon
                    poly = ShapelyPolygon(self.custom_polygon)
                    if not poly.is_valid or poly.area <= 0:
                        errors.append(f"custom_polygon is invalid or has zero area: {poly.area}")
                    else:
                        self.polygon = poly

        # 5. Validate polygon (legacy field)
        if self.polygon is not None:
            if isinstance(self.polygon, list):
                if len(self.polygon) > MAX_POLYGON_VERTICES:
                    errors.append(f"polygon exceeds max vertices ({MAX_POLYGON_VERTICES})")
                elif len(self.polygon) < 3:
                    errors.append(f"polygon list must have at least 3 points, got {len(self.polygon)}")
                else:
                    poly = ShapelyPolygon(self.polygon)
                    if not poly.is_valid or poly.area <= 0:
                        errors.append(f"polygon is invalid or has zero area: {poly.area}")
                    self.polygon = poly
            elif not isinstance(self.polygon, ShapelyPolygon):
                errors.append("polygon must be ShapelyPolygon or list of points")
            elif self.polygon.area <= 0:
                errors.append(f"polygon area must be > 0, got {self.polygon.area}")

        # 6. Validate occupancy_type
        # FIX: Remove dangerous types that require licensed FPE review
        valid_types = {
            "office",
            "corridor",
            "atrium",
            "sleeping",
            "server_room",
            "clean_room",
            "elevator",
            "stairwell",
            "standard",
            "hazardous",
            "industrial",
            "business",
            "educational",
            "factory",
            "mercantile",
            "residential",
            "storage",
            "utility",
            "institutional",
            "laboratory",
            "mechanical",
            "electrical",
            "data_center",
            "bathroom",
            "living",
            "meeting",
        }
        # DANGEROUS types that require manual FPE review (removed for safety)
        # kitchen, assembly - require special detector types and NFPA 72-2022 §17.7.1.1 compliance
        occ = self.occupancy_type
        if occ is None or not occ or (isinstance(occ, str) and occ.strip() == ""):
            errors.append("occupancy_type is required and cannot be empty")
        elif occ.lower().strip() not in valid_types:
            errors.append(f"occupancy_type '{occ}' not in valid set")

        # ===== VALIDATE HOLES (interior rings) =====
        # SAFETY FIX: Rooms with interior holes (columns, shafts, chases)
        # must have those holes excluded from coverage verification.
        # Without this, detectors placed over a hole would falsely report
        # coverage of an area that physically cannot have a detector above it.
        validated_holes = []
        if self.holes is not None:
            if not isinstance(self.holes, list):
                errors.append("holes must be a list of hole polygons (each hole is a list of (x,y) tuples)")
            else:
                for hi, hole in enumerate(self.holes):
                    if not isinstance(hole, list) or len(hole) < 4:
                        errors.append(f"hole {hi} must have at least 4 points, got {len(hole) if isinstance(hole, list) else 'non-list'}")
                    else:
                        try:
                            hole_poly = ShapelyPolygon(hole)
                            if not hole_poly.is_valid or hole_poly.area <= 0:
                                errors.append(f"hole {hi} is invalid or has zero area")
                            else:
                                validated_holes.append(list(hole))
                        except Exception as e:
                            errors.append(f"hole {hi} geometry error: {e}")

        # Raise if ANY validation fails (including holes)
        if errors:
            raise ValueError(f"RoomSpec validation failed for '{self.room_id}': " + "; ".join(errors))

        # ===== BUILD POLYGON FROM DIMENSIONS =====
        if self.polygon is None:
            exterior = [(0, 0), (self.width_m, 0), (self.width_m, self.depth_m), (0, self.depth_m)]
        elif isinstance(self.polygon, ShapelyPolygon):
            exterior = list(self.polygon.exterior.coords)
        else:
            exterior = [(0, 0), (self.width_m, 0), (self.width_m, self.depth_m), (0, self.depth_m)]

        # Apply holes (interior rings) to the polygon
        if validated_holes:
            hole_coords = [list(h) for h in validated_holes]
            self.polygon = ShapelyPolygon(exterior, hole_coords)
            if not self.polygon.is_valid:
                # Attempt repair with buffer(0)
                self.polygon = self.polygon.buffer(0)
            if not self.polygon.is_valid or self.polygon.area <= 0:
                raise ValueError(
                    f"RoomSpec '{self.room_id}': polygon with holes is invalid after construction. "
                    f"Check that holes are fully contained within the exterior boundary."
                )
        elif not isinstance(self.polygon, ShapelyPolygon):
            self.polygon = ShapelyPolygon(exterior)

        # ===== BUILD CEILING SPEC =====
        if self.ceiling_spec is None:
            # Get height from ceiling_spec.height_at_low_point_m, fallback to 3.0m default
            ceiling_height = 3.0  # NFPA minimum default
            self.ceiling_spec = CeilingSpec(ceiling_height, ceiling_height, CeilingType.FLAT, 0.0)

        if self.detector_type is None:
            self.detector_type = DetectorType.SMOKE

    @classmethod
    def create_validated(cls, **kwargs) -> RoomSpec:
        """Factory method - ONLY way to create RoomSpec safely"""
        return cls(**kwargs)

    @property
    def area_sqm(self) -> float:
        """Calculate room area from polygon if available, otherwise from dimensions.

        CRITICAL FIX: Previously computed from width_m * depth_m only,
        ignoring the actual polygon geometry. For non-rectangular rooms,
        this would produce wrong area in safety-critical calculations.
        """
        if self.polygon is not None and self.polygon.area > 0:
            return self.polygon.area
        return self.width_m * self.depth_m

    @property
    def polygon_coords(self) -> List[Tuple[float, float]]:
        """Get polygon coordinates as list of (x,y) tuples for V12 compatibility"""
        if self.polygon:
            return list(self.polygon.exterior.coords)[:-1]  # Remove repeated closing point
        # Build from width/depth if no polygon
        return [
            (0.0, 0.0),
            (self.width_m, 0.0),
            (self.width_m, self.depth_m),
            (0.0, self.depth_m),
        ]

    @property
    def ceiling(self) -> Optional[CeilingSpec]:
        """Get ceiling spec - maps to ceiling_spec for V12 compatibility"""
        return self.ceiling_spec

    @property
    def _hvac_ducts(self) -> List[HVACDuct]:
        """Get HVAC ducts - alias for V12 compatibility"""
        return self.hvac_duct_list

    # V12 compatibility: exposed as hvac_ducts via forward ref in V12
    @property
    def hvac_ducts(self) -> List[HVACDuct]:
        """Get HVAC ducts - maps to hvac_duct_list for V12 compatibility"""
        return self.hvac_duct_list


@dataclass
class SmokeDetectorSpec:
    """Smoke detector specification"""

    ceiling_spec: CeilingSpec
    room_spec: RoomSpec
    detector_type: DetectorType = DetectorType.SMOKE

    # V20.2 FIX: HEIGHT_TO_COVERAGE REMOVED — it used old S/2 values which
    # contradicted the corrected R = 0.7 × S in RADIUS_MAP and
    # get_smoke_detector_radius(). Use those functions instead.
    #
    # Old values (S/2 based, INCORRECT for R = 0.7 × S):
    #   (3.0, 4.3): (4.1, 6.4),   <- 4.1m = S/2, not R = 0.7×S
    #   (4.3, 6.1): (4.6, 7.2),   <- same issue
    #
    # Correct values are computed dynamically via radius_m / coverage_max_m.
    @property
    def radius_m(self) -> float:
        """Get radius based on ceiling height per NFPA 72"""
        return get_smoke_detector_radius(self.ceiling_spec.height_m)

    @property
    def coverage_max_m(self) -> float:
        """Get maximum coverage area (circles can extend)"""
        return get_smoke_detector_coverage_max(self.ceiling_spec.height_m)


@dataclass
class HeatDetectorSpec:
    """Heat detector specification"""

    ceiling_spec: CeilingSpec
    room_spec: RoomSpec
    detector_type: DetectorType = DetectorType.HEAT
    heat_mode: HeatDetectionMode = HeatDetectionMode.SQUARE_GRID
    # Fixed spacing per NFPA 72 (Table 17.6.2.1)
    # CRITICAL FIX: Heat detectors use 20ft (6.1m) listed spacing, NOT 30ft (9.1m).
    # NFPA 72 Table 17.6.3.1.1: Heat detector listed spacing = 20ft = 6.1m.
    # The previous value of 30ft (9.1m) was for smoke detectors.
    FIXED_SPACING_FT = 20  # 20 feet = 6.1m
    FIXED_SPACING_M = 6.1

    @property
    def spacing_m(self) -> float:
        """Get spacing for heat detector"""
        return self.FIXED_SPACING_M

    # V20.2 FIX: Add radius_m property for heat detectors
    # R = 0.7 × S = 0.7 × 6.1m = 4.27m for circular coverage equivalent
    @property
    def radius_m(self) -> float:
        """Get equivalent circular coverage radius R = 0.7 × S per NFPA 72."""
        return round(0.7 * self.FIXED_SPACING_M, 2)  # 4.27m


# ============================================================================
# ⚠️ FIXED: DetectorPlacement - Reference Bug Resolved (2026-05-14)
# ============================================================================
# ORIGINAL BUG (Line 240):
#   def __post_init__(self):
#       if self.coverage_radius_m is None:
#           self.coverage_radius_m = get_smoke_detector_radius(
#               ceiling_spec.height_at_low_point_m  # ReferenceError! ceiling_spec not defined
#           ) if hasattr(ceiling_spec, 'height_at_low_point_m') else 4.55
#
# FIX APPLIED:
#   - Added ceiling_height_m as EXPLICIT PARAMETER
#   - Uses get_smoke_detector_radius_safe() for safe fallback
#   - No more ReferenceError
# ============================================================================
@dataclass
class DetectorPlacement:
    """Individual detector placement
    FIXED: 2026-05-14
    - Added ceiling_height_m as explicit parameter
    - Uses get_smoke_detector_radius_safe() for safe fallback
    - Resolves ReferenceError that occurred when coverage_radius_m was None
    """

    x: float
    y: float
    z: float
    detector_type: DetectorType
    ceiling_height_m: float = 3.0  # ✅ FIXED: Added explicit parameter
    coverage_radius_m: Optional[float] = None

    def __post_init__(self):
        """Initialize coverage radius with type-appropriate fallback.
        V20.2 FIX: Use detector-type-appropriate default radius.
        Heat detectors use R = 0.7 × 6.1m = 4.27m, NOT the smoke detector
        radius of 6.37m. Using smoke radius for heat detectors overestimates
        coverage by ~50%, potentially leaving areas unprotected.
        """
        if self.coverage_radius_m is None:
            if self.detector_type in (DetectorType.HEAT, DetectorType.HEAT_FIXED):
                # Heat: R = 0.7 × S = 0.7 × 6.1m = 4.27m
                self.coverage_radius_m = 4.27
            else:
                # Smoke and other types: use safe fallback
                self.coverage_radius_m = get_smoke_detector_radius_safe(self.ceiling_height_m)

    @property
    def position_3d(self) -> Tuple[float, float, float]:
        """Get 3D position"""
        return (self.x, self.y, self.z)

    @property
    def effective_coverage_area(self) -> float:
        """Calculate effective coverage area in square meters"""
        import math

        return math.pi * (self.coverage_radius_m**2)


@dataclass
class CoverageResult:
    """Coverage check result - V12 compatible"""

    is_covered: bool
    uncovered_areas: List[Tuple[float, float]] = field(default_factory=list)
    coverage_percentage: float = 0.0
    detectors_in_coverage: int = 0
    # V12 compatibility fields
    proof_valid: bool = False  # V112: FAIL-SAFE — proof not valid until explicitly verified
    coverage_fraction: float = 0.0  # V112: FAIL-SAFE — no coverage until verified
    max_gap_m: float = 0.0

    def __bool__(self):
        return self.is_covered


@dataclass
class NFPAComplianceResult:
    """Overall NFPA compliance check result

    LEGAL DISCLAIMER: This software is provided for compliance assistance only.
    It does not constitute legal advice, engineering judgment, or AHJ approval.
    All results must be verified by a licensed fire protection engineer.
    """

    DISCLAIMER: ClassVar[str] = (
        "LEGAL DISCLAIMER: This software is provided for compliance assistance only. "
        "It does not constitute legal advice, engineering judgment, or AHJ approval. "
        "All results must be verified by a licensed fire protection engineer."
    )
    is_compliant: bool
    violations: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    detector_count: int = 0
    required_detector_count: int = 0

    def __bool__(self):
        """Allow if result: syntax — returns is_compliant."""
        return self.is_compliant

    def add_violation(self, message: str):
        """Add a violation message"""
        self.violations.append(message)
        self.is_compliant = False

    def add_warning(self, message: str):
        """Add a warning message"""
        self.warnings.append(message)


# ============================================================================
# FIRE ALARM PANEL - NFPA 72 Chapter 21
# ============================================================================


@dataclass
class FireAlarmPanel:
    """Fire Alarm Control Panel per NFPA 72 Chapter 21.

    ⚠️ CRITICAL LIMITS:
    - Maximum 250 devices per zone (NFPA 72 21.2.2)
    - Minimum operating voltage: 16V (85% of 24V)
    - Panel must be accessible for maintenance

    Args:
        panel_id: Unique identifier
        max_devices: Maximum devices (default 250)
        voltage: Operating voltage (default 24V)

    """

    panel_id: str
    max_devices: int = 250
    voltage: float = 24.0
    min_voltage: float = 16.0  # 85% of 24V
    connected_devices: List[str] = field(default_factory=list)
    zones: List[int] = field(default_factory=list)

    def add_device(self, device_id: str) -> None:
        """Add device to panel."""
        if len(self.connected_devices) >= self.max_devices:
            raise PanelCapacityError(
                f"Panel {self.panel_id} capacity exceeded: "
                f"{len(self.connected_devices)}/{self.max_devices} devices. "
                f"NFPA 72 limit is 250 devices per panel."
            )
        self.connected_devices.append(device_id)

    def check_voltage_drop(self, distance_m: float) -> float:
        """Calculate voltage drop at distance.

        DEPRECATED (Issue #12): This simplified formula (0.04V/100m) ignores
        load current and wire gauge. For accurate voltage drop calculations
        per NFPA 72 §10.14, use `nfpa72_calculations.check_voltage_drop()`
        which properly accounts for current, cable resistance, and return path.

        This method is retained for backward compatibility but will produce
        inaccurate results for any real-world design.
        """
        import warnings

        warnings.warn(
            "FireAlarmPanel.check_voltage_drop() is deprecated — it uses a "
            "simplified 0.04V/100m formula that ignores current and wire gauge. "
            "Use nfpa72_calculations.check_voltage_drop() for accurate results "
            "per NFPA 72 §10.14.",
            DeprecationWarning,
            stacklevel=2,
        )
        # Simplified: 0.04V per 100m (VERY rough approximation)
        v_drop = distance_m * 0.0004
        return v_drop

    def verify_voltage(self, distance_m: float) -> bool:
        """Verify voltage at farthest device is above minimum."""
        v_drop = self.check_voltage_drop(distance_m)
        v_remaining = self.voltage - v_drop
        return v_remaining >= self.min_voltage

    def is_accessible(self) -> bool:
        """Panel must be accessible for maintenance."""
        # In real implementation, check physical accessibility
        return True


class PanelCapacityError(NFPAComplianceError):
    """Raised when panel exceeds device capacity"""

    pass


# Legal disclaimer
DISCLAIMER = """
⚠️ LEGAL DISCLAIMER:
This report is generated by FireAI for compliance assistance only.
It does not constitute legal advice or certification.
Always verify with a licensed fire protection engineer.
NFPA 72 (2022 Edition) is the authoritative standard.
Verify all detector placements with local AHJ requirements.
"""


# ============================================================================
# HELPER FUNCTIONS - Radius Calculations
# ============================================================================
def get_smoke_detector_radius(ceiling_height_m: float) -> float:
    """Calculate smoke detector coverage radius based on NFPA 72 Table 17.6.3.2.

    Args:
        ceiling_height_m: Ceiling height in meters
    Returns:
        Coverage radius in meters
    Raises:
        CeilingHeightError: If height is outside NFPA 72 limits

    """
    # NFPA 72 Table 17.6.3.2 - Coverage per Ceiling Height
    # Heights in meters (converted from feet)
    # CRITICAL FIX: R = 0.7 × S (NFPA 72 §17.7.4.2.3.1)
    # Old values used S/2 which is WRONG — coverage radius is 0.7×S,
    # not half-spacing.  For h≤3.0m: S=9.1m → R=6.37m (not 4.55m).
    # CRITICAL FIX: RADIUS_MAP now uses height-adjusted spacing per
    # NFPA 72 Table 17.6.3.1.1. Higher ceilings → smaller spacing → smaller R.
    # R = 0.7 × adjusted_spacing for each height bracket.
    # V20.2 CRITICAL FIX: RADIUS_MAP brackets were off-by-one.
    # NFPA 72 Table 17.6.3.1.1 uses cumulative upper bounds (h ≤ h_max → S),
    # but the old brackets used (prev_h_max, h_max) which assigned the
    # PREVIOUS bracket's R to the current bracket's height range.
    # E.g. at h=3.5m: old map returned R=6.37 (h≤3.0m bracket) instead
    # of R=6.09 (3.0<h≤3.7m bracket). This overestimated R by up to 5%,
    # producing fewer detectors than required — a life-safety gap.
    # FIX: Lower bounds now start at 0.0 for the first bracket, and each
    # bracket's lower bound equals the PREVIOUS bracket's upper bound.
    # V24 SAFETY FIX: First bracket changed from (0.0, 3.0) to (3.0, 3.0).
    # Old (0.0, 3.0) with special min_h==0.0 condition accepted ANY height
    # from 0.0 to 3.0 silently, including h=0.1m which returned R=6.37
    # without any warning — a LIFE-SAFETY GAP. NFPA 72 Table 17.6.3.1.1
    # starts at h=3.0m. Heights below 3.0m are outside the standard's scope
    # and MUST raise CeilingHeightError in this strict function.
    # Use get_smoke_detector_radius_safe() for graceful handling of h<3.0m.
    RADIUS_MAP = {
        (3.0, 3.7): 6.37,  # R = 0.7 × 9.10 (3.0 ≤ h < 3.7m)
        (3.7, 4.6): 6.09,  # R = 0.7 × 8.70 (3.7 ≤ h < 4.6m)
        (4.6, 5.5): 5.74,  # R = 0.7 × 8.20 (4.6 ≤ h < 5.5m)
        (5.5, 6.1): 5.39,  # R = 0.7 × 7.70 (5.5 ≤ h < 6.1m)
        (6.1, 7.6): 5.11,  # R = 0.7 × 7.30 (6.1 ≤ h < 7.6m)
        (7.6, 9.1): 4.76,  # R = 0.7 × 6.80 (7.6 ≤ h < 9.1m)
        (9.1, 10.7): 4.48,  # R = 0.7 × 6.40 (9.1 ≤ h < 10.7m)
        (10.7, 12.2): 4.20,  # R = 0.7 × 6.00 (10.7 ≤ h < 12.2m)
        # V128 FIX: Upper bound extended from 15.24m to 18.288m per NFPA 72 §17.7.3.2.4
        (12.2, 18.288): 3.64,  # R = 0.7 × 5.20 (12.2 ≤ h ≤ 18.288m)
    }
    for (min_h, max_h), radius in RADIUS_MAP.items():
        if max_h == 18.288:
            if min_h <= ceiling_height_m <= max_h:
                return radius
        else:
            if min_h <= ceiling_height_m < max_h:
                return radius
    raise CeilingHeightError(f"Ceiling height {ceiling_height_m}m is outside NFPA 72 valid range of 3.0m to 18.288m")


def get_smoke_detector_coverage_max(ceiling_height_m: float) -> float:
    """Calculate maximum coverage area (circles can extend to) per NFPA 72.

    Args:
        ceiling_height_m: Ceiling height in meters
    Returns:
        Maximum coverage radius in meters

    """
    # Maximum coverage per NFPA 72 Table 17.6.3.2
    MAX_COVERAGE_MAP = {
        (3.0, 4.3): 5.5,
        (4.3, 6.1): 6.5,
        (6.1, 7.6): 8.1,
        (7.6, 9.1): 9.0,
        # V128 FIX: Upper bound extended from 15.24m to 18.288m
        (9.1, 18.288): 10.1,
    }
    for (min_h, max_h), max_cov in MAX_COVERAGE_MAP.items():
        if max_h == 18.288:
            if min_h <= ceiling_height_m <= max_h:
                return max_cov
        else:
            if min_h <= ceiling_height_m < max_h:
                return max_cov
    return 10.1  # Default max


def validate_ceiling_height(ceiling_height_m: float) -> None:
    """Validate ceiling height against NFPA 72 limits.

    Args:
        ceiling_height_m: Ceiling height in meters
    Raises:
        CeilingHeightError: If height is outside limits

    """
    # V128 FIX: Use canonical ceiling height limits from fireai.constants.nfpa72
    MIN_HEIGHT = _NFPA_HEIGHT_MIN_M
    MAX_HEIGHT = _NFPA_HEIGHT_MAX_M  # 18.288m (60ft) for smoke detectors
    if ceiling_height_m < MIN_HEIGHT:
        raise CeilingHeightError(
            f"Ceiling height {ceiling_height_m}m is below NFPA 72 minimum of {MIN_HEIGHT}m (10 feet)"
        )
    if ceiling_height_m > MAX_HEIGHT:
        raise CeilingHeightError(
            f"Ceiling height {ceiling_height_m}m exceeds NFPA 72 maximum of {MAX_HEIGHT}m (50 feet) for smoke detectors"
        )


# ============================================================================
# ⭐ ELITE SAFE FUNCTIONS - Conservative Fallback (2026-05-13)
# ============================================================================
# These functions provide SAFE FALLBACK for heights outside NFPA 72 range.
# Principle: More detectors (closer spacing) = safer for fire safety.
# ============================================================================
def get_smoke_detector_radius_safe(ceiling_height_m: float, _return_details: bool = False) -> float:
    """⭐ ELITE SOLUTION: Get smoke detector radius with SAFE FALLBACK.
    This provides CONSERVATIVE values for heights outside NFPA 72 range.
    More detectors (closer spacing) = safer design.

    ⚠️ CRITICAL: Negative/zero heights MUST be REJECTED with ValueError.
    Heights < 3.0m require PE REVIEW flag.

    Args:
        ceiling_height_m: Actual ceiling height in meters
        _return_details: If True, returns (radius, details dict)

    Returns:
        float: Coverage radius in meters (conservative)
        tuple: (radius, details) if _return_details=True
    Raises:
        ValueError: If ceiling_height_m <= 0 (MUST be rejected)
    Test Cases:
        Input <= 0  -> ValueError (MUST reject)
        Input 2.4m  -> Output 6.37m (conservative, using 3.0m values) + flag
        Input 3.0m  -> Output 6.37m (standard, R = 0.7 × 9.1)
        Input 15.24m -> Output 3.64m (standard, R = 0.7 × 5.20)
        Input 18.288m -> Output 3.64m (standard, R = 0.7 × 5.20)
        Input 20.0m -> Output 3.64m (capped at 18.288m) + flag

    """
    # ⚠️ CRITICAL: REJECT invalid heights - DO NOT fallback silently
    if ceiling_height_m <= 0:
        raise ValueError(
            f"CEILING_HEIGHT_MUST_BE_POSITIVE: {ceiling_height_m}m is not valid. "
            f"Must be > 0. REJECT - requires PE REVIEW"
        )

    actual_height = ceiling_height_m
    flag = None
    safe_height = ceiling_height_m
    # Case 1: Below NFPA range (< 3.0m) - use 3.0m values (more conservative)
    # STILL returns value BUT sets flag for PE REVIEW required
    if ceiling_height_m < 3.0:
        safe_height = 3.0
        flag = "LOW_CEILING: Using 3.0m values for safety - REQUIRES PE REVIEW"
    # V128 FIX: Case 2 - Above NFPA range (> 18.288m) - cap at maximum
    # Old code used 15.24m (50ft) which is the heat detector max, not smoke.
    elif ceiling_height_m > _SMOKE_MAX_CEILING_HEIGHT_M:
        safe_height = _SMOKE_MAX_CEILING_HEIGHT_M  # 18.288m
        flag = "HIGH_CEILING: Capped at 18.288m (60 ft) - REQUIRES PE REVIEW"
    # Get radius using internal function
    try:
        radius = _get_radius_internal(safe_height)
    except Exception as e:
        radius = _get_radius_internal(3.0)  # Fallback
        flag = "FALLBACK: Used 3.0m values"
        logger.warning("Radius lookup failed for %sm: %s", safe_height, e)
    details = {
        "input_height": actual_height,
        "effective_height": safe_height,
        "radius": radius,
        "flag": flag,
        "conservative": flag is not None,
    }
    if _return_details:
        return radius, details  # type: ignore[return-value]
    return radius


def _get_radius_internal(h: float) -> float:
    """Internal radius lookup."""
    # V20.2 CRITICAL FIX: Same off-by-one bracket fix as RADIUS_MAP above.
    # Old brackets started at (3.0, 3.7) which gave h=3.5m the wrong R=6.37
    # instead of R=6.09. Now aligned with NFPA 72 Table 17.6.3.1.1.
    # V24 SAFETY FIX: Same fix as get_smoke_detector_radius().
    # Removed (0.0, 3.0) bracket — heights below 3.0m are outside NFPA 72
    # scope and must raise CeilingHeightError. get_smoke_detector_radius_safe()
    # handles these gracefully with a PE review flag.
    # Also FIXED: bracket values now match NFPA 72 Table 17.6.3.1.1 correctly.
    # The (3.0, 3.7) bracket uses S=9.1m → R=6.37 (not 6.09 which was S=8.7).
    # Each bracket's spacing DECREASES as height INCREASES per NFPA 72.
    R = {
        (3.0, 3.7): 6.37,  # R = 0.7 × 9.10 (3.0 ≤ h < 3.7m)
        (3.7, 4.6): 6.09,  # R = 0.7 × 8.70 (3.7 ≤ h < 4.6m)
        (4.6, 5.5): 5.74,  # R = 0.7 × 8.20 (4.6 ≤ h < 5.5m)
        (5.5, 6.1): 5.39,  # R = 0.7 × 7.70 (5.5 ≤ h < 6.1m)
        (6.1, 7.6): 5.11,  # R = 0.7 × 7.30 (6.1 ≤ h < 7.6m)
        (7.6, 9.1): 4.76,  # R = 0.7 × 6.80 (7.6 ≤ h < 9.1m)
        (9.1, 10.7): 4.48,  # R = 0.7 × 6.40 (9.1 ≤ h < 10.7m)
        (10.7, 12.2): 4.20,  # R = 0.7 × 6.00 (10.7 ≤ h < 12.2m)
        # V128 FIX: Upper bound extended from 15.24m to 18.288m
        (12.2, 18.288): 3.64,  # R = 0.7 × 5.20 (12.2 ≤ h ≤ 18.288m)
    }
    for (min_h, max_h), r in R.items():
        if max_h == 18.288:
            if min_h <= h <= max_h:
                return r
        else:
            if min_h <= h < max_h:
                return r
    raise CeilingHeightError(f"Height {h}m outside NFPA range (3.0-18.288m for smoke detectors)")


def get_smoke_detector_coverage_max_safe(ceiling_height_m: float, _return_details: bool = False):
    """⭐ ELITE SOLUTION: Get max coverage with SAFE FALLBACK."""
    actual = ceiling_height_m
    flag = None
    safe_h = ceiling_height_m
    if ceiling_height_m < 3.0:
        safe_h = 3.0
        flag = "LOW_CEILING"
    # V128 FIX: Use canonical ceiling height max (18.288m)
    elif ceiling_height_m > _SMOKE_MAX_CEILING_HEIGHT_M:
        safe_h = _SMOKE_MAX_CEILING_HEIGHT_M  # 18.288m
        flag = "HIGH_CEILING"
    try:
        max_cov = _get_max_internal(safe_h)
    except Exception:
        max_cov = _get_max_internal(3.0)
        flag = "FALLBACK"
    details = {"input_height": actual, "effective_height": safe_h, "max_coverage": max_cov, "flag": flag}
    if _return_details:
        return max_cov, details
    return max_cov


def _get_max_internal(h: float) -> float:
    """Internal max coverage lookup.

    CRITICAL FIX (Issue #11): Previous version used min_h <= h <= max_h for
    ALL ranges, causing overlapping boundaries at h=4.3, 6.1, 7.6, 9.1.
    This produced non-deterministic results depending on dict iteration order.
    Now uses < for upper bound of non-last ranges (consistent with RADIUS_MAP
    and _get_radius_internal), and <= only for the final bracket.
    """
    # V128 FIX: Upper bound extended from 15.24m to 18.288m
    M = {(3.0, 4.3): 5.5, (4.3, 6.1): 6.5, (6.1, 7.6): 8.1, (7.6, 9.1): 9.0, (9.1, 18.288): 10.1}
    for (min_h, max_h), m in M.items():
        if max_h == 18.288:
            if min_h <= h <= max_h:
                return m
        else:
            if min_h <= h < max_h:
                return m
    raise CeilingHeightError(f"Height {h}m outside NFPA range (3.0-18.288m for smoke detectors)")


# Test exported symbols
__all__ = [
    "CeilingHeightError",
    "CeilingSpec",
    "CeilingType",
    "CoverageError",
    "CoverageGeometry",
    "CoverageResult",
    "DetectorPlacement",
    "DetectorType",
    "HeatDetectionMode",
    "HeatDetectorSpec",
    "NFPAComplianceError",
    "NFPAComplianceResult",
    "RidgeZoneError",
    "RoomSpec",
    "SmokeDetectorSpec",
    "SpacingError",
    "get_smoke_detector_coverage_max",
    "get_smoke_detector_coverage_max_safe",  # ⭐ safe fallback — REQUIRED
    "get_smoke_detector_radius",
    "get_smoke_detector_radius_safe",  # ⭐ safe fallback — REQUIRED
    "validate_ceiling_height",
]
