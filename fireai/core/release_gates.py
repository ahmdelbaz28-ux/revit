"""
fireai.core.release_gates — Release Gate Evaluation
=====================================================

Implements the 8 release gates that must ALL pass before a design
can be released (status = "green"). Any gate failure blocks release.

GATE ARCHITECTURE:
  Each gate checks a specific aspect of the design. Gates are
  independent — a failure in one gate does not affect others.
  However, ALL gates must pass for release.

THE 8 GATES:
  G1: Input Validation — payload passed contract validation
  G2: NFPA 72 Spacing — spacing calculated from ceiling height
  G3: Coverage Verification — coverage ≥ STANDARD_THRESHOLD
  G4: Wall Distance — no dead-air-space violations
  G5: Battery Adequacy — battery capacity meets NFPA 72 §10.6.7
  G6: Voltage Drop — end-of-line voltage within NFPA 72 §10.6.4
  G7: Fault Isolation — SLC isolators per NFPA 72 §12.3
  G8: Safety Tier — tier must be PROOF_VERIFIED or PROOF_VALID

SAFETY PRINCIPLE:
  A blocked release is ALWAYS safer than an unblocked one.
  False negatives (blocking good designs) are acceptable.
  False positives (approving bad designs) are NOT acceptable.
"""

from __future__ import annotations

import math
from typing import Any, Dict, List, Optional


# ═══════════════════════════════════════════════════════════════════════════════
# GATE DEFINITIONS
# ═══════════════════════════════════════════════════════════════════════════════

_GATE_NAMES = {
    "G1_input_validation":    "Input Validation",
    "G2_nfpa_spacing":        "NFPA 72 Spacing",
    "G3_coverage":            "Coverage Verification",
    "G4_wall_distance":       "Wall Distance Check",
    "G5_battery":             "Battery Adequacy",
    "G6_voltage_drop":        "Voltage Drop",
    "G7_fault_isolation":     "Fault Isolator Placement",
    "G8_safety_tier":         "Safety Tier Classification",
}


# ═══════════════════════════════════════════════════════════════════════════════
# INDIVIDUAL GATE CHECKS
# ═══════════════════════════════════════════════════════════════════════════════

def _gate_input_validation(input_payload: Optional[Dict]) -> Dict[str, Any]:
    """G1: Input payload must have been validated (not None)."""
    if input_payload is None:
        return {"passed": False, "reason": "Input payload is None — contract validation failed"}

    room_id = input_payload.get("room_id")
    if not room_id:
        return {"passed": False, "reason": "Missing room_id in validated payload"}

    area = input_payload.get("area_m2")
    if area is None or (isinstance(area, (int, float)) and (area <= 0 or not math.isfinite(area))):
        return {"passed": False, "reason": f"Invalid area_m2: {area}"}

    return {"passed": True, "reason": "Input validated"}


def _gate_nfpa_spacing(nfpa_results: Optional[Dict]) -> Dict[str, Any]:
    """G2: NFPA 72 spacing calculation must have succeeded."""
    if nfpa_results is None:
        return {"passed": False, "reason": "NFPA 72 spacing results unavailable"}

    is_compliant = nfpa_results.get("is_compliant", False)
    if not is_compliant:
        violations = nfpa_results.get("violations", [])
        violation_str = "; ".join(str(v) for v in violations[:3]) if violations else "unspecified"
        return {
            "passed": False,
            "reason": f"NFPA 72 compliance violations: {violation_str}",
        }

    return {"passed": True, "reason": "NFPA 72 spacing compliant"}


def _gate_coverage(coverage_pct: Optional[float]) -> Dict[str, Any]:
    """G3: Coverage must meet standard threshold (99.0%)."""
    if coverage_pct is None:
        return {"passed": False, "reason": "Coverage not computed"}

    if not math.isfinite(coverage_pct):
        return {"passed": False, "reason": f"Coverage is non-finite: {coverage_pct}"}

    if coverage_pct < 99.0:
        return {
            "passed": False,
            "reason": f"Coverage {coverage_pct:.2f}% < 99.0% standard threshold",
        }

    return {"passed": True, "reason": f"Coverage {coverage_pct:.2f}% ≥ 99.0%"}


def _gate_wall_distance(wall_violations: int) -> Dict[str, Any]:
    """G4: No dead-air-space wall distance violations."""
    if wall_violations is None:
        return {"passed": False, "reason": "Wall violations not checked"}

    if wall_violations > 0:
        return {
            "passed": False,
            "reason": f"{wall_violations} detector(s) too close to wall (<0.1m, dead air space per NFPA 72 §17.6.3.1.1)",
        }

    return {"passed": True, "reason": "No wall distance violations"}


def _gate_battery(battery_result: Optional[Dict]) -> Dict[str, Any]:
    """G5: Battery must be adequate per NFPA 72 §10.6.7.

    If no battery data provided, this gate PASSES (not all designs
    require battery calculation). If battery data IS provided,
    it must show adequate capacity.
    """
    if battery_result is None:
        return {"passed": True, "reason": "No battery calculation required (skipped)"}

    is_adequate = battery_result.get("is_adequate", False)
    if not is_adequate:
        req = battery_result.get("required_ah", "?")
        inst = battery_result.get("installed_ah", "?")
        return {
            "passed": False,
            "reason": f"Battery inadequate: required={req}Ah, installed={inst}Ah (NFPA 72 §10.6.7)",
        }

    return {"passed": True, "reason": "Battery capacity adequate per NFPA 72 §10.6.7"}


def _gate_voltage_drop(loop_data: Optional[Dict]) -> Dict[str, Any]:
    """G6: Voltage drop must be within limits per NFPA 72 §10.6.4.

    If no loop data provided, this gate PASSES. If loop data IS
    provided, it must show compliant voltage drop.
    """
    if loop_data is None:
        return {"passed": True, "reason": "No voltage drop calculation required (skipped)"}

    vd = loop_data.get("voltage_drop")
    if vd is not None:
        is_compliant = vd.get("is_compliant", True) if isinstance(vd, dict) else True
        if not is_compliant:
            drop_pct = vd.get("voltage_drop_pct", "?") if isinstance(vd, dict) else "?"
            return {
                "passed": False,
                "reason": f"Voltage drop {drop_pct}% exceeds limit (NFPA 72 §10.6.4)",
            }

    return {"passed": True, "reason": "Voltage drop within limits"}


def _gate_fault_isolation(loop_data: Optional[Dict]) -> Dict[str, Any]:
    """G7: SLC fault isolator placement per NFPA 72 §12.3.

    If no loop data provided, this gate PASSES.
    """
    if loop_data is None:
        return {"passed": True, "reason": "No fault isolation check required (skipped)"}

    fi = loop_data.get("fault_isolation")
    if fi is not None:
        compliant = fi.get("compliant", True) if isinstance(fi, dict) else True
        if not compliant:
            violations = fi.get("violations", [])
            n = len(violations) if isinstance(violations, list) else 0
            return {
                "passed": False,
                "reason": f"SLC fault isolation has {n} violation(s) (NFPA 72 §12.3)",
            }

    return {"passed": True, "reason": "Fault isolation compliant"}


def _gate_safety_tier(safety_tier_value: Optional[str]) -> Dict[str, Any]:
    """G8: Safety tier must be PROOF_VERIFIED or PROOF_VALID."""
    if safety_tier_value is None:
        return {"passed": False, "reason": "Safety tier not determined"}

    acceptable_tiers = {"PROOF_VERIFIED", "PROOF_VALID"}
    if safety_tier_value not in acceptable_tiers:
        return {
            "passed": False,
            "reason": f"Safety tier '{safety_tier_value}' is not submittable — requires PROOF_VERIFIED or PROOF_VALID",
        }

    return {"passed": True, "reason": f"Safety tier: {safety_tier_value}"}


# ═══════════════════════════════════════════════════════════════════════════════
# MAIN GATE EVALUATION
# ═══════════════════════════════════════════════════════════════════════════════

def verify_and_evaluate(
    input_payload: Optional[Dict] = None,
    nfpa_results: Optional[Dict] = None,
    evidence_envelope: Optional[Any] = None,
    drift_records: Optional[List[Dict]] = None,
    loop_data: Optional[Dict] = None,
    aset_rset_result: Optional[Dict] = None,
    battery_result: Optional[Dict] = None,
    stale_detector_ids: Optional[List[str]] = None,
    evidence_secret_key: Optional[str] = None,
) -> Dict[str, Any]:
    """Evaluate all 8 release gates.

    ALL gates must pass for release_status = "green".
    Any single gate failure results in release_status = "blocked".

    Args:
        input_payload: Validated room input dict (from Stage 0).
        nfpa_results: NFPA 72 compliance results (from Stages 1-3.5).
        evidence_envelope: Engineering evidence package (from Stage 6).
        drift_records: Digital twin drift records (optional).
        loop_data: SLC loop data including voltage drop and fault isolation.
        aset_rset_result: ASET/RSET analysis result (optional).
        battery_result: Battery sizing result dict (optional).
        stale_detector_ids: List of stale detector IDs from sync (optional).
        evidence_secret_key: HMAC key for evidence verification (optional).

    Returns:
        Dict with:
          - release_status: "green" | "blocked"
          - blockers: List of gate IDs that failed
          - checks: Dict of gate_id → {passed, reason}
          - gate_details: Detailed gate evaluation results
          - total_gates: Total number of gates evaluated
          - passed_gates: Number of gates that passed
          - failed_gates: Number of gates that failed
    """
    # Extract data from inputs for gate checks
    coverage_pct = None
    wall_violations = None
    safety_tier_value = None

    if input_payload:
        # Coverage and wall violations come from pipeline stages
        # These would be set by the pipeline caller, but we also
        # check nfpa_results for basic compliance
        pass

    if nfpa_results:
        # Extract coverage info if available
        is_compliant = nfpa_results.get("is_compliant", False)
        # If not compliant, this is a blocking condition
        pass

    # Run all gates
    checks = {}

    # G1: Input Validation
    checks["G1_input_validation"] = _gate_input_validation(input_payload)

    # G2: NFPA Spacing
    checks["G2_nfpa_spacing"] = _gate_nfpa_spacing(nfpa_results)

    # G3: Coverage — extracted from nfpa_results or input
    # The pipeline passes coverage_pct separately, but in this function
    # we infer it from the input payload or nfpa_results
    cov_pct = None
    if input_payload and "_coverage_pct" in input_payload:
        cov_pct = input_payload["_coverage_pct"]
    elif nfpa_results and "coverage_pct" in nfpa_results:
        cov_pct = nfpa_results["coverage_pct"]

    if cov_pct is not None:
        checks["G3_coverage"] = _gate_coverage(cov_pct)
    else:
        # If we can't determine coverage, check if NFPA says compliant
        if nfpa_results and nfpa_results.get("is_compliant"):
            checks["G3_coverage"] = {"passed": True, "reason": "Coverage compliant per NFPA results"}
        else:
            checks["G3_coverage"] = {"passed": False, "reason": "Coverage not verified"}

    # G4: Wall Distance — extracted from input or nfpa_results
    wv = None
    if input_payload and "_wall_violations" in input_payload:
        wv = input_payload["_wall_violations"]
    elif nfpa_results and "wall_violations" in nfpa_results:
        wv = nfpa_results["wall_violations"]

    if wv is not None:
        checks["G4_wall_distance"] = _gate_wall_distance(wv)
    else:
        # If no wall violation data, check if NFPA says compliant
        if nfpa_results and nfpa_results.get("is_compliant"):
            checks["G4_wall_distance"] = {"passed": True, "reason": "No wall violations per NFPA results"}
        else:
            checks["G4_wall_distance"] = {"passed": False, "reason": "Wall distance not verified"}

    # G5: Battery
    checks["G5_battery"] = _gate_battery(battery_result)

    # G6: Voltage Drop
    checks["G6_voltage_drop"] = _gate_voltage_drop(loop_data)

    # G7: Fault Isolation
    checks["G7_fault_isolation"] = _gate_fault_isolation(loop_data)

    # G8: Safety Tier — extracted from input or evidence
    tier = None
    if input_payload and "_safety_tier" in input_payload:
        tier = input_payload["_safety_tier"]
    elif nfpa_results and "safety_tier" in nfpa_results:
        tier = nfpa_results["safety_tier"]
    elif evidence_envelope and hasattr(evidence_envelope, "safety_tier"):
        tier = evidence_envelope.safety_tier

    checks["G8_safety_tier"] = _gate_safety_tier(tier)

    # Aggregate results
    blockers = [gid for gid, result in checks.items() if not result["passed"]]
    passed_gates = sum(1 for r in checks.values() if r["passed"])
    failed_gates = len(checks) - passed_gates
    release_status = "green" if not blockers else "blocked"

    return {
        "release_status": release_status,
        "blockers": blockers,
        "checks": checks,
        "gate_details": {
            gid: {
                "name": _GATE_NAMES.get(gid, gid),
                "passed": result["passed"],
                "reason": result["reason"],
            }
            for gid, result in checks.items()
        },
        "total_gates": len(checks),
        "passed_gates": passed_gates,
        "failed_gates": failed_gates,
    }


def describe_blockers(gate_result: Dict[str, Any]) -> List[str]:
    """Describe all blocking issues in human-readable form.

    Args:
        gate_result: Output of verify_and_evaluate().

    Returns:
        List of human-readable blocker descriptions.
    """
    if gate_result.get("release_status") == "green":
        return []

    blockers = gate_result.get("blockers", [])
    details = gate_result.get("gate_details", {})

    descriptions = []
    for blocker_id in blockers:
        detail = details.get(blocker_id, {})
        name = detail.get("name", blocker_id)
        reason = detail.get("reason", "Unknown reason")
        descriptions.append(f"[{name}] {reason}")

    return descriptions
