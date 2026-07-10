"""
marine/integration/autocad_exporter.py — DXF Layer + Entity Generator.

Generates DXF layer definitions and entity placements for marine fire-safety
drawings. Layers per ISO 1101 fire-safety drawing convention:
    F-ZONES, F-DETECTORS, F-EXTINGUISH, F-DIVISIONS, F-ESCAPE-ROUTES

v3: Replaced hand-rolled DXF group-code generation with ezdxf library.
"""
from __future__ import annotations

import math
import os
import tempfile

import ezdxf
from ezdxf.document import Drawing
from ezdxf.enums import TextEntityAlignment

from marine.core.types import DetectorPlacement, MarineZone

LAYER_SPECS: list[dict] = [
    {"name": "F-ZONES",        "color": 5, "linetype": "CONTINUOUS"},
    {"name": "F-DETECTORS",    "color": 1, "linetype": "CONTINUOUS"},
    {"name": "F-EXTINGUISH",   "color": 2, "linetype": "CONTINUOUS"},
    {"name": "F-DIVISIONS",    "color": 6, "linetype": "PHANTOM"},
    {"name": "F-ESCAPE-ROUTES","color": 3, "linetype": "DASHED"},
]

DXF_LAYERS = LAYER_SPECS


def _init_doc() -> Drawing:
    doc = ezdxf.new("R2010")
    for spec in LAYER_SPECS:
        layer = doc.layers.new(name=spec["name"])
        layer.color = spec["color"]
        layer.dxf.linetype = spec["linetype"]
    return doc


def _dxf_string(doc: Drawing) -> str:
    tmp = tempfile.NamedTemporaryFile(mode="w+", suffix=".dxf", delete=False)
    try:
        doc.saveas(tmp.name)
        tmp.seek(0)
        return tmp.read()
    finally:
        tmp.close()
        os.unlink(tmp.name)


def generate_dxf_layer_definitions() -> str:
    doc = _init_doc()
    return _dxf_string(doc)


def place_detector_entities(placements: list[DetectorPlacement]) -> str:
    doc = _init_doc()
    msp = doc.modelspace()
    for dp in placements:
        x, y, z = dp.position_xyz_mm
        msp.add_point((x, y, z), dxfattribs={"layer": "F-DETECTORS"})
        msp.add_text(
            dp.detector_id,
            height=200,
            dxfattribs={"layer": "F-DETECTORS"},
        ).set_placement((x, y + 200, z), align=TextEntityAlignment.LEFT)
    return _dxf_string(doc)


def draw_zones(zones: list[MarineZone], frame_spacing_m: float = 0.6) -> str:
    doc = _init_doc()
    msp = doc.modelspace()
    for z in zones:
        x_start_mm = z.frame_start * frame_spacing_m * 1000.0
        length_mm = (z.frame_end - z.frame_start) * frame_spacing_m * 1000.0
        if length_mm > 0:
            width_mm = (z.area_m2 * 1_000_000.0) / length_mm
        else:
            side = math.sqrt(z.area_m2) * 1000.0
            length_mm = side
            width_mm = side
        points = [
            (x_start_mm, 0.0),
            (x_start_mm + length_mm, 0.0),
            (x_start_mm + length_mm, width_mm),
            (x_start_mm, width_mm),
        ]
        msp.add_lwpolyline(points, close=True, dxfattribs={"layer": "F-ZONES"})
    return _dxf_string(doc)


def generate_full_dxf(
    zones: list[MarineZone],
    detector_placements: list[DetectorPlacement] | None = None,
    frame_spacing_m: float = 0.6,
) -> str:
    doc = _init_doc()
    msp = doc.modelspace()

    for z in zones:
        x_start_mm = z.frame_start * frame_spacing_m * 1000.0
        length_mm = (z.frame_end - z.frame_start) * frame_spacing_m * 1000.0
        if length_mm > 0:
            width_mm = (z.area_m2 * 1_000_000.0) / length_mm
        else:
            side = math.sqrt(z.area_m2) * 1000.0
            length_mm = side
            width_mm = side
        points = [
            (x_start_mm, 0.0),
            (x_start_mm + length_mm, 0.0),
            (x_start_mm + length_mm, width_mm),
            (x_start_mm, width_mm),
        ]
        msp.add_lwpolyline(points, close=True, dxfattribs={"layer": "F-ZONES"})

    if detector_placements:
        for dp in detector_placements:
            dx, dy, dz = dp.position_xyz_mm
            msp.add_point((dx, dy, dz), dxfattribs={"layer": "F-DETECTORS"})
            msp.add_text(
                dp.detector_id,
                height=200,
                dxfattribs={"layer": "F-DETECTORS"},
            ).set_placement((dx, dy + 200, dz), align=TextEntityAlignment.LEFT)

    return _dxf_string(doc)


__all__ = [
    "DXF_LAYERS",
    "draw_zones",
    "generate_dxf_layer_definitions",
    "generate_full_dxf",
    "place_detector_entities",
]
