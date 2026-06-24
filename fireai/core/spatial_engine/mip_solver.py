"""MIP Solver for FireAI — Set Covering Formulation
=================================================
Wraps PuLP with graceful fallback to greedy if unavailable or timeout.

Architecture:
  - Standalone module — does NOT import from DensityOptimizer (V7.3 frozen)
  - Returns MIPResult dataclass with proven optimal count on candidate grid
  - Greedy (DensityOptimizer) always places actual detectors
  - MIP is verification only — never used for placement

Mathematical Formulation (Set Covering ILP):
  Variables:  x_j ∈ {0,1}  — place detector at candidate position j
  Objective:  minimize  Σ x_j
  Constraints: For every grid point i (coverage target):
               Σ_{j: dist(i,j) ≤ R} x_j ≥ 1

Terminology (TECHNICAL_HONESTY.md §5):
  - theoretical_lower_bound: ceil(area / πR²) — estimative, NOT proven
  - mip_proven_optimal_count: minimum on candidate grid — proven by ILP
  - theoretical_minimum: inside MIPResult only — proven Optimal status
  - These three are DIFFERENT values with DIFFERENT guarantees

Safety:
  - MIP positions are NOT NFPA-verified — do NOT store in RoomSummary
  - Only the COUNT is stored (mip_proven_optimal_count)
  - Actual detector placement always comes from DensityOptimizer V7.3
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

from .density_optimizer import DETECTOR_RADIUS

try:
    import pulp

    PULP_AVAILABLE = True
except ImportError:
    PULP_AVAILABLE = False


@dataclass
class MIPResult:
    """Result of MIP Set Covering optimization.

    Attributes:
        success:             True if solver found proven Optimal solution.
        detector_positions:  Positions from MIP (NOT NFPA-verified — for analysis only).
        theoretical_minimum: Proven minimum count on candidate grid (Optimal status).
        solver_status:       PuLP solver status string.
        solve_time_seconds:  Wall-clock solve time.
        used_mip:            True if MIP solver was actually used.
        fallback_reason:     Reason for fallback, or None if successful.
        candidate_step:      Grid spacing used for candidate positions (meters).

    """

    success: bool
    detector_positions: List[Tuple[float, float]] = field(default_factory=list)
    theoretical_minimum: Optional[int] = None
    solver_status: str = "not_run"
    solve_time_seconds: float = 0.0
    used_mip: bool = False
    fallback_reason: Optional[str] = None
    candidate_step: float = 1.0


def solve_set_covering_mip(
    room_width: float,
    room_length: float,
    coverage_radius: float = DETECTOR_RADIUS,  # R = 0.7 × 9.1m (aligned with DensityOptimizer DETECTOR_RADIUS)
    candidate_step: float = 1.0,
    time_limit_seconds: float = 10.0,
) -> MIPResult:
    """Solves the minimum detector placement problem as a Set Covering ILP.

    Variables:
        x_j ∈ {0,1}  — place detector at candidate position j

    Objective:
        minimize  Σ x_j

    Constraints:
        For every grid point i (coverage target):
            Σ_{j: dist(i,j) ≤ R} x_j ≥ 1

    Returns MIPResult with theoretical_minimum and positions.
    Falls back gracefully if PuLP unavailable or solve exceeds time_limit.

    Note: theoretical_minimum is proven Optimal on the candidate grid only.
    It may not be the absolute minimum over all possible positions.
    See TECHNICAL_HONESTY.md §5 for the strict distinction.
    """
    if not PULP_AVAILABLE:
        return MIPResult(
            success=False,
            solver_status="pulp_not_installed",
            fallback_reason="PuLP library not available — install with: pip install pulp",
            candidate_step=candidate_step,
        )

    start = time.perf_counter()

    # --- Build candidate detector positions (grid over room) ---
    candidates: List[Tuple[float, float]] = []
    cx = candidate_step / 2
    while cx <= room_width:
        cy = candidate_step / 2
        while cy <= room_length:
            candidates.append((cx, cy))
            cy += candidate_step
        cx += candidate_step

    # --- Build coverage target points (finer grid) ---
    target_step = candidate_step / 2
    targets: List[Tuple[float, float]] = []
    tx = target_step / 2
    while tx <= room_width:
        ty = target_step / 2
        while ty <= room_length:
            targets.append((tx, ty))
            ty += target_step
        tx += target_step

    if not candidates or not targets:
        return MIPResult(
            success=False,
            solver_status="degenerate_room",
            fallback_reason="Room dimensions too small to generate candidates.",
            candidate_step=candidate_step,
        )

    # --- Coverage map: for each target, which candidates cover it ---
    R2 = coverage_radius**2
    coverage: List[List[int]] = []  # coverage[i] = list of candidate indices
    for tx, ty in targets:
        covers = [j for j, (cx, cy) in enumerate(candidates) if (tx - cx) ** 2 + (ty - cy) ** 2 <= R2]
        coverage.append(covers)

    # --- Formulate ILP ---
    prob = pulp.LpProblem("FireDetectorSetCovering", pulp.LpMinimize)

    x = [pulp.LpVariable(f"x_{j}", cat="Binary") for j in range(len(candidates))]

    # Objective: minimize total detectors
    prob += pulp.lpSum(x)

    # Constraints: every target covered by at least one detector
    for i, covers in enumerate(coverage):
        if not covers:
            # Target not coverable by any candidate — infeasible
            return MIPResult(
                success=False,
                solver_status="infeasible_coverage",
                fallback_reason=f"Target point {targets[i]} cannot be covered by any candidate.",
                candidate_step=candidate_step,
            )
        prob += pulp.lpSum(x[j] for j in covers) >= 1

    # --- Solve with time limit ---
    solver = pulp.PULP_CBC_CMD(
        msg=0,
        timeLimit=time_limit_seconds,
        gapRel=0.0,  # demand proven optimality
    )

    try:
        prob.solve(solver)
    except Exception as exc:
        return MIPResult(
            success=False,
            solver_status="solver_exception",
            fallback_reason=str(exc),
            solve_time_seconds=time.perf_counter() - start,
            candidate_step=candidate_step,
        )

    elapsed = time.perf_counter() - start
    status = pulp.LpStatus[prob.status]

    if prob.status not in (1,):  # 1 = Optimal
        return MIPResult(
            success=False,
            solver_status=status,
            fallback_reason=f"Solver ended with status '{status}' after {elapsed:.2f}s — falling back to greedy.",
            solve_time_seconds=elapsed,
            candidate_step=candidate_step,
        )

    # --- Extract solution ---
    selected = [
        candidates[j] for j in range(len(candidates)) if pulp.value(x[j]) is not None and pulp.value(x[j]) > 0.5
    ]
    theoretical_minimum = len(selected)

    return MIPResult(
        success=True,
        detector_positions=selected,
        theoretical_minimum=theoretical_minimum,
        solver_status="Optimal",
        solve_time_seconds=elapsed,
        used_mip=True,
        candidate_step=candidate_step,
    )
