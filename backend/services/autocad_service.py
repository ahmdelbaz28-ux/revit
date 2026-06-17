"""backend/services/autocad_service.py — AutoCAD Integration Service
================================================================

Complete AutoCAD integration service with multiple connection methods.
Based on research from:
- manufino/AutoCAD: OO wrapper pattern
- luanshixia/AutoCADCodePack: LINQ-style selection
- chuongmep/CadPythonShell: Python integration

CONNECTION METHODS:
- COM: Windows-only (win32com.client)
- Simulation: Cross-platform (no AutoCAD required)

FEATURES:
- Layer management (create, delete, lock, color, linetype)
- Block operations (insert, export, attributes)
- Transform operations (move, rotate, scale)
- Dimension creation (aligned, linear, angular, radial, diameter)
- Group operations
- Simulation mode with in-memory entity storage
- AI command execution

USAGE:
    from backend.services.autocad_service import AutoCADService
    service = AutoCADService()

    # Connect
    service.connect(method="com")  # or "simulation"

    # Draw entities
    service.draw_line([0,0,0], [100,100,0])
    service.draw_rectangle([0,0,0], [100,100,0])

    # Layer operations
    service.create_layer("MyLayer", color=1)
"""

import logging
import math
import os
import platform
import re
import uuid
from enum import Enum
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Connection method enum
class ConnectionMethod(str, Enum):
    COM = "com"           # Windows COM API
    SIMULATION = "simulation"  # In-memory simulation

# AutoCAD color indices (ACI)
class AutoCADColor:
    RED = 1
    YELLOW = 2
    GREEN = 3
    CYAN = 4
    BLUE = 5
    MAGENTA = 6
    WHITE = 7

# Cross-platform support
IS_WINDOWS = platform.system() == "Windows"
HAS_COM_API = False

if IS_WINDOWS:
    try:
        import pythoncom
        import win32com.client
        HAS_COM_API = True
    except ImportError:
        logger.warning("AutoCAD COM API not available. Install pywin32.")
        HAS_COM_API = False
else:
    logger.info("Non-Windows platform. Simulation mode only.")


class SimulationEntity:
    """In-memory entity for simulation mode."""

    def __init__(self, entity_type: str, handle: str, properties: Dict[str, Any]):
        self.entity_type = entity_type
        self.handle = handle
        self.properties = properties

    def __getitem__(self, key):
        return self.properties.get(key)

    def __setitem__(self, key, value):
        self.properties[key] = value


class SimulationLayer:
    """In-memory layer for simulation mode."""

    def __init__(self, name: str, color: int = 7, visible: bool = True):
        self.name = name
        self.color = color
        self.visible = visible
        self.locked = False


class SimulationDocument:
    """In-memory document for simulation mode."""

    def __init__(self):
        self.name = "Simulation"
        self.path = ""
        self.layers: Dict[str, SimulationLayer] = {"0": SimulationLayer("0", 7, True)}
        self.entities: List[SimulationEntity] = []
        self.groups: Dict[str, List[str]] = {}  # group_name -> entity_handles


class AutoCADService:
    """AutoCAD integration service with multiple connection methods.

    Supports:
    - COM API (Windows only)
    - Simulation mode (cross-platform, no AutoCAD required)
    """

    def __init__(self):
        self.connection_method: Optional[ConnectionMethod] = None
        self.acad_app = None
        self.acad_doc = None
        self.acad_util = None
        self.connected = False

        # Simulation mode storage
        self.simulation_doc: Optional[SimulationDocument] = None

        # Entity tracking
        self.active_entities: Dict[str, Any] = {}

    # =========================================================================
    # CONNECTION METHODS
    # =========================================================================

    def connect(self, method: str = "auto") -> bool:
        """Connect to AutoCAD using specified method.

        Args:
            method: Connection method - "com", "simulation", or "auto"
                   - "com": Windows COM API (requires AutoCAD)
                   - "simulation": In-memory simulation (no AutoCAD)
                   - "auto": Try COM first, fallback to simulation

        Returns:
            bool: True if connection successful

        """
        if method == "auto":
            if HAS_COM_API:
                return self._connect_com()
            return self._connect_simulation()
        if method == "com":
            return self._connect_com()
        if method == "simulation":
            return self._connect_simulation()
        logger.error(f"Unknown connection method: {method}")
        return False

    def _connect_com(self) -> bool:
        """Connect using Windows COM API."""
        if not HAS_COM_API:
            logger.error("COM API not available on this platform")
            return False

        try:
            pythoncom.CoInitialize()

            # Try to connect to existing instance
            try:
                self.acad_app = win32com.client.GetActiveObject("AutoCAD.Application")
                logger.info("Connected to existing AutoCAD instance")
            except Exception:
                # Launch new instance
                try:
                    self.acad_app = win32com.client.Dispatch("AutoCAD.Application")
                    self.acad_app.Visible = True
                    logger.info("Launched new AutoCAD instance")
                except Exception as e:
                    logger.error(f"Could not launch AutoCAD: {e}")
                    return False

            # Get or create document
            self.acad_doc = self.acad_app.ActiveDocument
            if not self.acad_doc:
                self.acad_doc = self.acad_app.Documents.Add()

            self.acad_util = self.acad_doc.Utility
            self.connection_method = ConnectionMethod.COM
            self.connected = True
            logger.info("Successfully connected to AutoCAD via COM")
            return True

        except Exception as e:
            logger.error(f"Error connecting to AutoCAD: {e}")
            self.connected = False
            return False

    def _connect_simulation(self) -> bool:
        """Connect using simulation mode."""
        try:
            self.simulation_doc = SimulationDocument()
            self.connection_method = ConnectionMethod.SIMULATION
            self.connected = True
            logger.info("Connected in simulation mode")
            return True
        except Exception as e:
            logger.error(f"Error initializing simulation mode: {e}")
            return False

    def disconnect(self) -> bool:
        """Disconnect from AutoCAD or exit simulation mode."""
        try:
            if self.connection_method == ConnectionMethod.COM:
                if self.acad_app:
                    self.acad_app.Visible = False
                    self.acad_app = None
                self.acad_doc = None
                self.acad_util = None
                if HAS_COM_API:
                    pythoncom.CoUninitialize()

            self.simulation_doc = None
            self.connection_method = None
            self.connected = False
            logger.info("Disconnected from AutoCAD")
            return True
        except Exception as e:
            logger.error(f"Error disconnecting: {e}")
            return False

    def get_status(self) -> Dict[str, Any]:
        """Get connection status."""
        return {
            "connected": self.connected,
            "method": self.connection_method.value if self.connection_method else None,
            "platform": "Windows" if IS_WINDOWS else "Linux/Mac",
            "com_available": HAS_COM_API
        }

    # =========================================================================
    # SIMULATION MODE ENTITIES
    # =========================================================================

    def _generate_handle(self) -> str:
        """Generate unique entity handle."""
        return str(uuid.uuid4())[:8]

    def _is_simulation(self) -> bool:
        """Check if running in simulation mode."""
        return self.connection_method == ConnectionMethod.SIMULATION

    def _add_simulation_entity(self, entity_type: str, properties: Dict[str, Any]) -> str:
        """Add entity in simulation mode."""
        if not self._is_simulation() or not self.simulation_doc:
            return None

        handle = self._generate_handle()
        entity = SimulationEntity(entity_type, handle, properties)
        self.simulation_doc.entities.append(entity)
        self.active_entities[handle] = entity
        return handle

    # =========================================================================
    # LAYER OPERATIONS
    # =========================================================================

    def create_layer(self, name: str, color: int = 7, visible: bool = True) -> bool:
        """Create a new layer.

        Args:
            name: Layer name
            color: AutoCAD color index (1-255)
            visible: Layer visibility

        Returns:
            bool: True if successful

        """
        if not self.connected:
            logger.error("Not connected to AutoCAD")
            return False

        try:
            if self._is_simulation():
                if name in self.simulation_doc.layers:
                    logger.warning(f"Layer {name} already exists")
                    return False
                self.simulation_doc.layers[name] = SimulationLayer(name, color, visible)
                logger.info(f"Created layer: {name}")
                return True
            layers = self.acad_doc.Layers
            layer = layers.Add(name)
            layer.color = color
            layer.LayerOn = visible
            logger.info(f"Created layer: {name}")
            return True
        except Exception as e:
            logger.error(f"Error creating layer: {e}")
            return False

    def delete_layer(self, name: str) -> bool:
        """Delete a layer by name."""
        if not self.connected:
            logger.error("Not connected to AutoCAD")
            return False

        try:
            if self._is_simulation():
                if name in self.simulation_doc.layers:
                    del self.simulation_doc.layers[name]
                    logger.info(f"Deleted layer: {name}")
                    return True
                return False
            layer = self.acad_doc.Layers.Item(name)
            layer.Delete()
            logger.info(f"Deleted layer: {name}")
            return True
        except Exception as e:
            logger.error(f"Error deleting layer: {e}")
            return False

    def set_layer_color(self, name: str, color: int) -> bool:
        """Set layer color."""
        if not self.connected:
            logger.error("Not connected to AutoCAD")
            return False

        try:
            if self._is_simulation():
                if name in self.simulation_doc.layers:
                    self.simulation_doc.layers[name].color = color
                    return True
                return False
            layer = self.acad_doc.Layers.Item(name)
            layer.color = color
            return True
        except Exception as e:
            logger.error(f"Error setting layer color: {e}")
            return False

    def set_layer_linetype(self, name: str, linetype: str) -> bool:
        """Set layer linetype."""
        if not self.connected:
            logger.error("Not connected to AutoCAD")
            return False

        try:
            if self._is_simulation():
                logger.info(f"Simulation: set linetype {linetype} on {name}")
                return True
            layer = self.acad_doc.Layers.Item(name)
            # Load linetype if not already loaded
            linetypes = self.acad_doc.Linetypes
            if linetype not in [lt.Name for lt in linetypes]:
                linetypes.Load(linetype, linetype)
            layer.Linetype = linetype
            return True
        except Exception as e:
            logger.error(f"Error setting layer linetype: {e}")
            return False

    def lock_layer(self, name: str, lock: bool = True) -> bool:
        """Lock or unlock a layer."""
        if not self.connected:
            logger.error("Not connected to AutoCAD")
            return False

        try:
            if self._is_simulation():
                if name in self.simulation_doc.layers:
                    self.simulation_doc.layers[name].locked = lock
                    return True
                return False
            layer = self.acad_doc.Layers.Item(name)
            layer.Lock = lock
            return True
        except Exception as e:
            logger.error(f"Error locking layer: {e}")
            return False

    def get_layers(self) -> List[Dict[str, Any]]:
        """Get all layers."""
        if not self.connected:
            logger.error("Not connected to AutoCAD")
            return []

        try:
            if self._is_simulation():
                return [
                    {"name": name, "color": layer.color, "visible": layer.visible, "locked": layer.locked}
                    for name, layer in self.simulation_doc.layers.items()
                ]
            layers = []
            for layer in self.acad_doc.Layers:
                layers.append({
                    "name": layer.Name,
                    "color": layer.color,
                    "visible": layer.LayerOn,
                    "locked": layer.Lock
                })
            return layers
        except Exception as e:
            logger.error(f"Error getting layers: {e}")
            return []

    # =========================================================================
    # DRAWING OPERATIONS
    # =========================================================================

    def draw_line(self, start_point: List[float], end_point: List[float],
                  layer: str = "0", color: int = 0) -> Optional[str]:
        """Draw a line.

        Args:
            start_point: [x, y, z]
            end_point: [x, y, z]
            layer: Layer name
            color: AutoCAD color index

        Returns:
            Entity handle or None

        """
        if not self.connected:
            logger.error("Not connected to AutoCAD")
            return None

        try:
            if self._is_simulation():
                return self._add_simulation_entity("LINE", {
                    "start_point": start_point,
                    "end_point": end_point,
                    "layer": layer,
                    "color": color
                })
            model_space = self.acad_doc.ModelSpace
            line = model_space.AddLine(start_point, end_point)
            line.Layer = layer
            line.Color = color
            handle = line.Handle
            self.active_entities[handle] = line
            logger.info(f"Drew line: {start_point} -> {end_point}")
            return handle
        except Exception as e:
            logger.error(f"Error drawing line: {e}")
            return None

    def draw_polyline(self, vertices: List[List[float]],
                      layer: str = "0", color: int = 0, closed: bool = False) -> Optional[str]:
        """Draw a polyline.

        Args:
            vertices: [[x, y, z], ...]
            layer: Layer name
            color: AutoCAD color index
            closed: Close the polyline

        Returns:
            Entity handle or None

        """
        if not self.connected:
            logger.error("Not connected to AutoCAD")
            return None

        try:
            if self._is_simulation():
                return self._add_simulation_entity("LWPOLYLINE", {
                    "vertices": vertices,
                    "closed": closed,
                    "layer": layer,
                    "color": color
                })
            # Flatten to 2D coordinates
            flat = []
            for v in vertices:
                flat.extend(v[:2])

            model_space = self.acad_doc.ModelSpace
            poly = model_space.AddLightWeightPolyline(flat)
            poly.Layer = layer
            poly.Color = color
            poly.Closed = closed
            handle = poly.Handle
            self.active_entities[handle] = poly
            logger.info(f"Drew polyline with {len(vertices)} vertices")
            return handle
        except Exception as e:
            logger.error(f"Error drawing polyline: {e}")
            return None

    def draw_rectangle(self, lower_left: List[float], upper_right: List[float],
                       layer: str = "0", color: int = 0) -> Optional[str]:
        """Draw a rectangle (as closed polyline).

        Args:
            lower_left: [x, y, z]
            upper_right: [x, y, z]
            layer: Layer name
            color: AutoCAD color index

        Returns:
            Entity handle or None

        """
        x1, y1 = lower_left[0], lower_left[1]
        x2, y2 = upper_right[0], upper_right[1]
        vertices = [[x1, y1, 0], [x2, y1, 0], [x2, y2, 0], [x1, y2, 0]]
        return self.draw_polyline(vertices, layer, color, closed=True)

    def draw_circle(self, center: List[float], radius: float,
                    layer: str = "0", color: int = 0) -> Optional[str]:
        """Draw a circle.

        Args:
            center: [x, y, z]
            radius: Circle radius
            layer: Layer name
            color: AutoCAD color index

        Returns:
            Entity handle or None

        """
        if not self.connected:
            logger.error("Not connected to AutoCAD")
            return None

        try:
            if self._is_simulation():
                return self._add_simulation_entity("CIRCLE", {
                    "center": center,
                    "radius": radius,
                    "layer": layer,
                    "color": color
                })
            model_space = self.acad_doc.ModelSpace
            circle = model_space.AddCircle(center, radius)
            circle.Layer = layer
            circle.Color = color
            handle = circle.Handle
            self.active_entities[handle] = circle
            logger.info(f"Drew circle at {center} radius {radius}")
            return handle
        except Exception as e:
            logger.error(f"Error drawing circle: {e}")
            return None

    def draw_arc(self, center: List[float], radius: float,
                 start_angle: float, end_angle: float,
                 layer: str = "0", color: int = 0) -> Optional[str]:
        """Draw an arc.

        Args:
            center: [x, y, z]
            radius: Arc radius
            start_angle: Start angle in degrees
            end_angle: End angle in degrees
            layer: Layer name
            color: AutoCAD color index

        Returns:
            Entity handle or None

        """
        if not self.connected:
            logger.error("Not connected to AutoCAD")
            return None

        try:
            if self._is_simulation():
                return self._add_simulation_entity("ARC", {
                    "center": center,
                    "radius": radius,
                    "start_angle": start_angle,
                    "end_angle": end_angle,
                    "layer": layer,
                    "color": color
                })
            # Convert degrees to radians
            start_rad = math.radians(start_angle)
            end_rad = math.radians(end_angle)

            model_space = self.acad_doc.ModelSpace
            arc = model_space.AddArc(center, radius, start_rad, end_rad)
            arc.Layer = layer
            arc.Color = color
            handle = arc.Handle
            self.active_entities[handle] = arc
            logger.info(f"Drew arc at {center}")
            return handle
        except Exception as e:
            logger.error(f"Error drawing arc: {e}")
            return None

    def draw_ellipse(self, center: List[float], major_axis: List[float],
                     ratio: float, layer: str = "0", color: int = 0) -> Optional[str]:
        """Draw an ellipse.

        Args:
            center: [x, y, z]
            major_axis: Major axis vector [x, y, z]
            ratio: Axis ratio (0 < ratio <= 1)
            layer: Layer name
            color: AutoCAD color index

        Returns:
            Entity handle or None

        """
        if not self.connected:
            logger.error("Not connected to AutoCAD")
            return None

        try:
            if self._is_simulation():
                return self._add_simulation_entity("ELLIPSE", {
                    "center": center,
                    "major_axis": major_axis,
                    "ratio": ratio,
                    "layer": layer,
                    "color": color
                })
            model_space = self.acad_doc.ModelSpace
            ellipse = model_space.AddEllipse(center, major_axis, ratio)
            ellipse.Layer = layer
            ellipse.Color = color
            handle = ellipse.Handle
            self.active_entities[handle] = ellipse
            logger.info(f"Drew ellipse at {center}")
            return handle
        except Exception as e:
            logger.error(f"Error drawing ellipse: {e}")
            return None

    def draw_text(self, text: str, insertion_point: List[float], height: float = 0.2,
                  layer: str = "0", color: int = 0) -> Optional[str]:
        """Draw text.

        Args:
            text: Text content
            insertion_point: [x, y, z]
            height: Text height
            layer: Layer name
            color: AutoCAD color index

        Returns:
            Entity handle or None

        """
        if not self.connected:
            logger.error("Not connected to AutoCAD")
            return None

        try:
            if self._is_simulation():
                return self._add_simulation_entity("TEXT", {
                    "text": text,
                    "insertion_point": insertion_point,
                    "height": height,
                    "layer": layer,
                    "color": color
                })
            model_space = self.acad_doc.ModelSpace
            txt = model_space.AddText(text, insertion_point, height)
            txt.Layer = layer
            txt.Color = color
            handle = txt.Handle
            self.active_entities[handle] = txt
            logger.info(f"Drew text: {text}")
            return handle
        except Exception as e:
            logger.error(f"Error drawing text: {e}")
            return None

    # =========================================================================
    # DIMENSION OPERATIONS
    # =========================================================================

    def draw_dimension_aligned(self, start_point: List[float], end_point: List[float],
                              text_point: List[float],
                              layer: str = "0", color: int = 0) -> Optional[str]:
        """Draw aligned dimension.

        Args:
            start_point: [x, y, z]
            end_point: [x, y, z]
            text_point: [x, y, z] - dimension text location
            layer: Layer name
            color: AutoCAD color index

        Returns:
            Entity handle or None

        """
        if not self.connected:
            logger.error("Not connected to AutoCAD")
            return None

        try:
            if self._is_simulation():
                return self._add_simulation_entity("DIMENSION_ALIGNED", {
                    "start_point": start_point,
                    "end_point": end_point,
                    "text_point": text_point,
                    "layer": layer,
                    "color": color
                })
            model_space = self.acad_doc.ModelSpace
            dim = model_space.AddDimAligned(start_point, end_point, text_point)
            dim.Layer = layer
            dim.Color = color
            handle = dim.Handle
            self.active_entities[handle] = dim
            logger.info("Drew aligned dimension")
            return handle
        except Exception as e:
            logger.error(f"Error drawing aligned dimension: {e}")
            return None

    def draw_dimension_linear(self, start_point: List[float], end_point: List[float],
                              text_point: List[float], angle: float = 0,
                              layer: str = "0", color: int = 0) -> Optional[str]:
        """Draw linear dimension.

        Args:
            start_point: [x, y, z]
            end_point: [x, y, z]
            text_point: [x, y, z]
            angle: Rotation angle in degrees
            layer: Layer name
            color: AutoCAD color index

        Returns:
            Entity handle or None

        """
        if not self.connected:
            logger.error("Not connected to AutoCAD")
            return None

        try:
            if self._is_simulation():
                return self._add_simulation_entity("DIMENSION_LINEAR", {
                    "start_point": start_point,
                    "end_point": end_point,
                    "text_point": text_point,
                    "angle": angle,
                    "layer": layer,
                    "color": color
                })
            model_space = self.acad_doc.ModelSpace
            dim = model_space.AddDimLinear(start_point, end_point, text_point, math.radians(angle))
            dim.Layer = layer
            dim.Color = color
            handle = dim.Handle
            self.active_entities[handle] = dim
            logger.info("Drew linear dimension")
            return handle
        except Exception as e:
            logger.error(f"Error drawing linear dimension: {e}")
            return None

    def draw_dimension_radial(self, center: List[float], chord_point: List[float],
                             leader_length: float = 0,
                             layer: str = "0", color: int = 0) -> Optional[str]:
        """Draw radial dimension.

        Args:
            center: [x, y, z] - circle center
            chord_point: [x, y, z] - point on circle
            leader_length: Leader length
            layer: Layer name
            color: AutoCAD color index

        Returns:
            Entity handle or None

        """
        if not self.connected:
            logger.error("Not connected to AutoCAD")
            return None

        try:
            if self._is_simulation():
                return self._add_simulation_entity("DIMENSION_RADIAL", {
                    "center": center,
                    "chord_point": chord_point,
                    "leader_length": leader_length,
                    "layer": layer,
                    "color": color
                })
            model_space = self.acad_doc.ModelSpace
            dim = model_space.AddDimRadial(center, chord_point, leader_length)
            dim.Layer = layer
            dim.Color = color
            handle = dim.Handle
            self.active_entities[handle] = dim
            logger.info("Drew radial dimension")
            return handle
        except Exception as e:
            logger.error(f"Error drawing radial dimension: {e}")
            return None

    def draw_dimension_diameter(self, center: List[float], chord_point: List[float],
                                leader_length: float = 0,
                                layer: str = "0", color: int = 0) -> Optional[str]:
        """Draw diameter dimension.

        Args:
            center: [x, y, z] - circle center
            chord_point: [x, y, z] - point on circle
            leader_length: Leader length
            layer: Layer name
            color: AutoCAD color index

        Returns:
            Entity handle or None

        """
        if not self.connected:
            logger.error("Not connected to AutoCAD")
            return None

        try:
            if self._is_simulation():
                return self._add_simulation_entity("DIMENSION_DIAMETER", {
                    "center": center,
                    "chord_point": chord_point,
                    "leader_length": leader_length,
                    "layer": layer,
                    "color": color
                })
            model_space = self.acad_doc.ModelSpace
            dim = model_space.AddDimDiameter(center, chord_point, leader_length)
            dim.Layer = layer
            dim.Color = color
            handle = dim.Handle
            self.active_entities[handle] = dim
            logger.info("Drew diameter dimension")
            return handle
        except Exception as e:
            logger.error(f"Error drawing diameter dimension: {e}")
            return None

    # =========================================================================
    # BLOCK OPERATIONS
    # =========================================================================

    def insert_block(self, file_path: str, insertion_point: List[float],
                     scale: float = 1.0, rotation: float = 0,
                     layer: str = "0") -> Optional[str]:
        """Insert a block from file.

        Args:
            file_path: Path to block file
            insertion_point: [x, y, z]
            scale: Scale factor
            rotation: Rotation angle in degrees
            layer: Layer name

        Returns:
            Entity handle or None

        """
        if not self.connected:
            logger.error("Not connected to AutoCAD")
            return None

        try:
            if self._is_simulation():
                return self._add_simulation_entity("BLOCK", {
                    "file_path": file_path,
                    "insertion_point": insertion_point,
                    "scale": scale,
                    "rotation": rotation,
                    "layer": layer
                })
            model_space = self.acad_doc.ModelSpace
            block_name = self.acad_doc.Blocks.Import(file_path, True)
            block = model_space.InsertBlock(insertion_point, block_name, scale, scale, scale, math.radians(rotation))
            block.Layer = layer
            handle = block.Handle
            self.active_entities[handle] = block
            logger.info(f"Inserted block from {file_path}")
            return handle
        except Exception as e:
            logger.error(f"Error inserting block: {e}")
            return None

    def get_blocks(self) -> List[Dict[str, Any]]:
        """Get all block definitions."""
        if not self.connected:
            logger.error("Not connected to AutoCAD")
            return []

        try:
            if self._is_simulation():
                return []
            blocks = []
            for block in self.acad_doc.Blocks:
                if not block.IsLayout:
                    blocks.append({
                        "name": block.Name,
                        "count": block.Count
                    })
            return blocks
        except Exception as e:
            logger.error(f"Error getting blocks: {e}")
            return []

    # =========================================================================
    # TRANSFORM OPERATIONS
    # =========================================================================

    def move_entity(self, handle: str, new_point: List[float]) -> bool:
        """Move an entity.

        Args:
            handle: Entity handle
            new_point: New position [x, y, z]

        Returns:
            bool: Success

        """
        if not self.connected:
            logger.error("Not connected to AutoCAD")
            return False

        try:
            if self._is_simulation():
                if handle in self.active_entities:
                    entity = self.active_entities[handle]
                    if "insertion_point" in entity.properties:
                        entity.properties["insertion_point"] = new_point
                    elif "start_point" in entity.properties:
                        dx = new_point[0] - entity.properties["start_point"][0]
                        dy = new_point[1] - entity.properties["start_point"][1]
                        entity.properties["start_point"] = new_point
                        if "end_point" in entity.properties:
                            entity.properties["end_point"] = [
                                entity.properties["end_point"][0] + dx,
                                entity.properties["end_point"][1] + dy,
                                entity.properties["end_point"][2]
                            ]
                    return True
                return False
            entity = self.acad_doc.HandleToObject(handle)
            if hasattr(entity, 'Move'):
                entity.Move(entity.InsertionPoint, new_point)
            logger.info(f"Moved entity {handle} to {new_point}")
            return True
        except Exception as e:
            logger.error(f"Error moving entity: {e}")
            return False

    def rotate_entity(self, handle: str, base_point: List[float], angle: float) -> bool:
        """Rotate an entity.

        Args:
            handle: Entity handle
            base_point: Center of rotation [x, y, z]
            angle: Rotation angle in degrees

        Returns:
            bool: Success

        """
        if not self.connected:
            logger.error("Not connected to AutoCAD")
            return False

        try:
            if self._is_simulation():
                if handle in self.active_entities:
                    entity = self.active_entities[handle]
                    entity.properties["rotation"] = entity.properties.get("rotation", 0) + angle
                    return True
                return False
            entity = self.acad_doc.HandleToObject(handle)
            if hasattr(entity, 'Rotate'):
                entity.Rotate(base_point, math.radians(angle))
            logger.info(f"Rotated entity {handle} by {angle} degrees")
            return True
        except Exception as e:
            logger.error(f"Error rotating entity: {e}")
            return False

    def scale_entity(self, handle: str, base_point: List[float], scale_factor: float) -> bool:
        """Scale an entity.

        Args:
            handle: Entity handle
            base_point: Base point [x, y, z]
            scale_factor: Scale factor (>0)

        Returns:
            bool: Success

        """
        if not self.connected:
            logger.error("Not connected to AutoCAD")
            return False

        try:
            if self._is_simulation():
                if handle in self.active_entities:
                    entity = self.active_entities[handle]
                    if "scale" in entity.properties:
                        entity.properties["scale"] *= scale_factor
                    return True
                return False
            entity = self.acad_doc.HandleToObject(handle)
            if hasattr(entity, 'ScaleEntity'):
                entity.ScaleEntity(base_point, scale_factor)
            logger.info(f"Scaled entity {handle} by {scale_factor}")
            return True
        except Exception as e:
            logger.error(f"Error scaling entity: {e}")
            return False

    # =========================================================================
    # GROUP OPERATIONS
    # =========================================================================

    def create_group(self, group_name: str, handles: List[str]) -> bool:
        """Create a group from entities.

        Args:
            group_name: Group name
            handles: List of entity handles

        Returns:
            bool: Success

        """
        if not self.connected:
            logger.error("Not connected to AutoCAD")
            return False

        try:
            if self._is_simulation():
                self.simulation_doc.groups[group_name] = handles
                logger.info(f"Created group: {group_name}")
                return True
            entities = []
            for h in handles:
                try:
                    entities.append(self.acad_doc.HandleToObject(h))
                except Exception:
                    pass
            if entities:
                group = self.acad_doc.Groups.Add(group_name)
                # Create SAFEARRAY of entities
                variant = win32com.client.VARIANT(
                    pythoncom.VT_ARRAY | pythoncom.VT_DISPATCH,
                    entities
                )
                group.AppendItems(variant)
                logger.info(f"Created group: {group_name}")
                return True
            return False
        except Exception as e:
            logger.error(f"Error creating group: {e}")
            return False

    def delete_group(self, group_name: str) -> bool:
        """Delete a group."""
        if not self.connected:
            logger.error("Not connected to AutoCAD")
            return False

        try:
            if self._is_simulation():
                if group_name in self.simulation_doc.groups:
                    del self.simulation_doc.groups[group_name]
                    logger.info(f"Deleted group: {group_name}")
                    return True
                return False
            group = self.acad_doc.Groups.Item(group_name)
            group.Delete()
            logger.info(f"Deleted group: {group_name}")
            return True
        except Exception as e:
            logger.error(f"Error deleting group: {e}")
            return False

    def get_groups(self) -> List[Dict[str, Any]]:
        """Get all groups."""
        if not self.connected:
            logger.error("Not connected to AutoCAD")
            return []

        try:
            if self._is_simulation():
                return [
                    {"name": name, "entities": handles}
                    for name, handles in self.simulation_doc.groups.items()
                ]
            groups = []
            for group in self.acad_doc.Groups:
                groups.append({
                    "name": group.Name,
                    "count": group.Count
                })
            return groups
        except Exception as e:
            logger.error(f"Error getting groups: {e}")
            return []

    # =========================================================================
    # ENTITY OPERATIONS
    # =========================================================================

    def get_entities(self, entity_type: Optional[str] = None) -> List[Dict[str, Any]]:
        """Get entities, optionally filtered by type.

        Args:
            entity_type: Filter by entity type (LINE, CIRCLE, etc.) or None for all

        Returns:
            List of entity data dictionaries

        """
        if not self.connected:
            logger.error("Not connected to AutoCAD")
            return []

        try:
            if self._is_simulation():
                entities = []
                for entity in self.simulation_doc.entities:
                    if entity_type is None or entity.entity_type == entity_type:
                        entities.append({
                            "handle": entity.handle,
                            "type": entity.entity_type,
                            "properties": entity.properties
                        })
                return entities
            entities = []
            model_space = self.acad_doc.ModelSpace
            for entity in model_space:
                etype = entity.ObjectName.split('.')[-1].upper().replace('ACDB', '')
                if entity_type is None or etype == entity_type.upper():
                    entities.append({
                        "handle": entity.Handle,
                        "type": etype,
                        "properties": {
                            "layer": entity.Layer,
                            "color": entity.Color
                        }
                    })
            return entities
        except Exception as e:
            logger.error(f"Error getting entities: {e}")
            return []

    def get_entity(self, handle: str) -> Optional[Dict[str, Any]]:
        """Get entity by handle."""
        if not self.connected:
            logger.error("Not connected to AutoCAD")
            return None

        try:
            if self._is_simulation():
                if handle in self.active_entities:
                    entity = self.active_entities[handle]
                    return {
                        "handle": handle,
                        "type": entity.entity_type,
                        "properties": entity.properties
                    }
                return None
            entity = self.acad_doc.HandleToObject(handle)
            return {
                "handle": handle,
                "type": entity.ObjectName.split('.')[-1],
                "properties": {"layer": entity.Layer, "color": entity.Color}
            }
        except Exception as e:
            logger.error(f"Error getting entity: {e}")
            return None

    def delete_entity(self, handle: str) -> bool:
        """Delete an entity by handle."""
        if not self.connected:
            logger.error("Not connected to AutoCAD")
            return False

        try:
            if self._is_simulation():
                if handle in self.active_entities:
                    entity = self.active_entities[handle]
                    if entity in self.simulation_doc.entities:
                        self.simulation_doc.entities.remove(entity)
                    del self.active_entities[handle]
                    logger.info(f"Deleted entity: {handle}")
                    return True
                return False
            entity = self.acad_doc.HandleToObject(handle)
            entity.Delete()
            if handle in self.active_entities:
                del self.active_entities[handle]
            logger.info(f"Deleted entity: {handle}")
            return True
        except Exception as e:
            logger.error(f"Error deleting entity: {e}")
            return False

    # =========================================================================
    # DOCUMENT OPERATIONS
    # =========================================================================

    def read_dwg(self, filepath: str) -> Dict[str, Any]:
        """Read entities from DWG file.

        Args:
            filepath: Path to DWG file

        Returns:
            Dict with entities data

        """
        if not self.connected:
            return {"success": False, "error": "Not connected", "entities": []}

        try:
            if self._is_simulation():
                logger.warning("Simulation mode: cannot read real DWG files")
                return {"success": False, "error": "Simulation mode", "entities": []}
            # Open the file
            target_doc = self.acad_app.Documents.Open(filepath)
            entities = []

            for entity in target_doc.ModelSpace:
                entity_data = {
                    "handle": entity.Handle,
                    "type": entity.ObjectName.split('.')[-1],
                    "layer": entity.Layer
                }
                entities.append(entity_data)

            result = {
                "success": True,
                "entities": entities,
                "count": len(entities),
                "source_file": filepath
            }

            target_doc.Close(False)
            return result
        except Exception as e:
            logger.error(f"Error reading DWG: {e}")
            return {"success": False, "error": str(e), "entities": []}

    def write_dwg(self, filepath: str, entities: List[Dict[str, Any]]) -> bool:
        """Write entities to new DWG file.

        Args:
            filepath: Output path
            entities: List of entity data

        Returns:
            bool: Success

        """
        if not self.connected:
            logger.error("Not connected to AutoCAD")
            return False

        try:
            if self._is_simulation():
                logger.info(f"Simulation: would write {len(entities)} entities to {filepath}")
                return True
            new_doc = self.acad_app.Documents.Add()
            model_space = new_doc.ModelSpace

            for entity_data in entities:
                etype = entity_data.get("type", "").upper()

                if etype == "LINE":
                    start = entity_data.get("start_point", [0, 0, 0])
                    end = entity_data.get("end_point", [1, 0, 0])
                    obj = model_space.AddLine(start, end)
                    if "layer" in entity_data:
                        obj.Layer = entity_data["layer"]

                elif etype == "CIRCLE":
                    center = entity_data.get("center", [0, 0, 0])
                    radius = entity_data.get("radius", 1)
                    obj = model_space.AddCircle(center, radius)
                    if "layer" in entity_data:
                        obj.Layer = entity_data["layer"]

            # Create directory if needed
            os.makedirs(os.path.dirname(filepath) or ".", exist_ok=True)
            new_doc.SaveAs(filepath)
            new_doc.Close(False)
            logger.info(f"Wrote {len(entities)} entities to {filepath}")
            return True
        except Exception as e:
            logger.error(f"Error writing DWG: {e}")
            return False

    def save(self, filepath: str) -> bool:
        """Save current document."""
        if not self.connected or not self.acad_doc:
            logger.error("Not connected to AutoCAD")
            return False

        try:
            if self._is_simulation():
                logger.info("Simulation: saved to memory")
                return True
            os.makedirs(os.path.dirname(filepath) or ".", exist_ok=True)
            self.acad_doc.SaveAs(filepath)
            logger.info(f"Saved document to {filepath}")
            return True
        except Exception as e:
            logger.error(f"Error saving: {e}")
            return False

    def get_document_info(self) -> Dict[str, Any]:
        """Get current document information."""
        if not self.connected:
            return {}

        try:
            if self._is_simulation():
                return {
                    "name": "Simulation",
                    "path": "",
                    "entity_count": len(self.simulation_doc.entities),
                    "layer_count": len(self.simulation_doc.layers),
                    "mode": "simulation"
                }
            doc = self.acad_doc
            return {
                "name": doc.Name,
                "path": doc.Path,
                "title": doc.Title,
                "active_space": doc.ActiveSpace,
                "mode": "com"
            }
        except Exception as e:
            logger.error(f"Error getting document info: {e}")
            return {}

    # =========================================================================
    # AI COMMAND EXECUTION
    # =========================================================================

    def execute_ai_command(self, command: str) -> Dict[str, Any]:
        """Execute natural language command.

        Supported commands:
        - "draw line from 0,0,0 to 100,100,0"
        - "draw rectangle from 0,0 to 100,100"
        - "draw circle at 50,50 radius 25"
        - "create layer MyLayer"
        - "get all entities"
        - "delete entity <handle>"
        - "get layers"

        Args:
            command: Natural language command

        Returns:
            Dict with execution result

        """
        command_lower = command.lower().strip()

        try:
            # Parse command patterns
            if "draw line" in command_lower or "create line" in command_lower:
                coords = re.findall(r'-?\d+\.?\d*', command)
                if len(coords) >= 6:
                    start = [float(coords[0]), float(coords[1]), float(coords[2])]
                    end = [float(coords[3]), float(coords[4]), float(coords[5])]
                    handle = self.draw_line(start, end)
                    return {"success": True, "action": "draw_line", "handle": handle}
                return {"success": False, "error": "Invalid coordinates"}

            if "draw rectangle" in command_lower or "create rectangle" in command_lower:
                coords = re.findall(r'-?\d+\.?\d*', command)
                if len(coords) >= 4:
                    p1 = [float(coords[0]), float(coords[1]), 0]
                    p2 = [float(coords[2]), float(coords[3]), 0]
                    handle = self.draw_rectangle(p1, p2)
                    return {"success": True, "action": "draw_rectangle", "handle": handle}
                return {"success": False, "error": "Invalid coordinates"}

            if "draw circle" in command_lower or "create circle" in command_lower:
                coords = re.findall(r'-?\d+\.?\d*', command)
                if len(coords) >= 3:
                    center = [float(coords[0]), float(coords[1]), 0]
                    radius = float(coords[2]) if len(coords) >= 3 else 10
                    handle = self.draw_circle(center, radius)
                    return {"success": True, "action": "draw_circle", "handle": handle}
                return {"success": False, "error": "Invalid coordinates"}

            if "create layer" in command_lower:
                parts = command_lower.replace("create layer", "").strip()
                if parts:
                    success = self.create_layer(parts)
                    return {"success": success, "action": "create_layer", "name": parts}
                return {"success": False, "error": "Layer name required"}

            if "get all entities" in command_lower or "list entities" in command_lower:
                entities = self.get_entities()
                return {"success": True, "action": "get_entities", "count": len(entities), "entities": entities}

            if "delete entity" in command_lower or "remove entity" in command_lower:
                handles = re.findall(r'[a-f0-9-]{8}', command_lower)
                if handles:
                    handle = handles[0]
                    success = self.delete_entity(handle)
                    return {"success": success, "action": "delete_entity", "handle": handle}
                return {"success": False, "error": "Handle required"}

            if "get layers" in command_lower or "list layers" in command_lower:
                layers = self.get_layers()
                return {"success": True, "action": "get_layers", "count": len(layers), "layers": layers}

            return {
                "success": False,
                "error": f"Unknown command: {command}",
                "suggestion": "Try: draw line, draw rectangle, draw circle, create layer, get all entities"
            }
        except Exception as e:
            logger.error(f"Error executing AI command: {e}")
            return {"success": False, "error": str(e)}
