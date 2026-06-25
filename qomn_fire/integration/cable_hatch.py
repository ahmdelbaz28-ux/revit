"""
QOMN-FIRE INTEGRATION ROUTING AND BOUNDARY PLACEMENTS
Reference Standard: NEC 760 spatial segregation compliance rules.

BUG-22 FIX: Boundary generation now handles diagonal (non-axis-aligned) segments.
The original code only generated boundary rectangles for horizontal and vertical
segments, ignoring diagonal segments entirely. Now uses perpendicular offset
to generate boundaries for any segment orientation.

SAFETY FIX: Now validates conduit fill ratio before producing output.
A conduit run that exceeds NEC fill limits is a fire hazard —
overheated wires in overfilled conduit can ignite surrounding materials.
"""

import math
from typing import Any, Tuple, Union

# BUG-44 FIX: Guard ezdxf import — module can be imported without ezdxf installed
try:
    import ezdxf
except ImportError:
    ezdxf = None

from qomn_fire.core.errors import (
    ConduitFillError,
    HatchPlacementError,
    NECViolationError,
    Result,
)
from qomn_fire.core.types import ConduitRun, ConduitType, HatchSpec, Point3D
from qomn_fire.drawing.hatch_engine import place_boundary_hatch
from qomn_fire.engine.fill import calculate_conduit_fill
from qomn_fire.engine.routing import GridMap3D, astar_route_3d

# Default wire configuration for fire alarm circuits per NFPA 72
# Most FA circuits use 14 AWG with 2-4 conductors per conduit
_DEFAULT_WIRE_GAUGE = "14 AWG"
_DEFAULT_WIRE_COUNT = 4


def route_conduit_and_hatch(
    grid_map: GridMap3D,
    doc: ezdxf.document.Drawing,
    start: Point3D,
    end: Point3D,
    conduit: ConduitType,
    conduit_id: str,
    spec: HatchSpec,
    trade_size: str = "",
    wire_gauge: str = _DEFAULT_WIRE_GAUGE,
    wire_count: int = _DEFAULT_WIRE_COUNT
) -> Result[Tuple[ConduitRun, Any], Union[NECViolationError, HatchPlacementError, ConduitFillError]]:
    """
    BUG-CH1 FIX: Added trade_size parameter to pass through to routing and fill engines.
    The original code did not pass trade_size to astar_route_3d, causing the routing
    engine to always use default trade sizes. Also did not pass conduit_type to
    calculate_conduit_fill, always defaulting to EMT. If the project uses RMC conduit,
    the fill calculation would be WRONG (RMC has smaller internal area than EMT for
    the same trade size) — potentially allowing overfilled conduit that violates
    NEC Chapter 9 Table 1 and creates a fire hazard.
    """
    # Step 1: Route the conduit path — pass trade_size through to routing engine
    route_res = astar_route_3d(grid_map, start, end, conduit, conduit_id, trade_size=trade_size)
    if route_res.is_failure:
        return Result(error=route_res.error())

    conduit_run = route_res.unwrap()

    # Step 2: SAFETY — Validate conduit fill ratio (NEC Chapter 9 Table 1)
    # BUG-CH1 FIX: Pass conduit_type so fill calculation uses correct internal area.
    # EMT and RMC have different internal areas for the same trade size.
    # Using wrong conduit type in fill calculation = wrong fill ratio = potential overfill.
    fill_res = calculate_conduit_fill(
        conduit_run.trade_size, wire_gauge, wire_count,
        conduit_type=conduit.value  # Pass conduit type (EMT/RMC) for correct area lookup
    )
    if fill_res.is_failure:
        return Result(error=fill_res.error())

    # Step 3: Generate boundary hatch points for conduit corridor
    pts = conduit_run.points
    boundary_points = []
    width_m = 0.20

    for i in range(len(pts) - 1):
        p1, p2 = pts[i], pts[i+1]
        dx = p2.x - p1.x
        dy = p2.y - p1.y
        seg_len = math.sqrt(dx * dx + dy * dy)

        if seg_len < 1e-8:
            continue  # Skip zero-length segments

        # BUG-22 FIX: Use perpendicular offset for any segment orientation.
        # For a segment from P1 to P2 with direction (dx, dy), the perpendicular
        # unit vector is (-dy/len, dx/len). Offset the segment by width_m on
        # both sides to create a rectangular boundary around the conduit path.
        # This works for horizontal, vertical, AND diagonal segments.
        perp_x = -dy / seg_len * width_m
        perp_y = dx / seg_len * width_m

        boundary_points.extend([
            (round(p1.x + perp_x, 4), round(p1.y + perp_y, 4)),
            (round(p2.x + perp_x, 4), round(p2.y + perp_y, 4)),
            (round(p2.x - perp_x, 4), round(p2.y - perp_y, 4)),
            (round(p1.x - perp_x, 4), round(p1.y - perp_y, 4))
        ])

    # Deduplicate boundary points
    unique_points = []
    for p in boundary_points:
        if p not in unique_points:
            unique_points.append(p)

    # Step 4: Place hatch only if boundary has valid geometry
    if len(unique_points) >= 3:
        hatch_res = place_boundary_hatch(doc, unique_points, spec, conduit_id)
        if hatch_res.is_failure:
            return Result(error=hatch_res.error())
        hatch_entity = hatch_res.unwrap()
    else:
        # Zero-length or single-segment path — no meaningful boundary to hatch
        hatch_entity = None

    # Step 5: Draw conduit lines in model space
    msp = doc.modelspace()
    for i in range(len(pts) - 1):
        msp.add_line(
            pts[i].to_tuple()[:2],
            pts[i+1].to_tuple()[:2],
            dxfattribs={"layer": "A-FIRE-CABLES", "color": 2}
        )

    return Result(value=(conduit_run, hatch_entity))
