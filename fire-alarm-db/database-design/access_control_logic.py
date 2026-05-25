#!/usr/bin/env python3
"""
access_control_logic.py - Access Control Engineering Logic
===============================================

Engineering logic for Access Control systems.
Places Card Readers, Electric Locks, and Exit Buttons at room door locations.

Usage:
    logic = AccessControlLogic(session)
    devices = logic.place_devices(room, session.SessionID, session)
    cost = logic.calculate_cost()
"""

import logging
from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session

from ai_design_integration import EngineeringLogic, AIDesignDevice, DeviceType, ProjectDomain

logger = logging.getLogger(__name__)


class AccessControlLogic(EngineeringLogic):
    """
    Access Control system engineering logic.
    
    Places security devices:
    - Card Reader: At each room door entry point (z=1.2m)
    - Electric Lock: On door frame per reader
    - Exit Button: Inside room near door (z=1.1m)
    """
    
    # Device costs (USD)
    COST_CARD_READER = 200.0
    COST_ELECTRIC_LOCK = 150.0
    COST_EXIT_BUTTON = 50.0
    
    def __init__(self, session: Session):
        """Initialize Access Control logic"""
        super().__init__(session=session, domain='AccessControl')
        self.devices_placed = []
    
    def place_devices(
        self,
        room: Any,
        session_id: int,
        db_session: Session
    ) -> List[AIDesignDevice]:
        """
        Place access control devices for a room.
        
        Args:
            room: Room object with room properties
            session_id: Design session ID
            db_session: SQLAlchemy session
            
        Returns:
            List of placed AIDesignDevice objects
        """
        devices = []
        
        # Find device type IDs
        card_reader_type = self._get_device_type(db_session, 'CardReader')
        electric_lock_type = self._get_device_type(db_session, 'ElectricLock')
        exit_button_type = self._get_device_type(db_session, 'ExitButton')
        
        # Get room geometry
        x1, y1 = room.XCoord or 0, room.YCoord or 0
        x2, y2 = x1 + (room.WidthMeters or 10), y1 + (room.HeightMeters or 10)
        room_center_y = y1 + (room.HeightMeters or 10) / 2
        
        # Place Card Reader at room door (x1, center of room width)
        if card_reader_type:
            device = AIDesignDevice(
                SessionID=session_id,
                RoomID=room.RoomID,
                DeviceTypeID=card_reader_type.DeviceTypeID,
                XCoord=x1,  # At door
                YCoord=y1 + (room.HeightMeters or 10) / 2,  # Center
                ZCoord=1.2,  # Eye level
                Status='placed',
                Description=f'Card Reader at {room.RoomName} entrance'
            )
            db_session.add(device)
            devices.append(device)
            logger.info(f"Placed Card Reader at ({device.XCoord}, {device.YCoord}, {device.ZCoord})")
        
        # Place Electric Lock at same location
        if electric_lock_type:
            device = AIDesignDevice(
                SessionID=session_id,
                RoomID=room.RoomID,
                DeviceTypeID=electric_lock_type.DeviceTypeID,
                XCoord=x1,
                YCoord=y1 + (room.HeightMeters or 10) / 2,
                ZCoord=1.0,  # Door height
                Status='placed',
                Description=f'Electric Lock at {room.RoomName} door'
            )
            db_session.add(device)
            devices.append(device)
            logger.info(f"Placed Electric Lock at ({device.XCoord}, {device.YCoord}, {device.ZCoord})")
        
        # Place Exit Button inside room (near x1, z=1.1m)
        if exit_button_type:
            device = AIDesignDevice(
                SessionID=session_id,
                RoomID=room.RoomID,
                DeviceTypeID=exit_button_type.DeviceTypeID,
                XCoord=x1 + 0.5,  # Inside room
                YCoord=y1 + (room.HeightMeters or 10) / 2,  # Center
                ZCoord=1.1,  # Reach height
                Status='placed',
                Description=f'Exit Button at {room.RoomName} interior'
            )
            db_session.add(device)
            devices.append(device)
            logger.info(f"Placed Exit Button at ({device.XCoord}, {device.YCoord}, {device.ZCoord})")
        
        db_session.commit()
        self.devices_placed.extend(devices)
        
        return devices
    
    def calculate_cost(self) -> float:
        """
        Calculate total cost for placed devices.
        
        Costs:
        - Card Reader: $200/reader
        - Electric Lock: $150/lock
        - Exit Button: $50/button
        
        Returns:
            Total cost in USD
        """
        card_readers = sum(
            1 for d in self.devices_placed
            if 'Card' in (d.DeviceTypeID or '')
        )
        
        # Count by device type (simplified - would need actual DeviceTypeID lookup)
        n_readers = len([d for d in self.devices_placed])
        n_locks = len([d for d in self.devices_placed])
        n_buttons = len([d for d in self.devices_placed])
        
        # Approximate cost: 1 reader + 1 lock + 1 button per room
        # Each room gets 3 devices
        n_rooms = len(self.devices_placed) // 3 if self.devices_placed else 0
        
        total_cost = (
            n_rooms * self.COST_CARD_READER +
            n_rooms * self.COST_ELECTRIC_LOCK +
            n_rooms * self.COST_EXIT_BUTTON
        )
        
        logger.info(f"Access Control total cost: ${total_cost:.2f}")
        
        return total_cost
    
    def get_device_count(self) -> Dict[str, int]:
        """
        Get count of each device type.
        
        Returns:
            Dict with device type counts
        """
        return {
            'card_readers': len(self.devices_placed),
            'electric_locks': len(self.devices_placed),
            'exit_buttons': len(self.devices_placed),
            'total': len(self.devices_placed)
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
                ProjectDomain.DomainName == 'AccessControl'
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

def create_access_control_system(
    session: Session,
    floor_id: int
) -> AccessControlLogic:
    """
    Create access control system for a floor.
    
    Args:
        session: Database session
        floor_id: Floor ID
        
    Returns:
        Configured AccessControlLogic
    """
    return AccessControlLogic(session=session)