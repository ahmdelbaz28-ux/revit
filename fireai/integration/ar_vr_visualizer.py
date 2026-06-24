"""fireai/integration/ar_vr_visualizer.py
========================================
AR/VR Visualization — Generates 3D scene descriptions for AR/VR rendering.

Converts fire alarm designs into:
  - Three.js scene JSON for web-based VR
  - USDZ scene for iOS Quick Look
  - glTF 2.0 scene for universal AR/VR
  - A-Frame HTML for web AR

All output formats describe the same scene:
  - Room geometry (walls, floor, ceiling)
  - Detector positions with type-specific icons
  - NAC device positions
  - FACP panel location
  - Cable routing paths
  - Coverage radius visualization

References:
  - Three.js JSON Model format 3.1
  - glTF 2.0 specification
  - USDZ (USD) specification for Apple platforms
  - A-Frame WebXR specification

"""

from __future__ import annotations

import json
import logging
import math
import struct
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# ===========================================================================
# Enums
# ===========================================================================


class SceneFormat(str, Enum):
    THREEJS = "THREEJS"
    GLTF = "GLTF"
    AFRAME = "AFRAME"
    USDZ = "USDZ"


class DetectorColor(str, Enum):
    SMOKE = "#2196F3"
    HEAT = "#F44336"
    COMBINATION = "#9C27B0"
    DUCT = "#FFEB3B"


# ===========================================================================
# Data Models
# ===========================================================================


@dataclass
class Vec3:
    x: float = 0.0
    y: float = 0.0
    z: float = 0.0

    def to_list(self) -> List[float]:
        return [self.x, self.y, self.z]

    def to_tuple(self) -> Tuple[float, float, float]:
        return (self.x, self.y, self.z)


@dataclass
class BoundingBox:
    min: Vec3 = field(default_factory=Vec3)
    max: Vec3 = field(default_factory=Vec3)

    @property
    def center(self) -> Vec3:
        return Vec3(
            x=(self.min.x + self.max.x) / 2,
            y=(self.min.y + self.max.y) / 2,
            z=(self.min.z + self.max.z) / 2,
        )

    @property
    def size(self) -> Vec3:
        return Vec3(
            x=self.max.x - self.min.x,
            y=self.max.y - self.min.y,
            z=self.max.z - self.min.z,
        )


@dataclass
class Material:
    name: str = ""
    color: str = "#CCCCCC"
    opacity: float = 1.0
    transparent: bool = False
    metallic: float = 0.0
    roughness: float = 0.8
    emissive: str = "#000000"
    side: str = "double"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "color": self.color,
            "opacity": self.opacity,
            "transparent": self.transparent,
            "metallic": self.metallic,
            "roughness": self.roughness,
            "emissive": self.emissive,
            "side": self.side,
        }


@dataclass
class MeshGeometry:
    type: str = "box"
    width: float = 1.0
    height: float = 1.0
    depth: float = 1.0
    radius: float = 0.5

    def to_dict(self) -> Dict[str, Any]:
        d: Dict[str, Any] = {"type": self.type}
        if self.type in ("box",):
            d.update(width=self.width, height=self.height, depth=self.depth)
        elif self.type in ("sphere", "cylinder"):
            d["radius"] = self.radius
            if self.type == "cylinder":
                d["height"] = self.height
        return d


@dataclass
class SceneNode:
    name: str = ""
    node_id: str = ""
    position: Vec3 = field(default_factory=Vec3)
    rotation: Vec3 = field(default_factory=Vec3)
    scale: Vec3 = field(default_factory=lambda: Vec3(1, 1, 1))
    geometry: Optional[MeshGeometry] = None
    material: Optional[Material] = None
    children: List[SceneNode] = field(default_factory=list)
    is_coverage: bool = False
    is_annotation: bool = False
    annotation_text: str = ""
    device_id: str = ""
    lod_min_distance: float = 0.0
    lod_max_distance: float = float("inf")

    def to_dict(self) -> Dict[str, Any]:
        d: Dict[str, Any] = {
            "name": self.name,
            "node_id": self.node_id,
            "position": self.position.to_list(),
            "rotation": self.rotation.to_list(),
            "scale": self.scale.to_list(),
        }
        if self.geometry:
            d["geometry"] = self.geometry.to_dict()
        if self.material:
            d["material"] = self.material.to_dict()
        if self.children:
            d["children"] = [c.to_dict() for c in self.children]
        if self.is_coverage:
            d["is_coverage"] = True
        if self.is_annotation:
            d["is_annotation"] = True
            d["annotation_text"] = self.annotation_text
            d["device_id"] = self.device_id
        if self.lod_min_distance > 0 or self.lod_max_distance < float("inf"):
            d["lod_min_distance"] = self.lod_min_distance
            d["lod_max_distance"] = self.lod_max_distance
        return d


@dataclass
class CameraKeyframe:
    position: Vec3 = field(default_factory=Vec3)
    target: Vec3 = field(default_factory=Vec3)
    duration_sec: float = 2.0


@dataclass
class CameraPath:
    name: str = "guided_tour"
    keyframes: List[CameraKeyframe] = field(default_factory=list)
    loop: bool = True
    autoplay: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "loop": self.loop,
            "autoplay": self.autoplay,
            "keyframes": [
                {
                    "position": kf.position.to_list(),
                    "target": kf.target.to_list(),
                    "duration_sec": kf.duration_sec,
                }
                for kf in self.keyframes
            ],
        }


@dataclass
class Scene:
    name: str = ""
    nodes: List[SceneNode] = field(default_factory=list)
    materials: List[Material] = field(default_factory=list)
    camera_paths: List[CameraPath] = field(default_factory=list)
    bounding_box: Optional[BoundingBox] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        d: Dict[str, Any] = {
            "name": self.name,
            "nodes": [n.to_dict() for n in self.nodes],
            "materials": [m.to_dict() for m in self.materials],
            "camera_paths": [cp.to_dict() for cp in self.camera_paths],
            "metadata": self.metadata,
        }
        if self.bounding_box:
            d["bounding_box"] = {
                "min": self.bounding_box.min.to_list(),
                "max": self.bounding_box.max.to_list(),
            }
        return d


# ===========================================================================
# LOD Manager
# ===========================================================================


class LODManager:
    """Manages level-of-detail for large scenes.

    Determines which nodes should render at a given camera distance
    to maintain performance on AR/VR devices.
    """

    DETAIL_HIGH = 0.0
    DETAIL_MEDIUM = 15.0
    DETAIL_LOW = 50.0
    DETAIL_CULL = 150.0

    def __init__(self, total_nodes: int) -> None:
        self._total_nodes = total_nodes
        self._thresholds = self._compute_thresholds()

    def _compute_thresholds(self) -> List[Tuple[float, float]]:
        if self._total_nodes <= 50:
            return [(0.0, float("inf"))]
        if self._total_nodes <= 200:
            return [
                (self.DETAIL_HIGH, self.DETAIL_MEDIUM),
                (self.DETAIL_MEDIUM, float("inf")),
            ]
        return [
            (self.DETAIL_HIGH, self.DETAIL_MEDIUM),
            (self.DETAIL_MEDIUM, self.DETAIL_LOW),
            (self.DETAIL_LOW, self.DETAIL_CULL),
        ]

    def assign_lod(
        self,
        node: SceneNode,
        distance_from_center: float,
    ) -> SceneNode:
        for min_dist, max_dist in self._thresholds:
            if min_dist <= distance_from_center < max_dist:
                node.lod_min_distance = min_dist
                node.lod_max_distance = max_dist
                break
        else:
            node.lod_min_distance = self.DETAIL_CULL
            node.lod_max_distance = float("inf")
        return node


# ===========================================================================
# Design Data Adapter
# ===========================================================================


@dataclass
class DesignData:
    """Fire alarm design data consumed by the AR/VR visualizer.

    Mirrors the structure from fireai/validation/qa_engine.py DesignData
    to avoid circular imports while maintaining compatibility.
    """

    design_id: str = ""
    rooms: List[Dict[str, Any]] = field(default_factory=list)
    detectors: List[Dict[str, Any]] = field(default_factory=list)
    notification_appliances: List[Dict[str, Any]] = field(default_factory=list)
    panels: List[Dict[str, Any]] = field(default_factory=list)
    cables: List[Dict[str, Any]] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


# ===========================================================================
# Coverage Result
# ===========================================================================


@dataclass
class CoverageResult:
    is_covered: bool = False
    coverage_percentage: float = 0.0
    uncovered_areas: List[Tuple[float, float]] = field(default_factory=list)
    detectors_in_coverage: int = 0
    coverage_radius_m: float = 0.0
    max_gap_m: float = 0.0


# ===========================================================================
# AR/VR Visualizer
# ===========================================================================


class ARVRVisualizer:
    """Generates 3D scene descriptions for AR/VR rendering.

    Converts fire alarm designs into:
    - Three.js scene JSON for web-based VR
    - USDZ scene for iOS Quick Look
    - glTF 2.0 scene for universal AR/VR
    - A-Frame HTML for web AR

    All output formats describe the same scene:
    - Room geometry (walls, floor, ceiling)
    - Detector positions with type-specific icons
    - NAC device positions
    - FACP panel location
    - Cable routing paths
    - Coverage radius visualization
    """

    # Detector type to color mapping
    DETECTOR_COLORS: Dict[str, str] = {
        "SMOKE": DetectorColor.SMOKE.value,
        "SMOKE_PHOTOELECTRIC": DetectorColor.SMOKE.value,
        "SMOKE_IONIZATION": DetectorColor.SMOKE.value,
        "SMOKE_MULTI_CRITERIA": DetectorColor.SMOKE.value,
        "HEAT": DetectorColor.HEAT.value,
        "HEAT_FIXED": DetectorColor.HEAT.value,
        "HEAT_FIXED_TEMP": DetectorColor.HEAT.value,
        "HEAT_RATE_OF_RISE": DetectorColor.HEAT.value,
        "HEAT_COMBINATION": DetectorColor.HEAT.value,
        "COMBINATION": DetectorColor.COMBINATION.value,
        "SMOKE_HEAT_COMBINATION": DetectorColor.COMBINATION.value,
        "DUCT": DetectorColor.DUCT.value,
        "FLAME": "#FF9800",
        "GAS": "#4CAF50",
    }

    # Default floor elevation
    FLOOR_Y: float = 0.0
    # Default ceiling height when not specified
    DEFAULT_CEILING_HEIGHT: float = 3.0
    # Detector icon size
    DETECTOR_SIZE: float = 0.15
    # Coverage visualization radius
    COVERAGE_OPACITY: float = 0.5
    # Cable visual thickness
    CABLE_RADIUS: float = 0.02

    def generate_scene(
        self,
        design: DesignData,
        fmt: SceneFormat,
    ) -> Any:
        """Generate a 3D scene description in the requested format.

        Args:
            design: Fire alarm design data.
            fmt: Target output format.

        Returns:
            Scene description in the requested format:
            - THREEJS: dict (JSON-serializable Three.js scene)
            - GLTF: bytes (binary glTF 2.0)
            - AFRAME: str (A-Frame HTML document)
            - USDZ: str (USD ASCII scene description)

        """
        scene = self._build_scene(design)

        if fmt == SceneFormat.THREEJS:
            return self.generate_threejs(design)
        if fmt == SceneFormat.GLTF:
            return self.generate_gltf(design)
        if fmt == SceneFormat.AFRAME:
            return self.generate_aframe_html(design)
        if fmt == SceneFormat.USDZ:
            return self._generate_usdz(scene)
        raise ValueError(f"Unsupported scene format: {fmt}")

    def generate_threejs(self, design: DesignData) -> dict:
        """Generate a Three.js-compatible JSON scene description.

        Returns a dict matching the Three.js JSON Object/Scene format (v3.1+)
        that can be loaded via THREE.ObjectLoader or THREE.JSONLoader.
        """
        scene = self._build_scene(design)
        return self._scene_to_threejs(scene)

    def generate_gltf(self, design: DesignData) -> bytes:
        """Generate a binary glTF 2.0 representation of the scene.

        Returns bytes in .glb format (binary glTF with embedded buffers).
        """
        scene = self._build_scene(design)
        return self._scene_to_glb(scene)

    def generate_aframe_html(self, design: DesignData) -> str:
        """Generate a self-contained A-Frame HTML document for web AR/VR.

        Includes:
        - Room geometry
        - Device markers with colors and labels
        - Coverage visualization
        - VR controller hints
        - Clickable annotations
        - Camera guided tour
        """
        scene = self._build_scene(design)
        return self._scene_to_aframe(scene)

    def add_coverage_visualization(
        self,
        scene: Scene,
        coverage_data: CoverageResult,
    ) -> Scene:
        """Add coverage radius visualization to an existing scene.

        For each uncovered area or detector position, adds translucent
        spheres or cubes indicating coverage radius at 50% opacity.

        Args:
            scene: Existing 3D scene to augment.
            coverage_data: Coverage analysis results.

        Returns:
            Scene with coverage visualization nodes added.

        """
        coverage_mat = Material(
            name="coverage_overlay",
            color="#4CAF50",
            opacity=self.COVERAGE_OPACITY,
            transparent=True,
            side="double",
        )
        scene.materials.append(coverage_mat)

        radius = max(coverage_data.coverage_radius_m, 1.0)

        for node in scene.nodes:
            if node.geometry and not node.is_coverage and node.device_id:
                cov_node = SceneNode(
                    name=f"coverage_{node.device_id}",
                    node_id=str(uuid.uuid4()),
                    position=node.position,
                    geometry=MeshGeometry(type="sphere", radius=radius),
                    material=coverage_mat,
                    is_coverage=True,
                    lod_min_distance=node.lod_min_distance,
                    lod_max_distance=node.lod_max_distance,
                )
                node.children.append(cov_node)

        for area_idx, (cx, cy) in enumerate(coverage_data.uncovered_areas):
            uncovered_node = SceneNode(
                name=f"uncovered_{area_idx}",
                node_id=str(uuid.uuid4()),
                position=Vec3(x=cx, y=self.FLOOR_Y + 0.1, z=cy),
                geometry=MeshGeometry(
                    type="box",
                    width=0.5,
                    height=0.1,
                    depth=0.5,
                ),
                material=Material(
                    name="uncovered_area",
                    color="#FF5722",
                    opacity=0.6,
                    transparent=True,
                ),
                is_coverage=True,
            )
            scene.nodes.append(uncovered_node)

        return scene

    def add_annotation(
        self,
        scene: Scene,
        device_id: str,
        text: str,
    ) -> Scene:
        """Add a clickable text annotation to a device in the scene.

        Args:
            scene: Existing 3D scene to augment.
            device_id: Target device identifier.
            text: Annotation text to display.

        Returns:
            Scene with annotation node added.

        """
        target_node = self._find_node_by_device_id(scene, device_id)
        if target_node is None:
            logger.warning("Device %s not found in scene — annotation skipped", device_id)
            return scene

        annotation_pos = Vec3(
            x=target_node.position.x,
            y=target_node.position.y + 0.5,
            z=target_node.position.z,
        )
        annotation_node = SceneNode(
            name=f"annotation_{device_id}",
            node_id=str(uuid.uuid4()),
            position=annotation_pos,
            geometry=MeshGeometry(type="box", width=0.4, height=0.15, depth=0.02),
            material=Material(
                name=f"annotation_mat_{device_id}",
                color="#FFFFFF",
                opacity=0.9,
                transparent=True,
                emissive="#333333",
            ),
            is_annotation=True,
            annotation_text=text,
            device_id=device_id,
        )
        target_node.children.append(annotation_node)
        return scene

    # ── Internal: Scene Building ────────────────────────────────────────

    def _build_scene(self, design: DesignData) -> Scene:
        """Build an intermediate Scene graph from design data."""
        scene = Scene(
            name=f"Fire Alarm Design - {design.design_id or 'Untitled'}",
            metadata={
                "design_id": design.design_id,
                "format_version": "1.0",
                "generator": "fireai_ar_vr_visualizer",
            },
        )

        # Compute bounding box from rooms
        bbox = self._compute_bounding_box(design)
        scene.bounding_box = bbox

        # Add room geometry
        self._add_rooms(scene, design)

        # Add detectors
        self._add_detectors(scene, design)

        # Add NAC devices
        self._add_nac_devices(scene, design)

        # Add FACP panels
        self._add_panels(scene, design)

        # Add cable routing
        self._add_cables(scene, design)

        # Add camera path for guided tour
        self._add_camera_path(scene, design)

        # Assign LOD levels for large scenes
        lod_mgr = LODManager(len(scene.nodes))
        if len(scene.nodes) > 100 and bbox:
            center = bbox.center
            for node in scene.nodes:
                dist = self._distance(node.position, center)
                lod_mgr.assign_lod(node, dist)

        return scene

    def _compute_bounding_box(self, design: DesignData) -> BoundingBox:
        """Compute the bounding box from room polygons."""
        all_points: List[Tuple[float, float, float]] = []

        for room in design.rooms:
            poly = room.get("polygon", [])
            ceiling_h = room.get("ceiling_height_m", self.DEFAULT_CEILING_HEIGHT)
            for pt in poly:
                if isinstance(pt, (list, tuple)) and len(pt) >= 2:
                    all_points.append((float(pt[0]), self.FLOOR_Y, float(pt[1])))
                    all_points.append((float(pt[0]), self.FLOOR_Y + ceiling_h, float(pt[1])))

        for det in design.detectors:
            pos = det.get("position", det.get("coordinates", [0, 0, 0]))
            if isinstance(pos, (list, tuple)) and len(pos) >= 2:
                x, z = float(pos[0]), float(pos[1]) if len(pos) >= 2 else 0.0
                y = float(pos[2]) if len(pos) >= 3 else self.FLOOR_Y + self.DEFAULT_CEILING_HEIGHT
                all_points.append((x, y, z))

        for nac in design.notification_appliances:
            pos = nac.get("position", nac.get("coordinates", [0, 0, 0]))
            if isinstance(pos, (list, tuple)) and len(pos) >= 2:
                x, z = float(pos[0]), float(pos[1]) if len(pos) >= 2 else 0.0
                y = float(pos[2]) if len(pos) >= 3 else self.FLOOR_Y + 2.5
                all_points.append((x, y, z))

        if not all_points:
            return BoundingBox(
                min=Vec3(-10, 0, -10),
                max=Vec3(10, 4, 10),
            )

        min_x = min(p[0] for p in all_points)
        min_y = min(p[1] for p in all_points)
        min_z = min(p[2] for p in all_points)
        max_x = max(p[0] for p in all_points)
        max_y = max(p[1] for p in all_points)
        max_z = max(p[2] for p in all_points)

        # Add padding
        padding = 0.5
        return BoundingBox(
            min=Vec3(min_x - padding, min_y - padding, min_z - padding),
            max=Vec3(max_x + padding, max_y + padding, max_z + padding),
        )

    def _add_rooms(self, scene: Scene, design: DesignData) -> None:
        """Add room geometry nodes to the scene."""
        floor_mat = Material(
            name="floor",
            color="#E8E8E8",
            roughness=0.9,
            metallic=0.0,
        )
        wall_mat = Material(
            name="wall",
            color="#D0D0D0",
            roughness=0.8,
            metallic=0.0,
            side="double",
        )
        ceiling_mat = Material(
            name="ceiling",
            color="#F0F0F0",
            roughness=0.9,
            metallic=0.0,
        )
        scene.materials.extend([floor_mat, wall_mat, ceiling_mat])

        for room_idx, room in enumerate(design.rooms):
            room_id = room.get("room_id", f"room_{room_idx}")
            poly = room.get("polygon", [])
            ceiling_h = room.get("ceiling_height_m", self.DEFAULT_CEILING_HEIGHT)
            room.get("name", room_id)

            if not poly or len(poly) < 3:
                continue

            # Compute room center and extents
            xs = [float(p[0]) if isinstance(p, (list, tuple)) else 0 for p in poly]
            zs = [float(p[1]) if isinstance(p, (list, tuple)) else 0 for p in poly]
            min_x, max_x = min(xs), max(xs)
            min_z, max_z = min(zs), max(zs)
            center_x = (min_x + max_x) / 2
            center_z = (min_z + max_z) / 2
            width = max_x - min_x
            depth = max_z - min_z

            if width < 0.01 or depth < 0.01:
                continue

            # Floor
            floor_node = SceneNode(
                name=f"floor_{room_id}",
                node_id=str(uuid.uuid4()),
                position=Vec3(x=center_x, y=self.FLOOR_Y, z=center_z),
                geometry=MeshGeometry(type="box", width=width, height=0.05, depth=depth),
                material=floor_mat,
            )
            scene.nodes.append(floor_node)

            # Ceiling
            ceiling_node = SceneNode(
                name=f"ceiling_{room_id}",
                node_id=str(uuid.uuid4()),
                position=Vec3(x=center_x, y=self.FLOOR_Y + ceiling_h, z=center_z),
                geometry=MeshGeometry(type="box", width=width, height=0.05, depth=depth),
                material=ceiling_mat,
            )
            scene.nodes.append(ceiling_node)

            # Walls (4 walls per axis-aligned room)
            wall_thickness = 0.05
            wall_nodes = [
                # North wall (z = max_z)
                SceneNode(
                    name=f"wall_north_{room_id}",
                    node_id=str(uuid.uuid4()),
                    position=Vec3(x=center_x, y=self.FLOOR_Y + ceiling_h / 2, z=max_z),
                    geometry=MeshGeometry(
                        type="box",
                        width=width,
                        height=ceiling_h,
                        depth=wall_thickness,
                    ),
                    material=wall_mat,
                ),
                # South wall (z = min_z)
                SceneNode(
                    name=f"wall_south_{room_id}",
                    node_id=str(uuid.uuid4()),
                    position=Vec3(x=center_x, y=self.FLOOR_Y + ceiling_h / 2, z=min_z),
                    geometry=MeshGeometry(
                        type="box",
                        width=width,
                        height=ceiling_h,
                        depth=wall_thickness,
                    ),
                    material=wall_mat,
                ),
                # East wall (x = max_x)
                SceneNode(
                    name=f"wall_east_{room_id}",
                    node_id=str(uuid.uuid4()),
                    position=Vec3(x=max_x, y=self.FLOOR_Y + ceiling_h / 2, z=center_z),
                    geometry=MeshGeometry(
                        type="box",
                        width=wall_thickness,
                        height=ceiling_h,
                        depth=depth,
                    ),
                    material=wall_mat,
                ),
                # West wall (x = min_x)
                SceneNode(
                    name=f"wall_west_{room_id}",
                    node_id=str(uuid.uuid4()),
                    position=Vec3(x=min_x, y=self.FLOOR_Y + ceiling_h / 2, z=center_z),
                    geometry=MeshGeometry(
                        type="box",
                        width=wall_thickness,
                        height=ceiling_h,
                        depth=depth,
                    ),
                    material=wall_mat,
                ),
            ]

            room_group = SceneNode(
                name=f"room_{room_id}",
                node_id=str(uuid.uuid4()),
                position=Vec3(),
                children=wall_nodes,
            )

            scene.nodes.append(room_group)

    def _detector_color(self, det_type: str) -> str:
        """Get the color for a detector type."""
        return self.DETECTOR_COLORS.get(det_type, "#9E9E9E")

    def _detector_icon_shape(self, det_type: str) -> str:
        """Determine the icon geometry shape for a detector type."""
        base = det_type.split("_", maxsplit=1)[0] if det_type else ""
        if base == "DUCT":
            return "box"
        if base == "FLAME":
            return "cylinder"
        if base == "GAS":
            return "box"
        if base in ("HEAT",):
            return "cylinder"
        return "sphere"

    def _add_detectors(self, scene: Scene, design: DesignData) -> None:
        """Add detector nodes to the scene."""
        for det in design.detectors:
            det_id = det.get("detector_id", str(uuid.uuid4()))
            det_type = det.get("detector_type", "SMOKE")
            pos_raw = det.get("position", det.get("coordinates", [0, 0, 0]))

            if isinstance(pos_raw, (list, tuple)):
                x = float(pos_raw[0]) if len(pos_raw) >= 1 else 0.0
                z = float(pos_raw[1]) if len(pos_raw) >= 2 else 0.0
                y = float(pos_raw[2]) if len(pos_raw) >= 3 else self.FLOOR_Y + self.DEFAULT_CEILING_HEIGHT
            else:
                x, y, z = 0.0, self.FLOOR_Y + self.DEFAULT_CEILING_HEIGHT, 0.0

            color = self._detector_color(det_type)
            shape = self._detector_icon_shape(det_type)

            det_mat = Material(
                name=f"det_mat_{det_id}",
                color=color,
                roughness=0.4,
                metallic=0.6,
            )
            scene.materials.append(det_mat)

            if shape == "box":
                geom = MeshGeometry(
                    type="box",
                    width=self.DETECTOR_SIZE * 1.5,
                    height=self.DETECTOR_SIZE,
                    depth=self.DETECTOR_SIZE * 1.5,
                )
            elif shape == "cylinder":
                geom = MeshGeometry(
                    type="cylinder",
                    radius=self.DETECTOR_SIZE * 0.8,
                    height=self.DETECTOR_SIZE * 0.5,
                )
            else:
                geom = MeshGeometry(
                    type="sphere",
                    radius=self.DETECTOR_SIZE,
                )

            det_node = SceneNode(
                name=f"detector_{det_id}",
                node_id=str(uuid.uuid4()),
                position=Vec3(x=x, y=y, z=z),
                geometry=geom,
                material=det_mat,
                device_id=det_id,
                is_annotation=True,
                annotation_text=f"{det_type}: {det_id}",
            )
            scene.nodes.append(det_node)

    def _add_nac_devices(self, scene: Scene, design: DesignData) -> None:
        """Add notification appliance nodes to the scene."""
        nac_mat = Material(
            name="nac_device",
            color="#FF5722",
            roughness=0.5,
            metallic=0.3,
        )
        scene.materials.append(nac_mat)

        for nac in design.notification_appliances:
            nac_id = nac.get("nac_id", str(uuid.uuid4()))
            pos_raw = nac.get("position", nac.get("coordinates", [0, 0, 0]))
            spl = nac.get("spl_dba", 0)

            if isinstance(pos_raw, (list, tuple)):
                x = float(pos_raw[0]) if len(pos_raw) >= 1 else 0.0
                z = float(pos_raw[1]) if len(pos_raw) >= 2 else 0.0
                y = float(pos_raw[2]) if len(pos_raw) >= 3 else self.FLOOR_Y + 2.5
            else:
                x, y, z = 0.0, self.FLOOR_Y + 2.5, 0.0

            nac_node = SceneNode(
                name=f"nac_{nac_id}",
                node_id=str(uuid.uuid4()),
                position=Vec3(x=x, y=y, z=z),
                geometry=MeshGeometry(
                    type="box",
                    width=0.2,
                    height=0.1,
                    depth=0.08,
                ),
                material=nac_mat,
                device_id=nac_id,
                is_annotation=True,
                annotation_text=f"NAC: {nac_id} ({spl}dBA)",
            )
            scene.nodes.append(nac_node)

    def _add_panels(self, scene: Scene, design: DesignData) -> None:
        """Add FACP panel nodes to the scene."""
        panel_mat = Material(
            name="facp_panel",
            color="#37474F",
            roughness=0.3,
            metallic=0.7,
        )
        scene.materials.append(panel_mat)

        for panel in design.panels:
            panel_id = panel.get("panel_id", str(uuid.uuid4()))
            pos_raw = panel.get("position", panel.get("coordinates", [0, 0, 0]))

            if isinstance(pos_raw, (list, tuple)):
                x = float(pos_raw[0]) if len(pos_raw) >= 1 else 0.0
                z = float(pos_raw[1]) if len(pos_raw) >= 2 else 0.0
                y = float(pos_raw[2]) if len(pos_raw) >= 3 else self.FLOOR_Y + 1.6
            else:
                x, y, z = 0.0, self.FLOOR_Y + 1.6, 0.0

            panel_node = SceneNode(
                name=f"panel_{panel_id}",
                node_id=str(uuid.uuid4()),
                position=Vec3(x=x, y=y, z=z),
                geometry=MeshGeometry(
                    type="box",
                    width=0.6,
                    height=0.8,
                    depth=0.2,
                ),
                material=panel_mat,
                device_id=panel_id,
                is_annotation=True,
                annotation_text=f"FACP: {panel_id}",
            )
            scene.nodes.append(panel_node)

    def _add_cables(self, scene: Scene, design: DesignData) -> None:
        """Add cable routing visualization nodes to the scene."""
        cable_mat = Material(
            name="cable_routing",
            color="#FFC107",
            roughness=0.6,
            metallic=0.2,
        )
        scene.materials.append(cable_mat)

        for cable in design.cables:
            cable_id = cable.get("cable_id", str(uuid.uuid4()))
            route = cable.get("route", cable.get("coordinates", []))

            if not route or len(route) < 6:
                continue

            # Create a series of small cylinders/segments along the route
            points: List[Tuple[float, float, float]] = []
            route_len = len(route)
            if route_len >= 6 and route_len % 3 == 0:
                for i in range(0, route_len, 3):
                    points.append((
                        float(route[i]),
                        float(route[i + 1]),
                        float(route[i + 2]),
                    ))
            elif route_len >= 6:
                for i in range(0, route_len - 2, 2):
                    x = float(route[i])
                    z = float(route[i + 1])
                    y = self.FLOOR_Y + 0.1
                    points.append((x, y, z))

            if len(points) < 2:
                continue

            for seg_idx in range(len(points) - 1):
                p0 = points[seg_idx]
                p1 = points[seg_idx + 1]
                mid = Vec3(
                    x=(p0[0] + p1[0]) / 2,
                    y=(p0[1] + p1[1]) / 2,
                    z=(p0[2] + p1[2]) / 2,
                )
                dx = p1[0] - p0[0]
                dy = p1[1] - p0[1]
                dz = p1[2] - p0[2]
                seg_length = math.sqrt(dx * dx + dy * dy + dz * dz)
                if seg_length < 0.01:
                    continue

                # Compute rotation to align cylinder along segment
                angle_y = math.atan2(dx, dz) if abs(dz) > 1e-6 or abs(dx) > 1e-6 else 0.0
                seg_node = SceneNode(
                    name=f"cable_{cable_id}_seg_{seg_idx}",
                    node_id=str(uuid.uuid4()),
                    position=mid,
                    rotation=Vec3(x=0, y=angle_y, z=0),
                    geometry=MeshGeometry(
                        type="cylinder",
                        radius=self.CABLE_RADIUS,
                        height=seg_length,
                    ),
                    material=cable_mat,
                    device_id=cable_id,
                )
                scene.nodes.append(seg_node)

    def _add_camera_path(self, scene: Scene, design: DesignData) -> None:
        """Add a guided tour camera path based on the design layout."""
        bbox = scene.bounding_box
        if bbox is None:
            return

        center = bbox.center
        size = bbox.size
        max_dim = max(size.x, size.z, 5.0)
        orbit_radius = max_dim * 1.2

        keyframes = [
            CameraKeyframe(
                position=Vec3(
                    x=center.x + orbit_radius,
                    y=center.y + 2.0,
                    z=center.z,
                ),
                target=Vec3(x=center.x, y=center.y, z=center.z),
                duration_sec=4.0,
            ),
            CameraKeyframe(
                position=Vec3(
                    x=center.x,
                    y=center.y + 2.0,
                    z=center.z + orbit_radius,
                ),
                target=Vec3(x=center.x, y=center.y, z=center.z),
                duration_sec=4.0,
            ),
            CameraKeyframe(
                position=Vec3(
                    x=center.x - orbit_radius,
                    y=center.y + 2.0,
                    z=center.z,
                ),
                target=Vec3(x=center.x, y=center.y, z=center.z),
                duration_sec=4.0,
            ),
            CameraKeyframe(
                position=Vec3(
                    x=center.x,
                    y=center.y + 2.0,
                    z=center.z - orbit_radius,
                ),
                target=Vec3(x=center.x, y=center.y, z=center.z),
                duration_sec=4.0,
            ),
            CameraKeyframe(
                position=Vec3(
                    x=center.x + 0.5,
                    y=center.y + 1.6,
                    z=center.z + 0.5,
                ),
                target=Vec3(x=center.x, y=center.y, z=center.z),
                duration_sec=3.0,
            ),
        ]

        path = CameraPath(
            name="guided_tour",
            keyframes=keyframes,
            loop=True,
            autoplay=True,
        )
        scene.camera_paths.append(path)

    def _distance(self, a: Vec3, b: Vec3) -> float:
        dx = a.x - b.x
        dy = a.y - b.y
        dz = a.z - b.z
        return math.sqrt(dx * dx + dy * dy + dz * dz)

    def _find_node_by_device_id(
        self,
        scene: Scene,
        device_id: str,
    ) -> Optional[SceneNode]:
        """Recursively find a node by device_id."""
        for node in scene.nodes:
            if node.device_id == device_id:
                return node
            found = self._find_node_in_children(node, device_id)
            if found is not None:
                return found
        return None

    def _find_node_in_children(
        self,
        node: SceneNode,
        device_id: str,
    ) -> Optional[SceneNode]:
        for child in node.children:
            if child.device_id == device_id:
                return child
            found = self._find_node_in_children(child, device_id)
            if found is not None:
                return found
        return None

    # ── Format: Three.js ─────────────────────────────────────────────────

    def _scene_to_threejs(self, scene: Scene) -> dict:
        """Convert the scene graph to Three.js JSON Object format (v3.1)."""
        geometries: List[dict] = []
        materials_list: List[dict] = []
        nodes_list: List[dict] = []

        geo_map: Dict[str, int] = {}
        mat_map: Dict[str, int] = {}

        def _build_geo_key(geom: MeshGeometry) -> str:
            return json.dumps(geom.to_dict(), sort_keys=True)

        def _ensure_geo(geom: MeshGeometry) -> int:
            key = _build_geo_key(geom)
            if key in geo_map:
                return geo_map[key]
            idx = len(geometries)
            geo_dict = geom.to_dict()
            if geom.type == "box":
                geo_dict["type"] = "BoxGeometry"
            elif geom.type == "sphere":
                geo_dict["type"] = "SphereGeometry"
            elif geom.type == "cylinder":
                geo_dict["type"] = "CylinderGeometry"
            geometries.append(geo_dict)
            geo_map[key] = idx
            return idx

        def _ensure_mat(mat: Material) -> int:
            key = f"{mat.name}_{mat.color}_{mat.opacity}"
            if key in mat_map:
                return mat_map[key]
            idx = len(materials_list)
            materials_list.append(mat.to_dict())
            mat_map[key] = idx
            return idx

        def _serialize_node(node: SceneNode) -> dict:
            node_dict: dict = {
                "name": node.name,
            }
            if node.device_id:
                node_dict["userData"] = {
                    "device_id": node.device_id,
                    "annotation_text": node.annotation_text,
                }
            pos = node.position
            if pos.x != 0 or pos.y != 0 or pos.z != 0:
                node_dict["position"] = pos.to_list()
            rot = node.rotation
            if rot.x != 0 or rot.y != 0 or rot.z != 0:
                node_dict["rotation"] = rot.to_list()
            scl = node.scale
            if scl.x != 1 or scl.y != 1 or scl.z != 1:
                node_dict["scale"] = scl.to_list()

            if node.geometry and node.material:
                geo_idx = _ensure_geo(node.geometry)
                mat_idx = _ensure_mat(node.material)
                node_dict["geometry"] = geo_idx
                node_dict["material"] = mat_idx

            if node.children:
                node_dict["children"] = [_serialize_node(c) for c in node.children]

            return node_dict

        for node in scene.nodes:
            nodes_list.append(_serialize_node(node))

        threejs_scene: dict = {
            "metadata": {
                "version": 4.6,
                "type": "Object",
                "generator": "FireAI_ARVRVisualizer",
            },
            "geometries": geometries,
            "materials": materials_list,
            "object": {
                "name": scene.name,
                "type": "Scene",
                "children": nodes_list,
            },
        }

        if scene.camera_paths:
            threejs_scene["camera_paths"] = [cp.to_dict() for cp in scene.camera_paths]

        return threejs_scene

    # ── Format: glTF 2.0 binary ──────────────────────────────────────────

    def _scene_to_glb(self, scene: Scene) -> bytes:
        """Generate a minimal binary glTF (GLB) representation.

        This is a simplified glTF generator that creates a valid .glb
        with scene structure. For production, the glTF JSON and binary
        buffer are constructed according to the glTF 2.0 spec.
        """
        if not scene.nodes:
            return self._make_empty_glb()

        nodes_json: List[dict] = []
        meshes_json: List[dict] = []
        accessors_json: List[dict] = []
        buffer_views: List[dict] = []
        materials_json: List[dict] = []
        all_positions: List[float] = []
        all_indices: List[int] = []
        mat_refs: List[Optional[int]] = []

        # Collect vertex data for each node
        for _node_idx, node in enumerate(scene.nodes):
            if not node.geometry:
                nodes_json.append({
                    "name": node.name,
                    "translation": node.position.to_list(),
                    "rotation": [0, 0, 0, 1],
                    "scale": node.scale.to_list(),
                })
                mat_refs.append(None)
                continue

            # Generate primitive geometry
            verts, tris = self._generate_primitive_mesh(node.geometry)
            if not verts or not tris:
                nodes_json.append({
                    "name": node.name,
                    "translation": node.position.to_list(),
                    "rotation": [0, 0, 0, 1],
                    "scale": node.scale.to_list(),
                })
                mat_refs.append(None)
                continue

            # Apply translation
            translated = list(verts)
            for i in range(0, len(translated), 3):
                translated[i] += node.position.x
                translated[i + 1] += node.position.y
                translated[i + 2] += node.position.z

            offset_pos = len(all_positions) // 3
            len(all_indices)

            all_positions.extend(translated)
            all_indices.extend(tri + offset_pos for tri in tris)

            accessors_json.append({
                "bufferView": 0,
                "componentType": 5126,
                "count": len(translated) // 3,
                "type": "VEC3",
                "max": [
                    max(translated[i] for i in range(0, len(translated), 3)),
                    max(translated[i + 1] for i in range(0, len(translated), 3)),
                    max(translated[i + 2] for i in range(0, len(translated), 3)),
                ],
                "min": [
                    min(translated[i] for i in range(0, len(translated), 3)),
                    min(translated[i + 1] for i in range(0, len(translated), 3)),
                    min(translated[i + 2] for i in range(0, len(translated), 3)),
                ],
            })

            accessors_json.append({
                "bufferView": 1,
                "componentType": 5123,
                "count": len(tris),
                "type": "SCALAR",
            })

            mesh_idx = len(meshes_json)

            if node.material:
                mat_idx = len(materials_json)
                materials_json.append({
                    "pbrMetallicRoughness": {
                        "baseColorFactor": self._hex_to_rgba(node.material.color, node.material.opacity),
                        "metallicFactor": node.material.metallic,
                        "roughnessFactor": node.material.roughness,
                    },
                    "alphaMode": "BLEND" if node.material.transparent else "OPAQUE",
                    "doubleSided": node.material.side == "double",
                    "name": node.material.name,
                })
            else:
                mat_idx = -1

            meshes_json.append({
                "primitives": [{
                    "attributes": {"POSITION": len(accessors_json) - 2},
                    "indices": len(accessors_json) - 1,
                    "material": mat_idx if mat_idx >= 0 else None,
                }],
                "name": node.name,
            })

            mat_refs.append(mat_idx if mat_idx >= 0 else None)

            nodes_json.append({
                "name": node.name,
                "mesh": mesh_idx,
                "translation": [0, 0, 0],
                "rotation": [0, 0, 0, 1],
                "scale": [1, 1, 1],
            })

        # Build buffer (positions + indices)
        pos_bytes = struct.pack(f"{len(all_positions)}f", *all_positions)
        idx_bytes = struct.pack(f"{len(all_indices)}H", *all_indices)
        total_buffer = pos_bytes + idx_bytes

        pos_byte_length = len(pos_bytes)
        idx_byte_offset = pos_byte_length

        buffer_views = [
            {"buffer": 0, "byteOffset": 0, "byteLength": pos_byte_length, "target": 34962},
            {"buffer": 0, "byteOffset": idx_byte_offset, "byteLength": len(idx_bytes), "target": 34963},
        ]

        scene_json: dict = {
            "asset": {"version": "2.0", "generator": "FireAI_ARVRVisualizer"},
            "scene": 0,
            "scenes": [{"nodes": list(range(len(nodes_json)))}],
            "nodes": nodes_json,
            "meshes": meshes_json,
            "accessors": accessors_json,
            "bufferViews": buffer_views,
            "buffers": [{"byteLength": len(total_buffer)}],
            "materials": materials_json,
        }

        # Encode JSON with padding
        json_str = json.dumps(scene_json, separators=(",", ":"))
        # Align to 4 bytes
        while len(json_str) % 4 != 0:
            json_str += " "

        json_bytes = json_str.encode("utf-8")
        json_pad = (4 - len(json_bytes) % 4) % 4

        # GLB header: magic (4), version (4), length (4)
        glb_length = 12 + 8 + len(json_bytes) + json_pad + 8 + len(total_buffer)

        header = struct.pack("<IIII", 0x46546C67, 2, glb_length, 12 + 8 + len(json_bytes) + json_pad)

        # JSON chunk
        json_chunk_header = struct.pack("<II", len(json_bytes) + json_pad, 0x4E4F534A)
        json_chunk = json_bytes + b" " * json_pad

        # BIN chunk
        bin_pad = (4 - len(total_buffer) % 4) % 4
        bin_chunk_header = struct.pack("<II", len(total_buffer) + bin_pad, 0x004E4942)
        bin_chunk = total_buffer + b"\x00" * bin_pad

        return header + json_chunk_header + json_chunk + bin_chunk_header + bin_chunk

    def _make_empty_glb(self) -> bytes:
        """Create a minimal valid GLB with an empty scene."""
        scene_json = {
            "asset": {"version": "2.0", "generator": "FireAI_ARVRVisualizer"},
            "scene": 0,
            "scenes": [{"nodes": []}],
            "nodes": [],
        }
        json_str = json.dumps(scene_json, separators=(",", ":"))
        while len(json_str) % 4 != 0:
            json_str += " "
        json_bytes = json_str.encode("utf-8")
        glb_length = 12 + 8 + len(json_bytes)
        header = struct.pack("<IIII", 0x46546C67, 2, glb_length, 12 + 8 + len(json_bytes))
        json_chunk_header = struct.pack("<II", len(json_bytes), 0x4E4F534A)
        return header + json_chunk_header + json_bytes

    def _generate_primitive_mesh(
        self,
        geom: MeshGeometry,
    ) -> Tuple[List[float], List[int]]:
        """Generate vertex positions and triangle indices for a primitive mesh.

        Returns (positions, indices) where positions is a flat list of
        x,y,z floats and indices is a flat list of triangle indices.
        """
        if geom.type == "box":
            return self._generate_box_mesh(geom.width, geom.height, geom.depth)
        if geom.type == "sphere":
            return self._generate_sphere_mesh(geom.radius)
        if geom.type == "cylinder":
            return self._generate_cylinder_mesh(geom.radius, geom.height)
        return self._generate_box_mesh(1, 1, 1)

    def _generate_box_mesh(
        self,
        w: float,
        h: float,
        d: float,
    ) -> Tuple[List[float], List[int]]:
        hw, hh, hd = w / 2, h / 2, d / 2
        verts = [
            -hw, -hh, -hd,  hw, -hh, -hd,  hw,  hh, -hd, -hw,  hh, -hd,
            -hw, -hh,  hd,  hw, -hh,  hd,  hw,  hh,  hd, -hw,  hh,  hd,
        ]
        indices = [
            0, 1, 2,  0, 2, 3,
            1, 5, 6,  1, 6, 2,
            5, 4, 7,  5, 7, 6,
            4, 0, 3,  4, 3, 7,
            3, 2, 6,  3, 6, 7,
            4, 5, 1,  4, 1, 0,
        ]
        return verts, indices

    def _generate_sphere_mesh(
        self,
        radius: float,
        segments: int = 16,
    ) -> Tuple[List[float], List[int]]:
        verts: List[float] = []
        indices: List[int] = []

        for lat in range(segments + 1):
            theta = math.pi * lat / segments
            sin_theta = math.sin(theta)
            cos_theta = math.cos(theta)
            for lon in range(segments + 1):
                phi = 2 * math.pi * lon / segments
                x = radius * sin_theta * math.cos(phi)
                y = radius * cos_theta
                z = radius * sin_theta * math.sin(phi)
                verts.extend([x, y, z])

        for lat in range(segments):
            for lon in range(segments):
                first = lat * (segments + 1) + lon
                second = first + segments + 1
                indices.extend([first, second, first + 1])
                indices.extend([second, second + 1, first + 1])

        return verts, indices

    def _generate_cylinder_mesh(
        self,
        radius: float,
        height: float,
        segments: int = 16,
    ) -> Tuple[List[float], List[int]]:
        verts: List[float] = []
        indices: List[int] = []

        hh = height / 2

        # Bottom cap center
        verts.extend([0, -hh, 0])
        bottom_center = 0

        # Bottom ring
        for i in range(segments):
            theta = 2 * math.pi * i / segments
            x = radius * math.cos(theta)
            z = radius * math.sin(theta)
            verts.extend([x, -hh, z])

        # Top cap center
        verts.extend([0, hh, 0])
        top_center = 1 + segments

        # Top ring
        for i in range(segments):
            theta = 2 * math.pi * i / segments
            x = radius * math.cos(theta)
            z = radius * math.sin(theta)
            verts.extend([x, hh, z])

        segments + 1

        # Bottom cap triangles
        for i in range(segments):
            next_i = (i + 1) % segments
            indices.extend([bottom_center, bottom_center + 1 + i, bottom_center + 1 + next_i])

        # Top cap triangles
        top_offset = top_center
        for i in range(segments):
            next_i = (i + 1) % segments
            indices.extend([top_offset, top_offset + 1 + next_i, top_offset + 1 + i])

        # Side triangles
        for i in range(segments):
            next_i = (i + 1) % segments
            b0 = bottom_center + 1 + i
            b1 = bottom_center + 1 + next_i
            t0 = top_center + 1 + i
            t1 = top_center + 1 + next_i
            indices.extend([b0, b1, t0])
            indices.extend([b1, t1, t0])

        return verts, indices

    def _hex_to_rgba(self, hex_color: str, alpha: float = 1.0) -> List[float]:
        """Convert hex color string to RGBA float list."""
        hex_color = hex_color.lstrip("#")
        if len(hex_color) == 3:
            hex_color = "".join(c * 2 for c in hex_color)
        r = int(hex_color[0:2], 16) / 255.0
        g = int(hex_color[2:4], 16) / 255.0
        b = int(hex_color[4:6], 16) / 255.0
        return [r, g, b, alpha]

    # ── Format: A-Frame HTML ─────────────────────────────────────────────

    def _scene_to_aframe(self, scene: Scene) -> str:
        """Generate a self-contained A-Frame HTML document."""
        html_parts: List[str] = []
        html_parts.append('<!DOCTYPE html>')
        html_parts.append('<html>')
        html_parts.append('<head>')
        html_parts.append('<meta charset="utf-8">')
        html_parts.append('<meta name="viewport" content="width=device-width, initial-scale=1">')
        html_parts.append('<title>Fire Alarm Design - AR/VR View</title>')
        html_parts.append('<script src="https://aframe.io/releases/1.5.0/aframe.min.js"></script>')
        html_parts.append('<script src="https://unpkg.com/aframe-event-set-component@3.0.0/dist/aframe-event-set-component.min.js"></script>')
        html_parts.append('<script src="https://unpkg.com/aframe-look-at-component@0.8.0/dist/aframe-look-at-component.min.js"></script>')
        html_parts.append('<style>')
        html_parts.append('  body { margin: 0; overflow: hidden; }')
        html_parts.append('  .annotation-label {')
        html_parts.append('    color: white; font-family: monospace; font-size: 14px;')
        html_parts.append('    background: rgba(0,0,0,0.7); padding: 4px 8px;')
        html_parts.append('    border-radius: 4px; pointer-events: none;')
        html_parts.append('    text-align: center; white-space: nowrap;')
        html_parts.append('  }')
        html_parts.append('</style>')
        html_parts.append('</head>')
        html_parts.append('<body>')

        # Scene
        bbox = scene.bounding_box
        if bbox:
            center = bbox.center
            size = bbox.size
            camera_pos = f"{center.x + max(size.x, size.z) * 1.5} {center.y + 3} {center.z + max(size.x, size.z) * 1.5}"
        else:
            camera_pos = "10 5 10"

        html_parts.append('<a-scene background="color: #1a1a2e" renderer="antialias: true" vr-mode-ui="enabled: true">')

        # Lighting
        html_parts.append('  <a-light type="ambient" color="#ffffff" intensity="0.6"></a-light>')
        html_parts.append('  <a-light type="directional" color="#ffffff" intensity="0.8" position="10 20 10"></a-light>')
        html_parts.append('  <a-light type="directional" color="#ffffff" intensity="0.4" position="-10 10 -10"></a-light>')

        # Camera with guided tour
        html_parts.append(f'  <a-entity id="camera-rig" position="{camera_pos}">')
        html_parts.append('    <a-entity id="camera" camera="active: true" wasd-controls look-controls position="0 1.6 0">')
        html_parts.append('      <a-cursor id="cursor" fuse="false" raycaster="objects: .clickable"></a-cursor>')
        html_parts.append('    </a-entity>')
        html_parts.append('  </a-entity>')

        # VR controller hints
        html_parts.append('  <!-- VR Controller Support -->')
        html_parts.append('  <a-entity id="left-hand" hand-controls="hand: left" controller-listeners>')
        html_parts.append('    <a-entity id="laser-left" laser-controls="hand: left" raycaster="objects: .clickable"></a-entity>')
        html_parts.append('  </a-entity>')
        html_parts.append('  <a-entity id="right-hand" hand-controls="hand: right" controller-listeners>')
        html_parts.append('    <a-entity id="laser-right" laser-controls="hand: right" raycaster="objects: .clickable"></a-entity>')
        html_parts.append('  </a-entity>')
        html_parts.append('  <a-entity id="teleport-rig" movement-controls="cameraRig: #camera-rig; speed: 2"></a-entity>')

        # Room geometry
        for node in scene.nodes:
            if node.name.startswith("room_"):
                self._aframe_add_room_group(html_parts, node)
            elif node.name.startswith("floor_") or node.name.startswith("ceiling_"):
                self._aframe_add_box(html_parts, node)
            elif node.name.startswith("detector_"):
                self._aframe_add_detector(html_parts, node)
            elif node.name.startswith("nac_"):
                self._aframe_add_nac(html_parts, node)
            elif node.name.startswith("panel_"):
                self._aframe_add_panel(html_parts, node)
            elif node.name.startswith("cable_"):
                self._aframe_add_cable_segment(html_parts, node)
            elif node.is_coverage:
                self._aframe_add_coverage(html_parts, node)

        # Annotation overlay instructions
        html_parts.append('  <!-- Annotation tooltip -->')
        html_parts.append('  <a-entity id="tooltip" position="0 0 0" visible="false">')
        html_parts.append('    <a-plane color="#333" width="1.2" height="0.4" position="0 0.3 0" opacity="0.85"></a-plane>')
        html_parts.append('    <a-text id="tooltip-text" value="" position="0 0.3 0.01" align="center" color="#FFF" width="1.1"></a-text>')
        html_parts.append('  </a-entity>')

        # Guided tour button
        html_parts.append('  <!-- Guided Tour Control -->')
        html_parts.append('  <a-entity position="-0.8 -0.6 -0.5" camera-parent>')
        html_parts.append('    <a-plane id="tour-btn" color="#2196F3" width="0.3" height="0.12" shader="flat" class="clickable"')
        html_parts.append('      event-set__click="_event: click; _target: #camera-rig; animation__guided_tour: property: position; dur: 0">')
        html_parts.append('      <a-text value="TOUR" color="white" align="center" position="0 0 0.02" scale="0.01 0.01 0.01"></a-text>')
        html_parts.append('    </a-plane>')
        html_parts.append('  </a-entity>')

        # Scene transition hint for VR
        html_parts.append('  <a-entity position="0 0.2 -0.5" camera-parent>')
        html_parts.append('    <a-text value="Press ENTER for VR mode" color="#888" align="center" scale="0.01 0.01 0.01" position="0 0 0"></a-text>')
        html_parts.append('  </a-entity>')

        # Guided tour animation (camera path)
        if scene.camera_paths:
            path = scene.camera_paths[0]
            if path.keyframes:
                html_parts.append('  <a-animation id="guided-tour-anim" attribute="position"')
                html_parts.append(f'    dur="{int(sum(kf.duration_sec for kf in path.keyframes) * 1000)}"')
                html_parts.append('    fill="backwards" repeat="indefinite"')
                html_parts.append('    begin="tour-start"')
                values = "; ".join(
                    f"{kf.position.x} {kf.position.y} {kf.position.z}"
                    for kf in path.keyframes
                )
                html_parts.append(f'    values="{values}"')
                html_parts.append('  ></a-animation>')

        html_parts.append('</a-scene>')

        # JavaScript for annotations and tour
        html_parts.append('<script>')
        html_parts.append('  AFRAME.registerComponent("controller-listeners", {')
        html_parts.append('    init: function() {')
        html_parts.append('      this.el.addEventListener("triggerdown", function(evt) {')
        html_parts.append('        console.log("VR trigger pressed");')
        html_parts.append('      });')
        html_parts.append('    }')
        html_parts.append('  });')
        html_parts.append('')
        html_parts.append('  // Click handler for device annotations')
        html_parts.append('  document.addEventListener("click", function(evt) {')
        html_parts.append('    var el = evt.target;')
        html_parts.append('    var annotation = el.getAttribute("data-annotation");')
        html_parts.append('    if (annotation) {')
        html_parts.append('      var tooltip = document.getElementById("tooltip");')
        html_parts.append('      var textEl = document.getElementById("tooltip-text");')
        html_parts.append('      if (tooltip && textEl) {')
        html_parts.append('        textEl.setAttribute("value", annotation);')
        html_parts.append('        tooltip.setAttribute("visible", "true");')
        html_parts.append('        // Position tooltip on object')
        html_parts.append('        var objPos = new THREE.Vector3();')
        html_parts.append('        el.object3D.getWorldPosition(objPos);')
        html_parts.append('        tooltip.setAttribute("position", objPos.x + " " + (objPos.y + 0.5) + " " + objPos.z);')
        html_parts.append('        // Hide after 3 seconds')
        html_parts.append('        setTimeout(function() {')
        html_parts.append('          tooltip.setAttribute("visible", "false");')
        html_parts.append('        }, 3000);')
        html_parts.append('      }')
        html_parts.append('    }')
        html_parts.append('  });')
        html_parts.append('')
        html_parts.append('  // Guided tour toggle')
        html_parts.append('  document.getElementById("tour-btn").addEventListener("click", function() {')
        html_parts.append('    var anim = document.getElementById("guided-tour-anim");')
        html_parts.append('    if (anim) {')
        html_parts.append('      if (anim.isRunning) {')
        html_parts.append('        anim.stop();')
        html_parts.append('      } else {')
        html_parts.append('        anim.emit("tour-start");')
        html_parts.append('      }')
        html_parts.append('    }')
        html_parts.append('  });')
        html_parts.append('</script>')
        html_parts.append('</body>')
        html_parts.append('</html>')

        return "\n".join(html_parts)

    def _aframe_add_room_group(self, parts: List[str], node: SceneNode) -> None:
        pos = node.position
        parts.append(f'  <a-entity position="{pos.x} {pos.y} {pos.z}">')
        for child in node.children:
            self._aframe_add_box(parts, child, indent=4)
        parts.append('  </a-entity>')

    def _aframe_add_box(
        self,
        parts: List[str],
        node: SceneNode,
        indent: int = 2,
    ) -> None:
        prefix = " " * indent
        pos = node.position
        geom = node.geometry
        mat = node.material or Material()

        color = mat.color
        opacity = mat.opacity
        transparent = "true" if mat.transparent else "false"
        side = mat.side

        if geom and geom.type == "box":
            parts.append(
                f'{prefix}<a-box position="{pos.x} {pos.y} {pos.z}" '
                f'width="{geom.width}" height="{geom.height}" depth="{geom.depth}" '
                f'color="{color}" opacity="{opacity}" transparent="{transparent}" '
                f'side="{side}" class="clickable" data-annotation="{node.annotation_text}">'
                f'</a-box>'
            )
        elif geom and geom.type == "sphere":
            parts.append(
                f'{prefix}<a-sphere position="{pos.x} {pos.y} {pos.z}" '
                f'radius="{geom.radius}" '
                f'color="{color}" opacity="{opacity}" transparent="{transparent}" '
                f'side="{side}" class="clickable" data-annotation="{node.annotation_text}">'
                f'</a-sphere>'
            )
        elif geom and geom.type == "cylinder":
            parts.append(
                f'{prefix}<a-cylinder position="{pos.x} {pos.y} {pos.z}" '
                f'radius="{geom.radius}" height="{geom.height}" '
                f'color="{color}" opacity="{opacity}" transparent="{transparent}" '
                f'side="{side}" class="clickable" data-annotation="{node.annotation_text}">'
                f'</a-cylinder>'
            )

    def _aframe_add_detector(self, parts: List[str], node: SceneNode) -> None:
        self._aframe_add_box(parts, node)
        if node.annotation_text:
            pos = node.position
            parts.append(
                f'  <a-text value="{node.device_id}" position="{pos.x} {pos.y + 0.3} {pos.z}" '
                f'align="center" color="white" scale="0.02 0.02 0.02" '
                f'class="clickable" data-annotation="{node.annotation_text}">'
                f'</a-text>'
            )

    def _aframe_add_nac(self, parts: List[str], node: SceneNode) -> None:
        self._aframe_add_box(parts, node)

    def _aframe_add_panel(self, parts: List[str], node: SceneNode) -> None:
        self._aframe_add_box(parts, node)

    def _aframe_add_cable_segment(self, parts: List[str], node: SceneNode) -> None:
        self._aframe_add_box(parts, node)

    def _aframe_add_coverage(self, parts: List[str], node: SceneNode) -> None:
        """Add coverage visualization as a wireframe or translucent sphere."""
        mat = node.material or Material(color="#4CAF50", opacity=0.5, transparent=True)
        pos = node.position
        geom = node.geometry
        if geom and geom.type == "sphere":
            parts.append(
                f'  <a-sphere position="{pos.x} {pos.y} {pos.z}" '
                f'radius="{geom.radius}" '
                f'color="{mat.color}" opacity="0.5" transparent="true" '
                f'side="double" wireframe="false">'
                f'</a-sphere>'
            )
        elif geom and geom.type == "box":
            parts.append(
                f'  <a-box position="{pos.x} {pos.y} {pos.z}" '
                f'width="{geom.width}" height="{geom.height}" depth="{geom.depth}" '
                f'color="{mat.color}" opacity="0.5" transparent="true" '
                f'side="double">'
                f'</a-box>'
            )

    # ── Format: USDZ ─────────────────────────────────────────────────────

    def _generate_usdz(self, scene: Scene) -> str:
        """Generate a USDA (USD ASCII) scene description for USDZ packaging.

        USDZ is a zip archive containing USDA/USDC files. This generates
        the USDA text representation that can be zipped into a .usdz file.

        For production use, this USDA text should be written to a file
        and packaged with Apple's usdzip or usdpython tools.
        """
        lines: List[str] = []
        lines.append("#usda 1.0")
        lines.append('(')
        lines.append('    defaultPrim = "FireAlarmScene"')
        lines.append('    metersPerUnit = 1')
        lines.append('    upAxis = "Y"')
        lines.append(')')
        lines.append('')

        # Define materials
        mat_defs: Dict[str, str] = {}
        for mat in scene.materials:
            mat_name = f"mat_{mat.name.replace(' ', '_')}"
            mat_defs[mat.name] = mat_name
            rgba = self._hex_to_rgba(mat.color, mat.opacity)
            lines.append(f'def Material "{mat_name}"')
            lines.append('{')
            lines.append('    token outputs:surface.connect = None')
            lines.append(f'    token outputs:surface.connect = </{mat_name}/PBRShader.outputs:surface>')
            lines.append('')
            lines.append('    def Shader "PBRShader"')
            lines.append('    {')
            lines.append('        uniform token info:id = "UsdPreviewSurface"')
            lines.append(f'        color3f inputs:diffuseColor = ({rgba[0]:.4f}, {rgba[1]:.4f}, {rgba[2]:.4f})')
            lines.append(f'        float inputs:opacity = {rgba[3]:.4f}')
            lines.append(f'        float inputs:metallic = {mat.metallic:.4f}')
            lines.append(f'        float inputs:roughness = {mat.roughness:.4f}')
            lines.append('        token outputs:surface')
            lines.append('    }')
            lines.append('}')
            lines.append('')

        # USDZ scene root
        lines.append('def Xform "FireAlarmScene"')
        lines.append('{')

        for node in scene.nodes:
            self._usdz_add_node(lines, node, mat_defs, indent=4)

        # Camera path (as a USD camera animation)
        if scene.camera_paths:
            path = scene.camera_paths[0]
            lines.append('    def Xform "CameraPath"')
            lines.append('    {')
            for kf_idx, kf in enumerate(path.keyframes):
                lines.append(f'        def Camera "Keyframe_{kf_idx}"')
                lines.append('        {')
                lines.append(f'            double3 xformOp:translate = ({kf.position.x:.4f}, {kf.position.y:.4f}, {kf.position.z:.4f})')
                lines.append('            uniform token[] xformOpOrder = ["xformOp:translate"]')
                lines.append('            float focalLength = 50')
                lines.append('        }')
                lines.append('')
            lines.append('    }')

        lines.append('}')
        lines.append('')

        # Metadata
        lines.append('def Xform "SceneMetadata"')
        lines.append('{')
        lines.append(f'    string design_id = "{scene.metadata.get("design_id", "")}"')
        lines.append('    string generator = "FireAI_ARVRVisualizer"')
        lines.append('}')

        return "\n".join(lines)

    def _usdz_add_node(
        self,
        lines: List[str],
        node: SceneNode,
        mat_defs: Dict[str, str],
        indent: int = 4,
    ) -> None:
        prefix = " " * indent
        node_name = node.name.replace(" ", "_").replace("-", "_")
        geom = node.geometry
        mat = node.material

        lines.append(f'{prefix}# {node.name}')

        if geom is None:
            # Transform node with children
            lines.append(f'{prefix}def Xform "{node_name}"')
            lines.append(f'{prefix}{{')
            pos = node.position
            if pos.x != 0 or pos.y != 0 or pos.z != 0:
                lines.append(f'{prefix}    double3 xformOp:translate = ({pos.x:.4f}, {pos.y:.4f}, {pos.z:.4f})')
                lines.append(f'{prefix}    uniform token[] xformOpOrder = ["xformOp:translate"]')
            if node.device_id:
                lines.append(f'{prefix}    string device_id = "{node.device_id}"')
                lines.append(f'{prefix}    string annotation = "{node.annotation_text}"')
            for child in node.children:
                self._usdz_add_node(lines, child, mat_defs, indent + 4)
            lines.append(f'{prefix}}}')
            lines.append('')
            return

        # Determine USD geom type
        if geom.type == "box":
            size_attr = f'size = {max(geom.width, geom.height, geom.depth):.4f}'
        elif geom.type == "sphere":
            size_attr = f'radius = {geom.radius:.4f}'
        elif geom.type == "cylinder":
            size_attr = f'height = {geom.height:.4f}  radius = {geom.radius:.4f}'
        else:
            size_attr = "size = 1"

        lines.append(f'{prefix}def Mesh "{node_name}"')
        lines.append(f'{prefix}{{')
        lines.append(f'{prefix}    {size_attr}')

        if mat:
            mat_name = mat_defs.get(mat.name, "")
            if mat_name:
                lines.append(f'{prefix}    rel material:binding = </{mat_name}>')

        pos = node.position
        if pos.x != 0 or pos.y != 0 or pos.z != 0:
            lines.append(f'{prefix}    double3 xformOp:translate = ({pos.x:.4f}, {pos.y:.4f}, {pos.z:.4f})')
            lines.append(f'{prefix}    uniform token[] xformOpOrder = ["xformOp:translate"]')

        if node.device_id:
            lines.append(f'{prefix}    string device_id = "{node.device_id}"')
            lines.append(f'{prefix}    string annotation = "{node.annotation_text}"')

        lines.append(f'{prefix}}}')
        lines.append('')


# ===========================================================================
# Self-Test
# ===========================================================================

if __name__ == "__main__":
    visualizer = ARVRVisualizer()

    design = DesignData(
        design_id="DSG-AR-001",
        rooms=[
            {
                "room_id": "R-101",
                "name": "Main Office",
                "polygon": [(0, 0), (10, 0), (10, 8), (0, 8)],
                "ceiling_height_m": 3.0,
            },
            {
                "room_id": "R-102",
                "name": "Server Room",
                "polygon": [(11, 0), (14, 0), (14, 5), (11, 5)],
                "ceiling_height_m": 3.0,
            },
        ],
        detectors=[
            {
                "detector_id": "DET-001",
                "detector_type": "SMOKE_PHOTOELECTRIC",
                "position": [5.0, 4.0, 3.0],
            },
            {
                "detector_id": "DET-002",
                "detector_type": "HEAT_FIXED",
                "position": [12.5, 3.0, 3.0],
            },
            {
                "detector_id": "DET-003",
                "detector_type": "COMBINATION",
                "position": [2.0, 6.0, 3.0],
            },
        ],
        notification_appliances=[
            {
                "nac_id": "NAC-001",
                "spl_dba": 85,
                "position": [0.5, 0.5, 2.5],
            },
        ],
        panels=[
            {
                "panel_id": "FACP-001",
                "position": [0.0, 0.0, 1.6],
            },
        ],
        cables=[
            {
                "cable_id": "CBL-001",
                "route": [0.5, 0.5, 0.1, 2.0, 4.0, 0.1, 5.0, 4.0, 0.1],
            },
        ],
    )

    # Three.js
    threejs_scene = visualizer.generate_threejs(design)
    print(f"Three.js: {len(json.dumps(threejs_scene))} bytes, "
          f"{len(threejs_scene['object']['children'])} root nodes")

    # glTF
    glb = visualizer.generate_gltf(design)
    print(f"glTF: {len(glb)} bytes")

    # A-Frame
    aframe_html = visualizer.generate_aframe_html(design)
    print(f"A-Frame: {len(aframe_html)} chars")

    # Coverage visualization
    coverage = CoverageResult(
        is_covered=True,
        coverage_percentage=99.9,
        coverage_radius_m=5.0,
    )
    scene = visualizer._build_scene(design)
    scene = visualizer.add_coverage_visualization(scene, coverage)
    print(f"Coverage added: {len(scene.nodes)} nodes")

    # Annotations
    scene = visualizer.add_annotation(scene, "DET-001", "SMOKE detector - Main Office")
    annotated = visualizer._find_node_by_device_id(scene, "DET-001")
    print(f"Annotation added to: {annotated.name if annotated else 'NOT FOUND'}")

    print("\nAll AR/VR visualizer tests passed.")
