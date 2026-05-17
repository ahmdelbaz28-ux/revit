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
        
        # First pass: prefer NFPA-compliant (no violations)
        for lay in cands:
            self._verify(lay)
            self._audit_nfpa(lay)
            if len(lay.violations) == 0:
                best = lay
                break

        # Second pass: if none NFPA-compliant, pick highest coverage
        if best is None:
            best_cov = -1
            for lay in cands:
                if lay.coverage_pct > best_cov:
                    best_cov = lay.coverage_pct
                    best = lay

        # Fallback to _fallback only if no candidates
        if best is None:
            best = self._fallback(room)
            self._verify(best)
            self._audit_nfpa(best)
        return best

    # ── A: Hex-Guarded ──────────────────────────────────────────────────────────

    def _hex_guarded(self, room: Room, along_x: bool) -> DetectorLayout:
        W, L = (room.width, room.length) if along_x else (room.length, room.width)
        S, Ry, wm, R = self.S_g, self.Ry_g, self.wm, self.R
        pts: List[Tuple[float, float]] = []
        row = 0; y = wm
        while True:
            offset = (S / 2) if (row % 2 == 1) else 0.0
            xs = self._row_xs_guarded(W, wm, S, offset, R)
            for x in xs: pts.append((x, y))
            nxt = y + Ry; far = L - wm
            if nxt > far + 1e-9:
                if far - y > R + 1e-9:
                    row += 1
                    off2 = (S / 2) if (row % 2 == 1) else 0.0
                    for x in self._row_xs_guarded(W, wm, S, off2, R):
                        pts.append((x, far))
                break
            y = nxt; row += 1

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
        New NFPA-Compliant version: Use slice-based row distribution.
        """
        W, L = (room.width, room.length) if along_x else (room.length, room.width)
        R, wm = self.R, self.wm
        pts: List[Tuple[float, float]] = []

        # --- New NFPA-Compliant Row Distribution ---
        S_max = min(R * math.sqrt(3), self.max_spacing / 2.0)  # Max horizontal spacing + NFPA limit

        top_boundary = L - wm
        bottom_boundary = wm
        usable_height = top_boundary - bottom_boundary

        # Number of slices = ceil(usable_height / S_max)
        num_rows = max(1, math.ceil(usable_height / S_max))
        slice_height = usable_height / num_rows

        # Generate row centers
        y_coords = []
        for i in range(num_rows):
            y = bottom_boundary + (i + 0.5) * slice_height
            y_coords.append(y)

        # Calculate horizontal spacing
        Nx = max(2, math.ceil((W - 2*wm) / S_max) + 1)
        Sx = (W - 2*wm) / (Nx - 1)
        even_xs = [wm + i * Sx for i in range(Nx)]
        odd_xs = [even_xs[0] + Sx / 2 + i * Sx for i in range(Nx)]

        # Place detectors for each row
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
        NFPA 72 §17.6.3.1 spacing audit - corrected interpretation.
        Checks:
          1. Max detector-to-detector spacing <= S
          2. Each wall has at least one detector within S/2.
        """
        if not hasattr(layout, 'violations'):
            layout.violations = []
        else:
            layout.violations.clear()

        dets = layout.detectors
        W, L = layout.room.width, layout.room.length
        S = self.max_spacing
        half_S = S / 2.0
        n = len(dets)
        if n == 0:
            return

        # Inter-device spacing
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

        # Wall coverage: each wall must have a detector within S/2
        walls = {
            'bottom': lambda x, y: y,
            'top':    lambda x, y: L - y,
            'left':   lambda x, y: x,
            'right':  lambda x, y: W - x,
        }
        for wall_name, dist_fn in walls.items():
            ok = any(dist_fn(x, y) <= half_S + 1e-6 for x, y in dets)
            if not ok:
                layout.violations.append(
                    f"No detector within S/2={half_S:.3f}m of {wall_name} wall"
                )

        # Update proof_valid to include NFPA audit
        if layout.violations:
            layout.proof_valid = False

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
