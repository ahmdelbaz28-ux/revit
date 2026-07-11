"""
msha_compliance.py — MSHA compliance checker for mine fire protection.

V214: Implements compliance checks per:
  - MSHA 30 CFR Part 75 (Underground Coal Mines)
  - NFPA 120-2022 (Coal Mine Fire Prevention)
  - NFPA 122-2022 (Metal/Nonmetal Mining)

This module aggregates checks from the other mining core modules and
provides a unified compliance report.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from fireai.mining.core.conveyor_fire import (
    ConveyorFireAnalyzer,
)
from fireai.mining.core.methane_calculator import MethaneCalculator
from fireai.mining.core.ventilation_calculator import VentilationCalculator


@dataclass
class ComplianceCheck:
    """A single compliance check result."""
    rule_id: str
    standard: str  # "MSHA 30 CFR §75.xxx" or "NFPA 120 §x.x"
    description: str
    status: str  # "PASS", "FAIL", "WARNING", "N/A"
    details: str
    remediation: str = ""


@dataclass
class MSHAComplianceReport:
    """Full MSHA compliance report for a mine section."""
    mine_name: str
    section_name: str
    checks: list[ComplianceCheck] = field(default_factory=list)
    overall_status: str = "PASS"

    def add_check(self, check: ComplianceCheck) -> None:
        self.checks.append(check)
        if check.status == "FAIL":
            self.overall_status = "FAIL"
        elif check.status == "WARNING" and self.overall_status != "FAIL":
            self.overall_status = "WARNING"


class MSHAComplianceChecker:
    """
    Check mine fire protection compliance per MSHA + NFPA 120/122.
    """

    @staticmethod
    def check_methane_monitoring(
        methane_concentration_pct: float,
        location: str = "working_face",
    ) -> ComplianceCheck:
        """
        Check methane monitoring compliance per MSHA 30 CFR §75.323.
        """
        hazard = MethaneCalculator.classify_hazard(methane_concentration_pct)

        if hazard == "normal":
            status = "PASS"
            details = f"CH4 = {methane_concentration_pct}% — within normal range"
            remediation = ""
        elif hazard == "notify":
            status = "WARNING"
            details = f"CH4 = {methane_concentration_pct}% — notify foreman, increase ventilation"
            remediation = "Increase ventilation airflow and notify mine foreman immediately."
        elif hazard == "evacuate_area":
            status = "FAIL"
            details = f"CH4 = {methane_concentration_pct}% — evacuate personnel from area"
            remediation = "Remove all personnel from the affected area immediately."
        elif hazard == "deenergize":
            status = "FAIL"
            details = f"CH4 = {methane_concentration_pct}% — de-energize electrical equipment"
            remediation = "De-energize all electrical equipment in the affected area."
        elif hazard == "withdraw_all":
            status = "FAIL"
            details = f"CH4 = {methane_concentration_pct}% — withdraw all personnel"
            remediation = "Withdraw ALL personnel from the mine. Post warning signs."
        else:  # explosive
            status = "FAIL"
            details = f"CH4 = {methane_concentration_pct}% — EXPLOSIVE ATMOSPHERE"
            remediation = "Immediate full evacuation. Do not re-enter until ventilated below 1%."

        return ComplianceCheck(
            rule_id="MSHA-75.323",
            standard="MSHA 30 CFR §75.323",
            description=f"Methane monitoring at {location}",
            status=status,
            details=details,
            remediation=remediation,
        )

    @staticmethod
    def check_ventilation(
        airflow_m3_s: float,
        location_type: str = "working_face",
        cross_sectional_area_m2: float | None = None,
    ) -> ComplianceCheck:
        """
        Check ventilation compliance per MSHA 30 CFR §75.326-327.
        """
        is_compliant, violations = VentilationCalculator.check_msha_compliance(
            airflow_m3_s, location_type, cross_sectional_area_m2
        )

        if is_compliant:
            status = "PASS"
            details = f"Airflow = {airflow_m3_s} m³/s at {location_type} — meets MSHA minimum"
            remediation = ""
        else:
            status = "FAIL"
            details = f"Airflow = {airflow_m3_s} m³/s at {location_type} — " + "; ".join(violations)
            remediation = "Increase ventilation fan capacity or reduce airway resistance."

        return ComplianceCheck(
            rule_id=f"MSHA-75.{326 if location_type == 'working_face' else 327}",
            standard=f"MSHA 30 CFR §75.{326 if location_type == 'working_face' else 327}",
            description=f"Ventilation at {location_type}",
            status=status,
            details=details,
            remediation=remediation,
        )

    @staticmethod
    def check_co_monitoring(co_concentration_ppm: float) -> ComplianceCheck:
        """
        Check CO monitoring compliance per MSHA 30 CFR §75.351.
        """
        hazard = ConveyorFireAnalyzer.classify_co_hazard(co_concentration_ppm)

        if hazard == "normal":
            status = "PASS"
            details = f"CO = {co_concentration_ppm} ppm — within normal range"
            remediation = ""
        elif hazard == "alert":
            status = "WARNING"
            details = f"CO = {co_concentration_ppm} ppm — alert level, notify foreman"
            remediation = "Notify mine foreman and investigate source."
        elif hazard == "evacuate":
            status = "FAIL"
            details = f"CO = {co_concentration_ppm} ppm — evacuate belt entry"
            remediation = "Evacuate personnel from belt entry immediately."
        elif hazard == "withdraw":
            status = "FAIL"
            details = f"CO = {co_concentration_ppm} ppm — withdraw all personnel, activate suppression"
            remediation = "Withdraw all personnel. Activate fire suppression system."
        else:  # imminent
            status = "FAIL"
            details = f"CO = {co_concentration_ppm} ppm — imminent danger"
            remediation = "Full mine evacuation. This is a life-threatening emergency."

        return ComplianceCheck(
            rule_id="MSHA-75.351",
            standard="MSHA 30 CFR §75.351",
            description="CO monitoring at belt entry",
            status=status,
            details=details,
            remediation=remediation,
        )

    @staticmethod
    def check_conveyor_suppression(
        belt_length_m: float,
        belt_width_m: float,
        has_fire_resistant_belt: bool = True,
    ) -> ComplianceCheck:
        """
        Check conveyor belt fire suppression per NFPA 120 §8.4 + MSHA §75.1108.
        """
        from fireai.mining.core.conveyor_fire import ConveyorSpec
        spec = ConveyorSpec(
            belt_length_m=belt_length_m,
            belt_width_m=belt_width_m,
            belt_speed_m_s=0.0,  # Not relevant for suppression design
            has_fire_resistant_belt=has_fire_resistant_belt,
        )
        design = ConveyorFireAnalyzer.design_suppression_system(spec)

        if design.is_compliant:
            status = "PASS"
            details = (
                f"Suppression system: {design.number_of_nozzle_groups} nozzle groups, "
                f"{design.water_flow_rate_lpm} L/min, "
                f"{design.total_water_volume_l} L total water"
            )
            remediation = ""
        else:
            status = "FAIL"
            details = "Non-compliant: " + "; ".join(design.violations)
            remediation = "Install fire-resistant belt and/or add suppression nozzle groups."

        return ComplianceCheck(
            rule_id="NFPA-120-8.4",
            standard="NFPA 120-2022 §8.4 + MSHA 30 CFR §75.1108",
            description="Conveyor belt fire suppression",
            status=status,
            details=details,
            remediation=remediation,
        )

    @staticmethod
    def full_compliance_report(
        mine_name: str,
        section_name: str,
        methane_pct: float = 0.0,
        co_ppm: float = 0.0,
        airflow_m3_s: float = 0.0,
        ventilation_location: str = "working_face",
        conveyor_length_m: float = 0.0,
        conveyor_width_m: float = 0.0,
        has_fire_resistant_belt: bool = True,
    ) -> MSHAComplianceReport:
        """
        Generate a full MSHA + NFPA 120 compliance report.
        """
        report = MSHAComplianceReport(
            mine_name=mine_name,
            section_name=section_name,
        )

        # Methane check
        report.add_check(MSHAComplianceChecker.check_methane_monitoring(
            methane_pct, section_name
        ))

        # CO check
        report.add_check(MSHAComplianceChecker.check_co_monitoring(co_ppm))

        # Ventilation check
        if airflow_m3_s > 0:
            report.add_check(MSHAComplianceChecker.check_ventilation(
                airflow_m3_s, ventilation_location
            ))

        # Conveyor suppression check
        if conveyor_length_m > 0:
            report.add_check(MSHAComplianceChecker.check_conveyor_suppression(
                conveyor_length_m, conveyor_width_m, has_fire_resistant_belt
            ))

        return report
