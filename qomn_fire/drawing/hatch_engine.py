"""
QOMN-FIRE HATCH AND PATTERN PLACEMENT MODULE
Reference Standard: NFPA 72 spacing boundary shapes.

BUG-44 FIX: ezdxf import is now guarded — module can be imported
without ezdxf installed, enabling test collection in CI environments.
"""

import math
from typing import List, Tuple, Any

try:
    import ezdxf
except ImportError:
    ezdxf = None

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
    doc,
    boundary_points: List[Tuple[float, float]],
    spec: HatchSpec,
    run_id: str
) -> Result[Any, HatchPlacementError]:
    if ezdxf is None:
        return Result(error=HatchPlacementError(
            message="ezdxf library is required for hatch placement. Install with: pip install ezdxf",
            code_ref="CAD Dependency",
            remedy="Install ezdxf or disable DXF drawing output."
        ))

    if spec.scale < 0.001:
        return Result(error=HatchPlacementError(
            message=f"Hatch scaling factor {spec.scale} is too small (< 0.001).",
            code_ref="CAD Drafting Standards",
            remedy="Increase hatch scale parameter bounds above 0.01."
        ))

    # SAFETY: A hatch boundary with fewer than 3 points is geometrically invalid.
    # A 0/1/2 point boundary produces a degenerate polyline that renders
    # incorrectly in CAD viewers and may cause DXF file corruption.
    if len(boundary_points) < 3:
        return Result(error=HatchPlacementError(
            message=f"Hatch boundary for '{run_id}' has {len(boundary_points)} points — minimum 3 required for a valid polygon.",
            code_ref="CAD Drafting Standards / ISO 19650",
            remedy="Ensure the hatch boundary encloses a valid area with at least 3 distinct vertices."
        ))

    msp = doc.modelspace()
    if spec.layer not in doc.layers:
        doc.layers.add(spec.layer, color=spec.color)

    hatch = msp.add_hatch(color=spec.color)
    hatch.dxf.layer = spec.layer
    hatch.dxf.associative = 1

    hatch.set_pattern_fill(spec.pattern_name, scale=spec.scale, angle=spec.angle)
    hatch.paths.add_polyline_path(boundary_points, is_closed=True)

    return Result(value=hatch)
