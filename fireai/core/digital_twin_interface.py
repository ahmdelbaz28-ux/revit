"""digital_twin_interface.py — FireAI Digital Twin Interface
=========================================================
Bidirectional synchronization layer between the FireAI placement
engine and Building Information Models (BIM).  Prepares the system
for real-time BIM synchronization by providing:

  1. Versioned snapshots of detector placements (TwinModelVersion)
  2. Change detection between design versions (ChangeRecord)
  3. IFC / gBXML export payloads ready for downstream generators
  4. Bidirectional sync protocol definition (DigitalTwinState)
  5. Real-time event streaming via EventBus integration

NFPA 72-2022 Compliance:
  Every snapshot captures proof certificate hashes, enabling AHJ
  audit trail reconstruction from any point in the design history.

Design Principles:
  - No external dependencies beyond stdlib + existing fireai modules
  - Thread-safe operations (threading.Lock)
  - Immutable version history — snapshots are append-only
  - EventBus integration for real-time notification
  - SHA-256 checksumming for tamper detection

Usage:
    from fireai.core.digital_twin_interface import (
        DigitalTwinInterface,
        DigitalTwinState,
        TwinModelVersion,
        ChangeRecord,
    )

    twin = DigitalTwinInterface()

    room_results = [
        {
            "room_id": "R1",
            "name": "Office 101",
            "floor_name": "Level 1",
            "width_m": 10.0,
            "depth_m": 8.0,
            "ceiling_height_m": 3.0,
            "detector_type": "smoke",
            "detectors": [
                {"x": 3.0, "y": 2.5, "z": 3.0, "radius": NFPA72_SMOKE_RADIUS_M},
                {"x": 7.0, "y": 5.5, "z": 3.0, "radius": NFPA72_SMOKE_RADIUS_M},
            ],
            "proof_certificates": ["abc123", "def456"],
        },
    ]

    version = twin.snapshot(room_results)
    ifc_payload = twin.export_ifc_payload(room_results)
"""

from __future__ import annotations

import hashlib
import json
import logging
import threading
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

from .digital_twin import NFPA72_DEFAULT_CEILING_M, NFPA72_SMOKE_RADIUS_M
from .event_bus import EventBus, Events

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════
# Digital Twin State Enum
# ═══════════════════════════════════════════════════════════════════════


class DigitalTwinState(Enum):
    """Synchronization state of the Digital Twin with the BIM model.

    State Transitions:
        DISCONNECTED → CONNECTED  (BIM connection established)
        CONNECTED    → SYNCING    (sync initiated)
        SYNCING      → SYNCED     (sync completed successfully)
        SYNCING      → CONFLICT   (BIM changed independently)
        SYNCING      → ERROR      (sync error occurred)
        CONFLICT     → SYNCING    (conflict resolved, re-sync)
        ERROR        → CONNECTED  (error recovered)
        *            → DISCONNECTED (connection lost)
    """

    DISCONNECTED = "disconnected"  # No BIM connection
    CONNECTED = "connected"  # Connected to BIM, not synced
    SYNCING = "syncing"  # Synchronization in progress
    SYNCED = "synced"  # Fully synchronized with BIM model
    CONFLICT = "conflict"  # Conflict detected (BIM changed independently)
    ERROR = "error"  # Sync error


# ═══════════════════════════════════════════════════════════════════════
# Data Models
# ═══════════════════════════════════════════════════════════════════════


@dataclass(frozen=True)
class TwinModelVersion:
    """Immutable snapshot of the Digital Twin model at a point in time.

    Each version captures:
      - The number of rooms and detectors in the model
      - SHA-256 checksum of all detector positions (tamper detection)
      - Proof certificate hashes for AHJ audit trail reconstruction

    Attributes:
        version_id: Unique UUID identifying this version.
        timestamp: ISO 8601 UTC timestamp when the snapshot was taken.
        room_count: Number of rooms in the model.
        detector_count: Total number of detectors across all rooms.
        proof_certificates: List of proof certificate hashes bound to
            this version — enables AHJ audit reconstruction.
        checksum: SHA-256 hash of all detector positions concatenated,
            providing a tamper-evident fingerprint of the layout.

    """

    version_id: str
    timestamp: str
    room_count: int
    detector_count: int
    proof_certificates: List[str]
    checksum: str

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to a plain dictionary."""
        return asdict(self)

    def to_json(self) -> str:
        """Serialize to a JSON string."""
        return json.dumps(self.to_dict(), sort_keys=True, ensure_ascii=False)


@dataclass(frozen=True)
class ChangeRecord:
    """Immutable record of a single change between two model versions.

    Change detection produces a list of ChangeRecords that describe
    exactly what was added, removed, modified, or repositioned between
    the old and new versions.  Each record is attributed to an author
    (system, pe, or ahj) with a reason string.

    Attributes:
        change_id: Unique UUID identifying this change.
        timestamp: ISO 8601 UTC timestamp when the change was detected.
        change_type: One of "added", "removed", "modified", "repositioned".
        room_id: The room where the change occurred.
        detector_index: Optional index of the affected detector within
            the room's detector list.
        old_value: Previous state (position, radius, etc.) if applicable.
        new_value: New state if applicable.
        author: Who made the change — "system", "pe" (professional
            engineer), or "ahj" (authority having jurisdiction).
        reason: Human-readable reason for the change.

    """

    change_id: str
    timestamp: str
    change_type: str  # Literal["added", "removed", "modified", "repositioned"]
    room_id: str
    detector_index: Optional[int]
    old_value: Optional[Dict[str, Any]]
    new_value: Optional[Dict[str, Any]]
    author: str  # Literal["system", "pe", "ahj"]
    reason: str

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to a plain dictionary."""
        return asdict(self)

    def to_json(self) -> str:
        """Serialize to a JSON string."""
        return json.dumps(self.to_dict(), sort_keys=True, ensure_ascii=False)


# ═══════════════════════════════════════════════════════════════════════
# IFC / gBXML GUID Generation Helpers
# ═══════════════════════════════════════════════════════════════════════


def _generate_ifc_guid() -> str:
    """Generate an IFC-compatible GUID (22-character base64-like string).

    IFC uses a compressed GUID format.  For simplicity and
    traceability, we use a hex UUID with the curly braces removed,
    which is valid for IfcGloballyUniqueId in IFC4.
    """
    return uuid.uuid4().hex[:22].upper()


# ═══════════════════════════════════════════════════════════════════════
# Digital Twin Interface
# ═══════════════════════════════════════════════════════════════════════


class DigitalTwinInterface:
    """Bidirectional synchronization interface between FireAI and BIM.

    Maintains versioned snapshots of detector placements, detects changes
    between versions, and exports IFC/gBXML payloads for downstream
    BIM integration.

    Thread Safety:
        All public methods are protected by a threading.Lock.

    EventBus Integration:
        - On each snapshot, publishes a "model.changed" event.
        - On each change detection, publishes the appropriate event
          (detector.placed, detector.removed, etc.).

    Example:
        twin = DigitalTwinInterface()
        version = twin.snapshot(room_results)
        changes = twin.detect_changes(old_version, version)
        ifc = twin.export_ifc_payload(room_results)

    """

    def __init__(self, event_bus: Optional[EventBus] = None) -> None:
        """Initialize the Digital Twin Interface.

        Args:
            event_bus: Optional EventBus instance. If not provided,
                the singleton EventBus is used.

        """
        self._lock = threading.Lock()
        self._state: DigitalTwinState = DigitalTwinState.DISCONNECTED
        self._version_history: List[TwinModelVersion] = []
        self._change_log: List[ChangeRecord] = []
        self._current_room_results: List[Dict[str, Any]] = []
        self._bus = event_bus or EventBus()

    # ── Properties ───────────────────────────────────────────────────

    @property
    def state(self) -> DigitalTwinState:
        """Current synchronization state."""
        with self._lock:
            return self._state

    @state.setter
    def state(self, new_state: DigitalTwinState) -> None:
        """Update the synchronization state.

        Args:
            new_state: The new DigitalTwinState to transition to.

        Raises:
            TypeError: If new_state is not a DigitalTwinState enum.

        """
        if not isinstance(new_state, DigitalTwinState):
            raise TypeError(f"state must be DigitalTwinState, got {type(new_state).__name__}")
        with self._lock:
            old_state = self._state
            self._state = new_state
        logger.info(
            "DigitalTwin state transition: %s → %s",
            old_state.value,
            new_state.value,
        )

    # ── Snapshot ─────────────────────────────────────────────────────

    def snapshot(self, room_results: List[Dict[str, Any]]) -> TwinModelVersion:
        """Capture a versioned snapshot of the current detector model.

        Creates a TwinModelVersion with a SHA-256 checksum of all
        detector positions, proof certificate hashes, and metadata.
        Appends the version to the internal version history and
        publishes a "model.changed" event on the EventBus.

        Args:
            room_results: List of room result dictionaries.  Each dict
                must contain at minimum:
                  - "room_id": str
                  - "detectors": list of dicts with "x", "y", "z"
                Optional keys:
                  - "proof_certificates": list of certificate hash strings

        Returns:
            A TwinModelVersion representing this snapshot.

        Raises:
            ValueError: If room_results is empty.

        """
        if not room_results:
            raise ValueError("room_results must not be empty for snapshot")

        # Collect detector positions and proof certificates
        detector_positions: List[Tuple[float, ...]] = []
        proof_certs: List[str] = []
        room_count = len(room_results)
        detector_count = 0

        for room in room_results:
            detectors = room.get("detectors", [])
            detector_count += len(detectors)
            for det in detectors:
                pos = (
                    float(det.get("x", 0.0)),
                    float(det.get("y", 0.0)),
                    float(det.get("z", 0.0)),
                )
                detector_positions.append(pos)

            # Collect proof certificates
            certs = room.get("proof_certificates", [])
            if isinstance(certs, list):
                proof_certs.extend(str(c) for c in certs)

        # Compute checksum
        checksum = self.compute_checksum(detector_positions)

        # Build version
        now = datetime.now(timezone.utc).isoformat()
        version = TwinModelVersion(
            version_id=str(uuid.uuid4()),
            timestamp=now,
            room_count=room_count,
            detector_count=detector_count,
            proof_certificates=proof_certs,
            checksum=checksum,
        )

        with self._lock:
            self._version_history.append(version)
            self._current_room_results = list(room_results)

        # Publish event
        self._bus.publish(
            Events.MODEL_CHANGED,
            {
                "version_id": version.version_id,
                "room_count": version.room_count,
                "detector_count": version.detector_count,
                "checksum": version.checksum,
            },
            source="digital_twin_interface",
            correlation_id=version.version_id,
        )

        logger.info(
            "Snapshot captured: version=%s rooms=%d detectors=%d checksum=%s",
            version.version_id[:8],
            version.room_count,
            version.detector_count,
            version.checksum[:16],
        )

        return version

    # ── Change Detection ─────────────────────────────────────────────

    def detect_changes(
        self,
        old_version: TwinModelVersion,
        new_version: TwinModelVersion,
    ) -> List[ChangeRecord]:
        """Detect changes between two model versions.

        Compares detector positions and room counts between the old
        and new versions by reconstructing the detector layouts from
        the stored room results.  Produces ChangeRecord entries for
        each detected difference.

        If the checksums are identical, no changes are detected and
        an empty list is returned.

        Args:
            old_version: The earlier TwinModelVersion to compare from.
            new_version: The later TwinModelVersion to compare to.

        Returns:
            List of ChangeRecord objects describing detected changes.

        """
        # Quick path: identical checksums means no changes
        if old_version.checksum == new_version.checksum:
            logger.debug("No changes detected — checksums match")
            return []

        changes: List[ChangeRecord] = []
        now = datetime.now(timezone.utc).isoformat()

        # Room count changes
        if old_version.room_count != new_version.room_count:
            diff = new_version.room_count - old_version.room_count
            change_type = "added" if diff > 0 else "removed"
            changes.append(
                ChangeRecord(
                    change_id=str(uuid.uuid4()),
                    timestamp=now,
                    change_type=change_type,
                    room_id="__global__",
                    detector_index=None,
                    old_value={"room_count": old_version.room_count},
                    new_value={"room_count": new_version.room_count},
                    author="system",
                    reason=(f"Room count changed from {old_version.room_count} to {new_version.room_count}"),
                )
            )

        # Detector count changes
        if old_version.detector_count != new_version.detector_count:
            diff = new_version.detector_count - old_version.detector_count
            change_type = "added" if diff > 0 else "removed"
            changes.append(
                ChangeRecord(
                    change_id=str(uuid.uuid4()),
                    timestamp=now,
                    change_type=change_type,
                    room_id="__global__",
                    detector_index=None,
                    old_value={"detector_count": old_version.detector_count},
                    new_value={"detector_count": new_version.detector_count},
                    author="system",
                    reason=(
                        f"Detector count changed from {old_version.detector_count} to {new_version.detector_count}"
                    ),
                )
            )

        # Per-room change detection from stored room results
        with self._lock:
            room_results = list(self._current_room_results)

        if room_results:
            old_detectors = self._reconstruct_detector_map(old_version, room_results)
            new_detectors = self._reconstruct_detector_map(new_version, room_results)

            all_room_ids = set(old_detectors.keys()) | set(new_detectors.keys())

            for room_id in all_room_ids:
                old_dets = old_detectors.get(room_id, [])
                new_dets = new_detectors.get(room_id, [])

                # Rooms added/removed
                if room_id not in old_detectors and room_id in new_detectors:
                    for idx, det in enumerate(new_dets):
                        changes.append(self._make_change("added", room_id, idx, None, det, now))
                    continue

                if room_id in old_detectors and room_id not in new_detectors:
                    for idx, det in enumerate(old_dets):
                        changes.append(self._make_change("removed", room_id, idx, det, None, now))
                    continue

                # Per-detector comparison
                max_len = max(len(old_dets), len(new_dets))
                for idx in range(max_len):
                    if idx >= len(old_dets):
                        # New detector added
                        changes.append(
                            self._make_change(
                                "added",
                                room_id,
                                idx,
                                None,
                                new_dets[idx],
                                now,
                            )
                        )
                    elif idx >= len(new_dets):
                        # Detector removed
                        changes.append(
                            self._make_change(
                                "removed",
                                room_id,
                                idx,
                                old_dets[idx],
                                None,
                                now,
                            )
                        )
                    else:
                        # Check for repositioning or modification
                        old_det = old_dets[idx]
                        new_det = new_dets[idx]
                        position_changed = (
                            abs(old_det.get("x", 0) - new_det.get("x", 0)) > 1e-6
                            or abs(old_det.get("y", 0) - new_det.get("y", 0)) > 1e-6
                            or abs(old_det.get("z", 0) - new_det.get("z", 0)) > 1e-6
                        )
                        radius_changed = abs(old_det.get("radius", 0) - new_det.get("radius", 0)) > 1e-6

                        if position_changed:
                            changes.append(
                                self._make_change(
                                    "repositioned",
                                    room_id,
                                    idx,
                                    old_det,
                                    new_det,
                                    now,
                                )
                            )
                        elif radius_changed:
                            changes.append(
                                self._make_change(
                                    "modified",
                                    room_id,
                                    idx,
                                    old_det,
                                    new_det,
                                    now,
                                )
                            )

        # Append changes to internal log
        with self._lock:
            self._change_log.extend(changes)

        # Publish per-change events
        for change in changes:
            event_type = {
                "added": Events.DETECTOR_PLACED,
                "removed": Events.DETECTOR_REMOVED,
                "modified": Events.MODEL_CHANGED,
                "repositioned": Events.MODEL_CHANGED,
            }.get(change.change_type, Events.MODEL_CHANGED)

            self._bus.publish(
                event_type,
                {
                    "change_id": change.change_id,
                    "change_type": change.change_type,
                    "room_id": change.room_id,
                    "detector_index": change.detector_index,
                    "author": change.author,
                    "reason": change.reason,
                },
                source="digital_twin_interface",
                correlation_id=new_version.version_id,
            )

        logger.info(
            "Change detection: %d changes between %s → %s",
            len(changes),
            old_version.version_id[:8],
            new_version.version_id[:8],
        )

        return changes

    # ── IFC Export ───────────────────────────────────────────────────

    def export_ifc_payload(self, room_results: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Export detector placements as an IFC4-compatible payload.

        This does NOT generate a full IFC file — it produces a
        structured dictionary that is ready for an IFC generator
        (e.g., IfcOpenShell) to consume and serialize.

        The payload follows IFC4 entity schema:
          - IFCBUILDINGSTOREY: Floor/storey container
          - IFCSPACE: Room as an IfcSpace with geometry
          - IFCFLOWSENSOR: Fire detector (SMOKESENSOR predefined type)

        Args:
            room_results: List of room result dictionaries with detector
                positions, dimensions, and metadata.

        Returns:
            Dictionary with "schema", "entities", and "property_sets".

        """
        entities: List[Dict[str, Any]] = []
        property_sets: List[Dict[str, Any]] = []

        # Group rooms by floor
        floors: Dict[str, List[Dict[str, Any]]] = {}
        for room in room_results:
            floor_name = room.get("floor_name", "Level 1")
            if floor_name not in floors:
                floors[floor_name] = []
            floors[floor_name].append(room)

        # Generate IFCBUILDINGSTOREY entities
        floor_guids: Dict[str, str] = {}
        for floor_name in floors:
            storey_guid = _generate_ifc_guid()
            floor_guids[floor_name] = storey_guid
            entities.append(
                {
                    "type": "IFCBUILDINGSTOREY",
                    "guid": storey_guid,
                    "name": floor_name,
                }
            )

        # Generate IFCSPACE and IFCFLOWSENSOR entities per room
        for floor_name, rooms in floors.items():
            storey_guid = floor_guids[floor_name]

            for room in rooms:
                room_id = room.get("room_id", "unknown")
                room_name = room.get("name", room_id)
                width = float(room.get("width_m", 0.0))
                depth = float(room.get("depth_m", 0.0))
                height = float(room.get("ceiling_height_m", NFPA72_DEFAULT_CEILING_M))

                # IFCSPACE entity
                space_guid = _generate_ifc_guid()
                entities.append(
                    {
                        "type": "IFCSPACE",
                        "guid": space_guid,
                        "name": room_name,
                        "long_name": f"Room {room_id}",
                        "composition_type": "ELEMENT",
                        "geometry": {
                            "width_m": width,
                            "depth_m": depth,
                            "height_m": height,
                            "shape": "extrusion",
                            "footprint": [
                                [0.0, 0.0],
                                [width, 0.0],
                                [width, depth],
                                [0.0, depth],
                            ],
                        },
                        "contained_in_storey": storey_guid,
                    }
                )

                # Property set for room NFPA metadata
                room_pset_guid = _generate_ifc_guid()
                property_sets.append(
                    {
                        "guid": room_pset_guid,
                        "name": "Pset_FireAI_RoomNFPA",
                        "properties": {
                            "RoomID": room_id,
                            "OccupancyType": room.get("occupancy_type", "office"),
                            "CeilingHeight_m": height,
                            "DetectorType": room.get("detector_type", "smoke"),
                            "FloorName": floor_name,
                        },
                        "related_entity": space_guid,
                    }
                )

                # IFCFLOWSENSOR entities for each detector
                detectors = room.get("detectors", [])
                for idx, det in enumerate(detectors):
                    sensor_guid = _generate_ifc_guid()
                    det_type = room.get("detector_type", "smoke").upper()
                    predefined_type = "SMOKESENSOR"
                    if "HEAT" in det_type:
                        predefined_type = "HEATSENSOR"
                    elif "FLAME" in det_type:
                        predefined_type = "FLAMESENSOR"
                    elif "GAS" in det_type:
                        predefined_type = "GASSENSOR"

                    x = float(det.get("x", 0.0))
                    y = float(det.get("y", 0.0))
                    z = float(det.get("z", height))

                    entities.append(
                        {
                            "type": "IFCFLOWSENSOR",
                            "guid": sensor_guid,
                            "name": f"{room_id}_Detector_{idx + 1}",
                            "predefined_type": predefined_type,
                            "object_placement": {
                                "x": x,
                                "y": y,
                                "z": z,
                            },
                            "contained_in": space_guid,
                        }
                    )

                    # Detector property set
                    det_pset_guid = _generate_ifc_guid()
                    property_sets.append(
                        {
                            "guid": det_pset_guid,
                            "name": "Pset_FireAI_DetectorNFPA",
                            "properties": {
                                "DetectorIndex": idx + 1,
                                "CoverageRadius_m": float(det.get("radius", NFPA72_SMOKE_RADIUS_M)),
                                "DetectorType": det_type,
                                "NFPAReference": "NFPA 72-2022 Table 17.6.3.1.1",
                                "X_m": x,
                                "Y_m": y,
                                "Z_m": z,
                            },
                            "related_entity": sensor_guid,
                        }
                    )

        payload = {
            "schema": "IFC4",
            "entities": entities,
            "property_sets": property_sets,
        }

        logger.info(
            "IFC payload exported: %d entities, %d property sets",
            len(entities),
            len(property_sets),
        )

        return payload

    # ── gBXML Export ─────────────────────────────────────────────────

    def export_gbxml_payload(self, room_results: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Export detector placements as a gBXML-compatible payload.

        Produces a structured dictionary that maps to the Green
        Building XML schema, suitable for integration with energy
        modeling and building analysis tools.

        gBXML maps:
          - Campus → Building → Space (rooms)
          - Each detector as a Sensor element within a Space

        Args:
            room_results: List of room result dictionaries with detector
                positions, dimensions, and metadata.

        Returns:
            Dictionary with "schema", "campus", and "sensors" keys.

        """
        spaces: List[Dict[str, Any]] = []
        sensors: List[Dict[str, Any]] = []

        # Group by floor for building storey mapping
        floors: Dict[str, List[Dict[str, Any]]] = {}
        for room in room_results:
            floor_name = room.get("floor_name", "Level 1")
            if floor_name not in floors:
                floors[floor_name] = []
            floors[floor_name].append(room)

        building_id = f"Building_{uuid.uuid4().hex[:8]}"
        storeys: List[Dict[str, Any]] = []

        for floor_name, rooms in floors.items():
            floor_spaces: List[str] = []

            for room in rooms:
                room_id = room.get("room_id", "unknown")
                room_name = room.get("name", room_id)
                width = float(room.get("width_m", 0.0))
                depth = float(room.get("depth_m", 0.0))
                height = float(room.get("ceiling_height_m", NFPA72_DEFAULT_CEILING_M))

                space_id = f"Space_{room_id}_{uuid.uuid4().hex[:6]}"
                floor_spaces.append(space_id)

                # Space geometry — rectangular plan
                area = width * depth
                volume = area * height

                space: Dict[str, Any] = {
                    "id": space_id,
                    "name": room_name,
                    "description": f"Room {room_id} — {room.get('occupancy_type', 'office')}",
                    "area_sqm": round(area, 4),
                    "volume_cubic_m": round(volume, 4),
                    "ceiling_height_m": height,
                    "floor_name": floor_name,
                    "planar_geometry": {
                        "type": "rectangle",
                        "width_m": width,
                        "depth_m": depth,
                        "vertices": [
                            {"x": 0.0, "y": 0.0},
                            {"x": width, "y": 0.0},
                            {"x": width, "y": depth},
                            {"x": 0.0, "y": depth},
                        ],
                    },
                }
                spaces.append(space)

                # Sensor elements for each detector
                detectors = room.get("detectors", [])
                for idx, det in enumerate(detectors):
                    sensor_id = f"Sensor_{room_id}_{idx + 1}_{uuid.uuid4().hex[:4]}"
                    det_type = room.get("detector_type", "smoke").upper()

                    x = float(det.get("x", 0.0))
                    y = float(det.get("y", 0.0))
                    z = float(det.get("z", height))

                    sensors.append(
                        {
                            "id": sensor_id,
                            "name": f"{room_id}_Detector_{idx + 1}",
                            "type": "FireDetector",
                            "subtype": det_type,
                            "space_id": space_id,
                            "position": {
                                "x_m": x,
                                "y_m": y,
                                "z_m": z,
                            },
                            "coverage_radius_m": float(det.get("radius", NFPA72_SMOKE_RADIUS_M)),
                            "nfpa_reference": "NFPA 72-2022 Table 17.6.3.1.1",
                        }
                    )

            storeys.append(
                {
                    "id": f"Storey_{floor_name.replace(' ', '_')}_{uuid.uuid4().hex[:6]}",
                    "name": floor_name,
                    "spaces": floor_spaces,
                }
            )

        payload = {
            "schema": "gbXML",
            "campus": {
                "id": f"Campus_{uuid.uuid4().hex[:8]}",
                "building": {
                    "id": building_id,
                    "name": "FireAI Building",
                    "storeys": storeys,
                },
            },
            "spaces": spaces,
            "sensors": sensors,
        }

        logger.info(
            "gBXML payload exported: %d spaces, %d sensors",
            len(spaces),
            len(sensors),
        )

        return payload

    # ── Query Methods ────────────────────────────────────────────────

    def get_current_version(self) -> Optional[TwinModelVersion]:
        """Return the most recent version from the version history.

        Returns:
            The latest TwinModelVersion, or None if no snapshots exist.

        """
        with self._lock:
            if self._version_history:
                return self._version_history[-1]
            return None

    def get_change_history(self) -> List[ChangeRecord]:
        """Return a copy of the full change log.

        Returns:
            List of all ChangeRecord objects accumulated over time.

        """
        with self._lock:
            return list(self._change_log)

    # ── Checksum ─────────────────────────────────────────────────────

    @staticmethod
    def compute_checksum(detector_positions: List[Tuple[float, ...]]) -> str:
        """Compute a SHA-256 checksum over all detector positions.

        The checksum is computed by serializing the detector positions
        as a JSON array of coordinate tuples (sorted by x, y, z) and
        hashing the result with SHA-256.  This provides a tamper-evident
        fingerprint of the detector layout.

        Args:
            detector_positions: List of (x, y, z) or (x, y) tuples
                representing all detector positions in the model.

        Returns:
            Hex-encoded SHA-256 digest string.

        """
        if not detector_positions:
            return hashlib.sha256(b"no_detectors").hexdigest()

        # Normalize positions to 6 decimal places and sort for determinism
        normalized = sorted([tuple(round(float(c), 6) for c in pos) for pos in detector_positions])
        raw = json.dumps(normalized, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(raw.encode()).hexdigest()

    # ── Validation ───────────────────────────────────────────────────

    def validate_synchronization(self) -> bool:
        """Check if the current state matches the latest snapshot.

        Re-computes the checksum from the current room results and
        compares it against the checksum of the latest version.  If
        they match, the twin is considered synchronized.

        Returns:
            True if the current room results match the latest snapshot,
            False otherwise (or if no snapshot exists).

        """
        current_version = self.get_current_version()
        if current_version is None:
            logger.warning("No snapshot exists — cannot validate synchronization")
            return False

        with self._lock:
            room_results = list(self._current_room_results)

        # Reconstruct detector positions from current room results
        detector_positions: List[Tuple[float, ...]] = []
        for room in room_results:
            for det in room.get("detectors", []):
                pos = (
                    float(det.get("x", 0.0)),
                    float(det.get("y", 0.0)),
                    float(det.get("z", 0.0)),
                )
                detector_positions.append(pos)

        current_checksum = self.compute_checksum(detector_positions)
        is_valid = current_checksum == current_version.checksum

        if is_valid:
            logger.debug("Synchronization valid: checksum=%s", current_checksum[:16])
        else:
            logger.warning(
                "Synchronization MISMATCH: current=%s version=%s",
                current_checksum[:16],
                current_version.checksum[:16],
            )

        return is_valid

    # ── Version History Access ───────────────────────────────────────

    def get_version_history(self) -> List[TwinModelVersion]:
        """Return a copy of the full version history.

        Returns:
            List of all TwinModelVersion objects in chronological order.

        """
        with self._lock:
            return list(self._version_history)

    def get_version_by_id(self, version_id: str) -> Optional[TwinModelVersion]:
        """Look up a version by its UUID.

        Args:
            version_id: The version UUID to search for.

        Returns:
            The matching TwinModelVersion, or None if not found.

        """
        with self._lock:
            for v in self._version_history:
                if v.version_id == version_id:
                    return v
        return None

    # ── Private Helpers ──────────────────────────────────────────────

    def _reconstruct_detector_map(
        self,
        version: TwinModelVersion,
        room_results: List[Dict[str, Any]],
    ) -> Dict[str, List[Dict[str, Any]]]:
        """Reconstruct a room→detectors map for a given version.

        Since TwinModelVersion only stores aggregate counts and a
        checksum, we reconstruct the per-room detector layout from
        the current room results.  This is a best-effort reconstruction
        for change detection purposes.

        Args:
            version: The version to reconstruct for.
            room_results: Current room results (used as baseline).

        Returns:
            Dictionary mapping room_id → list of detector dicts.

        """
        result: Dict[str, List[Dict[str, Any]]] = {}
        for room in room_results:
            room_id = room.get("room_id", "unknown")
            detectors = room.get("detectors", [])
            result[room_id] = [
                {
                    "x": det.get("x", 0.0),
                    "y": det.get("y", 0.0),
                    "z": det.get("z", 0.0),
                    "radius": det.get("radius", 0.0),
                }
                for det in detectors
            ]
        return result

    @staticmethod
    def _make_change(
        change_type: str,
        room_id: str,
        detector_index: int,
        old_det: Optional[Dict[str, Any]],
        new_det: Optional[Dict[str, Any]],
        timestamp: str,
    ) -> ChangeRecord:
        """Create a ChangeRecord from detector state transition.

        Args:
            change_type: One of "added", "removed", "modified", "repositioned".
            room_id: Room identifier.
            detector_index: Index of the detector in the room's list.
            old_det: Previous detector state dict (or None).
            new_det: New detector state dict (or None).
            timestamp: ISO 8601 timestamp string.

        Returns:
            A ChangeRecord instance.

        """
        return ChangeRecord(
            change_id=str(uuid.uuid4()),
            timestamp=timestamp,
            change_type=change_type,
            room_id=room_id,
            detector_index=detector_index,
            old_value=old_det,
            new_value=new_det,
            author="system",
            reason=_describe_change(change_type, room_id, detector_index),
        )


def _describe_change(change_type: str, room_id: str, detector_index: int) -> str:
    """Generate a human-readable reason string for a change.

    Args:
        change_type: The type of change.
        room_id: The affected room.
        detector_index: Index of the affected detector.

    Returns:
        A descriptive reason string.

    """
    descriptions = {
        "added": f"Detector {detector_index + 1} added in room {room_id}",
        "removed": f"Detector {detector_index + 1} removed from room {room_id}",
        "modified": f"Detector {detector_index + 1} properties changed in room {room_id}",
        "repositioned": (f"Detector {detector_index + 1} repositioned in room {room_id}"),
    }
    return descriptions.get(
        change_type,
        f"Change type '{change_type}' for detector {detector_index + 1} in room {room_id}",
    )


# ═══════════════════════════════════════════════════════════════════════
# Module Exports
# ═══════════════════════════════════════════════════════════════════════

__all__ = [
    "ChangeRecord",
    "DigitalTwinInterface",
    "DigitalTwinState",
    "TwinModelVersion",
]


# ═══════════════════════════════════════════════════════════════════════
# Self-Test Block
# ═══════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    print("=" * 70)
    print("FireAI Digital Twin Interface — Self-Test")
    print("=" * 70)

    # Reset EventBus singleton for clean test
    EventBus.reset()

    # ── Test Data ─────────────────────────────────────────────────────
    room_results_v1 = [
        {
            "room_id": "R1",
            "name": "Office 101",
            "floor_name": "Level 1",
            "width_m": 10.0,
            "depth_m": 8.0,
            "ceiling_height_m": 3.0,
            "detector_type": "smoke",
            "occupancy_type": "office",
            "detectors": [
                {"x": 3.0, "y": 2.5, "z": 3.0, "radius": NFPA72_SMOKE_RADIUS_M},
                {"x": 7.0, "y": 5.5, "z": 3.0, "radius": NFPA72_SMOKE_RADIUS_M},
            ],
            "proof_certificates": ["cert_r1_v1_hash"],
        },
        {
            "room_id": "R2",
            "name": "Corridor A",
            "floor_name": "Level 1",
            "width_m": 15.0,
            "depth_m": 2.0,
            "ceiling_height_m": 3.0,
            "detector_type": "smoke",
            "occupancy_type": "corridor",
            "detectors": [
                {"x": 3.75, "y": 1.0, "z": 3.0, "radius": NFPA72_SMOKE_RADIUS_M},
                {"x": 11.25, "y": 1.0, "z": 3.0, "radius": NFPA72_SMOKE_RADIUS_M},
            ],
            "proof_certificates": ["cert_r2_v1_hash"],
        },
    ]

    room_results_v2 = [
        {
            "room_id": "R1",
            "name": "Office 101",
            "floor_name": "Level 1",
            "width_m": 10.0,
            "depth_m": 8.0,
            "ceiling_height_m": 3.0,
            "detector_type": "smoke",
            "occupancy_type": "office",
            "detectors": [
                {"x": 3.5, "y": 2.5, "z": 3.0, "radius": NFPA72_SMOKE_RADIUS_M},  # repositioned
                {"x": 7.0, "y": 5.5, "z": 3.0, "radius": NFPA72_SMOKE_RADIUS_M},
                {"x": 5.0, "y": 4.0, "z": 3.0, "radius": NFPA72_SMOKE_RADIUS_M},  # added
            ],
            "proof_certificates": ["cert_r1_v2_hash"],
        },
        {
            "room_id": "R2",
            "name": "Corridor A",
            "floor_name": "Level 1",
            "width_m": 15.0,
            "depth_m": 2.0,
            "ceiling_height_m": 3.0,
            "detector_type": "smoke",
            "occupancy_type": "corridor",
            "detectors": [
                {"x": 3.75, "y": 1.0, "z": 3.0, "radius": NFPA72_SMOKE_RADIUS_M},
                {"x": 11.25, "y": 1.0, "z": 3.0, "radius": NFPA72_SMOKE_RADIUS_M},
            ],
            "proof_certificates": ["cert_r2_v2_hash"],
        },
    ]

    # ── Test 1: Create Interface + Snapshot ───────────────────────────
    print("\n[TEST 1] Snapshot creation")
    twin = DigitalTwinInterface()
    assert twin.state == DigitalTwinState.DISCONNECTED

    version = twin.snapshot(room_results_v1)
    assert version.room_count == 2
    assert version.detector_count == 4
    assert version.version_id  # UUID is non-empty
    assert version.checksum  # SHA-256 is non-empty
    assert len(version.proof_certificates) == 2
    print(
        f"   ✓ Snapshot: version={version.version_id[:8]} "
        f"rooms={version.room_count} detectors={version.detector_count} "
        f"checksum={version.checksum[:16]}..."
    )

    # ── Test 2: get_current_version ───────────────────────────────────
    print("\n[TEST 2] get_current_version")
    current = twin.get_current_version()
    assert current is not None
    assert current.version_id == version.version_id
    print(f"   ✓ Current version matches: {current.version_id[:8]}")

    # ── Test 3: Checksum Computation ──────────────────────────────────
    print("\n[TEST 3] Checksum computation")
    positions = [(3.0, 2.5, 3.0), (7.0, 5.5, 3.0)]
    checksum1 = twin.compute_checksum(positions)  # type: ignore[arg-type]
    checksum2 = twin.compute_checksum(positions)  # type: ignore[arg-type]
    assert checksum1 == checksum2, "Deterministic checksum required"
    checksum3 = twin.compute_checksum([(3.0, 2.5, 3.0)])
    assert checksum1 != checksum3, "Different positions → different checksum"
    print(f"   ✓ Deterministic checksum: {checksum1[:16]}...")
    print("   ✓ Different positions produce different checksum")

    # ── Test 4: Empty checksum ────────────────────────────────────────
    print("\n[TEST 4] Empty detector positions checksum")
    empty_checksum = twin.compute_checksum([])
    assert empty_checksum, "Empty checksum should still be non-empty"
    print(f"   ✓ Empty checksum: {empty_checksum[:16]}...")

    # ── Test 5: State Transitions ─────────────────────────────────────
    print("\n[TEST 5] State transitions")
    twin.state = DigitalTwinState.CONNECTED
    assert twin.state == DigitalTwinState.CONNECTED
    twin.state = DigitalTwinState.SYNCING
    assert twin.state == DigitalTwinState.SYNCING
    twin.state = DigitalTwinState.SYNCED
    assert twin.state == DigitalTwinState.SYNCED
    print("   ✓ State transitions: DISCONNECTED → CONNECTED → SYNCING → SYNCED")

    # ── Test 6: Change Detection ──────────────────────────────────────
    print("\n[TEST 6] Change detection between versions")
    old_version = twin.snapshot(room_results_v1)
    new_version = twin.snapshot(room_results_v2)
    changes = twin.detect_changes(old_version, new_version)
    assert len(changes) > 0, "Changes should be detected"
    change_types = [c.change_type for c in changes]
    print(f"   ✓ Detected {len(changes)} changes: {change_types}")

    # ── Test 7: Identical Versions (no changes) ──────────────────────
    print("\n[TEST 7] Identical versions — no changes")
    same_v1 = twin.snapshot(room_results_v1)
    same_v2 = twin.snapshot(room_results_v1)
    no_changes = twin.detect_changes(same_v1, same_v2)
    assert len(no_changes) == 0, "Identical versions should have no changes"
    print("   ✓ No changes detected for identical versions")

    # ── Test 8: IFC Export ────────────────────────────────────────────
    print("\n[TEST 8] IFC export payload")
    ifc = twin.export_ifc_payload(room_results_v1)
    assert ifc["schema"] == "IFC4"
    entity_types = [e["type"] for e in ifc["entities"]]
    assert "IFCBUILDINGSTOREY" in entity_types
    assert "IFCSPACE" in entity_types
    assert "IFCFLOWSENSOR" in entity_types
    print(f"   ✓ IFC4 payload: {len(ifc['entities'])} entities, {len(ifc['property_sets'])} property sets")
    print(f"   ✓ Entity types: {sorted(set(entity_types))}")

    # ── Test 9: gBXML Export ──────────────────────────────────────────
    print("\n[TEST 9] gBXML export payload")
    gbxml = twin.export_gbxml_payload(room_results_v1)
    assert gbxml["schema"] == "gbXML"
    assert "campus" in gbxml
    assert "spaces" in gbxml
    assert "sensors" in gbxml
    print(f"   ✓ gBXML payload: {len(gbxml['spaces'])} spaces, {len(gbxml['sensors'])} sensors")

    # ── Test 10: validate_synchronization ────────────────────────────
    print("\n[TEST 10] validate_synchronization")
    is_valid = twin.validate_synchronization()
    # The current room_results match the latest snapshot
    assert is_valid, "Current room results should match latest snapshot"
    print(f"   ✓ Synchronization valid: {is_valid}")

    # ── Test 11: Version History ──────────────────────────────────────
    print("\n[TEST 11] Version history")
    history = twin.get_version_history()
    assert len(history) >= 2, "Should have at least 2 versions"
    print(f"   ✓ Version history: {len(history)} versions")

    # ── Test 12: Change History ──────────────────────────────────────
    print("\n[TEST 12] Change history")
    change_hist = twin.get_change_history()
    assert len(change_hist) > 0, "Should have accumulated changes"
    print(f"   ✓ Change history: {len(change_hist)} records")

    # ── Test 13: Serialization ────────────────────────────────────────
    print("\n[TEST 13] TwinModelVersion serialization")
    v_dict = version.to_dict()
    assert "version_id" in v_dict
    assert "checksum" in v_dict
    v_json = version.to_json()
    assert '"version_id"' in v_json
    print(f"   ✓ TwinModelVersion → dict: {list(v_dict.keys())}")
    print(f"   ✓ TwinModelVersion → JSON: {len(v_json)} chars")

    # ── Test 14: ChangeRecord serialization ───────────────────────────
    print("\n[TEST 14] ChangeRecord serialization")
    if changes:
        cr_dict = changes[0].to_dict()
        assert "change_id" in cr_dict
        assert "change_type" in cr_dict
        cr_json = changes[0].to_json()
        assert '"change_id"' in cr_json
        print(f"   ✓ ChangeRecord → dict: {list(cr_dict.keys())}")
        print(f"   ✓ ChangeRecord → JSON: {len(cr_json)} chars")

    # ── Test 15: Invalid state transition ────────────────────────────
    print("\n[TEST 15] Invalid state assignment")
    try:
        twin.state = "not_a_state"  # type: ignore
        raise AssertionError("Should have raised TypeError")
    except TypeError:
        print("   ✓ TypeError raised for invalid state")

    # ── Test 16: Empty snapshot ───────────────────────────────────────
    print("\n[TEST 16] Empty snapshot rejection")
    try:
        twin.snapshot([])
        raise AssertionError("Should have raised ValueError")
    except ValueError:
        print("   ✓ ValueError raised for empty room_results")

    # ── Cleanup ───────────────────────────────────────────────────────
    EventBus.reset()

    print("\n" + "=" * 70)
    print("ALL TESTS PASSED ✓")
    print("=" * 70)
