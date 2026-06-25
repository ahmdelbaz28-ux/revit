"""fireai/core/facp_capacity_auditor.py
====================================
FACP (Fire Alarm Control Panel) Global Capacity Auditor.

CRITICAL life-safety module that verifies the panel's power supply and
signalling line circuit (SLC) protocol limits are not exceeded.  Overloading
a FACP PSU can cause catastrophic failure during an alarm event — the
notification appliance circuits (NAC) go dark precisely when they are
needed most.

Code references:
  - NEC 2023 §760.121  — Power-limited fire alarm circuit ampacity
  - UL 864 10th Edition — Control units and accessories
  - NFPA 72 (2022) §10.6.7 — Secondary power (battery) capacity
  - NFPA 72 (2022) §10.14  — Voltage drop under alarm conditions

This module performs two independent audits:
  1. **Global inrush audit** — per-NAC and aggregate PSU current checks
  2. **SLC protocol audit** — per-loop device count against manufacturer limits

Provenance:
  Uses DecisionProvenance when ``src.v8_core`` is available; degrades
  gracefully to plain dicts when it is not.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Dict, List

# ---------------------------------------------------------------------------
# Provenance — graceful degradation
# ---------------------------------------------------------------------------
try:
    from fireai.core.provenance import (
        ConfidenceLevel,
        ConfidenceScore,
        DecisionProvenance,
        RuleApplied,
        Violation,
    )
except ImportError:
    DecisionProvenance = None  # type: ignore[misc,assignment]
    RuleApplied = None  # type: ignore[misc,assignment]
    Violation = None  # type: ignore[misc,assignment]
    ConfidenceScore = None  # type: ignore[misc,assignment]
    ConfidenceLevel = None  # type: ignore[misc,assignment]

logger = logging.getLogger(__name__)

# ============================================================================
# Constants — code citations
# ============================================================================
_CITE_NEC_760_121 = "NEC 2023 §760.121"
_CITE_UL864_NFPA72_10_6_7 = "UL 864 / NFPA 72 §10.6.7"

# ============================================================================
# Detector / module classification sets
# ============================================================================
DETECTOR_DEVICE_TYPES: frozenset[str] = frozenset(
    {
        "SMOKE_PHOTOELECTRIC",
        "SMOKE_IONIZATION",
        "SMOKE_MULTI_CRITERIA",
        "HEAT_FIXED",
        "HEAT_RATE_OF_RISE",
    }
)

# Exact-match module types
_EXACT_MODULE_TYPES: frozenset[str] = frozenset(
    {
        "MANUAL_PULL_STATION",
        "DUCT_SMOKE",
    }
)

# Substring-match keywords for additional module identification
_MODULE_KEYWORDS: frozenset[str] = frozenset(
    {
        "MODULE",
        "MONITOR",
        "RELAY",
        "OUTPUT",
    }
)


# ============================================================================
# Data model
# ============================================================================
@dataclass(frozen=True)
class FACP_Profile:
    """Manufacturer-specific FACP protocol limits.

    Attributes:
        manufacturer:  Human-readable manufacturer name (e.g. "Notifier FlashScan").
        max_detectors_per_slc: Maximum detector addresses per SLC loop.
        max_modules_per_slc:   Maximum module addresses per SLC loop.
        max_total_devices_per_slc: Maximum total devices (det+mod) per SLC loop.
            Some manufacturers (Notifier FlashScan) cap the combined total
            separately from the individual detector/module limits.
            Others (Simplex IDNet) use a shared address pool where
            max_total = max_detectors = max_modules.
        max_total_nac_amps:    Aggregate NAC current the PSU can sustain (A).
        max_amps_per_nac:      Per-circuit NAC current limit (A).
        slc_max_current_ma:    Maximum quiescent current per SLC loop (mA).
            Exceeding this can burn the SLC card's output circuit.

    """

    manufacturer: str
    max_detectors_per_slc: int
    max_modules_per_slc: int
    max_total_devices_per_slc: int
    max_total_nac_amps: float
    max_amps_per_nac: float
    slc_max_current_ma: float


# ============================================================================
# Pre-defined manufacturer profiles
# ============================================================================
_MANUFACTURER_PROFILES: Dict[str, FACP_Profile] = {
    "notifier": FACP_Profile(
        manufacturer="Notifier FlashScan",
        max_detectors_per_slc=159,
        max_modules_per_slc=159,
        max_total_devices_per_slc=318,
        max_total_nac_amps=10.0,
        max_amps_per_nac=3.0,
        slc_max_current_ma=500.0,
    ),
    "simplex": FACP_Profile(
        manufacturer="Simplex IDNet",
        max_detectors_per_slc=250,
        max_modules_per_slc=250,
        max_total_devices_per_slc=250,
        max_total_nac_amps=10.0,
        max_amps_per_nac=3.0,
        slc_max_current_ma=500.0,
    ),
    "siemens": FACP_Profile(
        manufacturer="Siemens FDNet",
        max_detectors_per_slc=252,
        max_modules_per_slc=252,
        max_total_devices_per_slc=252,
        max_total_nac_amps=8.0,
        max_amps_per_nac=2.5,
        slc_max_current_ma=450.0,
    ),
}


def get_default_profile(manufacturer: str) -> FACP_Profile:
    """Return a pre-defined FACP profile for a known manufacturer.

    Args:
        manufacturer: Case-insensitive manufacturer key
                      ("notifier", "simplex", or "siemens").

    Returns:
        The matching ``FACP_Profile``.

    Raises:
        ValueError: If the manufacturer is not in the pre-defined set.

    """
    key = manufacturer.strip().lower()
    if key not in _MANUFACTURER_PROFILES:
        valid = ", ".join(sorted(_MANUFACTURER_PROFILES.keys()))
        raise ValueError(f"Unknown manufacturer '{manufacturer}'. Valid options: {valid}")
    return _MANUFACTURER_PROFILES[key]


# ============================================================================
# Helper — build a provenance-aware result dict
# ============================================================================
def _build_violation(
    code: str,
    message: str,
    severity: str = "CRITICAL",
) -> Dict[str, Any]:
    """Return a violation record as a plain dict.

    If the ``Violation`` provenance class is available the dict also
    includes a ``provenance`` key with a ``Violation`` instance; otherwise
    the dict is self-contained.

    Provenance ``Violation`` fields: ``severity``, ``citation``, ``description``.
    The *code* argument maps to ``citation``; *message* maps to ``description``.
    """
    entry: Dict[str, Any] = {
        "code": code,
        "message": message,
        "severity": severity,
    }
    if Violation is not None:
        try:
            entry["provenance"] = Violation(
                severity=severity,
                citation=code,
                description=message,
            )
        except Exception:
            # If the Violation constructor signature changes, degrade
            # gracefully rather than crash a life-safety audit.
            pass
    return entry


def _build_rule_applied(
    rule_id: str,
    description: str,
) -> Dict[str, Any]:
    """Return a rule-applied record as a plain dict.

    Provenance ``RuleApplied`` fields: ``citation``, ``constant_id``,
    ``value_used``, ``unit``.
    """
    entry: Dict[str, Any] = {
        "rule_id": rule_id,
        "description": description,
    }
    if RuleApplied is not None:
        try:
            entry["provenance"] = RuleApplied(
                citation=rule_id,
                constant_id=rule_id,
                value_used=0.0,
                unit="n/a",
            )
        except Exception as e:
            logger.warning(
                f"V112: _build_rule_applied: failed to construct RuleApplied provenance for rule_id={rule_id!r}: {e!r}"
            )
            pass
    return entry


# ============================================================================
# Device classification
# ============================================================================
def _classify_device(device_type: str) -> str:
    """Classify a device as ``"detector"`` or ``"module"``.

    Classification rules:
      1. If *device_type* is in ``DETECTOR_DEVICE_TYPES`` → detector.
      2. If *device_type* is in ``_EXACT_MODULE_TYPES`` → module.
      3. If any keyword in ``_MODULE_KEYWORDS`` is a substring of
         *device_type* (case-insensitive) → module.
      4. Otherwise → module (conservative default: unknown devices
         consume an address and are counted against the module limit).

    Returns:
        ``"detector"`` or ``"module"``.

    """
    if device_type in DETECTOR_DEVICE_TYPES:
        return "detector"
    if device_type in _EXACT_MODULE_TYPES:
        return "module"
    upper = device_type.upper()
    for kw in _MODULE_KEYWORDS:
        if kw in upper:
            return "module"
    # Conservative default: unknown types count as modules
    return "module"


# ============================================================================
# Main auditor class
# ============================================================================
class FACPCapacityAuditor:
    """Audits a FACP against its manufacturer profile for power-supply
    overloads and SLC protocol limit violations.

    Usage::

        profile = get_default_profile("notifier")
        auditor = FACPCapacityAuditor(profile)
        result = auditor.audit_global_inrush(nac_circuits)
        result = auditor.audit_slc_protocol_limits(slc_loops)
    """

    def __init__(self, profile: FACP_Profile) -> None:
        self.profile = profile

    # ------------------------------------------------------------------
    # Audit 1: Global inrush / NAC current
    # ------------------------------------------------------------------
    def audit_global_inrush(self, nac_circuits: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Audit all NAC circuits for per-circuit and aggregate current limits.

        Each element of *nac_circuits* must be a dict with at minimum:

        - ``id`` (str): Circuit identifier.
        - ``total_inrush_amps`` (float): Worst-case inrush current for the circuit.

        Checks performed:
          1. **Per-NAC** — each circuit's ``total_inrush_amps`` must not
             exceed ``profile.max_amps_per_nac``.  Violation cited to
             ``NEC 2023 §760.121``.
          2. **Aggregate** — the sum of all circuit inrush currents must
             not exceed ``profile.max_total_nac_amps``.  Violation cited
             to ``UL 864 / NFPA 72 §10.6.7`` (PSU burnout risk).

        Returns:
            Dict with keys:

            - ``total_inrush_a`` (float): Sum of all circuit inrush currents.
            - ``status`` (str): ``"SAFE"`` or ``"CATASTROPHIC_OVERLOAD"``.
            - ``violations`` (list[dict]): Each violation with ``code``,
              ``message``, and ``severity`` keys.
            - ``rules_applied`` (list[dict]): Rules evaluated during the audit.
            - ``provenance``: A ``DecisionProvenance`` object if available,
              otherwise ``None``.

        """
        violations: List[Dict[str, Any]] = []
        rules_applied: List[Dict[str, Any]] = []
        total_inrush: float = 0.0

        # --- Per-NAC check ---
        per_nac_rule = _build_rule_applied(
            rule_id="FACP-NAC-PER-CIRCUIT",
            description=(
                f"Each NAC circuit inrush must not exceed {self.profile.max_amps_per_nac:.1f} A ({_CITE_NEC_760_121})"
            ),
        )
        rules_applied.append(per_nac_rule)

        for circuit in nac_circuits:
            cid = circuit.get("id", "UNKNOWN")
            inrush = float(circuit.get("total_inrush_amps", 0.0))
            total_inrush += inrush

            if inrush > self.profile.max_amps_per_nac:
                msg = (
                    f"NAC circuit '{cid}' draws {inrush:.2f} A inrush, "
                    f"exceeding per-circuit limit of "
                    f"{self.profile.max_amps_per_nac:.1f} A "
                    f"({_CITE_NEC_760_121})"
                )
                violations.append(
                    _build_violation(
                        code="FACP-NAC-PER-CIRCUIT",
                        message=msg,
                        severity="CRITICAL",
                    )
                )
                logger.critical(msg)

        # --- Aggregate PSU check ---
        aggregate_rule = _build_rule_applied(
            rule_id="FACP-NAC-AGGREGATE",
            description=(
                f"Sum of all NAC inrush currents must not exceed "
                f"{self.profile.max_total_nac_amps:.1f} A "
                f"({_CITE_UL864_NFPA72_10_6_7})"
            ),
        )
        rules_applied.append(aggregate_rule)

        if total_inrush > self.profile.max_total_nac_amps:
            msg = (
                f"Total NAC inrush {total_inrush:.2f} A exceeds PSU "
                f"capacity of {self.profile.max_total_nac_amps:.1f} A "
                f"— risk of PSU burnout "
                f"({_CITE_UL864_NFPA72_10_6_7})"
            )
            violations.append(
                _build_violation(
                    code="FACP-NAC-AGGREGATE",
                    message=msg,
                    severity="CRITICAL",
                )
            )
            logger.critical(msg)

        status = "CATASTROPHIC_OVERLOAD" if violations else "SAFE"

        result: Dict[str, Any] = {
            "total_inrush_a": round(total_inrush, 4),
            "status": status,
            "violations": violations,
            "rules_applied": rules_applied,
            "provenance": None,
        }

        if DecisionProvenance is not None:
            try:
                result["provenance"] = DecisionProvenance(
                    decision_id="facp_global_inrush_audit",
                    decision_type="capacity_audit",
                    value=status,
                    inputs={"nac_circuits": len(nac_circuits)},
                    rules_applied=rules_applied,  # type: ignore[arg-type]
                    algorithm={"name": "facp_global_inrush"},
                    feasible_alternatives_considered=0,
                    selected_because="PSU capacity constraint",
                    alternatives_top_3=[],
                    warnings=[],
                    violations_detected=violations,
                    confidence=ConfidenceScore(
                        input_quality_score=1.0,
                        rule_coverage=1.0,
                        geometry_certainty=1.0,
                        overall=ConfidenceLevel.HIGH,
                    ),
                )
            except Exception:
                # Degrade gracefully — provenance is supplementary
                pass

        return result

    # ------------------------------------------------------------------
    # Audit 2: SLC protocol limits
    # ------------------------------------------------------------------
    def audit_slc_protocol_limits(
        self,
        slc_loops: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Audit each SLC loop for detector and module address limits.

        Each element of *slc_loops* must be a dict with:

        - ``loop_id`` (str): Loop identifier.
        - ``devices`` (list[dict]): List of device dicts, each with a
          ``device_type`` key.

        Device classification uses the ``device_type`` field directly:

        **Detectors**: ``SMOKE_PHOTOELECTRIC``, ``SMOKE_IONIZATION``,
        ``SMOKE_MULTI_CRITERIA``, ``HEAT_FIXED``, ``HEAT_RATE_OF_RISE``.

        **Modules**: ``MANUAL_PULL_STATION``, ``DUCT_SMOKE``, plus any
        type whose name contains ``MODULE``, ``MONITOR``, ``RELAY``, or
        ``OUTPUT`` (case-insensitive).

        Unknown types are conservatively counted as modules.

        Returns:
            Dict with keys:

            - ``loops_passing`` (list[dict]): Loops within limits.
            - ``loops_failing`` (list[dict]): Loops exceeding limits.
            - ``all_pass`` (bool): True only if every loop passes.
            - ``violations`` (list[dict]): Violation records.
            - ``provenance``: ``DecisionProvenance`` if available, else ``None``.

        """
        loops_passing: List[Dict[str, Any]] = []
        loops_failing: List[Dict[str, Any]] = []
        violations: List[Dict[str, Any]] = []

        for loop in slc_loops:
            loop_id = loop.get("loop_id", "UNKNOWN")
            devices: List[Dict[str, Any]] = loop.get("devices", [])

            detector_count = 0
            module_count = 0

            for dev in devices:
                device_type = dev.get("device_type", "")
                classification = _classify_device(device_type)
                if classification == "detector":
                    detector_count += 1
                else:
                    module_count += 1

            total_devices = detector_count + module_count

            # Quiescent current estimation (each device draws some standby current)
            quiescent_current_ma = 0.0
            for dev in devices:
                quiescent_current_ma += float(dev.get("quiescent_ma", 0.8))

            loop_summary: Dict[str, Any] = {
                "loop_id": loop_id,
                "detector_count": detector_count,
                "module_count": module_count,
                "total_devices": total_devices,
                "quiescent_current_ma": round(quiescent_current_ma, 2),
                "max_detectors_per_slc": self.profile.max_detectors_per_slc,
                "max_modules_per_slc": self.profile.max_modules_per_slc,
                "max_total_devices_per_slc": self.profile.max_total_devices_per_slc,
            }

            loop_failed = False

            # Detector limit check
            if detector_count > self.profile.max_detectors_per_slc:
                msg = (
                    f"SLC loop '{loop_id}': {detector_count} detectors "
                    f"exceeds limit of {self.profile.max_detectors_per_slc} "
                    f"for {self.profile.manufacturer}"
                )
                violations.append(
                    _build_violation(
                        code="FACP-SLC-DETECTORS",
                        message=msg,
                        severity="CRITICAL",
                    )
                )
                logger.critical(msg)
                loop_failed = True

            # Module limit check
            if module_count > self.profile.max_modules_per_slc:
                msg = (
                    f"SLC loop '{loop_id}': {module_count} modules "
                    f"exceeds limit of {self.profile.max_modules_per_slc} "
                    f"for {self.profile.manufacturer}"
                )
                violations.append(
                    _build_violation(
                        code="FACP-SLC-MODULES",
                        message=msg,
                        severity="CRITICAL",
                    )
                )
                logger.critical(msg)
                loop_failed = True

            # Total device limit check (V16: some manufacturers cap combined total)
            if total_devices > self.profile.max_total_devices_per_slc:
                msg = (
                    f"SLC loop '{loop_id}': {total_devices} total devices "
                    f"exceeds combined limit of "
                    f"{self.profile.max_total_devices_per_slc} "
                    f"for {self.profile.manufacturer}"
                )
                violations.append(
                    _build_violation(
                        code="FACP-SLC-TOTAL-DEVICES",
                        message=msg,
                        severity="CRITICAL",
                    )
                )
                logger.critical(msg)
                loop_failed = True

            # SLC quiescent current check (V16: loop card burnout prevention)
            if quiescent_current_ma > self.profile.slc_max_current_ma:
                msg = (
                    f"SLC loop '{loop_id}': quiescent current "
                    f"{quiescent_current_ma:.1f} mA exceeds SLC card "
                    f"limit of {self.profile.slc_max_current_ma:.0f} mA "
                    f"for {self.profile.manufacturer} — risk of loop card "
                    f"circuit burnout"
                )
                violations.append(
                    _build_violation(
                        code="FACP-SLC-CURRENT",
                        message=msg,
                        severity="CRITICAL",
                    )
                )
                logger.critical(msg)
                loop_failed = True

            if loop_failed:
                loops_failing.append(loop_summary)
            else:
                loops_passing.append(loop_summary)

        all_pass = len(loops_failing) == 0

        result: Dict[str, Any] = {
            "loops_passing": loops_passing,
            "loops_failing": loops_failing,
            "all_pass": all_pass,
            "violations": violations,
            "provenance": None,
        }

        if DecisionProvenance is not None:
            try:
                result["provenance"] = DecisionProvenance(
                    decision_id="facp_slc_protocol_audit",
                    decision_type="capacity_audit",
                    value="PASS" if all_pass else "FAIL",
                    inputs={"slc_loops": len(slc_loops)},
                    rules_applied=[],  # type: ignore[arg-type]
                    algorithm={"name": "facp_slc_protocol"},
                    feasible_alternatives_considered=0,
                    selected_because="SLC protocol constraint",
                    alternatives_top_3=[],
                    warnings=[],
                    violations_detected=violations,
                    confidence=ConfidenceScore(
                        input_quality_score=1.0,
                        rule_coverage=1.0,
                        geometry_certainty=1.0,
                        overall=ConfidenceLevel.HIGH,
                    ),
                )
            except Exception as e:
                logger.warning(
                    f"V112: audit_slc_protocol_limits: failed to construct DecisionProvenance audit result: {e!r}"
                )
                pass

        return result


# ============================================================================
# Module exports
# ============================================================================
__all__ = [
    "DETECTOR_DEVICE_TYPES",
    "FACPCapacityAuditor",
    "FACP_Profile",
    "get_default_profile",
]
