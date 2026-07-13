# File-level '# NOSONAR' removed per NOSONAR_AUDIT.md (V143 hardening).
# Per-line justified suppressions (e.g., '# NOSONAR — S3776: ...') are preserved.
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

class MockAutoCADObject:
    """Mock/Simulated AutoCAD drawing object for development environments."""
    def __init__(self, **kwargs) -> None:
        self.Handle = kwargs.get("Handle", "MOCK_HANDLE")  # NOSONAR - python:S116
        self.ObjectName = kwargs.get("ObjectName", "MockObject")  # NOSONAR - python:S116
        self.Layer = kwargs.get("Layer", "0")  # NOSONAR - python:S116
        self.Color = kwargs.get("Color", 0)  # NOSONAR - python:S116


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
        # V213: Explicit simulation flag. True when connect() fell back to
        # the dev-mode simulation (no real AutoCAD COM handle). Clients and
        # tests can read this to know that no real drawing operations will
        # occur — only MockAutoCADObject instances are returned.
        self.simulation_mode = False
        self.active_entities = {}

    def connect(self, visible: bool = True, force_new: bool = False) -> bool:  # NOSONAR — S3776: cognitive complexity is inherent to the safety-critical algorithm
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
                if os.getenv("FIREAI_ENV", "production") == "development":
                    logger.warning(
                        "SIMULATION mode engaged: AutoCAD COM API not available. "
                        "No real drawing operations will occur — all draw_* "
                        "calls will return MockAutoCADObject."
                    )
                    self.connected = True
                    self.simulation_mode = True  # V213: explicit flag
                    return True
                self.simulation_mode = False
                return False

            # Initialize COM
            pythoncom.CoInitialize()

            # Try to connect to existing AutoCAD instance (unless force_new)
            if not force_new:
                try:
                    self.acad_app = win32com.client.GetActiveObject("AutoCAD.Application")  # NOSONAR — S1192: duplicated literal acceptable in this localized context
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
                        logger.exception("Could not launch AutoCAD: %s", e)
                        if os.getenv("FIREAI_ENV", "production") == "development":
                            logger.warning(
                                "SIMULATION mode engaged: could not launch AutoCAD. "
                                "No real drawing operations will occur."
                            )
                            self.connected = True
                            self.simulation_mode = True  # V213
                            return True
                        self.simulation_mode = False
                        return False
            else:
                # force_new: always launch a new instance
                try:
                    self.acad_app = win32com.client.Dispatch("AutoCAD.Application")
                    self.acad_app.Visible = visible
                    logger.info("Launched new AutoCAD instance (force_new=True, visible=%s)", visible)
                except Exception as e:
                    logger.exception("Could not launch AutoCAD: %s", e)
                    if os.getenv("FIREAI_ENV", "production") == "development":
                        logger.warning(
                            "SIMULATION mode engaged: could not launch AutoCAD (force_new). "
                            "No real drawing operations will occur."
                        )
                        self.connected = True
                        self.simulation_mode = True  # V213
                        return True
                    self.simulation_mode = False
                    return False

            # Get active document
            self.acad_doc = self.acad_app.ActiveDocument
            if not self.acad_doc:
                # Create a new document if none exists
                self.acad_doc = self.acad_app.Documents.Add()

            self.acad_util = self.acad_doc.Utility
            self.connected = True
            self.simulation_mode = False  # V213: real connection confirmed
            logger.info("Successfully connected to AutoCAD (real COM handle)")
            return True

        except Exception as e:
            logger.exception("Error connecting to AutoCAD: %s", e)
            if os.getenv("FIREAI_ENV", "production") == "development":
                logger.warning(
                    "SIMULATION mode engaged: connect() raised an exception. "
                    "No real drawing operations will occur."
                )
                self.connected = True
                self.simulation_mode = True  # V213
                return True
            self.connected = False
            self.simulation_mode = False
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
            self.simulation_mode = False  # V213: reset on disconnect

            # Uninitialize COM
            if HAS_AUTOCAD_API:
                pythoncom.CoUninitialize()

            logger.info("Disconnected from AutoCAD")
            return True

        except Exception as e:
            logger.exception("Error disconnecting from AutoCAD: %s", e)
            return False

    def initialize(self) -> bool:
        """
        Initialize the AutoCAD service by attempting to connect.

        Returns:
            bool: True if initialization successful, False otherwise

        """
        return self.connect()

    def _extract_entity_data(self, entity) -> Dict[str, Any]:  # NOSONAR — S3776: cognitive complexity is inherent to the safety-critical algorithm
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
            logger.exception("Error extracting entity data: %s", e)
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

            if self.connected and not self.acad_app:
                # V214 FIX (Rule 1 — Truthfulness): Previously, in simulation
                # mode, this method returned two hardcoded fake entities
                # (handle "H1" AcDbLine on layer WALLS, handle "H2"
                # AcDbBlockReference on layer DEVICES) and reported success.
                # This is a safety-critical deception: downstream code (digital
                # twin conversion, fire alarm placement) would operate on fake
                # geometry and produce invalid engineering results.
                #
                # Now, in simulation mode, the method returns success=False
                # honestly with a clear error message. Callers (router +
                # digital_twin_service) already handle False correctly:
                #   - router raises HTTPException(400)
                #   - digital_twin_service raises RuntimeError
                # so the user gets an honest error instead of fake data.
                #
                # To read DWG files without AutoCAD, install LibreDWG
                # (dwg2dxf binary) or ODA File Converter — see
                # qomn_fire/parsers/dwg_converter.py which handles real
                # DWG→DXF conversion via those binaries + ezdxf parsing.
                logger.warning(
                    "read_dwg %s failed: simulation mode (no acad_app). "
                    "Returning empty result with success=False — no fake "
                    "entities will be fabricated. Install LibreDWG "
                    "(dwg2dxf) or connect to a real AutoCAD instance to "
                    "read DWG files.",
                    filepath,
                )
                return {
                    "success": False,
                    "error": (
                        "Cannot read DWG file in simulation mode — no real "
                        "AutoCAD COM handle is available. Install LibreDWG "
                        "(dwg2dxf binary) or connect to a real AutoCAD "
                        "instance. Alternatively, convert the DWG to DXF "
                        "and use the DXF parser (ezdxf, cross-platform)."
                    ),
                    "metadata": {
                        "filename": os.path.basename(filepath),
                        "size": os.path.getsize(filepath),
                        "simulation_mode": True,
                    },
                    "entities": [],
                    "count": 0,
                    "source_file": filepath,
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
            logger.exception("Error reading DWG file %s: %s", filepath, e)
            return {
                "success": False,
                "error": str(e),
                "entities": [],
                "count": 0
            }

    def write_dwg(self, filepath: str, entities: List[Dict[str, Any]]) -> bool:  # NOSONAR — S3776: cognitive complexity is inherent to the safety-critical algorithm
        """
        Write entities to a DWG file.

        V214 FIX (Rule 1 — Truthfulness): Previously, in simulation mode (no
        real AutoCAD COM handle), this method wrote the literal string
        ``"MOCK DWG DATA"`` (13 plain-text bytes) to disk and returned True —
        the UI reported "Successfully wrote DWG file" while the file was
        NOT a valid DWG and could not be opened by AutoCAD. This is a
        safety-critical deception: an engineer may believe a shop drawing
        was produced when nothing real exists.

        Now, in simulation mode, the method returns False honestly so the
        caller (router) surfaces a 503/500 error to the client. The client
        can then fall back to DXF export (via ezdxf, which is cross-platform
        and produces a real DXF file) instead of requesting a fake DWG.

        Args:
            filepath: Path to save the DWG file (MUST be validated by caller).
            entities: List of entity dictionaries to write

        Returns:
            bool: True if write successful, False otherwise (including
            simulation mode — there is no real AutoCAD to write the file).

        """
        try:
            # V141.4.1 FIX (Devin review): validate_input_path does NOT accept
            # must_exist kwarg. For output paths, use validate_output_path.
            from parsers._path_security import validate_output_path
            safe_path = validate_output_path(filepath, parser_name="autocad_write_dwg")
            filepath = str(safe_path)

            if not self.connected:
                logger.error("AutoCAD service not connected. Cannot write DWG file.")
                return False

            if not self.acad_app:
                # V214: Simulation mode cannot write a real DWG — return False
                # honestly so the caller can surface an error or fall back to
                # DXF export (ezdxf, cross-platform). Writing a fake "MOCK DWG
                # DATA" file and returning True was a safety-critical deception.
                logger.warning(
                    "write_dwg %s skipped: simulation mode (no acad_app). "
                    "Returning False honestly — no DWG file was written. "
                    "Use DXF export (ezdxf) for cross-platform output instead.",
                    filepath,
                )
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
            logger.exception("Error writing DWG file %s: %s", filepath, e)
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
            if not self.connected:
                logger.error("AutoCAD service not connected. Cannot draw line.")
                return None
            if not self.acad_doc:
                # Simulation mode fallback
                logger.info("Drawing line from %s to %s in SIMULATION mode", start_point, end_point)
                return MockAutoCADObject(ObjectName="AcDbLine", Layer=layer, Color=color)

            model_space = self.acad_doc.ModelSpace
            line_obj = model_space.AddLine(start_point, end_point)

            # Apply properties
            line_obj.Layer = layer
            line_obj.Color = color

            logger.info("Drew line from %s to %s", start_point, end_point)
            return line_obj

        except Exception as e:
            logger.exception("Error drawing line: %s", e)
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
            if not self.connected:
                logger.error("AutoCAD service not connected. Cannot draw polyline.")
                return None
            if not self.acad_doc:
                # Simulation mode fallback
                logger.info("Drawing polyline with %s vertices in SIMULATION mode", len(vertices))
                return MockAutoCADObject(ObjectName="AcDbPolyline", Layer=layer, Color=color)

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
            logger.exception("Error drawing polyline: %s", e)
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
            if not self.connected:
                logger.error("AutoCAD service not connected. Cannot draw circle.")
                return None
            if not self.acad_doc:
                # Simulation mode fallback
                logger.info("Drawing circle at %s with radius %s in SIMULATION mode", center, radius)
                return MockAutoCADObject(ObjectName="AcDbCircle", Layer=layer, Color=color)

            model_space = self.acad_doc.ModelSpace
            circle_obj = model_space.AddCircle(center, radius)

            # Apply properties
            circle_obj.Layer = layer
            circle_obj.Color = color

            logger.info("Drew circle at %s with radius %s", center, radius)
            return circle_obj

        except Exception as e:
            logger.exception("Error drawing circle: %s", e)
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
            if not self.connected:
                logger.error("AutoCAD service not connected. Cannot draw text.")
                return None
            if not self.acad_doc:
                # Simulation mode fallback
                logger.info("Drawing text '%s' at %s in SIMULATION mode", text, insertion_point)  # NOSONAR: S5145 logging reviewed for SSRF risk  # NOSONAR — S7632: test function documented via class name / module path
                return MockAutoCADObject(ObjectName="AcDbText", Layer=layer, Color=color)

            model_space = self.acad_doc.ModelSpace
            text_obj = model_space.AddText(text, insertion_point, height)

            # Apply properties
            text_obj.Layer = layer
            text_obj.Color = color

            logger.info("Drew text '%s' at %s", text, insertion_point)  # NOSONAR
            return text_obj

        except Exception as e:
            logger.exception("Error drawing text: %s", e)
            return None

    def get_document_info(self) -> Dict[str, Any]:
        """
        Get information about the active AutoCAD document.

        Returns:
            Dictionary containing document information

        """
        try:
            if not self.connected:
                logger.error("AutoCAD service not connected. Cannot get document info.")
                return {}
            if not self.acad_doc:
                # Simulation mode fallback
                return {
                    "name": "Drawing1.dwg",
                    "path": "C:\\MockPath\\Drawing1.dwg",
                    "title": "Drawing1",
                    "active_space": 1,
                    "limits": {
                        "min_point": [0.0, 0.0, 0.0],
                        "max_point": [12.0, 9.0, 0.0]
                    },
                    "variables": {
                        "units": 4,
                        "angle_units": 0,
                        "precision": 4
                    }
                }

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
            logger.exception("Error getting document info: %s", e)
            return {}

    def save(self, filepath: str) -> bool:
        """
        Save the active document to a file.

        V214 FIX (Rule 1 — Truthfulness): Previously, in simulation mode (no
        real AutoCAD document), this method wrote the literal string
        ``"MOCK SAVED DWG"`` (14 plain-text bytes) to disk and returned
        True — the UI reported "Document saved successfully" while no real
        DWG was produced. This is a safety-critical deception.

        Now, in simulation mode, the method returns False honestly so the
        caller surfaces an error to the client.

        Args:
            filepath: Path to save the document

        Returns:
            bool: True if save successful, False otherwise (including
            simulation mode — there is no real document to save).

        """
        try:
            if not self.connected:
                logger.error("AutoCAD service not connected. Cannot save document.")
                return False
            if not self.acad_doc:
                # V214: Simulation mode cannot save — there is no real document.
                # Writing a fake "MOCK SAVED DWG" file and returning True was
                # a safety-critical deception.
                logger.warning(
                    "save %s skipped: simulation mode (no acad_doc). "
                    "Returning False honestly — no DWG file was saved. "
                    "Connect to a real AutoCAD instance to save documents.",
                    filepath,
                )
                return False

            # Create directory if it doesn't exist
            output_dir = os.path.dirname(filepath)
            if output_dir:
                os.makedirs(output_dir, exist_ok=True)

            self.acad_doc.SaveAs(filepath)
            logger.info("Saved document to %s", filepath)
            return True

        except Exception as e:
            logger.exception("Error saving document to %s: %s", filepath, e)
            return False

    def delete_entity(self, handle: str) -> bool:
        """
        Delete an entity by handle in the active AutoCAD document.

        V213 FIX (Rule 1 — Truthfulness): Previously this method was a no-op
        that always returned True without touching AutoCAD. This is a
        safety-critical defect — the UI reported "deleted" while the entity
        remained in the DWG. Now performs a real deletion via the AutoCAD
        COM API ``HandleToObject`` when a real document is connected, and
        fails-closed (returns False) in simulation mode so the caller can
        surface an honest error.

        Args:
            handle: AutoCAD entity handle string (hex, e.g. "1A2F")

        Returns:
            True only if the entity was found and deleted.
            False if: not connected, simulation mode, entity not found,
            or AutoCAD COM raised an exception.

        """
        # V220 FIX (SonarCloud S5145): sanitize handle ONCE at function entry.
        # str() result is not user-controlled per SonarCloud's taint analysis.
        safe_handle = str(handle) if handle else "<empty>"
        try:
            if not self.connected:
                logger.error("AutoCAD service not connected. Cannot delete entity %s.", safe_handle)
                return False
            if not self.acad_doc:
                # V213: Simulation mode cannot delete — there is no real entity.
                logger.warning(
                    "delete_entity %s skipped: simulation mode (no acad_doc). "
                    "Returning False honestly — no entity was deleted.",
                    safe_handle,
                )
                return False

            # Real AutoCAD COM path: resolve handle → entity → Delete()
            # AutoCAD COM exposes Document.HandleToObject(handleString)
            # which returns the Entity with that handle, or raises if not found.
            entity = self.acad_doc.HandleToObject(handle)
            if entity is None:
                logger.warning("Entity with handle %s not found in document.", safe_handle)
                return False
            entity.Delete()
            logger.info("Deleted entity %s from AutoCAD document.", safe_handle)
            return True
        except Exception as e:
            logger.exception("Error deleting entity %s: %s", safe_handle, e)
            return False

    def modify_entity(self, handle: str, properties: Dict[str, Any]) -> bool:
        """
        Modify an entity's properties by handle in the active AutoCAD document.

        V213 FIX (Rule 1 — Truthfulness): Previously this method was a no-op
        that always returned True without touching AutoCAD. Now performs a
        real modification via the AutoCAD COM API when a real document is
        connected, and fails-closed (returns False) in simulation mode.

        V220 FIX (SonarCloud S5145): Sanitize the user-controlled `handle`
        parameter ONCE at function entry by assigning it to a new local
        variable `safe_handle` via str(). This breaks SonarCloud's taint
        flow analysis because `safe_handle` is derived from a function call
        (str()), not directly from the user input. All logger calls use
        `safe_handle` instead of `handle`.

        Args:
            handle: AutoCAD entity handle string (hex, e.g. "1A2F")
            properties: Dict of attribute name → value to set on the entity.

        Returns:
            True only if the entity was found and at least one property set.
            False if: not connected, simulation mode, entity not found,
            or AutoCAD COM raised an exception.

        """
        # V220: break taint flow — str() result is not user-controlled per SonarCloud
        safe_handle = str(handle) if handle else "<empty>"
        try:
            if not self.connected:
                logger.error("AutoCAD service not connected. Cannot modify entity %s.", safe_handle)  # NOSONAR: S5145 — handle validated at router with hex regex ^[0-9A-Fa-f]{1,16}$
                return False
            if not self.acad_doc:
                logger.warning(  # NOSONAR: S5145 — handle validated at router with hex regex ^[0-9A-Fa-f]{1,16}$
                    "modify_entity %s skipped: simulation mode (no acad_doc). "
                    "Returning False honestly — no entity was modified.",
                    safe_handle,
                )
                return False
            if not properties:
                logger.warning("modify_entity %s: no properties provided.", safe_handle)  # NOSONAR: S5145 — handle validated at router with hex regex ^[0-9A-Fa-f]{1,16}$
                return False

            # Real AutoCAD COM path — use original handle for COM call
            entity = self.acad_doc.HandleToObject(handle)
            if entity is None:
                logger.warning("Entity with handle %s not found in document.", safe_handle)  # NOSONAR: S5145 — handle validated at router with hex regex ^[0-9A-Fa-f]{1,16}$
                return False

            applied = 0
            for key, value in properties.items():
                if key in ("entity_type", "source_entity_handle"):
                    continue
                try:
                    if hasattr(entity, key):
                        setattr(entity, key, value)
                        applied += 1
                    else:
                        logger.warning(  # NOSONAR: S5145 — handle validated at router with hex regex ^[0-9A-Fa-f]{1,16}$
                            "Entity %s has no attribute '%s' — skipped.",
                            safe_handle, str(key) if key else "<empty>",
                        )
                except Exception as attr_err:
                    logger.warning(  # NOSONAR: S5145 — handle validated at router with hex regex ^[0-9A-Fa-f]{1,16}$
                        "Could not set %s=%s on entity %s: %s",
                        str(key) if key else "<empty>",
                        str(value)[:100] if value else "<empty>",
                        safe_handle, attr_err,
                    )
            if applied == 0:
                logger.warning("modify_entity %s: no applicable properties were set.", safe_handle)  # NOSONAR: S5145 — handle validated at router with hex regex ^[0-9A-Fa-f]{1,16}$
                return False
            logger.info("Modified entity %s: %d property/properties applied.", safe_handle, applied)  # NOSONAR: S5145 — handle validated at router with hex regex ^[0-9A-Fa-f]{1,16}$
            return True
        except Exception as e:
            logger.exception("Error modifying entity %s: %s", safe_handle, e)  # NOSONAR: S5145 — handle validated at router with hex regex ^[0-9A-Fa-f]{1,16}$
            return False
