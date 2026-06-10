"""
Tests for fireai.core.release_gates — Release Gate Evaluation
==============================================================

Covers all 8 release gates, verify_and_evaluate(), and describe_blockers().

SAFETY PRINCIPLE under test:
  A blocked release is ALWAYS safer than an unblocked one.
  False negatives (blocking good designs) are acceptable.
  False positives (approving bad designs) are NOT acceptable.
"""

from __future__ import annotations

import math
from typing import Any, Dict, List, Optional

import pytest

from fireai.core.release_gates import (
    _gate_battery,
    _gate_coverage,
    _gate_fault_isolation,
    _gate_input_validation,
    _gate_nfpa_spacing,
    _gate_safety_tier,
    _gate_voltage_drop,
    _gate_wall_distance,
    describe_blockers,
    verify_and_evaluate,
)


# ═══════════════════════════════════════════════════════════════════════════════
# FIXTURES — reusable inputs for a fully-passing scenario
# ═══════════════════════════════════════════════════════════════════════════════

def _green_input_payload() -> Dict[str, Any]:
    """Minimal input_payload that passes G1, and carries G3/G4/G8 data."""
    return {
        "room_id": "R-101",
        "area_m2": 42.0,
        "_coverage_pct": 99.5,
        "_wall_violations": 0,
        "_safety_tier": "PROOF_VERIFIED",
    }


def _green_nfpa_results() -> Dict[str, Any]:
    """Minimal nfpa_results that passes G2."""
    return {
        "is_compliant": True,
    }


def _green_loop_data() -> Dict[str, Any]:
    """Minimal loop_data that passes G6 and G7."""
    return {
        "voltage_drop": {"is_compliant": True, "voltage_drop_pct": 3.2},
        "fault_isolation": {"compliant": True, "violations": []},
    }


def _full_green_kwargs() -> Dict[str, Any]:
    """All keyword arguments that produce release_status='green'."""
    return dict(
        input_payload=_green_input_payload(),
        nfpa_results=_green_nfpa_results(),
        loop_data=_green_loop_data(),
    )


# ═══════════════════════════════════════════════════════════════════════════════
# G1 — Input Validation
# ═══════════════════════════════════════════════════════════════════════════════

class TestG1InputValidation:
    """G1: Input payload must have been validated."""

    def test_none_payload_fails(self) -> None:
        result = _gate_input_validation(None)
        assert result["passed"] is False
        assert "None" in result["reason"]

    def test_missing_room_id_fails(self) -> None:
        result = _gate_input_validation({"area_m2": 10.0})
        assert result["passed"] is False
        assert "room_id" in result["reason"]

    def test_empty_room_id_fails(self) -> None:
        result = _gate_input_validation({"room_id": "", "area_m2": 10.0})
        assert result["passed"] is False
        assert "room_id" in result["reason"]

    def test_missing_area_fails(self) -> None:
        result = _gate_input_validation({"room_id": "R-1"})
        assert result["passed"] is False
        assert "area_m2" in result["reason"]

    def test_zero_area_fails(self) -> None:
        result = _gate_input_validation({"room_id": "R-1", "area_m2": 0})
        assert result["passed"] is False
        assert "area_m2" in result["reason"]

    def test_negative_area_fails(self) -> None:
        result = _gate_input_validation({"room_id": "R-1", "area_m2": -5.0})
        assert result["passed"] is False

    def test_infinite_area_fails(self) -> None:
        result = _gate_input_validation({"room_id": "R-1", "area_m2": math.inf})
        assert result["passed"] is False
        assert "area_m2" in result["reason"]

    def test_nan_area_fails(self) -> None:
        result = _gate_input_validation({"room_id": "R-1", "area_m2": math.nan})
        assert result["passed"] is False

    def test_valid_payload_passes(self) -> None:
        result = _gate_input_validation({"room_id": "R-101", "area_m2": 42.0})
        assert result["passed"] is True
        assert "validated" in result["reason"].lower()


# ═══════════════════════════════════════════════════════════════════════════════
# G2 — NFPA 72 Spacing
# ═══════════════════════════════════════════════════════════════════════════════

class TestG2NfpaSpacing:
    """G2: NFPA 72 spacing calculation must have succeeded."""

    def test_none_results_fails(self) -> None:
        result = _gate_nfpa_spacing(None)
        assert result["passed"] is False
        assert "unavailable" in result["reason"].lower()

    def test_non_compliant_results_fails(self) -> None:
        nfpa = {"is_compliant": False, "violations": ["spacing exceeds 9.1m"]}
        result = _gate_nfpa_spacing(nfpa)
        assert result["passed"] is False
        assert "violation" in result["reason"].lower()

    def test_non_compliant_without_violations_list_fails(self) -> None:
        nfpa = {"is_compliant": False}
        result = _gate_nfpa_spacing(nfpa)
        assert result["passed"] is False
        assert "unspecified" in result["reason"].lower()

    def test_non_compliant_with_multiple_violations_shows_up_to_three(self) -> None:
        nfpa = {
            "is_compliant": False,
            "violations": ["v1", "v2", "v3", "v4"],
        }
        result = _gate_nfpa_spacing(nfpa)
        assert result["passed"] is False
        # Should show at most 3 violations in the reason string
        assert "v1" in result["reason"]
        assert "v2" in result["reason"]
        assert "v3" in result["reason"]
        # v4 should NOT be shown (truncated to first 3)
        assert "v4" not in result["reason"]

    def test_compliant_results_passes(self) -> None:
        nfpa = {"is_compliant": True}
        result = _gate_nfpa_spacing(nfpa)
        assert result["passed"] is True
        assert "compliant" in result["reason"].lower()

    def test_missing_is_compliant_defaults_to_false(self) -> None:
        """If is_compliant key is absent, defaults to False — safe default."""
        result = _gate_nfpa_spacing({})
        assert result["passed"] is False


# ═══════════════════════════════════════════════════════════════════════════════
# G3 — Coverage Verification
# ═══════════════════════════════════════════════════════════════════════════════

class TestG3Coverage:
    """G3: Coverage must meet 99.0% standard threshold."""

    def test_none_coverage_fails(self) -> None:
        result = _gate_coverage(None)
        assert result["passed"] is False
        assert "not computed" in result["reason"].lower()

    def test_infinite_coverage_fails(self) -> None:
        result = _gate_coverage(math.inf)
        assert result["passed"] is False
        assert "non-finite" in result["reason"].lower()

    def test_nan_coverage_fails(self) -> None:
        result = _gate_coverage(math.nan)
        assert result["passed"] is False
        assert "non-finite" in result["reason"].lower()

    def test_negative_infinity_coverage_fails(self) -> None:
        result = _gate_coverage(-math.inf)
        assert result["passed"] is False

    def test_below_threshold_fails(self) -> None:
        result = _gate_coverage(98.5)
        assert result["passed"] is False
        assert "98.50" in result["reason"]

    def test_just_below_threshold_fails(self) -> None:
        """98.99 is still below 99.0 — must fail."""
        result = _gate_coverage(98.99)
        assert result["passed"] is False

    def test_zero_coverage_fails(self) -> None:
        result = _gate_coverage(0.0)
        assert result["passed"] is False

    def test_at_threshold_passes(self) -> None:
        """Exactly 99.0% should pass."""
        result = _gate_coverage(99.0)
        assert result["passed"] is True

    def test_above_threshold_passes(self) -> None:
        result = _gate_coverage(100.0)
        assert result["passed"] is True

    def test_very_high_coverage_passes(self) -> None:
        result = _gate_coverage(99.99)
        assert result["passed"] is True


# ═══════════════════════════════════════════════════════════════════════════════
# G4 — Wall Distance
# ═══════════════════════════════════════════════════════════════════════════════

class TestG4WallDistance:
    """G4: No dead-air-space wall distance violations."""

    def test_none_violations_fails(self) -> None:
        result = _gate_wall_distance(None)
        assert result["passed"] is False
        assert "not checked" in result["reason"].lower()

    def test_violations_greater_than_zero_fails(self) -> None:
        result = _gate_wall_distance(3)
        assert result["passed"] is False
        assert "3 detector" in result["reason"]

    def test_single_violation_fails(self) -> None:
        result = _gate_wall_distance(1)
        assert result["passed"] is False
        assert "1 detector" in result["reason"]

    def test_zero_violations_passes(self) -> None:
        result = _gate_wall_distance(0)
        assert result["passed"] is True
        assert "no wall" in result["reason"].lower() or "no wall distance" in result["reason"].lower()


# ═══════════════════════════════════════════════════════════════════════════════
# G5 — Battery Adequacy
# ═══════════════════════════════════════════════════════════════════════════════

class TestG5Battery:
    """G5: Battery must be adequate per NFPA 72 §10.6.7 (skips if None)."""

    def test_none_passes_skipped(self) -> None:
        result = _gate_battery(None)
        assert result["passed"] is True
        assert "skip" in result["reason"].lower() or "no battery" in result["reason"].lower()

    def test_inadequate_battery_fails(self) -> None:
        battery_result = {
            "is_adequate": False,
            "required_ah": 26.0,
            "installed_ah": 18.0,
        }
        result = _gate_battery(battery_result)
        assert result["passed"] is False
        assert "26.0" in result["reason"]
        assert "18.0" in result["reason"]

    def test_inadequate_battery_missing_ah_fields(self) -> None:
        battery_result = {"is_adequate": False}
        result = _gate_battery(battery_result)
        assert result["passed"] is False
        assert "?" in result["reason"]

    def test_adequate_battery_passes(self) -> None:
        battery_result = {
            "is_adequate": True,
            "required_ah": 26.0,
            "installed_ah": 33.0,
        }
        result = _gate_battery(battery_result)
        assert result["passed"] is True
        assert "adequate" in result["reason"].lower()

    def test_missing_is_adequate_defaults_to_false(self) -> None:
        """Safe default: if is_adequate is absent, battery check fails."""
        battery_result = {}
        result = _gate_battery(battery_result)
        assert result["passed"] is False


# ═══════════════════════════════════════════════════════════════════════════════
# G6 — Voltage Drop
# ═══════════════════════════════════════════════════════════════════════════════

class TestG6VoltageDrop:
    """G6: Voltage drop within limits per NFPA 72 §10.6.4 (skips if None)."""

    def test_none_passes_skipped(self) -> None:
        result = _gate_voltage_drop(None)
        assert result["passed"] is True
        assert "skip" in result["reason"].lower() or "no voltage" in result["reason"].lower()

    def test_non_compliant_voltage_drop_fails(self) -> None:
        loop_data = {
            "voltage_drop": {
                "is_compliant": False,
                "voltage_drop_pct": 12.5,
            },
        }
        result = _gate_voltage_drop(loop_data)
        assert result["passed"] is False
        assert "12.5" in result["reason"]

    def test_compliant_voltage_drop_passes(self) -> None:
        loop_data = {
            "voltage_drop": {
                "is_compliant": True,
                "voltage_drop_pct": 3.2,
            },
        }
        result = _gate_voltage_drop(loop_data)
        assert result["passed"] is True

    def test_no_voltage_drop_key_passes(self) -> None:
        """If loop_data exists but has no voltage_drop key, gate passes."""
        result = _gate_voltage_drop({"other_key": "value"})
        assert result["passed"] is True

    def test_voltage_drop_not_a_dict_blocks(self) -> None:
        """V67 SAFETY FIX: If voltage_drop value is not a dict, release is BLOCKED.

        Previous behavior (V12-V66) defaulted to True (PASS), creating a
        false-GREEN release pathway. Missing/invalid compliance data must
        default to BLOCKED — it is ALWAYS safer to block than to approve.
        False negatives are acceptable; false positives are NOT.
        """
        loop_data = {"voltage_drop": "invalid"}
        result = _gate_voltage_drop(loop_data)
        assert result["passed"] is False
        assert "not a dict" in result["reason"].lower() or "cannot verify" in result["reason"].lower()

    def test_voltage_drop_dict_missing_is_compliant_blocks(self) -> None:
        """V67 SAFETY FIX: If voltage_drop dict lacks is_compliant, release is BLOCKED.

        Previous behavior (V12-V66) defaulted to True (PASS), creating a
        false-GREEN release pathway. Missing compliance data must default
        to BLOCKED — approving a design with unknown compliance status
        is a false positive that violates NFPA 72 safety requirements.
        """
        loop_data = {"voltage_drop": {"voltage_drop_pct": 5.0}}
        result = _gate_voltage_drop(loop_data)
        assert result["passed"] is False
        assert "unknown" in result["reason"].lower() or "not specified" in result["reason"].lower()


# ═══════════════════════════════════════════════════════════════════════════════
# G7 — Fault Isolation
# ═══════════════════════════════════════════════════════════════════════════════

class TestG7FaultIsolation:
    """G7: SLC fault isolator placement per NFPA 72 §12.3 (skips if None)."""

    def test_none_passes_skipped(self) -> None:
        result = _gate_fault_isolation(None)
        assert result["passed"] is True
        assert "skip" in result["reason"].lower() or "no fault" in result["reason"].lower()

    def test_non_compliant_fault_isolation_fails(self) -> None:
        loop_data = {
            "fault_isolation": {
                "compliant": False,
                "violations": ["missing isolator on segment 3"],
            },
        }
        result = _gate_fault_isolation(loop_data)
        assert result["passed"] is False
        assert "1 violation" in result["reason"]

    def test_non_compliant_with_multiple_violations(self) -> None:
        loop_data = {
            "fault_isolation": {
                "compliant": False,
                "violations": ["v1", "v2", "v3"],
            },
        }
        result = _gate_fault_isolation(loop_data)
        assert result["passed"] is False
        assert "3 violation" in result["reason"]

    def test_compliant_fault_isolation_passes(self) -> None:
        loop_data = {
            "fault_isolation": {
                "compliant": True,
                "violations": [],
            },
        }
        result = _gate_fault_isolation(loop_data)
        assert result["passed"] is True
        assert "compliant" in result["reason"].lower()

    def test_no_fault_isolation_key_passes(self) -> None:
        """If loop_data exists but has no fault_isolation key, gate passes."""
        result = _gate_fault_isolation({"other_key": "value"})
        assert result["passed"] is True

    def test_fault_isolation_not_a_dict_blocks(self) -> None:
        """V67 SAFETY FIX: If fault_isolation value is not a dict, release is BLOCKED.

        Previous behavior (V12-V66) defaulted to True (PASS), creating a
        false-GREEN release pathway. Invalid compliance data must default
        to BLOCKED per the safety principle: false positives are NOT acceptable.
        """
        loop_data = {"fault_isolation": "invalid"}
        result = _gate_fault_isolation(loop_data)
        assert result["passed"] is False
        assert "not a dict" in result["reason"].lower() or "cannot verify" in result["reason"].lower()

    def test_fault_isolation_dict_missing_compliant_blocks(self) -> None:
        """V67 SAFETY FIX: If fault_isolation dict lacks compliant, release is BLOCKED.

        Previous behavior (V12-V66) defaulted to True (PASS), creating a
        false-GREEN release pathway. Missing compliance data must default
        to BLOCKED — approving a design with unknown compliance status
        is a false positive that violates NFPA 72 §12.3 requirements.
        """
        loop_data = {"fault_isolation": {"violations": []}}
        result = _gate_fault_isolation(loop_data)
        assert result["passed"] is False
        assert "unknown" in result["reason"].lower() or "not specified" in result["reason"].lower()

    def test_non_compliant_with_non_list_violations(self) -> None:
        """If violations is not a list, len defaults to 0."""
        loop_data = {
            "fault_isolation": {
                "compliant": False,
                "violations": "not_a_list",
            },
        }
        result = _gate_fault_isolation(loop_data)
        assert result["passed"] is False
        assert "0 violation" in result["reason"]


# ═══════════════════════════════════════════════════════════════════════════════
# G8 — Safety Tier
# ═══════════════════════════════════════════════════════════════════════════════

class TestG8SafetyTier:
    """G8: Safety tier must be PROOF_VERIFIED or PROOF_VALID."""

    def test_none_fails(self) -> None:
        result = _gate_safety_tier(None)
        assert result["passed"] is False
        assert "not determined" in result["reason"].lower()

    def test_rejected_tier_fails(self) -> None:
        result = _gate_safety_tier("REJECTED")
        assert result["passed"] is False
        assert "REJECTED" in result["reason"]

    def test_fallback_used_tier_fails(self) -> None:
        result = _gate_safety_tier("FALLBACK_USED")
        assert result["passed"] is False
        assert "FALLBACK_USED" in result["reason"]

    def test_proof_valid_passes(self) -> None:
        result = _gate_safety_tier("PROOF_VALID")
        assert result["passed"] is True

    def test_proof_verified_passes(self) -> None:
        result = _gate_safety_tier("PROOF_VERIFIED")
        assert result["passed"] is True

    def test_lowercase_tier_fails(self) -> None:
        """Tier matching is case-sensitive — lowercase should fail."""
        result = _gate_safety_tier("proof_verified")
        assert result["passed"] is False

    def test_empty_string_tier_fails(self) -> None:
        result = _gate_safety_tier("")
        assert result["passed"] is False

    def test_arbitrary_tier_fails(self) -> None:
        result = _gate_safety_tier("CUSTOM_TIER")
        assert result["passed"] is False


# ═══════════════════════════════════════════════════════════════════════════════
# verify_and_evaluate() — main function
# ═══════════════════════════════════════════════════════════════════════════════

class TestVerifyAndEvaluate:
    """Integration tests for the main gate evaluation function."""

    # ── All gates pass → green ──────────────────────────────────────────────

    def test_all_gates_pass_returns_green(self) -> None:
        result = verify_and_evaluate(**_full_green_kwargs())
        assert result["release_status"] == "green"
        assert result["blockers"] == []
        assert result["passed_gates"] == result["total_gates"]
        assert result["failed_gates"] == 0

    def test_all_gates_pass_checks_all_true(self) -> None:
        result = verify_and_evaluate(**_full_green_kwargs())
        for gate_id, check in result["checks"].items():
            assert check["passed"] is True, f"Gate {gate_id} unexpectedly failed"

    def test_green_result_has_eight_gates(self) -> None:
        result = verify_and_evaluate(**_full_green_kwargs())
        assert result["total_gates"] == 8

    def test_green_result_gate_details(self) -> None:
        result = verify_and_evaluate(**_full_green_kwargs())
        details = result["gate_details"]
        assert len(details) == 8
        for gate_id, detail in details.items():
            assert "name" in detail
            assert "passed" in detail
            assert "reason" in detail

    # ── Individual gate failures block release ──────────────────────────────

    def test_g1_failure_blocks_release(self) -> None:
        """None input_payload → G1 fails → release blocked."""
        kwargs = _full_green_kwargs()
        kwargs["input_payload"] = None
        result = verify_and_evaluate(**kwargs)
        assert result["release_status"] == "blocked"
        assert "G1_input_validation" in result["blockers"]

    def test_g2_failure_blocks_release(self) -> None:
        """Non-compliant NFPA results → G2 fails → release blocked."""
        kwargs = _full_green_kwargs()
        kwargs["nfpa_results"] = {"is_compliant": False, "violations": ["spacing too large"]}
        result = verify_and_evaluate(**kwargs)
        assert result["release_status"] == "blocked"
        assert "G2_nfpa_spacing" in result["blockers"]

    def test_g3_failure_blocks_release(self) -> None:
        """Coverage below 99% → G3 fails → release blocked."""
        kwargs = _full_green_kwargs()
        kwargs["input_payload"]["_coverage_pct"] = 85.0
        result = verify_and_evaluate(**kwargs)
        assert result["release_status"] == "blocked"
        assert "G3_coverage" in result["blockers"]

    def test_g4_failure_blocks_release(self) -> None:
        """Wall violations > 0 → G4 fails → release blocked."""
        kwargs = _full_green_kwargs()
        kwargs["input_payload"]["_wall_violations"] = 2
        result = verify_and_evaluate(**kwargs)
        assert result["release_status"] == "blocked"
        assert "G4_wall_distance" in result["blockers"]

    def test_g5_failure_blocks_release(self) -> None:
        """Inadequate battery → G5 fails → release blocked."""
        kwargs = _full_green_kwargs()
        kwargs["battery_result"] = {
            "is_adequate": False,
            "required_ah": 26.0,
            "installed_ah": 18.0,
        }
        result = verify_and_evaluate(**kwargs)
        assert result["release_status"] == "blocked"
        assert "G5_battery" in result["blockers"]

    def test_g6_failure_blocks_release(self) -> None:
        """Non-compliant voltage drop → G6 fails → release blocked."""
        kwargs = _full_green_kwargs()
        kwargs["loop_data"] = {
            "voltage_drop": {"is_compliant": False, "voltage_drop_pct": 15.0},
            "fault_isolation": {"compliant": True, "violations": []},
        }
        result = verify_and_evaluate(**kwargs)
        assert result["release_status"] == "blocked"
        assert "G6_voltage_drop" in result["blockers"]

    def test_g7_failure_blocks_release(self) -> None:
        """Non-compliant fault isolation → G7 fails → release blocked."""
        kwargs = _full_green_kwargs()
        kwargs["loop_data"] = {
            "voltage_drop": {"is_compliant": True, "voltage_drop_pct": 3.0},
            "fault_isolation": {"compliant": False, "violations": ["missing isolator"]},
        }
        result = verify_and_evaluate(**kwargs)
        assert result["release_status"] == "blocked"
        assert "G7_fault_isolation" in result["blockers"]

    def test_g8_failure_blocks_release(self) -> None:
        """Rejected safety tier → G8 fails → release blocked."""
        kwargs = _full_green_kwargs()
        kwargs["input_payload"]["_safety_tier"] = "REJECTED"
        result = verify_and_evaluate(**kwargs)
        assert result["release_status"] == "blocked"
        assert "G8_safety_tier" in result["blockers"]

    # ── Multiple gates failing ──────────────────────────────────────────────

    def test_multiple_gate_failures_blocks_release(self) -> None:
        """Multiple failures still produce 'blocked' and list all blockers."""
        result = verify_and_evaluate(
            input_payload=None,
            nfpa_results=None,
        )
        assert result["release_status"] == "blocked"
        assert len(result["blockers"]) >= 2
        assert result["failed_gates"] >= 2

    def test_multiple_failures_all_reported(self) -> None:
        """All failing gates appear in blockers list."""
        result = verify_and_evaluate(
            input_payload=None,
            nfpa_results=None,
        )
        # G1, G2 fail for sure; G3, G4, G8 may also fail depending on fallback logic
        assert "G1_input_validation" in result["blockers"]
        assert "G2_nfpa_spacing" in result["blockers"]

    # ── Coverage extraction from nfpa_results ───────────────────────────────

    def test_coverage_from_nfpa_results(self) -> None:
        """When _coverage_pct not in input_payload, falls back to nfpa_results."""
        payload = {
            "room_id": "R-101",
            "area_m2": 42.0,
            "_wall_violations": 0,
            "_safety_tier": "PROOF_VERIFIED",
        }
        nfpa = {"is_compliant": True, "coverage_pct": 99.5}
        result = verify_and_evaluate(
            input_payload=payload,
            nfpa_results=nfpa,
            loop_data=_green_loop_data(),
        )
        assert result["checks"]["G3_coverage"]["passed"] is True

    def test_coverage_not_verified_when_no_data(self) -> None:
        """When coverage_pct is unavailable and NFPA not compliant, G3 fails."""
        result = verify_and_evaluate(
            input_payload={"room_id": "R-1", "area_m2": 10.0},
            nfpa_results={"is_compliant": False},
        )
        assert result["checks"]["G3_coverage"]["passed"] is False

    def test_coverage_blocked_without_explicit_data(self) -> None:
        """When coverage_pct unavailable, G3 FAILS even if NFPA says compliant.

        SAFETY FIX (CRITICAL-3): The old behavior allowed is_compliant=True
        to bypass the coverage gate, creating a false-GREEN release pathway.
        Now coverage_pct MUST be explicitly provided — no inference from
        is_compliant. False negatives (blocking good designs) are acceptable.
        False positives (approving bad designs) are NOT acceptable.
        """
        result = verify_and_evaluate(
            input_payload={"room_id": "R-1", "area_m2": 10.0},
            nfpa_results={"is_compliant": True},
        )
        assert result["checks"]["G3_coverage"]["passed"] is False

    # ── Wall violations extraction from nfpa_results ────────────────────────

    def test_wall_violations_from_nfpa_results(self) -> None:
        payload = {
            "room_id": "R-101",
            "area_m2": 42.0,
            "_coverage_pct": 99.5,
            "_safety_tier": "PROOF_VERIFIED",
        }
        nfpa = {"is_compliant": True, "wall_violations": 0}
        result = verify_and_evaluate(
            input_payload=payload,
            nfpa_results=nfpa,
            loop_data=_green_loop_data(),
        )
        assert result["checks"]["G4_wall_distance"]["passed"] is True

    def test_wall_not_verified_when_no_data(self) -> None:
        """When wall_violations unavailable and NFPA not compliant, G4 fails."""
        result = verify_and_evaluate(
            input_payload={"room_id": "R-1", "area_m2": 10.0},
            nfpa_results={"is_compliant": False},
        )
        assert result["checks"]["G4_wall_distance"]["passed"] is False

    # ── Safety tier extraction ──────────────────────────────────────────────

    def test_safety_tier_from_nfpa_results(self) -> None:
        payload = {
            "room_id": "R-101",
            "area_m2": 42.0,
            "_coverage_pct": 99.5,
            "_wall_violations": 0,
        }
        nfpa = {"is_compliant": True, "safety_tier": "PROOF_VERIFIED"}
        result = verify_and_evaluate(
            input_payload=payload,
            nfpa_results=nfpa,
            loop_data=_green_loop_data(),
        )
        assert result["checks"]["G8_safety_tier"]["passed"] is True

    def test_safety_tier_from_evidence_envelope(self) -> None:
        """Safety tier can be extracted from evidence_envelope.safety_tier."""

        class FakeEnvelope:
            safety_tier = "PROOF_VALID"

        payload = {
            "room_id": "R-101",
            "area_m2": 42.0,
            "_coverage_pct": 99.5,
            "_wall_violations": 0,
        }
        result = verify_and_evaluate(
            input_payload=payload,
            nfpa_results={"is_compliant": True},
            loop_data=_green_loop_data(),
            evidence_envelope=FakeEnvelope(),
        )
        assert result["checks"]["G8_safety_tier"]["passed"] is True

    # ── Default (no args) ──────────────────────────────────────────────────

    def test_no_args_produces_blocked(self) -> None:
        """Calling with no arguments should block release."""
        result = verify_and_evaluate()
        assert result["release_status"] == "blocked"
        assert len(result["blockers"]) > 0

    # ── Battery/voltage/fault None → pass (skipped) ────────────────────────

    def test_battery_none_passes(self) -> None:
        kwargs = _full_green_kwargs()
        # battery_result is not in _full_green_kwargs, so it's None by default
        result = verify_and_evaluate(**kwargs)
        assert result["checks"]["G5_battery"]["passed"] is True

    def test_loop_data_none_passes_g5_g6_g7(self) -> None:
        """Without loop_data, G5, G6, G7 should all pass (skipped)."""
        result = verify_and_evaluate(
            input_payload=_green_input_payload(),
            nfpa_results=_green_nfpa_results(),
            # loop_data intentionally omitted
        )
        assert result["checks"]["G5_battery"]["passed"] is True
        assert result["checks"]["G6_voltage_drop"]["passed"] is True
        assert result["checks"]["G7_fault_isolation"]["passed"] is True

    # ── Return structure validation ─────────────────────────────────────────

    def test_return_structure_keys(self) -> None:
        result = verify_and_evaluate(**_full_green_kwargs())
        expected_keys = {
            "release_status", "blockers", "checks",
            "gate_details", "total_gates", "passed_gates", "failed_gates",
        }
        assert set(result.keys()) == expected_keys

    def test_passed_plus_failed_equals_total(self) -> None:
        result = verify_and_evaluate(**_full_green_kwargs())
        assert result["passed_gates"] + result["failed_gates"] == result["total_gates"]


# ═══════════════════════════════════════════════════════════════════════════════
# describe_blockers() — human-readable blocker descriptions
# ═══════════════════════════════════════════════════════════════════════════════

class TestDescribeBlockers:
    """describe_blockers() converts gate results to readable descriptions."""

    def test_green_status_returns_empty_list(self) -> None:
        result = verify_and_evaluate(**_full_green_kwargs())
        descriptions = describe_blockers(result)
        assert descriptions == []

    def test_blocked_status_returns_descriptions(self) -> None:
        result = verify_and_evaluate(input_payload=None)
        descriptions = describe_blockers(result)
        assert len(descriptions) > 0

    def test_descriptions_contain_gate_name_and_reason(self) -> None:
        result = verify_and_evaluate(input_payload=None)
        descriptions = describe_blockers(result)
        for desc in descriptions:
            # Each description should be formatted as "[Gate Name] reason"
            assert desc.startswith("[")
            assert "]" in desc

    def test_descriptions_match_blockers_count(self) -> None:
        result = verify_and_evaluate(input_payload=None)
        descriptions = describe_blockers(result)
        assert len(descriptions) == len(result["blockers"])

    def test_g1_blocker_description_content(self) -> None:
        result = verify_and_evaluate(input_payload=None)
        descriptions = describe_blockers(result)
        # G1 should be in blockers, and its description should mention Input Validation
        g1_descs = [d for d in descriptions if "Input Validation" in d]
        assert len(g1_descs) == 1
        assert "None" in g1_descs[0]

    def test_multiple_blockers_each_described(self) -> None:
        result = verify_and_evaluate(input_payload=None, nfpa_results=None)
        descriptions = describe_blockers(result)
        # Should have descriptions for at least G1 and G2
        gate_names_in_descs = [d.split("]")[0] + "]" for d in descriptions]
        assert any("Input Validation" in g for g in gate_names_in_descs)
        assert any("NFPA 72 Spacing" in g for g in gate_names_in_descs)

    def test_empty_dict_input(self) -> None:
        """Passing an empty dict (no release_status) should not crash."""
        # release_status defaults to not "green", so blockers path is taken
        descriptions = describe_blockers({})
        # With no blockers or details, should return empty descriptions
        assert isinstance(descriptions, list)


# ═══════════════════════════════════════════════════════════════════════════════
# SAFETY PRINCIPLE — false negatives acceptable, false positives NOT
# ═══════════════════════════════════════════════════════════════════════════════

class TestSafetyPrinciple:
    """
    The core safety principle: it is always safer to block than to approve.

    False negatives (blocking a potentially good design) are acceptable.
    False positives (approving a bad design) are NOT acceptable.

    These tests verify the module errs on the side of blocking.
    """

    def test_missing_data_blocks_rather_than_approves(self) -> None:
        """When key data is missing, the design is blocked — never approved."""
        result = verify_and_evaluate()
        assert result["release_status"] == "blocked"

    def test_partial_data_blocks_rather_than_approves(self) -> None:
        """Partial input should never produce a green status."""
        result = verify_and_evaluate(
            input_payload={"room_id": "R-1", "area_m2": 10.0},
        )
        assert result["release_status"] == "blocked"

    def test_ambiguous_coverage_blocks(self) -> None:
        """If coverage cannot be determined, block rather than approve."""
        result = verify_and_evaluate(
            input_payload={"room_id": "R-1", "area_m2": 10.0},
            nfpa_results={"is_compliant": False},  # ambiguous — can't infer coverage
        )
        assert result["checks"]["G3_coverage"]["passed"] is False

    def test_ambiguous_wall_distance_blocks(self) -> None:
        """If wall distance can't be verified, block rather than approve."""
        result = verify_and_evaluate(
            input_payload={"room_id": "R-1", "area_m2": 10.0},
            nfpa_results={"is_compliant": False},
        )
        assert result["checks"]["G4_wall_distance"]["passed"] is False

    def test_ambiguous_safety_tier_blocks(self) -> None:
        """If safety tier is not determined, block rather than approve."""
        result = _gate_safety_tier(None)
        assert result["passed"] is False

    def test_single_gate_failure_is_sufficient_to_block(self) -> None:
        """Even if 7 of 8 gates pass, the one failure blocks release."""
        kwargs = _full_green_kwargs()
        # Introduce a single failure: inadequate battery
        kwargs["battery_result"] = {"is_adequate": False}
        result = verify_and_evaluate(**kwargs)
        assert result["release_status"] == "blocked"
        assert result["failed_gates"] == 1
        assert result["passed_gates"] == 7

    def test_rejected_tier_never_approves(self) -> None:
        """A REJECTED safety tier must never allow release."""
        result = _gate_safety_tier("REJECTED")
        assert result["passed"] is False

    def test_fallback_tier_never_approves(self) -> None:
        """A FALLBACK_USED tier must never allow release."""
        result = _gate_safety_tier("FALLBACK_USED")
        assert result["passed"] is False

    def test_non_compliant_nfpa_never_approves(self) -> None:
        """Non-compliant NFPA spacing must never allow release."""
        result = _gate_nfpa_spacing({"is_compliant": False})
        assert result["passed"] is False

    def test_below_threshold_coverage_never_approves(self) -> None:
        """Coverage just below threshold must never pass."""
        result = _gate_coverage(98.999)
        assert result["passed"] is False

    def test_wall_violations_never_approves(self) -> None:
        """Any wall distance violation must block release."""
        result = _gate_wall_distance(1)
        assert result["passed"] is False
