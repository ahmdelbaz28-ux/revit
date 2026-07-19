"""
QOMN-FIRE TITLE BLOCK AND FACP DRAWING SHEET PLOTTER
Reference Standard: ISO 19650 standard plotting borders.

BUG-44 FIX: ezdxf import is now guarded — module can be imported
without ezdxf installed, enabling test collection in CI environments.
"""

try:
    import ezdxf
except ImportError:
    ezdxf = None

from qomn_fire.core.types import PanelRecommendation, TitleBlock


def draw_title_block(doc, title: TitleBlock):
    if ezdxf is None:
        raise ImportError("ezdxf library is required for title block drawing.")

    layout = doc.layout("A1-Fire-Alarm-Plan") if "A1-Fire-Alarm-Plan" in doc.layouts else doc.layouts.new("A1-Fire-Alarm-Plan")

    # Border margins
    layout.add_line((10.0, 10.0), (831.0, 10.0), dxfattribs={"color": 7})
    layout.add_line((831.0, 10.0), (831.0, 584.0), dxfattribs={"color": 7})
    layout.add_line((831.0, 584.0), (10.0, 584.0), dxfattribs={"color": 7})
    layout.add_line((10.0, 584.0), (10.0, 10.0), dxfattribs={"color": 7})

    # Title block frame
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

def draw_facp_schedule(doc, rec: PanelRecommendation):
    """
    Renders the approved FACP Schedule dynamically inside the layout paper space block.
    Reference: NFPA 72 §10 submittals standards.
    """
    if ezdxf is None:
        raise ImportError("ezdxf library is required for FACP schedule drawing.")

    layout = doc.layout("A1-Fire-Alarm-Plan") if "A1-Fire-Alarm-Plan" in doc.layouts else doc.layouts.new("A1-Fire-Alarm-Plan")

    # Placed in left center section (X: 10 -> 250, Y: 320 -> 500)
    layout.add_line((10.0, 320.0), (10.0, 500.0), dxfattribs={"color": 7})
    layout.add_line((10.0, 500.0), (250.0, 500.0), dxfattribs={"color": 7})
    layout.add_line((250.0, 500.0), (250.0, 320.0), dxfattribs={"color": 7})
    layout.add_line((250.0, 320.0), (10.0, 320.0), dxfattribs={"color": 7})

    layout.add_text("FACP SELECTION SCHEDULE", dxfattribs={"insert": (15.0, 480.0), "height": 3.5, "color": 7})
    layout.add_line((10.0, 470.0), (250.0, 470.0), dxfattribs={"color": 7})

    layout.add_text(f"RECOMMENDED MODEL : {rec.recommended_model}", dxfattribs={"insert": (15.0, 450.0), "height": 2.5, "color": 7})
    layout.add_text(f"MANUFACTURER      : {rec.manufacturer}", dxfattribs={"insert": (15.0, 430.0), "height": 2.5, "color": 7})
    layout.add_text(f"BATTERY CAPACITY   : {rec.battery_size_ah} Ah (NFPA 72 §10.6.7)", dxfattribs={"insert": (15.0, 410.0), "height": 2.5, "color": 7})
    layout.add_text(f"POINTS UTILIZATION : {rec.capacity_utilization:.2%}", dxfattribs={"insert": (15.0, 390.0), "height": 2.5, "color": 7})
    layout.add_text(f"NAC UTILIZATION    : {rec.nac_utilization:.2%}", dxfattribs={"insert": (15.0, 370.0), "height": 2.5, "color": 7})
    layout.add_text(f"UL CODES LISTINGS  : {', '.join(rec.listings)}", dxfattribs={"insert": (15.0, 350.0), "height": 2.5, "color": 7})

    # Enforce SHA-256 footprint representation inside CAD layouts for document audit trail
    layout.add_text(f"SIGNATURE HASH     : {rec.signature_hash[:24]}...", dxfattribs={"insert": (15.0, 330.0), "height": 1.8, "color": 7})
