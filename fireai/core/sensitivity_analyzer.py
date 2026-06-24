"""fireai/core/sensitivity_analyzer.py  V1.0
==========================================
Standalone sensitivity tool for FireAI engineers.

Sweeps a single parameter across a list of values, calls
fireai's DensityOptimizer.optimize() for each value, and
returns a SensitivityReport with elasticity index and safe range.

DO NOT modify density_optimizer.py — this is a read-only consumer.

Parameters accepted
-------------------
'coverage_radius' : passed as coverage_radius= kwarg to optimize()
'verify_step'     : patched via _dm.VERIFY_STEP (restored after each call)

wall_min is NOT exposed because fireai's optimizer does not accept
it as a runtime argument — it is baked into the engine.

Usage
-----
    from fireai.core.sensitivity_analyzer import SensitivityAnalyzer

    analyzer = SensitivityAnalyzer()
    report   = analyzer.analyse(
        width=40.0, length=20.0, ceiling_height=3.0,
        param='coverage_radius',
        values=[3.5, 4.0, 4.57, 5.0, 5.5, 6.0],
        baseline_value=4.57,
    )
    print(report.table())
    report_dict = report.to_dict()   # JSON-serialisable
"""

from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass
from typing import Dict, List, Optional, Tuple

import fireai.core.spatial_engine.density_optimizer as _dm
from fireai.core.spatial_engine.density_optimizer import (
    DensityOptimizer,
    Room,
)

# ── data classes ─────────────────────────────────────────────


@dataclass
class SensitivityPoint:
    """One data point in a sensitivity sweep."""

    param_name: str
    param_value: float
    count: int
    coverage: float
    time_ms: int
    proof_valid: bool
    wall_viol: int
    method: str


@dataclass
class SensitivityReport:
    """Complete sensitivity analysis report for one parameter."""

    param_name: str
    baseline_value: float
    points: List[SensitivityPoint]
    elasticity: float  # |Δcount%| / |Δparam%| averaged
    safe_range: Tuple[float, float]  # values where proof_valid=True
    recommendation: str

    def table(self) -> str:
        """Format report as a human-readable table."""
        lines = [
            f"  Sensitivity: {self.param_name}  (baseline={self.baseline_value})",
            f"  {'Value':>8} {'Count':>6} {'Cov%':>7} {'ms':>6} {'Valid':>5} {'WallV':>5} {'Method'}",
            "  " + "-" * 60,
        ]
        for p in self.points:
            mark = " <-- baseline" if abs(p.param_value - self.baseline_value) < 1e-9 else ""
            lines.append(
                f"  {p.param_value:>8.3f} {p.count:>6} {p.coverage:>7.3f}"
                f" {p.time_ms:>6} {p.proof_valid!s:>5} {p.wall_viol:>5}"
                f"  {p.method}{mark}"
            )
        lines += [
            f"\n  Elasticity    : {self.elasticity:.4f}",
            f"  Safe range    : [{self.safe_range[0]:.3f}, {self.safe_range[1]:.3f}]",
            f"  Recommendation: {self.recommendation}",
        ]
        return "\n".join(lines)

    def to_dict(self) -> dict:
        """JSON-serialisable representation."""
        return asdict(self)


# ── main class ───────────────────────────────────────────────


class SensitivityAnalyzer:
    """Standalone sensitivity tool for FireAI engineers.

    Sweeps a single parameter across a list of values, calls
    fireai's DensityOptimizer.optimize() for each value, and
    returns a SensitivityReport with elasticity index and safe range.
    """

    SUPPORTED_PARAMS = ("coverage_radius", "verify_step")

    def __init__(self) -> None:
        pass

    # ── public ────────────────────────────────────────────────

    def analyse(
        self,
        width: float,
        length: float,
        ceiling_height: float = 3.0,
        room_name: str = "room",
        param: str = "coverage_radius",
        values: Optional[List[float]] = None,
        baseline_value: Optional[float] = None,
    ) -> SensitivityReport:
        """Run a single-parameter sensitivity sweep.

        Parameters
        ----------
        width, length, ceiling_height : room dimensions (metres)
        room_name     : label for the Room object
        param         : 'coverage_radius' or 'verify_step'
        values        : list of values to sweep (baseline included automatically)
        baseline_value: reference value (default: current engine default)

        """
        if param not in self.SUPPORTED_PARAMS:
            raise ValueError(
                f"param must be one of {self.SUPPORTED_PARAMS}. Do not pass 'wall_min' -- it is internal to the engine."
            )

        # Resolve baseline
        default_radius = 6.37  # NFPA 72 §17.7.4.2.3.1: R = 0.7 × S = 6.37m at h≤3.0m
        default_step = _dm.VERIFY_STEP
        base_val = (
            baseline_value
            if baseline_value is not None
            else (default_radius if param == "coverage_radius" else default_step)
        )

        values = sorted(set([base_val] + (values or [])))
        room = Room(name=room_name, width=width, length=length, ceiling_height=ceiling_height)
        points: List[SensitivityPoint] = []
        old_step = _dm.VERIFY_STEP

        for val in values:
            try:
                if param == "verify_step":
                    _dm.VERIFY_STEP = val
                    opt = DensityOptimizer()
                    t0 = time.time()
                    lay = opt.optimize(room, coverage_radius=default_radius)
                    ms = int((time.time() - t0) * 1000)
                    _dm.VERIFY_STEP = old_step

                else:  # coverage_radius
                    opt = DensityOptimizer()
                    t0 = time.time()
                    lay = opt.optimize(room, coverage_radius=val)
                    ms = int((time.time() - t0) * 1000)

                points.append(
                    SensitivityPoint(
                        param_name=param,
                        param_value=round(val, 6),
                        count=lay.count,
                        coverage=lay.coverage_pct,
                        time_ms=ms,
                        proof_valid=lay.proof_valid,
                        wall_viol=lay.wall_violations,
                        method=lay.method,
                    )
                )

            except Exception as exc:
                # Record failure without crashing the sweep
                points.append(
                    SensitivityPoint(
                        param_name=param,
                        param_value=round(val, 6),
                        count=-1,
                        coverage=0.0,
                        time_ms=0,
                        proof_valid=False,
                        wall_viol=-1,
                        method=f"ERROR: {exc}",
                    )
                )
            finally:
                _dm.VERIFY_STEP = old_step  # always restore

        base_pt = next((p for p in points if abs(p.param_value - base_val) < 1e-9), points[0])

        # Elasticity: |Δcount%| / |Δparam%| averaged across non-baseline points
        elast_vals = []
        for p in points:
            if abs(p.param_value - base_val) < 1e-9 or not p.proof_valid:
                continue
            dp = (p.param_value - base_val) / base_val if base_val else 0
            dc = (p.count - base_pt.count) / base_pt.count if base_pt.count else 0
            if abs(dp) > 1e-9:
                elast_vals.append(abs(dc / dp))
        elasticity = sum(elast_vals) / len(elast_vals) if elast_vals else 0.0

        valid_vals = [p.param_value for p in points if p.proof_valid and p.coverage >= 100.0]
        safe_lo = min(valid_vals) if valid_vals else base_val
        safe_hi = max(valid_vals) if valid_vals else base_val

        if elasticity < 0.10:
            rec = f"Insensitive -- safe to vary {param} freely in [{safe_lo:.3f}, {safe_hi:.3f}]"
        elif elasticity < 0.50:
            rec = f"Moderate -- stay within +/-20% of baseline ({base_val:.3f})"
        else:
            rec = f"Sensitive -- keep {param} at or near baseline ({base_val:.3f})"

        return SensitivityReport(
            param_name=param,
            baseline_value=base_val,
            points=points,
            elasticity=round(elasticity, 4),
            safe_range=(safe_lo, safe_hi),
            recommendation=rec,
        )

    def analyse_all(
        self,
        width: float,
        length: float,
        ceiling_height: float = 3.0,
        room_name: str = "room",
        radius_values: Optional[List[float]] = None,
        verify_step_values: Optional[List[float]] = None,
    ) -> Dict[str, SensitivityReport]:
        """Run both supported parameters and return dict of reports."""
        return {
            "coverage_radius": self.analyse(
                width,
                length,
                ceiling_height,
                room_name,
                param="coverage_radius",
                values=radius_values or [3.5, 3.8, 4.0, 4.2, 4.57, 5.0, 5.5, 6.0],
            ),
            "verify_step": self.analyse(
                width,
                length,
                ceiling_height,
                room_name,
                param="verify_step",
                values=verify_step_values or [0.10, 0.15, 0.20, 0.25, 0.30, 0.40],
            ),
        }

    def save_report(self, report: SensitivityReport, path: str) -> None:
        """Save a single report to JSON for manual review."""
        with open(path, "w") as f:
            json.dump(report.to_dict(), f, indent=2)

    def save_all_reports(self, reports: Dict[str, SensitivityReport], path: str) -> None:
        """Save all reports to one JSON file."""
        with open(path, "w") as f:
            json.dump({k: v.to_dict() for k, v in reports.items()}, f, indent=2)
