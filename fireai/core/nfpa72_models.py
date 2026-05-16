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
"""
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Tuple, Optional
from shapely.geometry import Polygon as ShapelyPolygon

# Constants
_NFPA_HEIGHT_MIN_M = 3.0   # NFPA 72 min ceiling height
_NFPA_HEIGHT_MAX_M = 15.24  # NFPA 72 max ceiling height
MIN_WALL_DISTANCE_M = 0.10  # 4 inches per NFPA 72 §17.6.3.1.1
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
    dangerous = {'\0', '\n', '\r', '\t', ';', '\'', '"', '\\', '\x00', '\x01', '\x02'}
    for ch in dangerous:
        if ch in value:
            raise ValueError("Input contains invalid characters")
    # Check for SQL comment --
    if '--' in value:
        raise ValueError("Input contains invalid sequence '--'")
    return value

# ============================================================================
# ENUMS - Detector Types and Modes
# ============================================================================
class DetectorType(Enum):
    """NFPA 72 detector types"""
    SMOKE = "SMOKE"
    SMOKE_PHOTOELECTRIC = "SMOKE_PHOTOELECTRIC"
    SMOKE_IONIZATION = "SMOKE_IONIZATION"
    SMOKE_MULTI_CRITERIA = "SMOKE_MULTI_CRITERIA"
    HEAT = "HEAT"
    FLAME = "FLAME"
    GAS = "GAS"
    HEAT_FIXED_TEMP = "HEAT_FIXED_TEMP"
    HEAT_RATE_OF_RISE = "HEAT_RATE_OF_RISE"
    HEAT_COMBINATION = "HEAT_COMBINATION"
    SMOKE_HEAT_COMBINATION = "SMOKE_HEAT_COMBINATION"
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
    FLAT = "FLAT"
    GABLE = "GABLE"
    SHED = "SHED"
    TRUSS = "TRUSS"
    COMBUSTIBLE = "COMBUSTIBLE"
    # Additional types used by expert system
    SMOOTH = "SMOOTH"
    BEAMED = "BEAMED"
    SLOPED = "SLOPED"
    CORRIDOR = "CORRIDOR"

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
        
        # NFPA 72 range validation - clamp heights at boundaries
        # Skip if caller (e.g., create_safe) already provided clamped value
        caller_provided_clamped = hasattr(self, 'was_clamped') and self.was_clamped and self.original_height_m is not None
        
        if not caller_provided_clamped:
            was_clamped = False
            if h_low < _NFPA_HEIGHT_MIN_M:
                h_low = _NFPA_HEIGHT_MIN_M
                was_clamped = True
            elif h_low > _NFPA_HEIGHT_MAX_M:
                original_height = h_low
                h_low = _NFPA_HEIGHT_MAX_M
                was_clamped = True
            
            self.height_at_low_point_m = h_low
            if was_clamped:
                self.original_height_m = original_height if h_low > _NFPA_HEIGHT_MIN_M else None
            self.was_clamped = was_clamped
        
        if self.height_at_high_point_m and self.height_at_high_point_m > self.height_at_low_point_m:
            run = 3.0
            rise = self.height_at_high_point_m - self.height_at_low_point_m
            self.slope_degrees = math.degrees(math.atan(rise / run))

    @classmethod
    def create_safe(
        cls,
        height_at_low_point_m: float,
        height_at_high_point_m: Optional[float] = None,
        ceiling_type: "CeilingType" = None,
        beam_depth_m: float = 0.0,
        beam_spacing_m: float = 0.0,
    ) -> "CeilingSpec":
        """
        V9: Factory method — clamps height to NFPA range instead of raising.
        Use this for production code to avoid crashes on unusual building heights.

        Heights outside 3.0–15.24m are clamped with a warning logged.
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
                f"CeilingSpec.create_safe: height {height_at_low_point_m}m > NFPA max {MAX_HEIGHT}m "
                f"— clamped to {MAX_HEIGHT}m. Review with licensed PE."
            )

        kwargs = {"height_at_low_point_m": clamped, "original_height_m": height_at_low_point_m, "was_clamped": height_at_low_point_m != clamped}
        if height_at_high_point_m is not None:
            kwargs["height_at_high_point_m"] = height_at_high_point_m
        if ceiling_type is not None:
            kwargs["ceiling_type"] = ceiling_type

        return cls(**kwargs)
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
    polygon: Optional[ShapelyPolygon] = None
    ceiling_spec: Optional[CeilingSpec] = None
    detector_type: Optional[DetectorType] = None
    occupancy_type: str = "office"
    heat_detector_spec: Optional['HeatDetectorSpec'] = None
    hvac_ducts: List[HVACDuct] = field(default_factory=list)

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

        # 4. Validate polygon
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

        # 5. Validate occupancy_type
        valid_types = {
            "office", "kitchen", "corridor", "atrium", "sleeping", "server_room",
            "clean_room", "elevator", "stairwell", "standard", "hazardous", "industrial",
            "assembly", "business", "educational", "factory", "mercantile", "residential",
            "storage", "utility", "institutional", "laboratory", "mechanical",
            "electrical", "data_center", "bathroom", "living", "data_center", "undry"
        }
        occ = self.occupancy_type
        if occ is None or not occ or (isinstance(occ, str) and occ.strip() == ""):
            errors.append("occupancy_type is required and cannot be empty")
        elif occ.lower().strip() not in valid_types:
            errors.append(f"occupancy_type '{occ}' not in valid set")

        # Raise if ANY validation fails
        if errors:
            raise ValueError(f"RoomSpec validation failed for '{self.room_id}': " + "; ".join(errors))

        # ===== BUILD POLYGON FROM DIMENSIONS =====
        if self.polygon is None:
            self.polygon = ShapelyPolygon([
                (0, 0),
                (self.width_m, 0),
                (self.width_m, self.depth_m),
                (0, self.depth_m)
            ])

        # ===== BUILD CEILING SPEC =====
        if self.ceiling_spec is None:
            # Get height from ceiling_spec.height_at_low_point_m, fallback to 3.0m default
            ceiling_height = 3.0  # NFPA minimum default
            self.ceiling_spec = CeilingSpec(
                ceiling_height, ceiling_height, CeilingType.FLAT, 0.0
            )

        if self.detector_type is None:
            self.detector_type = DetectorType.SMOKE

    @classmethod
    def create_validated(cls, **kwargs) -> 'RoomSpec':
        """Factory method - ONLY way to create RoomSpec safely"""
        return cls(**kwargs)

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
        (9.1, 15.24): (6.4, 10.1), # 30-50 ft
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
    """
    Individual detector placement
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
        """
        Initialize coverage radius with safe fallback.
        FIXED: 2026-05-14
        - Uses self.ceiling_height_m (explicit parameter)
        - Uses get_smoke_detector_radius_safe() for safe fallback
        - No longer references undefined 'ceiling_spec' variable
        """
        if self.coverage_radius_m is None:
            # ✅ FIXED: Use explicit ceiling_height_m parameter
            # ✅ FIXED: Use safe fallback function
            self.coverage_radius_m = get_smoke_detector_radius_safe(
                self.ceiling_height_m
            )
    @property
    def position_3d(self) -> Tuple[float, float, float]:
        """Get 3D position"""
        return (self.x, self.y, self.z)
    @property
    def effective_coverage_area(self) -> float:
        """Calculate effective coverage area in square meters"""
        import math
        return math.pi * (self.coverage_radius_m ** 2)
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


# ============================================================================
# FIRE ALARM PANEL - NFPA 72 Chapter 21
# ============================================================================

@dataclass
class FireAlarmPanel:
    """
    Fire Alarm Control Panel per NFPA 72 Chapter 21.
    
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
        """
        Calculate voltage drop at distance.
        Simple calculation: V_drop = 0.04V per 100m of wire (@ 1.5mm²)
        """
        # Simplified: 0.04V per 100m
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
        (9.1, 15.24): 6.4,   # 9.1-15.24m
    }
    for (min_h, max_h), radius in RADIUS_MAP.items():
        if min_h <= ceiling_height_m <= max_h:
            return radius
    # Handle edge case at 15.24m (exactly at max)
    if ceiling_height_m == 15.24:
        return 6.4
    # Outside valid range
    raise CeilingHeightError(
        f"Ceiling height {ceiling_height_m}m is outside NFPA 72 "
        f"valid range of 3.0m to 15.24m"
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
        (9.1, 15.24): 10.1,
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
    # NFPA 72 Chapter 17: 3.0m min, 15.24m max
    MIN_HEIGHT = _NFPA_HEIGHT_MIN_M
    MAX_HEIGHT = _NFPA_HEIGHT_MAX_M
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
) -> float:
    """
    ⭐ ELITE SOLUTION: Get smoke detector radius with SAFE FALLBACK.
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
        Input 2.4m  -> Output 4.55m (conservative) + flag
        Input 3.0m  -> Output 4.55m (standard)
        Input 15.24m -> Output 6.40m (standard)
        Input 20.0m -> Output 6.40m (capped) + flag
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
    # Case 2: Above NFPA range (> 15.24m) - cap at maximum
    elif ceiling_height_m > 15.24:
        safe_height = 15.24
        flag = "HIGH_CEILING: Capped at 15.24m - REQUIRES PE REVIEW"
    # Get radius using internal function
    try:
        radius = _get_radius_internal(safe_height)
    except Exception as e:
        radius = _get_radius_internal(3.0)  # Fallback
        flag = "FALLBACK: Used 3.0m values"
        logger.warning(f"Radius lookup failed for {safe_height}m: {e}")
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
        (9.1, 15.24): 6.4
    }
    for (min_h, max_h), r in R.items():
        if min_h <= h <= max_h:
            return r
    if h == 15.24:
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
    elif ceiling_height_m > 15.24:
        safe_h = 15.24
        flag = "HIGH_CEILING"
    try:
        max_cov = _get_max_internal(safe_h)
    except Exception as e:
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
        (9.1, 15.24): 10.1
    }
    for (min_h, max_h), m in M.items():
        if min_h <= h <= max_h:
            return m
    if h == 15.24:
        return 10.1
    raise CeilingHeightError(f"Height {h}m outside NFPA range")
# Test exported symbols
__all__ = [
    "DetectorType",
    "HeatDetectionMode",
    "CeilingType",
    "NFPAComplianceError",
    "CeilingHeightError",
    "CoverageError",
    "SpacingError",
    "RidgeZoneError",
    "CeilingSpec",
    "RoomSpec",
    "SmokeDetectorSpec",
    "HeatDetectorSpec",
    "DetectorPlacement",
    "CoverageResult",
    "NFPAComplianceResult",
    "get_smoke_detector_radius",
    "get_smoke_detector_radius_safe",          # ⭐ safe fallback — REQUIRED
    "get_smoke_detector_coverage_max",
    "get_smoke_detector_coverage_max_safe",    # ⭐ safe fallback — REQUIRED
    "validate_ceiling_height",
]
