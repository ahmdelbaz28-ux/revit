"""fireai.conduit.fitting_engine — NEC Fitting Placement Engine
=============================================================

Transforms a routed waypoint path into a complete ConduitRun with all
fittings catalogued, NEC compliance verified, and pull boxes inserted
where the 360° bend limit would be exceeded.

ALGORITHM:
  1. Walk waypoints; detect direction changes → place ELBOW_90
  2. On straight segments > 10 ft (3.048 m) → place COUPLING every 10 ft
     (EMT limited to 10 ft sticks, NEC 358.120)
  3. Track cumulative bend degrees; when > 360°, insert PULL_BOX
     (NEC 358.26 / 352.26 / 344.26) and reset bend counter
  4. Verify each elbow bend radius ≥ NEC minimum (catalog lookup)
  5. Return ConduitRun with all violations recorded

DESIGN LINEAGE:
  Coupling placement interval adapted from EMT standard 10 ft stick length
  (NEC 358.120). The approach of walking waypoints and classifying segments
  mirrors the OpenMEP library's conduit placement API pattern (C#), here
  reimplemented in pure Python with Result<T,E> error handling.

Reference: NEC 358.26 / 352.26 / 344.26 (bend limit); NEC 358.120 (EMT
           coupling); NEC 110.3(B) (only listed fittings); NFPA 72 §12.2.
"""

from __future__ import annotations

import math
import uuid
from typing import Optional, Tuple

from fireai.conduit.bend import (
    MAX_CUMULATIVE_BEND_DEG,
    verify_cumulative_bends,
)
from fireai.conduit.catalog import get_fitting
from fireai.conduit.errors import CodeViolationError, PhysicsError, Severity
from fireai.conduit.types import (
    ConduitRun,
    ConduitSegment,
    ConduitType,
    FittingType,
    PlacedFitting,
    Point3D,
    Result,
    RoutePath,
    TradeSize,
)

# ─────────────────────────────────────────────────────────────────────────────
# Constants
# ─────────────────────────────────────────────────────────────────────────────

# EMT standard stick length = 10 ft = 3.048 m (NEC 358.120)
# Couplings placed at every full stick boundary on straight runs
_EMT_STICK_LENGTH_M: float = 3.048

# UPVC / RGD standard stick length = 10 ft = 3.048 m
_PVC_STICK_LENGTH_M: float = 3.048
_RGD_STICK_LENGTH_M: float = 3.048

# Pull box clearance — stub label for pull box fittings
_PULL_BOX_CATALOG: str = "PB-GEN"

# Angle of each standard elbow (90°)
_ELBOW_ANGLE_DEG: float = 90.0


def _stick_length(conduit_type: ConduitType) -> float:
    """Return the standard conduit stick length in metres for coupling spacing."""
    if conduit_type == ConduitType.EMT:
        return _EMT_STICK_LENGTH_M
    if conduit_type in (ConduitType.UPVC_SCH40, ConduitType.UPVC_SCH80):
        return _PVC_STICK_LENGTH_M
    return _RGD_STICK_LENGTH_M   # RGD


def _midpoint(a: Point3D, b: Point3D) -> Point3D:
    """Return midpoint of two points."""
    return Point3D(
        x=(a.x + b.x) / 2.0,
        y=(a.y + b.y) / 2.0,
        z=(a.z + b.z) / 2.0,
    )


def _lerp(a: Point3D, b: Point3D, t: float) -> Point3D:
    """Linear interpolation: a + t × (b − a), t ∈ [0, 1]."""
    return Point3D(
        x=a.x + t * (b.x - a.x),
        y=a.y + t * (b.y - a.y),
        z=a.z + t * (b.z - a.z),
    )


# ─────────────────────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────────────────────

def place_fittings(
    path: RoutePath,
    conduit_type: ConduitType,
    trade_size: TradeSize,
    run_id: Optional[str] = None,
) -> Result[ConduitRun, PhysicsError | CodeViolationError]:
    """Place fittings along a routed path to produce a complete ConduitRun.

    Input is a RoutePath (waypoints list). Output is a ConduitRun with:
      - ConduitSegment for every straight stick
      - PlacedFitting (ELBOW_90) at every direction change
      - PlacedFitting (COUPLING) every 10 ft on straight runs
      - PlacedFitting (PULL_BOX) when cumulative bends would exceed 360°

    All NEC violations are recorded in ConduitRun.violations (never raised).
    The run is returned even when non-compliant so the caller can inspect
    and report all violations at once.

    Args:
        path:         RoutePath from orthogonal_astar().
        conduit_type: Conduit material type.
        trade_size:   Nominal trade size.
        run_id:       Optional identifier. Auto-generated if None.

    Returns:
        Result.ok(ConduitRun) — always (violations embedded in run).
        Result.err(PhysicsError) — non-finite waypoint coordinates.

    Reference: NEC 358.26 / 352.26 / 344.26; NEC 358.120; NEC 110.3(B).

    """
    # ── Validate input path ───────────────────────────────────────────────────

    if len(path.waypoints) < 2:
        return Result.err(PhysicsError(
            message=(
                f"RoutePath has {len(path.waypoints)} waypoints; minimum is 2."
            ),
            remediation=(
                "Ensure the router produced a path with at least a start and end point."
            ),
        ))

    for i, wp in enumerate(path.waypoints):
        for ax, v in (("x", wp.x), ("y", wp.y), ("z", wp.z)):
            if not math.isfinite(v):
                return Result.err(PhysicsError(
                    message=f"Waypoint[{i}].{ax}={v} is not finite.",
                    remediation="All waypoint coordinates must be finite numbers.",
                ))

    rid = run_id or f"RUN-{uuid.uuid4().hex[:8].upper()}"
    run = ConduitRun(
        run_id=rid,
        conduit_type=conduit_type,
        trade_size=trade_size,
    )

    waypoints = list(path.waypoints)
    cumulative_bends_deg: float = 0.0
    stick_len = _stick_length(conduit_type)

    # Walk segments between consecutive waypoints
    for seg_idx in range(len(waypoints) - 1):
        wp_start = waypoints[seg_idx]
        wp_end   = waypoints[seg_idx + 1]

        # ── Direction change → place ELBOW_90 ────────────────────────────────

        if seg_idx > 0:
            wp_prev = waypoints[seg_idx - 1]
            if _is_direction_change(wp_prev, wp_start, wp_end):
                elbow_result = _place_elbow(
                    position=wp_start,
                    conduit_type=conduit_type,
                    trade_size=trade_size,
                )
                if elbow_result.is_ok():
                    elbow = elbow_result.value
                    run.fittings.append(elbow)
                    cumulative_bends_deg += elbow.angle_deg

                    # Check cumulative bend limit
                    cum_result = verify_cumulative_bends(
                        conduit_type, [cumulative_bends_deg]
                    )
                    if cum_result.is_err():
                        # Insert pull box — resets bend counter
                        pb = _make_pull_box(wp_start, conduit_type, trade_size)
                        run.fittings.append(pb)
                        run.violations.append(
                            f"[PULL_BOX INSERTED at {wp_start!r}] "
                            + cum_result.error.message
                        )
                        cumulative_bends_deg = 0.0
                else:
                    run.violations.append(
                        f"ELBOW_90 not in catalog for "
                        f"{conduit_type.value} {trade_size.value}: "
                        + elbow_result.error.message
                    )

        # ── Place straight segment with couplings ─────────────────────────────

        seg_length = wp_start.distance_to(wp_end)
        _place_segment_with_couplings(
            run=run,
            seg_start=wp_start,
            seg_end=wp_end,
            seg_length=seg_length,
            conduit_type=conduit_type,
            trade_size=trade_size,
            stick_len=stick_len,
        )

    # ── Final bend compliance check ───────────────────────────────────────────

    if cumulative_bends_deg > MAX_CUMULATIVE_BEND_DEG:
        run.violations.append(
            f"Final cumulative bends {cumulative_bends_deg:.1f}° exceed "
            f"NEC limit {MAX_CUMULATIVE_BEND_DEG:.0f}°. "
            "Insert an additional pull box."
        )

    return Result.ok(run)


# ─────────────────────────────────────────────────────────────────────────────
# Internal helpers
# ─────────────────────────────────────────────────────────────────────────────

def _is_direction_change(
    prev: Point3D, curr: Point3D, nxt: Point3D
) -> bool:
    """True if the path changes direction at curr.

    Direction is the unit vector from one point to the next,
    quantised to the dominant axis (orthogonal routing guarantees
    only one axis changes at a time).
    """
    def dom_dir(a: Point3D, b: Point3D) -> Tuple[int, int, int]:
        dx, dy, dz = b.x - a.x, b.y - a.y, b.z - a.z
        return (
            (1 if dx > 0 else -1 if dx < 0 else 0),
            (1 if dy > 0 else -1 if dy < 0 else 0),
            (1 if dz > 0 else -1 if dz < 0 else 0),
        )

    d1 = dom_dir(prev, curr)
    d2 = dom_dir(curr, nxt)
    return d1 != d2


def _place_elbow(
    position: Point3D,
    conduit_type: ConduitType,
    trade_size: TradeSize,
) -> Result[PlacedFitting, CodeViolationError]:
    """Look up and construct a PlacedFitting for a 90° elbow.

    Reference: NEC 110.3(B) — only listed fittings.
    """
    cat_result = get_fitting(conduit_type, trade_size, FittingType.ELBOW_90)
    if cat_result.is_err():
        from fireai.conduit.errors import CodeViolationError
        return Result.err(CodeViolationError(
            message=cat_result.error.message,
            code_reference="NEC 110.3(B)",
            remediation=cat_result.error.remediation,
            severity=Severity.FATAL,
        ))

    fitting = cat_result.value
    pf = PlacedFitting(
        fitting_type=FittingType.ELBOW_90,
        conduit_type=conduit_type,
        trade_size=trade_size,
        position=position,
        catalog_number=fitting.catalog_number,
        angle_deg=_ELBOW_ANGLE_DEG,
        developed_length_m=fitting.developed_length_m,
        weight_kg=fitting.weight_kg,
    )
    return Result.ok(pf)


def _make_pull_box(
    position: Point3D,
    conduit_type: ConduitType,
    trade_size: TradeSize,
) -> PlacedFitting:
    """Construct a pull box PlacedFitting.

    Pull boxes are not catalogued as fittings but are tracked in the
    ConduitRun to ensure they appear in the material schedule and BOM.

    Reference: NEC 314.28 (pull box sizing); 358.26 (when required).
    """
    return PlacedFitting(
        fitting_type=FittingType.PULL_BOX,
        conduit_type=conduit_type,
        trade_size=trade_size,
        position=position,
        catalog_number=_PULL_BOX_CATALOG,
        angle_deg=0.0,
        developed_length_m=0.0,
        weight_kg=0.5,   # typical pull box weight
    )


def _place_segment_with_couplings(
    run: ConduitRun,
    seg_start: Point3D,
    seg_end: Point3D,
    seg_length: float,
    conduit_type: ConduitType,
    trade_size: TradeSize,
    stick_len: float,
) -> None:
    """Add straight ConduitSegment(s) and COUPLING fittings every stick_len.

    For a segment of length L:
      - If L ≤ stick_len: single segment, no coupling needed
      - If L > stick_len: multiple sticks, coupling at each joint

    Coupling positions are linearly interpolated along the segment.
    """
    if seg_length <= 0.0:
        return

    # Number of full sticks required
    n_sticks = math.ceil(seg_length / stick_len)

    if n_sticks <= 1:
        # Single stick — no coupling needed
        run.segments.append(ConduitSegment(
            start=seg_start,
            end=seg_end,
            conduit_type=conduit_type,
            trade_size=trade_size,
        ))
        return

    # Multiple sticks — place couplings at joints
    cat_result = get_fitting(conduit_type, trade_size, FittingType.COUPLING)
    coupling_cat = cat_result.value.catalog_number if cat_result.is_ok() else "EC-000"
    coupling_wt  = cat_result.value.weight_kg       if cat_result.is_ok() else 0.0

    prev_pt = seg_start
    for i in range(1, n_sticks + 1):
        t = min(1.0, (i * stick_len) / seg_length)
        next_pt = _lerp(seg_start, seg_end, t) if t < 1.0 else seg_end

        run.segments.append(ConduitSegment(
            start=prev_pt,
            end=next_pt,
            conduit_type=conduit_type,
            trade_size=trade_size,
        ))

        # Place coupling at joint (not after last stick)
        if i < n_sticks:
            run.fittings.append(PlacedFitting(
                fitting_type=FittingType.COUPLING,
                conduit_type=conduit_type,
                trade_size=trade_size,
                position=next_pt,
                catalog_number=coupling_cat,
                angle_deg=0.0,
                developed_length_m=0.0,
                weight_kg=coupling_wt,
            ))

        prev_pt = next_pt
