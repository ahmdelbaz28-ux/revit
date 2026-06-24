"""riser_diagram_generator.py — NFPA 72 §7.4.5 System Riser Diagram Generator
===============================================================================

Generates a fire alarm system riser diagram (one-line schematic) showing
the vertical and horizontal distribution of the fire alarm system from
the FACP through loops, NAC circuits, and network connections.

NFPA 72 §7.4.5 requires a "system riser diagram" as part of the
documentation package.  Without it:
  - The AHJ (Authority Having Jurisdiction) will REJECT the submittal.
  - The contractor will install without understanding the network topology.
  - There is no visual representation of vertical cable distribution.

This module generates DXF-format riser diagrams with:
  - FACP and booster panels vertically arranged
  - SLC loops branching horizontally from each panel
  - NAC circuits with device type annotations
  - Network connections between panels
  - Vertical fault isolators on SLC loops
  - Cable type annotations (FPL/FPLR/FPLP/CI) from survivability engine
  - Survivability level indication

The riser diagram is a SCHEMATIC, not a floor plan — it shows logical
connections, not physical routing.

Thread-safety: zero module-level mutable state.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Tuple

try:
    import ezdxf

    HAS_EZDXF = True
except ImportError:
    HAS_EZDXF = False

logger = logging.getLogger(__name__)

__all__ = [
    "RiserDiagramGenerator",
    "RiserDiagramResult",
    "RiserDiagramSpec",
    "RiserLoop",
    "RiserNACCircuit",
    "RiserNetworkLink",
    "RiserPanel",
]


# ============================================================================
# Data Structures
# ============================================================================


@dataclass(frozen=True)
class RiserPanel:
    """A fire alarm control panel or booster in the riser diagram.

    Attributes:
        panel_id:   Unique panel identifier (e.g. "FACP-1").
        panel_type: "FACP" (main) or "BOOSTER" (remote).
        floor_id:   Floor where panel is located.
        loop_count: Number of SLC loops on this panel.
        nac_count:  Number of NAC circuits on this panel.

    """

    panel_id: str
    panel_type: str = "FACP"
    floor_id: str = "GF"
    loop_count: int = 1
    nac_count: int = 2


@dataclass(frozen=True)
class RiserLoop:
    """An SLC loop in the riser diagram.

    Attributes:
        loop_id:           Loop identifier (e.g. "SLC-1").
        panel_id:          Parent panel.
        device_count:      Total devices on this loop.
        isolator_count:    Fault isolators on this loop.
        floors_served:     List of floor IDs served by this loop.
        cable_type:        Cable type (FPL/FPLR/FPLP/CI).
        cable_length_m:    Estimated cable length.
        class_type:        "A" or "B" (Class A or Class B wiring).

    """

    loop_id: str
    panel_id: str
    device_count: int = 0
    isolator_count: int = 0
    floors_served: Tuple[str, ...] = ()
    cable_type: str = "FPL"
    cable_length_m: float = 0.0
    class_type: str = "B"


@dataclass(frozen=True)
class RiserNACCircuit:
    """A NAC (Notification Appliance Circuit) in the riser diagram.

    Attributes:
        nac_id:         Circuit identifier (e.g. "NAC-1").
        panel_id:       Parent panel.
        device_types:   Types of devices on this circuit.
        device_count:   Number of notification appliances.
        floor_id:       Floor served.
        cable_type:     Cable type for NAC wiring.

    """

    nac_id: str
    panel_id: str
    device_types: Tuple[str, ...] = ("horn_strobe_15cd",)
    device_count: int = 0
    floor_id: str = "GF"
    cable_type: str = "FPL"


@dataclass(frozen=True)
class RiserNetworkLink:
    """A network connection between panels.

    Attributes:
        from_panel: Source panel ID.
        to_panel:   Destination panel ID.
        link_type:  "NETWORK" (panel-to-panel) or "RISER" (vertical cable).
        cable_type: Cable type for the network link.

    """

    from_panel: str
    to_panel: str
    link_type: str = "NETWORK"
    cable_type: str = "FPLR"


@dataclass
class RiserDiagramSpec:
    """Complete specification for a riser diagram.

    Attributes:
        project_name:    Project identifier.
        panels:          All panels in the system.
        loops:           All SLC loops.
        nac_circuits:    All NAC circuits.
        network_links:   Network connections between panels.
        survivability_level: Pathway survivability level (from engine).
        nfpa_version:    NFPA edition applied.

    """

    project_name: str = "FIRE ALARM SYSTEM"
    panels: List[RiserPanel] = field(default_factory=list)
    loops: List[RiserLoop] = field(default_factory=list)
    nac_circuits: List[RiserNACCircuit] = field(default_factory=list)
    network_links: List[RiserNetworkLink] = field(default_factory=list)
    survivability_level: str = "LEVEL_1"
    nfpa_version: str = "NFPA 72-2022"


@dataclass
class RiserDiagramResult:
    """Result of riser diagram generation.

    Attributes:
        output_path: Path to the generated DXF file.
        panel_count: Number of panels drawn.
        loop_count:  Number of SLC loops drawn.
        nac_count:   Number of NAC circuits drawn.
        warnings:    Non-fatal advisories.
        errors:      Fatal issues.

    """

    output_path: str = ""
    panel_count: int = 0
    loop_count: int = 0
    nac_count: int = 0
    warnings: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)


# ============================================================================
# Riser Diagram Generator
# ============================================================================


class RiserDiagramGenerator:
    """Generate NFPA 72 §7.4.5 compliant fire alarm riser diagrams.

    Creates a DXF-format schematic showing:
      - Panels (FACP/Booster) arranged vertically by floor
      - SLC loops branching horizontally from each panel
      - NAC circuits with device annotations
      - Network connections between panels
      - Fault isolators on loops
      - Cable type and survivability annotations

    Usage::

        gen = RiserDiagramGenerator()
        spec = RiserDiagramSpec(
            project_name="Building A",
            panels=[RiserPanel(panel_id="FACP-1", floor_id="GF", loop_count=2)],
            loops=[RiserLoop(loop_id="SLC-1", panel_id="FACP-1", device_count=48)],
            nac_circuits=[RiserNACCircuit(nac_id="NAC-1", panel_id="FACP-1")],
        )
        result = gen.generate(spec, output_path="riser_diagram.dxf")
    """

    # Layout constants (in drawing units = metres)
    FLOOR_SPACING = 5.0  # vertical distance between floors
    PANEL_WIDTH = 2.0  # panel box width
    PANEL_HEIGHT = 1.5  # panel box height
    LOOP_BRANCH_LEN = 8.0  # horizontal length of loop branch
    NAC_BRANCH_LEN = 6.0  # horizontal length of NAC branch
    BRANCH_SPACING = 1.0  # vertical spacing between branches
    TEXT_HEIGHT = 0.3  # text annotation height
    MARGIN_LEFT = 5.0  # left margin for panel placement
    MARGIN_BOTTOM = 5.0  # bottom margin

    def generate(
        self,
        spec: RiserDiagramSpec,
        output_path: str = "riser_diagram.dxf",
    ) -> RiserDiagramResult:
        """Generate a riser diagram DXF file.

        Args:
            spec: Riser diagram specification.
            output_path: Path for the output DXF file.

        Returns:
            RiserDiagramResult with generation statistics.

        """
        result = RiserDiagramResult()

        if not HAS_EZDXF:
            result.errors.append(
                "ezdxf >= 1.1.0 is required for riser diagram generation. Install with: pip install ezdxf>=1.1.0"
            )
            return result

        if not spec.panels:
            result.errors.append("No panels specified — cannot generate riser diagram.")
            return result

        try:
            doc = ezdxf.new(dxfversion="R2010")
            doc.header["$INSUNITS"] = 6  # metres
            msp = doc.modelspace()

            # Setup layers
            self._setup_layers(doc)

            # Layout: sort panels by floor
            panel_positions: Dict[str, Tuple[float, float]] = {}
            sorted_panels = sorted(spec.panels, key=lambda p: p.floor_id)

            # Draw panels
            for i, panel in enumerate(sorted_panels):
                px = self.MARGIN_LEFT
                py = self.MARGIN_BOTTOM + i * self.FLOOR_SPACING
                panel_positions[panel.panel_id] = (px, py)
                self._draw_panel(msp, px, py, panel, spec.survivability_level)

            # Draw network links between panels
            for link in spec.network_links:
                if link.from_panel in panel_positions and link.to_panel in panel_positions:
                    self._draw_network_link(
                        msp,
                        panel_positions[link.from_panel],
                        panel_positions[link.to_panel],
                        link,
                    )

            # Draw SLC loops
            branch_offset = 0
            for loop in spec.loops:
                if loop.panel_id not in panel_positions:
                    result.warnings.append(f"Loop {loop.loop_id}: panel {loop.panel_id} not found.")
                    continue
                px, py = panel_positions[loop.panel_id]
                branch_y = py + self.BRANCH_SPACING * (branch_offset + 1)
                self._draw_loop(msp, px, py, branch_y, loop)
                branch_offset += 1

            # Draw NAC circuits
            nac_offset = 0
            for nac in spec.nac_circuits:
                if nac.panel_id not in panel_positions:
                    result.warnings.append(f"NAC {nac.nac_id}: panel {nac.panel_id} not found.")
                    continue
                px, py = panel_positions[nac.panel_id]
                nac_y = py - self.BRANCH_SPACING * (nac_offset + 1)
                self._draw_nac(msp, px, py, nac_y, nac)
                nac_offset += 1

            # Title block
            self._draw_title(msp, spec)

            # Save
            doc.saveas(output_path)

            result.output_path = output_path
            result.panel_count = len(spec.panels)
            result.loop_count = len(spec.loops)
            result.nac_count = len(spec.nac_circuits)

            logger.info(
                "RiserDiagram: %d panels, %d loops, %d NAC → %s",
                result.panel_count,
                result.loop_count,
                result.nac_count,
                output_path,
            )

        except Exception as exc:
            result.errors.append(f"Riser diagram generation failed: {exc}")
            logger.error("RiserDiagram error: %s", exc)

        return result

    # ─── Drawing helpers ───────────────────────────────────────────────

    @staticmethod
    def _setup_layers(doc: Any) -> None:
        """Create CAD layers for the riser diagram."""
        layers = doc.layers
        layer_defs = {
            "RD-PANELS": (3, "Continuous"),  # Green — panels
            "RD-LOOPS": (5, "Continuous"),  # Blue — SLC loops
            "RD-NAC": (4, "Continuous"),  # Cyan — NAC circuits
            "RD-NETWORK": (1, "DASHED"),  # Red dashed — network links
            "RD-ISOLATORS": (2, "Continuous"),  # Yellow — fault isolators
            "RD-LABELS": (7, "Continuous"),  # White — text annotations
            "RD-TITLE": (7, "Continuous"),  # White — title block
        }
        for name, (color, lt) in layer_defs.items():
            try:
                layer = layers.add(name)
                layer.dxf.color = color
                layer.dxf.linetype = lt
            except ezdxf.DXFTableEntryError:
                pass

        # Add DASHED linetype
        try:
            doc.linetypes.add("DASHED", [0.6, 0.4, -0.2], description="__ __ __")
        except Exception:
            pass

    def _draw_panel(
        self,
        msp: Any,
        px: float,
        py: float,
        panel: RiserPanel,
        survivability_level: str,
    ) -> None:
        """Draw a panel symbol (rectangle with label)."""
        w = self.PANEL_WIDTH
        h = self.PANEL_HEIGHT

        # Panel rectangle
        pts = [
            (px - w / 2, py - h / 2, 0),
            (px + w / 2, py - h / 2, 0),
            (px + w / 2, py + h / 2, 0),
            (px - w / 2, py + h / 2, 0),
        ]
        msp.add_lwpolyline(pts, dxfattribs={"layer": "RD-PANELS", "closed": True})

        # Panel ID
        msp.add_text(
            panel.panel_id,
            dxfattribs={
                "layer": "RD-LABELS",
                "height": self.TEXT_HEIGHT,
                "insert": (px - w / 2 + 0.1, py + h / 2 - 0.4),
            },
        )

        # Panel type
        msp.add_text(
            panel.panel_type,
            dxfattribs={
                "layer": "RD-LABELS",
                "height": self.TEXT_HEIGHT * 0.8,
                "insert": (px - w / 2 + 0.1, py + h / 2 - 0.8),
            },
        )

        # Floor label
        msp.add_text(
            f"Floor: {panel.floor_id}",
            dxfattribs={
                "layer": "RD-LABELS",
                "height": self.TEXT_HEIGHT * 0.7,
                "insert": (px - w / 2 + 0.1, py - h / 2 + 0.1),
            },
        )

        # Survivability level
        if survivability_level != "LEVEL_1":
            msp.add_text(
                f"Survivability: {survivability_level}",
                dxfattribs={
                    "layer": "RD-LABELS",
                    "height": self.TEXT_HEIGHT * 0.6,
                    "insert": (px - w / 2 + 0.1, py - h / 2 + 0.4),
                },
            )

        # Loop/NAC counts
        msp.add_text(
            f"{panel.loop_count} SLC / {panel.nac_count} NAC",
            dxfattribs={
                "layer": "RD-LABELS",
                "height": self.TEXT_HEIGHT * 0.6,
                "insert": (px - w / 2 + 0.1, py - 0.1),
            },
        )

    def _draw_loop(
        self,
        msp: Any,
        panel_x: float,
        panel_y: float,
        branch_y: float,
        loop: RiserLoop,
    ) -> None:
        """Draw an SLC loop branch from a panel."""
        # Vertical line from panel to branch level
        msp.add_line(
            (panel_x + self.PANEL_WIDTH / 2, panel_y, 0),
            (panel_x + self.PANEL_WIDTH / 2, branch_y, 0),
            dxfattribs={"layer": "RD-LOOPS"},
        )

        # Horizontal branch
        end_x = panel_x + self.PANEL_WIDTH / 2 + self.LOOP_BRANCH_LEN
        msp.add_line(
            (panel_x + self.PANEL_WIDTH / 2, branch_y, 0),
            (end_x, branch_y, 0),
            dxfattribs={"layer": "RD-LOOPS"},
        )

        # Loop label
        msp.add_text(
            f"{loop.loop_id} (Class {loop.class_type})",
            dxfattribs={
                "layer": "RD-LABELS",
                "height": self.TEXT_HEIGHT * 0.8,
                "insert": (panel_x + self.PANEL_WIDTH / 2 + 0.2, branch_y + 0.2),
            },
        )

        # Device count
        msp.add_text(
            f"{loop.device_count} devices / {loop.isolator_count} isolators",
            dxfattribs={
                "layer": "RD-LABELS",
                "height": self.TEXT_HEIGHT * 0.6,
                "insert": (panel_x + self.PANEL_WIDTH / 2 + 0.2, branch_y - 0.3),
            },
        )

        # Cable type
        msp.add_text(
            f"Cable: {loop.cable_type} | {loop.cable_length_m:.0f}m",
            dxfattribs={
                "layer": "RD-LABELS",
                "height": self.TEXT_HEIGHT * 0.6,
                "insert": (panel_x + self.PANEL_WIDTH / 2 + 0.2, branch_y - 0.7),
            },
        )

        # Draw fault isolator symbols along the branch
        if loop.isolator_count > 0:
            for i in range(min(loop.isolator_count, 5)):  # max 5 symbols
                ix = panel_x + self.PANEL_WIDTH / 2 + (i + 1) * self.LOOP_BRANCH_LEN / (loop.isolator_count + 1)
                msp.add_text(
                    "FI",
                    dxfattribs={
                        "layer": "RD-ISOLATORS",
                        "height": self.TEXT_HEIGHT * 0.7,
                        "insert": (ix, branch_y - 1.0),
                    },
                )
                msp.add_circle(
                    (ix + 0.2, branch_y - 0.8),
                    radius=0.15,
                    dxfattribs={"layer": "RD-ISOLATORS"},
                )

        # Floors served
        if loop.floors_served:
            floors_str = ", ".join(loop.floors_served)
            msp.add_text(
                f"Serves: {floors_str}",
                dxfattribs={
                    "layer": "RD-LABELS",
                    "height": self.TEXT_HEIGHT * 0.5,
                    "insert": (panel_x + self.PANEL_WIDTH / 2 + 0.2, branch_y - 1.2),
                },
            )

    def _draw_nac(
        self,
        msp: Any,
        panel_x: float,
        panel_y: float,
        nac_y: float,
        nac: RiserNACCircuit,
    ) -> None:
        """Draw a NAC circuit branch from a panel."""
        # Vertical line from panel to NAC level
        msp.add_line(
            (panel_x + self.PANEL_WIDTH / 2, panel_y, 0),
            (panel_x + self.PANEL_WIDTH / 2, nac_y, 0),
            dxfattribs={"layer": "RD-NAC"},
        )

        # Horizontal branch
        end_x = panel_x + self.PANEL_WIDTH / 2 + self.NAC_BRANCH_LEN
        msp.add_line(
            (panel_x + self.PANEL_WIDTH / 2, nac_y, 0),
            (end_x, nac_y, 0),
            dxfattribs={"layer": "RD-NAC"},
        )

        # NAC label
        msp.add_text(
            nac.nac_id,
            dxfattribs={
                "layer": "RD-LABELS",
                "height": self.TEXT_HEIGHT * 0.8,
                "insert": (panel_x + self.PANEL_WIDTH / 2 + 0.2, nac_y + 0.2),
            },
        )

        # Device info
        dev_str = ", ".join(nac.device_types[:3])  # max 3 types
        msp.add_text(
            f"{nac.device_count}x {dev_str}",
            dxfattribs={
                "layer": "RD-LABELS",
                "height": self.TEXT_HEIGHT * 0.6,
                "insert": (panel_x + self.PANEL_WIDTH / 2 + 0.2, nac_y - 0.3),
            },
        )

        # Cable type
        msp.add_text(
            f"Cable: {nac.cable_type}",
            dxfattribs={
                "layer": "RD-LABELS",
                "height": self.TEXT_HEIGHT * 0.5,
                "insert": (panel_x + self.PANEL_WIDTH / 2 + 0.2, nac_y - 0.7),
            },
        )

    def _draw_network_link(
        self,
        msp: Any,
        pos_a: Tuple[float, float],
        pos_b: Tuple[float, float],
        link: RiserNetworkLink,
    ) -> None:
        """Draw a network connection between two panels."""
        # Draw vertical dashed line between panels
        msp.add_line(
            (pos_a[0] - self.PANEL_WIDTH / 2, pos_a[1], 0),
            (pos_b[0] - self.PANEL_WIDTH / 2, pos_b[1], 0),
            dxfattribs={"layer": "RD-NETWORK"},
        )

        # Link label
        mid_y = (pos_a[1] + pos_b[1]) / 2
        msp.add_text(
            f"NET: {link.cable_type}",
            dxfattribs={
                "layer": "RD-LABELS",
                "height": self.TEXT_HEIGHT * 0.6,
                "insert": (pos_a[0] - self.PANEL_WIDTH / 2 - 2.0, mid_y),
            },
        )

    def _draw_title(self, msp: Any, spec: RiserDiagramSpec) -> None:
        """Draw title block."""
        tx = self.MARGIN_LEFT + 15.0
        ty = self.MARGIN_BOTTOM + len(spec.panels) * self.FLOOR_SPACING + 2.0

        msp.add_text(
            f"FIRE ALARM RISER DIAGRAM — {spec.project_name}",
            dxfattribs={
                "layer": "RD-TITLE",
                "height": self.TEXT_HEIGHT * 2.0,
                "insert": (tx, ty),
            },
        )

        msp.add_text(
            f"{spec.nfpa_version} | Survivability: {spec.survivability_level}",
            dxfattribs={
                "layer": "RD-TITLE",
                "height": self.TEXT_HEIGHT,
                "insert": (tx, ty - 1.0),
            },
        )

        msp.add_text(
            f"Panels: {len(spec.panels)} | Loops: {len(spec.loops)} | NAC: {len(spec.nac_circuits)}",
            dxfattribs={
                "layer": "RD-TITLE",
                "height": self.TEXT_HEIGHT * 0.8,
                "insert": (tx, ty - 2.0),
            },
        )
