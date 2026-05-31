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
            message="Room dimensions must form positive volumes.",
            code_ref="NFPA 72 §17.7.3",
            remedy="Re-evaluate coordinate boundary bounding box input parameters."
        ))

    devices = []
    s = NFPA_SMOKE_DETECTOR_SPACING_M
    half_s = s / 2.0

    # BUG-42 FIX: For rooms narrower than half the NFPA spacing (4.572m),
    # the grid-based while loop never executes, and the old fallback placed
    # detectors at room_max - NFPA_MAX_WALL_DISTANCE_M / 2, which can be
    # NEGATIVE relative to room_min (e.g., a 2m wide room: 2 - 3.2 = -1.2).
    # Detectors placed outside room bounds provide ZERO coverage — the NFPA
    # spacing analysis would be completely wrong, leaving the room unprotected.
    # Fix: Use room center as fallback for narrow dimensions, and clamp all
    # detector positions to stay within room bounds.

    x_coords = []
    x_curr = room_min.x + half_s
    while x_curr < room_max.x:
        x_coords.append(x_curr)
        x_curr += s

    if not x_coords:
        # Room too narrow for grid — place detector at room center X
        x_coords.append((room_min.x + room_max.x) / 2.0)
    elif (room_max.x - x_coords[-1]) > NFPA_MAX_WALL_DISTANCE_M:
        extra = room_max.x - (NFPA_MAX_WALL_DISTANCE_M / 2.0)
        # Clamp to room bounds to avoid placing detectors outside the room
        extra = max(room_min.x + 0.1, min(extra, room_max.x - 0.1))
        x_coords.append(extra)

    y_coords = []
    y_curr = room_min.y + half_s
    while y_curr < room_max.y:
        y_coords.append(y_curr)
        y_curr += s

    if not y_coords:
        # Room too narrow for grid — place detector at room center Y
        y_coords.append((room_min.y + room_max.y) / 2.0)
    elif (room_max.y - y_coords[-1]) > NFPA_MAX_WALL_DISTANCE_M:
        extra = room_max.y - (NFPA_MAX_WALL_DISTANCE_M / 2.0)
        # Clamp to room bounds to avoid placing detectors outside the room
        extra = max(room_min.y + 0.1, min(extra, room_max.y - 0.1))
        y_coords.append(extra)

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
