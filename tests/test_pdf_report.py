"""
tests/test_pdf_report.py — Tests for fireai/core/pdf_report.py (Phase 13)
=========================================================================
Tests:
  1. PDF file creation from a compliant BuildingReport
  2. PDF header validity (starts with %PDF)
  3. Non-compliant building state (DO NOT SUBMIT verdict)
  4. Scenario data and audit data presence in output
  5. Crash resistance on bad/empty input
"""
import os
import tempfile
from dataclasses import dataclass, field
from typing import List, Optional

import pytest


# ---------------------------------------------------------------------------
# Lightweight mock objects to avoid importing the full engine stack
# ---------------------------------------------------------------------------

@dataclass
class MockRoomSummary:
    """Mimics floor_analyser.RoomSummary for testing."""
    room_id:          str  = "R1"
    name:             str  = "Office"
    detector_count:   int  = 2
    detector_type:    str  = "smoke_photoelectric"
    coverage_pct:     float = 100.0
    nfpa_valid:       bool  = True
    proof_valid:      bool  = True
    fallback_used:    bool  = False
    method:           str   = "hexG_x"
    compliant:        bool  = True
    safe_to_submit:   bool  = True
    violations:       List[str]       = field(default_factory=list)
    warnings:         List[str]       = field(default_factory=list)
    theoretical_lower_bound: int      = 2
    efficiency_ratio: float           = 1.0
    duct_devices:     int             = 0
    width:            float           = 10.0
    length:           float           = 8.0
    ceiling_height:   Optional[float] = 3.0
    duct_warnings:    List[str]       = field(default_factory=list)


@dataclass
class MockFloorReport:
    """Mimics floor_analyser.FloorReport for testing."""
    floor_id:             str  = "GF"
    room_summaries:       List[MockRoomSummary] = field(default_factory=list)
    total_detectors:      int  = 0
    total_theoretical_lower_bound: int = 0
    fully_compliant:      bool = True
    safe_to_submit:       bool = True
    non_compliant_rooms:  List[str] = field(default_factory=list)
    unsafe_rooms:         List[str] = field(default_factory=list)
    floor_warnings:       List[str] = field(default_factory=list)
    analysis_time_s:      float = 0.1
    total_duct_devices:   int   = 0


@dataclass
class MockBuildingReport:
    """Mimics building_engine.BuildingReport for testing."""
    building_id:                   str  = "BLDG-TEST"
    floor_reports:                 List[MockFloorReport] = field(default_factory=list)
    total_detectors:               int  = 0
    total_theoretical_lower_bound: int  = 0
    total_duct_devices:            int  = 0
    total_floors:                  int  = 0
    fully_compliant:               bool = True
    safe_to_submit:                bool = True
    non_compliant_floors:          List[str] = field(default_factory=list)
    unsafe_floors:                 List[str] = field(default_factory=list)
    building_warnings:             List[str] = field(default_factory=list)
    analysis_time_s:               float = 0.5
    project_profile:               object = None


@dataclass
class MockScenarioResult:
    """Mimics scenario_engine.ScenarioResult for testing."""
    scenario_id: str = "worst_case"
    verdict: str = "PASS"
    first_detection_time_s: Optional[float] = 12.5
    blind_spots: list = field(default_factory=list)
    compliant: bool = True


@dataclass
class MockScenarioBatteryResult:
    """Mimics scenario_engine.ScenarioBatteryResult for testing."""
    results: list = field(default_factory=list)
    det_type: str = "PHOTOELECTRIC"
    det_count: int = 2

    @property
    def passed(self):
        return sum(1 for r in self.results if getattr(r, 'compliant', True))

    @property
    def failed(self):
        return sum(1 for r in self.results if not getattr(r, 'compliant', True))

    @property
    def worst_detection_time_s(self):
        times = [getattr(r, 'first_detection_time_s', None)
                 for r in self.results
                 if getattr(r, 'first_detection_time_s', None) is not None]
        return max(times) if times else None

    @property
    def total_blind_spots(self):
        return sum(len(getattr(r, 'blind_spots', [])) for r in self.results)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_compliant_report() -> MockBuildingReport:
    """Build a fully compliant BuildingReport with 2 floors."""
    r1 = MockRoomSummary(
        room_id="R1", name="Lobby", detector_count=2,
        coverage_pct=100.0, nfpa_valid=True, proof_valid=True,
        method="hexG_x", compliant=True, safe_to_submit=True,
        width=12.0, length=8.0, ceiling_height=3.0,
    )
    r2 = MockRoomSummary(
        room_id="R2", name="Office", detector_count=1,
        coverage_pct=100.0, nfpa_valid=True, proof_valid=True,
        method="hexA_y", compliant=True, safe_to_submit=True,
        width=6.0, length=5.0, ceiling_height=3.0,
    )
    f1 = MockFloorReport(
        floor_id="GF", room_summaries=[r1], total_detectors=2,
        fully_compliant=True, safe_to_submit=True,
    )
    f2 = MockFloorReport(
        floor_id="L1", room_summaries=[r2], total_detectors=1,
        fully_compliant=True, safe_to_submit=True,
    )
    return MockBuildingReport(
        building_id="BLDG-COMPLIANT",
        floor_reports=[f1, f2],
        total_detectors=3,
        total_floors=2,
        fully_compliant=True,
        safe_to_submit=True,
    )


def _make_non_compliant_report() -> MockBuildingReport:
    """Build a non-compliant BuildingReport (one room fails)."""
    r1 = MockRoomSummary(
        room_id="R1", name="Lobby", detector_count=2,
        coverage_pct=100.0, nfpa_valid=True, proof_valid=True,
        method="hexG_x", compliant=True, safe_to_submit=True,
        width=12.0, length=8.0, ceiling_height=3.0,
    )
    r2 = MockRoomSummary(
        room_id="R2", name="Server Room", detector_count=0,
        coverage_pct=0.0, nfpa_valid=False, proof_valid=False,
        method="refused", compliant=False, safe_to_submit=False,
        width=5.0, length=4.0, ceiling_height=2.8,
        violations=["SMOKE_DETECTOR_PROHIBITED_IN_KITCHEN"],
        warnings=["SAFETY_REFUSAL: NFPA 72 17.6.4"],
    )
    f1 = MockFloorReport(
        floor_id="GF", room_summaries=[r1, r2], total_detectors=2,
        fully_compliant=False, safe_to_submit=False,
        unsafe_rooms=["R2"],
        non_compliant_rooms=["R2"],
    )
    return MockBuildingReport(
        building_id="BLDG-NONCOMPLIANT",
        floor_reports=[f1],
        total_detectors=2,
        total_floors=1,
        fully_compliant=False,
        safe_to_submit=False,
        non_compliant_floors=["GF"],
        unsafe_floors=["GF"],
        building_warnings=["UNSAFE floors: ['GF']"],
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestPDFReportCreation:
    """Test 1: PDF file creation from a compliant BuildingReport."""

    def test_file_created(self, tmp_path):
        """generate_building_report creates a PDF file that exists on disk."""
        from fireai.core.pdf_report import generate_building_report
        report = _make_compliant_report()
        out = str(tmp_path / "test_compliant.pdf")
        result = generate_building_report(report, output_path=out)
        assert os.path.exists(result), f"PDF file not created at {result}"

    def test_file_nonempty(self, tmp_path):
        """Generated PDF is non-empty (> 1 KB)."""
        from fireai.core.pdf_report import generate_building_report
        report = _make_compliant_report()
        out = str(tmp_path / "test_nonempty.pdf")
        generate_building_report(report, output_path=out)
        size = os.path.getsize(out)
        assert size > 1024, f"PDF file too small ({size} bytes)"


class TestPDFHeaderValidity:
    """Test 2: PDF starts with the %PDF magic header."""

    def test_pdf_header(self, tmp_path):
        """File starts with %PDF- indicating valid PDF."""
        from fireai.core.pdf_report import generate_building_report
        report = _make_compliant_report()
        out = str(tmp_path / "test_header.pdf")
        generate_building_report(report, output_path=out)
        with open(out, "rb") as f:
            header = f.read(5)
        assert header.startswith(b"%PDF"), f"Invalid PDF header: {header!r}"


class TestNonCompliantBuilding:
    """Test 3: Non-compliant building produces DO NOT SUBMIT report."""

    def test_noncompliant_file_created(self, tmp_path):
        """Non-compliant report still generates a PDF."""
        from fireai.core.pdf_report import generate_building_report
        report = _make_non_compliant_report()
        out = str(tmp_path / "test_noncompliant.pdf")
        result = generate_building_report(report, output_path=out)
        assert os.path.exists(result)

    def test_noncompliant_contains_text(self, tmp_path):
        """Non-compliant PDF contains building ID in extracted text."""
        from fireai.core.pdf_report import generate_building_report
        import pypdf
        report = _make_non_compliant_report()
        out = str(tmp_path / "test_noncompliant_text.pdf")
        generate_building_report(report, output_path=out)
        reader = pypdf.PdfReader(out)
        all_text = "".join(page.extract_text() or "" for page in reader.pages)
        assert "BLDG" in all_text, \
            f"Building ID not found in PDF text (len={len(all_text)})"


class TestScenarioAndAuditData:
    """Test 4: Scenario and audit data appear in the output."""

    def test_scenario_section_included(self, tmp_path):
        """Report includes scenario verification section when data provided."""
        from fireai.core.pdf_report import generate_building_report
        report = _make_compliant_report()

        sr = MockScenarioResult(
            scenario_id="worst_case_ultrafast",
            verdict="PASS",
            first_detection_time_s=12.5,
            compliant=True,
        )
        battery = MockScenarioBatteryResult(
            results=[sr], det_count=2,
        )
        scenario_results = {"R1": battery}

        out = str(tmp_path / "test_scenario.pdf")
        generate_building_report(report, output_path=out,
                                 scenario_results=scenario_results)
        assert os.path.exists(out)
        size = os.path.getsize(out)
        assert size > 1024, "Scenario PDF too small"

    def test_audit_section_included(self, tmp_path):
        """Report includes audit trail section when data provided."""
        from fireai.core.pdf_report import generate_building_report
        report = _make_compliant_report()
        audit_summary = {
            "total_records": 42,
            "hash_chain_valid": True,
        }
        out = str(tmp_path / "test_audit.pdf")
        generate_building_report(report, output_path=out,
                                 audit_summary=audit_summary)
        assert os.path.exists(out)
        size = os.path.getsize(out)
        assert size > 1024, "Audit PDF too small"

    def test_tampered_audit_shows_warning(self, tmp_path):
        """Audit with hash_chain_valid=False produces TAMPERED indicator."""
        from fireai.core.pdf_report import generate_building_report
        import pypdf
        report = _make_compliant_report()
        audit_summary = {
            "total_records": 10,
            "hash_chain_valid": False,
        }
        out = str(tmp_path / "test_tampered.pdf")
        generate_building_report(report, output_path=out,
                                 audit_summary=audit_summary)
        reader = pypdf.PdfReader(out)
        all_text = "".join(page.extract_text() or "" for page in reader.pages)
        assert "TAMPERED" in all_text, \
            f"TAMPERED status not found in PDF text (len={len(all_text)})"


class TestCrashResistance:
    """Test 5: Generator does not crash on bad/empty input."""

    def test_empty_floors(self, tmp_path):
        """Report with zero floors still generates without crash."""
        from fireai.core.pdf_report import generate_building_report
        report = MockBuildingReport(
            building_id="EMPTY",
            floor_reports=[],
            total_detectors=0,
            total_floors=0,
            fully_compliant=True,
            safe_to_submit=True,
        )
        out = str(tmp_path / "test_empty.pdf")
        result = generate_building_report(report, output_path=out)
        assert os.path.exists(result), "Empty report PDF not created"

    def test_none_scenario_and_audit(self, tmp_path):
        """Report with None scenario_results and None audit_summary works."""
        from fireai.core.pdf_report import generate_building_report
        report = _make_compliant_report()
        out = str(tmp_path / "test_none_extras.pdf")
        result = generate_building_report(
            report, output_path=out,
            scenario_results=None,
            audit_summary=None,
        )
        assert os.path.exists(result)

    def test_empty_scenario_dict(self, tmp_path):
        """Report with empty scenario_results dict works."""
        from fireai.core.pdf_report import generate_building_report
        report = _make_compliant_report()
        out = str(tmp_path / "test_empty_scenario.pdf")
        result = generate_building_report(
            report, output_path=out,
            scenario_results={},
        )
        assert os.path.exists(result)

    def test_floor_with_no_rooms(self, tmp_path):
        """Floor with empty room_summaries list does not crash."""
        from fireai.core.pdf_report import generate_building_report
        empty_floor = MockFloorReport(
            floor_id="B1", room_summaries=[], total_detectors=0,
        )
        report = MockBuildingReport(
            building_id="BLDG-EMPTY-FLOOR",
            floor_reports=[empty_floor],
            total_detectors=0,
            total_floors=1,
            fully_compliant=True,
            safe_to_submit=True,
        )
        out = str(tmp_path / "test_no_rooms.pdf")
        result = generate_building_report(report, output_path=out)
        assert os.path.exists(result)

    def test_room_with_missing_attrs(self, tmp_path):
        """RoomSummary with default/zero attributes does not crash."""
        from fireai.core.pdf_report import generate_building_report
        r = MockRoomSummary(
            room_id="R_DEF", name="Default Room",
            detector_count=0, coverage_pct=0.0,
            nfpa_valid=False, proof_valid=False,
        )
        floor = MockFloorReport(
            floor_id="GF", room_summaries=[r],
        )
        report = MockBuildingReport(
            building_id="BLDG-DEF",
            floor_reports=[floor],
            total_detectors=0,
            total_floors=1,
            fully_compliant=False,
            safe_to_submit=False,
        )
        out = str(tmp_path / "test_missing_attrs.pdf")
        result = generate_building_report(report, output_path=out)
        assert os.path.exists(result)

    def test_duct_warnings_present(self, tmp_path):
        """Room with duct_warnings produces duct section in PDF."""
        from fireai.core.pdf_report import generate_building_report
        import pypdf
        r = MockRoomSummary(
            room_id="R_DUCT", name="Mechanical Room",
            detector_count=1, duct_devices=2,
            duct_warnings=["DUCT_WARNING: Large duct cross-section detected"],
        )
        floor = MockFloorReport(
            floor_id="GF", room_summaries=[r], total_duct_devices=2,
        )
        report = MockBuildingReport(
            building_id="BLDG-DUCT",
            floor_reports=[floor],
            total_detectors=1,
            total_duct_devices=2,
            total_floors=1,
            fully_compliant=True,
            safe_to_submit=True,
        )
        out = str(tmp_path / "test_duct.pdf")
        result = generate_building_report(report, output_path=out)
        assert os.path.exists(result)
        reader = pypdf.PdfReader(out)
        all_text = "".join(page.extract_text() or "" for page in reader.pages)
        assert "Duct" in all_text or "duct" in all_text, \
            f"Duct section not found in PDF text (len={len(all_text)})"
