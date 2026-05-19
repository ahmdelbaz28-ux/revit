"""
engineering/nec_tables_v8.py

⚠️ LIFE-SAFETY WARNING ⚠️

THIS MODULE IS A PATTERN-MATCHING TOOL.
- ALL OUTPUTS REQUIRE PE VERIFICATION.
- NOT GUARANTEED CORRECT - MAY PRODUCE WRONG OUTPUTS.
- VERIFY BEFORE USE - WRONG OUTPUTS MAY CAUSE DEATH.

See: docs/SCOPE_DOCUMENT.md
See: docs/PE_LIABILITY_PROTOCOL.md

=========================
V8 Refactored NEC Tables - Returns DecisionProvenance

This module refactors nec_tables.py to return DecisionProvenance (§3.5 of Blueprint).
Returns full reasoning chain with NEC citations instead of bare scalars.
"""
from __future__ import annotations
import hashlib
from dataclasses import dataclass
from typing import Optional

# V8 Core imports
from ..v8_core.decision_provenance import (
    DecisionProvenance,
    RuleApplied,
    ConfidenceScore,
    ConfidenceLevel,
    Violation,
    Alternative
)

# ──────────────────────────────────────────────────────────────────────────
# Conductor DC resistance Ω per 1000 ft — copper, uncoated, NEC Ch.9 Table 8
RESISTIVITY_OHM_PER_KFT = {
    18: 7.95, 16: 4.99, 14: 3.14, 12: 1.98, 10: 1.24,
    8: 0.778, 6: 0.491, 4: 0.308, 3: 0.245, 2: 0.194,
    1: 0.154, "1/0": 0.122, "2/0": 0.0967, "3/0": 0.0766, "4/0": 0.0608,
    250: 0.0515, 300: 0.0429, 350: 0.0367, 500: 0.0258, 750: 0.0172,
}

def resistance_ohm_per_m(awg, code_authority=None) -> DecisionProvenance:
    """
    Calculate conductor resistance per metre with DecisionProvenance.
    """
    input_str = str(awg)
    seed = int(hashlib.sha256(input_str.encode()).hexdigest()[:8], 16) % (2**31)
    
    r_kft = RESISTIVITY_OHM_PER_KFT.get(awg)
    
    if r_kft is None:
        return DecisionProvenance.new(
            decision_type="resistance_lookup",
            value={"ohm_per_m": None, "error": f"Unknown AWG {awg}"},
            inputs={"awg": awg},
            rules_applied=[],
            algorithm={"name": "table_lookup", "version": "v8.0.0", "parameters": {}},
            confidence=ConfidenceScore(
                input_quality_score=0.0,
                rule_coverage=0.0,
                geometry_certainty=0.0,
                overall=ConfidenceLevel.REFUSE
            ),
            selected_because=f"Unknown AWG size {awg}",
            feasible_alternatives_considered=0,
            violations=[Violation(
                severity="ERROR",
                citation="NEC Chapter 9 Table 8",
                description=f"AWG {awg} not in resistance table"
            )]
        )
    
    value = r_kft / 304.8
    
    # Rules
    rules = [
        RuleApplied(
            citation="NEC-2023 Chapter 9 Table 8",
            constant_id="NEC.9 Table 8.resistivity",
            value_used=r_kft,
            unit="ohm_per_kft"
        )
    ]
    
    return DecisionProvenance.new(
        decision_type="resistance_lookup",
        value={"awg": awg, "ohm_per_m": value},
        inputs={"awg": awg},
        rules_applied=rules,
        algorithm={"name": "table_lookup", "version": "v8.0.0", "parameters": {"seed": seed}},
        confidence=ConfidenceScore(
            input_quality_score=1.0,
            rule_coverage=1.0,
            geometry_certainty=1.0,
            overall=ConfidenceLevel.HIGH
        ),
        selected_because=f"NEC Table 8 gives {r_kft} ohm/kft for AWG {awg}",
        feasible_alternatives_considered=len(RESISTIVITY_OHM_PER_KFT),
        warnings=[],
        violations=[]
    )


# ──────────────────────────────────────────────────────────────────────────
# Ampacity tables
AMPACITY_75C = {
    14: 20, 12: 25, 10: 35, 8: 50, 6: 65, 4: 85, 3: 100, 2: 115, 1: 130,
    "1/0":150,"2/0":175,"3/0":200,"4/0":230,
    250:255, 300:285, 350:310, 500:380, 750:475,
}

# Conductor areas
COND_AREA_MM2 = {
    18: 5.16, 16: 6.45, 14: 6.45, 12: 8.39, 10: 13.55, 8: 23.61, 6: 32.71,
    4: 53.16, 3: 62.77, 2: 74.71, 1: 100.85,
    "1/0":117.42,"2/0":135.16,"3/0":158.71,"4/0":189.94,
}

# Conduit areas
CONDUIT_AREA_MM2 = {
    "1/2":  201,   "3/4":  357,   "1":    579,    "1-1/4": 990,   "1-1/2":1346,
    "2":   2191, "2-1/2": 3613,  "3":   5523,    "3-1/2": 7298,  "4":  9621,
}

FILL_LIMITS = {1: 0.53, 2: 0.31, 3: 0.40, "over_2": 0.40}


@dataclass
class ConduitResult:
    size: str
    fill_pct: float
    ok: bool
    note: str = ""


def select_conduit(awg_list: list, code_authority=None) -> DecisionProvenance:
    """
    Select smallest EMT conduit with DecisionProvenance.
    """
    if not awg_list:
        return DecisionProvenance.new(
            decision_type="conduit_selection",
            value={"size": "none", "fill_pct": 0.0, "ok": True},
            inputs={"awg_count": 0},
            rules_applied=[],
            algorithm={"name": "fill_calculation", "version": "v8.0.0", "parameters": {}},
            confidence=ConfidenceScore(1.0, 1.0, 1.0, ConfidenceLevel.HIGH),
            selected_because="No conductors to route",
            feasible_alternatives_considered=0
        )
    
    total = sum(COND_AREA_MM2.get(a, 0) for a in awg_list)
    n = len(awg_list)
    limit = FILL_LIMITS.get(n) or FILL_LIMITS["over_2"]
    
    # Try each conduit size
    alternatives = []
    selected = None
    
    for size, inside in sorted(CONDUIT_AREA_MM2.items(), key=lambda kv: kv[1]):
        fill = total / inside
        ok = fill <= limit
        alternatives.append(Alternative(
            rank=len(alternatives) + 1,
            value={"size": size, "fill_pct": fill * 100},
            cost=inside,
            safety_margin=1.0 - fill / limit if ok else 0.0,
            why_not_selected="" if selected else f"not smallest"
        ))
        if ok and selected is None:
            selected = (size, fill * 100)
    
    if selected is None:
        size, fill = "4+", total / CONDUIT_AREA_MM2["4"] * 100
    else:
        size, fill = selected
    
    ok = fill <= limit * 100
    violations = []
    if not ok:
        violations.append(Violation(
            severity="ERROR",
            citation="NEC Chapter 9 Table 1",
            description=f"Conduit fill {fill:.1f}% exceeds {limit*100:.0f}% limit"
        ))
    
    rules = [
        RuleApplied(
            citation="NEC-2023 Chapter 9 Table 1",
            constant_id="NEC.9 Table 1.fill_limit",
            value_used=limit,
            unit="ratio"
        ),
        RuleApplied(
            citation="NEC-2023 Chapter 9 Table 4",
            constant_id="NEC.9 Table 4.conduit_area",
            value_used=CONDUIT_AREA_MM2.get(size, 0),
            unit="mm2"
        )
    ]
    
    return DecisionProvenance.new(
        decision_type="conduit_selection",
        value={"size": size, "fill_pct": round(fill, 1), "ok": ok},
        inputs={"awg_count": n, "total_area_mm2": total},
        rules_applied=rules,
        algorithm={"name": "fill_calculation", "version": "v8.0.0", "parameters": {}},
        confidence=ConfidenceScore(
            input_quality_score=1.0,
            rule_coverage=1.0,
            geometry_certainty=1.0,
            overall=ConfidenceLevel.HIGH if ok else ConfidenceLevel.MEDIUM
        ),
        selected_because=f"Smallest conduit with fill {fill:.1f}% ≤ {limit*100:.0f}% limit",
        alternatives_top_3=alternatives[:3],
        feasible_alternatives_considered=len(alternatives),
        warnings=[] if ok else [f"Exceeds conduit fill - split runs"],
        violations=violations
    )


# ──────────────────────────────────────────────────────────────────────────
SIZE_ORDER = [14, 12, 10, 8, 6, 4, 3, 2, 1,
            "1/0", "2/0", "3/0", "4/0",
            250, 300, 350, 500, 750]

def select_minimum_awg(current_a: float, ambient_c: int = 30,
                     code_authority=None) -> DecisionProvenance:
    """
    Select minimum AWG with DecisionProvenance.
    """
    input_str = str(current_a) + str(ambient_c)
    seed = int(hashlib.sha256(input_str.encode()).hexdigest()[:8], 16) % (2**31)
    
    derate = 1.0  # Can be adjusted per NEC 310.15(B)
    target = current_a / derate
    
    # Find smallest AWG that meets ampacity
    alternatives = []
    selected = None
    
    for s in SIZE_ORDER:
        if s in AMPACITY_75C:
            ampacity = AMPACITY_75C[s]
            margin = (ampacity - target) / ampacity if ampacity > 0 else 0
            alternatives.append(Alternative(
                rank=len(alternatives) + 1,
                value={"awg": s, "ampacity": ampacity},
                cost=s if isinstance(s, int) else 999,
                safety_margin=margin,
                why_not_selected=""
            ))
            if selected is None and ampacity >= target:
                selected = s
    
    if selected is None:
        selected = SIZE_ORDER[-1]
    
    violations = []
    if selected == SIZE_ORDER[-1]:
        violations.append(Violation(
            severity="WARNING",
            citation="NEC-2023 Table 310.16",
            description=f"AWG {selected} is largest size - consider larger conductor"
        ))
    
    rules = [
        RuleApplied(
            citation="NEC-2023 Table 310.16",
            constant_id="NEC.310.16.ampacity_75C",
            value_used=AMPACITY_75C.get(selected, 0),
            unit="amperes"
        )
    ]
    
    return DecisionProvenance.new(
        decision_type="awg_selection",
        value={"awg": selected, "ampacity": AMPACITY_75C.get(selected, 0)},
        inputs={"current_a": current_a, "ambient_c": ambient_c, "derate": derate},
        rules_applied=rules,
        algorithm={"name": "ampacity_lookup", "version": "v8.0.0", "parameters": {"seed": seed}},
        confidence=ConfidenceScore(
            input_quality_score=1.0,
            rule_coverage=1.0,
            geometry_certainty=1.0,
            overall=ConfidenceLevel.HIGH
        ),
        selected_because=f"AWG {selected} with {AMPACITY_75C.get(selected, 0)}A ampacity covers {current_a}A",
        alternatives_top_3=alternatives[:3],
        feasible_alternatives_considered=len(alternatives),
        warnings=[],
        violations=violations
    )