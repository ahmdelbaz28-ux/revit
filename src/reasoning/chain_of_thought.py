"""
reasoning/chain_of_thought.py
=============================
Explicit multi-step reasoning planner.

The classifier/compliance engine can be "tactically intelligent" — answer
single questions well — but real fire safety review needs *strategic*
reasoning: gather evidence, weigh it, decide, justify.

This module implements a small planner that:
  1. Takes a high-level question ("Is this floor compliant for fire alarm?")
  2. Decomposes into atomic sub-questions
  3. Calls the right tool for each (compliance engine, twin sim, ADA check…)
  4. Combines the evidence into a structured answer with citations

It's deterministic and inspectable — every step is logged with input/output
so a reviewer can audit how the conclusion was reached.
"""
from __future__ import annotations
import logging
from dataclasses import dataclass, field
from typing import Callable, Any

log = logging.getLogger(__name__)


@dataclass
class ReasoningStep:
    step:        int
    description: str
    tool:        str
    input:       Any
    output:      Any
    confidence:  float = 1.0
    notes:       str = ""


@dataclass
class ReasoningTrace:
    question:    str
    conclusion:  str
    confidence:  float
    severity:    str               # 'pass' | 'fail' | 'review_required'
    steps:       list = field(default_factory=list)
    evidence:    list = field(default_factory=list)
    recommendations: list = field(default_factory=list)


# ──────────────────────────────────────────────────────────────────────────
class FireSafetyReasoner:
    """High-level planner for fire-safety questions."""

    def __init__(self, kb, classifier, twin=None):
        self.kb = kb
        self.classifier = classifier
        self.twin = twin

    # ── Top-level templates ────────────────────────────────────────────
    def evaluate_floor(self, report, units_to_m: float = 0.001) -> ReasoningTrace:
        """Strategic question: is THIS floor fire-alarm compliant?"""
        from ..reasoning.compliance import ComplianceEngine
        from ..reasoning.spatial    import pairwise_min_distance
        from collections import defaultdict

        trace = ReasoningTrace(
            question="Is this floor compliant with NFPA 72 fire alarm requirements?",
            conclusion="", confidence=1.0, severity="review_required")
        eng = ComplianceEngine(self.kb, units_to_m=units_to_m)

        # Step 1: enumerate devices we trust
        positions = defaultdict(list)
        for el in report.elements:
            if el["classification"]["confidence"] < 0.6: continue
            sym = el["classification"]["symbol"]
            cx = (el["bbox"][0]+el["bbox"][2])/2
            cy = (el["bbox"][1]+el["bbox"][3])/2
            positions[sym].append((cx, cy))
        trace.steps.append(ReasoningStep(
            1, "Enumerate confidently-classified devices", "classifier",
            input={"min_conf": 0.6},
            output={k: len(v) for k,v in positions.items()},
        ))

        # Step 2: smoke detector spacing
        smoke = positions.get("smoke_detector", [])
        if smoke:
            f1 = eng.check_detector_spacing("smoke_detector", smoke)
            trace.steps.append(ReasoningStep(
                2, "Verify smoke detector max spacing (NFPA 72)", "compliance_engine",
                input={"count": len(smoke)},
                output={"findings": [x.__dict__ for x in f1]}))
            trace.evidence.extend(x.__dict__ for x in f1)
        else:
            trace.steps.append(ReasoningStep(
                2, "Smoke detector check skipped — no smoke detectors found",
                "compliance_engine", input={}, output={}))
            trace.evidence.append({
                "severity":"critical","rule":"smoke_detector.coverage",
                "message":"No smoke detectors detected on floor.",
                "citation":"NFPA 72 §17.6"})

        # Step 3: sprinkler check
        spr = positions.get("sprinkler_pendant", []) + positions.get("sprinkler_upright", [])
        if spr:
            f2 = eng.check_sprinkler_spacing(spr)
            trace.steps.append(ReasoningStep(
                3, "Verify sprinkler max spacing (NFPA 13)", "compliance_engine",
                input={"count": len(spr)}, output={"findings": [x.__dict__ for x in f2]}))
            trace.evidence.extend(x.__dict__ for x in f2)

        # Step 4: schedule reconciliation
        if report.reconciliation:
            mismatches = [r for r in report.reconciliation if r["status"] not in ("match",)]
            trace.steps.append(ReasoningStep(
                4, "Cross-check schedule (BoQ) against drawing count",
                "schedule_match",
                input={"items": len(report.reconciliation)},
                output={"mismatches": len(mismatches)}))
            if mismatches:
                trace.evidence.append({
                    "severity":"major","rule":"schedule.match",
                    "message":f"{len(mismatches)} item(s) don't match BoQ",
                    "citation":"project documentation"})

        # Step 5: smoke pre-screening (if twin available)
        if self.twin:
            for rid, room in self.twin.rooms.items():
                if room.use in ("corridor","exit","outside"): continue
                # V8: smoke_sim disabled - placeholder for future v8_core integration
                trace.steps.append(ReasoningStep(
                    5, f"Smoke pre-screening estimate for {rid}",
                    "smoke_estimator",
                    input={"room": rid, "volume_m3": room.area_m2 * room.ceiling_height_m},
                    output={"placeholder": "use v8_core.smoke_estimator for estimates"}))

        # ── Aggregate verdict ───────────────────────────────────────────
        severities = {e["severity"] for e in trace.evidence}
        if "critical" in severities:
            trace.severity = "fail"; trace.confidence = 0.95
            trace.conclusion = ("FAIL — Critical fire-alarm compliance issues "
                                "detected. Cannot be issued without remediation.")
        elif "major" in severities:
            trace.severity = "fail"; trace.confidence = 0.9
            trace.conclusion = "FAIL — Major issues require redesign of affected zones."
        elif not trace.evidence:
            trace.severity = "review_required"; trace.confidence = 0.6
            trace.conclusion = ("No critical issues automatically detected, but "
                                "professional engineer review is still mandatory.")
        else:
            trace.severity = "pass"; trace.confidence = 0.8
            trace.conclusion = ("PASS (with minor advisories) — subject to "
                                "professional engineer verification.")

        # Generate recommendations
        for e in trace.evidence:
            if e.get("recommendation"):
                trace.recommendations.append(e["recommendation"])
        return trace
