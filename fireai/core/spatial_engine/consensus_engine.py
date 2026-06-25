"""Consensus Verification Engine — Triple Verification System
===========================================================
Combines results from all three independent verification engines
to produce a consensus verdict with confidence level.

ENGINES:
  1. Analytical  — exact geometric proof (corners, midpoints, walls)
  2. Voronoi     — gap-based analysis (largest uncovered point)
  3. Grid-Based  — δ-conservative grid (full coverage proof)

CONSENSUS RULES:
  3/3 PASS → VERIFIED  (green)  — All engines agree: coverage is complete
  2/3 PASS → WARNING   (yellow) — Discrepancy detected: investigate
  1/3 PASS → FAIL      (red)    — Major problem: DO NOT deploy
  0/3 PASS → FAIL      (red)    — Complete failure: fundamental issue

SAFETY PRINCIPLE: In fire safety, we follow the MOST CONSERVATIVE result.
If any engine says FAIL, the consensus is at most WARNING, never VERIFIED.

WHY THIS MATTERS:
  - Each engine has different failure modes
  - Grid engine can fail if grid resolution is wrong
  - Analytical engine can miss interior gaps in complex rooms
  - Voronoi engine can fail with numerical precision issues
  - If all three agree, the probability of a shared bug is extremely low
  - If they disagree, we know EXACTLY where to investigate

NFPA 72-2022 §17.7.4.2.3.1: Coverage radius R = 0.7 × S
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, List, Optional, Union

from .analytical_verifier import AnalyticalVerifier
from .voronoi_verifier import VoronoiVerifier

if TYPE_CHECKING:
    from .consensus_engine_v2 import EngineNameV2


class ConfidenceLevel(enum.Enum):
    """Consensus confidence level."""

    VERIFIED = "VERIFIED"  # 3/3 engines agree — safe to deploy
    WARNING = "WARNING"  # 2/3 engines agree — investigate
    FAIL = "FAIL"  # 1/3 or 0/3 — DO NOT deploy


class EngineName(enum.Enum):
    """Verification engine identifiers."""

    ANALYTICAL = "analytical"
    VORONOI = "voronoi"
    GRID = "grid"


@dataclass
class EngineVerdict:
    """Result from a single verification engine."""

    engine: Union[EngineName, EngineNameV2]
    passed: bool
    details: str = ""
    raw_result: Optional[object] = None  # The full result object from the engine


@dataclass
class ConsensusResult:
    """Combined result from all verification engines."""

    confidence: ConfidenceLevel
    is_safe: bool  # True only if VERIFIED (3/3)
    engines: List[EngineVerdict] = field(default_factory=list)
    n_pass: int = 0
    n_total: int = 0
    discrepancies: List[str] = field(default_factory=list)
    recommendation: str = ""

    @property
    def consensus_str(self) -> str:
        return f"{self.n_pass}/{self.n_total} {self.confidence.value}"


class ConsensusEngine:
    """Triple verification consensus engine.

    Runs all three independent verification engines and produces
    a consensus verdict based on agreement level.

    Usage:
        consensus = ConsensusEngine(coverage_radius=6.37)
        result = consensus.verify(
            width=10.0, length=10.0,
            detectors=[(2.5, 2.5), (7.5, 7.5)],
            grid_proof_valid=True,  # From DensityOptimizer
        )
        if result.is_safe:
            print("Coverage VERIFIED by all engines")
        elif result.confidence == ConfidenceLevel.WARNING:
            print(f"WARNING: {result.discrepancies}")
        else:
            print(f"FAIL: {result.discrepancies}")
    """

    def __init__(self, coverage_radius: float, wall_min: float = 0.10):
        self.R = coverage_radius
        self.wm = wall_min
        self._analytical = AnalyticalVerifier(coverage_radius, wall_min)
        self._voronoi = VoronoiVerifier(coverage_radius)

    def verify(
        self,
        width: float,
        length: float,
        detectors: List[tuple],
        grid_proof_valid: Optional[bool] = None,
        grid_coverage_pct: Optional[float] = None,
    ) -> ConsensusResult:
        """Run all verification engines and produce consensus.

        Args:
            width: Room width in meters.
            length: Room length in meters.
            detectors: List of (x, y) detector positions.
            grid_proof_valid: Result from grid-based engine (DensityOptimizer).
                If None, the grid engine result is not included.
            grid_coverage_pct: Coverage percentage from grid engine.

        Returns:
            ConsensusResult with combined verdict.

        """
        verdicts: List[EngineVerdict] = []

        # Engine 1: Analytical
        try:
            anal_result = self._analytical.verify(width, length, detectors)
            verdicts.append(
                EngineVerdict(
                    engine=EngineName.ANALYTICAL,
                    passed=anal_result.is_covered,
                    details=anal_result.details
                    or (
                        "PASS"
                        if anal_result.is_covered
                        else f"FAIL: corners={anal_result.corner_coverage_complete}, "
                        f"midpoints={anal_result.midpoint_coverage_complete}, "
                        f"walls={anal_result.wall_coverage_complete}"
                    ),
                    raw_result=anal_result,
                )
            )
        except Exception as e:
            verdicts.append(
                EngineVerdict(
                    engine=EngineName.ANALYTICAL,
                    passed=False,
                    details=f"ERROR: {e}",
                )
            )

        # Engine 2: Voronoi
        try:
            voro_result = self._voronoi.verify(width, length, detectors)
            verdicts.append(
                EngineVerdict(
                    engine=EngineName.VORONOI,
                    passed=voro_result.is_covered,
                    details=(
                        f"Max gap: {voro_result.max_gap_m:.2f}m "
                        f"(R={self.R:.2f}m, {'PASS' if voro_result.is_covered else 'FAIL'})"
                    ),
                    raw_result=voro_result,
                )
            )
        except Exception as e:
            verdicts.append(
                EngineVerdict(
                    engine=EngineName.VORONOI,
                    passed=False,
                    details=f"ERROR: {e}",
                )
            )

        # Engine 3: Grid-Based (use external result)
        if grid_proof_valid is not None:
            grid_passed = grid_proof_valid and (grid_coverage_pct is None or grid_coverage_pct >= 99.9)
            verdicts.append(
                EngineVerdict(
                    engine=EngineName.GRID,
                    passed=grid_passed,
                    details=(
                        f"proof_valid={grid_proof_valid}, coverage={grid_coverage_pct:.1f}%"
                        if grid_coverage_pct is not None
                        else f"proof_valid={grid_proof_valid}"
                    ),
                )
            )

        # Compute consensus
        n_pass = sum(1 for v in verdicts if v.passed)
        n_total = len(verdicts)
        discrepancies = []

        # Find discrepancies
        [v.engine.value for v in verdicts if v.passed]
        failing_engines = [v.engine.value for v in verdicts if not v.passed]

        if failing_engines:
            for v in verdicts:
                if not v.passed:
                    discrepancies.append(f"{v.engine.value}: {v.details}")

        # Determine confidence level
        if n_total >= 3:
            if n_pass == n_total:
                confidence = ConfidenceLevel.VERIFIED
            elif n_pass >= 2:
                confidence = ConfidenceLevel.WARNING
            else:
                confidence = ConfidenceLevel.FAIL
        elif n_total == 2:
            if n_pass == 2:
                # SAFETY: 2-engine agreement is NOT sufficient for VERIFIED.
                # Triple verification requires 3 engines. 2-engine agreement
                # is at most WARNING — a single undetected bug could cause
                # both engines to agree on a wrong result.
                confidence = ConfidenceLevel.WARNING
            elif n_pass == 1:
                confidence = ConfidenceLevel.WARNING
            else:
                confidence = ConfidenceLevel.FAIL
        else:
            # Only 1 engine — can't verify consensus
            confidence = ConfidenceLevel.WARNING if n_pass == 1 else ConfidenceLevel.FAIL

        # Safety: is_safe ONLY if VERIFIED (all engines agree)
        is_safe = confidence == ConfidenceLevel.VERIFIED

        # Recommendation
        if confidence == ConfidenceLevel.VERIFIED:
            recommendation = "All engines agree: coverage is complete. Safe to deploy."
        elif confidence == ConfidenceLevel.WARNING:
            failing = ", ".join(failing_engines)
            recommendation = (
                f"DISCREPANCY: Engine(s) {failing} report failure while others pass. "
                f"Investigate before deploying. Discrepancy details: {'; '.join(discrepancies)}"
            )
        else:
            recommendation = (
                f"MAJORITY FAILURE: Only {n_pass}/{n_total} engines pass. "
                f"DO NOT deploy. Issues: {'; '.join(discrepancies)}"
            )

        return ConsensusResult(
            confidence=confidence,
            is_safe=is_safe,
            engines=verdicts,
            n_pass=n_pass,
            n_total=n_total,
            discrepancies=discrepancies,
            recommendation=recommendation,
        )
