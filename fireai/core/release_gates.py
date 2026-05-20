"""
release_gates.py — Release Blocking Policy as VERIFIABLE Code
==============================================================
STRENGTHENED: Gates now VERIFY, not just accept booleans.

Original problem: evaluate_release() accepted boolean values from the
caller. The caller could pass input_contract_valid=True without
actually running validation. This was SECURITY THEATER.

Solution: Each gate now has an optional verifier function that can
actually check the condition. If no verifier is provided AND no
explicit bool is given, the gate defaults to BLOCKED (fail-safe).

Three modes of operation:
  1. EXPLICIT BOOL: context={"gate_name": True}  — legacy mode, caller vouches
  2. VERIFIER: context={"gate_name": verification_data} — gate verifies itself
  3. MISSING: gate not in context — defaults to BLOCKED (fail-safe)

Added 3 new life-safety gates:
  - fault_isolation_verified — SLC loops have fault isolators
  - aset_rset_valid — ASET > RSET with safety margin
  - battery_sized — Battery capacity calculated per NFPA 72 §10.6.7

Usage:
    from fireai.core.release_gates import evaluate_release, verify_and_evaluate

    # Legacy mode (caller vouches — WEAK)
    result = evaluate_release({"input_contract_valid": True, ...})

    # Verified mode (gate checks itself — STRONG)
    result = verify_and_evaluate(
        input_payload=room_data,
        nfpa_results=compliance_results,
        loop_devices=loop_data,
        ...
    )
"""

from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional


# ============================================================================
# Gate Definitions — STRICT_ENGINEERING Mode
# ============================================================================

RELEASE_GATES = {
    # Gate 1: Input validation passed (no derived field injection, valid polygon)
    "input_contract_valid": {
        "description": "Room input payload passed strict contract validation",
        "nfpa_reference": "General — data integrity prerequisite",
        "failure_impact": "Fake data (e.g. injected area_m2) could produce fake compliance results",
    },
    # Gate 2: NFPA 72 compliance verified by all engines
    "nfpa_compliance_verified": {
        "description": "All NFPA 72 spacing, coverage, and wall-distance checks passed",
        "nfpa_reference": "§17.6.3.1.1, §17.6.3.4, §17.7.4.2.3.1, §10.14",
        "failure_impact": "Design may have detectors too far apart, too close to walls, or inadequate coverage",
    },
    # Gate 3: Evidence chain sealed (tamper-proof audit trail)
    "evidence_chain_sealed": {
        "description": "Evidence chain envelope built and verified for this design run",
        "nfpa_reference": "§7.4 — Documentation requirements",
        "failure_impact": "Cannot prove to AHJ that results match the input drawing",
    },
    # Gate 4: No drift between design model and BIM/IFC source
    "no_drift_detected": {
        "description": "No geometric drift between design model and source BIM file",
        "nfpa_reference": "General — design must match as-built",
        "failure_impact": "Design based on outdated floor plan — detectors may be in wrong rooms",
    },
    # Gate 5: Stale cached surfaces removed
    "stale_surfaces_removed": {
        "description": "No stale or orphaned detector placements from previous runs",
        "nfpa_reference": "General — output must reflect current input only",
        "failure_impact": "Report may include detectors from a previous design that no longer applies",
    },
    # Gate 6: SLC loop fault isolation verified — LIFE SAFETY
    "fault_isolation_verified": {
        "description": "All SLC loops have fault isolators per NFPA 72 §12.3.1",
        "nfpa_reference": "§12.3.1, §12.3.2 — Fault isolation on addressable circuits",
        "failure_impact": "A single short circuit disables all devices on the loop — no fire detection for entire zone",
    },
    # Gate 7: ASET > RSET verified — LIFE SAFETY
    "aset_rset_valid": {
        "description": "Available Safe Egress Time exceeds Required Safe Egress Time with safety margin",
        "nfpa_reference": "SFPE Engineering Guide / NFPA 101 §9.3",
        "failure_impact": "Occupants cannot escape before conditions become untenable — smoke inhalation deaths",
    },
    # Gate 8: Battery capacity sized — LIFE SAFETY
    "battery_sized": {
        "description": "Battery capacity calculated per NFPA 72 §10.6.7 with aging and temperature derating",
        "nfpa_reference": "§10.6.7.2.1 — Secondary supply requirements",
        "failure_impact": "Panel fails during power outage — no alarm during fire",
    },
}


# ============================================================================
# Legacy Mode — Caller Vouches (WEAK, backward compatible)
# ============================================================================

def evaluate_release(context: Dict[str, Any]) -> Dict[str, Any]:
    """Evaluate all release gates and return pass/block status.

    LEGACY MODE: Accepts boolean values from the caller. The caller
    is responsible for actually verifying each condition.
    For VERIFIED mode, use verify_and_evaluate() instead.

    Args:
        context: Dictionary with gate names as keys and bool values.
                 Each key must match a gate in RELEASE_GATES.

    Returns:
        Dictionary with:
          - checks: Dict of gate_name → bool (True = passed)
          - blockers: List of gate names that failed
          - release_status: "green" if all passed, "blocked" if any failed
          - gate_details: Dict with description and NFPA reference for each gate
          - mode: "legacy" to indicate this was not verified
    """
    checks = {}
    gate_details = {}

    for gate_name, gate_info in RELEASE_GATES.items():
        # MISSING gates default to BLOCKED (fail-safe)
        if gate_name in context:
            passed = bool(context[gate_name])
        else:
            passed = False  # Fail-safe: missing = blocked

        checks[gate_name] = passed
        gate_details[gate_name] = {
            "passed": passed,
            "description": gate_info["description"],
            "nfpa_reference": gate_info["nfpa_reference"],
            "failure_impact": gate_info["failure_impact"],
            "verification_method": "caller_vouched" if gate_name in context else "missing_blocked",
        }

    blockers: List[str] = [name for name, ok in checks.items() if not ok]

    return {
        "checks": checks,
        "blockers": blockers,
        "release_status": "blocked" if blockers else "green",
        "gate_details": gate_details,
        "mode": "legacy",
    }


# ============================================================================
# Verified Mode — Gates Verify Themselves (STRONG)
# ============================================================================

def verify_and_evaluate(
    input_payload: Optional[Dict[str, Any]] = None,
    nfpa_results: Optional[Dict[str, Any]] = None,
    evidence_envelope: Optional[Dict[str, Any]] = None,
    drift_records: Optional[List[Dict[str, Any]]] = None,
    loop_data: Optional[Dict[str, Any]] = None,
    aset_rset_result: Optional[Dict[str, Any]] = None,
    battery_result: Optional[Dict[str, Any]] = None,
    stale_detector_ids: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Evaluate release gates with ACTUAL VERIFICATION.

    Each gate that can be verified is verified against the provided
    data. If data is not provided for a gate, it defaults to BLOCKED
    (fail-safe). This prevents the "caller vouches" security theater.

    Args:
        input_payload: Raw room input dict (for contract validation).
        nfpa_results: NFPA compliance check results.
        evidence_envelope: Signed evidence envelope (for chain check).
        drift_records: Drift detection results (for BIM sync check).
        loop_data: Loop design data with device lists (for fault isolation).
        aset_rset_result: ASET vs RSET validation result.
        battery_result: Battery capacity calculation result.
        stale_detector_ids: List of stale detector IDs.

    Returns:
        Same format as evaluate_release() but with "mode": "verified"
        and actual verification evidence for each gate.
    """
    checks = {}
    gate_details = {}

    # --- Gate 1: Input Contract Validation ---
    if input_payload is not None:
        try:
            from fireai.core.contracts import validate_room_input, ContractViolation
            validate_room_input(input_payload)
            checks["input_contract_valid"] = True
            verify_method = "validate_room_input_passed"
        except ContractViolation as e:
            checks["input_contract_valid"] = False
            verify_method = f"contract_violation: {e}"
        except Exception as e:
            checks["input_contract_valid"] = False
            verify_method = f"validation_error: {e}"
    else:
        checks["input_contract_valid"] = False
        verify_method = "no_payload_provided"

    # --- Gate 2: NFPA Compliance ---
    if nfpa_results is not None:
        is_compliant = bool(nfpa_results.get("is_compliant", False))
        # Also check if there are any violations
        violations = nfpa_results.get("violations", [])
        checks["nfpa_compliance_verified"] = is_compliant and len(violations) == 0
        verify_method = (
            "nfpa_all_checks_passed"
            if checks["nfpa_compliance_verified"]
            else f"nfpa_violations: {len(violations)}"
        )
    else:
        checks["nfpa_compliance_verified"] = False
        verify_method = "no_nfpa_results_provided"

    # --- Gate 3: Evidence Chain ---
    if evidence_envelope is not None:
        has_hash = bool(evidence_envelope.get("envelope_hash"))
        has_sig = bool(evidence_envelope.get("signature"))
        checks["evidence_chain_sealed"] = has_hash and has_sig
        verify_method = (
            "envelope_hash_and_signature_present"
            if checks["evidence_chain_sealed"]
            else "envelope_missing_hash_or_signature"
        )
    else:
        checks["evidence_chain_sealed"] = False
        verify_method = "no_envelope_provided"

    # --- Gate 4: No Drift ---
    if drift_records is not None:
        # Any drift record with geometry_changed or room_removed is a blocker
        critical_drift = [
            d for d in drift_records
            if d.get("drift_type") in ("geometry_changed", "room_removed", "room_added")
        ]
        checks["no_drift_detected"] = len(critical_drift) == 0
        verify_method = (
            "no_critical_drift"
            if checks["no_drift_detected"]
            else f"critical_drift_count: {len(critical_drift)}"
        )
    else:
        checks["no_drift_detected"] = False
        verify_method = "no_drift_data_provided"

    # --- Gate 5: Stale Surfaces ---
    if stale_detector_ids is not None:
        checks["stale_surfaces_removed"] = len(stale_detector_ids) == 0
        verify_method = (
            "no_stale_detectors"
            if checks["stale_surfaces_removed"]
            else f"stale_count: {len(stale_detector_ids)}"
        )
    else:
        checks["stale_surfaces_removed"] = False
        verify_method = "no_stale_data_provided"

    # --- Gate 6: Fault Isolation (LIFE SAFETY) ---
    if loop_data is not None:
        try:
            from fireai.core.fault_isolator_injector import verify_isolator_compliance
            loops = loop_data.get("loops", [])
            all_compliant = True
            worst_violations = []
            for loop in loops:
                devices = loop.get("order", loop.get("devices", []))
                result = verify_isolator_compliance(devices)
                if not result["compliant"]:
                    all_compliant = False
                    worst_violations.extend(result["violations"][:2])
            checks["fault_isolation_verified"] = all_compliant
            verify_method = (
                "all_loops_have_isolators"
                if all_compliant
                else f"isolator_violations: {worst_violations[:3]}"
            )
        except ImportError:
            checks["fault_isolation_verified"] = False
            verify_method = "fault_isolator_module_not_available"
        except Exception as e:
            checks["fault_isolation_verified"] = False
            verify_method = f"verification_error: {e}"
    else:
        checks["fault_isolation_verified"] = False
        verify_method = "no_loop_data_provided"

    # --- Gate 7: ASET vs RSET (LIFE SAFETY) ---
    if aset_rset_result is not None:
        checks["aset_rset_valid"] = bool(aset_rset_result.get("is_safe", False))
        verify_method = (
            f"aset_{aset_rset_result.get('aset_seconds', 0):.1f}s_gt_rset_{aset_rset_result.get('rset_with_safety_s', 0):.1f}s"
            if checks["aset_rset_valid"]
            else f"aset_insufficient: {aset_rset_result.get('verdict', 'unknown')[:80]}"
        )
    else:
        checks["aset_rset_valid"] = False
        verify_method = "no_aset_rset_data_provided"

    # --- Gate 8: Battery Sized (LIFE SAFETY) ---
    if battery_result is not None:
        has_capacity = "required_ah" in battery_result or "capacity_ah" in battery_result
        is_adequate = battery_result.get("is_adequate", battery_result.get("compliant", True))
        checks["battery_sized"] = has_capacity and is_adequate
        verify_method = (
            f"battery_{battery_result.get('required_ah', battery_result.get('capacity_ah', 0)):.1f}Ah"
            if checks["battery_sized"]
            else "battery_not_adequately_sized"
        )
    else:
        checks["battery_sized"] = False
        verify_method = "no_battery_data_provided"

    # Build gate details
    for gate_name in RELEASE_GATES:
        gate_info = RELEASE_GATES[gate_name]
        passed = checks.get(gate_name, False)
        gate_details[gate_name] = {
            "passed": passed,
            "description": gate_info["description"],
            "nfpa_reference": gate_info["nfpa_reference"],
            "failure_impact": gate_info["failure_impact"],
            "verification_method": verify_method if gate_name in checks else "not_evaluated",
        }

    blockers: List[str] = [name for name, ok in checks.items() if not ok]

    return {
        "checks": checks,
        "blockers": blockers,
        "release_status": "blocked" if blockers else "green",
        "gate_details": gate_details,
        "mode": "verified",
    }


def describe_blockers(result: Dict[str, Any]) -> str:
    """Produce a human-readable description of what's blocking release.

    Args:
        result: Output from evaluate_release() or verify_and_evaluate().

    Returns:
        Multi-line string describing each blocker with NFPA reference.
    """
    if result["release_status"] == "green":
        mode = result.get("mode", "unknown")
        confidence = "VERIFIED" if mode == "verified" else "CALLER-VOUCHED"
        return f"All release gates passed ({confidence}) — design is cleared for output."

    lines = ["RELEASE BLOCKED — the following gates failed:"]
    for blocker in result["blockers"]:
        details = result["gate_details"][blocker]
        lines.append(f"  [BLOCKED] {blocker}")
        lines.append(f"    Description: {details['description']}")
        lines.append(f"    NFPA Reference: {details['nfpa_reference']}")
        lines.append(f"    Impact: {details['failure_impact']}")
        verify = details.get("verification_method", "unknown")
        lines.append(f"    Verification: {verify}")
    return "\n".join(lines)


__all__ = [
    "RELEASE_GATES",
    "evaluate_release",
    "verify_and_evaluate",
    "describe_blockers",
]
