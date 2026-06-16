"""
backend/services/autocad_service.py — AutoCAD Integration Service
================================================================

COMPLETE AutoCAD integration including:
- COM connection management
- DWG/DXF file parsing
- Drawing commands (create elements)
- Modification commands (edit elements)
- Configuration management

ARCHITECTURE:
- ConnectionManager: Handles AutoCAD process detection and COM connection
- DWGReader: Reads and parses DWG/DXF files using ezdxf library
- DrawingEngine: Creates and modifies AutoCAD drawings
- ConfigManager: Persists AutoCAD configuration settings

DEPENDENCIES:
- ezdxf: DXF/DWG file parsing (no AutoCAD installation required)
- pywin32: COM automation (requires AutoCAD installed)
- comtypes: Alternative COM library

USAGE:
    from backend.services.autocad_service import AutoCADService
    service = AutoCADService()
    service.connect()
    service.read_dwg("drawing.dwg")
    service.draw_line((0, 0), (10, 10))
    service.save()
"""

from __future__ import annotations

import logging
import os
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

logger = logging.getLogger(__name__)

# Try to import ezdxf for DXF/DWG parsing (works without AutoCAD)
try:
    import ezdxf  # type: ignore[import-untyped]
    from ezdxf.addons import odafc  # type: ignore[import-untyped]
    EZDXF_AVAILABLE = True
except ImportError:
    EZDXF_AVAILABLE = False
    logger.warning("ezdxf not available — DXF parsing disabled")

# Try to import COM libraries for AutoCAD automation (requires AutoCAD)
try:
    import win32com.client  # type: ignore[import-untyped]
    import pythoncom  # type: ignore[import-untyped]
    COM_AVAILABLE = True
except ImportError:
    COM_AVAILABLE = False
    logger.warning("pywin32 not available — COM automation disabled")


# ═══════════════════════════════════════════════════════════════════════════════
# DATA MODELS
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class AutoCADConfig:
    """Configuration for AutoCAD connection and operations."""
    
    # Connection settings
    acad_path: str = ""  # Path to AutoCAD executable
    acad_version: str = ""  # e.g., "2024", "2023"
    com_class_id: str = "AutoCAD.Application"  # COM class ID
    
    # File settings
    default_template: str = ""  # Default .dwt template file
    default_units: str = "Millimeters"  # Drawing units
    save_format: str = "DWG"  # DWG or DXF
    
    # Layer standards
    default_layer: str = "0"
    layer_colors: Dict[str, str] = field(default_factory=lambda: {
        "Walls": "Red",
        "Doors": "Green",
        "Windows": "Blue",
        "Dimensions": "Yellow",
        "Text": "White",
    })
    
    # Plot settings
    plot_style: str = "acad.ctb"
    paper_size: str = "A1"
    
    # Working directory
    working_dir: str = ""
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "acad_path": self.acad_path,
            "acad_version": self.acad_version,
            "com_class_id": self.com_class_id,
            "default_template": self.default_template,
            "default_units": self.default_units,
            "save_format": self.save_format,
            "default_layer": self.default_layer,
            "layer_colors": self.layer_colors,
            "plot_style": self.plot_style,
            "paper_size": self.paper_size,
            "working_dir": self.working_dir,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> AutoCADConfig:
        """Create from dictionary."""
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


@dataclass
class AutoCADEntity:
    """Represents an AutoCAD entity (line, circle, text, etc.)."""
    
    entity_type: str  # "LINE", "CIRCLE", "TEXT", "LWPOLYLINE", etc.
    layer: str = "0"
    color: int = 256  # 256 = BYLAYER
    properties: Dict[str, Any] = field(default_factory=dict)
    
    # Geometry data (varies by entity type)
    start_point: Optional[Tuple[float, float, float]] = None
    end_point: Optional[Tuple[float, float, float]] = None
    center: Optional[Tuple[float, float, float]] = None
    radius: Optional[float] = None
    text_content: Optional[str] = None
    vertices: Optional[List[Tuple[float, float, float]]] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "entity_type": self.entity_type,
            "layer": self.layer,
            "color": self.color,
            "properties": self.properties,
            "start_point": self.start_point,
            "end_point": self.end_point,
            "center": self.center,
            "radius": self.radius,
            "text_content": self.text_content,
            "vertices": self.vertices,
        }


# ═══════════════════════════════════════════════════════════════════════════════
# CONNECTION MANAGER
# ═══════════════════════════════════════════════════════════════════════════════

class AutoCADConnectionManager:
    """
    Manages AutoCAD COM connections.
    
    Supports:
    - Multiple AutoCAD instances
    - Version detection
    - Reconnection on failure
    - Process detection
    """
    
    def __init__(self, config: AutoCADConfig):
        self.config = config
        self._acad_app: Optional[Any] = None
        self._doc: Optional[Any] = None
        self._connected = False
        self._reconnect_attempts = 0
        self._max_reconnect_attempts = 3
        
    def is_autocad_running(self) -> bool:
        """Check if AutoCAD process is running."""
        if not COM_AVAILABLE:
            return False

        try:
            pythoncom.CoInitialize()  # type: ignore[possibly-unbound]
            acad_app = win32com.client.GetActiveObject(self.config.com_class_id)  # type: ignore[possibly-unbound]
            return acad_app is not None
        except Exception:
            return False
        finally:
            pythoncom.CoUninitialize()  # type: ignore[possibly-unbound]
    
    def find_autocad_installations(self) -> List[Dict[str, str]]:
        """Find all AutoCAD installations on the system."""
        installations = []
        
        # Common AutoCAD installation paths
        possible_paths = [
            r"C:\Program Files\Autodesk\AutoCAD 2024",
            r"C:\Program Files\Autodesk\AutoCAD 2023",
            r"C:\Program Files\Autodesk\AutoCAD 2022",
            r"C:\Program Files\Autodesk\AutoCAD 2021",
            r"C:\Program Files\Autodesk\AutoCAD 2020",
        ]
        
        for path in possible_paths:
            if os.path.exists(path):
                acad_exe = os.path.join(path, "acad.exe")
                if os.path.exists(acad_exe):
                    # Extract version from path
                    version = path.split()[-1]
                    installations.append({
                        "path": path,
                        "version": version,
                        "exe": acad_exe,
                    })
        
        return installations
    
    def connect(self, force_new: bool = False) -> bool:
        """
        Connect to AutoCAD via COM.
        
        Args:
            force_new: If True, start new AutoCAD instance even if one exists
        
        Returns:
            True if connection successful, False otherwise
        """
        if not COM_AVAILABLE:
            logger.error("COM automation not available (pywin32 not installed)")
            return False
        
        try:
            pythoncom.CoInitialize()  # type: ignore[possibly-unbound]

            if force_new or not self.is_autocad_running():
                # Start new AutoCAD instance
                logger.info("Starting new AutoCAD instance...")
                self._acad_app = win32com.client.Dispatch(self.config.com_class_id)  # type: ignore[possibly-unbound]
                self._acad_app.Visible = True
            else:
                # Connect to existing instance
                logger.info("Connecting to existing AutoCAD instance...")
                self._acad_app = win32com.client.GetActiveObject(self.config.com_class_id)  # type: ignore[possibly-unbound]

            # Get active document or create new one
            assert self._acad_app is not None
            if self._acad_app.Documents.Count == 0:
                if self.config.default_template and os.path.exists(self.config.default_template):
                    self._doc = self._acad_app.Documents.Open(self.config.default_template)
                else:
                    self._doc = self._acad_app.Documents.Add()
            else:
                self._doc = self._acad_app.ActiveDocument

            self._connected = True
            self._reconnect_attempts = 0
            logger.info(f"Connected to AutoCAD {self._acad_app.Version}")
            return True

        except Exception as e:
            logger.error(f"Failed to connect to AutoCAD: {e}")
            self._connected = False
            return False
        finally:
            pythoncom.CoUninitialize()  # type: ignore[possibly-unbound]
    
    def reconnect(self) -> bool:
        """Attempt to reconnect if connection lost."""
        if self._reconnect_attempts >= self._max_reconnect_attempts:
            logger.error("Max reconnection attempts reached")
            return False
        
        self._reconnect_attempts += 1
        logger.info(f"Reconnection attempt {self._reconnect_attempts}/{self._max_reconnect_attempts}")
        
        return self.connect(force_new=True)
    
    def disconnect(self):
        """Disconnect from AutoCAD."""
        if self._acad_app:
            try:
                # Save and close document
                if self._doc:
                    self._doc.Save()
                
                # Quit AutoCAD (optional — may want to keep it running)
                # self._acad_app.Quit()
                
                self._connected = False
                logger.info("Disconnected from AutoCAD")
            except Exception as e:
                logger.error(f"Error disconnecting: {e}")
    
    @property
    def is_connected(self) -> bool:
        """Check if connected to AutoCAD."""
        return self._connected and self._acad_app is not None
    
    @property
    def acad_app(self) -> Any:
        """Get AutoCAD application object."""
        if not self.is_connected:
            raise RuntimeError("Not connected to AutoCAD")
        return self._acad_app
    
    @property
    def doc(self) -> Any:
        """Get active document."""
        if not self.is_connected or self._doc is None:
            raise RuntimeError("No active document")
        return self._doc


# ═══════════════════════════════════════════════════════════════════════════════
# DWG/DXF READER
# ═══════════════════════════════════════════════════════════════════════════════

class DWGReader:
    """
    Reads and parses DWG/DXF files using ezdxf library.
    
    Supports:
    - DWG and DXF formats
    - All entity types (lines, circles, text, blocks, etc.)
    - Layer extraction
    - Block definitions
    - Metadata extraction
    """
    
    def __init__(self):
        if not EZDXF_AVAILABLE:
            raise RuntimeError("ezdxf library not available — install with: pip install ezdxf")
    
    def read_file(self, filepath: str) -> Dict[str, Any]:
        """
        Read a DWG/DXF file and extract all entities.
        
        Args:
            filepath: Path to DWG/DXF file
        
        Returns:
            Dictionary with extracted data:
            {
                "metadata": {...},
                "layers": [...],
                "entities": [...],
                "blocks": {...}
            }
        """
        path = Path(filepath)
        
        if not path.exists():
            raise FileNotFoundError(f"File not found: {path}")
        
        # Determine file type
        suffix = path.suffix.lower()
        if suffix == ".dxf":
            doc = ezdxf.readfile(str(path))  # type: ignore[possibly-unbound,attr-defined]
        elif suffix == ".dwg":
            try:
                doc = ezdxf.readfile(str(path))  # type: ignore[possibly-unbound,attr-defined]
            except Exception:
                if odafc.is_available():  # type: ignore[possibly-unbound,attr-defined]
                    dxf_path = path.with_suffix(".dxf")
                    odafc.convert(str(path), str(dxf_path))  # type: ignore[possibly-unbound,attr-defined]
                    doc = ezdxf.readfile(str(dxf_path))  # type: ignore[possibly-unbound,attr-defined]
                    dxf_path.unlink()
                else:
                    raise RuntimeError("Cannot read DWG — ODA File Converter not available")
        else:
            raise ValueError(f"Unsupported file format: {suffix}")
        
        metadata = self._extract_metadata(doc)
        layers = self._extract_layers(doc)
        entities = self._extract_entities(doc)
        blocks = self._extract_blocks(doc)
        
        return {
            "metadata": metadata,
            "layers": layers,
            "entities": entities,
            "blocks": blocks,
            "filepath": str(path),
        }
    
    def _extract_metadata(self, doc: Any) -> Dict[str, Any]:
        """Extract file metadata."""
        header = doc.header
        return {
            "filename": doc.filename,
            "dxfversion": header.get("$ACADVER", "Unknown"),
            "encoding": doc.encoding,
            "units": header.get("$INSUNITS", 0),
        }
    
    def _extract_layers(self, doc: Any) -> List[Dict[str, Any]]:
        """Extract all layers from document."""
        layers = []
        for layer in doc.layers:
            layers.append({
                "name": layer.dxf.name,
                "color": layer.dxf.color,
                "linetype": layer.dxf.linetype,
                "lineweight": layer.dxf.lineweight,
                "is_on": layer.is_on,
                "is_frozen": layer.is_frozen,
            })
        return layers
    
    def _extract_entities(self, doc: Any) -> List[Dict[str, Any]]:
        """Extract all entities from modelspace."""
        entities = []
        msp = doc.modelspace()
        
        for entity in msp:
            entity_data = self._parse_entity(entity)
            if entity_data:
                entities.append(entity_data)
        
        return entities
    
    def _parse_entity(self, entity: Any) -> Optional[Dict[str, Any]]:
        """Parse a single entity into dictionary."""
        dxftype = entity.dxftype()
        
        base_data = {
            "type": dxftype,
            "layer": entity.dxf.layer,
            "color": entity.dxf.color if hasattr(entity.dxf, "color") else 256,
        }
        
        # Parse based on entity type
        if dxftype == "LINE":
            base_data.update({
                "start": tuple(entity.dxf.start),
                "end": tuple(entity.dxf.end),
            })
        elif dxftype == "CIRCLE":
            base_data.update({
                "center": tuple(entity.dxf.center),
                "radius": entity.dxf.radius,
            })
        elif dxftype == "ARC":
            base_data.update({
                "center": tuple(entity.dxf.center),
                "radius": entity.dxf.radius,
                "start_angle": entity.dxf.start_angle,
                "end_angle": entity.dxf.end_angle,
            })
        elif dxftype == "TEXT":
            base_data.update({
                "text": entity.dxf.text,
                "insert": tuple(entity.dxf.insert),
                "height": entity.dxf.height,
                "rotation": entity.dxf.rotation if hasattr(entity.dxf, "rotation") else 0,
            })
        elif dxftype == "LWPOLYLINE":
            points = list(entity.get_points(format="xy"))
            base_data.update({
                "vertices": points,
                "closed": entity.closed,
            })
        elif dxftype == "INSERT":  # Block reference
            base_data.update({
                "block_name": entity.dxf.name,
                "insert": tuple(entity.dxf.insert),
                "xscale": entity.dxf.xscale if hasattr(entity.dxf, "xscale") else 1.0,
                "yscale": entity.dxf.yscale if hasattr(entity.dxf, "yscale") else 1.0,
                "rotation": entity.dxf.rotation if hasattr(entity.dxf, "rotation") else 0,
            })
        elif dxftype == "DIMENSION":
            base_data.update({
                "text": entity.dxf.text if hasattr(entity.dxf, "text") else "",
                "defpoint": tuple(entity.dxf.defpoint) if hasattr(entity.dxf, "defpoint") else None,
            })
        else:
            # Generic entity — store raw DXF attributes
            base_data["raw_attributes"] = {
                attr: str(getattr(entity.dxf, attr, None))
                for attr in dir(entity.dxf)
                if not attr.startswith("_")
            }
        
        return base_data
    
    def _extract_blocks(self, doc: Any) -> Dict[str, List[Dict[str, Any]]]:
        """Extract all block definitions."""
        blocks = {}
        
        for block in doc.blocks:
            block_entities = []
            for entity in block:
                entity_data = self._parse_entity(entity)
                if entity_data:
                    block_entities.append(entity_data)
            
            blocks[block.name] = block_entities
        
        return blocks


# ═══════════════════════════════════════════════════════════════════════════════
# DRAWING ENGINE
# ═══════════════════════════════════════════════════════════════════════════════

class AutoCADDrawingEngine:
    """
    Creates and modifies AutoCAD drawings via COM automation.
    
    Supports:
    - Creating new drawings from templates
    - Drawing primitives (lines, circles, text, etc.)
    - Modifying existing entities
    - Layer management
    - Block operations
    """
    
    def __init__(self, connection: AutoCADConnectionManager):
        self.conn = connection
    
    def draw_line(self, start: Tuple[float, float], end: Tuple[float, float], 
                  layer: str = "0", color: int = 256) -> str:
        """
        Draw a line in the active document.
        
        Args:
            start: Start point (x, y)
            end: End point (x, y)
            layer: Layer name
            color: Color index (256 = BYLAYER)
        
        Returns:
            Handle of created entity
        """
        if not self.conn.is_connected:
            raise RuntimeError("Not connected to AutoCAD")
        
        doc = self.conn.doc
        msp = doc.ModelSpace
        
        # Create 3D points (z=0 for 2D)
        start_3d = self._to_3d_point(start)
        end_3d = self._to_3d_point(end)
        
        # Add line
        line = msp.AddLine(start_3d, end_3d)
        
        # Set properties
        line.Layer = layer
        if color != 256:
            line.Color = color
        
        return line.Handle
    
    def draw_circle(self, center: Tuple[float, float], radius: float,
                    layer: str = "0", color: int = 256) -> str:
        """Draw a circle."""
        if not self.conn.is_connected:
            raise RuntimeError("Not connected to AutoCAD")
        
        doc = self.conn.doc
        msp = doc.ModelSpace
        
        center_3d = self._to_3d_point(center)
        circle = msp.AddCircle(center_3d, radius)
        
        circle.Layer = layer
        if color != 256:
            circle.Color = color
        
        return circle.Handle
    
    def draw_arc(self, center: Tuple[float, float], radius: float,
                 start_angle: float, end_angle: float,
                 layer: str = "0", color: int = 256) -> str:
        """Draw an arc (angles in degrees)."""
        if not self.conn.is_connected:
            raise RuntimeError("Not connected to AutoCAD")
        
        doc = self.conn.doc
        msp = doc.ModelSpace
        
        center_3d = self._to_3d_point(center)
        
        # Convert degrees to radians for AutoCAD
        import math
        start_rad = math.radians(start_angle)
        end_rad = math.radians(end_angle)
        
        arc = msp.AddArc(center_3d, radius, start_rad, end_rad)
        
        arc.Layer = layer
        if color != 256:
            arc.Color = color
        
        return arc.Handle
    
    def draw_text(self, text: str, insert_point: Tuple[float, float],
                  height: float = 2.5, rotation: float = 0,
                  layer: str = "0", color: int = 256) -> str:
        """Draw single-line text."""
        if not self.conn.is_connected:
            raise RuntimeError("Not connected to AutoCAD")
        
        doc = self.conn.doc
        msp = doc.ModelSpace
        
        insert_3d = self._to_3d_point(insert_point)
        
        # Add text
        text_obj = msp.AddText(text, insert_3d, height)
        text_obj.Rotation = rotation
        text_obj.Layer = layer
        
        if color != 256:
            text_obj.Color = color
        
        return text_obj.Handle
    
    def draw_polyline(self, points: List[Tuple[float, float]], closed: bool = False,
                      layer: str = "0", color: int = 256) -> str:
        """Draw a lightweight polyline."""
        if not self.conn.is_connected:
            raise RuntimeError("Not connected to AutoCAD")
        
        doc = self.conn.doc
        msp = doc.ModelSpace
        
        # Convert to 3D points
        points_3d = [self._to_3d_point(p) for p in points]
        
        # Create polyline
        polyline = msp.AddLightWeightPolyline(points_3d)
        
        if closed:
            polyline.Closed = True
        
        polyline.Layer = layer
        if color != 256:
            polyline.Color = color
        
        return polyline.Handle
    
    def insert_block(self, block_name: str, insert_point: Tuple[float, float],
                     xscale: float = 1.0, yscale: float = 1.0, rotation: float = 0,
                     layer: str = "0") -> str:
        """Insert a block reference."""
        if not self.conn.is_connected:
            raise RuntimeError("Not connected to AutoCAD")
        
        doc = self.conn.doc
        msp = doc.ModelSpace
        
        insert_3d = self._to_3d_point(insert_point)
        
        # Insert block
        block_ref = msp.InsertBlock(insert_3d, block_name, xscale, yscale, 1.0, rotation)
        block_ref.Layer = layer
        
        return block_ref.Handle
    
    def modify_entity(self, handle: str, **properties) -> bool:
        """
        Modify an existing entity by handle.
        
        Args:
            handle: Entity handle
            properties: Properties to modify (layer, color, etc.)
        
        Returns:
            True if successful
        """
        if not self.conn.is_connected:
            raise RuntimeError("Not connected to AutoCAD")
        
        doc = self.conn.doc
        
        try:
            entity = doc.HandleToObject(handle)
            
            for prop, value in properties.items():
                if hasattr(entity, prop):
                    setattr(entity, prop, value)
                else:
                    logger.warning(f"Property '{prop}' not found on entity")
            
            return True
        except Exception as e:
            logger.error(f"Failed to modify entity {handle}: {e}")
            return False
    
    def delete_entity(self, handle: str) -> bool:
        """Delete an entity by handle."""
        if not self.conn.is_connected:
            raise RuntimeError("Not connected to AutoCAD")
        
        doc = self.conn.doc
        
        try:
            entity = doc.HandleToObject(handle)
            entity.Delete()
            return True
        except Exception as e:
            logger.error(f"Failed to delete entity {handle}: {e}")
            return False
    
    def add_layer(self, name: str, color: int = 7, linetype: str = "Continuous") -> bool:
        """Add a new layer to the document."""
        if not self.conn.is_connected:
            raise RuntimeError("Not connected to AutoCAD")
        
        doc = self.conn.doc
        
        try:
            layers = doc.Layers
            layer = layers.Add(name)
            layer.Color = color
            layer.Linetype = linetype
            return True
        except Exception as e:
            logger.error(f"Failed to add layer {name}: {e}")
            return False
    
    def _to_3d_point(self, point_2d: Tuple[float, float]) -> Tuple[float, float, float]:
        """Convert 2D point to 3D (z=0)."""
        return (point_2d[0], point_2d[1], 0.0)
    
    def save(self, filepath: Optional[str] = None):
        """Save the active document."""
        if not self.conn.is_connected:
            raise RuntimeError("Not connected to AutoCAD")
        
        doc = self.conn.doc
        
        if filepath:
            doc.SaveAs(filepath)
        else:
            doc.Save()
    
    def close(self, save: bool = True):
        """Close the active document."""
        if not self.conn.is_connected:
            return
        
        doc = self.conn.doc
        
        if save:
            doc.Save()
        
        doc.Close()


# ═══════════════════════════════════════════════════════════════════════════════
# MAIN SERVICE
# ═══════════════════════════════════════════════════════════════════════════════

class AutoCADService:
    """
    Main AutoCAD service — orchestrates connection, reading, and drawing.
    
    Usage:
        service = AutoCADService()
        service.initialize()
        
        # Read a file
        data = service.read_dwg("input.dwg")
        
        # Draw something
        service.draw_line((0, 0), (10, 10))
        service.draw_circle((5, 5), 3)
        
        # Save
        service.save("output.dwg")
    """
    
    def __init__(self, config: Optional[AutoCADConfig] = None):
        self.config = config or AutoCADConfig()
        self.connection = AutoCADConnectionManager(self.config)
        self.reader = DWGReader() if EZDXF_AVAILABLE else None
        self.drawing_engine: Optional[AutoCADDrawingEngine] = None
    
    def initialize(self) -> bool:
        """Initialize the service — connect to AutoCAD."""
        if not self.connection.connect():
            return False
        
        self.drawing_engine = AutoCADDrawingEngine(self.connection)
        return True
    
    def read_dwg(self, filepath: str) -> Dict[str, Any]:
        """Read a DWG/DXF file and extract entities."""
        if not self.reader:
            raise RuntimeError("DWG reader not available (ezdxf not installed)")
        
        return self.reader.read_file(filepath)
    
    def draw_line(self, start: Tuple[float, float], end: Tuple[float, float], **kwargs) -> str:
        """Draw a line."""
        if not self.drawing_engine:
            raise RuntimeError("Drawing engine not initialized")
        return self.drawing_engine.draw_line(start, end, **kwargs)
    
    def draw_circle(self, center: Tuple[float, float], radius: float, **kwargs) -> str:
        """Draw a circle."""
        if not self.drawing_engine:
            raise RuntimeError("Drawing engine not initialized")
        return self.drawing_engine.draw_circle(center, radius, **kwargs)
    
    def draw_text(self, text: str, insert: Tuple[float, float], **kwargs) -> str:
        """Draw text."""
        if not self.drawing_engine:
            raise RuntimeError("Drawing engine not initialized")
        return self.drawing_engine.draw_text(text, insert, **kwargs)
    
    def save(self, filepath: Optional[str] = None):
        """Save the current drawing."""
        if not self.drawing_engine:
            raise RuntimeError("Drawing engine not initialized")
        self.drawing_engine.save(filepath)
    
    def shutdown(self):
        """Shutdown the service — disconnect from AutoCAD."""
        if self.connection.is_connected:
            self.connection.disconnect()


# ═══════════════════════════════════════════════════════════════════════════════
# CONFIGURATION MANAGER
# ═══════════════════════════════════════════════════════════════════════════════

class AutoCADConfigManager:
    """Manages AutoCAD configuration persistence."""
    
    CONFIG_FILE = "autocad_config.json"
    
    def __init__(self, config_dir: Optional[str] = None):
        self.config_dir = Path(config_dir or os.getenv("AUTOCAD_CONFIG_DIR", "."))
        self.config_file = self.config_dir / self.CONFIG_FILE
    
    def load(self) -> AutoCADConfig:
        """Load configuration from file."""
        if not self.config_file.exists():
            return AutoCADConfig()
        
        import json
        with open(self.config_file, "r") as f:
            data = json.load(f)
        
        return AutoCADConfig.from_dict(data)
    
    def save(self, config: AutoCADConfig):
        """Save configuration to file."""
        import json
        
        self.config_dir.mkdir(parents=True, exist_ok=True)
        
        with open(self.config_file, "w") as f:
            json.dump(config.to_dict(), f, indent=2)
    
    def get_default(self) -> AutoCADConfig:
        """Get default configuration."""
        return AutoCADConfig()
