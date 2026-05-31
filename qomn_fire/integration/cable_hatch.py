"""
QOMN-FIRE CABLE AND HATCH INTEGRATION CONTROLLER
Reference Standard: NEC 760 spatial segregation compliance rules.
"""

from typing import List, Tuple, Dict, Any, Union
import ezdxf
from qomn_fire.core.types import Point3D, ConduitType, ConduitRun, HatchSpec, Device
from qomn_fire.core.errors import Result, NECViolationError, HatchPlacementError
from qomn_fire.engine.routing import GridMap3D, astar_route_3d
from qomn_fire.drawing.hatch_engine import place_boundary_hatch

def route_conduit_and_hatch(
    grid_map: GridMap3D,
    doc: ezdxf.document.Drawing,
    start: Point3D,
    end: Point3D,
    conduit: ConduitType,
    conduit_id: str,
    spec: HatchSpec
) -> Result[Tuple[ConduitRun, Any], Union[NECViolationError, HatchPlacementError]]:
    route_res = astar_route_3d(grid_map, start, end, conduit, conduit_id)
    if route_res.is_failure:
        return Result(error=route_res.error())

    conduit_run = route_res.unwrap()
    pts = conduit_run.points

    boundary_points = []
    width_m = 0.20

    for i in range(len(pts) - 1):
        p1, p2 = pts[i], pts[i+1]
        x_min, x_max = min(p1.x, p2.x), max(p1.x, p2.x)
        y_min, y_max = min(p1.y, p2.y), max(p1.y, p2.y)

        if abs(y_max - y_min) < 1e-4:
            boundary_points.extend([
                (round(x_min, 4), round(y_min - width_m, 4)),
                (round(x_max, 4), round(y_min - width_m, 4)),
                (round(x_max, 4), round(y_min + width_m, 4)),
                (round(x_min, 4), round(y_min + width_m, 4))
            ])
        elif abs(x_max - x_min) < 1e-4:
            boundary_points.extend([
                (round(x_min - width_m, 4), round(y_min, 4)),
                (round(x_min + width_m, 4), round(y_min, 4)),
                (round(x_min + width_m, 4), round(y_max, 4)),
                (round(x_min - width_m, 4), round(y_max, 4))
            ])

    unique_points = []
    for p in boundary_points:
        if p not in unique_points:
            unique_points.append(p)

    hatch_res = place_boundary_hatch(doc, unique_points, spec, conduit_id)
    if hatch_res.is_failure:
        return Result(error=hatch_res.error())

    msp = doc.modelspace()
    for i in range(len(pts) - 1):
        msp.add_line(
            pts[i].to_tuple()[:2],
            pts[i+1].to_tuple()[:2],
            dxfattribs={"layer": "A-FIRE-CABLES", "color": 2}
        )

    return Result(value=(conduit_run, hatch_res.unwrap()))
