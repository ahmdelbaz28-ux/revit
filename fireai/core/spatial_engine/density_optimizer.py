"""
DensityOptimizer – NFPA 72 compliant smoke/heat detector placement.

NFPA 72 (2022 Edition) rules implemented:
  - Smooth ceiling: max spacing 9.14 m (30 ft) centre-to-centre
  - Wall offset: ≥ WALL_MIN_M (0.10 m / 4 in) from wall
  - Coverage: every floor point within detector radius (4.57 m = half of 9.14 m)
  - 100% area verified at VERIFY_STEP resolution

Algorithm: Minimum rectangular grid with wall-margin alignment.

Key insight:
  For a 1-D axis of length D, first detector at offset `a` from wall,
  last at `D-a`.  Spacing between detectors S = (D - 2a) / (N-1).
  NFPA constraint: S ≤ MAX_SPACING.
  Coverage constraint: every point within R = MAX_SPACING/2 of some detector.
  The hardest point to cover is the midpoint between two adjacent detectors:
  distance = S/2 ≤ R → S ≤ 2R = MAX_SPACING  ✓ (redundant with NFPA constraint).
  For diagonal coverage (2-D grid), worst-case point is centre of a cell:
  distance = sqrt((Sx/2)^2 + (Sy/2)^2) ≤ R.
  We enforce this explicitly and reduce spacing if needed.
"""

import math
from dataclasses import dataclass, field
from typing import List, Tuple

# ── NFPA 72 Constants ──────────────────────────────────────────────────────────
MAX_SPACING_M   = 9.14    # 30 ft  – max centre-to-centre on any axis
DETECTOR_RADIUS = MAX_SPACING_M / 2   # 4.57 m – coverage radius
WALL_MIN_M      = 0.10    # 4 in   – min distance from wall to detector centre
VERIFY_STEP     = 0.25    # m – grid density for coverage proof


@dataclass
class Room:
    name: str
    width: float   # metres (X axis)
    length: float  # metres (Y axis)
    ceiling_height: float = 3.0


@dataclass
class DetectorLayout:
    room: Room
    detectors: List[Tuple[float, float]] = field(default_factory=list)
    coverage_pct: float = 0.0
    proof_valid: bool = False
    wall_violations: int = 0
    notes: str = ""

    @property
    def count(self):
        return len(self.detectors)


class DensityOptimizer:
    """
    Minimum-detector NFPA-72 compliant layout for a rectangular room.

    Two-phase approach:
    1. Compute minimum N detectors per axis satisfying NFPA spacing + wall rules.
    2. Verify 2-D diagonal coverage; if any gap, reduce effective spacing
       by increasing N until coverage holds without adding extra detectors.
    """

    def __init__(self,
                 max_spacing: float = MAX_SPACING_M,
                 wall_min: float = WALL_MIN_M,
                 radius: float = DETECTOR_RADIUS):
        self.max_spacing = max_spacing
        self.wall_min    = wall_min
        self.radius      = radius

    # ── public API ─────────────────────────────────────────────────────────────

    def optimize(self, room: Room) -> DetectorLayout:
        """Return minimum-detector NFPA-72 layout for `room`."""
        layout = DetectorLayout(room=room)
        xs, ys = self._optimal_axes(room.width, room.length)
        layout.detectors = [(x, y) for x in xs for y in ys]
        self._verify(layout)
        # Fallback: should not be needed, but safety net
        if not layout.proof_valid:
            layout.detectors = self._emergency_fill(room, layout.detectors)
            self._verify(layout)
        return layout

    # ── axis computation ────────────────────────────────────────────────────────

    def _optimal_axes(self,
                      W: float,
                      L: float
                      ) -> Tuple[List[float], List[float]]:
        """
        Find minimum Nx × Ny such that:
          1. Per-axis NFPA spacing ≤ max_spacing
          2. Per-axis wall offset ≥ wall_min
          3. 2-D diagonal coverage: sqrt((Sx/2)^2 + (Sy/2)^2) ≤ radius

        Strategy: search all (Nx, Ny) pairs starting from the minimum on each
        axis, bounded to a reasonable range, and pick the pair with the smallest
        product that satisfies the 2-D diagonal constraint.
        """
        Nx0 = self._min_n(W)
        Ny0 = self._min_n(L)

        best_nx, best_ny = None, None
        best_total = float("inf")

        # Search window: never need more than 3× the 1-D minimum
        for Nx in range(Nx0, Nx0 + 15):
            for Ny in range(Ny0, Ny0 + 15):
                total = Nx * Ny
                if total >= best_total:
                    continue          # prune: can't beat current best
                xs = self._place(W, Nx)
                ys = self._place(L, Ny)
                Sx = (xs[-1] - xs[0]) / (Nx - 1) if Nx > 1 else 0.0
                Sy = (ys[-1] - ys[0]) / (Ny - 1) if Ny > 1 else 0.0
                diag = math.sqrt((Sx / 2) ** 2 + (Sy / 2) ** 2)
                if diag <= self.radius + 1e-9:
                    best_nx, best_ny, best_total = Nx, Ny, total

        if best_nx is None:
            best_nx, best_ny = Nx0 + 5, Ny0 + 5   # safety fallback

        return self._place(W, best_nx), self._place(L, best_ny)

    def _min_n(self, dim: float) -> int:
        """
        Minimum detector count along one axis of length `dim`.
        Based on 1-D spacing constraint only (NFPA, wall-offset).
        """
        if dim <= 2 * self.wall_min:
            return 1
        interior = dim - 2 * self.wall_min          # span between first & last
        n_intervals = math.ceil(interior / self.max_spacing)
        return max(1, n_intervals + 1)

    def _place(self, dim: float, n: int) -> List[float]:
        """
        Place `n` detectors evenly along axis of length `dim`.
        First/last at wall_min from walls (or centred if n=1).
        """
        if n == 1:
            return [dim / 2]
        a = self.wall_min
        b = dim - self.wall_min
        if b <= a:
            return [dim / 2]
        step = (b - a) / (n - 1)
        return [a + i * step for i in range(n)]

    # ── emergency fill ──────────────────────────────────────────────────────────

    def _emergency_fill(self,
                        room: Room,
                        existing: List[Tuple[float, float]]
                        ) -> List[Tuple[float, float]]:
        """Add detectors at uncovered sample-point centres (last resort)."""
        positions = list(existing)
        xs_grid = self._sample_coords(room.width)
        ys_grid = self._sample_coords(room.length)
        for x in xs_grid:
            for y in ys_grid:
                if not self._covered(x, y, positions):
                    positions.append((round(x, 4), round(y, 4)))
        return positions

    def _sample_coords(self, dim: float) -> List[float]:
        coords = []
        v = 0.0
        while v <= dim + 1e-9:
            coords.append(min(v, dim))
            v += VERIFY_STEP
        return coords

    # ── coverage verification ───────────────────────────────────────────────────

    def _verify(self, layout: DetectorLayout) -> None:
        """Compute coverage_pct, proof_valid, wall_violations in-place."""
        room = layout.room
        dets = layout.detectors
        W, L = room.width, room.length

        # Coverage
        total = covered = 0
        x = 0.0
        while x <= W + 1e-9:
            y = 0.0
            while y <= L + 1e-9:
                total += 1
                if self._covered(x, y, dets):
                    covered += 1
                y = min(y + VERIFY_STEP, L) if y < L else L + 1
            x = min(x + VERIFY_STEP, W) if x < W else W + 1

        layout.coverage_pct = round(100.0 * covered / total, 4) if total else 0.0
        layout.proof_valid  = (covered == total)

        # Wall violations
        violations = 0
        for (x, y) in dets:
            if x < self.wall_min - 1e-6 or x > W - self.wall_min + 1e-6:
                violations += 1
            if y < self.wall_min - 1e-6 or y > L - self.wall_min + 1e-6:
                violations += 1
        layout.wall_violations = violations

    def _covered(self,
                 px: float, py: float,
                 detectors: List[Tuple[float, float]]) -> bool:
        r2 = self.radius ** 2 + 1e-9
        return any((px - dx) ** 2 + (py - dy) ** 2 <= r2
                   for (dx, dy) in detectors)

    # ── theoretical minimum ─────────────────────────────────────────────────────

    @staticmethod
    def theoretical_minimum(room: Room) -> int:
        """Lower-bound: area covered by hexagonal close-packing of circles."""
        area     = room.width * room.length
        det_area = math.pi * DETECTOR_RADIUS ** 2
        return max(1, math.ceil(area / det_area))
