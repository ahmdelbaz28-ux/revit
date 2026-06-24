"""fireai/core/slc_capacitance.py
================================
SLC (Signaling Line Circuit) Data Attenuation & Capacitance Auditor.

V20 CRITICAL LIFE-SAFETY MODULE.

While V19.1 correctly validates DC voltage drop (power delivery), SLC
circuits also carry DIGITAL DATA between the FACP and addressable
devices.  This data signalling is a square-wave pulse train whose
integrity depends on the cable's distributed capacitance.  When the
total loop capacitance exceeds the protocol's limit (typically 0.5 µF
for most manufacturers), the square wave rounds off, rise/fall times
degrade, and the FACP can no longer distinguish logical 0 from 1.
The result: "SLC COMMUNICATION LOSS" — every device on the loop goes
dark precisely when it is needed most.

Physics:
  Cable capacitance is proportional to length:
    C_total = C_per_metre × L_total

  Typical values per NFPA 72 / UL 864 / EIA/TIA:
    - FPLR Solid (unshielded):    60 pF/m  (18 pF/ft)
    - FPLP Shielded:            164 pF/m  (50 pF/ft)
    - Standard Unshielded:       82 pF/m  (25 pF/ft)
    - Fiber Optic:                0 pF/m  (immune)

  Manufacturer SLC protocol limits (total loop capacitance):
    - Notifier FlashScan:    0.5 µF (500 nF)
    - Simplex IDNet:         0.75 µF (750 nF)
    - Siemens FDNet:         0.5 µF (500 nF)

  When C_total > C_max, the bit-error rate (BER) rises sharply and
  the protocol handshake fails.

Code references:
  - UL 864 10th Edition   — Control unit communication integrity
  - NFPA 72-2022 §12.2    — Pathway design
  - NFPA 72-2022 §23.8    — Network communication
  - EIA/TIA-568           — Telecommunications cabling standards

Provenance:
  Returns ``DecisionProvenance`` via the ``.new()`` factory when
  ``src.v8_core`` is available; degrades gracefully to plain dict.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

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
# Constants
# ============================================================================

# Cable capacitance per metre (pF/m) per EIA/TIA-568 / NFPA 72
CABLE_CAPACITANCE_PF_PER_M: Dict[str, float] = {
    "FPLR_Solid": 60.0,
    "FPLR_Unshielded": 60.0,  # V20.2 FIX: Same as FPLR_Solid (same physical cable)
    "FPLP_Shielded": 164.0,
    "FPLP_Unshielded": 100.0,
    "Standard_Unshielded": 82.0,
    "THHN_Paired": 70.0,
    "Fiber_Optic": 0.0,  # Immune to capacitance
}

# V20.2 FIX: Conservative per-device parasitic capacitance (pF)
# Each addressable device on an SLC loop adds parasitic capacitance
# — typically 15-30 pF per detector/module, up to 40-50 pF per isolator.
# Source: Notifier NFS2-3030 p.17, System Sensor, Edwards datasheets.
DEVICE_CAPACITANCE_PF: float = 25.0  # Conservative per-device parasitic (pF)
ISOLATOR_CAPACITANCE_PF: float = 40.0  # Isolator parasitic is higher (pF)

# Manufacturer SLC protocol maximum total loop capacitance (µF)
SLC_MAX_CAPACITANCE_UF: Dict[str, float] = {
    "notifier": 0.50,  # Notifier FlashScan
    "simplex": 0.75,  # Simplex IDNet
    "siemens": 0.50,  # Siemens FDNet
    "generic": 0.50,  # Conservative default
}

# Default maximum capacitance
DEFAULT_MAX_CAP_UF: float = 0.5

# Citations
_CITE_UL864 = "UL 864 10th Ed."
_CITE_NFPA72_12_2 = "NFPA 72-2022 §12.2"
_CITE_NFPA72_23_8 = "NFPA 72-2022 §23.8"
_CITE_EIA_TIA = "EIA/TIA-568"


@dataclass(frozen=True)
class SLCLoopSpec:
    """Specification for a single SLC loop.

    Attributes:
        loop_id: Unique loop identifier (e.g. "SLC-01").
        total_length_m: Total loop wire length in metres (out + return).
        wire_type: Cable type key for capacitance lookup.
        manufacturer: FACP manufacturer key for capacitance limit.
        device_count: Number of addressable devices on the loop.

    """

    loop_id: str
    total_length_m: float
    wire_type: str = "FPLP_Shielded"
    manufacturer: str = "generic"
    device_count: int = 0


@dataclass(frozen=True)
class SLCCapacitanceResult:
    """Result for a single SLC loop's capacitance audit."""

    loop_id: str
    total_length_m: float
    wire_type: str
    capacitance_pf: float
    capacitance_uf: float
    max_cap_uf: float
    compliant: bool
    margin_uf: float
    violation_description: Optional[str] = None


class SLCCapacitanceAuditor:
    """Audits SLC loops for data signalling integrity based on
    total cable capacitance.

    Unlike DC voltage drop (which only affects power delivery), cable
    capacitance affects the digital signalling waveform.  When total
    capacitance exceeds the manufacturer's limit, the FACP cannot
    reliably communicate with addressable devices.

    Usage::

        auditor = SLCCapacitanceAuditor(manufacturer="notifier")
        result = auditor.audit_slc_loops([
            SLCLoopSpec("SLC-01", 2500.0, "FPLP_Shielded", "notifier", 150),
        ])
    """

    def __init__(
        self,
        manufacturer: str = "generic",
        max_cap_uf: Optional[float] = None,
    ) -> None:
        """Initialise the auditor.

        Args:
            manufacturer: FACP manufacturer for protocol capacitance
                limit lookup.
            max_cap_uf: Override maximum capacitance in µF.  If None,
                uses manufacturer default.

        """
        self.manufacturer = manufacturer.strip().lower()
        if max_cap_uf is not None:
            self.max_cap_uf = max_cap_uf
        else:
            self.max_cap_uf = SLC_MAX_CAPACITANCE_UF.get(
                self.manufacturer,
                DEFAULT_MAX_CAP_UF,
            )

    def audit_slc_loops(
        self,
        loops: List[Dict[str, Any]],
    ) -> Any:
        """Audit multiple SLC loops for capacitance compliance.

        Each element of *loops* must be a dict with:
        - ``loop_id`` (str): Loop identifier.
        - ``total_length_m`` (float): Total wire length in metres.
        - ``wire_type`` (str, optional): Cable type. Defaults to
          ``"FPLP_Shielded"``.
        - ``manufacturer`` (str, optional): Override per-loop.
        - ``device_count`` (int, optional): Devices on loop.

        Returns:
            ``DecisionProvenance`` or plain dict.

        """
        violations: list = []
        detailed_results: List[SLCCapacitanceResult] = []

        for loop in loops:
            loop_id = loop.get("loop_id", "UNKNOWN")
            total_length_m = float(loop.get("total_length_m", 0.0))
            wire_type = loop.get("wire_type", "FPLP_Shielded")
            loop_mfr = loop.get("manufacturer", self.manufacturer).strip().lower()
            device_count = int(loop.get("device_count", 0))
            isolator_count = int(loop.get("isolator_count", 0))

            # V20.2 FIX: Validate loop length is positive
            if total_length_m <= 0:
                violations.append(
                    {
                        "severity": "CRITICAL",
                        "citation": f"{_CITE_NFPA72_12_2}",
                        "description": (
                            f"SLC loop '{loop_id}' has invalid length {total_length_m}m. Length must be positive."
                        ),
                    }
                )
                detailed_results.append(
                    SLCCapacitanceResult(
                        loop_id=loop_id,
                        total_length_m=total_length_m,
                        wire_type=wire_type,
                        capacitance_pf=0.0,
                        capacitance_uf=0.0,
                        max_cap_uf=0.0,
                        compliant=False,
                        margin_uf=0.0,
                        violation_description="Invalid loop length",
                    )
                )
                continue

            # Get per-loop capacitance limit
            # V20.2 FIX: Unknown manufacturer → conservative warning
            cap_limit_uf = SLC_MAX_CAPACITANCE_UF.get(loop_mfr, self.max_cap_uf)
            if loop_mfr not in SLC_MAX_CAPACITANCE_UF:
                # V65 FIX: Unknown manufacturer should add a violation, not just warn.
                # Old code only logged a warning but marked the loop as "safe" if
                # capacitance was below the default limit. But the actual panel limit
                # may be tighter (e.g., 0.3µF vs default 0.5µF), so a loop at 0.45µF
                # would be falsely marked compliant.
                logger.warning(
                    f"Unknown manufacturer '{loop_mfr}' for SLC loop '{loop_id}'; "
                    f"using default {self.max_cap_uf} µF which may EXCEED the "
                    f"actual panel limit. Verify with manufacturer installation manual."
                )
                if Violation is not None:
                    violations.append(
                        Violation(
                            severity="WARNING",
                            citation=_CITE_NFPA72_12_2,
                            description=(
                                f"Cannot verify SLC compliance for unknown manufacturer "
                                f"'{loop_mfr}' on loop '{loop_id}'. Default capacitance "
                                f"limit ({self.max_cap_uf} µF) may exceed actual panel "
                                f"specification. Verify with manufacturer datasheet."
                            ),
                        )
                    )
                else:
                    violations.append({
                        "severity": "WARNING",
                        "citation": _CITE_NFPA72_12_2,
                        "description": (
                            f"Cannot verify SLC compliance for unknown manufacturer "
                            f"'{loop_mfr}' on loop '{loop_id}'."
                        ),
                    })

            # V20.2 FIX: Unknown wire type → use most conservative (highest) value
            cap_pf_per_m = CABLE_CAPACITANCE_PF_PER_M.get(wire_type)
            if cap_pf_per_m is None:
                cap_pf_per_m = max(CABLE_CAPACITANCE_PF_PER_M.values())  # 164.0
                logger.warning(
                    f"Unknown wire_type '{wire_type}' for SLC loop '{loop_id}'; "
                    f"using conservative default {cap_pf_per_m} pF/m. "
                    f"Specify a known cable type for accurate results."
                )

            # V20.2 FIX: Calculate total loop capacitance INCLUDING device parasitics
            # Total = (cable capacitance) + (device parasitic) + (isolator parasitic)
            # Per UL 864 10th Ed., total loop capacitance includes ALL connected devices.
            cable_cap_pf = total_length_m * cap_pf_per_m
            device_cap_pf = (device_count * DEVICE_CAPACITANCE_PF) + (isolator_count * ISOLATOR_CAPACITANCE_PF)
            total_cap_pf = cable_cap_pf + device_cap_pf
            total_cap_uf = total_cap_pf / 1_000_000.0

            compliant = total_cap_uf <= cap_limit_uf
            margin_uf = round(cap_limit_uf - total_cap_uf, 6)

            violation_desc = None
            if not compliant:
                violation_desc = (
                    f"SLC loop '{loop_id}' total capacitance "
                    f"{total_cap_uf:.4f} µF ({total_cap_pf:.0f} pF) "
                    f"exceeds {loop_mfr.title()} signalling threshold of "
                    f"{cap_limit_uf:.2f} µF. Data packets will collide "
                    f"and distort — SLC COMMUNICATION LOSS imminent. "
                    f"Reduce loop length or switch to fiber optic trunk."
                )
                if Violation is not None:
                    violations.append(
                        Violation(
                            severity="CRITICAL",
                            citation=f"{_CITE_UL864} / {_CITE_NFPA72_12_2}",
                            description=violation_desc,
                        )
                    )
                else:
                    violations.append(
                        {
                            "severity": "CRITICAL",
                            "citation": f"{_CITE_UL864} / {_CITE_NFPA72_12_2}",
                            "description": violation_desc,
                        }
                    )
                logger.critical(violation_desc)

            # Recommend fiber optic trunk if margin is thin
            if compliant and total_cap_uf > cap_limit_uf * 0.8:
                warn = (
                    f"SLC loop '{loop_id}' capacitance at "
                    f"{total_cap_uf:.4f} µF is within {20:.0f}% of "
                    f"limit ({cap_limit_uf:.2f} µF). Consider fiber "
                    f"optic trunk for future-proofing."
                )
                logger.warning(warn)

            detailed_results.append(
                SLCCapacitanceResult(
                    loop_id=loop_id,
                    total_length_m=total_length_m,
                    wire_type=wire_type,
                    capacitance_pf=round(total_cap_pf, 1),
                    capacitance_uf=round(total_cap_uf, 6),
                    max_cap_uf=cap_limit_uf,
                    compliant=compliant,
                    margin_uf=margin_uf,
                    violation_description=violation_desc,
                )
            )

        safe = len(violations) == 0

        # Build provenance result
        if DecisionProvenance is not None:
            try:
                rules = [
                    RuleApplied(
                        citation=_CITE_UL864,
                        constant_id="SLC_MAX_CAPACITANCE",
                        value_used=self.max_cap_uf,
                        unit="microfarads",
                    ),
                    RuleApplied(
                        citation=_CITE_EIA_TIA,
                        constant_id="CABLE_CAP_PF_PER_M",
                        value_used=CABLE_CAPACITANCE_PF_PER_M.get("FPLP_Shielded", 164.0),
                        unit="pF/m",
                    ),
                ]
                conf = ConfidenceScore(
                    input_quality_score=1.0,
                    rule_coverage=1.0,
                    geometry_certainty=1.0,
                    overall=ConfidenceLevel.HIGH if safe else ConfidenceLevel.LOW,
                )
                return DecisionProvenance.new(
                    decision_type="slc_capacitance_audit",
                    value={
                        "loops_audited": len(loops),
                        "loops_compliant": sum(1 for r in detailed_results if r.compliant),
                        "loops_failing": sum(1 for r in detailed_results if not r.compliant),
                        "safe": safe,
                        "detailed_results": [
                            {
                                "loop_id": r.loop_id,
                                "total_length_m": r.total_length_m,
                                "wire_type": r.wire_type,
                                "capacitance_pf": r.capacitance_pf,
                                "capacitance_uf": r.capacitance_uf,
                                "max_cap_uf": r.max_cap_uf,
                                "compliant": r.compliant,
                                "margin_uf": r.margin_uf,
                                "violation_description": r.violation_description,
                            }
                            for r in detailed_results
                        ],
                    },
                    inputs={
                        "manufacturer": self.manufacturer,
                        "max_cap_uf": self.max_cap_uf,
                    },
                    rules_applied=rules,
                    algorithm={"name": "CapacitanceWaveformGuard", "version": "v20"},
                    confidence=conf,
                    selected_because=(
                        "SLC data signalling integrity requires total cable "
                        "capacitance within protocol limits. Exceeding this "
                        "threshold causes digital waveform distortion and "
                        "communication loss per UL 864 / NFPA 72 §12.2."
                    ),
                    violations=violations if violations else None,
                )
            except Exception as e:
                logger.warning("V112: audit_slc_loops: failed to construct DecisionProvenance audit result: %s", e)
                pass

        return {
            "decision_type": "slc_capacitance_audit",
            "value": {
                "safe": safe,
                "detailed_results": [{"loop_id": r.loop_id, "compliant": r.compliant} for r in detailed_results],
            },
            "safe": safe,
            "violations": violations,
        }


__all__ = [
    "CABLE_CAPACITANCE_PF_PER_M",
    "DEFAULT_MAX_CAP_UF",
    "SLC_MAX_CAPACITANCE_UF",
    "SLCCapacitanceAuditor",
    "SLCCapacitanceResult",
    "SLCLoopSpec",
]
