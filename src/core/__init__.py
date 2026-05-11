"""
FireAlarmAI Core Module
=======================
Core utilities and shared functionality.
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

__all__ = [
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
    'DomainType',
    'DeviceType',
    'RoomType',
    'ViolationSeverity',
    'DesignStatus',
    'validate_room',
    'validate_device',
]
