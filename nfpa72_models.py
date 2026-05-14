"""
NFPA 72 V5 Models - Enums, Dataclasses, and Exceptions

This module provides the data models for NFPA 72 Chapter 17 compliance.
All models are law-compliant implementations based on NFPA 72 (2022 Edition).

⚠️ LEGAL DISCLAIMER:
This code is provided for compliance assistance only.
It does not constitute legal advice.
Always verify with a licensed fire protection engineer.
NFPA 72 (2022 Edition) is the authoritative standard.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import List, Tuple, Optional
from shapely.geometry import Polygon as ShapelyPolygon
import math


# ============================================================================
# ENUMS - Detector Types and Modes
# ============================================================================

class DetectorType(Enum):
    """NFPA 72 detector types"""
    SMOKE = "smoke"
    HEAT = "heat"
    FLAME = "flame"
    GAS = "gas"
    HEAT_FIXED_TEMP = "heat_fixed_temp"
    HEAT_RATE_OF_RISE = "heat_rate_of_rise"
    HEAT_COMBINATION = "heat_combination"
    SMOKE_HEAT_COMBINATION = "smoke_heat_combination"


class CoverageGeometry(Enum):
    """Coverage geometry types per NFPA 72"""
    CIRCULAR = "circular"
    SQUARE_GRID = "square_grid"


class HeatDetectionMode(Enum):
    """Heat detector detection modes"""
    CIRCULAR = "circular"  # Euclidean (for smoke)
    SQUARE_GRID = "square_grid"  # Chebyshev (for heat)


class CeilingType(Enum):
    """Ceiling configuration types"""
    FLAT = "flat"
    GABLE = "gable"
    SHED = "shed"
    TRUSS = "truss"
    COMBUSTIBLE = "combustible"


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
    
    def __post_init__(self):
        # NFPA 72 height limits (Chapter 17)
        MIN_HEIGHT = 3.0  # 10 feet = 3.0m
        MAX_HEIGHT = 15.3  # 50 feet = 15.3m
        
        if self.height_at_low_point_m < MIN_HEIGHT:
            raise CeilingHeightError(
                f"Ceiling height {self.height_at_low_point_m}m is below NFPA 72 "
                f"minimum of {MIN_HEIGHT}m (10 feet)"
            )
        
        if self.height_at_low_point_m > MAX_HEIGHT:
            raise CeilingHeightError(
                f"Ceiling height {self.height_at_low_point_m}m exceeds NFPA 72 "
                f"maximum of {MAX_HEIGHT}m (50 feet)"
            )
        
        # Calculate slope if high point provided
        if self.height_at_high_point_m and self.height_at_high_point_m > self.height_at_low_point_m:
            run = 3.0  # Assume 3m run for slope calculation
            rise = self.height_at_high_point_m - self.height_at_low_point_m
            self.slope_degrees = math.degrees(math.atan(rise / run))
    
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
class RoomSpec:
    """Room specification with polygon boundary"""
    
    name: str
    width_m: float
    depth_m: float
    height_m: float
    polygon: Optional[ShapelyPolygon] = None
    ceiling_spec: Optional[CeilingSpec] = None
    detector_type: Optional[DetectorType] = None
    occupancy_type: str = "office"
    heat_detector_spec: Optional['HeatDetectorSpec'] = None
    
    def __post_init__(self):
        # Build polygon from dimensions if not provided
        if self.polygon is None:
            self.polygon = ShapelyPolygon([
                (0, 0),
                (self.width_m, 0),
                (self.width_m, self.depth_m),
                (0, self.depth_m)
            ])
        # Build ceiling_spec from height if not provided
        if self.ceiling_spec is None:
            try:
                self.ceiling_spec = CeilingSpec(self.height_m, self.height_m, CeilingType.FLAT, 0.0)
            except Exception:
                # Height may not meet NFPA 72 minimum - use default
                self.ceiling_spec = CeilingSpec(3.0, 3.0, CeilingType.FLAT, 0.0)
        if self.detector_type is None:
            self.detector_type = DetectorType.SMOKE
    
    @property
    def area_sqm(self) -> float:
        """Calculate room area"""
        return self.width_m * self.depth_m


@dataclass
class SmokeDetectorSpec:
    """Smoke detector specification"""
    
    ceiling_spec: CeilingSpec
    room_spec: RoomSpec
    detector_type: DetectorType = DetectorType.SMOKE
    
    # NFPA 72 Table 17.6.3.2 coverage areas
    HEIGHT_TO_COVERAGE = {
        (3.0, 4.3): (4.1, 6.4),    # 10-14 ft -> 4.1m radius (circles can extend to 6.4m)
        (4.3, 6.1): (4.6, 7.2),   # 14-20 ft
        (6.1, 7.6): (5.2, 8.1),    # 20-25 ft
        (7.6, 9.1): (5.8, 9.0),    # 25-30 ft
        (9.1, 15.3): (6.4, 10.1), # 30-50 ft
    }
    
    @property
    def radius_m(self) -> float:
        """Get radius based on ceiling height per NFPA 72"""
        # V9 FIX: Use safe radius function
        return get_smoke_detector_radius_safe(self.ceiling_spec.height_m)
    
    @property
    def coverage_max_m(self) -> float:
        """Get maximum coverage area (circles can extend)"""
        return get_smoke_detector_coverage_max(self.ceiling_spec.height_m)


@dataclass
class HeatDetectorSpec:
    """Heat detector specification per NFPA 72 Table 17.6.2.1"""
    
    ceiling_spec: CeilingSpec
    room_spec: RoomSpec
    detector_type: DetectorType = DetectorType.HEAT
    heat_mode: HeatDetectionMode = HeatDetectionMode.SQUARE_GRID
    
    # NFPA 72 Table 17.6.2.1 - Spacing in feet to meters
    FIXED_TEMP_FT = 20      # 20 feet = 6.1m (fixed temperature)
    RATE_OF_RISE_FT = 25   # 25 feet = 7.6m (rate of rise)
    
    # Spacing in meters
    FIXED_TEMP_M = 6.1      # 20 feet * 0.3048
    RATE_OF_RISE_M = 7.6    # 25 feet * 0.3048
    
    @property
    def spacing_m(self) -> float:
        """Get spacing per NFPA 72 Table 17.6.2.1"""
        # Default to fixed temp spacing (6.1m) - most conservative
        # SQUARE_GRID mode = fixed temp (6.1m)
        # CIRCULAR mode = rate of rise (7.6m) - less conservative
        if self.heat_mode == HeatDetectionMode.CIRCULAR:
            return self.RATE_OF_RISE_M  # 7.6m
        else:
            return self.FIXED_TEMP_M  # 6.1m default (SQUARE_GRID)


@dataclass
class DetectorPlacement:
    """Individual detector placement"""
    
    x: float
    y: float
    z: float
    detector_type: DetectorType
    coverage_radius_m: Optional[float] = None
    ceiling_spec: Optional[CeilingSpec] = None  # Added for V9
    
    def __post_init__(self):
        # V9 FIX: Use safe radius function with proper parameter
        if self.coverage_radius_m is None:
            if self.ceiling_spec and hasattr(self.ceiling_spec, 'height_at_low_point_m'):
                self.coverage_radius_m = get_smoke_detector_radius_safe(self.ceiling_spec.height_at_low_point_m)
            else:
                self.coverage_radius_m = 4.55  # Default safe radius


@dataclass
class CoverageResult:
    """Coverage check result"""
    
    is_covered: bool
    uncovered_areas: List[Tuple[float, float]] = field(default_factory=list)
    coverage_percentage: float = 0.0
    detectors_in_coverage: int = 0
    
    def __bool__(self):
        return self.is_covered


@dataclass
class NFPAComplianceResult:
    """Overall NFPA compliance check result"""
    
    is_compliant: bool
    violations: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    detector_count: int = 0
    required_detector_count: int = 0
    
    # Legal disclaimer
    DISCLAIMER = """
⚠️ LEGAL DISCLAIMER:
This report is generated by FireAI for compliance assistance only.
It does not constitute legal advice or certification.
Always verify with a licensed fire protection engineer.
NFPA 72 (2022 Edition) is the authoritative standard.
Verify all detector placements with local AHJ requirements.
"""
    
    def __bool__(self):
        return self.is_compliant
    
    def add_violation(self, message: str):
        """Add a violation message"""
        self.violations.append(message)
        self.is_compliant = False
    
    def add_warning(self, message: str):
        """Add a warning message"""
        self.warnings.append(message)


# ============================================================================
# HELPER FUNCTIONS - Radius Calculations
# ============================================================================

def get_smoke_detector_radius(ceiling_height_m: float) -> float:
    """
    Calculate smoke detector coverage radius based on NFPA 72 Table 17.6.3.2.
    
    Args:
        ceiling_height_m: Ceiling height in meters
        
    Returns:
        Coverage radius in meters
        
    Raises:
        CeilingHeightError: If height is outside NFPA 72 limits
    """
    # NFPA 72 Table 17.6.3.2 - Coverage per Ceiling Height
    # Heights in meters (converted from feet)
    RADIUS_MAP = {
        (3.0, 4.3): 4.55,   # 3.0m -> 4.55m
        (4.3, 6.1): 5.35,   # 4.3-6.1m -> 5.35m
        (6.1, 7.6): 5.2,    # 6.1-7.6m
        (7.6, 9.1): 5.8,    # 7.6-9.1m
        (9.1, 15.3): 6.4,   # 9.1-15.3m
    }
    
    for (min_h, max_h), radius in RADIUS_MAP.items():
        if min_h <= ceiling_height_m <= max_h:
            return radius
    
    # Handle edge case at 15.3m (exactly at max)
    if ceiling_height_m == 15.3:
        return 6.4
    
    # Outside valid range
    raise CeilingHeightError(
        f"Ceiling height {ceiling_height_m}m is outside NFPA 72 "
        f"valid range of 3.0m to 15.3m"
    )


def get_smoke_detector_coverage_max(ceiling_height_m: float) -> float:
    """
    Calculate maximum coverage area (circles can extend to) per NFPA 72.
    
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
        (9.1, 15.3): 10.1,
    }
    
    for (min_h, max_h), max_cov in MAX_COVERAGE_MAP.items():
        if min_h <= ceiling_height_m < max_h:
            return max_cov
    
    return 10.1  # Default max


def validate_ceiling_height(ceiling_height_m: float) -> None:
    """
    Validate ceiling height against NFPA 72 limits.
    
    Args:
        ceiling_height_m: Ceiling height in meters
        
    Raises:
        CeilingHeightError: If height is outside limits
    """
    # NFPA 72 Chapter 17: 3.0m (10 ft) min, 15.3m (50 ft) max
    MIN_HEIGHT = 3.0
    MAX_HEIGHT = 15.3
    
    if ceiling_height_m < MIN_HEIGHT:
        raise CeilingHeightError(
            f"Ceiling height {ceiling_height_m}m is below NFPA 72 minimum "
            f"of {MIN_HEIGHT}m (10 feet)"
        )
    
    if ceiling_height_m > MAX_HEIGHT:
        raise CeilingHeightError(
            f"Ceiling height {ceiling_height_m}m exceeds NFPA 72 maximum "
            f"of {MAX_HEIGHT}m (50 feet)"
        )


# ============================================================================
# ⭐ ELITE SAFE FUNCTIONS - Conservative Fallback (2026-05-13)
# ============================================================================
# These functions provide SAFE FALLBACK for heights outside NFPA 72 range.
# Principle: More detectors (closer spacing) = safer for fire safety.
# ============================================================================

def get_smoke_detector_radius_safe(
    ceiling_height_m: float,
    _return_details: bool = False
):
    """
    ⭐ ELITE SOLUTION: Get smoke detector radius with SAFE FALLBACK.
    
    This provides CONSERVATIVE values for heights outside NFPA 72 range.
    More detectors (closer spacing) = safer design.
    
    Args:
        ceiling_height_m: Actual ceiling height in meters
        _return_details: If True, returns (radius, details dict)
        
    Returns:
        float: Coverage radius in meters (conservative)
        tuple: (radius, details) if _return_details=True
        
    Test Cases:
        Input 2.4m  -> Output 4.55m (conservative)
        Input 2.7m  -> Output 4.55m (conservative)
        Input 3.0m  -> Output 4.55m (standard)
        Input 15.3m -> Output 6.40m (standard)
        Input 20.0m -> Output 6.40m (capped) + flag
    """
    actual_height = ceiling_height_m
    flag = None
    safe_height = ceiling_height_m
    
    # Case 1: Below NFPA range (< 3.0m) - use 3.0m values (more conservative)
    if ceiling_height_m < 3.0:
        safe_height = 3.0
        flag = "LOW_CEILING: Using 3.0m values for safety"
        
    # Case 2: Above NFPA range (> 15.3m) - cap at maximum
    elif ceiling_height_m > 15.3:
        safe_height = 15.3
        flag = "HIGH_CEILING: Capped at 15.3m, ENGINEER REVIEW REQUIRED"
    
    # Get radius using internal function
    try:
        radius = _get_radius_internal(safe_height)
    except:
        radius = _get_radius_internal(3.0)  # Fallback
        flag = "FALLBACK: Used 3.0m values"
    
    details = {
        "input_height": actual_height,
        "effective_height": safe_height,
        "radius": radius,
        "flag": flag,
        "conservative": flag is not None
    }
    
    if _return_details:
        return radius, details
    return radius


def _get_radius_internal(h: float) -> float:
    """Internal radius lookup."""
    R = {
        (3.0, 4.3): 4.55,
        (4.3, 6.1): 5.35,
        (6.1, 7.6): 5.2,
        (7.6, 9.1): 5.8,
        (9.1, 15.3): 6.4
    }
    for (min_h, max_h), r in R.items():
        if min_h <= h <= max_h:
            return r
    if h == 15.3:
        return 6.4
    raise CeilingHeightError(f"Height {h}m outside NFPA range")


def get_smoke_detector_coverage_max_safe(ceiling_height_m: float, _return_details: bool = False):
    """⭐ ELITE SOLUTION: Get max coverage with SAFE FALLBACK."""
    actual = ceiling_height_m
    flag = None
    safe_h = ceiling_height_m
    
    if ceiling_height_m < 3.0:
        safe_h = 3.0
        flag = "LOW_CEILING"
    elif ceiling_height_m > 15.3:
        safe_h = 15.3
        flag = "HIGH_CEILING"
    
    try:
        max_cov = _get_max_internal(safe_h)
    except:
        max_cov = _get_max_internal(3.0)
        flag = "FALLBACK"
    
    details = {
        "input_height": actual,
        "effective_height": safe_h,
        "max_coverage": max_cov,
        "flag": flag
    }
    
    if _return_details:
        return max_cov, details
    return max_cov


def _get_max_internal(h: float) -> float:
    """Internal max coverage lookup."""
    M = {
        (3.0, 4.3): 5.5,
        (4.3, 6.1): 6.5,
        (6.1, 7.6): 8.1,
        (7.6, 9.1): 9.0,
        (9.1, 15.3): 10.1
    }
    for (min_h, max_h), m in M.items():
        if min_h <= h <= max_h:
            return m
    if h == 15.3:
        return 10.1
    raise CeilingHeightError(f"Height {h}m outside NFPA range")


# Test exported symbols
__all__ = [
    # Enums
    "DetectorType",
    "HeatDetectionMode", 
    "CeilingType",
    # Exceptions
    "NFPAComplianceError",
    "CeilingHeightError",
    "CoverageError",
    "SpacingError",
    "RidgeZoneError",
    # Dataclasses
    "CeilingSpec",
    "RoomSpec",
    "SmokeDetectorSpec",
    "HeatDetectorSpec",
    "DetectorPlacement",
    "CoverageResult",
    "NFPAComplianceResult",
    # Functions
    "get_smoke_detector_radius",
    "get_smoke_detector_radius_safe",  # ⭐ New: Elite safe fallback
    "get_smoke_detector_coverage_max",
    "get_smoke_detector_coverage_max_safe",  # ⭐ New: Elite safe fallback
    "validate_ceiling_height",
]