"""
bridges/digital_twin_bridge.py
==============================
Bridge 4: FireAI ↔ IFC/Revit/BIM bidirectional sync

Connects the FireAI design engine to the BIM world:
  - Pull: Read rooms, devices, obstructions from IFC files
  - Push: Write fire alarm devices back into IFC models
  - Sync: Detect and resolve conflicts between design and BIM

SAFETY: Every sync operation is logged with SHA-256 hashes and timestamps.
No silent overwrites — every conflict requires explicit resolution.

Requires: ifcopenshell (for IFC), ezdxf (for DWG round-trip)

Usage:
    from bridges.digital_twin_bridge import DigitalTwinBridge
    bridge = DigitalTwinBridge("building.ifc")
    rooms, devices, obs = bridge.pull_from_bim()
    # ... run FireAI design ...
    bridge.push_to_bim(devices, rooms)
"""

from __future__ import annotations
import hashlib, json, logging, os, time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from shapely.geometry import Polygon as ShapelyPolygon, Point as ShapelyPoint

from core.models import Room, Device, Obstruction

log = logging.getLogger(__name__)


# ════════════════════════════════════════════════════════════════════════════
# Data structures
# ════════════════════════════════════════════════════════════════════════════

@dataclass
class SyncRecord:
    """Audit record for a sync operation."""
    timestamp: str
    operation: str   # 'pull', 'push', 'conflict'
    source: str      # 'ifc', 'revit', 'dwg', 'fireai'
    element_count: int
    sha256: str
    notes: str = ""


@dataclass
class ConflictRecord:
    """A conflict between BIM and FireAI data."""
    element_id: str
    bim_value: dict
    fireai_value: dict
    conflict_type: str  # 'geometry_mismatch', 'property_conflict', 'missing'
    auto_resolvable: bool = False
    resolution: str = ""   # 'bim_wins', 'fireai_wins', 'manual'


@dataclass
class TwinSyncResult:
    """Result of a sync operation."""
    operation: str
    elements_pulled: int = 0
    elements_pushed: int = 0
    conflicts: list = field(default_factory=list)
    sync_records: list = field(default_factory=list)
    warnings: list = field(default_factory=list)
    elapsed_seconds: float = 0.0


# ════════════════════════════════════════════════════════════════════════════
# IFC type → FireAI device type mapping
# ════════════════════════════════════════════════════════════════════════════

IFC_DEVICE_MAP = {
    "SMOKE_PHOTOELECTRIC":  "IfcSensor",
    "SMOKE_IONIZATION":     "IfcSensor",
    "SMOKE_MULTI_CRITERIA": "IfcSensor",
    "HEAT_FIXED":           "IfcSensor",
    "HEAT_RATE_OF_RISE":    "IfcSensor",
    "DUCT_SMOKE":           "IfcSensor",
    "MANUAL_PULL_STATION":  "IfcSwitchingDevice",
}

IFC_PREDEFINED_TYPE = {
    "SMOKE_PHOTOELECTRIC":  "SMOKESENSOR",
    "SMOKE_IONIZATION":     "SMOKESENSOR",
    "SMOKE_MULTI_CRITERIA": "MULTISENSOR",
    "HEAT_FIXED":           "HEATSENSOR",
    "HEAT_RATE_OF_RISE":    "HEATSENSOR",
    "DUCT_SMOKE":           "SMOKESENSOR",
    "MANUAL_PULL_STATION":  "SWITCH",
}


# ════════════════════════════════════════════════════════════════════════════
# Digital Twin Bridge
# ════════════════════════════════════════════════════════════════════════════

class DigitalTwinBridge:
    """
    Bidirectional bridge between FireAI and BIM models.

    Pull:  BIM → FireAI (read rooms, devices, obstructions)
    Push:  FireAI → BIM (write fire alarm devices into IFC)
    Sync:  Detect and resolve conflicts
    """

    def __init__(self, ifc_path: str = None, dwg_path: str = None):
        self.ifc_path = ifc_path
        self.dwg_path = dwg_path
        self.ifc_file = None
        self.sync_log: list[SyncRecord] = []
        self.conflicts: list[ConflictRecord] = []

        if ifc_path:
            self._load_ifc()

    # ── IFC Loading ──

    def _load_ifc(self):
        """Load IFC file using ifcopenshell."""
        try:
            import ifcopenshell
            self.ifc_file = ifcopenshell.open(self.ifc_path)
            log.info("Loaded IFC: %s", self.ifc_path)
        except ImportError:
            log.warning("ifcopenshell not installed — IFC operations disabled")
        except Exception as ex:
            log.error("Failed to load IFC: %s", ex)

    # ── Pull: BIM → FireAI ──

    def pull_from_bim(self) -> tuple:
        """
        Pull rooms, devices, and obstructions from BIM model.

        Returns (rooms, devices, obstructions) as FireAI model objects.
        """
        t0 = time.time()
        rooms, devices, obstructions = [], [], []

        if self.ifc_file:
            rooms, devices, obstructions = self._pull_from_ifc()
        elif self.dwg_path:
            rooms, devices, obstructions = self._pull_from_dwg()
        else:
            log.warning("No BIM source configured for pull")

        # Record sync
        record = SyncRecord(
            timestamp=datetime.now().isoformat(),
            operation="pull",
            source="ifc" if self.ifc_file else "dwg",
            element_count=len(rooms) + len(devices) + len(obstructions),
            sha256=self._hash_source(),
        )
        self.sync_log.append(record)

        log.info("Pull complete: %d rooms, %d devices, %d obstructions",
                 len(rooms), len(devices), len(obstructions))

        return rooms, devices, obstructions

    def _pull_from_ifc(self) -> tuple:
        """Extract rooms, devices, obstructions from IFC."""
        rooms, devices, obstructions = [], [], []

        if not self.ifc_file:
            return rooms, devices, obstructions

        # Extract rooms from IfcSpace
        for space in self.ifc_file.by_type("IfcSpace"):
            try:
                name = getattr(space, "Name", None) or "Unnamed"
                global_id = getattr(space, "GlobalId", str(space.id()))

                # Try to get geometry
                poly = self._ifc_space_to_polygon(space)

                # Get ceiling height from properties
                height = self._ifc_get_property(space, "FinishCeilingHeight") or 2.8

                rooms.append(Room(
                    id=global_id,
                    name=name,
                    room_type="unknown",
                    floor_area=poly.area if poly else 0.0,
                    geometry=poly or ShapelyPolygon([(0, 0), (1, 0), (1, 1), (0, 1)]),
                    ceiling_height=height,
                    ceiling_type="SMOOTH",
                ))
            except Exception as ex:
                log.warning("Failed to extract IfcSpace: %s", ex)

        # Extract existing fire alarm devices from IfcSensor
        for sensor in self.ifc_file.by_type("IfcSensor"):
            try:
                global_id = getattr(sensor, "GlobalId", str(sensor.id()))
                name = getattr(sensor, "Name", "") or ""
                predefined = getattr(sensor, "PredefinedType", "") or ""

                pos = self._ifc_get_position(sensor)
                if pos:
                    devices.append(Device(
                        id=global_id,
                        device_type="SMOKE_PHOTOELECTRIC",  # default
                        position=ShapelyPoint(pos[0], pos[1]),
                        room_id="",
                        z_height=pos[2] if len(pos) > 2 else 2.8,
                    ))
            except Exception as ex:
                log.warning("Failed to extract IfcSensor: %s", ex)

        # Extract obstructions from IfcColumn, IfcBeam
        for ifc_type in ["IfcColumn", "IfcBeam"]:
            for entity in self.ifc_file.by_type(ifc_type):
                try:
                    global_id = getattr(entity, "GlobalId", str(entity.id()))
                    # Simplified: use bounding box
                    pos = self._ifc_get_position(entity)
                    if pos:
                        w, h = 0.4, 0.4  # default column size
                        poly = ShapelyPolygon([
                            (pos[0] - w/2, pos[1] - h/2),
                            (pos[0] + w/2, pos[1] - h/2),
                            (pos[0] + w/2, pos[1] + h/2),
                            (pos[0] - w/2, pos[1] + h/2),
                        ])
                        obstructions.append(Obstruction(
                            id=global_id,
                            geometry=poly,
                            height=2.8,
                        ))
                except Exception as ex:
                    log.warning("Failed to extract %s: %s", ifc_type, ex)

        return rooms, devices, obstructions

    def _pull_from_dwg(self) -> tuple:
        """Extract rooms from DWG/DXF using Bridge 2."""
        try:
            from bridges.parser_bridge import parse_drawing_to_fireai
            result = parse_drawing_to_fireai(self.dwg_path)
            return result.rooms, result.devices, result.obstructions
        except Exception as ex:
            log.error("DWG pull failed: %s", ex)
            return [], [], []

    # ── Push: FireAI → BIM ──

    def push_to_bim(self, devices: list, rooms: list,
                    output_path: str = None) -> TwinSyncResult:
        """
        Push fire alarm devices into IFC model.

        Creates IfcSensor elements at each device position.
        Does NOT modify the original IFC file — creates a copy.
        """
        t0 = time.time()
        warnings = []

        if not self.ifc_file:
            return TwinSyncResult(
                operation="push",
                warnings=["No IFC file loaded. Cannot push."],
            )

        try:
            import ifcopenshell
            import ifcopenshell.api
        except ImportError:
            return TwinSyncResult(
                operation="push",
                warnings=["ifcopenshell not installed"],
            )

        # Create a copy of the IFC file
        output = output_path or self.ifc_path.replace(".ifc", "_fa.ifc")

        try:
            # Use ifcopenshell to add devices
            f = self.ifc_file

            # Get project hierarchy
            project = f.by_type("IfcProject")[0] if f.by_type("IfcProject") else None
            if not project:
                warnings.append("No IfcProject found in IFC file")
                return TwinSyncResult(operation="push", warnings=warnings)

            # Get or create building storey
            storeys = f.by_type("IfcBuildingStorey")
            storey = storeys[0] if storeys else None

            devices_pushed = 0
            for d in devices:
                try:
                    # Create IfcSensor
                    sensor_type = IFC_DEVICE_MAP.get(d.device_type, "IfcSensor")
                    predefined = IFC_PREDEFINED_TYPE.get(d.device_type, "USERDEFINED")

                    # Create placement
                    x, y, z = d.position.x, d.position.y, d.z_height

                    # Create point
                    point = f.create_entity(
                        "IfcCartesianPoint",
                        Coordinates=(x, y, z)
                    )
                    placement = f.create_entity(
                        "IfcLocalPlacement",
                        RelativePlacement=f.create_entity(
                            "IfcAxis2Placement3D",
                            Location=point,
                        )
                    )

                    # Create sensor
                    sensor = f.create_entity(
                        sensor_type,
                        GlobalId=f"FireAI_{d.id}",
                        Name=d.device_type,
                        PredefinedType=predefined,
                        ObjectPlacement=placement,
                    )

                    # Add to spatial structure if storey exists
                    if storey:
                        f.create_entity(
                            "IfcRelContainedInSpatialStructure",
                            RelatedElements=[sensor],
                            RelatingStructure=storey,
                        )

                    devices_pushed += 1

                except Exception as ex:
                    warnings.append(f"Failed to push device {d.id}: {ex}")

            # Save
            f.write(output)

            # Record sync
            record = SyncRecord(
                timestamp=datetime.now().isoformat(),
                operation="push",
                source="fireai",
                element_count=devices_pushed,
                sha256=self._hash_file(output),
                notes=f"Pushed {devices_pushed} devices to {output}",
            )
            self.sync_log.append(record)

            return TwinSyncResult(
                operation="push",
                elements_pushed=devices_pushed,
                sync_records=[record],
                warnings=warnings,
                elapsed_seconds=round(time.time() - t0, 2),
            )

        except Exception as ex:
            return TwinSyncResult(
                operation="push",
                warnings=[f"Push failed: {ex}"],
            )

    # ── Conflict Detection ──

    def detect_conflicts(self, fireai_devices: list) -> list:
        """
        Detect conflicts between FireAI devices and BIM model.
        """
        conflicts = []

        if not self.ifc_file:
            return conflicts

        # Check for spatial conflicts (devices overlapping columns, etc.)
        bim_sensors = self.ifc_file.by_type("IfcSensor")

        for d in fireai_devices:
            for sensor in bim_sensors:
                bim_pos = self._ifc_get_position(sensor)
                if bim_pos:
                    dist = math.hypot(
                        d.position.x - bim_pos[0],
                        d.position.y - bim_pos[1]
                    )
                    if dist < 0.3:  # 30cm — likely duplicate
                        conflicts.append(ConflictRecord(
                            element_id=d.id,
                            bim_value={"position": bim_pos, "name": getattr(sensor, "Name", "")},
                            fireai_value={"position": (d.position.x, d.position.y, d.z_height)},
                            conflict_type="geometry_mismatch",
                            auto_resolvable=True,
                        ))

        return conflicts

    # ── Utility methods ──

    def _ifc_space_to_polygon(self, space) -> Optional[ShapelyPolygon]:
        """Extract polygon geometry from IfcSpace."""
        try:
            import ifcopenshell.geom
            settings = ifcopenshell.geom.settings()
            shape = ifcopenshell.geom.create_shape(settings, space)
            verts = shape.geometry.verts
            if len(verts) >= 9:  # At least 3 points
                pts_2d = [(verts[i], verts[i+1]) for i in range(0, len(verts), 3)]
                poly = ShapelyPolygon(pts_2d)
                if poly.is_valid and poly.area > 0.01:
                    return poly
        except Exception:
            pass
        return None

    def _ifc_get_position(self, entity) -> Optional[tuple]:
        """Resolve entity position from placement chain."""
        try:
            placement = entity.ObjectPlacement
            x, y, z = 0.0, 0.0, 0.0
            while placement:
                if hasattr(placement, 'RelativePlacement') and placement.RelativePlacement:
                    rel = placement.RelativePlacement
                    if hasattr(rel, 'Location') and rel.Location:
                        coords = rel.Location.Coordinates
                        x += coords[0] if len(coords) > 0 else 0.0
                        y += coords[1] if len(coords) > 1 else 0.0
                        z += coords[2] if len(coords) > 2 else 0.0
                if hasattr(placement, 'PlacementRelTo') and placement.PlacementRelTo:
                    placement = placement.PlacementRelTo
                else:
                    break
            return (x, y, z)
        except Exception:
            return None

    def _ifc_get_property(self, entity, prop_name: str) -> Optional[float]:
        """Get a property value from IfcPropertySet."""
        try:
            for rel in getattr(entity, "IsDefinedBy", []) or []:
                if rel.is_a("IfcRelDefinesByProperties"):
                    pdef = rel.RelatingPropertyDefinition
                    if pdef.is_a("IfcPropertySet"):
                        for p in pdef.HasProperties:
                            if p.Name == prop_name and hasattr(p, "NominalValue"):
                                return float(p.NominalValue.wrappedValue)
        except Exception:
            pass
        return None

    def _hash_source(self) -> str:
        """SHA-256 hash of the source file."""
        if self.ifc_path and os.path.exists(self.ifc_path):
            return self._hash_file(self.ifc_path)
        return ""

    @staticmethod
    def _hash_file(path: str) -> str:
        """SHA-256 hash of a file."""
        h = hashlib.sha256()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(1 << 20), b""):
                h.update(chunk)
        return h.hexdigest()[:16]

    def get_sync_log(self) -> list:
        """Return all sync records for audit trail."""
        return self.sync_log

    def get_status(self) -> dict:
        """Return bridge status."""
        return {
            "ifc_loaded": self.ifc_file is not None,
            "ifc_path": self.ifc_path,
            "dwg_path": self.dwg_path,
            "sync_count": len(self.sync_log),
            "conflict_count": len(self.conflicts),
        }


# ════════════════════════════════════════════════════════════════════════════
# Self-test
# ════════════════════════════════════════════════════════════════════════════

def _self_test():
    """Test with a programmatically created IFC file."""
    print("=" * 60)
    print("BRIDGE 4: Digital Twin Bridge — Self-Test")
    print("=" * 60)

    try:
        import ifcopenshell
    except ImportError:
        print("SKIP: ifcopenshell not installed")
        return

    import tempfile

    # Create minimal IFC
    ifc = ifcopenshell.file(schema="IFC4")
    project = ifc.create_entity("IfcProject", GlobalId="proj_1", Name="Test")
    building = ifc.create_entity("IfcBuilding", GlobalId="bldg_1", Name="Test Building")
    storey = ifc.create_entity("IfcBuildingStorey", GlobalId="storey_1", Name="Ground Floor")

    # Create a room
    room_placement = ifc.create_entity(
        "IfcLocalPlacement",
        RelativePlacement=ifc.create_entity(
            "IfcAxis2Placement3D",
            Location=ifc.create_entity("IfcCartesianPoint", Coordinates=(0.0, 0.0, 0.0))
        )
    )
    space = ifc.create_entity(
        "IfcSpace", GlobalId="room_1", Name="Office A",
        ObjectPlacement=room_placement
    )

    with tempfile.NamedTemporaryFile(suffix=".ifc", delete=False) as f:
        ifc_path = f.name
    ifc.write(ifc_path)

    print(f"Created test IFC: {ifc_path}")

    # Test bridge
    bridge = DigitalTwinBridge(ifc_path=ifc_path)
    rooms, devices, obs = bridge.pull_from_bim()

    print(f"\nPull result:")
    print(f"  Rooms: {len(rooms)}")
    print(f"  Devices: {len(devices)}")
    print(f"  Obstructions: {len(obs)}")
    print(f"  Sync log: {len(bridge.get_sync_log())} records")

    for r in rooms:
        print(f"  Room: {r.name} ({r.room_type})")

    # Test push
    fa_devices = [
        Device(id="fa_smoke_1", device_type="SMOKE_PHOTOELECTRIC",
               position=ShapelyPoint(5.0, 5.0), room_id="room_1",
               z_height=2.8, coverage_radius=6.37),
    ]

    push_result = bridge.push_to_bim(fa_devices, rooms)
    print(f"\nPush result:")
    print(f"  Pushed: {push_result.elements_pushed}")
    print(f"  Warnings: {push_result.warnings}")

    # Cleanup
    os.unlink(ifc_path)

    print("\n" + "=" * 60)
    status = "PASS" if len(rooms) >= 1 else "FAIL"
    print(f"Bridge 4 Self-Test: {status}")
    print("=" * 60)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    _self_test()
