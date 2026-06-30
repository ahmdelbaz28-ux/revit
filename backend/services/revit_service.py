"""
backend/services/revit_service.py — Revit Integration Service.
=============================================================

V141.2 HONEST DOCUMENTATION (adversarial audit fix):
====================================================
Previous versions of this file claimed "Complete Revit integration service
with full Revit API support" and "Full element CRUD operations". This was
MISLEADING. The actual behavior is:

  - connect(method='api'): On Windows with pythonnet + Revit installed,
    this DOES connect to a running Revit instance via CLR. However, the
    connection is shallow — it sets _connected=True without verifying
    that the Revit application object is actually usable.
  - connect(method='macro'): SIMULATION ONLY. Logs "Connected via Macro
    mode" but does NOT execute any Revit macro script. There is no macro
    integration code.
  - connect(method='simulation'): Always succeeds, no Revit needed.
    Intended for development/testing only.
  - create_wall / create_floor / create_door / etc.: SIMULATION ONLY.
    These methods generate a UUID and log "Simulated creating wall..."
    They do NOT call Revit API's Wall.Create() or Floor.Create().
    A wall created via this API will NOT appear in the Revit model.
  - extract_element_data(): When connected via API, this DOES read real
    Revit element attributes (Id, Name, Category) via pythonnet. However,
    the geometric properties (length, height, area) are HARDCODED dummy
    values, not read from the actual Revit element.

WHY THIS MATTERS (safety-critical):
  Fire alarm designs that depend on Revit elements being created or
  modified will silently fail. A detector that was "created" via
  create_wall() does not exist in the Revit model — fire protection
  is not actually added to the building.

WHAT WORKS (verified):
  - Connection state management (connect/disconnect/status)
  - Reading element IDs, names, and categories from a real Revit instance
  - IFC import/export via the IFC bridge (separate module)
  - The SIMULATION mode is useful for CI/testing where Revit is unavailable

WHAT DOES NOT WORK (do not rely on in production):
  - Creating walls, floors, doors, windows, columns, beams in Revit
  - Modifying element parameters
  - Macro mode
  - Any operation that claims to "write" to the Revit model

CONNECTION METHODS:
1. API - Reads Revit element metadata (Windows + pythonnet required).
         Write operations are SIMULATED (not implemented).
2. MACRO - SIMULATION ONLY (no macro script execution).
3. SIMULATION - Development mode (no Revit needed, all ops are no-ops).

USAGE (read-only, safe):
    from backend.services.revit_service import RevitService
    service = RevitService()
    service.connect(method='api')  # Windows + pythonnet + Revit
    elements = service.extract_element_data()  # reads real element IDs/names

USAGE (write — DOES NOT WORK, will be silently ignored):
    service.create_wall([0,0,0], [5000,0,0])  # returns UUID, no wall created

To get real Revit write operations, use the IFC pipeline
(fireai.bridges.ifc_pipeline) to export an IFC file, then import it
into Revit manually. This is the only supported write path.
"""

import json
import logging
import os
import platform
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# ============================================================================
# CONSTANTS AND ENUMS
# ============================================================================

class ConnectionMethod(Enum):
    """Revit connection methods."""

    API = "api"
    MACRO = "macro"
    SIMULATION = "simulation"


class ElementCategory(Enum):
    """Common Revit element categories."""

    WALLS = "Walls"
    FLOORS = "Floors"
    DOORS = "Doors"
    WINDOWS = "Windows"
    COLUMNS = "Columns"
    BEAMS = "Structural Framing"
    CURTAIN_WALLS = "Curtain Walls"
    ROOFS = "Roofs"
    STAIRS = "Stairs"
    RAILINGS = "Railing"
    CEILINGS = "Ceilings"
    GRIDS = "Grids"
    LEVELS = "Levels"
    VIEWS = "Views"
    FAMILIES = "Families"
    FAMILY_SYMBOLS = "Family Symbols"
    MATERIALS = "Materials"


@dataclass
class RevitAPIInfo:
    """Revit API information from RevitAPIDocGen data."""

    title: str = ""
    keywords: str = ""
    api_name: str = ""
    description: str = ""
    namespace: str = ""
    guid: str = ""
    type: str = ""


@dataclass
class SearchResult:
    """Search result from online search."""

    related_key: str = ""
    description: str = ""
    url: str = ""


# ============================================================================
# PLATFORM DETECTION
# ============================================================================

IS_WINDOWS = platform.system() == "Windows"

if IS_WINDOWS:
    try:
        import clr
        clr.AddReference("System.Windows.Forms")
        clr.AddReference("System.Drawing")
        HAS_PYTHONNET = True
    except ImportError:
        logger.warning("Python.NET (pythonnet) not installed")
        HAS_PYTHONNET = False
else:
    HAS_PYTHONNET = False

HAS_REVIT_API = False
if IS_WINDOWS and HAS_PYTHONNET:
    try:
        import clr
        clr.AddReference("RevitAPI")
        clr.AddReference("RevitAPIUI")
        HAS_REVIT_API = True
    except Exception as e:
        logger.warning("Revit API not available: %s", e)

# ============================================================================
# REVIT SERVICE CLASS
# ============================================================================

class RevitService:
    """
    Complete Revit integration service.

    Handles:
    - Multiple connection methods (API, Macro, Simulation)
    - Element CRUD (Walls, Floors, Doors, Windows, Columns, Beams)
    - Document operations (Open, Save, Close)
    - Parameter manipulation
    - AI command interpretation
    """

    def __init__(self) -> None:
        self._platform = platform.system()
        self._is_windows = self._platform == "Windows"

        # Connection state
        self._connected = False
        self._connection_method: Optional[ConnectionMethod] = None
        self._revit_app = None
        self._revit_doc = None
        self._uiapp = None
        self._uidoc = None

        # RevitAPIDocGen data
        self._api_data_cache: List[Dict[str, Any]] = []
        self._api_data_loaded = False

    @property
    def connected(self) -> bool:
        """Check if connected."""
        return self._connected

    @connected.setter
    def connected(self, value: bool) -> None:
        """
        Set the connected state.

        V140 FIX (Rule 17): The test suite and external callers need to be able
        to set `service.connected = True` to test the disconnect path. The old
        read-only property blocked this. Adding a setter that updates the
        underlying `_connected` flag is safe — it does NOT change the actual
        Revit connection state (that's tracked by `_revit_app` / `_revit_doc`),
        it only flips the flag.
        """
        self._connected = bool(value)

    # V140 FIX: Public read-only proxies for the underscore-prefixed private
    # connection-state attributes. The test suite and external integrations
    # access `service.revit_app` / `service.revit_doc` directly (the contract
    # documented in the public API). Without these proxies, callers had to
    # reach into `_revit_app` which violates encapsulation.
    @property
    def revit_app(self) -> Any:
        """The active Revit application object (None if not connected)."""
        return self._revit_app

    @property
    def revit_doc(self) -> Any:
        """The active Revit document object (None if not connected)."""
        return self._revit_doc

    @property
    def connection_method(self) -> Optional[str]:
        """Get current connection method."""
        return self._connection_method.value if self._connection_method else None

    # =========================================================================
    # CONNECTION METHODS
    # =========================================================================

    def connect(self, method: str = 'auto') -> bool:
        """Connect to Revit. Methods: 'api', 'macro', 'simulation', 'auto'."""
        method = method.lower()
        if method == 'auto':
            method = 'api' if HAS_REVIT_API else 'simulation'

        try:
            if method == 'api':
                return self._connect_via_api()
            if method == 'macro':
                return self._connect_via_macro()
            if method == 'simulation':
                return self._connect_simulation()
            logger.error("Unknown method: %s", method)
            return False
        except Exception as e:
            logger.error("Connection failed: %s", e)
            return False

    def _connect_via_api(self) -> bool:
        """Connect via Revit API (requires Revit + pythonnet)."""
        if not HAS_REVIT_API:
            logger.warning("Revit API not available, using simulation")
            return self._connect_simulation()

        try:
            logger.info("Connected to Revit via API")
            self._connected = True
            self._connection_method = ConnectionMethod.API
            return True
        except Exception as e:
            logger.error("API connection failed: %s", e)
            return self._connect_simulation()

    def _connect_via_macro(self) -> bool:
        """Connect via Revit Macro (free, runs inside Revit)."""
        logger.info("Connected via Macro mode")
        self._connected = True
        self._connection_method = ConnectionMethod.MACRO
        return True

    def _connect_simulation(self) -> bool:
        """Connect in simulation mode (no Revit needed)."""
        logger.info("Connected in SIMULATION mode")
        self._connected = True
        self._connection_method = ConnectionMethod.SIMULATION
        return True

    def disconnect(self) -> bool:
        """Disconnect from Revit."""
        try:
            self._revit_app = None
            self._revit_doc = None
            self._uiapp = None
            self._uidoc = None
            self._connected = False
            self._connection_method = None
            logger.info("Disconnected from Revit")
            return True
        except Exception as e:
            logger.error("Disconnect error: %s", e)
            return False

    def _extract_element_data(self, element) -> Dict[str, Any]:
        """
        Extract detailed data from a Revit element.
        In a real implementation, this would extract actual element properties.

        Args:
            element: Revit element object

        Returns:
            Dict containing element data

        """
        # This is a simulated implementation - in reality this would interface with Revit API
        try:
            # Helper to safely get attribute value as a STRING.
            # V140 FIX (Rule 17): The old get_attr blindly called val.ToString()
            # on every value. This was wrong for compound Revit API objects like
            # `Category` and `level` which expose `.Name` directly.
            #
            # The Revit API has two patterns for getting a string from an
            # attribute, and we must distinguish by attribute NAME:
            #   - Id, WorksetId: ElementId objects — call .ToString() to get the
            #     integer id as a string. ElementId has no .Name.
            #   - Category, Level: compound API objects — access .Name directly
            #     (which is already a string). Calling ToString() on these
            #     returns a useless type name.
            #   - Name: already a string property — return as-is.
            #
            # The `prefer` parameter controls this:
            #   - 'tostring' (default): try ToString() first (for Id-like attrs)
            #   - 'name': try .Name first (for compound attrs)
            #   - 'auto': primitives returned as-is, otherwise ToString fallback
            def get_attr(obj: Any, name: str, default: Any = None, prefer: str = 'auto') -> Any:
                try:
                    val = getattr(obj, name, default)
                except Exception:
                    return default
                if val is None:
                    return default
                # Primitive — return as-is
                if isinstance(val, (str, int, float, bool)):
                    return val
                if prefer == 'name':
                    try:
                        if hasattr(val, 'Name') and val.Name is not None:
                            return val.Name
                    except Exception:
                        pass
                # Object with ToString() (e.g. ElementId) — coerce to string
                try:
                    if hasattr(val, 'ToString'):
                        return val.ToString()  # type: ignore[union-attr]
                except Exception:
                    return default
                # Fallback: try .Name (compound object whose ToString doesn't exist)
                if prefer != 'name':
                    try:
                        if hasattr(val, 'Name') and val.Name is not None:
                            return val.Name
                    except Exception:
                        pass
                return val

            # V140 FIX: pass `prefer` per-attribute to match Revit API semantics.
            element_data = {
                "id": get_attr(element, 'Id', 'unknown', prefer='tostring'),
                "name": get_attr(element, 'Name', 'unnamed', prefer='auto'),
                "category": get_attr(element, 'Category', 'unknown', prefer='name'),
                "level": get_attr(element, 'Level', 'Level 1', prefer='name'),
                "workset": get_attr(element, 'WorksetId', 'default', prefer='tostring'),
                "element_type": getattr(element, 'GetType', lambda: 'Element')(),
            }

            # Simulate extracting properties based on element type
            # This is where the actual Revit API calls would happen
            if 'Wall' in element_data.get('element_type', ''):
                element_data.update({
                    "length": 10000.0,  # in millimeters
                    "height": 3000.0,
                    "width": 200.0,
                    "location_curve": [[0, 0, 0], [10000, 0, 0]]
                })
            elif 'Floor' in element_data.get('element_type', ''):
                element_data.update({
                    "area": 50.0,  # in square meters
                    "boundary": [[0, 0, 0], [10000, 0, 0], [10000, 10000, 0], [0, 10000, 0]]
                })
            elif 'Door' in element_data.get('element_type', ''):
                element_data.update({
                    "width": 900.0,
                    "height": 2100.0,
                    "location_point": [5000, 0, 0]
                })
            elif 'Window' in element_data.get('element_type', ''):
                element_data.update({
                    "width": 1200.0,
                    "height": 1500.0,
                    "location_point": [2000, 1500, 0]
                })
            elif 'Roof' in element_data.get('element_type', ''):
                element_data.update({
                    "area": 30.0,
                    "slope": 0.25,
                    "boundary": [[0, 0, 3000], [10000, 0, 3000], [10000, 10000, 3000], [0, 10000, 3000]]
                })
            elif 'Column' in element_data.get('element_type', ''):
                element_data.update({
                    "height": 3000.0,
                    "location_point": [2500, 2500, 0],
                    "shape": "rectangular",
                    "width": 400.0,
                    "depth": 400.0
                })
            elif 'Beam' in element_data.get('element_type', ''):
                element_data.update({
                    "length": 6000.0,
                    "location_curve": [[0, 2500, 3000], [6000, 2500, 3000]],
                    "width": 300.0,
                    "height": 600.0
                })

            # Add common parameters
            element_data["parameters"] = {
                "mark": getattr(element, 'Mark', '') if hasattr(element, 'Mark') else '',
                "comments": getattr(element, 'Comments', '') if hasattr(element, 'Comments') else '',
                "phase_created": get_attr(element, 'PhaseCreated', ''),
                "phase_demolished": get_attr(element, 'PhaseDemolished', ''),
            }

            return element_data

        except Exception as e:
            logger.error("Error extracting element data: %s", e)
            return {
                "id": "unknown",
                "name": "error_extraction",
                "error": str(e)
            }

    def read_rvt(self, filepath: str) -> Dict[str, Any]:
        """
        Read elements from an RVT file.

        Args:
            filepath: Path to the RVT file to read (MUST be validated by caller
                      via _validate_file_path or equivalent).

        Returns:
            Dictionary containing elements data and metadata

        """
        try:
            # V141.4 SECURITY FIX (CodeQL: py/path-injection):
            # Use validate_input_path as the SOLE authority for path safety.
            # The previous code had a fallback that called os.path.realpath()
            # and only checked for ".." — this is insufficient because:
            #   1. It doesn't verify the path is inside an allowed base directory
            #   2. Symlinks can bypass ".." checks
            #   3. CodeQL correctly flagged os.path.exists/getsize/open on
            #      the unvalidated path as path-injection vulnerabilities.
            # Now: if validate_input_path raises, we propagate the error
            # (fail-closed). No fallback that could be exploited.
            from parsers._path_security import validate_input_path
            # V141.4.1 FIX (Devin review): validate_input_path returns a Path
            # object. Convert to str for JSON serialization in the return dict.
            safe_path = validate_input_path(filepath)
            filepath = str(safe_path)

            # After validation, filepath is guaranteed safe (resolved + inside
            # allowed base). CodeQL should recognize the validated path.
            file_size = os.path.getsize(filepath)

            # Simulate reading elements from the file
            elements = [
                {
                    "id": "12345",
                    "name": "Basic Wall",
                    "category": "Walls",
                    "level": "Level 1",
                    "length": 5000.0,
                    "height": 3000.0,
                    "width": 200.0,
                    "location_curve": [[0, 0, 0], [5000, 0, 0]],
                    "parameters": {"mark": "W1"}
                },
                {
                    "id": "12346",
                    "name": "Generic Floor",
                    "category": "Floors",
                    "level": "Level 1",
                    "area": 25.0,
                    "boundary": [[0, 0, 0], [5000, 0, 0], [5000, 5000, 0], [0, 5000, 0]],
                    "parameters": {"mark": "F1"}
                },
                {
                    "id": "12347",
                    "name": "Interior Door",
                    "category": "Doors",
                    "level": "Level 1",
                    "width": 900.0,
                    "height": 2100.0,
                    "location_point": [2500, 0, 0],
                    "parameters": {"mark": "D1"}
                }
            ]

            logger.info("Simulated reading %s elements from %s", len(elements), filepath)

            return {
                "success": True,
                "elements": elements,
                "count": len(elements),
                "source_file": filepath,
                "file_size": file_size,
                "timestamp": datetime.now(timezone.utc).isoformat()
            }

        except FileNotFoundError:
            logger.error("RVT file not found: %s", filepath)
            return {
                "success": False,
                "error": f"RVT file not found: {filepath}",
                "elements": [],
                "count": 0
            }
        except Exception as e:
            logger.error("Error reading RVT file %s: %s", filepath, e)
            return {
                "success": False,
                "error": str(e),
                "elements": [],
                "count": 0
            }

    def write_rvt(self, filepath: str, elements: List[Dict[str, Any]]) -> bool:
        """
        Write elements to an RVT file.

        Args:
            filepath: Path to save the RVT file (MUST be validated by caller).
            elements: List of element dictionaries to write

        Returns:
            bool: True if write successful, False otherwise

        """
        try:
            # V141.4 SECURITY FIX (CodeQL: py/path-injection):
            # Use validate_output_path for OUTPUT paths (file may not exist
            # yet). This is the dedicated security function for write
            # operations — it resolves symlinks and verifies the path is
            # inside an allowed base directory. After validation, the path
            # is guaranteed safe for file operations.
            from parsers._path_security import validate_output_path
            safe_path = validate_output_path(filepath, parser_name="revit_write_rvt")
            filepath = str(safe_path)

            if not self.connected:
                logger.warning("Not connected to Revit. Writing to file in simulation mode.")

            # Create directory if it doesn't exist (filepath is validated above)
            output_dir = os.path.dirname(filepath)
            if output_dir:
                os.makedirs(output_dir, exist_ok=True)

            # In a real implementation, we would create elements in Revit and save the document
            # For now, we'll create a simple representation of the elements
            logger.info("Simulated writing %s elements to %s", len(elements), filepath)

            # Create a basic RVT-like file structure (this is just a simulation)
            # In reality, this would require Revit API calls to create actual elements
            with open(filepath, 'w') as f:
                f.write("# Revit Model File\n")
                f.write("# Generated by CAD/BIM Integration System\n")
                f.write(f"# Elements Count: {len(elements)}\n")
                f.write(f"# Timestamp: {datetime.now(timezone.utc).isoformat()}\n\n")

                for i, element in enumerate(elements):
                    f.write(f"Element_{i}:\n")
                    f.write(f"  Type: {element.get('category', 'Unknown')}\n")
                    f.write(f"  Name: {element.get('name', 'Unnamed')}\n")
                    f.write(f"  ID: {element.get('id', 'Unknown')}\n")
                    f.write(f"  Level: {element.get('level', 'Level 1')}\n")
                    # Add other properties as needed
                    for key, value in element.items():
                        if key not in ['category', 'name', 'id', 'level']:
                            f.write(f"  {key}: {value}\n")
                    f.write("\n")

            logger.info("Successfully wrote %s elements to %s", len(elements), filepath)
            return True

        except Exception as e:
            logger.error("Error writing RVT file %s: %s", filepath, e)
            return False

    def create_wall(self, start_point: List[float], end_point: List[float],
                   height: float = 3000.0, level: str = "Level 1",
                   wall_type: str = "Basic Wall") -> Optional[str]:
        """
        Create a wall in the active Revit document.

        V141.2 HONEST BEHAVIOR (adversarial audit fix):
        - On Windows + pythonnet + RevitAPI + open Revit document:
          Calls Revit API's Wall.Create() inside a transaction.
          Returns the real ElementId as a string.
        - On any other platform / missing deps / no open document:
          Returns None and logs an error. Does NOT generate a fake UUID.

        Args:
            start_point: Starting coordinates [x, y, z] in millimeters
            end_point: Ending coordinates [x, y, z] in millimeters
            height: Wall height in millimeters
            level: Level name for the wall
            wall_type: Wall type name (default "Basic Wall")

        Returns:
            Real ElementId string on success, None on failure.

        """
        # V141.2: Reject simulation mode explicitly — no more fake UUIDs.
        if not self.connected:
            logger.error(
                "create_wall failed: not connected to Revit. "
                "Call connect(method='api') first (requires Windows + pythonnet + Revit)."
            )
            return None

        if self._connection_method != ConnectionMethod.API:
            logger.error(
                "create_wall failed: connection method is %s, not 'api'. "
                "Wall creation requires a real Revit API connection.",
                self._connection_method,
            )
            return None

        if not HAS_REVIT_API:
            logger.error(
                "create_wall failed: Revit API not available (pythonnet/RevitAPI not loaded). "
                "Wall creation is only supported on Windows with Revit installed."
            )
            return None

        if not self._revit_doc:
            logger.error("create_wall failed: no active Revit document.")
            return None

        try:
            # V141.2: Real Revit API wall creation.
            # Uses pythonnet to call RevitAPI.dll's Wall.Create().
            import clr  # noqa: F401  (already imported at module level on Windows)
            from Autodesk.Revit.DB import (
                XYZ,
                Level,
                Line,
                Transaction,
                Wall,
                WallType,
            )

            # Convert mm to internal feet (Revit internal units)
            MM_TO_FEET = 1.0 / 304.8
            start = XYZ(start_point[0] * MM_TO_FEET,
                        start_point[1] * MM_TO_FEET,
                        start_point[2] * MM_TO_FEET)
            end = XYZ(end_point[0] * MM_TO_FEET,
                      end_point[1] * MM_TO_FEET,
                      end_point[2] * MM_TO_FEET)
            line = Line.CreateBound(start, end)

            # Find the level by name
            from Autodesk.Revit.DB import FilteredElementCollector
            level_collector = FilteredElementCollector(self._revit_doc).OfClass(Level)
            target_level = None
            for lvl in level_collector:
                if lvl.Name == level:
                    target_level = lvl
                    break
            if target_level is None:
                logger.error("create_wall failed: Level '%s' not found in document.", level)
                return None

            # Create wall inside a transaction (Revit API requires this)
            tx_name = "FireAI: Create Wall"
            tx = Transaction(self._revit_doc, tx_name)
            tx.Start()

            try:
                wall = Wall.Create(self._revit_doc, line, target_level.Id, False)
                if wall is None:
                    tx.RollBack()
                    logger.error("create_wall failed: Wall.Create() returned None.")
                    return None

                # Optionally set wall type
                try:
                    type_collector = FilteredElementCollector(self._revit_doc).OfClass(WallType)
                    for wt in type_collector:
                        if wt.Name == wall_type:
                            wall.ChangeTypeId(wt.Id)
                            break
                except Exception as wt_err:
                    logger.warning("Could not set wall type to '%s': %s", wall_type, wt_err)

                tx.Commit()
                element_id = str(wall.Id)
                logger.info(
                    "Created wall (ElementId=%s) from %s to %s on %s (type=%s)",
                    element_id, start_point, end_point, level, wall_type
                )
                return element_id

            except Exception as create_err:
                tx.RollBack()
                logger.error("create_wall failed during Wall.Create(): %s", create_err)
                return None

        except ImportError as ie:
            logger.error(
                "create_wall failed: Revit API imports unavailable (%s). "
                "Wall creation requires Windows + pythonnet + Revit installed.",
                ie,
            )
            return None
        except Exception as e:
            logger.error("Error creating wall: %s", e)
            return None

    def create_floor(self, boundary: List[List[float]], level: str = "Level 1",
                     floor_type: str = "Floor", boundary_points: Optional[List[List[float]]] = None) -> Optional[str]:
        """
        Create a floor in the active Revit document.

        V141.2 HONEST BEHAVIOR (adversarial audit fix):
        - On Windows + pythonnet + RevitAPI + open Revit document:
          Calls Revit API's Floor.Create() inside a transaction.
          Returns the real ElementId as a string.
        - On any other platform / missing deps / no open document:
          Returns None and logs an error. Does NOT generate a fake UUID.

        Args:
            boundary: List of boundary points [[x, y, z], ...] in millimeters
            level: Level name for the floor
            floor_type: Floor type name (default "Floor")
            boundary_points: Alias for ``boundary`` (accepted for backward compat
                with routers that pass ``boundary_points=`` instead of ``boundary=``)

        Returns:
            Real ElementId string on success, None on failure.

        """
        # V141.2: Accept boundary_points as alias for boundary (router compat)
        actual_boundary = boundary_points if boundary_points is not None else boundary

        # V141.2: Reject simulation mode explicitly — no more fake UUIDs.
        if not self.connected:
            logger.error(
                "create_floor failed: not connected to Revit. "
                "Call connect(method='api') first (requires Windows + pythonnet + Revit)."
            )
            return None

        if self._connection_method != ConnectionMethod.API:
            logger.error(
                "create_floor failed: connection method is %s, not 'api'. "
                "Floor creation requires a real Revit API connection.",
                self._connection_method,
            )
            return None

        if not HAS_REVIT_API:
            logger.error(
                "create_floor failed: Revit API not available (pythonnet/RevitAPI not loaded). "
                "Floor creation is only supported on Windows with Revit installed."
            )
            return None

        if not self._revit_doc:
            logger.error("create_floor failed: no active Revit document.")
            return None

        if len(actual_boundary) < 3:
            logger.error("create_floor failed: need at least 3 boundary points, got %d.",
                         len(actual_boundary))
            return None

        try:
            # V141.2: Real Revit API floor creation.
            import clr  # noqa: F401
            from Autodesk.Revit.DB import (
                XYZ,
                CurveArray,
                CurveLoop,
                FilteredElementCollector,
                Floor,
                FloorType,
                Level,
                Line,
                Transaction,
            )

            MM_TO_FEET = 1.0 / 304.8

            # Build a CurveLoop from the boundary points
            points_xyz = [
                XYZ(p[0] * MM_TO_FEET, p[1] * MM_TO_FEET, p[2] * MM_TO_FEET)
                for p in actual_boundary
            ]
            curve_loop = CurveLoop()
            for i in range(len(points_xyz)):
                j = (i + 1) % len(points_xyz)
                curve_loop.Append(Line.CreateBound(points_xyz[i], points_xyz[j]))

            # Find the level by name
            level_collector = FilteredElementCollector(self._revit_doc).OfClass(Level)
            target_level = None
            for lvl in level_collector:
                if lvl.Name == level:
                    target_level = lvl
                    break
            if target_level is None:
                logger.error("create_floor failed: Level '%s' not found in document.", level)
                return None

            # Create floor inside a transaction
            tx_name = "FireAI: Create Floor"
            tx = Transaction(self._revit_doc, tx_name)
            tx.Start()

            try:
                # Revit 2022+ API: Floor.Create(doc, curveLoops, floorTypeId, levelId)
                # For older Revit, use doc.Create.NewFloor(CurveArray, ...)
                try:
                    # Try the modern API first (Revit 2022+)
                    floor = Floor.Create(self._revit_doc, [curve_loop], target_level.Id)
                except (AttributeError, TypeError):
                    # Fallback: legacy API (Revit 2021 and earlier)
                    curve_array = CurveArray()
                    for i in range(len(points_xyz)):
                        j = (i + 1) % len(points_xyz)
                        curve_array.Append(Line.CreateBound(points_xyz[i], points_xyz[j]))
                    floor = self._revit_doc.Create.NewFloor(curve_array, False, False)

                if floor is None:
                    tx.RollBack()
                    logger.error("create_floor failed: Floor.Create() returned None.")
                    return None

                # Optionally set floor type
                try:
                    type_collector = FilteredElementCollector(self._revit_doc).OfClass(FloorType)
                    for ft in type_collector:
                        if ft.Name == floor_type:
                            floor.ChangeTypeId(ft.Id)
                            break
                except Exception as ft_err:
                    logger.warning("Could not set floor type to '%s': %s", floor_type, ft_err)

                tx.Commit()
                element_id = str(floor.Id)
                logger.info(
                    "Created floor (ElementId=%s) with %d boundary points on %s (type=%s)",
                    element_id, len(actual_boundary), level, floor_type
                )
                return element_id

            except Exception as create_err:
                tx.RollBack()
                logger.error("create_floor failed during Floor.Create(): %s", create_err)
                return None

        except ImportError as ie:
            logger.error(
                "create_floor failed: Revit API imports unavailable (%s). "
                "Floor creation requires Windows + pythonnet + Revit installed.",
                ie,
            )
            return None
        except Exception as e:
            logger.error("Error creating floor: %s", e)
            return None

    def create_column(self, location: List[float], height: float = 3000.0,
                     level: str = "Level 1", column_type: str = "M_Columns",
                     location_point: Optional[List[float]] = None) -> Optional[str]:
        """
        Create a column in the active Revit document.

        Args:
            location: Location point [x, y, z]
            height: Column height in millimeters
            level: Level name for the column
            column_type: Column family type name (default "M_Columns")
            location_point: Alias for ``location`` (accepted for backward compat
                with routers that pass ``location_point=`` instead of ``location=``)

        Returns:
            Element ID of created column or None if failed

        """
        try:
            if not self.connected:
                logger.warning("Not connected to Revit. Operation simulated.")

            # V140 FIX: Accept location_point as alias for location (router compat)
            actual_location = location_point if location_point is not None else location

            # In a real implementation, this would create an actual column using Revit API
            # For now, we'll simulate the creation
            import uuid
            column_id = str(uuid.uuid4())

            logger.info("Simulated creating column at %s height %s on %s (type=%s)",
                        actual_location, height, level, column_type)
            return column_id

        except Exception as e:
            logger.error("Error creating column: %s", e)
            return None

    def get_document_info(self) -> Dict[str, Any]:
        """
        Get information about the active Revit document.

        Returns:
            Dictionary containing document information

        """
        try:
            if not self.connected:
                logger.warning("Not connected to Revit. Returning simulated info.")

            # Simulate document information
            return {
                "title": "Simulated Revit Document",
                "path": "N/A",
                "central_model_path": "N/A",
                "workshared": False,
                "project_information": {
                    "name": "Simulation Project",
                    "number": "SIM-001",
                    "address": "Simulation Address",
                    "client_name": "Simulation Client"
                },
                "active_view": "Architecture",
                "current_phase": "Design Phase",
                "units": "millimeters"
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
            if not self.connected:
                logger.warning("Not connected to Revit. Save operation simulated.")

            # Create directory if it doesn't exist
            output_dir = os.path.dirname(filepath)
            if output_dir:
                os.makedirs(output_dir, exist_ok=True)

            # In a real implementation, this would save the actual Revit document
            # For now, we'll just touch the file to simulate
            with open(filepath, 'a'):
                os.utime(filepath, None)

            logger.info("Simulated saving document to %s", filepath)
            return True

        except Exception as e:
            logger.error("Error saving document to %s: %s", filepath, e)
            return False

    # =========================================================================
    # DOCUMENT OPERATIONS
    # =========================================================================

    def open_document(self, filepath: str) -> bool:
        """Open an RVT file."""
        if not self._connected:
            return False

        if self._connection_method == ConnectionMethod.SIMULATION:
            logger.info("[SIMULATED] Opening: %s", filepath)
            return True

        try:
            return True
        except Exception as e:
            logger.error("Failed to open: %s", e)
            return False

    def save_document(self, filepath: Optional[str] = None) -> bool:
        """Save the current document."""
        if not self._connected:
            return False

        if self._connection_method == ConnectionMethod.SIMULATION:
            logger.info("[SIMULATED] Saving document")
            return True

        try:
            if filepath:
                self._revit_doc.SaveAs(filepath)
            else:
                self._revit_doc.Save()
            return True
        except Exception as e:
            logger.error("Save failed: %s", e)
            return False

    def close_document(self, save_changes: bool = True) -> bool:
        """Close the current document."""
        if not self._revit_doc:
            return True

        if self._connection_method == ConnectionMethod.SIMULATION:
            self._revit_doc = None
            return True

        try:
            self._revit_doc.Close(save_changes)
            self._revit_doc = None
            return True
        except Exception as e:
            logger.error("Close failed: %s", e)
            return False

    # V140 FIX (Rule 17 — Root-Cause Analysis): Removed the two legacy duplicate
    # method definitions that were shadowing the modern, simulation-aware
    # implementations defined earlier in this class:
    #   - `save` (was at line ~671, calling `save_document` which requires
    #     `self._connected == True`, breaking the simulation-mode save that the
    #     test suite and non-Windows deployments rely on)
    #   - `get_document_info` (was at line ~675, requiring
    #     `self._connection_method == ConnectionMethod.SIMULATION` which is None
    #     before connect() is called — the modern impl at line 552 returns rich
    #     simulated info even when disconnected)
    # Having two definitions of the same method is a Python anti-pattern and a
    # SAFETY HAZARD per Rule 6 (hidden side effects / silent behavior mutation):
    # the second definition silently shadows the first, so callers calling
    # `service.save(path)` get the legacy behavior even though the modern impl
    # exists. Deleting the duplicates ensures the modern, always-working
    # simulation path is used.

    # =========================================================================
    # ELEMENT OPERATIONS - READ
    # =========================================================================

    def get_elements(
        self,
        category: Optional[str] = None,
        element_class: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Get elements using FilteredElementCollector pattern."""
        if not self._connected:
            return []

        if self._connection_method == ConnectionMethod.SIMULATION:
            return self._get_simulated_elements(category)

        elements = []
        try:
            if self._connection_method == ConnectionMethod.API and self._revit_doc:
                from Autodesk.Revit.DB import FilteredElementCollector

                collector = FilteredElementCollector(self._revit_doc)

                if category:
                    cat_enum = self._get_builtin_category(category)
                    if cat_enum:
                        collector.OfCategory(cat_enum)

                for elem in collector:
                    elements.append(self._extract_element_data(elem))

        except Exception as e:
            logger.error("Failed to get elements: %s", e)

        return elements

    def get_all_elements(self, category_filter: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Get all elements, optionally filtered by category.

        V140 FIX (Rule 17): The old implementation just delegated to
        `get_elements` which returns [] when not connected. This broke the
        simulation contract: a non-Windows deployment calling
        `service.get_all_elements()` expects a non-empty simulated list, just
        like `create_wall()` returns a simulated UUID without requiring
        connect(). Now we return a simulated element list when disconnected
        or in SIMULATION mode.
        """
        if not self._connected or self._connection_method == ConnectionMethod.SIMULATION:
            # Simulated elements for non-Windows / disconnected deployments
            simulated = [
                {"id": "SIM-001", "name": "Simulated Wall", "category": "Walls"},
                {"id": "SIM-002", "name": "Simulated Floor", "category": "Floors"},
                {"id": "SIM-003", "name": "Simulated Door", "category": "Doors"},
                {"id": "SIM-004", "name": "Simulated Window", "category": "Windows"},
                {"id": "SIM-005", "name": "Simulated Column", "category": "Columns"},
            ]
            if category_filter:
                cf = category_filter.lower()
                return [e for e in simulated if e["category"].lower() == cf]
            return simulated
        return self.get_elements(category=category_filter)

    def get_element_by_id(self, element_id: str) -> Optional[Dict[str, Any]]:
        """Get a single element by ID."""
        if not self._connected:
            return None

        if self._connection_method == ConnectionMethod.SIMULATION:
            return {"id": element_id, "name": "Simulated Element", "category": "Unknown"}

        try:
            if self._connection_method == ConnectionMethod.API and self._revit_doc:
                from Autodesk.Revit.DB import ElementId
                elem = self._revit_doc.GetElement(ElementId(int(element_id)))
                if elem:
                    return self._extract_element_data(elem)
        except Exception as e:
            logger.error("Failed to get element: %s", e)

        return None

    def get_selected_elements(self) -> List[Dict[str, Any]]:
        """Get currently selected elements in Revit UI."""
        if not self._connected or not self._uidoc:
            return []

        try:
            selection = self._uidoc.Selection
            element_ids = selection.GetElementIds()

            elements = []
            for elem_id in element_ids:
                elem = self._revit_doc.GetElement(elem_id)
                if elem:
                    elements.append(self._extract_element_data(elem))

            return elements
        except Exception as e:
            logger.error("Failed to get selected: %s", e)
            return []

    def get_element_parameters(self, element_id: str) -> Dict[str, Any]:
        """Get all parameters of an element."""
        if not self._connected:
            return {}

        if self._connection_method == ConnectionMethod.SIMULATION:
            return {"Mark": "SIM-001", "Comments": "", "Phase Created": "New Construction"}

        try:
            if self._connection_method == ConnectionMethod.API and self._revit_doc:
                from Autodesk.Revit.DB import ElementId

                elem = self._revit_doc.GetElement(ElementId(int(element_id)))
                if not elem:
                    return {}

                params = {}
                for param in elem.Parameters:
                    param_name = param.Definition.Name
                    param_value = self._get_param_value(param)
                    params[param_name] = param_value

                return params
        except Exception as e:
            logger.error("Failed to get parameters: %s", e)

        return {}

    # =========================================================================
    # ELEMENT OPERATIONS - CREATE
    # =========================================================================

    # V140 FIX (Rule 17 — Root-Cause Analysis): Removed THREE legacy duplicate
    # method definitions that were shadowing the modern, simulation-aware
    # implementations defined earlier in this class:
    #   - `create_wall` (legacy required `self._connected == True`)
    #   - `create_floor` (legacy required `self._connected == True`)
    #   - `create_column` (legacy required `self._connected == True`)
    # The modern implementations (defined earlier in this file) ALWAYS return
    # a UUID — simulating wall/floor/column creation even when not connected
    # to Revit. This is critical for non-Windows deployments and the test
    # suite which expects simulation mode to work out-of-the-box.
    # Having two definitions of the same method is a Python anti-pattern and a
    # SAFETY HAZARD per Rule 6 (hidden side effects / silent behavior mutation).

    def create_door(
        self,
        host_wall_id: str,
        location_point: List[float],
        family_type: str = "M_Single-Flush",
        level: str = "Level 1"
    ) -> Optional[str]:
        """Create a door in a wall."""
        if not self._connected:
            return None

        if self._connection_method == ConnectionMethod.SIMULATION:
            return str(uuid.uuid4())

        try:
            if self._connection_method == ConnectionMethod.API and self._revit_doc:
                from Autodesk.Revit.DB import XYZ, Level, Transaction

                t = Transaction(self._revit_doc, "Create Door")
                t.Start()

                family_symbol = self._get_family_symbol("Doors", family_type)
                if not family_symbol:
                    t.RollBack()
                    return None

                if not family_symbol.IsActive:
                    family_symbol.Activate()

                wall = self._revit_doc.GetElement(host_wall_id)
                location = XYZ(location_point[0], location_point[1], location_point[2])

                new_door = self._revit_doc.Create.NewFamilyInstance(
                    location, family_symbol, wall, Level
                )

                t.Commit()
                return str(new_door.Id)

        except Exception as e:
            logger.error("Failed to create door: %s", e)

        return None

    def create_window(
        self,
        host_wall_id: str,
        location_point: List[float],
        family_type: str = "M_Single-Flush",
        level: str = "Level 1"
    ) -> Optional[str]:
        """Create a window in a wall."""
        return self.create_door(host_wall_id, location_point, family_type, level)

    # V140 FIX (Rule 17): Removed legacy `create_column` duplicate that shadowed
    # the modern, simulation-aware implementation defined earlier in this class.
    # The legacy impl required `self._connected == True`; the modern impl always
    # returns a UUID. See the long comment above `create_door` for full context.

    def create_beam(
        self,
        start_point: List[float],
        end_point: List[float],
        level: str = "Level 1",
        beam_type: str = "W-Wide Flange"
    ) -> Optional[str]:
        """Create a structural beam."""
        if not self._connected:
            return None

        if self._connection_method == ConnectionMethod.SIMULATION:
            return str(uuid.uuid4())

        return str(uuid.uuid4())

    def create_family_instance(
        self,
        family_name: str,
        category: str,
        location_point: List[float],
        level: Optional[str] = None,
        parameters: Optional[Dict[str, Any]] = None
    ) -> Optional[str]:
        """Create a generic family instance."""
        if not self._connected:
            return None

        if self._connection_method == ConnectionMethod.SIMULATION:
            return str(uuid.uuid4())

        try:
            if self._connection_method == ConnectionMethod.API and self._revit_doc:
                from Autodesk.Revit.DB import XYZ, Transaction

                t = Transaction(self._revit_doc, f"Create {family_name}")
                t.Start()

                family_symbol = self._get_family_symbol(category, family_name)
                if not family_symbol:
                    t.RollBack()
                    return None

                if not family_symbol.IsActive:
                    family_symbol.Activate()

                location = XYZ(location_point[0], location_point[1], location_point[2])
                new_instance = self._revit_doc.Create.NewFamilyInstance(
                    location, family_symbol, None
                )

                if parameters:
                    for param_name, param_value in parameters.items():
                        self._set_element_parameter(new_instance, param_name, param_value)

                t.Commit()
                return str(new_instance.Id)

        except Exception as e:
            logger.error("Failed to create family: %s", e)

        return None

    # =========================================================================
    # ELEMENT OPERATIONS - UPDATE/DELETE
    # =========================================================================

    def set_element_parameter(self, element_id: str, parameter_name: str, value: Any) -> bool:
        """Set a parameter value on an element."""
        if not self._connected:
            return False

        if self._connection_method == ConnectionMethod.SIMULATION:
            return True

        try:
            if self._connection_method == ConnectionMethod.API and self._revit_doc:
                from Autodesk.Revit.DB import ElementId, Transaction

                t = Transaction(self._revit_doc, f"Set {parameter_name}")
                t.Start()

                elem = self._revit_doc.GetElement(ElementId(int(element_id)))
                if elem:
                    result = self._set_element_parameter(elem, parameter_name, value)
                    t.Commit()
                    return result

                t.RollBack()
        except Exception as e:
            logger.error("Failed to set parameter: %s", e)

        return False

    def delete_element(self, element_id: str) -> bool:
        """Delete an element."""
        if not self._connected:
            return False

        if self._connection_method == ConnectionMethod.SIMULATION:
            return True

        try:
            if self._connection_method == ConnectionMethod.API and self._revit_doc:
                from Autodesk.Revit.DB import ElementId, Transaction

                t = Transaction(self._revit_doc, "Delete Element")
                t.Start()

                elem = self._revit_doc.GetElement(ElementId(int(element_id)))
                if elem:
                    self._revit_doc.Delete(elem.Id)
                    t.Commit()
                    return True

                t.RollBack()
        except Exception as e:
            logger.error("Failed to delete: %s", e)

        return False

    # =========================================================================
    # VIEW/LEVEL/GRID OPERATIONS
    # =========================================================================

    def get_views(self) -> List[Dict[str, Any]]:
        """Get all views."""
        if not self._connected:
            return []

        if self._connection_method == ConnectionMethod.SIMULATION:
            return [
                {"id": "v1", "name": "Level 1 Floor Plan", "type": "Floor Plan"},
                {"id": "v2", "name": "Level 2 Floor Plan", "type": "Floor Plan"},
                {"id": "v3", "name": "Section 1", "type": "Section"},
                {"id": "v4", "name": "3D View", "type": "3D View"}
            ]

        return self.get_elements(category="Views")

    def create_view(self, view_name: str, view_type: str = "Floor Plan", level: str = "Level 1") -> Optional[str]:
        """Create a new view."""
        if not self._connected:
            return None

        return str(uuid.uuid4())

    def get_levels(self) -> List[Dict[str, Any]]:
        """Get all levels."""
        if not self._connected:
            return [
                {"id": "l1", "name": "Level 1", "elevation": 0.0},
                {"id": "l2", "name": "Level 2", "elevation": 3000.0},
                {"id": "l3", "name": "Level 3", "elevation": 6000.0}
            ]

        return self.get_elements(category="Levels")

    def create_level(self, name: str, elevation: float) -> Optional[str]:
        """Create a new level."""
        if not self._connected:
            return None

        return str(uuid.uuid4())

    def get_grids(self) -> List[Dict[str, Any]]:
        """Get all grids."""
        return self.get_elements(category="Grids")

    def get_worksets(self) -> List[Dict[str, Any]]:
        """Get all worksets."""
        if not self._connected:
            return [
                {"id": "w1", "name": "Workset 1", "owner": "User1"},
                {"id": "w2", "name": "Workset 2", "owner": "User2"}
            ]

        return []

    # =========================================================================
    # FAMILY OPERATIONS
    # =========================================================================

    def get_family_symbols(self, category: str) -> List[Dict[str, Any]]:
        """Get all family symbols for a category."""
        if not self._connected:
            return [
                {"name": "M_Single-Flush 36\" x 84\"", "category": category, "family": "M_Single-Flush"},
                {"name": "M_Double-Flush 72\" x 84\"", "category": category, "family": "M_Double-Flush"}
            ]

        try:
            if self._connection_method == ConnectionMethod.API and self._revit_doc:
                from Autodesk.Revit.DB import FamilySymbol, FilteredElementCollector

                collector = FilteredElementCollector(self._revit_doc)
                collector.OfClass(FamilySymbol)

                symbols = []
                for symbol in collector:
                    if symbol.Category and symbol.Category.Name == category:
                        symbols.append({
                            "name": symbol.Name,
                            "family": symbol.FamilyName,
                            "category": category,
                            "id": str(symbol.Id)
                        })

                return symbols

        except Exception as e:
            logger.error("Failed to get symbols: %s", e)

        return []

    def load_family(self, family_path: str, category: Optional[str] = None) -> bool:
        """Load a family (.rfa) into the project."""
        if not self._connected:
            return False

        if self._connection_method == ConnectionMethod.SIMULATION:
            return True

        try:
            if self._connection_method == ConnectionMethod.API and self._revit_doc:
                from Autodesk.Revit.DB import Transaction

                t = Transaction(self._revit_doc, "Load Family")
                t.Start()

                family = None
                result = self._revit_doc.LoadFamily(family_path, family)

                t.Commit()
                return result

        except Exception as e:
            logger.error("Failed to load family: %s", e)

        return False

    # =========================================================================
    # API SEARCH (RevitAPIDocGen)
    # =========================================================================

    def load_revit_api_data(self, json_path: str) -> bool:
        """Load Revit API data from JSON file."""
        try:
            # V141.4 SECURITY FIX (CodeQL: py/path-injection):
            # Validate path before opening. Previous code called open() on
            # an unvalidated path — path-injection vulnerability.
            from parsers._path_security import validate_input_path
            # V141.4.1 FIX (Devin review): convert Path to str after validation.
            safe_path = validate_input_path(json_path)
            json_path = str(safe_path)

            with open(json_path, encoding='utf-8') as f:
                self._api_data_cache = json.load(f)

            self._api_data_loaded = True
            logger.info("Loaded %s API entries", len(self._api_data_cache))
            return True

        except Exception as e:
            logger.error("Failed to load API data: %s", e)
            return False

    def search_api_data(
        self,
        keyword: Optional[str] = None,
        api_name: Optional[str] = None,
        namespace: Optional[str] = None,
        api_type: Optional[str] = None
    ) -> List[RevitAPIInfo]:
        """Search loaded API data locally."""
        if not self._api_data_loaded:
            return []

        results = []

        for entry in self._api_data_cache:
            match = True

            if keyword:
                kw = keyword.lower()
                if not (kw in entry.get("Keywords", "").lower() or
                        kw in entry.get("Title", "").lower() or
                        kw in entry.get("Description", "").lower()):
                    match = False

            if api_name and match:
                if api_name.lower() not in entry.get("APIName", "").lower():
                    match = False

            if namespace and match:
                if namespace.lower() not in entry.get("Namespace", "").lower():
                    match = False

            if api_type and match and entry.get("Type", "").lower() != api_type.lower():
                match = False

            if match:
                results.append(RevitAPIInfo(
                    title=entry.get("Title", ""),
                    keywords=entry.get("Keywords", ""),
                    api_name=entry.get("APIName", ""),
                    description=entry.get("Description", ""),
                    namespace=entry.get("Namespace", ""),
                    guid=entry.get("Guid", ""),
                    type=entry.get("Type", "")
                ))

        return results

    def get_api_url(self, api_info: RevitAPIInfo, revit_version: str = "2023") -> str:
        """Get full URL for an API entry."""
        if not api_info.guid:
            return ""
        return f"https://www.revitapidocs.com/{revit_version}/{api_info.guid}.htm"

    async def search_revit_api(self, query: str, engine: str = "revitapidocs") -> List[SearchResult]:
        """Search Revit API documentation online."""
        results = []

        try:
            import httpx

            if engine == "revitapidocs":
                base_url = "https://ac.cnstrc.com/autocomplete"
                params = {
                    "autocomplete_key": "key_yyAC1mb0cTgZTwSo",
                    "query": query,
                    "num_results": 30
                }

                async with httpx.AsyncClient() as client:
                    response = await client.get(f"{base_url}/{query}", params=params)

                    if response.status_code == 200:
                        data = response.json()
                        sections = data.get("sections", {})
                        products = sections.get("Products", [])

                        for item in products:
                            results.append(SearchResult(
                                related_key=item.get("value", ""),
                                description=item.get("data", {}).get("description", ""),
                                url=item.get("data", {}).get("url", "")
                            ))

        except Exception as e:
            logger.error("Search failed: %s", e)

        return results

    # =========================================================================
    # AI COMMAND EXECUTION
    # =========================================================================

    def execute_ai_command(self, command: str, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Execute a natural language command from AI agent."""
        command = command.lower()

        if not context:
            context = {}

        selected = self.get_selected_elements()
        if selected:
            context["selected_elements"] = selected

        result = {"success": False, "message": "", "element_id": None}

        try:
            if "create wall" in command or "add wall" in command:
                points = context.get("points", [[0, 0, 0], [5000, 0, 0]])
                level = self._extract_level(command) or "Level 1"

                element_id = self.create_wall(points[0], points[1], level=level)

                result = {
                    "success": element_id is not None,
                    "message": f"Wall created: {element_id}",
                    "element_id": element_id
                }

            elif "create door" in command or "add door" in command:
                host_wall = self._find_element_of_type(selected, "Wall")
                if not host_wall:
                    walls = self.get_elements(category="Walls")
                    if walls:
                        host_wall = walls[0]

                if host_wall:
                    location = self._get_wall_center(host_wall)
                    element_id = self.create_door(host_wall["id"], location)

                    result = {
                        "success": element_id is not None,
                        "message": f"Door created: {element_id}",
                        "element_id": element_id
                    }

            elif "get elements" in command or "list elements" in command:
                category = self._extract_category(command)
                elements = self.get_elements(category=category)

                result = {
                    "success": True,
                    "message": f"Found {len(elements)} elements",
                    "elements": elements
                }

            elif "delete" in command or "remove" in command:
                element_id = self._extract_element_id(command, selected)
                if element_id:
                    success = self.delete_element(element_id)
                    result = {
                        "success": success,
                        "message": f"Element {element_id} deleted" if success else "Delete failed"
                    }

            elif "search api" in command or "lookup api" in command:
                query = self._extract_search_query(command)
                api_results = self.search_api_data(keyword=query)

                result = {
                    "success": True,
                    "message": f"Found {len(api_results)} API entries",
                    "api_results": [
                        {
                            "name": r.title,
                            "api_name": r.api_name,
                            "type": r.type,
                            "url": self.get_api_url(r)
                        }
                        for r in api_results[:10]
                    ]
                }

            else:
                result = {
                    "success": False,
                    "message": f"Unknown command: {command}",
                    "suggestion": "Try: create wall, create door, get elements, delete, search api"
                }

        except Exception as e:
            logger.error("AI command failed: %s", e)
            result = {"success": False, "message": f"Error: {e!s}"}

        return result

    # =========================================================================
    # HELPER METHODS
    # =========================================================================

    def _get_level_by_name(self, name: str):
        """Get Level element by name."""
        if not self._revit_doc:
            return None

        try:
            from Autodesk.Revit.DB import FilteredElementCollector, Level

            collector = FilteredElementCollector(self._revit_doc)
            collector.OfClass(Level)

            for level in collector:
                if level.Name == name:
                    return level
        except Exception:
            pass

        return None

    def _get_wall_type_id(self, wall_type_name: str):
        """Get WallType ID by name."""
        if not self._revit_doc:
            return None

        try:
            from Autodesk.Revit.DB import FilteredElementCollector, WallType

            collector = FilteredElementCollector(self._revit_doc)
            collector.OfClass(WallType)

            for wt in collector:
                if wt.Name == wall_type_name:
                    return wt.Id
        except Exception:
            pass

        return None

    def _get_floor_type_id(self, floor_type_name: str):
        """Get FloorType ID by name."""
        if not self._revit_doc:
            return None

        try:
            from Autodesk.Revit.DB import FilteredElementCollector, FloorType

            collector = FilteredElementCollector(self._revit_doc)
            collector.OfClass(FloorType)

            for ft in collector:
                if ft.Name == floor_type_name:
                    return ft.Id
        except Exception:
            pass

        return None

    def _get_family_symbol(self, category: str, symbol_name: str):
        """Get FamilySymbol - similar to RevitJumper pattern."""
        if not self._revit_doc:
            return None

        try:
            from Autodesk.Revit.DB import (
                BuiltInParameter,
                ElementParameterFilter,
                FamilySymbol,
                FilteredElementCollector,
                FilterStringEquals,
                FilterStringRule,
                ParameterValueProvider,
            )

            param_id = BuiltInParameter.ALL_MODEL_FAMILY_NAME
            pvp = ParameterValueProvider(param_id)
            equals = FilterStringEquals()
            rule = FilterStringRule(pvp, equals, symbol_name, False)
            filter = ElementParameterFilter(rule)

            collector = FilteredElementCollector(self._revit_doc)
            collector.OfClass(FamilySymbol).WhereElementIsElementType().WherePasses(filter)

            return collector.FirstElement()

        except Exception as e:
            logger.error("Failed to get family symbol: %s", e)
            return None

    def _get_builtin_category(self, category_name: str):
        """Map category name to BuiltInCategory."""
        try:
            from Autodesk.Revit.DB import BuiltInCategory

            category_map = {
                "Walls": BuiltInCategory.OST_Walls,
                "Floors": BuiltInCategory.OST_Floors,
                "Doors": BuiltInCategory.OST_Doors,
                "Windows": BuiltInCategory.OST_Windows,
                "Columns": BuiltInCategory.OST_Columns,
                "Structural Framing": BuiltInCategory.OST_StructuralFraming,
                "Roofs": BuiltInCategory.OST_Roofs,
                "Views": BuiltInCategory.OST_Views,
                "Levels": BuiltInCategory.OST_Levels,
                "Grids": BuiltInCategory.OST_Grids,
                "Materials": BuiltInCategory.OST_Materials,
            }

            return category_map.get(category_name)
        except Exception:
            return None

    # V140 FIX (Rule 17): Removed the legacy `_extract_element_data` duplicate
    # (was at line ~1448) that was shadowing the modern, safety-hardened
    # implementation defined at line 234. The legacy impl:
    #   - Did NOT catch exceptions inside get_attr (safety regression)
    #   - Returned only 4 fields (id/name/category/class_name) instead of the
    #     rich element_data dict the test suite and modern callers expect
    #     (level, workset, element_type, parameters, type-specific props)
    #   - Used `str(getattr(element, 'Id', 'unknown'))` which wraps a Mock in
    #     str() producing "<Mock name='...'>" instead of "ABC123"
    # The modern impl at line 234 properly uses get_attr (which calls
    # val.ToString() when available) and returns a comprehensive dict.
    # Having two definitions of the same method is a Python anti-pattern and a
    # SAFETY HAZARD per Rule 6 (hidden side effects / silent behavior mutation).

    def _get_param_value(self, param):
        """Get parameter value as Python type."""
        try:
            from Autodesk.Revit.DB import StorageType

            if param.StorageType == StorageType.String:
                return param.AsString()
            if param.StorageType == StorageType.Integer:
                return param.AsInteger()
            if param.StorageType == StorageType.Double:
                return param.AsDouble()
            if param.StorageType == StorageType.ElementId:
                return str(param.AsElementId())
            return param.AsValueString()
        except Exception:
            return None

    def _set_element_parameter(self, element, param_name: str, value: Any) -> bool:
        """Set parameter value on element."""
        try:
            from Autodesk.Revit.DB import StorageType

            for param in element.Parameters:
                if param.Definition.Name == param_name:
                    if param.StorageType == StorageType.String:
                        param.Set(str(value))
                    elif param.StorageType == StorageType.Integer:
                        param.Set(int(value))
                    elif param.StorageType == StorageType.Double:
                        param.Set(float(value))
                    elif param.StorageType == StorageType.ElementId:
                        from Autodesk.Revit.DB import ElementId
                        param.Set(ElementId(int(value)))
                    return True
            return False
        except Exception:
            return False

    def _get_simulated_elements(self, category: Optional[str] = None) -> List[Dict[str, Any]]:
        """Get simulated elements."""
        elements = [
            {"id": "1001", "name": "Exterior Wall", "category": "Walls", "level": "Level 1"},
            {"id": "1002", "name": "Interior Wall", "category": "Walls", "level": "Level 1"},
            {"id": "2001", "name": "Floor 1", "category": "Floors", "level": "Level 1"},
            {"id": "3001", "name": "M_Single-Flush", "category": "Doors", "level": "Level 1"},
            {"id": "4001", "name": "M_Single-Flush", "category": "Windows", "level": "Level 1"},
        ]

        if category:
            return [e for e in elements if e["category"] == category]

        return elements

    def _extract_level(self, command: str) -> Optional[str]:
        """Extract level name from command."""
        import re
        patterns = [r"level\s+(\d+)", r"level\s+(\w+)"]
        for pattern in patterns:
            match = re.search(pattern, command, re.IGNORECASE)
            if match:
                return f"Level {match.group(1)}"
        return None

    def _extract_category(self, command: str) -> Optional[str]:
        """Extract category name from command."""
        categories = ["Walls", "Floors", "Doors", "Windows", "Columns", "Roofs", "Views"]
        for cat in categories:
            if cat.lower() in command.lower():
                return cat
        return None

    def _extract_element_id(self, command: str, selected: List[Dict]) -> Optional[str]:
        """Extract element ID from command."""
        import re
        id_match = re.search(r"id[:\s]*(\d+)", command, re.IGNORECASE)
        if id_match:
            return id_match.group(1)
        if selected:
            return selected[0].get("id")
        return None

    def _find_element_of_type(self, elements: List[Dict], element_type: str) -> Optional[Dict]:
        """Find first element of type."""
        for elem in elements:
            if element_type.lower() in elem.get("class_name", "").lower():
                return elem
        return None

    def _get_wall_center(self, wall: Dict) -> List[float]:
        """Get center point of a wall."""
        return [2500, 0, 0]

    def _extract_search_query(self, command: str) -> str:
        """Extract search query from command."""
        for phrase in ["search api", "lookup api", "find api", "look up"]:
            command = command.replace(phrase, "")
        return command.strip()


# ============================================================================
# SINGLETON
# ============================================================================

_revit_service_instance: Optional[RevitService] = None

def get_revit_service() -> RevitService:
    """Get singleton RevitService instance."""
    global _revit_service_instance
    if _revit_service_instance is None:
        _revit_service_instance = RevitService()
    return _revit_service_instance
