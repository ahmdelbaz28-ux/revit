"""
engineering/panel_optimizer.py
==============================
Optimal placement of fire alarm control panels (FACPs) / power supplies.

Problem: given N devices to serve and a budget of K panels, place the panels
to minimize total cable run while obeying:
  - max devices per panel (loop capacity)
  - max cable length per device (voltage drop limit)
  - panel must be accessible from a corridor / public space (room.use)

Algorithm: weighted k-median (Lloyd-style):
  1. Initialize K panel positions by k-means++.
  2. Repeat:
        - Assign each device to nearest panel.
        - Move each panel to the WEIGHTED MEDIAN of its assigned devices
          (medoid in graph-distance space if walls provided).
  3. Stop when assignments stable.

Returns the panels + per-panel load + total cable estimate + warnings if
a constraint is violated.
"""
from __future__ import annotations
import math, random
from dataclasses import dataclass, field
import numpy as np


@dataclass
class Panel:
    id: str
    position: tuple[float, float]
    devices: list = field(default_factory=list)
    total_cable_m: float = 0.0
    max_single_run_m: float = 0.0
    @property
    def device_count(self): return len(self.devices)


@dataclass
class PanelPlan:
    panels: list
    unassigned: list = field(default_factory=list)
    warnings: list = field(default_factory=list)
    total_cable_m: float = 0.0


def optimize_panels(device_positions: list[tuple[float,float]],
                    k: int = 1,
                    max_devices_per_panel: int = 99,
                    max_single_run_m: float = 1000.0,
                    candidate_positions: list[tuple[float,float]] | None = None,
                    iterations: int = 50,
                    seed: int = 42) -> PanelPlan:
    """If `candidate_positions` is provided, panels can only sit there
    (e.g., corridors / utility rooms). Otherwise free placement."""
    rng = random.Random(seed)
    if not device_positions:
        return PanelPlan([], warnings=["No devices to serve."])

    pts = np.asarray(device_positions, dtype=np.float64)
    k = max(1, min(k, len(pts)))

    # k-means++ init
    centers = [pts[rng.randrange(len(pts))]]
    for _ in range(k-1):
        d2 = np.array([min(np.sum((p-c)**2) for c in centers) for p in pts])
        probs = d2 / d2.sum()
        idx = rng.choices(range(len(pts)), weights=probs)[0]
        centers.append(pts[idx])
    centers = np.array(centers)

    # constrain to candidates if given
    if candidate_positions:
        cand = np.asarray(candidate_positions, dtype=np.float64)
        centers = np.array([cand[np.argmin(np.linalg.norm(cand-c, axis=1))]
                            for c in centers])

    assign = np.zeros(len(pts), int)
    for _ in range(iterations):
        # assign each device to nearest panel
        new_assign = np.argmin(
            np.linalg.norm(pts[:,None,:] - centers[None,:,:], axis=2), axis=1)
        if np.array_equal(new_assign, assign): break
        assign = new_assign
        # update each center to weighted median of its cluster
        for i in range(k):
            members = pts[assign == i]
            if len(members) == 0: continue
            new_c = np.median(members, axis=0)
            if candidate_positions:
                cand = np.asarray(candidate_positions, dtype=np.float64)
                new_c = cand[np.argmin(np.linalg.norm(cand-new_c, axis=1))]
            centers[i] = new_c

    # Build PanelPlan
    panels = []
    warnings = []
    total = 0.0
    for i in range(k):
        members_idx = np.where(assign == i)[0].tolist()
        if not members_idx: continue
        ms = pts[members_idx]
        dists = np.linalg.norm(ms - centers[i], axis=1).tolist()
        load = float(sum(dists))
        worst = float(max(dists))
        total += load
        p = Panel(id=f"FACP-{i+1}", position=tuple(centers[i]),
                  devices=[(int(j), tuple(pts[j]), float(dists[k]))
                           for k,j in enumerate(members_idx)],
                  total_cable_m=load, max_single_run_m=worst)
        if len(members_idx) > max_devices_per_panel:
            warnings.append(f"{p.id} serves {len(members_idx)} devices "
                            f"> max {max_devices_per_panel} — split required.")
        if worst > max_single_run_m:
            warnings.append(f"{p.id} longest run {worst:.0f} m "
                            f"> {max_single_run_m} m (voltage-drop risk).")
        panels.append(p)
    return PanelPlan(panels=panels, warnings=warnings, total_cable_m=total)


def recommend_panel_count(device_positions, max_devices_per_panel: int = 99,
                          max_single_run_m: float = 500.0) -> int:
    """Suggest a starting K based on simple bounds."""
    n = len(device_positions)
    k_by_capacity = math.ceil(n / max_devices_per_panel)
    # try k=1; if violates run-length, increment
    for k in range(max(1,k_by_capacity), n+1):
        plan = optimize_panels(device_positions, k=k,
                               max_devices_per_panel=max_devices_per_panel,
                               max_single_run_m=max_single_run_m,
                               iterations=20)
        if not plan.warnings: return k
    return k_by_capacity
