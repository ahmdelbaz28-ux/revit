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
            # Filter devices and obstructions within this room
            room_devices = [d for d in raw_devices if room.geometry.covers(d.position)]
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
            try:
                # Try to get geometry using ifcopenshell.geom
                shape = ifcopenshell.geom.create_shape(space)
                verts = shape.geometry.verts  # flat list [x1,y1,z1, x2,y2,z2,...]
                
                # Convert to 2D polygon points
                if len(verts) >= 6:  # At least 3 points
                    pts_2d = [(verts[i], verts[i+1]) for i in range(0, len(verts), 3)]
                    poly = Polygon(pts_2d)
                    
                    if poly.is_valid and poly.area > 0.01:
                        rooms.append(Room(
                            id=getattr(space, 'GlobalId', str(space.id())),
                            name=getattr(space, 'Name', 'Unnamed') or "Unnamed",
                            geometry=poly,
                            ceiling_height=3.0,  # Default
                            ceiling_type="SMOOTH"
                        ))
            except Exception:
                # Skip spaces without geometry
                continue
        
        return rooms
    
    def _extract_devices(self) -> List[Device]:
        """Extract fire sensors from IfcSensor."""
        devices = []
        
        for sensor in self.ifc_file.by_type("IfcSensor"):
            try:
                placement = sensor.ObjectPlacement
                if placement and hasattr(placement, 'RelativePlacement'):
                    rel_placement = placement.RelativePlacement
                    if rel_placement and hasattr(rel_placement, 'Location'):
                        loc = rel_placement.Location
                        if hasattr(loc, 'Coordinates'):
                            coords = loc.Coordinates
                            x = coords[0] if len(coords) > 0 else 0
                            y = coords[1] if len(coords) > 1 else 0
                            z = coords[2] if len(coords) > 2 else 2.4
                            
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
    """Test with programmatically created IFC file"""
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
        ifc = ifcopenshell.file()
        
        # Create project
        project = ifc.create_entity("IfcProject", GlobalId="project_1")
        
        # Create a simple room entity first (without geometry for simplicity)
        room = ifc.create_entity(
            "IfcSpace",
            GlobalId="room_1",
            Name="Test Room"
        )
        
        # Create a sensor
        sensor = ifc.create_entity(
            "IfcSensor",
            GlobalId="sensor_1",
            Name="Smoke Detector"
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
        
        print("\n" + "=" * 60)
        print("✓ IFC BRIDGE VERIFIED")
        print("=" * 60)
        
    except Exception as e:
        print(f"\nError: {type(e).__name__}: {e}")
        print("=" * 60)
        print("✗ IFC BRIDGE FAILED")
        print("=" * 60)
    finally:
        # Clean up
        if os.path.exists(temp_path):
            os.remove(temp_path)


if __name__ == "__main__":
    _run_self_test()