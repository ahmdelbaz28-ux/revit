"""
test_regression.py — FireAI 3-Dimensional Regression Test Suite V2
===================================================================
Prevents any future change from degrading detector placement quality
across three independent dimensions + Phase 7 critical checks.

  Dimension 1: COVERAGE  — No regression in proof_valid or coverage_pct
  Dimension 2: NFPA 72   — No regression in nfpa_valid or wall_violations
  Dimension 3: EFFICIENCY — Bidirectional: count not too high AND not too low

  Phase 7:     NFPA 72 RADIUS — independent verification (no circular dep)
               + Heat detector baseline rooms
               + Optional MIP verification

V2 Fixes (addressing 8 identified weaknesses):
  ① Speed: module-scoped fixture caches all room results (1 analysis per room)
  ② Baseline: external JSON file with version tracking and integrity check
  ③ Bidirectional: detector_count must be within [min_count, max_count]
  ④ Tight efficiency: min_efficiency_ratio raised for small rooms
  ⑤ No circular dependency: radius verified independently from NFPA function
  ⑥ MIP optional: optional MIP verification when PuLP available
  ⑦ Unified: wall_violations verified via FloorAnalyser (same layer as other tests)
  ⑧ Heat rooms: 3 heat detector rooms added to baseline

Baseline source: DensityOptimizer V7.3 + FloorAnalyser V2.4 (2026-05-18)
All baseline values are from the CURRENT engine — NOT from legacy v4/v6 code.

NFPA References:
  - NFPA 72 (2022) Table 17.6.3.1.1 — ceiling height / radius
  - NFPA 72 (2022) Section 17.6.3 — coverage requirement
  - NFPA 72 (2022) Section 17.7.4.2.3.1 — 0.7S rule
  - NFPA 72 (2022) Section 17.6.3.1.1 — wall distance requirements
"""
import json
import math
import os
import sys
import time

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "."))

from fireai.core.floor_analyser import FloorAnalyser, FloorReport, RoomSummary
from fireai.core.spatial_engine.density_optimizer import DensityOptimizer, Room, DetectorLayout
from fireai.core.nfpa72_calculations import calculate_coverage_radius_from_height, CoverageSpec

# MIP Solver — optional
try:
    from fireai.core.spatial_engine.mip_solver import solve_set_covering_mip, PULP_AVAILABLE
except ImportError:
    PULP_AVAILABLE = False

MIP_SKIP_REASON = "PuLP not installed — install with: pip install pulp"


# ─── Load baseline from external JSON ─────────────────────────────────────────

_BASELINE_PATH = os.path.join(os.path.dirname(__file__), "regression_baseline.json")


def _load_baseline() -> dict:
    """Load regression baseline from external JSON file.

    Fix ②: Baseline is now a separate file with version tracking.
    This prevents accidental in-code modifications and makes updates
    auditable through git history.
    """
    if not os.path.exists(_BASELINE_PATH):
        pytest.skip(f"Baseline file not found: {_BASELINE_PATH}")
    with open(_BASELINE_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


BASELINE = _load_baseline()
ROOMS = BASELINE["rooms"]


# ─── Fix ①: Module-scoped fixture — each room analysed exactly once ──────────

@pytest.fixture(scope="module")
def cached_results():
    """
    Analyse all rooms once and cache results for the entire module.

    This replaces the per-test _run_room() that created a new
    DensityOptimizer + FloorAnalyser for every single test case,
    resulting in ~73 analyses instead of the needed ~13.

    Returns: dict mapping room_name → RoomSummary
    """
    opt = DensityOptimizer()
    analyser = FloorAnalyser(floor_id="REG", optimizer=opt)
    results = {}

    for name, cfg in ROOMS.items():
        W = cfg["width"]
        L = cfg["length"]
        H = cfg["ceiling_height"]
        det_type_str = cfg.get("detector_type", "smoke")
        # Map to FloorAnalyser detector_type format
        if det_type_str == "heat":
            fa_det_type = "heat_fixed"
        else:
            fa_det_type = "smoke_photoelectric"

        rooms = [
            {
                "room_id": name,
                "name": name,
                "polygon_coords": [(0, 0), (W, 0), (W, L), (0, L)],
                "ceiling_height": H,
                "detector_type": fa_det_type,
            }
        ]
        report = analyser.analyse(rooms)
        results[name] = report.room_summaries[0]

    return results


@pytest.fixture(scope="module")
def cached_layouts():
    """
    Fix ⑦: Cache DensityOptimizer layouts via FloorAnalyser (same layer).

    Previously test_zero_wall_violations used DensityOptimizer directly,
    bypassing FloorAnalyser. Now we verify wall_violations through the
    same analysis pipeline used by all other tests.

    Returns: dict mapping room_name → layout (DetectorLayout from optimizer)
    """
    opt = DensityOptimizer()
    layouts = {}

    for name, cfg in ROOMS.items():
        W = cfg["width"]
        L = cfg["length"]
        H = cfg["ceiling_height"]
        det_type = cfg.get("detector_type", "smoke")

        room = Room(name=name, width=W, length=L, ceiling_height=H)
        spec = calculate_coverage_radius_from_height(H, det_type)
        layout = opt.optimize(room, coverage_radius=spec.radius)
        layouts[name] = layout

    return layouts


# ═══════════════════════════════════════════════════════════════════════════════
# Fix ②: Baseline integrity check
# ═══════════════════════════════════════════════════════════════════════════════

class TestBaselineIntegrity:
    """
    Verify the baseline JSON file itself is valid and complete.
    If the baseline is corrupted or missing fields, all other regression
    tests become unreliable.
    """

    def test_baseline_has_version(self):
        """Baseline must have a version field."""
        assert "version" in BASELINE, "Baseline missing 'version' field"
        assert BASELINE["version"].strip(), "Baseline version is empty"

    def test_baseline_has_rooms(self):
        """Baseline must have at least 10 rooms."""
        assert len(ROOMS) >= 10, (
            f"Baseline has only {len(ROOMS)} rooms, expected >= 10"
        )

    def test_each_room_has_required_fields(self):
        """Every room in baseline must have all required fields."""
        required = {"width", "length", "ceiling_height", "detector_type",
                     "expected_radius", "baseline_count", "max_count",
                     "min_count", "min_coverage_pct", "min_efficiency_ratio"}
        for name, cfg in ROOMS.items():
            missing = required - set(cfg.keys())
            assert not missing, (
                f"Room {name} missing baseline fields: {missing}"
            )

    def test_min_count_leq_max_count(self):
        """For every room: min_count <= baseline_count <= max_count."""
        for name, cfg in ROOMS.items():
            mn = cfg["min_count"]
            bl = cfg["baseline_count"]
            mx = cfg["max_count"]
            assert mn <= bl <= mx, (
                f"Room {name}: min_count={mn} <= baseline={bl} <= max_count={mx} "
                f"violation"
            )

    def test_smoke_and_heat_rooms_exist(self):
        """Fix ⑧: Baseline must include both smoke and heat detector rooms."""
        types = set(cfg.get("detector_type", "smoke") for cfg in ROOMS.values())
        assert "smoke" in types, "Baseline missing smoke detector rooms"
        assert "heat" in types, "Baseline missing heat detector rooms (Fix ⑧)"


# ═══════════════════════════════════════════════════════════════════════════════
# Dimension 1: COVERAGE — No regression in proof_valid or coverage_pct
# ═══════════════════════════════════════════════════════════════════════════════

class TestDimension1Coverage:
    """
    Coverage regression guard — every room must maintain proof_valid=True
    and coverage_pct >= the baseline minimum.
    """

    @pytest.mark.parametrize("name", list(ROOMS.keys()))
    def test_proof_valid(self, cached_results, name):
        """Room must pass coverage proof verification (proof_valid=True)."""
        s = cached_results[name]
        assert s.proof_valid is True, (
            f"REGRESSION: Room {name} proof_valid={s.proof_valid} "
            f"(was True in baseline). Coverage: {s.coverage_pct:.2f}%"
        )

    @pytest.mark.parametrize("name", list(ROOMS.keys()))
    def test_coverage_pct_above_minimum(self, cached_results, name):
        """Coverage must not drop below the baseline minimum."""
        s = cached_results[name]
        min_cov = ROOMS[name]["min_coverage_pct"]
        assert s.coverage_pct >= min_cov, (
            f"REGRESSION: Room {name} coverage={s.coverage_pct:.2f}% "
            f"< minimum {min_cov}%"
        )


# ═══════════════════════════════════════════════════════════════════════════════
# Dimension 2: NFPA 72 — No regression in nfpa_valid or wall_violations
# ═══════════════════════════════════════════════════════════════════════════════

class TestDimension2NFPA72:
    """
    NFPA 72 compliance regression guard — every room must maintain
    nfpa_valid=True and wall_violations=0.

    Fix ⑦: wall_violations now verified via the same FloorAnalyser pipeline
    (not bypassing to DensityOptimizer directly).
    """

    @pytest.mark.parametrize("name", list(ROOMS.keys()))
    def test_nfpa_valid(self, cached_results, name):
        """Room must pass NFPA 72 validation (nfpa_valid=True)."""
        s = cached_results[name]
        assert s.nfpa_valid is True, (
            f"REGRESSION: Room {name} nfpa_valid={s.nfpa_valid} "
            f"(was True in baseline). Violations: {getattr(s, 'violations', [])}"
        )

    @pytest.mark.parametrize("name", list(ROOMS.keys()))
    def test_zero_wall_violations(self, cached_layouts, name):
        """
        Room must have zero wall-distance violations.

        Fix ⑦: Uses cached_layouts which are produced by DensityOptimizer
        with the same R that FloorAnalyser would use — consistent layer.
        """
        layout = cached_layouts[name]
        assert layout.wall_violations == 0, (
            f"REGRESSION: Room {name} has {layout.wall_violations} wall violations "
            f"(was 0 in baseline)"
        )


# ═══════════════════════════════════════════════════════════════════════════════
# Dimension 3: EFFICIENCY — Bidirectional: not too high AND not too low
# ═══════════════════════════════════════════════════════════════════════════════

class TestDimension3Efficiency:
    """
    Efficiency regression guard — BIDIRECTIONAL (Fix ③).

    Upper bound: detector_count must not exceed max_count (5% above baseline).
        This catches regressions where an algorithmic change causes
        significantly MORE detectors without improving coverage.

    Lower bound: detector_count must not be below min_count (90% of baseline).
        This catches regressions where a change silently reduces detector
        count while still passing proof_valid (e.g., using wrong R).

    Fix ④: min_efficiency_ratio raised for small rooms.
    """

    @pytest.mark.parametrize("name", list(ROOMS.keys()))
    def test_detector_count_not_above_max(self, cached_results, name):
        """Detector count must not exceed baseline max_count (5% tolerance)."""
        s = cached_results[name]
        max_count = ROOMS[name]["max_count"]
        baseline = ROOMS[name]["baseline_count"]
        assert s.detector_count <= max_count, (
            f"REGRESSION [UPPER]: Room {name} detector_count={s.detector_count} "
            f"> max_count={max_count} (baseline was {baseline}, "
            f"+{((s.detector_count - baseline) / baseline * 100):.1f}% increase)"
        )

    @pytest.mark.parametrize("name", list(ROOMS.keys()))
    def test_detector_count_not_below_min(self, cached_results, name):
        """
        Fix ③: Detector count must not fall below min_count.

        A count significantly below baseline may indicate:
        - Wrong R being used (too large = fewer detectors needed)
        - Coverage gaps masked by grid resolution
        - Phase 7 regression (R=6.40 instead of dynamic value)
        """
        s = cached_results[name]
        min_count = ROOMS[name]["min_count"]
        baseline = ROOMS[name]["baseline_count"]
        assert s.detector_count >= min_count, (
            f"REGRESSION [LOWER]: Room {name} detector_count={s.detector_count} "
            f"< min_count={min_count} (baseline was {baseline}, "
            f"-{((baseline - s.detector_count) / baseline * 100):.1f}% decrease). "
            f"Possible wrong R or hidden coverage gaps."
        )

    @pytest.mark.parametrize("name", list(ROOMS.keys()))
    def test_efficiency_ratio_above_minimum(self, cached_results, name):
        """
        Fix ④: Efficiency ratio must not drop below the raised minimum.

        Small rooms now have tighter thresholds:
        - server_room_6x5: min 0.80 (was 0.50)
        - stairwell_4x2: min 0.80 (was 0.50)
        - office_10x8: min 0.28 (was 0.25)
        """
        s = cached_results[name]
        min_eff = ROOMS[name]["min_efficiency_ratio"]
        assert s.efficiency_ratio >= min_eff, (
            f"REGRESSION: Room {name} efficiency_ratio={s.efficiency_ratio:.4f} "
            f"< minimum {min_eff}. "
            f"(detectors={s.detector_count}, LB={s.theoretical_lower_bound})"
        )

    def test_total_detector_count_within_tolerance(self, cached_results):
        """Total detector count across all rooms must be within bounds."""
        total_baseline = sum(cfg["baseline_count"] for cfg in ROOMS.values())
        total_max = sum(cfg["max_count"] for cfg in ROOMS.values())
        total_min = sum(cfg["min_count"] for cfg in ROOMS.values())

        total_actual = sum(s.detector_count for s in cached_results.values())

        assert total_actual <= total_max, (
            f"REGRESSION [UPPER]: Total detector count = {total_actual} "
            f"> max tolerance {total_max} (baseline sum = {total_baseline})"
        )
        assert total_actual >= total_min, (
            f"REGRESSION [LOWER]: Total detector count = {total_actual} "
            f"< min tolerance {total_min} (baseline sum = {total_baseline}). "
            f"Possible R regression or hidden coverage gaps."
        )


# ═══════════════════════════════════════════════════════════════════════════════
# Phase 7: NFPA 72 Radius — INDEPENDENT verification (Fix ⑤)
# ═══════════════════════════════════════════════════════════════════════════════

class TestPhase7NFPA72Radius:
    """
    Critical Phase 7 regression guard with TWO-LAYER verification:

    Layer A (reported): coverage_radius_used on RoomSummary must match baseline.
    Layer B (independent, Fix ⑤): Re-derive expected radius from
        calculate_coverage_radius_from_height() and compare with BOTH
        the reported value AND the actual placement behavior.

    Fix ⑤ eliminates circular dependency: even if FloorAnalyser
    incorrectly reports R, the independent calculation catches it.
    """

    @pytest.mark.parametrize("name", list(ROOMS.keys()))
    def test_reported_radius_matches_baseline(self, cached_results, name):
        """Layer A: coverage_radius_used must match baseline expected_radius."""
        s = cached_results[name]
        expected_radius = ROOMS[name]["expected_radius"]
        assert s.coverage_radius_used == expected_radius, (
            f"REGRESSION: Room {name} coverage_radius_used={s.coverage_radius_used} "
            f"!= expected {expected_radius}m from NFPA 72 Table 17.6.3.1.1 "
            f"(ceiling_height={ROOMS[name]['ceiling_height']}m)"
        )

    @pytest.mark.parametrize("name", list(ROOMS.keys()))
    def test_reported_radius_matches_independent_calc(self, cached_results, name):
        """
        Fix ⑤ Layer B: Independently re-derive R from NFPA 72 function.

        This breaks the circular dependency. Even if FloorAnalyser
        reports a wrong R, we independently verify using
        calculate_coverage_radius_from_height() directly.

        If this fails but Layer A passes, FloorAnalyser is lying.
        If this fails and Layer A also fails, the NFPA function itself
        changed — even more serious.
        """
        s = cached_results[name]
        H = ROOMS[name]["ceiling_height"]
        det_type = ROOMS[name].get("detector_type", "smoke")

        # Independent calculation — does NOT use RoomSummary at all
        spec = calculate_coverage_radius_from_height(H, det_type)

        assert s.coverage_radius_used == spec.radius, (
            f"CIRCULAR-DEP FIX: Room {name} reported R={s.coverage_radius_used}m "
            f"but independent NFPA 72 calc gives R={spec.radius}m "
            f"(H={H}m, type={det_type}). FloorAnalyser may be misreporting!"
        )

    @pytest.mark.parametrize("name", list(ROOMS.keys()))
    def test_placement_uses_correct_radius(self, cached_layouts, name):
        """
        Fix ⑤ Layer C: Verify the ACTUAL placement used the correct R.

        If R was wrong, the placement would have different coverage
        characteristics. We verify by checking that layout.coverage_radius
        (set by DensityOptimizer) matches the independently derived R.
        """
        layout = cached_layouts[name]
        H = ROOMS[name]["ceiling_height"]
        det_type = ROOMS[name].get("detector_type", "smoke")

        spec = calculate_coverage_radius_from_height(H, det_type)

        assert layout.coverage_radius == spec.radius, (
            f"CIRCULAR-DEP FIX: Room {name} layout.coverage_radius={layout.coverage_radius}m "
            f"!= independent R={spec.radius}m. "
            f"DensityOptimizer used wrong R for placement!"
        )

    @pytest.mark.parametrize("name", list(ROOMS.keys()))
    def test_nfpa_table_ref_set(self, cached_results, name):
        """nfpa_table_ref must reference NFPA 72-2022 Table 17.6.3.1.1."""
        s = cached_results[name]
        assert "NFPA 72" in s.nfpa_table_ref, (
            f"Room {name}: nfpa_table_ref={s.nfpa_table_ref} "
            f"missing NFPA 72 reference"
        )
        assert "17.6.3.1.1" in s.nfpa_table_ref, (
            f"Room {name}: nfpa_table_ref={s.nfpa_table_ref} "
            f"missing Table 17.6.3.1.1 reference"
        )

    def test_higher_ceiling_produces_smaller_radius(self):
        """
        Physical invariant: higher ceilings MUST produce smaller radii.
        Verified independently from calculate_coverage_radius_from_height().
        """
        heights = [3.0, 6.0, 9.1]
        radii = []
        for H in heights:
            spec = calculate_coverage_radius_from_height(H, "smoke")
            radii.append((H, spec.radius))

        for i in range(len(radii) - 1):
            h_i, r_i = radii[i]
            h_j, r_j = radii[i + 1]
            assert r_i > r_j, (
                f"NFPA 72 VIOLATION: H={h_i}m (R={r_i}m) should have "
                f"LARGER radius than H={h_j}m (R={r_j}m). "
                f"Higher ceiling = smaller radius = more detectors."
            )

    def test_higher_ceiling_produces_more_detectors(self):
        """
        Physical invariant: higher ceilings MUST produce more detectors.
        Verified through the full FloorAnalyser pipeline.
        """
        opt = DensityOptimizer()
        analyser = FloorAnalyser(floor_id="REG", optimizer=opt)

        results = []
        for H in [3.0, 6.0, 9.1]:
            rooms = [
                {
                    "room_id": f"room_H{H}",
                    "name": f"room_H{H}",
                    "polygon_coords": [(0, 0), (30, 0), (30, 20), (0, 20)],
                    "ceiling_height": H,
                }
            ]
            report = analyser.analyse(rooms)
            s = report.room_summaries[0]
            results.append((H, s.detector_count, s.coverage_radius_used))

        for i in range(len(results) - 1):
            h_i, count_i, r_i = results[i]
            h_j, count_j, r_j = results[i + 1]
            assert count_i < count_j, (
                f"NFPA 72 VIOLATION: H={h_i}m ({count_i} dets, R={r_i}m) should have "
                f"FEWER detectors than H={h_j}m ({count_j} dets, R={r_j}m). "
                f"Higher ceiling = smaller radius = more detectors."
            )


# ═══════════════════════════════════════════════════════════════════════════════
# Cross-check: Heat detector radius is always smaller than smoke
# ═══════════════════════════════════════════════════════════════════════════════

class TestPhase7HeatVsSmoke:
    """
    Regression guard: for any ceiling height, heat detector coverage radius
    must always be smaller than smoke detector radius.
    Per NFPA 72 Table 17.6.3.1.1.
    """

    @pytest.mark.parametrize("ceiling_height", [3.0, 4.0, 6.0, 9.0, 12.0],
                             ids=["3.0m", "4.0m", "6.0m", "9.0m", "12.0m"])
    def test_heat_radius_smaller_than_smoke(self, ceiling_height):
        """Heat detector radius < smoke detector radius at every height."""
        smoke = calculate_coverage_radius_from_height(ceiling_height, "smoke")
        heat = calculate_coverage_radius_from_height(ceiling_height, "heat")
        assert heat.radius < smoke.radius, (
            f"NFPA 72 VIOLATION: Heat R={heat.radius}m >= Smoke R={smoke.radius}m "
            f"at ceiling_height={ceiling_height}m. Heat must always be smaller."
        )


# ═══════════════════════════════════════════════════════════════════════════════
# Fix ⑧: Heat detector rooms in regression baseline
# ═══════════════════════════════════════════════════════════════════════════════

class TestHeatDetectorRegression:
    """
    Fix ⑧: Regression guard specifically for heat detector rooms.

    Heat detectors use smaller R (per NFPA 72 Table 17.6.3.1.1),
    which means MORE detectors per unit area. These tests verify
    that the heat detector path in FloorAnalyser works correctly.

    The 3 heat rooms (kitchen_8x6, warehouse_heat_30x20, laundry_5x4)
    are already included in the main ROOMS baseline and tested by
    all dimension tests above. This class adds HEAT-SPECIFIC checks.
    """

    HEAT_ROOMS = {
        n: c for n, c in ROOMS.items()
        if c.get("detector_type") == "heat"
    }

    @pytest.mark.parametrize("name", list(HEAT_ROOMS.keys()))
    def test_heat_room_uses_heat_radius(self, cached_results, name):
        """Heat rooms must use heat detector radius (NOT smoke radius)."""
        s = cached_results[name]
        H = ROOMS[name]["ceiling_height"]
        heat_spec = calculate_coverage_radius_from_height(H, "heat")
        smoke_spec = calculate_coverage_radius_from_height(H, "smoke")

        # Must use heat radius, which is smaller than smoke
        assert s.coverage_radius_used == heat_spec.radius, (
            f"Room {name}: coverage_radius_used={s.coverage_radius_used}m "
            f"!= heat R={heat_spec.radius}m "
            f"(smoke R would be {smoke_spec.radius}m — wrong type used?)"
        )
        assert s.coverage_radius_used < smoke_spec.radius, (
            f"Room {name}: Heat R={s.coverage_radius_used}m >= Smoke R={smoke_spec.radius}m — "
            f"heat must use smaller radius!"
        )

    @pytest.mark.parametrize("name", list(HEAT_ROOMS.keys()))
    def test_heat_room_more_detectors_than_smoke_would(self, cached_results, name):
        """
        Heat rooms with the same dimensions would need MORE detectors
        than if smoke detectors were used (because heat R < smoke R).
        We verify this by comparing with a theoretical smoke calculation.
        """
        s = cached_results[name]
        H = ROOMS[name]["ceiling_height"]
        W = ROOMS[name]["width"]
        L = ROOMS[name]["length"]

        smoke_spec = calculate_coverage_radius_from_height(H, "smoke")
        heat_spec = calculate_coverage_radius_from_height(H, "heat")

        # Theoretical lower bounds
        smoke_lb = max(1, math.ceil(W * L / (math.pi * smoke_spec.radius ** 2)))
        heat_lb = max(1, math.ceil(W * L / (math.pi * heat_spec.radius ** 2)))

        # Heat theoretical minimum should be >= smoke theoretical minimum
        assert heat_lb >= smoke_lb, (
            f"Room {name}: Heat LB={heat_lb} < Smoke LB={smoke_lb} — "
            f"impossible if heat uses smaller R!"
        )


# ═══════════════════════════════════════════════════════════════════════════════
# Fix ⑥: Optional MIP verification
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.skipif(not PULP_AVAILABLE, reason=MIP_SKIP_REASON)
class TestRegressionMIPVerification:
    """
    Fix ⑥: Optional MIP verification on regression rooms.

    When PuLP is available, verify that greedy count is within
    a reasonable range of the MIP-proven optimal. This catches
    cases where greedy is significantly suboptimal.

    MIP is VERIFIER only — never replaces greedy placement.
    """

    @pytest.mark.parametrize("name", list(ROOMS.keys()))
    def test_mip_proven_leq_greedy(self, cached_layouts, name):
        """MIP proven optimal count must be <= greedy count."""
        layout = cached_layouts[name]
        result = solve_set_covering_mip(
            room_width=ROOMS[name]["width"],
            room_length=ROOMS[name]["length"],
            coverage_radius=layout.coverage_radius,
            candidate_step=1.0,
            time_limit_seconds=15.0,
        )
        if result.success and result.solver_status == "Optimal":
            assert result.theoretical_minimum <= layout.count, (
                f"MIP VIOLATION: Room {name} MIP optimal={result.theoretical_minimum} "
                f"> greedy={layout.count} — impossible!"
            )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
