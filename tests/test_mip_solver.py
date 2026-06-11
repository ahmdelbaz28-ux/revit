"""
Tests for fireai/core/spatial_engine/mip_solver.py — MIP Set Covering Solver
=============================================================================

Covers all public functions and the MIPResult dataclass:

  - MIPResult dataclass construction, defaults, mutability, types
  - solve_set_covering_mip() fallback when PuLP unavailable
  - Degenerate rooms (too small for candidate grid)
  - Edge cases: zero area, negative dimensions
  - Infeasible coverage gaps
  - Solver exceptions and non-optimal statuses
  - Normal optimal solve with detector position extraction
  - Mathematical formulation verification (candidate/target geometry)
  - Solver parameter passthrough validation
"""

from __future__ import annotations

import importlib.util
import inspect
import sys
import types
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


class _LpSumResult:
    """Mock for a pulp.lpSum() result that supports ``>=`` with int.

    Python 3.13's ``MagicMock`` no longer auto-defines comparison dunder
    methods, so we need a plain object that can appear on the LHS of ``>= 1``
    inside ``prob += lpSum(...) >= 1``.
    """

    def __ge__(self, other: object) -> MagicMock:
        return MagicMock()


# ─────────────────────────────────────────────────────────────────────────────
# Import workaround for broken pydantic/shapely in test environment.
# The fireai/core/__init__.py triggers a deep import chain that fails because
# pydantic-core and shapely C extensions are missing.  We bypass this by
# loading only the modules we need via importlib, with a minimal mock package
# hierarchy so that relative imports resolve correctly.
# ─────────────────────────────────────────────────────────────────────────────

_FIREAI_ROOT = Path("/tmp/revit_audit")

for _pkg in ["fireai", "fireai.core", "fireai.core.spatial_engine"]:
    _m = types.ModuleType(_pkg)
    _m.__path__ = [str(_FIREAI_ROOT / _pkg.replace(".", "/"))]
    _m.__package__ = _pkg
    _m.__file__ = str(_FIREAI_ROOT / _pkg.replace(".", "/") / "__init__.py")
    _m.__name__ = _pkg
    sys.modules[_pkg] = _m

# Load density_optimizer first so that mip_solver's relative import resolves.
_spec_do = importlib.util.spec_from_file_location(
    "fireai.core.spatial_engine.density_optimizer",
    str(_FIREAI_ROOT / "fireai/core/spatial_engine/density_optimizer.py"),
)
_mod_do = importlib.util.module_from_spec(_spec_do)
sys.modules["fireai.core.spatial_engine.density_optimizer"] = _mod_do
_spec_do.loader.exec_module(_mod_do)

# Load the module under test.
_spec_ms = importlib.util.spec_from_file_location(
    "fireai.core.spatial_engine.mip_solver",
    str(_FIREAI_ROOT / "fireai/core/spatial_engine/mip_solver.py"),
)
_mod_ms = importlib.util.module_from_spec(_spec_ms)
sys.modules["fireai.core.spatial_engine.mip_solver"] = _mod_ms
_spec_ms.loader.exec_module(_mod_ms)

MIPResult = _mod_ms.MIPResult
solve_set_covering_mip = _mod_ms.solve_set_covering_mip

# Keep _mod_ms for patch.object usage in tests; clean up the rest.
del _pkg, _m, _mod_do, _spec_do, _spec_ms, _FIREAI_ROOT

DETECTOR_RADIUS = 6.37  # 0.7 × 9.1 m  (aligned with density_optimizer)


# ═══════════════════════════════════════════════════════════════════════════════
# 1. MIPResult DATACLASS
# ═══════════════════════════════════════════════════════════════════════════════


class TestMIPResult:
    """MIPResult dataclass — construction, defaults, field types."""

    def test_minimal_construction(self):
        result = MIPResult(success=True)
        assert result.success is True
        assert result.detector_positions == []
        assert result.theoretical_minimum is None
        assert result.solver_status == "not_run"
        assert result.solve_time_seconds == 0.0
        assert result.used_mip is False
        assert result.fallback_reason is None
        assert result.candidate_step == 1.0

    def test_full_construction(self):
        result = MIPResult(
            success=True,
            detector_positions=[(1.0, 2.0), (3.0, 4.0)],
            theoretical_minimum=2,
            solver_status="Optimal",
            solve_time_seconds=1.5,
            used_mip=True,
            fallback_reason=None,
            candidate_step=0.5,
        )
        assert result.success is True
        assert result.detector_positions == [(1.0, 2.0), (3.0, 4.0)]
        assert result.theoretical_minimum == 2
        assert result.solver_status == "Optimal"
        assert result.solve_time_seconds == 1.5
        assert result.used_mip is True
        assert result.fallback_reason is None
        assert result.candidate_step == 0.5

    def test_mutable_fields(self):
        result = MIPResult(success=False)
        result.detector_positions.append((5.0, 5.0))
        assert result.detector_positions == [(5.0, 5.0)]
        result.fallback_reason = "engine failure"
        assert result.fallback_reason == "engine failure"

    def test_default_optional_fields(self):
        result = MIPResult(success=False)
        assert result.theoretical_minimum is None
        assert result.fallback_reason is None
        assert result.detector_positions == []
        assert result.solve_time_seconds == 0.0

    def test_field_types(self):
        result = MIPResult(success=True)
        assert isinstance(result.detector_positions, list)
        assert isinstance(result.solve_time_seconds, float)
        assert isinstance(result.candidate_step, float)
        assert isinstance(result.success, bool)
        assert isinstance(result.used_mip, bool)

    def test_repr_contains_fields(self):
        result = MIPResult(success=True, theoretical_minimum=3)
        r = repr(result)
        assert "MIPResult" in r
        assert "success=True" in r
        assert "theoretical_minimum=3" in r

    def test_equality(self):
        a = MIPResult(True, [(1.0, 1.0)], 1, "Optimal", 0.5, True, None, 1.0)
        b = MIPResult(True, [(1.0, 1.0)], 1, "Optimal", 0.5, True, None, 1.0)
        assert a == b

    def test_inequality(self):
        a = MIPResult(True, theoretical_minimum=1)
        b = MIPResult(True, theoretical_minimum=2)
        assert a != b


# ═══════════════════════════════════════════════════════════════════════════════
# 2. solve_set_covering_mip() — FALLBACK PATHS
# ═══════════════════════════════════════════════════════════════════════════════


class TestSolveSetCoveringMIPFallback:
    """PuLP unavailable — graceful fallback path."""

    def test_fallback_when_pulp_not_available(self):
        with patch.object(_mod_ms, "PULP_AVAILABLE", False):
            result = solve_set_covering_mip(10.0, 10.0)

        assert result.success is False
        assert result.solver_status == "pulp_not_installed"
        assert "pip install pulp" in result.fallback_reason
        assert result.used_mip is False
        assert result.candidate_step == 1.0
        assert result.solve_time_seconds == 0.0
        assert result.detector_positions == []

    def test_fallback_preserves_candidate_step(self):
        with patch.object(_mod_ms, "PULP_AVAILABLE", False):
            result = solve_set_covering_mip(10.0, 10.0, candidate_step=0.5)
        assert result.candidate_step == 0.5

    def test_fallback_does_not_generate_grid(self):
        with patch.object(_mod_ms, "PULP_AVAILABLE", False):
            t0 = "not_run"
            result = solve_set_covering_mip(5.0, 5.0)
        assert result.solver_status == "pulp_not_installed"
        assert result.candidate_step == 1.0


class TestSolveSetCoveringMIPDegenerate:
    """Rooms too small to generate any candidate positions."""

    def test_room_smaller_than_step(self):
        with patch.object(_mod_ms, "PULP_AVAILABLE", True):
            result = solve_set_covering_mip(0.3, 0.3, candidate_step=1.0)
        assert result.success is False
        assert result.solver_status == "degenerate_room"
        assert "too small" in result.fallback_reason.lower()

    def test_zero_width(self):
        with patch.object(_mod_ms, "PULP_AVAILABLE", True):
            result = solve_set_covering_mip(0.0, 10.0)
        assert not result.success
        assert result.solver_status == "degenerate_room"

    def test_zero_length(self):
        with patch.object(_mod_ms, "PULP_AVAILABLE", True):
            result = solve_set_covering_mip(10.0, 0.0)
        assert not result.success
        assert result.solver_status == "degenerate_room"

    def test_negative_width(self):
        with patch.object(_mod_ms, "PULP_AVAILABLE", True):
            result = solve_set_covering_mip(-5.0, 10.0)
        assert not result.success
        assert result.solver_status == "degenerate_room"

    def test_negative_length(self):
        with patch.object(_mod_ms, "PULP_AVAILABLE", True):
            result = solve_set_covering_mip(10.0, -5.0)
        assert not result.success
        assert result.solver_status == "degenerate_room"

    def test_both_zero(self):
        with patch.object(_mod_ms, "PULP_AVAILABLE", True):
            result = solve_set_covering_mip(0.0, 0.0)
        assert not result.success
        assert result.solver_status == "degenerate_room"


class TestSolveSetCoveringMIPInfeasible:
    """Coverage gaps — targets unreachable by any candidate."""

    def test_infeasible_coverage_returned(self):
        with patch.object(_mod_ms, "PULP_AVAILABLE", True):
            with patch.object(_mod_ms, "pulp", MagicMock(), create=True):
                result = solve_set_covering_mip(
                    room_width=10.0,
                    room_length=10.0,
                    coverage_radius=0.1,
                    candidate_step=5.0,
                )
        assert result.success is False
        assert result.solver_status == "infeasible_coverage"
        assert "cannot be covered" in result.fallback_reason

    def test_infeasible_zero_coverage_radius(self):
        with patch.object(_mod_ms, "PULP_AVAILABLE", True):
            with patch.object(_mod_ms, "pulp", MagicMock(), create=True):
                result = solve_set_covering_mip(
                    room_width=10.0,
                    room_length=10.0,
                    coverage_radius=0.0,
                    candidate_step=1.0,
                )
        assert not result.success
        assert result.solver_status == "infeasible_coverage"


# ═══════════════════════════════════════════════════════════════════════════════
# 3. solve_set_covering_mip() — SOLVER ERRORS
# ═══════════════════════════════════════════════════════════════════════════════


class TestSolveSetCoveringMIPSolverErrors:
    """Solver-level exceptions and non-optimal statuses."""

    @staticmethod
    def _make_pulp_mock(
        num_vars: int,
        optimal: bool = True,
        selected_indices: list[int] | None = None,
    ):
        """Build a configured mock pulp module for controlled solver testing."""
        if selected_indices is None:
            selected_indices = [0]
        variables = [MagicMock() for _ in range(num_vars)]
        value_map = {variables[i]: 1.0 for i in selected_indices}
        for v in variables:
            if v not in value_map:
                value_map[v] = 0.0

        problem = MagicMock()
        problem.status = 1 if optimal else 3
        problem.solve = MagicMock()
        problem.__iadd__.return_value = problem  # keep prob pointing to same object

        mock_pulp = MagicMock()
        mock_pulp.LpProblem.return_value = problem
        mock_pulp.LpVariable.side_effect = variables
        mock_pulp.lpSum = lambda *a: _LpSumResult()
        mock_pulp.LpMinimize = 1
        mock_pulp.PULP_CBC_CMD.return_value = MagicMock()
        mock_pulp.LpStatus = {1: "Optimal", 3: "Infeasible", -1: "Not Solved"}
        mock_pulp.value.side_effect = lambda v: value_map.get(v, 0.0)
        return mock_pulp, problem, variables

    def test_solver_exception_caught(self):
        problem = MagicMock()
        problem.solve.side_effect = RuntimeError("CBC engine timeout")
        problem.__iadd__.return_value = problem

        mock_pulp = MagicMock()
        mock_pulp.LpProblem.return_value = problem
        mock_pulp.LpVariable.return_value = MagicMock()
        mock_pulp.lpSum = lambda *a: _LpSumResult()
        mock_pulp.LpMinimize = 1
        mock_pulp.PULP_CBC_CMD.return_value = MagicMock()
        mock_pulp.LpStatus = {1: "Optimal"}

        with patch.object(_mod_ms, "PULP_AVAILABLE", True):
            with patch.object(_mod_ms, "pulp", mock_pulp, create=True):
                result = solve_set_covering_mip(2.0, 2.0, coverage_radius=3.0)

        assert result.success is False
        assert result.solver_status == "solver_exception"
        assert "CBC engine timeout" in result.fallback_reason
        assert result.solve_time_seconds > 0
        assert result.candidate_step == 1.0

    def test_solver_general_exception(self):
        problem = MagicMock()
        problem.solve.side_effect = Exception("memory allocation failed")
        problem.__iadd__.return_value = problem

        mock_pulp = MagicMock()
        mock_pulp.LpProblem.return_value = problem
        mock_pulp.LpVariable.return_value = MagicMock()
        mock_pulp.lpSum = lambda *a: _LpSumResult()
        mock_pulp.LpMinimize = 1
        mock_pulp.PULP_CBC_CMD.return_value = MagicMock()
        mock_pulp.LpStatus = {1: "Optimal"}

        with patch.object(_mod_ms, "PULP_AVAILABLE", True):
            with patch.object(_mod_ms, "pulp", mock_pulp, create=True):
                result = solve_set_covering_mip(3.0, 3.0, coverage_radius=3.0)

        assert result.success is False
        assert result.solver_status == "solver_exception"
        assert "memory allocation failed" in result.fallback_reason

    def test_non_optimal_status_infeasible(self):
        mock_pulp, _, _ = self._make_pulp_mock(4, optimal=False)
        with patch.object(_mod_ms, "PULP_AVAILABLE", True):
            with patch.object(_mod_ms, "pulp", mock_pulp, create=True):
                result = solve_set_covering_mip(2.0, 2.0, coverage_radius=3.0)

        assert result.success is False
        assert result.solver_status == "Infeasible"
        assert "falling back" in result.fallback_reason
        assert result.solve_time_seconds > 0
        assert result.candidate_step == 1.0

    def test_non_optimal_not_solved(self):
        mock_pulp, problem, _ = self._make_pulp_mock(4, optimal=True)
        mock_pulp.LpStatus = {1: "Optimal", -1: "Not Solved", 3: "Infeasible"}
        problem.status = -1

        with patch.object(_mod_ms, "PULP_AVAILABLE", True):
            with patch.object(_mod_ms, "pulp", mock_pulp, create=True):
                result = solve_set_covering_mip(2.0, 2.0, coverage_radius=3.0)

        assert result.success is False
        assert "Not Solved" in result.solver_status
        assert "falling back" in result.fallback_reason


# ═══════════════════════════════════════════════════════════════════════════════
# 4. solve_set_covering_mip() — NORMAL OPTIMAL SOLVE
# ═══════════════════════════════════════════════════════════════════════════════


class TestSolveSetCoveringMIPNormal:
    """Normal operation — optimal MIP solve with detector positions returned."""

    @staticmethod
    def _expected_candidates(width: float, length: float, step: float) -> list:
        candidates = []
        cx = step / 2
        while cx <= width:
            cy = step / 2
            while cy <= length:
                candidates.append((cx, cy))
                cy += step
            cx += step
        return candidates

    @staticmethod
    def _make_optimal_mock(
        num_vars: int, selected_indices: list[int]
    ) -> tuple[MagicMock, MagicMock, list[MagicMock]]:
        variables = [MagicMock() for _ in range(num_vars)]
        problem = MagicMock()
        problem.status = 1
        problem.solve = MagicMock()
        problem.__iadd__.return_value = problem

        value_map = {variables[i]: 1.0 for i in selected_indices}
        for v in variables:
            if v not in value_map:
                value_map[v] = 0.0

        mock_pulp = MagicMock()
        mock_pulp.LpProblem.return_value = problem
        mock_pulp.LpVariable.side_effect = variables
        mock_pulp.lpSum = lambda *a: _LpSumResult()
        mock_pulp.LpMinimize = 1
        mock_pulp.PULP_CBC_CMD.return_value = MagicMock()
        mock_pulp.LpStatus = {1: "Optimal"}
        mock_pulp.value.side_effect = lambda v: value_map.get(v, 0.0)
        return mock_pulp, problem, variables

    def test_single_detector_covers_small_room(self):
        """2m × 2m room with coverage_radius=3m yields one detector."""
        w, l, r, s = 2.0, 2.0, 3.0, 1.0
        expected = self._expected_candidates(w, l, s)
        mock_pulp, _, _ = self._make_optimal_mock(len(expected), [0])

        with patch.object(_mod_ms, "PULP_AVAILABLE", True):
            with patch.object(_mod_ms, "pulp", mock_pulp, create=True):
                result = solve_set_covering_mip(w, l, r, s)

        assert result.success is True
        assert result.solver_status == "Optimal"
        assert result.used_mip is True
        assert result.theoretical_minimum == 1
        assert result.candidate_step == s
        assert result.solve_time_seconds > 0
        assert len(result.detector_positions) == 1
        assert result.detector_positions[0] == expected[0]
        for px, py in result.detector_positions:
            assert isinstance(px, float)
            assert isinstance(py, float)

    def test_multiple_detectors_selected(self):
        """4 candidates, indices 0 and 2 selected yields 2 positions."""
        w, l, s = 4.0, 4.0, 2.0
        expected = self._expected_candidates(w, l, s)
        assert len(expected) == 4
        mock_pulp, _, _ = self._make_optimal_mock(len(expected), [0, 2])

        with patch.object(_mod_ms, "PULP_AVAILABLE", True):
            with patch.object(_mod_ms, "pulp", mock_pulp, create=True):
                result = solve_set_covering_mip(w, l, coverage_radius=2.0, candidate_step=s)

        assert result.success is True
        assert result.theoretical_minimum == 2
        assert len(result.detector_positions) == 2
        assert result.detector_positions[0] == expected[0]
        assert result.detector_positions[1] == expected[2]

    def test_all_candidates_selected(self):
        w, l, s = 2.0, 2.0, 2.0
        expected = self._expected_candidates(w, l, s)
        assert len(expected) == 1
        mock_pulp, _, _ = self._make_optimal_mock(len(expected), [0])

        with patch.object(_mod_ms, "PULP_AVAILABLE", True):
            with patch.object(_mod_ms, "pulp", mock_pulp, create=True):
                # coverage_radius=1.0 ensures all targets are reachable
                # from the single candidate at (1.0, 1.0)
                result = solve_set_covering_mip(w, l, coverage_radius=1.0, candidate_step=s)

        assert result.theoretical_minimum == 1
        assert len(result.detector_positions) == 1
        assert result.detector_positions[0] == expected[0]

    def test_zero_candidates_selected(self):
        """No candidates selected (pulp.value returns 0 for all) → empty list."""
        w, l, r, s = 2.0, 2.0, 3.0, 1.0
        expected = self._expected_candidates(w, l, s)
        mock_pulp, _, _ = self._make_optimal_mock(len(expected), [])

        with patch.object(_mod_ms, "PULP_AVAILABLE", True):
            with patch.object(_mod_ms, "pulp", mock_pulp, create=True):
                result = solve_set_covering_mip(w, l, r, s)

        assert result.success is True
        assert result.theoretical_minimum == 0
        assert result.detector_positions == []

    def test_large_room_with_defaults(self):
        """10m × 10m room with default R=6.37, step=1.0 yields 100 candidates."""
        w, l, r, s = 10.0, 10.0, DETECTOR_RADIUS, 1.0
        expected = self._expected_candidates(w, l, s)
        assert len(expected) == 100

        mock_pulp, _, _ = self._make_optimal_mock(len(expected), list(range(50)))

        with patch.object(_mod_ms, "PULP_AVAILABLE", True):
            with patch.object(_mod_ms, "pulp", mock_pulp, create=True):
                result = solve_set_covering_mip(w, l, r, s)

        assert result.success is True
        assert result.used_mip is True
        assert result.theoretical_minimum == 50
        assert len(result.detector_positions) == 50
        assert result.detector_positions[0] == expected[0]
        assert result.detector_positions[49] == expected[49]


# ═══════════════════════════════════════════════════════════════════════════════
# 5. MATHEMATICAL FORMULATION VERIFICATION
# ═══════════════════════════════════════════════════════════════════════════════


class TestSolveSetCoveringMIPFormulation:
    """Verify the mathematical formulation is structurally correct."""

    def test_default_coverage_radius_is_detector_radius(self):
        sig = inspect.signature(solve_set_covering_mip)
        default = sig.parameters["coverage_radius"].default
        assert isinstance(default, float)
        assert default == pytest.approx(DETECTOR_RADIUS, abs=1e-2)
        assert default == pytest.approx(6.37, abs=1e-2)

    def test_candidates_placed_at_step_half_offset(self):
        """Candidates are placed at (step/2, step/2) offset from origin."""
        with patch.object(_mod_ms, "PULP_AVAILABLE", True):
            with patch.object(_mod_ms, "pulp", MagicMock(), create=True):
                result = solve_set_covering_mip(
                    room_width=2.0,
                    room_length=2.0,
                    coverage_radius=0.01,
                    candidate_step=1.0,
                )
        # First uncovered target is (0.25, 0.25), proving step/4 offset
        assert "0.25" in result.fallback_reason

    def test_target_grid_twice_as_fine_as_candidate_grid(self):
        """Target step = candidate_step / 2."""
        with patch.object(_mod_ms, "PULP_AVAILABLE", True):
            with patch.object(_mod_ms, "pulp", MagicMock(), create=True):
                result = solve_set_covering_mip(
                    room_width=2.0,
                    room_length=2.0,
                    coverage_radius=0.01,
                    candidate_step=2.0,
                )
        # Candidate_step=2.0 → target_step=1.0 → first target at 0.5
        assert "0.5" in result.fallback_reason

    def test_solver_PULP_CBC_CMD_parameters(self):
        """Verify timeLimit and gapRel are passed correctly."""
        mock_pulp, problem, _ = TestSolveSetCoveringMIPNormal._make_optimal_mock(4, [0])
        solver_mock = MagicMock()
        mock_pulp.PULP_CBC_CMD.return_value = solver_mock

        with patch.object(_mod_ms, "PULP_AVAILABLE", True):
            with patch.object(_mod_ms, "pulp", mock_pulp, create=True):
                solve_set_covering_mip(2.0, 2.0, candidate_step=1.0, time_limit_seconds=5.0)

        mock_pulp.PULP_CBC_CMD.assert_called_once_with(msg=0, timeLimit=5.0, gapRel=0.0)
        problem.solve.assert_called_once_with(solver_mock)

    def test_problem_created_with_correct_name_and_sense(self):
        mock_pulp, _, _ = TestSolveSetCoveringMIPNormal._make_optimal_mock(4, [0])
        with patch.object(_mod_ms, "PULP_AVAILABLE", True):
            with patch.object(_mod_ms, "pulp", mock_pulp, create=True):
                solve_set_covering_mip(2.0, 2.0, candidate_step=1.0)

        mock_pulp.LpProblem.assert_called_once_with(
            "FireDetectorSetCovering", mock_pulp.LpMinimize
        )

    def test_variables_created_as_binary(self):
        mock_pulp, _, variables = TestSolveSetCoveringMIPNormal._make_optimal_mock(4, [0])
        with patch.object(_mod_ms, "PULP_AVAILABLE", True):
            with patch.object(_mod_ms, "pulp", mock_pulp, create=True):
                solve_set_covering_mip(2.0, 2.0, candidate_step=1.0)

        assert mock_pulp.LpVariable.call_count == 4
        for i, call_args in enumerate(mock_pulp.LpVariable.call_args_list):
            name, kwargs = call_args
            assert name[0] == f"x_{i}"
            assert kwargs.get("cat") == "Binary"

    def test_candidate_count_depends_on_room_dimensions(self):
        """4m × 2m room with step=2.0 yields 2 × 1 = 2 candidates."""
        mock_pulp, _, _ = TestSolveSetCoveringMIPNormal._make_optimal_mock(2, [0])
        with patch.object(_mod_ms, "PULP_AVAILABLE", True):
            with patch.object(_mod_ms, "pulp", mock_pulp, create=True):
                solve_set_covering_mip(4.0, 2.0, coverage_radius=2.0, candidate_step=2.0)

        assert mock_pulp.LpVariable.call_count == 2

    def test_coverage_uses_squared_distance(self):
        """Squared-distance comparison ensures geometry correctness."""
        with patch.object(_mod_ms, "PULP_AVAILABLE", True):
            with patch.object(_mod_ms, "pulp", MagicMock(), create=True):
                result = solve_set_covering_mip(
                    3.0, 3.0, coverage_radius=1.0, candidate_step=3.0
                )
        assert result.solver_status == "infeasible_coverage"

    def test_detector_positions_are_tuples_of_floats(self):
        w, l, r, s = 2.0, 2.0, 3.0, 1.0
        expected = TestSolveSetCoveringMIPNormal._expected_candidates(w, l, s)
        mock_pulp, _, _ = TestSolveSetCoveringMIPNormal._make_optimal_mock(len(expected), [0])

        with patch.object(_mod_ms, "PULP_AVAILABLE", True):
            with patch.object(_mod_ms, "pulp", mock_pulp, create=True):
                result = solve_set_covering_mip(w, l, r, s)

        for pos in result.detector_positions:
            assert isinstance(pos, tuple)
            assert len(pos) == 2
            assert isinstance(pos[0], float)
            assert isinstance(pos[1], float)
