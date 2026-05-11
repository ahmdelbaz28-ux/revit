"""
FireAlarmAI Domain Standards
============================
Implementation of international fire alarm standards (NFPA, BS, EN).

This module contains the business rules for various standards,
implementing spacing requirements, wall distances, and coverage rules.
"""

from typing import Dict, Any, Optional, List
from dataclasses import dataclass, field
from .models import Room, Device, Violation, ViolationSeverity, Polygon, Point


@dataclass
class NFPA72:
    """
    NFPA 72 National Fire Alarm and Signaling Code constraints.
    
    Reference: NFPA 72 2019/2022 Edition
    """
    version: str = "2022"
    
    # Spacing requirements (meters)
    SMOKE_DETECTOR_SPACING: float = 9.1  # 30 feet
    HEAT_DETECTOR_SPACING: float = 9.1  # 30 feet
    MAX_WALL_DISTANCE_SMOKE: float = 4.6  # Half of 30ft (15ft)
    MAX_WALL_DISTANCE_HEAT: float = 4.6
    
    # Coverage requirements
    MIN_COVERAGE_RADIUS: float = 7.5
    BEAM_DEPTH_THRESHOLD: float = 0.1  # 10% of ceiling height
    
    # Special room requirements
    KITCHEN_HEAT_DETECTOR_REQUIRED: bool = True
    STAIRWELL_DETECTOR_EVERY_FLOOR: bool = True
    
    def get_max_spacing(self, device_type: str) -> float:
        """Get maximum spacing for device type"""
        spacing_map = {
            'SmokeDetector': self.SMOKE_DETECTOR_SPACING,
            'HeatDetector': self.HEAT_DETECTOR_SPACING,
            'ManualCallPoint': 30.0,  # Manual call points typically 30m apart
            'Sounder': 15.0,  # Sounders based on audibility requirements
        }
        return spacing_map.get(device_type, self.SMOKE_DETECTOR_SPACING)
    
    def get_max_wall_distance(self, device_type: str) -> float:
        """Get maximum allowed distance from wall"""
        if device_type in ['SmokeDetector', 'HeatDetector']:
            return self.MAX_WALL_DISTANCE_SMOKE
        return self.MAX_WALL_DISTANCE_SMOKE  # Default
    
    def check_device_spacing(self, devices: List[Device], room: Room) -> List[Violation]:
        """
        Check if devices comply with NFPA 72 spacing requirements.
        
        Returns list of violations if any devices are too close or too far.
        """
        violations = []
        
        if not room.polygon or len(devices) < 2:
            return violations
        
        # Get applicable spacing for first device type
        if len(devices) > 0:
            device_type = devices[0].device_type.value
            max_spacing = self.get_max_spacing(device_type)
            
            # Check pairwise distances
            for i, dev1 in enumerate(devices):
                if not dev1.position:
                    continue
                    
                for j, dev2 in enumerate(devices[i+1:], i+1):
                    if not dev2.position:
                        continue
                    
                    distance = dev1.position.distance_to(dev2.position)
                    
                    # Too close (less than half spacing - unusual but possible)
                    if distance < max_spacing * 0.3:
                        violations.append(Violation(
                            violation_code="NFPA72_DEVICES_TOO_CLOSE",
                            standard_name="NFPA 72",
                            severity=ViolationSeverity.MINOR,
                            device_id=dev1.device_id,
                            room_id=room.room_id,
                            description_template="Devices are too close: {distance:.2f}m (min recommended: {min_dist:.2f}m)",
                            params={
                                'distance': distance,
                                'min_dist': max_spacing * 0.3,
                                'device1_id': dev1.device_id,
                                'device2_id': dev2.device_id
                            }
                        ))
        
        return violations
    
    def check_wall_distance(self, device: Device, room: Room) -> Optional[Violation]:
        """
        Check if device complies with NFPA 72 wall distance requirements.
        
        NFPA 72 requires detectors to be within half the spacing from walls.
        """
        if not device.position or not room.polygon:
            return None
        
        wall_distance = device.distance_to_wall(room)
        max_allowed = self.get_max_wall_distance(device.device_type.value)
        
        if wall_distance > max_allowed:
            return Violation(
                violation_code="NFPA72_EXCEEDS_MAX_WALL_DISTANCE",
                standard_name="NFPA 72",
                severity=ViolationSeverity.MAJOR,
                device_id=device.device_id,
                room_id=room.room_id,
                description_template="Device exceeds maximum wall distance: {actual:.2f}m (max: {max:.2f}m)",
                params={
                    'actual': wall_distance,
                    'max': max_allowed,
                    'device_type': device.device_type.value
                }
            )
        
        # Check minimum distance from wall (typically 4 inches / 0.1m for smoke detectors)
        min_distance = 0.1
        if wall_distance < min_distance and device.device_type.value == 'SmokeDetector':
            return Violation(
                violation_code="NFPA72_TOO_CLOSE_TO_WALL",
                standard_name="NFPA 72",
                severity=ViolationSeverity.MINOR,
                device_id=device.device_id,
                room_id=room.room_id,
                description_template="Device too close to wall: {actual:.2f}m (min: {min:.2f}m)",
                params={
                    'actual': wall_distance,
                    'min': min_distance
                }
            )
        
        return None
    
    def check_coverage(self, device: Device, room: Room) -> List[Violation]:
        """
        Check if device provides adequate coverage for the room.
        
        Simplified coverage check based on radius and room area.
        """
        violations = []
        
        if not device.position or not room.area:
            return violations
        
        # Calculate coverage area (circle)
        coverage_area = 3.14159 * (device.coverage_radius ** 2)
        
        # Simple check: if room area is much larger than coverage, flag it
        if room.area > coverage_area * 1.5:
            violations.append(Violation(
                violation_code="NFPA72_INSUFFICIENT_COVERAGE",
                standard_name="NFPA 72",
                severity=ViolationSeverity.MAJOR,
                device_id=device.device_id,
                room_id=room.room_id,
                description_template="Single device may not provide adequate coverage. Room area: {room_area:.1f}m², Device coverage: {coverage:.1f}m²",
                params={
                    'room_area': room.area,
                    'coverage': coverage_area,
                    'device_type': device.device_type.value
                }
            ))
        
        return violations
    
    def validate_room_requirements(self, room: Room, devices: List[Device]) -> List[Violation]:
        """
        Validate room-specific requirements per NFPA 72.
        """
        violations = []
        
        # Kitchen requires heat detector instead of smoke
        if room.room_type.value == 'Kitchen':
            has_heat_detector = any(
                d.device_type.value == 'HeatDetector' for d in devices
            )
            has_smoke_detector = any(
                d.device_type.value == 'SmokeDetector' for d in devices
            )
            
            if has_smoke_detector and not has_heat_detector:
                violations.append(Violation(
                    violation_code="NFPA72_KITCHEN_REQUIRES_HEAT_DETECTOR",
                    standard_name="NFPA 72",
                    severity=ViolationSeverity.CRITICAL,
                    room_id=room.room_id,
                    description_template="Kitchens require heat detectors instead of smoke detectors to avoid false alarms",
                    params={'room_type': room.room_type.value}
                ))
        
        return violations


@dataclass
class BS5839:
    """
    BS 5839 Fire detection and fire alarm systems for buildings.
    
    Reference: BS 5839-1:2017
    """
    version: str = "2017"
    
    # Category-based requirements
    CATEGORY_L1_COVERAGE: str = "All areas"
    CATEGORY_L2_COVERAGE: str = "Escape routes and high risk rooms"
    CATEGORY_L3_COVERAGE: str = "Escape routes only"
    CATEGORY_L4_COVERAGE: str = "Escape routes within building"
    CATEGORY_L5_COVERAGE: str = "Custom/special requirement"
    
    # Spacing (similar to NFPA but with UK specifics)
    SMOKE_DETECTOR_SPACING: float = 7.5  # Typically 7.5m for BS
    HEAT_DETECTOR_SPACING: float = 5.3  # Typically 5.3m for BS
    MAX_WALL_DISTANCE: float = 3.75  # Half spacing
    
    def get_max_spacing(self, device_type: str) -> float:
        """Get maximum spacing for device type per BS 5839"""
        spacing_map = {
            'SmokeDetector': self.SMOKE_DETECTOR_SPACING,
            'HeatDetector': self.HEAT_DETECTOR_SPACING,
            'ManualCallPoint': 45.0,  # BS allows up to 45m travel distance
        }
        return spacing_map.get(device_type, self.SMOKE_DETECTOR_SPACING)
    
    def check_compliance(self, device: Device, room: Room) -> List[Violation]:
        """Check device compliance with BS 5839"""
        violations = []
        
        if not device.position or not room.polygon:
            return violations
        
        # Wall distance check
        wall_distance = device.distance_to_wall(room)
        max_allowed = self.MAX_WALL_DISTANCE
        
        if wall_distance > max_allowed:
            violations.append(Violation(
                violation_code="BS5839_EXCEEDS_MAX_WALL_DISTANCE",
                standard_name="BS 5839",
                severity=ViolationSeverity.MAJOR,
                device_id=device.device_id,
                room_id=room.room_id,
                description_template="Device exceeds BS 5839 maximum wall distance: {actual:.2f}m (max: {max:.2f}m)",
                params={
                    'actual': wall_distance,
                    'max': max_allowed
                }
            ))
        
        return violations


def get_standard(standard_name: str, version: Optional[str] = None) -> Any:
    """
    Factory function to get standard implementation by name.
    
    Args:
        standard_name: Name of standard (e.g., 'NFPA72', 'BS5839')
        version: Optional version string
        
    Returns:
        Standard instance or None if not found
    """
    standards_map = {
        'NFPA72': NFPA72,
        'NFPA 72': NFPA72,
        'BS5839': BS5839,
        'BS 5839': BS5839,
    }
    
    standard_class = standards_map.get(standard_name)
    if standard_class:
        return standard_class(version=version or "latest")
    
    return None


# Convenience instances
NFPA72_2022 = NFPA72(version="2022")
BS5839_2017 = BS5839(version="2017")
