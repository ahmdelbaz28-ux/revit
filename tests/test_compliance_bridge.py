"""
FireAI Rules Engine — Integration Bridge Tests
=================================================

Tests the high-level NFPA72ComplianceChecker API and the
compliance_bridge module that connects the rules engine
to the existing FireAI system.
"""

from __future__ import annotations

import pytest

from fireai.core.rules_engine.compliance_bridge import (
    NFPA72ComplianceChecker,
    ComplianceReport,
    room_to_facts,
    detector_to_fact,
    hvac_to_fact,
    elevator_to_fact,
    results_to_report,
)
from fireai.core.rules_engine.engine import (
    Fact,
    RulesEngine,
    RulePriority,
)
from fireai.core.rules_engine.nfpa72_rules import NFPA72RuleSet


class TestNFPA72ComplianceChecker:
    """Test the high-level compliance checker API."""

    def test_basic_room_analysis(self):
        checker = NFPA72ComplianceChecker(session_id="test-room-001")
        checker.add_room("R1", ceiling_height_m=3.0, detector_type="smoke")
        report = checker.evaluate()

        assert isinstance(report, ComplianceReport)
        assert report.session_id == "test-room-001"

    def test_room_with_high_ceiling_is_unsafe(self):
        checker = NFPA72ComplianceChecker()
        checker.add_room("R-TALL", ceiling_height_m=15.0, detector_type="smoke")
        report = checker.evaluate()

        assert not report.is_safe
        assert len(report.critical_issues) >= 1
        assert any(
            "AHJ" in issue["message"] or "exceeds" in issue["message"]
            for issue in report.critical_issues
        )

    def test_room_with_normal_ceiling_is_compliant(self):
        checker = NFPA72ComplianceChecker()
        checker.add_room("R1", ceiling_height_m=3.0, detector_type="smoke")
        report = checker.evaluate()

        # Normal ceiling height should not have critical issues
        # (but may have informational compliance checks)
        assert report.is_safe or len(report.critical_issues) == 0

    def test_dead_air_space_detector(self):
        checker = NFPA72ComplianceChecker()
        checker.add_detector(
            "D1", "R1", "smoke",
            x=5.0, y=5.0,
            distance_to_wall_m=0.05,  # Less than 0.1m
        )
        report = checker.evaluate()

        assert not report.is_safe
        assert any(
            "dead air" in v["message"].lower()
            for v in report.violations
        )

    def test_duct_detector_missing(self):
        checker = NFPA72ComplianceChecker()
        checker.add_hvac("AHU-1", cfm=5000, has_duct_detector=False)
        report = checker.evaluate()

        assert not report.is_safe

    def test_duct_detector_present(self):
        checker = NFPA72ComplianceChecker()
        checker.add_hvac("AHU-2", cfm=5000, has_duct_detector=True)
        report = checker.evaluate()

        # No duct detector violation should exist
        duct_violations = [
            v for v in report.violations
            if v["rule_id"] == "NFPA72-006"
        ]
        assert len(duct_violations) == 0

    def test_elevator_missing_detectors(self):
        checker = NFPA72ComplianceChecker()
        checker.add_elevator("E1", has_lobby_detector=False, has_hoistway_detector=False)
        report = checker.evaluate()

        assert not report.is_safe
        assert any(
            v["rule_id"] == "NFPA72-007"
            for v in report.violations
        )

    def test_elevator_with_all_detectors(self):
        checker = NFPA72ComplianceChecker()
        checker.add_elevator("E2", has_lobby_detector=True, has_hoistway_detector=True)
        report = checker.evaluate()

        # No elevator violation should exist
        elevator_violations = [
            v for v in report.violations
            if v["rule_id"] == "NFPA72-007"
        ]
        assert len(elevator_violations) == 0

    def test_multi_room_analysis(self):
        checker = NFPA72ComplianceChecker()
        checker.add_room("R1", ceiling_height_m=3.0, detector_type="smoke")
        checker.add_room("R2", ceiling_height_m=4.5, detector_type="heat")
        checker.add_hvac("AHU-1", cfm=3000, has_duct_detector=False)
        report = checker.evaluate()

        assert isinstance(report, ComplianceReport)
        assert len(report.compliance_checks) > 0

    def test_audit_log_available(self):
        checker = NFPA72ComplianceChecker()
        checker.add_room("R1", ceiling_height_m=3.0, detector_type="smoke")
        checker.evaluate()

        audit = checker.get_audit_log()
        assert len(audit) > 0

    def test_reset_clears_state(self):
        checker = NFPA72ComplianceChecker()
        checker.add_room("R1", ceiling_height_m=3.0, detector_type="smoke")
        checker.evaluate()

        checker.reset()
        # After reset, adding new room should work cleanly
        checker.add_room("R2", ceiling_height_m=3.0, detector_type="smoke")
        report = checker.evaluate()
        assert isinstance(report, ComplianceReport)

    def test_report_has_nfpa_references(self):
        checker = NFPA72ComplianceChecker()
        checker.add_room("R1", ceiling_height_m=3.0, detector_type="smoke")
        report = checker.evaluate()

        # Report should contain NFPA references
        assert len(report.nfpa_references) > 0 or len(report.compliance_checks) > 0


class TestDataConversion:
    """Test data conversion functions."""

    def test_room_to_facts(self):
        facts = room_to_facts(
            room_id="R1",
            ceiling_height_m=3.0,
            detector_type="smoke",
        )
        assert len(facts) == 1
        assert facts[0].fact_type == "room"
        assert facts[0].properties["ceiling_height_m"] == 3.0

    def test_detector_to_fact(self):
        fact = detector_to_fact(
            detector_id="D1",
            room_id="R1",
            detector_type="smoke",
            x=5.0,
            y=5.0,
            distance_to_wall_m=2.0,
        )
        assert fact.fact_type == "detector"
        assert fact.properties["distance_to_wall_m"] == 2.0

    def test_hvac_to_fact(self):
        fact = hvac_to_fact(
            unit_id="AHU-1",
            cfm=5000,
            has_duct_detector=False,
        )
        assert fact.fact_type == "hvac_unit"
        assert fact.properties["cfm"] == 5000

    def test_elevator_to_fact(self):
        fact = elevator_to_fact(
            elevator_id="E1",
            has_lobby_detector=True,
            has_hoistway_detector=False,
        )
        assert fact.fact_type == "elevator"
        assert fact.properties["has_lobby_detector"] is True
        assert fact.properties["has_hoistway_detector"] is False


class TestComplianceReport:
    """Test the ComplianceReport structure."""

    def test_report_from_engine(self):
        engine = RulesEngine()
        engine.add_rules(NFPA72RuleSet.all_rules())
        engine.assert_fact(Fact(
            fact_type="room",
            properties={
                "room_id": "R1",
                "ceiling_height_m": 3.0,
                "detector_type": "smoke",
            },
        ))
        engine.evaluate()

        report = results_to_report(engine)
        assert isinstance(report, ComplianceReport)
        assert "total_facts" in report.audit_summary
        assert "rules_fired" in report.audit_summary


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
