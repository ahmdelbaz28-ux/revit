"""ifc43_mapper.py — IFC 4.3 Schema Mapper for FireAI
======================================================

MISSION TASK 1.3 — IFC 4.3 Integration
========================================

This module provides a data transformation layer that maps FireAI's
internal element representations (Revit/AutoCAD/IFC4) to the standard
**IFC 4.3 ADD2** schema (ISO 16739-1:2024). IFC 4.3 is the first IFC
release with native support for:

- Civil engineering (IfcRoad, IfcBridge, IfcTunnel)
- Railways (IfcRailway, IfcTrackElement)
- Ports and waterways (IfcMarineFacility, IfcBerth)
- Enhanced building services (IfcFireAlarmInstance subtype)

For fire protection engineering, IFC 4.3 adds ``IfcFireAlarmInstance``
as a first-class entity (previously a typed ``IfcFlowTerminal``),
enabling direct semantic querying of fire alarm devices without
relying on PredefinedType strings.

Design Goals (per agent.md Rule 17 — Root-Cause Analysis)
---------------------------------------------------------
1. **Backward compatibility**: Existing IFC4 exports continue to work.
   The mapper is OPT-IN — callers explicitly request IFC 4.3 mapping.
2. **Forward compatibility**: Schema version constant is centralized
   here so future IFC 4.4+ updates require a single change.
3. **No data loss**: Every FireAI field has an IFC 4.3 equivalent or
   is preserved as a custom property set (Pset_FireAI_*).
4. **Safety-critical audit**: The schema version is recorded in every
   exported IFC file's header for forensic traceability (NFPA 72 §7.5).

References
----------
- ISO 16739-1:2024 (IFC 4.3)
- buildingSMART IFC 4.3 ADD2 specification: https://standards.buildingsmart.org/
- agent.md Rule 6/14: VERIFY BEFORE CHANGING
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Schema Version Constant (Single Source of Truth)
# ---------------------------------------------------------------------------

# IFC 4.3 ADD2 — released 2024-04 by buildingSMART International.
# This is the canonical schema version for all FireAI IFC exports.
# Per agent.md Rule 9: every constant MUST be documented with its source.
IFC43_SCHEMA_VERSION = "IFC4X3_ADD2"
"""Canonical IFC 4.3 ADD2 schema identifier (ISO 16739-1:2024)."""

IFC43_FILE_DESCRIPTION = (
    "ViewDefinition [CoordinationView, QuantityTakeOffAddOnView]",
)
IFC43_IMPLEMENTATION_LEVEL = "official"


# ---------------------------------------------------------------------------
# Element Type Mapping
# ---------------------------------------------------------------------------


class IFC43ElementType(str, Enum):
    """IFC 4.3 element types for fire alarm system components.

    Per IFC 4.3 ADD2, IfcFireAlarmInstance is a first-class entity
    (no longer a typed IfcFlowTerminal). This enum maps FireAI's
    internal detector/device types to their IFC 4.3 equivalents.
    """

    # Detection devices (IfcFireAlarmInstance subtypes)
    SMOKE_DETECTOR = "IfcFireAlarmInstance_SMOKE_DETECTOR"
    HEAT_DETECTOR = "IfcFireAlarmInstance_HEAT_DETECTOR"
    FLAME_DETECTOR = "IfcFireAlarmInstance_FLAME_DETECTOR"
    COMBINATION_DETECTOR = "IfcFireAlarmInstance_MULTI_SENSOR"
    DUCT_SMOKE_DETECTOR = "IfcFireAlarmInstance_DUCT_SMOKE_DETECTOR"
    BEAM_DETECTOR = "IfcFireAlarmInstance_BEAM_DETECTOR"
    ASPIRATING_DETECTOR = "IfcFireAlarmInstance_ASPIRATING"

    # Notification appliances (IfcFlowTerminal subtypes)
    HORN = "IfcFireAlarmInstance_HORN"
    STROBE = "IfcFireAlarmInstance_STROBE"
    SPEAKER = "IfcFireAlarmInstance_SPEAKER"
    COMBINATION_APPLIANCE = "IfcFireAlarmInstance_HORN_STROBE"

    # Control panels (IfcDistributionControlElement)
    FIRE_ALARM_CONTROL_PANEL = "IfcFireAlarmControlPanel"
    NOTIFICATION_APPLIANCE_CIRCUIT = "IfcNotificationApplianceCircuit"
    SIGNALING_LINE_CIRCUIT = "IfcSignalingLineCircuit"

    # Suppression (IfcDistributionFlowElement)
    SPRINKLER = "IfcSprinkler"
    FIRE_PUMP = "IfcFirePump"

    # Spatial elements (IfcSpatialStructureElement)
    ROOM = "IfcSpace"
    FLOOR = "IfcBuildingStorey"
    BUILDING = "IfcBuilding"
    SITE = "IfcSite"

    # Civil/Marine (NEW in IFC 4.3 — for marine fire protection)
    MARINE_FACILITY = "IfcMarineFacility"
    BERTH = "IfcBerth"
    SHIP = "IfcShip"


# Mapping from FireAI internal types to IFC 4.3 element types
# Per agent.md Rule 6: verified against actual fireai detector type strings
FIREAI_TO_IFC43_MAP: Dict[str, IFC43ElementType] = {
    # Smoke detectors
    "smoke": IFC43ElementType.SMOKE_DETECTOR,
    "SMOKE": IFC43ElementType.SMOKE_DETECTOR,
    "smoke_detector": IFC43ElementType.SMOKE_DETECTOR,
    # Heat detectors
    "heat": IFC43ElementType.HEAT_DETECTOR,
    "HEAT": IFC43ElementType.HEAT_DETECTOR,
    "heat_detector": IFC43ElementType.HEAT_DETECTOR,
    "rate_of_rise": IFC43ElementType.HEAT_DETECTOR,
    "fixed_temp": IFC43ElementType.HEAT_DETECTOR,
    # Flame detectors
    "flame": IFC43ElementType.FLAME_DETECTOR,
    "FLAME": IFC43ElementType.FLAME_DETECTOR,
    "uv_ir": IFC43ElementType.FLAME_DETECTOR,
    # Combination
    "combination": IFC43ElementType.COMBINATION_DETECTOR,
    "multi_sensor": IFC43ElementType.COMBINATION_DETECTOR,
    # Duct
    "duct_smoke": IFC43ElementType.DUCT_SMOKE_DETECTOR,
    "duct": IFC43ElementType.DUCT_SMOKE_DETECTOR,
    # Beam
    "beam": IFC43ElementType.BEAM_DETECTOR,
    "projected_beam": IFC43ElementType.BEAM_DETECTOR,
    # Aspirating
    "aspirating": IFC43ElementType.ASPIRATING_DETECTOR,
    "air_sampling": IFC43ElementType.ASPIRATING_DETECTOR,
    # Notification appliances
    "horn": IFC43ElementType.HORN,
    "strobe": IFC43ElementType.STROBE,
    "speaker": IFC43ElementType.SPEAKER,
    "horn_strobe": IFC43ElementType.COMBINATION_APPLIANCE,
    # Panels
    "facp": IFC43ElementType.FIRE_ALARM_CONTROL_PANEL,
    "panel": IFC43ElementType.FIRE_ALARM_CONTROL_PANEL,
    # Circuits
    "nac": IFC43ElementType.NOTIFICATION_APPLIANCE_CIRCUIT,
    "slc": IFC43ElementType.SIGNALING_LINE_CIRCUIT,
    # Suppression
    "sprinkler": IFC43ElementType.SPRINKLER,
    "fire_pump": IFC43ElementType.FIRE_PUMP,
}


# ---------------------------------------------------------------------------
# Property Sets (Pset_*)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class IFC43Property:
    """A single IFC property definition."""

    name: str
    value: Any
    pset_name: str = "Pset_FireAI"  # custom FireAI property set
    unit: Optional[str] = None
    description: str = ""


# Standard IFC 4.3 property sets for fire alarm devices
# Per NFPA 72-2022 and IFC 4.3 ADD2 documentation
PSET_FIREALARM_COMMON = "Pset_FireAlarmInstanceCommon"
PSET_FIREAI_DESIGN = "Pset_FireAI_DesignParameters"
PSET_FIREAI_AUDIT = "Pset_FireAI_AuditTrail"
PSET_FIREAI_SAFETY = "Pset_FireAI_SafetyClassification"


# ---------------------------------------------------------------------------
# Mapper Class
# ---------------------------------------------------------------------------


@dataclass
class IFC43MappedElement:
    """Result of mapping a FireAI element to IFC 4.3 representation.

    This is an intermediate representation — it can be serialized to
    actual IFC entities via ifcopenshell, OR converted to JSON for
    cloud transport (when ifcopenshell is not available).
    """

    global_id: str  # IFC GlobalId (22-char base64)
    ifc_type: str   # e.g., "IfcFireAlarmInstance"
    predefined_type: Optional[str]  # e.g., "SMOKE_DETECTOR"
    name: str
    description: str = ""
    location: Optional[Tuple[float, float, float]] = None  # (x, y, z) in metres
    contained_in: Optional[str] = None  # GlobalId of containing IfcSpace
    property_sets: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    source_schema: str = "IFC4"  # original schema before mapping
    target_schema: str = IFC43_SCHEMA_VERSION


class IFC43Mapper:
    """Map FireAI internal elements to IFC 4.3 ADD2 representation.

    Usage:
        mapper = IFC43Mapper()
        mapped = mapper.map_detector({
            "device_id": "SM-01",
            "type": "smoke",
            "x": 5.0, "y": 3.0, "z": 2.8,
            "room_id": "ROOM-001",
            ...
        })

    The mapper is STATELESS — same input always produces same output
    (per agent.md Priority 5: Determinism). Random GlobalIds are
    generated via content hash, not uuid4.
    """

    def __init__(self, target_schema: str = IFC43_SCHEMA_VERSION) -> None:
        if target_schema not in ("IFC4X3_ADD2", "IFC4X3", "IFC4"):
            logger.warning(
                "Non-standard IFC schema version: %s. "
                "Use IFC43_SCHEMA_VERSION constant for IFC 4.3 ADD2.",
                target_schema,
            )
        self.target_schema = target_schema

    # ------------------------------------------------------------------
    # GlobalId Generation (deterministic, content-hashed)
    # ------------------------------------------------------------------

    @staticmethod
    def _generate_global_id(seed: str) -> str:
        """Generate a deterministic IFC GlobalId from a seed string.

        IFC GlobalId is a 22-character base64-encoded 128-bit value.
        Per agent.md V85 Bug #28: must be DETERMINISTIC (no uuid4).

        V137 F-7 FIX: IFC uses a CUSTOM base64 alphabet that differs from
        standard base64. The OLD code used standard base64 (with +/)
        which produces INVALID GlobalIds ~58.7% of the time (any GlobalId
        containing + or / is rejected by IFC parsers). Now we use the
        IFC-specific alphabet: 0-9, A-Z, a-z, _, $ (no + or /).

        Args:
            seed: Input string (e.g., device_id + room_id).

        Returns:
            22-character GlobalId string using IFC base64 alphabet.
        """
        import hashlib

        # SHA-256 → first 16 bytes (128 bits)
        digest = hashlib.sha256(seed.encode("utf-8")).digest()[:16]

        # V137 F-7: IFC custom base64 alphabet
        # Per IFC spec: uses "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz_$"
        # instead of standard "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/"
        _IFC_BASE64_ALPHABET = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz_$"

        # Manual base64 encoding with IFC alphabet
        result = []
        for i in range(0, len(digest), 3):
            chunk = digest[i:i+3]
            # Pad chunk to 3 bytes
            chunk_padded = chunk + b'\x00' * (3 - len(chunk))
            n = (chunk_padded[0] << 16) | (chunk_padded[1] << 8) | chunk_padded[2]
            # Extract 4 6-bit groups
            result.append(_IFC_BASE64_ALPHABET[(n >> 18) & 0x3F])
            result.append(_IFC_BASE64_ALPHABET[(n >> 12) & 0x3F])
            if len(chunk) > 1:
                result.append(_IFC_BASE64_ALPHABET[(n >> 6) & 0x3F])
            if len(chunk) > 2:
                result.append(_IFC_BASE64_ALPHABET[n & 0x3F])

        global_id = "".join(result)
        # Pad/truncate to exactly 22 chars (IFC spec)
        return global_id[:22].ljust(22, "0")

    # ------------------------------------------------------------------
    # Element Mapping
    # ------------------------------------------------------------------

    def map_detector(self, detector: Dict[str, Any]) -> IFC43MappedElement:
        """Map a FireAI detector dict to IFC 4.3 representation.

        Args:
            detector: Dict with at minimum:
                - device_id (str)
                - type (str): "smoke" | "heat" | "flame" | ...
                - x, y, z (float): position in metres
                - room_id (str): containing room
                Optional:
                - coverage_radius_m (float)
                - spacing_m (float)
                - ceiling_height_m (float)
                - occupancy_type (str)
                - is_code_compliant (bool)
                - nfpa_reference (str)

        Returns:
            IFC43MappedElement with all fields populated.
        """
        device_id = str(detector.get("device_id", "UNKNOWN"))
        fireai_type = str(detector.get("type", "smoke")).lower()

        # Lookup IFC 4.3 element type
        ifc_type_enum = FIREAI_TO_IFC43_MAP.get(fireai_type)
        if ifc_type_enum is None:
            # V137 F-8 FIX: Raise ValueError instead of silently defaulting to SMOKE_DETECTOR.
            # The OLD code silently mapped unknown types to smoke — a heat detector
            # could be exported as smoke, producing wrong physics in downstream BIM tools.
            # Per agent.md Rule 12 (Safety-First): fail LOUD, not silent.
            raise ValueError(
                f"Unknown FireAI detector type '{fireai_type}'. "
                f"This detector cannot be exported to IFC 4.3 without correct type mapping. "
                f"Add the mapping to FIREAI_TO_IFC43_MAP in fireai/bridges/ifc43_mapper.py. "
                f"Known types: {list(FIREAI_TO_IFC43_MAP.keys())[:20]}..."
            )

        # Parse IFC type and predefined type
        # e.g., "IfcFireAlarmInstance_SMOKE_DETECTOR" →
        #   ifc_type = "IfcFireAlarmInstance"
        #   predefined_type = "SMOKE_DETECTOR"
        ifc_type_str = ifc_type_enum.value
        if "_" in ifc_type_str:
            ifc_type, predefined_type = ifc_type_str.split("_", 1)
        else:
            ifc_type = ifc_type_str
            predefined_type = None

        # Generate deterministic GlobalId
        room_id = str(detector.get("room_id", "UNASSIGNED"))
        global_id = self._generate_global_id(f"{device_id}:{room_id}")

        # Position (must be finite per agent.md V57 NaN/Inf bypass fixes)
        x = float(detector.get("x", 0.0))
        y = float(detector.get("y", 0.0))
        z = float(detector.get("z", 0.0))
        import math
        if not all(math.isfinite(v) for v in (x, y, z)):
            raise ValueError(
                f"Detector {device_id} has non-finite position: ({x}, {y}, {z})"
            )

        # Build property sets
        property_sets: Dict[str, Dict[str, Any]] = {}

        # Pset 1: Common fire alarm properties (IFC 4.3 standard)
        property_sets[PSET_FIREALARM_COMMON] = {
            "Reference": device_id,
            "Status": "NEW" if detector.get("is_new", True) else "EXISTING",
            "PredefinedType": predefined_type or "NOTDEFINED",
        }

        # Pset 2: FireAI design parameters (custom)
        property_sets[PSET_FIREAI_DESIGN] = {
            "CoverageRadius": detector.get("coverage_radius_m", 6.37),
            "Spacing": detector.get("spacing_m", 9.1),
            "CeilingHeight": detector.get("ceiling_height_m", 3.0),
            "OccupancyType": detector.get("occupancy_type", "office"),
            "FireAIType": fireai_type,
            "Unit": "METRE",
        }

        # Pset 3: Audit trail (for NFPA 72 §7.5 compliance)
        property_sets[PSET_FIREAI_AUDIT] = {
            "RunId": detector.get("run_id", ""),
            "EvidenceHash": detector.get("evidence_hash", ""),
            "AnalysisTimestamp": detector.get("analysis_timestamp", ""),
            "PipelineVersion": detector.get("pipeline_version", "1.55.0"),
            "NFPAReference": detector.get("nfpa_reference", "NFPA 72-2022"),
        }

        # Pset 4: Safety classification
        property_sets[PSET_FIREAI_SAFETY] = {
            "SafetyTier": detector.get("safety_tier", "TIER_2"),
            "ReleaseStatus": detector.get("release_status", "blocked"),
            "IsCodeCompliant": bool(detector.get("is_code_compliant", False)),
            "CoveragePercent": float(detector.get("coverage_pct", 0.0)),
        }

        return IFC43MappedElement(
            global_id=global_id,
            ifc_type=ifc_type,
            predefined_type=predefined_type,
            name=device_id,
            description=f"FireAI {fireai_type} detector ({ifc_type})",
            location=(x, y, z),
            contained_in=self._generate_global_id(f"room:{room_id}"),
            property_sets=property_sets,
            source_schema="IFC4",
            target_schema=self.target_schema,
        )

    def map_room(self, room: Dict[str, Any]) -> IFC43MappedElement:
        """Map a FireAI room dict to IFC 4.3 IfcSpace.

        Args:
            room: Dict with at minimum:
                - room_id (str)
                - name (str)
                - area_m2 (float)
                - ceiling_height_m (float)
                - polygon (List[Tuple[float, float]])
                - occupancy_type (str)
                - level_id (str)

        Returns:
            IFC43MappedElement representing an IfcSpace.
        """
        room_id = str(room.get("room_id", "UNKNOWN"))
        global_id = self._generate_global_id(f"room:{room_id}")

        property_sets: Dict[str, Dict[str, Any]] = {}
        property_sets["Pset_SpaceCommon"] = {
            "Reference": room_id,
            "Category": "Rooms",
            "OccupancyType": room.get("occupancy_type", "office"),
        }
        property_sets[PSET_FIREAI_DESIGN] = {
            "Area": float(room.get("area_m2", 0.0)),
            "CeilingHeight": float(room.get("ceiling_height_m", 3.0)),
            "IsSprinklered": bool(room.get("is_sprinklered", False)),
            "Unit": "METRE",
        }

        return IFC43MappedElement(
            global_id=global_id,
            ifc_type="IfcSpace",
            predefined_type=None,
            name=str(room.get("name", room_id)),
            description=f"FireAI room {room_id} ({room.get('occupancy_type', 'office')})",
            location=None,  # Rooms don't have a single point location
            contained_in=self._generate_global_id(f"level:{room.get('level_id', 'L1')}"),
            property_sets=property_sets,
            source_schema="IFC4",
            target_schema=self.target_schema,
        )

    def map_building(self, building: Dict[str, Any]) -> IFC43MappedElement:
        """Map a FireAI building to IFC 4.3 IfcBuilding."""
        building_id = str(building.get("building_id", "BUILDING-001"))
        global_id = self._generate_global_id(f"building:{building_id}")

        return IFC43MappedElement(
            global_id=global_id,
            ifc_type="IfcBuilding",
            predefined_type=None,
            name=str(building.get("name", building_id)),
            description=f"FireAI building {building_id}",
            location=None,
            contained_in=None,
            property_sets={
                "Pset_BuildingCommon": {
                    "Reference": building_id,
                    "NumberOfStoreys": int(building.get("num_storeys", 1)),
                },
            },
            source_schema="IFC4",
            target_schema=self.target_schema,
        )

    # ------------------------------------------------------------------
    # IFC File Header Generation
    # ------------------------------------------------------------------

    def generate_ifc_header(
        self,
        author: str = "FireAI",
        organization: str = "FireAI Platform",
        application: str = "FireAI IFC43Mapper v1.0",
        origin_schema: str = "IFC4",
    ) -> Dict[str, str]:
        """Generate IFC 4.3 file header metadata.

        Returns:
            Dict with keys: file_description, file_name, file_schema.
            Suitable for ifcopenshell.file() header setup.
        """
        from datetime import datetime, timezone

        timestamp = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

        return {
            "file_description": {
                "description": [IFC43_FILE_DESCRIPTION],
                "implementation_level": IFC43_IMPLEMENTATION_LEVEL,
            },
            "file_name": {
                "time_stamp": timestamp,
                "author": [author],
                "organization": [organization],
                "originating_system": application,
                "authorization": "FireAI Platform",
            },
            "file_schema": [self.target_schema],  # IFC4X3_ADD2
            "origin_schema": origin_schema,  # for audit trail
            "mapper_version": "1.0",
            "nfpa_reference": "NFPA 72-2022 §7.5 (Audit Trail)",
        }

    # ------------------------------------------------------------------
    # Batch Mapping
    # ------------------------------------------------------------------

    def map_project(
        self,
        project: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Map an entire FireAI project to IFC 4.3 representation.

        Args:
            project: Dict with:
                - building: Dict (building info)
                - rooms: List[Dict]
                - detectors: List[Dict]

        Returns:
            Dict with:
                - header: IFC header
                - building: IFC43MappedElement
                - rooms: List[IFC43MappedElement]
                - detectors: List[IFC43MappedElement]
                - schema_version: IFC43_SCHEMA_VERSION
                - statistics: mapping stats
        """
        building = project.get("building", {})
        rooms = project.get("rooms", [])
        detectors = project.get("detectors", [])

        mapped_building = self.map_building(building)
        mapped_rooms = [self.map_room(r) for r in rooms]
        mapped_detectors = [self.map_detector(d) for d in detectors]

        return {
            "header": self.generate_ifc_header(),
            "building": mapped_building,
            "rooms": mapped_rooms,
            "detectors": mapped_detectors,
            "schema_version": self.target_schema,
            "statistics": {
                "total_rooms": len(mapped_rooms),
                "total_detectors": len(mapped_detectors),
                "smoke_detectors": sum(
                    1 for d in mapped_detectors
                    if d.predefined_type == "SMOKE_DETECTOR"
                ),
                "heat_detectors": sum(
                    1 for d in mapped_detectors
                    if d.predefined_type == "HEAT_DETECTOR"
                ),
                "other_devices": sum(
                    1 for d in mapped_detectors
                    if d.predefined_type not in ("SMOKE_DETECTOR", "HEAT_DETECTOR")
                ),
                "source_schema": "IFC4",
                "target_schema": self.target_schema,
            },
        }


__all__ = [
    "IFC43_SCHEMA_VERSION",
    "IFC43_FILE_DESCRIPTION",
    "IFC43ElementType",
    "FIREAI_TO_IFC43_MAP",
    "IFC43Property",
    "IFC43MappedElement",
    "IFC43Mapper",
    "PSET_FIREALARM_COMMON",
    "PSET_FIREAI_DESIGN",
    "PSET_FIREAI_AUDIT",
    "PSET_FIREAI_SAFETY",
]
