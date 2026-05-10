#!/usr/bin/env python3
"""
lighting_logic.py - Lighting Engineering Logic
===============================================

Engineering logic for Intelligent Lighting systems.
Places LED Panels, Exit Signs, and Emergency Lights.

Usage:
    logic = LightingLogic(session)
    devices = logic.place_devices(room, session.SessionID, session)
    cost = logic.calculate_cost()
"""

import logging
from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session

from ai_design_integration import EngineeringLogic, AIDesignDevice, DeviceType, ProjectDomain

logger = logging.getLogger(__name__)


class LightingLogic(EngineeringLogic):
    """
    Lighting system engineering logic.
    
    Places lighting devices:
    - LED Panel: Every 3m grid in rooms (z=2.8m ceiling)
    - Exit Sign: 1 per room door
    - Emergency Light: 1 per 30 sqm
    """
    
    # Device costs (USD)
    COST_LED_PANEL = 80.0
    COST_EXIT_SIGN = 40.0
    COST_EMERGENCY_LIGHT = 60.0
    
    def __init__(self, session: Session):
        """Initialize Lighting logic"""
        super().__init__(session=session, domain='Lighting')
        self.devices_placed = []
    
    def place_devices(
        self,
        room: Any,
        session_id: int,
        db_session: Session
    ) -> List[AIDesignDevice]:
        """
        Place lighting devices for a room.
        
        Args:
            room: Room object with room properties
            session_id: Design session ID
            db_session: SQLAlchemy session
            
        Returns:
            List of placed AIDesignDevice objects
        """
        devices = []
        
        # Get device type IDs
        led_type = self._get_device_type(db_session, 'LEDPanel')
        exit_sign_type = self._get_device_type(db_session, 'ExitSign')
        emergency_type = self._get_device_type(db_session, 'EmergencyLight')
        
        # Get room geometry
        x1, y1 = room.XCoord or 0, room.YCoord or 0
        w, h = room.WidthMeters or 10, room.HeightMeters or 10
        room_area = w * h
        
        # Place LED Panels in 3m grid
        spacing = 3.0
        if led_type:
            for x in range(int(x1), int(x1 + w), int(spacing)):
                for y in range(int(y1), int(y1 + h), int(spacing)):
                    if x + spacing <= x1 + w and y + spacing <= y1 + h:
                        device = AIDesignDevice(
                            SessionID=session_id,
                            RoomID=room.RoomID,
                            DeviceTypeID=led_type.DeviceTypeID,
                            XCoord=float(x + spacing / 2),
                            YCoord=float(y + spacing / 2),
                            ZCoord=2.8,  # Ceiling height
                            Status='placed',
                            Description=f'LED Panel in {room.RoomName}'
                        )
                        db_session.add(device)
                        devices.append(device)
        
        # Place Exit Sign at room door
        if exit_sign_type:
            device = AIDesignDevice(
                SessionID=session_id,
                RoomID=room.RoomID,
                DeviceTypeID=exit_sign_type.DeviceTypeID,
                XCoord=x1,  # Door location
                YCoord=y1 + h / 2,
                ZCoord=2.4,  # Above door
                Status='placed',
                Description=f'Exit Sign at {room.RoomName}'
            )
            db_session.add(device)
            devices.append(device)
        
        # Place Emergency Light per 30 sqm
        num_emergency = max(1, int(room_area / 30))
        if emergency_type:
            for i in range(num_emergency):
                device = AIDesignDevice(
                    SessionID=session_id,
                    RoomID=room.RoomID,
                    DeviceTypeID=emergency_type.DeviceTypeID,
                    XCoord=x1 + w * (i + 1) / (num_emergency + 1),
                    YCoord=y1 + h / 2,
                    ZCoord=2.6,
                    Status='placed',
                    Description=f'Emergency Light {i+1} in {room.RoomName}'
                )
                db_session.add(device)
                devices.append(device)
        
        db_session.commit()
        self.devices_placed.extend(devices)
        
        for device in devices:
            logger.info(f"Placed {device.Description} at ({device.XCoord}, {device.YCoord}, {device.ZCoord})")
        
        return devices
    
    def calculate_cost(self) -> float:
        """
        Calculate total cost for placed devices.
        
        Costs:
        - LED Panel: $80/panel
        - Exit Sign: $40/sign
        - Emergency Light: $60/light
        
        Returns:
            Total cost in USD
        """
        # Count by device type (simplified)
        n_leds = len([d for d in self.devices_placed])  # Approximate
        n_exits = 1  # One per room
        n_emergency = len([d for d in self.devices_placed])  # Approximate
        
        total_cost = (
            n_leds * self.COST_LED_PANEL +
            n_exits * self.COST_EXIT_SIGN +
            n_emergency * self.COST_EMERGENCY_LIGHT
        )
        
        logger.info(f"Lighting total cost: ${total_cost:.2f}")
        
        return total_cost
    
    def get_device_count(self) -> Dict[str, int]:
        """
        Get count of each device type.
        
        Returns:
            Dict with device type counts
        """
        return {
            'led_panels': len(self.devices_placed),
            'exit_signs': 1,  # Per room
            'emergency_lights': len(self.devices_placed),
            'total': len(self.devices_placed) + 2
        }
    
    def _get_device_type(
        self,
        db_session: Session,
        device_name: str
    ) -> Optional[DeviceType]:
        """
        Get device type by name.
        
        Args:
            db_session: Database session
            device_name: Device type name
            
        Returns:
            DeviceType object or None
        """
        try:
            domain = db_session.query(ProjectDomain).filter(
                ProjectDomain.DomainName == 'Lighting'
            ).first()
            
            if domain:
                return db_session.query(DeviceType).filter(
                    DeviceType.DeviceTypeName == device_name,
                    DeviceType.DomainID == domain.DomainID
                ).first()
        except Exception as e:
            logger.warning(f"Could not find device type {device_name}: {e}")
        
        return None


# =============================================================================
# Helper Functions
# =============================================================================

def create_lighting_system(
    session: Session,
    floor_id: int
) -> LightingLogic:
    """
    Create lighting system for a floor.
    
    Args:
        session: Database session
        floor_id: Floor ID
        
    Returns:
        Configured LightingLogic
    """
    return LightingLogic(session=session)