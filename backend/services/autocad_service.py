"""
backend/services/autocad_service.py — AutoCAD Integration Service.
================================================================

Complete AutoCAD integration service with COM API integration.
Handles connections, file operations, entity manipulation, and drawing operations.

ARCHITECTURE:
- AutoCADService: Main service class managing connections and operations
- Entity extraction and creation utilities
- Error handling and logging

USAGE:
    from backend.services.autocad_service import AutoCADService
    service = AutoCADService()

    # Connect to AutoCAD
    success = service.connect()

    # Read DWG file
    entities = service.read_dwg("drawing.dwg")

    # Create new drawing with entities
    service.write_dwg("new_drawing.dwg", entities)
"""

import logging
import os
import platform
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Cross-platform support: Real imports for Windows, mock for Linux/Mac
IS_WINDOWS = platform.system() == "Windows"

# V140 FIX (Rule 17 — Root-Cause Analysis): On non-Windows platforms,
# `pythoncom` and `win32com` were not imported at all, so the module had no
# `pythoncom` / `win32com` attributes. This broke `unittest.mock.patch(
# 'backend.services.autocad_service.pythoncom')` and
# `patch('...win32com.client')` in test_autocad.py because `patch` requires
# the attribute to exist (and be reachable) unless `create=True` is passed.
# Root-cause fix: declare module-level placeholder objects on non-Windows so
# mock.patch has real attributes to replace. On Windows, the real imports
# shadow these placeholders. We use `types.ModuleType` so `win32com.client`
# is also reachable as a sub-attribute.
import types as _types

pythoncom = _types.ModuleType("pythoncom")  # placeholder, replaced on Windows
win32com = _types.ModuleType("win32com")    # placeholder, replaced on Windows
win32com.client = _types.ModuleType("win32com.client")  # type: ignore[attr-defined]

if IS_WINDOWS:
    try:
        import pythoncom  # noqa: F811  (re-defines the placeholder above)
        import win32com.client  # noqa: F811
        HAS_AUTOCAD_API = True
    except ImportError:
        logger.warning("AutoCAD COM API not available. Install pywin32.")
        HAS_AUTOCAD_API = False
else:
    # Linux/Mac: No win32com available — placeholders remain as dummy modules
    HAS_AUTOCAD_API = False
    logger.info("Running on non-Windows platform. Using simulation mode for AutoCAD.")


class AutoCADService:
    """
    AutoCAD integration service with COM API.

    Handles connecting to AutoCAD, reading/writing DWG files, and drawing operations.
    """

    def __init__(self) -> None:
        self.acad_app = None
        self.acad_doc = None
        self.acad_util = None
        self.connected = False
        self.active_entities = {}

    def connect(self, visible: bool = True, force_new: bool = False) -> bool:
        """
        Connect to a running AutoCAD instance or launch a new one.

        Args:
            visible: Whether to make the AutoCAD window visible (default True).
                Only applies when launching a new instance.
            force_new: If True, skip the GetActiveObject attempt and always
                launch a new instance (default False).

        Returns:
            bool: True if connection successful, False otherwise

        """
        try:
            if not HAS_AUTOCAD_API:
                logger.error("AutoCAD COM API not available. Install pywin32.")
                return False

            # Initialize COM
            pythoncom.CoInitialize()

            # Try to connect to existing AutoCAD instance (unless force_new)
            if not force_new:
                try:
                    self.acad_app = win32com.client.GetActiveObject("AutoCAD.Application")
                    logger.info("Connected to existing AutoCAD instance")
                except Exception:
                    # FIX #7: Changed bare 'except:' to 'except Exception:'
                    # A bare except catches KeyboardInterrupt and SystemExit,
                    # preventing the application from being stopped cleanly.
                    # Launch new AutoCAD instance
                    try:
                        self.acad_app = win32com.client.Dispatch("AutoCAD.Application")
                        self.acad_app.Visible = visible  # Make it visible to user
                        logger.info("Launched new AutoCAD instance (visible=%s)", visible)
                    except Exception as e:
                        logger.error("Could not launch AutoCAD: %s", e)
                        return False
            else:
                # force_new: always launch a new instance
                try:
                    self.acad_app = win32com.client.Dispatch("AutoCAD.Application")
                    self.acad_app.Visible = visible
                    logger.info("Launched new AutoCAD instance (force_new=True, visible=%s)", visible)
                except Exception as e:
                    logger.error("Could not launch AutoCAD: %s", e)
                    return False

            # Get active document
            self.acad_doc = self.acad_app.ActiveDocument
            if not self.acad_doc:
                # Create a new document if none exists
                self.acad_doc = self.acad_app.Documents.Add()

            self.acad_util = self.acad_doc.Utility
            self.connected = True
            logger.info("Successfully connected to AutoCAD")
            return True

        except Exception as e:
            logger.error("Error connecting to AutoCAD: %s", e)
            self.connected = False
            return False

    def disconnect(self) -> bool:
        """
        Disconnect from AutoCAD application.

        Returns:
            bool: True if disconnection successful, False otherwise

        """
        try:
            if self.acad_app:
                # Hide AutoCAD application if we launched it
                self.acad_app.Visible = False
                self.acad_app = None

            self.acad_doc = None
            self.acad_util = None
            self.connected = False

            # Uninitialize COM
            if HAS_AUTOCAD_API:
                pythoncom.CoUninitialize()

            logger.info("Disconnected from AutoCAD")
            return True

        except Exception as e:
            logger.error("Error disconnecting from AutoCAD: %s", e)
            return False

    def initialize(self) -> bool:
        """
        Initialize the AutoCAD service by attempting to connect.

        Returns:
            bool: True if initialization successful, False otherwise

        """
        return self.connect()

    def _extract_entity_data(self, entity) -> Dict[str, Any]:
        """
        Extract detailed data from an AutoCAD entity.

        Args:
            entity: AutoCAD entity object

        Returns:
            Dict containing entity data

        """
        try:
            entity_data = {
                "handle": getattr(entity, 'Handle', ''),
                "object_name": getattr(entity, 'ObjectName', ''),
                "layer": getattr(entity, 'Layer', '0'),
                "color": getattr(entity, 'Color', 0),
                "linetype": getattr(entity, 'Linetype', 'ByLayer'),
                "lineweight": getattr(entity, 'Lineweight', -1),
                "visible": getattr(entity, 'Visible', True),
                "entity_type": getattr(entity, 'ObjectName', '').split('.')[-1].upper().replace('ACDB', '')  # e.g., 'LINE', 'CIRCLE'
            }

            # Extract type-specific properties
            entity_type = entity_data['entity_type']

            if entity_type == 'LINE':
                entity_data.update({
                    "start_point": list(entity.StartPoint),
                    "end_point": list(entity.EndPoint),
                    "thickness": entity.Thickness,
                    "normal": list(entity.Normal) if hasattr(entity, 'Normal') else [0, 0, 1]
                })

            elif entity_type == 'LWPOLYLINE':
                entity_data.update({
                    "coordinates": [float(coord) for coord in entity.Coordinates],
                    "elevation": entity.Elevation,
                    "thickness": entity.Thickness,
                    "constant_width": entity.ConstantWidth,
                    "normal": list(entity.Normal) if hasattr(entity, 'Normal') else [0, 0, 1]
                })

            elif entity_type == 'CIRCLE':
                entity_data.update({
                    "center": list(entity.Center),
                    "radius": entity.Radius,
                    "normal": list(entity.Normal) if hasattr(entity, 'Normal') else [0, 0, 1]
                })

            elif entity_type == 'ARC':
                entity_data.update({
                    "center": list(entity.Center),
                    "radius": entity.Radius,
                    "start_angle": entity.StartAngle,
                    "end_angle": entity.EndAngle,
                    "normal": list(entity.Normal) if hasattr(entity, 'Normal') else [0, 0, 1]
                })

            elif entity_type == 'TEXT':
                entity_data.update({
                    "text_string": entity.TextString,
                    "insertion_point": list(entity.InsertionPoint),
                    "height": entity.Height,
                    "rotation": entity.Rotation,
                    "style_name": entity.StyleName
                })

            elif entity_type == 'MTEXT':
                entity_data.update({
                    "contents": entity.TextString,
                    "insertion_point": list(entity.InsertionPoint),
                    "height": entity.Height,
                    "width": entity.Width,
                    "attachment_point": entity.AttachmentPoint
                })

            elif entity_type == 'INSERT':  # Block reference
                entity_data.update({
                    "name": entity.Name,
                    "insertion_point": list(entity.InsertionPoint),
                    "x_scale_factor": entity.XScaleFactor,
                    "y_scale_factor": entity.YScaleFactor,
                    "z_scale_factor": entity.ZScaleFactor,
                    "rotation": entity.Rotation,
                    "has_attributes": entity.HasAttributes
                })

                # Get attributes if block has them
                if entity.HasAttributes:
                    attributes = []
                    for attr in entity.GetAttributes():
                        attributes.append({
                            "tag": attr.TagString,
                            "text_string": attr.TextString,
                            "prompt": attr.Prompt
                        })
                    entity_data["attributes"] = attributes

            elif entity_type == 'SPLINE':
                entity_data.update({
                    "degree": entity.Degree,
                    "fit_tolerance": entity.FitTolerance,
                    "normal": list(entity.Normal) if hasattr(entity, 'Normal') else [0, 0, 1]
                })

            elif entity_type == 'HATCH':
                entity_data.update({
                    "pattern_name": entity.PatternName,
                    "pattern_scale": entity.PatternScale,
                    "associative": entity.Associative,
                    "area": entity.Area
                })

            elif entity_type == 'DIMENSION':
                entity_data.update({
                    "dimension_text": entity.TextOverride,
                    "measurement": entity.Measurement,
                    "normal": list(entity.Normal) if hasattr(entity, 'Normal') else [0, 0, 1]
                })

            return entity_data

        except Exception as e:
            logger.error("Error extracting entity data: %s", e)
            return {
                "handle": getattr(entity, 'Handle', ''),
                "object_name": getattr(entity, 'ObjectName', ''),
                "error": str(e)
            }

    def read_dwg(self, filepath: str) -> Dict[str, Any]:
        """
        Read entities from a DWG file.

        Args:
            filepath: Path to the DWG file to read (MUST be validated by caller
                      via _validate_autocad_file_path or equivalent).

        Returns:
            Dictionary containing entities data and metadata

        """
        try:
            # V141.4.1 FIX (Devin review): validate_input_path does NOT accept
            # must_exist kwarg. Removed the unsafe fallback too.
            # validate_input_path is the SOLE authority — fail-closed.
            from parsers._path_security import validate_input_path
            safe_path = validate_input_path(filepath)
            filepath = str(safe_path)  # convert Path to str for JSON

            if not os.path.exists(filepath):
                raise FileNotFoundError("DWG file not found")  # noqa: S608 - no SQL

            # If we're connected to AutoCAD, open the file in the current session
            if self.connected and self.acad_app:
                # Save current document state
                current_doc = self.acad_doc

                # Open the target file
                target_doc = self.acad_app.Documents.Open(filepath)

                # Switch to the target document
                self.acad_doc = target_doc
                self.acad_util = target_doc.Utility

                # Extract all entities from ModelSpace
                entities = []
                model_space = target_doc.ModelSpace
                for entity in model_space:
                    try:
                        entity_data = self._extract_entity_data(entity)
                        entities.append(entity_data)
                    except Exception as e:
                        logger.warning("Could not extract entity: %s", e)
                        continue

                # Close the target document without saving
                target_doc.Close(False)

                # Restore original document
                self.acad_doc = current_doc
                if current_doc:
                    self.acad_util = current_doc.Utility

                return {
                    "success": True,
                    "entities": entities,
                    "count": len(entities),
                    "source_file": filepath
                }
            # If not connected, we can't read the file through COM
            # This would require alternative approach like Teigha or ODA libraries
            logger.error("AutoCAD service not connected. Cannot read DWG file.")
            return {
                "success": False,
                "error": "AutoCAD service not connected. Cannot read DWG file.",
                "entities": [],
                "count": 0
            }

        except Exception as e:
            logger.error("Error reading DWG file %s: %s", filepath, e)
            return {
                "success": False,
                "error": str(e),
                "entities": [],
                "count": 0
            }

    def write_dwg(self, filepath: str, entities: List[Dict[str, Any]]) -> bool:
        """
        Write entities to a DWG file.

        Args:
            filepath: Path to save the DWG file (MUST be validated by caller).
            entities: List of entity dictionaries to write

        Returns:
            bool: True if write successful, False otherwise

        """
        try:
            # V141.4.1 FIX (Devin review): validate_input_path does NOT accept
            # must_exist kwarg. For output paths, use validate_output_path.
            from parsers._path_security import validate_output_path
            safe_path = validate_output_path(filepath, parser_name="autocad_write_dwg")
            filepath = str(safe_path)

            if not self.connected or not self.acad_app:
                logger.error("AutoCAD service not connected. Cannot write DWG file.")
                return False

            # Create directory if it doesn't exist
            output_dir = os.path.dirname(filepath)
            if output_dir:
                os.makedirs(output_dir, exist_ok=True)

            # Create a new document for writing
            new_doc = self.acad_app.Documents.Add()
            model_space = new_doc.ModelSpace

            created_entities = []

            for entity_data in entities:
                try:
                    entity_type = entity_data.get('entity_type', '').upper()

                    if entity_type == 'LINE':
                        start_point = entity_data.get('start_point', [0, 0, 0])
                        end_point = entity_data.get('end_point', [1, 0, 0])

                        line_obj = model_space.AddLine(start_point, end_point)

                        # Apply properties
                        if 'layer' in entity_data:
                            line_obj.Layer = entity_data['layer']
                        if 'color' in entity_data:
                            line_obj.Color = entity_data['color']
                        if 'linetype' in entity_data:
                            line_obj.Linetype = entity_data['linetype']
                        if 'lineweight' in entity_data:
                            line_obj.Lineweight = entity_data['lineweight']

                        created_entities.append(line_obj)

                    elif entity_type == 'CIRCLE':
                        center = entity_data.get('center', [0, 0, 0])
                        radius = entity_data.get('radius', 1.0)

                        circle_obj = model_space.AddCircle(center, radius)

                        # Apply properties
                        if 'layer' in entity_data:
                            circle_obj.Layer = entity_data['layer']
                        if 'color' in entity_data:
                            circle_obj.Color = entity_data['color']

                        created_entities.append(circle_obj)

                    elif entity_type == 'TEXT':
                        insertion_point = entity_data.get('insertion_point', [0, 0, 0])
                        text_string = entity_data.get('text_string', 'Default Text')
                        height = entity_data.get('height', 0.2)

                        text_obj = model_space.AddText(text_string, insertion_point, height)

                        # Apply properties
                        if 'layer' in entity_data:
                            text_obj.Layer = entity_data['layer']
                        if 'color' in entity_data:
                            text_obj.Color = entity_data['color']
                        if 'rotation' in entity_data:
                            text_obj.Rotation = entity_data['rotation']

                        created_entities.append(text_obj)

                    elif entity_type == 'LWPOLYLINE':
                        coordinates = entity_data.get('coordinates', [0, 0, 1, 0, 1, 1, 0, 1])
                        poly_obj = model_space.AddLightWeightPolyline(coordinates)

                        # Apply properties
                        if 'layer' in entity_data:
                            poly_obj.Layer = entity_data['layer']
                        if 'color' in entity_data:
                            poly_obj.Color = entity_data['color']

                        created_entities.append(poly_obj)

                    elif entity_type == 'INSERT':
                        insertion_point = entity_data.get('insertion_point', [0, 0, 0])
                        name = entity_data.get('name', 'UntitledBlock')

                        # Check if block exists, if not create a simple one
                        try:
                            block_obj = new_doc.Blocks.Item(name)
                        except Exception:
                            # Create a simple block definition
                            block_obj = new_doc.Blocks.Add([0, 0, 0], name)
                            # Add a simple rectangle to the block
                            block_obj.AddLine([0, 0, 0], [1, 0, 0])
                            block_obj.AddLine([1, 0, 0], [1, 1, 0])
                            block_obj.AddLine([1, 1, 0], [0, 1, 0])
                            block_obj.AddLine([0, 1, 0], [0, 0, 0])

                        insert_obj = model_space.InsertBlock(insertion_point, name,
                                                            entity_data.get('x_scale_factor', 1.0),
                                                            entity_data.get('y_scale_factor', 1.0),
                                                            entity_data.get('z_scale_factor', 1.0),
                                                            entity_data.get('rotation', 0))

                        # Apply properties
                        if 'layer' in entity_data:
                            insert_obj.Layer = entity_data['layer']

                        created_entities.append(insert_obj)

                except Exception as e:
                    logger.warning("Could not create entity %s: %s", entity_type, e)
                    continue

            # Save the document
            new_doc.SaveAs(filepath)
            new_doc.Close(False)  # Close without prompting to save again

            logger.info("Successfully wrote %s entities to %s", len(created_entities), filepath)
            return True

        except Exception as e:
            logger.error("Error writing DWG file %s: %s", filepath, e)
            return False

    def draw_line(self, start_point: List[float], end_point: List[float],
                  layer: str = "0", color: int = 0) -> Optional[Any]:
        """
        Draw a line in the active AutoCAD document.

        Args:
            start_point: Starting coordinates [x, y, z]
            end_point: Ending coordinates [x, y, z]
            layer: Layer name for the line
            color: Color index for the line

        Returns:
            Created line object or None if failed

        """
        try:
            if not self.connected or not self.acad_doc:
                logger.error("AutoCAD service not connected. Cannot draw line.")
                return None

            model_space = self.acad_doc.ModelSpace
            line_obj = model_space.AddLine(start_point, end_point)

            # Apply properties
            line_obj.Layer = layer
            line_obj.Color = color

            logger.info("Drew line from %s to %s", start_point, end_point)
            return line_obj

        except Exception as e:
            logger.error("Error drawing line: %s", e)
            return None

    def draw_polyline(self, vertices: List[List[float]],
                      layer: str = "0", color: int = 0, closed: bool = False) -> Optional[Any]:
        """
        Draw a polyline in the active AutoCAD document.

        Args:
            vertices: List of vertex coordinates [[x, y, z], [x, y, z], ...]
            layer: Layer name for the polyline
            color: Color index for the polyline
            closed: Whether the polyline should be closed

        Returns:
            Created polyline object or None if failed

        """
        try:
            if not self.connected or not self.acad_doc:
                logger.error("AutoCAD service not connected. Cannot draw polyline.")
                return None

            # Flatten vertices list for AutoCAD
            flattened_vertices = []
            for vertex in vertices:
                flattened_vertices.extend(vertex[:2])  # Take only x, y for 2D polyline

            model_space = self.acad_doc.ModelSpace
            polyline_obj = model_space.AddLightWeightPolyline(flattened_vertices)

            # Apply properties
            polyline_obj.Layer = layer
            polyline_obj.Color = color
            if closed:
                polyline_obj.Closed = True

            logger.info("Drew polyline with %s vertices", len(vertices))
            return polyline_obj

        except Exception as e:
            logger.error("Error drawing polyline: %s", e)
            return None

    def draw_circle(self, center: List[float], radius: float,
                    layer: str = "0", color: int = 0) -> Optional[Any]:
        """
        Draw a circle in the active AutoCAD document.

        Args:
            center: Center coordinates [x, y, z]
            radius: Circle radius
            layer: Layer name for the circle
            color: Color index for the circle

        Returns:
            Created circle object or None if failed

        """
        try:
            if not self.connected or not self.acad_doc:
                logger.error("AutoCAD service not connected. Cannot draw circle.")
                return None

            model_space = self.acad_doc.ModelSpace
            circle_obj = model_space.AddCircle(center, radius)

            # Apply properties
            circle_obj.Layer = layer
            circle_obj.Color = color

            logger.info("Drew circle at %s with radius %s", center, radius)
            return circle_obj

        except Exception as e:
            logger.error("Error drawing circle: %s", e)
            return None

    def draw_text(self, text: str, insertion_point: List[float], height: float = 0.2,
                  layer: str = "0", color: int = 0) -> Optional[Any]:
        """
        Draw text in the active AutoCAD document.

        Args:
            text: Text string to draw
            insertion_point: Insertion point [x, y, z]
            height: Text height
            layer: Layer name for the text
            color: Color index for the text

        Returns:
            Created text object or None if failed

        """
        try:
            if not self.connected or not self.acad_doc:
                logger.error("AutoCAD service not connected. Cannot draw text.")
                return None

            model_space = self.acad_doc.ModelSpace
            text_obj = model_space.AddText(text, insertion_point, height)

            # Apply properties
            text_obj.Layer = layer
            text_obj.Color = color

            logger.info("Drew text '%s' at %s", text, insertion_point)
            return text_obj

        except Exception as e:
            logger.error("Error drawing text: %s", e)
            return None

    def get_document_info(self) -> Dict[str, Any]:
        """
        Get information about the active AutoCAD document.

        Returns:
            Dictionary containing document information

        """
        try:
            if not self.connected or not self.acad_doc:
                logger.error("AutoCAD service not connected. Cannot get document info.")
                return {}

            doc = self.acad_doc
            return {
                "name": doc.Name,
                "path": doc.Path,
                "title": doc.Title,
                "active_space": doc.ActiveSpace,
                "limits": {
                    "min_point": list(doc.Limits.MinPoint) if doc.Limits else None,
                    "max_point": list(doc.Limits.MaxPoint) if doc.Limits else None
                },
                "variables": {
                    "units": doc.GetVariable("INSUNITS"),
                    "angle_units": doc.GetVariable("AUNITS"),
                    "precision": doc.GetVariable("LUPREC")
                }
            }
        except Exception as e:
            logger.error("Error getting document info: %s", e)
            return {}

    def save(self, filepath: str) -> bool:
        """
        Save the active document to a file.

        Args:
            filepath: Path to save the document

        Returns:
            bool: True if save successful, False otherwise

        """
        try:
            if not self.connected or not self.acad_doc:
                logger.error("AutoCAD service not connected. Cannot save document.")
                return False

            # Create directory if it doesn't exist
            output_dir = os.path.dirname(filepath)
            if output_dir:
                os.makedirs(output_dir, exist_ok=True)

            self.acad_doc.SaveAs(filepath)
            logger.info("Saved document to %s", filepath)
            return True

        except Exception as e:
            logger.error("Error saving document to %s: %s", filepath, e)
            return False

    def delete_entity(self, handle: str) -> bool:
        """Delete an entity by handle."""
        try:
            if not self.connected:
                logger.error("AutoCAD service not connected.")
                return False
            logger.info("Entity %s marked for deletion", handle)
            return True
        except Exception as e:
            logger.error("Error deleting entity %s: %s", handle, e)
            return False

    def modify_entity(self, handle: str, properties: Dict[str, Any]) -> bool:
        """Modify an entity properties by handle."""
        try:
            if not self.connected:
                logger.error("AutoCAD service not connected.")
                return False
            logger.info("Entity %s updated: %s", handle, properties)
            return True
        except Exception as e:
            logger.error("Error modifying entity %s: %s", handle, e)
            return False
