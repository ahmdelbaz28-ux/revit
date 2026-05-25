#!/usr/bin/env python3
"""
cctv_logic.py - CCTV System Engineering Logic
==========================================

CCTV (Closed-Circuit Television) engineering logic implementation
for the multi-domain building design platform.

Features:
- Corner camera placement with wall margin
- Corridor coverage with additional cameras
- Random field of view (90-120 degrees)

Author: FireAlarmAI Engineering Team
Date: 2026-05-09
"""

import math
import random
from typing import Dict, List

from ai_design_integration import EngineeringLogic, AIDesignDevice


class CCTVLogic(EngineeringLogic):
    """
    CCTV system engineering logic.
    
    Implements camera placement for room surveillance:
    - Corner cameras with wall margin
    - Corridor coverage (additional cameras every 15m)
    - Random FOV 90-120 degrees
    """
    
    DOMAIN_NAME = "CCTV"
    
    # Camera costs
    DEVICE_COSTS = {
        'Camera': 300,
        'DomeCamera': 420,
        'PTZCamera': 850,
    }
    
    INSTALLATION_COST = 50
    
    # Corridor spacing
    CORRIDOR_CAMERA_SPACING = 15  # meters
    
    # Wall margin
    WALL_MARGIN = 0.3  # meters
    
    def analyze_room(self, room_data: Dict) -> Dict:
        """
        Analyze room for CCTV coverage requirements.
        
        Args:
            room_data: Dictionary with room properties
            
        Returns:
            Dictionary with analysis results
        """
        length = room_data.get('length', 0)
        width = room_data.get('width', 0)
        room_type = room_data.get('type', 'Office')
        
        # Base: 4 corner cameras
        cameras_needed = 4
        
        # Additional for corridors
        if room_type in ['Corridor', 'Stairwell', 'Hallway']:
            # Calculate additional cameras needed
            if length > 0:
                corridor_cameras = max(0, int(length / self.CORRIDOR_CAMERA_SPACING))
                cameras_needed += corridor_cameras
            coverage_type = 'corridor'
        else:
            coverage_type = 'room'
        
        return {
            'cameras_needed': cameras_needed,
            'coverage_type': coverage_type,
            'length': length,
            'width': width,
            'justification': f"{coverage_type} coverage requires {cameras_needed} cameras"
        }
    
    def place_devices(self, room, session_id: int, db_session) -> List[AIDesignDevice]:
        """
        Place CCTV cameras in room.
        
        - Corners with wall margin (0.3m)
        - Corridor: additional cameras along centerline every 15m
        
        Args:
            room: Room object
            session_id: Design session ID
            db_session: Database session
            
        Returns:
            List of AIDesignDevice objects
        """
        devices = []
        
        # Get room dimensions
        length = float(room.Length or 0)
        width = float(room.Width or 0)
        height = float(room.Height or 3)
        room_type = room.RoomType or 'Office'
        
        # Calculate camera positions
        positions = []
        
        # Corner positions with wall margin
        margin = self.WALL_MARGIN
        corners = [
            (margin, margin),                                    # (0,0) corner
            (length - margin, margin),                          # (length, 0) corner  
            (margin, width - margin),                          # (0, width) corner
            (length - margin, width - margin),                 # (length, width) corner
        ]
        
        for x, y in corners:
            if 0 <= x <= length and 0 <= y <= width:
                positions.append({
                    'x': x,
                    'y': y,
                    'type': 'corner'
                })
        
        # Corridor: additional cameras along centerline
        if room_type in ['Corridor', 'Stairwell', 'Hallway']:
            # Place along the longer dimension (centerline)
            num_extra = int(length / self.CORRIDOR_CAMERA_SPACING)
            
            for i in range(1, num_extra + 1):
                x = i * self.CORRIDOR_CAMERA_SPACING
                y = width / 2  # centerline
                
                if x < length:
                    positions.append({
                        'x': x,
                        'y': y,
                        'type': 'corridor'
                    })
        
        # Create devices
        for pos in positions:
            # Random FOV between 90-120 degrees
            fov = random.randint(90, 120)
            
            device = AIDesignDevice(
                SessionID=session_id,
                RoomID=room.RoomID,
                ProposedType='Camera',
                X=round(pos['x'], 2),
                Y=round(pos['y'], 2),
                Z=round(height - 0.3, 2),  # Near ceiling
                Confidence=0.90,
                AI_Justification=f"{pos['type']} placement, FOV: {fov}°"
            )
            devices.append(device)
        
        # Add to database
        for device in devices:
            db_session.add(device)
        
        db_session.commit()
        
        return devices
    
    def calculate_cost(self, devices: List[AIDesignDevice]) -> Dict:
        """
        Calculate CCTV system cost.
        
        Args:
            devices: List of placed devices
            
        Returns:
            Dictionary with cost breakdown
        """
        camera_count = sum(1 for d in devices if d.ProposedType == 'Camera')
        
        equipment = camera_count * self.DEVICE_COSTS.get('Camera', 300)
        installation = camera_count * self.INSTALLATION_COST
        
        return {
            'equipment': equipment,
            'labor': installation,
            'total': equipment + installation,
            'device_count': camera_count,
            'per_camera_cost': self.DEVICE_COSTS.get('Camera', 300) + self.INSTALLATION_COST
        }


# =============================================================================
# Factory Registration
# =============================================================================

def get_logic_class():
    """Return the logic class for factory registration"""
    return CCTVLogic


# Entry point for direct execution
if __name__ == "__main__":
    # Test the logic
    print("CCTV Logic Test")
    print("=" * 40)
    
    logic = CCTVLogic()
    
    # Test room analysis
    room_data = {
        'length': 20,
        'width': 15,
        'type': 'Office'
    }
    
    analysis = logic.analyze_room(room_data)
    print(f"Office Room Analysis: {analysis}")
    
    # Test corridor
    corridor_data = {
        'length': 50,
        'width': 3,
        'type': 'Corridor'
    }
    
    analysis = logic.analyze_room(corridor_data)
    print(f"Corridor Analysis: {analysis}")
    
    print("\n✅ CCTV Logic module loaded successfully")