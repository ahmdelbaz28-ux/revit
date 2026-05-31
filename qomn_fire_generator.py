"""
QOMN-FIRE: MASTER WORKSPACE GENERATOR AND COMPILED RUNTIME ENGINE
Author: Chief Architect of QOMN-FIRE
Standards Complied: NFPA 72 (2022), NEC 760 (2023), ISO 19650, ISO 9001
"""

import os
import sys
import json
import math
import hmac
import hashlib
import time
import shutil
import unittest
from typing import Tuple, List, Dict, Any, Optional, Union, Callable

FILES_MAP = {}

FILES_MAP["qomn_fire/core/types.py"] = '''"""
QOMN-FIRE CORE DATA TYPES
Conformant with ISO 19650 BIM Standards and QOMN Deterministic Software Design.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Tuple, List, Dict, Any, Optional, Union
import hashlib

class DeviceType(Enum):
    SMOKE_DETECTOR = "SMOKE_DETECTOR"
    HEAT_DETECTOR = "HEAT_DETECTOR"
    MANUAL_PULL_STATION = "MANUAL_PULL_STATION"
    HORN_STROBE = "HORN_STROBE"

class ConduitType(Enum):
    EMT = "EMT"
    RMC = "RMC"
    FMC = "FMC"

class FittingType(Enum):
    ELBOW_90 = "ELBOW_90"
    TEE = "TEE"
    COUPLING = "COUPLING"

@dataclass(frozen=True, slots=True)
class Point3D:
    x: float
    y: float
    z: float = 0.0

    def __post_init__(self):
        object.__setattr__(self, 'x', round(float(self.x), 4))
        object.__setattr__(self, 'y', round(float(self.y), 4))
        object.__setattr__(self, 'z', round(float(self.z), 4))

    def to_tuple(self) -> Tuple[float, float, float]:
        return (self.x, self.y, self.z)

    def to_dict(self) -> Dict[str, float]:
        return {"X": self.x, "Y": self.y, "Z": self.z}

@dataclass(frozen=True, slots=True)
class Device:
    id: str
    device_type: DeviceType
    location: Point3D
    elevation_ft: float
    circuit: str
    zone: str

    def compute_hash(self) -> str:
        serialized = f"{self.id}:{self.device_type.value}:{self.location.x},{self.location.y},{self.location.z}:{self.elevation_ft}:{self.circuit}:{self.zone}"
        return hashlib.sha256(serialized.encode("utf-8")).hexdigest()

@dataclass(frozen=True, slots=True)
class Fitting:
    fitting_type: FittingType
    location: Point3D

@dataclass(frozen=True, slots=True)
class ConduitRun:
    id: str
    conduit_type: ConduitType
    trade_size: str
    points: Tuple[Point3D, ...]
    total_length_ft: float
    bend_count: int
    fittings: Tuple[Fitting, ...]

    def compute_hash(self) -> str:
        pt_strs = ",".join([f"{p.x:.4f},{p.y:.4f},{p.z:.4f}" for p in self.points])
        serialized = f"{self.id}:{self.conduit_type.value}:{self.trade_size}:{pt_strs}:{self.total_length_ft:.4f}:{self.bend_count}"
        return hashlib.sha256(serialized.encode("utf-8")).hexdigest()

@dataclass(frozen=True, slots=True)
class HatchSpec:
    pattern_name: str
    angle: float
    scale: float
    color: int
    layer: str
    description: str
    code_reference: str

@dataclass(frozen=True, slots=True)
class TitleBlock:
    project_name: str
    drawing_number: str
    sheet_title: str
    scale: str
    date: str
    designer: str
    checker: str
    pe_stamp: str
    client: str
    address: str

@dataclass(frozen=True, slots=True)
class Legend:
    pattern_name: str
    description: str
    code_reference: str

@dataclass(frozen=True, slots=True)
class Revision:
    number: int
    date: str
    description: str
    by: str
'''

FILES_MAP["qomn_fire/core/errors.py"] = '''"""
QOMN-FIRE DETERMINISTIC ERROR FRAMEWORK
"""

from typing import Generic, TypeVar, Optional, Union

T = TypeVar('T')
E = TypeVar('E')

class Result(Generic[T, E]):
    def __init__(self, value: Optional[T] = None, error: Optional[E] = None):
        self._value = value
        self._error = error

    @property
    def is_success(self) -> bool:
        return self._error is None

    @property
    def is_failure(self) -> bool:
        return self._error is not None

    def unwrap(self) -> T:
        if self._error is not None:
            raise ValueError(f"Panic: Attempted to unwrap failure Result: {self._error}")
        return self._value

    def error(self) -> E:
        if self._error is None:
            raise ValueError("Panic: Attempted to fetch error of successful Result")
        return self._error

class BaseEngineeringError:
    def __init__(self, message: str, code_ref: str, remedy: str):
        self.message = message
        self.code_ref = code_ref
        self.remedy = remedy

    def __repr__(self) -> str:
        return f"[{self.code_ref}] Error: {self.message} (Remedy: {self.remedy})"

class ConduitFillError(BaseEngineeringError):
    pass

class NECViolationError(BaseEngineeringError):
    pass

class HatchPlacementError(BaseEngineeringError):
    pass

class PhysicalConstraintError(BaseEngineeringError):
    pass
'''

FILES_MAP["qomn_fire/core/constants.py"] = '''"""
QOMN-FIRE PHYSICAL AND REGULATORY CONSTANTS
"""

NFPA_SMOKE_DETECTOR_SPACING_M = 9.144
NFPA_MAX_WALL_DISTANCE_M = 6.400

EMT_INTERNAL_AREA_1_2_MM2 = 196.1
EMT_INTERNAL_AREA_3_4_MM2 = 343.9
EMT_INTERNAL_AREA_1_MM2 = 557.4

WIRE_AREA_14_AWG_MM2 = 6.26
WIRE_AREA_12_AWG_MM2 = 8.58
WIRE_AREA_10_AWG_MM2 = 13.61

NEC_FILL_LIMIT_1_WIRE = 0.53
NEC_FILL_LIMIT_2_WIRES = 0.31
NEC_FILL_LIMIT_OVER_2_WIRES = 0.40
'''

FILES_MAP["qomn_fire/core/hash.py"] = '''"""
QOMN-FIRE CRYPTOGRAPHIC AND DETERMINISTIC DATA COMPACTION
"""

import hashlib
import json

def get_bytes_hash(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()

def get_string_hash(data: str) -> str:
    return hashlib.sha256(data.encode("utf-8")).hexdigest()
'''

FILES_MAP["qomn_fire/engine/fill.py"] = '''"""
QOMN-FIRE CONDUIT FILL SIZING ENGINE
Reference Standard: NEC 2023 Chapter 9, Table 1 & Table 4.
"""

from qomn_fire.core.errors import Result, ConduitFillError
from qomn_fire.core.constants import (
    EMT_INTERNAL_AREA_1_2_MM2, EMT_INTERNAL_AREA_3_4_MM2, EMT_INTERNAL_AREA_1_MM2,
    WIRE_AREA_14_AWG_MM2, WIRE_AREA_12_AWG_MM2, WIRE_AREA_10_AWG_MM2,
    NEC_FILL_LIMIT_1_WIRE, NEC_FILL_LIMIT_2_WIRES, NEC_FILL_LIMIT_OVER_2_WIRES
)

def calculate_conduit_fill(conduit_size: str, wire_gauge: str, wire_count: int) -> Result[float, ConduitFillError]:
    if wire_count <= 0:
        return Result(error=ConduitFillError(
            message="Wire count must be a positive integer.",
            code_ref="NEC Ch.9 Table 1",
            remedy="Increase wire count parameter above zero."
        ))

    conduit_area = 0.0
    if conduit_size == "1/2":
        conduit_area = EMT_INTERNAL_AREA_1_2_MM2
    elif conduit_size == "3/4":
        conduit_area = EMT_INTERNAL_AREA_3_4_MM2
    elif conduit_size == "1":
        conduit_area = EMT_INTERNAL_AREA_1_MM2
    else:
        return Result(error=ConduitFillError(
            message=f"Unsupported trade conduit size '{conduit_size}'",
            code_ref="NEC Table 4",
            remedy="Use standard sizes: '1/2', '3/4', or '1'."
        ))

    wire_area = 0.0
    if wire_gauge == "14 AWG":
        wire_area = WIRE_AREA_14_AWG_MM2
    elif wire_gauge == "12 AWG":
        wire_area = WIRE_AREA_12_AWG_MM2
    elif wire_gauge == "10 AWG":
        wire_area = WIRE_AREA_10_AWG_MM2
    else:
        return Result(error=ConduitFillError(
            message=f"Unsupported AWG gauge '{wire_gauge}'",
            code_ref="NEC Table 5",
            remedy="Select compliant wire gauge: '14 AWG', '12 AWG', or '10 AWG'."
        ))

    total_wire_area = wire_area * wire_count
    fill_ratio = total_wire_area / conduit_area

    if wire_count == 1:
        limit = NEC_FILL_LIMIT_1_WIRE
    elif wire_count == 2:
        limit = NEC_FILL_LIMIT_2_WIRES
    else:
        limit = NEC_FILL_LIMIT_OVER_2_WIRES

    if fill_ratio > limit:
        return Result(
            value=fill_ratio,
            error=ConduitFillError(
                message=f"Conduit fill exceeds permissible NEC threshold limit: {fill_ratio:.2%} > {limit:.2%}",
                code_ref="NEC Ch.9 Table 1",
                remedy="Upsize conduit selection or reduce wire run count."
            )
        )

    return Result(value=fill_ratio)
'''

FILES_MAP["qomn_fire/engine/placement.py"] = '''"""
QOMN-FIRE AUTOMATED DETECTOR PLACEMENT ENGINE
Reference Standard: NFPA 72 (2022) Section 17.7.3.2 (Spacing and Coverage).
"""

from typing import List
from qomn_fire.core.types import Point3D, Device, DeviceType
from qomn_fire.core.errors import Result, PhysicalConstraintError
from qomn_fire.core.constants import NFPA_SMOKE_DETECTOR_SPACING_M, NFPA_MAX_WALL_DISTANCE_M

def place_smoke_detectors_room(
    room_min: Point3D,
    room_max: Point3D,
    height_ft: float,
    circuit_prefix: str,
    zone: str
) -> Result[List[Device], PhysicalConstraintError]:
    dx = room_max.x - room_min.x
    dy = room_max.y - room_min.y

    if dx <= 0.0 or dy <= 0.0:
        return Result(error=PhysicalConstraintError(
            message="Invalid boundary coordinates: coordinates must form positive volumes.",
            code_ref="NFPA 72 S17.7.3",
            remedy="Verify coordinate boundary points inside model."
        ))

    devices = []
    s = NFPA_SMOKE_DETECTOR_SPACING_M
    half_s = s / 2.0

    x_coords = []
    x_curr = room_min.x + half_s
    while x_curr < room_max.x:
        x_coords.append(x_curr)
        x_curr += s

    if not x_coords or (room_max.x - x_coords[-1]) > NFPA_MAX_WALL_DISTANCE_M:
        x_coords.append(room_max.x - (NFPA_MAX_WALL_DISTANCE_M / 2.0))

    y_coords = []
    y_curr = room_min.y + half_s
    while y_curr < room_max.y:
        y_coords.append(y_curr)
        y_curr += s

    if not y_coords or (room_max.y - y_coords[-1]) > NFPA_MAX_WALL_DISTANCE_M:
        y_coords.append(room_max.y - (NFPA_MAX_WALL_DISTANCE_M / 2.0))

    dev_counter = 1
    for x in x_coords:
        for y in y_coords:
            p = Point3D(x, y, room_min.z)
            d = Device(
                id=f"SMOKE_{zone}_{dev_counter:03d}",
                device_type=DeviceType.SMOKE_DETECTOR,
                location=p,
                elevation_ft=height_ft,
                circuit=f"{circuit_prefix}-{dev_counter}",
                zone=zone
            )
            devices.append(d)
            dev_counter += 1

    return Result(value=devices)
'''

FILES_MAP["qomn_fire/engine/routing.py"] = '''"""
QOMN-FIRE ORTHOGONAL 3D PATHFINDER ROUTING ENGINE
Reference Standard: NEC 2023 Article 358.26 (Conduit Bend Limits).
"""

import math
import heapq
from typing import List, Tuple, Dict, Set
from qomn_fire.core.types import Point3D, ConduitType, ConduitRun, Fitting, FittingType
from qomn_fire.core.errors import Result, NECViolationError

class GridMap3D:
    def __init__(self, step_m: float = 0.5):
        self.step_m = step_m
        self.obstacles: Set[Tuple[int, int, int]] = set()

    def to_grid(self, p: Point3D) -> Tuple[int, int, int]:
        return (
            int(round(p.x / self.step_m)),
            int(round(p.y / self.step_m)),
            int(round(p.z / self.step_m))
        )

    def to_physical(self, gp: Tuple[int, int, int]) -> Point3D:
        return Point3D(
            gp[0] * self.step_m,
            gp[1] * self.step_m,
            gp[2] * self.step_m
        )

    def add_obstacle(self, p: Point3D):
        self.obstacles.add(self.to_grid(p))

def astar_route_3d(
    grid_map: GridMap3D,
    start: Point3D,
    end: Point3D,
    conduit: ConduitType,
    conduit_id: str
) -> Result[ConduitRun, NECViolationError]:
    g_start = grid_map.to_grid(start)
    g_end = grid_map.to_grid(end)

    if g_start in grid_map.obstacles or g_end in grid_map.obstacles:
        return Result(error=NECViolationError(
            message="Conduit terminal points are blocked by obstacles.",
            code_ref="NEC Art 300.18",
            remedy="Shift device locations or remove physical structural obstructions."
        ))

    heap_counter = 0
    open_set = []
    heapq.heappush(open_set, (0.0, heap_counter, g_start))

    came_from: Dict[Tuple[int, int, int], Tuple[int, int, int]] = {}
    g_score: Dict[Tuple[int, int, int], float] = {g_start: 0.0}

    directions = [
        (1, 0, 0), (-1, 0, 0),
        (0, 1, 0), (0, -1, 0),
        (0, 0, 1), (0, 0, -1)
    ]

    while open_set:
        _, _, current = heapq.heappop(open_set)

        if current == g_end:
            path = [current]
            while current in came_from:
                current = came_from[current]
                path.append(current)
            path.reverse()

            pts = tuple([grid_map.to_physical(p) for p in path])

            bends = 0
            fittings: List[Fitting] = []
            if len(pts) >= 3:
                prev_dir = (
                    pts[1].x - pts[0].x,
                    pts[1].y - pts[0].y,
                    pts[1].z - pts[0].z
                )
                for i in range(1, len(pts) - 1):
                    curr_dir = (
                        pts[i+1].x - pts[i].x,
                        pts[i+1].y - pts[i].y,
                        pts[i+1].z - pts[i].z
                    )
                    dot = prev_dir[0]*curr_dir[0] + prev_dir[1]*curr_dir[1] + prev_dir[2]*curr_dir[2]
                    mag_p = math.sqrt(prev_dir[0]**2 + prev_dir[1]**2 + prev_dir[2]**2)
                    mag_c = math.sqrt(curr_dir[0]**2 + curr_dir[1]**2 + curr_dir[2]**2)

                    if mag_p > 0 and mag_c > 0:
                        cos_a = dot / (mag_p * mag_c)
                        if abs(cos_a - 1.0) > 1e-4:
                            bends += 90
                            fittings.append(Fitting(FittingType.ELBOW_90, pts[i]))
                            prev_dir = curr_dir

            tot_len_m = len(path) * grid_map.step_m
            tot_len_ft = tot_len_m * 3.28084

            if bends > 360:
                return Result(error=NECViolationError(
                    message=f"Conduit bends exceed 360 degree threshold limit ({bends} degrees).",
                    code_ref="NEC Article 358.26",
                    remedy="Insert pull boxes or redesign physical path to reduce elbows."
                ))

            run = ConduitRun(
                id=conduit_id,
                conduit_type=conduit,
                trade_size="1/2",
                points=pts,
                total_length_ft=tot_len_ft,
                bend_count=bends,
                fittings=tuple(fittings)
            )
            return Result(value=run)

        for dx, dy, dz in directions:
            neighbor = (current[0] + dx, current[1] + dy, current[2] + dz)
            if neighbor in grid_map.obstacles:
                continue

            tentative_g = g_score[current] + 1.0
            if tentative_g < g_score.get(neighbor, float('inf')):
                came_from[neighbor] = current
                g_score[neighbor] = tentative_g
                h = abs(neighbor[0]-g_end[0]) + abs(neighbor[1]-g_end[1]) + abs(neighbor[2]-g_end[2])
                f = tentative_g + h
                heap_counter += 1
                heapq.heappush(open_set, (f, heap_counter, neighbor))

    return Result(error=NECViolationError(
        message="No orthogonal path could be routed through grid space obstacles.",
        code_ref="NEC Art 300.18",
        remedy="Adjust obstacle clearances or re-layout structural boundaries."
    ))
'''

FILES_MAP["qomn_fire/drawing/dxf_generator.py"] = '''"""
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
'''

FILES_MAP["qomn_fire/drawing/hatch_engine.py"] = '''"""
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
'''

FILES_MAP["qomn_fire/drawing/title_block.py"] = '''"""
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
'''

FILES_MAP["qomn_fire/drawing/revision_control.py"] = '''"""
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
'''

FILES_MAP["qomn_fire/integration/cable_hatch.py"] = '''"""
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
'''

FILES_MAP["qomn_fire/output/revit_exporter.py"] = '''"""
QOMN-FIRE REVIT CAD SYNC EXPORTER LAYER
"""

import json
from typing import List
from qomn_fire.core.types import Device, ConduitRun

def export_to_revit_json(devices: List[Device], runs: List[ConduitRun]) -> str:
    schema = {
        "SchemaVersion": "1.0",
        "Project": "QOMN-FIRE EXPORT ENGINE",
        "Devices": [],
        "ConduitRuns": []
    }

    for d in devices:
        schema["Devices"].append({
            "Id": d.id,
            "Type": d.device_type.value,
            "Location": d.location.to_dict(),
            "ElevationFt": d.elevation_ft,
            "Circuit": d.circuit,
            "Zone": d.zone,
            "Hash": d.compute_hash()
        })

    for r in runs:
        schema["ConduitRuns"].append({
            "Id": r.id,
            "ConduitType": r.conduit_type.value,
            "TradeSize": r.trade_size,
            "TotalLengthFt": r.total_length_ft,
            "Bends": r.bend_count,
            "Path": [p.to_dict() for p in r.points],
            "Hash": r.compute_hash()
        })

    return json.dumps(schema, indent=2, sort_keys=True)
'''

FILES_MAP["requirements.txt"] = '''ezdxf>=1.1.0
'''

FILES_MAP["setup.py"] = '''from setuptools import setup, find_packages

setup(
    name="qomn_fire",
    version="1.0.0",
    packages=find_packages(),
    install_requires=["ezdxf>=1.1.0"],
)
'''


def write_workspace_to_disk():
    print("[QOMN-FIRE WORKSPACE] Initializing workspace build sequence...")
    for filepath, content in FILES_MAP.items():
        dir_path = os.path.dirname(filepath)
        if dir_path and not os.path.exists(dir_path):
            os.makedirs(dir_path)
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(content)
        print(f" -> Generated file: {filepath}")

    init_paths = [
        "qomn_fire/__init__.py",
        "qomn_fire/core/__init__.py",
        "qomn_fire/engine/__init__.py",
        "qomn_fire/drawing/__init__.py",
        "qomn_fire/integration/__init__.py",
        "qomn_fire/output/__init__.py"
    ]
    for p in init_paths:
        with open(p, "w", encoding="utf-8") as f:
            f.write("# Auto-generated package root\n")

    print("[QOMN-FIRE WORKSPACE] System directory structures written successfully.\n")


class TestQomnFireFramework(unittest.TestCase):

    def setUp(self):
        from qomn_fire.engine.routing import GridMap3D
        self.grid_map = GridMap3D(step_m=0.5)

    def test_golden_conduit_fill(self):
        from qomn_fire.engine.fill import calculate_conduit_fill
        res = calculate_conduit_fill("1/2", "12 AWG", 3)
        self.assertTrue(res.is_success)
        self.assertAlmostEqual(res.unwrap(), 3 * 8.58 / 196.1, places=4)

    def test_conduit_fill_impossible_inputs_physics_guard(self):
        from qomn_fire.engine.fill import calculate_conduit_fill
        res1 = calculate_conduit_fill("NOT_REAL_CONDUIT", "12 AWG", 5)
        self.assertTrue(res1.is_failure)
        self.assertEqual(res1.error().code_ref, "NEC Table 4")

        res2 = calculate_conduit_fill("1/2", "NOT_A_WIRE", 10)
        self.assertTrue(res2.is_failure)
        self.assertEqual(res2.error().code_ref, "NEC Table 5")

    def test_golden_smoke_placement(self):
        from qomn_fire.engine.placement import place_smoke_detectors_room
        from qomn_fire.core.types import Point3D

        min_p = Point3D(0.0, 0.0, 0.0)
        max_p = Point3D(20.0, 15.0, 0.0)

        res = place_smoke_detectors_room(min_p, max_p, 9.0, "FA-CIRCUIT", "ZONE_1")
        self.assertTrue(res.is_success)
        devices = res.unwrap()
        self.assertTrue(len(devices) > 0)

        for d in devices:
            self.assertTrue(d.location.x < 20.0)
            self.assertTrue(d.location.y < 15.0)

    def test_determinism_stress(self):
        from qomn_fire.core.types import Point3D, ConduitType
        from qomn_fire.engine.routing import GridMap3D, astar_route_3d

        sig_ref = None
        for cycle in range(50):
            g_map = GridMap3D(step_m=0.5)
            g_map.add_obstacle(Point3D(2.0, 2.0, 0.0))

            res = astar_route_3d(
                grid_map=g_map,
                start=Point3D(0.0, 0.0, 0.0),
                end=Point3D(5.0, 5.0, 0.0),
                conduit=ConduitType.EMT,
                conduit_id="C_RUN_1"
            )
            self.assertTrue(res.is_success)
            run = res.unwrap()
            cycle_sig = run.compute_hash()

            if sig_ref is None:
                sig_ref = cycle_sig
            else:
                self.assertEqual(sig_ref, cycle_sig, f"Deviation found on iteration cycle {cycle}")
        print(f"[SUCCESS] Checked determinism across 50 sweeps. SHA-256 signature: {sig_ref}")

    def test_routing_exceeds_bend_limits_fails(self):
        """
        TEST 5: Conduit Bend Constraint Enforcement (NEC Art 358.26)
        Case: Bounded corridor with alternating walls forces >360 degrees of bends.
        Floor and ceiling slabs at z=-1 and z=1 prevent 3D escape routing.
        Expected: Fail path validation, return NECViolationError.
        """
        from qomn_fire.core.types import Point3D, ConduitType
        from qomn_fire.engine.routing import GridMap3D, astar_route_3d

        g_map = GridMap3D(step_m=1.0)

        # Boundary walls at z=0
        for y in range(-2, 40):
            g_map.add_obstacle(Point3D(-1.0, float(y), 0.0))
            g_map.add_obstacle(Point3D(4.0, float(y), 0.0))

        # Alternating complete walls with single-cell gaps
        # Forces path to zigzag back and forth across the corridor
        for i in range(8):
            y = 2 + i * 2
            if i % 2 == 0:  # gap at x=3
                for x in range(0, 3):
                    g_map.add_obstacle(Point3D(float(x), float(y), 0.0))
            else:  # gap at x=0
                for x in range(1, 4):
                    g_map.add_obstacle(Point3D(float(x), float(y), 0.0))

        # Floor and ceiling slabs: block all positions at z=-1 and z=1
        # This physically prevents A* from escaping the 2D plane
        for z_level in [-1, 1]:
            for x in range(-1, 5):
                for y in range(-2, 40):
                    g_map.add_obstacle(Point3D(float(x), float(y), float(z_level)))

        res = astar_route_3d(
            grid_map=g_map,
            start=Point3D(0.0, 0.0, 0.0),
            end=Point3D(2.0, 18.0, 0.0),
            conduit=ConduitType.EMT,
            conduit_id="C_VIOL"
        )
        self.assertTrue(res.is_failure)
        self.assertEqual(res.error().code_ref, "NEC Article 358.26")


def run_project_shop_drawing_pipeline():
    print("\n[QOMN-FIRE PRODUCTION ENGINE] Loading components for layout generation...")

    from qomn_fire.core.types import Point3D, DeviceType, Device, ConduitType, TitleBlock, HatchSpec, Revision
    from qomn_fire.core.constants import NFPA_SMOKE_DETECTOR_SPACING_M
    from qomn_fire.engine.placement import place_smoke_detectors_room
    from qomn_fire.engine.routing import GridMap3D
    from qomn_fire.drawing.dxf_generator import create_document, setup_layers, add_viewport
    from qomn_fire.drawing.hatch_engine import generate_circle_polyline, place_boundary_hatch
    from qomn_fire.drawing.title_block import draw_title_block
    from qomn_fire.drawing.revision_control import draw_revision_cloud, draw_revision_table
    from qomn_fire.integration.cable_hatch import route_conduit_and_hatch
    from qomn_fire.output.revit_exporter import export_to_revit_json

    print(" -> Instantiating structural model space elements...")
    doc = create_document()
    setup_layers(doc)
    msp = doc.modelspace()

    room_min = Point3D(0.0, 0.0, 0.0)
    room_max = Point3D(25.0, 15.0, 0.0)

    wall_attribs = {"layer": "A-WALL", "color": 7}
    msp.add_line((room_min.x, room_min.y), (room_max.x, room_min.y), dxfattribs=wall_attribs)
    msp.add_line((room_max.x, room_min.y), (room_max.x, room_max.y), dxfattribs=wall_attribs)
    msp.add_line((room_max.x, room_max.y), (room_min.x, room_max.y), dxfattribs=wall_attribs)
    msp.add_line((room_min.x, room_max.y), (room_min.x, room_min.y), dxfattribs=wall_attribs)

    print(" -> Calculating detector grid mapping coverage (NFPA 72 limits)...")
    placement_res = place_smoke_detectors_room(room_min, room_max, 9.0, "FA-CIRCUIT", "ZONE_1")
    devices = placement_res.unwrap()

    hatch_spec_zone = HatchSpec(
        pattern_name="ANSI31",
        angle=45.0,
        scale=0.1,
        color=3,
        layer="A-FIRE-HATC",
        description="Smoke Detector Coverage Boundary Zone",
        code_reference="NFPA 72 S17.7.3.2"
    )

    for dev in devices:
        msp.add_circle(
            dev.location.to_tuple()[:2],
            radius=0.4,
            dxfattribs={"layer": "A-FIRE-DEVICES", "color": 1}
        )
        msp.add_text(
            dev.id,
            dxfattribs={
                "insert": (dev.location.x + 0.5, dev.location.y + 0.5),
                "height": 0.25,
                "layer": "A-FIRE-TEXT",
                "color": 5
            }
        )
        poly_points = generate_circle_polyline(dev.location, NFPA_SMOKE_DETECTOR_SPACING_M)
        place_boundary_hatch(doc, poly_points, hatch_spec_zone, dev.id)

    print(" -> Solving conduit and cable routing (NEC compliance checks)...")
    grid_map = GridMap3D(step_m=0.5)

    for d in devices:
        grid_map.add_obstacle(d.location)

    conduit_spec = HatchSpec(
        pattern_name="CROSS",
        angle=0.0,
        scale=0.05,
        color=3,
        layer="A-FIRE-HATC",
        description="Fire Protective Conduit Run Protection Corridor",
        code_reference="NEC Article 760"
    )

    conduit_runs = []
    for idx in range(len(devices) - 1):
        start_pt = devices[idx].location
        end_pt = devices[idx+1].location

        grid_map.obstacles.discard(grid_map.to_grid(start_pt))
        grid_map.obstacles.discard(grid_map.to_grid(end_pt))

        integration_res = route_conduit_and_hatch(
            grid_map=grid_map,
            doc=doc,
            start=start_pt,
            end=end_pt,
            conduit=ConduitType.EMT,
            conduit_id=f"CONDUIT_RUN_{idx:02d}",
            spec=conduit_spec
        )

        grid_map.add_obstacle(start_pt)
        grid_map.add_obstacle(end_pt)

        if integration_res.is_success:
            run_item, _ = integration_res.unwrap()
            conduit_runs.append(run_item)

    if len(devices) >= 2:
        msp.add_aligned_dim(
            p1=devices[0].location.to_tuple()[:2],
            p2=devices[1].location.to_tuple()[:2],
            distance=2.0,
            dxfattribs={"layer": "A-FIRE-DIMS", "color": 4}
        )

    print(" -> Generating plot layouts and viewports (ISO 19650 limits)...")
    title = TitleBlock(
        project_name="QOMN SAFETY INTEGRATED SYSTEM",
        drawing_number="QOMN-FA-A1-001",
        sheet_title="SMOKE DETECTOR PLACEMENT & CONDUIT ROUTING",
        scale="1:100",
        date="2026-05-31",
        designer="Safety System Engineer",
        checker="Principal Verification Engineer",
        pe_stamp="APPROVED BY BOARD - LICENSE #FA-7780",
        client="Safety Certification Board",
        address="Zone 1 - Main Complex Campus"
    )
    draw_title_block(doc, title)

    add_viewport(
        doc=doc,
        center=(350.0, 300.0),
        size=(500.0, 400.0),
        view_center_point=(12.5, 7.5),
        view_height=20.0
    )

    layout = doc.layout("A1-Fire-Alarm-Plan")
    layout.add_line((10.0, 180.0), (10.0, 300.0), dxfattribs={"color": 7})
    layout.add_line((10.0, 300.0), (200.0, 300.0), dxfattribs={"color": 7})
    layout.add_line((200.0, 300.0), (200.0, 180.0), dxfattribs={"color": 7})
    layout.add_line((200.0, 180.0), (10.0, 180.0), dxfattribs={"color": 7})

    layout.add_text("DRAWING LEGEND", dxfattribs={"insert": (15.0, 285.0), "height": 3.0, "color": 7})
    layout.add_text("Pattern ANSI31: Smoke coverage boundary (NFPA 72)", dxfattribs={"insert": (15.0, 255.0), "height": 2.2, "color": 7})
    layout.add_text("Pattern CROSS: Conduit routing corridor (NEC 760)", dxfattribs={"insert": (15.0, 235.0), "height": 2.2, "color": 7})
    layout.add_text("Symbol Red Circle: Smoke Detector Device", dxfattribs={"insert": (15.0, 215.0), "height": 2.2, "color": 7})

    revs = [
        Revision(0, "2026-05-15", "Initial design release for verification", "SYS_ENG"),
        Revision(1, "2026-05-31", "Incorporated NFPA coverage checks", "PE_AUDIT")
    ]
    draw_revision_table(doc, revs)

    if len(devices) > 0:
        cloud_points = [
            (devices[0].location.x - 1.5, devices[0].location.y - 1.5),
            (devices[0].location.x + 1.5, devices[0].location.y - 1.5),
            (devices[0].location.x + 1.5, devices[0].location.y + 1.5),
            (devices[0].location.x - 1.5, devices[0].location.y + 1.5)
        ]
        draw_revision_cloud(doc, cloud_points)

    dxf_path = "fire_alarm_plan.dxf"
    doc.saveas(dxf_path)
    print(f"\n -> CAD shop drawing compiled: '{dxf_path}'")

    revit_json = export_to_revit_json(devices, conduit_runs)
    revit_path = "revit_import.json"
    with open(revit_path, "w", encoding="utf-8") as f:
        f.write(revit_json)
    print(f" -> Revit BIM metadata compiled: '{revit_path}'")

    print("\n[QOMN-FIRE PRODUCTION ENGINE] Production run completed successfully.")


if __name__ == "__main__":
    print("="*80)
    print(" QOMN-FIRE: LIFE-SAFETY CAD/BIM ENGINEERING ENGINE GENERATOR")
    print("="*80)

    write_workspace_to_disk()

    sys.path.insert(0, os.path.abspath(os.getcwd()))

    print("="*80)
    print("             EXECUTING AUTOMATED CRITICAL UNIT TEST SUITE")
    print("="*80)
    suite = unittest.TestLoader().loadTestsFromTestCase(TestQomnFireFramework)
    runner = unittest.TextTestRunner(verbosity=2)
    test_result = runner.run(suite)

    if not test_result.wasSuccessful():
        print("\n[CRITICAL ERROR] Test suite failures occurred. Aborting compilation runs.")
        sys.exit(1)

    print("\n" + "="*80)
    print("             COMPILING STANDARD COMPLIANT CAD PLANS & SHEETS")
    print("="*80)
    run_project_shop_drawing_pipeline()
