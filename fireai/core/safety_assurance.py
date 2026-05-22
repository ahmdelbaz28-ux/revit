"""
safety_assurance.py — FireAI Safety Assurance Module
=====================================================

Adopted from the external consultant's Safety Assurance Architecture,
with modifications to fit FireAI's actual codebase and avoid over-engineering.

WHAT WE ADOPTED:
  1. 4-Tier Confidence Scoring (enhanced from our 3-tier)
  2. Fail-Safe behavior rules (never approve invalid designs)
  3. Override authorization matrix (who can override what)
  4. Human review checkpoint triggers
  5. Engineering evidence package structure

WHAT WE REJECTED:
  - Parser sandboxing (over-engineered for current scale)
  - Replay capability (requires code versioning we don't have yet)
  - Microservices decomposition (wrong for a 5-dev team)
  - Separate process for parser isolation (complexity not justified)

DESIGN PRINCIPLE (from consultant, which we agree with):
  "It is better to reject a valid design than to approve an invalid one."
  For a FIRE ALARM SYSTEM, false negatives (missed gaps) kill people.
  False positives (extra detectors) only cost money.

NFPA 72-2022 §17.7.4.2.3.1: Coverage radius R = 0.7 × S
"""

from __future__ import annotations

import enum
import hashlib
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════════
# 4-TIER CONFIDENCE SCORING
# ═══════════════════════════════════════════════════════════════════════════════

class SafetyTier(enum.Enum):
    """4-tier confidence scoring for fire safety designs.

    Adopted from consultant's Safety Assurance Architecture.
    Extends our existing 3-tier (VERIFIED/WARNING/FAIL) with a top
    PROOF_VERIFIED tier for designs with mathematical proof.

    TIER 1 — PROOF_VERIFIED: Mathematical proof passes, coverage ≥ 99.99%
      → APPROVE without review (green)

    TIER 2 — PROOF_VALID: Proof passes, coverage 99%–99.99%
      → FPE review recommended (yellow)

    TIER 3 — FALLBACK_USED: Heuristic placement, not proof-based
      → FPE review required (orange)

    TIER 4 — REJECTED: Coverage < 95%
      → Manual design required (red)

    RATIONALE:
      The existing 3-tier system (VERIFIED/WARNING/FAIL) was sufficient
      for engine agreement but didn't capture the quality of the proof
      itself. A design with 99.99% coverage and a valid proof is
      fundamentally safer than one with 99.1% coverage, even though
      both are "VERIFIED" by the engines. The 4th tier distinguishes
      mathematical certainty from statistical likelihood.
    """
    PROOF_VERIFIED = "PROOF_VERIFIED"  # Tier 1: coverage ≥ 99.99%
    PROOF_VALID = "PROOF_VALID"        # Tier 2: coverage 99%–99.99%
    FALLBACK_USED = "FALLBACK_USED"    # Tier 3: coverage 95%–99%
    REJECTED = "REJECTED"              # Tier 4: coverage < 95%


# Coverage thresholds (NFPA 72 aligned)
MINIMUM_COVERAGE_FOR_SUBMISSION = 95.0   # Below this = REJECTED
STANDARD_COVERAGE_THRESHOLD = 99.0       # Below this = FALLBACK_USED
PROOF_VERIFIED_THRESHOLD = 99.99         # Above this = PROOF_VERIFIED

# Absolute minimum coverage — CANNOT be overridden even by FPE
ABSOLUTE_MINIMUM_COVERAGE = 90.0


def classify_safety_tier(
    coverage_pct: float,
    proof_valid: bool = False,
    fallback_used: bool = False,
    wall_violations: int = 0,
) -> SafetyTier:
    """Classify a design into one of 4 safety tiers.

    This is the PRIMARY safety gate for all FireAI designs.
    No design should be submitted for AHJ review without
    first passing through this classification.

    Args:
        coverage_pct: Coverage percentage (0.0–100.0).
        proof_valid: Whether the mathematical proof passes.
        fallback_used: Whether heuristic fallback was used for placement.
        wall_violations: Number of wall distance violations.

    Returns:
        SafetyTier indicating the confidence level.

    Example:
        >>> classify_safety_tier(99.99, proof_valid=True)
        <SafetyTier.PROOF_VERIFIED: 'PROOF_VERIFIED'>
        >>> classify_safety_tier(97.0, fallback_used=True)
        <SafetyTier.FALLBACK_USED: 'FALLBACK_USED'>
    """
    # Tier 4: Absolute rejection
    if coverage_pct < MINIMUM_COVERAGE_FOR_SUBMISSION:
        return SafetyTier.REJECTED

    # Tier 3: Fallback/heuristic placement
    if fallback_used or coverage_pct < STANDARD_COVERAGE_THRESHOLD:
        return SafetyTier.FALLBACK_USED

    # Tier 2 vs Tier 1: Distinguished by proof quality
    if proof_valid and coverage_pct >= PROOF_VERIFIED_THRESHOLD:
        return SafetyTier.PROOF_VERIFIED

    # Tier 2: Valid proof but not at highest confidence
    if proof_valid:
        return SafetyTier.PROOF_VALID

    # No proof — treat as fallback even if coverage is good
    return SafetyTier.FALLBACK_USED


def tier_requires_fpe_review(tier: SafetyTier) -> bool:
    """Whether a safety tier requires Fire Protection Engineer review."""
    return tier in (SafetyTier.PROOF_VALID, SafetyTier.FALLBACK_USED)


def tier_can_submit(tier: SafetyTier) -> bool:
    """Whether a design at this tier can be submitted for AHJ review."""
    return tier in (SafetyTier.PROOF_VERIFIED, SafetyTier.PROOF_VALID)


# ═══════════════════════════════════════════════════════════════════════════════
# FAIL-SAFE BEHAVIOR RULES
# ═══════════════════════════════════════════════════════════════════════════════

class FailSafeRule:
    """Fail-safe rules for the FireAI system.

    Principle: "When in doubt, reject. When broken, stop. When unsure, escalate."

    Adopted from consultant's Fail-Safe Philosophy. These rules define
    how the system should respond to various failure modes.
    """

    # Component Failure → Response → System State
    RULES = {
        "parser_crash": {
            "response": "RETURN PARSE_FAILED",
            "system_state": "CONTINUE (isolated)",
            "description": "Parser failure is isolated — other rooms can still be analyzed.",
        },
        "coverage_below_95": {
            "response": "MARK UNSAFE + REJECT",
            "system_state": "HALT design submission",
            "description": "Insufficient coverage is a hard gate — design cannot proceed.",
        },
        "audit_chain_break": {
            "response": "HALT all operations",
            "system_state": "CRITICAL STOP",
            "description": "Broken audit chain means the system's integrity is compromised.",
        },
        "hmac_key_invalid": {
            "response": "HALT all operations",
            "system_state": "CRITICAL STOP",
            "description": "Invalid HMAC key means audit signatures cannot be verified.",
        },
        "db_connection_loss": {
            "response": "REJECT new requests",
            "system_state": "READ-ONLY MODE",
            "description": "Cannot persist results — reject new analysis to prevent data loss.",
        },
        "nfpa_parameter_out_of_range": {
            "response": "REJECT with standard reference",
            "system_state": "BLOCK design",
            "description": "Parameters outside NFPA 72 scope must be reviewed by FPE.",
        },
        "proof_verification_fails": {
            "response": "REJECT (not just warn)",
            "system_state": "NEVER approve invalid",
            "description": "Failed proof means coverage cannot be guaranteed.",
        },
    }


def apply_fail_safe(
    coverage_pct: Optional[float] = None,
    proof_valid: Optional[bool] = None,
    audit_chain_valid: Optional[bool] = None,
    hmac_key_valid: Optional[bool] = None,
) -> Dict[str, Any]:
    """Apply fail-safe rules and return a safety decision.

    This is the gate that ALL designs must pass before being submitted.
    It checks the most critical safety conditions first and fails fast.

    Args:
        coverage_pct: Coverage percentage (None = not calculated).
        proof_valid: Whether mathematical proof passes (None = not verified).
        audit_chain_valid: Whether audit chain is intact (None = not checked).
        hmac_key_valid: Whether HMAC key is properly configured (None = not checked).

    Returns:
        Dictionary with:
          - safe_to_submit: bool — whether the design can be submitted
          - tier: SafetyTier — confidence classification
          - reasons: List[str] — reasons for rejection (if any)
          - requires_fpe_review: bool — whether FPE review is needed
    """
    reasons = []

    # Critical stop conditions (checked first)
    if hmac_key_valid is False:
        return {
            "safe_to_submit": False,
            "tier": SafetyTier.REJECTED,
            "reasons": ["HMAC key invalid — system integrity compromised. HALT."],
            "requires_fpe_review": False,
            "system_state": "CRITICAL STOP",
        }

    if audit_chain_valid is False:
        return {
            "safe_to_submit": False,
            "tier": SafetyTier.REJECTED,
            "reasons": ["Audit chain broken — system integrity compromised. HALT."],
            "requires_fpe_review": False,
            "system_state": "CRITICAL STOP",
        }

    # Coverage checks
    if coverage_pct is not None:
        if coverage_pct < ABSOLUTE_MINIMUM_COVERAGE:
            reasons.append(
                f"Coverage {coverage_pct:.1f}% is below absolute minimum "
                f"{ABSOLUTE_MINIMUM_COVERAGE}%. Cannot override."
            )
            return {
                "safe_to_submit": False,
                "tier": SafetyTier.REJECTED,
                "reasons": reasons,
                "requires_fpe_review": True,
            }

        if proof_valid is False:
            reasons.append("Mathematical proof failed — coverage cannot be guaranteed.")

    # Classify tier
    tier = classify_safety_tier(
        coverage_pct=coverage_pct or 0.0,
        proof_valid=proof_valid or False,
        fallback_used=False,
    )

    # Final decision
    safe = tier_can_submit(tier) and len(reasons) == 0

    return {
        "safe_to_submit": safe,
        "tier": tier,
        "reasons": reasons,
        "requires_fpe_review": tier_requires_fpe_review(tier) or len(reasons) > 0,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# OVERRIDE AUTHORIZATION MATRIX
# ═══════════════════════════════════════════════════════════════════════════════

class OverrideRole(enum.Enum):
    """Roles that can override safety decisions."""
    FPE = "fpe"              # Fire Protection Engineer
    SENIOR_ENGINEER = "senior_engineer"
    JUNIOR_ENGINEER = "junior_engineer"
    SYSTEM = "system"        # System itself (never allowed to override)


# What CANNOT be overridden — ever
NON_OVERRIDABLE = {
    "proof_valid_false",       # Failed proof is never acceptable
    "coverage_below_90",       # Absolute minimum
    "audit_chain_broken",      # System integrity
    "hmac_key_invalid",        # System integrity
}


# What CAN be overridden and by whom
OVERRIDE_PERMISSIONS = {
    OverrideRole.FPE: {
        "coverage_threshold",   # Can lower to 90% minimum
        "wall_distance",        # Can waive with justification
        "detector_type",        # Can change with NFPA reference
        "spacing_calculation",  # Can adjust with manual verification
    },
    OverrideRole.SENIOR_ENGINEER: {
        "coverage_threshold",   # Can lower to 90% for standard rooms only
    },
    OverrideRole.JUNIOR_ENGINEER: set(),  # No overrides allowed
    OverrideRole.SYSTEM: set(),  # System CANNOT override
}


@dataclass
class OverrideRecord:
    """Record of a safety override for audit trail.

    All overrides must be documented with:
      - Who requested it
      - Who approved it
      - Why (justification, min 50 chars)
      - NFPA 72 section reference
      - What was changed (previous and new values)
    """
    override_id: str
    override_type: str
    requested_by: str
    approved_by: str
    justification: str
    nfpa_reference: str
    previous_value: Any
    requested_value: Any
    final_value: Any
    timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    risk_acknowledged: bool = False

    def __post_init__(self):
        if len(self.justification) < 50:
            raise ValueError(
                f"Override justification must be at least 50 characters, "
                f"got {len(self.justification)}: '{self.justification}'"
            )
        if self.override_type in NON_OVERRIDABLE:
            raise ValueError(
                f"Override type '{self.override_type}' is NON-OVERRIDABLE. "
                f"This is a safety-critical limit that cannot be changed."
            )


# ═══════════════════════════════════════════════════════════════════════════════
# HUMAN REVIEW CHECKPOINTS
# ═══════════════════════════════════════════════════════════════════════════════

# Conditions that trigger mandatory human review
MANDATORY_REVIEW_TRIGGERS = {
    "coverage_below_99": {
        "reviewer": "FPE",
        "timeout_hours": 48,
        "description": "Coverage below 99% requires FPE review",
    },
    "non_rectangular_room": {
        "reviewer": "FPE",
        "timeout_hours": 48,
        "description": "Non-rectangular rooms require FPE review",
    },
    "ceiling_height_above_10m": {
        "reviewer": "FPE",
        "timeout_hours": 48,
        "description": "Ceiling height > 10m requires FPE review",
    },
    "override_used": {
        "reviewer": "FPE + Senior Engineer",
        "timeout_hours": 24,
        "description": "Any override requires dual approval",
    },
    "system_confidence_below_80": {
        "reviewer": "FPE",
        "timeout_hours": 48,
        "description": "Low system confidence requires FPE review",
    },
    "more_than_10pct_rooms_flagged": {
        "reviewer": "Senior FPE",
        "timeout_hours": 72,
        "description": "Building-wide issue requires senior review",
    },
}


def check_review_triggers(
    coverage_pct: float = 100.0,
    room_shape: str = "rectangular",
    ceiling_height_m: float = 3.0,
    override_used: bool = False,
    confidence_score: float = 100.0,
    total_rooms: int = 1,
    flagged_rooms: int = 0,
) -> List[Dict[str, Any]]:
    """Check if any mandatory review triggers are activated.

    Args:
        coverage_pct: Room coverage percentage.
        room_shape: "rectangular" or other.
        ceiling_height_m: Ceiling height in meters.
        override_used: Whether an override was applied.
        confidence_score: System confidence score (0–100).
        total_rooms: Total rooms in building.
        flagged_rooms: Rooms flagged for review.

    Returns:
        List of triggered review requirements.
    """
    triggers = []

    if coverage_pct < 99.0:
        triggers.append({
            **MANDATORY_REVIEW_TRIGGERS["coverage_below_99"],
            "actual_value": f"coverage={coverage_pct:.1f}%",
        })

    if room_shape != "rectangular":
        triggers.append({
            **MANDATORY_REVIEW_TRIGGERS["non_rectangular_room"],
            "actual_value": f"shape={room_shape}",
        })

    if ceiling_height_m > 10.0:
        triggers.append({
            **MANDATORY_REVIEW_TRIGGERS["ceiling_height_above_10m"],
            "actual_value": f"height={ceiling_height_m:.1f}m",
        })

    if override_used:
        triggers.append({
            **MANDATORY_REVIEW_TRIGGERS["override_used"],
            "actual_value": "override_applied=True",
        })

    if confidence_score < 80.0:
        triggers.append({
            **MANDATORY_REVIEW_TRIGGERS["system_confidence_below_80"],
            "actual_value": f"confidence={confidence_score:.1f}",
        })

    if total_rooms > 0 and (flagged_rooms / total_rooms) > 0.10:
        triggers.append({
            **MANDATORY_REVIEW_TRIGGERS["more_than_10pct_rooms_flagged"],
            "actual_value": f"flagged={flagged_rooms}/{total_rooms}",
        })

    return triggers


# ═══════════════════════════════════════════════════════════════════════════════
# ENGINEERING EVIDENCE PACKAGE
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class EngineeringEvidencePackage:
    """Engineering evidence package for AHJ submission.

    Adopted from consultant's architecture. This structure ensures
    that all necessary information is captured for regulatory review.

    Each package contains:
      - Room geometry (polygon coordinates, area, ceiling)
      - Detector placement (positions, types, spacing calculations)
      - Compliance verification (NFPA 72 references, coverage %)
      - Proof certificate (mathematical proof of coverage)
      - Audit trail (hash chain, HMAC signatures)
      - Signatures (engineer, FPE, system authenticity)
    """
    package_id: str
    room_id: str
    room_polygon: List[Tuple[float, float]]
    room_area_m2: float
    ceiling_height_m: float
    ceiling_type: str
    occupancy_type: str

    # Detector placement
    detector_positions: List[Tuple[float, float]]
    detector_type: str
    spacing_m: float
    coverage_radius_m: float

    # Compliance
    coverage_pct: float
    wall_violations: int
    nfpa_references: List[str]
    compliance_status: str

    # Proof
    proof_valid: bool
    proof_hash: Optional[str] = None
    safety_tier: str = ""

    # Audit
    audit_chain_valid: bool = False
    audit_event_count: int = 0

    # Signatures
    engineer_signature: Optional[str] = None
    fpe_review_signature: Optional[str] = None
    system_certificate: Optional[str] = None

    # Metadata
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    algorithm_version: str = "V20.2"

    def compute_integrity_hash(self) -> str:
        """Compute SHA-256 hash of the entire evidence package for integrity."""
        payload = json.dumps({
            "package_id": self.package_id,
            "room_id": self.room_id,
            "detector_positions": self.detector_positions,
            "coverage_pct": self.coverage_pct,
            "proof_valid": self.proof_valid,
            "safety_tier": self.safety_tier,
            "algorithm_version": self.algorithm_version,
        }, sort_keys=True)
        return hashlib.sha256(payload.encode()).hexdigest()


# ═══════════════════════════════════════════════════════════════════════════════
# MODULE EXPORTS
# ═══════════════════════════════════════════════════════════════════════════════

__all__ = [
    "SafetyTier",
    "classify_safety_tier",
    "tier_requires_fpe_review",
    "tier_can_submit",
    "FailSafeRule",
    "apply_fail_safe",
    "OverrideRole",
    "OverrideRecord",
    "NON_OVERRIDABLE",
    "OVERRIDE_PERMISSIONS",
    "MANDATORY_REVIEW_TRIGGERS",
    "check_review_triggers",
    "EngineeringEvidencePackage",
    "ABSOLUTE_MINIMUM_COVERAGE",
    "MINIMUM_COVERAGE_FOR_SUBMISSION",
    "STANDARD_COVERAGE_THRESHOLD",
    "PROOF_VERIFIED_THRESHOLD",
]
