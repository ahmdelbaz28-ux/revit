"""
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
