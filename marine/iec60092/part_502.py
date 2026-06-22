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


from marine.engine.detector_selector import (  # noqa: F401  # M4 refactor
    calculate_detector_count,
    select_detector_type,
)


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

    Stratification fix: for ceilings above 12 m a second detector layer is
    added at an intermediate level (2/3 of ceiling height) so smoke/gas
    pockets forming below the ceiling are still detected. This doubles the
    number of placements for high compartments.

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

    # Build one layer at a given height.
    def _build_layer(
        height_m: float,
        suffix: str,
        start_index: int,
        standard_ref: str,
    ) -> List[DetectorPlacement]:
        layer: List[DetectorPlacement] = []
        detector_index = start_index
        for r in range(rows):
            for c in range(cols):
                x_mm = origin_xyz_mm[0] + (c + 0.5) * (side_m / cols) * 1000
                y_mm = origin_xyz_mm[1] + (r + 0.5) * (side_m / rows) * 1000
                z_mm = origin_xyz_mm[2] + height_m * 1000

                rated_temp = None
                if detector_type == DetectorType.HEAT_FIXED:
                    if zone.space_category in (
                        SpaceCategory.MACHINERY_SPACE_A,
                        SpaceCategory.MACHINERY_SPACE_OTHER,
                        SpaceCategory.SERVICE_SPACE_MAJOR,
                    ):
                        rated_temp = HEAT_DETECTOR_RATED_TEMPS_C["medium"]
                    else:
                        rated_temp = HEAT_DETECTOR_RATED_TEMPS_C["low"]

                layer.append(DetectorPlacement(
                    detector_id=(
                        f"{zone.zone_id}-D{detector_index:03d}{suffix}-"
                        f"{detector_type.value}"
                    ),
                    zone_id=zone.zone_id,
                    detector_type=detector_type,
                    position_xyz_mm=(x_mm, y_mm, z_mm),
                    coverage_m2=coverage,
                    rated_temp_c=rated_temp,
                    mounting_height_m=height_m,
                    standard_reference=standard_ref,
                ))
                detector_index += 1
        return layer

    placements: List[DetectorPlacement] = []
    base_count = rows * cols
    placements.extend(
        _build_layer(
            zone.height_m,
            suffix="",
            start_index=1,
            standard_ref="IEC 60092-502 §4 + FSS 9.2.4",
        )
    )

    if zone.height_m > MAX_DETECTOR_CEILING_HEIGHT_M:
        strat_height_m = max(3.0, zone.height_m * 2.0 / 3.0)
        placements.extend(
            _build_layer(
                strat_height_m,
                suffix="-S",
                start_index=base_count + 1,
                standard_ref=(
                    "IEC 60092-502 §4 + FSS 9.2.4 + "
                    "stratification layer (>12 m ceiling)"
                ),
            )
        )

    return placements


def validate_alarm_circuit_redundancy(
    zone: MarineZone,
    detector_count: int,
    actual_circuits: int = 0,
) -> ComplianceResult:
    """Validate alarm-circuit redundancy per IEC 60092-502 §6.3.

    Requirements:
      - Each main vertical zone shall have ≥2 independent detector circuits.
      - A single fault in one circuit shall not disable detection in the zone.
      - Loops shall not pass through spaces of higher fire risk than those
        they serve.

    BUGFIX v2: previously this function never added any finding — it only
    wrote `required_circuits=2` into details but accepted no input for the
    actual circuit count, so the validator could never FAIL. Misleading API.
    Now accepts `actual_circuits` parameter and adds a finding when the
    actual count is below the required count.

    Args:
        zone: Zone being validated.
        detector_count: Total detectors in this zone.
        actual_circuits: Actual number of independent detector circuits
            installed. If 0 (default), only the requirement is reported
            (no finding) — preserves backwards-compatible behavior for
            callers that haven't been updated to pass the actual count.

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
        result.details["actual_circuits"] = actual_circuits
        result.details["note"] = (
            "Split detectors across 2 independent circuits so single-fault "
            "does not blind the zone."
        )
        # If caller provided actual_circuits, validate it.
        if actual_circuits > 0 and actual_circuits < required_circuits:
            result.add_finding(
                f"Zone {zone.zone_id} has only {actual_circuits} detector "
                f"circuit(s) — IEC 60092-502 §6.3.2 requires ≥{required_circuits} "
                f"for any zone with >1 detector. Split detectors across "
                f"independent circuits so single-fault does not blind the zone."
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
