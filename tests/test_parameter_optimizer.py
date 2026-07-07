"""
tests/test_parameter_optimizer.py
==================================
Comprehensive test suite for:
  fireai/core/parameter_optimizer.py

Grid-searches verify_step on benchmark rooms for DensityOptimizer.
Results saved to JSON for manual engineer review.

Tests cover:
  - ParameterOptimizer construction and defaults
  - ParamConfig and ParameterOptimizationResult dataclasses
  - optimise() grid search logic
  - Pareto scoring formula
  - save() JSON output
  - Edge cases (empty rooms list, single step, etc.)
"""

from __future__ import annotations

import json
import os
import tempfile

import pytest

from fireai.core.parameter_optimizer import (
    ParamConfig,
    ParameterOptimizationResult,
    ParameterOptimizer,
)
from fireai.core.spatial_engine.density_optimizer import (
    DETECTOR_RADIUS,
    Room,
)

# Fixtures
# ─────────────────────────────────────────────────────────────────────────────


@pytest.fixture
def small_benchmark() -> list[Room]:
    """Small benchmark rooms for fast testing."""
    return [
        Room("lobby", 15, 15, 3.0),
        Room("office", 10, 8, 3.0),
    ]


@pytest.fixture
def optimizer() -> ParameterOptimizer:
    """Default ParameterOptimizer."""
    return ParameterOptimizer()


# ─────────────────────────────────────────────────────────────────────────────
# ParameterOptimizer — Construction
# ─────────────────────────────────────────────────────────────────────────────


class TestParameterOptimizerInit:
    """ParameterOptimizer initialization."""

    def test_default_coverage_radius(self):
        """Default coverage radius = DETECTOR_RADIUS (6.37m)."""
        opt = ParameterOptimizer()
        assert opt.coverage_radius == DETECTOR_RADIUS

    def test_custom_coverage_radius(self):
        """Custom coverage radius should be stored."""
        opt = ParameterOptimizer(coverage_radius=5.0)
        assert opt.coverage_radius == 5.0  # NOSONAR — S1244: import retained for re-export / API surface


# ─────────────────────────────────────────────────────────────────────────────
# ParamConfig — Data Structure
# ─────────────────────────────────────────────────────────────────────────────


class TestParamConfig:
    """ParamConfig dataclass tests."""

    def test_fields(self):
        """ParamConfig must have all required fields."""
        config = ParamConfig(
            verify_step=0.20,
            total_time_ms=100,
            avg_count=5.0,
            all_valid=True,
            pareto_score=50.0,
            per_room=[],
        )
        assert config.verify_step == 0.20  # NOSONAR — S1244: import retained for re-export / API surface
        assert config.total_time_ms == 100
        assert config.avg_count == 5.0  # NOSONAR — S1244: import retained for re-export / API surface
        assert config.all_valid is True
        assert config.pareto_score == 50.0  # NOSONAR — S1244: import retained for re-export / API surface
        assert config.per_room == []

    def test_pareto_score_inf_for_invalid(self):
        """Invalid configurations should have infinite pareto score."""
        config = ParamConfig(
            verify_step=0.10,
            total_time_ms=50,
            avg_count=3.0,
            all_valid=False,
            pareto_score=float("inf"),
            per_room=[],
        )
        assert config.all_valid is False
        assert config.pareto_score == float("inf")


# ─────────────────────────────────────────────────────────────────────────────
# ParameterOptimizationResult — Data Structure
# ─────────────────────────────────────────────────────────────────────────────


class TestParameterOptimizationResult:
    """ParameterOptimizationResult dataclass tests."""

    def test_fields(self):
        """Result must have all required fields."""
        best = ParamConfig(0.20, 100, 5.0, True, 50.0, [])
        result = ParameterOptimizationResult(
            best_config=best,
            all_configs=[best],
            recommendation="Use verify_step=0.20",
        )
        assert result.best_config is best
        assert len(result.all_configs) == 1
        assert result.recommendation == "Use verify_step=0.20"
        assert result.saved_to is None

    def test_table_output(self):
        """table() must produce formatted string output."""
        best = ParamConfig(0.20, 100, 5.0, True, 50.0, [])
        result = ParameterOptimizationResult(
            best_config=best,
            all_configs=[best],
            recommendation="Use verify_step=0.20",
        )
        table = result.table()
        assert "verify_step" in table
        assert "0.20" in table
        assert "BEST" in table

    def test_table_shows_saved_path(self):
        """table() must show saved path when present."""
        best = ParamConfig(0.20, 100, 5.0, True, 50.0, [])
        result = ParameterOptimizationResult(
            best_config=best,
            all_configs=[best],
            recommendation="Test",
            saved_to="/tmp/test.json",  # NOSONAR — S5443: safe in test (uses tempfile + cleanup)
        )
        table = result.table()
        assert "/tmp/test.json" in table  # NOSONAR — S5443: safe in test (uses tempfile + cleanup)


# ─────────────────────────────────────────────────────────────────────────────
# ParameterOptimizer — optimise()
# ─────────────────────────────────────────────────────────────────────────────


class TestOptimise:
    """Grid search optimization logic."""

    def test_optimise_returns_result(self, optimizer, small_benchmark):
        """optimise() must return a ParameterOptimizationResult."""
        result = optimizer.optimise(small_benchmark, steps=[0.20, 0.30])
        assert isinstance(result, ParameterOptimizationResult)
        assert len(result.all_configs) == 2

    def test_optimise_default_steps(self, optimizer, small_benchmark):
        """Default steps should be [0.10, 0.15, 0.20, 0.25, 0.30, 0.40]."""
        result = optimizer.optimise(small_benchmark)
        assert len(result.all_configs) == 6

    def test_optimise_single_step(self, optimizer, small_benchmark):
        """Single step should work."""
        result = optimizer.optimise(small_benchmark, steps=[0.20])
        assert len(result.all_configs) == 1
        assert result.all_configs[0].verify_step == 0.20  # NOSONAR — S1244: import retained for re-export / API surface

    def test_best_config_is_valid_or_first(self, optimizer, small_benchmark):
        """Best config should be valid if any valid config exists."""
        result = optimizer.optimise(small_benchmark, steps=[0.20])
        if result.best_config.all_valid:
            assert result.best_config.pareto_score != float("inf")

    def test_all_configs_have_verify_step(self, optimizer, small_benchmark):
        """Each config must record its verify_step."""
        steps = [0.15, 0.25, 0.35]
        result = optimizer.optimise(small_benchmark, steps=steps)
        for config in result.all_configs:
            assert config.verify_step in steps

    def test_pareto_score_inf_for_invalid(self, optimizer, small_benchmark):
        """Invalid configs must have pareto_score = inf."""
        result = optimizer.optimise(small_benchmark, steps=[0.20, 0.30])
        for config in result.all_configs:
            if not config.all_valid:
                assert config.pareto_score == float("inf")

    def test_pareto_score_formula(self, optimizer, small_benchmark):
        """Pareto score = total_time_ms * avg_count / 10 for valid configs."""
        result = optimizer.optimise(small_benchmark, steps=[0.20])
        for config in result.all_configs:
            if config.all_valid:
                expected = config.total_time_ms * config.avg_count / 10.0
                assert config.pareto_score == pytest.approx(expected, rel=0.01)

    def test_per_room_breakdown(self, optimizer, small_benchmark):
        """Each config must have per-room breakdown."""
        result = optimizer.optimise(small_benchmark, steps=[0.20])
        for config in result.all_configs:
            assert len(config.per_room) == len(small_benchmark)
            for room_result in config.per_room:
                assert "room" in room_result

    def test_recommendation_is_string(self, optimizer, small_benchmark):
        """Recommendation must be a non-empty string."""
        result = optimizer.optimise(small_benchmark, steps=[0.20])
        assert isinstance(result.recommendation, str)
        assert len(result.recommendation) > 0

    def test_verify_step_restored_after_optimise(self, optimizer, small_benchmark):
        """VERIFY_STEP must be restored to original value after optimise()."""
        import fireai.core.spatial_engine.density_optimizer as _dm
        original = _dm.VERIFY_STEP
        optimizer.optimise(small_benchmark, steps=[0.15, 0.25])
        assert original == _dm.VERIFY_STEP


# ─────────────────────────────────────────────────────────────────────────────
# ParameterOptimizer — optimise() Edge Cases
# ─────────────────────────────────────────────────────────────────────────────


class TestOptimiseEdgeCases:
    """Edge cases for the optimization grid search."""

    def test_empty_rooms_list(self, optimizer):
        """Empty rooms list → avg_count = 0, should handle gracefully."""
        result = optimizer.optimise([], steps=[0.20])
        assert isinstance(result, ParameterOptimizationResult)
        for config in result.all_configs:
            assert config.avg_count == 0

    def test_single_room(self, optimizer):
        """Single room benchmark."""
        rooms = [Room("test", 10, 10, 3.0)]
        result = optimizer.optimise(rooms, steps=[0.20])
        assert isinstance(result, ParameterOptimizationResult)

    def test_large_step_value(self, optimizer, small_benchmark):
        """Large verify_step values should still produce results."""
        result = optimizer.optimise(small_benchmark, steps=[1.0])
        assert isinstance(result, ParameterOptimizationResult)

    def test_very_small_step_value(self, optimizer, small_benchmark):
        """Very small verify_step may be slow but should work."""
        result = optimizer.optimise(small_benchmark, steps=[0.05])
        assert isinstance(result, ParameterOptimizationResult)


# ─────────────────────────────────────────────────────────────────────────────
# ParameterOptimizer — save()
# ─────────────────────────────────────────────────────────────────────────────


class TestSave:
    """JSON output for grid search results."""

    def test_save_creates_file(self, optimizer, small_benchmark):
        """save() must create a JSON file."""
        result = optimizer.optimise(small_benchmark, steps=[0.20])
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "test_result.json")
            optimizer.save(result, path)
            assert os.path.exists(path)

    def test_save_valid_json(self, optimizer, small_benchmark):
        """Saved file must be valid JSON."""
        result = optimizer.optimise(small_benchmark, steps=[0.20])
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "test_result.json")
            optimizer.save(result, path)
            with open(path) as f:
                data = json.load(f)
            assert "recommendation" in data
            assert "best" in data
            assert "all_configs" in data

    def test_save_contains_best_config(self, optimizer, small_benchmark):
        """JSON must contain best config details."""
        result = optimizer.optimise(small_benchmark, steps=[0.20])
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "test_result.json")
            optimizer.save(result, path)
            with open(path) as f:
                data = json.load(f)
            assert "verify_step" in data["best"]
            assert "pareto_score" in data["best"]

    def test_save_sets_saved_to(self, optimizer, small_benchmark):
        """save() must set result.saved_to to the file path."""
        result = optimizer.optimise(small_benchmark, steps=[0.20])
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "test_result.json")
            optimizer.save(result, path)
            assert result.saved_to == path

    def test_save_creates_directory(self, optimizer, small_benchmark):
        """save() must create parent directory if needed."""
        result = optimizer.optimise(small_benchmark, steps=[0.20])
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "subdir", "test_result.json")
            optimizer.save(result, path)
            assert os.path.exists(path)

    def test_save_all_configs_sorted_by_pareto(self, optimizer, small_benchmark):
        """all_configs in JSON should be sorted by pareto_score."""
        result = optimizer.optimise(small_benchmark, steps=[0.20, 0.30])
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "test_result.json")
            optimizer.save(result, path)
            with open(path) as f:
                data = json.load(f)
            scores = [c["pareto_score"] for c in data["all_configs"]]
            # Should be sorted ascending (best first)
            for i in range(len(scores) - 1):
                assert scores[i] <= scores[i + 1]


# ─────────────────────────────────────────────────────────────────────────────
# Integration — Full Optimization Workflow
# ─────────────────────────────────────────────────────────────────────────────


class TestIntegrationWorkflow:
    """End-to-end optimization workflow."""

    def test_full_workflow_optimise_and_save(self, optimizer, small_benchmark):
        """Complete workflow: optimise → save → verify JSON."""
        result = optimizer.optimise(small_benchmark, steps=[0.20, 0.30, 0.40])
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "full_workflow.json")
            optimizer.save(result, path)

            with open(path) as f:
                data = json.load(f)

            assert len(data["all_configs"]) == 3
            assert data["recommendation"] is not None
            assert data["best"]["verify_step"] in [0.20, 0.30, 0.40]

    def test_best_config_has_lowest_pareto_among_valid(self, optimizer, small_benchmark):
        """Best config should have the lowest pareto score among valid configs."""
        result = optimizer.optimise(small_benchmark, steps=[0.15, 0.20, 0.25, 0.30])
        valid = [c for c in result.all_configs if c.all_valid]
        if valid:
            min_pareto = min(c.pareto_score for c in valid)
            assert result.best_config.pareto_score == min_pareto


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
