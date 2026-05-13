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
from typing import List, Tuple, Optional, Any
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


class CoverageGeometry(Enum):
    """Coverage geometry types"""
    CIRCULAR = "circular"
    SQUARE_GRID = "square_grid"


class CeilingType(Enum):
    """Ceiling configuration types"""
    FLAT = "flat"
    SLOPED = "sloped"
    PEAKED = "peaked_gable"
    HIP = "hip"
    CURVED = "curved"
    GABLE = "gable"
    SHED = "shed"
    TRUSS = "truss"
    COMBUSTIBLE = "combustible"
    SUSPENDED = "suspended"


# ============================================================================
# EXCEPTIONS - NFPA Compliance Errors
# ============================================================================

class NFPAComplianceError(Exception):
    """
    يُرفع عندما لا يمكن لشروط الإدخال إنتاج تصميم متوافق.
    هذا ليس خطأ برمجي — يعني أن معلمات المبنى نفسها تخالف NFPA 72.
    """
    pass

class InvalidInputError(ValueError):
    """
    يُرفع عندما تكون بيانات الإدخال مفقودة أو غير منطقية.
    أمثلة: ارتفاع سلبي، حقل مطلوب مفقود.
    """
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
    """Ceiling specification with height, slope type, and run"""
    
    ceiling_type: CeilingType
    height_at_low_point_m: float
    height_at_high_point_m: float
    slope_run_m: float
    
    def __post_init__(self):
        if self.height_at_low_point_m <= 0:
            raise InvalidInputError(f"height_at_low_point_m must be > 0. Got: {self.height_at_low_point_m}")
        if self.height_at_high_point_m < self.height_at_low_point_m:
            raise InvalidInputError(f"height_at_high_point_m cannot be less than height_at_low_point_m")
        if self.slope_run_m <= 0:
            raise InvalidInputError(f"slope_run_m must be > 0")
    
    @property
    def slope_degrees(self) -> float:
        """Calculate slope in degrees"""
        rise = self.height_at_high_point_m - self.height_at_low_point_m
        if rise == 0:
            return 0.0
        return math.degrees(math.atan(rise / self.slope_run_m))

    @property
    def height_m(self) -> float:
        """Get ceiling height (low point)"""
        return self.height_at_low_point_m

    @property
    def is_sloped(self) -> bool:
        """Check if ceiling is sloped (>1.5 degrees)"""
        return self.slope_degrees > 1.5

    def get_local_height_at(self, distance_from_low_wall_m: float) -> float:
        """Get ceiling height at a given distance from the low wall"""
        if self.ceiling_type == CeilingType.FLAT:
            return self.height_at_low_point_m
        elif self.ceiling_type == CeilingType.SLOPED:
            slope_tan = (self.height_at_high_point_m - self.height_at_low_point_m) / self.slope_run_m
            height = self.height_at_low_point_m + distance_from_low_wall_m * slope_tan
            return min(height, self.height_at_high_point_m)
        elif self.ceiling_type in (CeilingType.PEAKED, CeilingType.HIP):
            dist_from_ridge = abs(distance_from_low_wall_m - self.slope_run_m)
            slope_tan = (self.height_at_high_point_m - self.height_at_low_point_m) / self.slope_run_m
            height = self.height_at_high_point_m - dist_from_ridge * slope_tan
            return max(height, self.height_at_low_point_m)
        return self.height_at_low_point_m


@dataclass
class RoomSpec:
    """Room specification with polygon boundary"""
    
    room_id: str
    polygon: Any  # ShapelyPolygon
    ceiling_spec: CeilingSpec
    detector_type: DetectorType
    occupancy_type: str
    
    def __post_init__(self):
        if not self.room_id.strip():
            raise InvalidInputError("room_id cannot be empty")
        if not self.polygon.is_valid:
            raise InvalidInputError(f"Room '{self.room_id}': polygon is not valid geometry")
        if self.polygon.area <= 0:
            raise InvalidInputError(f"Room '{self.room_id}': polygon has zero area")


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
    """Heat detector specification with manufacturer data for legal compliance"""
    
    detector_type: DetectorType
    listed_spacing_m: float      # From manufacturer catalog - REQUIRED
    manufacturer: str           # REQUIRED for audit trail
    model_number: str           # REQUIRED for audit trail
    listing_standard: str       # "UL 521" or "FM 1220" - REQUIRED for legal defense
    
    def __post_init__(self):
        if self.detector_type == DetectorType.SMOKE:
            raise InvalidInputError("HeatDetectorSpec cannot be used for smoke detectors")
        if self.listed_spacing_m <= 0:
            raise InvalidInputError(f"listed_spacing_m must be > 0")
        if self.listed_spacing_m > 15.25:
            raise NFPAComplianceError(f"listed_spacing_m exceeds maximum 15.25m")
        if not self.manufacturer.strip():
            raise InvalidInputError("manufacturer cannot be empty")
        if not self.model_number.strip():
            raise InvalidInputError("model_number cannot be empty")


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
    Calculate smoke detector coverage radius based on NFPA 72 Table 17.6.3.1.
    
    Args:
        ceiling_height_m: Ceiling height in meters
        
    Returns:
        Coverage radius in meters
    """
    if ceiling_height_m <= 0:
        raise InvalidInputError(f"ceiling_height_m must be > 0. Got: {ceiling_height_m}m")

    NFPA72_TABLE_17_6_3_1 = [
        (4.6,  4.55),   # ≤ 4.6m
        (6.1,  5.35),   # ≤ 6.1m
        (7.6,  6.10),   # ≤ 7.6m
        (9.1,  6.40),   # ≤ 9.1m
        (10.7, 6.90),   # ≤ 10.7m
        (12.2, 7.30),   # ≤ 12.2m
        (13.7, 7.60),   # ≤ 13.7m
        (15.2, 7.90),   # ≤ 15.2m
    ]

    for max_height, radius in NFPA72_TABLE_17_6_3_1:
        if ceiling_height_m <= max_height:
            return radius

    raise NFPAComplianceError(
        f"Ceiling height {ceiling_height_m}m exceeds 15.2m (50ft). "
        f"NFPA 72 (2022) Table 17.6.3.1 does NOT permit standard smoke "
        f"detectors on ceilings above 15.2m. "
        f"Engineering alternatives: beam-mounted detectors, projected beam "
        f"smoke detectors, or air-sampling systems per NFPA 72 Section 17.7."
    )


def get_smoke_detector_coverage_max(ceiling_height_m: float) -> float:
    """
    Calculate maximum coverage area (circles can extend to) per NFPA 72.
    """
    MAX_COVERAGE_MAP = {
        (4.6, 5.5),
        (6.1, 6.5),
        (7.6, 8.1),
        (9.1, 9.0),
        (10.7, 10.0),
        (12.2, 10.7),
        (13.7, 11.3),
        (15.2, 11.9),
    }

    for max_h, max_cov in MAX_COVERAGE_MAP:
        if ceiling_height_m <= max_h:
            return max_cov

    return 11.9  # Default max for heights > 15.2m


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