"""
reasoning/schedule_match.py
===========================
Compare the BOQ / schedule / legend table against what's actually on the drawing.
The classic "الحصر مطابق ولا لأ" problem.

Inputs:
  - schedule:  list of {"item": str, "qty": int, ...}   (parsed from a table)
  - actual:    dict[symbol_name] = count                 (from classified entities)

Output:
  - Reconciliation report with overage / underage / missing / extra
"""
from __future__ import annotations
from dataclasses import dataclass, field
from difflib import get_close_matches


@dataclass
class ScheduleLine:
    item: str
    qty: int
    raw: dict = field(default_factory=dict)


@dataclass
class Reconciliation:
    item: str
    scheduled_qty: int
    actual_qty: int
    delta: int                  # actual - scheduled
    status: str                 # 'match' | 'over' | 'under' | 'missing_on_drawing' | 'not_in_schedule'
    note: str = ""


def normalize_name(name: str) -> str:
    return (name or "").strip().lower().replace("-"," ").replace("_"," ")


def reconcile(schedule: list[ScheduleLine],
              actual_counts: dict[str, int],
              symbol_aliases: dict[str, list[str]] | None = None) -> list[Reconciliation]:
    """
    symbol_aliases: optional map of canonical_name → [alternative names users
                    might write in the schedule]. Allows fuzzy matching.
    """
    symbol_aliases = symbol_aliases or {}
    # Build reverse index: any-alias → canonical
    alias_to_canon = {}
    for canon, aliases in symbol_aliases.items():
        alias_to_canon[normalize_name(canon)] = canon
        for a in aliases: alias_to_canon[normalize_name(a)] = canon
    for sym in actual_counts:  # canonical names themselves
        alias_to_canon.setdefault(normalize_name(sym), sym)

    out: list[Reconciliation] = []
    matched_canon = set()

    for line in schedule:
        key = normalize_name(line.item)
        canon = alias_to_canon.get(key)
        if not canon:
            # fuzzy fallback
            cand = get_close_matches(key, list(alias_to_canon.keys()), n=1, cutoff=0.7)
            canon = alias_to_canon[cand[0]] if cand else None
        if not canon:
            out.append(Reconciliation(line.item, line.qty, 0, -line.qty,
                                      "missing_on_drawing",
                                      "Item in schedule but no matching symbol found."))
            continue
        actual = actual_counts.get(canon, 0)
        delta = actual - line.qty
        status = ("match" if delta == 0
                  else "over" if delta > 0 else "under")
        out.append(Reconciliation(canon, line.qty, actual, delta, status))
        matched_canon.add(canon)

    # Things on drawing but not in schedule
    for sym, qty in actual_counts.items():
        if sym in matched_canon: continue
        out.append(Reconciliation(sym, 0, qty, qty, "not_in_schedule",
                                  "Found on drawing but not listed in BOQ/schedule."))
    return out
