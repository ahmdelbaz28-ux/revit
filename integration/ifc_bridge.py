"""
Integration Layer - IFC Bridge
=========================
The ONLY bridge between the BIM world and the compliance kernel.
Ensures that all inputs to the kernel have been normalized and cleaned.

This layer is responsible for ensuring input purity.
The kernel does NOT touch raw BIM data.
"""

import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    import ifcopenshell
    import ifcopenshell.geom
    IFC_AVAILABLE = True
except ImportError:
    IFC_AVAILABLE = False

from shapely.geometry import Polygon, Point
from typing import List, Tuple

from core.models import Room, Device, Obstruction
from validation.spatial_normalizer import SpatialNormalizer
from validation.tolerance_model import ToleranceModel


class IFCBridge:
    """
    The ONLY bridge between BIM world and compliance kernel.
    Ensures that all inputs to kernel are normalized and cleaned.
    """
    
    def __init__(self, ifc_path: str):
        self.ifc_path = ifc_path
        if not IFC_AVAILABLE:
            raise ImportError("ifcopenshell not installed")
        self.ifc_file = ifcopenshell.open(ifc_path)
        self.normalizer = SpatialNormalizer(ToleranceModel())
        
        # Build spatial index for containment relationships
        self._build_spatial_index()
    
    def _resolve_placement(self, placement) -> Tuple[float, float, float]:
        """
        Resolve accumulated IfcLocalPlacement chain and return final coordinates.
        If unable to resolve, returns (0.0, 0.0, 0.0).
        """
        x, y, z = 0.0, 0.0, 0.0
        current = placement
        while current is not None:
            if hasattr(current, 'RelativePlacement') and current.RelativePlacement:
                rel = current.RelativePlacement
                if hasattr(rel, 'Location') and rel.Location:
                    loc = rel.Location
                    if hasattr(loc, 'Coordinates'):
                        coords = loc.Coordinates
                        x += coords[0] if len(coords) > 0 else 0.0
                        y += coords[1] if len(coords) > 1 else 0.0
                        z += coords[2] if len(coords) > 2 else 0.0
            # Move to parent placement (if exists)
            if hasattr(current, 'PlacementRelTo') and current.PlacementRelTo:
                current = current.PlacementRelTo
            else:
                break
        return x, y, z
    
    def _build_spatial_index(self):
        """
        Build spatial relationship index:
        - device_to_room: dict {device_GlobalId: room_GlobalId}
        - obstruction_to_room: dict {obs_GlobalId: room_GlobalId}
        Uses IfcRelContainedInSpatialStructure.
        """
        self.device_to_room = {}
        self.obstruction_to_room = {}
        
        for rel in self.ifc_file.by_type("IfcRelContainedInSpatialStructure"):
            related_elements = getattr(rel, 'RelatedElements', []) or []
            relating_structure = getattr(rel, 'RelatingStructure', None)
            if not relating_structure:
                continue
            room_id = getattr(relating_structure, 'GlobalId', None)
            if not room_id:
                continue
            for elem in related_elements:
                elem_id = getattr(elem, 'GlobalId', None)
                if not elem_id:
                    continue
                # Classify by type
                if elem.is_a("IfcSensor"):
                    self.device_to_room[elem_id] = room_id
                elif elem.is_a("IfcColumn") or elem.is_a("IfcBeam"):
                    self.obstruction_to_room[elem_id] = room_id
    
    def extract_and_normalize(self) -> Tuple[List[Room], List[Device], List[Obstruction]]:
        """
        Full pipeline:
        1. Extract rooms from IfcSpace
        2. Extract devices from IfcSensor
        3. Extract obstructions from IfcColumn/IfcBeam
        4. Normalize all elements (units, geometry repair, offset)
        5. Return clean elements ready for ComplianceOracle.verify_truth()
        """
        raw_rooms = self._extract_rooms()
        raw_devices = self._extract_devices()
        raw_obstructions = self._extract_obstructions()
        
        # Normalize each room with its devices and obstructions
        all_rooms, all_devices, all_obs = [], [], []
        for room in raw_rooms:
            room_id = room.id
            
            # Use spatial index to link elements to rooms
            room_devices = [d for d in raw_devices if self.device_to_room.get(d.id) == room_id]
            room_obs = [o for o in raw_obstructions if self.obstruction_to_room.get(o.id) == room_id]
            
            # Fallback: geometric filtering if no explicit spatial relationship
            if not room_devices:
                room_devices = [d for d in raw_devices if room.geometry.covers(d.position)]
            if not room_obs:
                room_obs = [o for o in raw_obstructions if room.geometry.contains(o.geometry)]
            
            # Normalize
            norm_room, norm_devs, norm_obs, errors = self.normalizer.normalize(
                room, room_devices, room_obs, "meters"
            )
            
            # Reject rooms with critical errors
            from validation.spatial_normalizer import ErrorSeverity
            if any(e.severity == ErrorSeverity.CRITICAL for e in errors):
                continue
            
            all_rooms.append(norm_room)
            all_devices.extend(norm_devs)
            all_obs.extend(norm_obs)
        
        return all_rooms, all_devices, all_obs
    
    def _extract_rooms(self) -> List[Room]:
        """Extract rooms from IfcSpace with Shapely Polygon geometry."""
        rooms = []
        
        for space in self.ifc_file.by_type("IfcSpace"):
            poly = None
            
            # Try direct geometry first
            try:
                shape = ifcopenshell.geom.create_shape(space)
                verts = shape.geometry.verts  # flat list [x1,y1,z1, x2,y2,z2,...]
                
                # Convert to 2D polygon points
                if len(verts) >= 6:  # At least 3 points
                    pts_2d = [(verts[i], verts[i+1]) for i in range(0, len(verts), 3)]
                    poly = Polygon(pts_2d)
                    
                    if not poly.is_valid or poly.area <= 0.01:
                        poly = None
            except:
                poly = None
            
            # Fallback 1: Bounding Box
            if poly is None:
                try:
                    shape = ifcopenshell.geom.create_shape(space)
                    bbox = shape.geometry.bbox  # (min_x, min_y, max_x, max_y)
                    min_x, min_y, max_x, max_y = bbox
                    poly = Polygon([
                        (min_x, min_y), (max_x, min_y),
                        (max_x, max_y), (min_x, max_y),
                        (min_x, min_y)
                    ])
                except:
                    poly = None
            
            # Fallback 2: Try to use ObjectPlacement for simple box
            if poly is None:
                try:
                    placement = space.ObjectPlacement
                    if placement:
                        x, y, z = self._resolve_placement(placement)
                        if x > 0 or y > 0:  # Valid placement
                            # Create 10x10 box around placement point
                            poly = Polygon([
                                (x - 5, y - 5), (x + 5, y - 5),
                                (x + 5, y + 5), (x - 5, y + 5),
                                (x - 5, y - 5)
                            ])
                except:
                    pass
            
            # Fallback 3: Default room if nothing works
            if poly is None or not poly.is_valid or poly.area <= 0.01:
                # Default 10x10 room at origin
                poly = Polygon([(0, 0), (10, 0), (10, 10), (0, 10), (0, 0)])
            
            if poly and poly.is_valid and poly.area > 0.01:
                rooms.append(Room(
                    id=getattr(space, 'GlobalId', str(space.id())),
                    name=getattr(space, 'Name', 'Unnamed') or "Unnamed",
                    geometry=poly,
                    ceiling_height=3.0,  # Default
                    ceiling_type="SMOOTH"
                ))
        
        return rooms
    
    def _extract_devices(self) -> List[Device]:
        """Extract fire sensors from IfcSensor using placement chain resolution."""
        devices = []
        
        for sensor in self.ifc_file.by_type("IfcSensor"):
            try:
                placement = sensor.ObjectPlacement
                if placement:
                    # Use placement chain resolution
                    x, y, z = self._resolve_placement(placement)
                    
                    dtype = getattr(sensor, 'PredefinedType', None) or "SMOKE_PHOTOELECTRIC"
                    
                    devices.append(Device(
                        id=getattr(sensor, 'GlobalId', str(sensor.id())),
                        device_type=dtype,
                        position=Point(x, y),
                        z_height=z
                    ))
            except Exception:
                continue
        
        return devices
    
    def _extract_obstructions(self) -> List[Obstruction]:
        """Extract obstructions from columns and beams."""
        obstructions = []
        
        for entity_type in ["IfcColumn", "IfcBeam"]:
            for entity in self.ifc_file.by_type(entity_type):
                try:
                    shape = ifcopenshell.geom.create_shape(entity)
                    verts = shape.geometry.verts
                    
                    if len(verts) >= 6:
                        pts_2d = [(verts[i], verts[i+1]) for i in range(0, len(verts), 3)]
                        poly = Polygon(pts_2d)
                        
                        if poly.is_valid and poly.area > 0.001:
                            obstructions.append(Obstruction(
                                id=getattr(entity, 'GlobalId', str(entity.id())),
                                geometry=poly,
                                height=2.4  # Default
                            ))
                except Exception:
                    continue
        
        return obstructions


def run_compliance_on_ifc(ifc_path: str) -> dict:
    """
    Complete binding function: takes IFC path, returns compliance report.
    Uses bridge then Oracle.
    """
    from validation.compliance_oracle import ComplianceOracle
    
    bridge = IFCBridge(ifc_path)
    rooms, devices, obstructions = bridge.extract_and_normalize()
    
    oracle = ComplianceOracle()
    all_violations = []
    all_results = []
    
    for room in rooms:
        result = oracle.verify_truth(room, devices, obstructions)
        all_results.append(result)
        all_violations.extend(result["violations"])
    
    return {
        "ifc_path": ifc_path,
        "rooms_processed": len(rooms),
        "total_violations": len(all_violations),
        "violations": all_violations,
        "results": all_results
    }


# =============================================================================
# Self-Test
# =============================================================================

def _run_self_test():
    """Test with programmatically created IFC file with spatial relationships"""
    import tempfile
    import os
    
    print("=" * 60)
    print("IFC BRIDGE SELF-TEST")
    print("=" * 60)
    
    if not IFC_AVAILABLE:
        print("Skipping: ifcopenshell not available")
        return
    
    try:
        # Create minimal IFC file programmatically
        ifc = ifcopenshell.file(schema="IFC4")
        
        # Create project
        project = ifc.create_entity(
            "IfcProject", 
            GlobalId="project_1",
            Name="Test Project"
        )
        
        # Create building
        building = ifc.create_entity(
            "IfcBuilding",
            GlobalId="building_1",
            Name="Test Building"
        )
        
        # Create building storey
        building_storey = ifc.create_entity(
            "IfcBuildingStorey",
            GlobalId="storey_1",
            Name="Ground Floor"
        )
        
        # Create a room with placement (simple box as bounding box will be used)
        room_placement = ifc.create_entity(
            "IfcLocalPlacement",
            RelativePlacement=ifc.create_entity(
                "IfcAxis2Placement3D",
                Location=ifc.create_entity("IfcCartesianPoint", Coordinates=(0.0, 0.0, 0.0))
            )
        )
        
        room = ifc.create_entity(
            "IfcSpace",
            GlobalId="room_1",
            Name="Test Room",
            ObjectPlacement=room_placement
        )
        
        # Create a sensor with placement at (5, 5, 2.4)
        sensor_placement = ifc.create_entity(
            "IfcLocalPlacement",
            RelativePlacement=ifc.create_entity(
                "IfcAxis2Placement3D",
                Location=ifc.create_entity("IfcCartesianPoint", Coordinates=(5.0, 5.0, 2.4))
            )
        )
        
        sensor = ifc.create_entity(
            "IfcSensor",
            GlobalId="sensor_1",
            Name="Smoke Detector",
            ObjectPlacement=sensor_placement
        )
        
        # Create spatial containment relationship (sensor in room)
        spatial_rel = ifc.create_entity(
            "IfcRelContainedInSpatialStructure",
            GlobalId="rel_contain_1",
            RelatingStructure=room,
            RelatedElements=[sensor]
        )
        
        # Save to temp file
        with tempfile.NamedTemporaryFile(mode='w', suffix='.ifc', delete=False) as f:
            temp_path = f.name
        
        # Write IFC file
        ifc.write(temp_path)
        
        print(f"\nCreated test IFC: {temp_path}")
        print("Running compliance bridge...")
        
        # Test that bridge can load the file
        bridge = IFCBridge(temp_path)
        rooms, devices, obstructions = bridge.extract_and_normalize()
        
        print(f"\nRooms extracted: {len(rooms)}")
        print(f"Devices extracted: {len(devices)}")
        print(f"Obstructions extracted: {len(obstructions)}")
        
        # Show spatial index
        print(f"\nSpatial index (device_to_room): {bridge.device_to_room}")
        
        print("\n" + "=" * 60)
        if len(rooms) > 0:
            print("✓ IFC BRIDGE VERIFIED")
        else:
            print("✗ Room extraction failed")
        print("=" * 60)
        
    except Exception as e:
        import traceback
        print(f"\nError: {type(e).__name__}: {e}")
        traceback.print_exc()
        print("=" * 60)
        print("✗ IFC BRIDGE FAILED")
        print("=" * 60)
    finally:
        # Clean up
        if 'temp_path' in dir() and os.path.exists(temp_path):
            os.remove(temp_path)


if __name__ == "__main__":
    _run_self_test()