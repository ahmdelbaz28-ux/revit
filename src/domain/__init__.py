"""
FireAlarmAI Domain Layer
========================
Domain models and business logic for fire alarm design.

This layer contains the core business entities and rules,
independent of any framework or infrastructure concerns.
"""

from .models import (
    Point,
    LineString,
    Polygon,
    Room,
    Device,
    Obstruction,
    Violation,
    Standard,
    DesignProject,
    DesignSession,
    DomainType,
    DeviceType,
    RoomType,
    ViolationSeverity,
    DesignStatus,
    validate_room,
    validate_device,
)

from .standards import NFPA72, BS5839, get_standard

__all__ = [
    # Models
    'Point',
    'LineString',
    'Polygon',
    'Room',
    'Device',
    'Obstruction',
    'Violation',
    'Standard',
    'DesignProject',
    'DesignSession',
    # Enums
    'DomainType',
    'DeviceType',
    'RoomType',
    'ViolationSeverity',
    'DesignStatus',
    # Validation
    'validate_room',
    'validate_device',
    # Standards
    'NFPA72',
    'BS5839',
    'get_standard',
]
