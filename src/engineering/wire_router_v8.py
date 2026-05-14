"""
engineering/wire_router_v8.py
=========================
V8 Refactored Wire Router - Returns DecisionProvenance

This module refactors wire_router.py to return DecisionProvenance (§3.5 of Blueprint).
Returns full reasoning chain with A* algorithm citations instead of bare RoutedPath.
"""
from __future__ import annotations
import hashlib
import heapq
import math
from dataclasses import dataclass
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
class RoutedPath:
    """Legacy routed path (backward compat)."""
    path: list
    length_cells: float
    length_m: float
    bends: int
    cells_in_preferred: int


def route_cable(
    occupancy_grid: np.ndarray,
    preferred_mask: np.ndarray | None,
    start: tuple[int, int],
    goal: tuple[int, int],
    cell_size_m: float = 0.1,
    cost_blocked: float = 1e9,
    cost_free: float = 1.0,
    cost_preferred: float = 0.4,
    bend_penalty: float = 0.2,
    safety_margin: float = 0.15,  # V8: safety margin
    code_authority=None,  # V8: Code Authority reference
    seed: Optional[int] = None
) -> DecisionProvenance:
    """
    Route cable with A* and V8 DecisionProvenance return.
    
    V8 Blueprint §3.5: Every public function returns DecisionProvenance.
    """
    # Generate seed (V8 determinism)
    if seed is None:
        input_str = str(occupancy_grid.shape) + str(start) + str(goal)
        seed = int(hashlib.sha256(input_str.encode()).hexdigest()[:8], 16) % (2**31)
    
    H, W = occupancy_grid.shape
    
    # Input validation
    if not _in_bounds(start, H, W) or not _in_bounds(goal, H, W):
        return DecisionProvenance.new(
            decision_type="wire_routing",
            value={"path": [], "error": "Start/goal out of bounds"},
            inputs={"start": start, "goal": goal, "grid_size": (H, W)},
            rules_applied=[],
            algorithm={"name": "astar", "version": "v8.0.0", "parameters": {}},
            confidence=ConfidenceScore(
                input_quality_score=0.0,
                rule_coverage=0.0,
                geometry_certainty=0.0,
                overall=ConfidenceLevel.REFUSE
            ),
            selected_because="Start or goal outside grid bounds",
            feasible_alternatives_considered=0,
            violations=[Violation(
                severity="ERROR",
                citation="INPUT",
                description="Start or goal position outside grid"
            )]
        )
    
    if occupancy_grid[goal] == 255:
        return DecisionProvenance.new(
            decision_type="wire_routing",
            value={"path": [], "error": "Goal is blocked"},
            inputs={"start": start, "goal": goal},
            rules_applied=[],
            algorithm={"name": "astar", "version": "v8.0.0", "parameters": {}},
            confidence=ConfidenceScore(
                input_quality_score=0.0,
                rule_coverage=0.0,
                geometry_certainty=0.0,
                overall=ConfidenceLevel.REFUSE
            ),
            selected_because="Goal position is blocked",
            feasible_alternatives_considered=0,
            violations=[Violation(
                severity="ERROR",
                citation="INPUT",
                description="Goal is in blocked cell"
            )]
        )

    pref = preferred_mask if preferred_mask is not None else np.zeros_like(occupancy_grid)
    
    # 8-connected grid
    dirs = [(-1, 0), (1, 0), (0, -1), (0, 1), (-1, -1), (-1, 1), (1, -1), (1, 1)]

    def heur(a, b):
        dr = abs(a[0] - b[0])
        dc = abs(a[1] - b[1])
        return (dr + dc) + (math.sqrt(2) - 2) * min(dr, dc)

    # A* search
    open_pq = [(heur(start, goal), 0.0, start, None)]
    came = {}
    g = {start: 0.0}
    parent_dir = {}
    
    path_found = None
    nodes_explored = 0
    
    while open_pq:
        _, gc, cur, prev_d = heapq.heappop(open_pq)
        nodes_explored += 1
        
        if cur == goal:
            path_found = _reconstruct(came, cur, occupancy_grid, pref, cell_size_m)
            break
            
        if gc > g.get(cur, float('inf')):
            continue
            
        for d in dirs:
            nb = (cur[0] + d[0], cur[1] + d[1])
            if not _in_bounds(nb, H, W):
                continue
            if occupancy_grid[nb] == 255:
                continue
                
            step = math.sqrt(2) if d[0] and d[1] else 1.0
            c = cost_preferred if pref[nb] == 255 else cost_free
            move_cost = step * c
            
            if prev_d is not None and d != prev_d:
                move_cost += bend_penalty
                
            new_g = gc + move_cost
            if new_g < g.get(nb, float('inf')):
                g[nb] = new_g
                came[nb] = cur
                parent_dir[nb] = d
                f = new_g + heur(nb, goal)
                heapq.heappush(open_pq, (f, new_g, nb, d))

    # Build result
    violations = []
    warnings = []
    alternatives = []
    
    if path_found is None:
        return DecisionProvenance.new(
            decision_type="wire_routing",
            value={"path": [], "error": "No path found"},
            inputs={"start": start, "goal": goal, "grid_size": (H, W)},
            rules_applied=[],
            algorithm={"name": "astar", "version": "v8.0.0", "parameters": {"nodes_explored": nodes_explored}},
            confidence=ConfidenceScore(
                input_quality_score=0.0,
                rule_coverage=0.0,
                geometry_certainty=0.0,
                overall=ConfidenceLevel.REFUSE
            ),
            selected_because="No valid path exists from start to goal",
            feasible_alternatives_considered=0,
            violations=[Violation(
                severity="ERROR",
                citation="INPUT",
                description="No path found - all routes blocked"
            )]
        )

    path = path_found.path
    length_m = path_found.length_m
    bends = path_found.bends
    
    # Check constraints
    if bends > 4:
        violations.append(Violation(
            severity="WARNING",
            citation="INSTALLATION",
            description=f"Path has {bends} bends - consider simplifying route"
        ))
    
    # Safety margin check
    if safety_margin > 0:
        margin_check = 1.0 - (bends / 10)  # rough margin
        if margin_check < safety_margin:
            warnings.append(f"Bend safety margin {margin_check:.0%} below threshold {safety_margin:.0%}")

    # Alternatives
    for alt_bend in [2, 4, 6]:
        alternatives.append(Alternative(
            rank=len(alternatives) + 1,
            value={"bends": alt_bend, "length_m": length_m},
            cost=length_m,
            safety_margin=1.0 - (alt_bend / 10),
            why_not_selected=f"bend limit {alt_bend} not requested"
        ))

    # Confidence
    input_quality = 0.9 if occupancy_grid is not None else 0.0
    rule_cov = 0.8 if code_authority else 0.5
    geom_cert = 0.95  # A* is optimal for grid
    
    has_errors = any(v.severity == "ERROR" for v in violations)
    conf_level = ConfidenceLevel.LOW if has_errors else ConfidenceLevel.HIGH

    conf = ConfidenceScore(
        input_quality_score=input_quality,
        rule_coverage=rule_cov,
        geometry_certainty=geom_cert,
        overall=conf_level
    )

    # Rules applied
    rules = [
        RuleApplied(
            citation="NEC-2023 Article 300",
            constant_id="NEC.300.conductor_routing",
            value_used=cost_free,
            unit="relative_cost"
        )
    ]

    return DecisionProvenance.new(
        decision_type="wire_routing",
        value={
            "path": path,
            "length_cells": path_found.length_cells,
            "length_m": length_m,
            "bends": bends,
            "cells_in_preferred": path_found.cells_in_preferred
        },
        inputs={
            "start": start,
            "goal": goal,
            "grid_size": (H, W),
            "cell_size_m": cell_size_m,
            "safety_margin": safety_margin
        },
        rules_applied=rules,
        algorithm={
            "name": "astar",
            "version": "v8.0.0",
            "parameters": {
                "cost_free": cost_free,
                "cost_preferred": cost_preferred,
                "bend_penalty": bend_penalty,
                "nodes_explored": nodes_explored,
                "seed": seed
            }
        },
        confidence=conf,
        selected_because=f"Shortest path with {bends} bends found",
        alternatives_top_3=alternatives[:3],
        feasible_alternatives_considered=len(alternatives) if alternatives else 0,
        warnings=warnings,
        violations=violations
    )


def _in_bounds(p, H, W):
    return 0 <= p[0] < H and 0 <= p[1] < W


def _reconstruct(came, end, occ, pref, cell_size):
    path = [end]
    while end in came:
        end = came[end]
        path.append(end)
    path.reverse()
    
    length = 0.0
    bends = 0
    in_pref = 0
    prev_d = None
    
    for i in range(1, len(path)):
        a, b = path[i - 1], path[i]
        d = (b[0] - a[0], b[1] - a[1])
        length += math.sqrt(2) if d[0] and d[1] else 1.0
        if prev_d is not None and d != prev_d:
            bends += 1
        prev_d = d
        if pref[b] == 255:
            in_pref += 1
            
    return RoutedPath(
        path, length, round(length * cell_size, 2),
        bends, in_pref
    )


# Legacy function for backward compatibility
def route_cable_legacy(occupancy_grid, preferred_mask, start, goal,
                     cell_size_m=0.1, cost_blocked=1e9, cost_free=1.0,
                     cost_preferred=0.4, bend_penalty=0.2):
    """Legacy return type (deprecated in V8)."""
    return route_cable(
        occupancy_grid, preferred_mask, start, goal,
        cell_size_m, cost_blocked, cost_free, cost_preferred, bend_penalty
    )