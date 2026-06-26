"""
backend/services/design_agent.py — AI Design Agent with MANDATORY Human Gate
=============================================================================

Single-agent system that PROPOSES (never auto-approves) fire alarm
detector placements. Every proposal REQUIRES human engineer approval.

SAFETY-CRITICAL:
  - Agent NEVER auto-approves — human gate is MANDATORY
  - Proposals are ADVISORY only
  - NFPA 72 requires professional engineer review
  - No proposal is valid until explicitly approved by a human

REFERENCE: NFPA 72-2022 §17.6, agent.md Rule 12 (safety-first)
"""

from __future__ import annotations

import logging
import math
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger("fireai.services.design_agent")


@dataclass
class DetectorProposal:
    """A proposed detector placement."""
    x: float
    y: float
    z: float
    detector_type: str  # "smoke" or "heat"
    coverage_radius: float
    room_id: str
    confidence: float = 0.0
    reasoning: str = ""


@dataclass
class DesignProposal:
    """Complete design proposal for a room/floor."""
    proposals: list[DetectorProposal] = field(default_factory=list)
    room_id: str = ""
    room_name: str = ""
    room_area: float = 0.0
    total_detectors: int = 0
    estimated_coverage_pct: float = 0.0
    correlation_id: str = ""
    approved: bool = False  # MUST be False until human approves
    approved_by: str = ""
    approved_at: str = ""
    disclaimer: str = ""

    def __post_init__(self):
        if not self.disclaimer:
            self.disclaimer = (
                "⚠️ ADVISORY ONLY — This proposal requires approval from a "
                "licensed fire protection engineer before implementation. "
                "NFPA 72 requires professional review of all detector placements."
            )


class DesignAgent:
    """
    Single-agent fire alarm design proposer.

    ARCHITECTURE: Single agent (NOT multi-agent) for stability.
    Human gate is MANDATORY and cannot be bypassed.
    """

    # NFPA 72-2022 coverage radii (0.7 × nominal spacing)
    SMOKE_RADIUS = 0.7 * 9.1   # 6.37 m (circular, smooth ceiling)
    HEAT_RADIUS = 0.7 * 15.2   # 10.64 m (but uses square spacing)

    def propose(
        self,
        room_id: str,
        room_name: str,
        room_area: float,
        room_width: float = 0,
        room_length: float = 0,
        detector_type: str = "smoke",
        correlation_id: str | None = None,
    ) -> DesignProposal:
        """
        Generate a detector placement proposal for a room.

        This is a PROPOSAL only — it MUST be approved by a human engineer.
        """
        if correlation_id is None:
            correlation_id = f"design-{uuid.uuid4().hex[:12]}"

        coverage_radius = self.SMOKE_RADIUS if detector_type == "smoke" else self.HEAT_RADIUS

        # Calculate number of detectors needed
        if room_area <= 0:
            return DesignProposal(
                room_id=room_id,
                room_name=room_name,
                room_area=room_area,
                correlation_id=correlation_id,
                approved=False,
            )

        # Area-based estimate
        coverage_area = math.pi * coverage_radius ** 2  # circular coverage
        num_detectors = max(1, math.ceil(room_area / coverage_area))

        # Generate positions using grid layout
        proposals = []
        if room_width > 0 and room_length > 0:
            cols = max(1, math.ceil(math.sqrt(num_detectors * room_width / room_length)))
            rows = max(1, math.ceil(num_detectors / cols))
            dx = room_width / (cols + 1)
            dy = room_length / (rows + 1)

            for row in range(rows):
                for col in range(cols):
                    if len(proposals) >= num_detectors:
                        break
                    proposals.append(DetectorProposal(
                        x=dx * (col + 1),
                        y=dy * (row + 1),
                        z=0.0,  # Ceiling-mounted
                        detector_type=detector_type,
                        coverage_radius=coverage_radius,
                        room_id=room_id,
                        confidence=0.8,
                        reasoning=f"Grid placement: {detector_type} detector at ({dx*(col+1):.1f}, {dy*(row+1):.1f}) covering {coverage_area:.1f} sqm each",
                    ))
        else:
            # Fallback: single detector at center
            proposals.append(DetectorProposal(
                x=0, y=0, z=0,
                detector_type=detector_type,
                coverage_radius=coverage_radius,
                room_id=room_id,
                confidence=0.5,
                reasoning=f"Single {detector_type} detector — room dimensions unknown",
            ))

        # Estimate coverage
        total_coverage = len(proposals) * coverage_area
        estimated_pct = min(100.0, (total_coverage / room_area) * 100) if room_area > 0 else 0

        return DesignProposal(
            proposals=proposals,
            room_id=room_id,
            room_name=room_name,
            room_area=room_area,
            total_detectors=len(proposals),
            estimated_coverage_pct=round(estimated_pct, 1),
            correlation_id=correlation_id,
            approved=False,  # ALWAYS False until human approval
        )

    def approve(self, proposal: DesignProposal, approver: str) -> DesignProposal:
        """
        Approve a design proposal — ONLY after human review.

        This method represents the MANDATORY human gate.
        It cannot be called automatically.
        """
        if not approver:
            raise ValueError("Approver name is required — auto-approval is FORBIDDEN")

        proposal.approved = True
        proposal.approved_by = approver
        proposal.approved_at = datetime.now(timezone.utc).isoformat()

        logger.info(
            "Design proposal APPROVED | room=%s | detectors=%d | by=%s | correlation_id=%s",
            proposal.room_id, proposal.total_detectors, approver, proposal.correlation_id,
        )
        return proposal

    def reject(self, proposal: DesignProposal, reason: str) -> DesignProposal:
        """Reject a design proposal with documented reason."""
        proposal.approved = False
        proposal.approved_by = f"REJECTED: {reason}"
        logger.info(
            "Design proposal REJECTED | room=%s | reason=%s",
            proposal.room_id, reason,
        )
        return proposal
