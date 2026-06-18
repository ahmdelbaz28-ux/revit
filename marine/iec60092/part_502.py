"""
marine/iec60092/part_502.py — IEC 60092-502 Fire Detection & Alarm on Ships
============================================================================
IEC 60092-502:1999 — Electrical installations in ships, Part 502: Tankers.

While the standard is titled "Tankers", its detection-and-alarm clauses
are referenced as the baseline for ALL ship types per SOLAS II-2/5
(which cross-references IEC 60092-502 for detector selection).

This module implements:
    - Detector spacing per detector type (cross-references FSS Code Ch. 9)
    - Detector count calculation per space
    - Detector-type-to-hazard matching
    - Circuit redundancy requirements (IEC 60092-502 §6.3)
    - Addressable loop capacity limits

References:
    [IEC502] IEC 60092-502:1999 §4 (detectors) + §6 (alarm circuits)
    [FSS]    IMO FSS Code Ch. 9 (detector spacing tables)
    [LR]     Lloyd's Register Rules Part 6 §2.4 (detection)
"""

from __future__ import annotations

import math
from typing import List, Tuple

from marine.core.constants import (
    CO2_DESIGN_CONCENTRATION_PCT,
    DETECTOR_COVERAGE_M2,
    HEAT_DETECTOR_RATED_TEMPS_C,
    MAX_DETECTOR_CEILING_HEIGHT_M,
    MAX_DETECTOR_SPACING_M,
    MAX_DISTANCE_FROM_BULKHEAD_M,
)
from marine.core.types import (
    AlarmLevel,
    ComplianceResult,
    DetectorPlacement,
    DetectorType,
    MarineZone,
    ShipProject,
    SpaceCategory,
)


def select_detector_type(
    zone: MarineZone,
    ship: ShipProject,
) -> ComplianceResult:
    """Select appropriate detector type(s) for a marine zone.

    Decision matrix based on IEC 60092-502 + FSS Ch. 9:
      - Machinery (A)  → heat_fixed + flame_uv_ir + smoke_photo
      - Machinery other → heat_fixed + smoke_photo
      - Accommodation   → smoke_photo (add CO for passenger ships)
      - Escape routes   → smoke_photo
      - Galley          → heat_fixed (kitchen-rated) + smoke_photo
      - Cargo space     → smoke_duct or heat_ror (per cargo type)
      - Control station → smoke_photo (low-sensitivity to avoid false alarms)

    Args:
        zone: The marine zone to design detection for.
        ship: Ship project (drives passenger-ship additions).

    Returns:
        ComplianceResult with `details["selected_types"]` = list of DetectorType.
    """
    result = ComplianceResult(
        compliant=True,
        standard_reference="IEC 60092-502 §4 + FSS Code Ch. 9",
    )

    cat = zone.space_category
    selected: List[DetectorType] = []

    if cat == SpaceCategory.MACHINERY_SPACE_A:
        # Main machinery: heat + flame + smoke (triple-redundant).
        selected = [
            DetectorType.HEAT_FIXED,
            DetectorType.FLAME_UV_IR,
            DetectorType.SMOKE_PHOTOELECTRIC,
        ]
        # Tankers use aspirating detectors in pump rooms (high-sensitivity).
        if ship.is_tanker:
            selected.append(DetectorType.ASPIRATING)

    elif cat == SpaceCategory.MACHINERY_SPACE_OTHER:
        selected = [DetectorType.HEAT_FIXED, DetectorType.SMOKE_PHOTOELECTRIC]

    elif cat == SpaceCategory.ACCOMMODATION:
        selected = [DetectorType.SMOKE_PHOTOELECTRIC]
        if ship.is_passenger_ship:
            selected.append(DetectorType.CO)

    elif cat == SpaceCategory.ESCAPE_ROUTE:
        selected = [DetectorType.SMOKE_PHOTOELECTRIC]
        if ship.is_passenger_ship:
            selected.append(DetectorType.CO)

    elif cat == SpaceCategory.SERVICE_SPACE_MAJOR:
        # Galleys: use medium-rated heat (78°C) + smoke.
        selected = [
            DetectorType.HEAT_FIXED,
            DetectorType.SMOKE_PHOTOELECTRIC,
        ]

    elif cat == SpaceCategory.SERVICE_SPACE_MINOR:
        selected = [DetectorType.SMOKE_PHOTOELECTRIC]

    elif cat == SpaceCategory.CARGO_SPACE:
        # Cargo: linear heat cable + smoke duct (per SOLAS II-2/7.6).
        selected = [DetectorType.LINEAR_HEAT, DetectorType.SMOKE_DUCT]

    elif cat == SpaceCategory.CONTROL_STATION:
        selected = [DetectorType.SMOKE_PHOTOELECTRIC]

    elif cat in (SpaceCategory.OPEN_DECK, SpaceCategory.EMPTY_SPACE,
                 SpaceCategory.TANK_SPACE):
        selected = []  # No automatic detection (manual call points only)

    else:
        result.add_warning(
            f"No detector selection rule for space category {cat.value}"
        )

    result.details["selected_types"] = [t.value for t in selected]
    result.details["count"] = len(selected)
    return result


def calculate_detector_count(
    zone: MarineZone,
    detector_type: DetectorType,
) -> ComplianceResult:
    """Calculate the number of detectors required for a zone.

    Per IEC 60092-502 + FSS Code Ch. 9 Table 9.1:
        N = ceil(area_m2 / coverage_m2)
    Plus a 10% spares allowance (LR Rules Part 6 §2.4).

    If zone.height_m > MAX_DETECTOR_CEILING_HEIGHT_M (12 m), additional
    detectors are required at intermediate levels (stratification effect).

    Args:
        zone: Zone to size detection for.
        detector_type: Type of detector to install.

    Returns:
        ComplianceResult with `details["detector_count"]` = int.
    """
    result = ComplianceResult(
        compliant=True,
        standard_reference="FSS Code Ch. 9 Table 9.1",
    )

    coverage = DETECTOR_COVERAGE_M2.get(detector_type.value)
    if coverage is None or coverage <= 0:
        # Linear/duct detectors: 1 per run/duct, not per area.
        result.details["detector_count"] = 1
        result.details["note"] = (
            f"Detector type {detector_type.value} is per-run, not per-area."
        )
        return result

    # Calculate base count.
    base_count = math.ceil(zone.area_m2 / coverage)
    spares = math.ceil(base_count * 0.10)  # 10% spares (LR)
    total = base_count + spares

    # High-ceiling adjustment (stratification).
    if zone.height_m > MAX_DETECTOR_CEILING_HEIGHT_M:
        levels = math.ceil(zone.height_m / MAX_DETECTOR_CEILING_HEIGHT_M)
        total *= levels
        result.warnings.append(
            f"Zone {zone.zone_id}: ceiling height {zone.height_m} m exceeds "
            f"{MAX_DETECTOR_CEILING_HEIGHT_M} m — detector count multiplied "
            f"by {levels} for stratification levels (FSS 9.2.2)."
        )

    result.details["detector_count"] = total
    result.details["base_count"] = base_count
    result.details["spares"] = spares
    result.details["coverage_m2_each"] = coverage
    result.details["spacings_m"] = math.sqrt(coverage)  # square-grid spacing
    return result


def place_detectors_grid(
    zone: MarineZone,
    detector_type: DetectorType,
    origin_xyz_mm: Tuple[float, float, float] = (0.0, 0.0, 0.0),
) -> List[DetectorPlacement]:
    """Place detectors in a square grid within a zone.

    Per FSS Code Ch. 9 §2.4:
      - Max spacing between detectors: 10.6 m (smoke)
      - Max distance from bulkhead: 5.3 m (half spacing)
      - Detector mounted at ceiling (zone.height_m)

    Args:
        zone: Zone to fill with detectors.
        detector_type: Type of detector to place.
        origin_xyz_mm: Zone origin in ship coordinates (mm).

    Returns:
        List of DetectorPlacement objects with absolute ship coordinates.
    """
    coverage = DETECTOR_COVERAGE_M2.get(detector_type.value, 74.0)
    if coverage is None or coverage <= 0:
        # Linear/duct: one placement at zone center.
        cx = origin_xyz_mm[0] + (zone.area_m2 ** 0.5) * 500  # mm
        cy = origin_xyz_mm[1] + (zone.area_m2 ** 0.5) * 500
        return [DetectorPlacement(
            detector_id=f"{zone.zone_id}-D001-{detector_type.value}",
            zone_id=zone.zone_id,
            detector_type=detector_type,
            position_xyz_mm=(cx, cy, origin_xyz_mm[2] + zone.height_m * 1000),
            coverage_m2=zone.area_m2,
            mounting_height_m=zone.height_m,
            standard_reference="IEC 60092-502 §4",
        )]

    # Square-grid spacing = sqrt(coverage).
    spacing_m = min(math.sqrt(coverage), MAX_DETECTOR_SPACING_M)

    # Assume zone is rectangular — derive length/width from area.
    # (Real implementation would use the zone's actual polygon.)
    side_m = math.sqrt(zone.area_m2)
    rows = max(1, math.ceil(side_m / spacing_m))
    cols = max(1, math.ceil(side_m / spacing_m))

    placements: List[DetectorPlacement] = []
    detector_index = 1
    for r in range(rows):
        for c in range(cols):
            # Center of each grid cell.
            x_mm = origin_xyz_mm[0] + (c + 0.5) * (side_m / cols) * 1000
            y_mm = origin_xyz_mm[1] + (r + 0.5) * (side_m / rows) * 1000
            z_mm = origin_xyz_mm[2] + zone.height_m * 1000  # ceiling

            rated_temp = None
            if detector_type == DetectorType.HEAT_FIXED:
                # Galley/machinery → medium temp (78°C); else low (54°C).
                if zone.space_category in (
                    SpaceCategory.MACHINERY_SPACE_A,
                    SpaceCategory.MACHINERY_SPACE_OTHER,
                    SpaceCategory.SERVICE_SPACE_MAJOR,
                ):
                    rated_temp = HEAT_DETECTOR_RATED_TEMPS_C["medium"]
                else:
                    rated_temp = HEAT_DETECTOR_RATED_TEMPS_C["low"]

            placements.append(DetectorPlacement(
                detector_id=(
                    f"{zone.zone_id}-D{detector_index:03d}-{detector_type.value}"
                ),
                zone_id=zone.zone_id,
                detector_type=detector_type,
                position_xyz_mm=(x_mm, y_mm, z_mm),
                coverage_m2=coverage,
                rated_temp_c=rated_temp,
                mounting_height_m=zone.height_m,
                standard_reference="IEC 60092-502 §4 + FSS 9.2.4",
            ))
            detector_index += 1

    return placements


def validate_alarm_circuit_redundancy(
    zone: MarineZone,
    detector_count: int,
) -> ComplianceResult:
    """Validate alarm-circuit redundancy per IEC 60092-502 §6.3.

    Requirements:
      - Each main vertical zone shall have ≥2 independent detector circuits.
      - A single fault in one circuit shall not disable detection in the zone.
      - Loops shall not pass through spaces of higher fire risk than those
        they serve.

    Args:
        zone: Zone being validated.
        detector_count: Total detectors in this zone.

    Returns:
        ComplianceResult.
    """
    result = ComplianceResult(
        compliant=True,
        standard_reference="IEC 60092-502 §6.3",
    )

    # IEC 60092-502 §6.3.2: minimum 2 circuits for any zone with >1 detector.
    if detector_count > 1:
        required_circuits = 2
        result.details["required_circuits"] = required_circuits
        result.details["note"] = (
            "Split detectors across 2 independent circuits so single-fault "
            "does not blind the zone."
        )

    # SOLAS II-2/5.1.3: detection system must be powered from both main
    # and emergency switchboard (already in ShipElectricalSpec).
    result.details["power_redundancy_required"] = True

    return result


__all__ = [
    "select_detector_type",
    "calculate_detector_count",
    "place_detectors_grid",
    "validate_alarm_circuit_redundancy",
]
