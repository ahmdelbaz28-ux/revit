"""
Normalization Service
=====================
Application service for normalizing and validating input data.

This service ensures all input data conforms to expected formats
before processing by domain logic.
"""

from typing import List, Optional, Dict, Any
from ..domain.models import Room, Device, Polygon, Point, RoomType, DeviceType


class NormalizationService:
    """
    Service for normalizing and validating input data.
    
    Responsibilities:
    - Normalize room data from various sources (CAD, BIM, manual)
    - Normalize device data from AI detection or manual input
    - Validate required fields and data types
    - Convert between coordinate systems if needed
    """
    
    def normalize_room(self, room_data: Dict[str, Any]) -> Room:
        """
        Normalize room data into a Room object.
        
        Args:
            room_data: Raw room data from any source
            
        Returns:
            Normalized Room object
        """
        # Extract and normalize polygon
        polygon = None
        if 'polygon' in room_data and room_data['polygon']:
            polygon = self._normalize_polygon(room_data['polygon'])
        
        # Normalize room type
        room_type = RoomType.OTHER
        if 'room_type' in room_data:
            room_type = self._normalize_room_type(room_data['room_type'])
        
        # Create room object
        room = Room(
            room_id=room_data.get('room_id'),
            name=room_data.get('name', ''),
            room_type=room_type,
            polygon=polygon,
            length=room_data.get('length'),
            width=room_data.get('width'),
            height=float(room_data.get('height', 3.0)),
            area=room_data.get('area'),
            occupancy_load=room_data.get('occupancy_load'),
            floor_number=int(room_data.get('floor_number', 1)),
            project_id=room_data.get('project_id')
        )
        
        return room
    
    def normalize_device(self, device_data: Dict[str, Any]) -> Device:
        """
        Normalize device data into a Device object.
        
        Args:
            device_data: Raw device data from any source
            
        Returns:
            Normalized Device object
        """
        # Normalize device type
        device_type = DeviceType.SMOKE_DETECTOR
        if 'device_type' in device_data:
            device_type = self._normalize_device_type(device_data['device_type'])
        
        # Normalize position
        position = None
        x = device_data.get('x')
        y = device_data.get('y')
        z = device_data.get('z', 0.0)
        
        if 'position' in device_data and device_data['position']:
            pos_data = device_data['position']
            x = pos_data.get('x', x)
            y = pos_data.get('y', y)
            z = pos_data.get('z', z)
        
        if x is not None and y is not None:
            position = Point(x=float(x), y=float(y), z=float(z))
        
        # Create device object
        device = Device(
            device_id=device_data.get('device_id'),
            device_type=device_type,
            position=position,
            x=float(x) if x is not None else None,
            y=float(y) if y is not None else None,
            z=float(z) if z is not None else None,
            orientation=float(device_data.get('orientation', 0.0)),
            coverage_radius=float(device_data.get('coverage_radius', 7.5)),
            loop_id=device_data.get('loop_id'),
            address=device_data.get('address'),
            is_approved=bool(device_data.get('is_approved', False)),
            room_id=device_data.get('room_id'),
            session_id=device_data.get('session_id'),
            confidence=float(device_data.get('confidence', 1.0)),
            ai_justification=device_data.get('ai_justification'),
            manufacturer=device_data.get('manufacturer'),
            model=device_data.get('model')
        )
        
        return device
    
    def _normalize_polygon(self, polygon_data: Any) -> Optional[Polygon]:
        """Normalize polygon data from various formats"""
        if isinstance(polygon_data, Polygon):
            return polygon_data
        
        if isinstance(polygon_data, dict):
            exterior = polygon_data.get('exterior', [])
            holes = polygon_data.get('holes', [])
            
            exterior_points = [self._normalize_point(p) for p in exterior]
            hole_lists = []
            for hole in holes:
                hole_points = [self._normalize_point(p) for p in hole]
                hole_lists.append(hole_points)
            
            return Polygon(exterior=exterior_points, holes=hole_lists)
        
        if isinstance(polygon_data, list):
            # Assume it's a list of points
            points = [self._normalize_point(p) for p in polygon_data]
            return Polygon(exterior=points)
        
        return None
    
    def _normalize_point(self, point_data: Any) -> Point:
        """Normalize point data from various formats"""
        if isinstance(point_data, Point):
            return point_data
        
        if isinstance(point_data, dict):
            return Point(
                x=float(point_data.get('x', 0)),
                y=float(point_data.get('y', 0)),
                z=float(point_data.get('z', 0))
            )
        
        if isinstance(point_data, (list, tuple)) and len(point_data) >= 2:
            return Point(
                x=float(point_data[0]),
                y=float(point_data[1]),
                z=float(point_data[2]) if len(point_data) > 2 else 0.0
            )
        
        return Point(x=0, y=0, z=0)
    
    def _normalize_room_type(self, room_type_value: Any) -> RoomType:
        """Normalize room type from string or other format"""
        if isinstance(room_type_value, RoomType):
            return room_type_value
        
        if isinstance(room_type_value, str):
            # Try to match enum value
            try:
                return RoomType(room_type_value)
            except ValueError:
                # Try case-insensitive matching
                for rt in RoomType:
                    if rt.value.lower() == room_type_value.lower():
                        return rt
                # Try snake_case to PascalCase conversion
                formatted = room_type_value.replace('_', '').title().replace(' ', '')
                for rt in RoomType:
                    if rt.value.lower() == formatted.lower():
                        return rt
        
        return RoomType.OTHER
    
    def _normalize_device_type(self, device_type_value: Any) -> DeviceType:
        """Normalize device type from string or other format"""
        if isinstance(device_type_value, DeviceType):
            return device_type_value
        
        if isinstance(device_type_value, str):
            try:
                return DeviceType(device_type_value)
            except ValueError:
                # Try case-insensitive matching
                for dt in DeviceType:
                    if dt.value.lower() == device_type_value.lower():
                        return dt
                # Common aliases
                aliases = {
                    'smoke': DeviceType.SMOKE_DETECTOR,
                    'heat': DeviceType.HEAT_DETECTOR,
                    'mcp': DeviceType.MANUAL_CALL_POINT,
                    'manual_call_point': DeviceType.MANUAL_CALL_POINT,
                    'sounder': DeviceType.SOUNDER,
                    'strobe': DeviceType.STROBE,
                    'speaker': DeviceType.SPEAKER,
                }
                if device_type_value.lower() in aliases:
                    return aliases[device_type_value.lower()]
        
        return DeviceType.SMOKE_DETECTOR
    
    def validate_room(self, room: Room) -> List[str]:
        """
        Validate normalized room has required fields.
        
        Returns:
            List of validation error messages
        """
        errors = []
        
        if not room.name:
            errors.append("Room name is required")
        
        if room.area is not None and room.area <= 0:
            errors.append("Room area must be positive")
        
        if room.height is not None and room.height <= 0:
            errors.append("Room height must be positive")
        
        return errors
    
    def validate_device(self, device: Device) -> List[str]:
        """
        Validate normalized device has required fields.
        
        Returns:
            List of validation error messages
        """
        errors = []
        
        if device.position is None and (device.x is None or device.y is None):
            errors.append("Device position is required")
        
        if device.coverage_radius is not None and device.coverage_radius <= 0:
            errors.append("Device coverage radius must be positive")
        
        return errors
