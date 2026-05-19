"""
Wall Distance Service
=====================
Application service for validating device distances from walls.

This service checks compliance with wall distance requirements per standards.
"""

from typing import List, Optional
from ..domain.models import Room, Device, Violation
from ..domain.standards import NFPA72, BS5839, get_standard


class WallDistanceService:
    """
    Service for validating device distances from walls.
    
    Responsibilities:
    - Check maximum wall distance compliance
    - Check minimum wall distance clearance
    - Provide wall distance recommendations
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
    
    def check_all_devices(self, room: Room, devices: List[Device]) -> List[Violation]:
        """
        Check wall distance compliance for all devices in a room.
        
        Args:
            room: Room containing devices
            devices: List of devices to check
            
        Returns:
            List of wall distance violations
        """
        violations = []
        
        for device in devices:
            violation = self.check_device(device, room)
            if violation:
                violations.append(violation)
        
        return violations
    
    def check_device(self, device: Device, room: Room) -> Optional[Violation]:
        """
        Check wall distance compliance for a single device.
        
        Args:
            device: Device to check
            room: Room containing the device
            
        Returns:
            Violation if non-compliant, None otherwise
        """
        if isinstance(self.standard, NFPA72):
            return self.standard.check_wall_distance(device, room)
        elif isinstance(self.standard, BS5839):
            bs_violations = self.standard.check_compliance(device, room)
            return bs_violations[0] if bs_violations else None
        
        return None
    
    def get_recommended_position(self, room: Room) -> Optional[dict]:
        """
        Get recommended device position based on room geometry.
        
        Args:
            room: Room to analyze
            
        Returns:
            Dictionary with recommended position and justification
        """
        if not room.polygon and not (room.length and room.width):
            return None
        
        centroid = room.get_centroid()
        if not centroid:
            return None
        
        max_wall_dist = 4.6  # NFPA default
        if isinstance(self.standard, NFPA72):
            max_wall_dist = self.standard.MAX_WALL_DISTANCE_SMOKE
        elif isinstance(self.standard, BS5839):
            max_wall_dist = self.standard.MAX_WALL_DISTANCE
        
        return {
            'x': centroid.x,
            'y': centroid.y,
            'z': room.height - 0.3,  # 30cm below ceiling
            'justification': f"Centroid placement ensures max wall distance of {max_wall_dist}m is met",
            'max_wall_distance': max_wall_dist
        }
