"""fireai.conduit.bend — NEC Bend Radius Verifier
===============================================

Verifies that conduit bend radii meet NEC minimums and computes
the developed length of each bend arc.

FORMULA (from NEC tables + geometry):
  developed_length = π × R × angle_degrees / 180

NEC MINIMUM BEND RADII (one-shot bends, Table 2 of each Article):
  EMT        — NEC 358.24
  UPVC Sch40 — NEC 352.24
  UPVC Sch80 — NEC 352.24
  RGD/RMC    — NEC 344.24

CUMULATIVE BEND LIMIT:
  NEC 358.26 / 352.26 / 344.26:
  "There shall not be more than the equivalent of four quarter bends
   (360° total) between pull points."

ENGINEERING NOTE (from pyRevit community discussion on conduit fitting
length calculation, discourse.pyrevitlabs.io/t/8712):
  The developed length of a bend (the actual conduit material consumed)
  is the arc length, not the chord. Many BIM tools incorrectly use chord
  length, under-counting material by up to 57% for 90° bends. This
  implementation always uses the correct arc formula.
"""

from __future__ import annotations

import math

from fireai.conduit.catalog import get_fitting
from fireai.conduit.errors import CodeViolationError, PhysicsError, Severity
from fireai.conduit.types import (
    BendResult,
    ConduitType,
    FittingType,
    Result,
    TradeSize,
)

# ─────────────────────────────────────────────────────────────────────────────
# NEC Minimum Bend Radii (inches) — from catalog (single source of truth)
# NEC 358.24 (EMT), 352.24 (PVC), 344.24 (RGD)
# These are the minimum centreline radii for field bends.
# Factory elbows (catalog fittings) meet or exceed these.
# ─────────────────────────────────────────────────────────────────────────────

def _min_bend_radius_in(
    conduit_type: ConduitType,
    trade_size: TradeSize,
) -> Result[float, PhysicsError]:
    """Return NEC minimum bend radius in inches from the fitting catalog.

    The catalog stores the STANDARD 90° elbow bend radius, which equals
    the NEC minimum for field bends. This avoids a second lookup table
    and keeps the catalog as the single source of truth.

    Reference: NEC 358.24 / 352.24 / 344.24.
    """
    result = get_fitting(conduit_type, trade_size, FittingType.ELBOW_90)
    if result.is_err():
        return Result.err(PhysicsError(
            message=(
                f"Cannot determine minimum bend radius for "
                f"{conduit_type.value} {trade_size.value}: "
                "no ELBOW_90 entry in catalog."
            ),
            remediation=(
                "Add an ELBOW_90 catalog entry for this conduit type and "
                "trade size, or specify a larger trade size."
            ),
        ))
    return Result.ok(result.value.bend_radius_in)


# ─────────────────────────────────────────────────────────────────────────────
# NEC Article references per conduit type
# ─────────────────────────────────────────────────────────────────────────────

_NEC_BEND_ARTICLE: dict[ConduitType, str] = {
    ConduitType.EMT:        "NEC 358.24 (EMT bend radius)",
    ConduitType.UPVC_SCH40: "NEC 352.24 (PVC conduit bend radius)",
    ConduitType.UPVC_SCH80: "NEC 352.24 (PVC conduit bend radius)",
    ConduitType.RGD:        "NEC 344.24 (RMC/RGD bend radius)",
}

_NEC_PULL_ARTICLE: dict[ConduitType, str] = {
    ConduitType.EMT:        "NEC 358.26 (EMT ≤360° between pull points)",
    ConduitType.UPVC_SCH40: "NEC 352.26 (PVC ≤360° between pull points)",
    ConduitType.UPVC_SCH80: "NEC 352.26 (PVC ≤360° between pull points)",
    ConduitType.RGD:        "NEC 344.26 (RMC ≤360° between pull points)",
}

# NEC maximum cumulative bend degrees between pull points (all conduit types)
MAX_CUMULATIVE_BEND_DEG: float = 360.0   # NEC 358.26/352.26/344.26


# ─────────────────────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────────────────────

def verify_bend_radius(
    conduit_type: ConduitType,
    trade_size: TradeSize,
    actual_radius_in: float,
    angle_deg: float = 90.0,
) -> Result[BendResult, PhysicsError | CodeViolationError]:
    """Verify a field bend meets NEC minimum radius and compute arc length.

    FORMULA (NEC + geometry):
      developed_length_in = π × R × angle_deg / 180

    This is the arc length formula. NEVER use chord length — it under-
    counts material by up to 57% for 90° bends (pyRevit community
    discussion, discourse.pyrevitlabs.io/t/8712).

    Args:
        conduit_type:     NEC wiring method.
        trade_size:       Nominal trade size.
        actual_radius_in: Measured centreline bend radius (inches).
        angle_deg:        Bend angle in degrees. Default 90°.

    Returns:
        Result.ok(BendResult) — radius ≥ NEC minimum (even if non-compliant
            the BendResult is returned; is_compliant flag indicates status).
        Result.err(PhysicsError) — non-finite or negative radius/angle.
        Result.err(CodeViolationError) — conduit type not in catalog.

    Reference: NEC 358.24 / 352.24 / 344.24.

    """
    # ── Input validation ─────────────────────────────────────────────────────

    if not math.isfinite(actual_radius_in):
        return Result.err(PhysicsError(
            message=f"actual_radius_in={actual_radius_in} is not finite.",
            remediation="Bend radius must be a positive finite number.",
        ))
    if actual_radius_in <= 0.0:
        return Result.err(PhysicsError(
            message=f"actual_radius_in={actual_radius_in} ≤ 0.",
            remediation=(
                "Bend radius must be > 0. "
                "A zero or negative radius is physically impossible."
            ),
        ))
    if not math.isfinite(angle_deg):
        return Result.err(PhysicsError(
            message=f"angle_deg={angle_deg} is not finite.",
            remediation="Bend angle must be a positive finite number.",
        ))
    if angle_deg <= 0.0:
        return Result.err(PhysicsError(
            message=f"angle_deg={angle_deg} ≤ 0.",
            remediation=(
                "Bend angle must be > 0°. "
                "A zero or negative angle produces no bend."
            ),
        ))
    if angle_deg > 360.0:
        return Result.err(PhysicsError(
            message=f"angle_deg={angle_deg} > 360°.",
            remediation=(
                "A single bend cannot exceed 360°. "
                "For spiral routing, sum multiple bend results."
            ),
        ))

    # ── Get NEC minimum radius ────────────────────────────────────────────────

    min_r_result = _min_bend_radius_in(conduit_type, trade_size)
    if min_r_result.is_err():
        return Result.err(min_r_result.error)  # type: ignore[arg-type]
    min_r = min_r_result.value

    # ── Compute developed length ──────────────────────────────────────────────
    # Arc length = π × R × θ / 180   (where θ is in degrees)

    developed_in: float = math.pi * actual_radius_in * angle_deg / 180.0
    developed_m: float = developed_in * 0.0254   # 1 in = 0.0254 m

    is_compliant = actual_radius_in >= min_r
    nec_ref = _NEC_BEND_ARTICLE.get(conduit_type, "NEC Chapter 3")

    bend_result = BendResult(
        conduit_type=conduit_type,
        trade_size=trade_size,
        actual_radius_in=actual_radius_in,
        min_required_in=min_r,
        angle_deg=angle_deg,
        developed_length_in=developed_in,
        developed_length_m=developed_m,
        is_compliant=is_compliant,
        nec_reference=nec_ref,
    )

    if not is_compliant:
        return Result.err(CodeViolationError(
            message=(
                f"Bend radius {actual_radius_in:.3f}\" is below NEC minimum "
                f"{min_r:.3f}\" for {conduit_type.value} {trade_size.value}. "
                f"Deficit: {min_r - actual_radius_in:.3f}\"."
            ),
            code_reference=nec_ref,
            remediation=(
                f"Increase bend radius to at least {min_r:.3f}\" "
                "or use a factory elbow (catalog fitting) which meets the minimum by design."
            ),
            severity=Severity.FATAL,
        ))

    return Result.ok(bend_result)


def calculate_developed_length(
    bend_radius_in: float,
    angle_deg: float,
) -> Result[float, PhysicsError]:
    """Compute bend arc length in inches.

    FORMULA: L = π × R × angle / 180
    This is the CORRECT arc formula. Never use chord (2R sin θ/2) for
    material takeoff — arc is always longer and gives the correct cut length.

    Args:
        bend_radius_in: Centreline bend radius in inches.
        angle_deg:      Bend angle in degrees.

    Returns:
        Result.ok(float) — arc length in inches.
        Result.err(PhysicsError) — non-finite or non-positive inputs.

    Reference: Geometry — arc length formula s = Rθ (θ in radians).

    """
    if not math.isfinite(bend_radius_in) or bend_radius_in <= 0.0:
        return Result.err(PhysicsError(
            message=f"bend_radius_in={bend_radius_in} must be a positive finite number.",
            remediation="Provide a positive finite radius.",
        ))
    if not math.isfinite(angle_deg) or angle_deg <= 0.0:
        return Result.err(PhysicsError(
            message=f"angle_deg={angle_deg} must be a positive finite number.",
            remediation="Provide a positive finite angle in degrees.",
        ))
    arc = math.pi * bend_radius_in * angle_deg / 180.0
    return Result.ok(arc)


def verify_cumulative_bends(
    conduit_type: ConduitType,
    bend_angles_deg: list[float],
) -> Result[float, CodeViolationError]:
    """Verify total bend degrees between pull points ≤ 360°.

    NEC 358.26 / 352.26 / 344.26: "There shall not be more than the
    equivalent of four quarter bends (360° total) between pull points,
    including bends located immediately at a box or conduit body."

    Args:
        conduit_type:     NEC wiring method (for article citation).
        bend_angles_deg:  List of individual bend angles between pull points.

    Returns:
        Result.ok(float) — total bend degrees (≤ 360°).
        Result.err(CodeViolationError) — total > 360°.

    Reference: NEC 358.26 / 352.26 / 344.26.

    """
    total = sum(bend_angles_deg)
    if total > MAX_CUMULATIVE_BEND_DEG:
        article = _NEC_PULL_ARTICLE.get(conduit_type, "NEC §xx.26")
        return Result.err(CodeViolationError(
            message=(
                f"Cumulative bend {total:.1f}° exceeds NEC limit of "
                f"{MAX_CUMULATIVE_BEND_DEG:.0f}° between pull points. "
                f"Excess: {total - MAX_CUMULATIVE_BEND_DEG:.1f}°."
            ),
            code_reference=article,
            remediation=(
                f"Insert a pull box after {MAX_CUMULATIVE_BEND_DEG:.0f}° of accumulated bends. "
                "The pull box resets the bend count to zero."
            ),
            severity=Severity.FATAL,
        ))
    return Result.ok(total)
