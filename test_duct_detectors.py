"""
test_duct_detectors.py — Duct Detector Placement Tests
========================================================
Tests for fireai.core.duct_detector and FloorAnalyser duct integration.

Covers:
  - Duct exemption logic (narrow, short, exhaust)
  - Detector count and spacing
  - Detector positions (bounds, indices, centreline)
  - CFM threshold warning
  - Length consistency warning
  - FloorAnalyser integration (duct_devices populated)
  - Multi-duct aggregation
  - Edge cases

Total: 35+ tests across 10 test classes.
"""

import math
import pytest

from fireai.core.duct_detector import (
    DuctSpec,
    DuctAnalysisResult,
    DuctDetectorPosition,
    analyse_duct,
    analyse_ducts,
    total_duct_detectors,
    NFPA_DUCT_MAX_SPACING_M,
    NFPA_DUCT_MIN_WIDTH_M,
    NFPA_DUCT_MIN_LENGTH_M,
    NFPA_DUCT_CFM_THRESHOLD,
    NFPA_DUCT_SPACING_REF,
)

from fireai.core.floor_analyser import FloorAnalyser, RoomSummary, FloorReport
from fireai.core.spatial_engine.density_optimizer import DensityOptimizer


# ============================================================================
# Test Duct Exemptions
# ============================================================================

class TestDuctExemptions:

    def test_narrow_duct_is_exempt(self):
        duct = DuctSpec("D-NARROW", length_m=5.0, width_m=0.10,
                        start_point=(0, 0), end_point=(5, 0))
        r = analyse_duct(duct)
        assert r.exempt is True
        assert r.detector_count == 0
        assert "exempt" in r.exemption_reason.lower()

    def test_short_duct_is_exempt(self):
        duct = DuctSpec("D-SHORT", length_m=0.5, width_m=0.5,
                        start_point=(0, 0), end_point=(0.5, 0))
        r = analyse_duct(duct)
        assert r.exempt is True
        assert r.detector_count == 0

    def test_minimum_width_boundary_not_exempt(self):
        """Duct exactly at minimum width should NOT be exempt."""
        duct = DuctSpec("D-BOUNDARY", length_m=2.0,
                        width_m=NFPA_DUCT_MIN_WIDTH_M,
                        start_point=(0, 0), end_point=(2, 0))
        r = analyse_duct(duct)
        assert r.exempt is False
        assert r.detector_count >= 1

    def test_exhaust_duct_is_exempt(self):
        """Exhaust ducts don't require detectors per §17.7.5.1."""
        duct = DuctSpec("D-EXHAUST", length_m=5.0, width_m=0.5,
                        start_point=(0, 0), end_point=(5, 0),
                        duct_type="exhaust")
        r = analyse_duct(duct)
        assert r.exempt is True
        assert "exhaust" in r.exemption_reason.lower()

    def test_return_duct_not_exempt(self):
        """Return ducts DO require detectors."""
        duct = DuctSpec("D-RETURN", length_m=5.0, width_m=0.5,
                        start_point=(0, 0), end_point=(5, 0),
                        duct_type="return")
        r = analyse_duct(duct)
        assert r.exempt is False


# ============================================================================
# Test Duct Detector Count
# ============================================================================

class TestDuctDetectorCount:

    def test_short_duct_one_detector(self):
        duct = DuctSpec("D-01", length_m=2.0, width_m=0.6,
                        start_point=(0, 0), end_point=(2, 0))
        r = analyse_duct(duct)
        assert r.detector_count == 1

    def test_exact_spacing_boundary(self):
        """Duct exactly 3.05m → 1 detector."""
        duct = DuctSpec("D-02", length_m=NFPA_DUCT_MAX_SPACING_M,
                        width_m=0.6,
                        start_point=(0, 0),
                        end_point=(NFPA_DUCT_MAX_SPACING_M, 0))
        r = analyse_duct(duct)
        assert r.detector_count == 1

    def test_just_over_spacing_two_detectors(self):
        """Duct 3.06m → 2 detectors."""
        duct = DuctSpec("D-03", length_m=3.06, width_m=0.6,
                        start_point=(0, 0), end_point=(3.06, 0))
        r = analyse_duct(duct)
        assert r.detector_count == 2

    def test_long_duct_correct_count(self):
        """Duct 9.15m → 3 detectors."""
        length = NFPA_DUCT_MAX_SPACING_M * 3
        duct = DuctSpec("D-04", length_m=length, width_m=0.6,
                        start_point=(0, 0), end_point=(length, 0))
        r = analyse_duct(duct)
        assert r.detector_count == 3

    def test_very_long_duct(self):
        """15m duct → 5 detectors."""
        duct = DuctSpec("D-LONG", length_m=15.0, width_m=0.6,
                        start_point=(0, 0), end_point=(15, 0))
        r = analyse_duct(duct)
        assert r.detector_count == 5

    def test_core_regression_duct_devices_gt_zero(self):
        """A room with a duct must yield duct_devices > 0."""
        ducts = [
            DuctSpec("MAIN-SUPPLY", length_m=4.0, width_m=0.5,
                     start_point=(1.0, 2.0), end_point=(5.0, 2.0),
                     airflow_cfm=3000)
        ]
        results = analyse_ducts(ducts)
        total = total_duct_detectors(results)
        assert total > 0


# ============================================================================
# Test Duct Positions
# ============================================================================

class TestDuctPositions:

    def test_positions_inside_duct_bounds(self):
        duct = DuctSpec("D-POS", length_m=6.0, width_m=0.5,
                        start_point=(0, 0), end_point=(6, 0))
        r = analyse_duct(duct)
        for pos in r.detectors:
            assert 0.0 <= pos.x <= 6.0
            assert pos.distance_from_start_m <= duct.length_m

    def test_detector_indices_sequential(self):
        duct = DuctSpec("D-IDX", length_m=7.0, width_m=0.5,
                        start_point=(0, 0), end_point=(7, 0))
        r = analyse_duct(duct)
        for i, pos in enumerate(r.detectors, start=1):
            assert pos.index == i

    def test_diagonal_duct_positions_on_centreline(self):
        """Detectors must lie on the duct centreline for diagonal ducts."""
        duct = DuctSpec("D-DIAG", length_m=math.hypot(3, 4), width_m=0.5,
                        start_point=(0, 0), end_point=(3, 4))
        r = analyse_duct(duct)
        assert r.detector_count >= 1
        for pos in r.detectors:
            if pos.x > 1e-6:
                assert abs(pos.y / pos.x - 4 / 3) < 0.01

    def test_nfpa_ref_on_positions(self):
        duct = DuctSpec("D-REF", length_m=3.0, width_m=0.5,
                        start_point=(0, 0), end_point=(3, 0))
        r = analyse_duct(duct)
        for pos in r.detectors:
            assert "NFPA 72" in pos.nfpa_ref
            assert "NFPA 90A" in pos.spacing_ref

    def test_spacing_ref_cites_nfpa_90a(self):
        """spacing_ref must cite NFPA 90A (the actual spacing source)."""
        duct = DuctSpec("D-SPR", length_m=5.0, width_m=0.5,
                        start_point=(0, 0), end_point=(5, 0))
        r = analyse_duct(duct)
        for pos in r.detectors:
            assert "NFPA 90A" in pos.spacing_ref
            assert "6.4.2.2" in pos.spacing_ref


# ============================================================================
# Test Duct Spacing
# ============================================================================

class TestDuctSpacing:

    def test_spacing_never_exceeds_nfpa_max(self):
        for length in [1.5, 3.05, 3.06, 6.1, 9.15, 12.2, 15.0]:
            duct = DuctSpec(f"D-{length}", length_m=length, width_m=0.5,
                            start_point=(0, 0), end_point=(length, 0))
            r = analyse_duct(duct)
            if not r.exempt:
                assert r.spacing_used_m <= NFPA_DUCT_MAX_SPACING_M + 1e-9, (
                    f"length={length}: spacing {r.spacing_used_m} > NFPA max"
                )

    def test_nfpa_ref_present_in_result(self):
        duct = DuctSpec("D-REF", length_m=3.0, width_m=0.5,
                        start_point=(0, 0), end_point=(3, 0))
        r = analyse_duct(duct)
        assert "NFPA 72" in r.nfpa_ref
        assert "NFPA 90A" in r.spacing_ref

    def test_result_spacing_ref_cites_90a(self):
        """Result spacing_ref must cite NFPA 90A §6.4.2.2."""
        duct = DuctSpec("D-SPR", length_m=5.0, width_m=0.5,
                        start_point=(0, 0), end_point=(5, 0))
        r = analyse_duct(duct)
        assert "NFPA 90A" in r.spacing_ref
        assert "6.4.2.2" in r.spacing_ref


# ============================================================================
# Test CFM Threshold Warning
# ============================================================================

class TestCFMThreshold:

    def test_low_airflow_generates_warning(self):
        duct = DuctSpec("D-LOW", length_m=3.0, width_m=0.5,
                        start_point=(0, 0), end_point=(3, 0),
                        airflow_cfm=1500)
        r = analyse_duct(duct)
        assert any("2000" in w for w in r.warnings)

    def test_high_airflow_no_warning(self):
        duct = DuctSpec("D-HIGH", length_m=3.0, width_m=0.5,
                        start_point=(0, 0), end_point=(3, 0),
                        airflow_cfm=5000)
        r = analyse_duct(duct)
        assert not r.warnings

    def test_unknown_airflow_no_warning(self):
        """airflow_cfm=None = unknown — no warning (conservative)."""
        duct = DuctSpec("D-UNKN", length_m=3.0, width_m=0.5,
                        start_point=(0, 0), end_point=(3, 0),
                        airflow_cfm=None)
        r = analyse_duct(duct)
        # Should NOT warn about CFM when unknown
        assert not any("CFM" in w for w in r.warnings)

    def test_exact_cfm_threshold_no_warning(self):
        """airflow = exactly 2000 CFM → warning (≤ threshold)."""
        duct = DuctSpec("D-EXACT", length_m=3.0, width_m=0.5,
                        start_point=(0, 0), end_point=(3, 0),
                        airflow_cfm=2000)
        r = analyse_duct(duct)
        assert any("2000" in w for w in r.warnings)


# ============================================================================
# Test Length Consistency Warning
# ============================================================================

class TestLengthConsistency:

    def test_mismatched_length_warns(self):
        """length_m=5 but geometric distance=10 → warning."""
        duct = DuctSpec("D-MISMATCH", length_m=5.0, width_m=0.5,
                        start_point=(0, 0), end_point=(10, 0))
        r = analyse_duct(duct)
        assert any("differs" in w.lower() for w in r.warnings)

    def test_matching_length_no_warning(self):
        """length_m matches geometric distance → no length warning."""
        duct = DuctSpec("D-MATCH", length_m=6.0, width_m=0.5,
                        start_point=(0, 0), end_point=(6, 0))
        r = analyse_duct(duct)
        assert not any("differs" in w.lower() for w in r.warnings)


# ============================================================================
# Test Multi-Duct Aggregation
# ============================================================================

class TestMultiDuctAggregation:

    def test_total_duct_detectors_across_ducts(self):
        ducts = [
            DuctSpec("D-A", length_m=2.0, width_m=0.5,
                     start_point=(0, 0), end_point=(2, 0)),
            DuctSpec("D-B", length_m=4.0, width_m=0.5,
                     start_point=(0, 2), end_point=(4, 2)),
            DuctSpec("D-C", length_m=0.1, width_m=0.1,
                     start_point=(0, 4), end_point=(0.1, 4)),
        ]
        results = analyse_ducts(ducts)
        total = total_duct_detectors(results)
        # D-A → 1, D-B → 2, D-C → exempt (0)
        assert total == 3

    def test_all_exempt_ducts_total_zero(self):
        ducts = [
            DuctSpec("D-EX1", length_m=0.5, width_m=0.1,
                     start_point=(0, 0), end_point=(0.5, 0)),
            DuctSpec("D-EX2", length_m=0.3, width_m=0.1,
                     start_point=(1, 0), end_point=(1.3, 0)),
        ]
        results = analyse_ducts(ducts)
        assert total_duct_detectors(results) == 0

    def test_analyse_ducts_returns_one_per_duct(self):
        ducts = [
            DuctSpec("D-1", length_m=3.0, width_m=0.5,
                     start_point=(0, 0), end_point=(3, 0)),
            DuctSpec("D-2", length_m=6.0, width_m=0.5,
                     start_point=(0, 5), end_point=(6, 5)),
        ]
        results = analyse_ducts(ducts)
        assert len(results) == 2


# ============================================================================
# Test FloorAnalyser Integration
# ============================================================================

class TestFloorAnalyserDuctIntegration:

    def test_room_without_ducts_duct_devices_zero(self):
        """No ducts in room_dict → duct_devices stays 0."""
        opt = DensityOptimizer()
        fa = FloorAnalyser("floor_1", opt)
        rooms = [
            {"room_id": "R1", "name": "Office",
             "polygon_coords": [(0, 0), (10, 0), (10, 8), (0, 8)],
             "ceiling_height": 3.0},
        ]
        report = fa.analyse(rooms)
        s = report.room_summaries[0]
        assert s.duct_devices == 0
        assert s.duct_results == []
        assert s.duct_warnings == []

    def test_room_with_duct_duct_devices_populated(self):
        """Room with duct → duct_devices > 0."""
        opt = DensityOptimizer()
        fa = FloorAnalyser("floor_1", opt)
        rooms = [
            {"room_id": "R1", "name": "Office",
             "polygon_coords": [(0, 0), (10, 0), (10, 8), (0, 8)],
             "ceiling_height": 3.0,
             "ducts": [
                 {"duct_id": "SUP-1", "length_m": 4.0, "width_m": 0.5,
                  "start_point": (1.0, 2.0), "end_point": (5.0, 2.0),
                  "airflow_cfm": 3000},
             ]},
        ]
        report = fa.analyse(rooms)
        s = report.room_summaries[0]
        assert s.duct_devices > 0
        assert len(s.duct_results) == 1
        assert s.duct_results[0].duct_id == "SUP-1"

    def test_room_with_exempt_duct_duct_devices_zero(self):
        """Room with exempt duct → duct_devices == 0."""
        opt = DensityOptimizer()
        fa = FloorAnalyser("floor_1", opt)
        rooms = [
            {"room_id": "R1", "name": "Office",
             "polygon_coords": [(0, 0), (10, 0), (10, 8), (0, 8)],
             "ceiling_height": 3.0,
             "ducts": [
                 {"duct_id": "TINY", "length_m": 0.5, "width_m": 0.1,
                  "start_point": (0, 0), "end_point": (0.5, 0)},
             ]},
        ]
        report = fa.analyse(rooms)
        s = report.room_summaries[0]
        assert s.duct_devices == 0
        assert s.duct_results[0].exempt is True

    def test_room_with_ductspec_object(self):
        """DuctSpec objects (not dicts) should also work."""
        opt = DensityOptimizer()
        fa = FloorAnalyser("floor_1", opt)
        rooms = [
            {"room_id": "R1", "name": "Office",
             "polygon_coords": [(0, 0), (10, 0), (10, 8), (0, 8)],
             "ceiling_height": 3.0,
             "ducts": [
                 DuctSpec("OBJ-1", length_m=5.0, width_m=0.5,
                          start_point=(1, 1), end_point=(6, 1)),
             ]},
        ]
        report = fa.analyse(rooms)
        s = report.room_summaries[0]
        assert s.duct_devices > 0

    def test_floor_report_total_duct_devices(self):
        """FloorReport should aggregate duct devices across rooms."""
        opt = DensityOptimizer()
        fa = FloorAnalyser("floor_1", opt)
        rooms = [
            {"room_id": "R1", "name": "Office A",
             "polygon_coords": [(0, 0), (10, 0), (10, 8), (0, 8)],
             "ceiling_height": 3.0,
             "ducts": [
                 {"duct_id": "SUP-1", "length_m": 4.0, "width_m": 0.5,
                  "start_point": (1, 2), "end_point": (5, 2)},
             ]},
            {"room_id": "R2", "name": "Office B",
             "polygon_coords": [(0, 0), (6, 0), (6, 5), (0, 5)],
             "ceiling_height": 3.0},
        ]
        report = fa.analyse(rooms)
        # Only R1 has ducts
        assert report.total_duct_devices > 0

    def test_duct_devices_does_not_affect_compliant(self):
        """duct_devices should not affect the compliant flag."""
        opt = DensityOptimizer()
        fa_no_duct = FloorAnalyser("floor_1", opt)
        fa_with_duct = FloorAnalyser("floor_2", opt)
        rooms_no = [
            {"room_id": "R1", "name": "Office",
             "polygon_coords": [(0, 0), (10, 0), (10, 8), (0, 8)],
             "ceiling_height": 3.0},
        ]
        rooms_with = [
            {"room_id": "R1", "name": "Office",
             "polygon_coords": [(0, 0), (10, 0), (10, 8), (0, 8)],
             "ceiling_height": 3.0,
             "ducts": [
                 {"duct_id": "SUP-1", "length_m": 4.0, "width_m": 0.5,
                  "start_point": (1, 2), "end_point": (5, 2)},
             ]},
        ]
        r_no = fa_no_duct.analyse(rooms_no)
        r_with = fa_with_duct.analyse(rooms_with)
        assert r_no.room_summaries[0].compliant == r_with.room_summaries[0].compliant

    def test_refused_room_no_duct_analysis(self):
        """Kitchen + smoke detector → refused → no duct analysis."""
        opt = DensityOptimizer()
        fa = FloorAnalyser("floor_1", opt)
        rooms = [
            {"room_id": "K1", "name": "Kitchen",
             "polygon_coords": [(0, 0), (6, 0), (6, 5), (0, 5)],
             "ceiling_height": 3.0,
             "room_type": "kitchen",
             "detector_type": "smoke_photoelectric",
             "ducts": [
                 {"duct_id": "SUP-K", "length_m": 4.0, "width_m": 0.5,
                  "start_point": (1, 2), "end_point": (5, 2)},
             ]},
        ]
        report = fa.analyse(rooms)
        s = report.room_summaries[0]
        assert s.refused is True
        assert s.duct_devices == 0  # refused rooms skip duct analysis


# ============================================================================
# Test Edge Cases
# ============================================================================

class TestDuctEdgeCases:

    def test_zero_length_duct(self):
        """Zero-length duct should be exempt."""
        duct = DuctSpec("D-ZERO", length_m=0.0, width_m=0.5,
                        start_point=(0, 0), end_point=(0, 0))
        r = analyse_duct(duct)
        assert r.exempt is True

    def test_zero_width_duct(self):
        """Zero-width duct should be exempt."""
        duct = DuctSpec("D-ZEROW", length_m=5.0, width_m=0.0,
                        start_point=(0, 0), end_point=(5, 0))
        r = analyse_duct(duct)
        assert r.exempt is True

    def test_very_short_duct_one_detector(self):
        """Duct just over minimum length → 1 detector."""
        duct = DuctSpec("D-1.01", length_m=1.01, width_m=0.5,
                        start_point=(0, 0), end_point=(1.01, 0))
        r = analyse_duct(duct)
        assert not r.exempt
        assert r.detector_count == 1

    def test_ductspec_frozen(self):
        """DuctSpec should be immutable."""
        duct = DuctSpec("D-IMM", length_m=5.0, width_m=0.5)
        with pytest.raises(AttributeError):
            duct.duct_id = "modified"

    def test_multiple_ducts_with_mixed_types(self):
        """Supply + return + exhaust ducts."""
        ducts = [
            DuctSpec("SUP-1", length_m=5.0, width_m=0.5,
                     start_point=(0, 0), end_point=(5, 0),
                     duct_type="supply"),
            DuctSpec("RET-1", length_m=5.0, width_m=0.5,
                     start_point=(0, 3), end_point=(5, 3),
                     duct_type="return"),
            DuctSpec("EXH-1", length_m=5.0, width_m=0.5,
                     start_point=(0, 6), end_point=(5, 6),
                     duct_type="exhaust"),
        ]
        results = analyse_ducts(ducts)
        # Supply + return should have detectors, exhaust exempt
        supply_result = next(r for r in results if r.duct_id == "SUP-1")
        return_result = next(r for r in results if r.duct_id == "RET-1")
        exhaust_result = next(r for r in results if r.duct_id == "EXH-1")
        assert not supply_result.exempt
        assert not return_result.exempt
        assert exhaust_result.exempt


# ============================================================================
# Test Duct Key Compatibility (hvac_ducts / hvac_duct_list)
# ============================================================================

class TestDuctKeyCompatibility:
    """Test that _inject_duct_analysis supports multiple key names."""

    def test_hvac_ducts_key_works(self):
        """room_dict with 'hvac_ducts' key should populate duct_devices."""
        opt = DensityOptimizer()
        fa = FloorAnalyser("floor_1", opt)
        rooms = [
            {"room_id": "R1", "name": "Office",
             "polygon_coords": [(0, 0), (10, 0), (10, 8), (0, 8)],
             "ceiling_height": 3.0,
             "hvac_ducts": [
                 {"duct_id": "SUP-1", "length_m": 4.0, "width_m": 0.5,
                  "start_point": (1.0, 2.0), "end_point": (5.0, 2.0),
                  "airflow_cfm": 3000},
             ]},
        ]
        report = fa.analyse(rooms)
        s = report.room_summaries[0]
        assert s.duct_devices > 0
        assert len(s.duct_results) == 1
        assert s.duct_results[0].duct_id == "SUP-1"

    def test_hvac_duct_list_key_works(self):
        """room_dict with 'hvac_duct_list' key should populate duct_devices."""
        opt = DensityOptimizer()
        fa = FloorAnalyser("floor_1", opt)
        rooms = [
            {"room_id": "R1", "name": "Office",
             "polygon_coords": [(0, 0), (10, 0), (10, 8), (0, 8)],
             "ceiling_height": 3.0,
             "hvac_duct_list": [
                 {"duct_id": "SUP-1", "length_m": 4.0, "width_m": 0.5,
                  "start_point": (1.0, 2.0), "end_point": (5.0, 2.0),
                  "airflow_cfm": 3000},
             ]},
        ]
        report = fa.analyse(rooms)
        s = report.room_summaries[0]
        assert s.duct_devices > 0
        assert len(s.duct_results) == 1

    def test_ducts_key_takes_priority(self):
        """'ducts' key should take priority when multiple keys present."""
        opt = DensityOptimizer()
        fa = FloorAnalyser("floor_1", opt)
        rooms = [
            {"room_id": "R1", "name": "Office",
             "polygon_coords": [(0, 0), (10, 0), (10, 8), (0, 8)],
             "ceiling_height": 3.0,
             "ducts": [
                 {"duct_id": "PRIORITY", "length_m": 4.0, "width_m": 0.5,
                  "start_point": (1.0, 2.0), "end_point": (5.0, 2.0)},
             ],
             "hvac_ducts": [
                 {"duct_id": "FALLBACK", "length_m": 6.0, "width_m": 0.5,
                  "start_point": (1.0, 2.0), "end_point": (7.0, 2.0)},
             ]},
        ]
        report = fa.analyse(rooms)
        s = report.room_summaries[0]
        assert s.duct_results[0].duct_id == "PRIORITY"

    def test_empty_ducts_falls_through_to_hvac_ducts(self):
        """If 'ducts' is empty list, should try 'hvac_ducts'."""
        opt = DensityOptimizer()
        fa = FloorAnalyser("floor_1", opt)
        rooms = [
            {"room_id": "R1", "name": "Office",
             "polygon_coords": [(0, 0), (10, 0), (10, 8), (0, 8)],
             "ceiling_height": 3.0,
             "ducts": [],
             "hvac_ducts": [
                 {"duct_id": "FROM-HVAC", "length_m": 4.0, "width_m": 0.5,
                  "start_point": (1.0, 2.0), "end_point": (5.0, 2.0)},
             ]},
        ]
        report = fa.analyse(rooms)
        s = report.room_summaries[0]
        assert s.duct_devices > 0
        assert s.duct_results[0].duct_id == "FROM-HVAC"
