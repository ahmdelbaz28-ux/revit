"""
test_regression.py — FireAI 3-Dimensional Regression Test Suite
================================================================
Prevents any future change from degrading detector placement quality
across three independent dimensions:

  Dimension 1: COVERAGE  — No regression in proof_valid or coverage_pct
  Dimension 2: NFPA 72   — No regression in nfpa_valid or wall_violations
  Dimension 3: EFFICIENCY — No unbounded increase in detector count

Plus Phase 7 critical check:
  NFPA 72 RADIUS — coverage_radius_used must match NFPA 72 Table 17.6.3.1.1
  for the room's ceiling_height and detector_type.

Baseline source: DensityOptimizer V7.3 + FloorAnalyser V2.4 (2026-05-18)
All baseline values are from the CURRENT engine — NOT from legacy v4/v6 code.

Room dimensions inspired by the original test_suite.py 10-room set,
but baseline numbers are re-measured with dynamic R from NFPA 72
Table 17.6.3.1.1 (Phase 7).

NFPA References:
  - NFPA 72 (2022) Table 17.6.3.1.1 — ceiling height / radius
  - NFPA 72 (2022) Section 17.6.3 — coverage requirement
  - NFPA 72 (2022) Section 17.7.4.2.3.1 — 0.7S rule
  - NFPA 72 (2022) Section 17.6.3.1.1 — wall distance requirements
"""
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "."))

from fireai.core.floor_analyser import FloorAnalyser, FloorReport, RoomSummary
from fireai.core.spatial_engine.density_optimizer import DensityOptimizer
from fireai.core.nfpa72_calculations import calculate_coverage_radius_from_height, CoverageSpec


# ─── Baseline data (measured from V7.3 + V2.4 on 2026-05-18) ──────────────────
# Each room's baseline was obtained by running FloorAnalyser.analyse()
# with the current engine. The max_count adds a 5% tolerance above the
# measured count to allow for legitimate algorithmic improvements while
# still catching regressions (unexpected large increases).
#
# IMPORTANT: These baselines use DYNAMIC R from NFPA 72 Table 17.6.3.1.1.
# The old test_suite.py baseline values (77, 174, 14, etc.) used R=4.57m
# and are NOT comparable — they are from a different algorithm entirely.

REGRESSION_BASELINE = {
    "version": "1.0",
    "last_updated": "2026-05-18",
    "engine": "DensityOptimizer V7.3 + FloorAnalyser V2.4",
    "note": "All values measured with dynamic R from NFPA 72 Table 17.6.3.1.1",
    "rooms": {
        "open_plan_40x20": {
            "width": 40.0, "length": 20.0, "ceiling_height": 3.0,
            "detector_type": "smoke",
            "expected_radius": 4.55,
            "baseline_count": 32,
            "max_count": 34,  # 32 * 1.05 ≈ 33.6 → 34
            "min_coverage_pct": 99.0,
            "min_efficiency_ratio": 0.30,
        },
        "warehouse_60x30": {
            "width": 60.0, "length": 30.0, "ceiling_height": 6.0,
            "detector_type": "smoke",
            "expected_radius": 3.65,
            "baseline_count": 91,
            "max_count": 96,  # 91 * 1.05 ≈ 95.55 → 96
            "min_coverage_pct": 99.0,
            "min_efficiency_ratio": 0.40,
        },
        "corridor_20x3": {
            "width": 20.0, "length": 3.0, "ceiling_height": 2.8,
            "detector_type": "smoke",
            "expected_radius": 4.55,
            "baseline_count": 4,
            "max_count": 5,
            "min_coverage_pct": 99.0,
            "min_efficiency_ratio": 0.20,
        },
        "office_10x8": {
            "width": 10.0, "length": 8.0, "ceiling_height": 3.0,
            "detector_type": "smoke",
            "expected_radius": 4.55,
            "baseline_count": 6,
            "max_count": 7,
            "min_coverage_pct": 99.0,
            "min_efficiency_ratio": 0.25,
        },
        "lobby_15x15": {
            "width": 15.0, "length": 15.0, "ceiling_height": 4.5,
            "detector_type": "smoke",
            "expected_radius": 4.10,
            "baseline_count": 16,
            "max_count": 17,
            "min_coverage_pct": 99.0,
            "min_efficiency_ratio": 0.25,
        },
        "classroom_12x9": {
            "width": 12.0, "length": 9.0, "ceiling_height": 3.0,
            "detector_type": "smoke",
            "expected_radius": 4.55,
            "baseline_count": 9,
            "max_count": 10,
            "min_coverage_pct": 99.0,
            "min_efficiency_ratio": 0.18,
        },
        "server_room_6x5": {
            "width": 6.0, "length": 5.0, "ceiling_height": 3.0,
            "detector_type": "smoke",
            "expected_radius": 4.55,
            "baseline_count": 1,
            "max_count": 2,
            "min_coverage_pct": 99.0,
            "min_efficiency_ratio": 0.50,
        },
        "stairwell_4x2": {
            "width": 4.0, "length": 2.0, "ceiling_height": 3.0,
            "detector_type": "smoke",
            "expected_radius": 4.55,
            "baseline_count": 1,
            "max_count": 2,
            "min_coverage_pct": 99.0,
            "min_efficiency_ratio": 0.50,
        },
        "cafeteria_25x18": {
            "width": 25.0, "length": 18.0, "ceiling_height": 3.5,
            "detector_type": "smoke",
            "expected_radius": 4.35,
            "baseline_count": 20,
            "max_count": 21,
            "min_coverage_pct": 99.0,
            "min_efficiency_ratio": 0.35,
        },
        "parking_50x25": {
            "width": 50.0, "length": 25.0, "ceiling_height": 3.0,
            "detector_type": "smoke",
            "expected_radius": 4.55,
            "baseline_count": 45,
            "max_count": 48,  # 45 * 1.05 ≈ 47.25 → 48
            "min_coverage_pct": 99.0,
            "min_efficiency_ratio": 0.35,
        },
    },
}


# ─── Helper ────────────────────────────────────────────────────────────────────

def _run_room(name: str, cfg: dict) -> RoomSummary:
    """Analyse a single room and return its RoomSummary."""
    opt = DensityOptimizer()
    analyser = FloorAnalyser(floor_id="REG", optimizer=opt)
    W, L, H = cfg["width"], cfg["length"], cfg["ceiling_height"]
    det_type = cfg.get("detector_type", "smoke_photoelectric")

    rooms = [
        {
            "room_id": name,
            "name": name,
            "polygon_coords": [(0, 0), (W, 0), (W, L), (0, L)],
            "ceiling_height": H,
            "detector_type": det_type,
        }
    ]
    report = analyser.analyse(rooms)
    return report.room_summaries[0]


# ═══════════════════════════════════════════════════════════════════════════════
# Dimension 1: COVERAGE — No regression in proof_valid or coverage_pct
# ═══════════════════════════════════════════════════════════════════════════════

class TestDimension1Coverage:
    """
    Coverage regression guard — every room must maintain proof_valid=True
    and coverage_pct >= the baseline minimum.

    If a future algorithmic change causes proof_valid to become False
    or coverage to drop below 99%, these tests will catch it immediately.
    """

    @pytest.mark.parametrize("name, cfg", [
        (n, c) for n, c in REGRESSION_BASELINE["rooms"].items()
    ], ids=list(REGRESSION_BASELINE["rooms"].keys()))
    def test_proof_valid(self, name, cfg):
        """Room must pass coverage proof verification (proof_valid=True)."""
        s = _run_room(name, cfg)
        assert s.proof_valid is True, (
            f"REGRESSION: Room {name} proof_valid={s.proof_valid} "
            f"(was True in baseline). Coverage: {s.coverage_pct:.2f}%"
        )

    @pytest.mark.parametrize("name, cfg", [
        (n, c) for n, c in REGRESSION_BASELINE["rooms"].items()
    ], ids=list(REGRESSION_BASELINE["rooms"].keys()))
    def test_coverage_pct_above_minimum(self, name, cfg):
        """Coverage must not drop below the baseline minimum."""
        s = _run_room(name, cfg)
        min_cov = cfg["min_coverage_pct"]
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

    If a future change violates NFPA 72 spacing or wall-distance rules,
    these tests will catch it immediately.
    """

    @pytest.mark.parametrize("name, cfg", [
        (n, c) for n, c in REGRESSION_BASELINE["rooms"].items()
    ], ids=list(REGRESSION_BASELINE["rooms"].keys()))
    def test_nfpa_valid(self, name, cfg):
        """Room must pass NFPA 72 validation (nfpa_valid=True)."""
        s = _run_room(name, cfg)
        assert s.nfpa_valid is True, (
            f"REGRESSION: Room {name} nfpa_valid={s.nfpa_valid} "
            f"(was True in baseline). Violations: {getattr(s, 'violations', [])}"
        )

    @pytest.mark.parametrize("name, cfg", [
        (n, c) for n, c in REGRESSION_BASELINE["rooms"].items()
    ], ids=list(REGRESSION_BASELINE["rooms"].keys()))
    def test_zero_wall_violations(self, name, cfg):
        """Room must have zero wall-distance violations."""
        s = _run_room(name, cfg)
        # Wall violations are tracked on the layout level; FloorAnalyser
        # doesn't expose wall_violations directly on RoomSummary,
        # but nfpa_valid encompasses wall compliance.
        # We verify via the underlying layout for completeness.
        opt = DensityOptimizer()
        from fireai.core.spatial_engine.density_optimizer import Room
        W, L, H = cfg["width"], cfg["length"], cfg["ceiling_height"]
        room = Room(name=name, width=W, length=L, ceiling_height=H)
        spec = calculate_coverage_radius_from_height(H, "smoke")
        layout = opt.optimize(room, coverage_radius=spec.radius)
        assert layout.wall_violations == 0, (
            f"REGRESSION: Room {name} has {layout.wall_violations} wall violations "
            f"(was 0 in baseline)"
        )


# ═══════════════════════════════════════════════════════════════════════════════
# Dimension 3: EFFICIENCY — No unbounded increase in detector count
# ═══════════════════════════════════════════════════════════════════════════════

class TestDimension3Efficiency:
    """
    Efficiency regression guard — detector count must not exceed the
    baseline max_count (baseline * 1.05 tolerance), and the efficiency
    ratio must not drop below the minimum threshold.

    This catches regressions where an algorithmic change causes
    significantly MORE detectors to be placed without improving coverage.

    Note: The max_count allows a 5% tolerance above the measured baseline
    to accommodate legitimate improvements that may slightly change
    the count. Any increase beyond 5% requires manual review.
    """

    @pytest.mark.parametrize("name, cfg", [
        (n, c) for n, c in REGRESSION_BASELINE["rooms"].items()
    ], ids=list(REGRESSION_BASELINE["rooms"].keys()))
    def test_detector_count_within_tolerance(self, name, cfg):
        """Detector count must not exceed baseline max_count (5% tolerance)."""
        s = _run_room(name, cfg)
        max_count = cfg["max_count"]
        baseline = cfg["baseline_count"]
        assert s.detector_count <= max_count, (
            f"REGRESSION: Room {name} detector_count={s.detector_count} "
            f"> max_count={max_count} (baseline was {baseline}, "
            f"+{((s.detector_count - baseline) / baseline * 100):.1f}% increase)"
        )

    @pytest.mark.parametrize("name, cfg", [
        (n, c) for n, c in REGRESSION_BASELINE["rooms"].items()
    ], ids=list(REGRESSION_BASELINE["rooms"].keys()))
    def test_efficiency_ratio_above_minimum(self, name, cfg):
        """Efficiency ratio must not drop below the minimum threshold."""
        s = _run_room(name, cfg)
        min_eff = cfg["min_efficiency_ratio"]
        assert s.efficiency_ratio >= min_eff, (
            f"REGRESSION: Room {name} efficiency_ratio={s.efficiency_ratio:.4f} "
            f"< minimum {min_eff}. "
            f"(detectors={s.detector_count}, LB={s.theoretical_lower_bound})"
        )

    def test_total_detector_count_summary(self):
        """
        Smoke test: total detector count across all 10 rooms should be
        within 5% of the sum of baseline counts.
        """
        total_baseline = sum(
            cfg["baseline_count"]
            for cfg in REGRESSION_BASELINE["rooms"].values()
        )
        total_max = sum(
            cfg["max_count"]
            for cfg in REGRESSION_BASELINE["rooms"].values()
        )

        total_actual = 0
        for name, cfg in REGRESSION_BASELINE["rooms"].items():
            s = _run_room(name, cfg)
            total_actual += s.detector_count

        assert total_actual <= total_max, (
            f"REGRESSION: Total detector count across 10 rooms = {total_actual} "
            f"> max tolerance {total_max} "
            f"(baseline sum = {total_baseline})"
        )


# ═══════════════════════════════════════════════════════════════════════════════
# Phase 7: NFPA 72 Radius — coverage_radius_used must match Table 17.6.3.1.1
# ═══════════════════════════════════════════════════════════════════════════════

class TestPhase7NFPA72Radius:
    """
    Critical Phase 7 regression guard: the coverage radius used for each
    room MUST match NFPA 72 Table 17.6.3.1.1 for the room's ceiling height
    and detector type.

    This is the most important regression check because:
    - A wrong radius means wrong detector count (too few = danger, too many = waste)
    - Higher ceilings MUST produce smaller radii (inverse relationship)
    - The NFPA table reference must be correctly set

    If any future change breaks the dynamic radius calculation, these
    tests will catch it immediately.
    """

    @pytest.mark.parametrize("name, cfg", [
        (n, c) for n, c in REGRESSION_BASELINE["rooms"].items()
    ], ids=list(REGRESSION_BASELINE["rooms"].keys()))
    def test_coverage_radius_matches_nfpa_table(self, name, cfg):
        """
        coverage_radius_used must exactly match NFPA 72 Table 17.6.3.1.1
        for the room's ceiling_height and detector_type.
        """
        s = _run_room(name, cfg)
        expected_radius = cfg["expected_radius"]
        assert s.coverage_radius_used == expected_radius, (
            f"REGRESSION: Room {name} coverage_radius_used={s.coverage_radius_used} "
            f"!= expected {expected_radius}m from NFPA 72 Table 17.6.3.1.1 "
            f"(ceiling_height={cfg['ceiling_height']}m)"
        )

    @pytest.mark.parametrize("name, cfg", [
        (n, c) for n, c in REGRESSION_BASELINE["rooms"].items()
    ], ids=list(REGRESSION_BASELINE["rooms"].keys()))
    def test_nfpa_table_ref_set(self, name, cfg):
        """nfpa_table_ref must reference NFPA 72-2022 Table 17.6.3.1.1."""
        s = _run_room(name, cfg)
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
        This is the core of NFPA 72 Table 17.6.3.1.1.

        Compare rooms with different ceiling heights but same detector type.
        """
        rooms_data = [
            ("low_3m",  40.0, 20.0, 3.0),
            ("mid_6m",  40.0, 20.0, 6.0),
            ("high_9m", 40.0, 20.0, 9.1),
        ]

        radii = []
        for rname, W, L, H in rooms_data:
            spec = calculate_coverage_radius_from_height(H, "smoke")
            radii.append((rname, H, spec.radius))

        # Must be strictly decreasing
        for i in range(len(radii) - 1):
            name_i, h_i, r_i = radii[i]
            name_j, h_j, r_j = radii[i + 1]
            assert r_i > r_j, (
                f"NFPA 72 VIOLATION: {name_i} (H={h_i}m, R={r_i}m) should have "
                f"LARGER radius than {name_j} (H={h_j}m, R={r_j}m). "
                f"Higher ceiling = smaller radius = more detectors."
            )

    def test_higher_ceiling_produces_more_detectors(self):
        """
        Physical invariant: higher ceilings MUST produce more detectors.
        This follows from the smaller radius requirement.
        """
        opt = DensityOptimizer()
        analyser = FloorAnalyser(floor_id="REG", optimizer=opt)

        # Same room dimensions, different ceiling heights
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

        # Strictly increasing detector count
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
    Additional regression guard: for any ceiling height, heat detector
    coverage radius must always be smaller than smoke detector radius.
    This is per NFPA 72 Table 17.6.3.1.1.
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


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
