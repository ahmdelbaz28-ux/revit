"""
Core Layer - Unified Model Definitions
==========================
These definitions are the SINGLE SOURCE OF TRUTH for the entire system.
No other files should define these classes.

Import them from core.models throughout the project.
"""

from dataclasses import dataclass
from shapely.geometry import Point, Polygon
from typing import Optional, List


# =============================================================================
# Immutable Core Models (frozen=True for hashing safety)
# =============================================================================

@dataclass(frozen=True)
class Room:
    """Room node in the semantic graph - immutable for safety"""
    id: str
    name: str
    geometry: Polygon
    ceiling_height: float
    ceiling_type: str = "SMOOTH"  # SMOOTH, BEAMED, SLOPED, CORRIDOR


@dataclass(frozen=True)
class Device:
    """Detector/Device node - immutable for safety"""
    id: str
    device_type: str  # SMOKE_PHOTOELECTRIC, HEAT_FIXED, etc.
    position: Point  # x, y coordinates
    z_height: float = 2.4  # mounting height in meters
    coverage_radius: float = 4.6  # meters (NFPA 72 default for smooth ceiling)


@dataclass(frozen=True)
class Obstruction:
    """Obstruction node - immutable for safety"""
    id: str
    geometry: Polygon  # obstruction footprint
    height: float  # height from floor
    blocks_visibility: bool = True


@dataclass(frozen=True)
class Violation:
    """Represents a constraint violation - immutable for safety"""
    rule: str
    device_id: str
    severity: str  # CRITICAL, MAJOR, MINOR
    value: float  # actual measured value
    threshold: float  # allowed maximum
    location: Optional[Point] = None  # where violation occurred
    
    def __post_init__(self):
        """Validate violation data"""
        if self.value < 0:
            raise ValueError(f"Violation value cannot be negative: {self.value}")
        if self.threshold <= 0:
            raise ValueError(f"Threshold must be positive: {self.threshold}")


# =============================================================================
# Standard Reference (immutable)
# =============================================================================

@dataclass(frozen=True)
class NFPAStandard:
    """Standard reference for compliance rules"""
    code: str  # NFPA72, BS5839, etc.
    edition: str
    spacing_rules: tuple  # frozen tuple of spacing rules


# =============================================================================
# Helper functions for core models
# =============================================================================

def create_room(id: str, name: str, coordinates: List[tuple], 
             ceiling_height: float, ceiling_type: str = "SMOOTH") -> Room:
    """Helper to create a Room from coordinate list"""
    return Room(
        id=id,
        name=name,
        geometry=Polygon(coordinates),
        ceiling_height=ceiling_height,
        ceiling_type=ceiling_type
    )


def create_device(id: str, device_type: str, x: float, y: float,
              z_height: float = 2.4, coverage_radius: float = 4.6) -> Device:
    """Helper to create a Device from coordinates"""
    return Device(
        id=id,
        device_type=device_type,
        position=Point(x, y),
        z_height=z_height,
        coverage_radius=coverage_radius
    )


def create_obstruction(id: str, coordinates: List[tuple],
                   height: float, blocks_visibility: bool = True) -> Obstruction:
    """Helper to create an Obstruction from coordinate list"""
    return Obstruction(
        id=id,
        geometry=Polygon(coordinates),
        height=height,
        blocks_visibility=blocks_visibility
    )