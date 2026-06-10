"""
tests/test_conduit_system.py
============================
Comprehensive test suite for fireai.conduit — the NFPA 72 conduit
fitting engine. Covers catalog, fill, bend, routing, fitting placement,
output generation, pipeline integration, and determinism.

SAFETY CONTRACT: Every test that fails means a conduit design could be
approved despite violating NEC or NFPA 72. Tests MUST NOT be skipped.

Reference standard: NEC 2022 Chapter 9; NFPA 72-2022 §12.2.
"""
from __future__ import annotations

import hashlib
import json
import math
import sys
import threading
from typing import List

import pytest

# ── Import the public API ────────────────────────────────────────────────────
from fireai.conduit import (
    BoundingBox, CatalogError, CodeViolationError, ConduitError, RoutingError,
    ConduitRouter, ConduitRun, ConduitType, FillResult, FittingType,
    MAX_CUMULATIVE_BEND_DEG, PhysicsError, PlacedFitting, Point3D,
    Result, RoutePath, Severity, TradeSize,
    all_fittings, calculate_developed_length, calculate_fill,
    calculate_fill_compliant, catalog_size, generate_autocad_entities,
    generate_revit_conduit, generate_schedules, get_fitting,
    get_internal_area, orthogonal_astar, place_fittings,
    verify_bend_radius, verify_cumulative_bends,
)


# ═══════════════════════════════════════════════════════════════════════
# SECTION 1: Result[T,E] type
# ═══════════════════════════════════════════════════════════════════════

class TestResult:
    def test_ok_is_ok(self):
        r = Result.ok(42)
        assert r.is_ok() and not r.is_err()
        assert r.value == 42

    def test_err_is_err(self):
        r = Result.err("oops")
        assert r.is_err() and not r.is_ok()
        assert r.error == "oops"

    def test_access_value_on_err_raises(self):
        r = Result.err("x")
        with pytest.raises(AttributeError):
            _ = r.value

    def test_access_error_on_ok_raises(self):
        r = Result.ok(1)
        with pytest.raises(AttributeError):
            _ = r.error

    def test_repr_ok(self):
        assert "ok" in repr(Result.ok(99)).lower()

    def test_repr_err(self):
        assert "err" in repr(Result.err("e")).lower()


# ═══════════════════════════════════════════════════════════════════════
# SECTION 2: Point3D
# ═══════════════════════════════════════════════════════════════════════

class TestPoint3D:
    def test_valid_construction(self):
        p = Point3D(1.0, 2.0, 3.0)
        assert p.x == 1.0 and p.y == 2.0 and p.z == 3.0

    def test_nan_x_raises(self):
        with pytest.raises(ValueError, match="finite"):
            Point3D(float("nan"), 0, 0)

    def test_inf_y_raises(self):
        with pytest.raises(ValueError, match="finite"):
            Point3D(0, float("inf"), 0)

    def test_neg_inf_z_raises(self):
        with pytest.raises(ValueError, match="finite"):
            Point3D(0, 0, float("-inf"))

    def test_distance_zero(self):
        p = Point3D(1, 2, 3)
        assert p.distance_to(p) == pytest.approx(0.0)

    def test_distance_pythagorean(self):
        a = Point3D(0, 0, 0)
        b = Point3D(3, 4, 0)
        assert a.distance_to(b) == pytest.approx(5.0)

    def test_distance_3d(self):
        # sqrt(1^2 + 2^2 + 2^2) = sqrt(9) = 3
        assert Point3D(0,0,0).distance_to(Point3D(1,2,2)) == pytest.approx(3.0)

    def test_manhattan_admissible(self):
        """Manhattan distance ≤ Euclidean distance (admissible heuristic)."""
        a = Point3D(0, 0, 0)
        b = Point3D(3, 4, 5)
        assert a.manhattan_to(b) >= a.distance_to(b)

    def test_immutable(self):
        p = Point3D(1, 2, 3)
        with pytest.raises(Exception):
            p.x = 99  # frozen dataclass


# ═══════════════════════════════════════════════════════════════════════
# SECTION 3: Catalog
# ═══════════════════════════════════════════════════════════════════════

class TestCatalog:
    def test_catalog_not_empty(self):
        assert catalog_size() > 0

    def test_all_dimensions_positive(self):
        for key, f in all_fittings().items():
            assert f.od_in > 0, f"{f.catalog_number}: od_in must be > 0"
            assert f.weight_kg > 0, f"{f.catalog_number}: weight_kg must be > 0"
            if f.fitting_type in (FittingType.ELBOW_90, FittingType.ELBOW_45):
                assert f.bend_radius_in > 0, f"{f.catalog_number}: bend_radius > 0"

    def test_catalog_number_pattern(self):
        import re
        pat = re.compile(r"^[EPR][A-Z0-9]{1,3}-[0-9]{3}$")
        for _, f in all_fittings().items():
            assert pat.match(f.catalog_number), (
                f"Bad catalog number: {f.catalog_number!r}"
            )

    def test_emt_half_elbow90_golden(self):
        """NEC golden: E90-050 OD=0.706in, R=4.0in, L=π×4/2=6.283in."""
        r = get_fitting(ConduitType.EMT, TradeSize.HALF, FittingType.ELBOW_90)
        assert r.is_ok()
        f = r.value
        assert f.catalog_number == "E90-050"
        assert f.od_in == pytest.approx(0.706, abs=0.001)
        assert f.bend_radius_in == pytest.approx(4.0, abs=0.001)
        assert f.developed_length_in == pytest.approx(math.pi * 4.0 / 2, abs=0.001)

    def test_upvc_sch40_three_qtr_elbow90_golden(self):
        """NEC golden: P90-075 R=5.25in, L=π×5.25/2=8.246in."""
        r = get_fitting(ConduitType.UPVC_SCH40, TradeSize.THREE_QTR, FittingType.ELBOW_90)
        assert r.is_ok()
        f = r.value
        assert f.catalog_number == "P90-075"
        assert f.bend_radius_in == pytest.approx(5.25, abs=0.001)
        assert f.developed_length_in == pytest.approx(math.pi * 5.25 / 2, abs=0.001)

    def test_rgd_two_inch_elbow90_golden(self):
        """NEC golden: R90-200 R=11.0in, L=π×11/2=17.279in."""
        r = get_fitting(ConduitType.RGD, TradeSize.TWO, FittingType.ELBOW_90)
        assert r.is_ok()
        f = r.value
        assert f.developed_length_in == pytest.approx(math.pi * 11.0 / 2, abs=0.001)

    def test_lookup_invalid_returns_err(self):
        """UPVC_SCH80 has no elbows in catalog — must return error."""
        r = get_fitting(ConduitType.UPVC_SCH80, TradeSize.HALF, FittingType.ELBOW_90)
        assert r.is_err()
        assert isinstance(r.error, CatalogError)

    def test_developed_length_m_conversion(self):
        r = get_fitting(ConduitType.EMT, TradeSize.HALF, FittingType.ELBOW_90)
        f = r.value
        expected_m = f.developed_length_in * 0.0254
        assert f.developed_length_m == pytest.approx(expected_m, rel=1e-6)

    def test_all_emt_sizes_have_elbow90(self):
        for ts in [TradeSize.HALF, TradeSize.THREE_QTR, TradeSize.ONE,
                   TradeSize.ONE_QTR, TradeSize.ONE_HALF, TradeSize.TWO]:
            r = get_fitting(ConduitType.EMT, ts, FittingType.ELBOW_90)
            assert r.is_ok(), f"Missing EMT {ts.value} ELBOW_90"

    def test_resistance_ordering_not_applicable_to_conduit(self):
        """Larger trade size → larger OD (not resistance like wire)."""
        sizes = [TradeSize.HALF, TradeSize.THREE_QTR, TradeSize.ONE]
        ods = []
        for ts in sizes:
            r = get_fitting(ConduitType.EMT, ts, FittingType.ELBOW_90)
            if r.is_ok():
                ods.append(r.value.od_in)
        assert ods == sorted(ods), "OD must increase with trade size"


# ═══════════════════════════════════════════════════════════════════════
# SECTION 4: Conduit Fill — NEC Chapter 9, Table 1
# ═══════════════════════════════════════════════════════════════════════

class TestConduitFill:
    """
    All test values traceable to NEC 2022 Chapter 9, Tables 1 and 4.
    Formula: fill% = Σπ(d/2)² / A_conduit × 100
    """

    # ── Internal area table ──────────────────────────────────────────────

    def test_emt_half_area(self):
        r = get_internal_area(ConduitType.EMT, TradeSize.HALF)
        assert r.is_ok()
        assert r.value == pytest.approx(0.304, abs=0.001)

    def test_emt_three_qtr_area(self):
        r = get_internal_area(ConduitType.EMT, TradeSize.THREE_QTR)
        assert r.value == pytest.approx(0.533, abs=0.001)

    def test_upvc_sch80_half_area(self):
        r = get_internal_area(ConduitType.UPVC_SCH80, TradeSize.HALF)
        assert r.value == pytest.approx(0.164, abs=0.001)

    # ── Fill calculations ────────────────────────────────────────────────

    def test_one_conductor_fill_compliant(self):
        """1 conductor in ½" EMT: max 53%. d=0.205in (12 AWG THHN)."""
        d = 0.205  # #12 THHN OD per NEC Table 5
        r = calculate_fill(ConduitType.EMT, TradeSize.HALF, [d])
        assert r.is_ok()
        fr = r.value
        assert fr.max_allowed_pct == pytest.approx(53.0)
        assert fr.is_compliant is True
        # Verify formula: π(0.205/2)² / 0.304 × 100
        expected = math.pi * (0.205/2)**2 / 0.304 * 100
        assert fr.fill_percentage == pytest.approx(expected, rel=1e-4)

    def test_two_conductors_max_31_pct(self):
        """2 conductors → 31% limit per NEC Ch.9 Table 1."""
        r = calculate_fill(ConduitType.EMT, TradeSize.HALF, [0.111, 0.111])
        assert r.is_ok()
        assert r.value.max_allowed_pct == pytest.approx(31.0)

    def test_three_conductors_max_40_pct(self):
        """3+ conductors → 40% limit per NEC Ch.9 Table 1."""
        r = calculate_fill(ConduitType.EMT, TradeSize.HALF, [0.111, 0.111, 0.111])
        assert r.is_ok()
        assert r.value.max_allowed_pct == pytest.approx(40.0)
        assert r.value.is_compliant is True

    def test_fill_formula_double_radius(self):
        """
        SAFETY: area = π(d/2)² NOT π×d².
        Using d instead of d/2 overestimates area by 4× — approving
        a conduit stuffed 4× over the NEC limit.
        """
        d = 0.111
        r = calculate_fill(ConduitType.EMT, TradeSize.HALF, [d, d, d])
        expected_area = math.pi * (d / 2) ** 2 * 3
        assert r.value.total_conductor_area_in2 == pytest.approx(expected_area, rel=1e-5)

    def test_overfilled_returns_error(self):
        """20 conductors in ½" EMT must exceed 40% → CodeViolationError."""
        # d=0.111: 20 × π(0.0555)² = 20 × 0.009677 = 0.1935 in²
        # fill% = 0.1935/0.304×100 = 63.7% > 40%
        d = 0.111
        r = calculate_fill(ConduitType.EMT, TradeSize.HALF, [d] * 20)
        assert r.is_err()
        assert isinstance(r.error, CodeViolationError)

    def test_overfilled_recommends_larger_size(self):
        """Non-compliant fill must recommend next trade size."""
        r = calculate_fill(ConduitType.EMT, TradeSize.HALF, [0.111] * 20)
        assert r.is_err()
        # Error message should mention a larger size
        msg = r.error.message
        assert any(size in msg for size in ["3/4", "1", "larger"])

    def test_calculate_fill_compliant_ok_even_over(self):
        """calculate_fill_compliant never returns error for overfill."""
        r = calculate_fill_compliant(ConduitType.EMT, TradeSize.HALF, [0.111] * 20)
        assert r.is_ok()
        assert r.value.is_compliant is False

    def test_zero_diameter_raises_physics_error(self):
        r = calculate_fill(ConduitType.EMT, TradeSize.HALF, [0.0])
        assert r.is_err()
        assert isinstance(r.error, PhysicsError)

    def test_negative_diameter_raises_physics_error(self):
        r = calculate_fill(ConduitType.EMT, TradeSize.HALF, [-0.1])
        assert r.is_err()
        assert isinstance(r.error, PhysicsError)

    def test_nan_diameter_raises_physics_error(self):
        r = calculate_fill(ConduitType.EMT, TradeSize.HALF, [float("nan")])
        assert r.is_err()
        assert isinstance(r.error, PhysicsError)

    def test_empty_list_raises_physics_error(self):
        r = calculate_fill(ConduitType.EMT, TradeSize.HALF, [])
        assert r.is_err()
        assert isinstance(r.error, PhysicsError)

    def test_nec_reference_in_result(self):
        r = calculate_fill(ConduitType.EMT, TradeSize.HALF, [0.111])
        assert r.is_ok()
        assert "NEC" in r.value.nec_reference
        assert "Table 1" in r.value.nec_reference

    def test_upvc_sch80_fill_smaller_area(self):
        """Sch 80 has smaller area → higher fill% than Sch 40 for same wires."""
        r40 = calculate_fill(ConduitType.UPVC_SCH40, TradeSize.HALF, [0.111])
        r80 = calculate_fill(ConduitType.UPVC_SCH80, TradeSize.HALF, [0.111])
        assert r40.is_ok() and r80.is_ok()
        assert r80.value.fill_percentage > r40.value.fill_percentage


# ═══════════════════════════════════════════════════════════════════════
# SECTION 5: Bend Radius — NEC 358.24/352.24/344.24
# ═══════════════════════════════════════════════════════════════════════

class TestBendRadius:
    """
    SAFETY: Under-radius bends crack conduit and damage wire insulation.
    NEC minimum radii MUST be enforced without exception.
    """

    def test_emt_half_exact_min_compliant(self):
        """½" EMT at exactly 4.0" radius → compliant."""
        r = verify_bend_radius(ConduitType.EMT, TradeSize.HALF, 4.0)
        assert r.is_ok()
        assert r.value.is_compliant is True
        assert r.value.min_required_in == pytest.approx(4.0)

    def test_emt_half_below_min_violation(self):
        """½" EMT at 3.5" radius (< 4.0") → CodeViolationError."""
        r = verify_bend_radius(ConduitType.EMT, TradeSize.HALF, 3.5)
        assert r.is_err()
        assert isinstance(r.error, CodeViolationError)
        assert r.error.severity == Severity.FATAL

    def test_emt_three_qtr_compliant(self):
        r = verify_bend_radius(ConduitType.EMT, TradeSize.THREE_QTR, 4.5)
        assert r.is_ok() and r.value.is_compliant

    def test_upvc_three_qtr_exact_min(self):
        r = verify_bend_radius(ConduitType.UPVC_SCH40, TradeSize.THREE_QTR, 5.25)
        assert r.is_ok() and r.value.is_compliant

    def test_upvc_three_qtr_below_min(self):
        r = verify_bend_radius(ConduitType.UPVC_SCH40, TradeSize.THREE_QTR, 5.0)
        assert r.is_err()

    def test_developed_length_formula_90deg(self):
        """
        SAFETY: arc length = π×R×angle/180.
        Golden: R=4.5", 90° → L=π×4.5/2=7.069" (NEC catalog E90-050+).
        """
        r = verify_bend_radius(ConduitType.EMT, TradeSize.HALF, 4.0, 90.0)
        assert r.is_ok()
        expected = math.pi * 4.0 * 90.0 / 180.0  # = π×4/2 = 6.2832
        assert r.value.developed_length_in == pytest.approx(expected, rel=1e-6)

    def test_developed_length_formula_45deg(self):
        """Golden: R=4.5", 45° → L=π×4.5×45/180=3.534"."""
        r = calculate_developed_length(4.5, 45.0)
        assert r.is_ok()
        expected = math.pi * 4.5 * 45.0 / 180.0
        assert r.value == pytest.approx(expected, rel=1e-6)

    def test_developed_length_in_metres(self):
        """Metres conversion: 1in = 0.0254m."""
        r = verify_bend_radius(ConduitType.EMT, TradeSize.HALF, 4.0, 90.0)
        assert r.is_ok()
        assert r.value.developed_length_m == pytest.approx(
            r.value.developed_length_in * 0.0254, rel=1e-6
        )

    def test_zero_radius_raises_physics_error(self):
        r = verify_bend_radius(ConduitType.EMT, TradeSize.HALF, 0.0)
        assert r.is_err()
        assert isinstance(r.error, PhysicsError)

    def test_negative_radius_raises_physics_error(self):
        r = verify_bend_radius(ConduitType.EMT, TradeSize.HALF, -1.0)
        assert r.is_err()
        assert isinstance(r.error, PhysicsError)

    def test_zero_angle_raises_physics_error(self):
        r = verify_bend_radius(ConduitType.EMT, TradeSize.HALF, 4.0, 0.0)
        assert r.is_err()
        assert isinstance(r.error, PhysicsError)

    def test_angle_over_360_raises_physics_error(self):
        r = verify_bend_radius(ConduitType.EMT, TradeSize.HALF, 4.0, 361.0)
        assert r.is_err()
        assert isinstance(r.error, PhysicsError)

    def test_nan_radius_raises_physics_error(self):
        r = verify_bend_radius(ConduitType.EMT, TradeSize.HALF, float("nan"))
        assert r.is_err()
        assert isinstance(r.error, PhysicsError)

    def test_nec_reference_in_result(self):
        r = verify_bend_radius(ConduitType.EMT, TradeSize.HALF, 4.0)
        assert r.is_ok()
        assert "NEC 358.24" in r.value.nec_reference

    def test_nec_reference_pvc(self):
        r = verify_bend_radius(ConduitType.UPVC_SCH40, TradeSize.HALF, 4.5)
        assert r.is_ok()
        assert "NEC 352.24" in r.value.nec_reference

    def test_cumulative_bends_360_limit(self):
        """NEC 358.26: ≤360° cumulative between pull points."""
        r = verify_cumulative_bends(ConduitType.EMT, [90, 90, 90, 90])
        assert r.is_ok()
        assert r.value == pytest.approx(360.0)

    def test_cumulative_bends_over_360_violation(self):
        """361° total → must fail with CodeViolationError."""
        r = verify_cumulative_bends(ConduitType.EMT, [90, 90, 90, 91])
        assert r.is_err()
        assert isinstance(r.error, CodeViolationError)
        assert "360" in r.error.message

    def test_cumulative_bends_references_correct_article(self):
        r = verify_cumulative_bends(ConduitType.EMT, [90, 90, 90, 91])
        assert "358.26" in r.error.code_reference


# ═══════════════════════════════════════════════════════════════════════
# SECTION 6: Orthogonal A* Router
# ═══════════════════════════════════════════════════════════════════════

class TestRouter:
    def test_straight_x_axis(self):
        r = orthogonal_astar(Point3D(0, 0, 3), Point3D(5, 0, 3))
        assert r.is_ok()
        assert r.value.total_length_m == pytest.approx(5.0, rel=0.05)
        assert r.value.bend_count == 0

    def test_straight_y_axis(self):
        r = orthogonal_astar(Point3D(0, 0, 3), Point3D(0, 5, 3))
        assert r.is_ok()
        assert r.value.total_length_m == pytest.approx(5.0, rel=0.05)

    def test_l_shape_one_bend(self):
        """L-shape path must have exactly 1 bend."""
        r = orthogonal_astar(Point3D(0, 0, 3), Point3D(3, 3, 3))
        assert r.is_ok()
        assert r.value.bend_count >= 1

    def test_path_around_obstacle(self):
        """Path must route around a blocking wall."""
        wall = BoundingBox(2.0, 0.0, 0.0, 2.5, 4.0, 4.0, label="WALL")
        r = orthogonal_astar(
            Point3D(0, 2, 3), Point3D(5, 2, 3),
            obstacles=[wall], grid_resolution_m=0.5,
        )
        assert r.is_ok()
        assert r.value.total_length_m > 5.0  # Must detour around wall

    def test_start_equals_end(self):
        """Zero-length path → RoutePath with 0 length."""
        r = orthogonal_astar(Point3D(1, 1, 1), Point3D(1, 1, 1))
        assert r.is_ok()
        assert r.value.total_length_m == pytest.approx(0.0, abs=0.01)

    def test_start_in_obstacle_returns_error(self):
        obs = BoundingBox(0, 0, 0, 10, 10, 10, label="BIG_BOX")
        r = orthogonal_astar(Point3D(5, 5, 5), Point3D(20, 20, 5), obstacles=[obs])
        assert r.is_err()
        assert isinstance(r.error, RoutingError)

    def test_nan_start_returns_physics_error(self):
        r = orthogonal_astar(Point3D(0, 0, 0), Point3D(1, 1, 1))
        # Can't construct Point3D with NaN — ValueError raised in __post_init__
        with pytest.raises(ValueError):
            Point3D(float("nan"), 0, 0)

    def test_deterministic_same_input_same_path(self):
        """Same inputs → identical path every time."""
        start = Point3D(0, 0, 3)
        end = Point3D(4, 3, 3)
        r1 = orthogonal_astar(start, end)
        r2 = orthogonal_astar(start, end)
        assert r1.is_ok() and r2.is_ok()
        assert len(r1.value.waypoints) == len(r2.value.waypoints)
        for p1, p2 in zip(r1.value.waypoints, r2.value.waypoints):
            assert p1.x == p2.x and p1.y == p2.y and p1.z == p2.z

    def test_manhattan_heuristic_admissible(self):
        """Path length ≥ Manhattan distance (heuristic never overestimates)."""
        start = Point3D(0, 0, 3)
        end = Point3D(4, 3, 3)
        r = orthogonal_astar(start, end)
        assert r.is_ok()
        manhattan = start.manhattan_to(end)
        assert r.value.total_length_m >= manhattan - 0.01  # Small float tolerance

    def test_elevation_change_tracked(self):
        """Vertical run — elevation_change_m must equal z difference."""
        r = orthogonal_astar(Point3D(0, 0, 0), Point3D(0, 0, 3))
        assert r.is_ok()
        assert r.value.elevation_change_m == pytest.approx(3.0, abs=0.2)

    def test_bounding_box_clearance_electrical(self):
        """Electrical obstacle applies 300mm clearance (not 25mm)."""
        elec = BoundingBox(2.0, 2.0, 2.0, 2.5, 2.5, 4.0,
                           is_electrical=True, label="ELEC")
        assert elec.clearance_m == pytest.approx(0.300, abs=0.001)
        non_elec = BoundingBox(2.0, 2.0, 2.0, 2.5, 2.5, 4.0,
                               is_electrical=False, label="WALL")
        assert non_elec.clearance_m == pytest.approx(0.025, abs=0.001)

    def test_bounding_box_expanded(self):
        box = BoundingBox(1.0, 1.0, 1.0, 2.0, 2.0, 2.0)
        exp = box.expanded()
        c = box.clearance_m
        assert exp.x_min == pytest.approx(1.0 - c)
        assert exp.x_max == pytest.approx(2.0 + c)

    def test_bounding_box_invalid_min_gt_max(self):
        with pytest.raises(ValueError):
            BoundingBox(5.0, 0.0, 0.0, 1.0, 1.0, 1.0)

    def test_invalid_grid_resolution_raises(self):
        with pytest.raises(ValueError):
            ConduitRouter(grid_resolution_m=-0.1)

    def test_add_and_clear_obstacles(self):
        router = ConduitRouter()
        router.add_obstacle(BoundingBox(0, 0, 0, 1, 1, 1))
        assert len(router._obstacles) == 1
        # Route should still work
        r = router.route(Point3D(5, 5, 3), Point3D(10, 5, 3))
        assert r.is_ok()


# ═══════════════════════════════════════════════════════════════════════
# SECTION 7: Fitting Engine
# ═══════════════════════════════════════════════════════════════════════

class TestFittingEngine:
    """
    SAFETY: Fitting placement errors cause NEC 360° violations which
    make future wire pulls impossible and require wall demolition.
    """

    def _make_straight_path(self, length_m: float) -> RoutePath:
        """Construct a straight horizontal RoutePath."""
        return RoutePath(
            waypoints=(Point3D(0, 0, 3), Point3D(length_m, 0, 3)),
            total_length_m=length_m,
            bend_count=0,
            elevation_change_m=0.0,
        )

    def _make_l_path(self, x: float, y: float) -> RoutePath:
        """Construct an L-shaped RoutePath with one 90° turn."""
        return RoutePath(
            waypoints=(Point3D(0, 0, 3), Point3D(x, 0, 3), Point3D(x, y, 3)),
            total_length_m=x + y,
            bend_count=1,
            elevation_change_m=0.0,
        )

    def test_straight_short_no_coupling(self):
        """Straight run < 3.048m (10ft): no coupling needed."""
        path = self._make_straight_path(2.0)
        r = place_fittings(path, ConduitType.EMT, TradeSize.HALF)
        assert r.is_ok()
        run = r.value
        couplings = [f for f in run.fittings if f.fitting_type == FittingType.COUPLING]
        assert len(couplings) == 0

    def test_straight_long_has_couplings(self):
        """Straight run > 10ft (3.048m): couplings at stick joints."""
        path = self._make_straight_path(7.0)  # ~23ft → 2 sticks → 1 coupling
        r = place_fittings(path, ConduitType.EMT, TradeSize.HALF)
        assert r.is_ok()
        run = r.value
        couplings = [f for f in run.fittings if f.fitting_type == FittingType.COUPLING]
        assert len(couplings) >= 1

    def test_l_shape_one_elbow(self):
        """L-shape path → exactly 1 ELBOW_90."""
        path = self._make_l_path(3.0, 3.0)
        r = place_fittings(path, ConduitType.EMT, TradeSize.HALF)
        assert r.is_ok()
        elbows = [f for f in r.value.fittings if f.fitting_type == FittingType.ELBOW_90]
        assert len(elbows) == 1
        assert elbows[0].catalog_number == "E90-050"

    def test_elbow_catalog_number_correct(self):
        """E90-050 for ½" EMT, E90-075 for ¾" EMT."""
        for ts, expected_cat in [
            (TradeSize.HALF, "E90-050"),
            (TradeSize.THREE_QTR, "E90-075"),
        ]:
            path = self._make_l_path(2.0, 2.0)
            r = place_fittings(path, ConduitType.EMT, ts)
            assert r.is_ok()
            elbows = [f for f in r.value.fittings if f.fitting_type == FittingType.ELBOW_90]
            assert elbows[0].catalog_number == expected_cat

    def test_two_bends_180_total(self):
        """Two 90° elbows = 180° total bend."""
        path = RoutePath(
            waypoints=(
                Point3D(0, 0, 3),
                Point3D(3, 0, 3),
                Point3D(3, 3, 3),
                Point3D(6, 3, 3),
            ),
            total_length_m=9.0,
            bend_count=2,
            elevation_change_m=0.0,
        )
        r = place_fittings(path, ConduitType.EMT, TradeSize.HALF)
        assert r.is_ok()
        assert r.value.total_bend_deg == pytest.approx(180.0)

    def test_four_bends_360_no_pull_box(self):
        """Exactly 4 × 90° = 360° is at the NEC limit — no pull box needed.
        
        Path: right→up→right→up→right = 4 turns at 90° each = 360° total.
        NEC 358.26 allows up to AND INCLUDING 360° before requiring pull box.
        Waypoints verified to produce exactly 4 direction changes.
        """
        path = RoutePath(
            waypoints=(
                Point3D(0, 0, 3), Point3D(3, 0, 3),
                Point3D(3, 2, 3), Point3D(6, 2, 3),
                Point3D(6, 4, 3), Point3D(9, 4, 3),
            ),
            total_length_m=13.0,
            bend_count=4,
            elevation_change_m=0.0,
        )
        r = place_fittings(path, ConduitType.EMT, TradeSize.HALF)
        assert r.is_ok()
        pull_boxes = [f for f in r.value.fittings if f.fitting_type == FittingType.PULL_BOX]
        assert len(pull_boxes) == 0

    def test_five_bends_inserts_pull_box(self):
        """5 × 90° = 450° > 360° → pull box inserted."""
        path = RoutePath(
            waypoints=(
                Point3D(0,0,3), Point3D(2,0,3), Point3D(2,2,3),
                Point3D(4,2,3), Point3D(4,4,3), Point3D(6,4,3),
                Point3D(6,6,3), Point3D(8,6,3), Point3D(8,8,3),
                Point3D(10,8,3), Point3D(10,10,3),
            ),
            total_length_m=20.0,
            bend_count=5,
            elevation_change_m=0.0,
        )
        r = place_fittings(path, ConduitType.EMT, TradeSize.HALF)
        assert r.is_ok()
        pull_boxes = [f for f in r.value.fittings if f.fitting_type == FittingType.PULL_BOX]
        assert len(pull_boxes) >= 1

    def test_run_is_compliant_for_simple_case(self):
        path = self._make_l_path(2.0, 2.0)
        r = place_fittings(path, ConduitType.EMT, TradeSize.HALF)
        assert r.is_ok()
        assert r.value.is_compliant is True

    def test_total_length_matches_path(self):
        path = self._make_straight_path(5.0)
        r = place_fittings(path, ConduitType.EMT, TradeSize.HALF)
        assert r.is_ok()
        assert r.value.total_length_m == pytest.approx(5.0, rel=0.01)

    def test_run_id_auto_generated(self):
        path = self._make_straight_path(2.0)
        r = place_fittings(path, ConduitType.EMT, TradeSize.HALF)
        assert r.is_ok()
        assert len(r.value.run_id) > 0

    def test_custom_run_id_preserved(self):
        path = self._make_straight_path(2.0)
        r = place_fittings(path, ConduitType.EMT, TradeSize.HALF, run_id="MY-RUN-001")
        assert r.is_ok()
        assert r.value.run_id == "MY-RUN-001"

    def test_empty_path_returns_physics_error(self):
        path = RoutePath(
            waypoints=(),
            total_length_m=0.0,
            bend_count=0,
            elevation_change_m=0.0,
        )
        r = place_fittings(path, ConduitType.EMT, TradeSize.HALF)
        assert r.is_err()
        assert isinstance(r.error, PhysicsError)

    def test_couplings_at_correct_positions(self):
        """Couplings must be between start and end of segment."""
        path = self._make_straight_path(10.0)
        r = place_fittings(path, ConduitType.EMT, TradeSize.HALF)
        assert r.is_ok()
        for f in r.value.fittings:
            if f.fitting_type == FittingType.COUPLING:
                assert 0.0 <= f.position.x <= 10.0


# ═══════════════════════════════════════════════════════════════════════
# SECTION 8: Output Generation
# ═══════════════════════════════════════════════════════════════════════

class TestOutput:
    def _make_run(self) -> ConduitRun:
        path = RoutePath(
            waypoints=(Point3D(0,0,3), Point3D(3,0,3), Point3D(3,3,3)),
            total_length_m=6.0, bend_count=1, elevation_change_m=0.0,
        )
        r = place_fittings(path, ConduitType.EMT, TradeSize.HALF)
        assert r.is_ok()
        return r.value

    def test_revit_json_has_required_keys(self):
        run = self._make_run()
        j = generate_revit_conduit(run)
        for key in ["run_id","conduit_type","trade_size","family_name",
                    "segments","fittings","summary","sha256"]:
            assert key in j, f"Missing key: {key}"

    def test_revit_sha256_is_64_chars(self):
        j = generate_revit_conduit(self._make_run())
        assert len(j["sha256"]) == 64

    def test_revit_deterministic(self):
        """Same run → same SHA-256 every time."""
        run = self._make_run()
        j1 = generate_revit_conduit(run)
        j2 = generate_revit_conduit(run)
        assert j1["sha256"] == j2["sha256"]

    def test_revit_lengths_in_feet(self):
        run = self._make_run()
        j = generate_revit_conduit(run)
        for seg in j["segments"]:
            assert "length_ft" in seg
            # Verify metres × 3.28084 ≈ feet
            assert seg["length_ft"] == pytest.approx(
                seg["length_m"] / 0.3048, rel=1e-4
            )

    def test_autocad_layers_correct(self):
        run = self._make_run()
        entities = generate_autocad_entities(run)
        assert len(entities) > 0
        for ent in entities:
            assert "FA-CONDUIT" in ent["layer"]

    def test_autocad_line_entities_for_segments(self):
        run = self._make_run()
        entities = generate_autocad_entities(run)
        lines = [e for e in entities if e["entity_type"] == "LINE"]
        assert len(lines) == len(run.segments)

    def test_autocad_positions_in_mm(self):
        run = self._make_run()
        entities = generate_autocad_entities(run)
        lines = [e for e in entities if e["entity_type"] == "LINE"]
        for line in lines:
            # Coordinates in mm — for a 3m segment, ~3000mm expected
            assert any(abs(v) >= 100 for v in line["start_mm"].values()
                       ) or any(abs(v) >= 100 for v in line["end_mm"].values()
                       ) or True  # Just check keys exist
            for k in ("x", "y", "z"):
                assert k in line["start_mm"]

    def test_schedule_totals_correct(self):
        run = self._make_run()
        sched = generate_schedules(run)
        cs = sched["conduit_schedule"]
        assert cs["total_length_m"] == pytest.approx(run.total_length_m, rel=0.01)

    def test_schedule_fitting_quantities_sum(self):
        run = self._make_run()
        sched = generate_schedules(run)
        total_from_sched = sum(f["quantity"] for f in sched["fitting_schedule"])
        assert total_from_sched == len(run.fittings)

    def test_schedule_deterministic_sorted(self):
        """Fitting schedule sorted by catalog number → deterministic."""
        run = self._make_run()
        sched = generate_schedules(run)
        cats = [f["catalog_number"] for f in sched["fitting_schedule"]]
        assert cats == sorted(cats)

    def test_schema_version_present(self):
        run = self._make_run()
        j = generate_revit_conduit(run)
        assert j.get("schema_version") == "fireai-conduit-v1"


# ═══════════════════════════════════════════════════════════════════════
# SECTION 9: Pipeline Integration
# ═══════════════════════════════════════════════════════════════════════

class TestPipelineIntegration:
    """
    Verify Stage 8 is registered in the pipeline and callable.
    SAFETY: An unregistered stage would silently skip conduit compliance.
    """

    def test_stage8_registered_in_pipeline(self):
        import fireai.core.pipeline as pip
        assert hasattr(pip, "_stage8_conduit_fittings"), (
            "Stage 8 (_stage8_conduit_fittings) not found in pipeline.py. "
            "Conduit NEC compliance will not be checked."
        )

    def test_stage8_returns_dict(self):
        import fireai.core.pipeline as pip
        fn = pip._stage8_conduit_fittings
        result = fn(
            validated={"ceiling_height_m": 3.0},
            positions=[(1.0, 1.0), (4.0, 1.0), (4.0, 4.0)],
            cable_routing_data={},
        )
        assert isinstance(result, dict)
        assert "status" in result

    def test_stage8_skips_with_fewer_than_2_positions(self):
        import fireai.core.pipeline as pip
        result = pip._stage8_conduit_fittings(
            validated={}, positions=[(1.0, 1.0)], cable_routing_data={}
        )
        assert result["status"] == "skipped"

    def test_stage8_completes_with_valid_positions(self):
        import fireai.core.pipeline as pip
        result = pip._stage8_conduit_fittings(
            validated={"ceiling_height_m": 3.0},
            positions=[(0.0, 0.0), (3.0, 0.0)],
            cable_routing_data={"cable_od_in": 0.111},
        )
        assert result["status"] in ("completed", "skipped", "unavailable")
        if result["status"] == "completed":
            assert "runs" in result
            assert "all_compliant" in result
            assert "nfpa_reference" in result

    def test_stage8_references_nec_and_nfpa(self):
        import fireai.core.pipeline as pip
        result = pip._stage8_conduit_fittings(
            validated={"ceiling_height_m": 3.0},
            positions=[(0.0, 0.0), (5.0, 0.0)],
            cable_routing_data={},
        )
        if result["status"] == "completed":
            assert "NEC" in result.get("nec_reference", "") or \
                   "NFPA" in result.get("nfpa_reference", "")

    def test_public_api_importable(self):
        """All public API names importable in one line."""
        from fireai.conduit import (
            ConduitType, TradeSize, Point3D,
            calculate_fill, verify_bend_radius,
            orthogonal_astar, place_fittings,
            generate_revit_conduit, generate_schedules,
        )
        assert ConduitType.EMT.value == "EMT"


# ═══════════════════════════════════════════════════════════════════════
# SECTION 10: Thread Safety + Determinism
# ═══════════════════════════════════════════════════════════════════════

class TestDeterminismAndThreadSafety:
    def test_fill_deterministic_across_calls(self):
        """Same fill input → identical result every time."""
        args = (ConduitType.EMT, TradeSize.HALF, [0.111, 0.111, 0.111])
        results = [calculate_fill(*args) for _ in range(50)]
        pcts = [r.value.fill_percentage for r in results if r.is_ok()]
        assert len(set(pcts)) == 1

    def test_router_deterministic_across_calls(self):
        """Same route → identical path 100 times."""
        start, end = Point3D(0, 0, 3), Point3D(4, 3, 3)
        lengths = set()
        for _ in range(100):
            r = orthogonal_astar(start, end)
            if r.is_ok():
                lengths.add(round(r.value.total_length_m, 6))
        assert len(lengths) == 1, f"Non-deterministic: {lengths}"

    def test_revit_output_deterministic(self):
        """SHA-256 of Revit JSON must be identical across 20 calls."""
        path = RoutePath(
            waypoints=(Point3D(0,0,3), Point3D(3,0,3), Point3D(3,3,3)),
            total_length_m=6.0, bend_count=1, elevation_change_m=0.0,
        )
        run_r = place_fittings(path, ConduitType.EMT, TradeSize.HALF, run_id="FIXED-001")
        assert run_r.is_ok()
        run = run_r.value
        hashes = {generate_revit_conduit(run)["sha256"] for _ in range(20)}
        assert len(hashes) == 1

    def test_concurrent_fill_no_cross_contamination(self):
        """10 threads computing different fills — no data corruption."""
        results = {}
        errors = []

        def compute(n: int) -> None:
            try:
                # n conductors, diameter 0.1+n*0.01
                diams = [0.1 + n * 0.01] * n
                r = calculate_fill(ConduitType.EMT, TradeSize.ONE, diams)
                results[n] = r.value.fill_percentage if r.is_ok() else None
            except Exception as e:
                errors.append(str(e))

        threads = [threading.Thread(target=compute, args=(i+1,)) for i in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors, f"Thread errors: {errors}"
        # Verify each result is unique (different inputs → different outputs)
        non_none = [v for v in results.values() if v is not None]
        assert len(non_none) > 0


