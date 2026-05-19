"""
fire_expert_system.py
=====================
Fire-detection expert system – rectangular rooms, NFPA 72 compliance.

Integrates DensityOptimizer (density_optimizer.py) as the sole placement
engine, replacing any previous naive grid algorithm.
"""

from __future__ import annotations
import math
from dataclasses import dataclass, field
from typing import List, Optional

from fireai.core.spatial_engine.density_optimizer import DensityOptimizer, Room, DetectorLayout, DETECTOR_RADIUS


# ── Expert-system facade ────────────────────────────────────────────────────────

class FireExpertSystem:
    """
    Main expert system class.

    Usage
    -----
    system = FireExpertSystem()
    result = system.analyse_room("office_10x8", width=10, length=8)
    print(result.summary())
    """

    def __init__(self):
        self.optimizer = DensityOptimizer()

    # ── public API ──────────────────────────────────────────────────────────────

    def analyse_room(self,
                     name: str,
                     width: float,
                     length: float,
                     ceiling_height: float = 3.0) -> AnalysisResult:
        """
        Perform full NFPA-72 analysis for a rectangular room.

        Parameters
        ----------
        name            : identifier string
        width, length   : room dimensions in metres
        ceiling_height  : used for future heat-stratification checks

        Returns
        -------
        AnalysisResult with detector positions, coverage, violations.
        """
        room   = Room(name=name, width=width, length=length,
                      ceiling_height=ceiling_height)
        layout = self.optimizer.optimize(room)
        theory = DensityOptimizer.theoretical_lower_bound(room)
        return AnalysisResult(layout=layout, theoretical_lower_bound=theory)

    def analyse_batch(self, rooms: List[dict]) -> List[AnalysisResult]:
        """Analyse a list of room dicts (keys: name, width, length[, ceiling_height])."""
        return [self.analyse_room(**r) for r in rooms]


# ── Result wrapper ──────────────────────────────────────────────────────────────

@dataclass
class AnalysisResult:
    layout: DetectorLayout
    theoretical_lower_bound: int

    @property
    def name(self):           return self.layout.room.name
    @property
    def count(self):          return self.layout.count
    @property
    def coverage(self):       return self.layout.coverage_pct
    @property
    def proof_valid(self):    return self.layout.proof_valid
    @property
    def wall_violations(self):return self.layout.wall_violations
    @property
    def passed(self):
        return self.proof_valid and self.wall_violations == 0

    def efficiency_ratio(self) -> float:
        """actual / theoretical_lower_bound — lower is better (1.0 = perfect)."""
        if self.theoretical_lower_bound == 0:
            return float("inf")
        return self.count / self.theoretical_lower_bound

    def summary(self) -> str:
        room = self.layout.room
        status = "PASS" if self.passed else "FAIL"
        return (
            f"[{status}] {self.name:30s} | "
            f"Detectors: {self.count:4d} (LB≥{self.theoretical_lower_bound:3d}) | "
            f"Coverage: {self.coverage:6.2f}% | "
            f"proof_valid: {str(self.proof_valid):5s} | "
            f"wall_violations: {self.wall_violations:2d} | "
            f"Ratio: {self.efficiency_ratio():.2f}x"
        )
