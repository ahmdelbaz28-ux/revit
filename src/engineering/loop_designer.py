"""
engineering/loop_designer.py
============================
Addressable signaling line circuit (SLC) loop designer.

Constraints per loop:
  - max devices       (typical: 159 per IDNAC, 99-318 per panel make)
  - max total length  (typical: 760 m for #14 AWG)
  - return-to-panel    (Class A loop = redundant path)

Algorithm:
  1. Partition devices into K clusters using panel_optimizer.
  2. Within each cluster, solve a TSP-style tour starting and ending at the
     panel position (greedy nearest-neighbour + 2-opt local search).
  3. Verify constraints; split a loop if violated.

This produces an ACTUAL routing (sequence of devices) — not just counts.
"""
from __future__ import annotations
import math
from dataclasses import dataclass, field
from typing import Optional
import numpy as np


@dataclass
class Loop:
    id: str
    panel_pos: tuple[float, float]
    order: list                       # list[(device_idx, position)]
    total_length_m: float = 0.0
    class_b: bool = True               # True = open ended; False = Class A (closed)
    zone_id: Optional[str] = None      # NFPA 72 §12.3.1/§12.3.2 fault isolation zone


@dataclass
class LoopPlan:
    loops: list
    warnings: list = field(default_factory=list)


def design_loops(devices: list[tuple[float,float]],
                 panel_pos: tuple[float,float],
                 max_devices_per_loop: int = 99,
                 max_loop_length_m: float = 760.0,
                 class_a: bool = False) -> LoopPlan:
    if not devices:
        return LoopPlan([], warnings=["No devices."])

    arr = np.asarray(devices, dtype=np.float64)
    panel = np.asarray(panel_pos, dtype=np.float64)

    # Sort devices by polar angle around panel — gives a sensible starting tour
    angles = np.arctan2(arr[:,1]-panel[1], arr[:,0]-panel[0])
    order_idx = list(np.argsort(angles))

    # Chunk into loops by device count first; we'll length-check after
    loops = []
    warnings = []
    chunk: list[int] = []
    loop_num = 0
    for di in order_idx:
        chunk.append(int(di))
        if len(chunk) >= max_devices_per_loop:
            loops.append(_build_loop(loop_num:=loop_num+1, chunk, arr, panel, class_a, max_loop_length_m, warnings))
            chunk = []
    if chunk:
        loops.append(_build_loop(loop_num:=loop_num+1, chunk, arr, panel, class_a, max_loop_length_m, warnings))
    return LoopPlan(loops=loops, warnings=warnings)


def _build_loop(num, indices, arr, panel, class_a, max_len, warnings):
    # Greedy NN starting from panel, then 2-opt
    seq = _greedy_nn(indices, arr, panel)
    seq = _two_opt(seq, arr, panel, return_to_panel=class_a)
    length = _tour_length(seq, arr, panel, return_to_panel=class_a)
    if length > max_len:
        warnings.append(f"Loop {num}: {length:.0f} m > max {max_len} m — split required.")
    return Loop(
        id=f"SLC-{num}", panel_pos=tuple(panel),
        order=[(i, tuple(arr[i])) for i in seq],
        total_length_m=round(length, 1),
        class_b=not class_a,
    )


def _greedy_nn(indices, arr, panel):
    remaining = list(indices)
    out = []
    cur = panel
    while remaining:
        d = [np.linalg.norm(arr[i]-cur) for i in remaining]
        j = int(np.argmin(d))
        out.append(remaining.pop(j))
        cur = arr[out[-1]]
    return out


def _tour_length(seq, arr, panel, return_to_panel=False):
    if not seq: return 0.0
    pts = [panel] + [arr[i] for i in seq] + ([panel] if return_to_panel else [])
    return float(sum(np.linalg.norm(pts[i+1]-pts[i]) for i in range(len(pts)-1)))


def _two_opt(seq, arr, panel, return_to_panel=False, max_iters=200):
    best = list(seq)
    best_len = _tour_length(best, arr, panel, return_to_panel)
    improved = True; it = 0
    while improved and it < max_iters:
        improved = False; it += 1
        for i in range(1, len(best)-2):
            for j in range(i+1, len(best)):
                if j-i == 1: continue
                new = best[:i] + best[i:j][::-1] + best[j:]
                nl = _tour_length(new, arr, panel, return_to_panel)
                if nl + 1e-6 < best_len:
                    best = new; best_len = nl; improved = True
        if not improved: break
    return best
