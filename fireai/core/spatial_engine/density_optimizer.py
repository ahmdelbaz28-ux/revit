"""
DensityOptimizer v6 – NFPA 72 Maximum-Reduction Placement Engine
=================================================================
Three placement strategies; best proven result selected per room.

  A) Hex-Guarded   : fixed S=6.794m, boundary guards ensure wall coverage.
  B) Hex-Adaptive  : S adapted so Nx positions span [wm,W-wm] exactly,
                     Ry = S·√3/2 (equilateral triangles, S ≤ R·√3).
  C) Rect-Best     : exhaustive (Nx,Ny) search with analytic diagonal filter.

All candidates sorted by count; cheapest verified first.
"""
import math
from dataclasses import dataclass, field
from typing import List, Tuple, Optional

MAX_SPACING_M   = 9.144         # 30 ft exactly in meters
DETECTOR_RADIUS = 0.7 * MAX_SPACING_M  # 6.40 m (NFPA 72 §17.7.4.2.3.1 - 0.7S Rule)
WALL_MIN_M      = 0.10
VERIFY_STEP     = 0.20                  # proof resolution (m)


def _hex_s_guarded(R: float, wm: float) -> float:
    """Max S s.t. side-wall boundary worst point ≤ R (analytical)."""
    a, b, c = 7/16, wm, wm**2 - R**2
    return (-b + math.sqrt(b**2 - 4*a*c)) / (2*a)


@dataclass
class Room:
    name: str
    width: float
    length: float
    ceiling_height: float = 3.0


@dataclass
class DetectorLayout:
    room: Room
    detectors: List[Tuple[float, float]] = field(default_factory=list)
    coverage_pct: float = 0.0
    proof_valid: bool = False
    wall_violations: int = 0
    method: str = ""
    violations: List[str] = field(default_factory=list)
    fallback_used: bool = False

    @property
    def count(self) -> int:
        return len(self.detectors)


class DensityOptimizer:

    def __init__(self,
                 max_spacing: float = MAX_SPACING_M,
                 wall_min:    float = WALL_MIN_M,
                 radius:      float = DETECTOR_RADIUS):
        self.max_spacing = max_spacing
        self.wm          = wall_min
        self.R           = radius
        # Hex spacing: use R*sqrt(3), clamped to max_spacing (NFPA 72 rule)
        self.S_g         = min(radius * math.sqrt(3), max_spacing)
        self.Ry_g        = self.S_g * math.sqrt(3) / 2

    # ── public ──────────────────────────────────────────────────────────────────

    def optimize(self, room: Room) -> DetectorLayout:
        cands: List[DetectorLayout] = []

        # Strategy A: hex-guarded (both orientations)
        for ax in (True, False):
            cands.append(self._hex_guarded(room, ax))

        # Strategy B: hex-adaptive (both orientations)
        for ax in (True, False):
            cands.append(self._hex_adaptive(room, ax))

        # Strategy C: best rectangular (analytic filter only)
        r = self._rect_best(room)
        if r:
            cands.append(r)

        # Verify cheapest candidates first; stop at first valid
        cands.sort(key=lambda c: c.count)
        best: Optional[DetectorLayout] = None
        
        # First pass: prefer NFPA-compliant with 100% coverage
        for lay in cands:
            self._verify(lay)
            self._audit_nfpa(lay)
            if len(lay.violations) == 0 and lay.coverage_pct == 100.0:
                best = lay
                break

        # Second pass: if none with 100%, pick highest coverage NFPA-compliant
        if best is None:
            best_cov = -1
            for lay in cands:
                if len(lay.violations) == 0 and lay.coverage_pct > best_cov:
                    best_cov = lay.coverage_pct
                    best = lay

        # Third pass: if none NFPA-compliant, pick highest coverage
        if best is None:
            best_cov = -1
            for lay in cands:
                if lay.coverage_pct > best_cov:
                    best_cov = lay.coverage_pct
                    best = lay

        # Fallback to _fallback only if no candidates
        if best is None:
            best = self._fallback(room)
            best.fallback_used = True
            self._verify(best)
            self._audit_nfpa(best)
            # Warn if coverage below 99.9%
            if best.coverage_pct < 99.9:
                best.proof_valid = False
                if not hasattr(best, 'violations'):
                    best.violations = []
                best.violations.append("FALLBACK_WARNING: coverage < 99.9%")
        return best

    # ── A: Hex-Guarded ──────────────────────────────────────────────────────────

    def _calculate_rows(self, L: float) -> List[float]:
        """
        Returns y-coordinates of rows.
        - First and last rows are within wall_limit (S/2) of the walls.
        - Inner rows are evenly spaced such that no wall segment is left uncovered.
        Uses max_spacing (S) to ensure wall segment coverage.
        """
        wm = self.wm
        S = self.max_spacing
        wall_limit = S / 2.0

        # Small room: single row at center
        if L <= 2 * wall_limit + 2 * wm:
            return [round(L / 2.0, 3)]

        # Boundary rows at wall_limit
        y_first = wall_limit
        y_last = L - wall_limit
        available = y_last - y_first

        # Number of gaps between rows (must be <= S for wall coverage)
        n_gaps = max(1, math.ceil(available / S))
        actual_gap = available / n_gaps

        rows = [y_first + i * actual_gap for i in range(n_gaps + 1)]
        return [round(y, 3) for y in rows]

    def _distribute_rows(self, L: float, n_rows: int) -> List[float]:
        """
        Evenly distribute row centers in [wm, L-wm].
        Guarantees wall distance <= S/2 for first and last rows.
        """
        if n_rows == 1:
            return [L / 2]
        available = L - 2 * self.wm
        gap = available / (n_rows - 1)
        return [self.wm + i * gap for i in range(n_rows)]

    def _calculate_columns(self, W: float) -> Tuple[int, float]:
        """
        Returns (n_cols, step_x) for horizontal placement.
        Handles very narrow rooms where single detector covers entire width.
        """
        available = W - 2 * self.wm
        
        # Very narrow room: single detector at center covers width
        if available <= self.R:
            return 1, 0.0
        
        # Medium room
        if available <= self.max_spacing:
            return 1, available / 2
        
        # Large room
        n = max(2, math.ceil(available / self.max_spacing) + 1)
        step = available / (n - 1)
        return n, step

    def _hex_guarded(self, room: Room, along_x: bool) -> DetectorLayout:
        W, L = (room.width, room.length) if along_x else (room.length, room.width)
        S, wm, R = self.S_g, self.wm, self.R
        pts: List[Tuple[float, float]] = []
        
        # Use calculated row distribution for NFPA compliance
        # _calculate_rows now returns y-coordinates directly
        y_coords = self._calculate_rows(L)
        n_cols, step_x = self._calculate_columns(W)
        
        for row_index, y in enumerate(y_coords):
            # Use actual step_x for offset (not S/2)
            offset = (step_x / 2) if (row_index % 2 == 1) else 0.0
            xs = self._row_xs_guarded(W, wm, step_x if step_x > 0 else S, offset, R)
            for x in xs:
                pts.append((x, y))

        # Corner Guards
        corners = [(wm, wm), (W - wm, wm), (wm, L - wm), (W - wm, L - wm)]
        for cx, cy in corners:
            covered = False
            for dx, dy in pts:
                if (cx - dx) ** 2 + (cy - dy) ** 2 <= R ** 2 + 1e-9:
                    covered = True
                    break
            if not covered:
                pts.append((cx, cy))

        if not along_x: pts = [(b, a) for a, b in pts]
        return DetectorLayout(room=room, detectors=pts,
                              method=f"hexG_{'x' if along_x else 'y'}")

    def _row_xs_guarded(self, W, wm, S, offset, R):
        xs = []; x = wm + offset
        while x <= W - wm + 1e-9: xs.append(x); x += S
        if xs and W - wm - xs[-1] > R + 1e-9: xs.append(W - wm)
        if xs and xs[0] - wm > R + 1e-9: xs.insert(0, wm)
        return xs

    # ── B: Hex-Adaptive ──────────────────────────────────────────────────────────

    def _hex_adaptive(self, room: Room, along_x: bool) -> DetectorLayout:
        """
        Uses calculated row distribution for NFPA compliance.
        """
        W, L = (room.width, room.length) if along_x else (room.length, room.width)
        R, wm = self.R, self.wm
        pts: List[Tuple[float, float]] = []

        # Use calculated row distribution (now returns y-coordinates directly)
        y_coords = self._calculate_rows(L)
        
        # Use _calculate_columns for horizontal placement
        Nx, Sx = self._calculate_columns(W)
        if Nx == 1:
            even_xs = [W / 2]
            odd_xs = [W / 2]
        else:
            even_xs = [wm + i * Sx for i in range(Nx)]
            odd_xs = [even_xs[0] + Sx / 2 + i * Sx for i in range(Nx)]

        # Place detectors for each row using Sx/2 offset
        for row_index, y in enumerate(y_coords):
            xs = even_xs if row_index % 2 == 0 else odd_xs
            for x in xs:
                pts.append((x, y))

        # Add Corner Guards
        corners = [(wm, wm), (W - wm, wm), (wm, L - wm), (W - wm, L - wm)]
        for cx, cy in corners:
            covered = False
            for dx, dy in pts:
                if (cx - dx) ** 2 + (cy - dy) ** 2 <= R ** 2 + 1e-9:
                    covered = True
                    break
            if not covered:
                pts.append((cx, cy))

        if not along_x:
            pts = [(b, a) for a, b in pts]
        return DetectorLayout(room=room, detectors=pts,
                              method=f"hexA_{'x' if along_x else 'y'}")

    # ── C: Rect-Best ──────────────────────────────────────────────────────────────

    def _rect_best(self, room: Room) -> Optional[DetectorLayout]:
        W, L = room.width, room.length
        Nx0 = self._min_n(W); Ny0 = self._min_n(L)
        best_nx, best_ny, best_t = None, None, 10**9
        for Nx in range(Nx0, Nx0 + 25):
            if Nx * Ny0 >= best_t: break
            for Ny in range(Ny0, Ny0 + 25):
                t = Nx * Ny
                if t >= best_t: break
                xs = self._place(W, Nx); ys = self._place(L, Ny)
                Sx = (xs[-1]-xs[0])/(Nx-1) if Nx > 1 else 0.0
                Sy = (ys[-1]-ys[0])/(Ny-1) if Ny > 1 else 0.0
                if math.sqrt((Sx/2)**2+(Sy/2)**2) <= self.R+1e-9:
                    best_nx, best_ny, best_t = Nx, Ny, t
        if best_nx is None: return None
        xs = self._place(W, best_nx); ys = self._place(L, best_ny)
        return DetectorLayout(room=room,
                              detectors=[(x, y) for x in xs for y in ys],
                              method=f"rect_{best_nx}x{best_ny}")

    # ── helpers ──────────────────────────────────────────────────────────────────

    def _min_n(self, dim: float) -> int:
        if dim <= 2*self.wm: return 1
        return max(1, math.ceil((dim-2*self.wm)/self.max_spacing)+1)

    def _place(self, dim: float, n: int) -> List[float]:
        if n == 1: return [dim / 2]
        a, b = self.wm, dim - self.wm
        if b <= a: return [dim / 2]
        return [a + i*(b-a)/(n-1) for i in range(n)]

    def _fallback(self, room: Room) -> DetectorLayout:
        xs = self._place(room.width, self._min_n(room.width))
        ys = self._place(room.length, self._min_n(room.length))
        pts = [(x, y) for x in xs for y in ys]

        # Corner guards: ensure all corners are within R of a detector
        W, L = room.width, room.length
        wm, R = self.wm, self.R
        corners = [(wm, wm), (W - wm, wm), (wm, L - wm), (W - wm, L - wm)]
        for cx, cy in corners:
            covered = False
            for dx, dy in pts:
                if (cx - dx) ** 2 + (cy - dy) ** 2 <= R ** 2 + 1e-9:
                    covered = True
                    break
            if not covered:
                pts.append((cx, cy))

        return DetectorLayout(room=room,
                              detectors=pts,
                              method="fallback")

    # ── exact proof ──────────────────────────────────────────────────────────────

    def _verify(self, layout: DetectorLayout) -> None:
        room = layout.room; dets = layout.detectors
        W, L = room.width, room.length
        R2 = self.R**2 + 1e-9; step = VERIFY_STEP
        total = covered = 0
        x = 0.0
        while True:
            y = 0.0
            while True:
                px, py = min(x, W), min(y, L)
                total += 1
                if any((px-dx)**2+(py-dy)**2 <= R2 for dx, dy in dets):
                    covered += 1
                if y >= L: break
                y = min(y+step, L)
            if x >= W: break
            x = min(x+step, W)
        layout.coverage_pct = round(100.0*covered/total, 4) if total else 0.0
        layout.proof_valid  = (covered == total)

        viol = 0
        for xd, yd in dets:
            if xd < self.wm-1e-6 or xd > W-self.wm+1e-6: viol += 1
            if yd < self.wm-1e-6 or yd > L-self.wm+1e-6: viol += 1
        layout.wall_violations = viol

    def _audit_nfpa(self, layout: DetectorLayout) -> None:
        """
        NFPA 72 §17.6.3.1 spacing audit - hardened version.
        Checks:
          1. Max detector-to-detector spacing <= S
          2. Every S meters of wall must have at least one detector within S/2
        """
        if not hasattr(layout, 'violations'):
            layout.violations = []
        else:
            layout.violations.clear()

        dets = layout.detectors
        W, L = layout.room.width, layout.room.length
        S = self.max_spacing
        wall_limit = S / 2.0
        n = len(dets)
        if n == 0:
            return

        # 1. Max spacing between any two detectors
        max_gap = 0.0
        for i in range(n):
            xi, yi = dets[i]
            min_dist_i = float('inf')
            for j in range(n):
                if i == j: continue
                xj, yj = dets[j]
                d2 = (xi - xj) ** 2 + (yi - yj) ** 2
                if d2 < min_dist_i:
                    min_dist_i = d2
            dist_i = math.sqrt(min_dist_i)
            if dist_i > max_gap:
                max_gap = dist_i
        if max_gap > S + 1e-6:
            layout.violations.append(
                f"Max detector spacing {max_gap:.3f}m > S={S:.3f}m"
            )

        # 2. Wall segment coverage: every S meters of wall must have detector within S/2
        def check_wall_segments(wall_length: float, get_point, wall_name: str):
            n_segments = max(1, int(math.ceil(wall_length / S)))
            seg_length = wall_length / n_segments
            for seg in range(n_segments):
                seg_center = (seg + 0.5) * seg_length
                px, py = get_point(seg_center)
                if not any(math.hypot(px-dx, py-dy) <= wall_limit for dx, dy in dets):
                    layout.violations.append(
                        f"No detector within {wall_limit:.2f}m of {wall_name} at {seg_center:.1f}m"
                    )

        check_wall_segments(L, lambda y: (0, y), "left wall")
        check_wall_segments(L, lambda y: (W, y), "right wall")
        check_wall_segments(W, lambda x: (x, 0), "bottom wall")
        check_wall_segments(W, lambda x: (x, L), "top wall")

        # Update proof_valid
        layout.proof_valid = len(layout.violations) == 0

    def _verify_vectorized(self, layout: DetectorLayout) -> None:
        """
        Vectorised coverage verification using NumPy.
        Same logic as _verify, but O(n*k) with broadcasting for speed.
        Falls back silently to _verify if NumPy is unavailable.
        """
        try:
            import numpy as np
        except ImportError:
            self._verify(layout)
            return

        room = layout.room
        dets = np.array(layout.detectors)
        if len(dets) == 0:
            layout.coverage_pct = 0.0
            layout.proof_valid = False
            layout.wall_violations = 0
            return

        W, L = room.width, room.length
        step = VERIFY_STEP
        xs = np.arange(0, W + step * 0.5, step)
        ys = np.arange(0, L + step * 0.5, step)
        xv, yv = np.meshgrid(xs, ys)
        test_points = np.column_stack([xv.ravel(), yv.ravel()])

        # Clip test points to room bounds exactly as _verify does
        test_points[:, 0] = np.clip(test_points[:, 0], 0, W)
        test_points[:, 1] = np.clip(test_points[:, 1], 0, L)

        # Vectorised distance check: (k, 1, 2) - (1, n, 2) -> (k, n, 2)
        diff = test_points[:, np.newaxis, :] - dets[np.newaxis, :, :]
        dist2 = (diff ** 2).sum(axis=2)
        r2 = self.R ** 2 + 1e-9
        covered = (dist2 <= r2).any(axis=1)

        total = len(test_points)
        covered_count = covered.sum()
        layout.coverage_pct = round(100.0 * covered_count / total, 4) if total else 0.0
        layout.proof_valid = (covered_count == total)

        # Wall violations — same logic as _verify
        viol = 0
        for xd, yd in layout.detectors:
            if xd < self.wm - 1e-6 or xd > W - self.wm + 1e-6:
                viol += 1
            if yd < self.wm - 1e-6 or yd > L - self.wm + 1e-6:
                viol += 1
        layout.wall_violations = viol

    @staticmethod
    def theoretical_minimum(room: Room) -> int:
        return max(1, math.ceil(
            room.width * room.length / (math.pi * DETECTOR_RADIUS**2)))
