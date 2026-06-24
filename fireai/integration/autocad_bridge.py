"""fireai/integration/autocad_bridge.py
======================================
AutoCAD Integration — DWG/DXF processing and AutoCAD APS/Forge compatibility.

Provides bidirectional translation between AutoCAD drawing files (DWG/DXF)
and the FireAI DesignData model, enabling automated fire alarm design
verification directly from architectural drawings.

Layer conventions extracted:
  - ARCH-WALL, ARCH-DOOR, ARCH-WINDOW, ARCH-COLUMN
  - FIRE-DETECTOR, FIRE-NAC, FIRE-PANEL, FIRE-CABLE
  - FIRE-SPRINKLER, FIRE-STROBE, FIRE-PULLSTATION

References:
  - AutoCAD DXF Reference (Autodesk)
  - ezdxf library documentation (https://ezdxf.mozman.at)

"""

from __future__ import annotations

import hashlib
import logging
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

from fireai.core.event_bus import EventBus, Events

logger = logging.getLogger(__name__)


# ===========================================================================
# Enums
# ===========================================================================


class LayerCategory(str, Enum):
    ARCH_WALL = "ARCH-WALL"
    ARCH_DOOR = "ARCH-DOOR"
    ARCH_WINDOW = "ARCH-WINDOW"
    ARCH_COLUMN = "ARCH-COLUMN"
    FIRE_DETECTOR = "FIRE-DETECTOR"
    FIRE_NAC = "FIRE-NAC"
    FIRE_PANEL = "FIRE-PANEL"
    FIRE_CABLE = "FIRE-CABLE"
    FIRE_SPRINKLER = "FIRE-SPRINKLER"
    FIRE_STROBE = "FIRE-STROBE"
    FIRE_PULLSTATION = "FIRE-PULLSTATION"
    FIRE_DUCT = "FIRE-DUCT"
    FIRE_DAMPER = "FIRE-DAMPER"
    HVAC_DIFFUSER = "HVAC-DIFFUSER"
    HVAC_DUCT = "HVAC-DUCT"
    ELEC_CONDUIT = "ELEC-CONDUIT"
    ELEC_PANEL = "ELEC-PANEL"


LAYER_MAP: Dict[str, LayerCategory] = {
    "arch-wall": LayerCategory.ARCH_WALL,
    "arch-walls": LayerCategory.ARCH_WALL,
    "a-wall": LayerCategory.ARCH_WALL,
    "arch-door": LayerCategory.ARCH_DOOR,
    "arch-doors": LayerCategory.ARCH_DOOR,
    "a-door": LayerCategory.ARCH_DOOR,
    "arch-window": LayerCategory.ARCH_WINDOW,
    "arch-windows": LayerCategory.ARCH_WINDOW,
    "a-window": LayerCategory.ARCH_WINDOW,
    "arch-column": LayerCategory.ARCH_COLUMN,
    "a-column": LayerCategory.ARCH_COLUMN,
    "fire-detector": LayerCategory.FIRE_DETECTOR,
    "fire-detect": LayerCategory.FIRE_DETECTOR,
    "f-detector": LayerCategory.FIRE_DETECTOR,
    "fire-nac": LayerCategory.FIRE_NAC,
    "f-nac": LayerCategory.FIRE_NAC,
    "fire-panel": LayerCategory.FIRE_PANEL,
    "f-panel": LayerCategory.FIRE_PANEL,
    "fire-cable": LayerCategory.FIRE_CABLE,
    "f-cable": LayerCategory.FIRE_CABLE,
    "fire-sprinkler": LayerCategory.FIRE_SPRINKLER,
    "f-sprinkler": LayerCategory.FIRE_SPRINKLER,
    "fire-strobe": LayerCategory.FIRE_STROBE,
    "f-strobe": LayerCategory.FIRE_STROBE,
    "fire-pull": LayerCategory.FIRE_PULLSTATION,
    "fire-pullstation": LayerCategory.FIRE_PULLSTATION,
    "f-pull": LayerCategory.FIRE_PULLSTATION,
    "hvac-diffuser": LayerCategory.HVAC_DIFFUSER,
    "hvac-duct": LayerCategory.HVAC_DUCT,
    "elec-conduit": LayerCategory.ELEC_CONDUIT,
    "elec-panel": LayerCategory.ELEC_PANEL,
}


# ===========================================================================
# Data Models
# ===========================================================================


@dataclass(frozen=True)
class LayerData:
    name: str
    category: LayerCategory
    entities: List[Dict[str, Any]] = field(default_factory=list)
    color: int = 7  # AutoCAD color index (default = white)
    linetype: str = "CONTINUOUS"
    is_frozen: bool = False
    is_locked: bool = False


@dataclass(frozen=True)
class DWGEntity:
    handle: str
    dxf_type: str
    layer: str
    coordinates: List[Tuple[float, float, float]]
    properties: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class DesignData:
    source_file: str = ""
    file_hash: str = ""
    layers: List[LayerData] = field(default_factory=list)
    entities: List[DWGEntity] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    imported_at: str = ""


# ===========================================================================
# DXF Parser (ezdxf preferred, fallback text parser)
# ===========================================================================


class _DXFTextParser:
    """Minimal DXF text parser for when ezdxf is unavailable.

    Parses basic DXF entities (LINE, LWPOLYLINE, CIRCLE, INSERT)
    and groups them by layer. Does not support blocks, xdata, or
    advanced DXF features.
    """

    def __init__(self) -> None:
        self._layers: Dict[str, List[Dict[str, Any]]] = {}
        self._current_section: str = ""
        self._current_entity: Optional[Dict[str, Any]] = None
        self._current_code: Optional[int] = None
        self._header: Dict[str, Any] = {}

    def parse(self, content: str) -> Dict[str, Any]:
        self._layers = {}
        self._current_section = ""
        self._current_entity = None

        lines = content.splitlines()
        i = 0
        while i < len(lines):
            code_line = lines[i].strip()
            i += 1
            if i >= len(lines):
                break
            value_line = lines[i].strip()
            i += 1

            try:
                code = int(code_line)
            except ValueError:
                continue

            if code == 0:
                self._finalize_entity()
                if value_line in ("SECTION", "ENDSEC", "EOF"):
                    if value_line == "SECTION":
                        pass
                    elif value_line == "ENDSEC":
                        self._current_section = ""
                elif value_line == "HEADER":
                    self._current_section = "HEADER"
                elif value_line == "TABLES":
                    self._current_section = "TABLES"
                elif value_line == "ENTITIES":
                    self._current_section = "ENTITIES"
                elif self._current_section == "ENTITIES":
                    self._current_entity = {"type": value_line, "layer": "0"}
                else:
                    self._current_entity = {"type": value_line, "layer": "0"}
            elif code == 2:
                if self._current_section == "TABLES":
                    pass
            elif code == 8:
                if self._current_entity is not None:
                    self._current_entity["layer"] = value_line
            elif code in (10, 11, 12, 13):
                self._add_coord(code, value_line, "x")
            elif code in (20, 21, 22, 23):
                self._add_coord(code, value_line, "y")
            elif code in (30, 31, 32, 33):
                self._add_coord(code, value_line, "z")
            elif code == 100:
                pass
            elif code == 410:
                if self._current_entity is not None:
                    self._current_entity.setdefault("properties", {})[
                        "layout"
                    ] = value_line
            elif code == 62:
                if self._current_entity is not None:
                    try:
                        self._current_entity.setdefault(
                            "properties", {}
                        )["color"] = int(value_line)
                    except ValueError:
                        pass
            elif code == 6:
                if self._current_entity is not None:
                    self._current_entity.setdefault("properties", {})[
                        "linetype"
                    ] = value_line

        self._finalize_entity()
        return {
            "layers": self._layers,
            "header": self._header,
        }

    def _add_coord(self, code: int, value: str, axis: str) -> None:
        if self._current_entity is None:
            return
        coord_idx = (code % 10) - 10 if code >= 20 else code - 10
        if coord_idx < 0:
            coord_idx = 0
        try:
            val = float(value)
        except ValueError:
            return
        coords = self._current_entity.setdefault("coords", [])
        while len(coords) <= coord_idx:
            coords.append([0.0, 0.0, 0.0])
        if axis == "x":
            coords[coord_idx][0] = val
        elif axis == "y":
            coords[coord_idx][1] = val
        elif axis == "z":
            coords[coord_idx][2] = val

    def _finalize_entity(self) -> None:
        if self._current_entity is not None:
            layer_name = self._current_entity.get("layer", "0").lower()
            self._layers.setdefault(layer_name, []).append(
                self._current_entity
            )
            self._current_entity = None


# ===========================================================================
# AutoCAD Bridge
# ===========================================================================


class AutoCADBridge:
    """DWG/DXF processing and AutoCAD APS/Forge compatibility.

    Handles:
      - DXF import (via ezdxf when available, fallback text parser)
      - DWG import (documents requirement for ODA/Teigha or AutoCAD API)
      - DXF export with layer preservation
      - Layer extraction and classification
      - Round-trip: import DXF -> process -> export DXF

    Note on DWG:
      The DWG format is proprietary. For full DWG support in production,
      use the Open Design Alliance (ODA/Teigha) SDK or AutoCAD's .NET API.
      This bridge provides a structured import path for when those are
      available, and documents the requirement clearly.
    """

    # Supported layers for fire alarm design extraction
    FIRE_LAYERS = {
        LayerCategory.FIRE_DETECTOR,
        LayerCategory.FIRE_NAC,
        LayerCategory.FIRE_PANEL,
        LayerCategory.FIRE_CABLE,
        LayerCategory.FIRE_SPRINKLER,
        LayerCategory.FIRE_STROBE,
        LayerCategory.FIRE_PULLSTATION,
    }

    ARCH_LAYERS = {
        LayerCategory.ARCH_WALL,
        LayerCategory.ARCH_DOOR,
        LayerCategory.ARCH_WINDOW,
        LayerCategory.ARCH_COLUMN,
    }

    def __init__(self, event_bus: Optional[EventBus] = None) -> None:
        self._event_bus = event_bus or EventBus.instance()
        self._has_ezdxf: bool = self._check_ezdxf()
        self._last_design: Optional[DesignData] = None

    # ── Import ──────────────────────────────────────────────────────────

    def import_dwg(self, path: str) -> DesignData:
        """Import a DWG file.

        Production Note:
          Full DWG support requires the Open Design Alliance (ODA/Teigha)
          SDK or AutoCAD's .NET API. This implementation reads the file
          header and documents what a full implementation would do.

        Args:
            path: Path to the DWG file.

        Returns:
            DesignData with extracted entities (or error metadata).

        """
        if not os.path.exists(path):
            raise FileNotFoundError(f"DWG file not found: {path}")

        file_size = os.path.getsize(path)
        with open(path, "rb") as f:
            raw = f.read()

        file_hash = hashlib.sha256(raw).hexdigest()

        design = DesignData(
            source_file=path,
            file_hash=file_hash,
            imported_at=datetime.now(timezone.utc).isoformat(),
            metadata={
                "format": "DWG",
                "file_size_bytes": file_size,
                "note": "Full DWG parsing requires ODA/Teigha SDK or AutoCAD API. "
                "See docs/autocad_integration.md for setup instructions.",
            },
        )

        self._last_design = design
        self._event_bus.publish(
            Events.MODEL_CHANGED,
            data={
                "source": "autocad_bridge",
                "format": "DWG",
                "file": path,
                "hash": file_hash[:16],
            },
            source="autocad_bridge",
        )
        return design

    def import_dxf(self, path: str) -> DesignData:
        """Import a DXF file using ezdxf (preferred) or fallback text parser.

        Args:
            path: Path to the DXF file.

        Returns:
            DesignData with extracted layers and entities.

        """
        if not os.path.exists(path):
            raise FileNotFoundError(f"DXF file not found: {path}")

        with open(path, encoding="utf-8", errors="replace") as f:
            content = f.read()

        file_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()

        if self._has_ezdxf:
            layers = self._parse_dxf_ezdxf(content)
        else:
            layers = self._parse_dxf_text(content)

        classified_layers = self._classify_layers(layers)

        design = DesignData(
            source_file=path,
            file_hash=file_hash,
            layers=classified_layers,
            imported_at=datetime.now(timezone.utc).isoformat(),
            metadata={
                "format": "DXF",
                "parser": "ezdxf" if self._has_ezdxf else "text_fallback",
                "entity_count": sum(
                    len(l.entities) for l in classified_layers
                ),
            },
        )

        self._last_design = design

        self._event_bus.publish(
            Events.MODEL_CHANGED,
            data={
                "source": "autocad_bridge",
                "format": "DXF",
                "file": path,
                "hash": file_hash[:16],
                "layers": len(classified_layers),
            },
            source="autocad_bridge",
        )
        return design

    # ── Export ──────────────────────────────────────────────────────────

    def export_dwg(self, design: DesignData, path: str) -> str:
        """Export design data to DWG format.

        Production Note:
          DWG export requires the ODA/Teigha SDK or AutoCAD API.
          This implementation writes a placeholder noting the requirement.

        Args:
            design: Design data to export.
            path: Output path for the DWG file.

        Returns:
            Path to the exported file.

        """
        output_dir = os.path.dirname(path)
        if output_dir and not os.path.exists(output_dir):
            os.makedirs(output_dir, exist_ok=True)

        # Write a minimal DWG header placeholder
        with open(path, "wb") as f:
            f.write(b"AC1032")  # AutoCAD 2024 header marker
            f.write(b"\x00" * 128)

        logger.info(
            "DWG export placeholder written to %s. "
            "Full DWG export requires ODA/Teigha SDK or AutoCAD API.",
            path,
        )

        self._event_bus.publish(
            Events.MODEL_CHANGED,
            data={
                "source": "autocad_bridge",
                "action": "export",
                "format": "DWG",
                "path": path,
            },
            source="autocad_bridge",
        )
        return path

    def export_dxf(self, design: DesignData, path: str) -> str:
        """Export design data to DXF format.

        Preserves all layers and entities from the design data,
        enabling round-trip: import DXF -> process -> export DXF.

        Args:
            design: Design data to export.
            path: Output path for the DXF file.

        Returns:
            Path to the exported file.

        """
        output_dir = os.path.dirname(path)
        if output_dir and not os.path.exists(output_dir):
            os.makedirs(output_dir, exist_ok=True)

        lines: List[str] = []
        lines.append("0")
        lines.append("SECTION")
        lines.append("2")
        lines.append("HEADER")
        lines.append("9")
        lines.append("$ACADVER")
        lines.append("1")
        lines.append("AC1032")
        lines.append("0")
        lines.append("ENDSEC")

        # Tables section (layer definitions)
        lines.append("0")
        lines.append("SECTION")
        lines.append("2")
        lines.append("TABLES")
        lines.append("0")
        lines.append("TABLE")
        lines.append("2")
        lines.append("LAYER")
        lines.append("70")
        lines.append(str(len(design.layers)))

        for layer in design.layers:
            lines.append("0")
            lines.append("LAYER")
            lines.append("2")
            lines.append(layer.name)
            lines.append("70")
            lines.append("0")
            lines.append("62")
            lines.append(str(layer.color))
            lines.append("6")
            lines.append(layer.linetype)

        lines.append("0")
        lines.append("ENDTAB")
        lines.append("0")
        lines.append("ENDSEC")

        # Entities section
        lines.append("0")
        lines.append("SECTION")
        lines.append("2")
        lines.append("ENTITIES")

        for layer in design.layers:
            for entity in layer.entities:
                dxf_type = entity.get("type", "LINE")
                lines.append("0")
                lines.append(dxf_type)
                lines.append("8")
                lines.append(layer.name)

                color = entity.get("properties", {}).get("color", 7)
                lines.append("62")
                lines.append(str(color))

                coords = entity.get("coords", [])
                for i, pt in enumerate(coords):
                    x = pt[0] if len(pt) > 0 else 0.0
                    y = pt[1] if len(pt) > 1 else 0.0
                    z = pt[2] if len(pt) > 2 else 0.0
                    lines.append("10" if i == 0 else f"1{i}")
                    lines.append(f"{x:.6f}")
                    lines.append("20" if i == 0 else f"2{i}")
                    lines.append(f"{y:.6f}")
                    lines.append("30" if i == 0 else f"3{i}")
                    lines.append(f"{z:.6f}")

        lines.append("0")
        lines.append("ENDSEC")
        lines.append("0")
        lines.append("EOF")

        dxf_content = "\r\n".join(lines)

        with open(path, "w", encoding="utf-8") as f:
            f.write(dxf_content)

        self._event_bus.publish(
            Events.MODEL_CHANGED,
            data={
                "source": "autocad_bridge",
                "action": "export",
                "format": "DXF",
                "path": path,
                "layers": len(design.layers),
            },
            source="autocad_bridge",
        )
        return path

    # ── Layer Queries ───────────────────────────────────────────────────

    def get_fire_layers(
        self, design: DesignData
    ) -> List[LayerData]:
        return [
            l
            for l in design.layers
            if l.category in self.FIRE_LAYERS
        ]

    def get_arch_layers(
        self, design: DesignData
    ) -> List[LayerData]:
        return [
            l
            for l in design.layers
            if l.category in self.ARCH_LAYERS
        ]

    # ── Internal: DXF Parsing ───────────────────────────────────────────

    def _check_ezdxf(self) -> bool:
        try:
            import ezdxf  # noqa: F401
            return True
        except ImportError:
            logger.warning(
                "ezdxf not available — using fallback DXF text parser. "
                "Install ezdxf with: pip install ezdxf"
            )
            return False

    def _parse_dxf_ezdxf(self, content: str) -> Dict[str, List[Dict[str, Any]]]:
        import io

        import ezdxf

        layers: Dict[str, List[Dict[str, Any]]] = {}

        try:
            doc = ezdxf.readfile(
                io.StringIO(content)  # type: ignore[arg-type]
            )
        except Exception:
            doc = ezdxf.new("R2010")
            try:
                doc = ezdxf.readfile(
                    io.StringIO(content)  # type: ignore[arg-type]
                )
            except Exception as exc:
                logger.error(
                    "ezdxf parsing failed: %s", exc
                )
                return {}

        for entity in doc.modelspace():
            layer_name = entity.dxf.layer.lower() if hasattr(entity.dxf, 'layer') else "0"
            entity_data = {
                "type": entity.dxftype(),
                "layer": entity.dxf.layer,
                "properties": {},
            }

            if hasattr(entity.dxf, "color"):
                entity_data["properties"]["color"] = entity.dxf.color
            if hasattr(entity.dxf, "linetype"):
                entity_data["properties"]["linetype"] = entity.dxf.linetype
            if entity.dxftype() == "CIRCLE" and hasattr(entity.dxf, "radius"):
                entity_data["properties"]["radius"] = entity.dxf.radius

            coords = self._extract_ezdxf_coords(entity)
            if coords:
                entity_data["coords"] = coords

            layers.setdefault(layer_name, []).append(entity_data)

            if hasattr(entity, "attribs"):
                for attrib in entity.attribs:
                    if hasattr(attrib.dxf, "text"):
                        entity_data["properties"]["text"] = attrib.dxf.text

        return layers

    def _extract_ezdxf_coords(
        self, entity: Any
    ) -> List[List[float]]:
        coords: List[List[float]] = []
        dxf_type = entity.dxftype()

        if dxf_type == "LINE":
            coords.append(
                [entity.dxf.start.x, entity.dxf.start.y, entity.dxf.start.z]
            )
            coords.append(
                [entity.dxf.end.x, entity.dxf.end.y, entity.dxf.end.z]
            )
        elif dxf_type == "LWPOLYLINE":
            for point in entity.get_points():
                coords.append([point[0], point[1], 0.0])
        elif dxf_type == "CIRCLE":
            coords.append(
                [entity.dxf.center.x, entity.dxf.center.y, entity.dxf.center.z]
            )
        elif dxf_type == "INSERT" or dxf_type == "TEXT" or dxf_type == "MTEXT":
            coords.append(
                [
                    entity.dxf.insert.x,
                    entity.dxf.insert.y,
                    entity.dxf.insert.z,
                ]
            )

        return coords

    def _parse_dxf_text(
        self, content: str
    ) -> Dict[str, List[Dict[str, Any]]]:
        parser = _DXFTextParser()
        return parser.parse(content)["layers"]

    def _classify_layers(
        self,
        raw_layers: Dict[str, List[Dict[str, Any]]],
    ) -> List[LayerData]:
        classified: List[LayerData] = []

        for raw_name, entities in sorted(raw_layers.items()):
            lower_name = raw_name.lower().strip()
            category = LAYER_MAP.get(lower_name, LayerCategory.ARCH_WALL)

            classified.append(
                LayerData(
                    name=raw_name,
                    category=category,
                    entities=entities,
                )
            )

        return classified


# ===========================================================================
# Self-Test
# ===========================================================================

if __name__ == "__main__":
    import tempfile

    bridge = AutoCADBridge()

    # Create a sample DXF for round-trip testing
    sample = DesignData(
        source_file="test.dxf",
        imported_at=datetime.now(timezone.utc).isoformat(),
        layers=[
            LayerData(
                name="ARCH-WALL",
                category=LayerCategory.ARCH_WALL,
                entities=[
                    {
                        "type": "LINE",
                        "coords": [
                            [0.0, 0.0, 0.0],
                            [10.0, 0.0, 0.0],
                        ],
                        "properties": {"color": 7},
                    }
                ],
            ),
            LayerData(
                name="FIRE-DETECTOR",
                category=LayerCategory.FIRE_DETECTOR,
                entities=[
                    {
                        "type": "CIRCLE",
                        "coords": [[5.0, 5.0, 0.0, 0.3]],
                        "properties": {"color": 1},
                    }
                ],
            ),
        ],
    )

    with tempfile.NamedTemporaryFile(
        suffix=".dxf", delete=False
    ) as tmp:
        export_path = bridge.export_dxf(sample, tmp.name)
        print(f"Exported to: {export_path}")

        imported = bridge.import_dxf(export_path)
        print(f"Imported: {len(imported.layers)} layers")

        fire_layers = bridge.get_fire_layers(imported)
        print(f"Fire layers: {len(fire_layers)}")

        os.unlink(export_path)
