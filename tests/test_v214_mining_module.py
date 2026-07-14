"""
test_v214_mining_module.py — V214 regression tests for the fireai.mining module.

Verifies:
  1. Module imports correctly
  2. MethaneCalculator: classification, layering, dilution
  3. VentilationCalculator: Atkinson equation, MSHA compliance
  4. ConveyorFireAnalyzer: CO classification, suppression design
  5. MSHAComplianceChecker: full compliance report
  6. MethaneDetectorSelector: detector selection + placement
  7. MSHA report generation (markdown + json)
"""

from __future__ import annotations

import pytest


class TestV214MiningModuleExists:
    """V214: fireai.mining module must exist with all subpackages."""

    def test_module_imports(self):
        import fireai.mining
        assert fireai.mining is not None

    def test_core_classes_importable(self):
        from fireai.mining import (
            ConveyorFireAnalyzer,
            MethaneCalculator,
            MSHAComplianceChecker,
            VentilationCalculator,
        )
        assert MethaneCalculator is not None
        assert VentilationCalculator is not None
        assert ConveyorFireAnalyzer is not None
        assert MSHAComplianceChecker is not None


class TestV214MethaneCalculator:
    """V214: MethaneCalculator per NFPA 120 + MSHA §75.323."""

    def test_classify_normal(self):
        from fireai.mining.core.methane_calculator import MethaneCalculator
        assert MethaneCalculator.classify_hazard(0.1) == "normal"

    def test_classify_notify(self):
        from fireai.mining.core.methane_calculator import MethaneCalculator
        assert MethaneCalculator.classify_hazard(0.5) == "notify"

    def test_classify_evacuate_area(self):
        from fireai.mining.core.methane_calculator import MethaneCalculator
        assert MethaneCalculator.classify_hazard(1.0) == "evacuate_area"

    def test_classify_deenergize(self):
        from fireai.mining.core.methane_calculator import MethaneCalculator
        assert MethaneCalculator.classify_hazard(1.5) == "deenergize"

    def test_classify_withdraw_all(self):
        from fireai.mining.core.methane_calculator import MethaneCalculator
        assert MethaneCalculator.classify_hazard(2.0) == "withdraw_all"

    def test_classify_explosive(self):
        from fireai.mining.core.methane_calculator import MethaneCalculator
        assert MethaneCalculator.classify_hazard(5.0) == "explosive"

    def test_is_in_explosive_range(self):
        from fireai.mining.core.methane_calculator import MethaneCalculator
        assert MethaneCalculator.is_in_explosive_range(5.0) is True
        assert MethaneCalculator.is_in_explosive_range(10.0) is True
        assert MethaneCalculator.is_in_explosive_range(15.0) is True
        assert MethaneCalculator.is_in_explosive_range(4.9) is False
        assert MethaneCalculator.is_in_explosive_range(15.1) is False

    def test_layering_analysis(self):
        from fireai.mining.core.methane_calculator import MethaneCalculator
        # Roof = 2%, mid = 1%, floor = 0.5% → stratified
        result = MethaneCalculator.analyze_layering(2.0, 1.0, 0.5)
        assert result.is_stratified is True
        assert result.layering_index > 1.5
        assert result.roof_concentration_pct == 2.0  # NOSONAR: S1244 — float comparison in test

    def test_dilution_airflow(self):
        from fireai.mining.core.methane_calculator import MethaneCalculator
        # Dilute 2% to 1% with current 10 m³/s → need 20 m³/s
        result = MethaneCalculator.dilution_airflow_required(2.0, 1.0, 10.0)
        assert result == 20.0  # NOSONAR: S1244 — float comparison in test


class TestV214VentilationCalculator:
    """V214: VentilationCalculator per Atkinson + MSHA §75.326-327."""

    def test_pressure_drop_atkinson(self):
        from fireai.mining.core.ventilation_calculator import VentilationCalculator
        # ΔP = R × Q² = 0.1 × 10² = 10 Pa
        result = VentilationCalculator.pressure_drop(0.1, 10.0)
        assert result == pytest.approx(10.0, rel=0.01)

    def test_airway_resistance(self):
        from fireai.mining.core.ventilation_calculator import VentilationCalculator
        # R = (K × L × P) / A³ = (0.01 × 100 × 10) / 5³ = 10 / 125 = 0.08
        result = VentilationCalculator.airway_resistance(100.0, 10.0, 5.0)
        assert result == pytest.approx(0.08, rel=0.01)

    def test_msha_compliance_working_face_pass(self):
        from fireai.mining.core.ventilation_calculator import VentilationCalculator
        # 5 m³/s > 1.42 m³/s minimum → compliant
        is_ok, violations = VentilationCalculator.check_msha_compliance(5.0, "working_face")
        assert is_ok is True
        assert violations == []

    def test_msha_compliance_working_face_fail(self):
        from fireai.mining.core.ventilation_calculator import VentilationCalculator
        # 1.0 m³/s < 1.42 m³/s minimum → non-compliant
        is_ok, violations = VentilationCalculator.check_msha_compliance(1.0, "working_face")
        assert is_ok is False
        assert len(violations) > 0

    def test_methane_dilution_airflow(self):
        from fireai.mining.core.ventilation_calculator import VentilationCalculator
        # 0.01 m³/s CH4 → need 1.0 m³/s airflow to keep below 1%
        result = VentilationCalculator.methane_dilution_airflow(0.01, 1.0)
        assert result == pytest.approx(1.0, rel=0.01)


class TestV214ConveyorFireAnalyzer:
    """V214: ConveyorFireAnalyzer per NFPA 120 §8.4."""

    def test_classify_co_normal(self):
        from fireai.mining.core.conveyor_fire import ConveyorFireAnalyzer
        assert ConveyorFireAnalyzer.classify_co_hazard(5.0) == "normal"

    def test_classify_co_alert(self):
        from fireai.mining.core.conveyor_fire import ConveyorFireAnalyzer
        assert ConveyorFireAnalyzer.classify_co_hazard(10.0) == "alert"

    def test_classify_co_evacuate(self):
        from fireai.mining.core.conveyor_fire import ConveyorFireAnalyzer
        assert ConveyorFireAnalyzer.classify_co_hazard(15.0) == "evacuate"

    def test_classify_co_withdraw(self):
        from fireai.mining.core.conveyor_fire import ConveyorFireAnalyzer
        assert ConveyorFireAnalyzer.classify_co_hazard(30.0) == "withdraw"

    def test_classify_co_imminent(self):
        from fireai.mining.core.conveyor_fire import ConveyorFireAnalyzer
        assert ConveyorFireAnalyzer.classify_co_hazard(50.0) == "imminent"

    def test_suppression_design_compliant(self):
        from fireai.mining.core.conveyor_fire import ConveyorFireAnalyzer, ConveyorSpec
        spec = ConveyorSpec(
            belt_length_m=1000.0,
            belt_width_m=1.2,
            belt_speed_m_s=3.0,
            has_fire_resistant_belt=True,
        )
        design = ConveyorFireAnalyzer.design_suppression_system(spec)
        assert design.is_compliant is True
        assert design.number_of_nozzle_groups > 0
        assert design.water_flow_rate_lpm > 0

    def test_suppression_design_non_compliant_no_fire_resistant_belt(self):
        from fireai.mining.core.conveyor_fire import ConveyorFireAnalyzer, ConveyorSpec
        spec = ConveyorSpec(
            belt_length_m=500.0,
            belt_width_m=1.0,
            belt_speed_m_s=2.0,
            has_fire_resistant_belt=False,
        )
        design = ConveyorFireAnalyzer.design_suppression_system(spec)
        assert design.is_compliant is False
        assert len(design.violations) > 0

    def test_fire_spread_rate(self):
        from fireai.mining.core.conveyor_fire import ConveyorFireAnalyzer
        rate = ConveyorFireAnalyzer.estimate_fire_spread_rate(2.0, "fire_resistant")
        # base 0.05 + 2.0 × 0.5 = 1.05
        assert rate == pytest.approx(1.05, rel=0.01)


class TestV214MSHAComplianceChecker:
    """V214: MSHAComplianceChecker full report."""

    def test_full_report_all_pass(self):
        from fireai.mining.core.msha_compliance import MSHAComplianceChecker
        report = MSHAComplianceChecker.full_compliance_report(
            mine_name="Test Mine",
            section_name="Section A",
            methane_pct=0.1,  # normal
            co_ppm=5.0,  # normal
            airflow_m3_s=5.0,  # compliant
            conveyor_length_m=500.0,
            conveyor_width_m=1.2,
            has_fire_resistant_belt=True,
        )
        assert report.overall_status == "PASS"
        # 4 checks: methane + CO + ventilation + conveyor suppression
        assert len(report.checks) == 4

    def test_full_report_no_conveyor(self):
        """Report without conveyor should have 3 checks (no suppression check)."""
        from fireai.mining.core.msha_compliance import MSHAComplianceChecker
        report = MSHAComplianceChecker.full_compliance_report(
            mine_name="Test Mine",
            section_name="Section A",
            methane_pct=0.1,
            co_ppm=5.0,
            airflow_m3_s=5.0,
            conveyor_length_m=0.0,  # No conveyor
        )
        assert report.overall_status == "PASS"
        # 3 checks: methane + CO + ventilation (no conveyor)
        assert len(report.checks) == 3

    def test_full_report_methane_fail(self):
        from fireai.mining.core.msha_compliance import MSHAComplianceChecker
        report = MSHAComplianceChecker.full_compliance_report(
            mine_name="Test Mine",
            section_name="Section A",
            methane_pct=2.0,  # withdraw_all
            co_ppm=5.0,
            airflow_m3_s=5.0,
        )
        assert report.overall_status == "FAIL"

    def test_full_report_co_fail(self):
        from fireai.mining.core.msha_compliance import MSHAComplianceChecker
        report = MSHAComplianceChecker.full_compliance_report(
            mine_name="Test Mine",
            section_name="Section A",
            methane_pct=0.1,
            co_ppm=50.0,  # imminent
            airflow_m3_s=5.0,
        )
        assert report.overall_status == "FAIL"


class TestV214MethaneDetectorSelector:
    """V214: MethaneDetectorSelector."""

    def test_select_catalytic_with_oxygen(self):
        from fireai.mining.detectors.methane_detector import MethaneDetectorSelector
        det = MethaneDetectorSelector.select("working_face", oxygen_available=True)
        assert det.detector_type == "catalytic"

    def test_select_infrared_without_oxygen(self):
        from fireai.mining.detectors.methane_detector import MethaneDetectorSelector
        det = MethaneDetectorSelector.select("working_face", oxygen_available=False)
        assert det.detector_type == "infrared"

    def test_placement_locations(self):
        from fireai.mining.detectors.methane_detector import MethaneDetectorSelector
        locations = MethaneDetectorSelector.placement_locations(
            mine_length_m=600.0,
            has_conveyor=True,
            conveyor_length_m=300.0,
        )
        assert len(locations) > 0
        # Should include working face + main entries + conveyor points
        assert any(l["location"] == "Working face" for l in locations)


class TestV214MSHAReport:
    """V214: MSHA report generation."""

    def test_generate_markdown_report(self):
        from fireai.mining.core.msha_compliance import MSHAComplianceChecker
        from fireai.mining.output.msha_report import generate_msha_report

        report = MSHAComplianceChecker.full_compliance_report(
            mine_name="Test Mine",
            section_name="Section A",
            methane_pct=0.1,
            co_ppm=5.0,
            airflow_m3_s=5.0,
        )
        md = generate_msha_report(report, "markdown")
        assert "MSHA Compliance Report" in md
        assert "Test Mine" in md
        assert "Section A" in md

    def test_generate_json_report(self):
        import json

        from fireai.mining.core.msha_compliance import MSHAComplianceChecker
        from fireai.mining.output.msha_report import generate_msha_report

        report = MSHAComplianceChecker.full_compliance_report(
            mine_name="Test Mine",
            section_name="Section A",
            methane_pct=0.1,
            co_ppm=5.0,
            airflow_m3_s=5.0,
            conveyor_length_m=500.0,
            conveyor_width_m=1.2,
            has_fire_resistant_belt=True,
        )
        json_str = generate_msha_report(report, "json")
        data = json.loads(json_str)
        assert data["mine_name"] == "Test Mine"
        assert data["section_name"] == "Section A"
        assert "checks" in data
        assert len(data["checks"]) == 4
