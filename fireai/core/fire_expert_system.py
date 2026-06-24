"""fire_expert_system.py
=====================
Fire-detection expert system – rectangular rooms, NFPA 72 compliance.

Integrates DensityOptimizer (density_optimizer.py) as the sole placement
engine, replacing any previous naive grid algorithm.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, List

from fireai.core.nfpa72_calculations import calculate_coverage_radius_from_height
from fireai.core.spatial_engine.density_optimizer import (
    DensityOptimizer,
    DetectorLayout,
    Room,
)

# ── Expert-system facade ────────────────────────────────────────────────────────


class FireExpertSystem:
    """Main expert system class.

    Usage
    -----
    system = FireExpertSystem()
    result = system.analyse_room("office_10x8", width=10, length=8)
    print(result.summary())
    """

    def __init__(self):
        self.optimizer = DensityOptimizer()

    # ── public API ──────────────────────────────────────────────────────────────

    def analyse_room(self, name: str, width: float, length: float, ceiling_height: float = 3.0) -> AnalysisResult:
        """Perform full NFPA-72 analysis for a rectangular room.

        Parameters
        ----------
        name            : identifier string
        width, length   : room dimensions in metres
        ceiling_height  : used for height-adjusted coverage radius per
                          NFPA 72 Table 17.6.3.1.1

        Returns
        -------
        AnalysisResult with detector positions, coverage, violations.

        V20.2 CRITICAL FIX: Now passes height-adjusted coverage_radius to
        DensityOptimizer.optimize(). Previous version used the default static
        radius (6.40m) regardless of ceiling height, which overestimated
        coverage at high ceilings (e.g., h=10m got R=6.40m instead of the
        correct R=4.48m) — producing too few detectors and leaving areas
        unprotected. Per NFPA 72 §17.6.3.1.1, coverage radius MUST be
        height-adjusted.

        """
        room = Room(name=name, width=width, length=length, ceiling_height=ceiling_height)
        # V20.2 FIX: Use height-adjusted coverage radius from NFPA 72 Table 17.6.3.1.1
        # instead of the static default DETECTOR_RADIUS=6.40m from DensityOptimizer.
        # At h=10m: old R=6.40m → only R=4.48m is correct → 43% overestimate.
        spec = calculate_coverage_radius_from_height(ceiling_height)
        layout = self.optimizer.optimize(room, coverage_radius=spec.radius)
        theory = DensityOptimizer.theoretical_lower_bound(room, coverage_radius=spec.radius)
        return AnalysisResult(layout=layout, theoretical_lower_bound=theory)

    def analyse_batch(self, rooms: List[dict]) -> List[AnalysisResult]:
        """Analyse a list of room dicts (keys: name, width, length[, ceiling_height])."""
        return [self.analyse_room(**r) for r in rooms]


# ── Result wrapper ──────────────────────────────────────────────────────────────


@dataclass
class AnalysisResult:
    layout: DetectorLayout
    theoretical_lower_bound: int
    room_id: str = ""
    detector_positions: list = field(default_factory=list)
    detector_type: Any = None
    coverage_result: Any = None

    @property
    def name(self):
        return self.layout.room.name

    @property
    def count(self):
        return self.layout.count

    @property
    def coverage(self):
        return self.layout.coverage_pct

    @property
    def proof_valid(self):
        return self.layout.proof_valid

    @property
    def wall_violations(self):
        return self.layout.wall_violations

    @property
    def passed(self):
        return self.proof_valid and self.wall_violations == 0

    def efficiency_ratio(self) -> float:
        """Actual / theoretical_lower_bound — lower is better (1.0 = perfect)."""
        if self.theoretical_lower_bound == 0:
            return float("inf")
        return self.count / self.theoretical_lower_bound

    def summary(self) -> str:
        status = "PASS" if self.passed else "FAIL"
        return (
            f"[{status}] {self.name:30s} | "
            f"Detectors: {self.count:4d} (LB≥{self.theoretical_lower_bound:3d}) | "
            f"Coverage: {self.coverage:6.2f}% | "
            f"proof_valid: {self.proof_valid!s:5s} | "
            f"wall_violations: {self.wall_violations:2d} | "
            f"Ratio: {self.efficiency_ratio():.2f}x"
        )
