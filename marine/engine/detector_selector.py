"""
marine/engine/detector_selector.py — Fire Detector Type Selection & Counting
=============================================================================
Moved from marine/iec60092/part_502.py as part of M4 refactor. Contains
the detector-type-to-hazard matching and spacing-based count logic.

References:
    [IEC502] IEC 60092-502:1999 §4 (detectors) + §6 (alarm circuits)
    [FSS]    IMO FSS Code Ch. 9 (detector spacing tables)
    [LR]     Lloyd's Register Rules Part 6 §2.4 (detection)

"""
from __future__ import annotations

import math

from marine.core.constants import (
    DETECTOR_COVERAGE_M2,
    MAX_DETECTOR_CEILING_HEIGHT_M,
)
from marine.core.types import (
    ComplianceResult,
    DetectorType,
    MarineZone,
    ShipProject,
    SpaceCategory,
)


def select_detector_type(
    zone: MarineZone,
    ship: ShipProject,
) -> ComplianceResult:
    """
    Select appropriate detector type(s) for a marine zone.

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
        ComplianceResult with ``details["selected_types"]`` = list of DetectorType.

    """
    result = ComplianceResult(
        compliant=True,
        standard_reference="IEC 60092-502 §4 + FSS Code Ch. 9",
    )

    cat = zone.space_category
    selected: list[DetectorType] = []

    if cat == SpaceCategory.MACHINERY_SPACE_A:
        selected = [
            DetectorType.HEAT_FIXED,
            DetectorType.FLAME_UV_IR,
            DetectorType.SMOKE_PHOTOELECTRIC,
        ]
        if ship.is_tanker:
            selected.append(DetectorType.ASPIRATING)

    elif cat == SpaceCategory.MACHINERY_SPACE_OTHER:
        selected = [DetectorType.HEAT_FIXED, DetectorType.SMOKE_PHOTOELECTRIC]

    elif cat == SpaceCategory.ACCOMMODATION or cat == SpaceCategory.ESCAPE_ROUTE:
        selected = [DetectorType.SMOKE_PHOTOELECTRIC]
        if ship.is_passenger_ship:
            selected.append(DetectorType.CO)

    elif cat == SpaceCategory.SERVICE_SPACE_MAJOR:
        selected = [
            DetectorType.HEAT_FIXED,
            DetectorType.SMOKE_PHOTOELECTRIC,
        ]

    elif cat == SpaceCategory.SERVICE_SPACE_MINOR:
        selected = [DetectorType.SMOKE_PHOTOELECTRIC]

    elif cat == SpaceCategory.CARGO_SPACE:
        selected = [DetectorType.LINEAR_HEAT, DetectorType.SMOKE_DUCT]

    elif cat == SpaceCategory.CONTROL_STATION:
        selected = [DetectorType.SMOKE_PHOTOELECTRIC]

    elif cat in (SpaceCategory.OPEN_DECK, SpaceCategory.EMPTY_SPACE,
                 SpaceCategory.TANK_SPACE):
        selected = []

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
    """
    Calculate the number of detectors required for a zone.

    Per IEC 60092-502 + FSS Code Ch. 9 Table 9.1:
        N = ceil(area_m2 / coverage_m2)
    Plus a 10% spares allowance (LR Rules Part 6 §2.4).

    If zone.height_m > MAX_DETECTOR_CEILING_HEIGHT_M (12 m), additional
    detectors are required at intermediate levels (stratification effect).

    Args:
        zone: Zone to size detection for.
        detector_type: Type of detector to install.

    Returns:
        ComplianceResult with ``details["detector_count"]`` = int.

    """
    result = ComplianceResult(
        compliant=True,
        standard_reference="FSS Code Ch. 9 Table 9.1",
    )

    coverage = DETECTOR_COVERAGE_M2.get(detector_type.value)
    if coverage is None or coverage <= 0:
        result.details["detector_count"] = 1
        result.details["note"] = (
            f"Detector type {detector_type.value} is per-run, not per-area."
        )
        return result

    base_count = math.ceil(zone.area_m2 / coverage)
    spares = math.ceil(base_count * 0.10)
    total = base_count + spares

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
    result.details["spacings_m"] = math.sqrt(coverage)
    return result


__all__ = ["calculate_detector_count", "select_detector_type"]
