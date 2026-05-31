"""
QOMN-FIRE SEMANTIC COVERAGE GRAPHICS ENGINE
Reference Standard: NFPA 72 spacing boundary shapes.
"""

import math
from typing import List, Tuple, Any
import ezdxf
from qomn_fire.core.types import HatchSpec, Point3D
from qomn_fire.core.errors import Result, HatchPlacementError

def generate_circle_polyline(center: Point3D, radius: float, num_sides: int = 16) -> List[Tuple[float, float]]:
    poly = []
    for i in range(num_sides):
        angle = (2.0 * math.pi * i) / num_sides
        x = center.x + radius * math.cos(angle)
        y = center.y + radius * math.sin(angle)
        poly.append((round(x, 4), round(y, 4)))
    return poly

def place_boundary_hatch(
    doc: ezdxf.document.Drawing,
    boundary_points: List[Tuple[float, float]],
    spec: HatchSpec,
    run_id: str
) -> Result[Any, HatchPlacementError]:
    if spec.scale < 0.001:
        return Result(error=HatchPlacementError(
            message=f"Hatch scaling factor {spec.scale} is too small (rendering boundaries < 0.001).",
            code_ref="CAD Drafting standard",
            remedy="Increase scale metric parameter above 0.01."
        ))

    msp = doc.modelspace()
    if spec.layer not in doc.layers:
        doc.layers.new(spec.layer, dxfattribs={"color": spec.color})

    hatch = msp.add_hatch(color=spec.color)
    hatch.dxf.layer = spec.layer
    hatch.dxf.associative = 1

    hatch.set_pattern_fill(spec.pattern_name, scale=spec.scale, angle=spec.angle)
    hatch.paths.add_polyline_path(boundary_points, is_closed=True)

    return Result(value=hatch)
