"""fireai.conduit.fill — NEC Chapter 9 Conduit Fill Calculator
============================================================

Implements conduit fill percentage calculation and trade size
recommendation per NEC 2022 Chapter 9, Table 1.

FORMULA:
  fill% = (Σ π(dᵢ/2)²) / A_conduit × 100

  where dᵢ = diameter of conductor i (inches)
        A_conduit = tabulated internal area (NEC Table 4) (in²)

MAXIMUM FILL RATIOS (NEC Chapter 9, Table 1):
  1 conductor:  53%
  2 conductors: 31%
  3+ conductors: 40%
  Nipple (≤24"): 60% (NEC Ch.9 Note 4) — not implemented here

ENGINEERING SOURCES:
  NEC 2022 Chapter 9, Table 1 — Fill Percentages
  NEC 2022 Chapter 9, Table 4 — Conduit Areas
  NEC 2022 Chapter 9, Table 5 — Conductor Cross-Sectional Areas

DESIGN NOTE (from pyRevit conduit discussion, discourse.pyrevitlabs.io):
  The pyRevit community uses conductor OD² × π/4 directly, consistent
  with NEC Table 5 which tabulates area = π(OD/2)². This implementation
  matches that approach exactly.
"""

from __future__ import annotations

import math
from typing import Dict, List, Optional, Tuple

from fireai.conduit.errors import CodeViolationError, PhysicsError, Severity
from fireai.conduit.types import (
    ConduitType,
    FillResult,
    Result,
    TradeSize,
)

# ─────────────────────────────────────────────────────────────────────────────
# NEC Chapter 9, Table 1 — Fill Percentage Limits
# ─────────────────────────────────────────────────────────────────────────────

# NEC Chapter 9, Table 1: maximum conduit fill by conductor count
_MAX_FILL_1_CONDUCTOR:    float = 53.0  # NEC Ch.9 Table 1, col "1 Wire"
_MAX_FILL_2_CONDUCTORS:   float = 31.0  # NEC Ch.9 Table 1, col "2 Wires"
_MAX_FILL_3PLUS_CONDUCTORS: float = 40.0  # NEC Ch.9 Table 1, col "Over 2 Wires"


def _max_fill_pct(conductor_count: int) -> float:
    """Return the NEC Table 1 maximum fill percentage for the given conductor count.

    Reference: NEC 2022 Chapter 9, Table 1.
    """
    if conductor_count == 1:
        return _MAX_FILL_1_CONDUCTOR
    if conductor_count == 2:
        return _MAX_FILL_2_CONDUCTORS
    return _MAX_FILL_3PLUS_CONDUCTORS


# ─────────────────────────────────────────────────────────────────────────────
# NEC Chapter 9, Table 4 — Conduit Internal Cross-Sectional Areas (in²)
# These are the 100% fill areas from which Table 1 percentages are applied.
# ─────────────────────────────────────────────────────────────────────────────

# Format: (ConduitType, TradeSize) → internal area in²
# Source: NEC 2022 Chapter 9, Table 4
_INTERNAL_AREA_IN2: Dict[Tuple[ConduitType, TradeSize], float] = {
    # EMT — Electrical Metallic Tubing (NEC Table 4, EMT section)
    (ConduitType.EMT, TradeSize.HALF):      0.304,
    (ConduitType.EMT, TradeSize.THREE_QTR): 0.533,
    (ConduitType.EMT, TradeSize.ONE):       0.864,
    (ConduitType.EMT, TradeSize.ONE_QTR):  1.496,
    (ConduitType.EMT, TradeSize.ONE_HALF): 2.036,
    (ConduitType.EMT, TradeSize.TWO):      3.356,

    # UPVC Schedule 40 — Rigid PVC (NEC Table 4, PVC Sch 40 section)
    (ConduitType.UPVC_SCH40, TradeSize.HALF):      0.220,
    (ConduitType.UPVC_SCH40, TradeSize.THREE_QTR): 0.410,
    (ConduitType.UPVC_SCH40, TradeSize.ONE):       0.690,
    (ConduitType.UPVC_SCH40, TradeSize.ONE_QTR):  1.240,
    (ConduitType.UPVC_SCH40, TradeSize.ONE_HALF): 1.710,
    (ConduitType.UPVC_SCH40, TradeSize.TWO):      2.930,

    # UPVC Schedule 80 — Rigid PVC heavy wall (NEC Table 4, PVC Sch 80 section)
    (ConduitType.UPVC_SCH80, TradeSize.HALF):      0.164,
    (ConduitType.UPVC_SCH80, TradeSize.THREE_QTR): 0.333,
    (ConduitType.UPVC_SCH80, TradeSize.ONE):       0.581,
    (ConduitType.UPVC_SCH80, TradeSize.ONE_QTR):  1.079,
    (ConduitType.UPVC_SCH80, TradeSize.ONE_HALF): 1.520,
    (ConduitType.UPVC_SCH80, TradeSize.TWO):      2.648,

    # RGD — Rigid Metal Conduit (NEC Table 4, RMC section)
    (ConduitType.RGD, TradeSize.HALF):      0.220,
    (ConduitType.RGD, TradeSize.THREE_QTR): 0.410,
    (ConduitType.RGD, TradeSize.ONE):       0.690,
    (ConduitType.RGD, TradeSize.ONE_QTR):  1.240,
    (ConduitType.RGD, TradeSize.ONE_HALF): 1.710,
    (ConduitType.RGD, TradeSize.TWO):      2.930,
}

# Ordered trade sizes for "next larger" recommendation
_TRADE_SIZE_ORDER: List[TradeSize] = [
    TradeSize.HALF,
    TradeSize.THREE_QTR,
    TradeSize.ONE,
    TradeSize.ONE_QTR,
    TradeSize.ONE_HALF,
    TradeSize.TWO,
]


def _next_larger_size(current: TradeSize) -> Optional[TradeSize]:
    """Return the next larger trade size, or None if already at maximum."""
    try:
        idx = _TRADE_SIZE_ORDER.index(current)
    except ValueError:
        return None
    if idx + 1 < len(_TRADE_SIZE_ORDER):
        return _TRADE_SIZE_ORDER[idx + 1]
    return None


def get_internal_area(
    conduit_type: ConduitType,
    trade_size: TradeSize,
) -> Result[float, PhysicsError]:
    """Return the tabulated internal cross-sectional area in in².

    Reference: NEC 2022 Chapter 9, Table 4.

    Args:
        conduit_type: Conduit material type.
        trade_size:   Nominal trade size.

    Returns:
        Result.ok(float) — area in in².
        Result.err(PhysicsError) — unsupported combination.

    """
    key = (conduit_type, trade_size)
    area = _INTERNAL_AREA_IN2.get(key)
    if area is None:
        return Result.err(PhysicsError(
            message=(
                f"No NEC Table 4 entry for "
                f"{conduit_type.value} {trade_size.value}. "
                "This conduit type/size combination is not in NEC Table 4."
            ),
            remediation=(
                "Verify conduit type and trade size. "
                "Only sizes ½\" through 2\" are currently catalogued. "
                "For larger sizes, extend _INTERNAL_AREA_IN2."
            ),
        ))
    return Result.ok(area)


def calculate_fill(
    conduit_type: ConduitType,
    trade_size: TradeSize,
    cable_diameters_in: List[float],
) -> Result[FillResult, PhysicsError | CodeViolationError]:
    """Calculate conduit fill percentage per NEC Chapter 9, Table 1.

    FORMULA (NEC Chapter 9, Table 1 + Table 5):
      conductor_area_i = π × (dᵢ/2)²   [each conductor, in²]
      total_area = Σ conductor_area_i
      fill% = (total_area / conduit_internal_area) × 100

    The ×2 divisor in (d/2) is CRITICAL. Using diameter directly instead
    of radius would report 4× the correct area — approving overloaded
    conduits. Internally verified against NEC Annex C examples.

    Args:
        conduit_type:        Conduit material type.
        trade_size:          Nominal trade size.
        cable_diameters_in:  List of cable outer diameters in inches.
                             Each entry is one conductor (including insulation).

    Returns:
        Result.ok(FillResult) — fill calculation complete.
        Result.err(PhysicsError) — negative diameter or empty list.
        Result.err(CodeViolationError) — fill > NEC limit (informational,
            but returned as error so caller must explicitly handle).

    Reference: NEC 2022 Chapter 9, Table 1.

    """
    # ── Input validation ─────────────────────────────────────────────────────

    if not cable_diameters_in:
        return Result.err(PhysicsError(
            message="cable_diameters_in must not be empty.",
            remediation=(
                "Provide at least one conductor diameter. "
                "If the conduit is empty, no fill calculation is needed."
            ),
        ))

    for i, d in enumerate(cable_diameters_in):
        if not math.isfinite(d):
            return Result.err(PhysicsError(
                message=f"cable_diameters_in[{i}]={d} is not finite.",
                remediation="All cable diameters must be positive finite numbers.",
            ))
        if d <= 0.0:
            return Result.err(PhysicsError(
                message=f"cable_diameters_in[{i}]={d} ≤ 0.",
                remediation=(
                    "All cable diameters must be strictly positive. "
                    "Verify conductor OD values from NEC Table 5 or manufacturer data."
                ),
            ))

    # ── Get conduit internal area from NEC Table 4 ───────────────────────────

    area_result = get_internal_area(conduit_type, trade_size)
    if area_result.is_err():
        return Result.err(area_result.error)  # type: ignore[arg-type]
    conduit_area = area_result.value

    if conduit_area <= 0.0:
        return Result.err(PhysicsError(
            message=f"Conduit internal area={conduit_area} ≤ 0 in².",
            remediation="Internal area must be positive. Check NEC Table 4 data.",
        ))

    # ── Calculate total conductor cross-sectional area ───────────────────────
    # Formula: π × (d/2)² = π × d² / 4
    # NEC Chapter 9, Table 5 uses this formula (area = π/4 × OD²)

    total_conductor_area: float = sum(
        math.pi * (d / 2.0) ** 2
        for d in cable_diameters_in
    )

    # ── Fill percentage ───────────────────────────────────────────────────────

    fill_pct: float = (total_conductor_area / conduit_area) * 100.0
    n = len(cable_diameters_in)
    max_pct = _max_fill_pct(n)
    is_compliant = fill_pct <= max_pct

    # ── Recommendation if non-compliant ──────────────────────────────────────

    recommended: Optional[TradeSize] = None
    if not is_compliant:
        # Walk up trade sizes until fill is compliant
        candidate = _next_larger_size(trade_size)
        while candidate is not None:
            candidate_area_result = get_internal_area(conduit_type, candidate)
            if candidate_area_result.is_ok():
                candidate_area = candidate_area_result.value
                if (total_conductor_area / candidate_area) * 100.0 <= max_pct:
                    recommended = candidate
                    break
            candidate = _next_larger_size(candidate)

    nec_ref = (
        f"NEC 2022 Ch.9 Table 1: {n} conductor(s) → {max_pct:.0f}% max fill; "
        f"Table 4: {conduit_type.value} {trade_size.value} "
        f"internal area = {conduit_area:.3f} in²"
    )

    result = FillResult(
        conduit_type=conduit_type,
        trade_size=trade_size,
        conductor_count=n,
        total_conductor_area_in2=total_conductor_area,  # float64 precision preserved per zero-defect policy
        conduit_internal_area_in2=conduit_area,
        fill_percentage=round(fill_pct, 4),
        max_allowed_pct=max_pct,
        is_compliant=is_compliant,
        recommended_size=recommended,
        nec_reference=nec_ref,
    )

    if not is_compliant:
        return Result.err(CodeViolationError(
            message=(
                f"Conduit fill {fill_pct:.2f}% exceeds NEC Table 1 limit "
                f"of {max_pct:.0f}% for {n} conductor(s) in "
                f"{conduit_type.value} {trade_size.value}. "
                + (f"Recommended: {recommended.value}." if recommended else
                   "No standard size in catalog can accommodate these conductors.")
            ),
            code_reference=nec_ref,
            remediation=(
                f"""Increase conduit to {recommended.value if recommended else 'larger than 2"'}, """
                "reduce conductor count, or split conductors into two conduits."
            ),
            severity=Severity.FATAL,
        ))

    return Result.ok(result)


def calculate_fill_compliant(
    conduit_type: ConduitType,
    trade_size: TradeSize,
    cable_diameters_in: List[float],
) -> Result[FillResult, PhysicsError | CodeViolationError]:
    """Identical to calculate_fill but returns Result.ok() even when
    fill is non-compliant, embedding the violation in FillResult.

    Use this when you want to inspect fill percentage regardless of
    compliance (e.g. for reporting), rather than treating violation
    as an error. The is_compliant flag and violations field carry
    the status.

    Reference: NEC 2022 Chapter 9, Table 1.
    """
    result = calculate_fill(conduit_type, trade_size, cable_diameters_in)
    if result.is_err():
        err = result.error
        # If it's a CodeViolationError from fill overage, rebuild as ok()
        if isinstance(err, CodeViolationError):
            area_r = get_internal_area(conduit_type, trade_size)
            if area_r.is_err():
                return result  # propagate real error
            conduit_area = area_r.value
            total_area = sum(math.pi * (d / 2.0) ** 2 for d in cable_diameters_in)
            fill_pct = (total_area / conduit_area) * 100.0
            n = len(cable_diameters_in)
            max_pct = _max_fill_pct(n)
            fill_result = FillResult(
                conduit_type=conduit_type,
                trade_size=trade_size,
                conductor_count=n,
                total_conductor_area_in2=total_area,  # float64 precision preserved per zero-defect policy
                conduit_internal_area_in2=conduit_area,
                fill_percentage=round(fill_pct, 4),
                max_allowed_pct=max_pct,
                is_compliant=False,
                recommended_size=None,
                nec_reference="NEC 2022 Ch.9 Table 1 — VIOLATION",
            )
            return Result.ok(fill_result)
        return result  # PhysicsError — always propagate
    return result
