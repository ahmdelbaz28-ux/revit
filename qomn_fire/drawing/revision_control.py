"""
QOMN-FIRE REVISION SCHEMATIC SYSTEM
Reference Standard: ISO 9001 quality audits.
"""

from typing import List, Tuple
import ezdxf
from qomn_fire.core.types import Revision

def draw_revision_cloud(doc: ezdxf.document.Drawing, vertices: List[Tuple[float, float]]):
    msp = doc.modelspace()
    # ezdxf 1.4.x: bulge set via format='xyb' (x, y, bulge) in point tuples
    bulge_vertices = [(x, y, 0.4) for (x, y) in vertices]
    p_line = msp.add_lwpolyline(bulge_vertices, format='xyb', close=True,
                                 dxfattribs={"layer": "A-FIRE-REVC", "color": 1})

def draw_revision_table(doc: ezdxf.document.Drawing, revisions: List[Revision]):
    layout = doc.layout("A1-Fire-Alarm-Plan") if "A1-Fire-Alarm-Plan" in doc.layouts else doc.layouts.new("A1-Fire-Alarm-Plan")

    layout.add_line((600.0, 180.0), (600.0, 250.0), dxfattribs={"color": 7})
    layout.add_line((600.0, 250.0), (831.0, 250.0), dxfattribs={"color": 7})
    layout.add_text("REVISIONS LOG", dxfattribs={"insert": (610.0, 235.0), "height": 3.0, "color": 7})

    y_offset = 215.0
    for rev in revisions:
        rev_str = f"REV {rev.number} - {rev.date} - {rev.description} ({rev.by})"
        layout.add_text(rev_str, dxfattribs={"insert": (610.0, y_offset), "height": 2.2, "color": 7})
        y_offset -= 15.0
