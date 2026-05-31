"""
tests/test_compliance_proof_document.py
========================================
Comprehensive test suite for fireai/core/compliance_proof_document.py.

SAFETY CRITICAL: Compliance proof documents are submitted to the AHJ
(Authority Having Jurisdiction) for fire alarm system permitting. Errors
could lead to false compliance claims — a direct life-safety hazard.

NFPA 72 References:
  §17.6.3.1.1 — Spot-type smoke detector spacing
  §17.7.4.2.3.1 — Coverage radius R = 0.7 × S
  V57 FIX (Finding 15) — NaN/Inf in AHJ documents replaced with [INVALID DATA]

Key features tested:
  - ComplianceProofDocument generation
  - Room-by-room verification records
  - Consensus engine results (3-engine verification)
  - _safe_fmt for NaN/Inf handling
  - _radius_source for NFPA 72 Table references
  - Markdown output structure and content
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import List, Optional
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
    DetectorLayout,
    Room,
)


# ─────────────────────────────────────────────────────────────────────────────
# _safe_fmt (V57 FIX)
# ─────────────────────────────────────────────────────────────────────────────


class TestSafeFmt:
    """V57 FIX (Finding 15): NaN/Inf in AHJ documents replaced with [INVALID DATA]."""

    def test_normal_float(self):
        assert _safe_fmt(3.14159) == "3.1"

    def test_custom_format(self):
        assert _safe_fmt(3.14159, ".2f") == "3.14"

    def test_integer_value(self):
        assert _safe_fmt(5.0) == "5.0"

    def test_nan_returns_invalid(self):
        assert _safe_fmt(float("nan")) == "[INVALID DATA]"

    def test_inf_returns_invalid(self):
        assert _safe_fmt(float("inf")) == "[INVALID DATA]"

    def test_neg_inf_returns_invalid(self):
        assert _safe_fmt(float("-inf")) == "[INVALID DATA]"

    def test_zero(self):
        assert _safe_fmt(0.0) == "0.0"

    def test_negative(self):
        assert _safe_fmt(-5.5) == "-5.5"

    def test_very_small(self):
        result = _safe_fmt(0.0001, ".4f")
        assert result == "0.0001"

    def test_very_large(self):
        result = _safe_fmt(99999.9)
        assert result == "99999.9"

    def test_percentage_format(self):
        result = _safe_fmt(99.9, ".1f")
        assert result == "99.9"


# ─────────────────────────────────────────────────────────────────────────────
# RoomVerificationRecord
# ─────────────────────────────────────────────────────────────────────────────


class TestRoomVerificationRecord:
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
            room=room, layout=layout, consensus=consensus, notes=["Note 1"]
        )
        assert rec.consensus is consensus
        assert rec.notes == ["Note 1"]


# ─────────────────────────────────────────────────────────────────────────────
# ComplianceProofDocument — Initialization
# ─────────────────────────────────────────────────────────────────────────────


class TestComplianceProofDocumentInit:
    def test_default_values(self):
        doc = ComplianceProofDocument()
        assert doc.project_name == "FireAI V30 Project"
        assert doc.designer == ""
        assert doc.nfpa_edition == "2022"
        assert doc.jurisdiction == ""
        assert doc.records == []

    def test_custom_values(self):
        doc = ComplianceProofDocument(
            project_name="ABC Office Tower",
            designer="Jane Smith, PE #12345",
            nfpa_edition="2022",
            jurisdiction="City of Metropolis",
        )
        assert doc.project_name == "ABC Office Tower"
        assert doc.designer == "Jane Smith, PE #12345"
        assert doc.jurisdiction == "City of Metropolis"

    def test_generation_date_utc(self):
        """V54 FIX (AUDIT-012): Generation date must be timezone-aware UTC."""
        doc = ComplianceProofDocument()
        assert "UTC" in doc.generation_date


# ─────────────────────────────────────────────────────────────────────────────
# ComplianceProofDocument — add_room_result
# ─────────────────────────────────────────────────────────────────────────────


class TestAddRoomResult:
    def test_add_single_room(self):
        doc = ComplianceProofDocument()
        room = Room("Office-101", 10.0, 10.0, 3.0)
        layout = DetectorLayout(room=room, detectors=[(5.0, 5.0)], coverage_pct=99.9)
        doc.add_room_result(room, layout)
        assert len(doc.records) == 1

    def test_add_multiple_rooms(self):
        doc = ComplianceProofDocument()
        for i in range(3):
            room = Room(f"Room-{i}", 10.0, 10.0, 3.0)
            layout = DetectorLayout(room=room, detectors=[(5.0, 5.0)])
            doc.add_room_result(room, layout)
        assert len(doc.records) == 3

    def test_add_with_consensus(self):
        doc = ComplianceProofDocument()
        room = Room("R1", 10.0, 10.0, 3.0)
        layout = DetectorLayout(room=room, detectors=[(5.0, 5.0)])
        consensus = ConsensusResult(
            confidence=ConfidenceLevel.VERIFIED,
            is_safe=True,
            n_pass=3,
            n_total=3,
        )
        doc.add_room_result(room, layout, consensus)
        assert doc.records[0].consensus is consensus

    def test_add_with_notes(self):
        doc = ComplianceProofDocument()
        room = Room("R1", 10.0, 10.0, 3.0)
        layout = DetectorLayout(room=room, detectors=[(5.0, 5.0)])
        doc.add_room_result(room, layout, notes=["Beam detection required"])
        assert doc.records[0].notes == ["Beam detection required"]

    def test_add_without_notes_defaults_empty(self):
        doc = ComplianceProofDocument()
        room = Room("R1", 10.0, 10.0, 3.0)
        layout = DetectorLayout(room=room, detectors=[(5.0, 5.0)])
        doc.add_room_result(room, layout)
        assert doc.records[0].notes == []


# ─────────────────────────────────────────────────────────────────────────────
# ComplianceProofDocument — generate()
# ─────────────────────────────────────────────────────────────────────────────


class TestGenerate:
    def _make_doc_with_room(self, room_name="Office-101", width=10.0, length=10.0,
                            ceiling_height=3.0, coverage_pct=99.9,
                            proof_valid=True, nfpa_valid=True,
                            detector_positions=None, consensus=None):
        doc = ComplianceProofDocument(
            project_name="Test Building",
            designer="Test Engineer, PE",
            nfpa_edition="2022",
            jurisdiction="Test City",
        )
        room = Room(room_name, width, length, ceiling_height)
        layout = DetectorLayout(
            room=room,
            detectors=detector_positions or [(5.0, 5.0)],
            coverage_pct=coverage_pct,
            proof_valid=proof_valid,
            nfpa_valid=nfpa_valid,
            method="hex",
        )
        doc.add_room_result(room, layout, consensus)
        return doc

    def test_generate_returns_string(self):
        doc = self._make_doc_with_room()
        result = doc.generate()
        assert isinstance(result, str)

    def test_generate_contains_header(self):
        doc = self._make_doc_with_room()
        md = doc.generate()
        assert "NFPA 72-2022 Compliance Proof Document" in md
        assert "Test Building" in md
        assert "Test Engineer, PE" in md
        assert "Test City" in md

    def test_generate_contains_design_criteria(self):
        doc = self._make_doc_with_room()
        md = doc.generate()
        assert "## 1. Design Criteria" in md
        assert "§17.6.3.1.1" in md
        assert "§17.7.4.2.3.1" in md
        assert "0.7 × 9.1m = 6.37m" in md

    def test_generate_contains_room_summary(self):
        doc = self._make_doc_with_room()
        md = doc.generate()
        assert "## 2. Room Summary" in md
        assert "Office-101" in md
        assert "Total Detectors" in md

    def test_generate_contains_detailed_results(self):
        doc = self._make_doc_with_room()
        md = doc.generate()
        assert "## 3. Detailed Room Results" in md
        assert "Office-101" in md

    def test_generate_contains_consensus_summary(self):
        doc = self._make_doc_with_room()
        md = doc.generate()
        assert "## 4. Consensus Verification Summary" in md

    def test_generate_contains_certification(self):
        doc = self._make_doc_with_room()
        md = doc.generate()
        assert "## 5. Engineer Certification" in md
        assert "Test Engineer, PE" in md

    def test_generate_empty_records(self):
        """Document with no rooms must still generate valid structure."""
        doc = ComplianceProofDocument(project_name="Empty")
        md = doc.generate()
        assert "NFPA 72-2022 Compliance Proof Document" in md
        assert "Total Rooms:** 0" in md

    def test_generate_proof_valid_markers(self):
        doc = self._make_doc_with_room(proof_valid=True)
        md = doc.generate()
        assert "✓" in md

    def test_generate_proof_invalid_markers(self):
        doc = self._make_doc_with_room(proof_valid=False)
        md = doc.generate()
        assert "✗" in md or "REQUIRES REVIEW" in md

    def test_generate_with_consensus_verified(self):
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
        doc = self._make_doc_with_room(consensus=consensus)
        md = doc.generate()
        assert "3/3 VERIFIED" in md

    def test_generate_with_consensus_warning(self):
        consensus = ConsensusResult(
            confidence=ConfidenceLevel.WARNING,
            is_safe=False,
            engines=[
                EngineVerdict(engine=EngineName.ANALYTICAL, passed=True, details="OK"),
                EngineVerdict(engine=EngineName.VORONOI, passed=True, details="OK"),
                EngineVerdict(engine=EngineName.GRID, passed=False, details="Gap found"),
            ],
            n_pass=2,
            n_total=3,
        )
        doc = self._make_doc_with_room(consensus=consensus)
        md = doc.generate()
        assert "2/3 WARNING" in md

    def test_generate_with_consensus_fail(self):
        consensus = ConsensusResult(
            confidence=ConfidenceLevel.FAIL,
            is_safe=False,
            engines=[
                EngineVerdict(engine=EngineName.ANALYTICAL, passed=False, details="FAIL"),
            ],
            n_pass=0,
            n_total=1,
        )
        doc = self._make_doc_with_room(consensus=consensus)
        md = doc.generate()
        assert "0/1 FAIL" in md

    def test_generate_multiple_rooms(self):
        doc = ComplianceProofDocument(project_name="Multi-Room")
        for i in range(3):
            room = Room(f"Room-{i}", 10.0 + i * 5, 10.0, 3.0)
            layout = DetectorLayout(room=room, detectors=[(5.0, 5.0)])
            doc.add_room_result(room, layout)
        md = doc.generate()
        assert "Room-0" in md
        assert "Room-1" in md
        assert "Room-2" in md

    def test_generate_detector_positions_table(self):
        doc = self._make_doc_with_room(
            detector_positions=[(3.0, 3.0), (7.0, 7.0)]
        )
        md = doc.generate()
        assert "Detector Positions" in md
        assert "3.000" in md
        assert "7.000" in md


# ─────────────────────────────────────────────────────────────────────────────
# ComplianceProofDocument — _radius_source
# ─────────────────────────────────────────────────────────────────────────────


class TestRadiusSource:
    """NFPA 72 Table 17.6.3.1.1 references for different ceiling heights."""

    def test_low_ceiling_3m(self):
        result = ComplianceProofDocument._radius_source(3.0)
        assert "h ≤ 3.0m" in result
        assert "6.37m" in result

    def test_medium_ceiling_3_5m(self):
        result = ComplianceProofDocument._radius_source(3.5)
        assert "3.0" in result and "3.7" in result

    def test_4m_ceiling(self):
        result = ComplianceProofDocument._radius_source(4.0)
        assert "3.7" in result and "4.3" in result

    def test_high_ceiling_5m(self):
        result = ComplianceProofDocument._radius_source(5.0)
        assert "R reduced" in result

    def test_very_high_ceiling(self):
        result = ComplianceProofDocument._radius_source(10.0)
        assert "h=10.0m" in result
        assert "R reduced" in result

    def test_boundary_3_0m(self):
        """Exactly 3.0m — boundary condition."""
        result = ComplianceProofDocument._radius_source(3.0)
        assert "h ≤ 3.0m" in result

    def test_just_above_3_0m(self):
        """Just above 3.0m — different row in Table 17.6.3.1.1."""
        result = ComplianceProofDocument._radius_source(3.01)
        assert "3.0" in result and "3.7" in result


# ─────────────────────────────────────────────────────────────────────────────
# V57 FIX (Finding 15): NaN/Inf in AHJ documents
# ─────────────────────────────────────────────────────────────────────────────


class TestV57SafeFmtInDocument:
    """V57 FIX: NaN/Inf values in AHJ documents replaced with [INVALID DATA].

    NaN values produce 'nan%' in the AHJ submission document, which is
    unacceptable for regulatory filings. Non-finite data indicates a
    calculation error that must be flagged.
    """

    def test_nan_coverage_in_room_summary(self):
        """NaN coverage_pct must show [INVALID DATA], not 'nan%'."""
        doc = ComplianceProofDocument(project_name="NaN Test")
        room = Room("BadRoom", 10.0, 10.0, 3.0)
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

    def test_inf_coverage_in_room_summary(self):
        doc = ComplianceProofDocument(project_name="Inf Test")
        room = Room("InfRoom", 10.0, 10.0, 3.0)
        layout = DetectorLayout(
            room=room,
            detectors=[(5.0, 5.0)],
            coverage_pct=float("inf"),
        )
        doc.add_room_result(room, layout)
        md = doc.generate()
        assert "[INVALID DATA]" in md

    def test_nan_room_dimensions(self):
        """NaN room dimensions in detailed results must show [INVALID DATA]."""
        # We can't create a Room with NaN dimensions (it validates), but
        # we can mock it
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

        doc = ComplianceProofDocument(project_name="NaN Dim Test")
        doc.add_room_result(room, layout)
        md = doc.generate()
        assert "[INVALID DATA]" in md


# ─────────────────────────────────────────────────────────────────────────────
# ComplianceProofDocument — Consensus Summary Edge Cases
# ─────────────────────────────────────────────────────────────────────────────


class TestConsensusSummaryEdgeCases:
    def test_all_verified(self):
        """All rooms VERIFIED → special success message."""
        doc = ComplianceProofDocument(project_name="All Verified")
        for i in range(3):
            room = Room(f"Room-{i}", 10.0, 10.0, 3.0)
            layout = DetectorLayout(room=room, detectors=[(5.0, 5.0)])
            consensus = ConsensusResult(
                confidence=ConfidenceLevel.VERIFIED,
                is_safe=True,
                n_pass=3,
                n_total=3,
            )
            doc.add_room_result(room, layout, consensus)
        md = doc.generate()
        assert "ALL ROOMS VERIFIED" in md

    def test_mixed_consensus_with_fail(self):
        """Rooms with FAIL status must be highlighted."""
        doc = ComplianceProofDocument(project_name="Mixed")
        # One verified room
        room1 = Room("Good-Room", 10.0, 10.0, 3.0)
        layout1 = DetectorLayout(room=room1, detectors=[(5.0, 5.0)])
        consensus1 = ConsensusResult(
            confidence=ConfidenceLevel.VERIFIED, is_safe=True, n_pass=3, n_total=3,
            recommendation="OK",
        )
        doc.add_room_result(room1, layout1, consensus1)

        # One failed room
        room2 = Room("Bad-Room", 30.0, 30.0, 3.0)
        layout2 = DetectorLayout(room=room2, detectors=[(5.0, 5.0)])
        consensus2 = ConsensusResult(
            confidence=ConfidenceLevel.FAIL, is_safe=False, n_pass=0, n_total=3,
            recommendation="Add more detectors",
        )
        doc.add_room_result(room2, layout2, consensus2)

        md = doc.generate()
        assert "FAIL" in md
        assert "ATTENTION" in md or "DO NOT" in md

    def test_no_consensus_rooms(self):
        """Rooms without consensus should show 'Not Verified'."""
        doc = ComplianceProofDocument(project_name="No Consensus")
        room = Room("Room-1", 10.0, 10.0, 3.0)
        layout = DetectorLayout(room=room, detectors=[(5.0, 5.0)])
        doc.add_room_result(room, layout)  # No consensus
        md = doc.generate()
        assert "Not Verified" in md


# ─────────────────────────────────────────────────────────────────────────────
# ComplianceProofDocument — Certification Section
# ─────────────────────────────────────────────────────────────────────────────


class TestCertificationSection:
    def test_certification_contains_nfpa_reference(self):
        doc = ComplianceProofDocument(nfpa_edition="2022")
        md = doc.generate()
        assert "NFPA 72-2022" in md
        assert "FireAI V30" in md

    def test_certification_designer_name(self):
        doc = ComplianceProofDocument(designer="John Smith, PE")
        md = doc.generate()
        assert "John Smith, PE" in md

    def test_certification_designer_tbd(self):
        """When designer is empty, placeholder line must be shown."""
        doc = ComplianceProofDocument(designer="")
        md = doc.generate()
        assert "_________________________________" in md

    def test_certification_contains_signature_line(self):
        doc = ComplianceProofDocument()
        md = doc.generate()
        assert "Signature" in md
        assert "License" in md

    def test_certification_contains_triangle_inequality_proof(self):
        doc = ComplianceProofDocument()
        md = doc.generate()
        assert "R_eff = R - δ√2/2" in md
        assert "triangle inequality" in md.lower()


# ─────────────────────────────────────────────────────────────────────────────
# Integration — Full Document Generation
# ─────────────────────────────────────────────────────────────────────────────


class TestIntegrationFullDocument:
    def test_complete_document_structure(self):
        """Full document must have all 5 sections."""
        doc = ComplianceProofDocument(
            project_name="Integration Test Building",
            designer="Test PE",
            nfpa_edition="2022",
            jurisdiction="Test City",
        )
        # Add a room with full consensus
        room = Room("Office-101", 12.0, 10.0, 3.0)
        layout = DetectorLayout(
            room=room,
            detectors=[(4.0, 3.0), (8.0, 7.0)],
            coverage_pct=99.95,
            proof_valid=True,
            nfpa_valid=True,
            method="hex",
        )
        consensus = ConsensusResult(
            confidence=ConfidenceLevel.VERIFIED,
            is_safe=True,
            engines=[
                EngineVerdict(engine=EngineName.ANALYTICAL, passed=True, details="All corners covered"),
                EngineVerdict(engine=EngineName.VORONOI, passed=True, details="Max gap 4.2m < R"),
                EngineVerdict(engine=EngineName.GRID, passed=True, details="All cells covered"),
            ],
            n_pass=3,
            n_total=3,
        )
        doc.add_room_result(room, layout, consensus, notes=["Standard office layout"])

        md = doc.generate()
        # Verify all 5 sections
        assert "## 1. Design Criteria" in md
        assert "## 2. Room Summary" in md
        assert "## 3. Detailed Room Results" in md
        assert "## 4. Consensus Verification Summary" in md
        assert "## 5. Engineer Certification" in md
        # Verify room details
        assert "Office-101" in md
        assert "3/3 VERIFIED" in md
        assert "Standard office layout" in md

    def test_document_with_no_rooms(self):
        """Empty document must still generate valid structure."""
        doc = ComplianceProofDocument(project_name="Empty Project")
        md = doc.generate()
        assert "Total Rooms:** 0" in md
        assert "No rooms verified" in md


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
