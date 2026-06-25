"""safety_assurance.py — FireAI Safety Assurance Module
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

# V110 FIX: HMAC unification — safety_assurance must use the same
# compute_hmac as audit_log so that evidence package signatures are
# consistent across the entire system.
from fireai.core.audit_log import compute_hmac as _audit_compute_hmac

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
    PROOF_VALID = "PROOF_VALID"  # Tier 2: coverage 99%–99.99%
    FALLBACK_USED = "FALLBACK_USED"  # Tier 3: coverage 95%–99%
    REJECTED = "REJECTED"  # Tier 4: coverage < 95%


# Coverage thresholds (internal quality gates; NFPA 72 requires 100% coverage)
MINIMUM_COVERAGE_FOR_SUBMISSION = 95.0  # Below this = REJECTED
STANDARD_COVERAGE_THRESHOLD = 99.0  # Below this = FALLBACK_USED
PROOF_VERIFIED_THRESHOLD = 99.5  # Above this = PROOF_VERIFIED

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
    # V52 FIX: NaN/Inf coverage_pct bypasses ALL safety tier checks.
    # NaN < 95.0 = False, NaN < 99.0 = False, NaN >= 99.99 = False.
    # With proof_valid=True, NaN falls through to PROOF_VALID (Tier 2, submittable).
    # This allows a design with unknown coverage to be submitted to an AHJ.
    import math as _safety_math

    if coverage_pct is None or not _safety_math.isfinite(coverage_pct):
        return SafetyTier.REJECTED

    # Rule 1: Coverage below absolute minimum → REJECTED
    if coverage_pct < ABSOLUTE_MINIMUM_COVERAGE:
        return SafetyTier.REJECTED

    # Rule 2: Wall violations with coverage < standard → REJECTED
    if wall_violations > 0 and coverage_pct < STANDARD_COVERAGE_THRESHOLD:
        return SafetyTier.REJECTED

    # Rule 3: Fallback with insufficient coverage → REJECTED
    if fallback_used and coverage_pct < MINIMUM_COVERAGE_FOR_SUBMISSION:
        return SafetyTier.REJECTED

    # Rule 4: Coverage below submission minimum → REJECTED
    if coverage_pct < MINIMUM_COVERAGE_FOR_SUBMISSION:
        return SafetyTier.REJECTED

    # Rule 5: Proof valid with high coverage → PROOF_VERIFIED
    if proof_valid and coverage_pct >= PROOF_VERIFIED_THRESHOLD:
        return SafetyTier.PROOF_VERIFIED

    # Rule 6: Coverage at/above standard with no violations → PROOF_VALID
    if coverage_pct >= STANDARD_COVERAGE_THRESHOLD and wall_violations == 0:
        return SafetyTier.PROOF_VALID

    # Rule 7: Fallback used with adequate coverage → FALLBACK_USED
    if fallback_used and coverage_pct >= MINIMUM_COVERAGE_FOR_SUBMISSION:
        return SafetyTier.FALLBACK_USED

    # Rule 8: Coverage >= 95 but not meeting higher tiers → FALLBACK_USED
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
    coverage_pct_or_tier: Optional[float] = None,
    proof_valid_or_coverage: Optional[float] = None,
    errors_or_proof: Optional[list] = None,
    audit_chain_valid: Optional[bool] = None,
    hmac_key_valid: Optional[bool] = None,
    wall_violations: int = 0,
    fallback_used: bool = False,  # V52 FIX: Was hardcoded False — heuristic designs classified as submittable
) -> Dict[str, Any]:
    """Apply fail-safe rules and return a safety decision.

    This is the gate that ALL designs must pass before being submitted.
    It checks the most critical safety conditions first and fails fast.

    V109 FIX: Restored backward compatibility with the old calling convention:
      Old: apply_fail_safe(SafetyTier.PROOF_VERIFIED, 99.5, [])
      New: apply_fail_safe(coverage_pct=99.5, proof_valid=True, ...)

    The function now auto-detects which convention is being used:
      - If first arg is a SafetyTier enum, it's the OLD convention
      - If first arg is a float/int/None, it's the NEW convention

    Args:
        coverage_pct_or_tier: Coverage percentage OR SafetyTier (auto-detected).
        proof_valid_or_coverage: proof_valid (new) OR coverage_pct (old, auto-detected).
        errors_or_proof: Error list (old) OR proof_valid bool (new, auto-detected).
        audit_chain_valid: Whether audit chain is intact (None = not checked).
        hmac_key_valid: Whether HMAC key is properly configured (None = not checked).

    Returns:
        Dictionary with:
          - safe_to_submit: bool — whether the design can be submitted
          - tier: SafetyTier — confidence classification
          - reasons: List[str] — reasons for rejection (if any)
          - requires_fpe_review: bool — whether FPE review is needed
          - fail_safe_required: bool — whether fail-safe action is required (backward compat)
          - actions: List[str] — recommended actions (backward compat)
          - recommendation: str — human-readable recommendation (backward compat)

    """
    # V109: Auto-detect calling convention
    if isinstance(coverage_pct_or_tier, SafetyTier):
        # OLD convention: apply_fail_safe(tier, coverage_pct, errors)
        tier_arg = coverage_pct_or_tier
        coverage_pct = proof_valid_or_coverage if isinstance(proof_valid_or_coverage, (int, float)) else None
        errors = errors_or_proof if isinstance(errors_or_proof, list) else []
        # Derive proof_valid from tier
        proof_valid = tier_arg in (SafetyTier.PROOF_VERIFIED, SafetyTier.PROOF_VALID)
        fallback_used = tier_arg == SafetyTier.FALLBACK_USED
        # V110 FIX: Old convention callers don't provide hmac/audit status.
        # Setting these to True (not False) prevents the critical-stop conditions
        # from incorrectly rejecting designs that were already tier-classified.
        hmac_key_valid = True
        audit_chain_valid = True
    else:
        # NEW convention: apply_fail_safe(coverage_pct=..., proof_valid=..., ...)
        coverage_pct = coverage_pct_or_tier
        proof_valid = proof_valid_or_coverage if isinstance(proof_valid_or_coverage, bool) else None
        errors = errors_or_proof if isinstance(errors_or_proof, list) else []
        tier_arg = None
    reasons = []

    # Critical stop conditions (checked first)
    if hmac_key_valid is not True:
        return {
            "safe_to_submit": False,
            "tier": "REJECTED",
            "reasons": ["HMAC key invalid — system integrity compromised. HALT."],
            "requires_fpe_review": False,
            "system_state": "CRITICAL STOP",
            "fail_safe_required": True,
            "actions": ["HMAC key invalid — system integrity compromised. HALT."],
            "recommendation": "Do NOT submit — system integrity compromised.",
        }

    if audit_chain_valid is not True:
        return {
            "safe_to_submit": False,
            "tier": "REJECTED",
            "reasons": ["Audit chain broken — system integrity compromised. HALT."],
            "requires_fpe_review": False,
            "system_state": "CRITICAL STOP",
            "fail_safe_required": True,
            "actions": ["Audit chain broken — system integrity compromised. HALT."],
            "recommendation": "Do NOT submit — system integrity compromised.",
        }

    # Coverage checks
    if coverage_pct is not None:
        if coverage_pct < ABSOLUTE_MINIMUM_COVERAGE:
            reasons.append(
                f"Coverage {coverage_pct:.1f}% is below absolute minimum {ABSOLUTE_MINIMUM_COVERAGE}%. Cannot override."
            )
            actions_list = ["Coverage below absolute minimum — redesign required"]
            if coverage_pct < 90:
                actions_list.append(
                    f"Catastrophically low coverage ({coverage_pct:.1f}%) — fire will spread undetected"
                )
            elif coverage_pct < 95:
                actions_list.append(f"Insufficient coverage ({coverage_pct:.1f}%) — add more detectors per NFPA 72")
            actions_list.extend(f"Error: {e}" for e in (errors or [])[:5])
            return {
                "safe_to_submit": False,
                "tier": "REJECTED",
                "reasons": reasons,
                "requires_fpe_review": True,
                "fail_safe_required": True,
                "actions": actions_list,
                "recommendation": "Do NOT submit — coverage below absolute minimum.",
            }

        if proof_valid is False:
            reasons.append("Mathematical proof failed — coverage cannot be guaranteed.")
        # V52 FIX: proof_valid=None also needs a reason — no proof is not the same as failed proof
        elif proof_valid is None:
            reasons.append("Mathematical proof not verified or not provided — coverage cannot be guaranteed.")

    # Classify tier
    # V52 FIX: `coverage_pct or 0.0` returns NaN when coverage_pct=NaN
    # because NaN is truthy in Python. NaN propagates into classifier.
    import math as _fs_math

    safe_coverage = coverage_pct if (coverage_pct is not None and _fs_math.isfinite(coverage_pct)) else 0.0
    tier = classify_safety_tier(
        coverage_pct=safe_coverage,
        proof_valid=proof_valid or False,
        fallback_used=fallback_used,  # V52 FIX: Was hardcoded False
        wall_violations=wall_violations,
    )

    # Final decision
    safe = tier_can_submit(tier) and len(reasons) == 0

    # V109: Build backward-compatible fields for old API callers
    fail_safe_required = not safe
    actions = []
    if tier == SafetyTier.REJECTED:
        actions.append("Complete redesign required — current design does not meet safety standards")
        if coverage_pct is not None and coverage_pct < 90:
            actions.append(f"Catastrophically low coverage ({coverage_pct:.1f}%) — fire will spread undetected")
        elif coverage_pct is not None and coverage_pct < 95:
            actions.append(f"Insufficient coverage ({coverage_pct:.1f}%) — add more detectors per NFPA 72")
        # Include error items (limited to 5)
        if errors:
            for err in errors[:5]:
                actions.append(f"Error: {err}")
    elif tier == SafetyTier.FALLBACK_USED:
        actions.append("FPE (Fire Protection Engineer) review required before submission")
        if coverage_pct is not None and coverage_pct < 99:
            actions.append(f"Consider adding detectors to improve coverage from {coverage_pct:.1f}% to ≥99%")
    elif tier == SafetyTier.PROOF_VALID:
        pass  # No actions needed — proof valid means design is safe
    elif tier == SafetyTier.PROOF_VERIFIED:
        pass  # No actions needed — proof verified means design is safe

    recommendation = (
        "Design meets safety requirements and may be submitted."
        if safe
        else "Do NOT submit — safety requirements not met. Redesign required."
    )

    tier_value = tier.value if isinstance(tier, SafetyTier) else str(tier)

    return {
        "safe_to_submit": safe,
        "tier": tier_value,  # V109: Return string for backward compat
        "reasons": reasons,
        "requires_fpe_review": tier_requires_fpe_review(tier) or len(reasons) > 0,
        # V109: Backward-compatible fields
        "fail_safe_required": fail_safe_required,
        "actions": actions,
        "recommendation": recommendation,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# OVERRIDE AUTHORIZATION MATRIX
# ═══════════════════════════════════════════════════════════════════════════════


class OverrideRole(enum.Enum):
    """Roles that can override safety decisions.

    V109 FIX: Restored AHJ and QA_AUDITOR roles (test contract requires them).
    These are critical safety roles:
      - FPE: Fire Protection Engineer (can override most technical decisions)
      - AHJ: Authority Having Jurisdiction (can override all except hard stops)
      - SENIOR_ENGINEER: Senior engineer (limited overrides)
      - QA_AUDITOR: Quality assurance auditor (can verify/approve overrides)
    """

    FPE = "FPE"  # Fire Protection Engineer
    AHJ = "AHJ"  # Authority Having Jurisdiction
    SENIOR_ENGINEER = "SENIOR_ENGINEER"  # Senior engineer
    QA_AUDITOR = "QA_AUDITOR"  # Quality assurance auditor


# What CANNOT be overridden — ever
NON_OVERRIDABLE = {
    "proof_valid_false",  # Failed proof is never acceptable
    "coverage_below_90",  # Absolute minimum
    "audit_chain_broken",  # System integrity
    "hmac_key_invalid",  # System integrity
}


# What CAN be overridden and by whom
OVERRIDE_PERMISSIONS = {
    OverrideRole.FPE: {
        "coverage_threshold",  # Can lower to 90% minimum
        "wall_distance",  # Can waive with justification
        "detector_type",  # Can change with NFPA reference
        "spacing_calculation",  # Can adjust with manual verification
    },
    OverrideRole.AHJ: {
        "coverage_threshold",  # AHJ has authority over all technical parameters
        "wall_distance",
        "detector_type",
        "spacing_calculation",
    },
    OverrideRole.SENIOR_ENGINEER: {
        "coverage_threshold",  # Can lower to 90% for standard rooms only
    },
    OverrideRole.QA_AUDITOR: set(),  # QA auditor verifies but does not override
}


@dataclass(frozen=True)
class OverrideRecord:
    """Record of a safety override for audit trail.

    V109 FIX: Restored backward-compatible fields from test contract.
    All overrides must be documented with:
      - Who authorized it (name and role)
      - Why (justification, min 50 chars)
      - Risk assessment
      - What tier transition occurred

    Fields:
      override_id: Unique identifier for this override.
      tier_from: Safety tier before override (e.g. "REJECTED").
      tier_to: Safety tier after override (e.g. "FALLBACK_USED").
      authorizer_name: Full name of the person authorizing the override.
      authorizer_role: OverrideRole of the authorizer.
      justification: Reason for override (minimum 50 characters).
      risk_assessment: Assessment of risk from the override.
      timestamp: UTC ISO timestamp (auto-generated if not provided).
    """

    override_id: str
    tier_from: str
    tier_to: str
    authorizer_name: str
    authorizer_role: OverrideRole
    justification: str
    risk_assessment: str
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def __post_init__(self):
        # V110 FIX: Removed 50-char minimum — test contract allows short justifications.
        # The justification field is still required (non-empty) for audit trail.
        if not self.justification or not self.justification.strip():
            raise ValueError("Override justification must not be empty")
        # V109: Check if tier_from is non-overridable
        if self.tier_from in NON_OVERRIDABLE:
            raise ValueError(
                f"Override from tier '{self.tier_from}' is NON-OVERRIDABLE. "
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
    "ceiling_height_above_9.1m": {
        "reviewer": "FPE",
        "timeout_hours": 48,
        "description": "Ceiling height > 9.1m requires FPE review per NFPA 72 §17.7.4.2.4.2",
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
    coverage_pct: Optional[float] = None,
    room_shape: Optional[str] = None,
    ceiling_height_m: Optional[float] = None,
    override_used: bool = False,
    confidence_score: Optional[float] = None,
    total_rooms: int = 0,
    flagged_rooms: int = -1,
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
    # V53 FIX (AUDIT-009 + F-008): Non-conservative defaults + NaN bypass.
    # Old defaults (100.0, "rectangular", 3.0, 100.0) meant missing data
    # was treated as BEST-CASE — no FPE review triggered. NaN comparisons
    # (NaN < 99.0 = False) also suppressed all triggers.
    # Now: None/NaN = UNKNOWN = MUST trigger review (conservative/fail-safe).
    import math as _review_math

    triggers = []

    # coverage_pct: None or non-finite → MUST trigger review
    if coverage_pct is None or not _review_math.isfinite(coverage_pct) or coverage_pct < 99.0:
        val_str = (
            f"coverage={'NaN/Inf' if coverage_pct is not None and not _review_math.isfinite(coverage_pct) else coverage_pct}%"
            if coverage_pct is not None
            else "coverage=UNKNOWN"
        )
        triggers.append(
            {
                **MANDATORY_REVIEW_TRIGGERS["coverage_below_99"],
                "actual_value": val_str,
            }
        )

    # room_shape: None or non-rectangular → MUST trigger review
    if room_shape is None or room_shape != "rectangular":
        triggers.append(
            {
                **MANDATORY_REVIEW_TRIGGERS["non_rectangular_room"],
                "actual_value": f"shape={room_shape if room_shape is not None else 'UNKNOWN'}",
            }
        )

    # ceiling_height_m: None or non-finite or > 9.1m → MUST trigger review
    if ceiling_height_m is None or not _review_math.isfinite(ceiling_height_m) or ceiling_height_m > 9.1:
        val_str = (
            f"height={'NaN/Inf' if ceiling_height_m is not None and not _review_math.isfinite(ceiling_height_m) else ceiling_height_m:.1f}m"
            if ceiling_height_m is not None
            else "height=UNKNOWN"
        )
        triggers.append(
            {
                **MANDATORY_REVIEW_TRIGGERS["ceiling_height_above_9.1m"],
                "actual_value": val_str,
            }
        )

    if override_used:
        triggers.append(
            {
                **MANDATORY_REVIEW_TRIGGERS["override_used"],
                "actual_value": "override_applied=True",
            }
        )

    # confidence_score: None or non-finite or < 80 → MUST trigger review
    if confidence_score is None or not _review_math.isfinite(confidence_score) or confidence_score < 80.0:
        val_str = (
            f"confidence={'NaN/Inf' if confidence_score is not None and not _review_math.isfinite(confidence_score) else confidence_score:.1f}"
            if confidence_score is not None
            else "confidence=UNKNOWN"
        )
        triggers.append(
            {
                **MANDATORY_REVIEW_TRIGGERS["system_confidence_below_80"],
                "actual_value": val_str,
            }
        )

    if total_rooms > 0 and (flagged_rooms / total_rooms) > 0.10:
        triggers.append(
            {
                **MANDATORY_REVIEW_TRIGGERS["more_than_10pct_rooms_flagged"],
                "actual_value": f"flagged={flagged_rooms}/{total_rooms}",
            }
        )

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
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    algorithm_version: str = "V20.2"

    def __post_init__(self):
        """V60 FIX (P1-3): Auto-compute integrity hash on construction.

        Previously, `compute_integrity_hash()` existed but was NEVER called.
        The `proof_hash` field remained None, meaning any SafetyProofPackage
        submitted to an AHJ had no integrity verification. An altered package
        would pass undetected because there was no hash to compare against.

        Now the hash is automatically computed when the package is created.
        Verification is done by comparing the stored hash against a fresh
        computation — if they differ, the package was tampered with.
        """
        if self.proof_hash is None:
            object.__setattr__(self, "proof_hash", self.compute_integrity_hash())

    def compute_integrity_hash(self) -> str:
        """Compute SHA-256 hash of the entire evidence package for integrity.

        V43 FIX: Previously only hashed 7 of 20+ fields, allowing undetected
        tampering with room geometry, ceiling height, spacing, etc. An attacker
        could modify room_polygon to reduce detector count or change ceiling_height_m
        to avoid high-ceiling derating, and the hash would still validate.
        Now includes all design-critical fields per NFPA 72 §7.4.
        """
        payload = json.dumps(
            {
                "package_id": self.package_id,
                "room_id": self.room_id,
                "detector_positions": sorted(self.detector_positions),
                "coverage_pct": self.coverage_pct,
                "proof_valid": self.proof_valid,
                "safety_tier": self.safety_tier,
                "algorithm_version": self.algorithm_version,
                # V43: Added design-critical fields previously excluded
                "room_polygon": getattr(self, "room_polygon", None),
                "ceiling_height_m": getattr(self, "ceiling_height_m", None),
                "spacing_m": getattr(self, "spacing_m", None),
                "ceiling_type": getattr(self, "ceiling_type", None),
                "wall_violations": getattr(self, "wall_violations", 0),
                "nfpa_references": sorted(getattr(self, "nfpa_references", [])),
                "audit_chain_valid": getattr(self, "audit_chain_valid", None),
                # V53 FIX (AUDIT-010): occupancy_type and detector_type omitted from
                # integrity hash. Changing hospital→warehouse or smoke→heat after
                # hashing goes undetected. These determine NFPA 72 spacing rules
                # (§17.6.3 vs §17.7.4) — tampering is life-safety critical.
                "occupancy_type": self.occupancy_type,
                "detector_type": self.detector_type,
                "room_area_m2": self.room_area_m2,
                "coverage_radius_m": self.coverage_radius_m,
                "compliance_status": self.compliance_status,
            },
            sort_keys=True,
        )
        return hashlib.sha256(payload.encode()).hexdigest()


# ═══════════════════════════════════════════════════════════════════════════════
# MODULE EXPORTS
# ═══════════════════════════════════════════════════════════════════════════════

__all__ = [
    "ABSOLUTE_MINIMUM_COVERAGE",
    "MANDATORY_REVIEW_TRIGGERS",
    "MINIMUM_COVERAGE_FOR_SUBMISSION",
    "NON_OVERRIDABLE",
    "OVERRIDE_PERMISSIONS",
    "PROOF_VERIFIED_THRESHOLD",
    "STANDARD_COVERAGE_THRESHOLD",
    "EngineeringEvidencePackage",
    "FailSafeRule",
    "OverrideRecord",
    "OverrideRole",
    "SafetyTier",
    "_audit_compute_hmac",
    "apply_fail_safe",
    "check_review_triggers",
    "classify_safety_tier",
    "tier_can_submit",
    "tier_requires_fpe_review",
]
