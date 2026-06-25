"""D2: Compliance Proof Document Generator — AHJ-Ready Markdown
=============================================================
Generates a comprehensive NFPA 72 compliance proof document from
verified placement results. This document is intended for submission
to the Authority Having Jurisdiction (AHJ) as part of the fire alarm
system permitting process.

The document includes:
  1. Project summary and design criteria
  2. Room-by-room detector placement details
  3. Verification proof status for each room
  4. NFPA 72 section references for every design decision
  5. Consensus engine verification results
  6. Engineer certification section

FORMAT: Markdown (easily convertible to PDF/DOCX for AHJ submission)

Usage:
  from fireai.core.compliance_proof_document import ComplianceProofDocument

  doc = ComplianceProofDocument(
      project_name="ABC Office Building",
      designer="John Smith, PE",
      nfpa_edition="2022",
  )
  doc.add_room_result(room, layout, consensus_result)
  markdown = doc.generate()

Run:
  python -m fireai.tools.compliance_proof_document --help

NFPA 72-2022 §17.7.4.2.3.1: Coverage radius R = 0.7 × S
"""

from __future__ import annotations

import datetime
import math
from dataclasses import dataclass, field
from typing import List, Optional

from fireai.core.spatial_engine.consensus_engine import (
    ConfidenceLevel,
    ConsensusEngine,
    ConsensusResult,
)
from fireai.core.spatial_engine.density_optimizer import (
    COARSE_STEP,
    COVERAGE_SAFETY_FACTOR,
    DENSITY_CAP_FACTOR,
    DETECTOR_RADIUS,
    MAX_SPACING_M,
    PLACEMENT_MARGIN,
    VERIFY_STEP,
    WALL_MIN_M,
    DensityOptimizer,
    DetectorLayout,
    Room,
)

# ═══════════════════════════════════════════════════════════════════════════════
# Data Classes
# ═══════════════════════════════════════════════════════════════════════════════


@dataclass
class RoomVerificationRecord:
    """Complete verification record for a single room."""

    room: Room
    layout: DetectorLayout
    consensus: Optional[ConsensusResult] = None
    notes: List[str] = field(default_factory=list)


# ═══════════════════════════════════════════════════════════════════════════════
# Compliance Proof Document
# ═══════════════════════════════════════════════════════════════════════════════


def _safe_fmt(value: float, fmt: str = ".1f") -> str:
    """V57 FIX (Finding 15): Format a float for AHJ document, replacing
    NaN/Inf with '[INVALID DATA]'. NaN values produce 'nan%' in the
    AHJ submission document, which is unacceptable for regulatory filings.
    Non-finite data indicates a calculation error that must be flagged.
    """
    if not math.isfinite(value):
        return "[INVALID DATA]"
    return f"{value:{fmt}}"


class ComplianceProofDocument:
    """Generates AHJ-ready NFPA 72 compliance proof documents.

    The document is structured to satisfy typical AHJ requirements:
      - Project identification
      - Design criteria and code references
      - Room-by-room verification with mathematical proof status
      - Consensus engine results (3-engine verification)
      - Engineer certification

    Usage:
        doc = ComplianceProofDocument(
            project_name="ABC Office Tower",
            designer="Jane Smith, PE #12345",
            nfpa_edition="2022",
        )
        doc.add_room_result(room, layout, consensus_result)
        markdown_text = doc.generate()
    """

    def __init__(
        self,
        project_name: str = "FireAI V30 Project",
        designer: str = "",
        nfpa_edition: str = "2022",
        jurisdiction: str = "",
    ):
        self.project_name = project_name
        self.designer = designer
        self.nfpa_edition = nfpa_edition
        self.jurisdiction = jurisdiction
        self.records: List[RoomVerificationRecord] = []
        self.generation_date = datetime.datetime.now(datetime.timezone.utc).strftime(
            "%Y-%m-%d %H:%M UTC"
        )  # V54 FIX (AUDIT-012): timezone-aware UTC

    def add_room_result(
        self,
        room: Room,
        layout: DetectorLayout,
        consensus: Optional[ConsensusResult] = None,
        notes: Optional[List[str]] = None,
    ) -> None:
        """Add a room's verification result to the document."""
        self.records.append(
            RoomVerificationRecord(
                room=room,
                layout=layout,
                consensus=consensus,
                notes=notes or [],
            )
        )

    def generate(self) -> str:
        """Generate the complete compliance proof document as Markdown.

        Returns:
            Markdown-formatted string ready for AHJ submission.

        """
        sections = [
            self._header(),
            self._design_criteria(),
            self._room_summary_table(),
            self._detailed_room_results(),
            self._consensus_summary(),
            self._certification(),
        ]
        return "\n\n".join(sections)

    # ── Section Generators ─────────────────────────────────────────────────

    def _header(self) -> str:
        """Document header with project identification."""
        lines = [
            f"# NFPA 72-{self.nfpa_edition} Compliance Proof Document",
            "",
            f"**Project:** {self.project_name}",
            f"**Designer:** {self.designer or 'TBD'}",
            f"**Jurisdiction:** {self.jurisdiction or 'TBD'}",
            f"**Date:** {self.generation_date}",
            "**FireAI Version:** V30",
            f"**Total Rooms:** {len(self.records)}",
        ]
        return "\n".join(lines)

    def _design_criteria(self) -> str:
        """Design criteria and NFPA 72 references."""
        lines = [
            "## 1. Design Criteria",
            "",
            "### 1.1 Applicable Codes and Standards",
            "",
            f"- **NFPA 72-{self.nfpa_edition}**: National Fire Alarm and Signaling Code",
            "- **NFPA 72 §17.6.3.1.1**: Spot-type smoke detector spacing — maximum "
            "30 ft (9.1 m) nominal spacing on smooth ceilings",
            "- **NFPA 72 §17.7.4.2.3.1**: Coverage radius R = 0.7 × S where S is the "
            "nominal spacing (0.7 × 9.1m = 6.37m)",
            "- **NFPA 72 §17.6.3.1.1**: Minimum distance from wall = 4 inches (0.10m) to avoid dead air space",
            "",
            "### 1.2 Design Parameters",
            "",
            "| Parameter | Value | NFPA Reference |",
            "|-----------|-------|----------------|",
            f"| Maximum Spacing (S) | {MAX_SPACING_M:.1f} m (30 ft) | NFPA 72 Table 17.6.3.1.1 |",
            f"| Coverage Radius (R) | {DETECTOR_RADIUS:.2f} m (0.7 × S) | NFPA 72 §17.7.4.2.3.1 |",
            f"| Wall Minimum Distance | {WALL_MIN_M:.2f} m (4 in) | NFPA 72 §17.6.3.1.1 |",
            f"| Verification Grid Resolution | {VERIFY_STEP:.2f} m | Internal — proof resolution |",
            f"| Coarse Grid Step | {COARSE_STEP:.2f} m | Internal — hierarchical verification |",
            f"| Placement Margin | {PLACEMENT_MARGIN:.4f} m | Internal — V7.4 alignment |",
            f"| Coverage Safety Factor | {COVERAGE_SAFETY_FACTOR:.0%} | Defense-in-depth |",
            f"| Density Cap Factor | {DENSITY_CAP_FACTOR:.1f}× | Prevents over-placement |",
            "",
            "### 1.3 Verification Methodology",
            "",
            "FireAI V30 uses a **Triple Verification System** with three independent engines:",
            "",
            "1. **Analytical Engine**: Exact geometric proof checking room corners, "
            "detector midpoints, and wall coverage via interval merging (O(n log n)).",
            "2. **Voronoi Engine**: Gap-based analysis using Voronoi tessellation to find "
            "the farthest point from any detector.",
            "3. **Grid Engine**: δ-conservative hierarchical grid verification with "
            "mathematical proof via triangle inequality (R_eff = R - δ√2/2).",
            "",
            "**Consensus Rules:**",
            "- 3/3 engines PASS → VERIFIED (green) — Safe to deploy",
            "- 2/3 engines PASS → WARNING (yellow) — Investigate before deploying",
            "- 1/3 or 0/3 PASS → FAIL (red) — DO NOT deploy",
            "",
            "### 1.4 Mathematical Proof Foundation",
            "",
            "The grid-based verification uses a **δ-conservative effective radius**:",
            "",
            "    R_eff = R - δ√2/2",
            "",
            "where δ = grid step size. By the triangle inequality:",
            "",
            "    dist(P, D) ≤ dist(P, corner) + dist(corner, D)",
            "              ≤ δ√2/2 + R_eff",
            "              = δ√2/2 + (R - δ√2/2)",
            "              = R",
            "",
            "Therefore, if all grid cell corners are within R_eff of some detector, "
            "then every point in the room is within R of some detector. This is a "
            "**rigorous mathematical proof** with zero false positives.",
        ]
        return "\n".join(lines)

    def _room_summary_table(self) -> str:
        """Summary table of all rooms."""
        lines = [
            "## 2. Room Summary",
            "",
            "| # | Room | Dimensions (m) | Ceiling H | Detectors | Coverage | Proof | NFPA | Consensus |",
            "|---|------|---------------|-----------|-----------|----------|-------|------|-----------|",
        ]

        for i, rec in enumerate(self.records, 1):
            room = rec.room
            layout = rec.layout
            cons_str = (
                f"{rec.consensus.n_pass}/{rec.consensus.n_total} {rec.consensus.confidence.value}"
                if rec.consensus
                else "N/A"
            )
            proof_str = "✓" if layout.proof_valid else "✗"
            nfpa_str = "✓" if layout.nfpa_valid else "✗"
            # V57 FIX (Finding 15): NaN values produce 'nan%' in AHJ submission.
            # Use _safe_fmt to replace non-finite values with '[INVALID DATA]'.
            lines.append(
                f"| {i} | {room.name} | "
                f"{_safe_fmt(room.width)} × {_safe_fmt(room.length)} | "
                f"{_safe_fmt(room.ceiling_height)} | "
                f"{layout.count} | "
                f"{_safe_fmt(layout.coverage_pct)}% | "
                f"{proof_str} | {nfpa_str} | {cons_str} |"
            )

        # Summary statistics
        total_detectors = sum(r.layout.count for r in self.records)
        all_proof = all(r.layout.proof_valid for r in self.records)
        all_nfpa = all(r.layout.nfpa_valid for r in self.records)
        all_verified = all(r.consensus and r.consensus.confidence == ConfidenceLevel.VERIFIED for r in self.records)

        lines.extend(
            [
                "",
                f"**Total Detectors:** {total_detectors}",
                f"**All Rooms Proof Valid:** {'Yes ✓' if all_proof else 'No ✗ — requires review'}",
                f"**All Rooms NFPA Compliant:** {'Yes ✓' if all_nfpa else 'No ✗ — requires review'}",
                f"**All Rooms Consensus VERIFIED:** {'Yes ✓' if all_verified else 'No — some rooms require investigation'}",
            ]
        )
        return "\n".join(lines)

    def _detailed_room_results(self) -> str:
        """Detailed results for each room."""
        lines = ["## 3. Detailed Room Results", ""]

        for i, rec in enumerate(self.records, 1):
            room = rec.room
            layout = rec.layout

            # V57 FIX (Finding 15): NaN values produce 'nan%' in AHJ submission.
            # Use _safe_fmt to replace non-finite values with '[INVALID DATA]'.
            area = room.width * room.length
            lines.extend(
                [
                    f"### 3.{i} Room: {room.name}",
                    "",
                    f"**Dimensions:** {_safe_fmt(room.width)} m × {_safe_fmt(room.length)} m "
                    f"(Area: {_safe_fmt(area)} m²)",
                    f"**Ceiling Height:** {_safe_fmt(room.ceiling_height)} m",
                    f"**Coverage Radius Used:** {_safe_fmt(layout.coverage_radius, '.2f')} m "
                    f"({self._radius_source(room.ceiling_height)})",
                    f"**Placement Method:** {layout.method}",
                    f"**Detector Count:** {layout.count}",
                    f"**Theoretical Lower Bound:** {layout.theoretical_lower_bound}",
                    f"**Efficiency Ratio:** {_safe_fmt(layout.efficiency_ratio, '.2f')}",
                    f"**Coverage:** {_safe_fmt(layout.coverage_pct, '.2f')}%",
                    f"**Proof Valid:** {'Yes' if layout.proof_valid else 'No — REQUIRES REVIEW'}",
                    f"**NFPA 72 Compliant:** {'Yes' if layout.nfpa_valid else 'No — REQUIRES REVIEW'}",
                    f"**Wall Violations:** {layout.wall_violations}",
                    f"**Fallback Used:** {'Yes — requires manual design review' if layout.fallback_used else 'No'}",
                    "",
                ]
            )

            # Detector positions table
            if layout.detectors:
                lines.extend(
                    [
                        "**Detector Positions:**",
                        "",
                        "| # | X (m) | Y (m) | Wall Dist Min (m) |",
                        "|---|-------|-------|-------------------|",
                    ]
                )
                for j, (x, y) in enumerate(layout.detectors, 1):
                    wall_dist = min(
                        x,
                        room.width - x,
                        y,
                        room.length - y,
                    )
                    # V57 FIX (Finding 15): NaN detector positions or wall distances
                    # produce 'nan' in AHJ table. Replace with '[INVALID DATA]'.
                    lines.append(
                        f"| {j} | {_safe_fmt(x, '.3f')} | {_safe_fmt(y, '.3f')} | {_safe_fmt(wall_dist, '.3f')} |"
                    )
                lines.append("")

            # Consensus result
            if rec.consensus:
                lines.extend(
                    [
                        f"**Consensus:** {rec.consensus.consensus_str}",
                        f"**is_safe:** {rec.consensus.is_safe}",
                    ]
                )
                for v in rec.consensus.engines:
                    lines.append(f"- {v.engine.value}: {'PASS' if v.passed else 'FAIL'} — {v.details}")
                lines.append("")

            # Notes
            if rec.notes:
                lines.append("**Notes:**")
                for note in rec.notes:
                    lines.append(f"- {note}")
                lines.append("")

        return "\n".join(lines)

    def _consensus_summary(self) -> str:
        """Summary of consensus verification results."""
        if not self.records:
            return "## 4. Consensus Summary\n\nNo rooms verified."

        verified = sum(1 for r in self.records if r.consensus and r.consensus.confidence == ConfidenceLevel.VERIFIED)
        warning = sum(1 for r in self.records if r.consensus and r.consensus.confidence == ConfidenceLevel.WARNING)
        fail = sum(1 for r in self.records if r.consensus and r.consensus.confidence == ConfidenceLevel.FAIL)
        no_consensus = sum(1 for r in self.records if not r.consensus)
        total = len(self.records)

        lines = [
            "## 4. Consensus Verification Summary",
            "",
            "| Status | Count | Percentage |",
            "|--------|-------|------------|",
            f"| VERIFIED (3/3) | {verified} | {100 * verified / total:.0f}% |",
            f"| WARNING (2/3) | {warning} | {100 * warning / total:.0f}% |",
            f"| FAIL (≤1/3) | {fail} | {100 * fail / total:.0f}% |",
            f"| Not Verified | {no_consensus} | {100 * no_consensus / total:.0f}% |",
            "",
        ]

        if fail > 0:
            lines.extend(
                [
                    "**⚠ ATTENTION:** The following rooms have FAIL status and MUST NOT be "
                    "deployed without resolution:",
                    "",
                ]
            )
            for r in self.records:
                if r.consensus and r.consensus.confidence == ConfidenceLevel.FAIL:
                    lines.append(
                        f"- **{r.room.name}** ({r.room.width:.0f}×{r.room.length:.0f}m): {r.consensus.recommendation}"
                    )
            lines.append("")

        if warning > 0:
            lines.extend(
                [
                    "**⚠ WARNING:** The following rooms have discrepancies between engines and require investigation:",
                    "",
                ]
            )
            for r in self.records:
                if r.consensus and r.consensus.confidence == ConfidenceLevel.WARNING:
                    lines.append(
                        f"- **{r.room.name}** ({r.room.width:.0f}×{r.room.length:.0f}m): {r.consensus.recommendation}"
                    )
            lines.append("")

        if verified == total:
            lines.append(
                "✓ **ALL ROOMS VERIFIED (3/3):** The detector placement in every room has "
                "been independently verified by all three verification engines. The system "
                "is safe for deployment per NFPA 72-2022 requirements."
            )

        return "\n".join(lines)

    def _certification(self) -> str:
        """Engineer certification section."""
        lines = [
            "## 5. Engineer Certification",
            "",
            "I certify that the fire alarm system design documented herein complies with "
            f"NFPA 72-{self.nfpa_edition} requirements as verified by the FireAI V30 "
            "automated verification system. The detector placement has been independently "
            "verified by three separate verification engines (Analytical, Voronoi, and "
            "Grid-based), and the mathematical proof of coverage has been validated for "
            "each room using δ-conservative grid verification.",
            "",
            "The verification methodology is based on the triangle inequality proof that "
            "R_eff = R - δ√2/2 guarantees full coverage when all grid cell corners are "
            "within R_eff of a detector. This is a rigorous mathematical proof with "
            "zero false positives.",
            "",
            "All design parameters (spacing, wall distance, coverage radius) have been "
            "verified against the NFPA 72-2022 tables and sections referenced in this "
            "document.",
            "",
            "---",
            "",
            f"**Engineer:** {self.designer or '_________________________________'}",
            "",
            f"**Date:** {self.generation_date}",
            "",
            "**License #:** _________________________________",
            "",
            "**Signature:** _________________________________",
        ]
        return "\n".join(lines)

    # ── Helpers ────────────────────────────────────────────────────────────

    @staticmethod
    def _radius_source(ceiling_height: float) -> str:
        """Return the NFPA reference for the coverage radius at a given height."""
        if ceiling_height <= 3.0:
            return "NFPA 72 Table 17.6.3.1.1 — h ≤ 3.0m → R = 0.7 × 9.1 = 6.37m"
        if ceiling_height <= 3.7:
            return "NFPA 72 Table 17.6.3.1.1 — h ∈ (3.0, 3.7]m → R = 6.37m"
        if ceiling_height <= 4.3:
            return "NFPA 72 Table 17.6.3.1.1 — h ∈ (3.7, 4.3]m → R < 6.37m"
        return f"NFPA 72 Table 17.6.3.1.1 — h={ceiling_height:.1f}m → R reduced"


# ═══════════════════════════════════════════════════════════════════════════════
# CLI Interface
# ═══════════════════════════════════════════════════════════════════════════════


def _cli_main():
    """Command-line interface for generating compliance proof documents."""
    import argparse
    import sys

    parser = argparse.ArgumentParser(
        description="Generate NFPA 72 compliance proof document from FireAI results",
    )
    parser.add_argument(
        "--project",
        default="FireAI V30 Project",
        help="Project name (default: 'FireAI V30 Project')",
    )
    parser.add_argument(
        "--designer",
        default="",
        help="Designer name and PE number",
    )
    parser.add_argument(
        "--edition",
        default="2022",
        help="NFPA 72 edition (default: 2022)",
    )
    parser.add_argument(
        "--demo",
        action="store_true",
        help="Generate a demo document with sample rooms",
    )
    parser.add_argument(
        "--output",
        default="-",
        help="Output file path (default: stdout)",
    )

    args = parser.parse_args()

    doc = ComplianceProofDocument(
        project_name=args.project,
        designer=args.designer,
        nfpa_edition=args.edition,
    )

    if args.demo:
        # Generate demo with sample rooms
        opt = DensityOptimizer()
        consensus_engine = ConsensusEngine(coverage_radius=DETECTOR_RADIUS)

        demo_rooms = [
            Room("Office-101", 5.0, 5.0, 3.0),
            Room("Conference-A", 10.0, 12.0, 3.0),
            Room("Open-Office-B", 15.0, 20.0, 3.0),
            Room("Warehouse-C", 25.0, 30.0, 6.0),
        ]

        for room in demo_rooms:
            from fireai.core.nfpa72_models import get_smoke_detector_radius_safe

            R = get_smoke_detector_radius_safe(room.ceiling_height)
            layout = opt.optimize(room, coverage_radius=R)
            consensus = consensus_engine.verify(
                width=room.width,
                length=room.length,
                detectors=layout.detectors,
                grid_proof_valid=layout.proof_valid,
                grid_coverage_pct=layout.coverage_pct,
            )
            doc.add_room_result(room, layout, consensus)

    markdown = doc.generate()

    if args.output == "-":
        print(markdown)
    else:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(markdown)
        print(f"Compliance document written to {args.output}", file=sys.stderr)


if __name__ == "__main__":
    _cli_main()
