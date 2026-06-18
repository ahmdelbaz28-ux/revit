"""marine/integration/autocad_exporter.py — DXF Layer + Entity Generator.

Generates DXF layer definitions and entity placements for marine fire-safety
drawings. Layers per ISO 1101 fire-safety drawing convention:
    F-ZONES, F-DETECTORS, F-EXTINGUISH, F-DIVISIONS, F-ESCAPE-ROUTES

v2 BUGFIXES:
    - Output now wrapped in proper DXF SECTION/ENTITIES/ENDSEC/EOF markers.
      The previous output was a bare stream of group codes that no AutoCAD/
      BricsCAD/Oqto would import.
    - draw_zones() previously placed every zone at the same (0,0) origin
      with a square of side sqrt(area). All zones overlapped perfectly.
      Now offsets each zone by its frame_start so they tile the ship's
      longitudinal axis.
"""
from __future__ import annotations
import math
from typing import List
from marine.core.types import DetectorPlacement, ExtinguishingDesign, MarineZone


DXF_LAYERS = [
    {"name": "F-ZONES", "color": 5, "linetype": "CONTINUOUS"},
    {"name": "F-DETECTORS", "color": 1, "linetype": "CONTINUOUS"},
    {"name": "F-EXTINGUISH", "color": 2, "linetype": "CONTINUOUS"},
    {"name": "F-DIVISIONS", "color": 6, "linetype": "PHANTOM"},
    {"name": "F-ESCAPE-ROUTES", "color": 3, "linetype": "DASHED"},
]


def generate_dxf_layer_definitions() -> str:
    """Return DXF LAYER table section as a string.

    Output is the TABLES/ENDSEC section only — callers composing a full
    DXF file should wrap this in a complete HEADER + TABLES + ENTITIES
    + EOF structure (see `generate_full_dxf`).
    """
    lines = ["0", "SECTION", "2", "TABLES", "0", "TABLE", "2", "LAYER", "70", str(len(DXF_LAYERS))]
    for layer in DXF_LAYERS:
        lines.extend([
            "0", "LAYER", "2", layer["name"], "70", "0",
            "62", str(layer["color"]), "6", layer["linetype"],
        ])
    lines.extend(["0", "ENDTAB", "0", "ENDSEC"])
    return "\n".join(lines)


def place_detector_entities(placements: List[DetectorPlacement]) -> str:
    """Return DXF INSERT entities for detectors (point placement).

    Output is the ENTITIES section content (no SECTION/ENDSEC wrappers).
    Use generate_full_dxf() to wrap with proper structure.
    """
    lines = []
    for dp in placements:
        x, y, z = dp.position_xyz_mm
        lines.extend([
            "0", "POINT", "8", "F-DETECTORS",
            "10", f"{x:.2f}", "20", f"{y:.2f}", "30", f"{z:.2f}",
            "0", "TEXT", "8", "F-DETECTORS",
            "10", f"{x:.2f}", "20", f"{y + 200:.2f}", "30", f"{z:.2f}",
            "40", "200", "1", dp.detector_id,
        ])
    return "\n".join(lines)


def draw_zones(zones: List[MarineZone], frame_spacing_m: float = 0.6) -> str:
    """Return DXF LWPOLYLINE entities for zone boundaries (rectangles).

    BUGFIX v2: previously placed every zone at (0,0) with a square of
    side sqrt(area_m2)*1000 mm — all zones overlapped perfectly. Now
    offsets each zone by frame_start * frame_spacing_m so they tile the
    ship's longitudinal axis (forward = 0, aft = +X).

    Args:
        zones: List of MarineZone objects with frame_start, frame_end,
            and area_m2 fields populated.
        frame_spacing_m: Frame spacing in metres (default 0.6 m for
            typical merchant vessels). Used to convert frame numbers to
            millimetres for DXF coordinates.

    Returns:
        DXF entity string (ENTITIES section content, no wrappers).
    """
    lines = []
    for z in zones:
        # Longitudinal position: forward edge of zone in mm.
        x_start_mm = z.frame_start * frame_spacing_m * 1000.0
        # Zone length in mm.
        length_mm = (z.frame_end - z.frame_start) * frame_spacing_m * 1000.0
        # Beam (width): derived from area / length so the rectangle has the
        # correct area. Falls back to sqrt(area) if length is zero.
        if length_mm > 0:
            width_mm = (z.area_m2 * 1_000_000.0) / length_mm  # m² → mm²
        else:
            side = math.sqrt(z.area_m2) * 1000.0  # mm
            length_mm = side
            width_mm = side
        # Draw rectangle (closed LWPOLYLINE).
        lines.extend([
            "0", "LWPOLYLINE", "8", "F-ZONES", "90", "4", "70", "1",
            "10", f"{x_start_mm:.2f}",                    "20", "0.0",
            "10", f"{x_start_mm + length_mm:.2f}",        "20", "0.0",
            "10", f"{x_start_mm + length_mm:.2f}",        "20", f"{width_mm:.2f}",
            "10", f"{x_start_mm:.2f}",                    "20", f"{width_mm:.2f}",
        ])
    return "\n".join(lines)


def generate_full_dxf(
    zones: List[MarineZone],
    detector_placements: List[DetectorPlacement] = None,
    frame_spacing_m: float = 0.6,
) -> str:
    """Generate a complete, valid DXF file with sections and EOF marker.

    Composes:
      - HEADER section (minimal)
      - TABLES section (layer definitions)
      - ENTITIES section (zones + detectors, if provided)
      - EOF marker
    """
    detector_placements = detector_placements or []
    lines: List[str] = []

    # HEADER (minimal — AutoCAD will accept defaults).
    lines.extend([
        "0", "SECTION", "2", "HEADER",
        "9", "$ACADVER", "1", "AC1014",  # R14 — universally readable
        "0", "ENDSEC",
    ])

    # TABLES — layer definitions.
    lines.extend(generate_dxf_layer_definitions().split("\n"))

    # ENTITIES — zones + detectors.
    lines.extend(["0", "SECTION", "2", "ENTITIES"])
    if zones:
        lines.extend(draw_zones(zones, frame_spacing_m).split("\n"))
    if detector_placements:
        lines.extend(place_detector_entities(detector_placements).split("\n"))
    lines.extend(["0", "ENDSEC"])

    # EOF marker (mandatory).
    lines.append("0")
    lines.append("EOF")
    return "\n".join(lines)


__all__ = [
    "DXF_LAYERS", "generate_dxf_layer_definitions",
    "place_detector_entities", "draw_zones", "generate_full_dxf",
]
