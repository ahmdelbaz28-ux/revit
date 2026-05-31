"""
QOMN-FIRE TITLE BLOCK LAYOUT ENGINE
Reference Standard: ISO 19650 standard plotting borders.
"""

import ezdxf
from qomn_fire.core.types import TitleBlock

def draw_title_block(doc: ezdxf.document.Drawing, title: TitleBlock):
    layout = doc.layout("A1-Fire-Alarm-Plan") if "A1-Fire-Alarm-Plan" in doc.layouts else doc.layouts.new("A1-Fire-Alarm-Plan")

    layout.add_line((10.0, 10.0), (831.0, 10.0), dxfattribs={"color": 7})
    layout.add_line((831.0, 10.0), (831.0, 584.0), dxfattribs={"color": 7})
    layout.add_line((831.0, 584.0), (10.0, 584.0), dxfattribs={"color": 7})
    layout.add_line((10.0, 584.0), (10.0, 10.0), dxfattribs={"color": 7})

    layout.add_line((600.0, 10.0), (600.0, 180.0), dxfattribs={"color": 7})
    layout.add_line((600.0, 180.0), (831.0, 180.0), dxfattribs={"color": 7})

    layout.add_line((600.0, 130.0), (831.0, 130.0), dxfattribs={"color": 7})
    layout.add_line((600.0, 80.0), (831.0, 80.0), dxfattribs={"color": 7})

    layout.add_text(f"PROJECT: {title.project_name}", dxfattribs={"insert": (610.0, 150.0), "height": 3.5, "color": 7})
    layout.add_text(f"SHEET TITLE: {title.sheet_title}", dxfattribs={"insert": (610.0, 105.0), "height": 3.5, "color": 7})
    layout.add_text(f"DWG NO: {title.drawing_number}", dxfattribs={"insert": (610.0, 90.0), "height": 3.0, "color": 7})

    layout.add_text(f"SCALE: {title.scale}  DATE: {title.date}", dxfattribs={"insert": (610.0, 60.0), "height": 2.5, "color": 7})
    layout.add_text(f"DES: {title.designer}  CHK: {title.checker}", dxfattribs={"insert": (610.0, 45.0), "height": 2.5, "color": 7})
    layout.add_text(f"PE STAMP: {title.pe_stamp}", dxfattribs={"insert": (610.0, 25.0), "height": 2.5, "color": 7})
