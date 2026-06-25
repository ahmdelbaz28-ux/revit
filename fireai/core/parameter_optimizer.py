"""fireai/core/parameter_optimizer.py  V1.0
=========================================
Grid-searches verify_step on benchmark rooms.
Results saved to JSON for manual engineer review.

DO NOT modify density_optimizer.py — this is a read-only consumer.

Only verify_step (patched via _dm.VERIFY_STEP) is swept.
k_neighbours is NOT grid-searched because fireai's DensityOptimizer
does not expose it as a parameter — it is internal to the engine.

Usage
-----
    from fireai.core.parameter_optimizer import ParameterOptimizer
    from fireai.core.spatial_engine.density_optimizer import Room

    benchmark = [
        Room("open_plan", 40, 20, 3.0),
        Room("warehouse",  60, 30, 6.0),
        Room("lobby",      15, 15, 4.5),
        Room("cafeteria",  25, 18, 3.5),
    ]
    opt    = ParameterOptimizer()
    result = opt.optimise(benchmark, steps=[0.15, 0.20, 0.25, 0.30])
    print(result.table())
    opt.save(result, "fireai/reports/param_search.json")
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import asdict, dataclass
from typing import List, Optional

import fireai.core.spatial_engine.density_optimizer as _dm
from fireai.core.spatial_engine.density_optimizer import (
    DETECTOR_RADIUS,
    DensityOptimizer,
    Room,
)


@dataclass
class ParamConfig:
    """Result of one verify_step configuration across benchmark rooms."""

    verify_step: float
    total_time_ms: int
    avg_count: float
    all_valid: bool
    pareto_score: float  # time_ms * avg_count / 10  (lower = better)
    per_room: List[dict]  # breakdown per benchmark room


@dataclass
class ParameterOptimizationResult:
    """Complete grid search result with best config identified."""

    best_config: ParamConfig
    all_configs: List[ParamConfig]
    recommendation: str
    saved_to: Optional[str] = None

    def table(self) -> str:
        """Format results as a human-readable table."""
        lines = [
            "  verify_step Grid Search (fireai DensityOptimizer)",
            f"  {'step':>6} {'time_ms':>8} {'avg_count':>10} {'all_valid':>9} {'pareto':>8}",
            "  " + "-" * 50,
        ]
        for c in sorted(self.all_configs, key=lambda x: x.pareto_score):
            mark = "  <-- BEST" if c is self.best_config else ""
            lines.append(
                f"  {c.verify_step:>6.2f} {c.total_time_ms:>8}"
                f" {c.avg_count:>10.1f} {c.all_valid!s:>9}"
                f" {c.pareto_score:>8.2f}{mark}"
            )
        lines += [
            f"\n  Recommendation: {self.recommendation}",
        ]
        if self.saved_to:
            lines.append(f"  Results saved  : {self.saved_to}")
        return "\n".join(lines)


class ParameterOptimizer:
    """Finds the Pareto-optimal verify_step for fireai's DensityOptimizer.

    Only configurations where ALL benchmark rooms return proof_valid=True
    are considered. Results are written to JSON for manual engineer review.
    """

    def __init__(self, coverage_radius: float = DETECTOR_RADIUS) -> None:
        """Args:
        coverage_radius: Coverage radius in metres (default DETECTOR_RADIUS = 6.37m
                         per NFPA 72 §17.7.4.2.3.1: R = 0.7 × S = 0.7 × 9.1m at h≤3.0m).
                         Passed to DensityOptimizer.optimize().

        """
        self.coverage_radius = coverage_radius

    def optimise(
        self,
        rooms: List[Room],
        steps: Optional[List[float]] = None,
    ) -> ParameterOptimizationResult:
        """Run grid search over verify_step values.

        Args:
            rooms: List of Room objects to benchmark against.
            steps: List of verify_step values to try. Default: [0.10..0.40].

        Returns:
            ParameterOptimizationResult with best config and all configs.

        """
        steps = steps or [0.10, 0.15, 0.20, 0.25, 0.30, 0.40]
        old_step = _dm.VERIFY_STEP
        configs: List[ParamConfig] = []

        for step in steps:
            _dm.VERIFY_STEP = step
            t_total = 0
            count_sum = 0
            all_valid = True
            per_room = []

            for room in rooms:
                opt = DensityOptimizer()
                t0 = time.time()
                try:
                    lay = opt.optimize(
                        room,
                        coverage_radius=self.coverage_radius,
                    )
                    ms = int((time.time() - t0) * 1000)
                    t_total += ms
                    count_sum += lay.count
                    if not lay.proof_valid or lay.wall_violations > 0:
                        all_valid = False
                    per_room.append(
                        {
                            "room": room.name,
                            "count": lay.count,
                            "coverage": lay.coverage_pct,
                            "proof_valid": lay.proof_valid,
                            "wall_violations": lay.wall_violations,
                            "method": lay.method,
                            "ms": ms,
                        }
                    )
                except Exception as exc:
                    all_valid = False
                    per_room.append({"room": room.name, "error": str(exc)})

            _dm.VERIFY_STEP = old_step

            avg_count = count_sum / len(rooms) if rooms else 0
            pareto = t_total * avg_count / 10.0 if all_valid else float("inf")
            configs.append(
                ParamConfig(
                    verify_step=step,
                    total_time_ms=t_total,
                    avg_count=round(avg_count, 2),
                    all_valid=all_valid,
                    pareto_score=round(pareto, 3),
                    per_room=per_room,
                )
            )

        _dm.VERIFY_STEP = old_step  # safety restore

        valid = [c for c in configs if c.all_valid]
        best = min(valid, key=lambda c: c.pareto_score) if valid else configs[0]
        rec = (
            f"verify_step={best.verify_step:.2f} -> "
            f"pareto={best.pareto_score:.1f} "
            f"({best.total_time_ms}ms, avg {best.avg_count:.0f} dets/room). "
            f"Apply by setting _dm.VERIFY_STEP={best.verify_step:.2f} "
            f"in your startup config."
        )
        return ParameterOptimizationResult(
            best_config=best,
            all_configs=configs,
            recommendation=rec,
        )

    def save(
        self,
        result: ParameterOptimizationResult,
        path: str,
    ) -> None:
        """Write full grid search results to JSON for manual review."""
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        payload = {
            "recommendation": result.recommendation,
            "best": asdict(result.best_config),
            "all_configs": [asdict(c) for c in sorted(result.all_configs, key=lambda x: x.pareto_score)],
        }
        with open(path, "w") as f:
            json.dump(payload, f, indent=2)
        result.saved_to = path
