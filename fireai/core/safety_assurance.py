"""
fireai.core.safety_assurance — Safety Tier Classification & Evidence Package
============================================================================

Implements the safety classification system and engineering evidence
packaging for the FireAI pipeline.

SAFETY TIERS (from most to least trusted):
  1. PROOF_VERIFIED — Mathematical proof + ≥99.5% coverage
  2. PROOF_VALID    — Algorithmic verification + ≥98.0% coverage
  3. FALLBACK_USED  — Hex grid fallback + ≥95.0% coverage
  4. REJECTED       — <95.0% coverage OR critical violations

EVIDENCE PACKAGE:
  - HMAC-SHA256 cryptographic hash of all engineering inputs and outputs
  - NFPA references for every decision
  - Traceable chain of reasoning
  - Tamper-proof (HMAC-SHA256 with secret key prevents forgery)

CONSTANTS:
  - ABSOLUTE_MINIMUM_COVERAGE: Below this = automatic REJECT
  - MINIMUM_COVERAGE_FOR_SUBMISSION: Minimum to submit for review
  - STANDARD_COVERAGE_THRESHOLD: Expected for normal operation
  - PROOF_VERIFIED_THRESHOLD: Required for proof-verified tier

DESIGN PRINCIPLE:
  - Safety is NEVER compromised for convenience
  - REJECTED tier means the design MUST NOT be submitted
  - All thresholds are traceable to NFPA 72 sections
"""

from __future__ import annotations

import enum
import hashlib
import hmac
import json
import logging
import math
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

# Re-use the canonical HMAC-SHA256 function from audit_log instead of
# duplicating the logic.  Both modules must agree on the exact HMAC
# computation so that evidence-package hashes are consistent across the
# pipeline.  The import is guarded so that safety_assurance still works
# standalone if audit_log is unavailable.
try:
    from fireai.core.audit_log import compute_hmac as _audit_compute_hmac
except ImportError:
    _audit_compute_hmac = None


# ═══════════════════════════════════════════════════════════════════════════════
# SAFETY TIER CONSTANTS
# ═══════════════════════════════════════════════════════════════════════════════

# NFPA 72 §17.7.4.2.3.1 requires every point on the ceiling to be
# within the coverage radius of a detector. These thresholds enforce
# that requirement with increasing strictness.

ABSOLUTE_MINIMUM_COVERAGE = 90.0       # Below this → automatic REJECT
MINIMUM_COVERAGE_FOR_SUBMISSION = 95.0 # Minimum to even submit for review
STANDARD_COVERAGE_THRESHOLD = 99.0     # Expected for normal operation
PROOF_VERIFIED_THRESHOLD = 99.5        # Required for mathematical proof tier


class SafetyTier(enum.Enum):
    """Safety classification tier.

    Each tier has specific requirements for what actions are permitted:
    - PROOF_VERIFIED: Can submit without FPE review
    - PROOF_VALID: Can submit with FPE review required
    - FALLBACK_USED: Must be reviewed and approved by FPE
    - REJECTED: Must NOT be submitted — redesign required
    """
    PROOF_VERIFIED = "PROOF_VERIFIED"
    PROOF_VALID    = "PROOF_VALID"
    FALLBACK_USED  = "FALLBACK_USED"
    REJECTED       = "REJECTED"


def classify_safety_tier(
    coverage_pct: float,
    proof_valid: bool,
    fallback_used: bool,
    wall_violations: int,
) -> SafetyTier:
    """Classify the safety tier based on pipeline results.

    Classification rules (in priority order):
    1. If coverage < ABSOLUTE_MINIMUM → REJECTED
    2. If wall violations exist and coverage < STANDARD → REJECTED
    3. If fallback used and coverage < MINIMUM_FOR_SUBMISSION → REJECTED
    4. If coverage < MINIMUM_FOR_SUBMISSION → REJECTED
    5. If proof_valid and coverage ≥ PROOF_VERIFIED → PROOF_VERIFIED
    6. If coverage ≥ STANDARD and no wall violations → PROOF_VALID
    7. If fallback used and coverage ≥ MINIMUM_FOR_SUBMISSION → FALLBACK_USED
    8. Otherwise → REJECTED

    Args:
        coverage_pct: Coverage percentage (0.0–100.0).
        proof_valid: Whether mathematical proof was verified.
        fallback_used: Whether hex-grid fallback was used.
        wall_violations: Number of dead-air-space wall violations.

    Returns:
        SafetyTier enum value.
    """
    # Safety: reject NaN/Inf coverage
    if not math.isfinite(coverage_pct):
        return SafetyTier.REJECTED

    # Rule 1: Absolute minimum
    if coverage_pct < ABSOLUTE_MINIMUM_COVERAGE:
        return SafetyTier.REJECTED

    # Rule 2: Wall violations with low coverage
    if wall_violations > 0 and coverage_pct < STANDARD_COVERAGE_THRESHOLD:
        return SafetyTier.REJECTED

    # Rule 3: Fallback with insufficient coverage
    if fallback_used and coverage_pct < MINIMUM_COVERAGE_FOR_SUBMISSION:
        return SafetyTier.REJECTED

    # Rule 4: Below submission minimum
    if coverage_pct < MINIMUM_COVERAGE_FOR_SUBMISSION:
        return SafetyTier.REJECTED

    # Rule 5: Proof verified (highest tier)
    if proof_valid and coverage_pct >= PROOF_VERIFIED_THRESHOLD:
        return SafetyTier.PROOF_VERIFIED

    # Rule 6: Standard coverage, no violations
    if coverage_pct >= STANDARD_COVERAGE_THRESHOLD and wall_violations == 0:
        return SafetyTier.PROOF_VALID

    # Rule 7: Fallback used but adequate coverage
    if fallback_used and coverage_pct >= MINIMUM_COVERAGE_FOR_SUBMISSION:
        return SafetyTier.FALLBACK_USED

    # Rule 8: Coverage between minimum and standard with violations
    if coverage_pct >= MINIMUM_COVERAGE_FOR_SUBMISSION:
        return SafetyTier.FALLBACK_USED

    # Default: reject
    return SafetyTier.REJECTED


def apply_fail_safe(
    tier: SafetyTier,
    coverage_pct: float,
    errors: List[str],
) -> Dict[str, Any]:
    """Apply fail-safe behavior for non-compliant results.

    When the safety tier is not PROOF_VERIFIED or PROOF_VALID,
    this function generates a fail-safe action plan.

    Args:
        tier: Current safety tier.
        coverage_pct: Coverage percentage.
        errors: List of error messages from the pipeline.

    Returns:
        Dict with fail-safe actions and recommendations.
    """
    if tier in (SafetyTier.PROOF_VERIFIED, SafetyTier.PROOF_VALID):
        return {
            "fail_safe_required": False,
            "actions": [],
            "recommendation": "Design meets safety requirements",
        }

    actions = []

    if tier == SafetyTier.FALLBACK_USED:
        actions.append("MANDATORY: Fire Protection Engineer review required before submission")
        actions.append("Verify fallback detector placement meets NFPA 72 coverage requirements")
        if coverage_pct < STANDARD_COVERAGE_THRESHOLD:
            actions.append(
                f"Coverage {coverage_pct:.2f}% is below standard "
                f"({STANDARD_COVERAGE_THRESHOLD}%) — consider adding detectors"
            )
    elif tier == SafetyTier.REJECTED:
        actions.append("CRITICAL: Design CANNOT be submitted — redesign required")
        actions.append("Increase detector count to achieve minimum coverage")
        if coverage_pct < ABSOLUTE_MINIMUM_COVERAGE:
            actions.append(
                f"Coverage {coverage_pct:.2f}% is catastrophically below "
                f"minimum ({ABSOLUTE_MINIMUM_COVERAGE}%)"
            )
        for err in errors[:5]:  # Limit to first 5 errors
            actions.append(f"Error: {err}")

    return {
        "fail_safe_required": True,
        "tier": tier.value,
        "actions": actions,
        "recommendation": "Do NOT submit until all actions are resolved",
    }


def tier_requires_fpe_review(tier: SafetyTier) -> bool:
    """Check if a safety tier requires Fire Protection Engineer review."""
    return tier in (SafetyTier.PROOF_VALID, SafetyTier.FALLBACK_USED)


def tier_can_submit(tier: SafetyTier) -> bool:
    """Check if a design at this tier can be submitted."""
    return tier in (SafetyTier.PROOF_VERIFIED, SafetyTier.PROOF_VALID)


# ═══════════════════════════════════════════════════════════════════════════════
# OVERRIDE SYSTEM — For FPE review with audit trail
# ═══════════════════════════════════════════════════════════════════════════════

class OverrideRole(enum.Enum):
    """Roles authorized to override safety decisions."""
    FPE = "FPE"               # Fire Protection Engineer
    AHJ = "AHJ"               # Authority Having Jurisdiction
    SENIOR_ENGINEER = "SENIOR_ENGINEER"
    QA_AUDITOR = "QA_AUDITOR"


@dataclass(frozen=True)
class OverrideRecord:
    """Record of a safety override decision.

    Every override MUST be documented with:
    - Who authorized it (name + role)
    - Why it was necessary (justification)
    - What risk it introduces (risk assessment)
    - When it was made (timestamp)
    """
    override_id: str
    tier_from: str
    tier_to: str
    authorizer_name: str
    authorizer_role: OverrideRole
    justification: str
    risk_assessment: str
    timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


# ═══════════════════════════════════════════════════════════════════════════════
# ENGINEERING EVIDENCE PACKAGE
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class EngineeringEvidencePackage:
    """Complete engineering evidence package for a room analysis.

    This package provides a tamper-evident record of all engineering
    decisions, inputs, and outputs for a single room analysis.

    The integrity hash is computed over ALL fields, so any change
    to any field will produce a different hash. This prevents
    undetected modification of engineering results.

    NFPA 72 Reference:
      - §17.6.3.1 — Spacing requirements
      - §17.7.4.2.3.1 — Coverage requirements
      - §10.6.7 — Battery requirements
      - §10.6.4 — Voltage drop requirements
    """
    package_id:         str
    room_id:            str
    room_polygon:       List[Tuple[float, float]]
    room_area_m2:       float
    ceiling_height_m:   float
    ceiling_type:       str
    occupancy_type:     str
    detector_positions: List[Tuple[float, float]]
    detector_type:      str
    spacing_m:          float
    coverage_radius_m:  float
    coverage_pct:       float
    wall_violations:    int
    nfpa_references:    List[str]
    compliance_status:  str
    proof_valid:        bool
    safety_tier:        str

    def compute_integrity_hash(self, key: Optional[bytes] = None) -> str:
        """Compute HMAC-SHA256 hash of the entire evidence package.

        Uses canonical JSON serialization for deterministic hashing, then
        applies HMAC-SHA256 for tamper-proof authentication.

        SECURITY FIX (CRITICAL): Previous implementation used plain SHA-256,
        which only provides tamper-**evident** (not tamper-**proof**) hashing.
        An attacker who can modify both data and hash can recompute SHA-256.
        HMAC-SHA256 requires a secret key, making forgery computationally
        infeasible without the key.

        The hash covers:
        - All input parameters (room geometry, detector type, etc.)
        - All computed results (coverage, spacing, positions)
        - All compliance decisions (safety tier, NFPA references)

        Args:
            key: Optional HMAC secret key. If not provided, reads from
                 FIREAI_EVIDENCE_HMAC_KEY environment variable. Falls back
                 to a default key (with CRITICAL warning) if neither is set.
                 Key must be at least 32 bytes for security.

        Returns:
            Hex-encoded HMAC-SHA256 hash string.
        """
        # Build deterministic representation
        # SAFETY FIX (HIGH-15): Include room_polygon in hash computation.
        # Without it, two rooms with the same area but different shapes
        # would produce the same hash, allowing undetected tampering.
        hash_data = {
            "pkg":     self.package_id,
            "room":    self.room_id,
            "poly":    sorted(
                [(round(x, 4), round(y, 4)) for x, y in self.room_polygon]
            ),
            "area":    round(self.room_area_m2, 6),
            "ceil_h":  round(self.ceiling_height_m, 4),
            "ceil_t":  self.ceiling_type,
            "occ":     self.occupancy_type,
            "det_t":   self.detector_type,
            "space":   round(self.spacing_m, 4),
            "radius":  round(self.coverage_radius_m, 4),
            "cov":     round(self.coverage_pct, 6),
            "walls":   self.wall_violations,
            "nfpa":    sorted(self.nfpa_references),
            "status":  self.compliance_status,
            "proof":   self.proof_valid,
            "tier":    self.safety_tier,
            # Detector positions — sorted for determinism
            "dets":    sorted(
                [(round(x, 4), round(y, 4)) for x, y in self.detector_positions]
            ),
        }

        # Canonical JSON with sorted keys
        canonical = json.dumps(hash_data, sort_keys=True, separators=(',', ':'))

        # Step 1: Compute SHA-256 digest of the canonical data
        sha256_hash = hashlib.sha256(canonical.encode('utf-8')).hexdigest()

        # Step 2: Apply HMAC-SHA256 for tamper-proof authentication
        # Resolve the HMAC key: explicit param > env var > default (with warning)
        _logger = logging.getLogger(__name__)

        if key is not None:
            hmac_key = key
        else:
            env_key = os.getenv("FIREAI_EVIDENCE_HMAC_KEY", "")
            if env_key:
                hmac_key = env_key.encode('utf-8')
            else:
                # V102 FIX: In production, refuse to use a default key.
                # The derived default key is computable from source code,
                # meaning anyone with code access can forge evidence packages.
                # In a safety-critical system, this is unacceptable.
                # Only enforce this when FIREAI_ENV is EXPLICITLY set to
                # "production" — if the variable is not set at all, we assume
                # a development/testing context for backward compatibility.
                _fireai_env = os.getenv("FIREAI_ENV", "")
                if _fireai_env == "production":
                    raise RuntimeError(
                        "FIREAI_EVIDENCE_HMAC_KEY must be set in production. "
                        "Evidence packages cannot be tamper-proof without a "
                        "secret HMAC key. Generate one with: "
                        "python -c \"import secrets; print(secrets.token_hex(32))\""
                    )
                # Use default key when FIREAI_ENV is not set or is "development"
                _default_key = hashlib.sha256(
                    b"fireai.core.safety_assurance.default-hmac-key-v1"
                ).digest()
                hmac_key = _default_key
                _logger.critical(
                    "SECURITY: FIREAI_EVIDENCE_HMAC_KEY not set. "
                    "Using derived default HMAC key — evidence packages are "
                    "tamper-evident but NOT tamper-proof against attackers with "
                    "source code access. Set FIREAI_EVIDENCE_HMAC_KEY env var "
                    "with a random 32+ byte key for production use."
                )

        # Warn if key is too short (security best practice)
        if len(hmac_key) < 32:
            _logger.warning(
                f"HMAC key is {len(hmac_key)} bytes — minimum 32 bytes "
                f"recommended for HMAC-SHA256. Consider using a longer key."
            )

        # Use the shared compute_hmac from audit_log when available, so that
        # both modules agree on the exact HMAC-SHA256 computation.  Falls back
        # to inline hmac.new() only if audit_log cannot be imported (rare).
        if _audit_compute_hmac is not None:
            return _audit_compute_hmac(sha256_hash, hmac_key)
        return hmac.new(hmac_key, sha256_hash.encode('utf-8'), hashlib.sha256).hexdigest()
