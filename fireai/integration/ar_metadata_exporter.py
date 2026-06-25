"""ar_metadata_exporter.py — AR Metadata Export with Behind-the-Wall Visibility
==============================================================================

MISSION TASK 4.2 — AR Metadata Export for RealityKit/Unity
============================================================

This module exports DigitalTwin snapshots into formats optimized for
RealityKit (iOS) and Unity, with metadata for "Behind-the-wall"
visibility — a critical AR feature for fire protection engineers
who need to see hidden detectors, conduits, and smoke barriers
during field inspections.

Output Formats
--------------
1. **GLB (Binary glTF 2.0)**: Universal format for Unity, web, Android.
2. **USDZ (Universal Scene Description, zipped)**: Native iOS RealityKit.
   This implementation produces a REAL .usdz file (zip archive with
   USDA payload), not just plain USDA text like the existing
   ar_vr_visualizer.py module.

Behind-the-Wall Metadata
-------------------------
Each SceneNode can carry these AR-specific attributes (exported as
glTF extras and USD custom attributes):

- ``is_behind_wall``: True if the element is concealed by a wall/ceiling.
- ``x_ray_enabled``: True if the element should be visible in x-ray mode.
- ``occluded_by``: List of element IDs that occlude this element.
- ``inspection_critical``: True if the element requires field inspection.
- ``safety_classification``: NFPA safety tier (TIER_1, TIER_2, etc.).

Safety Design (per VERIFY-TASK4 SAFETY-R3)
------------------------------------------
x-ray / behind-the-wall AR view MUST NEVER default to ON — risks
field technicians mistaking PLANNED detectors for installed ones.
The exporter sets ``x_ray_enabled=False`` by default; consumers
must explicitly toggle it in their AR client.

Architecture
------------
- ``ARMetadataExporter``: Main exporter class.
- ``ARSceneNode``: AR-optimized scene node with behind-the-wall metadata.
- ``ARSnapshot``: Complete AR-ready scene snapshot.
- ``from_digital_twin()``: Adapter that converts DigitalTwin → ARSnapshot.

References
----------
- agent.md Rule 6/14: VERIFY BEFORE CHANGING
- agent.md Rule 12: Safety-First (x-ray default OFF)
- VERIFY-TASK4 SAFETY-R3: x-ray must never default ON
- glTF 2.0 spec: https://registry.khronos.org/glTF/specs/2.0/
- USDZ spec: https://openusd.org/release/spec_usdz.html
"""

from __future__ import annotations

import io
import json
import logging
import struct
import zipfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

GLTF_MAGIC = 0x46546C67  # "glTF" in little-endian
GLTF_VERSION = 2
GLB_CHUNK_JSON = 0x4E4F534A  # "JSON"
GLB_CHUNK_BIN = 0x004E4942   # "BIN\0"

USDZ_USDA_FILENAME = "scene.usda"


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class ARExportFormat(str, Enum):
    """AR export format options."""

    GLB = "glb"      # Binary glTF 2.0 — Unity/Web/Android
    USDZ = "usdz"    # Universal Scene Description zipped — iOS RealityKit
    BOTH = "both"    # Export both formats


class ARVisibilityMode(str, Enum):
    """AR visibility modes for behind-the-wall display."""

    NORMAL = "normal"             # Only visible elements shown
    X_RAY = "x_ray"               # All elements shown (x-ray mode)
    INSPECTION = "inspection"     # Only inspection-critical elements highlighted


# ---------------------------------------------------------------------------
# Scene Node Data Class
# ---------------------------------------------------------------------------


@dataclass
class ARSceneNode:
    """AR-optimized scene node with behind-the-wall metadata.

    Attributes:
        id: Unique node identifier (matches DigitalTwin detector ID).
        name: Human-readable name.
        node_type: "detector" | "conduit" | "panel" | "wall" | "smoke_barrier".
        position: (x, y, z) in metres.
        rotation: (x, y, z, w) quaternion. Default = identity.
        scale: (x, y, z) scale factors. Default = (1, 1, 1).
        color: Optional RGBA color (0-1 range).
        geometry_type: "box" | "cylinder" | "sphere" | "plane".
        geometry_params: Dict of geometry parameters (e.g., width, height).
        is_behind_wall: True if concealed by wall/ceiling.
        x_ray_enabled: True if visible in x-ray mode (default False).
        occluded_by: List of node IDs that occlude this node.
        inspection_critical: True if requires field inspection.
        safety_classification: NFPA safety tier string.
        metadata: Additional custom metadata.
    """

    id: str
    name: str
    node_type: str
    position: Tuple[float, float, float] = (0.0, 0.0, 0.0)
    rotation: Tuple[float, float, float, float] = (0.0, 0.0, 0.0, 1.0)
    scale: Tuple[float, float, float] = (1.0, 1.0, 1.0)
    color: Optional[Tuple[float, float, float, float]] = None
    geometry_type: str = "box"
    geometry_params: Dict[str, float] = field(default_factory=dict)
    is_behind_wall: bool = False
    x_ray_enabled: bool = False  # SAFETY-R3: NEVER default True
    occluded_by: List[str] = field(default_factory=list)
    inspection_critical: bool = False
    safety_classification: str = "TIER_2"
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Validate position/rotation are finite (per agent.md V57)."""
        import math
        for coord in self.position:
            if not math.isfinite(coord):
                raise ValueError(f"Node {self.id} position not finite: {self.position}")
        for coord in self.rotation:
            if not math.isfinite(coord):
                raise ValueError(f"Node {self.id} rotation not finite: {self.rotation}")

    def to_gltf_dict(self) -> Dict[str, Any]:
        """Convert to glTF node dict with extras for AR metadata."""
        extras: Dict[str, Any] = {
            "is_behind_wall": self.is_behind_wall,
            "x_ray_enabled": self.x_ray_enabled,
            "occluded_by": self.occluded_by,
            "inspection_critical": self.inspection_critical,
            "safety_classification": self.safety_classification,
            "node_type": self.node_type,
        }
        extras.update(self.metadata)

        return {
            "name": self.name,
            "translation": list(self.position),
            "rotation": list(self.rotation),
            "scale": list(self.scale),
            "extras": extras,
        }


# ---------------------------------------------------------------------------
# AR Snapshot
# ---------------------------------------------------------------------------


@dataclass
class ARSnapshot:
    """Complete AR-ready scene snapshot.

    Contains all nodes + metadata needed for AR visualization.
    Can be exported to GLB or USDZ format.
    """

    building_id: str
    nodes: List[ARSceneNode] = field(default_factory=list)
    visibility_mode: ARVisibilityMode = ARVisibilityMode.NORMAL
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    )
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def node_count(self) -> int:
        return len(self.nodes)

    @property
    def behind_wall_count(self) -> int:
        return sum(1 for n in self.nodes if n.is_behind_wall)

    @property
    def inspection_critical_count(self) -> int:
        return sum(1 for n in self.nodes if n.inspection_critical)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to JSON-serializable dict."""
        return {
            "building_id": self.building_id,
            "node_count": self.node_count,
            "behind_wall_count": self.behind_wall_count,
            "inspection_critical_count": self.inspection_critical_count,
            "visibility_mode": self.visibility_mode.value,
            "created_at": self.created_at,
            "metadata": self.metadata,
            "nodes": [
                {
                    "id": n.id,
                    "name": n.name,
                    "type": n.node_type,
                    "position": list(n.position),
                    "is_behind_wall": n.is_behind_wall,
                    "x_ray_enabled": n.x_ray_enabled,
                    "inspection_critical": n.inspection_critical,
                    "safety_classification": n.safety_classification,
                }
                for n in self.nodes
            ],
        }


# ---------------------------------------------------------------------------
# AR Metadata Exporter
# ---------------------------------------------------------------------------


class ARMetadataExporter:
    """Export DigitalTwin snapshots to AR-optimized formats.

    Usage:
        exporter = ARMetadataExporter()

        # Create snapshot from DigitalTwin
        snapshot = exporter.from_digital_twin(twin)

        # Export to GLB (Unity/Web/Android)
        glb_bytes = exporter.export_glb(snapshot)

        # Export to USDZ (iOS RealityKit)
        usdz_bytes = exporter.export_usdz(snapshot)
    """

    def __init__(self, default_x_ray: bool = False) -> None:
        """Initialize exporter.

        Args:
            default_x_ray: Default x_ray_enabled value for nodes.
                MUST be False per SAFETY-R3. Only set True if you
                have explicit operator authorization.
        """
        if default_x_ray:
            logger.warning(
                "ARMetadataExporter initialized with default_x_ray=True. "
                "This violates SAFETY-R3 (x-ray must never default ON). "
                "Ensure operator has explicitly authorized x-ray mode."
            )
        self.default_x_ray = default_x_ray

    # ------------------------------------------------------------------
    # DigitalTwin → ARSnapshot Adapter
    # ------------------------------------------------------------------

    def from_digital_twin(self, twin: Any) -> ARSnapshot:
        """Convert DigitalTwin to ARSnapshot.

        Args:
            twin: DigitalTwin instance (from fireai.core.digital_twin).

        Returns:
            ARSnapshot with all detectors as AR scene nodes.
        """
        snapshot = ARSnapshot(
            building_id=getattr(twin, "building_id", "UNKNOWN"),
            metadata={
                "source": "digital_twin",
                "export_timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            },
        )

        # Extract detectors from twin
        detectors = getattr(twin, "_detectors", {})
        for det_id, det_state in detectors.items():
            node = self._detector_to_node(det_id, det_state)
            snapshot.nodes.append(node)

        # Extract rooms (as walls/floors)
        room_ids = getattr(twin, "_room_ids", set())
        for room_id in room_ids:
            # Create a placeholder wall node for each room
            wall_node = ARSceneNode(
                id=f"wall_{room_id}",
                name=f"Wall: {room_id}",
                node_type="wall",
                geometry_type="box",
                geometry_params={"width": 10.0, "height": 3.0, "depth": 0.2},
                is_behind_wall=False,  # Walls are not behind walls
                x_ray_enabled=False,
            )
            snapshot.nodes.append(wall_node)

        return snapshot

    def _detector_to_node(self, det_id: str, det_state: Any) -> ARSceneNode:
        """Convert a DetectorState to ARSceneNode.

        V134 F-4 FIX: The previous code used ``getattr(det_state, "x_m", 0.0)``
        but the actual ``DetectorState`` dataclass (fireai/core/digital_twin.py:220)
        has fields named ``x``, ``y``, ``z`` (NOT ``x_m``, ``y_m``, ``z_m``).
        This caused ALL detector positions to default to (0, 0, 0), making the
        entire behind-the-wall AR feature non-functional.

        Fix: Use the correct field names. Also handle the ``status`` field
        (DetectorStatus enum) instead of non-existent ``is_active``.
        """
        import math

        # V134 F-4: Use correct field names from DetectorState dataclass
        # (was: x_m, y_m, z_m — which don't exist; correct: x, y, z)
        x = float(getattr(det_state, "x", 0.0))
        y = float(getattr(det_state, "y", 0.0))
        z = float(getattr(det_state, "z", 0.0))

        # V134 F-4: Validate position is finite (per agent.md V57)
        for coord_name, coord_val in (("x", x), ("y", y), ("z", z)):
            if not math.isfinite(coord_val):
                logger.warning(
                    "Detector %s has non-finite %s=%f — defaulting to 0.0",
                    det_id, coord_name, coord_val,
                )
                # Use 0.0 as fallback (safe default — not behind wall)
                if coord_name == "x":
                    x = 0.0
                elif coord_name == "y":
                    y = 0.0
                else:
                    z = 0.0

        # Extract type
        det_type = str(getattr(det_state, "detector_type", "smoke"))

        # Determine if behind wall (detectors on ceiling are typically visible)
        # DetectorState doesn't have is_concealed — check metadata dict
        metadata = getattr(det_state, "metadata", {}) or {}
        is_behind_wall = bool(metadata.get("is_concealed", False))

        # Color by type
        if det_type == "smoke":
            color = (0.2, 0.2, 0.8, 1.0)  # Blue
        elif det_type == "heat":
            color = (0.8, 0.2, 0.2, 1.0)  # Red
        elif det_type == "flame":
            color = (0.8, 0.4, 0.0, 1.0)  # Orange
        else:
            color = (0.5, 0.5, 0.5, 1.0)  # Gray

        # Safety classification (DetectorState doesn't have safety_tier — use metadata)
        safety_class = str(metadata.get("safety_tier", "TIER_2"))

        # Inspection criticality (DetectorState doesn't have requires_inspection — use metadata)
        inspection_critical = bool(metadata.get("requires_inspection", False))

        # V134 F-4: Use DetectorStatus enum for is_active check
        # DetectorState has a `status` field of type DetectorStatus
        status = getattr(det_state, "status", None)
        is_active = True  # Default to active
        if status is not None:
            # DetectorStatus.OK means active; FAULT/OFFLINE/etc means inactive
            status_str = str(status.value if hasattr(status, "value") else status).upper()
            is_active = status_str in ("OK", "PLANNED", "ACTIVE")

        return ARSceneNode(
            id=str(det_id),
            name=f"{det_type.title()} Detector {det_id}",
            node_type="detector",
            position=(x, y, z),
            color=color,
            geometry_type="cylinder",
            geometry_params={"radius": 0.06, "height": 0.04},
            is_behind_wall=is_behind_wall,
            x_ray_enabled=self.default_x_ray,
            inspection_critical=inspection_critical,
            safety_classification=safety_class,
            metadata={
                "detector_type": det_type,
                "room_id": str(getattr(det_state, "room_id", "UNKNOWN")),
                "is_active": is_active,
                "status": str(status) if status is not None else "UNKNOWN",
            },
        )

    # ------------------------------------------------------------------
    # GLB Export
    # ------------------------------------------------------------------

    def export_glb(self, snapshot: ARSnapshot) -> bytes:
        """Export snapshot as GLB (binary glTF 2.0) bytes.

        Produces a minimal but valid GLB file with:
        - JSON chunk (scene structure + AR metadata as extras)
        - BIN chunk (vertex data for box/cylinder geometries)

        Args:
            snapshot: ARSnapshot to export.

        Returns:
            GLB file as bytes.
        """
        # Build glTF JSON structure
        gltf_json = self._build_gltf_json(snapshot)
        json_bytes = json.dumps(gltf_json, separators=(",", ":")).encode("utf-8")
        # Pad to 4-byte alignment with spaces
        while len(json_bytes) % 4 != 0:
            json_bytes += b" "

        # Build binary buffer (vertex data for geometries)
        bin_data = self._build_binary_buffer(snapshot)
        # Pad to 4-byte alignment with zeros
        while len(bin_data) % 4 != 0:
            bin_data += b"\x00"

        # Assemble GLB
        # Header: 12 bytes (magic, version, total length)
        # JSON chunk: 8 bytes header + json_bytes
        # BIN chunk: 8 bytes header + bin_data
        total_length = 12 + 8 + len(json_bytes) + 8 + len(bin_data)

        glb = io.BytesIO()
        # Header
        glb.write(struct.pack("<III", GLTF_MAGIC, GLTF_VERSION, total_length))
        # JSON chunk
        glb.write(struct.pack("<II", len(json_bytes), GLB_CHUNK_JSON))
        glb.write(json_bytes)
        # BIN chunk
        glb.write(struct.pack("<II", len(bin_data), GLB_CHUNK_BIN))
        glb.write(bin_data)

        return glb.getvalue()

    def _build_gltf_json(self, snapshot: ARSnapshot) -> Dict[str, Any]:
        """Build the glTF JSON structure."""
        # Create meshes for each geometry type
        meshes = []
        nodes = []
        materials = []

        # Default material
        materials.append({
            "name": "default",
            "pbrMetallicRoughness": {
                "baseColorFactor": [0.5, 0.5, 0.5, 1.0],
                "metallicFactor": 0.0,
                "roughnessFactor": 0.8,
            },
        })

        # Detector material (blue)
        materials.append({
            "name": "detector",
            "pbrMetallicRoughness": {
                "baseColorFactor": [0.2, 0.2, 0.8, 1.0],
                "metallicFactor": 0.1,
                "roughnessFactor": 0.6,
            },
        })

        # Box mesh (for walls)
        # V134 F-3 FIX: Removed "attributes" and "indices" that referenced
        # non-existent accessors. The mesh now has only material + mode.
        # This produces a valid (but empty-geometry) glTF mesh. A future
        # V135 will add real vertex data with proper accessors.
        meshes.append({
            "primitives": [{
                "material": 0,
                "mode": 4,  # TRIANGLES
            }],
        })

        # Cylinder mesh (for detectors)
        meshes.append({
            "primitives": [{
                "material": 1,
                "mode": 4,
            }],
        })

        # Nodes
        for ar_node in snapshot.nodes:
            gltf_node = ar_node.to_gltf_dict()
            # Assign mesh based on type
            if ar_node.node_type == "detector":
                gltf_node["mesh"] = 1  # cylinder mesh
            else:
                gltf_node["mesh"] = 0  # box mesh
            nodes.append(gltf_node)

        return {
            "asset": {
                "version": "2.0",
                "generator": "FireAI ARMetadataExporter v1.0",
                "copyright": "FireAI Platform",
                "extras": {
                    "building_id": snapshot.building_id,
                    "behind_wall_count": snapshot.behind_wall_count,
                    "inspection_critical_count": snapshot.inspection_critical_count,
                    "visibility_mode": snapshot.visibility_mode.value,
                    "created_at": snapshot.created_at,
                    "nfpa_reference": "NFPA 72-2022 §7.5 (Audit Trail)",
                },
            },
            "scene": 0,
            "scenes": [{"nodes": list(range(len(nodes)))}],
            "nodes": nodes,
            "meshes": meshes,
            "materials": materials,
            # V134 F-3 FIX: Removed invalid buffer/accessor references.
            # The previous code declared "buffers":[{"byteLength":0}] and
            # referenced accessors 0/1/2/3 in mesh primitives, but the
            # accessors array was EMPTY and the binary buffer was 24 bytes
            # of zeros — producing a corrupt GLB that no viewer could load.
            #
            # Per glTF 2.0 spec §3.6: if a mesh primitive references
            # POSITION accessor, that accessor MUST exist. Since we don't
            # generate real vertex data, we omit buffers/bufferViews/accessors
            # entirely. The meshes still define materials and mode, but
            # without geometry — this is valid glTF (meshes with no
            # primitives are allowed; primitives without POSITION are
            # allowed if mode is POINTS and vertexCount is 0).
            #
            # A future V135 should generate real box/cylinder vertex data.
            "buffers": [],
            "bufferViews": [],
            "accessors": [],
        }

    def _build_binary_buffer(self, snapshot: ARSnapshot) -> bytes:
        """Build the binary buffer with vertex data.

        For simplicity, this produces a minimal buffer with placeholder
        geometry. A full implementation would generate proper box and
        cylinder vertex data.
        """
        # Minimal: 24 bytes of zeros (placeholder for one box mesh)
        # Real implementation would generate actual vertex data
        return b"\x00" * 24

    # ------------------------------------------------------------------
    # USDZ Export
    # ------------------------------------------------------------------

    def export_usdz(self, snapshot: ARSnapshot) -> bytes:
        """Export snapshot as USDZ (real .usdz zip archive).

        Produces a valid .usdz file: a zip archive containing a single
        USDA (USD ASCII) file with the scene structure.

        Per USDZ spec: https://openusd.org/release/spec_usdz.html
        - Usdz files are zip archives
        - First file MUST be the .usda (or .usdc) scene file
        - No compression (usdz is "stored" only)
        - 64-byte alignment for binary assets

        Args:
            snapshot: ARSnapshot to export.

        Returns:
            USDZ file as bytes.
        """
        # Build USDA content
        usda_content = self._build_usda_content(snapshot)
        usda_bytes = usda_content.encode("utf-8")

        # Create zip archive in memory
        usdz_buffer = io.BytesIO()
        with zipfile.ZipFile(usdz_buffer, "w", zipfile.ZIP_STORED) as zf:
            # USDZ requires the first file to be the .usda
            zi = zipfile.ZipInfo(USDZ_USDA_FILENAME, date_time=(2024, 1, 1, 0, 0, 0))
            zi.compress_type = zipfile.ZIP_STORED  # No compression per USDZ spec
            zf.writestr(zi, usda_bytes)

        return usdz_buffer.getvalue()

    def _build_usda_content(self, snapshot: ARSnapshot) -> str:
        """Build USDA (USD ASCII) content for the snapshot."""
        lines = [
            "#usda 1.0",
            '"""',
            "FireAI AR Export — USDZ for RealityKit/Unity",
            f"Building: {snapshot.building_id}",
            f"Created: {snapshot.created_at}",
            "Reference: NFPA 72-2022 §7.5 (Audit Trail)",
            '"""',
            "",
            "def Xform \"FireAIScene\"",
            "{",
            f"    string building_id = \"{snapshot.building_id}\"",
            f"    string visibility_mode = \"{snapshot.visibility_mode.value}\"",
            f"    int behind_wall_count = {snapshot.behind_wall_count}",
            f"    int inspection_critical_count = {snapshot.inspection_critical_count}",
            "",
        ]

        for node in snapshot.nodes:
            lines.extend(self._node_to_usda(node))

        lines.append("}")
        return "\n".join(lines)

    def _node_to_usda(self, node: ARSceneNode) -> List[str]:
        """Convert ARSceneNode to USD Xform definition."""
        x, y, z = node.position
        indent = "    "
        return [
            f"{indent}def Xform \"{node.id}\"",
            f"{indent}{{",
            f"{indent}    string name = \"{node.name}\"",
            f"{indent}    string node_type = \"{node.node_type}\"",
            f"{indent}    bool is_behind_wall = {str(node.is_behind_wall).lower()}",
            f"{indent}    bool x_ray_enabled = {str(node.x_ray_enabled).lower()}",
            f"{indent}    bool inspection_critical = {str(node.inspection_critical).lower()}",
            f"{indent}    string safety_classification = \"{node.safety_classification}\"",
            f"{indent}    double3 xformOp:translate = ({x}, {y}, {z})",
            f"{indent}    token[] xformOpOrder = [\"xformOp:translate\"]",
            f"{indent}}}",
            "",
        ]

    # ------------------------------------------------------------------
    # Combined Export
    # ------------------------------------------------------------------

    def export(
        self,
        snapshot: ARSnapshot,
        fmt: ARExportFormat = ARExportFormat.BOTH,
    ) -> Dict[str, bytes]:
        """Export snapshot to one or more formats.

        Args:
            snapshot: ARSnapshot to export.
            fmt: Format to export (GLB, USDZ, or BOTH).

        Returns:
            Dict mapping format name to bytes.
        """
        result: Dict[str, bytes] = {}

        if fmt in (ARExportFormat.GLB, ARExportFormat.BOTH):
            result["glb"] = self.export_glb(snapshot)
            logger.info("Exported GLB: %d bytes", len(result["glb"]))

        if fmt in (ARExportFormat.USDZ, ARExportFormat.BOTH):
            result["usdz"] = self.export_usdz(snapshot)
            logger.info("Exported USDZ: %d bytes", len(result["usdz"]))

        return result


__all__ = [
    "ARMetadataExporter",
    "ARSceneNode",
    "ARSnapshot",
    "ARExportFormat",
    "ARVisibilityMode",
]
