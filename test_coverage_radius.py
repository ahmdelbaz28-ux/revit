"""
test_coverage_radius.py — NFPA 72 Table 17.6.3.1.1 Coverage Radius Tests
=========================================================================
Tests for CoverageSpec and calculate_coverage_radius_from_height.
Validates NFPA 72-2022 Table 17.6.3.1.1 radius values for smoke and heat
detectors at various ceiling heights.

Phase 7: Variable Coverage Radius
"""

import math
import pytest
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "."))

from fireai.core.nfpa72_calculations import (
    calculate_coverage_radius_from_height,
    get_ceiling_height_warnings,
    CoverageSpec,
    DetectorTypeSimple,
    _NFPA72_TABLE_17_6_3_1_1,
    _NFPA72_ABSOLUTE_MAX_HEIGHT,
    _NFPA72_SMOKE_FALLBACK,
    _NFPA72_HEAT_FALLBACK,
)


# ═══════════════════════════════════════════════════════════════════
# Parametrized: Correct radius values per NFPA 72 Table 17.6.3.1.1
# ═══════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("height, det_type, expected_r", [
    (2.4,  "smoke", 4.55),
    (3.0,  "smoke", 4.55),
    (3.5,  "smoke", 4.35),
    (4.0,  "smoke", 4.10),
    (5.0,  "smoke", 3.85),
    (6.0,  "smoke", 3.65),
    (7.0,  "smoke", 3.40),
    (8.0,  "smoke", 3.20),
    (10.0, "smoke", 3.00),
    (12.0, "smoke", 2.80),
    (2.4,  "heat",  3.05),
    (3.0,  "heat",  3.05),
    (4.0,  "heat",  2.75),
    (6.0,  "heat",  2.45),
    (9.0,  "heat",  2.15),
    (12.0, "heat",  1.85),
])
def test_radius_correct_by_height_and_type(height, det_type, expected_r):
    spec = calculate_coverage_radius_from_height(height, det_type)
    assert spec.radius == expected_r, (
        f"h={height}m type={det_type}: expected {expected_r}, got {spec.radius}"
    )


# ═══════════════════════════════════════════════════════════════════
# Physical invariants
# ═══════════════════════════════════════════════════════════════════

def test_smoke_radius_always_greater_than_heat():
    """Smoke detectors always have larger coverage radius than heat at same height."""
    for h in [2.5, 4.0, 6.0, 9.0, 12.0]:
        s = calculate_coverage_radius_from_height(h, "smoke").radius
        ht = calculate_coverage_radius_from_height(h, "heat").radius
        assert s > ht, f"h={h}: smoke R={s} should > heat R={ht}"


def test_radius_decreases_with_height():
    """Per NFPA 72, radius decreases as ceiling height increases."""
    heights = [2.5, 4.0, 6.0, 8.0, 11.0]
    for det in ("smoke", "heat"):
        radii = [calculate_coverage_radius_from_height(h, det).radius for h in heights]
        for i in range(len(radii) - 1):
            assert radii[i] >= radii[i+1], (
                f"{det}: h={heights[i]} R={radii[i]} -> h={heights[i+1]} R={radii[i+1]}"
            )


# ═══════════════════════════════════════════════════════════════════
# Boundary conditions and error handling
# ═══════════════════════════════════════════════════════════════════

def test_above_max_height_warning_and_fallback():
    spec = calculate_coverage_radius_from_height(15.0, "smoke")
    assert spec.radius == _NFPA72_SMOKE_FALLBACK
    assert spec.warning is not None
    assert "AHJ" in spec.warning


def test_above_max_height_heat_fallback():
    spec = calculate_coverage_radius_from_height(15.0, "heat")
    assert spec.radius == _NFPA72_HEAT_FALLBACK
    assert spec.warning is not None


# Fix 8: Test for None height
def test_none_height_raises_type_error():
    with pytest.raises(TypeError, match="must be a float"):
        calculate_coverage_radius_from_height(None)


def test_negative_height_raises():
    with pytest.raises(ValueError):
        calculate_coverage_radius_from_height(-1.0)


def test_zero_height_raises():
    with pytest.raises(ValueError):
        calculate_coverage_radius_from_height(0.0)


# ═══════════════════════════════════════════════════════════════════
# CoverageSpec internal consistency
# ═══════════════════════════════════════════════════════════════════

def test_area_matches_radius():
    for h in [2.4, 5.0, 9.0]:
        for det in ("smoke", "heat"):
            spec = calculate_coverage_radius_from_height(h, det)
            assert spec.area == round(math.pi * spec.radius ** 2, 2)


def test_spacing_max_matches_radius():
    for h in [2.4, 5.0, 9.0]:
        for det in ("smoke", "heat"):
            spec = calculate_coverage_radius_from_height(h, det)
            assert spec.spacing_max == round(spec.radius * 2, 2)


def test_frozen_spec():
    """CoverageSpec is frozen — cannot modify after creation."""
    spec = calculate_coverage_radius_from_height(3.0, "smoke")
    with pytest.raises(Exception):
        spec.radius = 99.0


# ═══════════════════════════════════════════════════════════════════
# Warnings
# ═══════════════════════════════════════════════════════════════════

def test_high_bay_warning():
    spec = calculate_coverage_radius_from_height(10.0, "smoke")
    assert spec.warning and "beam" in spec.warning.lower()


def test_no_warning_in_normative_range():
    spec = calculate_coverage_radius_from_height(4.0, "smoke")
    assert spec.warning is None


def test_extrapolated_nfpa_ref():
    """Above 12.2m, nfpa_ref should mention extrapolation."""
    spec = calculate_coverage_radius_from_height(15.0, "smoke")
    assert "extrapolated" in spec.nfpa_ref.lower()


# ═══════════════════════════════════════════════════════════════════
# get_ceiling_height_warnings
# ═══════════════════════════════════════════════════════════════════

def test_validate_ceiling_height_low():
    w = get_ceiling_height_warnings(1.5)
    assert any("minimum" in x.lower() or "habitable" in x.lower() for x in w)


def test_validate_ceiling_height_high():
    w = get_ceiling_height_warnings(14.0)
    assert any("AHJ" in x for x in w)


def test_validate_ceiling_height_normal():
    w = get_ceiling_height_warnings(4.0)
    assert len(w) == 0


# ═══════════════════════════════════════════════════════════════════
# Integration: CoverageSpec with FloorAnalyser
# ═══════════════════════════════════════════════════════════════════

def test_coverage_spec_radius_used_in_floor_analyser():
    """FloorAnalyser should use CoverageSpec radius for placement."""
    from fireai.core.floor_analyser import FloorAnalyser, RoomSummary
    from fireai.core.spatial_engine.density_optimizer import DensityOptimizer

    opt = DensityOptimizer()
    analyser = FloorAnalyser(floor_id="GF", optimizer=opt)

    rooms = [
        {"room_id": "R1", "name": "low_office",
         "polygon_coords": [(0,0),(10,0),(10,8),(0,8)],
         "ceiling_height": 3.0},
    ]
    report = analyser.analyse(rooms)
    s = report.room_summaries[0]

    # 3.0m ceiling -> smoke R=4.55 per NFPA 72 Table 17.6.3.1.1
    assert s.coverage_radius_used == 4.55, (
        f"Expected coverage_radius_used=4.55, got {s.coverage_radius_used}"
    )
    assert s.ceiling_height == 3.0
    assert s.nfpa_table_ref == "NFPA 72-2022 Table 17.6.3.1.1"


def test_heat_detector_smaller_radius():
    """Heat detector should use smaller radius than smoke at same height."""
    from fireai.core.floor_analyser import FloorAnalyser
    from fireai.core.spatial_engine.density_optimizer import DensityOptimizer

    opt = DensityOptimizer()
    analyser_smoke = FloorAnalyser(floor_id="GF", optimizer=opt)
    analyser_heat = FloorAnalyser(floor_id="GF", optimizer=opt)

    rooms_smoke = [
        {"room_id": "S1", "name": "smoke_room",
         "polygon_coords": [(0,0),(20,0),(20,15),(0,15)],
         "ceiling_height": 5.0,
         "detector_type": "smoke_photoelectric"},
    ]
    rooms_heat = [
        {"room_id": "H1", "name": "heat_room",
         "polygon_coords": [(0,0),(20,0),(20,15),(0,15)],
         "ceiling_height": 5.0,
         "detector_type": "heat_fixed"},
    ]

    report_smoke = analyser_smoke.analyse(rooms_smoke)
    report_heat = analyser_heat.analyse(rooms_heat)

    # At 5.0m: smoke R=3.85, heat R=2.60 — heat should produce more detectors
    assert report_heat.room_summaries[0].coverage_radius_used < report_smoke.room_summaries[0].coverage_radius_used, (
        f"Heat radius ({report_heat.room_summaries[0].coverage_radius_used}) should be < "
        f"smoke radius ({report_smoke.room_summaries[0].coverage_radius_used})"
    )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
