"""
release_gates.py — Release Blocking Policy as Executable Code
==============================================================
Adapted from Elite Platform V2 + STRICT_ENGINEERING mode.

Implements the principle that no design output should leave the system
unless ALL safety gates pass. This is the code-level enforcement of
STRICT_ENGINEERING mode — a design is either GREEN (all checks pass)
or BLOCKED (one or more gates fail).

Gates are evaluated in order. Any BLOCKED gate prevents release.
This prevents:
  - Releasing a design where NFPA compliance was not verified.
  - Releasing a design with unsealed evidence (tamper risk).
  - Releasing a design where input data was not validated.
  - Releasing a design where BIM drift was detected but not resolved.
  - Releasing a design with stale cached surfaces.

Usage:
    from fireai.core.release_gates import evaluate_release

    result = evaluate_release({
        "input_contract_valid": True,
        "nfpa_compliance_verified": True,
        "evidence_chain_sealed": True,
        "no_drift_detected": True,
        "stale_surfaces_removed": True,
    })
    if result["release_status"] == "blocked":
        print("BLOCKED:", result["blockers"])
"""

from __future__ import annotations

from typing import Any, Dict, List


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
}


def evaluate_release(context: Dict[str, Any]) -> Dict[str, Any]:
    """Evaluate all release gates and return pass/block status.

    Args:
        context: Dictionary with gate names as keys and bool values.
                 Each key must match a gate in RELEASE_GATES.

    Returns:
        Dictionary with:
          - checks: Dict of gate_name → bool (True = passed)
          - blockers: List of gate names that failed
          - release_status: "green" if all passed, "blocked" if any failed
          - gate_details: Dict with description and NFPA reference for each gate
    """
    checks = {}
    gate_details = {}

    for gate_name, gate_info in RELEASE_GATES.items():
        passed = bool(context.get(gate_name, False))
        checks[gate_name] = passed
        gate_details[gate_name] = {
            "passed": passed,
            "description": gate_info["description"],
            "nfpa_reference": gate_info["nfpa_reference"],
            "failure_impact": gate_info["failure_impact"],
        }

    blockers: List[str] = [name for name, ok in checks.items() if not ok]

    return {
        "checks": checks,
        "blockers": blockers,
        "release_status": "blocked" if blockers else "green",
        "gate_details": gate_details,
    }


def describe_blockers(result: Dict[str, Any]) -> str:
    """Produce a human-readable description of what's blocking release.

    Args:
        result: Output from evaluate_release().

    Returns:
        Multi-line string describing each blocker with NFPA reference.
    """
    if result["release_status"] == "green":
        return "All release gates passed — design is cleared for output."

    lines = ["RELEASE BLOCKED — the following gates failed:"]
    for blocker in result["blockers"]:
        details = result["gate_details"][blocker]
        lines.append(f"  ✗ {blocker}")
        lines.append(f"    Description: {details['description']}")
        lines.append(f"    NFPA Reference: {details['nfpa_reference']}")
        lines.append(f"    Impact: {details['failure_impact']}")
    return "\n".join(lines)


__all__ = ["RELEASE_GATES", "evaluate_release", "describe_blockers"]
