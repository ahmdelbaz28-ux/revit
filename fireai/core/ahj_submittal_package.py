"""ahj_submittal_package.py — AHJ Submittal Package Generator
================================================================

Assembles a complete Authority Having Jurisdiction (AHJ) submittal
package from all FireAI outputs.  This is the final deliverable that
gets submitted to the fire marshal / building department for approval.

NFPA 72 Chapter 7 requires specific documentation for fire alarm
system submittals.  This module collects, validates, and assembles:

  1. Cover page with project information
  2. System riser diagram (from riser_diagram_generator.py)
  3. Floor plans with device placement (from auto_drafting_engine.py)
  4. Equipment specification sheets
  5. BOQ (Bill of Quantities) — from boq_generator.py
  6. Voltage drop calculations — from nfpa72_calculations.py
  7. Battery calculations — from nfpa72_calculations.py
  8. Pathway survivability classification — from pathway_survivability_engine.py
  9. NAC circuit loading — from nfpa72_calculations.py
  10. Compliance certification

Priority: LOW — useful for production but not life-safety critical.
This is a presentation/formatting layer, not a computation layer.

Thread-safety: zero module-level mutable state.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

__all__ = [
    "AHJSubmittalGenerator",
    "SubmittalPackage",
    "SubmittalResult",
    "SubmittalSection",
]


# ============================================================================
# Data Structures
# ============================================================================


@dataclass(frozen=True)
class SubmittalSection:
    """A section of the AHJ submittal package.

    Attributes:
        title:     Section title.
        section_id: Section number (e.g. "1.0").
        content:   Text content of the section.
        file_paths: Paths to attached files (DWG, DXF, PDF, etc.).
        nfpa_ref:  NFPA 72 reference for this section.
        required:  Whether this section is mandatory per NFPA 72.

    """

    title: str
    section_id: str = ""
    content: str = ""
    file_paths: tuple = ()
    nfpa_ref: str = ""
    required: bool = True


@dataclass
class SubmittalPackage:
    """Complete AHJ submittal package.

    Attributes:
        project_name:     Project identifier.
        project_address:  Building address.
        engineer_name:    Engineer of record.
        license_number:   PE license number.
        nfpa_version:     NFPA edition applied.
        sections:         All sections of the submittal.
        dxf_files:        Paths to DXF drawing files.
        warnings:         Non-fatal advisories.
        errors:           Fatal issues.

    """

    project_name: str = ""
    project_address: str = ""
    engineer_name: str = ""
    license_number: str = ""
    nfpa_version: str = "NFPA 72-2022"
    sections: List[SubmittalSection] = field(default_factory=list)
    dxf_files: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)


@dataclass
class SubmittalResult:
    """Result of submittal package generation.

    Attributes:
        output_path: Path to the generated package index.
        section_count: Number of sections included.
        file_count: Number of attached files.
        complete:   Whether all required sections are present.
        warnings:   Non-fatal advisories.
        errors:     Fatal issues.

    """

    output_path: str = ""
    section_count: int = 0
    file_count: int = 0
    complete: bool = False
    warnings: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)


# ============================================================================
# Generator
# ============================================================================


class AHJSubmittalGenerator:
    """Generate an AHJ submittal package from FireAI outputs.

    Collects all engineering outputs (placement results, BOQ, voltage
    drop calculations, survivability classification, drawings) into a
    structured package ready for submission to the authority having
    jurisdiction.

    Usage::

        gen = AHJSubmittalGenerator()
        pkg = gen.assemble(
            project_name="Tower A",
            boq_result=boq,
            survivability_result=surv,
            nac_loading=nac,
            voltage_drop_results=vd_list,
            building_report=report,
        )
        result = gen.generate_index(pkg, output_dir="/tmp/submittal/")
    """

    # Required sections per NFPA 72 §7.4
    REQUIRED_SECTIONS = [
        ("1.0", "Cover Page", "NFPA 72 §7.4.1"),
        ("2.0", "System Riser Diagram", "NFPA 72 §7.4.5"),
        ("3.0", "Floor Plans", "NFPA 72 §7.4.2"),
        ("4.0", "Equipment Specifications", "NFPA 72 §7.4.3"),
        ("5.0", "Bill of Quantities", "NFPA 72 §7.4.4"),
        ("6.0", "Voltage Drop Calculations", "NFPA 72 §10.14"),
        ("7.0", "Battery Calculations", "NFPA 72 §10.6.7"),
        ("8.0", "Pathway Survivability", "NFPA 72 §12.4"),
        ("9.0", "NAC Circuit Loading", "NFPA 72 §18.5"),
        ("10.0", "Compliance Certification", "NFPA 72 §7.4.6"),
    ]

    def assemble(
        self,
        project_name: str = "",
        project_address: str = "",
        engineer_name: str = "",
        license_number: str = "",
        boq_result: Optional[Any] = None,
        survivability_result: Optional[Any] = None,
        nac_loading: Optional[Dict] = None,
        voltage_drop_results: Optional[List[Dict]] = None,
        battery_result: Optional[Dict] = None,
        building_report: Optional[Any] = None,
    ) -> SubmittalPackage:
        """Assemble a submittal package from engineering outputs.

        Args:
            project_name:          Project name.
            project_address:       Building address.
            engineer_name:         Engineer of record.
            license_number:        PE license number.
            boq_result:            BOQResult from boq_generator.
            survivability_result:  SurvivabilityResult from pathway_survivability_engine.
            nac_loading:           NAC loading dict from calculate_nac_loading().
            voltage_drop_results:  List of voltage drop result dicts.
            battery_result:        Battery calculation dict.
            building_report:       BuildingReport from building_engine.

        Returns:
            SubmittalPackage with all sections populated.

        """
        pkg = SubmittalPackage(
            project_name=project_name,
            project_address=project_address,
            engineer_name=engineer_name,
            license_number=license_number,
        )

        # Section 1: Cover Page
        pkg.sections.append(
            SubmittalSection(
                section_id="1.0",
                title="Cover Page",
                content=self._cover_page_content(pkg),
                nfpa_ref="NFPA 72 §7.4.1",
                required=True,
            )
        )

        # Section 2: Riser Diagram (placeholder — actual DXF generated separately)
        pkg.sections.append(
            SubmittalSection(
                section_id="2.0",
                title="System Riser Diagram",
                content="See attached riser diagram DXF file.",
                nfpa_ref="NFPA 72 §7.4.5",
                required=True,
            )
        )

        # Section 3: Floor Plans (placeholder)
        pkg.sections.append(
            SubmittalSection(
                section_id="3.0",
                title="Floor Plans",
                content="See attached floor plan DXF files with device placement.",
                nfpa_ref="NFPA 72 §7.4.2",
                required=True,
            )
        )

        # Section 4: Equipment Specifications
        equipment_content = self._equipment_specs_content(boq_result)
        pkg.sections.append(
            SubmittalSection(
                section_id="4.0",
                title="Equipment Specifications",
                content=equipment_content,
                nfpa_ref="NFPA 72 §7.4.3",
                required=True,
            )
        )

        # Section 5: BOQ
        boq_content = self._boq_content(boq_result)
        pkg.sections.append(
            SubmittalSection(
                section_id="5.0",
                title="Bill of Quantities",
                content=boq_content,
                nfpa_ref="NFPA 72 §7.4.4",
                required=True,
            )
        )

        # Section 6: Voltage Drop Calculations
        vd_content = self._voltage_drop_content(voltage_drop_results)
        pkg.sections.append(
            SubmittalSection(
                section_id="6.0",
                title="Voltage Drop Calculations",
                content=vd_content,
                nfpa_ref="NFPA 72 §10.14",
                required=True,
            )
        )

        # Section 7: Battery Calculations
        bat_content = self._battery_content(battery_result)
        pkg.sections.append(
            SubmittalSection(
                section_id="7.0",
                title="Battery Calculations",
                content=bat_content,
                nfpa_ref="NFPA 72 §10.6.7",
                required=True,
            )
        )

        # Section 8: Pathway Survivability
        surv_content = self._survivability_content(survivability_result)
        pkg.sections.append(
            SubmittalSection(
                section_id="8.0",
                title="Pathway Survivability Classification",
                content=surv_content,
                nfpa_ref="NFPA 72 §12.4",
                required=True,
            )
        )

        # Section 9: NAC Circuit Loading
        nac_content = self._nac_content(nac_loading)
        pkg.sections.append(
            SubmittalSection(
                section_id="9.0",
                title="NAC Circuit Loading",
                content=nac_content,
                nfpa_ref="NFPA 72 §18.5",
                required=True,
            )
        )

        # Section 10: Compliance Certification
        cert_content = self._certification_content(pkg, building_report)
        pkg.sections.append(
            SubmittalSection(
                section_id="10.0",
                title="Compliance Certification",
                content=cert_content,
                nfpa_ref="NFPA 72 §7.4.6",
                required=True,
            )
        )

        return pkg

    def generate_index(
        self,
        package: SubmittalPackage,
        output_dir: str = ".",
    ) -> SubmittalResult:
        """Generate a text index file listing all submittal sections.

        Args:
            package: Assembled submittal package.
            output_dir: Directory for output files.

        Returns:
            SubmittalResult with generation statistics.

        """
        result = SubmittalResult()

        # Check completeness
        required_ids = {s[0] for s in self.REQUIRED_SECTIONS}
        present_ids = {s.section_id for s in package.sections}
        missing = required_ids - present_ids

        if missing:
            package.warnings.append(
                f"Missing required sections: {missing}. NFPA 72 §7.4 requires all these sections for submittal."
            )

        # Generate index
        output_path = f"{output_dir}/submittal_index.txt"
        try:
            with open(output_path, "w") as f:
                f.write("=" * 72 + "\n")
                f.write("FIRE ALARM SYSTEM — AHJ SUBMITTAL PACKAGE\n")
                f.write("=" * 72 + "\n\n")
                f.write(f"Project:    {package.project_name}\n")
                f.write(f"Address:    {package.project_address}\n")
                f.write(f"Engineer:   {package.engineer_name}\n")
                f.write(f"PE License: {package.license_number}\n")
                f.write(f"NFPA:       {package.nfpa_version}\n\n")

                f.write("-" * 72 + "\n")
                f.write("SECTION INDEX\n")
                f.write("-" * 72 + "\n\n")

                for section in package.sections:
                    req = "[REQUIRED]" if section.required else "[OPTIONAL]"
                    f.write(f"  {section.section_id}  {section.title}  {req}\n")
                    f.write(f"       NFPA Ref: {section.nfpa_ref}\n")
                    if section.file_paths:
                        for fp in section.file_paths:
                            f.write(f"       File: {fp}\n")
                    f.write("\n")

                if package.warnings:
                    f.write("-" * 72 + "\n")
                    f.write("WARNINGS\n")
                    f.write("-" * 72 + "\n\n")
                    for w in package.warnings:
                        f.write(f"  ⚠ {w}\n\n")

                # Write full content for each section
                for section in package.sections:
                    f.write("\n" + "=" * 72 + "\n")
                    f.write(f"SECTION {section.section_id}: {section.title}\n")
                    f.write(f"NFPA Reference: {section.nfpa_ref}\n")
                    f.write("=" * 72 + "\n\n")
                    f.write(section.content + "\n")

            result.output_path = output_path
            result.section_count = len(package.sections)
            result.file_count = len(package.dxf_files)
            result.complete = len(missing) == 0
            result.warnings = package.warnings
            result.errors = package.errors

        except Exception as exc:
            result.errors.append(f"Failed to write submittal index: {exc}")

        return result

    # ─── Content generators ────────────────────────────────────────────

    @staticmethod
    def _cover_page_content(pkg: SubmittalPackage) -> str:
        return (
            f"FIRE ALARM SYSTEM SUBMITTAL\n\n"
            f"Project: {pkg.project_name}\n"
            f"Address: {pkg.project_address}\n"
            f"Engineer of Record: {pkg.engineer_name}\n"
            f"PE License: {pkg.license_number}\n"
            f"Applicable Code: {pkg.nfpa_version}\n\n"
            f"This submittal package contains all required documentation "
            f"per {pkg.nfpa_version} Chapter 7 for the fire alarm system "
            f"installation at the above address."
        )

    @staticmethod
    def _equipment_specs_content(boq_result: Optional[Any]) -> str:
        if boq_result is None:
            return "Equipment specifications pending — BOQ not yet generated."
        lines = ["EQUIPMENT SPECIFICATION SUMMARY\n"]
        if hasattr(boq_result, "items"):
            for item in boq_result.items:
                lines.append(
                    f"  {item.item_type}: {item.description} (Qty: {item.quantity} {item.unit}) [{item.nfpa_reference}]"
                )
        return "\n".join(lines)

    @staticmethod
    def _boq_content(boq_result: Optional[Any]) -> str:
        if boq_result is None:
            return "Bill of Quantities pending — not yet generated."
        lines = ["BILL OF QUANTITIES\n"]
        if hasattr(boq_result, "items"):
            total = 0.0
            for item in boq_result.items:
                lines.append(
                    f"  {item.item_type}: {item.quantity} {item.unit} "
                    f"@ ${item.unit_cost_usd:.2f} = ${item.total_cost_usd:.2f}"
                )
                total += item.total_cost_usd
            lines.append(f"\nGRAND TOTAL: ${total:.2f}")
        return "\n".join(lines)

    @staticmethod
    def _voltage_drop_content(results: Optional[List[Dict]]) -> str:
        if not results:
            return "Voltage drop calculations pending."
        lines = ["VOLTAGE DROP CALCULATIONS\n", "NFPA 72 §10.14\n"]
        for i, vd in enumerate(results):
            lines.append(
                f"  Circuit {i + 1}: "
                f"drop={vd.get('drop_v', 0):.2f}V "
                f"({vd.get('drop_fraction', 0) * 100:.1f}%) "
                f"{'COMPLIANT' if vd.get('compliant') else 'NON-COMPLIANT'}"
            )
        return "\n".join(lines)

    @staticmethod
    def _battery_content(result: Optional[Dict]) -> str:
        if result is None:
            return "Battery calculations pending."
        return (
            f"BATTERY CALCULATIONS\n"
            f"NFPA 72 §10.6.7\n\n"
            f"Required: {result.get('required_ah', 0):.2f} Ah\n"
            f"Installed: {result.get('installed_ah', 0):.0f} Ah\n"
            f"Battery count: {result.get('battery_count', 0)} "
            f"(2 per panel for redundancy)\n"
            f"Adequate: {'YES' if result.get('is_adequate') else 'NO'}\n"
        )

    @staticmethod
    def _survivability_content(result: Optional[Any]) -> str:
        if result is None:
            return "Pathway survivability classification pending."
        lines = ["PATHWAY SURVIVABILITY CLASSIFICATION\n", "NFPA 72 §12.4\n"]
        if hasattr(result, "building_level"):
            lines.append(f"Building Level: {result.building_level.value}")
        if hasattr(result, "classification_rationale"):
            lines.append("\nClassification Rationale:")
            for reason in result.classification_rationale:
                lines.append(f"  • {reason}")
        if hasattr(result, "cable_requirements"):
            lines.append("\nCable Requirements:")
            for req in result.cable_requirements:
                enclosure = f" in {req.enclosure_rating_hr:.0f}hr rated enclosure" if req.in_rated_enclosure else ""
                lines.append(f"  • {req.route_type}: {req.cable_type.value} cable{enclosure}")
        return "\n".join(lines)

    @staticmethod
    def _nac_content(result: Optional[Dict]) -> str:
        if result is None:
            return "NAC circuit loading analysis pending."
        lines = ["NAC CIRCUIT LOADING\n", "NFPA 72 §18.5 / §10.14.1\n"]
        lines.append(f"Total steady-state current: {result.get('steady_total_a', 0):.2f} A")
        lines.append(f"Total inrush current: {result.get('inrush_total_a', 0):.2f} A")
        lines.append(f"Within panel limit: {'YES' if result.get('within_panel_limit') else 'NO'}")
        for w in result.get("warnings", []):
            lines.append(f"  ⚠ {w}")
        return "\n".join(lines)

    @staticmethod
    def _certification_content(pkg: SubmittalPackage, report: Optional[Any]) -> str:
        lines = [
            "COMPLIANCE CERTIFICATION\n",
            f"I, {pkg.engineer_name}, PE License #{pkg.license_number}, "
            f"certify that the fire alarm system design for {pkg.project_name} "
            f"complies with {pkg.nfpa_version} and all applicable local codes.\n",
        ]
        if report is not None:
            if hasattr(report, "safe_to_submit"):
                if report.safe_to_submit:
                    lines.append("Building analysis result: SAFE TO SUBMIT")
                else:
                    lines.append(
                        "⚠ BUILDING ANALYSIS RESULT: NOT SAFE TO SUBMIT\n"
                        "One or more rooms have failed compliance checks. "
                        "This submittal cannot be certified until all issues are resolved."
                    )
            if hasattr(report, "total_detectors"):
                lines.append(f"\nTotal detectors: {report.total_detectors}")
            if hasattr(report, "fully_compliant"):
                lines.append(f"Fully compliant: {report.fully_compliant}")

        lines.append(
            "\nSignature: ________________________    Date: ____________\n"
            f"Engineer: {pkg.engineer_name}    PE #: {pkg.license_number}"
        )
        return "\n".join(lines)
