#!/usr/bin/env python3
"""
power_logic.py - Power Distribution Engineering Logic
===================================================

Engineering logic for Electrical Power Distribution systems.
Places Socket Outlets, Distribution Boards, MCBs, and RCCBs.

Usage:
    logic = PowerLogic(session)
    devices = logic.place_devices(room, session.SessionID, session)
    cost = logic.calculate_cost()
"""

import logging
from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session

from ai_design_integration import EngineeringLogic, AIDesignDevice, DeviceType, ProjectDomain

logger = logging.getLogger(__name__)


class PowerLogic(EngineeringLogic):
    """
    Power Distribution system engineering logic.
    
    Places power devices:
    - Socket Outlet: 1 per 10 sqm (z=0.3m desk height)
    - Distribution Board: 1 per floor
    - MCB: Per circuit in DB
    - RCCB: 1 per DB
    """
    
    # Device costs (USD)
    COST_SOCKET = 15.0
    COST_DISTRIBUTION_BOARD = 300.0
    COST_MCB = 20.0
    
    def __init__(self, session: Session):
        """Initialize Power logic"""
        super().__init__(session=session, domain='Power')
        self.devices_placed = []
        self.dbs_placed = 0
    
    def place_devices(
        self,
        room: Any,
        session_id: int,
        db_session: Session
    ) -> List[AIDesignDevice]:
        """
        Place power devices for a room.
        
        Args:
            room: Room object with room properties
            session_id: Design session ID
            db_session: SQLAlchemy session
            
        Returns:
            List of placed AIDesignDevice objects
        """
        devices = []
        
        # Get device type IDs
        socket_type = self._get_device_type(db_session, 'SocketOutlet')
        mcb_type = self._get_device_type(db_session, 'MCB')
        
        # Get room geometry
        x1, y1 = room.XCoord or 0, room.YCoord or 0
        w, h = room.WidthMeters or 10, room.HeightMeters or 10
        room_area = w * h
        
        # Place Socket Outlets: 1 per 10 sqm
        num_sockets = max(1, int(room_area / 10))
        if socket_type:
            for i in range(num_sockets):
                device = AIDesignDevice(
                    SessionID=session_id,
                    RoomID=room.RoomID,
                    DeviceTypeID=socket_type.DeviceTypeID,
                    XCoord=x1 + (i % 3) * 2,
                    YCoord=y1 + (i // 3) * 2,
                    ZCoord=0.3,  # Desk height
                    Status='placed',
                    Description=f'Socket Outlet {i+1} in {room.RoomName}'
                )
                db_session.add(device)
                devices.append(device)
        
        # Place MCBs per room (simplified - would connect to DB)
        if mcb_type:
            device = AIDesignDevice(
                SessionID=session_id,
                RoomID=room.RoomID,
                DeviceTypeID=mcb_type.DeviceTypeID,
                XCoord=x1,
                YCoord=y1,
                ZCoord=1.5,  # Wall mounted
                Status='placed',
                Description=f'MCB for {room.RoomName}'
            )
            db_session.add(device)
            devices.append(device)
        
        db_session.commit()
        self.devices_placed.extend(devices)
        
        for device in devices:
            logger.info(f"Placed {device.Description} at ({device.XCoord}, {device.YCoord}, {device.ZCoord})")
        
        return devices
    
    def place_distribution_board(
        self,
        floor_id: int,
        session_id: int,
        x: float,
        y: float,
        db_session: Session
    ) -> Optional[AIDesignDevice]:
        """
        Place distribution board for the floor.
        
        Args:
            floor_id: Floor ID
            session_id: Design session ID
            x: X coordinate
            y: Y coordinate
            db_session: Database session
            
        Returns:
            Placed device or None
        """
        db_type = self._get_device_type(db_session, 'DistributionBoard')
        rccb_type = self._get_device_type(db_session, 'RCCB')
        
        devices = []
        
        if db_type:
            device = AIDesignDevice(
                SessionID=session_id,
                FloorID=floor_id,
                DeviceTypeID=db_type.DeviceTypeID,
                XCoord=x,
                YCoord=y,
                ZCoord=1.5,  # Wall height
                Status='placed',
                Description=f'Distribution Board for Floor {floor_id}'
            )
            db_session.add(device)
            devices.append(device)
            self.dbs_placed += 1
        
        # Add RCCB protection
        if rccb_type:
            device = AIDesignDevice(
                SessionID=session_id,
                FloorID=floor_id,
                DeviceTypeID=rccb_type.DeviceTypeID,
                XCoord=x + 0.5,
                YCoord=y,
                ZCoord=1.5,
                Status='placed',
                Description=f'RCCB for Floor {floor_id}'
            )
            db_session.add(device)
            devices.append(device)
        
        db_session.commit()
        
        logger.info(f"Placed Distribution Board at ({x}, {y})")
        
        return devices[0] if devices else None
    
    def calculate_cost(self) -> float:
        """
        Calculate total cost for placed devices.
        
        Costs:
        - Socket Outlet: $15/socket
        - Distribution Board: $300/DB
        - MCB: $20/MCB
        - RCCB: Included with DB
        
        Returns:
            Total cost in USD
        """
        sockets = len([d for d in self.devices_placed])  # Approximate
        dbs = self.dbs_placed
        mcbs = len([d for d in self.devices_placed])  # Approximate
        
        total_cost = (
            sockets * self.COST_SOCKET +
            dbs * self.COST_DISTRIBUTION_BOARD +
            mcbs * self.COST_MCB
        )
        
        logger.info(f"Power Distribution total cost: ${total_cost:.2f}")
        
        return total_cost
    
    def get_device_count(self) -> Dict[str, int]:
        """
        Get count of each device type.
        
        Returns:
            Dict with device type counts
        """
        return {
            'socket_outlets': len(self.devices_placed),
            'distribution_boards': self.dbs_placed,
            'mcbs': len(self.devices_placed),
            'total': len(self.devices_placed) + self.dbs_placed
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
                ProjectDomain.DomainName == 'Power'
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

def create_power_system(
    session: Session,
    floor_id: int
) -> PowerLogic:
    """
    Create power distribution system for a floor.
    
    Args:
        session: Database session
        floor_id: Floor ID
        
    Returns:
        Configured PowerLogic
    """
    return PowerLogic(session=session)