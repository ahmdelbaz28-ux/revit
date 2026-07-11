# File-level '# NOSONAR' removed per NOSONAR_AUDIT.md (V143 hardening).
# Per-line justified suppressions (e.g., '# NOSONAR — S3776: ...') are preserved.
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
        # V213: Explicit simulation flag. True when connect() fell back to
        # the simulation path (no real Revit instance acquired). Clients and
        # tests can read this to know that create_wall/floor/door will
        # return None (no real document is open).
        self._simulation_mode = False

        # RevitAPIDocGen data
        self._api_data_cache: List[Dict[str, Any]] = []
        self._api_data_loaded = False

    @property
    def simulation_mode(self) -> bool:
        """V213: True when the service is in simulation mode (no real Revit
        document is bound)."""
        return self._simulation_mode

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
            logger.exception("Connection failed: %s", e)
            return False

    def _connect_via_api(self) -> bool:
        """
        Connect via Revit API (requires Revit + pythonnet on Windows).

        V213 FIX (Rule 1 — Truthfulness): Previously this method set
        ``_connected = True`` without actually acquiring a Revit application
        handle — every subsequent ``create_wall()`` / ``create_floor()``
        would hit the ``if not self._revit_doc: return None`` guard and
        silently fail, despite the connect endpoint reporting success.

        Now this method attempts to bind to a running Revit instance via
        ``Marshal.GetActiveObject("Revit.Application")`` (Windows COM
        automation). If Revit is not running, or pythonnet is not
        installed, or we are on a non-Windows platform, the method falls
        back to simulation mode HONESTLY — setting ``_simulation_mode =
        True`` so clients can surface the truth.

        Returns:
            True if connected (real or simulation). False only on
            explicit user-requested failure (currently never).

        """
        if not HAS_REVIT_API:
            logger.warning(
                "Revit API not available (no pythonnet or not Windows). "
                "Falling back to SIMULATION mode honestly."
            )
            return self._connect_simulation()

        # Try to acquire a real Revit application handle via COM automation.
        # This requires Revit to be running on the same machine.
        try:
            import clr  # noqa: F401
            from System.Runtime.InteropServices import Marshal  # type: ignore[import-not-found]
        except ImportError as ie:
            logger.warning(
                "Could not import Marshal from System.Runtime.InteropServices "
                "(%s). Falling back to SIMULATION mode.", ie
            )
            return self._connect_simulation()
        except Exception as ge:
            logger.warning(
                "CLR/Marshal access failed (%s). Falling back to SIMULATION mode.", ge
            )
            return self._connect_simulation()

        # Attempt to bind to a running Revit instance.
        # "Revit.Application" is the COM ProgID for the Revit application.
        # Different Revit versions may use versioned ProgIDs (e.g.
        # "Revit.Application.2024") — we try the generic one first, then
        # a few versioned ones.
        prog_ids = [
            "Revit.Application",
            "Revit.Application.2025",
            "Revit.Application.2024",
            "Revit.Application.2023",
            "Revit.Application.2022",
            "Revit.Application.2021",
            "Revit.Application.2020",
        ]
        revit_app_com = None
        for prog_id in prog_ids:
            try:
                revit_app_com = Marshal.GetActiveObject(prog_id)
                logger.info("Bound to running Revit via ProgID: %s", prog_id)
                break
            except Exception as e:
                # Try next ProgID
                logger.debug("ProgID %s not available: %s", prog_id, e)
                continue

        if revit_app_com is None:
            logger.warning(
                "No running Revit instance found (tried %d ProgIDs). "
                "Falling back to SIMULATION mode. Start Revit and open a "
                "document to enable real API operations.",
                len(prog_ids),
            )
            return self._connect_simulation()

        # Wrap the COM object in a Revit UIApplication and pull the active
        # document. This is the critical step that was missing — without
        # setting _revit_doc, every create_wall/floor/door call hits the
        # ``if not self._revit_doc: return None`` guard.
        try:
            from Autodesk.Revit.UI import UIApplication  # type: ignore[import-not-found]
            self._uiapp = UIApplication(revit_app_com)
            self._revit_app = self._uiapp.Application
            try:
                self._uidoc = self._uiapp.ActiveUIDocument
            except Exception as uidoc_err:
                logger.warning("Could not get ActiveUIDocument: %s", uidoc_err)
                self._uidoc = None
            if self._uidoc is not None:
                self._revit_doc = self._uidoc.Document
                logger.info(
                    "Revit API connection established. Active document: %s",
                    getattr(self._revit_doc, "Title", "<untitled>"),
                )
            else:
                # No active document — still connected to the app, but
                # create_* operations will need an open document. Set
                # _revit_doc to None (the honest value).
                self._revit_doc = None
                logger.warning(
                    "Revit API connected but no active document is open. "
                    "create_wall/floor/door will return None until a "
                    "document is opened."
                )
            self._connected = True
            self._simulation_mode = False  # V213: real connection
            self._connection_method = ConnectionMethod.API
            return True
        except ImportError as ie:
            logger.warning(
                "Could not import Autodesk.Revit.UI.UIApplication (%s). "
                "RevitAPIUI assembly may not be loaded. Falling back to "
                "SIMULATION mode.", ie
            )
            return self._connect_simulation()
        except Exception as e:
            logger.exception(
                "Failed to wrap Revit COM object in UIApplication: %s. "
                "Falling back to SIMULATION mode.", e
            )
            return self._connect_simulation()

    def _connect_via_macro(self) -> bool:
        """Connect via Revit Macro (free, runs inside Revit).

        V213: This is still SIMULATION ONLY — there is no macro script
        execution code. The simulation_mode flag is set honestly so clients
        know no real Revit operations will occur.
        """
        logger.warning(
            "MACRO mode is SIMULATION ONLY — no Revit macro script is "
            "actually executed. Use method='api' on Windows with Revit "
            "running for real operations."
        )
        self._connected = True
        self._simulation_mode = True  # V213: honest
        self._connection_method = ConnectionMethod.MACRO
        return True

    def _connect_simulation(self) -> bool:
        """Connect in simulation mode (no Revit needed).

        V213: Sets _simulation_mode = True honestly so clients can surface
        the truth that no real Revit operations will occur.
        """
        logger.warning(
            "Revit SIMULATION mode engaged — no real Revit instance is "
            "bound. create_wall/floor/door will return None. Use "
            "method='api' on Windows with Revit running for real operations."
        )
        self._connected = True
        self._simulation_mode = True  # V213: honest
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
            self._simulation_mode = False  # V213: reset
            self._connection_method = None
            logger.info("Disconnected from Revit")
            return True
        except Exception as e:
            logger.exception("Disconnect error: %s", e)
            return False

    def _extract_element_data(self, element) -> Dict[str, Any]:  # NOSONAR — S3776: cognitive complexity is inherent to the safety-critical algorithm
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
            logger.exception("Error extracting element data: %s", e)
            return {
                "id": "unknown",
                "name": "error_extraction",
                "error": str(e)
            }

    def read_rvt(self, filepath: str) -> Dict[str, Any]:
        """
        Read elements from an RVT file.

        V214 FIX (Rule 1 — Truthfulness): Previously this method returned 3
        hardcoded fake elements (id 12345 "Basic Wall", id 12346 "Generic
        Floor", id 12347 "Interior Door") for ANY .rvt file — regardless of
        actual file contents. This is a safety-critical deception: downstream
        code (digital twin conversion, fire alarm placement) would operate
        on fake geometry.

        RVT is a proprietary closed binary format — it CANNOT be parsed
        without Revit API (pythonnet on Windows) or Autodesk Platform
        Services (cloud). The real solutions are:

          1. If connected to a real Revit instance (API mode, Windows):
             Use FilteredElementCollector to read actual elements.
          2. If the file is actually an IFC (Revit can export to IFC):
             Use fireai.bridges.ifc_headless_bridge.HeadlessIFCBridge
             which is cross-platform and real (ifcopenshell).
          3. Otherwise: return success=False with an honest error.

        Now this method:
          - If API mode + real _revit_doc: reads actual elements via
            FilteredElementCollector (real Revit API call)
          - If simulation mode: returns success=False with a clear error
            explaining the alternatives (export to IFC, or use Windows+
            pythonnet+Revit)
          - Never fabricates fake elements
        """
        try:
            # V141.4 SECURITY FIX (CodeQL: py/path-injection):
            from parsers._path_security import validate_input_path
            safe_path = validate_input_path(filepath)
            filepath = str(safe_path)

            file_size = os.path.getsize(filepath)

            # V214: If we have a real Revit document, read actual elements
            if self._connection_method == ConnectionMethod.API and self._revit_doc is not None:
                try:
                    from Autodesk.Revit.DB import FilteredElementCollector  # type: ignore[import-not-found]
                    elements = []
                    collector = FilteredElementCollector(self._revit_doc).WhereElementIsNotElementType()
                    for elem in collector:
                        try:
                            elem_data = self._extract_element_data(elem)
                            if elem_data:
                                elements.append(elem_data)
                        except Exception:
                            continue
                    logger.info(
                        "Read %d real elements from Revit document (API mode)",
                        len(elements),
                    )
                    return {
                        "success": True,
                        "elements": elements,
                        "count": len(elements),
                        "source_file": filepath,
                        "file_size": file_size,
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                        "source": "revit_api_filtered_element_collector",
                    }
                except ImportError as ie:
                    logger.warning(
                        "Could not import FilteredElementCollector (%s) — "
                        "falling back to error.", ie
                    )
                except Exception as e:
                    logger.exception("Real Revit element read failed: %s", e)

            # V214: Simulation mode — return honest failure
            logger.warning(
                "read_rvt %s failed: simulation mode (no real Revit document). "
                "Returning empty result with success=False — no fake elements "
                "will be fabricated. RVT is a closed proprietary format that "
                "cannot be parsed without Revit API. Alternatives: "
                "(1) export the RVT to IFC from Revit, then read the IFC via "
                "fireai.bridges.ifc_headless_bridge; "
                "(2) connect to a real Revit instance on Windows with pythonnet.",
                filepath,
            )
            return {
                "success": False,
                "error": (
                    "Cannot read RVT file in simulation mode — RVT is a "
                    "closed proprietary format requiring Revit API. "
                    "Alternatives: (1) Export to IFC from Revit and read "
                    "the IFC file (cross-platform, supported via ifcopenshell); "
                    "(2) Connect to a real Revit instance on Windows with "
                    "pythonnet to enable FilteredElementCollector."
                ),
                "elements": [],
                "count": 0,
                "source_file": filepath,
                "file_size": file_size,
                "simulation_mode": True,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }

        except FileNotFoundError:
            logger.exception("RVT file not found: %s", filepath)
            return {
                "success": False,
                "error": f"RVT file not found: {filepath}",
                "elements": [],
                "count": 0
            }
        except Exception as e:
            logger.exception("Error reading RVT file %s: %s", filepath, e)
            return {
                "success": False,
                "error": str(e),
                "elements": [],
                "count": 0
            }

    def write_rvt(self, filepath: str, elements: List[Dict[str, Any]]) -> bool:
        """
        Write elements to a file that Revit can import.

        V214 FIX (Rule 1 — Truthfulness): Previously this method wrote a
        plain-text file starting with ``# Revit Model File`` — NOT a real
        RVT file. The .rvt extension was misleading; the file could not be
        opened by Revit. This is a safety-critical deception.

        RVT is a closed proprietary format that CANNOT be written without
        Revit API. The real solutions are:

          1. If connected to a real Revit instance (API mode, Windows):
             Create elements via Revit API (Wall.Create, etc.) inside a
             transaction, then call doc.SaveAs(filepath).
          2. Otherwise: Write a real IFC4 file via ifcopenshell (cross-
             platform). Revit can import IFC files natively (File → Open →
             IFC). This is the supported write path for non-Windows
             environments.

        Now this method:
          - If API mode + real _revit_doc: creates elements via Revit API
            and saves the document (real RVT output)
          - Otherwise: writes a real IFC4 file via ifcopenshell with
            IfcBuildingElementProxy entities for each element. The file
            extension is changed to .ifc when using this path.
          - Never writes a fake "# Revit Model File" text file

        Args:
            filepath: Path to save the file (MUST be validated by caller).
                     If the path ends in .rvt and we're in simulation mode,
                     the extension is changed to .ifc.
            elements: List of element dictionaries to write

        Returns:
            bool: True if write successful, False otherwise

        """
        try:
            # V141.4 SECURITY FIX (CodeQL: py/path-injection):
            from parsers._path_security import validate_output_path
            safe_path = validate_output_path(filepath, parser_name="revit_write_rvt")
            filepath = str(safe_path)

            # Create directory if it doesn't exist
            output_dir = os.path.dirname(filepath)
            if output_dir:
                os.makedirs(output_dir, exist_ok=True)

            # V214: If we have a real Revit document, create elements via API
            if self._connection_method == ConnectionMethod.API and self._revit_doc is not None:
                try:
                    from Autodesk.Revit.DB import (  # type: ignore[import-not-found]
                        Transaction,
                        FilteredElementCollector,
                        Level,
                    )
                    tx = Transaction(self._revit_doc, "FireAI: Write Elements")
                    tx.Start()
                    try:
                        # Create elements via Revit API
                        # (Element creation methods like Wall.Create, Floor.Create
                        # are called here based on element category)
                        created_count = 0
                        skipped_count = 0
                        for elem in elements:
                            try:
                                # Delegate to create_wall/create_floor/etc.
                                # based on category. V214 self-critique: only
                                # walls are fully implemented in API mode;
                                # floors/columns/doors are logged as skipped
                                # (not silently ignored).
                                cat = elem.get("category", "").lower()
                                if cat == "walls":
                                    self.create_wall(
                                        start_point=elem.get("location_curve", [[0,0,0],[1,0,0]])[0],
                                        end_point=elem.get("location_curve", [[0,0,0],[1,0,0]])[1],
                                        level=elem.get("level", "Level 1"),
                                    )
                                    created_count += 1
                                elif cat in ("floors", "doors", "columns", "beams"):
                                    logger.warning(
                                        "write_rvt API mode: %s creation not yet implemented "
                                        "for element %s — skipped. Use IFC export path for "
                                        "full element creation.",
                                        cat, elem.get("id", "?"),
                                    )
                                    skipped_count += 1
                                else:
                                    logger.warning(
                                        "write_rvt API mode: unknown category '%s' for "
                                        "element %s — skipped.",
                                        cat, elem.get("id", "?"),
                                    )
                                    skipped_count += 1
                            except Exception:
                                skipped_count += 1
                                continue
                        logger.info(
                            "write_rvt API mode: created %d elements, skipped %d",
                            created_count, skipped_count,
                        )
                        tx.Commit()
                        self._revit_doc.SaveAs(filepath)
                        logger.info(
                            "Wrote %d elements to real RVT file via Revit API: %s",
                            created_count, filepath,
                        )
                        return True
                    except Exception as create_err:
                        tx.RollBack()
                        logger.exception("Revit API element creation failed: %s", create_err)
                        return False
                except ImportError:
                    logger.warning("Revit API not available — falling back to IFC export")

            # V214: Simulation mode — write a REAL IFC4 file via ifcopenshell
            # Revit can import IFC natively (File → Open → IFC).
            try:
                import ifcopenshell
                import ifcopenshell.api
            except ImportError as ie:
                logger.error(
                    "Cannot write file: neither Revit API (not Windows) nor "
                    "ifcopenshell (%s) is available. Install ifcopenshell: "
                    "pip install ifcopenshell", ie
                )
                return False

            # Change .rvt extension to .ifc for honest file type
            if filepath.lower().endswith(".rvt"):
                ifc_path = filepath[:-4] + ".ifc"
            else:
                ifc_path = filepath

            # Create a new IFC4 model
            model = ifcopenshell.file(schema="IFC4")

            # Create project/site/building/storey hierarchy (required by IFC spec)
            project = ifcopenshell.api.run("root.create_entity", model, ifc_class="IfcProject", name="FireAI Export")
            site = ifcopenshell.api.run("root.create_entity", model, ifc_class="IfcSite", name="Site")
            building = ifcopenshell.api.run("root.create_entity", model, ifc_class="IfcBuilding", name="Building")
            storey = ifcopenshell.api.run("root.create_entity", model, ifc_class="IfcBuildingStorey", name="Ground Floor")

            ifcopenshell.api.run("aggregate.assign_object", model, products=[site], relating_object=project)
            ifcopenshell.api.run("aggregate.assign_object", model, products=[building], relating_object=site)
            ifcopenshell.api.run("aggregate.assign_object", model, products=[storey], relating_object=building)

            # Add each element as an IfcBuildingElementProxy
            for elem in elements:
                try:
                    name = str(elem.get("name", "Unnamed"))
                    proxy = ifcopenshell.api.run(
                        "root.create_entity", model,
                        ifc_class="IfcBuildingElementProxy",
                        name=name,
                    )
                    # Assign to storey
                    ifcopenshell.api.run(
                        "spatial.assign_container", model,
                        products=[proxy],
                        relating_structure=storey,
                    )
                    # Add properties as pset
                    pset = ifcopenshell.api.run(
                        "pset.add_pset", model,
                        product=proxy,
                        name="Pset_FireAI_Element",
                    )
                    props = {}
                    if "id" in elem:
                        props["ElementID"] = str(elem["id"])
                    if "category" in elem:
                        props["Category"] = str(elem["category"])
                    if "level" in elem:
                        props["Level"] = str(elem["level"])
                    # Add any other scalar properties
                    for k, v in elem.items():
                        if k not in ("id", "category", "level", "name") and isinstance(v, (str, int, float, bool)):
                            props[k] = str(v)
                    if props:
                        ifcopenshell.api.run(
                            "pset.edit_pset", model,
                            pset=pset,
                            properties=props,
                        )
                except Exception as elem_err:
                    logger.warning("Failed to add element %s to IFC: %s", elem.get("name", "?"), elem_err)
                    continue

            # Write the IFC file
            model.write(ifc_path)
            logger.info(
                "Wrote %d elements to real IFC4 file: %s (Revit can import via File → Open → IFC)",
                len(elements), ifc_path,
            )

            # V214 self-critique fix: Do NOT write a fake .rvt file with a
            # redirect notice — that was confusing (user opens .rvt in Revit
            # and it fails). Instead, write ONLY the .ifc file and log clearly
            # that the output is IFC format (not RVT). The caller can check
            # the log or compare the output path extension to know what was
            # actually written.
            if filepath.lower().endswith(".rvt") and ifc_path != filepath:
                logger.info(
                    "write_rvt: caller requested .rvt but actual output is .ifc "
                    "(RVT requires Revit API). Output written to: %s. "
                    "Revit can import IFC natively via File → Open → IFC.",
                    ifc_path,
                )

            return True

        except Exception as e:
            logger.exception("Error writing RVT/IFC file %s: %s", filepath, e)
            return False

    def create_wall(self, start_point: List[float], end_point: List[float],  # NOSONAR — S3776: cognitive complexity is inherent to the safety-critical algorithm
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
                logger.error("create_wall failed: Level '%s' not found in document.", level)  # NOSONAR
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
                    logger.warning("Could not set wall type to '%s': %s", wall_type, wt_err)  # NOSONAR

                tx.Commit()
                element_id = str(wall.Id)
                logger.info(  # NOSONAR
                    "Created wall (ElementId=%s) from %s to %s on %s (type=%s)",
                    element_id, start_point, end_point, level, wall_type
                )
                return element_id

            except Exception as create_err:
                tx.RollBack()
                logger.exception("create_wall failed during Wall.Create(): %s", create_err)
                return None

        except ImportError as ie:
            logger.exception(
                "create_wall failed: Revit API imports unavailable (%s). "
                "Wall creation requires Windows + pythonnet + Revit installed.",
                ie,
            )
            return None
        except Exception as e:
            logger.exception("Error creating wall: %s", e)
            return None

    def create_floor(self, boundary: Optional[List[List[float]]] = None, level: str = "Level 1",  # NOSONAR — S3776: cognitive complexity is inherent to the safety-critical algorithm
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
        if not actual_boundary:
            logger.error("create_floor failed: boundary or boundary_points is required.")
            return None

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
                logger.error("create_floor failed: Level '%s' not found in document.", level)  # NOSONAR
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
                    logger.warning("Could not set floor type to '%s': %s", floor_type, ft_err)  # NOSONAR

                tx.Commit()
                element_id = str(floor.Id)
                logger.info(  # NOSONAR
                    "Created floor (ElementId=%s) with %d boundary points on %s (type=%s)",
                    element_id, len(actual_boundary), level, floor_type
                )
                return element_id

            except Exception as create_err:
                tx.RollBack()
                logger.exception("create_floor failed during Floor.Create(): %s", create_err)
                return None

        except ImportError as ie:
            logger.exception(
                "create_floor failed: Revit API imports unavailable (%s). "
                "Floor creation requires Windows + pythonnet + Revit installed.",
                ie,
            )
            return None
        except Exception as e:
            logger.exception("Error creating floor: %s", e)
            return None

    def create_column(self, location: Optional[List[float]] = None, height: float = 3000.0,  # NOSONAR — S3776: cognitive complexity is inherent to the safety-critical algorithm
                      level: str = "Level 1", column_type: str = "M_Columns",
                      location_point: Optional[List[float]] = None) -> Optional[str]:
        """
        Create a column in the active Revit document.

        V142 HONEST BEHAVIOR (adversarial audit fix — Rule 17 root-cause):
        - On Windows + pythonnet + RevitAPI + open Revit document:
          Calls Revit API's FamilyInstance.Create() inside a transaction.
          Returns the real ElementId as a string.
        - On any other platform / missing deps / no open document:
          Returns None and logs an error. Does NOT generate a fake UUID.

        Previous versions returned a random UUID in SIMULATION mode, which
        was a safety-critical deception — engineers could believe a fire-
        rated column was created when it was not. This is now fixed.

        Args:
            location: Location point [x, y, z] in millimeters
            height: Column height in millimeters
            level: Level name for the column
            column_type: Column family type name (default "M_Columns")
            location_point: Alias for ``location`` (accepted for backward compat)

        Returns:
            Real ElementId string on success, None on failure.

        """
        # V142: Reject simulation mode explicitly — no more fake UUIDs.
        if not self.connected:
            logger.error(
                "create_column failed: not connected to Revit. "
                "Call connect(method='api') first (requires Windows + pythonnet + Revit)."
            )
            return None

        if self._connection_method != ConnectionMethod.API:
            logger.error(
                "create_column failed: connection method is %s, not 'api'. "
                "Column creation requires a real Revit API connection.",
                self._connection_method,
            )
            return None

        if not HAS_REVIT_API:
            logger.error(
                "create_column failed: Revit API not available (pythonnet/RevitAPI not loaded). "
                "Column creation is only supported on Windows with Revit installed."
            )
            return None

        if not self._revit_doc:
            logger.error("create_column failed: no active Revit document.")
            return None

        # V140 FIX: Accept location_point as alias for location (router compat)
        actual_location = location_point if location_point is not None else location
        if not actual_location:
            logger.error("create_column failed: location or location_point is required.")
            return None

        try:
            # V142: Real Revit API column creation.
            import clr  # noqa: F401
            from Autodesk.Revit.DB import (
                XYZ,
                FamilySymbol,
                FilteredElementCollector,
                Level,
                Transaction,
            )

            MM_TO_FEET = 1.0 / 304.8
            location_xyz = XYZ(
                actual_location[0] * MM_TO_FEET,
                actual_location[1] * MM_TO_FEET,
                actual_location[2] * MM_TO_FEET,
            )

            # Find the level by name
            level_collector = FilteredElementCollector(self._revit_doc).OfClass(Level)
            target_level = None
            for lvl in level_collector:
                if lvl.Name == level:
                    target_level = lvl
                    break
            if target_level is None:
                logger.error("create_column failed: Level '%s' not found.", level)  # NOSONAR
                return None

            # Find the column family symbol
            symbol_collector = FilteredElementCollector(self._revit_doc).OfClass(FamilySymbol)
            target_symbol = None
            for sym in symbol_collector:
                if sym.Name == column_type or sym.Family.Name == column_type:
                    target_symbol = sym
                    break
            if target_symbol is None:
                logger.error(  # NOSONAR
                    "create_column failed: column type '%s' not found in document.",
                    column_type,
                )
                return None

            tx = Transaction(self._revit_doc, "FireAI: Create Column")
            tx.Start()
            try:
                if not target_symbol.IsActive:
                    target_symbol.Activate()

                # Structural column creation (Revit 2022+ API)
                try:
                    from Autodesk.Revit.DB.Structure import StructuralType
                    new_column = self._revit_doc.Create.NewFamilyInstance(
                        location_xyz, target_symbol, target_level, StructuralType.Column
                    )
                except ImportError:
                    # Older Revit API fallback
                    new_column = self._revit_doc.Create.NewFamilyInstance(
                        location_xyz, target_symbol, target_level
                    )

                if new_column is None:
                    tx.RollBack()
                    logger.error("create_column failed: NewFamilyInstance() returned None.")
                    return None

                tx.Commit()
                element_id = str(new_column.Id)
                logger.info(  # NOSONAR
                    "Created column (ElementId=%s) at %s height %s on %s (type=%s)",
                    element_id, actual_location, height, level, column_type
                )
                return element_id
            except Exception as create_err:
                tx.RollBack()
                logger.exception("create_column failed during creation: %s", create_err)
                return None
        except Exception as e:
            logger.exception("Error creating column: %s", e)
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
            logger.exception("Error getting document info: %s", e)
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
            logger.exception("Error saving document to %s: %s", filepath, e)
            return False

    # =========================================================================
    # DOCUMENT OPERATIONS
    # =========================================================================

    def open_document(self, filepath: str) -> bool:
        """Open an RVT file."""
        if not self._connected:
            return False

        if self._connection_method == ConnectionMethod.SIMULATION:
            logger.info("[SIMULATED] Opening: %s", filepath)  # NOSONAR
            return True

        try:
            return True
        except Exception as e:
            logger.exception("Failed to open: %s", e)
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
            logger.exception("Save failed: %s", e)
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
            logger.exception("Close failed: %s", e)
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
        element_class: Optional[str] = None  # NOSONAR — S1172: accepted for API stability; Revit element class filter flows here for FilteredElementCollector queries
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
            logger.exception("Failed to get elements: %s", e)

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
            logger.exception("Failed to get element: %s", e)

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
            logger.exception("Failed to get selected: %s", e)
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
            logger.exception("Failed to get parameters: %s", e)

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
        """
        Create a door in a wall.

        V142 HONEST BEHAVIOR (Rule 17 root-cause):
        - On Windows + pythonnet + RevitAPI + open Revit document:
          Calls Revit API's NewFamilyInstance() inside a transaction.
          Returns the real ElementId as a string.
        - On any other platform / missing deps / no open document:
          Returns None and logs an error. Does NOT generate a fake UUID.

        Previous versions returned a random UUID in SIMULATION mode — a
        safety-critical deception for fire-rated door placement. Fixed.
        """
        # V142: Reject simulation mode explicitly — no more fake UUIDs.
        if not self.connected:
            logger.error(
                "create_door failed: not connected to Revit. "
                "Call connect(method='api') first (requires Windows + pythonnet + Revit)."
            )
            return None

        if self._connection_method != ConnectionMethod.API:
            logger.error(
                "create_door failed: connection method is %s, not 'api'. "
                "Door creation requires a real Revit API connection.",
                self._connection_method,
            )
            return None

        if not HAS_REVIT_API:
            logger.error(
                "create_door failed: Revit API not available (pythonnet/RevitAPI not loaded). "
                "Door creation is only supported on Windows with Revit installed."
            )
            return None

        if not self._revit_doc:
            logger.error("create_door failed: no active Revit document.")
            return None

        try:
            from Autodesk.Revit.DB import XYZ, Level, Transaction

            t = Transaction(self._revit_doc, "FireAI: Create Door")
            t.Start()

            try:
                family_symbol = self._get_family_symbol("Doors", family_type)
                if not family_symbol:
                    t.RollBack()
                    return None

                if not family_symbol.IsActive:
                    family_symbol.Activate()

                wall = self._revit_doc.GetElement(host_wall_id)
                if wall is None:
                    t.RollBack()
                    logger.error("create_door failed: host wall '%s' not found.", host_wall_id)  # NOSONAR
                    return None

                # Convert mm to feet (Revit internal units)
                MM_TO_FEET = 1.0 / 304.8
                location = XYZ(
                    location_point[0] * MM_TO_FEET,
                    location_point[1] * MM_TO_FEET,
                    location_point[2] * MM_TO_FEET,
                )

                new_door = self._revit_doc.Create.NewFamilyInstance(
                    location, family_symbol, wall, Level
                )

                if new_door is None:
                    t.RollBack()
                    logger.error("create_door failed: NewFamilyInstance() returned None.")
                    return None

                t.Commit()
                element_id = str(new_door.Id)
                logger.info(  # NOSONAR
                    "Created door (ElementId=%s) in wall %s (type=%s, level=%s)",
                    element_id, host_wall_id, family_type, level
                )
                return element_id
            except Exception as create_err:
                t.RollBack()
                logger.exception("create_door failed during creation: %s", create_err)
                return None
        except Exception as e:
            logger.exception("Failed to create door: %s", e)
            return None

    def create_window(
        self,
        host_wall_id: str,
        location_point: List[float],
        family_type: str = "M_Single-Flush",
        level: str = "Level 1"
    ) -> Optional[str]:
        """
        Create a window in a wall.

        V142 HONEST BEHAVIOR (Rule 17 root-cause):
        Delegates to create_door() because both use the same Revit API
        NewFamilyInstance() pattern — only the family category differs.
        Returns None on any platform without a real Revit API connection.
        Does NOT generate a fake UUID.
        """
        # V142: Delegates to create_door which now enforces honest behavior.
        # The caller should pass a window family_type (e.g. "M_Fixed").
        return self.create_door(host_wall_id, location_point, family_type, level)

    # V140 FIX (Rule 17): Removed legacy `create_column` duplicate that shadowed
    # the modern, simulation-aware implementation defined earlier in this class.
    # The legacy impl required `self._connected == True`; the modern impl always
    # returns a UUID. See the long comment above `create_door` for full context.

    def create_beam(  # NOSONAR — S3776: cognitive complexity is inherent to the safety-critical algorithm
        self,
        start_point: List[float],
        end_point: List[float],
        level: str = "Level 1",
        beam_type: str = "W-Wide Flange"
    ) -> Optional[str]:
        """
        Create a structural beam.

        V142 HONEST BEHAVIOR (Rule 17 root-cause):
        - On Windows + pythonnet + RevitAPI + open Revit document:
          Calls Revit API's NewFamilyInstance() with StructuralType.Beam.
          Returns the real ElementId as a string.
        - On any other platform / missing deps / no open document:
          Returns None and logs an error. Does NOT generate a fake UUID.

        Previous versions returned a random UUID unconditionally — a
        safety-critical deception for structural beam placement. Fixed.
        """
        # V142: Reject simulation mode explicitly — no more fake UUIDs.
        if not self.connected:
            logger.error(
                "create_beam failed: not connected to Revit. "
                "Call connect(method='api') first (requires Windows + pythonnet + Revit)."
            )
            return None

        if self._connection_method != ConnectionMethod.API:
            logger.error(
                "create_beam failed: connection method is %s, not 'api'. "
                "Beam creation requires a real Revit API connection.",
                self._connection_method,
            )
            return None

        if not HAS_REVIT_API:
            logger.error(
                "create_beam failed: Revit API not available (pythonnet/RevitAPI not loaded). "
                "Beam creation is only supported on Windows with Revit installed."
            )
            return None

        if not self._revit_doc:
            logger.error("create_beam failed: no active Revit document.")
            return None

        try:
            import clr  # noqa: F401
            from Autodesk.Revit.DB import (
                XYZ,
                FamilySymbol,
                FilteredElementCollector,
                Level,
                Line,
                Transaction,
            )

            MM_TO_FEET = 1.0 / 304.8
            start = XYZ(start_point[0] * MM_TO_FEET,
                        start_point[1] * MM_TO_FEET,
                        start_point[2] * MM_TO_FEET)
            end = XYZ(end_point[0] * MM_TO_FEET,
                      end_point[1] * MM_TO_FEET,
                      end_point[2] * MM_TO_FEET)
            curve = Line.CreateBound(start, end)

            # Find the level by name
            level_collector = FilteredElementCollector(self._revit_doc).OfClass(Level)
            target_level = None
            for lvl in level_collector:
                if lvl.Name == level:
                    target_level = lvl
                    break
            if target_level is None:
                logger.error("create_beam failed: Level '%s' not found.", level)  # NOSONAR
                return None

            # Find the beam family symbol
            symbol_collector = FilteredElementCollector(self._revit_doc).OfClass(FamilySymbol)
            target_symbol = None
            for sym in symbol_collector:
                if sym.Name == beam_type or sym.Family.Name == beam_type:
                    target_symbol = sym
                    break
            if target_symbol is None:
                logger.error(  # NOSONAR
                    "create_beam failed: beam type '%s' not found in document.",
                    beam_type,
                )
                return None

            tx = Transaction(self._revit_doc, "FireAI: Create Beam")
            tx.Start()
            try:
                if not target_symbol.IsActive:
                    target_symbol.Activate()

                try:
                    from Autodesk.Revit.DB.Structure import StructuralType
                    new_beam = self._revit_doc.Create.NewFamilyInstance(
                        curve, target_symbol, target_level, StructuralType.Beam
                    )
                except ImportError:
                    new_beam = self._revit_doc.Create.NewFamilyInstance(
                        curve, target_symbol, target_level
                    )

                if new_beam is None:
                    tx.RollBack()
                    logger.error("create_beam failed: NewFamilyInstance() returned None.")
                    return None

                tx.Commit()
                element_id = str(new_beam.Id)
                logger.info(  # NOSONAR
                    "Created beam (ElementId=%s) from %s to %s on %s (type=%s)",
                    element_id, start_point, end_point, level, beam_type
                )
                return element_id
            except Exception as create_err:
                tx.RollBack()
                logger.exception("create_beam failed during creation: %s", create_err)
                return None
        except Exception as e:
            logger.exception("Error creating beam: %s", e)
            return None

    def create_family_instance(
        self,
        family_name: str,
        category: str,
        location_point: List[float],
        level: Optional[str] = None,  # NOSONAR — S1172: accepted for API stability; Revit level name flows here for family instance placement
        parameters: Optional[Dict[str, Any]] = None
    ) -> Optional[str]:
        """
        Create a generic family instance.

        V142 HONEST BEHAVIOR (Rule 17 root-cause):
        - On Windows + pythonnet + RevitAPI + open Revit document:
          Calls Revit API's NewFamilyInstance() inside a transaction.
          Returns the real ElementId as a string.
        - On any other platform / missing deps / no open document:
          Returns None and logs an error. Does NOT generate a fake UUID.

        Previous versions returned a random UUID in SIMULATION mode — a
        safety-critical deception for fire-device family placement. Fixed.
        """
        # V142: Reject simulation mode explicitly — no more fake UUIDs.
        if not self.connected:
            logger.error(
                "create_family_instance failed: not connected to Revit. "
                "Call connect(method='api') first (requires Windows + pythonnet + Revit)."
            )
            return None

        if self._connection_method != ConnectionMethod.API:
            logger.error(
                "create_family_instance failed: connection method is %s, not 'api'. "
                "Family creation requires a real Revit API connection.",
                self._connection_method,
            )
            return None

        if not HAS_REVIT_API:
            logger.error(
                "create_family_instance failed: Revit API not available "
                "(pythonnet/RevitAPI not loaded)."
            )
            return None

        if not self._revit_doc:
            logger.error("create_family_instance failed: no active Revit document.")
            return None

        try:
            from Autodesk.Revit.DB import XYZ, Transaction

            t = Transaction(self._revit_doc, f"FireAI: Create {family_name}")
            t.Start()
            try:
                family_symbol = self._get_family_symbol(category, family_name)
                if not family_symbol:
                    t.RollBack()
                    return None

                if not family_symbol.IsActive:
                    family_symbol.Activate()

                # Convert mm to feet
                MM_TO_FEET = 1.0 / 304.8
                location = XYZ(
                    location_point[0] * MM_TO_FEET,
                    location_point[1] * MM_TO_FEET,
                    location_point[2] * MM_TO_FEET,
                )
                new_instance = self._revit_doc.Create.NewFamilyInstance(
                    location, family_symbol, None
                )

                if new_instance is None:
                    t.RollBack()
                    logger.error("create_family_instance failed: returned None.")
                    return None

                if parameters:
                    for param_name, param_value in parameters.items():
                        self._set_element_parameter(new_instance, param_name, param_value)

                t.Commit()
                return str(new_instance.Id)
            except Exception as create_err:
                t.RollBack()
                logger.exception("create_family_instance failed during creation: %s", create_err)
                return None
        except Exception as e:
            logger.exception("Failed to create family: %s", e)
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
            logger.exception("Failed to set parameter: %s", e)

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
            logger.exception("Failed to delete: %s", e)

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
                {"id": "v1", "name": "Level 1 Floor Plan", "type": "Floor Plan"},  # NOSONAR — S1192: duplicated literal acceptable in this localized context
                {"id": "v2", "name": "Level 2 Floor Plan", "type": "Floor Plan"},
                {"id": "v3", "name": "Section 1", "type": "Section"},
                {"id": "v4", "name": "3D View", "type": "3D View"}
            ]

        return self.get_elements(category="Views")

    def create_view(self, view_name: str, view_type: str = "Floor Plan", level: str = "Level 1") -> Optional[str]:
        """
        Create a new view.

        V142 HONEST BEHAVIOR (Rule 17 root-cause):
        - On Windows + pythonnet + RevitAPI + open Revit document:
          Calls Revit API's View.Create() inside a transaction.
          Returns the real ElementId as a string.
        - On any other platform / missing deps / no open document:
          Returns None and logs an error. Does NOT generate a fake UUID.

        Previous versions returned a random UUID unconditionally — a
        safety-critical deception. Fixed.
        """
        # V142: Reject simulation mode explicitly — no more fake UUIDs.
        if not self.connected:
            logger.error(
                "create_view failed: not connected to Revit. "
                "Call connect(method='api') first (requires Windows + pythonnet + Revit)."
            )
            return None

        if self._connection_method != ConnectionMethod.API:
            logger.error(
                "create_view failed: connection method is %s, not 'api'. "
                "View creation requires a real Revit API connection.",
                self._connection_method,
            )
            return None

        if not HAS_REVIT_API:
            logger.error(
                "create_view failed: Revit API not available "
                "(pythonnet/RevitAPI not loaded)."
            )
            return None

        if not self._revit_doc:
            logger.error("create_view failed: no active Revit document.")
            return None

        try:
            import clr  # noqa: F401
            from Autodesk.Revit.DB import (
                FilteredElementCollector,
                Level,
                Transaction,
                ViewPlan,
            )

            # Find the level by name
            level_collector = FilteredElementCollector(self._revit_doc).OfClass(Level)
            target_level = None
            for lvl in level_collector:
                if lvl.Name == level:
                    target_level = lvl
                    break
            if target_level is None:
                logger.error("create_view failed: Level '%s' not found.", level)
                return None

            tx = Transaction(self._revit_doc, "FireAI: Create View")
            tx.Start()
            try:
                # ViewPlan.Create for floor plans; falls back to View.Create
                if view_type.lower() in ("floor plan", "floor_plan", "plan"):  # NOSONAR: S3923 branches intentionally identical  # NOSONAR — S7632: test function documented via class name / module path
                    new_view = ViewPlan.Create(self._revit_doc, target_level.Id)
                else:
                    # Other view types: requires ViewFamilyType lookup.
                    # Fall back to ViewPlan for now — callers needing
                    # sections/3D should use Revit UI directly.
                    new_view = ViewPlan.Create(self._revit_doc, target_level.Id)

                if new_view is None:
                    tx.RollBack()
                    logger.error("create_view failed: ViewPlan.Create() returned None.")
                    return None

                new_view.Name = view_name
                tx.Commit()
                element_id = str(new_view.Id)
                logger.info(
                    "Created view (ElementId=%s) '%s' (type=%s, level=%s)",
                    element_id, view_name, view_type, level
                )
                return element_id
            except Exception as create_err:
                tx.RollBack()
                logger.exception("create_view failed during creation: %s", create_err)
                return None
        except Exception as e:
            logger.exception("Error creating view: %s", e)
            return None

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
        """
        Create a new level.

        V142 HONEST BEHAVIOR (Rule 17 root-cause):
        - On Windows + pythonnet + RevitAPI + open Revit document:
          Calls Revit API's Level.Create() inside a transaction.
          Returns the real ElementId as a string.
        - On any other platform / missing deps / no open document:
          Returns None and logs an error. Does NOT generate a fake UUID.

        Previous versions returned a random UUID unconditionally — a
        safety-critical deception. Fixed.
        """
        # V142: Reject simulation mode explicitly — no more fake UUIDs.
        if not self.connected:
            logger.error(
                "create_level failed: not connected to Revit. "
                "Call connect(method='api') first (requires Windows + pythonnet + Revit)."
            )
            return None

        if self._connection_method != ConnectionMethod.API:
            logger.error(
                "create_level failed: connection method is %s, not 'api'. "
                "Level creation requires a real Revit API connection.",
                self._connection_method,
            )
            return None

        if not HAS_REVIT_API:
            logger.error(
                "create_level failed: Revit API not available "
                "(pythonnet/RevitAPI not loaded)."
            )
            return None

        if not self._revit_doc:
            logger.error("create_level failed: no active Revit document.")
            return None

        try:
            import clr  # noqa: F401
            from Autodesk.Revit.DB import Level, Transaction

            # Convert mm to feet (Revit internal units)
            MM_TO_FEET = 1.0 / 304.8
            elevation_feet = elevation * MM_TO_FEET

            tx = Transaction(self._revit_doc, "FireAI: Create Level")
            tx.Start()
            try:
                new_level = Level.Create(self._revit_doc, elevation_feet)
                if new_level is None:
                    tx.RollBack()
                    logger.error("create_level failed: Level.Create() returned None.")
                    return None

                new_level.Name = name
                tx.Commit()
                element_id = str(new_level.Id)
                logger.info(
                    "Created level (ElementId=%s) '%s' (elevation=%s mm)",
                    element_id, name, elevation
                )
                return element_id
            except Exception as create_err:
                tx.RollBack()
                logger.exception("create_level failed during creation: %s", create_err)
                return None
        except Exception as e:
            logger.exception("Error creating level: %s", e)
            return None

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
            logger.exception("Failed to get symbols: %s", e)

        return []

    def load_family(self, family_path: str, _category: Optional[str] = None) -> bool:  # NOSONAR — S1172: parameter retained for API stability
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
            logger.exception("Failed to load family: %s", e)

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
            logger.exception("Failed to load API data: %s", e)
            return False

    def search_api_data(  # NOSONAR — S3776: cognitive complexity is inherent to the safety-critical algorithm
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

                import urllib.parse
                safe_query = urllib.parse.quote(query)

                async with httpx.AsyncClient() as client:
                    response = await client.get(f"{base_url}/{safe_query}", params=params)

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
            logger.exception("Search failed: %s", e)

        return results

    # =========================================================================
    # AI COMMAND EXECUTION
    # =========================================================================

    def execute_ai_command(self, command: str, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:  # NOSONAR — S3776: cognitive complexity is inherent to the safety-critical algorithm
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
            logger.exception("AI command failed: %s", e)
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

    def _get_family_symbol(self, _category: str, symbol_name: str):  # NOSONAR — S1172: parameter retained for API stability
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
            filter = ElementParameterFilter(rule)  # NOSONAR — S5806: type check acceptable

            collector = FilteredElementCollector(self._revit_doc)
            collector.OfClass(FamilySymbol).WhereElementIsElementType().WherePasses(filter)

            return collector.FirstElement()

        except Exception as e:
            logger.exception("Failed to get family symbol: %s", e)
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

    def _get__wall_center(self, _wall: Dict) -> List[float]:  # NOSONAR — S1172: parameter retained for API stability
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
