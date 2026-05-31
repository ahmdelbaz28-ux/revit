"""
QOMN-FIRE COMPLETE DXF SHOP DRAWING GENERATOR

BUG-44 FIX: ezdxf import is now guarded — modules can be imported
without ezdxf installed, enabling type hints and test collection
in CI environments. Functions that need ezdxf raise ImportError
with a clear message at call time instead of crashing at import time.
"""

try:
    import ezdxf
except ImportError:
    ezdxf = None

from typing import Tuple


def create_document():
    if ezdxf is None:
        raise ImportError(
            "ezdxf library is required for DXF document creation. "
            "Install with: pip install ezdxf"
        )
    doc = ezdxf.new("R2000")
    return doc


def setup_layers(doc):
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
            doc.layers.add(name, color=color)


def add_viewport(
    doc,
    center: Tuple[float, float],
    size: Tuple[float, float],
    view_center: Tuple[float, float],
    view_height: float
):
    if ezdxf is None:
        raise ImportError("ezdxf library is required for viewport creation.")
    layout = doc.layout("A1-Fire-Alarm-Plan") if "A1-Fire-Alarm-Plan" in doc.layouts else doc.layouts.new("A1-Fire-Alarm-Plan")
    vp = layout.add_viewport(
        center=center,
        size=size,
        view_center_point=view_center,
        view_height=view_height,
    )
    vp.dxf.status = 1
