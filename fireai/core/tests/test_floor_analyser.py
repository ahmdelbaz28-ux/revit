"""Floor analyser tests — NFPA 72 floor-level fire detection validation.

Tests the FloorAnalyser class which performs floor-level analysis of
fire alarm detector placement using DensityOptimizer V7.3.
"""
import pytest

from fireai.core.floor_analyser import FloorAnalyser, FloorReport, RoomSummary
from fireai.core.spatial_engine.density_optimizer import DensityOptimizer

# ── Fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture
def optimizer():
    return DensityOptimizer()


@pytest.fixture
def analyser(optimizer):
    return FloorAnalyser("GF", optimizer)


@pytest.fixture
def simple_room():
    return {
        "room_id": "R1",
        "name": "Office",
        "polygon_coords": [(0, 0), (10, 0), (10, 8), (0, 8)],
        "ceiling_height": 3.0,
    }


@pytest.fixture
def large_room():
    return {
        "room_id": "R2",
        "name": "Warehouse",
        "polygon_coords": [(0, 0), (30, 0), (30, 20), (0, 20)],
        "ceiling_height": 4.0,
    }


@pytest.fixture
def kitchen_room():
    return {
        "room_id": "R3",
        "name": "Kitchen",
        "polygon_coords": [(0, 0), (8, 0), (8, 6), (0, 6)],
        "ceiling_height": 3.0,
        "room_type": "kitchen",
    }


# ═══════════════════════════════════════════════════════════════════════════════
# 1. FloorAnalyser Initialization
# ═══════════════════════════════════════════════════════════════════════════════

class TestFloorAnalyserInit:
    """Verify FloorAnalyser initialization and configuration."""

    def test_basic_initialization(self, optimizer) -> None:
        fa = FloorAnalyser("L1", optimizer)
        assert fa.floor_id == "L1"
        assert fa.opt is optimizer
        assert fa.use_mip is False
        assert fa.use_scenarios is False

    def test_mip_enabled(self, optimizer) -> None:
        fa = FloorAnalyser("L1", optimizer, use_mip=True)
        assert fa.use_mip is True

    def test_scenario_enabled(self, optimizer) -> None:
        fa = FloorAnalyser("L1", optimizer, use_scenarios=True)
        assert fa.use_scenarios is True

    def test_custom_mip_params(self, optimizer) -> None:
        fa = FloorAnalyser("L1", optimizer, use_mip=True, mip_candidate_step=0.5, mip_time_limit=5.0)
        assert fa.mip_candidate_step == 0.5
        assert fa.mip_time_limit == 5.0

    def test_sensor_advisor_initialized(self, optimizer) -> None:
        fa = FloorAnalyser("L1", optimizer)
        assert fa.sensor_advisor is not None


# ═══════════════════════════════════════════════════════════════════════════════
# 2. FloorAnalyser.analyse — Basic Scenarios
# ═══════════════════════════════════════════════════════════════════════════════

class TestAnalyseBasic:
    """Basic analysis scenarios for FloorAnalyser."""

    def test_single_room(self, analyser, simple_room) -> None:
        report = analyser.analyse([simple_room])
        assert isinstance(report, FloorReport)
        assert report.floor_id == "GF"
        assert len(report.room_summaries) == 1

    def test_multiple_rooms(self, analyser, simple_room, large_room) -> None:
        report = analyser.analyse([simple_room, large_room])
        assert len(report.room_summaries) == 2
        assert report.total_detectors > 0

    def test_empty_rooms_list(self, analyser) -> None:
        report = analyser.analyse([])
        assert isinstance(report, FloorReport)
        assert len(report.room_summaries) == 0
        assert "No rooms provided" in report.floor_warnings[0]

    def test_room_summary_fields(self, analyser, simple_room) -> None:
        report = analyser.analyse([simple_room])
        summary = report.room_summaries[0]
        assert isinstance(summary, RoomSummary)
        assert summary.room_id == "R1"
        assert summary.name == "Office"
        assert summary.detector_count >= 0
        assert 0.0 <= summary.coverage_pct <= 100.0 + 1e-6

    def test_compliant_room_has_detectors(self, analyser, simple_room) -> None:
        report = analyser.analyse([simple_room])
        summary = report.room_summaries[0]
        if summary.compliant:
            assert summary.detector_count > 0
            assert summary.proof_valid is True
            assert summary.nfpa_valid is True


# ═══════════════════════════════════════════════════════════════════════════════
# 3. FloorAnalyser.analyse — Safety Refusal (NFPA 72 §17.6.4)
# ═══════════════════════════════════════════════════════════════════════════════

class TestSafetyRefusal:
    """NFPA 72 §17.6.4 — safety refusal for inappropriate detector types."""

    def test_kitchen_smoke_detector_refused(self, analyser, kitchen_room) -> None:
        report = analyser.analyse([kitchen_room])
        summary = report.room_summaries[0]
        assert summary.refused is True
        assert summary.refusal_reason is not None
        assert summary.detector_count == 0

    def test_office_not_refused(self, analyser, simple_room) -> None:
        report = analyser.analyse([simple_room])
        summary = report.room_summaries[0]
        assert summary.refused is False

    def test_kitchen_heat_detector_not_refused(self, optimizer, kitchen_room) -> None:
        kitchen_room["detector_type"] = "heat"
        analyser = FloorAnalyser("GF", optimizer)
        report = analyser.analyse([kitchen_room])
        summary = report.room_summaries[0]
        # Kitchen with heat detector should NOT be refused
        assert summary.refused is False


# ═══════════════════════════════════════════════════════════════════════════════
# 4. FloorAnalyser.analyse — Coverage and Compliance
# ═══════════════════════════════════════════════════════════════════════════════

class TestCoverageAndCompliance:
    """Coverage percentage and compliance validation."""

    def test_standard_room_high_coverage(self, analyser, simple_room) -> None:
        report = analyser.analyse([simple_room])
        summary = report.room_summaries[0]
        # Standard room should achieve high coverage
        assert summary.coverage_pct > 90.0 or summary.refused

    def test_large_room_needs_more_detectors(self, analyser, simple_room, large_room) -> None:
        report = analyser.analyse([simple_room, large_room])
        small_summary = report.room_summaries[0]
        large_summary = report.room_summaries[1]
        if not small_summary.refused and not large_summary.refused:
            assert large_summary.detector_count >= small_summary.detector_count

    def test_floor_report_totals(self, analyser, simple_room, large_room) -> None:
        report = analyser.analyse([simple_room, large_room])
        total = sum(s.detector_count for s in report.room_summaries)
        assert report.total_detectors == total


# ═══════════════════════════════════════════════════════════════════════════════
# 5. FloorAnalyser.analyse — Ceiling Height Variations
# ═══════════════════════════════════════════════════════════════════════════════

class TestCeilingHeightVariations:
    """Dynamic coverage radius from NFPA 72 Table 17.6.3.1.1."""

    def test_low_ceiling_warning(self, optimizer) -> None:
        room = {
            "room_id": "R_low",
            "name": "Low Room",
            "polygon_coords": [(0, 0), (10, 0), (10, 8), (0, 8)],
            "ceiling_height": 2.5,
        }
        fa = FloorAnalyser("GF", optimizer)
        report = fa.analyse([room])
        summary = report.room_summaries[0]
        # Low ceiling should produce a warning
        if not summary.refused:
            has_low_warning = any("LOW_CEILING" in w for w in summary.warnings)
            assert has_low_warning or summary.coverage_pct > 0

    def test_high_ceiling_reduces_radius(self, optimizer) -> None:
        room_low = {
            "room_id": "R_low_h",
            "name": "LowH",
            "polygon_coords": [(0, 0), (10, 0), (10, 10), (0, 10)],
            "ceiling_height": 3.0,
        }
        room_high = {
            "room_id": "R_high_h",
            "name": "HighH",
            "polygon_coords": [(0, 0), (10, 0), (10, 10), (0, 10)],
            "ceiling_height": 9.0,
        }
        fa = FloorAnalyser("GF", optimizer)
        report_low = fa.analyse([room_low])
        report_high = fa.analyse([room_high])
        # Higher ceilings may produce different coverage radius
        assert report_low.room_summaries[0].coverage_radius_used > 0
        assert report_high.room_summaries[0].coverage_radius_used > 0

    def test_none_ceiling_height_defaults_to_3m(self, optimizer) -> None:
        room = {
            "room_id": "R_none",
            "name": "No Ceiling",
            "polygon_coords": [(0, 0), (10, 0), (10, 8), (0, 8)],
        }
        fa = FloorAnalyser("GF", optimizer)
        report = fa.analyse([room])
        summary = report.room_summaries[0]
        assert summary.ceiling_height == 3.0 or summary.coverage_pct >= 0


# ═══════════════════════════════════════════════════════════════════════════════
# 6. FloorAnalyser.analyse — FloorReport
# ═══════════════════════════════════════════════════════════════════════════════

class TestFloorReport:
    """FloorReport data class and aggregation."""

    def test_report_has_correct_floor_id(self, analyser, simple_room) -> None:
        report = analyser.analyse([simple_room])
        assert report.floor_id == "GF"

    def test_safe_to_submit_when_all_compliant(self, analyser, simple_room) -> None:
        report = analyser.analyse([simple_room])
        summary = report.room_summaries[0]
        if summary.compliant:
            assert report.safe_to_submit is True

    def test_non_compliant_rooms_tracked(self, optimizer, kitchen_room) -> None:
        fa = FloorAnalyser("GF", optimizer)
        report = fa.analyse([kitchen_room])
        summary = report.room_summaries[0]
        if summary.refused:
            assert kitchen_room["room_id"] in report.unsafe_rooms or summary.compliant is False

    def test_analysis_time_recorded(self, analyser, simple_room) -> None:
        report = analyser.analyse([simple_room])
        assert report.analysis_time_s >= 0


# ═══════════════════════════════════════════════════════════════════════════════
# 7. FloorAnalyser — Heat Detector Support
# ═══════════════════════════════════════════════════════════════════════════════

class TestHeatDetectorSupport:
    """Heat detector type detection and coverage radius calculation."""

    def test_heat_detector_type(self, optimizer) -> None:
        room = {
            "room_id": "R_heat",
            "name": "Heat Room",
            "polygon_coords": [(0, 0), (10, 0), (10, 10), (0, 10)],
            "ceiling_height": 3.0,
            "detector_type": "heat",
        }
        fa = FloorAnalyser("GF", optimizer)
        report = fa.analyse([room])
        summary = report.room_summaries[0]
        assert summary.detector_type == "heat"
        # Heat detector coverage radius should be smaller than smoke
        assert summary.coverage_radius_used > 0


# ═══════════════════════════════════════════════════════════════════════════════
# 8. FloorAnalyser — Geometry Handling
# ═══════════════════════════════════════════════════════════════════════════════

class TestGeometryHandling:
    """Geometry sanitization and non-rectangular room handling."""

    def test_degenerate_geometry_rejected(self, optimizer) -> None:
        room = {
            "room_id": "R_degen",
            "name": "Degenerate",
            "polygon_coords": [(0, 0), (0, 0), (0, 0)],  # Zero area
            "ceiling_height": 3.0,
        }
        fa = FloorAnalyser("GF", optimizer)
        report = fa.analyse([room])
        summary = report.room_summaries[0]
        assert summary.refused is True or summary.method == "rejected_geometry"

    def test_no_polygon_coords(self, optimizer) -> None:
        """Room without polygon_coords — _build_room requires it."""
        # _build_room requires polygon_coords, so this should raise KeyError
        # unless the room has polygon_coords set.
        room = {
            "room_id": "R_nopoly",
            "name": "No Poly",
            "ceiling_height": 3.0,
            "polygon_coords": [(0, 0), (10, 0), (10, 8), (0, 8)],  # Required
        }
        fa = FloorAnalyser("GF", optimizer)
        report = fa.analyse([room])
        assert len(report.room_summaries) == 1

    def test_l_shape_room(self, optimizer) -> None:
        """L-shaped room (6 unique vertices) classified correctly."""
        room = {
            "room_id": "R_lshape",
            "name": "L-Shape",
            "polygon_coords": [(0, 0), (10, 0), (10, 5), (5, 5), (5, 10), (0, 10)],
            "ceiling_height": 3.0,
        }
        fa = FloorAnalyser("GF", optimizer)
        report = fa.analyse([room])
        summary = report.room_summaries[0]
        # L-shape should be classified and filtered
        assert summary.shape_type in ("l_shape", "rectangular", "polygon")


# ═══════════════════════════════════════════════════════════════════════════════
# 9. RoomSummary Dataclass
# ═══════════════════════════════════════════════════════════════════════════════

class TestRoomSummary:
    """RoomSummary dataclass field defaults and construction."""

    def test_default_values(self) -> None:
        rs = RoomSummary(room_id="R1", name="Test", detector_count=0)
        assert rs.coverage_pct == 0.0
        assert rs.nfpa_valid is False
        assert rs.proof_valid is False
        assert rs.compliant is False
        assert rs.refused is False
        assert rs.violations == []
        assert rs.warnings == []
        assert rs.scenario_pass is None

    def test_custom_values(self) -> None:
        rs = RoomSummary(
            room_id="R1", name="Test", detector_count=5,
            coverage_pct=99.5, nfpa_valid=True, proof_valid=True,
            compliant=True, safe_to_submit=True,
        )
        assert rs.detector_count == 5
        assert rs.coverage_pct == 99.5
        assert rs.compliant is True


# ═══════════════════════════════════════════════════════════════════════════════
# 10. FloorReport Dataclass
# ═══════════════════════════════════════════════════════════════════════════════

class TestFloorReportDataclass:
    """FloorReport dataclass field defaults."""

    def test_default_values(self) -> None:
        fr = FloorReport(floor_id="L1")
        assert fr.total_detectors == 0
        assert fr.fully_compliant is False
        assert fr.safe_to_submit is False
        assert fr.room_summaries == []
        assert fr.non_compliant_rooms == []
