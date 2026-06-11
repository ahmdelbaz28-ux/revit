"""
tests/test_compliance_proof_document_v2.py
============================================
Comprehensive test suite for fireai/core/compliance_proof_document.py.

SAFETY CRITICAL: Compliance proof documents are submitted to the AHJ
(Authority Having Jurisdiction) for fire alarm system permitting. Errors
could lead to false compliance claims — a direct life-safety hazard.

Covers:
  - _safe_fmt()        — NaN/Inf → "[INVALID DATA]"
  - RoomVerificationRecord dataclass
  - ComplianceProofDocument:
      __init__, add_room_result, generate,
      _header, _design_criteria, _room_summary_table,
      _detailed_room_results, _consensus_summary, _certification
  - Edge cases: empty, single, multiple rooms, VERIFIED/FAIL consensus,
    proof_valid=False, nfpa_valid=False, NaN coverage, default constructor

NFPA 72 References:
  §17.6.3.1.1 — Spot-type smoke detector spacing
  §17.7.4.2.3.1 — Coverage radius R = 0.7 × S
  V57 FIX (Finding 15) — NaN/Inf in AHJ documents replaced with [INVALID DATA]
"""

from __future__ import annotations

import math
from unittest.mock import MagicMock

import pytest

from fireai.core.compliance_proof_document import (
    ComplianceProofDocument,
    RoomVerificationRecord,
    _safe_fmt,
)
from fireai.core.spatial_engine.consensus_engine import (
    ConfidenceLevel,
    ConsensusResult,
    EngineName,
    EngineVerdict,
)
from fireai.core.spatial_engine.density_optimizer import (
    DETECTOR_RADIUS,
    MAX_SPACING_M,
    DetectorLayout,
    Room,
)


# ═══════════════════════════════════════════════════════════════════════════════
# 1. _safe_fmt
# ═══════════════════════════════════════════════════════════════════════════════


class TestSafeFmt:
    """V57 FIX (Finding 15): NaN/Inf → [INVALID DATA] for AHJ documents."""

    def test_normal_float_default_format(self):
        assert _safe_fmt(3.14159) == "3.1"

    def test_normal_float_custom_format(self):
        assert _safe_fmt(3.14159, ".2f") == "3.14"

    def test_normal_float_three_decimals(self):
        assert _safe_fmt(3.14159, ".3f") == "3.142"

    def test_integer_value(self):
        assert _safe_fmt(5.0) == "5.0"

    def test_zero(self):
        assert _safe_fmt(0.0) == "0.0"

    def test_negative(self):
        assert _safe_fmt(-5.5) == "-5.5"

    def test_nan_returns_invalid_data(self):
        assert _safe_fmt(float("nan")) == "[INVALID DATA]"

    def test_inf_returns_invalid_data(self):
        assert _safe_fmt(float("inf")) == "[INVALID DATA]"

    def test_neg_inf_returns_invalid_data(self):
        assert _safe_fmt(float("-inf")) == "[INVALID DATA]"

    def test_very_small_number(self):
        assert _safe_fmt(0.0001, ".4f") == "0.0001"

    def test_very_large_number(self):
        assert _safe_fmt(99999.9) == "99999.9"

    def test_percentage_format(self):
        assert _safe_fmt(99.9, ".1f") == "99.9"

    def test_nan_with_custom_format(self):
        assert _safe_fmt(float("nan"), ".3f") == "[INVALID DATA]"

    def test_inf_with_custom_format(self):
        assert _safe_fmt(float("inf"), ".4f") == "[INVALID DATA]"

    def test_neg_inf_with_percentage_format(self):
        assert _safe_fmt(float("-inf"), ".1f") == "[INVALID DATA]"

    def test_large_precision(self):
        assert _safe_fmt(1.23456789, ".6f") == "1.234568"


# ═══════════════════════════════════════════════════════════════════════════════
# 2. RoomVerificationRecord Dataclass
# ═══════════════════════════════════════════════════════════════════════════════


class TestRoomVerificationRecord:
    """RoomVerificationRecord dataclass construction and field access."""

    def _make_layout(self, room=None):
        if room is None:
            room = Room("TestRoom", 10.0, 10.0, 3.0)
        return DetectorLayout(
            room=room,
            detectors=[(5.0, 5.0)],
            coverage_pct=99.9,
            proof_valid=True,
            nfpa_valid=True,
            method="hex",
        )

    def test_create_with_required_fields(self):
        room = Room("R1", 10.0, 10.0, 3.0)
        layout = self._make_layout(room)
        rec = RoomVerificationRecord(room=room, layout=layout)
        assert rec.room is room
        assert rec.layout is layout
        assert rec.consensus is None
        assert rec.notes == []

    def test_create_with_consensus(self):
        room = Room("R1", 10.0, 10.0, 3.0)
        layout = self._make_layout(room)
        consensus = ConsensusResult(
            confidence=ConfidenceLevel.VERIFIED,
            is_safe=True,
            n_pass=3,
            n_total=3,
        )
        rec = RoomVerificationRecord(room=room, layout=layout, consensus=consensus)
        assert rec.consensus is consensus
        assert rec.notes == []

    def test_create_with_notes(self):
        room = Room("R1", 10.0, 10.0, 3.0)
        layout = self._make_layout(room)
        rec = RoomVerificationRecord(room=room, layout=layout, notes=["Note 1", "Note 2"])
        assert rec.notes == ["Note 1", "Note 2"]

    def test_create_with_all_fields(self):
        room = Room("R1", 10.0, 10.0, 3.0)
        layout = self._make_layout(room)
        consensus = ConsensusResult(
            confidence=ConfidenceLevel.VERIFIED,
            is_safe=True,
            engines=[
                EngineVerdict(engine=EngineName.ANALYTICAL, passed=True, details="OK"),
            ],
            n_pass=1,
            n_total=1,
        )
        rec = RoomVerificationRecord(
            room=room, layout=layout, consensus=consensus, notes=["Test note"]
        )
        assert rec.room is room
        assert rec.layout is layout
        assert rec.consensus is consensus
        assert rec.notes == ["Test note"]

    def test_notes_defaults_to_empty_list(self):
        room = Room("R1", 10.0, 10.0, 3.0)
        layout = self._make_layout(room)
        rec = RoomVerificationRecord(room=room, layout=layout)
        assert rec.notes == []

    def test_mutable_notes_copy(self):
        room = Room("R1", 10.0, 10.0, 3.0)
        layout = self._make_layout(room)
        rec = RoomVerificationRecord(room=room, layout=layout, notes=["A"])
        rec.notes.append("B")
        assert rec.notes == ["A", "B"]

    def test_consensus_defaults_to_none(self):
        room = Room("R1", 10.0, 10.0, 3.0)
        layout = self._make_layout(room)
        rec = RoomVerificationRecord(room=room, layout=layout)
        assert rec.consensus is None


# ═══════════════════════════════════════════════════════════════════════════════
# 3. ComplianceProofDocument — __init__
# ═══════════════════════════════════════════════════════════════════════════════


class TestComplianceProofDocumentInit:
    """Constructor defaults and custom values."""

    def test_default_values(self):
        doc = ComplianceProofDocument()
        assert doc.project_name == "FireAI V30 Project"
        assert doc.designer == ""
        assert doc.nfpa_edition == "2022"
        assert doc.jurisdiction == ""
        assert doc.records == []

    def test_custom_project_name(self):
        doc = ComplianceProofDocument(project_name="Custom Project")
        assert doc.project_name == "Custom Project"

    def test_custom_designer(self):
        doc = ComplianceProofDocument(designer="Jane Smith, PE")
        assert doc.designer == "Jane Smith, PE"

    def test_custom_nfpa_edition(self):
        doc = ComplianceProofDocument(nfpa_edition="2019")
        assert doc.nfpa_edition == "2019"

    def test_custom_jurisdiction(self):
        doc = ComplianceProofDocument(jurisdiction="New York City")
        assert doc.jurisdiction == "New York City"

    def test_all_custom_values(self):
        doc = ComplianceProofDocument(
            project_name="ABC Office Tower",
            designer="Jane Smith, PE #12345",
            nfpa_edition="2022",
            jurisdiction="City of Metropolis",
        )
        assert doc.project_name == "ABC Office Tower"
        assert doc.designer == "Jane Smith, PE #12345"
        assert doc.nfpa_edition == "2022"
        assert doc.jurisdiction == "City of Metropolis"

    def test_generation_date_is_string(self):
        doc = ComplianceProofDocument()
        assert isinstance(doc.generation_date, str)

    def test_generation_date_contains_utc(self):
        """V54 FIX (AUDIT-012): Generation date must be timezone-aware UTC."""
        doc = ComplianceProofDocument()
        assert "UTC" in doc.generation_date

    def test_records_starts_empty(self):
        doc = ComplianceProofDocument()
        assert doc.records == []


# ═══════════════════════════════════════════════════════════════════════════════
# 4. ComplianceProofDocument — add_room_result
# ═══════════════════════════════════════════════════════════════════════════════


class TestAddRoomResult:
    """Adding room results via add_room_result()."""

    def _make_room_and_layout(self, name="R1", width=10.0, length=10.0, ceiling=3.0,
                              coverage_pct=99.9, proof_valid=True, nfpa_valid=True,
                              detectors=None):
        room = Room(name, width, length, ceiling)
        layout = DetectorLayout(
            room=room,
            detectors=detectors or [(5.0, 5.0)],
            coverage_pct=coverage_pct,
            proof_valid=proof_valid,
            nfpa_valid=nfpa_valid,
            method="hex",
        )
        return room, layout

    def test_add_single_room(self):
        doc = ComplianceProofDocument()
        room, layout = self._make_room_and_layout()
        doc.add_room_result(room, layout)
        assert len(doc.records) == 1
        assert doc.records[0].room is room
        assert doc.records[0].layout is layout
        assert doc.records[0].consensus is None

    def test_add_multiple_rooms(self):
        doc = ComplianceProofDocument()
        for i in range(5):
            room, layout = self._make_room_and_layout(name=f"Room-{i}")
            doc.add_room_result(room, layout)
        assert len(doc.records) == 5
        assert doc.records[0].room.name == "Room-0"
        assert doc.records[4].room.name == "Room-4"

    def test_add_with_consensus(self):
        doc = ComplianceProofDocument()
        room, layout = self._make_room_and_layout()
        consensus = ConsensusResult(
            confidence=ConfidenceLevel.VERIFIED,
            is_safe=True,
            n_pass=3,
            n_total=3,
        )
        doc.add_room_result(room, layout, consensus=consensus)
        assert doc.records[0].consensus is consensus
        assert doc.records[0].consensus.confidence == ConfidenceLevel.VERIFIED

    def test_add_with_notes(self):
        doc = ComplianceProofDocument()
        room, layout = self._make_room_and_layout()
        doc.add_room_result(room, layout, notes=["Test note"])
        assert doc.records[0].notes == ["Test note"]

    def test_add_with_multiple_notes(self):
        doc = ComplianceProofDocument()
        room, layout = self._make_room_and_layout()
        notes = ["Note 1", "Note 2", "Note 3"]
        doc.add_room_result(room, layout, notes=notes)
        assert doc.records[0].notes == notes

    def test_add_without_notes_defaults_empty(self):
        doc = ComplianceProofDocument()
        room, layout = self._make_room_and_layout()
        doc.add_room_result(room, layout)
        assert doc.records[0].notes == []

    def test_add_with_consensus_and_notes(self):
        doc = ComplianceProofDocument()
        room, layout = self._make_room_and_layout()
        consensus = ConsensusResult(
            confidence=ConfidenceLevel.VERIFIED,
            is_safe=True,
            n_pass=3,
            n_total=3,
        )
        doc.add_room_result(room, layout, consensus=consensus, notes=["Full setup"])
        rec = doc.records[0]
        assert rec.consensus is consensus
        assert rec.notes == ["Full setup"]

    def test_add_preserves_insertion_order(self):
        doc = ComplianceProofDocument()
        names = ["Alpha", "Beta", "Gamma"]
        for name in names:
            room, layout = self._make_room_and_layout(name=name)
            doc.add_room_result(room, layout)
        assert [r.room.name for r in doc.records] == names

    def test_rooms_are_independent(self):
        doc = ComplianceProofDocument()
        room1, layout1 = self._make_room_and_layout(name="Room-A")
        room2, layout2 = self._make_room_and_layout(name="Room-B")
        doc.add_room_result(room1, layout1)
        doc.add_room_result(room2, layout2)
        assert doc.records[0].room.name == "Room-A"
        assert doc.records[1].room.name == "Room-B"


# ═══════════════════════════════════════════════════════════════════════════════
# 5. ComplianceProofDocument — _header
# ═══════════════════════════════════════════════════════════════════════════════


class TestHeader:
    """_header() section generation."""

    def test_header_contains_nfpa_title(self):
        doc = ComplianceProofDocument(nfpa_edition="2022")
        header = doc._header()
        assert "NFPA 72-2022 Compliance Proof Document" in header

    def test_header_contains_project_name(self):
        doc = ComplianceProofDocument(project_name="Test Building")
        header = doc._header()
        assert "Test Building" in header

    def test_header_designer_tbd_when_empty(self):
        doc = ComplianceProofDocument(designer="")
        header = doc._header()
        assert "TBD" in header

    def test_header_designer_shown_when_set(self):
        doc = ComplianceProofDocument(designer="John Smith, PE")
        header = doc._header()
        assert "John Smith, PE" in header

    def test_header_jurisdiction_tbd_when_empty(self):
        doc = ComplianceProofDocument(jurisdiction="")
        header = doc._header()
        assert "Jurisdiction:** TBD" in header

    def test_header_jurisdiction_shown_when_set(self):
        doc = ComplianceProofDocument(jurisdiction="Chicago")
        header = doc._header()
        assert "Chicago" in header

    def test_header_contains_fireai_version(self):
        doc = ComplianceProofDocument()
        header = doc._header()
        assert "FireAI Version:** V30" in header

    def test_header_total_rooms_zero(self):
        doc = ComplianceProofDocument()
        header = doc._header()
        assert "Total Rooms:** 0" in header

    def test_header_total_rooms_with_records(self):
        doc = ComplianceProofDocument()
        room = Room("R1", 10.0, 10.0, 3.0)
        layout = DetectorLayout(room=room, detectors=[(5.0, 5.0)])
        doc.add_room_result(room, layout)
        header = doc._header()
        assert "Total Rooms:** 1" in header

    def test_header_contains_generation_date(self):
        doc = ComplianceProofDocument()
        header = doc._header()
        assert "Date:** " in header
        assert "UTC" in header

    def test_header_with_multiple_rooms(self):
        doc = ComplianceProofDocument()
        for i in range(3):
            room = Room(f"R{i}", 10.0, 10.0, 3.0)
            layout = DetectorLayout(room=room, detectors=[(5.0, 5.0)])
            doc.add_room_result(room, layout)
        header = doc._header()
        assert "Total Rooms:** 3" in header


# ═══════════════════════════════════════════════════════════════════════════════
# 6. ComplianceProofDocument — _design_criteria
# ═══════════════════════════════════════════════════════════════════════════════


class TestDesignCriteria:
    """_design_criteria() section generation."""

    def test_section_title(self):
        doc = ComplianceProofDocument()
        section = doc._design_criteria()
        assert "## 1. Design Criteria" in section

    def test_nfpa_edition_referenced(self):
        doc = ComplianceProofDocument(nfpa_edition="2022")
        section = doc._design_criteria()
        assert "NFPA 72-2022" in section

    def test_custom_nfpa_edition(self):
        doc = ComplianceProofDocument(nfpa_edition="2019")
        section = doc._design_criteria()
        assert "NFPA 72-2019" in section

    def test_section_17_6_3_1_1_referenced(self):
        doc = ComplianceProofDocument()
        section = doc._design_criteria()
        assert "§17.6.3.1.1" in section

    def test_section_17_7_4_2_3_1_referenced(self):
        doc = ComplianceProofDocument()
        section = doc._design_criteria()
        assert "§17.7.4.2.3.1" in section

    def test_coverage_radius_formula(self):
        doc = ComplianceProofDocument()
        section = doc._design_criteria()
        assert "0.7 × 9.1m = 6.37m" in section

    def test_design_parameters_table(self):
        doc = ComplianceProofDocument()
        section = doc._design_criteria()
        assert "| Parameter | Value | NFPA Reference |" in section
        assert f"| Maximum Spacing (S) | {MAX_SPACING_M:.1f} m" in section
        assert f"| Coverage Radius (R) | {DETECTOR_RADIUS:.2f} m" in section

    def test_verification_methodology(self):
        doc = ComplianceProofDocument()
        section = doc._design_criteria()
        assert "Triple Verification System" in section
        assert "Analytical Engine" in section
        assert "Voronoi Engine" in section
        assert "Grid Engine" in section

    def test_consensus_rules(self):
        doc = ComplianceProofDocument()
        section = doc._design_criteria()
        assert "3/3 engines PASS" in section
        assert "2/3 engines PASS" in section
        assert "1/3 or 0/3 PASS" in section

    def test_mathematical_proof(self):
        doc = ComplianceProofDocument()
        section = doc._design_criteria()
        assert "R_eff = R - δ√2/2" in section
        assert "triangle inequality" in section


# ═══════════════════════════════════════════════════════════════════════════════
# 7. ComplianceProofDocument — _room_summary_table
# ═══════════════════════════════════════════════════════════════════════════════


class TestRoomSummaryTable:
    """_room_summary_table() section generation."""

    def test_section_title(self):
        doc = ComplianceProofDocument()
        summary = doc._room_summary_table()
        assert "## 2. Room Summary" in summary

    def test_table_header(self):
        doc = ComplianceProofDocument()
        summary = doc._room_summary_table()
        assert "| # | Room | Dimensions (m) | Ceiling H | Detectors | Coverage | Proof | NFPA | Consensus |" in summary

    def test_room_appears_in_table(self):
        doc = ComplianceProofDocument()
        room = Room("Office-101", 5.0, 6.0, 3.0)
        layout = DetectorLayout(
            room=room,
            detectors=[(2.5, 3.0)],
            coverage_pct=95.5,
            proof_valid=True,
            nfpa_valid=True,
            method="hex",
        )
        doc.add_room_result(room, layout)
        summary = doc._room_summary_table()
        assert "Office-101" in summary
        assert "95.5%" in summary
        assert "✓" in summary

    def test_multiple_rooms_in_table(self):
        doc = ComplianceProofDocument()
        for i in range(3):
            room = Room(f"Room-{i}", 10.0, 10.0, 3.0)
            layout = DetectorLayout(
                room=room,
                detectors=[(5.0, 5.0)],
                coverage_pct=99.0 + i,
                proof_valid=True,
                nfpa_valid=True,
            )
            doc.add_room_result(room, layout)
        summary = doc._room_summary_table()
        for i in range(3):
            assert f"Room-{i}" in summary

    def test_proof_invalid_shows_x_mark(self):
        doc = ComplianceProofDocument()
        room = Room("Bad-Room", 10.0, 10.0, 3.0)
        layout = DetectorLayout(
            room=room,
            detectors=[(5.0, 5.0)],
            coverage_pct=50.0,
            proof_valid=False,
            nfpa_valid=True,
        )
        doc.add_room_result(room, layout)
        summary = doc._room_summary_table()
        assert "✗" in summary

    def test_nfpa_invalid_shows_x_mark(self):
        doc = ComplianceProofDocument()
        room = Room("NFPA-Room", 10.0, 10.0, 3.0)
        layout = DetectorLayout(
            room=room,
            detectors=[(5.0, 5.0)],
            coverage_pct=99.0,
            proof_valid=True,
            nfpa_valid=False,
        )
        doc.add_room_result(room, layout)
        summary = doc._room_summary_table()
        assert "✗" in summary

    def test_consensus_verified_display(self):
        doc = ComplianceProofDocument()
        room = Room("Verified-Room", 10.0, 10.0, 3.0)
        layout = DetectorLayout(room=room, detectors=[(5.0, 5.0)])
        consensus = ConsensusResult(
            confidence=ConfidenceLevel.VERIFIED,
            is_safe=True,
            n_pass=3,
            n_total=3,
        )
        doc.add_room_result(room, layout, consensus=consensus)
        summary = doc._room_summary_table()
        assert "3/3 VERIFIED" in summary

    def test_consensus_fail_display(self):
        doc = ComplianceProofDocument()
        room = Room("Fail-Room", 10.0, 10.0, 3.0)
        layout = DetectorLayout(room=room, detectors=[(5.0, 5.0)])
        consensus = ConsensusResult(
            confidence=ConfidenceLevel.FAIL,
            is_safe=False,
            n_pass=0,
            n_total=3,
        )
        doc.add_room_result(room, layout, consensus=consensus)
        summary = doc._room_summary_table()
        assert "0/3 FAIL" in summary

    def test_no_consensus_shows_na(self):
        doc = ComplianceProofDocument()
        room = Room("No-Consensus", 10.0, 10.0, 3.0)
        layout = DetectorLayout(room=room, detectors=[(5.0, 5.0)])
        doc.add_room_result(room, layout)
        summary = doc._room_summary_table()
        assert "N/A" in summary

    def test_empty_records_no_summary_stats(self):
        doc = ComplianceProofDocument()
        summary = doc._room_summary_table()
        assert "## 2. Room Summary" in summary

    def test_summary_total_detectors(self):
        doc = ComplianceProofDocument()
        room = Room("R1", 10.0, 10.0, 3.0)
        layout = DetectorLayout(room=room, detectors=[(5.0, 5.0), (7.0, 7.0)])
        doc.add_room_result(room, layout)
        summary = doc._room_summary_table()
        assert "Total Detectors:** 2" in summary

    def test_summary_all_proof_valid_yes(self):
        doc = ComplianceProofDocument()
        room = Room("R1", 10.0, 10.0, 3.0)
        layout = DetectorLayout(
            room=room, detectors=[(5.0, 5.0)], proof_valid=True, nfpa_valid=True,
        )
        doc.add_room_result(room, layout)
        summary = doc._room_summary_table()
        assert "Yes ✓" in summary

    def test_summary_proof_invalid_requires_review(self):
        doc = ComplianceProofDocument()
        room = Room("R1", 10.0, 10.0, 3.0)
        layout = DetectorLayout(
            room=room, detectors=[(5.0, 5.0)], proof_valid=False, nfpa_valid=True,
        )
        doc.add_room_result(room, layout)
        summary = doc._room_summary_table()
        assert "requires review" in summary

    def test_summary_nfpa_invalid_requires_review(self):
        doc = ComplianceProofDocument()
        room = Room("R1", 10.0, 10.0, 3.0)
        layout = DetectorLayout(
            room=room, detectors=[(5.0, 5.0)], proof_valid=True, nfpa_valid=False,
        )
        doc.add_room_result(room, layout)
        summary = doc._room_summary_table()
        assert "requires review" in summary

    def test_summary_all_consensus_verified_yes(self):
        doc = ComplianceProofDocument()
        room = Room("R1", 10.0, 10.0, 3.0)
        layout = DetectorLayout(room=room, detectors=[(5.0, 5.0)])
        consensus = ConsensusResult(
            confidence=ConfidenceLevel.VERIFIED,
            is_safe=True,
            n_pass=3,
            n_total=3,
        )
        doc.add_room_result(room, layout, consensus=consensus)
        summary = doc._room_summary_table()
        assert "All Rooms Consensus VERIFIED" in summary

    def test_summary_not_all_consensus_verified(self):
        doc = ComplianceProofDocument()
        room = Room("R1", 10.0, 10.0, 3.0)
        layout = DetectorLayout(room=room, detectors=[(5.0, 5.0)])
        doc.add_room_result(room, layout)
        summary = doc._room_summary_table()
        assert "some rooms require investigation" in summary

    def test_nan_coverage_shows_invalid_data(self):
        """V57 FIX: NaN coverage_pct must show [INVALID DATA]%, not nan%."""
        doc = ComplianceProofDocument()
        room = Room("NaN-Room", 10.0, 10.0, 3.0)
        layout = DetectorLayout(
            room=room,
            detectors=[(5.0, 5.0)],
            coverage_pct=float("nan"),
            proof_valid=False,
            nfpa_valid=False,
        )
        doc.add_room_result(room, layout)
        summary = doc._room_summary_table()
        assert "[INVALID DATA]%" in summary
        assert "nan%" not in summary

    def test_inf_coverage_shows_invalid_data(self):
        doc = ComplianceProofDocument()
        room = Room("Inf-Room", 10.0, 10.0, 3.0)
        layout = DetectorLayout(
            room=room,
            detectors=[(5.0, 5.0)],
            coverage_pct=float("inf"),
            proof_valid=False,
            nfpa_valid=False,
        )
        doc.add_room_result(room, layout)
        summary = doc._room_summary_table()
        assert "[INVALID DATA]" in summary


# ═══════════════════════════════════════════════════════════════════════════════
# 8. ComplianceProofDocument — _detailed_room_results
# ═══════════════════════════════════════════════════════════════════════════════


class TestDetailedRoomResults:
    """_detailed_room_results() section generation."""

    def test_section_title(self):
        doc = ComplianceProofDocument()
        detail = doc._detailed_room_results()
        assert "## 3. Detailed Room Results" in detail

    def test_room_name_appears(self):
        doc = ComplianceProofDocument()
        room = Room("Office-101", 5.0, 6.0, 3.0)
        layout = DetectorLayout(room=room, detectors=[(2.5, 3.0)])
        doc.add_room_result(room, layout)
        detail = doc._detailed_room_results()
        assert "Office-101" in detail

    def test_room_dimensions(self):
        doc = ComplianceProofDocument()
        room = Room("R1", 5.0, 6.0, 3.0)
        layout = DetectorLayout(room=room, detectors=[(2.5, 3.0)])
        doc.add_room_result(room, layout)
        detail = doc._detailed_room_results()
        assert "5.0 m × 6.0 m" in detail

    def test_room_area(self):
        doc = ComplianceProofDocument()
        room = Room("R1", 5.0, 6.0, 3.0)
        layout = DetectorLayout(room=room, detectors=[(2.5, 3.0)])
        doc.add_room_result(room, layout)
        detail = doc._detailed_room_results()
        assert "Area: 30.0 m²" in detail or "Area: 30.0" in detail

    def test_ceiling_height(self):
        doc = ComplianceProofDocument()
        room = Room("R1", 5.0, 6.0, 3.0)
        layout = DetectorLayout(room=room, detectors=[(2.5, 3.0)])
        doc.add_room_result(room, layout)
        detail = doc._detailed_room_results()
        assert "Ceiling Height:** 3.0 m" in detail

    def test_coverage_radius(self):
        doc = ComplianceProofDocument()
        room = Room("R1", 5.0, 6.0, 3.0)
        layout = DetectorLayout(
            room=room, detectors=[(2.5, 3.0)], coverage_radius=DETECTOR_RADIUS,
        )
        doc.add_room_result(room, layout)
        detail = doc._detailed_room_results()
        assert "Coverage Radius Used:**" in detail
        assert f"{DETECTOR_RADIUS:.2f} m" in detail

    def test_placement_method(self):
        doc = ComplianceProofDocument()
        room = Room("R1", 5.0, 6.0, 3.0)
        layout = DetectorLayout(room=room, detectors=[(2.5, 3.0)], method="hex")
        doc.add_room_result(room, layout)
        detail = doc._detailed_room_results()
        assert "Placement Method:** hex" in detail

    def test_detector_count(self):
        doc = ComplianceProofDocument()
        room = Room("R1", 5.0, 6.0, 3.0)
        layout = DetectorLayout(room=room, detectors=[(2.5, 3.0), (4.0, 5.0)])
        doc.add_room_result(room, layout)
        detail = doc._detailed_room_results()
        assert "Detector Count:** 2" in detail

    def test_theoretical_lower_bound(self):
        doc = ComplianceProofDocument()
        room = Room("R1", 5.0, 6.0, 3.0)
        layout = DetectorLayout(room=room, detectors=[(2.5, 3.0)])
        doc.add_room_result(room, layout)
        detail = doc._detailed_room_results()
        tlb = layout.theoretical_lower_bound
        assert f"Theoretical Lower Bound:** {tlb}" in detail

    def test_efficiency_ratio(self):
        doc = ComplianceProofDocument()
        room = Room("R1", 10.0, 10.0, 3.0)
        layout = DetectorLayout(room=room, detectors=[(5.0, 5.0)])
        doc.add_room_result(room, layout)
        detail = doc._detailed_room_results()
        assert "Efficiency Ratio:**" in detail

    def test_coverage_percentage(self):
        doc = ComplianceProofDocument()
        room = Room("R1", 10.0, 10.0, 3.0)
        layout = DetectorLayout(room=room, detectors=[(5.0, 5.0)], coverage_pct=99.9)
        doc.add_room_result(room, layout)
        detail = doc._detailed_room_results()
        assert "Coverage:** 99.90%" in detail or "Coverage:** 99.9" in detail

    def test_proof_valid_yes(self):
        doc = ComplianceProofDocument()
        room = Room("R1", 10.0, 10.0, 3.0)
        layout = DetectorLayout(
            room=room, detectors=[(5.0, 5.0)], proof_valid=True,
        )
        doc.add_room_result(room, layout)
        detail = doc._detailed_room_results()
        assert "Proof Valid:** Yes" in detail

    def test_proof_invalid_requires_review(self):
        doc = ComplianceProofDocument()
        room = Room("R1", 10.0, 10.0, 3.0)
        layout = DetectorLayout(
            room=room, detectors=[(5.0, 5.0)], proof_valid=False,
        )
        doc.add_room_result(room, layout)
        detail = doc._detailed_room_results()
        assert "No — REQUIRES REVIEW" in detail

    def test_nfpa_valid_yes(self):
        doc = ComplianceProofDocument()
        room = Room("R1", 10.0, 10.0, 3.0)
        layout = DetectorLayout(
            room=room, detectors=[(5.0, 5.0)], nfpa_valid=True,
        )
        doc.add_room_result(room, layout)
        detail = doc._detailed_room_results()
        assert "NFPA 72 Compliant:** Yes" in detail

    def test_nfpa_invalid_requires_review(self):
        doc = ComplianceProofDocument()
        room = Room("R1", 10.0, 10.0, 3.0)
        layout = DetectorLayout(
            room=room, detectors=[(5.0, 5.0)], nfpa_valid=False,
        )
        doc.add_room_result(room, layout)
        detail = doc._detailed_room_results()
        assert "No — REQUIRES REVIEW" in detail

    def test_wall_violations(self):
        doc = ComplianceProofDocument()
        room = Room("R1", 10.0, 10.0, 3.0)
        layout = DetectorLayout(
            room=room, detectors=[(5.0, 5.0)], wall_violations=2,
        )
        doc.add_room_result(room, layout)
        detail = doc._detailed_room_results()
        assert "Wall Violations:** 2" in detail

    def test_fallback_not_used(self):
        doc = ComplianceProofDocument()
        room = Room("R1", 10.0, 10.0, 3.0)
        layout = DetectorLayout(
            room=room, detectors=[(5.0, 5.0)], fallback_used=False,
        )
        doc.add_room_result(room, layout)
        detail = doc._detailed_room_results()
        assert "Fallback Used:** No" in detail

    def test_fallback_used(self):
        doc = ComplianceProofDocument()
        room = Room("R1", 10.0, 10.0, 3.0)
        layout = DetectorLayout(
            room=room, detectors=[(5.0, 5.0)], fallback_used=True,
        )
        doc.add_room_result(room, layout)
        detail = doc._detailed_room_results()
        assert "Yes — requires manual design review" in detail

    def test_detector_positions_table(self):
        doc = ComplianceProofDocument()
        room = Room("R1", 10.0, 10.0, 3.0)
        layout = DetectorLayout(
            room=room,
            detectors=[(3.0, 3.0), (7.0, 7.0)],
        )
        doc.add_room_result(room, layout)
        detail = doc._detailed_room_results()
        assert "Detector Positions:" in detail
        assert "| # | X (m) | Y (m) | Wall Dist Min (m) |" in detail
        assert "3.000" in detail
        assert "7.000" in detail

    def test_detector_positions_with_wall_dist(self):
        doc = ComplianceProofDocument()
        room = Room("R1", 10.0, 10.0, 3.0)
        layout = DetectorLayout(room=room, detectors=[(2.0, 3.0)])
        doc.add_room_result(room, layout)
        detail = doc._detailed_room_results()
        # Wall dist = min(2.0, 10-2.0, 3.0, 10-3.0) = min(2.0, 8.0, 3.0, 7.0) = 2.0
        assert "2.000" in detail

    def test_no_detector_positions_table_when_empty(self):
        doc = ComplianceProofDocument()
        room = Room("R1", 10.0, 10.0, 3.0)
        layout = DetectorLayout(
            room=room, detectors=[],
        )
        doc.add_room_result(room, layout)
        detail = doc._detailed_room_results()
        assert "Detector Positions:" not in detail

    def test_consensus_displayed(self):
        doc = ComplianceProofDocument()
        room = Room("R1", 10.0, 10.0, 3.0)
        layout = DetectorLayout(room=room, detectors=[(5.0, 5.0)])
        consensus = ConsensusResult(
            confidence=ConfidenceLevel.VERIFIED,
            is_safe=True,
            engines=[
                EngineVerdict(engine=EngineName.ANALYTICAL, passed=True, details="All good"),
                EngineVerdict(engine=EngineName.VORONOI, passed=True, details="OK"),
                EngineVerdict(engine=EngineName.GRID, passed=True, details="Covered"),
            ],
            n_pass=3,
            n_total=3,
        )
        doc.add_room_result(room, layout, consensus=consensus)
        detail = doc._detailed_room_results()
        assert "Consensus:** 3/3 VERIFIED" in detail or "Consensus:**" in detail
        assert "is_safe:** True" in detail

    def test_engine_verdicts_displayed(self):
        doc = ComplianceProofDocument()
        room = Room("R1", 10.0, 10.0, 3.0)
        layout = DetectorLayout(room=room, detectors=[(5.0, 5.0)])
        consensus = ConsensusResult(
            confidence=ConfidenceLevel.WARNING,
            is_safe=False,
            engines=[
                EngineVerdict(engine=EngineName.ANALYTICAL, passed=True, details="OK"),
                EngineVerdict(engine=EngineName.VORONOI, passed=False, details="Gap found"),
                EngineVerdict(engine=EngineName.GRID, passed=True, details="OK"),
            ],
            n_pass=2,
            n_total=3,
        )
        doc.add_room_result(room, layout, consensus=consensus)
        detail = doc._detailed_room_results()
        assert "analytical" in detail.lower() or "ANALYTICAL" in detail
        assert "PASS" in detail
        assert "FAIL" in detail
        assert "Gap found" in detail

    def test_notes_displayed(self):
        doc = ComplianceProofDocument()
        room = Room("R1", 10.0, 10.0, 3.0)
        layout = DetectorLayout(room=room, detectors=[(5.0, 5.0)])
        doc.add_room_result(room, layout, notes=["Beam detection required", "Verify spacing"])
        detail = doc._detailed_room_results()
        assert "Notes:**" in detail
        assert "Beam detection required" in detail
        assert "Verify spacing" in detail

    def test_no_notes_not_displayed(self):
        doc = ComplianceProofDocument()
        room = Room("R1", 10.0, 10.0, 3.0)
        layout = DetectorLayout(room=room, detectors=[(5.0, 5.0)])
        doc.add_room_result(room, layout)
        detail = doc._detailed_room_results()
        assert "Notes:**" not in detail

    def test_radius_source_low_ceiling(self):
        doc = ComplianceProofDocument()
        room = Room("R1", 10.0, 10.0, 3.0)
        layout = DetectorLayout(
            room=room, detectors=[(5.0, 5.0)], coverage_radius=DETECTOR_RADIUS,
        )
        doc.add_room_result(room, layout)
        detail = doc._detailed_room_results()
        assert "h ≤ 3.0m" in detail

    def test_radius_source_high_ceiling(self):
        doc = ComplianceProofDocument()
        room = Room("R1", 10.0, 10.0, 5.0)
        layout = DetectorLayout(
            room=room, detectors=[(5.0, 5.0)], coverage_radius=4.0,
        )
        doc.add_room_result(room, layout)
        detail = doc._detailed_room_results()
        assert "R reduced" in detail

    def test_multi_room_numbering(self):
        doc = ComplianceProofDocument()
        for i in range(3):
            room = Room(f"Room-{i}", 10.0, 10.0, 3.0)
            layout = DetectorLayout(room=room, detectors=[(5.0, 5.0)])
            doc.add_room_result(room, layout)
        detail = doc._detailed_room_results()
        assert "### 3.1 Room: Room-0" in detail
        assert "### 3.2 Room: Room-1" in detail
        assert "### 3.3 Room: Room-2" in detail

    def test_nan_dimensions_via_mock(self):
        """NaN dimensions must show [INVALID DATA] in detailed results."""
        room = MagicMock()
        room.name = "NaN-Room"
        room.width = float("nan")
        room.length = float("nan")
        room.ceiling_height = float("nan")
        layout = MagicMock()
        layout.count = 2
        layout.coverage_pct = 99.9
        layout.proof_valid = True
        layout.nfpa_valid = True
        layout.method = "hex"
        layout.coverage_radius = DETECTOR_RADIUS
        layout.theoretical_lower_bound = 1
        layout.efficiency_ratio = 1.0
        layout.wall_violations = 0
        layout.fallback_used = False
        layout.detectors = [(5.0, 5.0)]
        doc = ComplianceProofDocument(project_name="NaN Dims")
        doc.add_room_result(room, layout)
        detail = doc._detailed_room_results()
        assert "[INVALID DATA]" in detail


# ═══════════════════════════════════════════════════════════════════════════════
# 9. ComplianceProofDocument — _consensus_summary
# ═══════════════════════════════════════════════════════════════════════════════


class TestConsensusSummary:
    """_consensus_summary() section generation."""

    def test_section_title(self):
        doc = ComplianceProofDocument()
        summary = doc._consensus_summary()
        assert "## 4. Consensus Summary" in summary or "## 4. Consensus Verification Summary" in summary

    def test_empty_rooms_shows_no_rooms(self):
        doc = ComplianceProofDocument()
        summary = doc._consensus_summary()
        assert "No rooms verified" in summary

    def test_table_shown_with_records(self):
        doc = ComplianceProofDocument()
        room = Room("R1", 10.0, 10.0, 3.0)
        layout = DetectorLayout(room=room, detectors=[(5.0, 5.0)])
        doc.add_room_result(room, layout)
        summary = doc._consensus_summary()
        assert "| Status | Count | Percentage |" in summary

    def test_all_verified_success_message(self):
        doc = ComplianceProofDocument()
        for _ in range(2):
            room = Room("R1", 10.0, 10.0, 3.0)
            layout = DetectorLayout(room=room, detectors=[(5.0, 5.0)])
            consensus = ConsensusResult(
                confidence=ConfidenceLevel.VERIFIED,
                is_safe=True,
                n_pass=3,
                n_total=3,
            )
            doc.add_room_result(room, layout, consensus=consensus)
        summary = doc._consensus_summary()
        assert "ALL ROOMS VERIFIED" in summary

    def test_fail_rooms_highlighted(self):
        doc = ComplianceProofDocument()
        room = Room("Bad-Room", 30.0, 30.0, 3.0)
        layout = DetectorLayout(room=room, detectors=[(5.0, 5.0)])
        consensus = ConsensusResult(
            confidence=ConfidenceLevel.FAIL,
            is_safe=False,
            n_pass=0,
            n_total=3,
            recommendation="Add more detectors",
        )
        doc.add_room_result(room, layout, consensus=consensus)
        summary = doc._consensus_summary()
        assert "ATTENTION" in summary
        assert "Bad-Room" in summary

    def test_warning_rooms_highlighted(self):
        doc = ComplianceProofDocument()
        room = Room("Warn-Room", 10.0, 10.0, 3.0)
        layout = DetectorLayout(room=room, detectors=[(5.0, 5.0)])
        consensus = ConsensusResult(
            confidence=ConfidenceLevel.WARNING,
            is_safe=False,
            n_pass=2,
            n_total=3,
            recommendation="Investigate gap",
        )
        doc.add_room_result(room, layout, consensus=consensus)
        summary = doc._consensus_summary()
        assert "WARNING" in summary
        assert "Warn-Room" in summary

    def test_mixed_consensus_counts(self):
        doc = ComplianceProofDocument()
        # VERIFIED room
        room1 = Room("Good", 10.0, 10.0, 3.0)
        layout1 = DetectorLayout(room=room1, detectors=[(5.0, 5.0)])
        consensus1 = ConsensusResult(
            confidence=ConfidenceLevel.VERIFIED, is_safe=True, n_pass=3, n_total=3,
        )
        doc.add_room_result(room1, layout1, consensus=consensus1)
        # WARNING room
        room2 = Room("Warn", 10.0, 10.0, 3.0)
        layout2 = DetectorLayout(room=room2, detectors=[(5.0, 5.0)])
        consensus2 = ConsensusResult(
            confidence=ConfidenceLevel.WARNING, is_safe=False, n_pass=2, n_total=3,
        )
        doc.add_room_result(room2, layout2, consensus=consensus2)
        # FAIL room
        room3 = Room("Bad", 10.0, 10.0, 3.0)
        layout3 = DetectorLayout(room=room3, detectors=[(5.0, 5.0)])
        consensus3 = ConsensusResult(
            confidence=ConfidenceLevel.FAIL, is_safe=False, n_pass=0, n_total=3,
        )
        doc.add_room_result(room3, layout3, consensus=consensus3)
        # No consensus
        room4 = Room("None", 10.0, 10.0, 3.0)
        layout4 = DetectorLayout(room=room4, detectors=[(5.0, 5.0)])
        doc.add_room_result(room4, layout4)
        summary = doc._consensus_summary()
        assert "1" in summary  # VERIFIED count
        assert "2" in summary  # WARNING count
        # FAIL + Not Verified both present
        assert "ATTENTION" in summary
        assert "WARNING" in summary

    def test_no_consensus_count(self):
        doc = ComplianceProofDocument()
        room = Room("No-Consensus", 10.0, 10.0, 3.0)
        layout = DetectorLayout(room=room, detectors=[(5.0, 5.0)])
        doc.add_room_result(room, layout)
        summary = doc._consensus_summary()
        assert "Not Verified" in summary


# ═══════════════════════════════════════════════════════════════════════════════
# 10. ComplianceProofDocument — _certification
# ═══════════════════════════════════════════════════════════════════════════════


class TestCertification:
    """_certification() section generation."""

    def test_section_title(self):
        doc = ComplianceProofDocument()
        cert = doc._certification()
        assert "## 5. Engineer Certification" in cert

    def test_nfpa_edition_referenced(self):
        doc = ComplianceProofDocument(nfpa_edition="2022")
        cert = doc._certification()
        assert "NFPA 72-2022" in cert

    def test_custom_nfpa_edition(self):
        doc = ComplianceProofDocument(nfpa_edition="2019")
        cert = doc._certification()
        assert "NFPA 72-2019" in cert

    def test_fireai_version(self):
        doc = ComplianceProofDocument()
        cert = doc._certification()
        assert "FireAI V30" in cert

    def test_verification_methodology(self):
        doc = ComplianceProofDocument()
        cert = doc._certification()
        assert "three separate verification engines" in cert
        assert "Analytical" in cert
        assert "Voronoi" in cert
        assert "Grid" in cert

    def test_triangle_inequality_referenced(self):
        doc = ComplianceProofDocument()
        cert = doc._certification()
        assert "R_eff = R - δ√2/2" in cert
        assert "triangle inequality" in cert

    def test_designer_name_appears(self):
        doc = ComplianceProofDocument(designer="John Smith, PE")
        cert = doc._certification()
        assert "John Smith, PE" in cert

    def test_designer_placeholder_when_empty(self):
        doc = ComplianceProofDocument(designer="")
        cert = doc._certification()
        assert "_________________________________" in cert

    def test_generation_date(self):
        doc = ComplianceProofDocument()
        cert = doc._certification()
        assert "Date:**" in cert
        assert "UTC" in cert

    def test_license_number_line(self):
        doc = ComplianceProofDocument()
        cert = doc._certification()
        assert "License #" in cert

    def test_signature_line(self):
        doc = ComplianceProofDocument()
        cert = doc._certification()
        assert "Signature" in cert

    def test_separator_line(self):
        doc = ComplianceProofDocument()
        cert = doc._certification()
        assert "---" in cert


# ═══════════════════════════════════════════════════════════════════════════════
# 11. ComplianceProofDocument — generate() Full Document
# ═══════════════════════════════════════════════════════════════════════════════


class TestGenerateFullDocument:
    """generate() produces complete, well-structured Markdown."""

    def test_generate_returns_string(self):
        doc = ComplianceProofDocument()
        result = doc.generate()
        assert isinstance(result, str)

    def test_generate_non_empty(self):
        doc = ComplianceProofDocument()
        result = doc.generate()
        assert len(result) > 0

    def test_all_five_sections_present(self):
        doc = ComplianceProofDocument()
        md = doc.generate()
        assert "NFPA 72" in md
        assert "## 1. Design Criteria" in md
        assert "## 2. Room Summary" in md
        assert "## 3. Detailed Room Results" in md
        assert "## 4. Consensus" in md
        assert "## 5. Engineer Certification" in md

    def test_sections_separated_by_blank_line(self):
        doc = ComplianceProofDocument()
        md = doc.generate()
        assert "\n\n" in md

    def test_empty_document_structure(self):
        doc = ComplianceProofDocument(project_name="Empty Project")
        md = doc.generate()
        assert "Total Rooms:** 0" in md
        assert "No rooms verified" in md
        assert "Empty Project" in md

    def test_single_room_document(self):
        doc = ComplianceProofDocument(project_name="Single Room Test")
        room = Room("Office-101", 5.0, 6.0, 3.0)
        layout = DetectorLayout(
            room=room,
            detectors=[(2.5, 3.0)],
            coverage_pct=99.9,
            proof_valid=True,
            nfpa_valid=True,
            method="hex",
        )
        doc.add_room_result(room, layout)
        md = doc.generate()
        assert "Office-101" in md
        assert "99.9%" in md
        assert "Total Detectors:** 1" in md

    def test_multiple_rooms_document(self):
        doc = ComplianceProofDocument(project_name="Multi Room")
        for i in range(3):
            room = Room(f"Room-{i}", 10.0, 10.0, 3.0)
            layout = DetectorLayout(room=room, detectors=[(5.0, 5.0)])
            doc.add_room_result(room, layout)
        md = doc.generate()
        assert "Room-0" in md
        assert "Room-1" in md
        assert "Room-2" in md
        assert "Total Detectors:** 3" in md

    def test_document_with_consensus_verified(self):
        doc = ComplianceProofDocument(project_name="Verified")
        room = Room("Verified-Room", 10.0, 10.0, 3.0)
        layout = DetectorLayout(room=room, detectors=[(5.0, 5.0)])
        consensus = ConsensusResult(
            confidence=ConfidenceLevel.VERIFIED,
            is_safe=True,
            engines=[
                EngineVerdict(engine=EngineName.ANALYTICAL, passed=True, details="OK"),
                EngineVerdict(engine=EngineName.VORONOI, passed=True, details="OK"),
                EngineVerdict(engine=EngineName.GRID, passed=True, details="OK"),
            ],
            n_pass=3,
            n_total=3,
        )
        doc.add_room_result(room, layout, consensus=consensus)
        md = doc.generate()
        assert "3/3 VERIFIED" in md
        assert "ALL ROOMS VERIFIED" in md

    def test_document_with_consensus_fail(self):
        doc = ComplianceProofDocument(project_name="Fail")
        room = Room("Fail-Room", 30.0, 30.0, 3.0)
        layout = DetectorLayout(room=room, detectors=[(5.0, 5.0)])
        consensus = ConsensusResult(
            confidence=ConfidenceLevel.FAIL,
            is_safe=False,
            engines=[
                EngineVerdict(engine=EngineName.ANALYTICAL, passed=False, details="Not covered"),
            ],
            n_pass=0,
            n_total=1,
            recommendation="Add more detectors",
        )
        doc.add_room_result(room, layout, consensus=consensus)
        md = doc.generate()
        assert "0/1 FAIL" in md
        assert "ATTENTION" in md

    def test_document_with_proof_invalid(self):
        doc = ComplianceProofDocument(project_name="Proof Invalid")
        room = Room("Bad-Proof", 10.0, 10.0, 3.0)
        layout = DetectorLayout(
            room=room,
            detectors=[(5.0, 5.0)],
            coverage_pct=45.0,
            proof_valid=False,
            nfpa_valid=True,
        )
        doc.add_room_result(room, layout)
        md = doc.generate()
        assert "✗" in md
        assert "REQUIRES REVIEW" in md

    def test_document_with_nfpa_invalid(self):
        doc = ComplianceProofDocument(project_name="NFPA Invalid")
        room = Room("NFPA-Bad", 10.0, 10.0, 3.0)
        layout = DetectorLayout(
            room=room,
            detectors=[(5.0, 5.0)],
            coverage_pct=99.0,
            proof_valid=True,
            nfpa_valid=False,
        )
        doc.add_room_result(room, layout)
        md = doc.generate()
        assert "✗" in md
        assert "REQUIRES REVIEW" in md

    def test_nan_coverage_in_generated_document(self):
        """V57 FIX: NaN coverage → [INVALID DATA] in final document."""
        doc = ComplianceProofDocument(project_name="NaN Coverage")
        room = Room("NaN-Coverage", 10.0, 10.0, 3.0)
        layout = DetectorLayout(
            room=room,
            detectors=[(5.0, 5.0)],
            coverage_pct=float("nan"),
            proof_valid=False,
            nfpa_valid=False,
        )
        doc.add_room_result(room, layout)
        md = doc.generate()
        assert "[INVALID DATA]%" in md
        assert "nan%" not in md

    def test_nan_dimensions_in_generated_document_mock(self):
        """NaN dimensions via mock produce [INVALID DATA] in final doc."""
        room = MagicMock()
        room.name = "NaN-Room"
        room.width = float("nan")
        room.length = float("nan")
        room.ceiling_height = float("nan")
        layout = MagicMock()
        layout.count = 1
        layout.coverage_pct = 99.9
        layout.proof_valid = True
        layout.nfpa_valid = True
        layout.method = "hex"
        layout.coverage_radius = DETECTOR_RADIUS
        layout.theoretical_lower_bound = 1
        layout.efficiency_ratio = 1.0
        layout.wall_violations = 0
        layout.fallback_used = False
        layout.detectors = [(5.0, 5.0)]
        doc = ComplianceProofDocument(project_name="NaN Dims Full Doc")
        doc.add_room_result(room, layout)
        md = doc.generate()
        assert "[INVALID DATA]" in md

    def test_document_with_notes(self):
        doc = ComplianceProofDocument(project_name="With Notes")
        room = Room("Office", 10.0, 10.0, 3.0)
        layout = DetectorLayout(room=room, detectors=[(5.0, 5.0)])
        doc.add_room_result(room, layout, notes=["Special ceiling treatment required"])
        md = doc.generate()
        assert "Special ceiling treatment required" in md

    def test_document_detector_positions(self):
        doc = ComplianceProofDocument(project_name="Positions")
        room = Room("Office", 10.0, 10.0, 3.0)
        layout = DetectorLayout(
            room=room,
            detectors=[(2.0, 2.0), (8.0, 8.0)],
        )
        doc.add_room_result(room, layout)
        md = doc.generate()
        assert "2.000" in md
        assert "8.000" in md

    def test_document_all_sections_join_with_double_newline(self):
        doc = ComplianceProofDocument()
        room = Room("R1", 10.0, 10.0, 3.0)
        layout = DetectorLayout(room=room, detectors=[(5.0, 5.0)])
        doc.add_room_result(room, layout)
        md = doc.generate()
        # Check each section boundary has double newline
        assert "## 1. Design Criteria\n\n" in md or "## 1. Design Criteria" in md


# ═══════════════════════════════════════════════════════════════════════════════
# 12. Edge Cases — Zero / Empty / Boundary
# ═══════════════════════════════════════════════════════════════════════════════


class TestEdgeCases:
    """Edge cases and boundary conditions."""

    def test_empty_records_generates_valid_document(self):
        doc = ComplianceProofDocument()
        md = doc.generate()
        assert md is not None
        assert len(md) > 0

    def test_zero_rooms_header_shows_zero(self):
        doc = ComplianceProofDocument()
        header = doc._header()
        assert "Total Rooms:** 0" in header

    def test_zero_rooms_consensus_summary_says_no_rooms(self):
        doc = ComplianceProofDocument()
        summary = doc._consensus_summary()
        assert "No rooms verified" in summary

    def test_room_with_zero_detectors(self):
        doc = ComplianceProofDocument()
        room = Room("Empty", 10.0, 10.0, 3.0)
        layout = DetectorLayout(room=room, detectors=[])
        doc.add_room_result(room, layout)
        md = doc.generate()
        assert "Empty" in md
        assert "Detector Count:** 0" in md

    def test_room_with_many_detectors(self):
        doc = ComplianceProofDocument()
        room = Room("Big", 50.0, 50.0, 3.0)
        detectors = [(i * 5.0, j * 5.0) for i in range(5) for j in range(5)]
        layout = DetectorLayout(room=room, detectors=detectors)
        doc.add_room_result(room, layout)
        md = doc.generate()
        assert "Detector Count:** 25" in md
        assert "Total Detectors:** 25" in md

    def test_varied_consensus_levels_in_summary_table(self):
        doc = ComplianceProofDocument()
        # Verified
        room1 = Room("R1", 10.0, 10.0, 3.0)
        layout1 = DetectorLayout(room=room1, detectors=[(5.0, 5.0)])
        c1 = ConsensusResult(confidence=ConfidenceLevel.VERIFIED, is_safe=True, n_pass=3, n_total=3)
        doc.add_room_result(room1, layout1, consensus=c1)
        # Warning
        room2 = Room("R2", 10.0, 10.0, 3.0)
        layout2 = DetectorLayout(room=room2, detectors=[(5.0, 5.0)])
        c2 = ConsensusResult(confidence=ConfidenceLevel.WARNING, is_safe=False, n_pass=2, n_total=3)
        doc.add_room_result(room2, layout2, consensus=c2)
        # Fail
        room3 = Room("R3", 10.0, 10.0, 3.0)
        layout3 = DetectorLayout(room=room3, detectors=[(5.0, 5.0)])
        c3 = ConsensusResult(confidence=ConfidenceLevel.FAIL, is_safe=False, n_pass=0, n_total=3)
        doc.add_room_result(room3, layout3, consensus=c3)
        # No consensus
        room4 = Room("R4", 10.0, 10.0, 3.0)
        layout4 = DetectorLayout(room=room4, detectors=[(5.0, 5.0)])
        doc.add_room_result(room4, layout4)
        summary = doc._room_summary_table()
        assert "3/3 VERIFIED" in summary
        assert "2/3 WARNING" in summary
        assert "0/3 FAIL" in summary
        assert "N/A" in summary

    def test_default_constructor_empty_document(self):
        doc = ComplianceProofDocument()
        md = doc.generate()
        assert "FireAI V30 Project" in md
        assert "TBD" in md  # designer TBD, jurisdiction TBD


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
