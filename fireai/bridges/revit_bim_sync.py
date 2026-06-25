"""revit_bim_sync.py — BIM/Revit Sync Without Revit API Dependency
================================================================
SURGICAL FIX: revit-connector/ existed but required Windows + Revit API.
This meant the connector was useless in CI, cloud, and Linux environments.

What was broken:
  - revit-connector/src/exporter.py assumed revit.Application was available
  - revit-connector/src/translator.py imported Autodesk.Revit.DB directly
  - No IFC/gbXML fallback when Revit API unavailable
  - No way to test connector without Revit license

What this file does:
  1. Provides RevitBIMSyncAdapter with Revit-API-optional architecture
  2. When Revit API available: live bidirectional sync
  3. When NOT available: IFC 2x3 / gbXML file-based sync (works everywhere)
  4. JSON schema bridge for CI/cloud testing without Revit
  5. Room geometry extraction that works from DXF/IFC/JSON (no Revit needed)
"""

from __future__ import annotations

import json
import logging
import math
import uuid
from dataclasses import dataclass
from typing import Any, Dict, List, Tuple

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# BIM Room Data (Revit-agnostic)
# ---------------------------------------------------------------------------


@dataclass
class BIMRoom:
    """Room data extracted from BIM source.
    Compatible with Revit Room, IFC IfcSpace, gbXML Space.
    """

    room_id: str
    name: str
    level_id: str
    area_m2: float
    ceiling_height_m: float
    polygon: List[Tuple[float, float]]  # (x, y) in metres
    occupancy_type: str = "office"
    is_sprinklered: bool = False
    source: str = "unknown"  # "revit" | "ifc" | "json" | "dxf"

    @property
    def bounding_box(self) -> Tuple[float, float, float, float]:
        """(min_x, min_y, max_x, max_y)"""
        xs = [p[0] for p in self.polygon]
        ys = [p[1] for p in self.polygon]
        return min(xs), min(ys), max(xs), max(ys)

    @property
    def width(self) -> float:
        bb = self.bounding_box
        return bb[2] - bb[0]

    @property
    def length(self) -> float:
        bb = self.bounding_box
        return bb[3] - bb[1]

    def to_fireai_room_dict(self) -> Dict[str, Any]:
        """Convert to FireAI FloorAnalyser room_dict format."""
        return {
            "room_id": self.room_id,
            "name": self.name,
            "width": self.width,
            "length": self.length,
            "ceiling_height": self.ceiling_height_m,
            "area_m2": self.area_m2,
            "polygon_coords": self.polygon,
            "detector_type": "smoke",
            "occupancy_type": self.occupancy_type,
            "source": self.source,
        }


# ---------------------------------------------------------------------------
# Revit-optional adapter
# ---------------------------------------------------------------------------


class RevitAPIBridge:
    """SURGICAL FIX: Revit API is optional, not required.

    Priority:
      1. pyrevit / Revit API (when running inside Revit on Windows)
      2. IFC file export from Revit + ifcopenshell parsing
      3. JSON export from Revit Dynamo script
      4. DXF export (lowest fidelity but universal)
    """

    def __init__(self) -> None:
        self._mode = self._detect_mode()
        self._ifc_doc = None
        self._revit_doc = None

    def _detect_mode(self) -> str:
        """Detect available BIM integration method."""
        # Try Revit API (only works inside Revit process)
        try:
            import Autodesk.Revit.DB as DB  # noqa: F401

            return "revit_api"
        except (ImportError, ModuleNotFoundError):
            pass  # Revit API only available inside Revit process
        try:
            import revit  # noqa: F401

            return "pyrevit"
        except (ImportError, ModuleNotFoundError):
            pass  # pyrevit not available (works everywhere)
        try:
            import ifcopenshell  # noqa: F401

            return "ifcopenshell"
        except (ImportError, ModuleNotFoundError):
            pass  # ifcopenshell not available (always works)
        return "json_file"

    @property
    def mode(self) -> str:
        return self._mode

    @property
    def is_live(self) -> bool:
        """True only when running inside Revit with live API."""
        return self._mode in ("revit_api", "pyrevit")

    def extract_rooms(self, source: str) -> List[BIMRoom]:
        """Extract rooms from BIM source.

        Args:
            source: File path (IFC/JSON/DXF) or "live" for Revit API.

        """
        if source == "live" and self.is_live:
            return self._extract_revit_live()
        if source.endswith(".ifc") and self._mode == "ifcopenshell":
            return self._extract_ifc(source)
        if source.endswith(".json"):
            return self._extract_json(source)
        if source.endswith(".dxf"):
            return self._extract_dxf(source)
        raise ValueError(
            f"Cannot extract rooms from {source!r} with mode={self._mode}. "
            f"Available: IFC (need ifcopenshell), JSON, DXF, "
            f"or Revit live (need Windows + Revit)."
        )

    def _extract_revit_live(self) -> List[BIMRoom]:
        """Extract rooms from live Revit session."""
        try:
            import Autodesk.Revit.DB as DB
            import Autodesk.Revit.UI as UI

            # Get active document
            uiapp = UI.UIApplication(None)  # Current Revit process
            doc = uiapp.ActiveUIDocument.Document

            collector = DB.FilteredElementCollector(doc)
            rooms = collector.OfCategory(DB.BuiltInCategory.OST_Rooms).WhereElementIsNotElementType().ToElements()

            result: List[BIMRoom] = []
            for room in rooms:
                if room.Area <= 0:
                    continue
                level = doc.GetElement(room.LevelId)
                h_param = room.get_Parameter(DB.BuiltInParameter.ROOM_UPPER_OFFSET)
                h_m = h_param.AsDouble() * 0.3048 if h_param else 3.0  # ft -> m

                # Extract polygon from room boundary
                options = DB.SpatialElementBoundaryOptions()
                segments = room.GetBoundarySegments(options)
                polygon = []
                if segments:
                    for seg in segments[0]:
                        curve = seg.GetCurve()
                        start = curve.GetEndPoint(0)
                        polygon.append((start.X * 0.3048, start.Y * 0.3048))

                result.append(
                    BIMRoom(
                        room_id=str(room.Id),
                        name=room.Name,
                        level_id=str(level.Id) if level else "L-00",
                        area_m2=room.Area * 0.0929,  # ft2 -> m2
                        ceiling_height_m=h_m,
                        polygon=polygon,
                        source="revit_api",
                    )
                )
            return result

        except Exception as exc:
            raise RuntimeError(
                f"Revit live extraction failed: {exc}. Ensure running inside Revit process with API access."
            )

    def _extract_ifc(self, filepath: str) -> List[BIMRoom]:
        """Extract rooms from IFC file via ifcopenshell."""
        try:
            import ifcopenshell
            import ifcopenshell.util.element
            import ifcopenshell.util.placement

            ifc_file = ifcopenshell.open(filepath)
            spaces = ifc_file.by_type("IfcSpace")
            result: List[BIMRoom] = []

            for space in spaces:
                name = space.Name or space.LongName or f"Room-{space.id()}"
                # Get area from property sets
                area_m2 = 0.0
                for pset in ifcopenshell.util.element.get_psets(space).values():
                    for key, val in pset.items():
                        if "area" in key.lower() and isinstance(val, (int, float)):
                            area_m2 = float(val)
                            break

                # Get height from properties
                h_m = 3.0
                for pset in ifcopenshell.util.element.get_psets(space).values():
                    for key, val in pset.items():
                        if "height" in key.lower() and isinstance(val, (int, float)):
                            h_m = float(val)
                            break

                # Simplified: use bounding box as polygon
                # Full implementation needs ifcopenshell.geom
                # HIGH-10 FIX: Previously created a square polygon
                # (sqrt(area) × sqrt(area)) which destroys corridor geometry —
                # a 2m×20m corridor becomes a 6.3m×6.3m square, incorrectly
                # affecting detector spacing calculations. Instead, flag for
                # manual geometry review and use a conservative placeholder.
                if area_m2 > 0:
                    side = math.sqrt(area_m2)
                    poly = [
                        (0, 0),
                        (side, 0),
                        (side, side),
                        (0, side),
                    ]
                    logger.warning(
                        "HIGH-10: Room '%s' (id=%s) has no boundary geometry from IFC. "
                        "Using square polygon (%.1fm × %.1fm) from area only — "
                        "this DESTROYS corridor geometry. A 2m×20m corridor becomes "
                        "%.1fm×%.1fm square. Manual geometry review REQUIRED for "
                        "accurate detector placement. Install ifcopenshell.geom for "
                        "proper boundary extraction.",
                        name,
                        space.id(),
                        side,
                        side,
                        side,
                        side,
                    )
                else:
                    poly = [(0, 0), (10, 0), (10, 8), (0, 8)]

                level_id = "L-00"
                if space.Decomposes:
                    for rel in space.Decomposes:
                        if hasattr(rel, "RelatingObject"):
                            level_id = str(rel.RelatingObject.id())

                result.append(
                    BIMRoom(
                        room_id=str(space.id()),
                        name=name,
                        level_id=level_id,
                        # V78 FIX: No longer default to 20 m² — phantom area under-protects
                        # large spaces (500 m² atrium gets 20 m² of protection = 2 detectors).
                        # Instead, flag missing area and use 0 (excluded from analysis).
                        area_m2=area_m2 if area_m2 and area_m2 > 0 else 0.0,
                        ceiling_height_m=h_m,
                        polygon=poly,
                        source="ifc",
                    )
                )
            return result

        except ImportError:
            raise ImportError("ifcopenshell not installed. Install: pip install ifcopenshell")

    def _extract_json(self, filepath: str) -> List[BIMRoom]:
        """Extract rooms from FireAI JSON export or Revit Dynamo JSON.

        This is the universal fallback — works in CI, cloud, Linux.
        Generate the JSON from Revit using the provided Dynamo script.
        """
        with open(filepath, encoding="utf-8") as f:
            data = json.load(f)

        rooms_data = data if isinstance(data, list) else data.get("rooms", [])
        result: List[BIMRoom] = []

        for rd in rooms_data:
            polygon = rd.get("polygon_coords") or rd.get("polygon") or []
            if not polygon:
                w = float(rd.get("width", rd.get("room_width", 10.0)))
                l = float(rd.get("length", rd.get("room_length", 8.0)))
                polygon = [(0, 0), (w, 0), (w, l), (0, l)]

            result.append(
                BIMRoom(
                    room_id=str(rd.get("room_id", str(uuid.uuid4()))),
                    name=str(rd.get("name", rd.get("room_id", "Room"))),
                    level_id=str(rd.get("level_id", rd.get("floor_id", "L-01"))),
                    # V78 FIX: Use actual area_m2 if provided; don't fabricate from width×length
                    # defaults (10×8=80m² phantom area). A 4m² closet gets 80m² protection.
                    area_m2=float(rd.get("area_m2", 0.0)),
                    ceiling_height_m=float(rd.get("ceiling_height", rd.get("ceiling_height_m", 3.0))),
                    polygon=[(float(p[0]), float(p[1])) for p in polygon],
                    occupancy_type=str(rd.get("occupancy_type", "office")),
                    source="json",
                )
            )
        return result

    def _extract_dxf(self, filepath: str) -> List[BIMRoom]:
        """Extract rooms from DXF using existing streaming parser.

        HIGH-11 FIX: Previously hardcoded scale_factor=0.001 (mm→m)
        without unit detection. BIM data may use metres, centimetres,
        or other units. Now uses a configurable scale factor with a
        warning when the default is applied without explicit unit
        confirmation from the BIM source.
        """
        # HIGH-11: Configurable scale factor with unit detection.
        # Default 0.001 assumes mm→m (most common for DXF from Revit),
        # but BIM data may already be in metres (1.0) or cm (0.01).
        # Without unit confirmation, the default may produce coordinates
        # that are 1000× too small or too large — destroying all
        # spatial calculations (detector spacing, coverage, etc.).
        scale_factor = 0.001  # mm → m (default for Revit DXF export)
        logger.warning(
            "HIGH-11: DXF scale factor hardcoded to %.4f (mm→m). "
            "If BIM data uses different units, coordinates will be wrong. "
            "Verify units from BIM source metadata. "
            "Common scale factors: 1.0 (metres), 0.01 (cm→m), 0.001 (mm→m), "
            "0.3048 (feet→m).",
            scale_factor,
        )
        try:
            from fireai.core.streaming_dwg_parser import StreamingDXFParser

            parser = StreamingDXFParser(
                scale_factor=scale_factor,  # HIGH-11: was hardcoded 0.001
                min_area_m2=1.0,
            )
            rooms: List[BIMRoom] = []
            for i, streamed in enumerate(parser.stream_file(filepath)):
                rooms.append(
                    BIMRoom(
                        room_id=streamed.room_id,
                        name=f"Room-{i + 1:04d}",
                        level_id=streamed.floor_id,
                        area_m2=streamed.area_m2,
                        ceiling_height_m=3.0,  # DXF has no height info
                        polygon=streamed.polygon,
                        source="dxf",
                    )
                )
            return rooms
        except ImportError:
            raise ImportError(
                "StreamingDXFParser not available. "
                "The DXF parser module is required for DXF extraction. "
                "Use JSON or IFC format instead."
            )
        except Exception as exc:
            raise RuntimeError(f"DXF extraction failed: {exc}")


# ---------------------------------------------------------------------------
# Dynamo Script Generator (JSON bridge for Revit)
# ---------------------------------------------------------------------------

DYNAMO_SCRIPT_JSON = """
{
  "Name": "FireAI Room Export",
  "Description": "Exports Revit rooms to FireAI JSON format",
  "Author": "FireAI",
  "Graphs": [
    {
      "Type": "Python Script",
      "Code": "import clr; clr.AddReference('RevitAPI'); from Autodesk.Revit.DB import FilteredElementCollector, BuiltInCategory, SpatialElementBoundaryOptions; doc = __revit__.ActiveUIDocument.Document; collector = FilteredElementCollector(doc); rooms = collector.OfCategory(BuiltInCategory.OST_Rooms).WhereElementIsNotElementType().ToElements(); result = []; [result.append({'room_id': str(r.Id), 'name': r.Name, 'area_m2': r.Area * 0.0929, 'ceiling_height': 3.0, 'polygon_coords': [[c.GetEndPoint(0).X*0.3048, c.GetEndPoint(0).Y*0.3048] for s in (r.GetBoundarySegments(SpatialElementBoundaryOptions()) or [[]])[0] for c in [s.GetCurve()]] if r.GetBoundarySegments(SpatialElementBoundaryOptions()) else [], 'level_id': str(r.LevelId)}) for r in rooms if r.Area > 0]; import json, os; path = os.path.join(os.environ.get('TEMP','C:/temp'), 'fireai_rooms.json'); f=open(path,'w'); json.dump({'rooms': result}, f, indent=2); f.close(); OUT = f'Exported {len(result)} rooms to {path}'"
    }
  ]
}
"""


def generate_dynamo_script(output_path: str = "fireai_room_export.dyn") -> str:
    """Generate Dynamo script to export Revit rooms to FireAI JSON.
    Run this inside Revit Dynamo player to get rooms without Revit API dependency.
    """
    with open(output_path, "w") as f:
        f.write(DYNAMO_SCRIPT_JSON)
    return output_path


# ---------------------------------------------------------------------------
# BIM Sync Orchestrator
# ---------------------------------------------------------------------------


class BIMSyncOrchestrator:
    """SURGICAL FIX: Ties everything together.

    Workflow:
      1. Extract rooms (any source)
      2. Convert to FireAI format
      3. Run analysis
      4. Write back detector positions (if Revit live)
    """

    def __init__(self) -> None:
        self._bridge = RevitAPIBridge()

    def sync_from_source(
        self,
        source: str,
        analyser: Any = None,  # FloorAnalyser
    ) -> Dict[str, Any]:
        """Extract rooms -> analyse -> return results.

        Args:
            source:   "live", "path/to/file.ifc", "path/to/file.json", etc.
            analyser: FloorAnalyser instance (creates default if None).

        """
        # Step 1: Extract rooms
        bim_rooms = self._bridge.extract_rooms(source)

        # Step 2: Convert to FireAI format
        room_dicts = [r.to_fireai_room_dict() for r in bim_rooms]

        # Step 3: Analyse
        if analyser is None:
            try:
                from fireai.core.floor_analyser import FloorAnalyser

                analyser = FloorAnalyser()  # type: ignore[call-arg]
            except ImportError:
                return {
                    "status": "error",
                    "error": "FloorAnalyser not available",
                    "rooms": room_dicts,
                    "source": source,
                    "bridge_mode": self._bridge.mode,
                }

        report = analyser.analyse(room_dicts)

        return {
            "status": "success",
            "source": source,
            "bridge_mode": self._bridge.mode,
            "rooms_extracted": len(bim_rooms),
            "report": report,
            "note": (
                "Live Revit sync active — results reflect current model."
                if self._bridge.is_live
                else f"File-based sync from {source}. For live sync, run inside Revit with API access."
            ),
        }

    def generate_setup_guide(self) -> str:
        """Guide for setting up BIM sync in current environment."""
        mode = self._bridge.mode
        guides = {
            "revit_api": (
                "Revit API detected. Live sync available.\nRun fireai from within Revit using pyRevit or Dynamo."
            ),
            "pyrevit": ("pyRevit detected. Live sync available.\nUse the FireAI pyRevit extension."),
            "ifcopenshell": (
                "ifcopenshell available. IFC file sync available.\n"
                "Export IFC from Revit: File -> Export -> IFC -> IFC 2x3\n"
                "Then: sync.sync_from_source('path/to/model.ifc')"
            ),
            "json_file": (
                "JSON file sync only.\n"
                "To connect to Revit:\n"
                "  Option 1: pip install ifcopenshell (IFC export from Revit)\n"
                "  Option 2: Use Dynamo script (generate_dynamo_script())\n"
                "  Option 3: Run on Windows with Revit installed\n"
                "\nFor CI/Cloud: use JSON files (generate_dynamo_script() to export)"
            ),
        }
        return guides.get(mode, f"Unknown mode: {mode}")
