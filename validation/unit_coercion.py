"""
Validation Layer - Unit Coercion
===============================
Converts input geometries from source units to meters.
"""

from typing import List, Tuple
from shapely.geometry import Point, Polygon

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from spatial_constraint_engine import Room, Device, Obstruction
from validation.tolerance_model import ToleranceModel


# Unit conversion factors to meters
UNIT_TO_METERS = {
    "feet": 0.3048,
    "foot": 0.3048,
    "ft": 0.3048,
    "meters": 1.0,
    "meter": 1.0,
    "m": 1.0,
    "millimeters": 0.001,
    "millimeter": 0.001,
    "mm": 0.001,
    "inches": 0.0254,
    "inch": 0.0254,
    "in": 0.0254,
    "centimeters": 0.01,
    "centimeter": 0.01,
    "cm": 0.01,
}


def coerce_units(
    room: Room,
    devices: List[Device],
    obstructions: List[Obstruction],
    source_units: str = "feet"
) -> Tuple[Room, List[Device], List[Obstruction], ToleranceModel]:
    """
    Convert room, devices, and obstructions from source_units to meters.
    
    Args:
        room: Room with original coordinates
        devices: List of devices with original coordinates
        obstructions: List of obstructions with original coordinates
        source_units: Source unit (feet, meters, millimeters, etc.)
        
    Returns:
        Tuple of (converted_room, converted_devices, converted_obstructions, tolerance_model)
    """
    # Get conversion factor
    source_units_lower = source_units.lower()
    if source_units_lower not in UNIT_TO_METERS:
        raise ValueError(f"Unknown unit: {source_units}. Supported: {list(UNIT_TO_METERS.keys())}")
    
    factor = UNIT_TO_METERS[source_units_lower]
    
    # If already in meters, return as-is
    if factor == 1.0:
        tol = ToleranceModel(unit_scale_factor=1.0)
        return room, devices, obstructions, tol
    
    # Convert room geometry
    room_coords = list(room.geometry.exterior.coords)
    converted_room_coords = [(x * factor, y * factor) for x, y in room_coords]
    converted_room_geometry = Polygon(converted_room_coords)
    
    converted_room = Room(
        id=room.id,
        name=room.name,
        geometry=converted_room_geometry,
        ceiling_height=room.ceiling_height * factor,
        ceiling_type=room.ceiling_type
    )
    
    # Convert devices
    converted_devices = []
    for device in devices:
        new_position = Point(device.position.x * factor, device.position.y * factor)
        converted_devices.append(Device(
            id=device.id,
            device_type=device.device_type,
            position=new_position,
            z_height=device.z_height * factor if hasattr(device, 'z_height') else device.z_height,
            coverage_radius=device.coverage_radius * factor if hasattr(device, 'coverage_radius') else device.coverage_radius
        ))
    
    # Convert obstructions
    converted_obstructions = []
    for obs in obstructions:
        obs_coords = list(obs.geometry.exterior.coords)
        converted_obs_coords = [(x * factor, y * factor) for x, y in obs_coords]
        converted_obs_geometry = Polygon(converted_obs_coords)
        
        converted_obstructions.append(Obstruction(
            id=obs.id,
            geometry=converted_obs_geometry,
            height=obs.height * factor,
            blocks_visibility=obs.blocks_visibility
        ))
    
    # Create tolerance model with scale factor
    tol = ToleranceModel(unit_scale_factor=factor)
    
    return converted_room, converted_devices, converted_obstructions, tol