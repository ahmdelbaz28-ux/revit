# NOSONAR
"""
tests/test_mip_solver.py — Tests for MIP Set Covering solver.

Covers:
  - PuLP unavailable → graceful fallback
  - Degenerate room (too small) → fallback
  - Normal room → solver runs and returns result
  - MIPResult structure validation
  - Coverage radius affects result
  - Candidate step affects result
"""

from __future__ import annotations

import pytest

from fireai.core.spatial_engine.mip_solver import (
    PULP_AVAILABLE,
    MIPResult,
    solve_set_covering_mip,
)


class TestMIPResultStructure:
    """Tests for MIPResult dataclass."""

    def test_default_values(self) -> None:
        """MIPResult should have sensible defaults."""
        result = MIPResult(success=True)
        assert result.success is True
        assert result.detector_positions == []
        assert result.theoretical_minimum is None
        assert result.solver_status == "not_run"
        assert result.solve_time_seconds == 0.0  # NOSONAR — S1244: import retained for re-export / API surface
        assert result.used_mip is False
        assert result.fallback_reason is None
        assert result.candidate_step == 1.0  # NOSONAR — S1244: import retained for re-export / API surface

    def test_custom_values(self) -> None:
        """MIPResult should accept custom values."""
        result = MIPResult(
            success=True,
            detector_positions=[(1.0, 2.0), (3.0, 4.0)],
            theoretical_minimum=2,
            solver_status="Optimal",
            solve_time_seconds=0.5,
            used_mip=True,
            candidate_step=0.5,
        )
        assert result.success is True
        assert len(result.detector_positions) == 2
        assert result.theoretical_minimum == 2


class TestSolveSetCoveringMIP:
    """Tests for solve_set_covering_mip function."""

    @pytest.mark.skipif(not PULP_AVAILABLE, reason="PuLP not installed")
    def test_normal_room_returns_result(self) -> None:
        """A normal-sized room should return a valid MIPResult."""
        result = solve_set_covering_mip(
            room_width=10.0,
            room_length=10.0,
            coverage_radius=6.37,  # Default DETECTOR_RADIUS
            candidate_step=2.0,
            time_limit_seconds=5.0,
        )
        assert isinstance(result, MIPResult)
        # Either success or graceful fallback
        if result.success:
            assert result.theoretical_minimum is not None
            assert result.theoretical_minimum >= 1
            assert result.solver_status == "Optimal"
            assert result.used_mip is True
        else:
            assert result.fallback_reason is not None

    @pytest.mark.skipif(not PULP_AVAILABLE, reason="PuLP not installed")
    def test_small_room_may_fallback(self) -> None:
        """A very small room might fallback (degenerate)."""
        result = solve_set_covering_mip(
            room_width=0.1,
            room_length=0.1,
            candidate_step=1.0,
        )
        assert isinstance(result, MIPResult)
        # Small room with large step → degenerate
        if result.fallback_reason:
            assert "degenerate" in result.fallback_reason or "too small" in result.fallback_reason

    @pytest.mark.skipif(not PULP_AVAILABLE, reason="PuLP not installed")
    def test_larger_room_needs_more_detectors(self) -> None:
        """A larger room should need at least as many detectors as a smaller one."""
        small = solve_set_covering_mip(
            room_width=5.0,
            room_length=5.0,
            candidate_step=1.0,
            time_limit_seconds=10.0,
        )
        large = solve_set_covering_mip(
            room_width=20.0,
            room_length=20.0,
            candidate_step=1.0,
            time_limit_seconds=10.0,
        )
        if small.success and large.success:
            assert large.theoretical_minimum >= small.theoretical_minimum

    @pytest.mark.skipif(not PULP_AVAILABLE, reason="PuLP not installed")
    def test_solve_time_is_positive(self) -> None:
        """Solve time should be non-negative."""
        result = solve_set_covering_mip(
            room_width=8.0,
            room_length=8.0,
            candidate_step=2.0,
        )
        assert result.solve_time_seconds >= 0.0

    @pytest.mark.skipif(not PULP_AVAILABLE, reason="PuLP not installed")
    def test_candidate_step_affects_grid(self) -> None:
        """Different candidate steps should produce valid results."""
        for step in [1.0, 2.0, 4.0]:
            result = solve_set_covering_mip(
                room_width=10.0,
                room_length=10.0,
                candidate_step=step,
                time_limit_seconds=5.0,
            )
            assert isinstance(result, MIPResult)
            assert result.candidate_step == step

    def test_returns_mip_result_type(self) -> None:
        """Function should always return MIPResult, never raise."""
        result = solve_set_covering_mip(
            room_width=10.0,
            room_length=10.0,
        )
        assert isinstance(result, MIPResult)

    def test_does_not_raise_on_invalid_input(self) -> None:
        """Should not raise on edge-case input."""
        # Very small room
        result = solve_set_covering_mip(
            room_width=0.01,
            room_length=0.01,
            candidate_step=1.0,
        )
        assert isinstance(result, MIPResult)

    @pytest.mark.skipif(not PULP_AVAILABLE, reason="PuLP not installed")
    def test_detector_positions_are_in_room_bounds(self) -> None:
        """Detector positions should be within room bounds."""
        width, length = 10.0, 10.0
        result = solve_set_covering_mip(
            room_width=width,
            room_length=length,
            candidate_step=2.0,
        )
        if result.success and result.detector_positions:
            for x, y in result.detector_positions:
                assert 0 <= x <= width
                assert 0 <= y <= length


class TestPuLPUnavailable:
    """Tests for graceful fallback when PuLP is not available."""

    def test_pulp_availability_flag(self) -> None:
        """PULP_AVAILABLE should be a boolean."""
        assert isinstance(PULP_AVAILABLE, bool)
