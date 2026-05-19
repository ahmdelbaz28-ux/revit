"""
test_phase12.py — FireAI Phase 12 Test Suite
==============================================
Tests for polygon optimizer and FloorAnalyser polygon verifier integration.

Phase 12 adds:
  1. PolygonDensityOptimizer — standalone polygon placement tool
     (rectangular -> DensityOptimizer, non-rectangular -> Greedy Set Cover + NFPA audit)
  2. FloorAnalyser polygon verifier — optional, same pattern as MIP
     (VERIFICATION ONLY — never replaces placement)

Design principles:
  - Greedy Set Cover is a VERIFIER, not a replacement for DensityOptimizer
  - All existing safety gates (triple-check, safety refusal, AuditStore) are preserved
  - Backward compatible: use_polygon_verifier=False (default) = zero change
"""

import pytest
import sys
import os
import math

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "."))

from fireai.core.spatial_engine.density_optimizer import DensityOptimizer, Room, DETECTOR_RADIUS
from fireai.core.floor_analyser import FloorAnalyser, FloorReport, RoomSummary
from fireai.core.building_engine import BuildingEngine, BuildingReport
from fireai.core.polygon_optimizer import (
    PolygonDensityOptimizer, PolygonRoom, PolygonRoomSummary,
    _generate_interior_grid, _greedy_set_cover, _coverage_percentage,
    _count_wall_violations, _audit_nfpa_spacing,
)
from fireai.core.geometry_utils import is_rectangular, polygon_area, point_in_polygon


# ─── Fixtures ───────────────────────────────────────────────

@pytest.fixture
def optimizer():
    """V7.3 DensityOptimizer with default R=6.40m."""
    return DensityOptimizer()


@pytest.fixture
def poly_optimizer():
    """PolygonDensityOptimizer instance."""
    return PolygonDensityOptimizer()


# L-shape polygon: 20x15 room with 8x6 cutout at NE corner
L_SHAPE_POLYGON = [
    (0, 0), (20, 0), (20, 9), (12, 9), (12, 15), (0, 15)
]

# Rectangular polygon: 12x8 room
RECT_POLYGON = [
    (0, 0), (12, 0), (12, 8), (0, 8)
]


# ═══════════════════════════════════════════════════════════════
# Test 1: PolygonRoom model
# ═══════════════════════════════════════════════════════════════

class TestPolygonRoom:
    """Test PolygonRoom dataclass and class methods."""

    def test_from_rect_creates_rectangular_polygon(self):
        """from_rect() must produce a valid rectangular polygon."""
        room = PolygonRoom.from_rect("R1", width=10, length=8)
        assert len(room.polygon) == 4
        assert is_rectangular(room.polygon)
        assert room.ceiling_height == 3.0

    def test_from_l_shape_creates_non_rectangular_polygon(self):
        """from_l_shape() must produce a valid L-shape polygon."""
        room = PolygonRoom.from_l_shape(
            "L1", total_width=20, total_length=15,
            cutout_width=8, cutout_length=6, cutout_corner="NE",
        )
        assert len(room.polygon) == 6
        assert not is_rectangular(room.polygon)

    def test_l_shape_area_smaller_than_bounding_rect(self):
        """L-shape area must be less than bounding rectangle area."""
        room = PolygonRoom.from_l_shape(
            "L1", total_width=20, total_length=15,
            cutout_width=8, cutout_length=6,
        )
        poly_area_val = polygon_area(room.polygon)
        bbox_area = 20 * 15
        assert poly_area_val < bbox_area
        assert poly_area_val == pytest.approx(bbox_area - 8 * 6, abs=1.0)

    def test_name_defaults_to_room_id(self):
        """Name must default to room_id if not provided."""
        room = PolygonRoom(room_id="R99", polygon=RECT_POLYGON)
        assert room.name == "R99"


# ═══════════════════════════════════════════════════════════════
# Test 2: PolygonDensityOptimizer — rectangular path
# ═══════════════════════════════════════════════════════════════

class TestPolygonOptimizerRectangular:
    """Test that rectangular polygons delegate to DensityOptimizer."""

    def test_rectangular_room_uses_rectangular_method(self, poly_optimizer):
        """Rectangular room must use method='rectangular'."""
        room = PolygonRoom.from_rect("rect1", width=12, length=8)
        result = poly_optimizer.optimize_polygon(room)
        assert result.method == "rectangular"

    def test_rectangular_room_has_valid_coverage(self, poly_optimizer):
        """Rectangular room must have coverage >= 99%."""
        room = PolygonRoom.from_rect("rect2", width=12, length=8)
        result = poly_optimizer.optimize_polygon(room)
        assert result.coverage_pct >= 99.0
        assert result.count >= 1

    def test_rectangular_room_detectors_translated(self, poly_optimizer):
        """Rectangular room with offset origin must have translated detectors."""
        room = PolygonRoom.from_rect(
            "offset", width=10, length=8, origin=(5.0, 3.0),
        )
        result = poly_optimizer.optimize_polygon(room)
        # All detectors must be in the offset coordinate space
        for x, y in result.detectors:
            assert x >= 5.0 - 0.2, f"Detector x={x} < origin offset 5.0"
            assert y >= 3.0 - 0.2, f"Detector y={y} < origin offset 3.0"


# ═══════════════════════════════════════════════════════════════
# Test 3: PolygonDensityOptimizer — non-rectangular path
# ═══════════════════════════════════════════════════════════════

class TestPolygonOptimizerGreedy:
    """Test Greedy Set Cover on non-rectangular polygons."""

    def test_l_shape_uses_greedy_polygon_method(self, poly_optimizer):
        """L-shape room must use method='greedy_polygon'."""
        room = PolygonRoom(
            room_id="L1", polygon=L_SHAPE_POLYGON,
            ceiling_height=3.0,
        )
        result = poly_optimizer.optimize_polygon(room)
        assert result.method == "greedy_polygon"

    def test_l_shape_has_coverage(self, poly_optimizer):
        """L-shape room must achieve >= 99% coverage."""
        room = PolygonRoom(
            room_id="L2", polygon=L_SHAPE_POLYGON,
            ceiling_height=3.0,
        )
        result = poly_optimizer.optimize_polygon(room)
        assert result.coverage_pct >= 99.0, f"Coverage {result.coverage_pct}% < 99%"

    def test_l_shape_detectors_inside_polygon(self, poly_optimizer):
        """All detectors from greedy must be inside the polygon."""
        room = PolygonRoom(
            room_id="L3", polygon=L_SHAPE_POLYGON,
            ceiling_height=3.0,
        )
        result = poly_optimizer.optimize_polygon(room)
        assert result.wall_violations == 0, (
            f"Greedy placed {result.wall_violations} detectors outside polygon"
        )

    def test_greedy_nfpa_spacing_audit(self, poly_optimizer):
        """Greedy result must include NFPA spacing audit."""
        room = PolygonRoom(
            room_id="L4", polygon=L_SHAPE_POLYGON,
            ceiling_height=3.0,
        )
        result = poly_optimizer.optimize_polygon(room)
        # nfpa_valid must be True or False (not unset)
        assert isinstance(result.nfpa_valid, bool)
        # spacing_violations must be a list
        assert isinstance(result.spacing_violations, list)

    def test_coverage_radius_from_ceiling_height(self, poly_optimizer):
        """High ceiling must produce smaller radius (more detectors)."""
        room_low = PolygonRoom(
            room_id="low", polygon=L_SHAPE_POLYGON, ceiling_height=3.0,
        )
        room_high = PolygonRoom(
            room_id="high", polygon=L_SHAPE_POLYGON, ceiling_height=9.1,
        )
        result_low = poly_optimizer.optimize_polygon(room_low)
        result_high = poly_optimizer.optimize_polygon(room_high)
        assert result_high.coverage_radius < result_low.coverage_radius


# ═══════════════════════════════════════════════════════════════
# Test 4: Internal helper functions
# ═══════════════════════════════════════════════════════════════

class TestInternalHelpers:
    """Test internal helper functions."""

    def test_interior_grid_inside_polygon(self):
        """Interior grid points must all lie inside the polygon."""
        grid = _generate_interior_grid(L_SHAPE_POLYGON, spacing=1.0)
        assert len(grid) > 0
        for pt in grid:
            assert point_in_polygon(pt, L_SHAPE_POLYGON), (
                f"Grid point {pt} is outside polygon"
            )

    def test_greedy_set_cover_covers_all(self):
        """Greedy set cover must cover all interior points."""
        grid = _generate_interior_grid(L_SHAPE_POLYGON, spacing=1.0)
        detectors = _greedy_set_cover(grid, L_SHAPE_POLYGON, DETECTOR_RADIUS)
        cov = _coverage_percentage(detectors, grid, DETECTOR_RADIUS)
        assert cov >= 99.99, f"Greedy coverage {cov}% < 99.99%"

    def test_wall_violations_count(self):
        """_count_wall_violations must correctly count outside detectors."""
        # Point clearly outside L-shape (in the cutout NE corner)
        outside = [(16, 12)]
        viol = _count_wall_violations(outside, L_SHAPE_POLYGON)
        assert viol == 1

    def test_nfpa_spacing_violation_detected(self):
        """_audit_nfpa_spacing must detect excessive spacing."""
        # Two detectors 15m apart (> MAX_SPACING_M = 9.144m)
        detectors = [(0, 0), (15, 0)]
        violations = _audit_nfpa_spacing(detectors)
        assert len(violations) > 0, "Should detect spacing violation"


# ═══════════════════════════════════════════════════════════════
# Test 5: FloorAnalyser polygon verifier integration
# ═══════════════════════════════════════════════════════════════

class TestFloorAnalyserPolygonVerifier:
    """
    Test FloorAnalyser with use_polygon_verifier=True.
    Same pattern as MIP integration (V2.3) — verification only.
    """

    def test_verifier_populates_fields(self, optimizer):
        """use_polygon_verifier=True must populate verifier fields for L-shape."""
        analyser = FloorAnalyser(
            floor_id="GF", optimizer=optimizer,
            use_polygon_verifier=True,
        )
        rooms = [
            {"room_id": "L1", "name": "l_shape_room",
             "polygon_coords": L_SHAPE_POLYGON, "ceiling_height": 3.0},
        ]
        report = analyser.analyse(rooms)
        s = report.room_summaries[0]
        assert s.polygon_verifier_count is not None, "polygon_verifier_count must be set"
        assert s.polygon_verifier_method == "greedy_polygon"
        assert s.polygon_verifier_ms > 0

    def test_verifier_off_no_fields(self, optimizer):
        """Without use_polygon_verifier, verifier fields must be None/0."""
        analyser = FloorAnalyser(floor_id="GF", optimizer=optimizer)
        rooms = [
            {"room_id": "L1", "name": "l_shape_room",
             "polygon_coords": L_SHAPE_POLYGON, "ceiling_height": 3.0},
        ]
        report = analyser.analyse(rooms)
        s = report.room_summaries[0]
        assert s.polygon_verifier_count is None
        assert s.polygon_verifier_method is None
        assert s.polygon_verifier_ms == 0.0

    def test_verifier_not_run_for_rectangular(self, optimizer):
        """Polygon verifier must NOT run for rectangular rooms."""
        analyser = FloorAnalyser(
            floor_id="GF", optimizer=optimizer,
            use_polygon_verifier=True,
        )
        rooms = [
            {"room_id": "R1", "name": "rect_room",
             "polygon_coords": RECT_POLYGON, "ceiling_height": 3.0},
        ]
        report = analyser.analyse(rooms)
        s = report.room_summaries[0]
        # Rectangular rooms should not have polygon verifier results
        assert s.polygon_verifier_count is None

    def test_optimality_gap_warning(self, optimizer):
        """If verifier proves fewer detectors, POLYGON_OPTIMALITY_GAP must appear."""
        analyser = FloorAnalyser(
            floor_id="GF", optimizer=optimizer,
            use_polygon_verifier=True,
        )
        rooms = [
            {"room_id": "L1", "name": "l_shape_room",
             "polygon_coords": L_SHAPE_POLYGON, "ceiling_height": 3.0},
        ]
        report = analyser.analyse(rooms)
        s = report.room_summaries[0]

        # If gap exists, warning must be present
        if s.polygon_optimality_gap:
            has_gap = any("POLYGON_OPTIMALITY_GAP" in w for w in s.warnings)
            assert has_gap, "POLYGON_OPTIMALITY_GAP warning missing"

    def test_verifier_does_not_change_placement(self, optimizer):
        """Verifier must not change the actual detector placement."""
        analyser_no_ver = FloorAnalyser(floor_id="GF", optimizer=optimizer)
        analyser_ver = FloorAnalyser(
            floor_id="GF", optimizer=optimizer,
            use_polygon_verifier=True,
        )
        rooms = [
            {"room_id": "L1", "name": "l_shape_room",
             "polygon_coords": L_SHAPE_POLYGON, "ceiling_height": 3.0},
        ]
        report_no = analyser_no_ver.analyse(rooms)
        report_ver = analyser_ver.analyse(rooms)
        s_no = report_no.room_summaries[0]
        s_ver = report_ver.room_summaries[0]

        # Placement must be identical
        assert s_no.detector_count == s_ver.detector_count, (
            f"Verifier changed detector count: {s_no.detector_count} vs {s_ver.detector_count}"
        )
        assert s_no.coverage_pct == s_ver.coverage_pct
        assert s_no.method == s_ver.method
        assert s_no.compliant == s_ver.compliant


# ═══════════════════════════════════════════════════════════════
# Test 6: Standalone usage of PolygonDensityOptimizer
# ═══════════════════════════════════════════════════════════════

class TestStandaloneUsage:
    """Test that PolygonDensityOptimizer can be used standalone."""

    def test_standalone_rectangular(self):
        """Standalone rectangular room analysis."""
        opt = PolygonDensityOptimizer()
        room = PolygonRoom.from_rect("standalone_rect", width=15, length=10)
        result = opt.optimize_polygon(room)
        assert result.method == "rectangular"
        assert result.count >= 1
        assert result.coverage_pct >= 99.0
        assert result.nfpa_valid is True

    def test_standalone_l_shape(self):
        """Standalone L-shape room analysis."""
        opt = PolygonDensityOptimizer()
        room = PolygonRoom.from_l_shape(
            "standalone_l", total_width=20, total_length=15,
            cutout_width=8, cutout_length=6, cutout_corner="NE",
        )
        result = opt.optimize_polygon(room)
        assert result.method == "greedy_polygon"
        assert result.count >= 1
        assert result.coverage_pct >= 99.0

    def test_analysis_ms_populated(self):
        """analysis_ms must be populated and > 0."""
        opt = PolygonDensityOptimizer()
        room = PolygonRoom(room_id="ms_test", polygon=L_SHAPE_POLYGON)
        result = opt.optimize_polygon(room)
        assert result.analysis_ms > 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
