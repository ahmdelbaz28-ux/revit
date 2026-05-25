"""
safety_optimizer.py — Layer 2 (constrained) optimization
=========================================================
REPLACES the V7.6 panel_optimizer, which minimized cable length without
a safety floor.

Formulation:
    feasible_set = { s : compliance(s) AND safety_margin(s) >= MARGIN }
    if feasible_set is empty:
        return DecisionProvenance(confidence=REFUSE, violations=[...])
    minimize cost(s) over feasible_set
    return: selected, top-3 by cost, top-3 by safety_margin, |feasible_set|

The optimizer never returns a single "answer" alone — it returns the trade
frontier so the licensed PE can see what was rejected and why.

Determinism: random seed derived from a hash of the input. Same input ->
byte-identical output.
"""

from __future__ import annotations

import hashlib
import random
from dataclasses import dataclass
from itertools import combinations
from typing import Optional

from .code_authority import CodeAuthority
from .decision_provenance import (
    Alternative, ConfidenceLevel, ConfidenceScore,
    DecisionProvenance, RuleApplied, Violation,
)


@dataclass(frozen=True)
class Device:
    id: str
    x: float
    y: float


@dataclass(frozen=True)
class PanelSolution:
    panels: tuple                          # ((x,y), ...)
    total_cable_length: float              # cost proxy
    max_device_to_panel: float             # safety proxy (lower = better)
    safety_margin: float                   # (max_allowed - max_actual) / max_allowed


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _euclidean(a, b) -> float:
    return ((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2) ** 0.5


def _evaluate(panel_positions, devices, max_distance_allowed) -> PanelSolution:
    total = 0.0
    worst = 0.0
    for d in devices:
        best = min(_euclidean((d.x, d.y), p) for p in panel_positions)
        total += best
        worst = max(worst, best)
    safety_margin = (max_distance_allowed - worst) / max_distance_allowed
    return PanelSolution(
        panels=tuple(panel_positions),
        total_cable_length=total,
        max_device_to_panel=worst,
        safety_margin=safety_margin,
    )


def _candidate_positions(devices, grid_step: float):
    """Generate candidate panel positions on a deterministic grid bounded by devices."""
    xs = [d.x for d in devices]
    ys = [d.y for d in devices]
    x_min, x_max = min(xs), max(xs)
    y_min, y_max = min(ys), max(ys)
    # Walk a grid
    cands = []
    x = x_min
    while x <= x_max + 1e-9:
        y = y_min
        while y <= y_max + 1e-9:
            cands.append((round(x, 3), round(y, 3)))
            y += grid_step
        x += grid_step
    return cands


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def optimize_panels_safety_first(
    devices: list[Device],
    k: int,
    *,
    jurisdiction_id: str,
    code_authority: CodeAuthority,
    project_date: Optional[str] = None,
    grid_step: float = 1.0,
    drawing_hash: str = "sha256:unknown",
) -> DecisionProvenance:
    """
    Safety-first constrained k-median panel siting.

    The objective is *cost* (cable length), but only among solutions that:
      (a) keep max device-to-panel distance within the code limit, and
      (b) keep a safety margin >= the configured margin (Code Authority).

    Returns a fully-formed DecisionProvenance — never a bare list of points.
    """
    if not devices:
        raise ValueError("devices must be non-empty")
    if k < 1:
        raise ValueError("k must be >= 1")

    # 1) Resolve the code constants we need (no literals!)
    max_spacing = code_authority.get_constant(
        "NFPA72.17.6.3.1.smoke_max_spacing", jurisdiction_id, project_date,
    )
    margin_const = code_authority.get_constant(
        "NFPA72.internal.safety_margin.default", jurisdiction_id, project_date,
    )
    max_allowed = max_spacing.value_numeric          # used as "max device-to-panel" proxy in V8.0 alpha
    safety_margin_required = margin_const.value_numeric

    rules = [
        RuleApplied(citation=f"NFPA72-{max_spacing.edition} §{max_spacing.section}",
                    constant_id=max_spacing.constant_id,
                    value_used=max_spacing.value_numeric,
                    unit=max_spacing.value_unit),
        RuleApplied(citation=f"FireCalc internal — {margin_const.section}",
                    constant_id=margin_const.constant_id,
                    value_used=margin_const.value_numeric,
                    unit=margin_const.value_unit),
    ]

    # 2) Build deterministic candidates
    seed_material = hashlib.sha256(
        repr(sorted((d.id, d.x, d.y) for d in devices)).encode() +
        f"|k={k}|grid={grid_step}|max={max_allowed}".encode()
    ).hexdigest()
    rng = random.Random(int(seed_material[:16], 16))
    candidates = _candidate_positions(devices, grid_step)

    # 3) Enumerate combinations (small k only — for large k swap in clustering)
    if len(candidates) > 60 and k > 1:
        # Sample to keep bounded; deterministic via rng.
        candidates = rng.sample(candidates, 60)

    feasible: list[PanelSolution] = []
    infeasible_seen = 0
    for combo in combinations(candidates, k):
        sol = _evaluate(combo, devices, max_allowed)
        if sol.max_device_to_panel <= max_allowed and sol.safety_margin >= safety_margin_required:
            feasible.append(sol)
        else:
            infeasible_seen += 1

    # 4) Confidence & violation handling
    input_quality = 0.95  # placeholder — real source: parser confidence
    rule_coverage = 1.0
    geom_certainty = 0.9

    if not feasible:
        # REFUSE rather than silently return a non-compliant best-effort.
        confidence = ConfidenceScore(
            input_quality_score=input_quality, rule_coverage=rule_coverage,
            geometry_certainty=geom_certainty, overall=ConfidenceLevel.REFUSE,
        )
        dp = DecisionProvenance.new(
            decision_type="panel_placement",
            value=None,
            inputs={"drawing_hash": drawing_hash,
                    "jurisdiction": jurisdiction_id,
                    "code_versions": {"NFPA72": max_spacing.edition}},
            rules_applied=rules,
            algorithm={"name": "k_median_constrained", "version": "v8.0.0",
                       "parameters": {"k": k, "grid_step": grid_step,
                                      "seed": seed_material[:16]}},
            confidence=confidence,
            selected_because="No feasible solution within safety margin. "
                             "Refuse to emit a non-compliant placement.",
            feasible_alternatives_considered=0,
            violations=[Violation(
                severity="ERROR",
                citation=rules[0].citation,
                description=(f"No panel placement keeps all devices within "
                             f"{max_allowed} {max_spacing.value_unit} with a "
                             f"≥{safety_margin_required*100:.0f}% safety margin. "
                             "Increase number of panels or revise geometry."),
            )],
            warnings=[f"Considered {infeasible_seen} infeasible combinations."],
        )
        dp.validate()
        dp.sign_engine()
        return dp

    # 5) Pick by cost; report top-3 by cost and top-3 by safety
    feasible_by_cost = sorted(feasible, key=lambda s: (s.total_cable_length, s.max_device_to_panel))
    feasible_by_safety = sorted(feasible, key=lambda s: (-s.safety_margin, s.total_cable_length))
    selected = feasible_by_cost[0]

    alts: list[Alternative] = []
    seen_panels = {selected.panels}
    rank = 1
    for s in feasible_by_cost[1:4]:
        if s.panels in seen_panels:
            continue
        rank += 1
        alts.append(Alternative(
            rank=rank, value={"panels": list(s.panels)},
            cost=s.total_cable_length,
            safety_margin=s.safety_margin,
            why_not_selected=(
                f"Higher cost ({s.total_cable_length:.2f} vs "
                f"{selected.total_cable_length:.2f}); same compliance class."),
        ))
        seen_panels.add(s.panels)
    # Add the safety-first alternative if it differs
    if feasible_by_safety[0].panels != selected.panels:
        s = feasible_by_safety[0]
        alts.append(Alternative(
            rank=99, value={"panels": list(s.panels)},
            cost=s.total_cable_length,
            safety_margin=s.safety_margin,
            why_not_selected=("Safer (margin "
                              f"{s.safety_margin*100:.1f}% vs "
                              f"{selected.safety_margin*100:.1f}%) but higher cost."),
        ))

    overall = (ConfidenceLevel.HIGH if selected.safety_margin >= 0.25
               else ConfidenceLevel.MEDIUM)
    confidence = ConfidenceScore(
        input_quality_score=input_quality, rule_coverage=rule_coverage,
        geometry_certainty=geom_certainty, overall=overall,
    )

    dp = DecisionProvenance.new(
        decision_type="panel_placement",
        value={
            "panels": [list(p) for p in selected.panels],
            "total_cable_length": round(selected.total_cable_length, 3),
            "max_device_to_panel": round(selected.max_device_to_panel, 3),
            "safety_margin": round(selected.safety_margin, 4),
        },
        inputs={"drawing_hash": drawing_hash,
                "jurisdiction": jurisdiction_id,
                "code_versions": {"NFPA72": max_spacing.edition}},
        rules_applied=rules,
        algorithm={"name": "k_median_constrained", "version": "v8.0.0",
                   "parameters": {"k": k, "grid_step": grid_step,
                                  "seed": seed_material[:16]}},
        confidence=confidence,
        selected_because=("Lowest cable length among compliant solutions "
                          "satisfying the configured safety margin. "
                          "PE must review the alternatives before sign-off."),
        feasible_alternatives_considered=len(feasible),
        alternatives_top_3=alts,
        warnings=([] if selected.safety_margin >= 0.25
                  else ["Safety margin is below 25% — PE review strongly recommended."]),
    )
    dp.validate()
    dp.sign_engine()
    return dp


# ---------------------------------------------------------------------------
# Self-test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    from pathlib import Path
    from .code_authority import CodeAuthority, seed_nfpa72_2019_minimum

    db = "/tmp/firecalc_optim_selftest.db"
    Path(db).unlink(missing_ok=True)
    auth = CodeAuthority(db)
    seed_nfpa72_2019_minimum(auth)
    auth.set_jurisdiction("US.GENERIC", "NFPA72", "2019", "2019-01-01")

    # 4 devices in a 6m x 6m square — easily within 9.1m of one panel at center.
    devices = [
        Device("D1", 0.0, 0.0),
        Device("D2", 6.0, 0.0),
        Device("D3", 0.0, 6.0),
        Device("D4", 6.0, 6.0),
    ]
    dp = optimize_panels_safety_first(
        devices, k=1, jurisdiction_id="US.GENERIC",
        code_authority=auth, project_date="2026-01-01",
        grid_step=1.0, drawing_hash="sha256:test",
    )
    assert dp.value is not None, "should have a feasible solution"
    assert dp.confidence.overall in {ConfidenceLevel.HIGH, ConfidenceLevel.MEDIUM}
    print("[safety_optimizer] feasible run PASS — panels:", dp.value["panels"])
    print("                   safety_margin:", dp.value["safety_margin"])
    print("                   feasible alternatives considered:", dp.feasible_alternatives_considered)

    # Stress: devices spread too far for k=1 should REFUSE.
    far = [Device("F1", 0.0, 0.0), Device("F2", 50.0, 0.0)]
    dp2 = optimize_panels_safety_first(
        far, k=1, jurisdiction_id="US.GENERIC",
        code_authority=auth, project_date="2026-01-01",
        grid_step=2.0, drawing_hash="sha256:test_far",
    )
    assert dp2.confidence.overall == ConfidenceLevel.REFUSE
    assert dp2.value is None
    print("[safety_optimizer] infeasible run PASS — refused with violations:",
          len(dp2.violations_detected))
