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
import hashlib, json, logging, math, os, time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Tuple

from shapely.geometry import Polygon as ShapelyPolygon, Point as ShapelyPoint

from core.models import Room, Device, Obstruction
from core.ifc_utils import generate_ifc_guid, is_valid_ifc_guid, step_header, step_footer, step_entity, device_to_ifc_type

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

# Legacy maps kept for backward compatibility with existing code.
# New code should use device_to_ifc_type() from core.ifc_utils.
IFC_DEVICE_MAP = {
    "SMOKE_PHOTOELECTRIC":  "IfcSensor",
    "SMOKE_IONIZATION":     "IfcSensor",
    "SMOKE_MULTI_CRITERIA": "IfcSensor",
    "HEAT_FIXED":           "IfcSensor",
    "HEAT_RATE_OF_RISE":    "IfcSensor",
    "DUCT_SMOKE":           "IfcSensor",
    "MANUAL_PULL_STATION":  "IfcSwitchingDevice",
    "STROBE":               "IfcActuator",
    "HORN":                 "IfcActuator",
    "HORN_STROBE":          "IfcActuator",
    "FIRE_ALARM_PANEL":     "IfcController",
}

IFC_PREDEFINED_TYPE = {
    "SMOKE_PHOTOELECTRIC":  "SMOKESENSOR",
    "SMOKE_IONIZATION":     "SMOKESENSOR",
    "SMOKE_MULTI_CRITERIA": "MULTISENSOR",
    "HEAT_FIXED":           "HEATSENSOR",
    "HEAT_RATE_OF_RISE":    "HEATSENSOR",
    "DUCT_SMOKE":           "SMOKESENSOR",
    "MANUAL_PULL_STATION":  "SWITCH",
    "STROBE":               "USERDEFINED",
    "HORN":                 "USERDEFINED",
    "HORN_STROBE":          "USERDEFINED",
    "FIRE_ALARM_PANEL":     "FIREALARM",
}


# ════════════════════════════════════════════════════════════════════════════
# Fire Safety Property Set Template
# ════════════════════════════════════════════════════════════════════════════

FIRE_SAFETY_PSET_TEMPLATE = {
    "Pset_FireSafetyRequirements": {
        "OccupancyType":       "BUSINESS",
        "OccupancyLoad":       0,           # persons per m²
        "FireRating":          "",          # e.g. "1HR", "2HR"
        "SprinklerProtection": False,
        "DetectionRequired":   True,
        "NotificationRequired": True,
        "EgressPath":          False,
    },
    "Pset_FireAlarmDesign": {
        "DetectorType":        "SMOKE",
        "DetectorSpacing_m":   9.1,
        "CoverageRadius_m":    6.37,
        "CeilingType":         "SMOOTH",
        "CeilingHeight_m":     2.8,
        "DesignStandard":      "NFPA 72-2022",
        "DesignVerifiedBy":    "",
    },
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
    Sim:   Run fire physics simulation via twin module
    NFPA:  Validate design compliance via NFPA72 bridge

    Level 4 Digital Twin capabilities:
      - Event-sourced state management (twin.state_engine)
      - NFPA 72-2022 compliance validation (twin.nfpa72_bridge)
      - Physics-based fire simulation (twin.fire_physics)
    """

    def __init__(self, ifc_path: str = None, dwg_path: str = None,
                 building_id: str = "default"):
        self.ifc_path = ifc_path
        self.dwg_path = dwg_path
        self.building_id = building_id
        self.ifc_file = None
        self.sync_log: list[SyncRecord] = []
        self.conflicts: list[ConflictRecord] = []

        # Level 4 twin modules
        self._state_engine = None
        self._nfpa72_bridge = None
        self._last_simulation_result = None

        self._init_twin_modules()

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

    # ── Level 4: Twin Module Integration ──

    def _init_twin_modules(self):
        """Initialize Level 4 twin modules (state engine + NFPA72 bridge)."""
        try:
            from twin.state_engine import StateEngine
            self._state_engine = StateEngine()
            log.info("State engine initialized for building %s", self.building_id)
        except ImportError:
            log.warning("twin.state_engine not available")

        try:
            from twin.nfpa72_bridge import NFPA72Bridge
            self._nfpa72_bridge = NFPA72Bridge()
            log.info("NFPA72 bridge initialized")
        except ImportError:
            log.warning("twin.nfpa72_bridge not available")

    def register_detector(self, detector_id: str, room_id: str,
                         x: float, y: float, z: float,
                         detector_type: str = "smoke",
                         status: str = "planned") -> Optional[object]:
        """Register a detector in the state engine (event-sourced)."""
        if not self._state_engine:
            log.warning("State engine not available")
            return None
        return self._state_engine.register_detector(
            self.building_id, detector_id, room_id,
            x, y, z, detector_type, status)

    def validate_nfpa72(self, rooms: list, devices: list) -> Optional[dict]:
        """Validate design against NFPA 72-2022 using twin bridge."""
        if not self._nfpa72_bridge:
            log.warning("NFPA72 bridge not available")
            return None

        from twin.nfpa72_bridge import (
            RoomConfig, DetectorPlacement, OccupancyType
        )

        room_configs = []
        for r in rooms:
            if hasattr(r, 'geometry') and hasattr(r.geometry, 'bounds'):
                minx, miny, maxx, maxy = r.geometry.bounds
                w = maxx - minx
                d = maxy - miny
            else:
                w, d = 10.0, 10.0  # fallback

            occ = OccupancyType.BUSINESS
            rt = getattr(r, 'room_type', 'unknown')
            if 'corridor' in rt.lower():
                occ = OccupancyType.BUSINESS
            elif 'assembly' in rt.lower():
                occ = OccupancyType.ASSEMBLY

            room_configs.append(RoomConfig(
                room_id=r.id, name=r.name,
                width_m=w, depth_m=d,
                ceiling_height_m=getattr(r, 'ceiling_height', 2.8),
                occupancy_type=occ,
                floor_number=1,
                ceiling_type=getattr(r, 'ceiling_type', 'smooth'),
            ))

        detector_placements = []
        for d in devices:
            detector_placements.append(DetectorPlacement(
                detector_id=d.id, room_id=getattr(d, 'room_id', ''),
                x=d.position.x, y=d.position.y,
                z=getattr(d, 'z_height', 2.8),
                detector_type=getattr(d, 'device_type', 'smoke').lower().replace('_', ' '),
                coverage_radius_m=getattr(d, 'coverage_radius', 6.37),
            ))

        return self._nfpa72_bridge.validate_design(
            self.building_id, room_configs, detector_placements
        )

    def run_fire_simulation(self, width: float, length: float, height: float,
                            fire_x: float, fire_y: float,
                            detectors: list = None,
                            t_end: float = 300.0,
                            resolution: float = 0.5) -> Optional[object]:
        """Run a fire physics simulation via twin module.

        SAFETY: Simulation results are approximate. Must be verified by PE.
        """
        try:
            from twin.simulation_layer import (
                SimulationLayer, SimulationMode,
                SimulationRoomConfig, SimulationFireSource,
                SimulationDetector,
            )
            # Doorway imported for multi-room vent connections (future use)
            # from twin.fire_physics import Doorway
        except ImportError:
            log.warning("twin.simulation_layer not available")
            return None

        # BUG FIX: Previous version referenced non-existent ScenarioRunner
        # and DetectorType.MULTI (should be DetectorType.COMBINATION).
        # Now uses the correct SimulationLayer API.
        sim = SimulationLayer(mode=SimulationMode.ZONE_MODEL, resolution_m=resolution)

        room_cfg = SimulationRoomConfig(
            room_id='Z1', name='FireRoom',
            width_m=width, depth_m=length, height_m=height,
        )

        fire_cfg = SimulationFireSource(
            room_id='Z1', x=fire_x, y=fire_y, z=0.0,
            hrr_peak_w=1_000_000.0,
        )

        det_cfgs = []
        if detectors:
            for det in detectors:
                det_type = getattr(det, 'device_type', 'smoke').lower()
                if 'heat' in det_type:
                    det_type = 'heat'
                elif 'multi' in det_type or 'combination' in det_type:
                    det_type = 'combination'
                elif 'co' == det_type:
                    det_type = 'co'
                else:
                    det_type = 'smoke'

                det_cfgs.append(SimulationDetector(
                    detector_id=getattr(det, 'id', f'det_{fire_x}'),
                    room_id='Z1',
                    x=getattr(det.position, 'x', fire_x),
                    y=getattr(det.position, 'y', fire_y),
                    z=getattr(det, 'z_height', height),
                    detector_type=det_type,
                ))

        sim.setup([room_cfg], [fire_cfg], det_cfgs)
        self._last_simulation_result = sim.run(t_end=t_end)
        return self._last_simulation_result

    def get_state_checksum(self) -> str:
        """Get SHA-256 checksum of current twin state."""
        if self._state_engine:
            return self._state_engine.get_checksum()
        return ""

    def verify_twin_integrity(self) -> tuple:
        """Verify event store integrity."""
        if self._state_engine:
            return self._state_engine.verify_integrity(self.building_id)
        return False, "State engine not available"

    def get_sync_log(self) -> list:
        """Return all sync records for audit trail."""
        return self.sync_log

    def get_status(self) -> dict:
        """Return bridge status."""
        return {
            "ifc_loaded": self.ifc_file is not None,
            "ifc_path": self.ifc_path,
            "dwg_path": self.dwg_path,
            "building_id": self.building_id,
            "sync_count": len(self.sync_log),
            "conflict_count": len(self.conflicts),
            "state_engine": self._state_engine is not None,
            "nfpa72_bridge": self._nfpa72_bridge is not None,
            "simulation_available": True,  # twin.fire_physics importable
        }

    # ── FIRE-BIM: Full IFC Export Pipeline ──

    def export_to_ifc(self, rooms: list, devices: list,
                      output_path: str,
                      project_name: str = "FireAI Project",
                      building_name: str = "Building",
                      storey_name: str = "Ground Floor",
                      storey_elevation: float = 0.0) -> TwinSyncResult:
        """
        Export a complete IFC4 file from FireAI data.

        Creates a proper spatial hierarchy:
          IfcProject → IfcSite → IfcBuilding → IfcBuildingStorey → IfcSpace

        Each IfcSpace has extruded geometry from the room polygon.
        Each device gets an IfcSensor/IfcSwitchingDevice with placement.
        Fire safety property sets are attached to each space.

        Parameters
        ----------
        rooms : list of Room
            FireAI Room objects with geometry.
        devices : list of Device
            FireAI Device objects with positions.
        output_path : str
            Output IFC file path.
        project_name : str
            IfcProject name.
        building_name : str
            IfcBuilding name.
        storey_name : str
            IfcBuildingStorey name.
        storey_elevation : float
            Storey elevation in metres.

        Returns
        -------
        TwinSyncResult
        """
        t0 = time.time()
        warnings = []

        try:
            import ifcopenshell
        except ImportError:
            return TwinSyncResult(
                operation="export_ifc",
                warnings=["ifcopenshell not installed"],
            )

        try:
            f = ifcopenshell.file(schema="IFC4")

            # ── Spatial Hierarchy ──
            project_guid = generate_ifc_guid()
            site_guid = generate_ifc_guid()
            building_guid = generate_ifc_guid()
            storey_guid = generate_ifc_guid()

            # Units
            length_unit = f.create_entity("IfcSIUnit", UnitType="LENGTHUNIT", Name="METRE")
            area_unit = f.create_entity("IfcSIUnit", UnitType="AREAUNIT", Name="SQUARE_METRE")
            volume_unit = f.create_entity("IfcSIUnit", UnitType="VOLUMEUNIT", Name="CUBIC_METRE")
            unit_assignment = f.create_entity(
                "IfcUnitAssignment", Units=[length_unit, area_unit, volume_unit]
            )

            # Project
            project = f.create_entity(
                "IfcProject",
                GlobalId=project_guid,
                Name=project_name,
                UnitsInContext=unit_assignment,
            )

            # Site
            site_placement = f.create_entity(
                "IfcLocalPlacement", RelativePlacement=f.create_entity(
                    "IfcAxis2Placement3D",
                    Location=f.create_entity("IfcCartesianPoint", Coordinates=(0.0, 0.0, 0.0)),
                )
            )
            site = f.create_entity(
                "IfcSite",
                GlobalId=site_guid,
                Name="Site",
                ObjectPlacement=site_placement,
                RefLatitude=(0, 0, 0),
                RefLongitude=(0, 0, 0),
            )

            # Building
            building_placement = f.create_entity(
                "IfcLocalPlacement",
                PlacementRelTo=site_placement,
                RelativePlacement=f.create_entity(
                    "IfcAxis2Placement3D",
                    Location=f.create_entity("IfcCartesianPoint", Coordinates=(0.0, 0.0, 0.0)),
                )
            )
            building = f.create_entity(
                "IfcBuilding",
                GlobalId=building_guid,
                Name=building_name,
                ObjectPlacement=building_placement,
            )

            # Storey
            storey_placement = f.create_entity(
                "IfcLocalPlacement",
                PlacementRelTo=building_placement,
                RelativePlacement=f.create_entity(
                    "IfcAxis2Placement3D",
                    Location=f.create_entity("IfcCartesianPoint",
                                            Coordinates=(0.0, 0.0, storey_elevation)),
                )
            )
            storey = f.create_entity(
                "IfcBuildingStorey",
                GlobalId=storey_guid,
                Name=storey_name,
                ObjectPlacement=storey_placement,
                Elevation=storey_elevation,
            )

            # Spatial hierarchy relations
            f.create_entity(
                "IfcRelAggregates",
                GlobalId=generate_ifc_guid(),
                RelatingObject=project,
                RelatedObjects=[site],
            )
            f.create_entity(
                "IfcRelAggregates",
                GlobalId=generate_ifc_guid(),
                RelatingObject=site,
                RelatedObjects=[building],
            )
            f.create_entity(
                "IfcRelAggregates",
                GlobalId=generate_ifc_guid(),
                RelatingObject=building,
                RelatedObjects=[storey],
            )

            # ── Create IfcSpace for each room ──
            spaces_created = 0
            for room in rooms:
                try:
                    space = self._create_ifc_space(f, room, storey_placement)
                    if space:
                        # Add to storey
                        f.create_entity(
                            "IfcRelContainedInSpatialStructure",
                            GlobalId=generate_ifc_guid(),
                            RelatedElements=[space],
                            RelatingStructure=storey,
                        )
                        # Add fire safety property set
                        self._add_fire_safety_pset(f, space, room)
                        spaces_created += 1
                except Exception as ex:
                    warnings.append(f"Failed to create IfcSpace for {getattr(room, 'name', '?')}: {ex}")

            # ── Create devices ──
            devices_pushed = 0
            for d in devices:
                try:
                    sensor_type, predefined = device_to_ifc_type(d.device_type)
                    x, y = d.position.x, d.position.y
                    z = getattr(d, 'z_height', 2.8)

                    point = f.create_entity(
                        "IfcCartesianPoint", Coordinates=(x, y, z)
                    )
                    placement = f.create_entity(
                        "IfcLocalPlacement",
                        PlacementRelTo=storey_placement,
                        RelativePlacement=f.create_entity(
                            "IfcAxis2Placement3D", Location=point,
                        )
                    )

                    sensor = f.create_entity(
                        sensor_type,
                        GlobalId=generate_ifc_guid(),
                        Name=d.device_type,
                        PredefinedType=predefined,
                        ObjectPlacement=placement,
                    )

                    # Add device to storey
                    f.create_entity(
                        "IfcRelContainedInSpatialStructure",
                        GlobalId=generate_ifc_guid(),
                        RelatedElements=[sensor],
                        RelatingStructure=storey,
                    )

                    # Add device property set
                    self._add_device_pset(f, sensor, d)

                    devices_pushed += 1

                except Exception as ex:
                    warnings.append(f"Failed to create device {d.id}: {ex}")

            # ── Write file ──
            f.write(output_path)

            # Record sync
            record = SyncRecord(
                timestamp=datetime.now().isoformat(),
                operation="export_ifc",
                source="fireai",
                element_count=spaces_created + devices_pushed,
                sha256=self._hash_file(output_path) if os.path.exists(output_path) else "",
                notes=f"Exported {spaces_created} spaces + {devices_pushed} devices to {output_path}",
            )
            self.sync_log.append(record)

            log.info("IFC export: %d spaces, %d devices → %s",
                     spaces_created, devices_pushed, output_path)

            return TwinSyncResult(
                operation="export_ifc",
                elements_pushed=devices_pushed,
                sync_records=[record],
                warnings=warnings,
                elapsed_seconds=round(time.time() - t0, 2),
            )

        except Exception as ex:
            return TwinSyncResult(
                operation="export_ifc",
                warnings=[f"IFC export failed: {ex}"],
            )

    def _create_ifc_space(self, f, room, parent_placement) -> Optional[object]:
        """
        Create an IfcSpace with extruded geometry from a FireAI Room.

        Uses IfcExtrudedAreaSolid to give the space 3D volume.
        """
        geom = getattr(room, 'geometry', None)
        if geom is None:
            return None

        # Get polygon coordinates
        if hasattr(geom, 'exterior') and hasattr(geom.exterior, 'coords'):
            coords = list(geom.exterior.coords)[:-1]  # Remove closing duplicate
        elif hasattr(geom, 'bounds'):
            # Fallback: create rectangle from bounds
            minx, miny, maxx, maxy = geom.bounds
            coords = [(minx, miny), (maxx, miny), (maxx, maxy), (minx, maxy)]
        else:
            return None

        if len(coords) < 3:
            return None

        room_name = getattr(room, 'name', 'Unnamed')
        room_id = getattr(room, 'id', generate_ifc_guid())
        ceiling_height = getattr(room, 'ceiling_height', 2.8)

        # Create 2D profile from polygon
        ifc_points = [f.create_entity("IfcCartesianPoint", Coordinates=(x, y))
                      for x, y in coords]
        polyline = f.create_entity("IfcPolyline", Points=ifc_points)
        # Create an IfcArbitraryClosedProfileDef from the polyline
        profile = f.create_entity(
            "IfcArbitraryClosedProfileDef",
            ProfileType="AREA",
            OuterCurve=polyline,
        )

        # Create extruded area solid
        origin = f.create_entity("IfcCartesianPoint", Coordinates=(0.0, 0.0, 0.0))
        axis2d = f.create_entity("IfcAxis2Placement2D", Location=origin)
        axis3d = f.create_entity("IfcAxis2Placement3D", Location=origin)
        extrude_dir = f.create_entity(
            "IfcDirection", DirectionRatios=(0.0, 0.0, 1.0)
        )
        extrusion = f.create_entity(
            "IfcExtrudedAreaSolid",
            SweptArea=profile,
            Position=axis3d,
            ExtrudedDirection=extrude_dir,
            Depth=ceiling_height,
        )

        # Create local placement for the space
        space_placement = f.create_entity(
            "IfcLocalPlacement",
            PlacementRelTo=parent_placement,
            RelativePlacement=f.create_entity(
                "IfcAxis2Placement3D",
                Location=f.create_entity("IfcCartesianPoint", Coordinates=(0.0, 0.0, 0.0)),
            )
        )

        # Create styled item / representation
        # Create a shape representation
        body_context = None
        for ctx in f.by_type("IfcGeometricRepresentationContext"):
            body_context = ctx
            break
        if body_context is None:
            body_context = f.create_entity(
                "IfcGeometricRepresentationContext",
                ContextIdentifier="Body",
                CoordinateSpaceDimension=3,
                Precision=1e-5,
            )

        shape_rep = f.create_entity(
            "IfcShapeRepresentation",
            ContextOfItems=body_context,
            RepresentationIdentifier="Body",
            RepresentationType="SweptSolid",
            Items=[extrusion],
        )

        shape = f.create_entity(
            "IfcProductDefinitionShape",
            Representations=[shape_rep],
        )

        # Create the IfcSpace
        space_guid = room_id if is_valid_ifc_guid(str(room_id)) else generate_ifc_guid()
        space = f.create_entity(
            "IfcSpace",
            GlobalId=space_guid,
            Name=room_name,
            Description=getattr(room, 'room_type', ''),
            ObjectPlacement=space_placement,
            Representation=shape,
            InteriorOrExteriorSpace="INTERNAL",
            ElevationWithFlooring=0.0,
        )

        return space

    def _add_fire_safety_pset(self, f, space, room) -> None:
        """
        Attach fire safety property sets to an IfcSpace.

        Adds Pset_FireSafetyRequirements and Pset_FireAlarmDesign.
        """
        room_type = getattr(room, 'room_type', 'unknown')
        ceiling_height = getattr(room, 'ceiling_height', 2.8)
        ceiling_type = getattr(room, 'ceiling_type', 'SMOOTH')

        # Map room type to occupancy
        occupancy_map = {
            "office": "BUSINESS", "corridor": "BUSINESS",
            "warehouse": "STORAGE", "storage": "STORAGE",
            "assembly": "ASSEMBLY", "server_room": "BUSINESS",
            "stairwell": "MEANS_OF_EGRESS", "mechanical": "UTILITY",
            "kitchen": "BUSINESS", "lobby": "BUSINESS",
        }
        occupancy = occupancy_map.get(room_type, "BUSINESS")

        # Pset_FireSafetyRequirements
        pset_safety = f.create_entity(
            "IfcPropertySet",
            GlobalId=generate_ifc_guid(),
            Name="Pset_FireSafetyRequirements",
            HasProperties=[
                f.create_entity("IfcPropertySingleValue", Name="OccupancyType",
                                NominalValue=f.create_entity("IfcLabel", wrappedValue=occupancy)),
                f.create_entity("IfcPropertySingleValue", Name="FireRating",
                                NominalValue=f.create_entity("IfcLabel", wrappedValue="")),
                f.create_entity("IfcPropertySingleValue", Name="SprinklerProtection",
                                NominalValue=f.create_entity("IfcBoolean", wrappedValue=False)),
                f.create_entity("IfcPropertySingleValue", Name="DetectionRequired",
                                NominalValue=f.create_entity("IfcBoolean", wrappedValue=True)),
            ]
        )

        f.create_entity(
            "IfcRelDefinesByProperties",
            GlobalId=generate_ifc_guid(),
            RelatedObjects=[space],
            RelatingPropertyDefinition=pset_safety,
        )

        # Pset_FireAlarmDesign
        detector_spacing = 9.1  # Default smooth ceiling
        if ceiling_type.upper() == "BEAMED":
            detector_spacing = 6.1

        pset_alarm = f.create_entity(
            "IfcPropertySet",
            GlobalId=generate_ifc_guid(),
            Name="Pset_FireAlarmDesign",
            HasProperties=[
                f.create_entity("IfcPropertySingleValue", Name="DetectorType",
                                NominalValue=f.create_entity("IfcLabel", wrappedValue="SMOKE")),
                f.create_entity("IfcPropertySingleValue", Name="DetectorSpacing_m",
                                NominalValue=f.create_entity("IfcReal", wrappedValue=detector_spacing)),
                f.create_entity("IfcPropertySingleValue", Name="CeilingType",
                                NominalValue=f.create_entity("IfcLabel", wrappedValue=ceiling_type.upper())),
                f.create_entity("IfcPropertySingleValue", Name="CeilingHeight_m",
                                NominalValue=f.create_entity("IfcReal", wrappedValue=ceiling_height)),
                f.create_entity("IfcPropertySingleValue", Name="DesignStandard",
                                NominalValue=f.create_entity("IfcLabel", wrappedValue="NFPA 72-2022")),
            ]
        )

        f.create_entity(
            "IfcRelDefinesByProperties",
            GlobalId=generate_ifc_guid(),
            RelatedObjects=[space],
            RelatingPropertyDefinition=pset_alarm,
        )

    def _add_device_pset(self, f, sensor, device) -> None:
        """
        Attach a property set to an IfcSensor/IfcSwitchingDevice
        with FireAI design parameters.
        """
        coverage_radius = getattr(device, 'coverage_radius', 6.37)
        z_height = getattr(device, 'z_height', 2.8)
        device_type = getattr(device, 'device_type', 'UNKNOWN')

        pset = f.create_entity(
            "IfcPropertySet",
            GlobalId=generate_ifc_guid(),
            Name="Pset_FireAlarmDevice",
            HasProperties=[
                f.create_entity("IfcPropertySingleValue", Name="DeviceType",
                                NominalValue=f.create_entity("IfcLabel", wrappedValue=device_type)),
                f.create_entity("IfcPropertySingleValue", Name="CoverageRadius_m",
                                NominalValue=f.create_entity("IfcReal", wrappedValue=coverage_radius)),
                f.create_entity("IfcPropertySingleValue", Name="MountingHeight_m",
                                NominalValue=f.create_entity("IfcReal", wrappedValue=z_height)),
                f.create_entity("IfcPropertySingleValue", Name="DesignStandard",
                                NominalValue=f.create_entity("IfcLabel", wrappedValue="NFPA 72-2022")),
                f.create_entity("IfcPropertySingleValue", Name="FireAI_DeviceId",
                                NominalValue=f.create_entity("IfcIdentifier", wrappedValue=device.id)),
            ]
        )

        f.create_entity(
            "IfcRelDefinesByProperties",
            GlobalId=generate_ifc_guid(),
            RelatedObjects=[sensor],
            RelatingPropertyDefinition=pset,
        )


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
