"""
QOMN-FIRE COMPLETE DXF SHOP DRAWING GENERATOR
Reference Standard: National CAD Standards (NCS) Layer Specifications.
"""

import ezdxf
from typing import Tuple

def create_document() -> ezdxf.document.Drawing:
    doc = ezdxf.new("R2000")
    doc.header['$TDCREATE'] = 0.0
    doc.header['$TDUPDATE'] = 0.0
    doc.header['$HANDSEED'] = '1'
    return doc

def setup_layers(doc: ezdxf.document.Drawing):
    layers = [
        ("A-WALL", 7),
        ("A-FIRE-DEVICES", 1),
        ("A-FIRE-CABLES", 2),
        ("A-FIRE-HATC", 3),
        ("A-FIRE-DIMS", 4),
        ("A-FIRE-TEXT", 5),
        ("A-FIRE-REVC", 1)
    ]
    for name, color in layers:
        if name not in doc.layers:
            doc.layers.new(name=name, dxfattribs={"color": color})

def add_viewport(
    doc: ezdxf.document.Drawing,
    center: Tuple[float, float],
    size: Tuple[float, float],
    view_center_point: Tuple[float, float],
    view_height: float
):
    layout = doc.layout("A1-Fire-Alarm-Plan") if "A1-Fire-Alarm-Plan" in doc.layouts else doc.layouts.new("A1-Fire-Alarm-Plan")
    vp = layout.add_viewport(
        center=center,
        size=size,
        view_center_point=view_center_point,
        view_height=view_height
    )
    vp.dxf.status = 1
