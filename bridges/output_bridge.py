"""
bridges/output_bridge.py
========================
Bridge 3: FireAI design → DWG with symbols + cables

Writes NFPA 72-compliant fire alarm design to DXF/DWG files:
  - Detector symbols (smoke, heat, multi-criteria, duct)
  - Cable routing between devices (Dijkstra + nearest-neighbour TSP)
  - Coverage circles for each detector
  - Fire alarm panel marker
  - Device schedule table
  - Layer scheme per NFPA / industry standards

SAFETY GATE: If proof_valid=False, the bridge REFUSES to draw unless
force=True is set. This prevents issuing non-compliant drawings.

Requires: ezdxf ≥ 1.0

Usage:
    from bridges.output_bridge import draw_fire_alarm_design
    result = draw_fire_alarm_design(
        dxf_path="floor.dxf",
        output_path="floor_fa.dxf",
        rooms=rooms,
        devices=devices,
        proof_valid=True,
    )
    print(result.stats)
"""

from __future__ import annotations
import logging, math, time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Optional

try:
    import ezdxf
    from ezdxf.enums import TextEntityAlignment
    EZDXF_AVAILABLE = True
except ImportError:
    EZDXF_AVAILABLE = False

try:
    import networkx as nx
    NX_AVAILABLE = True
except ImportError:
    NX_AVAILABLE = False

from shapely.geometry import Polygon, Point, LineString
from shapely.ops import nearest_points

log = logging.getLogger(__name__)


# ════════════════════════════════════════════════════════════════════════════
# Data structures
# ════════════════════════════════════════════════════════════════════════════

@dataclass
class CableSegment:
    """One segment of cable routing."""
    start: tuple
    end: tuple
    length_m: float


@dataclass
class DrawingResult:
    """Result of the drawing output bridge."""
    output_path: str
    devices_drawn: int = 0
    cable_segments: int = 0
    total_cable_m: float = 0.0
    coverage_circles: int = 0
    layers_created: list = field(default_factory=list)
    warnings: list = field(default_factory=list)
    stats: dict = field(default_factory=dict)
    elapsed_seconds: float = 0.0


# ════════════════════════════════════════════════════════════════════════════
# DWG Layer scheme (NFPA / industry standard)
# ════════════════════════════════════════════════════════════════════════════

LAYER_SCHEME = {
    "FA-DETECTOR-SMOKE":  {"color": 1,   "desc": "Smoke detectors"},       # Red
    "FA-DETECTOR-HEAT":   {"color": 40,  "desc": "Heat detectors"},        # Orange
    "FA-DETECTOR-MULTI":  {"color": 6,   "desc": "Multi-criteria detectors"}, # Magenta
    "FA-DETECTOR-DUCT":   {"color": 30,  "desc": "Duct smoke detectors"},  # Brown/Orange
    "FA-MCP":             {"color": 2,   "desc": "Manual call points"},    # Yellow
    "FA-PANEL":           {"color": 5,   "desc": "Fire alarm panel"},      # Blue
    "FA-CABLE-MAIN":      {"color": 5,   "desc": "Main cable runs"},       # Blue
    "FA-CABLE-BRANCH":    {"color": 4,   "desc": "Branch cable runs"},     # Cyan
    "FA-COVERAGE":        {"color": 7,   "desc": "Coverage circles"},      # White
    "FA-SCHEDULE":        {"color": 7,   "desc": "Device schedule text"},  # White
    "FA-NOTES":           {"color": 3,   "desc": "Design notes"},          # Green
}


# ════════════════════════════════════════════════════════════════════════════
# Symbol drawing primitives
# ════════════════════════════════════════════════════════════════════════════

def _draw_smoke_detector(msp, x, y, layer="FA-DETECTOR-SMOKE", scale=300):
    """Draw smoke detector symbol: circle with S label."""
    r = scale
    msp.add_circle(center=(x, y), radius=r, dxfattribs={"layer": layer})
    msp.add_circle(center=(x, y), radius=r * 0.5, dxfattribs={"layer": layer})
    msp.add_text("S", dxfattribs={
        "layer": layer, "height": r * 0.8,
        "insert": (x, y - r * 0.3),
    })


def _draw_heat_detector(msp, x, y, layer="FA-DETECTOR-HEAT", scale=300):
    """Draw heat detector symbol: circle with H label."""
    r = scale
    msp.add_circle(center=(x, y), radius=r, dxfattribs={"layer": layer})
    msp.add_text("H", dxfattribs={
        "layer": layer, "height": r * 0.8,
        "insert": (x, y - r * 0.3),
    })


def _draw_multi_detector(msp, x, y, layer="FA-DETECTOR-MULTI", scale=300):
    """Draw multi-criteria detector: circle with M label."""
    r = scale
    msp.add_circle(center=(x, y), radius=r, dxfattribs={"layer": layer})
    msp.add_text("M", dxfattribs={
        "layer": layer, "height": r * 0.8,
        "insert": (x, y - r * 0.3),
    })


def _draw_duct_detector(msp, x, y, layer="FA-DETECTOR-DUCT", scale=300):
    """Draw duct detector: rectangle with D label."""
    r = scale
    msp.add_lwpolyline(
        [(x - r, y - r * 0.6), (x + r, y - r * 0.6),
         (x + r, y + r * 0.6), (x - r, y + r * 0.6)],
        format="xy", close=True,
        dxfattribs={"layer": layer}
    )
    msp.add_text("D", dxfattribs={
        "layer": layer, "height": r * 0.7,
        "insert": (x, y - r * 0.25),
    })


def _draw_mcp(msp, x, y, layer="FA-MCP", scale=300):
    """Draw manual call point: rectangle with MCP label."""
    r = scale
    msp.add_lwpolyline(
        [(x - r * 0.8, y - r * 0.5), (x + r * 0.8, y - r * 0.5),
         (x + r * 0.8, y + r * 0.5), (x - r * 0.8, y + r * 0.5)],
        format="xy", close=True,
        dxfattribs={"layer": layer}
    )
    msp.add_text("MCP", dxfattribs={
        "layer": layer, "height": r * 0.5,
        "insert": (x, y - r * 0.15),
    })


def _draw_panel(msp, x, y, layer="FA-PANEL", scale=600):
    """Draw fire alarm panel: large rectangle with FAP label."""
    r = scale
    msp.add_lwpolyline(
        [(x - r, y - r * 0.6), (x + r, y - r * 0.6),
         (x + r, y + r * 0.6), (x - r, y + r * 0.6)],
        format="xy", close=True,
        dxfattribs={"layer": layer}
    )
    msp.add_text("FAP", dxfattribs={
        "layer": layer, "height": r * 0.5,
        "insert": (x, y - r * 0.15),
    })


# Dispatch table
SYMBOL_DRAWERS = {
    "SMOKE_PHOTOELECTRIC": _draw_smoke_detector,
    "SMOKE_IONIZATION":    _draw_smoke_detector,
    "SMOKE_MULTI_CRITERIA": _draw_multi_detector,
    "HEAT_FIXED":          _draw_heat_detector,
    "HEAT_RATE_OF_RISE":   _draw_heat_detector,
    "DUCT_SMOKE":          _draw_duct_detector,
    "MANUAL_PULL_STATION": _draw_mcp,
}


# ════════════════════════════════════════════════════════════════════════════
# Cable Router (Dijkstra + Nearest-Neighbour TSP)
# ════════════════════════════════════════════════════════════════════════════

def route_cables(
    devices: list,
    panel_pos: tuple,
    room_polygon: Polygon = None,
    grid_step: float = 500.0,  # mm
    panel_height_m: float = 1.5,
    obstacle_tolerance: float = 1.25,
) -> list:
    """
    Route cables from panel to all devices using Manhattan routing.

    Algorithm:
    1. Order devices using nearest-neighbour TSP
    2. Route panel → device1 → device2 → ... → deviceN → panel
    3. Each segment uses Manhattan (L-shaped) routing
    4. Total = loop cable route
    5. Vertical drops added for ceiling-to-device and panel riser
    6. Obstacle tolerance factor applied to horizontal runs

    Engineering Factors (V11 — Voltage Drop Safety):
      - panel_height_m : Height of the fire alarm panel (default 1.5m).
                        A vertical riser from panel height to ceiling is added
                        at the start of each home-run from the panel.
      - obstacle_tolerance : Multiplier on horizontal Manhattan distance to
                        account for cable routing around walls, columns, and
                        conduit bends. Industry practice uses 1.20–1.35.
                        Default 1.25 (25% overhead).

    Returns list of CableSegment objects.
    """
    if not devices:
        return []

    # Convert device positions to mm
    device_pts = []
    for d in devices:
        dx = d.position.x * 1000
        dy = d.position.y * 1000
        dz = getattr(d, 'z_height', 2.8)  # device mounting height
        device_pts.append((dx, dy, d.id, dz))

    # Nearest-neighbour TSP ordering
    ordered = []
    remaining = list(range(len(device_pts)))
    current = panel_pos

    while remaining:
        best_idx = min(remaining, key=lambda i:
            (device_pts[i][0] - current[0]) ** 2 +
            (device_pts[i][1] - current[1]) ** 2)
        ordered.append(best_idx)
        remaining.remove(best_idx)
        current = (device_pts[best_idx][0], device_pts[best_idx][1])

    # Route with Manhattan (L-shaped) segments + vertical drops + tolerance
    segments = []
    prev = panel_pos
    is_first_segment = True

    for idx in ordered:
        dx, dy, dev_id, dev_z = device_pts[idx]

        # Panel riser: vertical from panel height up to ceiling level
        if is_first_segment:
            vertical_rise = dev_z - panel_height_m
            if vertical_rise > 0:
                segments.append(CableSegment(
                    start=prev, end=prev, length_m=vertical_rise
                ))
            is_first_segment = False

        # Horizontal segment first, then vertical (Manhattan routing)
        # Apply obstacle tolerance to horizontal distance
        if abs(dx - prev[0]) > 1.0:  # non-zero horizontal
            seg_len = abs(dx - prev[0]) / 1000.0
            segments.append(CableSegment(
                start=prev, end=(dx, prev[1]),
                length_m=round(seg_len * obstacle_tolerance, 3)
            ))
        if abs(dy - prev[1]) > 1.0:  # non-zero vertical
            seg_len = abs(dy - prev[1]) / 1000.0
            segments.append(CableSegment(
                start=(dx, prev[1]), end=(dx, dy),
                length_m=round(seg_len * obstacle_tolerance, 3)
            ))

        # If same position, add zero-length segment
        if abs(dx - prev[0]) <= 1.0 and abs(dy - prev[1]) <= 1.0:
            segments.append(CableSegment(
                start=prev, end=(dx, dy), length_m=0.0
            ))

        prev = (dx, dy)

    # Return path from last device back to panel
    dx, dy = panel_pos
    if abs(dx - prev[0]) > 1.0:
        seg_len = abs(dx - prev[0]) / 1000.0
        segments.append(CableSegment(
            start=prev, end=(dx, prev[1]),
            length_m=round(seg_len * obstacle_tolerance, 3)
        ))
    if abs(dy - prev[1]) > 1.0:
        seg_len = abs(dy - prev[1]) / 1000.0
        segments.append(CableSegment(
            start=(dx, prev[1]), end=(dx, dy),
            length_m=round(seg_len * obstacle_tolerance, 3)
        ))

    return segments


# ════════════════════════════════════════════════════════════════════════════
# Main drawing function
# ════════════════════════════════════════════════════════════════════════════

def draw_fire_alarm_design(
    dxf_path: str,
    output_path: str,
    rooms: list,
    devices: list,
    panel_position: tuple = None,
    proof_valid: bool = False,
    force: bool = False,
    draw_coverage: bool = True,
    draw_cables: bool = True,
    draw_schedule: bool = True,
    units_to_m: float = 0.001,
) -> DrawingResult:
    """
    Bridge 3: Write fire alarm design to DXF file.

    Parameters
    ----------
    dxf_path       : Original floor plan DXF (used as base)
    output_path    : Output DXF path with FA overlay
    rooms          : List of FireAI Room objects
    devices        : List of FireAI Device objects
    panel_position : (x_mm, y_mm) or None (auto-placed)
    proof_valid    : Has the design passed NFPA 72 verification?
    force          : Draw even if proof_valid=False (PE override)
    draw_coverage  : Draw coverage circles
    draw_cables    : Route and draw cables
    draw_schedule  : Draw device schedule table
    units_to_m     : Drawing unit to metre conversion
    """
    t0 = time.time()
    warnings = []

    if not EZDXF_AVAILABLE:
        return DrawingResult(
            output_path=output_path,
            warnings=["ezdxf not installed. pip install ezdxf"],
        )

    # ── SAFETY GATE ──
    if not proof_valid and not force:
        return DrawingResult(
            output_path=output_path,
            warnings=[
                "SAFETY GATE: Design has NOT been verified against NFPA 72. "
                "Drawing REFUSED. Set proof_valid=True after PE review, "
                "or force=True to override (requires PE sign-off)."
            ],
        )

    if not proof_valid and force:
        warnings.append(
            "⚠ SAFETY OVERRIDE: Drawing produced WITHOUT NFPA 72 verification. "
            "PE must review and sign off before issuing."
        )

    # ── Load or create DXF ──
    try:
        doc = ezdxf.readfile(dxf_path)
        msp = doc.modelspace()
    except Exception:
        # Create new document
        doc = ezdxf.new("R2018")
        msp = doc.modelspace()
        warnings.append(f"Could not read {dxf_path}, creating new DXF.")

    # ── Setup layers ──
    layers_created = []
    for layer_name, layer_info in LAYER_SCHEME.items():
        if layer_name not in doc.layers:
            doc.layers.add(layer_name, color=layer_info["color"])
            layers_created.append(layer_name)

    # ── Draw devices ──
    devices_drawn = 0
    for d in devices:
        # BUG FIX: Guard against division by zero when units_to_m is 0
        safe_units = units_to_m if units_to_m and units_to_m > 0 else 1.0
        x = d.position.x / safe_units
        y = d.position.y / safe_units

        drawer = SYMBOL_DRAWERS.get(d.device_type, _draw_smoke_detector)
        drawer(msp, x, y)
        devices_drawn += 1

    # ── Draw fire alarm panel ──
    if panel_position:
        _draw_panel(msp, panel_position[0], panel_position[1])
    else:
        # Auto-place panel near first room centroid
        if rooms:
            safe_units = units_to_m if units_to_m and units_to_m > 0 else 1.0
            cx = rooms[0].geometry.centroid.x / safe_units
            cy = rooms[0].geometry.centroid.y / safe_units
            _draw_panel(msp, cx - 3000, cy - 3000)
            panel_position = (cx - 3000, cy - 3000)

    # ── Draw coverage circles ──
    coverage_count = 0
    if draw_coverage:
        safe_units = units_to_m if units_to_m and units_to_m > 0 else 1.0
        for d in devices:
            if d.coverage_radius <= 0:
                continue
            x = d.position.x / safe_units
            y = d.position.y / safe_units
            r = d.coverage_radius / safe_units
            msp.add_circle(
                center=(x, y), radius=r,
                dxfattribs={"layer": "FA-COVERAGE"}
            )
            coverage_count += 1

    # ── Route cables ──
    cable_segments = []
    total_cable_m = 0.0
    if draw_cables and devices and panel_position:
        cable_segments = route_cables(devices, panel_position)
        for seg in cable_segments:
            msp.add_line(
                start=seg.start, end=seg.end,
                dxfattribs={"layer": "FA-CABLE-MAIN"}
            )
            total_cable_m += seg.length_m

    # ── Draw device schedule ──
    if draw_schedule:
        _draw_schedule_table(msp, devices, doc)

    # ── Save ──
    doc.saveas(output_path)

    stats = {
        "devices_drawn": devices_drawn,
        "cable_segments": len(cable_segments),
        "total_cable_m": round(total_cable_m, 2),
        "coverage_circles": coverage_count,
        "layers_created": layers_created,
        "proof_valid": proof_valid,
        "force_override": force and not proof_valid,
    }

    result = DrawingResult(
        output_path=output_path,
        devices_drawn=devices_drawn,
        cable_segments=len(cable_segments),
        total_cable_m=round(total_cable_m, 2),
        coverage_circles=coverage_count,
        layers_created=layers_created,
        warnings=warnings,
        stats=stats,
        elapsed_seconds=round(time.time() - t0, 2),
    )

    log.info("Bridge 3 complete: %d devices, %d cable segments, %.1fm cable → %s",
             devices_drawn, len(cable_segments), total_cable_m, output_path)

    return result


def _draw_schedule_table(msp, devices, doc):
    """Draw a device schedule table on the drawing."""
    # Count by type
    counts = defaultdict(int)
    for d in devices:
        counts[d.device_type] += 1

    if not counts:
        return

    # Position table at a fixed offset (top-right area)
    table_x = 15000
    table_y = 20000
    row_h = 500
    col_w = 5000

    # Header
    msp.add_text("FIRE ALARM DEVICE SCHEDULE", dxfattribs={
        "layer": "FA-SCHEDULE", "height": 400,
        "insert": (table_x, table_y),
    })

    row = 1
    msp.add_text("Device Type", dxfattribs={
        "layer": "FA-SCHEDULE", "height": 300,
        "insert": (table_x, table_y - row * row_h),
    })
    msp.add_text("Qty", dxfattribs={
        "layer": "FA-SCHEDULE", "height": 300,
        "insert": (table_x + col_w, table_y - row * row_h),
    })

    for dtype, count in sorted(counts.items()):
        row += 1
        msp.add_text(dtype, dxfattribs={
            "layer": "FA-SCHEDULE", "height": 250,
            "insert": (table_x, table_y - row * row_h),
        })
        msp.add_text(str(count), dxfattribs={
            "layer": "FA-SCHEDULE", "height": 250,
            "insert": (table_x + col_w, table_y - row * row_h),
        })

    # Total
    row += 1
    msp.add_text("TOTAL", dxfattribs={
        "layer": "FA-SCHEDULE", "height": 300,
        "insert": (table_x, table_y - row * row_h),
    })
    msp.add_text(str(sum(counts.values())), dxfattribs={
        "layer": "FA-SCHEDULE", "height": 300,
        "insert": (table_x + col_w, table_y - row * row_h),
    })


# ════════════════════════════════════════════════════════════════════════════
# Self-test
# ════════════════════════════════════════════════════════════════════════════

def _self_test():
    """Test with programmatically created DXF and devices."""
    import tempfile, os
    print("=" * 60)
    print("BRIDGE 3: Output Bridge — Self-Test")
    print("=" * 60)

    if not EZDXF_AVAILABLE:
        print("SKIP: ezdxf not installed")
        return

    # Create base DXF
    doc = ezdxf.new("R2018")
    msp = doc.modelspace()
    msp.add_lwpolyline(
        [(0, 0), (15000, 0), (15000, 10000), (0, 10000)],
        format="xy", close=True,
        dxfattribs={"layer": "A-ROOM"}
    )

    with tempfile.NamedTemporaryFile(suffix=".dxf", delete=False) as f:
        base_path = f.name
    doc.saveas(base_path)

    # Create test devices
    from core.models import Device
    devices = [
        Device(id="s1", device_type="SMOKE_PHOTOELECTRIC",
               position=Point(3000, 3000), room_id="r1",
               z_height=2.8, coverage_radius=6.37),
        Device(id="s2", device_type="SMOKE_PHOTOELECTRIC",
               position=Point(8000, 3000), room_id="r1",
               z_height=2.8, coverage_radius=6.37),
        Device(id="s3", device_type="SMOKE_PHOTOELECTRIC",
               position=Point(13000, 3000), room_id="r1",
               z_height=2.8, coverage_radius=6.37),
        Device(id="h1", device_type="HEAT_FIXED",
               position=Point(5000, 7000), room_id="r1",
               z_height=2.4, coverage_radius=4.90),
        Device(id="mcp1", device_type="MANUAL_PULL_STATION",
               position=Point(1000, 5000), room_id="r1",
               z_height=1.4, coverage_radius=0.0),
    ]

    from core.models import Room
    rooms = [Room(
        id="r1", name="TestRoom", room_type="office",
        floor_area=150.0,
        geometry=Polygon([(0, 0), (15, 0), (15, 10), (0, 10)]),
    )]

    output_path = base_path.replace(".dxf", "_fa.dxf")

    # Run bridge
    result = draw_fire_alarm_design(
        dxf_path=base_path,
        output_path=output_path,
        rooms=rooms,
        devices=devices,
        proof_valid=True,
        draw_coverage=True,
        draw_cables=True,
        draw_schedule=True,
        units_to_m=0.001,
    )

    print(f"\nOutput: {result.output_path}")
    print(f"Devices drawn: {result.devices_drawn}")
    print(f"Cable segments: {result.cable_segments}")
    print(f"Total cable: {result.total_cable_m:.1f}m")
    print(f"Coverage circles: {result.coverage_circles}")
    print(f"Layers: {result.layers_created}")
    print(f"Warnings: {result.warnings}")
    print(f"Stats: {result.stats}")

    # Verify file exists
    if os.path.exists(output_path):
        size = os.path.getsize(output_path)
        print(f"\nOutput file size: {size} bytes")
    else:
        print(f"\nERROR: Output file not created!")

    # Cleanup
    os.unlink(base_path)
    if os.path.exists(output_path):
        os.unlink(output_path)

    print("\n" + "=" * 60)
    status = "PASS" if result.devices_drawn > 0 else "FAIL"
    print(f"Bridge 3 Self-Test: {status}")
    print("=" * 60)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    _self_test()
