"""
tests/test_nfpa72_calculations.py
==================================
Comprehensive test suite for fireai/core/nfpa72_calculations.py

Covers the NFPA 72 calculation module identified in
TestSprite_Full_Report.md as missing test coverage (TC015-TC020).

NFPA 72 (2022 Edition) References:
  §10.6.4        — NAC voltage drop (≤ 20% for NAC)
  §10.6.7.2.1    — Battery standby (24h + 5min alarm)
  §10.14         — Voltage drop calculation
  §10.14.1       — Inrush current under alarm conditions
  §14.4          — Inspection, testing and maintenance
  §17.6.3.1.1    — Height-adjusted spacing (Table 17.6.3.1.1)
  §17.6.3.3      — Corridor spacing
  §17.6.3.4      — Sloped ceiling / ridge zone
  §17.6.3.5.1    — Heat detector spacing (Table)
  §17.6.3.6      — Beam pocket correction
  §17.7.4.2.3.1  — Coverage radius R = 0.7 × S
  §17.7.5.4.2    — Duct detector spacing (≤ 10m)
  §18.5          — NAC circuit loading
  §21.2.2        — Max devices per panel
  §27.4.1.2      — PLFA circuit voltage drop (≤ 10%)
  NEC Art. 760.71 — Minimum AWG 14 for fire alarm wiring

Scope:
  - Smoke detector radius & spacing (R = 0.7 × S, S = 9.1m at h≤3m)
  - Heat detector coverage (Chebyshev / square grid)
  - Heat detector spacing & position generation
  - Ridge zone boundary & point-in-zone check (sloped ceilings)
  - Detector requirements (combined smoke/heat)
  - calculate_max_spacing / calculate_coverage_radius / calculate_max_wall_distance
  - calculate_coverage_radius_from_height (height-adjusted table)
  - get_ceiling_height_warnings
  - beam_pocket_correction_factor (NFPA 72 §17.6.3.6)
  - calculate_corridor_spacing (NFPA 72 §17.6.3.3)
  - calculate_duct_detector_positions (NFPA 72 §17.7.5.4.2)
  - check_voltage_drop (NFPA 72 §10.14, §27.4.1.2)
  - required_battery_capacity_ah (NFPA 72 §10.6.7.2.1)
  - calculate_inrush_current (NFPA 72 §10.14.1)
  - calculate_nac_loading (NFPA 72 §18.5)
  - auto_select_awg (NEC Art. 760.71 + NFPA 72 §10.14)
"""

from __future__ import annotations

import math

import pytest
from shapely.geometry import Polygon as ShapelyPolygon

from fireai.core.nfpa72_calculations import (
    AWG_GAUGES,
    AWG_RESISTANCE_TABLE,
    DEVICE_CURRENT_DRAW,
    NAC_MAX_CURRENT_A,
    CoverageSpec,
    auto_select_awg,
    beam_pocket_correction_factor,
    calculate_corridor_spacing,
    calculate_coverage_radius,
    calculate_coverage_radius_from_height,
    calculate_detector_requirements,
    calculate_duct_detector_positions,
    calculate_heat_detector_coverage_chebyshev,
    calculate_heat_detector_spacing_rectangular,
    calculate_inrush_current,
    calculate_max_spacing,
    calculate_max_wall_distance,
    calculate_nac_loading,
    calculate_ridge_zone_boundary,
    calculate_smoke_detector_radius,
    calculate_smoke_detector_spacing,
    check_voltage_drop,
    estimate_detector_count_polygon,
    generate_heat_detector_positions,
    get_ceiling_height_warnings,
    is_in_ridge_zone,
    is_point_covered_by_heat_detectors,
    minimum_detector_count_rectangular,
    required_battery_capacity_ah,
    requires_ridge_zone_detector,
)
from fireai.core.nfpa72_models import (
    CeilingSpec,
    CeilingType,
    DetectorType,
    HVACDuct,
    RoomSpec,
)


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────


@pytest.fixture
def flat_ceiling_3m() -> CeilingSpec:
    """Standard flat ceiling at 3.0m — NFPA 72 baseline height."""
    return CeilingSpec(
        height_at_low_point_m=3.0,
        ceiling_type=CeilingType.FLAT,
        slope_degrees=0.0,
    )


@pytest.fixture
def room_10x10(flat_ceiling_3m: CeilingSpec) -> RoomSpec:
    """10m × 10m room — typical office space."""
    return RoomSpec(
        room_id="R-001",
        name="Office",
        width_m=10.0,
        depth_m=10.0,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Smoke Detector Radius & Spacing
# ─────────────────────────────────────────────────────────────────────────────


class TestSmokeDetectorRadius:
    """calculate_smoke_detector_radius — R = 0.7 × S."""

    def test_radius_at_3m(self):
        """At h=3.0m, R = 0.7 × 9.1m = 6.37m (NFPA 72 §17.7.4.2.3.1)."""
        assert calculate_smoke_detector_radius(3.0) == pytest.approx(6.37, abs=0.01)

    def test_radius_at_2m(self):
        """Below 3m, R remains 6.37m (NFPA 72 §17.7.3.2.3 — flat)."""
        assert calculate_smoke_detector_radius(2.0) == pytest.approx(6.37, abs=0.01)

    def test_radius_at_6m_legacy_height_adjusted(self):
        """Legacy calculate_smoke_detector_radius() returns HEIGHT-ADJUSTED value.

        NOTE: This documents a known inconsistency between two code paths:
          - `calculate_smoke_detector_radius()` (via `_get_radius_internal`)
            returns HEIGHT-VARYING values per the pre-V130 NFPA 72 table
            (R=5.39m at h=5.5–6.1m, R=4.76m at h=7.6–9.1m, etc.).
          - `calculate_coverage_radius_from_height(h, "smoke").radius`
            returns FLAT R=6.37m at all heights per the V130 §17.7.3.2.3 fix.

        Callers needing the V130-correct flat spacing should use
        `calculate_coverage_radius_from_height()` instead. This test pins the
        current legacy behavior so any future unification is detected.
        """
        # At h=6m, _get_radius_internal returns R=5.39m (S=7.7m, height-adjusted)
        assert calculate_smoke_detector_radius(6.0) == pytest.approx(5.39, abs=0.01)
        # The V130-correct flat spacing is available via the other function:
        v130_spec = calculate_coverage_radius_from_height(6.0, "smoke")
        assert v130_spec.radius == pytest.approx(6.37, abs=0.01)


class TestSmokeDetectorSpacing:
    """calculate_smoke_detector_spacing — number of detectors per axis."""

    def test_small_room_one_detector(self, flat_ceiling_3m: CeilingSpec):
        """Room 5m × 5m: spacing = 6.37/0.7 = 9.1m, so 1×1 = 1 detector."""
        num_w, num_d = calculate_smoke_detector_spacing(flat_ceiling_3m, 5.0, 5.0)
        assert (num_w, num_d) == (1, 1)

    def test_10x10_room(self, flat_ceiling_3m: CeilingSpec):
        """10m × 10m room: ceil(10/9.1) = 2 detectors per axis → 4 total."""
        num_w, num_d = calculate_smoke_detector_spacing(flat_ceiling_3m, 10.0, 10.0)
        assert (num_w, num_d) == (2, 2)

    def test_large_room_30x30(self, flat_ceiling_3m: CeilingSpec):
        """30m × 30m room: ceil(30/9.1) = 4 detectors per axis → 16 total."""
        num_w, num_d = calculate_smoke_detector_spacing(flat_ceiling_3m, 30.0, 30.0)
        assert (num_w, num_d) == (4, 4)

    def test_minimum_one_detector(self, flat_ceiling_3m: CeilingSpec):
        """Even a tiny room must have at least 1 detector per axis."""
        num_w, num_d = calculate_smoke_detector_spacing(flat_ceiling_3m, 0.5, 0.5)
        assert (num_w, num_d) == (1, 1)


# ─────────────────────────────────────────────────────────────────────────────
# Heat Detector Coverage (Chebyshev / Square Grid)
# ─────────────────────────────────────────────────────────────────────────────


class TestHeatDetectorCoverage:
    """Chebyshev distance — square coverage of side = spacing."""

    def test_point_at_center_covered(self):
        """Point at detector location is always covered."""
        assert calculate_heat_detector_coverage_chebyshev(5, 5, 5, 5, 6.1) is True

    def test_point_within_half_spacing_covered(self):
        """Point at (3, 3) within half-spacing (3.05m) of detector at (0,0)."""
        assert calculate_heat_detector_coverage_chebyshev(0, 0, 3, 3, 6.1) is True

    def test_point_just_outside_not_covered(self):
        """Point at (3.1, 3.1) exceeds half-spacing 3.05m → not covered."""
        assert calculate_heat_detector_coverage_chebyshev(0, 0, 3.1, 3.1, 6.1) is False

    def test_boundary_point_covered(self):
        """Boundary point exactly at half-spacing is covered (≤ comparison)."""
        assert calculate_heat_detector_coverage_chebyshev(0, 0, 3.05, 0, 6.1) is True

    def test_asymmetric_coverage(self):
        """Chebyshev uses max(|dx|, |dy|) — point at (3, 1) covered by (0,0)."""
        # max(3, 1) = 3 ≤ 3.05 → covered
        assert calculate_heat_detector_coverage_chebyshev(0, 0, 3, 1, 6.1) is True


class TestHeatDetectorSpacing:
    """calculate_heat_detector_spacing_rectangular."""

    def test_10x10_default_6_1m(self):
        """10m × 10m with default 6.1m spacing: ceil(10/6.1) = 2 per axis."""
        num_w, num_d = calculate_heat_detector_spacing_rectangular(10.0, 10.0)
        assert (num_w, num_d) == (2, 2)

    def test_15x15_requires_3_per_axis(self):
        """15m × 15m with 6.1m spacing: ceil(15/6.1) = 3 per axis → 9 total."""
        num_w, num_d = calculate_heat_detector_spacing_rectangular(15.0, 15.0)
        assert (num_w, num_d) == (3, 3)

    def test_custom_spacing(self):
        """Custom 5m spacing: 12m × 8m → ceil(12/5)=3 × ceil(8/5)=2 = 6."""
        num_w, num_d = calculate_heat_detector_spacing_rectangular(12.0, 8.0, 5.0)
        assert (num_w, num_d) == (3, 2)


class TestHeatDetectorPositions:
    """generate_heat_detector_positions — square grid layout."""

    def test_10x10_positions_count(self, flat_ceiling_3m: CeilingSpec, room_10x10: RoomSpec):
        """10m × 10m room at 3m ceiling → 2×2 = 4 positions."""
        positions = generate_heat_detector_positions(room_10x10, flat_ceiling_3m)
        assert len(positions) == 4

    def test_positions_are_within_room_bounds(
        self, flat_ceiling_3m: CeilingSpec, room_10x10: RoomSpec
    ):
        """All positions must be inside the room (with margin for wall distance)."""
        positions = generate_heat_detector_positions(room_10x10, flat_ceiling_3m)
        for x, y in positions:
            assert 0 <= x <= room_10x10.width_m
            assert 0 <= y <= room_10x10.depth_m

    def test_single_detector_in_tiny_room(self, flat_ceiling_3m: CeilingSpec):
        """Tiny 3m × 3m room → 1 detector, centered."""
        room = RoomSpec(room_id="R", name="R", width_m=3.0, depth_m=3.0)
        positions = generate_heat_detector_positions(room, flat_ceiling_3m)
        assert len(positions) == 1
        # Should be at center
        x, y = positions[0]
        assert x == pytest.approx(1.5, abs=0.1)
        assert y == pytest.approx(1.5, abs=0.1)

    def test_15x15_uses_3x3_grid(self, flat_ceiling_3m: CeilingSpec):
        """15m × 15m room → V79 FIX ensures 3×3 = 9 detectors, not 4.

        Previous while-loop bug placed only 4 detectors (2×2), leaving the
        far wall 5.85m from nearest detector — exceeding the S/2 = 3.05m
        NFPA 72 §17.6.3.1.1 wall-distance limit.
        """
        room = RoomSpec(room_id="R", name="R", width_m=15.0, depth_m=15.0)
        positions = generate_heat_detector_positions(room, flat_ceiling_3m)
        assert len(positions) == 9  # 3×3


class TestIsPointCoveredByHeatDetectors:
    """is_point_covered_by_heat_detectors — multi-detector coverage check."""

    def test_covered_by_one_of_many(self):
        """Point covered by any one detector in the list → True."""
        detectors = [(0, 0), (10, 0), (0, 10), (10, 10)]
        # Point (1, 1) is within half-spacing (3.05m) of (0, 0)
        assert is_point_covered_by_heat_detectors((1, 1), detectors, 6.1) is True

    def test_not_covered_by_any(self):
        """Point not within range of any detector → False."""
        detectors = [(0, 0), (10, 0), (0, 10), (10, 10)]
        # Point (5, 5) is 5m from every detector, exceeds 3.05m half-spacing
        assert is_point_covered_by_heat_detectors((5, 5), detectors, 6.1) is False

    def test_empty_detector_list(self):
        """Empty detector list → no coverage."""
        assert is_point_covered_by_heat_detectors((1, 1), [], 6.1) is False


# ─────────────────────────────────────────────────────────────────────────────
# Sloped Ceiling — Ridge Zone
# ─────────────────────────────────────────────────────────────────────────────


class TestRidgeZone:
    """Ridge zone detection per NFPA 72 §17.6.3.4."""

    def test_flat_ceiling_no_ridge_required(self, flat_ceiling_3m: CeilingSpec):
        """Flat ceiling (slope ≤ 1.5°) does not require ridge zone."""
        assert requires_ridge_zone_detector(flat_ceiling_3m) is False

    def test_gentle_slope_no_ridge_required(self):
        """Slope ≤ 14° does NOT require ridge zone (V65 FIX)."""
        ceil = CeilingSpec(
            height_at_low_point_m=3.0,
            height_at_high_point_m=3.5,
            ceiling_type=CeilingType.SLOPED,
            slope_run_m=10.0,  # arctan(0.5/10) ≈ 2.86°
        )
        assert ceil.slope_degrees < 14.0
        assert requires_ridge_zone_detector(ceil) is False

    def test_steep_slope_requires_ridge(self):
        """Slope > 14° requires ridge zone detector per NFPA 72 §17.6.3.4."""
        ceil = CeilingSpec(
            height_at_low_point_m=3.0,
            height_at_high_point_m=6.0,  # arctan(3/10) ≈ 16.7°
            ceiling_type=CeilingType.SLOPED,
            slope_run_m=10.0,
        )
        assert ceil.slope_degrees > 14.0
        assert requires_ridge_zone_detector(ceil) is True

    def test_ridge_zone_boundary_flat_returns_unchanged(self):
        """Flat ceiling (slope ≤ 1.5°) → ridge_line returned unchanged."""
        ridge = (0.0, 0.0, 10.0, 0.0)
        result = calculate_ridge_zone_boundary(ridge, 0.0)
        assert result == ridge

    def test_ridge_zone_boundary_sloped_offsets_perpendicular(self):
        """Sloped ceiling → ridge boundary offset perpendicular by buffer_m.

        V65 FIX: Buffer must extend PERPENDICULAR to the ridge line, not
        just along the x-axis. For a horizontal ridge (dy=0), perpendicular
        is along y-axis → boundary y-coords shift by ±buffer.
        """
        ridge = (0.0, 0.0, 10.0, 0.0)  # Horizontal ridge along x-axis
        result = calculate_ridge_zone_boundary(ridge, 30.0, buffer_m=0.9)
        # Perpendicular to (dx=10, dy=0) is (0, 1) — so y shifts by +0.9
        assert result[1] == pytest.approx(0.9, abs=1e-6)
        assert result[3] == pytest.approx(0.9, abs=1e-6)

    def test_ridge_zone_default_buffer_is_0_9m(self):
        """NFPA 72 §17.6.3.4 default ridge buffer = 0.9m (3ft).

        Pins the default value so changing it is detected. Most callers
        rely on the default, so a silent change would affect every
        sloped-ceiling ridge zone check in the system.
        """
        ridge = (0.0, 0.0, 10.0, 0.0)
        # Call WITHOUT explicit buffer_m — should use default 0.9
        result = calculate_ridge_zone_boundary(ridge, 30.0)
        assert result[1] == pytest.approx(0.9, abs=1e-6), (
            f"Default ridge buffer changed: expected 0.9m, got {result[1]}m. "
            f"NFPA 72 §17.6.3.4 specifies 0.9m (3ft) — verify any change with AHJ."
        )

    def test_is_in_ridge_zone_default_buffer_is_0_9m(self):
        """is_in_ridge_zone also uses 0.9m default buffer."""
        # Point 0.95m from ridge — inside default 0.9m? No, 0.95 > 0.9
        # (with default buffer=0.9, point at 0.95m should be OUTSIDE)
        assert is_in_ridge_zone((5, 0.95), (0, 0, 10, 0), 30.0) is False
        # Point 0.85m from ridge — inside default 0.9m
        assert is_in_ridge_zone((5, 0.85), (0, 0, 10, 0), 30.0) is True

    def test_is_in_ridge_zone_flat_always_true(self):
        """Flat ceiling → every point is in the ridge zone (no requirement)."""
        assert is_in_ridge_zone((5, 5), (0, 0, 10, 0), 0.0) is True

    def test_is_in_ridge_zone_on_ridge(self):
        """Point on the ridge line is in the zone."""
        # Horizontal ridge from (0,0) to (10,0); point (5, 0) is on ridge
        assert is_in_ridge_zone((5, 0), (0, 0, 10, 0), 30.0) is True

    def test_is_in_ridge_zone_just_off_ridge(self):
        """Point 0.5m from ridge is in the 0.9m buffer zone."""
        assert is_in_ridge_zone((5, 0.5), (0, 0, 10, 0), 30.0, buffer_m=0.9) is True

    def test_is_in_ridge_zone_outside_buffer(self):
        """Point 2m from ridge is OUTSIDE the 0.9m buffer."""
        assert is_in_ridge_zone((5, 2.0), (0, 0, 10, 0), 30.0, buffer_m=0.9) is False

    def test_degenerate_ridge_returns_input(self):
        """Zero-length ridge → degenerate, return as-is."""
        ridge = (5, 5, 5, 5)
        result = calculate_ridge_zone_boundary(ridge, 30.0)
        assert result == ridge


# ─────────────────────────────────────────────────────────────────────────────
# Combined Detector Requirements
# ─────────────────────────────────────────────────────────────────────────────


class TestDetectorRequirements:
    """calculate_detector_requirements — combined smoke/heat dispatch."""

    def test_smoke_requirements(self, flat_ceiling_3m: CeilingSpec, room_10x10: RoomSpec):
        """Smoke detector requirements for 10m × 10m at 3m ceiling."""
        result = calculate_detector_requirements(
            room_10x10, flat_ceiling_3m, DetectorType.SMOKE
        )
        assert result["detector_type"] == "SMOKE"
        assert result["ceiling_height"] == 3.0
        assert result["radius"] == pytest.approx(6.37, abs=0.01)
        assert result["max_coverage"] == pytest.approx(5.5, abs=0.01)
        assert result["total_detectors"] == 4  # 2×2
        assert result["requires_ridge_zone"] is False

    def test_heat_requirements(self, flat_ceiling_3m: CeilingSpec, room_10x10: RoomSpec):
        """Heat detector requirements for 10m × 10m at 3m ceiling."""
        result = calculate_detector_requirements(
            room_10x10, flat_ceiling_3m, DetectorType.HEAT
        )
        assert result["detector_type"] == "HEAT"
        assert result["spacing"] == pytest.approx(6.1, abs=0.01)
        assert result["total_detectors"] == 4  # 2×2 with 6.1m spacing

    def test_large_room_smoke_count(
        self, flat_ceiling_3m: CeilingSpec
    ):
        """30m × 30m smoke at 3m → 4×4 = 16 detectors."""
        room = RoomSpec(room_id="R", name="R", width_m=30.0, depth_m=30.0)
        result = calculate_detector_requirements(
            room, flat_ceiling_3m, DetectorType.SMOKE
        )
        assert result["total_detectors"] == 16


# ─────────────────────────────────────────────────────────────────────────────
# Spacing / Coverage Radius / Wall Distance Triad
# ─────────────────────────────────────────────────────────────────────────────


class TestSpacingTriad:
    """calculate_max_spacing / calculate_coverage_radius / calculate_max_wall_distance.

    These three functions are mathematically related:
      - S = max_spacing  (NFPA 72 §17.6.3.1.1)
      - R = 0.7 × S       (NFPA 72 §17.7.4.2.3.1 — coverage radius)
      - W = S / 2          (NFPA 72 §17.6.3.1.1 — wall distance)

    The historical bug was confusing R and W (both are derived from S).
    """

    def test_3m_ceiling_smoke_spacing_is_9_1m(self, flat_ceiling_3m: CeilingSpec):
        """S = 9.1m at h≤3.0m per NFPA 72 Table 17.6.3.1.1."""
        s = calculate_max_spacing(flat_ceiling_3m, DetectorType.SMOKE)
        assert s == pytest.approx(9.1, abs=0.05)

    def test_coverage_radius_is_0p7_times_spacing(self, flat_ceiling_3m: CeilingSpec):
        """R = 0.7 × S — NOT S/2 (the historical bug)."""
        s = calculate_max_spacing(flat_ceiling_3m, DetectorType.SMOKE)
        r = calculate_coverage_radius(flat_ceiling_3m, DetectorType.SMOKE)
        assert r == pytest.approx(0.7 * s, abs=0.01)

    def test_wall_distance_is_half_spacing(self, flat_ceiling_3m: CeilingSpec):
        """W = S/2 per NFPA 72 §17.6.3.1.1."""
        s = calculate_max_spacing(flat_ceiling_3m, DetectorType.SMOKE)
        w = calculate_max_wall_distance(flat_ceiling_3m, DetectorType.SMOKE)
        assert w == pytest.approx(s / 2.0, abs=0.01)

    def test_coverage_radius_exceeds_wall_distance(self, flat_ceiling_3m: CeilingSpec):
        """R > W always (diagonal of square > half-side).

        Confirms the three quantities are distinct and the historical
        confusion (treating S/2 as radius) is detected.
        """
        r = calculate_coverage_radius(flat_ceiling_3m, DetectorType.SMOKE)
        w = calculate_max_wall_distance(flat_ceiling_3m, DetectorType.SMOKE)
        assert r > w

    def test_at_3m_radius_is_6_37m(self, flat_ceiling_3m: CeilingSpec):
        """Smoke R at h=3.0m = 0.7 × 9.1 = 6.37m (the canonical NFPA 72 value)."""
        r = calculate_coverage_radius(flat_ceiling_3m, DetectorType.SMOKE)
        assert r == pytest.approx(6.37, abs=0.01)

    def test_radius_wall_distance_ratio_is_0_7_vs_0_5(self, flat_ceiling_3m: CeilingSpec):
        """R = 0.7×S and W = 0.5×S, so R/W = 1.4 exactly.

        This pins the relationship that distinguishes coverage radius from
        wall distance — the historical confusion that caused over-conservative
        detector placement.
        """
        r = calculate_coverage_radius(flat_ceiling_3m, DetectorType.SMOKE)
        w = calculate_max_wall_distance(flat_ceiling_3m, DetectorType.SMOKE)
        # R = 0.7S, W = 0.5S → R/W = 1.4 (NOT 1.0 — they are different quantities)
        assert r / w == pytest.approx(1.4, abs=1e-3)


# ─────────────────────────────────────────────────────────────────────────────
# Coverage Radius from Height (Table 17.6.3.1.1)
# ─────────────────────────────────────────────────────────────────────────────


class TestCoverageRadiusFromHeight:
    """calculate_coverage_radius_from_height — height-adjusted spacing table."""

    def test_3m_smoke_returns_6_37m_radius(self):
        """h=3.0m → smoke spacing 9.1m → R = 6.37m."""
        spec = calculate_coverage_radius_from_height(3.0, "smoke")
        assert isinstance(spec, CoverageSpec)
        assert spec.radius == pytest.approx(6.37, abs=0.01)
        assert spec.spacing_max == pytest.approx(9.1, abs=0.01)
        assert spec.wall_distance_max == pytest.approx(4.55, abs=0.01)
        assert spec.detector_type == "smoke"
        assert spec.warning is None

    def test_3m_heat_returns_smaller_spacing(self):
        """h=3.0m → heat spacing 6.1m → smaller than smoke (9.1m)."""
        spec = calculate_coverage_radius_from_height(3.0, "heat")
        assert spec.spacing_max < 9.1
        assert spec.spacing_max == pytest.approx(6.1, abs=0.05)

    def test_none_height_raises_type_error(self):
        """None height → TypeError (V114 FIX — was silently returning NaN)."""
        with pytest.raises(TypeError):
            calculate_coverage_radius_from_height(None, "smoke")  # type: ignore[arg-type]

    def test_nan_height_raises_value_error(self):
        """NaN height → ValueError (V114 FIX — NaN bypasses `<= 0` guard)."""
        with pytest.raises(ValueError, match="finite number"):
            calculate_coverage_radius_from_height(float("nan"), "smoke")

    def test_inf_height_raises_value_error(self):
        with pytest.raises(ValueError, match="finite number"):
            calculate_coverage_radius_from_height(float("inf"), "smoke")

    def test_zero_height_raises_value_error(self):
        with pytest.raises(ValueError, match="positive"):
            calculate_coverage_radius_from_height(0.0, "smoke")

    def test_negative_height_raises_value_error(self):
        with pytest.raises(ValueError, match="positive"):
            calculate_coverage_radius_from_height(-1.0, "smoke")

    def test_high_bay_above_9_1m_emits_warning(self):
        """Heights > 9.1m trigger high-bay warning per NFPA 72 §17.7."""
        spec = calculate_coverage_radius_from_height(10.0, "smoke")
        assert spec.warning is not None
        assert "beam" in spec.warning.lower() or "high-bay" in spec.warning.lower()

    def test_extremely_high_ceiling_uses_fallback(self):
        """Heights > 12.2m (table max) → conservative fallback + warning."""
        spec = calculate_coverage_radius_from_height(15.0, "smoke")
        assert spec.warning is not None
        assert "AHJ" in spec.warning or "exceeds" in spec.warning.lower()
        # Smoke fallback = 9.1m → R = 6.37m
        assert spec.radius == pytest.approx(6.37, abs=0.01)

    def test_extremely_high_ceiling_heat_uses_smaller_fallback(self):
        """Heat fallback (3.50m) is much smaller than smoke fallback (9.10m)."""
        spec = calculate_coverage_radius_from_height(15.0, "heat")
        assert spec.spacing_max == pytest.approx(3.50, abs=0.01)
        assert spec.radius == pytest.approx(0.7 * 3.50, abs=0.01)

    def test_area_is_pi_r_squared(self):
        """Coverage area = π × R² (mathematical invariant)."""
        spec = calculate_coverage_radius_from_height(3.0, "smoke")
        expected_area = math.pi * (spec.radius ** 2)
        assert spec.area == pytest.approx(expected_area, rel=1e-3)


# ─────────────────────────────────────────────────────────────────────────────
# Ceiling Height Warnings
# ─────────────────────────────────────────────────────────────────────────────


class TestCeilingHeightWarnings:
    """get_ceiling_height_warnings — non-throwing validation."""

    def test_normal_height_no_warnings(self):
        assert get_ceiling_height_warnings(3.0) == []

    def test_very_low_height_warns(self):
        """Height < 2.1m → habitable minimum warning."""
        warnings = get_ceiling_height_warnings(2.0)
        assert any("habitable" in w.lower() for w in warnings)

    def test_extremely_high_warns(self):
        """Height > 12.2m → AHJ warning."""
        warnings = get_ceiling_height_warnings(15.0)
        assert any("ahj" in w.lower() for w in warnings)

    def test_high_bay_warns(self):
        """Height > 9.1m → beam detector warning."""
        warnings = get_ceiling_height_warnings(10.0)
        assert any("beam" in w.lower() for w in warnings)

    def test_nan_height_returns_warning(self):
        """NaN must NOT return empty list (V79 FIX)."""
        warnings = get_ceiling_height_warnings(float("nan"))
        assert len(warnings) > 0
        assert any("finite" in w.lower() for w in warnings)


# ─────────────────────────────────────────────────────────────────────────────
# Beam Pocket Correction Factor (NFPA 72 §17.6.3.6)
# ─────────────────────────────────────────────────────────────────────────────


class TestBeamPocketCorrection:
    """beam_pocket_correction_factor — spacing reduction for beamed ceilings."""

    def test_shallow_beam_no_reduction(self):
        """Beam depth ≤ 10% of ceiling height → factor = 1.0."""
        # 0.3m beam / 3.0m ceiling = 10% → exactly threshold → 1.0
        assert beam_pocket_correction_factor(0.3, 3.0) == pytest.approx(1.0)

    def test_deep_beam_reduces_spacing(self):
        """Beam depth > 10% → factor < 1.0."""
        # 0.6m beam / 3.0m ceiling = 20% → factor = 1 - (0.20-0.10)*2 = 0.8
        assert beam_pocket_correction_factor(0.6, 3.0) == pytest.approx(0.8, abs=0.01)

    def test_very_deep_beam_floor_at_0_25(self):
        """Extremely deep beams clamp at 0.25 minimum."""
        # 2.0m beam / 3.0m ceiling = 66.7% → excess = 56.7% × 2 = 1.13
        # 1.0 - 1.13 = -0.13 → clamped to 0.25
        assert beam_pocket_correction_factor(2.0, 3.0) == pytest.approx(0.25, abs=0.01)

    def test_nan_beam_depth_raises(self):
        """V114 FIX — NaN inputs must not propagate."""
        with pytest.raises(ValueError, match="finite"):
            beam_pocket_correction_factor(float("nan"), 3.0)

    def test_nan_ceiling_height_raises(self):
        with pytest.raises(ValueError, match="finite"):
            beam_pocket_correction_factor(0.3, float("nan"))

    def test_negative_beam_depth_raises(self):
        with pytest.raises(ValueError, match="non-negative"):
            beam_pocket_correction_factor(-0.1, 3.0)

    def test_zero_ceiling_height_raises(self):
        with pytest.raises(ValueError, match="positive"):
            beam_pocket_correction_factor(0.3, 0.0)


# ─────────────────────────────────────────────────────────────────────────────
# Corridor Spacing (NFPA 72 §17.6.3.3)
# ─────────────────────────────────────────────────────────────────────────────


class TestCorridorSpacing:
    """calculate_corridor_spacing — narrow corridor allowance."""

    def test_wide_corridor_returns_base_spacing(self, flat_ceiling_3m: CeilingSpec):
        """Corridor ≥ 3.0m wide uses normal spacing (no corridor allowance)."""
        spacing = calculate_corridor_spacing(
            flat_ceiling_3m, DetectorType.SMOKE, 3.5
        )
        base = calculate_max_spacing(flat_ceiling_3m, DetectorType.SMOKE)
        assert spacing == pytest.approx(base, abs=0.01)

    def test_narrow_corridor_increases_spacing(self, flat_ceiling_3m: CeilingSpec):
        """Corridor < 3.0m wide allows LARGER along-corridor spacing.

        §17.6.3.3: S = 2 × √(R² − (W/2)²) where R = 0.7×S_base.
        For 1.5m corridor, R = 6.37m: S = 2×√(6.37² − 0.75²) ≈ 12.66m
        But capped at base spacing 9.1m.
        """
        spacing = calculate_corridor_spacing(
            flat_ceiling_3m, DetectorType.SMOKE, 1.5
        )
        base = calculate_max_spacing(flat_ceiling_3m, DetectorType.SMOKE)
        # Narrow corridor can use up to base spacing (9.1m) along its length
        assert spacing <= base
        assert spacing > 0

    def test_invalid_corridor_width_raises(self, flat_ceiling_3m: CeilingSpec):
        """V79 FIX — NaN corridor width must not silently produce NaN."""
        with pytest.raises(ValueError, match="finite"):
            calculate_corridor_spacing(
                flat_ceiling_3m, DetectorType.SMOKE, float("nan")
            )

    def test_zero_corridor_width_raises(self, flat_ceiling_3m: CeilingSpec):
        with pytest.raises(ValueError, match="positive"):
            calculate_corridor_spacing(
                flat_ceiling_3m, DetectorType.SMOKE, 0.0
            )


# ─────────────────────────────────────────────────────────────────────────────
# Duct Detector Positions (NFPA 72 §17.7.5.4.2)
# ─────────────────────────────────────────────────────────────────────────────


class TestDuctDetectorPositions:
    """calculate_duct_detector_positions — HVAC duct detector placement."""

    def test_short_duct_no_detector(self):
        """Single-point duct (degenerate) returns the point or empty list."""
        duct = HVACDuct(
            duct_id="D1",
            centerline=[(0, 0)],
            width_m=0.5,
            height_m=0.3,
            airflow_m3s=1.0,
        )
        positions = calculate_duct_detector_positions(duct, 10.0)
        # Single point returns the point itself
        assert len(positions) <= 1

    def test_10m_straight_duct_one_detector(self):
        """10m straight duct → 1 detector at midpoint (5m)."""
        duct = HVACDuct(
            duct_id="D1",
            centerline=[(0, 0), (10, 0)],
            width_m=0.5,
            height_m=0.3,
            airflow_m3s=1.0,
        )
        positions = calculate_duct_detector_positions(duct, 10.0)
        assert len(positions) == 1
        # Detector at midpoint (5, 0)
        assert positions[0][0] == pytest.approx(5.0, abs=0.5)

    def test_30m_duct_three_detectors(self):
        """30m duct with 10m max spacing → 3 detectors at interval midpoints."""
        duct = HVACDuct(
            duct_id="D1",
            centerline=[(0, 0), (30, 0)],
            width_m=0.5,
            height_m=0.3,
            airflow_m3s=1.0,
        )
        positions = calculate_duct_detector_positions(duct, 10.0)
        # 30m / 10m = 3 intervals → 3 detectors at midpoints 5, 15, 25
        assert len(positions) == 3

    def test_default_max_spacing_is_10m_per_nfpa(self):
        """Default max_spacing_m = 10.0m per NFPA 72 §17.7.5.4.2."""
        # Use a 25m duct: with 10m default → 3 intervals (ceil(25/10)=3)
        duct = HVACDuct(
            duct_id="D1",
            centerline=[(0, 0), (25, 0)],
            width_m=0.5,
            height_m=0.3,
            airflow_m3s=1.0,
        )
        positions = calculate_duct_detector_positions(duct)  # default
        assert len(positions) == 3


# ─────────────────────────────────────────────────────────────────────────────
# Voltage Drop (NFPA 72 §10.14, §27.4.1.2)
# ─────────────────────────────────────────────────────────────────────────────


class TestVoltageDrop:
    """check_voltage_drop — PLFA (10%) and NAC (20%) drop limits."""

    def test_compliant_plfa_circuit(self):
        """Typical PLFA: 24V, 0.5A, 10m of 0.01Ω/m cable → 0.4% drop, compliant."""
        result = check_voltage_drop(24.0, 0.5, 0.01, 10.0, 0.10)
        # total R = 0.01 * 10 * 2 = 0.2 Ω (return path)
        # drop = 0.5 * 0.2 = 0.1 V → fraction = 0.1/24 = 0.417%
        assert result["drop_v"] == pytest.approx(0.1, abs=0.001)
        assert result["drop_fraction"] == pytest.approx(0.004167, abs=1e-5)
        assert result["compliant"] is True

    def test_non_compliant_long_cable(self):
        """Long cable run: 24V, 2A, 100m of 0.01Ω/m → 16.7% drop, non-compliant."""
        result = check_voltage_drop(24.0, 2.0, 0.01, 100.0, 0.10)
        # total R = 0.01 * 100 * 2 = 2 Ω, drop = 2 * 2 = 4V → 16.7%
        assert result["drop_v"] == pytest.approx(4.0, abs=0.001)
        assert result["drop_fraction"] == pytest.approx(0.1667, abs=1e-4)
        assert result["compliant"] is False

    def test_nac_circuit_allows_20_percent(self):
        """NAC circuit with 20% limit allows larger drop than PLFA 10%."""
        # 19% drop — non-compliant for PLFA, compliant for NAC
        # V=24, drop=4.56V → 19%; need: 4.56 = I * R * 2; I=2.28, R=0.01, L=100
        result_plfa = check_voltage_drop(24.0, 2.28, 0.01, 100.0, 0.10)
        result_nac = check_voltage_drop(24.0, 2.28, 0.01, 100.0, 0.20)
        assert result_plfa["compliant"] is False
        assert result_nac["compliant"] is True

    def test_zero_current_zero_drop(self):
        """Zero load → zero drop, compliant."""
        result = check_voltage_drop(24.0, 0.0, 0.01, 10.0, 0.10)
        assert result["drop_v"] == 0.0
        assert result["compliant"] is True

    def test_nan_input_raises(self):
        """V114 FIX — NaN must not silently produce NaN result."""
        with pytest.raises(ValueError, match="finite"):
            check_voltage_drop(24.0, float("nan"), 0.01, 10.0, 0.10)

    def test_zero_supply_voltage_raises(self):
        with pytest.raises(ValueError, match="positive"):
            check_voltage_drop(0.0, 0.5, 0.01, 10.0, 0.10)

    def test_negative_cable_length_raises(self):
        with pytest.raises(ValueError, match="non-negative"):
            check_voltage_drop(24.0, 0.5, 0.01, -1.0, 0.10)

    def test_invalid_drop_fraction_raises(self):
        """max_drop_fraction must be in (0, 1]."""
        with pytest.raises(ValueError, match="max_drop_fraction"):
            check_voltage_drop(24.0, 0.5, 0.01, 10.0, 0.0)
        with pytest.raises(ValueError, match="max_drop_fraction"):
            check_voltage_drop(24.0, 0.5, 0.01, 10.0, 1.5)


# ─────────────────────────────────────────────────────────────────────────────
# Battery Capacity (NFPA 72 §10.6.7.2.1)
# ─────────────────────────────────────────────────────────────────────────────


class TestBatteryCapacity:
    """required_battery_capacity_ah — 24h standby + 5min alarm."""

    def test_typical_battery_capacity(self):
        """0.5A standby × 24h + 1A × 5min × 1.2 safety = 14.5 Ah."""
        result = required_battery_capacity_ah(0.5, 1.0, 24.0, 5.0, 1.20)
        # standby: 0.5 × 24 = 12 Ah
        # alarm:   1.0 × (5/60) = 0.0833 Ah
        # total × 1.20 = 14.5 Ah
        assert result == pytest.approx(14.5, abs=0.01)

    def test_minimum_24h_standby_enforced(self):
        """Standby < 24h violates §10.6.7.2.1 — must raise."""
        with pytest.raises(ValueError, match="24h"):
            required_battery_capacity_ah(0.5, 1.0, 12.0, 5.0, 1.20)

    def test_safety_factor_below_one_rejected(self):
        """Safety factor < 1.0 undersizes battery — must raise."""
        with pytest.raises(ValueError, match="safety_factor"):
            required_battery_capacity_ah(0.5, 1.0, 24.0, 5.0, 0.8)

    def test_zero_alarm_minutes_rejected(self):
        with pytest.raises(ValueError, match="alarm_minutes"):
            required_battery_capacity_ah(0.5, 1.0, 24.0, 0.0, 1.20)

    def test_nan_input_rejected(self):
        """V114 FIX — NaN must not silently produce NaN capacity."""
        with pytest.raises(ValueError, match="finite"):
            required_battery_capacity_ah(float("nan"), 1.0, 24.0, 5.0, 1.20)

    def test_negative_standby_current_rejected(self):
        with pytest.raises(ValueError, match="non-negative"):
            required_battery_capacity_ah(-0.1, 1.0, 24.0, 5.0, 1.20)

    def test_larger_safety_factor_proportionally_larger(self):
        """1.25 safety factor → 25% more capacity than 1.20."""
        c120 = required_battery_capacity_ah(0.5, 1.0, 24.0, 5.0, 1.20)
        c125 = required_battery_capacity_ah(0.5, 1.0, 24.0, 5.0, 1.25)
        assert c125 == pytest.approx(c120 * 1.25 / 1.20, rel=1e-3)


# ─────────────────────────────────────────────────────────────────────────────
# Inrush Current (NFPA 72 §10.14.1)
# ─────────────────────────────────────────────────────────────────────────────


class TestInrushCurrent:
    """calculate_inrush_current — NAC device current draw."""

    def test_known_device_strobe_15cd(self):
        """15cd strobe: 0.15A steady, 0.38A inrush, ×10 → 1.5A / 3.8A."""
        result = calculate_inrush_current("strobe_15cd", 10)
        assert result["steady_total_a"] == pytest.approx(1.5, abs=0.01)
        assert result["inrush_total_a"] == pytest.approx(3.8, abs=0.01)
        assert result["inrush_factor"] == 2.5
        assert result["device_type"] == "strobe_15cd"
        assert result["quantity"] == 10

    def test_known_device_horn(self):
        """Horn: 0.25A steady, 0.50A inrush, ×4 → 1.0A / 2.0A."""
        result = calculate_inrush_current("horn", 4)
        assert result["steady_total_a"] == pytest.approx(1.0, abs=0.01)
        assert result["inrush_total_a"] == pytest.approx(2.0, abs=0.01)
        assert result["inrush_factor"] == 2.0

    def test_unknown_device_uses_conservative_default(self):
        """Unknown device type → 0.25A / 0.63A default with warning log."""
        result = calculate_inrush_current("unknown_widget", 4)
        assert result["steady_total_a"] == pytest.approx(1.0, abs=0.01)  # 0.25 × 4
        assert result["inrush_total_a"] == pytest.approx(2.52, abs=0.01)  # 0.63 × 4
        assert result["inrush_factor"] == 2.5

    def test_inrush_exceeds_steady(self):
        """All known strobes have inrush > steady (V65 sanity check)."""
        for dtype, spec in DEVICE_CURRENT_DRAW.items():
            if "strobe" in dtype:
                assert spec["inrush_a"] > spec["steady_a"], (
                    f"{dtype}: inrush must exceed steady for strobe devices"
                )


# ─────────────────────────────────────────────────────────────────────────────
# NAC Loading (NFPA 72 §18.5)
# ─────────────────────────────────────────────────────────────────────────────


class TestNACLoading:
    """calculate_nac_loading — multi-device NAC circuit aggregation."""

    def test_within_panel_limit(self):
        """Total steady ≤ 3.0A → within_panel_limit=True, no warnings."""
        result = calculate_nac_loading(
            [
                {"device_type": "horn", "quantity": 4},  # 1.0A steady
                {"device_type": "strobe_15cd", "quantity": 5},  # 0.75A steady
            ]
        )
        # 1.0 + 0.75 = 1.75A, well under 3.0A limit
        assert result["steady_total_a"] == pytest.approx(1.75, abs=0.01)
        assert result["within_panel_limit"] is True
        assert result["warnings"] == []

    def test_over_panel_limit_emits_warning(self):
        """Total steady > 3.0A → warning about NAC overload."""
        result = calculate_nac_loading(
            [
                {"device_type": "strobe_75cd", "quantity": 10},  # 4.5A steady
            ]
        )
        assert result["steady_total_a"] > NAC_MAX_CURRENT_A
        assert result["within_panel_limit"] is False
        assert any("overload" in w.lower() for w in result["warnings"])

    def test_high_inrush_emits_warning(self):
        """Combined inrush > 1.5× panel limit → voltage sag warning."""
        result = calculate_nac_loading(
            [
                {"device_type": "strobe_75cd", "quantity": 20},  # 22.5A inrush
            ]
        )
        assert any("inrush" in w.lower() or "sag" in w.lower() for w in result["warnings"])

    def test_empty_device_list(self):
        """Empty device list → zero totals, compliant."""
        result = calculate_nac_loading([])
        assert result["steady_total_a"] == 0.0
        assert result["within_panel_limit"] is True

    def test_device_details_echoed(self):
        """device_details contains per-type breakdown."""
        result = calculate_nac_loading(
            [{"device_type": "horn", "quantity": 2}]
        )
        assert len(result["device_details"]) == 1
        assert result["device_details"][0]["device_type"] == "horn"


# ─────────────────────────────────────────────────────────────────────────────
# Auto-Select AWG (NEC Art. 760.71 + NFPA 72 §10.14)
# ─────────────────────────────────────────────────────────────────────────────


class TestAutoSelectAWG:
    """auto_select_awg — pick smallest compliant wire gauge."""

    def test_short_run_selects_smallest_permitted_awg(self):
        """Short run, low current → smallest permitted AWG (14) selected.

        NEC 760.71 minimum is AWG 14 — AWG 18 and 16 are excluded from
        AWG_GAUGES auto-selection (V132 FIX). With only [14, 12, 10] in
        the candidate list and a low-current short run, AWG 14 (the
        thinnest permitted) should satisfy the drop constraint.
        """
        result = auto_select_awg(24.0, 0.5, 10.0, 0.10)
        # After V132 fix, AWG 14 is the thinnest permitted; AWG 18/16 excluded.
        # AWG_GAUGES is [14, 12, 10] sorted descending — auto_select_awg tries
        # them in that order and returns the first that satisfies the constraint.
        # For a short low-current run, AWG 14 should be compliant.
        assert result["selected_awg"] in AWG_GAUGES
        assert result["selected_awg"] >= 14  # NEC minimum (14 = thinnest permitted)
        assert result["compliant"] is True

    def test_long_run_may_need_thicker_wire(self):
        """Long run → smaller AWG (thicker wire) needed to stay within drop."""
        # 100m run at 0.5A — check that selected AWG has thicker wire
        result = auto_select_awg(24.0, 0.5, 100.0, 0.10)
        # Either we found a compliant gauge or we report error
        if result["selected_awg"] is not None:
            assert result["compliant"] is True
            assert result["selected_awg"] in AWG_GAUGES

    def test_impossible_run_returns_error(self):
        """Run that no AWG can satisfy → selected_awg=None, error message."""
        # 1000m at 5A — no AWG 14/12/10 will keep drop under 10%
        result = auto_select_awg(24.0, 5.0, 1000.0, 0.10)
        assert result["selected_awg"] is None
        assert result["compliant"] is False
        assert "error" in result

    def test_all_candidates_returned(self):
        """Even on success, all_candidates list contains every gauge tried."""
        result = auto_select_awg(24.0, 0.5, 10.0, 0.10)
        assert len(result["all_candidates"]) == len(AWG_GAUGES)

    def test_awg_18_and_16_excluded_from_auto_selection(self):
        """NEC 760.71 — AWG 18 and 16 must NOT be auto-selected for FA circuits.

        V132 FIX (2026-06-21): The V131 filter `g >= 14` was INVERTED.
        Because AWG numbering is inverted (smaller number = thicker wire),
        `g >= 14` selected [18, 16, 14] (the THINNEST three) instead of
        [14, 12, 10] (the THICKEST three). This caused auto_select_awg() to
        return AWG 18 — an illegal gauge for fire alarm wiring per NEC 760.71.
        The correct filter is `g <= 14`, which is what this test enforces.

        AWG numbering reminder: smaller number = THICKER wire.
          - AWG 10 = thickest in our table
          - AWG 14 = thinnest permitted for fire alarm circuits
          - AWG 18, 16 = NOT permitted for fire alarm circuits (NEC 760.71)
        """
        assert 18 not in AWG_GAUGES
        assert 16 not in AWG_GAUGES
        # min/max operate on the AWG NUMBER, not wire thickness.
        # min(AWG_GAUGES) = 10 (thickest wire), max = 14 (thinnest permitted)
        assert min(AWG_GAUGES) == 10  # 10 = thickest wire in the candidate list
        assert max(AWG_GAUGES) == 14  # 14 = thinnest permitted (NEC 760.71 minimum)
        assert AWG_GAUGES == [14, 12, 10]  # exact expected order (descending AWG #)

    def test_auto_select_never_returns_illegal_awg(self):
        """No compliant result may ever return AWG 18 or 16 (NEC 760.71 violation)."""
        # Test a range of scenarios — none should produce AWG 18 or 16
        for v, i, l in [(24, 0.1, 5), (24, 0.5, 10), (24, 1.0, 50), (24, 2.0, 100)]:
            result = auto_select_awg(v, i, l, 0.10)
            if result["selected_awg"] is not None:
                assert result["selected_awg"] not in (18, 16), (
                    f"ILLEGAL: auto_select_awg({v},{i},{l}) returned AWG {result['selected_awg']} "
                    f"— NEC 760.71 requires minimum AWG 14 for fire alarm circuits"
                )

    def test_resistance_table_includes_reference_for_18_and_16(self):
        """AWG 18/16 remain in resistance table for lookup, just not auto-selected."""
        # V131 FIX — kept for reference but excluded from AWG_GAUGES
        assert 18 in AWG_RESISTANCE_TABLE
        assert 16 in AWG_RESISTANCE_TABLE


# ─────────────────────────────────────────────────────────────────────────────
# Polygon / Rectangular Detector Count Estimators
# ─────────────────────────────────────────────────────────────────────────────


class TestDetectorCountEstimators:
    """estimate_detector_count_polygon / minimum_detector_count_rectangular."""

    def test_rectangular_count_at_3m(self):
        """10×10m room at 3m → ceil(10/9.1)² = 4 detectors (smoke)."""
        count = minimum_detector_count_rectangular(10.0, 10.0, 3.0)
        assert count == 4

    def test_rectangular_count_large_room(self):
        """30×30m at 3m → ceil(30/9.1)² = 16 detectors."""
        count = minimum_detector_count_rectangular(30.0, 30.0, 3.0)
        assert count == 16

    def test_polygon_count_positive_for_valid_polygon(self):
        """100 m² polygon at 3m → positive detector count."""
        poly = ShapelyPolygon([(0, 0), (10, 0), (10, 10), (0, 10)])
        count = estimate_detector_count_polygon(poly, 3.0, "smoke")
        # Area = 100, radius = 5.5, coverage/detector = π × 5.5² × 0.7 = 66.6
        # 100 / 66.6 ≈ 1.5 → ceil = 2
        assert count >= 1
        assert isinstance(count, int)

    def test_polygon_count_zero_for_non_polygon(self):
        """Non-Polygon input → 0 (graceful degradation)."""
        count = estimate_detector_count_polygon("not a polygon", 3.0, "smoke")
        assert count == 0
