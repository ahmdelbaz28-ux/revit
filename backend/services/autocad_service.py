import logging
import os
import platform
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Cross-platform support: Real imports for Windows, mock for Linux/Mac
IS_WINDOWS = platform.system() == "Windows"

if IS_WINDOWS:
    try:
        import win32com.client  # type: ignore
        import pythoncom  # type: ignore

        HAS_AUTOCAD_API = True
    except ImportError:
        logger.warning("AutoCAD COM API not available. Install pywin32.")
        HAS_AUTOCAD_API = False
else:
    HAS_AUTOCAD_API = False
    logger.info("Running on non-Windows platform. Using simulation mode for AutoCAD.")

# Define stubs for type checkers when imports are not available
if not IS_WINDOWS or not globals().get('HAS_AUTOCAD_API', False):
    pythoncom = None
    win32com = None


class AutoCADService:
    """
    AutoCAD integration service with COM API.

    Handles connecting to AutoCAD, reading/writing DWG files, and drawing operations.
    """

    def __init__(self):
        self.acad_app = None
        self.acad_doc = None
        self.acad_util = None
        self.connected = False
        self.active_entities: Dict[str, Dict[str, Any]] = {}

    def connect(self) -> bool:
        """
        Connect to a running AutoCAD instance or launch a new one.

        Returns:
            bool: True if connection successful, False otherwise
        """
        try:
            if not HAS_AUTOCAD_API:
                logger.error("AutoCAD COM API not available. Install pywin32.")
                return False

            # Check if pythoncom is available before using it
            if pythoncom is None:
                logger.error("pythoncom is not available on this platform")
                return False
                
            pythoncom.CoInitialize()

            # Try to launch a new AutoCAD instance first; fallback to existing instance
            try:
                self.acad_app = win32com.client.Dispatch("AutoCAD.Application")
                self.acad_app.Visible = True
                logger.info("Launched new AutoCAD instance")
            except Exception:
                try:
                    self.acad_app = win32com.client.GetActiveObject("AutoCAD.Application")
                    logger.info("Connected to existing AutoCAD instance")
                except Exception as e:
                    logger.error("Could not launch or attach to AutoCAD: %s", e)
                    return False

            # Get active document
            self.acad_doc = self.acad_app.ActiveDocument
            if not self.acad_doc:
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
                try:
                    self.acad_app.Visible = False
                except Exception:
                    pass
                self.acad_app = None

            self.acad_doc = None
            self.acad_util = None
            self.connected = False

            if HAS_AUTOCAD_API:
                # Check if pythoncom is available before using it
                if pythoncom is not None:
                    try:
                        pythoncom.CoUninitialize()
                    except Exception:
                        pass

            logger.info("Disconnected from AutoCAD")
            return True
        except Exception as e:
            logger.error("Error disconnecting from AutoCAD: %s", e)
            return False

    def initialize(self) -> bool:
        """Initialize the AutoCAD service by attempting to connect."""
        return self.connect()

    def _extract_entity_data(self, entity: Any) -> Dict[str, Any]:
        """Extract detailed data from an AutoCAD entity."""
        try:
            entity_type = getattr(entity, "ObjectName", "")
            entity_type = entity_type.split(".")[-1].upper().replace("ACDB", "")

            entity_data: Dict[str, Any] = {
                "handle": getattr(entity, "Handle", ""),
                "object_name": getattr(entity, "ObjectName", ""),
                "layer": getattr(entity, "Layer", "0"),
                "color": getattr(entity, "Color", 0),
                "linetype": getattr(entity, "Linetype", "ByLayer"),
                "lineweight": getattr(entity, "Lineweight", -1),
                "visible": getattr(entity, "Visible", True),
                "entity_type": entity_type,
            }

            if entity_type == "LINE":
                entity_data.update(
                    {
                        "start_point": list(entity.StartPoint),
                        "end_point": list(entity.EndPoint),
                        "thickness": getattr(entity, "Thickness", None),
                        "normal": list(entity.Normal) if hasattr(entity, "Normal") else [0, 0, 1],
                    }
                )
            elif entity_type == "LWPOLYLINE":
                entity_data.update(
                    {
                        "coordinates": [float(coord) for coord in entity.Coordinates],
                        "elevation": getattr(entity, "Elevation", None),
                        "thickness": getattr(entity, "Thickness", None),
                        "constant_width": getattr(entity, "ConstantWidth", None),
                        "normal": list(entity.Normal) if hasattr(entity, "Normal") else [0, 0, 1],
                    }
                )
            elif entity_type == "CIRCLE":
                entity_data.update(
                    {
                        "center": list(entity.Center),
                        "radius": entity.Radius,
                        "normal": list(entity.Normal) if hasattr(entity, "Normal") else [0, 0, 1],
                    }
                )
            elif entity_type == "ARC":
                entity_data.update(
                    {
                        "center": list(entity.Center),
                        "radius": entity.Radius,
                        "start_angle": entity.StartAngle,
                        "end_angle": entity.EndAngle,
                        "normal": list(entity.Normal) if hasattr(entity, "Normal") else [0, 0, 1],
                    }
                )
            elif entity_type == "TEXT":
                entity_data.update(
                    {
                        "text_string": entity.TextString,
                        "insertion_point": list(entity.InsertionPoint),
                        "height": entity.Height,
                        "rotation": getattr(entity, "Rotation", 0),
                        "style_name": getattr(entity, "StyleName", ""),
                    }
                )
            elif entity_type == "MTEXT":
                entity_data.update(
                    {
                        "contents": entity.TextString,
                        "insertion_point": list(entity.InsertionPoint),
                        "height": entity.Height,
                        "width": getattr(entity, "Width", None),
                        "attachment_point": getattr(entity, "AttachmentPoint", None),
                    }
                )
            elif entity_type == "INSERT":
                entity_data.update(
                    {
                        "name": getattr(entity, "Name", ""),
                        "insertion_point": list(entity.InsertionPoint),
                        "x_scale_factor": getattr(entity, "XScaleFactor", 1.0),
                        "y_scale_factor": getattr(entity, "YScaleFactor", 1.0),
                        "z_scale_factor": getattr(entity, "ZScaleFactor", 1.0),
                        "rotation": getattr(entity, "Rotation", 0),
                        "has_attributes": getattr(entity, "HasAttributes", False),
                    }
                )

                if getattr(entity, "HasAttributes", False):
                    attributes = []
                    for attr in entity.GetAttributes():
                        attributes.append(
                            {
                                "tag": getattr(attr, "TagString", ""),
                                "text_string": getattr(attr, "TextString", ""),
                                "prompt": getattr(attr, "Prompt", ""),
                            }
                        )
                    entity_data["attributes"] = attributes

            return entity_data
        except Exception as e:
            logger.error("Error extracting entity data: %s", e)
            return {
                "handle": getattr(entity, "Handle", ""),
                "object_name": getattr(entity, "ObjectName", ""),
                "error": str(e),
            }

    def read_dwg(self, filepath: str) -> Dict[str, Any]:
        """Read entities from a DWG file."""
        try:
            if not os.path.exists(filepath):
                raise FileNotFoundError(f"DWG file not found: {filepath}")

            if self.connected and self.acad_app and self.acad_doc:
                current_doc = self.acad_doc
                target_doc = self.acad_app.Documents.Open(filepath)

                self.acad_doc = target_doc
                self.acad_util = target_doc.Utility

                entities: List[Dict[str, Any]] = []
                model_space = target_doc.ModelSpace
                for entity in model_space:
                    try:
                        entities.append(self._extract_entity_data(entity))
                    except Exception as e:
                        logger.warning("Could not extract entity: %s", e)
                        continue

                target_doc.Close(False)

                self.acad_doc = current_doc
                self.acad_util = current_doc.Utility if current_doc else None

                return {
                    "success": True,
                    "entities": entities,
                    "count": len(entities),
                    "source_file": filepath,
                }

            logger.error("AutoCAD service not connected. Cannot read DWG file.")
            return {
                "success": False,
                "error": "AutoCAD service not connected. Cannot read DWG file.",
                "entities": [],
                "count": 0,
            }
        except Exception as e:
            logger.error("Error reading DWG file %s: %s", filepath, e)
            return {
                "success": False,
                "error": str(e),
                "entities": [],
                "count": 0,
            }

    def write_dwg(self, filepath: str, entities: List[Dict[str, Any]]) -> bool:
        """Write entities to a DWG file."""
        try:
            if not self.connected or not self.acad_app:
                # Attempt to connect automatically if not already connected
                logger.info("AutoCAD not connected, attempting auto-connect before write.")
                if not self.connect():
                    logger.error("AutoCAD service not connected after auto-connect attempt. Cannot write DWG file.")
                    return False

            output_dir = os.path.dirname(filepath)
            if output_dir:
                os.makedirs(output_dir, exist_ok=True)

            new_doc = self.acad_app.Documents.Add()
            model_space = new_doc.ModelSpace

            created_entities: List[Any] = []

            for entity_data in entities:
                entity_type = str(entity_data.get("entity_type", "")).upper()

                try:
                    if entity_type == "LINE":
                        start_point = entity_data.get("start_point", [0, 0, 0])
                        end_point = entity_data.get("end_point", [1, 0, 0])
                        line_obj = model_space.AddLine(start_point, end_point)

                        if "layer" in entity_data:
                            line_obj.Layer = entity_data["layer"]
                        if "color" in entity_data:
                            line_obj.Color = entity_data["color"]
                        if "linetype" in entity_data:
                            line_obj.Linetype = entity_data["linetype"]
                        if "lineweight" in entity_data:
                            line_obj.Lineweight = entity_data["lineweight"]

                        created_entities.append(line_obj)

                    elif entity_type == "CIRCLE":
                        center = entity_data.get("center", [0, 0, 0])
                        radius = entity_data.get("radius", 1.0)
                        circle_obj = model_space.AddCircle(center, radius)

                        if "layer" in entity_data:
                            circle_obj.Layer = entity_data["layer"]
                        if "color" in entity_data:
                            circle_obj.Color = entity_data["color"]

                        created_entities.append(circle_obj)

                    elif entity_type == "TEXT":
                        insertion_point = entity_data.get("insertion_point", [0, 0, 0])
                        text_string = entity_data.get("text_string", "Default Text")
                        height = entity_data.get("height", 0.2)

                        text_obj = model_space.AddText(text_string, insertion_point, height)

                        if "layer" in entity_data:
                            text_obj.Layer = entity_data["layer"]
                        if "color" in entity_data:
                            text_obj.Color = entity_data["color"]
                        if "rotation" in entity_data:
                            text_obj.Rotation = entity_data["rotation"]

                        created_entities.append(text_obj)

                    elif entity_type == "LWPOLYLINE":
                        coordinates = entity_data.get(
                            "coordinates", [0, 0, 1, 0, 1, 1, 0, 1]
                        )
                        poly_obj = model_space.AddLightWeightPolyline(coordinates)

                        if "layer" in entity_data:
                            poly_obj.Layer = entity_data["layer"]
                        if "color" in entity_data:
                            poly_obj.Color = entity_data["color"]

                        created_entities.append(poly_obj)

                    elif entity_type == "INSERT":
                        insertion_point = entity_data.get("insertion_point", [0, 0, 0])
                        name = entity_data.get("name", "UntitledBlock")

                        # Ensure block exists
                        try:
                            _ = new_doc.Blocks.Item(name)
                        except Exception:
                            block_obj = new_doc.Blocks.Add([0, 0, 0], name)
                            block_obj.AddLine([0, 0, 0], [1, 0, 0])
                            block_obj.AddLine([1, 0, 0], [1, 1, 0])
                            block_obj.AddLine([1, 1, 0], [0, 1, 0])
                            block_obj.AddLine([0, 1, 0], [0, 0, 0])

                        insert_obj = model_space.InsertBlock(
                            insertion_point,
                            name,
                            entity_data.get("x_scale_factor", 1.0),
                            entity_data.get("y_scale_factor", 1.0),
                            entity_data.get("z_scale_factor", 1.0),
                            entity_data.get("rotation", 0),
                        )

                        if "layer" in entity_data:
                            insert_obj.Layer = entity_data["layer"]

                        created_entities.append(insert_obj)

                except Exception as e:
                    logger.warning("Could not create entity %s: %s", entity_type, e)
                    continue

            new_doc.SaveAs(filepath)
            new_doc.Close(False)

            logger.info("Successfully wrote %s entities to %s", len(created_entities), filepath)
            return True
        except Exception as e:
            logger.error("Error writing DWG file %s: %s", filepath, e)
            return False

    def draw_line(
        self,
        start_point: List[float],
        end_point: List[float],
        layer: str = "0",
        color: int = 0,
    ) -> Optional[Any]:
        try:
            if not self.connected or not self.acad_doc:
                logger.error("AutoCAD service not connected. Cannot draw line.")
                return None

            model_space = self.acad_doc.ModelSpace
            line_obj = model_space.AddLine(start_point, end_point)
            line_obj.Layer = layer
            line_obj.Color = color
            return line_obj
        except Exception as e:
            logger.error("Error drawing line: %s", e)
            return None

    def draw_polyline(
        self,
        vertices: List[List[float]],
        layer: str = "0",
        color: int = 0,
        closed: bool = False,
    ) -> Optional[Any]:
        try:
            if not self.connected or not self.acad_doc:
                logger.error("AutoCAD service not connected. Cannot draw polyline.")
                return None

            flattened_vertices: List[float] = []
            for vertex in vertices:
                flattened_vertices.extend(vertex[:2])

            model_space = self.acad_doc.ModelSpace
            polyline_obj = model_space.AddLightWeightPolyline(flattened_vertices)
            polyline_obj.Layer = layer
            polyline_obj.Color = color
            if closed:
                polyline_obj.Closed = True
            return polyline_obj
        except Exception as e:
            logger.error("Error drawing polyline: %s", e)
            return None

    def draw_circle(
        self,
        center: List[float],
        radius: float,
        layer: str = "0",
        color: int = 0,
    ) -> Optional[Any]:
        try:
            if not self.connected or not self.acad_doc:
                logger.error("AutoCAD service not connected. Cannot draw circle.")
                return None

            model_space = self.acad_doc.ModelSpace
            circle_obj = model_space.AddCircle(center, radius)
            circle_obj.Layer = layer
            circle_obj.Color = color
            return circle_obj
        except Exception as e:
            logger.error("Error drawing circle: %s", e)
            return None

    def draw_text(
        self,
        text: str,
        insertion_point: List[float],
        height: float = 0.2,
        layer: str = "0",
        color: int = 0,
    ) -> Optional[Any]:
        try:
            if not self.connected or not self.acad_doc:
                logger.error("AutoCAD service not connected. Cannot draw text.")
                return None

            model_space = self.acad_doc.ModelSpace
            text_obj = model_space.AddText(text, insertion_point, height)
            text_obj.Layer = layer
            text_obj.Color = color
            return text_obj
        except Exception as e:
            logger.error("Error drawing text: %s", e)
            return None

    def get_document_info(self) -> Dict[str, Any]:
        """Get information about the active AutoCAD document."""
        try:
            if not self.connected or not self.acad_doc:
                logger.error("AutoCAD service not connected. Cannot get document info.")
                return {}

            doc = self.acad_doc
            return {
                "name": getattr(doc, "Name", None),
                "path": getattr(doc, "Path", None),
                "title": getattr(doc, "Title", None),
                "active_space": getattr(doc, "ActiveSpace", None),
                "limits": {
                    "min_point": list(doc.Limits.MinPoint) if getattr(doc, "Limits", None) else None,
                    "max_point": list(doc.Limits.MaxPoint) if getattr(doc, "Limits", None) else None,
                },
                "variables": {
                    "units": doc.GetVariable("INSUNITS"),
                    "angle_units": doc.GetVariable("AUNITS"),
                    "precision": doc.GetVariable("LUPREC"),
                },
            }
        except Exception as e:
            logger.error("Error getting document info: %s", e)
            return {}

    def save(self, filepath: str) -> bool:
        """Save the active document to a file."""
        try:
            if not self.connected or not self.acad_doc:
                logger.error("AutoCAD service not connected. Cannot save document.")
                return False

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
        """Delete an entity by its handle."""
        try:
            if not self.connected or not self.acad_doc:
                logger.error("AutoCAD service not connected. Cannot delete entity.")
                return False

            entity = self.acad_doc.HandleToObject(handle)
            if not entity:
                logger.warning("No entity found with handle: %s", handle)
                return False

            entity.Delete()

            if handle in self.active_entities:
                del self.active_entities[handle]

            logger.info("Deleted entity with handle: %s", handle)
            return True
        except Exception as e:
            logger.error("Error deleting entity %s: %s", handle, e)
            return False

    def modify_entity(self, handle: str, properties: Dict[str, Any]) -> bool:
        """Modify an entity's properties by its handle."""
        try:
            if not self.connected or not self.acad_doc:
                logger.error("AutoCAD service not connected. Cannot modify entity.")
                return False

            entity = self.acad_doc.HandleToObject(handle)
            if not entity:
                logger.warning("No entity found with handle: %s", handle)
                return False

            modified = False

            if "layer" in properties:
                try:
                    entity.Layer = properties["layer"]
                    modified = True
                except Exception as e:
                    logger.warning("Could not set layer for entity %s: %s", handle, e)

            if "color" in properties:
                try:
                    entity.Color = properties["color"]
                    modified = True
                except Exception as e:
                    logger.warning("Could not set color for entity %s: %s", handle, e)

            if "linetype" in properties:
                try:
                    entity.Linetype = properties["linetype"]
                    modified = True
                except Exception as e:
                    logger.warning("Could not set linetype for entity %s: %s", handle, e)

            if "lineweight" in properties:
                try:
                    entity.Lineweight = properties["lineweight"]
                    modified = True
                except Exception as e:
                    logger.warning("Could not set lineweight for entity %s: %s", handle, e)

            if hasattr(entity, "StartPoint") and "start_point" in properties:
                try:
                    entity.StartPoint = properties["start_point"]
                    modified = True
                except Exception as e:
                    logger.warning("Could not set start_point for entity %s: %s", handle, e)

            if hasattr(entity, "EndPoint") and "end_point" in properties:
                try:
                    entity.EndPoint = properties["end_point"]
                    modified = True
                except Exception as e:
                    logger.warning("Could not set end_point for entity %s: %s", handle, e)

            if hasattr(entity, "Center") and "center" in properties:
                try:
                    entity.Center = properties["center"]
                    modified = True
                except Exception as e:
                    logger.warning("Could not set center for entity %s: %s", handle, e)

            if hasattr(entity, "Radius") and "radius" in properties:
                try:
                    entity.Radius = properties["radius"]
                    modified = True
                except Exception as e:
                    logger.warning("Could not set radius for entity %s: %s", handle, e)

            if hasattr(entity, "TextString") and "text" in properties:
                try:
                    entity.TextString = properties["text"]
                    modified = True
                except Exception as e:
                    logger.warning("Could not set text for entity %s: %s", handle, e)

            if hasattr(entity, "Height") and "height" in properties:
                try:
                    entity.Height = properties["height"]
                    modified = True
                except Exception as e:
                    logger.warning("Could not set height for entity %s: %s", handle, e)

            if modified:
                if handle in self.active_entities:
                    self.active_entities[handle].update(properties)

            return modified
        except Exception as e:
            logger.error("Error modifying entity %s: %s", handle, e)
            return False
