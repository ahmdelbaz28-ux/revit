"""
Validation Layer - Spatial Normalizer
=================================
Main normalizer that combines all validation steps.
"""

from dataclasses import dataclass
from typing import List, Tuple
from shapely.geometry import Point, Polygon

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from spatial_constraint_engine import Room, Device, Obstruction
from validation.tolerance_model import ToleranceModel
from validation.geometry_repair import (
    repair_polygon,
    is_degenerate,
    is_valid_polygon,
    repair_self_intersection,
    repair_duplicate_points
)
from validation.unit_coercion import coerce_units


# =============================================================================
# Error Types
# =============================================================================

class ErrorSeverity:
    REPAIRED = "REPAIRED"      # Auto-repaired (e.g., simple self-intersection)
    WARNING = "WARNING"        # Ambiguous case needs human review
    CRITICAL = "CRITICAL"    # Cannot process, must reject


@dataclass
class GeometryError:
    """Represents a geometry validation error"""
    message: str
    entity_id: str
    severity: str  # REPAIRED, WARNING, CRITICAL
    original_state: str = ""  # Description of original problem


# =============================================================================
# Spatial Normalizer
# =============================================================================

class SpatialNormalizer:
    """
    Normalizes and validates geometric inputs.
    
    Steps:
    1. Unit conversion (feet -> meters)
    2. Geometry repair (self-intersections, duplicate points)
    3. Degeneracy check
    4. Spatial relationship validation
    5. Coordinate offset normalization (shift to origin)
    """
    
    def __init__(self, tolerance_model: ToleranceModel = None):
        self.tol = tolerance_model or ToleranceModel()
    
    def normalize(
        self,
        room: Room,
        devices: List[Device],
        obstructions: List[Obstruction],
        source_units: str = "meters"
    ) -> Tuple[Room, List[Device], List[Obstruction], List[GeometryError]]:
        """
        Normalize all geometric inputs.
        
        Args:
            room: Room geometry
            devices: List of devices
            obstructions: List of obstructions
            source_units: Source units (feet, meters, etc.)
            
        Returns:
            Tuple of (normalized_room, normalized_devices, normalized_obstructions, errors)
        """
        errors = []
        
        # Step 1: Unit coercion
        room, devices, obstructions, unit_tol = coerce_units(
            room, devices, obstructions, source_units
        )
        
        # Use unit scale factor in tolerance
        effective_scale = unit_tol.unit_scale_factor
        linear_eps = self.tol.linear_epsilon * effective_scale
        area_eps = self.tol.area_epsilon * effective_scale
        
        # Step 2: Repair room geometry
        room_repaired, room_modified = self._repair_room(room, linear_eps, area_eps, errors)
        if not room_repaired:
            return room, [], [], errors
        
        # Step 3: Repair obstruction geometries
        obs_repaired, obs_errors = self._repair_obstructions(
            obstructions, room_repaired.geometry, linear_eps, area_eps, errors
        )
        
        # Step 4: Validate spatial relationships
        rel_errors = self._validate_relationships(
            room_repaired, devices, obs_repaired, area_eps
        )
        errors.extend(rel_errors)
        
        # Step 5: Normalize coordinates to origin (0,0)
        room_final, devices_final = self._normalize_to_origin(
            room_repaired, devices, room_repaired.geometry.bounds
        )
        
        # Step 6: Sort for determinism
        devices_final = sorted(devices_final, key=lambda d: d.id)
        obs_repaired = sorted(obs_repaired, key=lambda o: o.id)
        
        return room_final, devices_final, obs_repaired, errors
    
    def _repair_room(
        self,
        room: Room,
        linear_eps: float,
        area_eps: float,
        errors: List[GeometryError]
    ) -> Tuple[Room, bool]:
        """Repair and validate room geometry"""
        
        # Repair the polygon
        repaired_geom, modified = repair_polygon(room.geometry, self.tol)
        
        # Track repair status
        if modified:
            errors.append(GeometryError(
                message="Room polygon was auto-repaired",
                entity_id=room.id,
                severity=ErrorSeverity.REPAIRED,
                original_state="invalid or self-intersecting"
            ))
        
        # Check for degeneracy
        if is_degenerate(repaired_geom, area_eps):
            errors.append(GeometryError(
                message="Room has zero or near-zero area after repair",
                entity_id=room.id,
                severity=ErrorSeverity.CRITICAL,
                original_state="degenerate polygon"
            ))
            return None, False
        
        # Final validity check
        if not is_valid_polygon(repaired_geom):
            errors.append(GeometryError(
                message="Room polygon cannot be repaired to valid state",
                entity_id=room.id,
                severity=ErrorSeverity.CRITICAL,
                original_state="unrepairable polygon"
            ))
            return None, False
        
        # Create repaired room
        repaired_room = Room(
            id=room.id,
            name=room.name,
            geometry=repaired_geom,
            ceiling_height=room.ceiling_height,
            ceiling_type=room.ceiling_type
        )
        
        return repaired_room, modified
    
    def _repair_obstructions(
        self,
        obstructions: List[Obstruction],
        room_geom: Polygon,
        linear_eps: float,
        area_eps: float,
        errors: List[GeometryError]
    ) -> Tuple[List[Obstruction], List[GeometryError]]:
        """Repair and validate obstruction geometries"""
        
        repaired_obs = []
        obs_errors = []
        
        for obs in obstructions:
            # Repair polygon
            repaired_geom, modified = repair_polygon(obs.geometry, self.tol)
            
            if modified:
                obs_errors.append(GeometryError(
                    message="Obstruction polygon was auto-repaired",
                    entity_id=obs.id,
                    severity=ErrorSeverity.REPAIRED,
                    original_state="invalid or self-intersecting"
                ))
            
            # Check for degeneracy
            if is_degenerate(repaired_geom, area_eps):
                obs_errors.append(GeometryError(
                    message="Obstruction has zero or near-zero area after repair",
                    entity_id=obs.id,
                    severity=ErrorSeverity.WARNING,
                    original_state="degenerate"
                ))
                continue  # Skip this obstruction
            
            # Final validity check
            if not is_valid_polygon(repaired_geom):
                obs_errors.append(GeometryError(
                    message="Obstruction cannot be repaired",
                    entity_id=obs.id,
                    severity=ErrorSeverity.CRITICAL,
                    original_state="unrepairable"
                ))
                continue
            
            # Create repaired obstruction
            repaired_obs.append(Obstruction(
                id=obs.id,
                geometry=repaired_geom,
                height=obs.height,
                blocks_visibility=obs.blocks_visibility
            ))
        
        return repaired_obs, obs_errors
    
    def _validate_relationships(
        self,
        room: Room,
        devices: List[Device],
        obstructions: List[Obstruction],
        area_eps: float
    ) -> List[GeometryError]:
        """Validate spatial relationships between entities"""
        
        errors = []
        room_geom = room.geometry
        
        # Check each device is in room (within or on boundary)
        for device in devices:
            if not room_geom.covers(device.position):
                errors.append(GeometryError(
                    message=f"Device {device.id} is outside room",
                    entity_id=device.id,
                    severity=ErrorSeverity.CRITICAL,
                    original_state="device outside room"
                ))
        
        # Check each obstruction is in room
        for obs in obstructions:
            if not room_geom.contains(obs.geometry):
                errors.append(GeometryError(
                    message=f"Obstruction {obs.id} is not fully inside room",
                    entity_id=obs.id,
                    severity=ErrorSeverity.WARNING,
                    original_state="obstruction partially outside room"
                ))
            
            # Check no device inside obstruction (not on boundary)
            for device in devices:
                if obs.geometry.contains(device.position):
                    errors.append(GeometryError(
                        message=f"Device {device.id} is inside obstruction {obs.id}",
                        entity_id=device.id,
                        severity=ErrorSeverity.CRITICAL,
                        original_state="device inside obstruction"
                    ))
        
        return errors
    
    def _normalize_to_origin(
        self,
        room: Room,
        devices: List[Device],
        bounds: tuple
    ) -> Tuple[Room, List[Device]]:
        """Shift all coordinates so room starts at (0,0)"""
        
        min_x, min_y, max_x, max_y = bounds
        
        # Shift room geometry
        room_coords = list(room.geometry.exterior.coords)
        shifted_coords = [(x - min_x, y - min_y) for x, y in room_coords]
        shifted_geometry = Polygon(shifted_coords)
        
        shifted_room = Room(
            id=room.id,
            name=room.name,
            geometry=shifted_geometry,
            ceiling_height=room.ceiling_height,
            ceiling_type=room.ceiling_type
        )
        
        # Shift device positions
        shifted_devices = []
        for device in devices:
            new_x = device.position.x - min_x
            new_y = device.position.y - min_y
            shifted_devices.append(Device(
                id=device.id,
                device_type=device.device_type,
                position=Point(new_x, new_y),
                z_height=device.z_height,
                coverage_radius=device.coverage_radius
            ))
        
        return shifted_room, shifted_devices


# =============================================================================
# Tests
# =============================================================================

def run_test(name: str, room, devices, obstructions, source_units, expected_errors: int = None):
    """Run a normalization test."""
    print("=" * 60)
    print(f"TEST: {name}")
    print("=" * 60)
    
    try:
        normalizer = SpatialNormalizer()
        norm_room, norm_devices, norm_obs, errors = normalizer.normalize(
            room, devices, obstructions, source_units
        )
        
        print(f"Source units: {source_units}")
        print(f"Original room bounds: {room.geometry.bounds}")
        print(f"Normalized room bounds: {norm_room.geometry.bounds}")
        print(f"Total errors: {len(errors)}")
        
        for e in errors:
            print(f"  [{e.severity}] {e.entity_id}: {e.message}")
        
        if expected_errors is not None:
            print(f"\nExpected errors: {expected_errors}")
            if len(errors) == expected_errors:
                print("✓ Test result matches expected")
            else:
                print(f"✗ Expected {expected_errors}, got {len(errors)}")
        
        print("=" * 60)
        
    except Exception as ex:
        print(f"Error: {ex}")
        print("=" * 60)
    
    return errors


if __name__ == "__main__":
    from shapely.geometry import Point, Polygon
    from spatial_constraint_engine import Room, Device, Obstruction
    
    # Test 1: Unit conversion (feet to meters)
    print("\n" + "=" * 60)
    print("TEST 1: Feet to Meters Conversion")
    print("=" * 60)
    
    room_feet = Room(
        id="room_ft",
        name="Room 32.8ft x 32.8ft",
        geometry=Polygon([(0, 0), (32.8, 0), (32.8, 32.8), (0, 32.8), (0, 0)]),
        ceiling_height=8.0
    )
    devices_feet = [
        Device(id="smoke_1", device_type="SMOKE_PHOTOELECTRIC", position=Point(16.4, 16.4)),
    ]
    obstructions_feet = []
    
    run_test("Feet to Meters", room_feet, devices_feet, obstructions_feet, "feet", 0)
    
    # Test 2: Self-intersecting polygon (bowtie)
    print("\n\n")
    
    # Create a bowtie / figure-8 polygon
    bowtie_coords = [(0, 0), (10, 5), (0, 10), (5, 5), (0, 0)]
    # This is a simple self-intersecting polygon
    bowtie_room = Room(
        id="room_bowtie",
        name="Bowtie Room",
        geometry=Polygon(bowtie_coords),
        ceiling_height=3.0
    )
    bowtie_devices = []
    bowtie_obs = []
    
    run_test("Self-Intersecting Polygon", bowtie_room, bowtie_devices, bowtie_obs, "meters")
    
    # Test 3: Device outside room
    print("\n\n")
    
    room3 = Room(
        id="room_003",
        name="Room with Outside Device",
        geometry=Polygon([(0, 0), (10, 0), (10, 10), (0, 10), (0, 0)]),
        ceiling_height=3.0
    )
    devices3 = [
        Device(id="smoke_inside", device_type="SMOKE_PHOTOELECTRIC", position=Point(5, 5)),
        Device(id="smoke_outside", device_type="SMOKE_PHOTOELECTRIC", position=Point(15, 15)),  # Outside!
    ]
    obstructions3 = []
    
    run_test("Device Outside Room", room3, devices3, obstructions3, "meters", 1)
    
    # Test 4: Obstruction outside room
    print("\n\n")
    
    room4 = Room(
        id="room_004",
        name="Room with Outside Obstruction",
        geometry=Polygon([(0, 0), (10, 0), (10, 10), (0, 10), (0, 0)]),
        ceiling_height=3.0
    )
    devices4 = [
        Device(id="smoke_1", device_type="SMOKE_PHOTOELECTRIC", position=Point(5, 5)),
    ]
    obstructions4 = [
        Obstruction(
            id="wall_outside",
            geometry=Polygon([(15, 15), (16, 15), (16, 16), (15, 16), (15, 15)]),
            height=3.0,
            blocks_visibility=True
        )
    ]
    
    run_test("Obstruction Outside Room", room4, devices4, obstructions4, "meters", 1)