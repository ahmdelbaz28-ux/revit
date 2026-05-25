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
    evidence_secret_key: Optional[str] = None,
) -> Dict[str, Any]:
    """Evaluate release gates with ACTUAL VERIFICATION.

    Each gate that can be verified is verified against the provided
    data. If data is not provided for a gate, it defaults to BLOCKED
    (fail-safe). This prevents the "caller vouches" security theater.

    FIX v2: The single `verify_method` variable was overwritten by each
    gate, causing ALL gates to show the LAST gate's verification_method.
    Now uses `verify_methods` dict for per-gate tracking.

    STRENGTHENED v2:
    - Gate 3: Actually verifies HMAC signature (not just key presence).
    - Gate 7: Numerically re-verifies ASET > RSET * safety_factor.
    - Gate 8: Verifies capacity values are positive (not just key existence).

    Args:
        input_payload: Raw room input dict (for contract validation).
        nfpa_results: NFPA compliance check results.
        evidence_envelope: Signed evidence envelope (for chain check).
        drift_records: Drift detection results (for BIM sync check).
        loop_data: Loop design data with device lists (for fault isolation).
        aset_rset_result: ASET vs RSET validation result.
        battery_result: Battery capacity calculation result.
        stale_detector_ids: List of stale detector IDs.
        evidence_secret_key: Secret key for HMAC verification of evidence envelope.
            If provided, Gate 3 performs full cryptographic verification.
            If not provided, Gate 3 falls back to structural check only.

    Returns:
        Same format as evaluate_release() but with "mode": "verified"
        and actual verification evidence for each gate.
    """
    checks = {}
    verify_methods = {}  # FIX: per-gate verification method (was single variable overwritten)

    # --- Gate 1: Input Contract Validation ---
    if input_payload is not None:
        try:
            from fireai.core.contracts import validate_room_input, ContractViolation
            validate_room_input(input_payload)
            checks["input_contract_valid"] = True
            verify_methods["input_contract_valid"] = "validate_room_input_passed"
        except ContractViolation as e:
            checks["input_contract_valid"] = False
            verify_methods["input_contract_valid"] = f"contract_violation: {e}"
        except Exception as e:
            checks["input_contract_valid"] = False
            verify_methods["input_contract_valid"] = f"validation_error: {e}"
    else:
        checks["input_contract_valid"] = False
        verify_methods["input_contract_valid"] = "no_payload_provided"

    # --- Gate 2: NFPA Compliance ---
    if nfpa_results is not None:
        is_compliant = bool(nfpa_results.get("is_compliant", False))
        # Also check if there are any violations
        # V53 FIX (F-005): Missing "violations" key treated as empty (no violations).
        # This is inconsistent with fail-safe principle — missing violation data should
        # be treated as unknown (block), not as empty (pass).
        violations = nfpa_results.get("violations")
        if violations is None:
            checks["nfpa_compliance_verified"] = False
            verify_methods["nfpa_compliance_verified"] = "violations_key_missing_from_nfpa_results"
        else:
            checks["nfpa_compliance_verified"] = is_compliant and len(violations) == 0
            verify_methods["nfpa_compliance_verified"] = (
                "nfpa_all_checks_passed"
                if checks["nfpa_compliance_verified"]
                else f"nfpa_violations: {len(violations)}"
            )
    else:
        checks["nfpa_compliance_verified"] = False
        verify_methods["nfpa_compliance_verified"] = "no_nfpa_results_provided"

    # --- Gate 3: Evidence Chain ---
    # STRENGTHENED: Actually verify HMAC, not just check key presence.
    # The old code only checked `has_hash and has_sig`, which is security theater —
    # an attacker can inject fake hash/signature values. Now we call
    # EvidenceChain.verify_envelope() to cryptographically validate.
    if evidence_envelope is not None:
        snapshot_payload_for_verify = input_payload  # Use the input payload as snapshot
        analysis_payload_for_verify = nfpa_results  # Use the NFPA results as analysis
        try:
            from fireai.core.evidence_chain import EvidenceChain
            # Reconstruct the chain with the signer_id from the envelope
            signer_id = evidence_envelope.get("signer_id", "fireai-v1")
            # Use the explicitly provided secret_key (never read from envelope itself —
            # that would allow an attacker to supply their own key)
            secret_key = evidence_secret_key
            if secret_key and snapshot_payload_for_verify and analysis_payload_for_verify:
                chain = EvidenceChain(secret_key=secret_key, signer_id=signer_id)
                hmac_valid = chain.verify_envelope(
                    envelope=evidence_envelope,
                    snapshot_payload=snapshot_payload_for_verify,
                    analysis_payload=analysis_payload_for_verify,
                )
                checks["evidence_chain_sealed"] = hmac_valid
                verify_methods["evidence_chain_sealed"] = (
                    "hmac_signature_verified"
                    if hmac_valid
                    else "hmac_signature_invalid"
                )
            else:
                # V53 FIX (F-003): Structural check (hash+sig present) is SECURITY THEATER.
                # An attacker could inject {"envelope_hash": "fake", "signature": "also_fake"}
                # and pass the gate. Without HMAC key, we CANNOT verify integrity.
                # Evidence chain integrity is non-negotiable per NFPA 72 §7.4.
                # GATE BLOCKED when HMAC verification is not possible.
                has_hash = bool(evidence_envelope.get("envelope_hash"))
                has_sig = bool(evidence_envelope.get("signature"))
                has_prev = "previous_envelope_hash" in evidence_envelope
                # V53 FIX (F-004): has_prev was computed but not used — chain requires
                # linking to previous envelope. Missing previous_envelope_hash = broken chain.
                checks["evidence_chain_sealed"] = False  # Always BLOCK without HMAC verification
                verify_methods["evidence_chain_sealed"] = (
                    "hmac_key_or_payloads_missing_GATE_BLOCKED"
                    # "structural" check is NOT verification — documented for audit only
                    f"_structural_indicators: hash={has_hash}_sig={has_sig}_prev={has_prev}"
                )
        except ImportError:
            # V52 FIX: Gate 3 ImportError should BLOCK (consistent with Gate 6).
            # Structural check (key existence) is NOT cryptographic verification.
            # An attacker could inject {"envelope_hash": "fake", "signature": "also_fake"}
            # and pass the gate. Evidence chain integrity is non-negotiable.
            checks["evidence_chain_sealed"] = False
            verify_methods["evidence_chain_sealed"] = (
                "evidence_chain_module_unavailable_GATE_BLOCKED"
            )
        except Exception as e:
            checks["evidence_chain_sealed"] = False
            verify_methods["evidence_chain_sealed"] = f"verification_error: {e}"
    else:
        checks["evidence_chain_sealed"] = False
        verify_methods["evidence_chain_sealed"] = "no_envelope_provided"

    # --- Gate 4: No Drift ---
    if drift_records is not None:
        # Any drift record with geometry_changed, room_removed/added, ceiling_height_changed,
        # or detector_type_changed is a blocker. These directly affect NFPA 72 compliance.
        critical_drift_types = (
            "geometry_changed", "room_removed", "room_added",
            "ceiling_height_changed", "detector_type_changed",
        )
        critical_drift = [
            d for d in drift_records
            if d.get("drift_type") in critical_drift_types
        ]
        checks["no_drift_detected"] = len(critical_drift) == 0
        verify_methods["no_drift_detected"] = (
            "no_critical_drift"
            if checks["no_drift_detected"]
            else f"critical_drift_count: {len(critical_drift)}"
        )
    else:
        checks["no_drift_detected"] = False
        verify_methods["no_drift_detected"] = "no_drift_data_provided"

    # --- Gate 5: Stale Surfaces ---
    if stale_detector_ids is not None:
        checks["stale_surfaces_removed"] = len(stale_detector_ids) == 0
        verify_methods["stale_surfaces_removed"] = (
            "no_stale_detectors"
            if checks["stale_surfaces_removed"]
            else f"stale_count: {len(stale_detector_ids)}"
        )
    else:
        checks["stale_surfaces_removed"] = False
        verify_methods["stale_surfaces_removed"] = "no_stale_data_provided"

    # --- Gate 6: Fault Isolation (LIFE SAFETY) ---
    if loop_data is not None:
        try:
            from fireai.core.fault_isolator_injector import verify_isolator_compliance
            loops = loop_data.get("loops", [])
            all_compliant = True
            worst_violations = []
            for loop in loops:
                devices = loop.get("order", loop.get("devices", []))
                # V52 FIX: Empty device list passes fault isolation trivially.
                # verify_isolator_compliance([]) returns compliant=True because
                # empty loop has no violations. But an empty loop means we
                # CANNOT verify isolation — the data is missing.
                if not devices:
                    all_compliant = False
                    worst_violations.append(
                        f"Loop '{loop.get('id', '?')}' has no devices — "
                        f"cannot verify fault isolation per NFPA 72 §12.3.1"
                    )
                    continue
                result = verify_isolator_compliance(devices)
                if not result["compliant"]:
                    all_compliant = False
                    worst_violations.extend(result["violations"][:2])
            checks["fault_isolation_verified"] = all_compliant
            verify_methods["fault_isolation_verified"] = (
                "all_loops_have_isolators"
                if all_compliant
                else f"isolator_violations: {worst_violations[:3]}"
            )
        except ImportError:
            checks["fault_isolation_verified"] = False
            verify_methods["fault_isolation_verified"] = "fault_isolator_module_not_available"
        except Exception as e:
            checks["fault_isolation_verified"] = False
            verify_methods["fault_isolation_verified"] = f"verification_error: {e}"
    else:
        checks["fault_isolation_verified"] = False
        verify_methods["fault_isolation_verified"] = "no_loop_data_provided"

    # --- Gate 7: ASET vs RSET (LIFE SAFETY) ---
    # STRENGTHENED: Don't just trust is_safe boolean — verify ASET > RSET numerically.
    # If aset_rset_result contains raw scenario data, we can also compute
    # ASET from the semi_cfast_engine for independent verification.
    if aset_rset_result is not None:
        aset_s = float(aset_rset_result.get("aset_seconds", 0))
        rset_s = float(aset_rset_result.get("rset_seconds", 0))
        safety_factor = float(aset_rset_result.get("safety_factor", 1.5))

        # V52 FIX: NaN/Inf values bypass ALL ASET/RSET checks.
        # ASET=Inf > any RSET → gate PASSES with corrupted data.
        # safety_factor=0 negates the entire check (ASET > RSET*0 = ASET > 0).
        # Both must be caught before the numeric comparison.
        import math as _gate_math
        MIN_ASET_RSET_SAFETY_FACTOR = 1.0  # Absolute minimum (SFPE recommends 1.5-2.0)
        aset_rset_invalid = False
        for _name, _val in [("aset", aset_s), ("rset", rset_s), ("safety_factor", safety_factor)]:
            if not _gate_math.isfinite(_val):
                verify_methods["aset_rset_valid"] = f"{_name}_is_not_finite: {_val}"
                aset_rset_invalid = True
                break
        if not aset_rset_invalid and safety_factor < MIN_ASET_RSET_SAFETY_FACTOR:
            verify_methods["aset_rset_valid"] = (
                f"safety_factor_{safety_factor}_below_minimum_{MIN_ASET_RSET_SAFETY_FACTOR}"
            )
            aset_rset_invalid = True

        if aset_rset_invalid:
            checks["aset_rset_valid"] = False
        # V53 FIX (F-001): Gate 7 re-verification used to OVERRIDE the
        # aset_rset_invalid flag. When safety_factor < MIN_ASET_RSET_SAFETY_FACTOR,
        # the gate must remain BLOCKED regardless of numeric_safe. A safety_factor
        # below 1.0 means occupants may not escape before untenable conditions —
        # smoke inhalation death risk per SFPE / NFPA 101 §9.3.
        # Example bypass: ASET=600s, RSET=800s, safety_factor=0.5:
        #   numeric_safe = 600 > 800*0.5=400 → True → gate PASSES with factor=0.5!
        else:
            # Only proceed to numeric re-verification if pre-validation passed
            # If ASET is not provided but scenario data is, compute it
            if aset_s <= 0 and "scenario" in aset_rset_result:
                try:
                    from fireai.core.semi_cfast_engine import (
                        calculate_aset, FireScenario, TenabilityCriteria,
                    )
                    scenario_data = aset_rset_result["scenario"]
                    scenario = FireScenario(**scenario_data)
                    criteria_data = aset_rset_result.get("criteria", {})
                    criteria = TenabilityCriteria(**criteria_data) if criteria_data else None
                    aset_result = calculate_aset(scenario, criteria)
                    aset_s = aset_result.aset_seconds
                except Exception as e:
                    verify_methods.setdefault("aset_rset_valid", f"aset_computation_failed: {e}")

            # Re-verify: ASET must exceed RSET * safety_factor (SFPE / NFPA 101 §9.3)
            numeric_safe = aset_s > 0 and rset_s > 0 and aset_s > rset_s * safety_factor
            # If the caller claims is_safe but our numeric check disagrees, TRUST the math.
            if numeric_safe:
                checks["aset_rset_valid"] = True
                verify_methods["aset_rset_valid"] = (
                    f"aset_{aset_s:.1f}s_gt_rset×{safety_factor}_{rset_s * safety_factor:.1f}s"
                )
            else:
                checks["aset_rset_valid"] = False
                if aset_s <= 0 or rset_s <= 0:
                    verify_methods["aset_rset_valid"] = "aset_or_rset_zero_or_negative"
                else:
                    verify_methods["aset_rset_valid"] = (
                        f"aset_{aset_s:.1f}s_not_gt_rset×{safety_factor}_{rset_s * safety_factor:.1f}s"
                    )
    else:
        checks["aset_rset_valid"] = False
        verify_methods["aset_rset_valid"] = "no_aset_rset_data_provided"

    # --- Gate 8: Battery Sized (LIFE SAFETY) ---
    # STRENGTHENED: Verify capacity is positive and adequate, not just key existence.
    if battery_result is not None:
        # V52 FIX: capacity_ah used as fallback for BOTH required_ah AND installed_ah
        # makes them always equal, so installed_meets is always True.
        # required_ah and installed_ah are fundamentally different quantities:
        # required_ah = calculated capacity needed (alarm load × duration × derating)
        # installed_ah = actual battery capacity installed
        # Only use capacity_ah as fallback for installed_ah (conservative).
        required_ah = battery_result.get("required_ah", 0)  # No false fallback
        installed_ah = battery_result.get("installed_ah", battery_result.get("capacity_ah", 0))
        # V43 FIX: Default is_adequate to False (fail-safe). Previously defaulted
        # to True, allowing insufficient battery capacity to pass when the
        # battery result dict lacked 'is_adequate' or 'compliant' keys.
        # NFPA 72 §10.6.7.2.1 requires secondary supply — assuming adequacy
        # without evidence is a life-safety failure.
        is_adequate = battery_result.get("is_adequate", battery_result.get("compliant", False))
        # V52 FIX: is_adequate=True must NOT override failed numeric check.
        # A boolean claim should NEVER override a failed numeric verification.
        # Per NFPA 72 §10.6.7.2.1, secondary supply must be CALCULATED, not claimed.
        # V53 FIX (F-002): float('inf') bypasses battery adequacy gate.
        # isinstance(float('inf'), (int, float)) → True, inf > 0 → True, inf >= x → True.
        # Infinite values indicate corrupted/missing data — must BLOCK.
        import math as _gate_math_batt
        batt_nan_inf = False
        for _bname, _bval in [("required_ah", required_ah), ("installed_ah", installed_ah)]:
            if isinstance(_bval, float) and not _gate_math_batt.isfinite(_bval):
                checks["battery_sized"] = False
                verify_methods["battery_sized"] = f"{_bname}_is_not_finite: {_bval}"
                batt_nan_inf = True
                break
        if not batt_nan_inf:
            has_required = isinstance(required_ah, (int, float)) and required_ah > 0
            installed_meets = isinstance(installed_ah, (int, float)) and installed_ah >= required_ah
            checks["battery_sized"] = has_required and installed_meets
            verify_methods["battery_sized"] = (
                f"battery_required_{required_ah:.1f}Ah_installed_{installed_ah:.1f}Ah"
                if checks["battery_sized"]
                else f"battery_insufficient: required_{required_ah}Ah_installed_{installed_ah}Ah"
            )
    else:
        checks["battery_sized"] = False
        verify_methods["battery_sized"] = "no_battery_data_provided"

    # Build gate details — FIX: use per-gate verify_methods dict
    gate_details = {}
    for gate_name in RELEASE_GATES:
        gate_info = RELEASE_GATES[gate_name]
        passed = checks.get(gate_name, False)
        gate_details[gate_name] = {
            "passed": passed,
            "description": gate_info["description"],
            "nfpa_reference": gate_info["nfpa_reference"],
            "failure_impact": gate_info["failure_impact"],
            "verification_method": verify_methods.get(gate_name, "not_evaluated"),
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
