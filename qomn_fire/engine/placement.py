# NOSONAR
"""
QOMN-FIRE AUTOMATED DETECTOR PLACEMENT ENGINE
Reference Standard: NFPA 72 (2022) Section 17.7.3.2 (Spacing and Coverage).
"""

import logging
import math
from typing import List

from qomn_fire.core.constants import (
    NFPA_MAX_WALL_DISTANCE_M,
    NFPA_SMOKE_DETECTOR_SPACING_M,
)
from qomn_fire.core.errors import PhysicalConstraintError, Result
from qomn_fire.core.types import Device, DeviceType, Point3D

logger = logging.getLogger("qomn_fire.placement")

def place_smoke_detectors_room(  # NOSONAR — S3776: cognitive complexity is inherent to the safety-critical algorithm
    room_min: Point3D,
    room_max: Point3D,
    height_ft: float,
    circuit_prefix: str,
    zone: str
) -> Result[List[Device], PhysicalConstraintError]:
    # SAFETY FIX (V58): Validate inputs for NaN/Inf per IEEE 754 bypass risk.
    # NaN comparisons always return False — NaN room dimensions would silently
    # bypass all validation checks, producing detectors at invalid positions.
    for label, pt in [("room_min", room_min), ("room_max", room_max)]:
        for coord_name, val in [("x", pt.x), ("y", pt.y), ("z", pt.z)]:
            if not math.isfinite(val):
                return Result(error=PhysicalConstraintError(
                    message=f"{label}.{coord_name}={val} is not finite (NaN or Inf). "
                            f"Detector placement requires finite room coordinates.",
                    code_ref="NFPA 72 §17.7.3",  # NOSONAR — S1192: duplicated literal acceptable in this localized context
                    remedy="Validate room geometry before calling placement. Check for NaN in IFC parsing."
                ))
    if not math.isfinite(height_ft):
        return Result(error=PhysicalConstraintError(
            message=f"height_ft={height_ft} is not finite (NaN or Inf). "
                    f"Detector elevation must be a finite value.",
            code_ref="NFPA 72 §17.7.3",
            remedy="Provide a valid room ceiling height."
        ))

    # BUG-P1 FIX: Validate that height_ft is in a physically reasonable range for feet.
    # NFPA 72 §17.7.3.1.4: Smoke detectors are mounted on ceilings. Typical building
    # ceiling heights range from 8 ft (2.4m residential) to 30 ft (9.1m industrial).
    # A value < 3.0 ft likely means the caller passed meters instead of feet
    # (e.g., 3.0m room height from IFC parser misinterpreted as 3.0 ft = 0.91m).
    # A value > 100 ft likely means the caller passed millimeters or centimeters.
    # Either error produces WRONG detector elevation = WRONG NFPA coverage.
    if height_ft < 3.0:
        logger.warning(
            "POTENTIAL UNIT ERROR: height_ft=%.2f is below 3.0 ft (0.91 m). "
            "This parameter expects FEET. If you have meters, convert first: "
            "height_ft = height_m * 3.28084. Typical IFC room heights are 2.4-9.1 m "
            "(8-30 ft). A value of %.2f ft suggests this might be %.2f meters "
            "mistakenly passed as feet.",
            height_ft, height_ft, height_ft
        )
    if height_ft > 100.0:
        logger.warning(
            "POTENTIAL UNIT ERROR: height_ft=%.2f exceeds 100 ft (30.5 m). "
            "This parameter expects FEET. If you have millimeters, divide by 304.8. "
            "No typical building ceiling exceeds 100 ft.",
            height_ft
        )

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
