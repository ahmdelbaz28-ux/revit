"""
Coverage Service
================
Application service for checking device coverage compliance.

This service orchestrates coverage checks across multiple standards.
"""

from typing import List, Optional
from ..domain.models import Room, Device, Violation, ViolationSeverity
from ..domain.standards import NFPA72, BS5839, get_standard


class CoverageService:
    """
    Service for validating device coverage against standards.
    
    Responsibilities:
    - Check if devices provide adequate coverage for rooms
    - Validate spacing between devices
    - Identify uncovered areas
    """
    
    def __init__(self, standard_name: str = "NFPA72", version: Optional[str] = None):
        """
        Initialize with a specific standard.
        
        Args:
            standard_name: Name of standard (e.g., 'NFPA72', 'BS5839')
            version: Optional version string
        """
        self.standard = get_standard(standard_name, version)
        if not self.standard:
            raise ValueError(f"Standard '{standard_name}' not found")
    
    def check_room_coverage(self, room: Room, devices: List[Device]) -> List[Violation]:
        """
        Check if devices provide adequate coverage for a room.
        
        Args:
            room: Room to check
            devices: List of devices in the room
            
        Returns:
            List of coverage violations
        """
        violations = []
        
        if not room.area or room.area <= 0:
            violations.append(Violation(
                violation_code="COVERAGE_INVALID_ROOM_AREA",
                standard_name=self.standard.__class__.__name__,
                severity=ViolationSeverity.CRITICAL,
                room_id=room.room_id,
                description_template="Room area is invalid or zero",
                params={}
            ))
            return violations
        
        if not devices:
            violations.append(Violation(
                violation_code="COVERAGE_NO_DEVICES",
                standard_name=self.standard.__class__.__name__,
                severity=ViolationSeverity.CRITICAL,
                room_id=room.room_id,
                description_template="No devices found in room - no coverage provided",
                params={'room_area': room.area}
            ))
            return violations
        
        # Check each device's coverage
        for device in devices:
            if isinstance(self.standard, NFPA72):
                device_violations = self.standard.check_coverage(device, room)
                violations.extend(device_violations)
        
        # Check overall room coverage (simplified grid-based approach)
        uncovered_areas = self._calculate_uncovered_areas(room, devices)
        if uncovered_areas > room.area * 0.1:  # More than 10% uncovered
            violations.append(Violation(
                violation_code="COVERAGE_INSUFFICIENT_TOTAL",
                standard_name=self.standard.__class__.__name__,
                severity=ViolationSeverity.MAJOR,
                room_id=room.room_id,
                description_template="Room has significant uncovered areas: {uncovered:.1f}m² ({percent:.1f}%)",
                params={
                    'uncovered': uncovered_areas,
                    'percent': (uncovered_areas / room.area) * 100
                }
            ))
        
        return violations
    
    def _calculate_uncovered_areas(self, room: Room, devices: List[Device]) -> float:
        """
        Calculate total uncovered area in room.
        
        Simplified calculation using circular coverage areas.
        TODO: Replace with proper computational geometry using Shapely.
        """
        if not room.area or not devices:
            return room.area or 0.0
        
        # Sum up coverage areas (overlapping areas will be double-counted,
        # but this is acceptable for a simplified check)
        total_covered = 0.0
        for device in devices:
            if device.position:
                coverage_area = 3.14159 * (device.coverage_radius ** 2)
                total_covered += coverage_area
        
        # Cap at room area (can't cover more than the room)
        covered = min(total_covered, room.area)
        uncovered = room.area - covered
        
        return max(0.0, uncovered)
    
    def check_device_spacing(self, room: Room, devices: List[Device]) -> List[Violation]:
        """
        Check spacing between devices complies with standards.
        
        Args:
            room: Room containing devices
            devices: List of devices to check
            
        Returns:
            List of spacing violations
        """
        if len(devices) < 2:
            return []
        
        if isinstance(self.standard, NFPA72):
            return self.standard.check_device_spacing(devices, room)
        
        return []
