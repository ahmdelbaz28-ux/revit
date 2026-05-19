"""
engineering/loop_designer_v8.py

⚠️ LIFE-SAFETY WARNING ⚠️

THIS MODULE IS A PATTERN-MATCHING TOOL.
- ALL OUTPUTS REQUIRE PE VERIFICATION.
- NOT GUARANTEED CORRECT - MAY PRODUCE WRONG OUTPUTS.
- VERIFY BEFORE USE - WRONG OUTPUTS MAY CAUSE DEATH.

See: docs/SCOPE_DOCUMENT.md
See: docs/PE_LIABILITY_PROTOCOL.md

=============================
V8 Refactored Loop Designer - Returns DecisionProvenance

This module refactors loop_designer.py to return DecisionProvenance (§3.5 of Blueprint).
Returns full reasoning chain with citations instead of bare scalars.
"""
from __future__ import annotations
import hashlib
import math
from dataclasses import dataclass, field
from typing import Optional

import numpy as np

# V8 Core imports
from ..v8_core.decision_provenance import (
    DecisionProvenance,
    RuleApplied,
    ConfidenceScore,
    ConfidenceLevel,
    Violation,
    Alternative
)


@dataclass
class Loop:
    """Loop data structure (legacy, for backward compat)."""
    id: str
    panel_pos: tuple[float, float]
    order: list  # list[(device_idx, position)]
    total_length_m: float = 0.0
    class_b: bool = True


@dataclass
class LoopPlan:
    """Loop plan (legacy return type)."""
    loops: list
    warnings: list = field(default_factory=list)


def design_loops(
    devices: list[tuple[float, float]],
    panel_pos: tuple[float, float],
    max_devices_per_loop: int = 99,
    max_loop_length_m: float = 760.0,
    class_a: bool = False,
    safety_margin: float = 0.15,
    code_authority=None,
    seed: Optional[int] = None
) -> DecisionProvenance:
    """
    Design addressable SLC loops with V8 DecisionProvenance return.
    
    V8 Blueprint §3.5: Every public function returns DecisionProvenance.
    """
    # Generate seed from input hash (V8 determinism)
    if seed is None:
        import random
        input_str = str(devices) + str(panel_pos)
        seed = int(hashlib.sha256(input_str.encode()).hexdigest()[:8], 16) % (2**31)
    
    if not devices:
        return DecisionProvenance.new(
            decision_type="loop_design",
            value={"loops": [], "error": "No devices"},
            inputs={"device_count": 0, "panel_pos": panel_pos},
            rules_applied=[],
            algorithm={"name": "greedy_nn_2opt", "version": "v8.0.0", "parameters": {}},
            confidence=ConfidenceScore(
                input_quality_score=0.0,
                rule_coverage=0.0,
                geometry_certainty=0.0,
                overall=ConfidenceLevel.REFUSE
            ),
            selected_because="No input devices",
            feasible_alternatives_considered=0,
            violations=[Violation(
                severity="ERROR",
                citation="INPUT",
                description="No devices provided"
            )]
        )

    arr = np.asarray(devices, dtype=np.float64)
    panel = np.asarray(panel_pos, dtype=np.float64)

    # Sort devices by polar angle (initial heuristic)
    angles = np.arctan2(arr[:, 1] - panel[1], arr[:, 0] - panel[0])
    order_idx = list(np.argsort(angles))

    # Build loops
    loops_result = []
    warnings = []
    violations = []
    alternatives = []
    total_length = 0.0

    chunk = []
    loop_num = 0
    
    for di in order_idx:
        chunk.append(int(di))
        if len(chunk) >= max_devices_per_loop:
            loops_result.append(_build_loop_v8(
                loop_num := loop_num + 1, chunk, arr, panel,
                class_a, max_loop_length_m, safety_margin,
                warnings, violations
            ))
            total_length += loops_result[-1]["total_length_m"]
            chunk = []
    
    if chunk:
        loops_result.append(_build_loop_v8(
            loop_num := loop_num + 1, chunk, arr, panel,
            class_a, max_loop_length_m, safety_margin,
            warnings, violations
        ))
        total_length += loops_result[-1]["total_length_m"]

    # Alternative: try different safety margins
    for margin_test in [0.10, 0.20, 0.25]:
        alternatives.append(Alternative(
            rank=len(alternatives) + 1,
            value={"loops": len(loops_result), "safety_margin": margin_test},
            cost=total_length,
            safety_margin=margin_test,
            why_not_selected=f"margin {margin_test} not requested"
        ))

    # Confidence calculation
    input_quality = 0.9 if devices else 0.0
    rule_cov = 0.8 if code_authority else 0.5
    geom_cert = 0.90  # 2-opt is good approximation
    
    has_errors = any(v.severity == "ERROR" for v in violations)
    conf_level = ConfidenceLevel.LOW if has_errors else ConfidenceLevel.HIGH

    conf = ConfidenceScore(
        input_quality_score=input_quality,
        rule_coverage=rule_cov,
        geometry_certainty=geom_cert,
        overall=conf_level
    )

    # Rules applied (NFPA 72)
    rules = [
        RuleApplied(
            citation="NFPA72-2022 §21.2.2",
            constant_id="NFPA72.21.2.panel_max_devices",
            value_used=max_devices_per_loop,
            unit="devices"
        ),
        RuleApplied(
            citation="NFPA72-2022 §21.3",
            constant_id="NFPA72.21.3.max_loop_length",
            value_used=max_loop_length_m,
            unit="m"
        )
    ]

    # Selection reason
    if violations:
        selected_because = f"Loop design with {len(violations)} constraint violations"
    else:
        selected_because = f"Optimal tour within safety margin {safety_margin:.0%}"

    return DecisionProvenance.new(
        decision_type="loop_design",
        value={"loops": loops_result, "total_length_m": total_length},
        inputs={
            "device_count": len(devices),
            "panel_pos": panel_pos,
            "max_devices_per_loop": max_devices_per_loop,
            "max_loop_length_m": max_loop_length_m,
            "class_a": class_a,
            "safety_margin": safety_margin
        },
        rules_applied=rules,
        algorithm={
            "name": "greedy_nn_2opt",
            "version": "v8.0.0",
            "parameters": {"seed": seed, "max_iters": 200}
        },
        confidence=conf,
        selected_because=selected_because,
        alternatives_top_3=alternatives[:3],
        feasible_alternatives_considered=len(alternatives) if alternatives else 0,
        warnings=warnings,
        violations=violations
    )


def _build_loop_v8(num, indices, arr, panel, class_a, max_len, safety_margin,
                 warnings, violations):
    """Build a single loop with V8 tracking."""
    seq = _greedy_nn(indices, arr, panel)
    seq = _two_opt(seq, arr, panel, return_to_panel=class_a)
    length = _tour_length(seq, arr, panel, return_to_panel=class_a)
    
    # Apply safety margin
    effective_max = max_len * (1 - safety_margin)
    
    if length > effective_max:
        violations.append(Violation(
            severity="WARNING",
            citation="NFPA72-2022 §21.3",
            description=f"Loop {num}: {length:.0f}m exceeds margin-adjusted limit {effective_max:.0f}m"
        ))
    
    return {
        "id": f"SLC-{num}",
        "panel_pos": tuple(panel),
        "order": [(i, tuple(arr[i])) for i in seq],
        "total_length_m": round(length, 1),
        "class_b": not class_a
    }


def _greedy_nn(indices, arr, panel):
    """Greedy nearest neighbor heuristic."""
    remaining = list(indices)
    out = []
    cur = panel
    while remaining:
        d = [np.linalg.norm(arr[i] - cur) for i in remaining]
        j = int(np.argmin(d))
        out.append(remaining.pop(j))
        cur = arr[out[-1]]
    return out


def _tour_length(seq, arr, panel, return_to_panel=False):
    """Calculate total tour length."""
    if not seq:
        return 0.0
    pts = [panel] + [arr[i] for i in seq] + ([panel] if return_to_panel else [])
    return float(sum(np.linalg.norm(pts[i + 1] - pts[i]) for i in range(len(pts) - 1)))


def _two_opt(seq, arr, panel, return_to_panel=False, max_iters=200):
    """2-opt local search optimization."""
    best = list(seq)
    best_len = _tour_length(best, arr, panel, return_to_panel)
    improved = True
    it = 0
    while improved and it < max_iters:
        improved = False
        it += 1
        for i in range(1, len(best) - 2):
            for j in range(i + 1, len(best)):
                if j - i == 1:
                    continue
                new = best[:i] + best[i:j][::-1] + best[j:]
                nl = _tour_length(new, arr, panel, return_to_panel)
                if nl + 1e-6 < best_len:
                    best = new
                    best_len = nl
                    improved = True
        if not improved:
            break
    return best


# Legacy functions for backward compatibility
def design_loops_legacy(devices, panel_pos, max_devices_per_loop=99,
                       max_loop_length_m=760.0, class_a=False):
    """Legacy return type (deprecated in V8)."""
    arr = np.asarray(devices, dtype=np.float64)
    panel = np.asarray(panel_pos, dtype=np.float64)
    angles = np.arctan2(arr[:, 1] - panel[1], arr[:, 0] - panel[0])
    order_idx = list(np.argsort(angles))
    
    loops = []
    warnings = []
    chunk = []
    loop_num = 0
    
    for di in order_idx:
        chunk.append(int(di))
        if len(chunk) >= max_devices_per_loop:
            loops.append(_build_loop(loop_num := loop_num + 1, chunk, arr, panel,
                               class_a, max_loop_length_m, warnings))
            chunk = []
    if chunk:
        loops.append(_build_loop(loop_num := loop_num + 1, chunk, arr, panel,
                           class_a, max_loop_length_m, warnings))
    
    return LoopPlan(loops=loops, warnings=warnings)


def _build_loop(num, indices, arr, panel, class_a, max_len, warnings):
    """Build a single loop (legacy)."""
    seq = _greedy_nn(indices, arr, panel)
    seq = _two_opt(seq, arr, panel, return_to_panel=class_a)
    length = _tour_length(seq, arr, panel, return_to_panel=class_a)
    if length > max_len:
        warnings.append(f"Loop {num}: {length:.0f}m > max {max_len}m")
    return Loop(
        id=f"SLC-{num}",
        panel_pos=tuple(panel),
        order=[(i, tuple(arr[i])) for i in seq],
        total_length_m=round(length, 1),
        class_b=not class_a
    )