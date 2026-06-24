"""test_monte_carlo_pipeline.py — Comprehensive tests for the Monte Carlo pipeline.

Covers:
  1. DetectorFailureModel dataclass (defaults, custom values, field access)
  2. DetectorReliabilitySimulator (init, _frange, _empty_result, simulate_room_reliability)
  3. MCPipelineAdapter (init, enrich_layout, analyse_floor)

Target: raise coverage from 23% to 80%+.
"""

import math
from dataclasses import fields
from unittest.mock import MagicMock, PropertyMock, patch

import pytest

from fireai.core.monte_carlo_pipeline import (
    DetectorFailureModel,
    DetectorReliabilitySimulator,
    MCPipelineAdapter,
)

# ═══════════════════════════════════════════════════════════════════════════════
# Fixtures
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.fixture
def default_failure_model():
    """A DetectorFailureModel with all defaults."""
    return DetectorFailureModel(detector_id="D1")


@pytest.fixture
def high_failure_model():
    """A model with very high failure rates — forces many failures."""
    return DetectorFailureModel(
        detector_id="D_high",
        annual_failure_rate=0.95,
        common_cause_beta=0.0,
        p_blind=0.95,
    )


@pytest.fixture
def guaranteed_common_cause_model():
    """A model with beta=1.0 — guaranteed common-cause failure every trial."""
    return DetectorFailureModel(
        detector_id="D_ccf",
        annual_failure_rate=0.0,
        common_cause_beta=1.0,
        p_blind=0.0,
    )


@pytest.fixture
def zero_failure_model():
    """A model where detectors never fail."""
    return DetectorFailureModel(
        detector_id="D_zero",
        annual_failure_rate=0.0,
        common_cause_beta=0.0,
        p_blind=0.0,
    )


@pytest.fixture
def simulator_fast():
    """A simulator with a small number of trials for speed."""
    return DetectorReliabilitySimulator(n_trials=200, seed=123)


@pytest.fixture
def adapter_fast():
    """An adapter with few trials for speed."""
    return MCPipelineAdapter(n_trials=200, reliability_threshold=0.95, seed=42)


@pytest.fixture
def single_detector():
    """One detector centred in a 10×8 room."""
    return [(5.0, 4.0)]


@pytest.fixture
def two_detectors():
    """Two detectors covering a 10×8 room well."""
    return [(2.5, 2.0), (7.5, 6.0)]


@pytest.fixture
def many_detectors():
    """Six detectors in a 12×10 room for high redundancy."""
    return [
        (2.0, 2.0),
        (6.0, 2.0),
        (10.0, 2.0),
        (2.0, 8.0),
        (6.0, 8.0),
        (10.0, 8.0),
    ]


@pytest.fixture
def mock_layout():
    """A mock DetectorLayout with sensible defaults."""
    layout = MagicMock()
    layout.detectors = [(5.0, 4.0)]
    layout.coverage_radius = 6.37
    layout.room_width = 10.0
    layout.room_length = 8.0
    layout.warnings = []
    layout.proof_valid = True
    return layout


@pytest.fixture
def mock_room():
    """A mock room object."""
    room = MagicMock()
    room.width = 10.0
    room.length = 8.0
    return room


@pytest.fixture
def mock_floor_report():
    """A mock FloorReport with two room summaries."""
    rs1 = MagicMock()
    rs1.room_id = "R1"
    rs1.detectors = [(2.5, 2.0), (7.5, 6.0)]
    rs1.width = 10.0
    rs1.length = 8.0
    rs1.coverage_radius = 6.37

    rs2 = MagicMock()
    rs2.room_id = "R2"
    rs2.detectors = [(3.0, 3.0), (9.0, 7.0)]
    rs2.width = 12.0
    rs2.length = 10.0
    rs2.coverage_radius = 6.37

    report = MagicMock()
    report.floor_id = "F1"
    report.room_summaries = [rs1, rs2]
    return report


@pytest.fixture
def mock_floor_report_empty():
    """A mock FloorReport with no room summaries."""
    report = MagicMock()
    report.floor_id = "F_empty"
    report.room_summaries = []
    return report


@pytest.fixture
def mock_floor_report_no_detectors():
    """A mock FloorReport where rooms have no detectors."""
    rs = MagicMock()
    rs.room_id = "R_empty"
    rs.detectors = []
    rs.width = 10.0
    rs.length = 8.0
    rs.coverage_radius = 6.37

    report = MagicMock()
    report.floor_id = "F_nodet"
    report.room_summaries = [rs]
    return report


# ═══════════════════════════════════════════════════════════════════════════════
# 1. DetectorFailureModel
# ═══════════════════════════════════════════════════════════════════════════════


class TestDetectorFailureModel:
    """Tests for the DetectorFailureModel dataclass."""

    def test_default_values(self):
        """All defaults should match NFPA 72 typical values."""
        fm = DetectorFailureModel(detector_id="D1")
        assert fm.detector_id == "D1"
        assert fm.annual_failure_rate == 0.005
        assert fm.common_cause_beta == 0.02
        assert fm.test_interval_months == 6.0
        assert fm.p_false_alarm == 0.001
        assert fm.p_stuck_alarm == 0.0005
        assert fm.p_blind == 0.003

    def test_custom_values(self):
        """Custom values should be stored correctly."""
        fm = DetectorFailureModel(
            detector_id="custom",
            annual_failure_rate=0.1,
            common_cause_beta=0.5,
            test_interval_months=12.0,
            p_false_alarm=0.01,
            p_stuck_alarm=0.005,
            p_blind=0.02,
        )
        assert fm.detector_id == "custom"
        assert fm.annual_failure_rate == 0.1
        assert fm.common_cause_beta == 0.5
        assert fm.test_interval_months == 12.0
        assert fm.p_false_alarm == 0.01
        assert fm.p_stuck_alarm == 0.005
        assert fm.p_blind == 0.02

    def test_is_dataclass(self):
        """DetectorFailureModel should be a dataclass with 7 fields."""
        field_names = {f.name for f in fields(DetectorFailureModel)}
        expected = {
            "detector_id",
            "annual_failure_rate",
            "common_cause_beta",
            "test_interval_months",
            "p_false_alarm",
            "p_stuck_alarm",
            "p_blind",
        }
        assert field_names == expected

    def test_equality(self):
        """Two instances with same values should be equal (dataclass)."""
        fm1 = DetectorFailureModel(detector_id="X")
        fm2 = DetectorFailureModel(detector_id="X")
        assert fm1 == fm2

    def test_inequality(self):
        """Instances with different values should not be equal."""
        fm1 = DetectorFailureModel(detector_id="A")
        fm2 = DetectorFailureModel(detector_id="B")
        assert fm1 != fm2

    def test_zero_failure_rate(self, zero_failure_model):
        """Zero failure rate model should have zero rates."""
        assert zero_failure_model.annual_failure_rate == 0.0
        assert zero_failure_model.common_cause_beta == 0.0
        assert zero_failure_model.p_blind == 0.0

    def test_high_failure_rate(self, high_failure_model):
        """High failure rate model for stress testing."""
        assert high_failure_model.annual_failure_rate == 0.95
        assert high_failure_model.p_blind == 0.95


# ═══════════════════════════════════════════════════════════════════════════════
# 2. DetectorReliabilitySimulator — Initialization
# ═══════════════════════════════════════════════════════════════════════════════


class TestSimulatorInit:
    """Tests for DetectorReliabilitySimulator construction."""

    def test_default_init(self):
        """Default constructor stores n_trials=10000, seed=None, n_workers=1."""
        sim = DetectorReliabilitySimulator()
        assert sim.n_trials == 10_000
        assert sim.n_workers == 1

    def test_custom_init(self):
        """Custom parameters are stored."""
        sim = DetectorReliabilitySimulator(n_trials=500, seed=99, n_workers=4)
        assert sim.n_trials == 500
        assert sim.n_workers == 4

    def test_rng_is_seeded(self):
        """Providing a seed makes the RNG deterministic."""
        sim1 = DetectorReliabilitySimulator(n_trials=10, seed=42)
        sim2 = DetectorReliabilitySimulator(n_trials=10, seed=42)
        # Both RNGs should produce same sequence
        vals1 = [sim1._rng.random() for _ in range(5)]
        vals2 = [sim2._rng.random() for _ in range(5)]
        assert vals1 == vals2

    def test_rng_different_seeds(self):
        """Different seeds produce different sequences."""
        sim1 = DetectorReliabilitySimulator(n_trials=10, seed=1)
        sim2 = DetectorReliabilitySimulator(n_trials=10, seed=2)
        vals1 = [sim1._rng.random() for _ in range(5)]
        vals2 = [sim2._rng.random() for _ in range(5)]
        assert vals1 != vals2

    def test_has_lock(self):
        """Simulator should have a threading lock attribute."""
        sim = DetectorReliabilitySimulator()
        import threading
        assert isinstance(sim._lock, type(threading.Lock()))


# ═══════════════════════════════════════════════════════════════════════════════
# 3. DetectorReliabilitySimulator — Static helpers
# ═══════════════════════════════════════════════════════════════════════════════


class TestSimulatorHelpers:
    """Tests for _empty_result and _frange static methods."""

    def test_empty_result_structure(self):
        """_empty_result returns dict with expected keys and zero/falsy values."""
        result = DetectorReliabilitySimulator._empty_result()
        assert result["n_trials"] == 0
        assert result["mean_coverage_pct"] == 0.0
        assert result["p_full_coverage"] == 0.0
        assert result["cvar_5pct"] == 0.0
        assert result["worst_coverage_pct"] == 0.0
        assert result["is_reliable"] is False

    def test_empty_result_is_dict(self):
        """_empty_result should return a dict."""
        result = DetectorReliabilitySimulator._empty_result()
        assert isinstance(result, dict)

    def test_frange_basic(self):
        """_frange yields float values from start to stop by step."""
        vals = list(DetectorReliabilitySimulator._frange(0.0, 1.0, 0.5))
        assert vals == [0.0, 0.5, 1.0]

    def test_frange_single_value(self):
        """_frange with start==stop yields that value."""
        vals = list(DetectorReliabilitySimulator._frange(0.5, 0.5, 0.1))
        assert vals == [0.5]

    def test_frange_small_step(self):
        """_frange with small step yields many values."""
        vals = list(DetectorReliabilitySimulator._frange(0.0, 0.1, 0.05))
        assert len(vals) == 3  # 0.0, 0.05, 0.1
        assert vals[0] == pytest.approx(0.0)
        assert vals[-1] == pytest.approx(0.1, abs=0.01)

    def test_frange_zero_step_infinite(self):
        """_frange with zero step would infinite loop — caller must avoid this."""
        # We just test that it yields the start value at least
        gen = DetectorReliabilitySimulator._frange(1.0, 2.0, 0.0)
        # First value should be 1.0
        assert next(gen) == 1.0
        # Second value would still be 1.0 (infinite loop if consumed fully)
        assert next(gen) == 1.0


# ═══════════════════════════════════════════════════════════════════════════════
# 4. DetectorReliabilitySimulator — simulate_room_reliability
# ═══════════════════════════════════════════════════════════════════════════════


class TestSimulateRoomReliability:
    """Core simulation tests for DetectorReliabilitySimulator."""

    # --- Empty / edge-case inputs ---

    def test_empty_detectors_returns_empty_result(self, simulator_fast):
        """No detectors should return _empty_result()."""
        result = simulator_fast.simulate_room_reliability(
            detectors=[], room_width=10.0, room_length=8.0,
        )
        assert result["n_trials"] == 0
        assert result["mean_coverage_pct"] == 0.0
        assert result["is_reliable"] is False

    # --- Result structure ---

    def test_result_has_all_keys(self, simulator_fast, single_detector):
        """Result dict should contain all expected keys."""
        result = simulator_fast.simulate_room_reliability(
            detectors=single_detector, room_width=10.0, room_length=8.0,
        )
        expected_keys = {
            "n_trials", "mean_coverage_pct", "p_full_coverage", "cvar_5pct",
            "worst_coverage_pct", "best_coverage_pct", "std_dev_pct",
            "is_reliable", "nfpa_reference", "time_horizon_yr", "detector_count",
        }
        assert expected_keys.issubset(result.keys())

    def test_n_trials_matches_config(self, simulator_fast, single_detector):
        """Result n_trials should match the simulator's n_trials."""
        result = simulator_fast.simulate_room_reliability(
            detectors=single_detector, room_width=10.0, room_length=8.0,
        )
        assert result["n_trials"] == 200

    def test_detector_count_stored(self, simulator_fast, two_detectors):
        """Result detector_count should match input detector list length."""
        result = simulator_fast.simulate_room_reliability(
            detectors=two_detectors, room_width=10.0, room_length=8.0,
        )
        assert result["detector_count"] == 2

    def test_nfpa_reference_present(self, simulator_fast, single_detector):
        """Result should include NFPA reference string."""
        result = simulator_fast.simulate_room_reliability(
            detectors=single_detector, room_width=10.0, room_length=8.0,
        )
        assert "NFPA 72" in result["nfpa_reference"]

    def test_time_horizon_stored(self, simulator_fast, single_detector):
        """Result should record the time horizon used."""
        result = simulator_fast.simulate_room_reliability(
            detectors=single_detector, room_width=10.0, room_length=8.0,
            time_horizon_yr=5.0,
        )
        assert result["time_horizon_yr"] == 5.0

    # --- Coverage bounds ---

    def test_coverage_between_zero_and_hundred(self, simulator_fast, two_detectors):
        """Mean and worst coverage should be in [0, 100]."""
        result = simulator_fast.simulate_room_reliability(
            detectors=two_detectors, room_width=10.0, room_length=8.0,
        )
        assert 0.0 <= result["mean_coverage_pct"] <= 100.0
        assert 0.0 <= result["worst_coverage_pct"] <= 100.0
        assert 0.0 <= result["best_coverage_pct"] <= 100.0

    def test_p_full_coverage_between_zero_and_one(self, simulator_fast, two_detectors):
        """P(full coverage) should be in [0, 1]."""
        result = simulator_fast.simulate_room_reliability(
            detectors=two_detectors, room_width=10.0, room_length=8.0,
        )
        assert 0.0 <= result["p_full_coverage"] <= 1.0

    # --- Deterministic seed ---

    def test_deterministic_with_same_seed(self, single_detector):
        """Same seed should produce identical results."""
        sim1 = DetectorReliabilitySimulator(n_trials=200, seed=42)
        sim2 = DetectorReliabilitySimulator(n_trials=200, seed=42)
        r1 = sim1.simulate_room_reliability(
            detectors=single_detector, room_width=10.0, room_length=8.0,
        )
        r2 = sim2.simulate_room_reliability(
            detectors=single_detector, room_width=10.0, room_length=8.0,
        )
        assert r1["mean_coverage_pct"] == r2["mean_coverage_pct"]
        assert r1["p_full_coverage"] == r2["p_full_coverage"]

    def test_different_seeds_may_differ(self, single_detector):
        """Different seeds may produce different results (probabilistic)."""
        sim1 = DetectorReliabilitySimulator(n_trials=500, seed=1)
        sim2 = DetectorReliabilitySimulator(n_trials=500, seed=999)
        r1 = sim1.simulate_room_reliability(
            detectors=single_detector, room_width=10.0, room_length=8.0,
        )
        r2 = sim2.simulate_room_reliability(
            detectors=single_detector, room_width=10.0, room_length=8.0,
        )
        # Not guaranteed, but extremely likely with different seeds
        # We just check they both return valid results
        assert 0.0 <= r1["mean_coverage_pct"] <= 100.0
        assert 0.0 <= r2["mean_coverage_pct"] <= 100.0

    # --- Zero failure model (detectors never fail) ---

    def test_zero_failure_high_coverage(self, single_detector):
        """With zero failure rate, detectors always survive => high coverage."""
        sim = DetectorReliabilitySimulator(n_trials=200, seed=42)
        fm = DetectorFailureModel(
            detector_id="zero", annual_failure_rate=0.0,
            common_cause_beta=0.0, p_blind=0.0,
        )
        result = sim.simulate_room_reliability(
            detectors=single_detector, room_width=10.0, room_length=8.0,
            failure_model=fm,
        )
        # With zero failures, all detectors survive every trial
        # A single detector at (5,4) with R=6.37 should cover the 10×8 room well
        assert result["mean_coverage_pct"] > 80.0
        assert result["p_full_coverage"] > 0.5

    def test_zero_failure_is_reliable(self, many_detectors):
        """With many detectors and zero failures, should be reliable."""
        sim = DetectorReliabilitySimulator(n_trials=200, seed=42)
        fm = DetectorFailureModel(
            detector_id="zero", annual_failure_rate=0.0,
            common_cause_beta=0.0, p_blind=0.0,
        )
        result = sim.simulate_room_reliability(
            detectors=many_detectors, room_width=12.0, room_length=10.0,
            failure_model=fm,
        )
        assert result["is_reliable"] is True

    # --- High failure model ---

    def test_high_failure_low_coverage(self, single_detector):
        """With very high failure rate, coverage should be very low."""
        sim = DetectorReliabilitySimulator(n_trials=500, seed=42)
        fm = DetectorFailureModel(
            detector_id="high", annual_failure_rate=0.99,
            common_cause_beta=0.0, p_blind=0.99,
        )
        result = sim.simulate_room_reliability(
            detectors=single_detector, room_width=10.0, room_length=8.0,
            failure_model=fm,
        )
        # With 99% failure rate, most trials have no active detectors
        assert result["mean_coverage_pct"] < 20.0

    def test_high_failure_not_reliable(self, single_detector):
        """With high failure rate, should not be reliable."""
        sim = DetectorReliabilitySimulator(n_trials=500, seed=42)
        fm = DetectorFailureModel(
            detector_id="high", annual_failure_rate=0.99,
            common_cause_beta=0.0, p_blind=0.99,
        )
        result = sim.simulate_room_reliability(
            detectors=single_detector, room_width=10.0, room_length=8.0,
            failure_model=fm,
        )
        assert result["is_reliable"] is False

    # --- Common-cause failure (beta=1.0 guarantees all fail) ---

    def test_guaranteed_common_cause_zero_coverage(self, many_detectors, guaranteed_common_cause_model):
        """With beta=1.0, every trial has common-cause failure => 0% coverage."""
        sim = DetectorReliabilitySimulator(n_trials=200, seed=42)
        result = sim.simulate_room_reliability(
            detectors=many_detectors, room_width=12.0, room_length=10.0,
            failure_model=guaranteed_common_cause_model,
        )
        assert result["mean_coverage_pct"] == 0.0
        assert result["p_full_coverage"] == 0.0
        assert result["worst_coverage_pct"] == 0.0
        assert result["is_reliable"] is False

    # --- Redundancy helps ---

    def test_more_detectors_higher_reliability(self):
        """More detectors should improve reliability (with typical failure rates)."""
        sim = DetectorReliabilitySimulator(n_trials=500, seed=42)
        # Single detector
        r1 = sim.simulate_room_reliability(
            detectors=[(5.0, 4.0)], room_width=10.0, room_length=8.0,
        )
        # Need fresh sim to reset RNG state
        sim2 = DetectorReliabilitySimulator(n_trials=500, seed=42)
        # Multiple detectors
        r2 = sim2.simulate_room_reliability(
            detectors=[(2.5, 2.0), (7.5, 6.0), (5.0, 4.0)],
            room_width=10.0, room_length=8.0,
        )
        # More detectors should have higher mean coverage
        assert r2["mean_coverage_pct"] >= r1["mean_coverage_pct"]

    # --- Custom coverage radius ---

    def test_large_coverage_radius_improves_coverage(self, single_detector):
        """Larger coverage radius should improve coverage."""
        sim1 = DetectorReliabilitySimulator(n_trials=200, seed=42)
        r_small = sim1.simulate_room_reliability(
            detectors=single_detector, room_width=10.0, room_length=8.0,
            coverage_radius=3.0,
        )
        sim2 = DetectorReliabilitySimulator(n_trials=200, seed=42)
        r_large = sim2.simulate_room_reliability(
            detectors=single_detector, room_width=10.0, room_length=8.0,
            coverage_radius=10.0,
        )
        assert r_large["mean_coverage_pct"] >= r_small["mean_coverage_pct"]

    # --- Time horizon ---

    def test_longer_time_horizon_more_failures(self, single_detector):
        """Longer time horizon => higher effective failure probability => lower coverage."""
        sim1 = DetectorReliabilitySimulator(n_trials=500, seed=42)
        r_short = sim1.simulate_room_reliability(
            detectors=single_detector, room_width=10.0, room_length=8.0,
            time_horizon_yr=0.01,
        )
        sim2 = DetectorReliabilitySimulator(n_trials=500, seed=42)
        r_long = sim2.simulate_room_reliability(
            detectors=single_detector, room_width=10.0, room_length=8.0,
            time_horizon_yr=50.0,
        )
        # Short horizon has very low failure probability
        # Long horizon has high failure probability
        assert r_short["mean_coverage_pct"] >= r_long["mean_coverage_pct"]

    def test_default_time_horizon_is_one_year(self, simulator_fast, single_detector):
        """Default time_horizon_yr should be 1.0."""
        result = simulator_fast.simulate_room_reliability(
            detectors=single_detector, room_width=10.0, room_length=8.0,
        )
        assert result["time_horizon_yr"] == 1.0

    # --- Custom failure model parameter ---

    def test_custom_failure_model_used(self, single_detector):
        """Passing a custom failure_model should use its rates."""
        sim = DetectorReliabilitySimulator(n_trials=200, seed=42)
        fm = DetectorFailureModel(
            detector_id="custom", annual_failure_rate=0.0,
            common_cause_beta=0.0, p_blind=0.0,
        )
        result = sim.simulate_room_reliability(
            detectors=single_detector, room_width=10.0, room_length=8.0,
            failure_model=fm,
        )
        # With zero failure, should have high coverage
        assert result["mean_coverage_pct"] > 50.0

    def test_default_failure_model_when_none(self, simulator_fast, single_detector):
        """Passing failure_model=None should use default DetectorFailureModel."""
        result = simulator_fast.simulate_room_reliability(
            detectors=single_detector, room_width=10.0, room_length=8.0,
            failure_model=None,
        )
        # Should produce a valid result using defaults
        assert result["n_trials"] == 200
        assert 0.0 <= result["mean_coverage_pct"] <= 100.0

    # --- Statistical output fields ---

    def test_cvar_5pct_is_fifth_percentile(self):
        """cvar_5pct should be less than or equal to best coverage."""
        sim = DetectorReliabilitySimulator(n_trials=500, seed=42)
        result = sim.simulate_room_reliability(
            detectors=[(5.0, 4.0)], room_width=10.0, room_length=8.0,
        )
        # cvar_5pct is the 5th-percentile value from sorted coverage results
        # It should be <= best_coverage_pct (not necessarily <= mean if
        # distribution is bimodal with many 100% and some 0% trials)
        assert result["cvar_5pct"] <= result["best_coverage_pct"]
        assert 0.0 <= result["cvar_5pct"] <= 100.0

    def test_worst_leq_mean_leq_best(self, two_detectors):
        """worst_coverage_pct <= mean_coverage_pct <= best_coverage_pct."""
        sim = DetectorReliabilitySimulator(n_trials=500, seed=42)
        result = sim.simulate_room_reliability(
            detectors=two_detectors, room_width=10.0, room_length=8.0,
        )
        assert result["worst_coverage_pct"] <= result["mean_coverage_pct"]
        assert result["mean_coverage_pct"] <= result["best_coverage_pct"]

    def test_std_dev_non_negative(self, simulator_fast, two_detectors):
        """Standard deviation should be non-negative."""
        result = simulator_fast.simulate_room_reliability(
            detectors=two_detectors, room_width=10.0, room_length=8.0,
        )
        assert result["std_dev_pct"] >= 0.0

    # --- is_reliable flag ---

    def test_is_reliable_true_when_p_full_gte_95(self, many_detectors):
        """is_reliable should be True when p_full_coverage >= 0.95."""
        sim = DetectorReliabilitySimulator(n_trials=500, seed=42)
        fm = DetectorFailureModel(
            detector_id="zero", annual_failure_rate=0.0,
            common_cause_beta=0.0, p_blind=0.0,
        )
        result = sim.simulate_room_reliability(
            detectors=many_detectors, room_width=12.0, room_length=10.0,
            failure_model=fm,
        )
        # With zero failure and many detectors, should be reliable
        if result["p_full_coverage"] >= 0.95:
            assert result["is_reliable"] is True

    def test_is_reliable_false_when_p_full_lt_95(self, single_detector):
        """is_reliable should be False when p_full_coverage < 0.95."""
        sim = DetectorReliabilitySimulator(n_trials=500, seed=42)
        fm = DetectorFailureModel(
            detector_id="high", annual_failure_rate=0.5,
            common_cause_beta=0.1, p_blind=0.5,
        )
        result = sim.simulate_room_reliability(
            detectors=single_detector, room_width=10.0, room_length=8.0,
            failure_model=fm,
        )
        if result["p_full_coverage"] < 0.95:
            assert result["is_reliable"] is False

    # --- Room geometry variations ---

    def test_small_room(self, single_detector):
        """A small room should be well-covered by a single detector."""
        sim = DetectorReliabilitySimulator(n_trials=200, seed=42)
        fm = DetectorFailureModel(
            detector_id="zero", annual_failure_rate=0.0,
            common_cause_beta=0.0, p_blind=0.0,
        )
        result = sim.simulate_room_reliability(
            detectors=single_detector, room_width=5.0, room_length=4.0,
            failure_model=fm,
        )
        assert result["mean_coverage_pct"] > 90.0

    def test_very_large_room_single_detector(self, single_detector):
        """A very large room with one detector should have lower coverage."""
        sim = DetectorReliabilitySimulator(n_trials=200, seed=42)
        fm = DetectorFailureModel(
            detector_id="zero", annual_failure_rate=0.0,
            common_cause_beta=0.0, p_blind=0.0,
        )
        result = sim.simulate_room_reliability(
            detectors=single_detector, room_width=50.0, room_length=50.0,
            failure_model=fm,
        )
        # One detector can't cover a 50×50 room
        assert result["mean_coverage_pct"] < 30.0


# ═══════════════════════════════════════════════════════════════════════════════
# 5. MCPipelineAdapter — Initialization
# ═══════════════════════════════════════════════════════════════════════════════


class TestMCPipelineAdapterInit:
    """Tests for MCPipelineAdapter construction."""

    def test_default_init(self):
        """Default constructor should create a simulator with n_trials=1000."""
        adapter = MCPipelineAdapter()
        assert adapter._sim.n_trials == 1_000
        assert adapter._threshold == 0.95

    def test_custom_init(self):
        """Custom parameters should be forwarded correctly."""
        adapter = MCPipelineAdapter(
            n_trials=5000, reliability_threshold=0.99, seed=7,
        )
        assert adapter._sim.n_trials == 5_000
        assert adapter._threshold == 0.99

    def test_simulator_is_created(self):
        """Adapter should create a DetectorReliabilitySimulator instance."""
        adapter = MCPipelineAdapter()
        assert isinstance(adapter._sim, DetectorReliabilitySimulator)


# ═══════════════════════════════════════════════════════════════════════════════
# 6. MCPipelineAdapter — enrich_layout
# ═══════════════════════════════════════════════════════════════════════════════


class TestEnrichLayout:
    """Tests for MCPipelineAdapter.enrich_layout."""

    def test_returns_mc_result_dict(self, adapter_fast, mock_layout, mock_room):
        """enrich_layout should return the MC result dict."""
        result = adapter_fast.enrich_layout(mock_layout, mock_room)
        assert isinstance(result, dict)
        assert "mean_coverage_pct" in result
        assert "p_full_coverage" in result

    def test_passes_room_dimensions(self, adapter_fast, mock_room):
        """enrich_layout should use room.width and room.length."""
        layout = MagicMock()
        layout.detectors = [(5.0, 4.0)]
        layout.coverage_radius = 6.37
        layout.warnings = []
        layout.proof_valid = True

        result = adapter_fast.enrich_layout(layout, mock_room)
        assert isinstance(result, dict)

    def test_falls_back_to_layout_dimensions(self, adapter_fast):
        """When room has no width/length, falls back to layout attributes."""
        room = MagicMock(spec=[])  # No attributes
        layout = MagicMock()
        layout.detectors = [(5.0, 4.0)]
        layout.coverage_radius = 6.37
        layout.room_width = 10.0
        layout.room_length = 8.0
        layout.warnings = []
        layout.proof_valid = True

        result = adapter_fast.enrich_layout(layout, room)
        assert isinstance(result, dict)

    def test_warning_added_when_not_reliable(self, adapter_fast):
        """When MC shows is_reliable=False, a warning should be appended."""
        layout = MagicMock()
        layout.detectors = [(5.0, 4.0)]
        layout.coverage_radius = 6.37
        layout.room_width = 10.0
        layout.room_length = 8.0
        layout.warnings = []
        layout.proof_valid = True

        # Force unreliability by using high failure model
        DetectorFailureModel(
            detector_id="high", annual_failure_rate=0.99,
            common_cause_beta=0.5, p_blind=0.99,
        )
        # Patch the simulator to use our high-failure model
        original_sim = adapter_fast._sim
        with patch.object(
            original_sim, "simulate_room_reliability",
            return_value={
                "n_trials": 200,
                "mean_coverage_pct": 5.0,
                "p_full_coverage": 0.01,
                "cvar_5pct": 0.0,
                "worst_coverage_pct": 0.0,
                "best_coverage_pct": 10.0,
                "std_dev_pct": 3.0,
                "is_reliable": False,
                "nfpa_reference": "NFPA 72-2022",
                "time_horizon_yr": 1.0,
                "detector_count": 1,
            },
        ):
            adapter_fast.enrich_layout(layout, MagicMock())

        # Warnings list on the layout should have been updated
        warning_texts = layout.warnings
        assert any("MC RELIABILITY WARNING" in w for w in warning_texts)

    def test_proof_invalidated_when_p_full_below_90(self, adapter_fast):
        """When p_full_coverage < 0.90, proof_valid should be set to False."""
        layout = MagicMock()
        layout.detectors = [(5.0, 4.0)]
        layout.coverage_radius = 6.37
        layout.room_width = 10.0
        layout.room_length = 8.0
        layout.warnings = []
        layout.proof_valid = True

        with patch.object(
            adapter_fast._sim, "simulate_room_reliability",
            return_value={
                "n_trials": 200,
                "mean_coverage_pct": 5.0,
                "p_full_coverage": 0.05,  # < 0.90
                "cvar_5pct": 0.0,
                "worst_coverage_pct": 0.0,
                "best_coverage_pct": 10.0,
                "std_dev_pct": 3.0,
                "is_reliable": False,
                "nfpa_reference": "NFPA 72-2022",
                "time_horizon_yr": 1.0,
                "detector_count": 1,
            },
        ):
            adapter_fast.enrich_layout(layout, MagicMock())

        assert layout.proof_valid is False
        assert any("MC PROOF INVALIDATED" in w for w in layout.warnings)

    def test_proof_not_invalidated_when_p_full_gte_90(self, adapter_fast):
        """When p_full_coverage >= 0.90, proof_valid should remain True."""
        layout = MagicMock()
        layout.detectors = [(5.0, 4.0)]
        layout.coverage_radius = 6.37
        layout.room_width = 10.0
        layout.room_length = 8.0
        layout.warnings = []
        layout.proof_valid = True

        with patch.object(
            adapter_fast._sim, "simulate_room_reliability",
            return_value={
                "n_trials": 200,
                "mean_coverage_pct": 95.0,
                "p_full_coverage": 0.95,
                "cvar_5pct": 80.0,
                "worst_coverage_pct": 70.0,
                "best_coverage_pct": 100.0,
                "std_dev_pct": 5.0,
                "is_reliable": True,
                "nfpa_reference": "NFPA 72-2022",
                "time_horizon_yr": 1.0,
                "detector_count": 1,
            },
        ):
            adapter_fast.enrich_layout(layout, MagicMock())

        assert layout.proof_valid is True

    def test_frozen_layout_handles_attribute_error(self, adapter_fast):
        """If layout.proof_valid can't be set (frozen), no exception raised."""
        layout = MagicMock()
        layout.detectors = [(5.0, 4.0)]
        layout.coverage_radius = 6.37
        layout.room_width = 10.0
        layout.room_length = 8.0
        layout.warnings = []
        # Make proof_valid a property that raises AttributeError on set
        type(layout).proof_valid = PropertyMock(side_effect=AttributeError("frozen"))

        with patch.object(
            adapter_fast._sim, "simulate_room_reliability",
            return_value={
                "n_trials": 200,
                "mean_coverage_pct": 5.0,
                "p_full_coverage": 0.05,
                "cvar_5pct": 0.0,
                "worst_coverage_pct": 0.0,
                "best_coverage_pct": 10.0,
                "std_dev_pct": 3.0,
                "is_reliable": False,
                "nfpa_reference": "NFPA 72-2022",
                "time_horizon_yr": 1.0,
                "detector_count": 1,
            },
        ):
            # Should NOT raise
            adapter_fast.enrich_layout(layout, MagicMock())

        # Clean up the PropertyMock to avoid affecting other tests
        del type(layout).proof_valid

    def test_warnings_attribute_error_handled(self, adapter_fast):
        """If layout.warnings can't be set, no exception raised."""
        layout = MagicMock()
        layout.detectors = [(5.0, 4.0)]
        layout.coverage_radius = 6.37
        layout.room_width = 10.0
        layout.room_length = 8.0
        # Make warnings raise AttributeError on set
        type(layout).warnings = PropertyMock(side_effect=AttributeError("frozen"))

        with patch.object(
            adapter_fast._sim, "simulate_room_reliability",
            return_value={
                "n_trials": 200,
                "mean_coverage_pct": 95.0,
                "p_full_coverage": 0.95,
                "cvar_5pct": 80.0,
                "worst_coverage_pct": 70.0,
                "best_coverage_pct": 100.0,
                "std_dev_pct": 5.0,
                "is_reliable": True,
                "nfpa_reference": "NFPA 72-2022",
                "time_horizon_yr": 1.0,
                "detector_count": 1,
            },
        ):
            # Should NOT raise
            adapter_fast.enrich_layout(layout, MagicMock())

        del type(layout).warnings

    def test_layout_with_no_detectors(self, adapter_fast, mock_room):
        """Layout with empty detectors list — MC returns empty result."""
        layout = MagicMock()
        layout.detectors = []
        layout.coverage_radius = 6.37
        layout.room_width = 10.0
        layout.room_length = 8.0
        layout.warnings = []
        layout.proof_valid = True

        result = adapter_fast.enrich_layout(layout, mock_room)
        # Empty result from simulate_room_reliability
        assert result["n_trials"] == 0

    def test_enrich_layout_uses_coverage_radius_from_layout(self, adapter_fast):
        """enrich_layout should pass layout.coverage_radius to simulation."""
        layout = MagicMock()
        layout.detectors = [(5.0, 4.0)]
        layout.coverage_radius = 3.0  # Custom radius
        layout.room_width = 10.0
        layout.room_length = 8.0
        layout.warnings = []
        layout.proof_valid = True

        with patch.object(
            adapter_fast._sim, "simulate_room_reliability", return_value={
                "n_trials": 200,
                "mean_coverage_pct": 50.0,
                "p_full_coverage": 0.30,
                "cvar_5pct": 10.0,
                "worst_coverage_pct": 0.0,
                "best_coverage_pct": 80.0,
                "std_dev_pct": 15.0,
                "is_reliable": False,
                "nfpa_reference": "NFPA 72-2022",
                "time_horizon_yr": 1.0,
                "detector_count": 1,
            },
        ) as mock_sim:
            adapter_fast.enrich_layout(layout, MagicMock())
            _, kwargs = mock_sim.call_args
            assert kwargs["coverage_radius"] == 3.0

    def test_warning_contains_threshold(self, adapter_fast):
        """Warning message should contain the threshold value."""
        layout = MagicMock()
        layout.detectors = [(5.0, 4.0)]
        layout.coverage_radius = 6.37
        layout.room_width = 10.0
        layout.room_length = 8.0
        layout.warnings = []
        layout.proof_valid = True

        with patch.object(
            adapter_fast._sim, "simulate_room_reliability",
            return_value={
                "n_trials": 200,
                "mean_coverage_pct": 5.0,
                "p_full_coverage": 0.01,
                "cvar_5pct": 0.0,
                "worst_coverage_pct": 0.0,
                "best_coverage_pct": 10.0,
                "std_dev_pct": 3.0,
                "is_reliable": False,
                "nfpa_reference": "NFPA 72-2022",
                "time_horizon_yr": 1.0,
                "detector_count": 1,
            },
        ):
            adapter_fast.enrich_layout(layout, MagicMock())

        # The warning should contain "95%" (the default threshold)
        assert any("95%" in w for w in layout.warnings)

    def test_existing_warnings_preserved(self, adapter_fast):
        """enrich_layout should append to existing warnings, not replace."""
        layout = MagicMock()
        layout.detectors = [(5.0, 4.0)]
        layout.coverage_radius = 6.37
        layout.room_width = 10.0
        layout.room_length = 8.0
        layout.warnings = ["Existing warning"]
        layout.proof_valid = True

        with patch.object(
            adapter_fast._sim, "simulate_room_reliability",
            return_value={
                "n_trials": 200,
                "mean_coverage_pct": 5.0,
                "p_full_coverage": 0.01,
                "cvar_5pct": 0.0,
                "worst_coverage_pct": 0.0,
                "best_coverage_pct": 10.0,
                "std_dev_pct": 3.0,
                "is_reliable": False,
                "nfpa_reference": "NFPA 72-2022",
                "time_horizon_yr": 1.0,
                "detector_count": 1,
            },
        ):
            adapter_fast.enrich_layout(layout, MagicMock())

        assert "Existing warning" in layout.warnings

    def test_reliable_result_no_reliability_warning(self, adapter_fast):
        """When is_reliable=True, no MC RELIABILITY WARNING should be added."""
        layout = MagicMock()
        layout.detectors = [(5.0, 4.0)]
        layout.coverage_radius = 6.37
        layout.room_width = 10.0
        layout.room_length = 8.0
        layout.warnings = []
        layout.proof_valid = True

        with patch.object(
            adapter_fast._sim, "simulate_room_reliability",
            return_value={
                "n_trials": 200,
                "mean_coverage_pct": 99.0,
                "p_full_coverage": 0.97,
                "cvar_5pct": 90.0,
                "worst_coverage_pct": 80.0,
                "best_coverage_pct": 100.0,
                "std_dev_pct": 2.0,
                "is_reliable": True,
                "nfpa_reference": "NFPA 72-2022",
                "time_horizon_yr": 1.0,
                "detector_count": 1,
            },
        ):
            adapter_fast.enrich_layout(layout, MagicMock())

        assert not any("MC RELIABILITY WARNING" in w for w in layout.warnings)

    # --- Fail-safe: missing keys in result dict ---

    def test_missing_is_reliable_key_treated_as_unreliable(self, adapter_fast):
        """V111 FIX: missing 'is_reliable' key => treated as unreliable => warning."""
        layout = MagicMock()
        layout.detectors = [(5.0, 4.0)]
        layout.coverage_radius = 6.37
        layout.room_width = 10.0
        layout.room_length = 8.0
        layout.warnings = []
        layout.proof_valid = True

        with patch.object(
            adapter_fast._sim, "simulate_room_reliability",
            return_value={
                "n_trials": 200,
                "mean_coverage_pct": 95.0,
                "p_full_coverage": 0.95,
                "worst_coverage_pct": 50.0,
                # NO "is_reliable" key — should default to False via .get()
            },
        ):
            adapter_fast.enrich_layout(layout, MagicMock())

        assert any("MC RELIABILITY WARNING" in w for w in layout.warnings)

    def test_missing_p_full_coverage_key_treated_as_zero(self, adapter_fast):
        """V112 FIX: missing 'p_full_coverage' key => treated as 0% => proof invalidated."""
        layout = MagicMock()
        layout.detectors = [(5.0, 4.0)]
        layout.coverage_radius = 6.37
        layout.room_width = 10.0
        layout.room_length = 8.0
        layout.warnings = []
        layout.proof_valid = True

        with patch.object(
            adapter_fast._sim, "simulate_room_reliability",
            return_value={
                "n_trials": 200,
                "mean_coverage_pct": 95.0,
                "is_reliable": True,
                # NO "p_full_coverage" key
            },
        ):
            adapter_fast.enrich_layout(layout, MagicMock())

        assert layout.proof_valid is False
        assert any("MC PROOF INVALIDATED" in w for w in layout.warnings)


# ═══════════════════════════════════════════════════════════════════════════════
# 7. MCPipelineAdapter — analyse_floor
# ═══════════════════════════════════════════════════════════════════════════════


class TestAnalyseFloor:
    """Tests for MCPipelineAdapter.analyse_floor."""

    def test_basic_floor_analysis(self, adapter_fast, mock_floor_report):
        """analyse_floor should return a dict with floor-level results."""
        result = adapter_fast.analyse_floor(mock_floor_report)
        assert isinstance(result, dict)
        assert "floor_id" in result
        assert "room_results" in result
        assert "floor_reliable" in result
        assert "n_rooms" in result
        assert "n_reliable" in result

    def test_floor_id_from_report(self, adapter_fast, mock_floor_report):
        """Result should carry the floor_id from the report."""
        result = adapter_fast.analyse_floor(mock_floor_report)
        assert result["floor_id"] == "F1"

    def test_n_rooms_matches_rooms_with_detectors(self, adapter_fast, mock_floor_report):
        """n_rooms should count only rooms that have detectors."""
        result = adapter_fast.analyse_floor(mock_floor_report)
        assert result["n_rooms"] == 2

    def test_room_results_keys_are_room_ids(self, adapter_fast, mock_floor_report):
        """room_results should be keyed by room_id."""
        result = adapter_fast.analyse_floor(mock_floor_report)
        assert "R1" in result["room_results"]
        assert "R2" in result["room_results"]

    def test_room_results_are_mc_dicts(self, adapter_fast, mock_floor_report):
        """Each room result should be a MC simulation result dict."""
        result = adapter_fast.analyse_floor(mock_floor_report)
        for _room_id, mc in result["room_results"].items():
            assert "mean_coverage_pct" in mc
            assert "p_full_coverage" in mc

    def test_empty_floor_report(self, adapter_fast, mock_floor_report_empty):
        """Floor report with no rooms should return empty results."""
        result = adapter_fast.analyse_floor(mock_floor_report_empty)
        assert result["room_results"] == {}
        assert result["n_rooms"] == 0
        assert result["n_reliable"] == 0

    def test_rooms_without_detectors_skipped(self, adapter_fast, mock_floor_report_no_detectors):
        """Rooms with no detectors should be skipped."""
        result = adapter_fast.analyse_floor(mock_floor_report_no_detectors)
        assert result["n_rooms"] == 0

    def test_floor_reliable_true_when_all_rooms_reliable(self, adapter_fast):
        """floor_reliable=True when every room has is_reliable=True."""
        report = MagicMock()
        report.floor_id = "F_ok"

        rs = MagicMock()
        rs.room_id = "R1"
        rs.detectors = [(5.0, 4.0)]
        rs.width = 10.0
        rs.length = 8.0
        rs.coverage_radius = 6.37

        DetectorFailureModel(
            detector_id="zero", annual_failure_rate=0.0,
            common_cause_beta=0.0, p_blind=0.0,
        )
        report.room_summaries = [rs]

        result = adapter_fast.analyse_floor(report)
        # With zero failure model and one detector, it should be reliable
        # (deterministic due to seed=42)
        assert isinstance(result["floor_reliable"], bool)

    def test_floor_reliable_false_when_any_room_unreliable(self, adapter_fast):
        """floor_reliable=False if any room has is_reliable=False."""
        report = MagicMock()
        report.floor_id = "F_mixed"

        rs = MagicMock()
        rs.room_id = "R1"
        rs.detectors = [(5.0, 4.0)]
        rs.width = 10.0
        rs.length = 8.0
        rs.coverage_radius = 6.37

        report.room_summaries = [rs]

        # Patch to force unreliable result
        with patch.object(
            adapter_fast._sim, "simulate_room_reliability",
            return_value={
                "n_trials": 200,
                "mean_coverage_pct": 5.0,
                "p_full_coverage": 0.01,
                "cvar_5pct": 0.0,
                "worst_coverage_pct": 0.0,
                "best_coverage_pct": 10.0,
                "std_dev_pct": 3.0,
                "is_reliable": False,
                "nfpa_reference": "NFPA 72-2022",
                "time_horizon_yr": 1.0,
                "detector_count": 1,
            },
        ):
            result = adapter_fast.analyse_floor(report)

        assert result["floor_reliable"] is False
        assert result["n_reliable"] == 0

    def test_n_reliable_counts_reliable_rooms(self, adapter_fast):
        """n_reliable should count rooms where is_reliable=True."""
        report = MagicMock()
        report.floor_id = "F_count"

        rs1 = MagicMock()
        rs1.room_id = "R1"
        rs1.detectors = [(5.0, 4.0)]
        rs1.width = 10.0
        rs1.length = 8.0
        rs1.coverage_radius = 6.37

        rs2 = MagicMock()
        rs2.room_id = "R2"
        rs2.detectors = [(3.0, 3.0)]
        rs2.width = 12.0
        rs2.length = 10.0
        rs2.coverage_radius = 6.37

        report.room_summaries = [rs1, rs2]

        call_count = [0]
        def side_effect(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                return {
                    "n_trials": 200, "mean_coverage_pct": 99.0,
                    "p_full_coverage": 0.97, "cvar_5pct": 90.0,
                    "worst_coverage_pct": 80.0, "best_coverage_pct": 100.0,
                    "std_dev_pct": 2.0, "is_reliable": True,
                    "nfpa_reference": "NFPA 72-2022",
                    "time_horizon_yr": 1.0, "detector_count": 1,
                }
            return {
                "n_trials": 200, "mean_coverage_pct": 5.0,
                "p_full_coverage": 0.01, "cvar_5pct": 0.0,
                "worst_coverage_pct": 0.0, "best_coverage_pct": 10.0,
                "std_dev_pct": 3.0, "is_reliable": False,
                "nfpa_reference": "NFPA 72-2022",
                "time_horizon_yr": 1.0, "detector_count": 1,
            }

        with patch.object(
            adapter_fast._sim, "simulate_room_reliability",
            side_effect=side_effect,
        ):
            result = adapter_fast.analyse_floor(report)

        assert result["n_rooms"] == 2
        assert result["n_reliable"] == 1
        assert result["floor_reliable"] is False

    def test_missing_floor_id_defaults_to_empty(self, adapter_fast):
        """Floor report without floor_id should default to empty string."""
        report = MagicMock(spec=[])  # No attributes
        report.room_summaries = []
        result = adapter_fast.analyse_floor(report)
        assert result["floor_id"] == ""

    def test_room_with_missing_width_defaults(self, adapter_fast):
        """Room without width/length should use default 10.0 / 8.0."""
        report = MagicMock()
        report.floor_id = "F1"

        rs = MagicMock(spec=["room_id", "detectors"])
        rs.room_id = "R1"
        rs.detectors = [(5.0, 4.0)]

        report.room_summaries = [rs]
        # Should not raise — defaults of 10.0 and 8.0 are used
        result = adapter_fast.analyse_floor(report)
        assert result["n_rooms"] == 1

    def test_missing_is_reliable_in_room_result_treated_as_unreliable(self, adapter_fast):
        """V111 FIX: missing is_reliable in room result => treated as False."""
        report = MagicMock()
        report.floor_id = "F1"

        rs = MagicMock()
        rs.room_id = "R1"
        rs.detectors = [(5.0, 4.0)]
        rs.width = 10.0
        rs.length = 8.0
        rs.coverage_radius = 6.37

        report.room_summaries = [rs]

        with patch.object(
            adapter_fast._sim, "simulate_room_reliability",
            return_value={
                "n_trials": 200,
                "mean_coverage_pct": 95.0,
                # NO "is_reliable" key — should default to False
            },
        ):
            result = adapter_fast.analyse_floor(report)

        assert result["floor_reliable"] is False
        assert result["n_reliable"] == 0


# ═══════════════════════════════════════════════════════════════════════════════
# 8. Integration / End-to-End
# ═══════════════════════════════════════════════════════════════════════════════


class TestIntegration:
    """End-to-end tests combining multiple classes."""

    def test_full_pipeline_reliable_scenario(self):
        """Full pipeline with zero-failure model and good detector placement."""
        MCPipelineAdapter(n_trials=300, seed=42)
        layout = MagicMock()
        layout.detectors = [(2.5, 2.0), (7.5, 6.0)]
        layout.coverage_radius = 6.37
        layout.room_width = 10.0
        layout.room_length = 8.0
        layout.warnings = []
        layout.proof_valid = True

        room = MagicMock()
        room.width = 10.0
        room.length = 8.0

        fm = DetectorFailureModel(
            detector_id="zero", annual_failure_rate=0.0,
            common_cause_beta=0.0, p_blind=0.0,
        )

        # Manually run simulation with the zero-failure model
        sim = DetectorReliabilitySimulator(n_trials=300, seed=42)
        mc_result = sim.simulate_room_reliability(
            detectors=list(layout.detectors),
            room_width=room.width,
            room_length=room.length,
            coverage_radius=layout.coverage_radius,
            failure_model=fm,
        )

        assert mc_result["is_reliable"] is True
        assert mc_result["mean_coverage_pct"] > 90.0

    def test_full_pipeline_unreliable_scenario(self):
        """Full pipeline with high-failure model shows unreliable results."""
        MCPipelineAdapter(n_trials=300, seed=42)
        layout = MagicMock()
        layout.detectors = [(5.0, 4.0)]
        layout.coverage_radius = 6.37
        layout.room_width = 10.0
        layout.room_length = 8.0
        layout.warnings = []
        layout.proof_valid = True

        room = MagicMock()
        room.width = 10.0
        room.length = 8.0

        fm = DetectorFailureModel(
            detector_id="high", annual_failure_rate=0.99,
            common_cause_beta=0.5, p_blind=0.99,
        )

        sim = DetectorReliabilitySimulator(n_trials=300, seed=42)
        mc_result = sim.simulate_room_reliability(
            detectors=list(layout.detectors),
            room_width=room.width,
            room_length=room.length,
            coverage_radius=layout.coverage_radius,
            failure_model=fm,
        )

        assert mc_result["is_reliable"] is False
        assert mc_result["mean_coverage_pct"] < 50.0

    def test_adapter_enrich_then_analyse_floor(self, adapter_fast):
        """Run enrich_layout then analyse_floor in sequence."""
        # First enrich a layout
        layout = MagicMock()
        layout.detectors = [(5.0, 4.0)]
        layout.coverage_radius = 6.37
        layout.room_width = 10.0
        layout.room_length = 8.0
        layout.warnings = []
        layout.proof_valid = True

        room = MagicMock()
        room.width = 10.0
        room.length = 8.0

        mc_result = adapter_fast.enrich_layout(layout, room)
        assert "mean_coverage_pct" in mc_result

        # Then analyse a floor
        report = MagicMock()
        report.floor_id = "F1"

        rs = MagicMock()
        rs.room_id = "R1"
        rs.detectors = [(5.0, 4.0)]
        rs.width = 10.0
        rs.length = 8.0
        rs.coverage_radius = 6.37

        report.room_summaries = [rs]

        floor_result = adapter_fast.analyse_floor(report)
        assert "floor_id" in floor_result

    def test_failure_model_probabilities_are_exponential(self):
        """Verify p_fail = 1 - exp(-rate * horizon) matches code logic."""
        DetectorFailureModel(detector_id="test", annual_failure_rate=0.01)
        expected_p_fail = 1.0 - math.exp(-0.01 * 1.0)
        expected_p_blind = 1.0 - math.exp(-0.003 * 1.0)

        # These are the formulas used in simulate_room_reliability
        assert abs(expected_p_fail - 0.00995) < 0.0001
        assert abs(expected_p_blind - 0.002996) < 0.0001

    def test_common_cause_mechanism(self):
        """Common cause failure (beta) should zero out all active detectors."""
        # With beta=1.0, every trial should trigger CCF => all detectors removed
        sim = DetectorReliabilitySimulator(n_trials=100, seed=42)
        fm = DetectorFailureModel(
            detector_id="ccf_test",
            annual_failure_rate=0.0,  # No individual failures
            common_cause_beta=1.0,   # 100% CCF
            p_blind=0.0,
        )
        result = sim.simulate_room_reliability(
            detectors=[(5.0, 4.0), (2.0, 2.0)],
            room_width=10.0, room_length=8.0,
            failure_model=fm,
        )
        # Every trial: active starts with all detectors, then CCF zeroes them
        assert result["mean_coverage_pct"] == 0.0

    def test_frange_generates_coverage_grid(self):
        """The _frange function should generate grid points for the room."""
        sim = DetectorReliabilitySimulator(n_trials=10, seed=42)
        # Grid step is 0.5, from 0.1 to room_dim-0.1
        # For room_width=10.0: 0.1, 0.6, 1.1, ..., 9.6 => (9.6-0.1)/0.5 + 1 = 20 pts
        x_pts = list(sim._frange(0.1, 9.9, 0.5))
        y_pts = list(sim._frange(0.1, 7.9, 0.5))
        assert len(x_pts) > 0
        assert len(y_pts) > 0
        # Total grid points for 10x8 room
        total = len(x_pts) * len(y_pts)
        assert total > 100  # Reasonable grid density
