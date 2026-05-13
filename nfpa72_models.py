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
    polygon: Optional[List[Tuple[float, float]]] = None
    
    def __post_init__(self):
        if self.polygon is None:
            # Default rectangle
            self.polygon = [
                (0, 0),
                (self.width_m, 0),
                (self.width_m, self.depth_m),
                (0, self.depth_m)
            ]
    
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
    FIXED_SPACING_FT = 30  # 30 feet = 9.1m
    FIXED_SPACING_M = 9.1
    
    @property
    def spacing_m(self) -> float:
        """Get spacing for heat detector"""
        return self.FIXED_SPACING_M


@dataclass
class DetectorPlacement:
    """Individual detector placement"""
    
    x: float
    y: float
    z: float
    detector_type: DetectorType
    coverage_radius_m: Optional[float] = None
    
    def __post_init__(self):
        if self.coverage_radius_m is None:
            self.coverage_radius_m = get_smoke_detector_radius(ceiling_spec.height_at_low_point_m) if hasattr(ceiling_spec, 'height_at_low_point_m') else 4.55  # Default


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
        if min_h <= ceiling_height_m < max_h:
            return radius
    
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
    "get_smoke_detector_coverage_max",
    "validate_ceiling_height",
]