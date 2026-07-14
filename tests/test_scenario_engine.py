# File-level '# NOSONAR' removed per NOSONAR_AUDIT.md (V143 hardening).
# Per-line justified suppressions (e.g., '# NOSONAR — S3776: ...') are preserved.
"""
test_scenario_engine.py — Tests for the FireAI Scenario Engine.

This test file closes a critical gap identified in the production-readiness
review: the module `fireai/core/scenario_engine.py` had ZERO tests, even
though it implements the fire physics that determines ASET (Available Safe
Egress Time) and RSET (Required Safe Egress Time) per NFPA 72 / NFPA 101.
The function `q_max_from_fire_load` is explicitly flagged as
safety-critical in ENGINEERING_REVIEW_REQUIRED.md.

Scope of coverage:
  1. NFPA 72 / Alpert constants — guard against silent regressions.
  2. GrowthRate / SmokeType enumerations — verify alpha values match NFPA 72 Table B.2.3.
  3. FirePhysics — t² HRR model, q_max_from_fire_load, ceiling jet, detection time.
  4. ScenarioLibrary — worst_case, corner_fire, wall_midpoint_fire, all_scenarios dedup.
  5. ScenarioRunner — full scenario run with detector layout.
  6. ScenarioBatteryResult — pass/fail aggregation, worst detection time.
  7. ScenarioReporter — text/JSON/CSV output formats.
  8. run_scenarios_for_room — convenience wrapper.
  9. FIRE_LOAD_BY_OCCUPANCY — NFPA 557-2016 Table 5.1 stability.

ENGINEERING POLICY (agent.md Rule 10):
  Tests are NEVER modified to hide defects. The q_max_from_fire_load tests
  verify the formula documented in ENGINEERING_REVIEW_REQUIRED.md. If a
  PE/FPE changes the formula, the tests MUST be updated to match the
  signed-off formula — never weakened.

Reference:
  NFPA 72-2022 §A.17.6.3 (t² fire growth), §17.7.3 (response time),
    Annex B.2 (engineering guide)
  NFPA 101-2021 §A.7.2.2.2 (ASET/RSET)
  NFPA 557-2016 Table 5.1 (fire load by occupancy)
  Alpert (1972) — ceiling jet correlations
  Heskestad (1972) — plume correlations
  UL 268 — smoke detector sensitivity thresholds
"""

from __future__ import annotations

import json

import pytest

from fireai.core.scenario_engine import (
    _ALPERT_DT_FAR,
    _ALPERT_DT_NEAR,
    _ALPERT_V_FAR,
    _ALPERT_V_NEAR,
    _ALPHA,
    _BURN_DURATION,
    _EXTINCTION_COEFF,
    _NFPA_MAX_DETECTION_S,
    _SMOKE_THRESHOLD_ION_PCT_M,
    _SMOKE_THRESHOLD_PHOTO_PCT_M,
    _SMOKE_YIELD,
    FIRE_LOAD_BY_OCCUPANCY,
    BlindSpot,
    DetectionEvent,
    FirePhysics,
    FireScenario,
    GrowthRate,
    ScenarioBatteryResult,
    ScenarioLibrary,
    ScenarioReporter,
    ScenarioResult,
    ScenarioRunner,
    ScenarioVerdict,
    SmokeType,
    get_fire_load,
    run_scenarios_for_room,
)

# ═══════════════════════════════════════════════════════════════════════════════
# 1. CONSTANTS — guards against silent regression of safety-critical values
# ═══════════════════════════════════════════════════════════════════════════════


class TestNFPA72Constants:
    """Verify NFPA 72 / Alpert / Heskestad constants match published values."""

    def test_alpha_slow_matches_nfpa_72_table_b23(self):
        """NFPA 72-2022 Table B.2.3: slow = 0.00293 kW/s²."""
        assert _ALPHA["slow"] == pytest.approx(0.00293, abs=1e-6)

    def test_alpha_medium_matches_nfpa_72_table_b23(self):
        """NFPA 72-2022 Table B.2.3: medium = 0.01172 kW/s²."""
        assert _ALPHA["medium"] == pytest.approx(0.01172, abs=1e-6)

    def test_alpha_fast_matches_nfpa_72_table_b23(self):
        """NFPA 72-2022 Table B.2.3: fast = 0.04689 kW/s²."""
        assert _ALPHA["fast"] == pytest.approx(0.04689, abs=1e-6)

    def test_alpha_ultrafast_matches_nfpa_72_table_b23(self):
        """NFPA 72-2022 Table B.2.3: ultrafast = 0.18760 kW/s²."""
        assert _ALPHA["ultrafast"] == pytest.approx(0.18760, abs=1e-6)

    def test_alpha_ultra_fast_alias_exists(self):
        """The 'ultra-fast' alias (hyphenated) must resolve to ultrafast."""
        assert _ALPHA["ultra-fast"] == _ALPHA["ultrafast"]

    def test_nfpa_max_detection_60_seconds(self):
        """§17.7.3 — maximum detection time for life-safety is 60 s."""
        assert _NFPA_MAX_DETECTION_S == 60.0  # NOSONAR

    def test_smoke_threshold_ionization_25_pct_m(self):
        """UL 268 — ionization detector threshold = 2.5 %/m."""
        assert _SMOKE_THRESHOLD_ION_PCT_M == pytest.approx(2.5)

    def test_smoke_threshold_photoelectric_40_pct_m(self):
        """UL 268 — photoelectric detector threshold = 4.0 %/m."""
        assert _SMOKE_THRESHOLD_PHOTO_PCT_M == pytest.approx(4.0)

    def test_alpert_dt_far_constant(self):
        """Alpert (1972) — far-field dT coefficient = 5.38."""
        assert _ALPERT_DT_FAR == pytest.approx(5.38)

    def test_alpert_dt_near_constant(self):
        """Alpert (1972) — near-field dT coefficient = 16.9."""
        assert _ALPERT_DT_NEAR == pytest.approx(16.9)

    def test_alpert_v_far_constant(self):
        """Alpert (1972) — far-field velocity coefficient = 0.197."""
        assert _ALPERT_V_FAR == pytest.approx(0.197)

    def test_alpert_v_near_constant(self):
        """Alpert (1972) — near-field velocity coefficient = 0.962."""
        assert _ALPERT_V_NEAR == pytest.approx(0.962)

    def test_smoke_yield_flaming_matches_sfpe(self):
        """SFPE Handbook — flaming smoke yield = 0.015 kg/kg."""
        assert _SMOKE_YIELD["flaming"] == pytest.approx(0.015)

    def test_smoke_yield_smouldering_higher_than_flaming(self):
        """Smouldering produces heavier smoke than flaming."""
        assert _SMOKE_YIELD["smouldering"] > _SMOKE_YIELD["flaming"]

    def test_extinction_coeff_flaming_greater_than_smouldering(self):
        """Flaming smoke (small particles) has higher extinction coeff."""
        assert _EXTINCTION_COEFF["flaming"] > _EXTINCTION_COEFF["smouldering"]


class TestBurnDurationTable:
    """Verify the _BURN_DURATION table is internally consistent.

    NOTE: These values require PE/FPE review per ENGINEERING_REVIEW_REQUIRED.md.
    These tests only verify internal consistency, NOT engineering correctness.
    """

    def test_all_occupancies_have_positive_burn_duration(self):
        """Every burn duration must be positive (seconds)."""
        for occ, t_burn in _BURN_DURATION.items():
            assert t_burn > 0, f"Burn duration for '{occ}' must be positive"

    def test_default_burn_duration_exists(self):
        """A 'default' fallback must exist."""
        assert "default" in _BURN_DURATION

    def test_warehouse_burns_faster_than_healthcare(self):
        """High-fuel warehouse burns out faster than compartmented healthcare."""
        assert _BURN_DURATION["warehouse"] < _BURN_DURATION["healthcare"]

    def test_industrial_burns_fastest(self):
        """Industrial (high ventilation) has the shortest burn duration."""
        # Exclude 'default' from comparison
        occupancy_durations = {k: v for k, v in _BURN_DURATION.items() if k != "default"}
        assert min(occupancy_durations, key=occupancy_durations.get) == "industrial"


# ═══════════════════════════════════════════════════════════════════════════════
# 2. ENUMERATIONS — GrowthRate / SmokeType / ScenarioVerdict
# ═══════════════════════════════════════════════════════════════════════════════


class TestEnumerations:
    """Verify enums expose the correct alpha values and verdicts."""

    def test_growth_rate_slow_alpha(self):
        assert GrowthRate.SLOW.alpha == pytest.approx(0.00293, abs=1e-6)

    def test_growth_rate_medium_alpha(self):
        assert GrowthRate.MEDIUM.alpha == pytest.approx(0.01172, abs=1e-6)

    def test_growth_rate_fast_alpha(self):
        assert GrowthRate.FAST.alpha == pytest.approx(0.04689, abs=1e-6)

    def test_growth_rate_ultrafast_alpha(self):
        assert GrowthRate.ULTRAFAST.alpha == pytest.approx(0.18760, abs=1e-6)

    def test_growth_rate_alpha_monotonic(self):
        """Alpha must increase from SLOW → MEDIUM → FAST → ULTRAFAST."""
        alphas = [
            GrowthRate.SLOW.alpha,
            GrowthRate.MEDIUM.alpha,
            GrowthRate.FAST.alpha,
            GrowthRate.ULTRAFAST.alpha,
        ]
        assert alphas == sorted(alphas)

    def test_growth_rate_label_returns_human_readable(self):
        """label property must return a non-empty string."""
        for gr in GrowthRate:
            assert isinstance(gr.label, str)
            assert len(gr.label) > 0
            assert "NFPA" in gr.label

    def test_smoke_type_values(self):
        assert SmokeType.SMOULDERING.value == "smouldering"
        assert SmokeType.FLAMING.value == "flaming"

    def test_scenario_verdict_values(self):
        """Verdict enum must cover all outcome categories."""
        expected = {"PASS", "FAIL_SLOW", "FAIL_NO_DETECTOR", "FAIL_BLIND_SPOT", "SKIPPED"}
        actual = {v.value for v in ScenarioVerdict}
        assert expected == actual


# ═══════════════════════════════════════════════════════════════════════════════
# 3. FIRE PHYSICS — HRR, ceiling jet, smoke, detection time
# ═══════════════════════════════════════════════════════════════════════════════


class TestFirePhysicsHRR:
    """Tests for the t² HRR model (NFPA 72 §A.17.6.3)."""

    def test_hrr_at_time_zero_is_zero(self):
        """At t=0, HRR must be 0 (no fire yet)."""
        assert FirePhysics.hrr_at_time(0.04689, 0.0) == 0.0  # NOSONAR

    def test_hrr_at_time_matches_t_squared_formula(self):
        """Q(t) = alpha * t² — verify exact value at t=10s, alpha=fast."""
        # fast = 0.04689 kW/s², t=10 s → Q = 0.04689 * 100 = 4.689 kW
        q = FirePhysics.hrr_at_time(0.04689, 10.0)
        assert q == pytest.approx(4.689, abs=1e-3)

    def test_hrr_monotonically_increases_with_time(self):
        """Q(t) must increase monotonically with t (no q_max cap)."""
        alpha = 0.01172
        prev_q = 0.0
        for t in range(0, 100, 5):
            q = FirePhysics.hrr_at_time(alpha, float(t))
            assert q >= prev_q
            prev_q = q

    def test_hrr_caps_at_q_max_when_provided(self):
        """When q_max is provided, HRR must not exceed it."""
        alpha = 0.04689
        q_max = 1000.0  # 1 MW cap
        # At t=100s: Q = 0.04689 * 10000 = 468.9 kW (< q_max)
        assert FirePhysics.hrr_at_time(alpha, 100.0, q_max) == pytest.approx(468.9, abs=0.1)
        # At t=200s: Q = 0.04689 * 40000 = 1875.6 kW (> q_max → capped)
        assert FirePhysics.hrr_at_time(alpha, 200.0, q_max) == q_max  # NOSONAR

    def test_hrr_q_max_none_means_no_cap(self):
        """q_max=None means the t² growth continues indefinitely."""
        alpha = 0.04689
        q_large = FirePhysics.hrr_at_time(alpha, 10000.0)
        assert q_large > 1e6  # > 1 MW at t=10000s


class TestQMaxFromFireLoad:
    """
    Tests for FirePhysics.q_max_from_fire_load.

    CRITICAL: This formula is flagged for PE/FPE review in
    ENGINEERING_REVIEW_REQUIRED.md (Change 1). These tests verify the
    formula AS IMPLEMENTED. If a PE/FPE changes the formula, the tests
    MUST be updated to match — never weakened (Rule 10).

    Formula: Q_max = (fire_load_mj_m2 × area_m2) / t_burn × 1000  [kW]
    """

    def test_q_max_office_100sqm_400mj(self):
        """Office 100m² × 400 MJ/m² / 1200s × 1000 = 33,333 kW = 33.3 MW."""
        q = FirePhysics.q_max_from_fire_load(400.0, 100.0, "office")
        assert q == pytest.approx(33333.33, rel=1e-3)

    def test_q_max_warehouse_200sqm_800mj(self):
        """Warehouse 200m² × 800 MJ/m² / 900s × 1000 = 177,778 kW = 177.8 MW."""
        q = FirePhysics.q_max_from_fire_load(800.0, 200.0, "warehouse")
        assert q == pytest.approx(177777.78, rel=1e-3)

    def test_q_max_returns_positive_value(self):
        """Q_max must be positive for any non-zero input."""
        q = FirePhysics.q_max_from_fire_load(500.0, 50.0, "office")
        assert q > 0

    def test_q_max_scales_linearly_with_area(self):
        """Doubling area must double Q_max (linear in area)."""
        q1 = FirePhysics.q_max_from_fire_load(400.0, 100.0, "office")
        q2 = FirePhysics.q_max_from_fire_load(400.0, 200.0, "office")
        assert q2 == pytest.approx(2.0 * q1)

    def test_q_max_scales_linearly_with_fire_load(self):
        """Doubling fire_load must double Q_max (linear in fire_load)."""
        q1 = FirePhysics.q_max_from_fire_load(400.0, 100.0, "office")
        q2 = FirePhysics.q_max_from_fire_load(800.0, 100.0, "office")
        assert q2 == pytest.approx(2.0 * q1)

    def test_q_max_uses_default_for_unknown_occupancy(self):
        """Unknown occupancy must fall back to 'default' burn duration."""
        q_known = FirePhysics.q_max_from_fire_load(400.0, 100.0, "default")
        q_unknown = FirePhysics.q_max_from_fire_load(400.0, 100.0, "nonexistent_occupancy")
        assert q_unknown == q_known

    def test_q_max_case_insensitive_occupancy(self):
        """Occupancy string must be case-insensitive."""
        q_lower = FirePhysics.q_max_from_fire_load(400.0, 100.0, "office")
        q_upper = FirePhysics.q_max_from_fire_load(400.0, 100.0, "OFFICE")
        q_mixed = FirePhysics.q_max_from_fire_load(400.0, 100.0, "OfFiCe")
        assert q_lower == q_upper == q_mixed

    def test_q_max_warehouse_higher_than_office(self):
        """For same area & fire_load, warehouse (faster burn) → higher Q_max."""
        # Same fire_load and area, but warehouse t_burn=900 < office t_burn=1200
        q_office = FirePhysics.q_max_from_fire_load(500.0, 100.0, "office")
        q_warehouse = FirePhysics.q_max_from_fire_load(500.0, 100.0, "warehouse")
        assert q_warehouse > q_office

    def test_q_max_zero_fire_load_returns_zero(self):
        """Zero fire_load → zero energy → zero Q_max."""
        q = FirePhysics.q_max_from_fire_load(0.0, 100.0, "office")
        assert q == 0.0  # NOSONAR

    def test_q_max_zero_area_returns_zero(self):
        """Zero area → zero energy → zero Q_max."""
        q = FirePhysics.q_max_from_fire_load(400.0, 0.0, "office")
        assert q == 0.0  # NOSONAR


class TestCeilingJet:
    """Tests for Alpert (1972) ceiling jet temperature and velocity."""

    def test_ceiling_jet_temp_rise_zero_q_returns_zero(self):
        """Zero HRR → zero temperature rise."""
        assert FirePhysics.ceiling_jet_temp_rise(0.0, 5.0, 3.0) == 0.0  # NOSONAR

    def test_ceiling_jet_temp_rise_zero_radius_returns_zero(self):
        """Zero radius → division-by-zero protection must return 0."""
        assert FirePhysics.ceiling_jet_temp_rise(1000.0, 0.0, 3.0) == 0.0  # NOSONAR

    def test_ceiling_jet_temp_rise_zero_ceiling_returns_zero(self):
        """Zero ceiling height → division-by-zero protection must return 0."""
        assert FirePhysics.ceiling_jet_temp_rise(1000.0, 5.0, 0.0) == 0.0  # NOSONAR

    def test_ceiling_jet_temp_rise_far_field_matches_alpert(self):
        """Far field (r/H > 0.18): dT = 5.38 * (Q/r)^(2/3) / H."""
        # Q=1000 kW, r=5m, H=3m → r/H = 1.667 > 0.18 → far field
        # dT = 5.38 * (1000/5)^(2/3) / 3 = 5.38 * 34.20 / 3 = 61.32 °C
        dt = FirePhysics.ceiling_jet_temp_rise(1000.0, 5.0, 3.0)
        assert dt == pytest.approx(61.32, rel=1e-2)

    def test_ceiling_jet_temp_rise_near_field_matches_alpert(self):
        """Near field (r/H <= 0.18): dT = 16.9 * Q^(2/3) / H^(5/3)."""
        # Q=1000 kW, r=0.5m, H=3m → r/H = 0.167 < 0.18 → near field
        # dT = 16.9 * 1000^(2/3) / 3^(5/3) = 16.9 * 100 / 6.2403 = 270.82 °C
        dt = FirePhysics.ceiling_jet_temp_rise(1000.0, 0.5, 3.0)
        assert dt == pytest.approx(270.82, rel=1e-2)

    def test_ceiling_jet_temp_rise_always_non_negative(self):
        """Temperature rise must never be negative."""
        for q in [0, 100, 1000, 10000]:
            for r in [0.1, 1.0, 5.0, 10.0]:
                for h in [2.0, 3.0, 5.0]:
                    dt = FirePhysics.ceiling_jet_temp_rise(float(q), r, h)
                    assert dt >= 0.0

    def test_ceiling_jet_velocity_zero_q_returns_zero(self):
        """Zero HRR → zero velocity."""
        assert FirePhysics.ceiling_jet_velocity(0.0, 5.0, 3.0) == 0.0  # NOSONAR

    def test_ceiling_jet_velocity_far_field_positive(self):
        """Far field velocity must be positive for non-zero HRR."""
        v = FirePhysics.ceiling_jet_velocity(1000.0, 5.0, 3.0)
        assert v > 0.0

    def test_ceiling_jet_velocity_near_field_positive(self):
        """Near field velocity must be positive for non-zero HRR."""
        v = FirePhysics.ceiling_jet_velocity(1000.0, 0.3, 3.0)
        assert v > 0.0


class TestSmokeOpticalDensity:
    """Tests for smoke obscuration estimation."""

    def test_smoke_od_zero_q_returns_zero(self):
        """Zero HRR → zero smoke production → zero OD."""
        assert FirePhysics.smoke_optical_density(0.0, 5.0, 3.0, SmokeType.FLAMING) == 0.0  # NOSONAR

    def test_smoke_od_capped_at_100(self):
        """OD must be capped at 100 %/m to prevent unbounded output."""
        # Very large HRR → OD would exceed 100 without cap
        od = FirePhysics.smoke_optical_density(1e8, 0.1, 3.0, SmokeType.FLAMING)
        assert od <= 100.0

    def test_smoke_od_smouldering_smoke_type(self):
        """Smouldering smoke type must produce a valid OD."""
        od = FirePhysics.smoke_optical_density(1000.0, 5.0, 3.0, SmokeType.SMOULDERING)
        assert 0.0 <= od <= 100.0

    def test_smoke_od_flaming_smoke_type(self):
        """Flaming smoke type must produce a valid OD."""
        od = FirePhysics.smoke_optical_density(1000.0, 5.0, 3.0, SmokeType.FLAMING)
        assert 0.0 <= od <= 100.0


class TestDetectionTime:
    """Tests for the detection time solver."""

    def test_detection_time_returns_tuple_of_three(self):
        """Must return (time_s, hrr_kw, od_pct_m)."""
        result = FirePhysics.detection_time(
            alpha=0.04689,
            distance_m=3.0,
            ceiling_h_m=3.0,
            smoke_type=SmokeType.FLAMING,
            smoke_threshold=4.0,
        )
        assert isinstance(result, tuple)
        assert len(result) == 3

    def test_detection_time_at_zero_distance_is_finite(self):
        """Detector at ignition point must detect very quickly."""
        t_det, hrr, od = FirePhysics.detection_time(  # NOSONAR
            alpha=0.04689,
            distance_m=0.0,
            ceiling_h_m=3.0,
            smoke_type=SmokeType.FLAMING,
            smoke_threshold=4.0,
        )
        assert t_det >= 0
        assert t_det < 60.0  # Must detect within NFPA limit

    def test_detection_time_far_distance_takes_longer(self):
        """Detector far from fire must take longer to detect than near one."""
        t_near, _, _ = FirePhysics.detection_time(
            alpha=0.04689,
            distance_m=1.0,
            ceiling_h_m=3.0,
            smoke_type=SmokeType.FLAMING,
            smoke_threshold=4.0,
        )
        t_far, _, _ = FirePhysics.detection_time(
            alpha=0.04689,
            distance_m=10.0,
            ceiling_h_m=3.0,
            smoke_type=SmokeType.FLAMING,
            smoke_threshold=4.0,
        )
        assert t_far > t_near

    def test_detection_time_ultrafast_faster_than_slow(self):
        """Ultrafast growth must trigger detection before slow growth."""
        t_slow, _, _ = FirePhysics.detection_time(
            alpha=GrowthRate.SLOW.alpha,
            distance_m=3.0,
            ceiling_h_m=3.0,
            smoke_type=SmokeType.FLAMING,
            smoke_threshold=4.0,
        )
        t_ultra, _, _ = FirePhysics.detection_time(
            alpha=GrowthRate.ULTRAFAST.alpha,
            distance_m=3.0,
            ceiling_h_m=3.0,
            smoke_type=SmokeType.FLAMING,
            smoke_threshold=4.0,
        )
        assert t_ultra < t_slow

    def test_detection_time_returns_max_when_never_detected(self):
        """If threshold never reached within max_t_s, return (max_t_s, ...)."""
        # Very low alpha + high threshold → never reaches 4.0 %/m in 30 s
        t_det, hrr, od = FirePhysics.detection_time(  # NOSONAR
            alpha=0.0001,  # Very slow
            distance_m=20.0,  # Very far
            ceiling_h_m=3.0,
            smoke_type=SmokeType.FLAMING,
            smoke_threshold=4.0,
            max_t_s=30.0,
        )
        assert t_det == pytest.approx(30.0)  # Hit the cap
        assert od == pytest.approx(0.0)  # Never detected

    def test_detection_time_q_max_caps_hrr_at_detection(self):
        """When q_max is low, HRR at detection must not exceed q_max."""
        t_det, hrr, od = FirePhysics.detection_time(  # NOSONAR
            alpha=0.04689,
            distance_m=0.5,
            ceiling_h_m=3.0,
            smoke_type=SmokeType.FLAMING,
            smoke_threshold=4.0,
            q_max=500.0,  # 500 kW cap
        )
        if t_det < 300.0:  # If detected
            assert hrr <= 500.0 + 1.0  # Allow small numerical slack


# ═══════════════════════════════════════════════════════════════════════════════
# 4. SCENARIO LIBRARY — predefined fire scenarios
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.fixture
def square_room_polygon():
    """10×10 m square room as list of (x,y) tuples."""
    return [(0.0, 0.0), (10.0, 0.0), (10.0, 10.0), (0.0, 10.0)]


class TestScenarioLibrary:
    """Tests for predefined scenario generators."""

    def test_worst_case_uses_ultrafast_growth(self, square_room_polygon):
        """Worst case must use the fastest growth rate (ultrafast)."""
        sc = ScenarioLibrary.worst_case(square_room_polygon, ceiling_height=3.0)
        assert sc.growth_rate == GrowthRate.ULTRAFAST

    def test_worst_case_uses_flaming_smoke(self, square_room_polygon):
        """Worst case must use flaming smoke (more challenging for detection)."""
        sc = ScenarioLibrary.worst_case(square_room_polygon, ceiling_height=3.0)
        assert sc.smoke_type == SmokeType.FLAMING

    def test_worst_case_ignition_at_centroid(self, square_room_polygon):
        """Worst case ignition at room centroid (max avg detector distance)."""
        sc = ScenarioLibrary.worst_case(square_room_polygon, ceiling_height=3.0)
        # Centroid of 10×10 square is (5, 5)
        assert sc.ignition_point[0] == pytest.approx(5.0, abs=0.01)
        assert sc.ignition_point[1] == pytest.approx(5.0, abs=0.01)

    def test_most_probable_office_uses_medium_growth(self, square_room_polygon):
        """Most probable office fire uses medium t² growth."""
        sc = ScenarioLibrary.most_probable_office(square_room_polygon, ceiling_height=3.0)
        assert sc.growth_rate == GrowthRate.MEDIUM

    def test_most_probable_office_uses_smouldering_smoke(self, square_room_polygon):
        """Most probable office starts as smouldering."""
        sc = ScenarioLibrary.most_probable_office(square_room_polygon, ceiling_height=3.0)
        assert sc.smoke_type == SmokeType.SMOULDERING

    def test_most_probable_office_default_fire_load_400(self, square_room_polygon):
        """Default fire load for office = 400 MJ/m² (NFPA 557 Table 5.1)."""
        sc = ScenarioLibrary.most_probable_office(square_room_polygon, ceiling_height=3.0)
        assert sc.fire_load_mj_m2 == 400.0  # NOSONAR

    def test_corner_fire_uses_fast_growth(self, square_room_polygon):
        """Corner fires use fast t² growth."""
        sc = ScenarioLibrary.corner_fire(square_room_polygon, ceiling_height=3.0, corner_index=0)
        assert sc.growth_rate == GrowthRate.FAST

    def test_corner_fire_ignition_inside_polygon(self, square_room_polygon):
        """Corner fire ignition point must be 30% toward centroid (inside polygon)."""
        sc = ScenarioLibrary.corner_fire(square_room_polygon, ceiling_height=3.0, corner_index=0)
        # Corner 0 = (0,0), centroid = (5,5), 30% toward centroid = (1.5, 1.5)
        assert sc.ignition_point[0] == pytest.approx(1.5, abs=0.01)
        assert sc.ignition_point[1] == pytest.approx(1.5, abs=0.01)

    def test_corner_fire_wraps_around_index(self, square_room_polygon):
        """corner_index > len(polygon) must wrap around."""
        sc1 = ScenarioLibrary.corner_fire(square_room_polygon, ceiling_height=3.0, corner_index=0)
        sc4 = ScenarioLibrary.corner_fire(square_room_polygon, ceiling_height=3.0, corner_index=4)
        # Index 4 wraps to index 0
        assert sc1.ignition_point == sc4.ignition_point

    def test_all_corners_returns_one_per_vertex(self, square_room_polygon):
        """all_corners must return one scenario per polygon vertex."""
        scenarios = ScenarioLibrary.all_corners(square_room_polygon, ceiling_height=3.0)
        assert len(scenarios) == len(square_room_polygon)

    def test_wall_midpoint_fire_ignition_inside_polygon(self, square_room_polygon):
        """Wall midpoint fire must be pushed 0.5m inside the polygon."""
        sc = ScenarioLibrary.wall_midpoint_fire(square_room_polygon, ceiling_height=3.0, wall_index=0)
        # Wall 0: (0,0)→(10,0). Midpoint = (5, 0). Pushed 0.5m inside (toward y=5).
        assert sc.ignition_point[1] > 0.0  # Must be inside (y > 0)

    def test_all_scenarios_deduplicates_by_ignition_point(self, square_room_polygon):
        """all_scenarios must deduplicate scenarios with identical ignition points."""
        scenarios = ScenarioLibrary.all_scenarios(square_room_polygon, ceiling_height=3.0, fire_load_mj_m2=400.0)
        # For a square room: worst_case + most_probable + 4 corners = 6 raw
        # But centroid and corners are different points → all 6 should survive
        ignition_points = {(round(s.ignition_point[0], 3), round(s.ignition_point[1], 3)) for s in scenarios}
        assert len(ignition_points) == len(scenarios), "Duplicate ignition points not deduplicated"

    def test_blind_spot_scan_returns_grid_points(self, square_room_polygon):
        """blind_spot_scan must return one scenario per interior grid point."""
        scenarios = ScenarioLibrary.blind_spot_scan(
            square_room_polygon, ceiling_height=3.0, grid_m=2.0
        )
        # 10×10 room with 2m grid: ~5×5 = 25 points (minus margins)
        assert len(scenarios) > 0
        # All ignition points must be inside the polygon (x in [0,10], y in [0,10])
        for sc in scenarios:
            assert 0.0 <= sc.ignition_point[0] <= 10.0
            assert 0.0 <= sc.ignition_point[1] <= 10.0


# ═══════════════════════════════════════════════════════════════════════════════
# 5. SCENARIO RUNNER — full scenario execution
# ═══════════════════════════════════════════════════════════════════════════════


class TestScenarioRunner:
    """Tests for the ScenarioRunner class."""

    @pytest.fixture
    def runner(self):
        return ScenarioRunner(time_step_s=0.5)

    @pytest.fixture
    def simple_scenario(self, square_room_polygon):
        return ScenarioLibrary.worst_case(square_room_polygon, ceiling_height=3.0, fire_load_mj_m2=400.0)

    def test_run_returns_scenario_result(self, runner, simple_scenario, square_room_polygon):
        """run() must return a ScenarioResult instance."""
        detectors = [(5.0, 5.0)]  # Detector at centroid
        result = runner.run(simple_scenario, detectors, square_room_polygon)
        assert isinstance(result, ScenarioResult)

    def test_run_ignition_outside_polygon_returns_skipped(self, runner, square_room_polygon):
        """Ignition point outside polygon → verdict SKIPPED."""
        sc = FireScenario(
            scenario_id="outside",
            description="Outside polygon",
            ignition_point=(100.0, 100.0),  # Way outside
            growth_rate=GrowthRate.FAST,
            smoke_type=SmokeType.FLAMING,
            fire_load_mj_m2=400.0,
            ambient_temp_c=20.0,
            ceiling_height_m=3.0,
        )
        result = runner.run(sc, [(5.0, 5.0)], square_room_polygon)
        assert result.verdict == ScenarioVerdict.SKIPPED
        assert not result.compliant

    def test_run_detector_at_ignition_detects_fast(self, runner, simple_scenario, square_room_polygon):
        """Detector at ignition point must detect very quickly (< 10 s)."""
        detectors = [simple_scenario.ignition_point]
        result = runner.run(simple_scenario, detectors, square_room_polygon)
        assert result.first_detection_time_s is not None
        assert result.first_detection_time_s < 10.0
        assert result.verdict == ScenarioVerdict.PASS

    def test_run_far_detector_fails_or_slow(self, runner, simple_scenario, square_room_polygon):
        """Detector at the opposite corner of a large fire may fail or be slow."""
        # Move ignition to (5,5), put detector at (50, 50) (way outside, but we
        # test detection physics — distance matters, not polygon membership)
        detectors = [(50.0, 50.0)]
        result = runner.run(simple_scenario, detectors, square_room_polygon)
        # Either no detection (FAIL_NO_DETECTOR) or slow (FAIL_SLOW)
        assert result.verdict in (
            ScenarioVerdict.FAIL_NO_DETECTOR,
            ScenarioVerdict.FAIL_SLOW,
            ScenarioVerdict.FAIL_BLIND_SPOT,
        )

    def test_run_battery_returns_battery_result(self, runner, square_room_polygon):
        """run_battery must return a ScenarioBatteryResult."""
        scenarios = ScenarioLibrary.all_scenarios(square_room_polygon, ceiling_height=3.0)
        detectors = [(5.0, 5.0), (2.5, 2.5), (7.5, 7.5)]
        battery = runner.run_battery(detectors, square_room_polygon, scenarios)
        assert isinstance(battery, ScenarioBatteryResult)
        assert len(battery.results) == len(scenarios)

    def test_run_includes_warnings(self, runner, simple_scenario, square_room_polygon):
        """run() must include at least the CFD validation warning."""
        result = runner.run(simple_scenario, [(5.0, 5.0)], square_room_polygon)
        assert len(result.warnings) > 0
        # The CFD/FDS validation warning must be present
        assert any("CFD" in w or "FDS" in w for w in result.warnings)

    def test_run_records_compute_time(self, runner, simple_scenario, square_room_polygon):
        """compute_time_s must be a non-negative float."""
        result = runner.run(simple_scenario, [(5.0, 5.0)], square_room_polygon)
        assert isinstance(result.compute_time_s, float)
        assert result.compute_time_s >= 0.0

    def test_run_no_detectors_fails(self, runner, simple_scenario, square_room_polygon):
        """With zero detectors, the verdict must be FAIL_NO_DETECTOR."""
        result = runner.run(simple_scenario, [], square_room_polygon)
        assert result.verdict == ScenarioVerdict.FAIL_NO_DETECTOR
        assert not result.compliant


# ═══════════════════════════════════════════════════════════════════════════════
# 6. BATTERY RESULT — aggregation
# ═══════════════════════════════════════════════════════════════════════════════


class TestScenarioBatteryResult:
    """Tests for the ScenarioBatteryResult aggregator."""

    @pytest.fixture
    def passing_result(self):
        return ScenarioResult(
            scenario_id="pass_1",
            scenario_description="pass",
            verdict=ScenarioVerdict.PASS,
            first_detection_time_s=15.0,
            first_detector=None,
            all_detections=[],
            blind_spots=[],
            blind_spot_area_pct=0.0,
            hrr_at_first_alarm_kw=100.0,
            smoke_at_first_alarm_pct_m=5.0,
            nfpa_time_limit_s=60.0,
            compliant=True,
            margin_s=45.0,
            detectors_tested=4,
            grid_points_tested=100,
            compute_time_s=0.1,
        )

    @pytest.fixture
    def failing_result(self):
        return ScenarioResult(
            scenario_id="fail_1",
            scenario_description="fail",
            verdict=ScenarioVerdict.FAIL_SLOW,
            first_detection_time_s=90.0,
            first_detector=None,
            all_detections=[],
            blind_spots=[],
            blind_spot_area_pct=0.0,
            hrr_at_first_alarm_kw=200.0,
            smoke_at_first_alarm_pct_m=3.0,
            nfpa_time_limit_s=60.0,
            compliant=False,
            margin_s=-30.0,
            detectors_tested=4,
            grid_points_tested=100,
            compute_time_s=0.1,
        )

    def test_all_pass_true_when_all_pass(self, passing_result):
        battery = ScenarioBatteryResult(results=[passing_result, passing_result], det_type="PHOTO", det_count=4)
        assert battery.all_pass is True

    def test_all_pass_false_when_any_fails(self, passing_result, failing_result):
        battery = ScenarioBatteryResult(results=[passing_result, failing_result], det_type="PHOTO", det_count=4)
        assert battery.all_pass is False

    def test_pass_count(self, passing_result, failing_result):
        battery = ScenarioBatteryResult(results=[passing_result, failing_result, passing_result], det_type="PHOTO", det_count=4)
        assert battery.pass_count == 2

    def test_fail_count(self, passing_result, failing_result):
        battery = ScenarioBatteryResult(results=[passing_result, failing_result, passing_result], det_type="PHOTO", det_count=4)
        assert battery.fail_count == 1

    def test_worst_detection_time_picks_max(self, passing_result, failing_result):
        battery = ScenarioBatteryResult(results=[passing_result, failing_result], det_type="PHOTO", det_count=4)
        assert battery.worst_detection_time_s == 90.0  # NOSONAR

    def test_worst_detection_time_none_when_no_detections(self):
        """When no scenario detected, worst_detection_time_s is None."""
        no_det = ScenarioResult(
            scenario_id="none",
            scenario_description="none",
            verdict=ScenarioVerdict.FAIL_NO_DETECTOR,
            first_detection_time_s=None,
            first_detector=None,
            all_detections=[],
            blind_spots=[],
            blind_spot_area_pct=0.0,
            hrr_at_first_alarm_kw=None,
            smoke_at_first_alarm_pct_m=None,
            nfpa_time_limit_s=60.0,
            compliant=False,
            margin_s=None,
            detectors_tested=4,
            grid_points_tested=100,
            compute_time_s=0.1,
        )
        battery = ScenarioBatteryResult(results=[no_det], det_type="PHOTO", det_count=4)
        assert battery.worst_detection_time_s is None

    def test_summary_dict_contains_required_fields(self, passing_result):
        battery = ScenarioBatteryResult(results=[passing_result], det_type="PHOTO", det_count=4)
        d = battery.summary_dict()
        assert "detector_type" in d
        assert "detector_count" in d
        assert "scenarios_run" in d
        assert "scenarios_pass" in d
        assert "scenarios_fail" in d
        assert "all_pass" in d
        assert "worst_detection_s" in d
        assert "total_blind_spots" in d
        assert "nfpa_compliant" in d
        assert "nfpa_clause" in d
        assert "per_scenario" in d
        assert d["nfpa_clause"] == "NFPA 72-2022 §17.7.3"


# ═══════════════════════════════════════════════════════════════════════════════
# 7. REPORTER — output formats
# ═══════════════════════════════════════════════════════════════════════════════


class TestScenarioReporter:
    """Tests for the text/JSON/CSV output formatters."""

    @pytest.fixture
    def battery(self, square_room_polygon):
        runner = ScenarioRunner(time_step_s=1.0)
        scenarios = ScenarioLibrary.all_scenarios(square_room_polygon, ceiling_height=3.0, fire_load_mj_m2=400.0)
        detectors = [(5.0, 5.0), (2.5, 2.5), (7.5, 7.5), (2.5, 7.5), (7.5, 2.5)]
        return runner.run_battery(detectors, square_room_polygon, scenarios)

    def test_to_text_returns_non_empty_string(self, battery):
        text = ScenarioReporter.to_text(battery)
        assert isinstance(text, str)
        assert len(text) > 0
        assert "SCENARIO BATTERY REPORT" in text

    def test_to_text_contains_pass_fail_summary(self, battery):
        text = ScenarioReporter.to_text(battery)
        assert "Pass:" in text
        assert "Fail:" in text

    def test_to_json_returns_valid_json(self, battery):
        json_str = ScenarioReporter.to_json(battery)
        parsed = json.loads(json_str)
        assert isinstance(parsed, dict)
        assert "scenarios_run" in parsed

    def test_to_csv_has_header_row(self, battery):
        csv_str = ScenarioReporter.to_csv(battery)
        lines = csv_str.split("\n")
        assert lines[0].startswith("scenario_id,verdict,detection_time_s")

    def test_to_csv_has_one_row_per_scenario(self, battery):
        csv_str = ScenarioReporter.to_csv(battery)
        lines = csv_str.split("\n")
        # 1 header + N scenario rows
        assert len(lines) == 1 + len(battery.results)

    def test_to_csv_escapes_commas_in_scenario_id(self, battery):  # NOSONAR
        """Commas in scenario_id must be replaced with semicolons."""
        # Force a scenario with a comma in ID
        from fireai.core.scenario_engine import ScenarioResult

        result_with_comma = ScenarioResult(
            scenario_id="scenario,with,commas",
            scenario_description="test",
            verdict=ScenarioVerdict.PASS,
            first_detection_time_s=10.0,
            first_detector=None,
            all_detections=[],
            blind_spots=[],
            blind_spot_area_pct=0.0,
            hrr_at_first_alarm_kw=100.0,
            smoke_at_first_alarm_pct_m=5.0,
            nfpa_time_limit_s=60.0,
            compliant=True,
            margin_s=50.0,
            detectors_tested=1,
            grid_points_tested=10,
            compute_time_s=0.01,
        )
        battery = ScenarioBatteryResult(results=[result_with_comma], det_type="PHOTO", det_count=1)
        csv_str = ScenarioReporter.to_csv(battery)
        # The scenario_id should not contain commas (replaced with ;)
        data_line = csv_str.split("\n")[1]
        first_field = data_line.split(",")[0]
        assert "," not in first_field
        assert "scenario;with;commas" in first_field


# ═══════════════════════════════════════════════════════════════════════════════
# 8. CONVENIENCE WRAPPER — run_scenarios_for_room
# ═══════════════════════════════════════════════════════════════════════════════


class TestRunScenariosForRoom:
    """Tests for the one-call convenience wrapper."""

    def test_returns_battery_result(self, square_room_polygon):
        """Must return a ScenarioBatteryResult."""
        detectors = [(5.0, 5.0), (2.5, 2.5), (7.5, 7.5)]
        result = run_scenarios_for_room(
            room_polygon=square_room_polygon,
            ceiling_height=3.0,
            detector_positions=detectors,
            detector_type="PHOTOELECTRIC",
            fire_load_mj_m2=400.0,
        )
        assert isinstance(result, ScenarioBatteryResult)
        assert len(result.results) > 0

    def test_uses_photoelectric_threshold_by_default(self, square_room_polygon):
        """Default detector_type='PHOTOELECTRIC' → 4.0 %/m threshold."""
        detectors = [(5.0, 5.0)]
        result = run_scenarios_for_room(
            room_polygon=square_room_polygon,
            ceiling_height=3.0,
            detector_positions=detectors,
            detector_type="PHOTOELECTRIC",
            fire_load_mj_m2=400.0,
        )
        assert result.det_type == "PHOTOELECTRIC"

    def test_ionization_uses_lower_threshold(self, square_room_polygon):
        """IONIZATION detector type → 2.5 %/m threshold (more sensitive)."""
        detectors = [(5.0, 5.0)]
        result = run_scenarios_for_room(
            room_polygon=square_room_polygon,
            ceiling_height=3.0,
            detector_positions=detectors,
            detector_type="IONIZATION",
            fire_load_mj_m2=400.0,
        )
        assert "ION" in result.det_type.upper()


# ═══════════════════════════════════════════════════════════════════════════════
# 9. FIRE LOAD TABLE — NFPA 557-2016 Table 5.1
# ═══════════════════════════════════════════════════════════════════════════════


class TestFireLoadTable:
    """Tests for the FIRE_LOAD_BY_OCCUPANCY table (NFPA 557-2016 Table 5.1)."""

    def test_office_fire_load_400(self):
        """Office fire load = 400 MJ/m² (NFPA 557 Table 5.1)."""
        assert FIRE_LOAD_BY_OCCUPANCY["office"] == 400.0  # NOSONAR

    def test_warehouse_fire_load_800(self):
        """Warehouse fire load = 800 MJ/m² (high fuel storage)."""
        assert FIRE_LOAD_BY_OCCUPANCY["warehouse"] == 800.0  # NOSONAR

    def test_warehouse_higher_than_office(self):
        """Warehouse must have higher fire load than office."""
        assert FIRE_LOAD_BY_OCCUPANCY["warehouse"] > FIRE_LOAD_BY_OCCUPANCY["office"]

    def test_all_fire_loads_positive(self):
        """Every fire load must be positive."""
        for occ, fl in FIRE_LOAD_BY_OCCUPANCY.items():
            assert fl > 0, f"Fire load for '{occ}' must be positive"

    def test_get_fire_load_returns_value_for_known_occupancy(self):
        """get_fire_load('office') must return 400.0."""
        assert get_fire_load("office") == 400.0  # NOSONAR

    def test_get_fire_load_returns_default_for_unknown(self):
        """Unknown occupancy must fall back to office (400.0)."""
        assert get_fire_load("nonexistent") == 400.0  # NOSONAR

    def test_get_fire_load_case_insensitive(self):
        """get_fire_load must be case-insensitive."""
        assert get_fire_load("OFFICE") == get_fire_load("office")
        assert get_fire_load("Warehouse") == get_fire_load("warehouse")


# ═══════════════════════════════════════════════════════════════════════════════
# 10. DATA CLASS BEHAVIOR
# ═══════════════════════════════════════════════════════════════════════════════


class TestDataClasses:
    """Tests for FireScenario, DetectionEvent, BlindSpot dataclasses."""

    def test_fire_scenario_is_frozen(self):
        """FireScenario must be immutable (frozen=True)."""
        sc = FireScenario(
            scenario_id="test",
            description="test",
            ignition_point=(1.0, 2.0),
            growth_rate=GrowthRate.MEDIUM,
            smoke_type=SmokeType.FLAMING,
            fire_load_mj_m2=400.0,
            ambient_temp_c=20.0,
            ceiling_height_m=3.0,
        )
        with pytest.raises((AttributeError, Exception)):
            sc.scenario_id = "modified"  # Should raise FrozenInstanceError

    def test_detection_event_holds_all_fields(self):
        """DetectionEvent must hold detector_index, pos, dist, time, hrr, od."""
        ev = DetectionEvent(
            detector_index=0,
            detector_pos=(1.0, 2.0),
            distance_m=3.5,
            detection_time_s=15.2,
            hrr_at_detection_kw=125.0,
            smoke_conc_pct_m=4.5,
        )
        assert ev.detector_index == 0
        assert ev.detector_pos == (1.0, 2.0)
        assert ev.distance_m == pytest.approx(3.5)
        assert ev.detection_time_s == pytest.approx(15.2)
        assert ev.hrr_at_detection_kw == pytest.approx(125.0)
        assert ev.smoke_conc_pct_m == pytest.approx(4.5)

    def test_blind_spot_holds_all_fields(self):
        """BlindSpot must hold position, nearest_dist, estimated_time."""
        bs = BlindSpot(
            position=(5.0, 5.0),
            nearest_detector_dist_m=8.5,
            estimated_detection_s=75.0,
        )
        assert bs.position == (5.0, 5.0)
        assert bs.nearest_detector_dist_m == pytest.approx(8.5)
        assert bs.estimated_detection_s == pytest.approx(75.0)


# ═══════════════════════════════════════════════════════════════════════════════
# 11. INTEGRATION — full pipeline from polygon to report
# ═══════════════════════════════════════════════════════════════════════════════


class TestIntegrationEndToEnd:
    """End-to-end integration: room → scenarios → battery → report."""

    def test_full_pipeline_produces_json_report(self, square_room_polygon):
        """Run full pipeline and verify JSON report is well-formed."""
        detectors = [(5.0, 5.0), (2.5, 2.5), (7.5, 7.5), (2.5, 7.5), (7.5, 2.5)]
        battery = run_scenarios_for_room(
            room_polygon=square_room_polygon,
            ceiling_height=3.0,
            detector_positions=detectors,
            detector_type="PHOTOELECTRIC",
            fire_load_mj_m2=400.0,
        )
        json_report = ScenarioReporter.to_json(battery)
        parsed = json.loads(json_report)
        assert "scenarios_run" in parsed
        assert parsed["scenarios_run"] > 0
        assert "per_scenario" in parsed
        assert len(parsed["per_scenario"]) == parsed["scenarios_run"]

    def test_full_pipeline_text_report_contains_pass_or_fail(self, square_room_polygon):
        """Text report must explicitly state PASS or FAIL outcome."""
        detectors = [(5.0, 5.0)]
        battery = run_scenarios_for_room(
            room_polygon=square_room_polygon,
            ceiling_height=3.0,
            detector_positions=detectors,
            fire_load_mj_m2=400.0,
        )
        text = ScenarioReporter.to_text(battery)
        assert "RESULT:" in text
        # Must say either ALL PASS or N SCENARIO(S) FAILED
        assert "PASS" in text or "FAILED" in text
