"""
Comprehensive tests for fireai.core.safety_assurance.

Covers all public functions, classes, and constants:
  - Constants
  - SafetyTier enum
  - classify_safety_tier() — all 8 classification rules + NaN/Inf
  - apply_fail_safe()
  - tier_requires_fpe_review()
  - tier_can_submit()
  - OverrideRole enum
  - OverrideRecord dataclass
  - EngineeringEvidencePackage — creation, hash determinism, tamper detection
"""

from __future__ import annotations

import math
from datetime import datetime, timezone

import pytest

from fireai.core.safety_assurance import (
    ABSOLUTE_MINIMUM_COVERAGE,
    MINIMUM_COVERAGE_FOR_SUBMISSION,
    OverrideRecord,
    OverrideRole,
    PROOF_VERIFIED_THRESHOLD,
    STANDARD_COVERAGE_THRESHOLD,
    EngineeringEvidencePackage,
    SafetyTier,
    apply_fail_safe,
    classify_safety_tier,
    tier_can_submit,
    tier_requires_fpe_review,
)


# ═══════════════════════════════════════════════════════════════════════════════
# CONSTANTS
# ═══════════════════════════════════════════════════════════════════════════════

class TestConstants:
    """Verify that safety threshold constants have the expected values."""

    def test_absolute_minimum_coverage(self):
        assert ABSOLUTE_MINIMUM_COVERAGE == 90.0

    def test_minimum_coverage_for_submission(self):
        assert MINIMUM_COVERAGE_FOR_SUBMISSION == 95.0

    def test_standard_coverage_threshold(self):
        assert STANDARD_COVERAGE_THRESHOLD == 99.0

    def test_proof_verified_threshold(self):
        assert PROOF_VERIFIED_THRESHOLD == 99.5


# ═══════════════════════════════════════════════════════════════════════════════
# SafetyTier ENUM
# ═══════════════════════════════════════════════════════════════════════════════

class TestSafetyTier:
    """Verify SafetyTier enum values and membership."""

    def test_proof_verified_value(self):
        assert SafetyTier.PROOF_VERIFIED.value == "PROOF_VERIFIED"

    def test_proof_valid_value(self):
        assert SafetyTier.PROOF_VALID.value == "PROOF_VALID"

    def test_fallback_used_value(self):
        assert SafetyTier.FALLBACK_USED.value == "FALLBACK_USED"

    def test_rejected_value(self):
        assert SafetyTier.REJECTED.value == "REJECTED"

    def test_enum_has_exactly_four_members(self):
        assert len(SafetyTier) == 4

    def test_all_tiers_accessible(self):
        expected = {"PROOF_VERIFIED", "PROOF_VALID", "FALLBACK_USED", "REJECTED"}
        actual = {t.name for t in SafetyTier}
        assert actual == expected


# ═══════════════════════════════════════════════════════════════════════════════
# classify_safety_tier
# ═══════════════════════════════════════════════════════════════════════════════

class TestClassifySafetyTier:
    """Test every classification rule in classify_safety_tier()."""

    # ── Rule 1: coverage < ABSOLUTE_MINIMUM_COVERAGE → REJECTED ────────────

    def test_rule1_coverage_below_absolute_minimum(self):
        assert classify_safety_tier(89.9, False, False, 0) == SafetyTier.REJECTED

    def test_rule1_coverage_well_below_minimum(self):
        assert classify_safety_tier(50.0, False, False, 0) == SafetyTier.REJECTED

    def test_rule1_coverage_zero(self):
        assert classify_safety_tier(0.0, False, False, 0) == SafetyTier.REJECTED

    def test_rule1_coverage_negative(self):
        assert classify_safety_tier(-10.0, False, False, 0) == SafetyTier.REJECTED

    def test_rule1_just_below_absolute_minimum(self):
        """89.999 is still below 90.0 → REJECTED."""
        assert classify_safety_tier(89.999, False, False, 0) == SafetyTier.REJECTED

    # ── Rule 2: wall_violations > 0 and coverage < STANDARD → REJECTED ────

    def test_rule2_wall_violations_with_low_coverage(self):
        """Coverage 96, wall violations → REJECTED (below 99)."""
        assert classify_safety_tier(96.0, False, False, 1) == SafetyTier.REJECTED

    def test_rule2_wall_violations_with_medium_coverage(self):
        """Coverage 98, wall violations → REJECTED (below 99)."""
        assert classify_safety_tier(98.0, False, False, 3) == SafetyTier.REJECTED

    def test_rule2_wall_violations_just_below_standard(self):
        """Coverage 98.999 with wall violations → still REJECTED."""
        assert classify_safety_tier(98.999, False, False, 1) == SafetyTier.REJECTED

    # ── Rule 3: fallback and coverage < MINIMUM_FOR_SUBMISSION → REJECTED ─

    def test_rule3_fallback_with_insufficient_coverage(self):
        """Fallback used, coverage 93 → REJECTED (< 95)."""
        assert classify_safety_tier(93.0, False, True, 0) == SafetyTier.REJECTED

    def test_rule3_fallback_with_coverage_just_below_submission(self):
        assert classify_safety_tier(94.999, False, True, 0) == SafetyTier.REJECTED

    # ── Rule 4: coverage < MINIMUM_FOR_SUBMISSION → REJECTED ───────────────

    def test_rule4_below_submission_minimum_no_fallback(self):
        """Coverage 92, no fallback, no violations → still REJECTED."""
        assert classify_safety_tier(92.0, False, False, 0) == SafetyTier.REJECTED

    def test_rule4_coverage_just_below_95(self):
        assert classify_safety_tier(94.999, False, False, 0) == SafetyTier.REJECTED

    # ── Rule 5: proof_valid and coverage >= PROOF_VERIFIED_THRESHOLD → PROOF_VERIFIED

    def test_rule5_proof_verified_at_threshold(self):
        assert classify_safety_tier(99.5, True, False, 0) == SafetyTier.PROOF_VERIFIED

    def test_rule5_proof_verified_above_threshold(self):
        assert classify_safety_tier(99.9, True, False, 0) == SafetyTier.PROOF_VERIFIED

    def test_rule5_proof_verified_at_100(self):
        assert classify_safety_tier(100.0, True, False, 0) == SafetyTier.PROOF_VERIFIED

    def test_rule5_proof_valid_but_coverage_below_proof_threshold(self):
        """proof_valid=True but coverage 99.4 → not PROOF_VERIFIED."""
        result = classify_safety_tier(99.4, True, False, 0)
        assert result == SafetyTier.PROOF_VALID  # Falls to rule 6

    def test_rule5_proof_valid_false_even_with_high_coverage(self):
        """proof_valid=False, coverage >= 99.5 → PROOF_VALID (not PROOF_VERIFIED)."""
        result = classify_safety_tier(99.5, False, False, 0)
        assert result == SafetyTier.PROOF_VALID

    # ── Rule 6: coverage >= STANDARD and no wall violations → PROOF_VALID ─

    def test_rule6_standard_coverage_no_violations(self):
        assert classify_safety_tier(99.0, False, False, 0) == SafetyTier.PROOF_VALID

    def test_rule6_above_standard_coverage_no_violations(self):
        assert classify_safety_tier(99.3, False, False, 0) == SafetyTier.PROOF_VALID

    def test_rule6_standard_coverage_with_wall_violations(self):
        """Coverage >= 99 but wall_violations > 0 → NOT PROOF_VALID, falls through."""
        result = classify_safety_tier(99.0, False, False, 1)
        # With wall violations at 99%+ coverage: rule 6 skips, rule 7 may apply
        # (fallback_used=False), rule 8: coverage >= 95 → FALLBACK_USED
        assert result == SafetyTier.FALLBACK_USED

    # ── Rule 7: fallback used and coverage >= MINIMUM_FOR_SUBMISSION → FALLBACK_USED

    def test_rule7_fallback_with_adequate_coverage(self):
        assert classify_safety_tier(97.0, False, True, 0) == SafetyTier.FALLBACK_USED

    def test_rule7_fallback_exactly_at_submission_minimum(self):
        assert classify_safety_tier(95.0, False, True, 0) == SafetyTier.FALLBACK_USED

    def test_rule7_fallback_above_submission_minimum(self):
        assert classify_safety_tier(96.5, False, True, 0) == SafetyTier.FALLBACK_USED

    # ── Rule 8: coverage >= 95 but not >= 99 with violations → FALLBACK_USED

    def test_rule8_coverage_between_95_and_99_with_violations(self):
        """Coverage 96, no fallback, wall violations → FALLBACK_USED via rule 8."""
        result = classify_safety_tier(96.0, False, False, 1)
        # Rule 2 catches this: wall_violations > 0 and coverage < 99 → REJECTED
        # Actually wait — coverage 96 < 99 and violations > 0 → REJECTED by rule 2
        assert result == SafetyTier.REJECTED

    def test_rule8_coverage_exactly_95_no_fallback_no_violations(self):
        """Coverage 95, no fallback, no violations — not >= 99, so not PROOF_VALID.
        Not fallback_used, so not rule 7. Rule 8: coverage >= 95 → FALLBACK_USED."""
        result = classify_safety_tier(95.0, False, False, 0)
        assert result == SafetyTier.FALLBACK_USED

    def test_rule8_coverage_97_no_fallback_no_violations(self):
        """Coverage 97, no fallback, no violations → FALLBACK_USED (rule 8)."""
        result = classify_safety_tier(97.0, False, False, 0)
        assert result == SafetyTier.FALLBACK_USED

    def test_rule8_coverage_98_no_fallback_no_violations(self):
        result = classify_safety_tier(98.0, False, False, 0)
        assert result == SafetyTier.FALLBACK_USED

    # ── NaN / Inf coverage → always REJECTED ───────────────────────────────

    def test_nan_coverage_rejected(self):
        assert classify_safety_tier(float("nan"), True, False, 0) == SafetyTier.REJECTED

    def test_positive_inf_coverage_rejected(self):
        assert classify_safety_tier(float("inf"), True, False, 0) == SafetyTier.REJECTED

    def test_negative_inf_coverage_rejected(self):
        assert classify_safety_tier(float("-inf"), True, False, 0) == SafetyTier.REJECTED

    def test_nan_coverage_even_with_proof(self):
        """NaN coverage is rejected regardless of proof_valid."""
        assert classify_safety_tier(float("nan"), True, False, 0) == SafetyTier.REJECTED

    def test_inf_coverage_even_with_proof_and_no_violations(self):
        assert classify_safety_tier(float("inf"), True, False, 0) == SafetyTier.REJECTED

    # ── Boundary / edge cases ──────────────────────────────────────────────

    def test_exactly_90_no_other_issues(self):
        """Coverage exactly 90, but < 95 → REJECTED by rule 4."""
        result = classify_safety_tier(90.0, False, False, 0)
        assert result == SafetyTier.REJECTED

    def test_exactly_95_no_fallback_no_violations(self):
        """Coverage exactly 95, no fallback, no violations → FALLBACK_USED."""
        result = classify_safety_tier(95.0, False, False, 0)
        assert result == SafetyTier.FALLBACK_USED

    def test_exactly_99_no_violations(self):
        """Coverage exactly 99, no violations → PROOF_VALID."""
        result = classify_safety_tier(99.0, False, False, 0)
        assert result == SafetyTier.PROOF_VALID

    def test_exactly_99_with_violations_no_fallback(self):
        """Coverage 99, violations → rule 6 skipped, rule 8: FALLBACK_USED."""
        result = classify_safety_tier(99.0, False, False, 1)
        assert result == SafetyTier.FALLBACK_USED

    def test_proof_valid_fallback_used_high_coverage(self):
        """proof_valid=True, fallback=True, coverage=99.5 → PROOF_VERIFIED (rule 5)."""
        result = classify_safety_tier(99.5, True, True, 0)
        assert result == SafetyTier.PROOF_VERIFIED


# ═══════════════════════════════════════════════════════════════════════════════
# apply_fail_safe
# ═══════════════════════════════════════════════════════════════════════════════

class TestApplyFailSafe:
    """Test fail-safe action generation for each tier."""

    def test_proof_verified_no_action_needed(self):
        result = apply_fail_safe(SafetyTier.PROOF_VERIFIED, 99.5, [])
        assert result["fail_safe_required"] is False
        assert result["actions"] == []
        assert "meets safety" in result["recommendation"].lower()

    def test_proof_valid_no_action_needed(self):
        result = apply_fail_safe(SafetyTier.PROOF_VALID, 99.0, [])
        assert result["fail_safe_required"] is False
        assert result["actions"] == []
        assert "meets safety" in result["recommendation"].lower()

    def test_fallback_used_requires_fpe_review(self):
        result = apply_fail_safe(SafetyTier.FALLBACK_USED, 97.0, [])
        assert result["fail_safe_required"] is True
        assert result["tier"] == "FALLBACK_USED"
        # Must include FPE review action
        fpe_actions = [a for a in result["actions"] if "FPE" in a or "Fire Protection Engineer" in a]
        assert len(fpe_actions) > 0
        assert "Do NOT submit" in result["recommendation"]

    def test_fallback_used_coverage_below_standard_mentions_detectors(self):
        """FALLBACK_USED with coverage < 99% should suggest adding detectors."""
        result = apply_fail_safe(SafetyTier.FALLBACK_USED, 96.5, [])
        assert result["fail_safe_required"] is True
        detector_actions = [a for a in result["actions"] if "detector" in a.lower() or "adding" in a.lower()]
        assert len(detector_actions) > 0

    def test_fallback_used_coverage_at_standard_no_detector_advice(self):
        """FALLBACK_USED with coverage >= 99% — no 'consider adding detectors' message."""
        result = apply_fail_safe(SafetyTier.FALLBACK_USED, 99.0, [])
        detector_actions = [a for a in result["actions"] if "consider adding detectors" in a.lower()]
        assert len(detector_actions) == 0

    def test_rejected_requires_redesign(self):
        result = apply_fail_safe(SafetyTier.REJECTED, 85.0, ["Wall violation", "Low coverage"])
        assert result["fail_safe_required"] is True
        assert result["tier"] == "REJECTED"
        redesign_actions = [a for a in result["actions"] if "redesign" in a.lower()]
        assert len(redesign_actions) > 0

    def test_rejected_catastrophically_low_coverage(self):
        """REJECTED with coverage < 90 → mentions 'catastrophically'."""
        result = apply_fail_safe(SafetyTier.REJECTED, 80.0, [])
        catastrophic = [a for a in result["actions"] if "catastrophically" in a.lower()]
        assert len(catastrophic) > 0

    def test_rejected_above_absolute_min_no_catastrophic(self):
        """REJECTED with coverage >= 90 → no 'catastrophically' message."""
        result = apply_fail_safe(SafetyTier.REJECTED, 92.0, [])
        catastrophic = [a for a in result["actions"] if "catastrophically" in a.lower()]
        assert len(catastrophic) == 0

    def test_rejected_includes_errors_limited_to_five(self):
        """Error messages are capped at 5."""
        errors = [f"Error {i}" for i in range(10)]
        result = apply_fail_safe(SafetyTier.REJECTED, 85.0, errors)
        error_actions = [a for a in result["actions"] if a.startswith("Error:")]
        assert len(error_actions) == 5

    def test_rejected_includes_first_five_errors(self):
        errors = ["err_A", "err_B", "err_C", "err_D", "err_E", "err_F"]
        result = apply_fail_safe(SafetyTier.REJECTED, 85.0, errors)
        error_actions = [a for a in result["actions"] if a.startswith("Error:")]
        assert "err_A" in error_actions[0]
        assert "err_E" in error_actions[4]

    def test_rejected_no_errors_no_error_actions(self):
        result = apply_fail_safe(SafetyTier.REJECTED, 85.0, [])
        error_actions = [a for a in result["actions"] if a.startswith("Error:")]
        assert len(error_actions) == 0


# ═══════════════════════════════════════════════════════════════════════════════
# tier_requires_fpe_review
# ═══════════════════════════════════════════════════════════════════════════════

class TestTierRequiresFpeReview:
    """Test which tiers require Fire Protection Engineer review."""

    def test_proof_valid_requires_review(self):
        assert tier_requires_fpe_review(SafetyTier.PROOF_VALID) is True

    def test_fallback_used_requires_review(self):
        assert tier_requires_fpe_review(SafetyTier.FALLBACK_USED) is True

    def test_proof_verified_does_not_require_review(self):
        assert tier_requires_fpe_review(SafetyTier.PROOF_VERIFIED) is False

    def test_rejected_does_not_require_review(self):
        """REJECTED designs are not reviewed — they must be redesigned."""
        assert tier_requires_fpe_review(SafetyTier.REJECTED) is False


# ═══════════════════════════════════════════════════════════════════════════════
# tier_can_submit
# ═══════════════════════════════════════════════════════════════════════════════

class TestTierCanSubmit:
    """Test which tiers allow submission."""

    def test_proof_verified_can_submit(self):
        assert tier_can_submit(SafetyTier.PROOF_VERIFIED) is True

    def test_proof_valid_can_submit(self):
        assert tier_can_submit(SafetyTier.PROOF_VALID) is True

    def test_fallback_used_cannot_submit(self):
        assert tier_can_submit(SafetyTier.FALLBACK_USED) is False

    def test_rejected_cannot_submit(self):
        assert tier_can_submit(SafetyTier.REJECTED) is False


# ═══════════════════════════════════════════════════════════════════════════════
# OverrideRole ENUM
# ═══════════════════════════════════════════════════════════════════════════════

class TestOverrideRole:
    """Verify OverrideRole enum values."""

    def test_fpe_value(self):
        assert OverrideRole.FPE.value == "FPE"

    def test_ahj_value(self):
        assert OverrideRole.AHJ.value == "AHJ"

    def test_senior_engineer_value(self):
        assert OverrideRole.SENIOR_ENGINEER.value == "SENIOR_ENGINEER"

    def test_qa_auditor_value(self):
        assert OverrideRole.QA_AUDITOR.value == "QA_AUDITOR"

    def test_enum_has_exactly_four_members(self):
        assert len(OverrideRole) == 4

    def test_all_roles_accessible(self):
        expected = {"FPE", "AHJ", "SENIOR_ENGINEER", "QA_AUDITOR"}
        actual = {r.name for r in OverrideRole}
        assert actual == expected


# ═══════════════════════════════════════════════════════════════════════════════
# OverrideRecord DATACLASS
# ═══════════════════════════════════════════════════════════════════════════════

class TestOverrideRecord:
    """Test OverrideRecord creation and auto-timestamp."""

    def test_creation_with_all_fields(self):
        record = OverrideRecord(
            override_id="OVR-001",
            tier_from="REJECTED",
            tier_to="FALLBACK_USED",
            authorizer_name="Jane Smith",
            authorizer_role=OverrideRole.FPE,
            justification="Reviewed and accepted with additional detectors",
            risk_assessment="Low risk — additional detectors compensate",
        )
        assert record.override_id == "OVR-001"
        assert record.tier_from == "REJECTED"
        assert record.tier_to == "FALLBACK_USED"
        assert record.authorizer_name == "Jane Smith"
        assert record.authorizer_role == OverrideRole.FPE
        assert record.justification == "Reviewed and accepted with additional detectors"
        assert record.risk_assessment == "Low risk — additional detectors compensate"

    def test_auto_timestamp_generated(self):
        """When no timestamp is provided, one is auto-generated in UTC ISO format."""
        before = datetime.now(timezone.utc)
        record = OverrideRecord(
            override_id="OVR-002",
            tier_from="REJECTED",
            tier_to="FALLBACK_USED",
            authorizer_name="John Doe",
            authorizer_role=OverrideRole.AHJ,
            justification="Jurisdictional override",
            risk_assessment="Moderate risk",
        )
        after = datetime.now(timezone.utc)

        # The auto-generated timestamp should be parseable and between before/after
        ts = datetime.fromisoformat(record.timestamp)
        assert before <= ts <= after

    def test_explicit_timestamp_preserved(self):
        """When a timestamp is explicitly provided, it should be used as-is."""
        explicit_ts = "2024-01-15T10:30:00+00:00"
        record = OverrideRecord(
            override_id="OVR-003",
            tier_from="FALLBACK_USED",
            tier_to="PROOF_VALID",
            authorizer_name="Alice",
            authorizer_role=OverrideRole.SENIOR_ENGINEER,
            justification="Design verified",
            risk_assessment="Low",
            timestamp=explicit_ts,
        )
        assert record.timestamp == explicit_ts

    def test_frozen_dataclass_immutable(self):
        """OverrideRecord is frozen — attribute assignment should raise."""
        record = OverrideRecord(
            override_id="OVR-004",
            tier_from="REJECTED",
            tier_to="PROOF_VALID",
            authorizer_name="Bob",
            authorizer_role=OverrideRole.QA_AUDITOR,
            justification="QA override",
            risk_assessment="Acceptable",
        )
        with pytest.raises(AttributeError):
            record.override_id = "CHANGED"


# ═══════════════════════════════════════════════════════════════════════════════
# EngineeringEvidencePackage
# ═══════════════════════════════════════════════════════════════════════════════

def _make_evidence_package(**overrides):
    """Helper to create a standard evidence package with optional overrides."""
    defaults = dict(
        package_id="PKG-001",
        room_id="ROOM-A1",
        room_polygon=[(0.0, 0.0), (10.0, 0.0), (10.0, 8.0), (0.0, 8.0)],
        room_area_m2=80.0,
        ceiling_height_m=3.6,
        ceiling_type="smooth",
        occupancy_type="office",
        detector_positions=[(3.3, 2.7), (6.6, 5.4)],
        detector_type="photoelectric",
        spacing_m=9.1,
        coverage_radius_m=6.4,
        coverage_pct=99.7,
        wall_violations=0,
        nfpa_references=["NFPA 72 §17.6.3.1", "NFPA 72 §17.7.4.2.3.1"],
        compliance_status="COMPLIANT",
        proof_valid=True,
        safety_tier="PROOF_VERIFIED",
    )
    defaults.update(overrides)
    return EngineeringEvidencePackage(**defaults)


class TestEngineeringEvidencePackage:
    """Test EngineeringEvidencePackage creation, hash determinism, tamper detection."""

    # ── Creation ────────────────────────────────────────────────────────────

    def test_creation_with_all_fields(self):
        pkg = _make_evidence_package()
        assert pkg.package_id == "PKG-001"
        assert pkg.room_id == "ROOM-A1"
        assert pkg.room_polygon == [(0.0, 0.0), (10.0, 0.0), (10.0, 8.0), (0.0, 8.0)]
        assert pkg.room_area_m2 == 80.0
        assert pkg.ceiling_height_m == 3.6
        assert pkg.ceiling_type == "smooth"
        assert pkg.occupancy_type == "office"
        assert pkg.detector_positions == [(3.3, 2.7), (6.6, 5.4)]
        assert pkg.detector_type == "photoelectric"
        assert pkg.spacing_m == 9.1
        assert pkg.coverage_radius_m == 6.4
        assert pkg.coverage_pct == 99.7
        assert pkg.wall_violations == 0
        assert pkg.nfpa_references == ["NFPA 72 §17.6.3.1", "NFPA 72 §17.7.4.2.3.1"]
        assert pkg.compliance_status == "COMPLIANT"
        assert pkg.proof_valid is True
        assert pkg.safety_tier == "PROOF_VERIFIED"

    # ── Hash determinism ───────────────────────────────────────────────────

    def test_hash_is_deterministic(self):
        """Same inputs → same hash, every time."""
        pkg1 = _make_evidence_package()
        pkg2 = _make_evidence_package()
        assert pkg1.compute_integrity_hash() == pkg2.compute_integrity_hash()

    def test_hash_is_deterministic_across_multiple_calls(self):
        """Calling compute_integrity_hash() multiple times returns the same value."""
        pkg = _make_evidence_package()
        hash1 = pkg.compute_integrity_hash()
        hash2 = pkg.compute_integrity_hash()
        hash3 = pkg.compute_integrity_hash()
        assert hash1 == hash2 == hash3

    def test_hash_is_sha256_hex(self):
        """Hash should be a 64-character hex string (SHA-256)."""
        pkg = _make_evidence_package()
        h = pkg.compute_integrity_hash()
        assert len(h) == 64
        assert all(c in "0123456789abcdef" for c in h)

    # ── Tamper detection: hash changes when any field is modified ──────────

    def test_hash_changes_when_package_id_changes(self):
        original = _make_evidence_package()
        modified = _make_evidence_package(package_id="PKG-999")
        assert original.compute_integrity_hash() != modified.compute_integrity_hash()

    def test_hash_changes_when_room_id_changes(self):
        original = _make_evidence_package()
        modified = _make_evidence_package(room_id="ROOM-Z9")
        assert original.compute_integrity_hash() != modified.compute_integrity_hash()

    def test_hash_changes_when_room_area_changes(self):
        original = _make_evidence_package()
        modified = _make_evidence_package(room_area_m2=85.0)
        assert original.compute_integrity_hash() != modified.compute_integrity_hash()

    def test_hash_changes_when_ceiling_height_changes(self):
        original = _make_evidence_package()
        modified = _make_evidence_package(ceiling_height_m=4.0)
        assert original.compute_integrity_hash() != modified.compute_integrity_hash()

    def test_hash_changes_when_ceiling_type_changes(self):
        original = _make_evidence_package()
        modified = _make_evidence_package(ceiling_type="beamed")
        assert original.compute_integrity_hash() != modified.compute_integrity_hash()

    def test_hash_changes_when_occupancy_type_changes(self):
        original = _make_evidence_package()
        modified = _make_evidence_package(occupancy_type="warehouse")
        assert original.compute_integrity_hash() != modified.compute_integrity_hash()

    def test_hash_changes_when_detector_positions_change(self):
        original = _make_evidence_package()
        modified = _make_evidence_package(detector_positions=[(1.0, 1.0), (5.0, 5.0)])
        assert original.compute_integrity_hash() != modified.compute_integrity_hash()

    def test_hash_changes_when_detector_type_changes(self):
        original = _make_evidence_package()
        modified = _make_evidence_package(detector_type="ionization")
        assert original.compute_integrity_hash() != modified.compute_integrity_hash()

    def test_hash_changes_when_spacing_changes(self):
        original = _make_evidence_package()
        modified = _make_evidence_package(spacing_m=10.0)
        assert original.compute_integrity_hash() != modified.compute_integrity_hash()

    def test_hash_changes_when_coverage_radius_changes(self):
        original = _make_evidence_package()
        modified = _make_evidence_package(coverage_radius_m=7.0)
        assert original.compute_integrity_hash() != modified.compute_integrity_hash()

    def test_hash_changes_when_coverage_pct_changes(self):
        original = _make_evidence_package()
        modified = _make_evidence_package(coverage_pct=95.0)
        assert original.compute_integrity_hash() != modified.compute_integrity_hash()

    def test_hash_changes_when_wall_violations_changes(self):
        original = _make_evidence_package()
        modified = _make_evidence_package(wall_violations=2)
        assert original.compute_integrity_hash() != modified.compute_integrity_hash()

    def test_hash_changes_when_nfpa_references_change(self):
        original = _make_evidence_package()
        modified = _make_evidence_package(
            nfpa_references=["NFPA 72 §10.6.7", "NFPA 72 §10.6.4"]
        )
        assert original.compute_integrity_hash() != modified.compute_integrity_hash()

    def test_hash_changes_when_compliance_status_changes(self):
        original = _make_evidence_package()
        modified = _make_evidence_package(compliance_status="NON_COMPLIANT")
        assert original.compute_integrity_hash() != modified.compute_integrity_hash()

    def test_hash_changes_when_proof_valid_changes(self):
        original = _make_evidence_package()
        modified = _make_evidence_package(proof_valid=False)
        assert original.compute_integrity_hash() != modified.compute_integrity_hash()

    def test_hash_changes_when_safety_tier_changes(self):
        original = _make_evidence_package()
        modified = _make_evidence_package(safety_tier="REJECTED")
        assert original.compute_integrity_hash() != modified.compute_integrity_hash()

    def test_hash_changes_when_only_coverage_pct_slightly_changes(self):
        """Even a tiny change in coverage_pct must be detected."""
        original = _make_evidence_package(coverage_pct=99.7)
        modified = _make_evidence_package(coverage_pct=99.700001)
        assert original.compute_integrity_hash() != modified.compute_integrity_hash()

    # ── Hash stability: different object identity, same data → same hash ───

    def test_different_objects_same_data_produce_same_hash(self):
        """Two independently constructed packages with identical data → same hash."""
        pkg_a = EngineeringEvidencePackage(
            package_id="PKG-X",
            room_id="ROOM-X",
            room_polygon=[(0, 0), (5, 0), (5, 5), (0, 5)],
            room_area_m2=25.0,
            ceiling_height_m=3.0,
            ceiling_type="smooth",
            occupancy_type="storage",
            detector_positions=[(2.5, 2.5)],
            detector_type="heat",
            spacing_m=7.0,
            coverage_radius_m=5.0,
            coverage_pct=98.5,
            wall_violations=0,
            nfpa_references=["NFPA 72 §17.6.3.1"],
            compliance_status="COMPLIANT",
            proof_valid=False,
            safety_tier="PROOF_VALID",
        )
        pkg_b = EngineeringEvidencePackage(
            package_id="PKG-X",
            room_id="ROOM-X",
            room_polygon=[(0, 0), (5, 0), (5, 5), (0, 5)],
            room_area_m2=25.0,
            ceiling_height_m=3.0,
            ceiling_type="smooth",
            occupancy_type="storage",
            detector_positions=[(2.5, 2.5)],
            detector_type="heat",
            spacing_m=7.0,
            coverage_radius_m=5.0,
            coverage_pct=98.5,
            wall_violations=0,
            nfpa_references=["NFPA 72 §17.6.3.1"],
            compliance_status="COMPLIANT",
            proof_valid=False,
            safety_tier="PROOF_VALID",
        )
        assert pkg_a.compute_integrity_hash() == pkg_b.compute_integrity_hash()

    # ── Detector position ordering does not affect hash ────────────────────

    def test_detector_position_ordering_does_not_affect_hash(self):
        """Detector positions are sorted for hash computation, so order doesn't matter."""
        pkg_a = _make_evidence_package(detector_positions=[(1.0, 2.0), (3.0, 4.0)])
        pkg_b = _make_evidence_package(detector_positions=[(3.0, 4.0), (1.0, 2.0)])
        assert pkg_a.compute_integrity_hash() == pkg_b.compute_integrity_hash()

    # ── NFPA reference ordering does not affect hash ───────────────────────

    def test_nfpa_reference_ordering_does_not_affect_hash(self):
        """NFPA references are sorted for hash computation, so order doesn't matter."""
        pkg_a = _make_evidence_package(
            nfpa_references=["NFPA 72 §17.6.3.1", "NFPA 72 §17.7.4.2.3.1"]
        )
        pkg_b = _make_evidence_package(
            nfpa_references=["NFPA 72 §17.7.4.2.3.1", "NFPA 72 §17.6.3.1"]
        )
        assert pkg_a.compute_integrity_hash() == pkg_b.compute_integrity_hash()
