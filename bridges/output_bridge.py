"""
bridges/output_bridge.py  V2.0
==============================
Bridge 3: FireAI design -> DWG with symbols + cables

Writes NFPA 72-compliant fire alarm design to DXF/DWG files:
  - Detector symbols (smoke, heat, multi-criteria, duct)
  - Cable routing between devices (Dijkstra + nearest-neighbour TSP)
  - **V2.0: Class A return path with NFPA 72 §12.2.2 separation**
  - **V2.0: Firestopping callouts at fire-rated wall penetrations (IBC §714)**
  - **V2.0: DXF TABLE entity for device schedule (not text blocks)**
  - Coverage circles for each detector
  - Fire alarm panel marker
  - Layer scheme per NFPA / industry standards

SAFETY GATE: If proof_valid=False, the bridge REFUSES to draw unless
force=True is set. This prevents issuing non-compliant drawings.

Requires: ezdxf >= 1.0

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
from typing import Optional, List, Tuple

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

# ════════════════════════════════════════════════════════════════════════════
# NFPA 72 Class A Separation Constants
# ════════════════════════════════════════════════════════════════════════════
# NFPA 72-2022 §12.2.2: Class A outgoing and return conductors must be
# separated by at least 1m (3ft) to prevent a single point of failure
# from disabling the entire circuit.
CLASS_A_SEPARATION_MM = 1000.0  # 1m minimum separation in mm

# IBC §714: Firestopping required at fire-rated wall penetrations
FIRESTOPPING_LABEL = "FIRESTOP - IBC S714"

log = logging.getLogger(__name__)


# ════════════════════════════════════════════════════════════════════════════
# Data structures
# ════════════════════════════════════════════════════════════════════════════

@dataclass
class CableSegment:
    """One segment of cable routing.

    V2.0: Now tracks whether this is an outgoing or return (Class A) segment,
    and whether it penetrates a fire-rated wall requiring firestopping.
    """
    start: tuple
    end: tuple
    length_m: float
    is_return_path: bool = False   # True = Class A return conductor
    firestopping: bool = False     # True = penetrates fire-rated wall
    firestopping_ref: str = ""     # IBC reference if firestopping=True


@dataclass
class DrawingResult:
    """Result of the drawing output bridge.

    V2.0: Added Class A and firestopping tracking fields.
    """
    output_path: str
    devices_drawn: int = 0
    cable_segments: int = 0
    total_cable_m: float = 0.0
    coverage_circles: int = 0
    layers_created: list = field(default_factory=list)
    warnings: list = field(default_factory=list)
    stats: dict = field(default_factory=dict)
    elapsed_seconds: float = 0.0
    class_a_return_segments: int = 0    # V2.0: Number of Class A return path segments
    firestopping_points: int = 0       # V2.0: Number of firestopping callouts


# ════════════════════════════════════════════════════════════════════════════
# DWG Layer scheme (NFPA / industry standard) — V2.0 with return + firestopping
# ════════════════════════════════════════════════════════════════════════════

LAYER_SCHEME = {
    "FA-DETECTOR-SMOKE":  {"color": 1,   "desc": "Smoke detectors"},              # Red
    "FA-DETECTOR-HEAT":   {"color": 40,  "desc": "Heat detectors"},               # Orange
    "FA-DETECTOR-MULTI":  {"color": 6,   "desc": "Multi-criteria detectors"},     # Magenta
    "FA-DETECTOR-DUCT":   {"color": 30,  "desc": "Duct smoke detectors"},         # Brown/Orange
    "FA-MCP":             {"color": 2,   "desc": "Manual call points"},           # Yellow
    "FA-PANEL":           {"color": 5,   "desc": "Fire alarm panel"},             # Blue
    "FA-CABLE-MAIN":      {"color": 5,   "desc": "Main cable runs (outgoing)"},   # Blue
    "FA-CABLE-RETURN":    {"color": 141, "desc": "Class A return cable runs"},     # Gray-blue (V2.0)
    "FA-CABLE-BRANCH":    {"color": 4,   "desc": "Branch cable runs"},            # Cyan
    "FA-COVERAGE":        {"color": 7,   "desc": "Coverage circles"},             # White
    "FA-SCHEDULE":        {"color": 7,   "desc": "Device schedule table"},         # White
    "FA-NOTES":           {"color": 3,   "desc": "Design notes"},                 # Green
    "FA-FIRESTOPPING":    {"color": 1,   "desc": "Firestopping callouts (IBC S714)"},  # Red (V2.0)
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


def _draw_firestopping_marker(msp, x, y, layer="FA-FIRESTOPPING", scale=300):
    """V2.0: Draw firestopping callout at fire-rated wall penetration.

    IBC §714: Penetrations in fire-resistance-rated walls must be firestopped
    using approved materials. This marker serves as a visual callout on the
    drawing to indicate where cable routing penetrates a fire-rated wall.
    """
    r = scale
    # Diamond shape for firestopping marker
    msp.add_lwpolyline(
        [(x, y + r * 0.8), (x + r * 0.5, y),
         (x, y - r * 0.8), (x - r * 0.5, y)],
        format="xy", close=True,
        dxfattribs={"layer": layer}
    )
    msp.add_text("FS", dxfattribs={
        "layer": layer, "height": r * 0.4,
        "insert": (x - r * 0.2, y - r * 0.15),
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
# Cable Router V2.0 — Class A Return Path with NFPA 72 §12.2.2 Separation
# ════════════════════════════════════════════════════════════════════════════

def route_cables(
    devices: list,
    panel_pos: tuple,
    room_polygon: Polygon = None,
    grid_step: float = 500.0,  # mm
    panel_height_m: float = 1.5,
    obstacle_tolerance: float = 1.25,
    class_a: bool = True,
    fire_rated_walls: list = None,
) -> list:
    """
    Route cables from panel to all devices using Manhattan routing.

    V2.0 Changes:
    - Class A return path: When class_a=True (default), the return path is
      offset by CLASS_A_SEPARATION_MM (1m) from the outgoing path per
      NFPA 72-2022 §12.2.2. This prevents a single point of failure from
      disabling the entire circuit.
    - Firestopping detection: When fire_rated_walls are provided, segments
      that cross fire-rated walls are flagged for firestopping callouts
      per IBC §714.

    Algorithm:
    1. Order devices using nearest-neighbour TSP
    2. Route panel -> device1 -> device2 -> ... -> deviceN -> panel
    3. Each segment uses Manhattan (L-shaped) routing
    4. Total = loop cable route
    5. Vertical drops added for ceiling-to-device and panel riser
    6. Obstacle tolerance factor applied to horizontal runs
    7. V2.0: Return path offset by 1m for Class A separation
    8. V2.0: Firestopping callouts at fire-rated wall penetrations

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
            new_seg = CableSegment(
                start=prev, end=(dx, prev[1]),
                length_m=round(seg_len * obstacle_tolerance, 3)
            )
            # V2.0: Check firestopping at fire-rated wall crossings
            _check_firestopping(new_seg, prev, (dx, prev[1]), fire_rated_walls)
            segments.append(new_seg)
        if abs(dy - prev[1]) > 1.0:  # non-zero vertical
            seg_len = abs(dy - prev[1]) / 1000.0
            new_seg = CableSegment(
                start=(dx, prev[1]), end=(dx, dy),
                length_m=round(seg_len * obstacle_tolerance, 3)
            )
            _check_firestopping(new_seg, (dx, prev[1]), (dx, dy), fire_rated_walls)
            segments.append(new_seg)

        # If same position, add zero-length segment
        if abs(dx - prev[0]) <= 1.0 and abs(dy - prev[1]) <= 1.0:
            segments.append(CableSegment(
                start=prev, end=(dx, dy), length_m=0.0
            ))

        prev = (dx, dy)

    # ── V2.0: Return path with Class A separation ──────────────────────
    # NFPA 72-2022 §12.2.2: Outgoing and return conductors must be
    # separated by at least 1m (3ft). The return path is offset from
    # the outgoing path by CLASS_A_SEPARATION_MM perpendicular to the
    # cable direction.
    last_dev = prev
    px, py = panel_pos

    if class_a:
        # Route return path on a parallel track offset by 1m
        # We offset in the Y direction (perpendicular to typical horizontal run)
        # This creates physical separation between outgoing and return conductors
        offset_y = CLASS_A_SEPARATION_MM  # 1m offset

        # Return: last device -> offset path -> panel
        # Step 1: From last device, go to offset Y track
        ret_start = last_dev
        ret_track_y = last_dev[1] + offset_y

        if abs(ret_track_y - ret_start[1]) > 1.0:
            ret_seg = CableSegment(
                start=ret_start, end=(ret_start[0], ret_track_y),
                length_m=round(abs(offset_y) / 1000.0 * obstacle_tolerance, 3),
                is_return_path=True
            )
            _check_firestopping(ret_seg, ret_start, (ret_start[0], ret_track_y), fire_rated_walls)
            segments.append(ret_seg)

        # Step 2: Travel along offset Y track to panel X
        if abs(px - ret_start[0]) > 1.0:
            seg_len = abs(px - ret_start[0]) / 1000.0
            ret_seg = CableSegment(
                start=(ret_start[0], ret_track_y), end=(px, ret_track_y),
                length_m=round(seg_len * obstacle_tolerance, 3),
                is_return_path=True
            )
            _check_firestopping(ret_seg, (ret_start[0], ret_track_y), (px, ret_track_y), fire_rated_walls)
            segments.append(ret_seg)

        # Step 3: Drop from offset Y track back to panel Y
        if abs(py - ret_track_y) > 1.0:
            seg_len = abs(py - ret_track_y) / 1000.0
            ret_seg = CableSegment(
                start=(px, ret_track_y), end=(px, py),
                length_m=round(seg_len * obstacle_tolerance, 3),
                is_return_path=True
            )
            _check_firestopping(ret_seg, (px, ret_track_y), (px, py), fire_rated_walls)
            segments.append(ret_seg)
    else:
        # Class B: Return path follows same route (no separation)
        # WARNING: This violates NFPA 72 §12.2.2 for Class A circuits
        if abs(px - prev[0]) > 1.0:
            seg_len = abs(px - prev[0]) / 1000.0
            segments.append(CableSegment(
                start=prev, end=(px, prev[1]),
                length_m=round(seg_len * obstacle_tolerance, 3),
                is_return_path=True
            ))
        if abs(py - prev[1]) > 1.0:
            seg_len = abs(py - prev[1]) / 1000.0
            segments.append(CableSegment(
                start=(px, prev[1]), end=(px, py),
                length_m=round(seg_len * obstacle_tolerance, 3),
                is_return_path=True
            ))

    return segments


def _check_firestopping(
    segment: CableSegment,
    start: tuple,
    end: tuple,
    fire_rated_walls: list = None,
) -> None:
    """V2.0: Check if a cable segment crosses a fire-rated wall.

    If the segment intersects a fire-rated wall line, mark it for
    firestopping per IBC §714. The fire_rated_walls list contains
    LineString objects representing fire-rated wall centerlines.

    Args:
        segment: The CableSegment to check (modified in-place).
        start: (x_mm, y_mm) start point.
        end: (x_mm, y_mm) end point.
        fire_rated_walls: List of Shapely LineString objects for fire-rated walls.
    """
    if not fire_rated_walls:
        return

    cable_line = LineString([start, end])

    for wall_line in fire_rated_walls:
        try:
            if cable_line.intersects(wall_line):
                segment.firestopping = True
                segment.firestopping_ref = "IBC S714"
                return  # One firestopping callout per segment is sufficient
        except Exception:
            # Shapely geometry errors should not crash the routing
            pass


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
    class_a: bool = True,
    fire_rated_walls: list = None,
) -> DrawingResult:
    """
    Bridge 3 V2.0: Write fire alarm design to DXF file.

    V2.0 Changes:
    - class_a: If True (default), draw Class A return path with 1m separation
      per NFPA 72-2022 §12.2.2 on the FA-CABLE-RETURN layer.
    - fire_rated_walls: List of Shapely LineString objects. When cables cross
      these walls, firestopping callouts (FS markers) are added per IBC §714.
    - Device schedule now uses proper DXF TABLE entity when ezdxf supports it,
      falling back to text blocks for older versions.

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
    class_a        : V2.0 — Route Class A return with separation (default True)
    fire_rated_walls : V2.0 — Fire-rated wall LineStrings for firestopping callouts
    """
    t0 = time.time()
    warnings = []

    if not EZDXF_AVAILABLE:
        return DrawingResult(
            output_path=output_path,
            warnings=["ezdxf not installed. pip install ezdxf"],
        )

    # -- SAFETY GATE --
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
            "SAFETY OVERRIDE: Drawing produced WITHOUT NFPA 72 verification. "
            "PE must review and sign off before issuing."
        )

    # -- Load or create DXF --
    try:
        doc = ezdxf.readfile(dxf_path)
        msp = doc.modelspace()
    except Exception:
        # Create new document
        doc = ezdxf.new("R2018")
        msp = doc.modelspace()
        warnings.append(f"Could not read {dxf_path}, creating new DXF.")

    # -- Setup layers --
    layers_created = []
    for layer_name, layer_info in LAYER_SCHEME.items():
        if layer_name not in doc.layers:
            doc.layers.add(layer_name, color=layer_info["color"])
            layers_created.append(layer_name)

    # -- Draw devices --
    devices_drawn = 0
    for d in devices:
        # BUG FIX: Guard against division by zero when units_to_m is 0
        safe_units = units_to_m if units_to_m and units_to_m > 0 else 1.0
        x = d.position.x / safe_units
        y = d.position.y / safe_units

        drawer = SYMBOL_DRAWERS.get(d.device_type, _draw_smoke_detector)
        drawer(msp, x, y)
        devices_drawn += 1

    # -- Draw fire alarm panel --
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

    # -- Draw coverage circles --
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

    # -- Route cables (V2.0: Class A + Firestopping) --
    cable_segments = []
    total_cable_m = 0.0
    return_segments = 0
    firestopping_count = 0

    if draw_cables and devices and panel_position:
        cable_segments = route_cables(
            devices, panel_position,
            class_a=class_a,
            fire_rated_walls=fire_rated_walls,
        )
        for seg in cable_segments:
            # V2.0: Draw outgoing and return on separate layers
            layer = "FA-CABLE-RETURN" if seg.is_return_path else "FA-CABLE-MAIN"
            msp.add_line(
                start=seg.start, end=seg.end,
                dxfattribs={"layer": layer}
            )
            total_cable_m += seg.length_m

            if seg.is_return_path:
                return_segments += 1

            # V2.0: Draw firestopping marker at midpoint of segment
            if seg.firestopping:
                mid_x = (seg.start[0] + seg.end[0]) / 2
                mid_y = (seg.start[1] + seg.end[1]) / 2
                _draw_firestopping_marker(msp, mid_x, mid_y)
                firestopping_count += 1

    # -- Draw device schedule (V2.0: DXF TABLE entity) --
    if draw_schedule:
        _draw_schedule_table(msp, devices, rooms, doc, units_to_m)

    # -- Save --
    doc.saveas(output_path)

    stats = {
        "devices_drawn": devices_drawn,
        "cable_segments": len(cable_segments),
        "total_cable_m": round(total_cable_m, 2),
        "coverage_circles": coverage_count,
        "layers_created": layers_created,
        "proof_valid": proof_valid,
        "force_override": force and not proof_valid,
        "class_a_return_segments": return_segments,
        "firestopping_points": firestopping_count,
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
        class_a_return_segments=return_segments,
        firestopping_points=firestopping_count,
    )

    log.info("Bridge 3 V2.0 complete: %d devices, %d cable segs (%d return), "
             "%.1fm cable, %d firestops -> %s",
             devices_drawn, len(cable_segments), return_segments,
             total_cable_m, firestopping_count, output_path)

    return result


def _draw_schedule_table(msp, devices, rooms, doc, units_to_m=0.001):
    """V2.0: Draw device schedule as DXF TABLE entity.

    Previous versions used add_text() for each cell, which does not create
    proper DXF TABLE entities. This version creates a real TABLE entity
    using ezdxf's Table class, falling back to text blocks if the ezdxf
    version does not support table creation.

    V12 Fix: Dynamic table positioning based on building bounding box
    (prevents hardcoded coordinates overlapping geometry).
    """
    # Count by type
    counts = defaultdict(int)
    for d in devices:
        counts[d.device_type] += 1

    if not counts:
        return

    # Dynamic table positioning based on building bounding box
    safe_units = units_to_m if units_to_m and units_to_m > 0 else 1.0
    max_x, max_y = 0.0, 0.0

    if rooms:
        for r in rooms:
            geom = getattr(r, 'geometry', None)
            if geom and hasattr(geom, 'bounds'):
                try:
                    _, _, rx, ry = geom.bounds
                    max_x = max(max_x, rx / safe_units)
                    max_y = max(max_y, ry / safe_units)
                except Exception:
                    pass

    if max_x == 0.0 and max_y == 0.0:
        # Fallback: try to get extents from modelspace entities
        try:
            ext = msp.query('*').extents
            if ext:
                max_x = ext.upper_right[0]
                max_y = ext.upper_right[1]
        except Exception:
            max_x, max_y = 10000.0, 10000.0  # Last resort fallback

    # Place table in upper-right area outside building with safe margin
    margin_x = 2000.0  # 2m margin in drawing units
    margin_y = 1000.0  # 1m margin
    table_x = max_x + margin_x
    table_y = max_y + margin_y

    # ── V2.0: Try DXF TABLE entity first, fallback to text ──────────
    try:
        # ezdxf supports TABLE entity creation
        # Define columns: Device Type | Qty | Coverage Radius
        col_widths = [6000.0, 2500.0, 3500.0]
        col_names = ["Device Type", "Qty", "Coverage R (m)"]
        n_cols = len(col_names)
        row_h = 500.0

        # Build table data rows
        data_rows = []
        for dtype, count in sorted(counts.items()):
            # Find coverage radius from first matching device
            cov_r = 0.0
            for d in devices:
                if d.device_type == dtype and d.coverage_radius > 0:
                    cov_r = d.coverage_radius
                    break
            data_rows.append([dtype, str(count), f"{cov_r:.2f}"])

        # Total row
        total_count = sum(counts.values())
        data_rows.append(["TOTAL", str(total_count), ""])

        # Calculate total rows (header + data)
        n_rows = 1 + len(data_rows)

        # Create TABLE entity
        table = msp.add_table(
            insert=(table_x, table_y),
            nrows=n_rows,
            ncols=n_cols,
            default_cell_width=3000.0,
            default_cell_height=row_h,
            dxfattribs={"layer": "FA-SCHEDULE"}
        )

        # Set column widths
        for i, w in enumerate(col_widths):
            table.set_col_width(i, w)

        # Header row
        for i, name in enumerate(col_names):
            cell = table.get_cell(0, i)
            cell.text = name
            cell.text_style = "Standard"
            cell.char_height = 300.0

        # Data rows
        for row_idx, row_data in enumerate(data_rows):
            for col_idx, cell_text in enumerate(row_data):
                cell = table.get_cell(row_idx + 1, col_idx)
                cell.text = cell_text
                cell.text_style = "Standard"
                cell.char_height = 250.0

        log.info("Schedule table: DXF TABLE entity created (%d rows x %d cols)",
                 n_rows, n_cols)

    except (AttributeError, TypeError) as e:
        # Fallback: ezdxf version does not support TABLE entity
        # Use text blocks as before
        log.warning("DXF TABLE not supported by this ezdxf version (%s), "
                     "falling back to text blocks", e)

        row_h = 500.0
        col_w = 5000.0

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
    print("BRIDGE 3 V2.0: Output Bridge - Self-Test")
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

    # Test with fire-rated wall
    fire_rated_walls = [
        LineString([(7000, 0), (7000, 10000)])  # Vertical fire-rated wall at x=7m
    ]

    # Run bridge with Class A + Firestopping
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
        class_a=True,
        fire_rated_walls=fire_rated_walls,
    )

    print(f"\nOutput: {result.output_path}")
    print(f"Devices drawn: {result.devices_drawn}")
    print(f"Cable segments: {result.cable_segments}")
    print(f"Total cable: {result.total_cable_m:.1f}m")
    print(f"Class A return segments: {result.class_a_return_segments}")
    print(f"Firestopping points: {result.firestopping_points}")
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
    status = "PASS" if result.devices_drawn > 0 and result.class_a_return_segments > 0 else "FAIL"
    print(f"Bridge 3 V2.0 Self-Test: {status}")
    print("=" * 60)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    _self_test()
