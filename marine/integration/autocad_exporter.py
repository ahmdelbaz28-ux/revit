"""marine/integration/autocad_exporter.py — DXF Layer Generator.
Generates DXF layer definitions for marine fire-safety drawings:
    F-ZONES, F-DETECTORS, F-EXTINGUISH, F-DIVISIONS, F-ESCAPE-ROUTES"""
from __future__ import annotations
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
    """Return DXF LAYER table section as a string."""
    lines = ["0", "SECTION", "2", "TABLES", "0", "TABLE", "2", "LAYER", "70", str(len(DXF_LAYERS))]
    for layer in DXF_LAYERS:
        lines.extend([
            "0", "LAYER", "2", layer["name"], "70", "0",
            "62", str(layer["color"]), "6", layer["linetype"],
        ])
    lines.extend(["0", "ENDTAB", "0", "ENDSEC"])
    return "\n".join(lines)


def place_detector_entities(placements: List[DetectorPlacement]) -> str:
    """Return DXF INSERT entities for detectors (point placement)."""
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


def draw_zones(zones: List[MarineZone]) -> str:
    """Return DXF POLYLINE entities for zone boundaries (rectangles)."""
    lines = []
    for z in zones:
        side = (z.area_m2 ** 0.5) * 1000  # mm
        lines.extend([
            "0", "LWPOLYLINE", "8", "F-ZONES", "90", "4", "70", "1",
            "10", "0.0", "20", "0.0",
            "10", f"{side:.2f}", "20", "0.0",
            "10", f"{side:.2f}", "20", f"{side:.2f}",
            "10", "0.0", "20", f"{side:.2f}",
        ])
    return "\n".join(lines)


__all__ = ["DXF_LAYERS", "generate_dxf_layer_definitions", "place_detector_entities", "draw_zones"]
