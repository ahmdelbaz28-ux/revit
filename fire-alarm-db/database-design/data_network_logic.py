#!/usr/bin/env python3
"""
data_network_logic.py - Data Network Engineering Logic
=====================================================

Engineering logic for Data and Network systems.
Places Data Outlets, Wireless Access Points, and Network Racks.

Usage:
    logic = DataNetworkLogic(session)
    devices = logic.place_devices(room, session.SessionID, session)
    cost = logic.calculate_cost()
"""

import logging
from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session

from ai_design_integration import EngineeringLogic, AIDesignDevice, DeviceType, ProjectDomain

logger = logging.getLogger(__name__)


class DataNetworkLogic(EngineeringLogic):
    """
    Data Network system engineering logic.
    
    Places network devices:
    - Data Outlet: 2 per room at z=0.3m
    - Wireless Access Point: 1 per 50 sqm
    - Network Rack: 1 per floor
    """
    
    # Device costs (USD)
    COST_DATA_OUTLET = 20.0
    COST_WIRELESS_AP = 150.0
    COST_NETWORK_RACK = 500.0
    
    def __init__(self, session: Session):
        """Initialize Data Network logic"""
        super().__init__(session=session, domain='DataNetwork')
        self.devices_placed = []
        self.aps_placed = 0
    
    def place_devices(
        self,
        room: Any,
        session_id: int,
        db_session: Session
    ) -> List[AIDesignDevice]:
        """
        Place data network devices for a room.
        
        Args:
            room: Room object with room properties
            session_id: Design session ID
            db_session: SQLAlchemy session
            
        Returns:
            List of placed AIDesignDevice objects
        """
        devices = []
        
        # Get device type IDs
        outlet_type = self._get_device_type(db_session, 'DataOutlet')
        ap_type = self._get_device_type(db_session, 'WirelessAP')
        
        # Get room geometry
        room_area = (room.WidthMeters or 10) * (room.HeightMeters or 10)
        
        # Place 2 Data Outlets per room
        if outlet_type:
            for i in range(2):
                device = AIDesignDevice(
                    SessionID=session_id,
                    RoomID=room.RoomID,
                    DeviceTypeID=outlet_type.DeviceTypeID,
                    XCoord=(room.XCoord or 0) + (i * 2),
                    YCoord=(room.YCoord or 0) + 1,
                    ZCoord=0.3,  # Desk height
                    Status='placed',
                    Description=f'Data Outlet {i+1} in {room.RoomName}'
                )
                db_session.add(device)
                devices.append(device)
        
        # Place Wireless AP if room > 50 sqm
        if room_area > 50 and ap_type:
            device = AIDesignDevice(
                SessionID=session_id,
                RoomID=room.RoomID,
                DeviceTypeID=ap_type.DeviceTypeID,
                XCoord=(room.XCoord or 0) + (room.WidthMeters or 10) / 2,
                YCoord=(room.YCoord or 0) + (room.HeightMeters or 10) / 2,
                ZCoord=2.5,  # Ceiling mount
                Status='placed',
                Description=f'Wireless AP in {room.RoomName}'
            )
            db_session.add(device)
            devices.append(device)
            self.aps_placed += 1
        
        db_session.commit()
        self.devices_placed.extend(devices)
        
        for device in devices:
            logger.info(f"Placed {device.Description} at ({device.XCoord}, {device.YCoord}, {device.ZCoord})")
        
        return devices
    
    def place_floor_rack(
        self,
        floor_id: int,
        session_id: int,
        x: float,
        y: float,
        db_session: Session
    ) -> Optional[AIDesignDevice]:
        """
        Place network rack for the floor.
        
        Args:
            floor_id: Floor ID
            session_id: Design session ID
            x: X coordinate
            y: Y coordinate
            db_session: Database session
            
        Returns:
            Placed device or None
        """
        rack_type = self._get_device_type(db_session, 'NetworkRack')
        
        if rack_type:
            device = AIDesignDevice(
                SessionID=session_id,
                FloorID=floor_id,
                DeviceTypeID=rack_type.DeviceTypeID,
                XCoord=x,
                YCoord=y,
                ZCoord=0.0,  # Floor level
                Status='placed',
                Description='Floor Network Rack'
            )
            db_session.add(device)
            db_session.commit()
            
            logger.info(f"Placed Network Rack at ({x}, {y})")
            return device
        
        return None
    
    def calculate_cost(self) -> float:
        """
        Calculate total cost for placed devices.
        
        Costs:
        - Data Outlet: $20/outlet
        - Wireless AP: $150/AP
        - Network Rack: $500/rack
        
        Returns:
            Total cost in USD
        """
        outlets = len([d for d in self.devices_placed])  # Approximate
        aps = self.aps_placed
        racks = 1  # One per floor (would need floor count)
        
        total_cost = (
            outlets * self.COST_DATA_OUTLET +
            aps * self.COST_WIRELESS_AP +
            racks * self.COST_NETWORK_RACK
        )
        
        logger.info(f"Data Network total cost: ${total_cost:.2f}")
        
        return total_cost
    
    def get_device_count(self) -> Dict[str, int]:
        """
        Get count of each device type.
        
        Returns:
            Dict with device type counts
        """
        return {
            'data_outlets': len(self.devices_placed),
            'wireless_aps': self.aps_placed,
            'network_racks': 1,
            'total': len(self.devices_placed) + self.aps_placed + 1
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
                ProjectDomain.DomainName == 'DataNetwork'
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

def create_data_network_system(
    session: Session,
    floor_id: int
) -> DataNetworkLogic:
    """
    Create data network system for a floor.
    
    Args:
        session: Database session
        floor_id: Floor ID
        
    Returns:
        Configured DataNetworkLogic
    """
    return DataNetworkLogic(session=session)