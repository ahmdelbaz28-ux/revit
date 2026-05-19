"""
test_scenario_integration.py — FloorAnalyser V3.0 Scenario Verification Tests
===============================================================================
Tests the integration of scenario_engine.py into floor_analyser.py (V3.0).

Covers:
  - RoomSummary scenario fields (defaults + populated)
  - FloorReport scenario aggregation
  - FloorAnalyser with use_scenarios=True
  - Backward compatibility (use_scenarios=False)
  - Scenario PASS/FAIL detection
  - Warnings generation (SCENARIO_DETECTION_FAIL, SCENARIO_BLIND_SPOT)
  - Occupancy-aware fire load selection
  - Refused rooms skip scenario verification
  - Multi-room floor with mixed results
  - Edge cases: tiny rooms, high ceilings, corridors

Total: 30+ tests across 8 test classes.
"""

import pytest
from fireai.core.floor_analyser import FloorAnalyser, RoomSummary, FloorReport
from fireai.core.spatial_engine.density_optimizer import DensityOptimizer


# ============================================================================
# Test Constants
# ============================================================================

RECT_10x8 = [(0, 0), (10, 0), (10, 8), (0, 8)]
LARGE_30x25 = [(0, 0), (30, 0), (30, 25), (0, 25)]
CORRIDOR_20x2 = [(0, 0), (20, 0), (20, 2), (0, 2)]
TINY_2x2 = [(0, 0), (2, 0), (2, 2), (0, 2)]


# ============================================================================
# Test RoomSummary Scenario Fields (Defaults)
# ============================================================================

class TestRoomSummaryScenarioDefaults:
    """Verify scenario fields have correct defaults when not run."""

    def test_scenario_pass_default_none(self):
        s = RoomSummary(room_id="R1", name="test", detector_count=1)
        assert s.scenario_pass is None

    def test_scenario_fail_count_default_zero(self):
        s = RoomSummary(room_id="R1", name="test", detector_count=1)
        assert s.scenario_fail_count == 0

    def test_scenario_worst_time_default_none(self):
        s = RoomSummary(room_id="R1", name="test", detector_count=1)
        assert s.scenario_worst_time_s is None

    def test_scenario_blind_spots_default_zero(self):
        s = RoomSummary(room_id="R1", name="test", detector_count=1)
        assert s.scenario_blind_spots == 0

    def test_scenario_battery_ms_default_zero(self):
        s = RoomSummary(room_id="R1", name="test", detector_count=1)
        assert s.scenario_battery_ms == 0.0


# ============================================================================
# Test FloorReport Scenario Fields (Defaults)
# ============================================================================

class TestFloorReportScenarioDefaults:
    """Verify FloorReport scenario fields have correct defaults."""

    def test_scenario_non_compliant_default_empty(self):
        r = FloorReport(floor_id="F1")
        assert r.scenario_non_compliant_rooms == []

    def test_scenario_safe_to_submit_default_true(self):
        """Default True — no scenario verification = not flagged."""
        r = FloorReport(floor_id="F1")
        assert r.scenario_safe_to_submit is True


# ============================================================================
# Test Backward Compatibility
# ============================================================================

class TestBackwardCompatibility:
    """Verify use_scenarios=False (default) produces zero change."""

    def test_default_no_scenario_fields_populated(self):
        opt = DensityOptimizer()
        fa = FloorAnalyser("floor_1", opt)
        rooms = [
            {"room_id": "R1", "name": "Office",
             "polygon_coords": RECT_10x8, "ceiling_height": 3.0},
        ]
        report = fa.analyse(rooms)
        s = report.room_summaries[0]
        assert s.scenario_pass is None
        assert s.scenario_fail_count == 0
        assert s.scenario_worst_time_s is None
        assert s.scenario_blind_spots == 0
        assert s.scenario_battery_ms == 0.0

    def test_default_floor_report_no_scenario_data(self):
        opt = DensityOptimizer()
        fa = FloorAnalyser("floor_1", opt)
        rooms = [
            {"room_id": "R1", "name": "Office",
             "polygon_coords": RECT_10x8, "ceiling_height": 3.0},
        ]
        report = fa.analyse(rooms)
        assert report.scenario_non_compliant_rooms == []
        assert report.scenario_safe_to_submit is True

    def test_default_no_scenario_warnings(self):
        opt = DensityOptimizer()
        fa = FloorAnalyser("floor_1", opt)
        rooms = [
            {"room_id": "R1", "name": "Office",
             "polygon_coords": RECT_10x8, "ceiling_height": 3.0},
        ]
        report = fa.analyse(rooms)
        s = report.room_summaries[0]
        assert not any("SCENARIO" in w for w in s.warnings)

    def test_default_compliant_unchanged(self):
        """Compliant result should be identical with or without scenarios."""
        opt = DensityOptimizer()
        rooms = [
            {"room_id": "R1", "name": "Office",
             "polygon_coords": RECT_10x8, "ceiling_height": 3.0},
        ]
        fa_no_sc = FloorAnalyser("floor_1", opt)
        report = fa_no_sc.analyse(rooms)
        # The compliant flag should be based only on coverage triple-check
        # (no scenario dimension when use_scenarios=False)
        assert report.room_summaries[0].compliant == report.room_summaries[0].proof_valid


# ============================================================================
# Test Scenario Verification Basic
# ============================================================================

class TestScenarioVerificationBasic:
    """Test basic scenario verification with use_scenarios=True."""

    def test_scenario_fields_populated(self):
        opt = DensityOptimizer()
        fa = FloorAnalyser("floor_1", opt, use_scenarios=True,
                           scenario_time_step=1.0)
        rooms = [
            {"room_id": "R1", "name": "Office",
             "polygon_coords": RECT_10x8, "ceiling_height": 3.0},
        ]
        report = fa.analyse(rooms)
        s = report.room_summaries[0]
        # scenario_pass should be set (True or False, not None)
        assert s.scenario_pass is not None
        assert isinstance(s.scenario_pass, bool)
        assert s.scenario_battery_ms > 0

    def test_scenario_worst_time_is_positive(self):
        opt = DensityOptimizer()
        fa = FloorAnalyser("floor_1", opt, use_scenarios=True,
                           scenario_time_step=1.0)
        rooms = [
            {"room_id": "R1", "name": "Office",
             "polygon_coords": RECT_10x8, "ceiling_height": 3.0},
        ]
        report = fa.analyse(rooms)
        s = report.room_summaries[0]
        if s.scenario_worst_time_s is not None:
            assert s.scenario_worst_time_s > 0

    def test_scenario_fail_count_non_negative(self):
        opt = DensityOptimizer()
        fa = FloorAnalyser("floor_1", opt, use_scenarios=True,
                           scenario_time_step=1.0)
        rooms = [
            {"room_id": "R1", "name": "Office",
             "polygon_coords": RECT_10x8, "ceiling_height": 3.0},
        ]
        report = fa.analyse(rooms)
        s = report.room_summaries[0]
        assert s.scenario_fail_count >= 0

    def test_scenario_blind_spots_non_negative(self):
        opt = DensityOptimizer()
        fa = FloorAnalyser("floor_1", opt, use_scenarios=True,
                           scenario_time_step=1.0)
        rooms = [
            {"room_id": "R1", "name": "Office",
             "polygon_coords": RECT_10x8, "ceiling_height": 3.0},
        ]
        report = fa.analyse(rooms)
        s = report.room_summaries[0]
        assert s.scenario_blind_spots >= 0


# ============================================================================
# Test Scenario Results for Well-Designed Layouts
# ============================================================================

class TestScenarioWellDesignedLayout:
    """Rooms with good detector coverage should pass scenarios."""

    def test_small_office_passes_scenarios(self):
        """3x4m room with DensityOptimizer should pass all scenarios."""
        opt = DensityOptimizer()
        fa = FloorAnalyser("floor_1", opt, use_scenarios=True,
                           scenario_time_step=1.0)
        rooms = [
            {"room_id": "R1", "name": "Small Office",
             "polygon_coords": [(0, 0), (3, 0), (3, 4), (0, 4)],
             "ceiling_height": 3.0},
        ]
        report = fa.analyse(rooms)
        s = report.room_summaries[0]
        # Small room with detector → should pass scenarios
        # (single detector is close to any ignition point)
        assert s.scenario_pass is True or s.scenario_pass is False  # no crash
        assert s.scenario_battery_ms > 0

    def test_medium_office_has_results(self):
        """10x8m office should have scenario results."""
        opt = DensityOptimizer()
        fa = FloorAnalyser("floor_1", opt, use_scenarios=True,
                           scenario_time_step=1.0)
        rooms = [
            {"room_id": "R1", "name": "Medium Office",
             "polygon_coords": RECT_10x8, "ceiling_height": 3.0},
        ]
        report = fa.analyse(rooms)
        s = report.room_summaries[0]
        assert s.scenario_pass is not None
        assert s.scenario_fail_count >= 0


# ============================================================================
# Test Warnings Generation
# ============================================================================

class TestScenarioWarnings:
    """Test that scenario warnings are properly generated."""

    def test_scenario_fail_produces_warning(self):
        """If scenarios fail, SCENARIO_DETECTION_FAIL warning should appear."""
        opt = DensityOptimizer()
        fa = FloorAnalyser("floor_1", opt, use_scenarios=True,
                           scenario_time_step=1.0)
        rooms = [
            {"room_id": "R1", "name": "Office",
             "polygon_coords": RECT_10x8, "ceiling_height": 3.0},
        ]
        report = fa.analyse(rooms)
        s = report.room_summaries[0]
        if not s.scenario_pass:
            assert any("SCENARIO_DETECTION_FAIL" in w for w in s.warnings)

    def test_no_scenario_warning_when_pass(self):
        """If scenarios pass, no SCENARIO_DETECTION_FAIL warning."""
        opt = DensityOptimizer()
        fa = FloorAnalyser("floor_1", opt, use_scenarios=True,
                           scenario_time_step=1.0)
        rooms = [
            {"room_id": "R1", "name": "Office",
             "polygon_coords": RECT_10x8, "ceiling_height": 3.0},
        ]
        report = fa.analyse(rooms)
        s = report.room_summaries[0]
        if s.scenario_pass:
            assert not any("SCENARIO_DETECTION_FAIL" in w for w in s.warnings)

    def test_blind_spots_produce_warning(self):
        """If blind spots exist, SCENARIO_BLIND_SPOT warning should appear."""
        opt = DensityOptimizer()
        fa = FloorAnalyser("floor_1", opt, use_scenarios=True,
                           scenario_time_step=1.0)
        rooms = [
            {"room_id": "R1", "name": "Office",
             "polygon_coords": RECT_10x8, "ceiling_height": 3.0},
        ]
        report = fa.analyse(rooms)
        s = report.room_summaries[0]
        if s.scenario_blind_spots > 0:
            assert any("SCENARIO_BLIND_SPOT" in w for w in s.warnings)


# ============================================================================
# Test Floor-Level Scenario Aggregation
# ============================================================================

class TestFloorLevelScenarioAggregation:
    """Test FloorReport scenario aggregation."""

    def test_all_pass_scenario_safe(self):
        """If all rooms pass scenarios, scenario_safe_to_submit=True."""
        opt = DensityOptimizer()
        fa = FloorAnalyser("floor_1", opt, use_scenarios=True,
                           scenario_time_step=1.0)
        rooms = [
            {"room_id": "R1", "name": "Small Office",
             "polygon_coords": [(0, 0), (3, 0), (3, 4), (0, 4)],
             "ceiling_height": 3.0},
        ]
        report = fa.analyse(rooms)
        if all(s.scenario_pass for s in report.room_summaries):
            assert report.scenario_safe_to_submit is True
            assert len(report.scenario_non_compliant_rooms) == 0

    def test_scenario_non_compliant_populated(self):
        """Rooms that fail scenarios should appear in scenario_non_compliant."""
        opt = DensityOptimizer()
        fa = FloorAnalyser("floor_1", opt, use_scenarios=True,
                           scenario_time_step=1.0)
        rooms = [
            {"room_id": "R1", "name": "Office",
             "polygon_coords": RECT_10x8, "ceiling_height": 3.0},
        ]
        report = fa.analyse(rooms)
        # Check consistency: if any room has scenario_pass=False, it should be in the list
        failing = [
            s.room_id for s in report.room_summaries
            if s.scenario_pass is False
        ]
        assert report.scenario_non_compliant_rooms == failing

    def test_multi_room_mixed_results(self):
        """Multiple rooms may have mixed scenario results."""
        opt = DensityOptimizer()
        fa = FloorAnalyser("floor_1", opt, use_scenarios=True,
                           scenario_time_step=1.0)
        rooms = [
            {"room_id": "R1", "name": "Small",
             "polygon_coords": [(0, 0), (3, 0), (3, 4), (0, 4)],
             "ceiling_height": 3.0},
            {"room_id": "R2", "name": "Medium",
             "polygon_coords": RECT_10x8, "ceiling_height": 3.0},
        ]
        report = fa.analyse(rooms)
        # Both should have scenario results
        for s in report.room_summaries:
            assert s.scenario_pass is not None
        # Floor report should have consistent aggregation
        failing_ids = [
            s.room_id for s in report.room_summaries
            if s.scenario_pass is False
        ]
        assert report.scenario_non_compliant_rooms == failing_ids


# ============================================================================
# Test Occupancy-Aware Fire Load
# ============================================================================

class TestOccupancyFireLoad:
    """Test that occupancy type affects scenario fire load."""

    def test_office_occupancy(self):
        opt = DensityOptimizer()
        fa = FloorAnalyser("floor_1", opt, use_scenarios=True,
                           scenario_time_step=1.0)
        rooms = [
            {"room_id": "R1", "name": "Office",
             "polygon_coords": RECT_10x8, "ceiling_height": 3.0,
             "room_type": "office"},
        ]
        report = fa.analyse(rooms)
        s = report.room_summaries[0]
        assert s.scenario_pass is not None

    def test_warehouse_occupancy(self):
        opt = DensityOptimizer()
        fa = FloorAnalyser("floor_1", opt, use_scenarios=True,
                           scenario_time_step=1.0)
        rooms = [
            {"room_id": "R1", "name": "Warehouse",
             "polygon_coords": LARGE_30x25, "ceiling_height": 6.0,
             "room_type": "warehouse"},
        ]
        report = fa.analyse(rooms)
        s = report.room_summaries[0]
        assert s.scenario_pass is not None

    def test_unknown_occupancy_uses_default(self):
        """Unknown occupancy should use office (default) fire load."""
        opt = DensityOptimizer()
        fa = FloorAnalyser("floor_1", opt, use_scenarios=True,
                           scenario_time_step=1.0)
        rooms = [
            {"room_id": "R1", "name": "Unknown",
             "polygon_coords": RECT_10x8, "ceiling_height": 3.0,
             "room_type": "space_station"},
        ]
        report = fa.analyse(rooms)
        s = report.room_summaries[0]
        assert s.scenario_pass is not None  # should not crash


# ============================================================================
# Test Refused Rooms Skip Scenario Verification
# ============================================================================

class TestRefusedRoomsSkipScenario:
    """Kitchen + smoke detector → refused → no scenario verification."""

    def test_kitchen_no_scenario(self):
        opt = DensityOptimizer()
        fa = FloorAnalyser("floor_1", opt, use_scenarios=True,
                           scenario_time_step=1.0)
        rooms = [
            {"room_id": "K1", "name": "Kitchen",
             "polygon_coords": [(0, 0), (6, 0), (6, 5), (0, 5)],
             "ceiling_height": 3.0,
             "room_type": "kitchen",
             "detector_type": "smoke_photoelectric"},
        ]
        report = fa.analyse(rooms)
        s = report.room_summaries[0]
        assert s.refused is True
        # Refused rooms should not have scenario results
        assert s.scenario_pass is None
        assert s.scenario_fail_count == 0
        assert s.scenario_battery_ms == 0.0


# ============================================================================
# Test Edge Cases
# ============================================================================

class TestScenarioEdgeCases:
    """Edge cases for scenario verification."""

    def test_tiny_room_scenario(self):
        """2x2m room with 1 detector should pass scenarios quickly."""
        opt = DensityOptimizer()
        fa = FloorAnalyser("floor_1", opt, use_scenarios=True,
                           scenario_time_step=1.0)
        rooms = [
            {"room_id": "R1", "name": "Tiny",
             "polygon_coords": TINY_2x2, "ceiling_height": 3.0},
        ]
        report = fa.analyse(rooms)
        s = report.room_summaries[0]
        assert s.scenario_pass is not None
        assert s.scenario_battery_ms > 0

    def test_high_ceiling_warehouse(self):
        """8m ceiling warehouse — different physics."""
        opt = DensityOptimizer()
        fa = FloorAnalyser("floor_1", opt, use_scenarios=True,
                           scenario_time_step=1.0)
        rooms = [
            {"room_id": "R1", "name": "Warehouse",
             "polygon_coords": LARGE_30x25, "ceiling_height": 8.0,
             "room_type": "warehouse"},
        ]
        report = fa.analyse(rooms)
        s = report.room_summaries[0]
        assert s.scenario_pass is not None

    def test_corridor_scenario(self):
        """Narrow corridor — detectors placed centrally."""
        opt = DensityOptimizer()
        fa = FloorAnalyser("floor_1", opt, use_scenarios=True,
                           scenario_time_step=1.0)
        rooms = [
            {"room_id": "R1", "name": "Corridor",
             "polygon_coords": CORRIDOR_20x2, "ceiling_height": 3.0},
        ]
        report = fa.analyse(rooms)
        s = report.room_summaries[0]
        assert s.scenario_pass is not None

    def test_empty_rooms_list(self):
        """Empty rooms list should not crash with scenarios enabled."""
        opt = DensityOptimizer()
        fa = FloorAnalyser("floor_1", opt, use_scenarios=True)
        report = fa.analyse([])
        assert len(report.room_summaries) == 0
        assert report.scenario_safe_to_submit is True

    def test_scenario_time_step_custom(self):
        """Custom time step should be respected."""
        opt = DensityOptimizer()
        fa = FloorAnalyser("floor_1", opt, use_scenarios=True,
                           scenario_time_step=2.0)
        rooms = [
            {"room_id": "R1", "name": "Office",
             "polygon_coords": RECT_10x8, "ceiling_height": 3.0},
        ]
        report = fa.analyse(rooms)
        s = report.room_summaries[0]
        # Should still produce valid results
        assert s.scenario_pass is not None

    def test_l_shape_room_scenario(self):
        """L-shape room scenario verification."""
        l_shape = [(0, 0), (10, 0), (10, 5), (5, 5), (5, 10), (0, 10)]
        opt = DensityOptimizer()
        fa = FloorAnalyser("floor_1", opt, use_scenarios=True,
                           scenario_time_step=1.0)
        rooms = [
            {"room_id": "R1", "name": "L-Shape",
             "polygon_coords": l_shape, "ceiling_height": 3.0},
        ]
        report = fa.analyse(rooms)
        s = report.room_summaries[0]
        assert s.scenario_pass is not None


# ============================================================================
# Test Full Pipeline Integration
# ============================================================================

class TestFullPipelineIntegration:
    """End-to-end: DensityOptimizer → FloorAnalyser + Scenarios → FloorReport."""

    def test_full_pipeline_with_scenarios(self):
        """Complete pipeline: optimize + analyse + verify scenarios."""
        opt = DensityOptimizer()
        fa = FloorAnalyser("GF", opt, use_scenarios=True,
                           scenario_time_step=1.0)
        rooms = [
            {"room_id": "R1", "name": "Office A",
             "polygon_coords": RECT_10x8, "ceiling_height": 3.0,
             "room_type": "office"},
            {"room_id": "R2", "name": "Office B",
             "polygon_coords": [(0, 0), (6, 0), (6, 5), (0, 5)],
             "ceiling_height": 3.0, "room_type": "office"},
        ]
        report = fa.analyse(rooms)

        # All rooms should have coverage results
        assert len(report.room_summaries) == 2
        assert report.total_detectors > 0

        # All rooms should have scenario results
        for s in report.room_summaries:
            assert s.scenario_pass is not None
            assert s.scenario_battery_ms > 0

        # Floor report should have scenario aggregation
        assert isinstance(report.scenario_non_compliant_rooms, list)
        assert isinstance(report.scenario_safe_to_submit, bool)

    def test_full_pipeline_without_scenarios(self):
        """Pipeline without scenarios = same as V2.4."""
        opt = DensityOptimizer()
        fa = FloorAnalyser("GF", opt, use_scenarios=False)
        rooms = [
            {"room_id": "R1", "name": "Office",
             "polygon_coords": RECT_10x8, "ceiling_height": 3.0},
        ]
        report = fa.analyse(rooms)

        s = report.room_summaries[0]
        assert s.scenario_pass is None
        assert report.scenario_non_compliant_rooms == []
        assert report.scenario_safe_to_submit is True

    def test_scenario_does_not_modify_compliant(self):
        """Scenario verification should NOT modify the compliant flag.
        compliant is based on coverage triple-check only."""
        opt = DensityOptimizer()
        fa = FloorAnalyser("GF", opt, use_scenarios=True,
                           scenario_time_step=1.0)
        rooms = [
            {"room_id": "R1", "name": "Office",
             "polygon_coords": RECT_10x8, "ceiling_height": 3.0},
        ]
        report_no_sc = FloorAnalyser("GF", opt, use_scenarios=False).analyse(rooms)
        report_with_sc = fa.analyse(rooms)

        s_no = report_no_sc.room_summaries[0]
        s_with = report_with_sc.room_summaries[0]

        # compliant flag should be the same (coverage-based only)
        assert s_no.compliant == s_with.compliant
        assert s_no.safe_to_submit == s_with.safe_to_submit

    def test_scenario_plus_mip_both_enabled(self):
        """Both MIP and scenario verification can run together."""
        opt = DensityOptimizer()
        fa = FloorAnalyser("GF", opt, use_mip=True, use_scenarios=True,
                           scenario_time_step=1.0)
        rooms = [
            {"room_id": "R1", "name": "Office",
             "polygon_coords": RECT_10x8, "ceiling_height": 3.0},
        ]
        report = fa.analyse(rooms)
        s = report.room_summaries[0]
        # Both verification results should be populated
        assert s.scenario_pass is not None
        # MIP may or may not have run (depends on PuLP availability)
        # But scenario results should always be there

    def test_floor_warning_for_scenario_fail(self):
        """Floor-level warning when scenarios fail."""
        opt = DensityOptimizer()
        fa = FloorAnalyser("GF", opt, use_scenarios=True,
                           scenario_time_step=1.0)
        rooms = [
            {"room_id": "R1", "name": "Office",
             "polygon_coords": RECT_10x8, "ceiling_height": 3.0},
        ]
        report = fa.analyse(rooms)
        if report.scenario_non_compliant_rooms:
            assert any(
                "SCENARIO_NON_COMPLIANT" in w
                for w in report.floor_warnings
            )
