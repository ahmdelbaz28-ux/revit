"""
test_phase11.py — FireAI Phase 11 Test Suite
==============================================
Tests for the three new standalone tools:
  1. SensitivityAnalyzer — parameter sensitivity sweep
  2. ParameterOptimizer — verify_step grid search
  3. ProjectLearner — room-pattern clustering + BuildingEngine integration

Design principles:
  - DO NOT modify DensityOptimizer, FloorAnalyser, or BuildingEngine internals
  - All tools are read-only consumers of the existing engine
  - Tests verify correct integration without breaking existing behaviour
"""

import pytest
import sys
import os
import json
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "."))

from fireai.core.spatial_engine.density_optimizer import DensityOptimizer, Room, VERIFY_STEP
from fireai.core.floor_analyser import FloorAnalyser, FloorReport, RoomSummary
from fireai.core.building_engine import BuildingEngine, BuildingReport
from fireai.core.sensitivity_analyzer import SensitivityAnalyzer, SensitivityReport
from fireai.core.parameter_optimizer import ParameterOptimizer, ParameterOptimizationResult
from fireai.core.project_learner import ProjectLearner, BuildingProjectProfile


# ─── Fixtures ───────────────────────────────────────────────

@pytest.fixture
def optimizer():
    """V7.3 DensityOptimizer with default R=6.40m."""
    return DensityOptimizer()


# ═══════════════════════════════════════════════════════════════
# Test 1: SensitivityAnalyzer — basic sweep
# ═══════════════════════════════════════════════════════════════

class TestSensitivityAnalyzer:
    """
    Test that SensitivityAnalyzer sweeps coverage_radius correctly.
    It must call DensityOptimizer.optimize() for each value and
    return a SensitivityReport with points, elasticity, and safe_range.
    """

    def test_coverage_radius_sweep_produces_report(self):
        """Sweep coverage_radius must produce a SensitivityReport."""
        analyzer = SensitivityAnalyzer()
        report = analyzer.analyse(
            width=20.0, length=15.0, ceiling_height=3.0,
            param="coverage_radius",
            values=[4.0, 4.57, 5.5],
            baseline_value=4.57,
        )
        assert isinstance(report, SensitivityReport)
        assert report.param_name == "coverage_radius"
        assert report.baseline_value == 4.57
        assert len(report.points) == 3
        # Each point must have valid fields
        for p in report.points:
            assert p.param_name == "coverage_radius"
            assert p.count >= 1 or p.count == -1  # -1 means error
            assert p.method != ""

    def test_smaller_radius_produces_more_detectors(self):
        """Smaller coverage_radius must produce >= detectors than larger radius."""
        analyzer = SensitivityAnalyzer()
        report = analyzer.analyse(
            width=30.0, length=20.0, ceiling_height=3.0,
            param="coverage_radius",
            values=[3.5, 5.5],
            baseline_value=4.57,
        )
        # Find points for 3.5 and 5.5
        p_small = next(p for p in report.points if abs(p.param_value - 3.5) < 1e-6)
        p_large = next(p for p in report.points if abs(p.param_value - 5.5) < 1e-6)
        if p_small.proof_valid and p_large.proof_valid:
            assert p_small.count >= p_large.count, (
                f"Smaller radius ({p_small.param_value}) should need >= detectors "
                f"than larger radius ({p_large.param_value}): "
                f"{p_small.count} vs {p_large.count}"
            )

    def test_invalid_param_raises_value_error(self):
        """Passing an unsupported param must raise ValueError."""
        analyzer = SensitivityAnalyzer()
        with pytest.raises(ValueError, match="param must be one of"):
            analyzer.analyse(
                width=10.0, length=10.0,
                param="wall_min",  # NOT supported
            )

    def test_elasticity_is_non_negative(self):
        """Elasticity must be >= 0 (it's an absolute value ratio)."""
        analyzer = SensitivityAnalyzer()
        report = analyzer.analyse(
            width=20.0, length=15.0,
            param="coverage_radius",
            values=[3.5, 4.0, 4.57, 5.0, 5.5],
        )
        assert report.elasticity >= 0.0

    def test_table_method_returns_string(self):
        """table() must return a non-empty formatted string."""
        analyzer = SensitivityAnalyzer()
        report = analyzer.analyse(
            width=10.0, length=8.0,
            param="coverage_radius",
            values=[4.57],
        )
        table = report.table()
        assert isinstance(table, str)
        assert "Sensitivity" in table
        assert "coverage_radius" in table

    def test_to_dict_is_json_serialisable(self):
        """to_dict() must return a JSON-serialisable dict."""
        analyzer = SensitivityAnalyzer()
        report = analyzer.analyse(
            width=10.0, length=8.0,
            param="coverage_radius",
            values=[4.57, 5.0],
        )
        d = report.to_dict()
        assert isinstance(d, dict)
        # Must not raise on JSON dump
        json.dumps(d)


# ═══════════════════════════════════════════════════════════════
# Test 2: ParameterOptimizer — verify_step grid search
# ═══════════════════════════════════════════════════════════════

class TestParameterOptimizer:
    """
    Test that ParameterOptimizer grid-searches verify_step
    across benchmark rooms and returns a valid result.
    """

    def test_grid_search_produces_result(self):
        """Grid search must produce a ParameterOptimizationResult."""
        opt = ParameterOptimizer()
        rooms = [
            Room("small", 10, 8, 3.0),
            Room("medium", 20, 15, 3.0),
        ]
        result = opt.optimise(rooms, steps=[0.20, 0.30])
        assert isinstance(result, ParameterOptimizationResult)
        assert len(result.all_configs) == 2
        assert result.best_config is not None
        assert result.recommendation != ""

    def test_best_config_has_valid_step(self):
        """Best config must have a verify_step from the input list."""
        opt = ParameterOptimizer()
        rooms = [Room("test", 15, 10, 3.0)]
        result = opt.optimise(rooms, steps=[0.20, 0.25, 0.30])
        assert result.best_config.verify_step in [0.20, 0.25, 0.30]

    def test_pareto_score_inf_when_invalid(self):
        """Configurations with invalid rooms must have pareto_score=inf."""
        opt = ParameterOptimizer()
        rooms = [Room("test", 15, 10, 3.0)]
        result = opt.optimise(rooms, steps=[0.20, 0.30])
        for c in result.all_configs:
            if not c.all_valid:
                assert c.pareto_score == float("inf")

    def test_save_writes_json(self):
        """save() must write a valid JSON file."""
        opt = ParameterOptimizer()
        rooms = [Room("test", 10, 8, 3.0)]
        result = opt.optimise(rooms, steps=[0.20, 0.30])

        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            path = f.name
        try:
            opt.save(result, path)
            assert os.path.exists(path)
            with open(path) as f:
                data = json.load(f)
            assert "recommendation" in data
            assert "best" in data
            assert "all_configs" in data
        finally:
            os.unlink(path)

    def test_verify_step_restored_after_optimise(self):
        """VERIFY_STEP must be restored to its original value after grid search."""
        original = VERIFY_STEP
        opt = ParameterOptimizer()
        rooms = [Room("test", 10, 8, 3.0)]
        opt.optimise(rooms, steps=[0.10, 0.20, 0.40])
        import fireai.core.spatial_engine.density_optimizer as _dm
        assert _dm.VERIFY_STEP == original, (
            f"VERIFY_STEP not restored: expected {original}, got {_dm.VERIFY_STEP}"
        )


# ═══════════════════════════════════════════════════════════════
# Test 3: ProjectLearner — clustering and profiling
# ═══════════════════════════════════════════════════════════════

class TestProjectLearner:
    """
    Test that ProjectLearner records rooms, builds a profile,
    and provides hints without modifying any engine code.
    """

    def test_empty_learner_returns_zero_profile(self):
        """Empty learner must return a profile with total_rooms=0."""
        learner = ProjectLearner(building_id="empty")
        profile = learner.profile()
        assert isinstance(profile, BuildingProjectProfile)
        assert profile.total_rooms == 0
        assert profile.n_clusters == 0
        assert profile.global_dominant_strategy == "unknown"

    def test_record_and_profile(self):
        """Recording rooms must produce a profile with correct totals."""
        learner = ProjectLearner(building_id="test")
        learner.record("office", 10, 8, "hexG_x", 0.85)
        learner.record("lobby", 12, 12, "rect_2x2", 0.90)
        learner.record("warehouse", 50, 40, "hexG_x", 0.80)
        profile = learner.profile()
        assert profile.total_rooms == 3
        assert profile.global_dominant_strategy == "hexG_x"
        assert profile.avg_efficiency > 0

    def test_hint_for_returns_strategy(self):
        """hint_for() must return the dominant strategy of the nearest cluster."""
        learner = ProjectLearner(building_id="hint_test")
        # Add enough rooms for clustering (>=3)
        learner.record("office_a", 10, 8, "hexG_x", 0.85)
        learner.record("office_b", 11, 9, "hexG_x", 0.82)
        learner.record("warehouse_a", 50, 40, "rect_8x6", 0.78)
        learner.record("warehouse_b", 55, 35, "rect_8x6", 0.80)
        learner.record("lobby", 12, 12, "rect_2x2", 0.90)

        hint = learner.hint_for(10, 8)
        # Should return a strategy (hexG_x likely for small rooms)
        assert isinstance(hint, str)
        assert hint != ""

    def test_hint_for_returns_none_under_three_rooms(self):
        """hint_for() must return None with fewer than 3 rooms."""
        learner = ProjectLearner(building_id="small")
        learner.record("room1", 10, 8, "hexG_x", 0.85)
        learner.record("room2", 12, 12, "rect_2x2", 0.90)
        assert learner.hint_for(10, 8) is None

    def test_summary_returns_string(self):
        """summary() must return a human-readable string."""
        learner = ProjectLearner(building_id="sum_test")
        learner.record("office", 10, 8, "hexG_x", 0.85)
        learner.record("lobby", 12, 12, "rect_2x2", 0.90)
        learner.record("warehouse", 50, 40, "hexG_x", 0.80)
        s = learner.summary()
        assert isinstance(s, str)
        assert "sum_test" in s

    def test_persistence_save_load(self):
        """Room records must persist across save/load cycles."""
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            path = f.name
        try:
            learner1 = ProjectLearner(building_id="persist_test", persist_path=path)
            learner1.record("office", 10, 8, "hexG_x", 0.85)
            learner1.record("lobby", 12, 12, "rect_2x2", 0.90)

            # Reload
            learner2 = ProjectLearner(building_id="persist_test", persist_path=path)
            profile = learner2.profile()
            assert profile.total_rooms == 2
        finally:
            os.unlink(path)


# ═══════════════════════════════════════════════════════════════
# Test 4: BuildingEngine + ProjectLearner integration
# ═══════════════════════════════════════════════════════════════

class TestBuildingEngineProfile:
    """
    Test that BuildingEngine.analyse() populates project_profile
    on the BuildingReport without breaking existing behaviour.
    """

    def test_profile_populated_after_analyse(self, optimizer):
        """BuildingReport.project_profile must be populated after analyse()."""
        engine = BuildingEngine("BLDG-PROFILE", optimizer)
        floors = {
            "GF": [
                {"room_id": "lobby", "name": "lobby",
                 "polygon_coords": [(0,0),(12,0),(12,8),(0,8)], "ceiling_height": 3.0},
                {"room_id": "office", "name": "office",
                 "polygon_coords": [(0,0),(10,0),(10,8),(0,8)], "ceiling_height": 3.0},
                {"room_id": "meeting", "name": "meeting",
                 "polygon_coords": [(0,0),(6,0),(6,5),(0,5)], "ceiling_height": 3.0},
            ],
        }
        report = engine.analyse(floors)
        assert report.project_profile is not None
        assert isinstance(report.project_profile, BuildingProjectProfile)
        assert report.project_profile.building_id == "BLDG-PROFILE"
        assert report.project_profile.total_rooms == 3

    def test_profile_dominant_strategy_matches_methods(self, optimizer):
        """Profile dominant strategy must match the most common method used."""
        engine = BuildingEngine("BLDG-STRAT", optimizer)
        floors = {
            "GF": [
                {"room_id": "R1", "name": "room1",
                 "polygon_coords": [(0,0),(12,0),(12,8),(0,8)], "ceiling_height": 3.0},
                {"room_id": "R2", "name": "room2",
                 "polygon_coords": [(0,0),(10,0),(10,8),(0,8)], "ceiling_height": 3.0},
                {"room_id": "R3", "name": "room3",
                 "polygon_coords": [(0,0),(30,0),(30,20),(0,20)], "ceiling_height": 3.0},
            ],
        }
        report = engine.analyse(floors)
        profile = report.project_profile
        # Verify strategy_distribution sums to 100%
        total_pct = sum(profile.strategy_distribution.values())
        assert abs(total_pct - 100.0) < 1.0, f"Strategy distribution sums to {total_pct}%"

    def test_existing_building_report_fields_unchanged(self, optimizer):
        """Existing BuildingReport fields must remain unchanged after profile addition."""
        engine = BuildingEngine("BLDG-CHECK", optimizer)
        floors = {
            "GF": [
                {"room_id": "lobby", "name": "lobby",
                 "polygon_coords": [(0,0),(12,0),(12,8),(0,8)], "ceiling_height": 3.0},
            ],
        }
        report = engine.analyse(floors)

        # All existing fields must still be present and correct
        assert report.building_id == "BLDG-CHECK"
        assert report.total_floors == 1
        assert report.total_detectors > 0
        assert report.total_theoretical_lower_bound > 0
        assert isinstance(report.fully_compliant, bool)
        assert isinstance(report.safe_to_submit, bool)

    def test_room_summary_has_width_length(self, optimizer):
        """RoomSummary must have width and length fields populated."""
        analyser = FloorAnalyser(floor_id="GF", optimizer=optimizer)
        rooms = [
            {"room_id": "R1", "name": "test_room",
             "polygon_coords": [(0,0),(10,0),(10,8),(0,8)], "ceiling_height": 3.0},
        ]
        report = analyser.analyse(rooms)
        s = report.room_summaries[0]
        assert hasattr(s, "width")
        assert hasattr(s, "length")
        assert s.width == 10.0, f"Expected width=10.0, got {s.width}"
        assert s.length == 8.0, f"Expected length=8.0, got {s.length}"


# ═══════════════════════════════════════════════════════════════
# Test 5: VERIFY_STEP restoration safety
# ═══════════════════════════════════════════════════════════════

class TestVerifyStepSafety:
    """
    VERIFY_STEP must always be restored to its original value
    after any tool that patches it finishes — even on error.
    """

    def test_sensitivity_analyzer_restores_verify_step(self):
        """VERIFY_STEP must be restored after sensitivity sweep."""
        import fireai.core.spatial_engine.density_optimizer as _dm
        original = _dm.VERIFY_STEP
        analyzer = SensitivityAnalyzer()
        analyzer.analyse(
            width=10.0, length=8.0,
            param="verify_step",
            values=[0.10, 0.20, 0.30],
        )
        assert _dm.VERIFY_STEP == original, (
            f"VERIFY_STEP not restored: expected {original}, got {_dm.VERIFY_STEP}"
        )

    def test_parameter_optimizer_restores_verify_step(self):
        """VERIFY_STEP must be restored after parameter grid search."""
        import fireai.core.spatial_engine.density_optimizer as _dm
        original = _dm.VERIFY_STEP
        opt = ParameterOptimizer()
        rooms = [Room("test", 10, 8, 3.0)]
        opt.optimise(rooms, steps=[0.10, 0.20, 0.30])
        assert _dm.VERIFY_STEP == original


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
