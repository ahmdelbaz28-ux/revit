#!/usr/bin/env python3
"""
pa_logic.py - Public Address (PA) System Engineering Logic
=======================================================

Public Address / Voice Alarm system engineering logic implementation
for the multi-domain building design platform.

Features:
- Ceiling-mounted speakers at grid spacing
- Wall-mounted speakers for corridors/stairwells
- Coverage calculations based on room area

Author: FireAlarmAI Engineering Team
Date: 2026-05-09
"""

import math
from typing import Dict, List

from ai_design_integration import EngineeringLogic, AIDesignDevice


class PublicAddressLogic(EngineeringLogic):
    """
    Public Address (PA) system engineering logic.
    
    Implements speaker placement for voice alarm / public address:
    - Ceiling-mounted speakers at grid spacing (6m)
    - Wall-mounted for corridors/stairwells
    - Coverage based on room area
    """
    
    DOMAIN_NAME = "PublicAddress"
    
    # Speaker costs
    DEVICE_COSTS = {
        'Speaker': 200,
        'HornSpeaker': 180,
        'CeilingSpeaker': 150,
        'WallSpeaker': 170,
    }
    
    INSTALLATION_COST = 30
    
    # Grid spacing for ceiling speakers
    SPEAKER_SPACING = 6  # meters
    WALL_MARGIN = 1  # meters from wall
    
    def analyze_room(self, room_data: Dict) -> Dict:
        """
        Analyze room for PA speaker requirements.
        
        Args:
            room_data: Dictionary with room properties
            
        Returns:
            Dictionary with analysis results
        """
        length = room_data.get('length', 0)
        width = room_data.get('width', 0)
        room_type = room_data.get('type', 'Office')
        height = room_data.get('height', 3)
        
        area = length * width
        
        # Determine placement type
        if room_type in ['Corridor', 'Stairwell', 'Hallway', 'Exit']:
            placement_type = 'wall_mounted'
            # For corridors: speakers along one wall
            if length > 0:
                speakers_needed = max(1, int(length / self.SPEAKER_SPACING))
            else:
                speakers_needed = 1
        else:
            placement_type = 'ceiling_mounted'
            # Grid placement
            cols = max(1, int((length - 2 * self.WALL_MARGIN) / self.SPEAKER_SPACING))
            rows = max(1, int((width - 2 * self.WALL_MARGIN) / self.SPEAKER_SPACING))
            speakers_needed = cols * rows
        
        # Calculate coverage area per speaker
        coverage_per_speaker = area / speakers_needed if speakers_needed > 0 else area
        
        return {
            'speakers_needed': speakers_needed,
            'placement_type': placement_type,
            'area': area,
            'coverage_per_speaker': coverage_per_speaker,
            'justification': f"{placement_type} requires {speakers_needed} speakers"
        }
    
    def place_devices(self, room, session_id: int, db_session) -> List[AIDesignDevice]:
        """
        Place PA speakers in room.
        
        - Ceiling: grid spacing (6m, 1m margin)
        - Wall: corridor/stairwell speakers
        
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
        
        # Determine speaker type based on room type
        if room_type in ['Corridor', 'Stairwell', 'Hallway', 'Exit']:
            # Wall-mounted speakers
            positions = self._wall_mounted_positions(length, width, height)
            speaker_type = 'WallSpeaker'
        else:
            # Ceiling-mounted speakers
            positions = self._ceiling_mounted_positions(length, width, height)
            speaker_type = 'CeilingSpeaker'
        
        # Create devices
        for pos in positions:
            device = AIDesignDevice(
                SessionID=session_id,
                RoomID=room.RoomID,
                ProposedType='Speaker',
                X=round(pos['x'], 2),
                Y=round(pos['y'], 2),
                Z=round(pos['z'], 2),
                Confidence=0.88,
                AI_Justification=f"{speaker_type} for {room_type}"
            )
            devices.append(device)
        
        # Add to database
        for device in devices:
            db_session.add(device)
        
        db_session.commit()
        
        return devices
    
    def _ceiling_mounted_positions(self, length: float, width: float, height: float) -> List[Dict]:
        """
        Calculate ceiling speaker grid positions.
        
        Args:
            length: Room length
            width: Room width
            height: Room height
            
        Returns:
            List of (x, y, z) positions
        """
        positions = []
        
        margin = self.WALL_MARGIN
        
        # Calculate grid
        effective_length = length - 2 * margin
        effective_width = width - 2 * margin
        
        if effective_length <= 0 or effective_width <= 0:
            # Room too small, single speaker at center
            return [{
                'x': length / 2,
                'y': width / 2,
                'z': height - 0.1  # Near ceiling
            }]
        
        cols = max(1, int(effective_length / self.SPEAKER_SPACING))
        rows = max(1, int(effective_width / self.SPEAKER_SPACING))
        
        # Calculate spacing
        spacing_x = effective_length / (cols + 1)
        spacing_y = effective_width / (rows + 1)
        
        for row in range(rows):
            for col in range(cols):
                x = margin + spacing_x * (col + 1)
                y = margin + spacing_y * (row + 1)
                
                positions.append({
                    'x': x,
                    'y': y,
                    'z': height - 0.1  # Near ceiling
                })
        
        return positions
    
    def _wall_mounted_positions(self, length: float, width: float, height: float) -> List[Dict]:
        """
        Calculate wall-mounted speaker positions for corridors.
        
        Args:
            length: Room length (corridor direction)
            width: Room width
            height: Room height
            
        Returns:
            List of (x, y, z) positions
        """
        positions = []
        
        # Place speakers along the center of one wall
        num_speakers = max(1, int(length / self.SPEAKER_SPACING))
        spacing = length / (num_speakers + 1)
        
        # Mount on one wall (y = 0.3 from wall)
        wall_y = 0.3
        
        for i in range(num_speakers):
            x = spacing * (i + 1)
            
            positions.append({
                'x': x,
                'y': wall_y,
                'z': height - 0.3  # Wall-mounted at ear level
            })
        
        return positions
    
    def calculate_cost(self, devices: List[AIDesignDevice]) -> Dict:
        """
        Calculate PA system cost.
        
        Args:
            devices: List of placed devices
            
        Returns:
            Dictionary with cost breakdown
        """
        speaker_count = sum(1 for d in devices if d.ProposedType == 'Speaker')
        
        # Average cost per speaker
        avg_equipment = sum(
            self.DEVICE_COSTS.get(d.ProposedType, 200) 
            for d in devices
        ) / max(1, speaker_count)
        
        equipment = speaker_count * avg_equipment
        installation = speaker_count * self.INSTALLATION_COST
        
        return {
            'equipment': equipment,
            'labor': installation,
            'total': equipment + installation,
            'device_count': speaker_count,
            'per_speaker_cost': avg_equipment + self.INSTALLATION_COST
        }


# =============================================================================
# Factory Registration
# =============================================================================

def get_logic_class():
    """Return the logic class for factory registration"""
    return PublicAddressLogic


# Entry point for direct execution
if __name__ == "__main__":
    # Test the logic
    print("Public Address Logic Test")
    print("=" * 40)
    
    logic = PublicAddressLogic()
    
    # Test office room
    room_data = {
        'length': 20,
        'width': 15,
        'height': 3,
        'type': 'Office'
    }
    
    analysis = logic.analyze_room(room_data)
    print(f"Office Room Analysis: {analysis}")
    
    # Test corridor
    corridor_data = {
        'length': 50,
        'width': 3,
        'height': 3,
        'type': 'Corridor'
    }
    
    analysis = logic.analyze_room(corridor_data)
    print(f"Corridor Analysis: {analysis}")
    
    print("\n✅ PA Logic module loaded successfully")