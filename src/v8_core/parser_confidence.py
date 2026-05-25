"""
parser_confidence.py — Input Quality Gate (V8.0)
===================================================
The single most under-discussed risk in V7.6 was: a perfectly engineered
trust stack built on top of a parser that silently mis-reads its input.

This module is the GATE between the parser and every downstream engineering
module. No calculation runs against geometry that has not been scored, gated,
and explicitly accepted.

CONTRACT:
    1. The parser populates a ParserObservations object during parsing.
    2. The gate consumes it and produces a ParserConfidenceReport.
    3. The pipeline runs `gate_input_or_refuse(...)`:
         - PROCEED  -> downstream modules run, confidence is recorded.
         - WARN     -> downstream modules run, but every DecisionProvenance
                       inherits a "low input quality" warning + a forced
                       PE-acknowledgement requirement.
         - REFUSE   -> NO downstream module runs. A DecisionProvenance is
                       emitted carrying the gate report as evidence.

DESIGN NOTES:
    - Cheap checks fire first; expensive checks are short-circuited if the
      cheap ones already fail. Target: <500ms for any input on a clean run.
    - Each signal carries both a numeric value (0..1) AND a human-readable
      raw_observation — because the PE reading the report needs to know
      WHY the score is what it is, not just the number.
    - Hard refuse triggers exist independently of the weighted score.
      Example: scale is not parseable -> REFUSE, even if every other
      signal is 1.0. You cannot calculate distances without a scale.
"""
from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, Optional

from .decision_provenance import (
    ConfidenceLevel, ConfidenceScore, DecisionProvenance,
    RuleApplied, Violation,
)


# ---------------------------------------------------------------------------
# Public types
# ---------------------------------------------------------------------------

class GateDecision(str, Enum):
    PROCEED = "PROCEED"     # input_quality_score >= 0.85
    WARN = "WARN"           # 0.70 <= score < 0.85
    LOW = "LOW"             # 0.50 <= score < 0.70 -> requires explicit PE override
    REFUSE = "REFUSE"       # score < 0.50 OR a hard refuse trigger fired


@dataclass
class ParserObservations:
    """Populated by the parser during PDF/DWG/DXF ingestion.

    Each field is a value in [0,1] plus a free-text raw observation that
    the PE will read in the audit report. The parser is honest: missing
    signals are reported with value=0.0 and a clear reason, not omitted.
    """
    # The eight canonical signals (sum of weights = 1.0)
    legend_coverage:           tuple[float, str] = (0.0, "not measured")
    scale_present:             tuple[float, str] = (0.0, "not measured")
    vector_purity:             tuple[float, str] = (0.0, "not measured")
    polygon_closure:           tuple[float, str] = (0.0, "not measured")
    layer_hygiene:             tuple[float, str] = (0.0, "not measured")
    title_block_completeness:  tuple[float, str] = (0.0, "not measured")
    ocr_confidence:            tuple[float, str] = (0.0, "not measured")
    coordinate_sanity:         tuple[float, str] = (0.0, "not measured")

    # Pathology counts (subtractive penalty, not part of the weighted sum)
    self_intersecting_polygons: int = 0
    zero_area_polygons:         int = 0
    unmatched_symbols:          int = 0
    notes:                      list[str] = field(default_factory=list)


@dataclass
class SignalResult:
    name: str
    weight: float
    value: float
    raw_observation: str
    hard_refuse_fired: bool = False
    hard_refuse_reason: Optional[str] = None


@dataclass
class ParserConfidenceReport:
    file_hash: str
    signals: list[SignalResult]
    pathology_penalty: float
    weighted_score: float          # in [0,1]
    final_score: float             # weighted_score - pathology_penalty, clamped [0,1]
    decision: GateDecision
    decision_reason: str
    hard_refuse_triggers: list[str]
    elapsed_ms: float
    cached: bool = False


# ---------------------------------------------------------------------------
# Configuration (immutable in V8.0; tunable per-jurisdiction in V8.1)
# ---------------------------------------------------------------------------

# Weights sum to 1.0. Top two (legend_coverage + scale_present) carry 45% —
# because if you don't know what the symbols mean AND don't know the scale,
# nothing else matters.
SIGNAL_WEIGHTS: dict[str, float] = {
    "legend_coverage":          0.25,
    "scale_present":            0.20,
    "vector_purity":            0.15,
    "polygon_closure":          0.15,
    "layer_hygiene":            0.10,
    "title_block_completeness": 0.05,
    "ocr_confidence":           0.05,
    "coordinate_sanity":        0.05,
}
assert abs(sum(SIGNAL_WEIGHTS.values()) - 1.0) < 1e-9, "weights must sum to 1.0"

# Hard refuse: irrespective of weighted score, REFUSE if any signal is below.
HARD_REFUSE_THRESHOLDS: dict[str, float] = {
    "scale_present":      0.50,   # can't compute distances
    "coordinate_sanity":  0.30,   # likely unit-error or corrupt geometry
    "legend_coverage":    0.50,   # don't know what >50% of the symbols mean
}

# Pathology penalty: subtract from the weighted score.
PATHOLOGY_PENALTY_PER_ITEM = {
    "self_intersecting_polygons": 0.02,   # up to -0.20 cap below
    "zero_area_polygons":         0.03,
    "unmatched_symbols":          0.01,
}
PATHOLOGY_PENALTY_CAP = 0.20

# Decision thresholds (on FINAL score after pathology penalty)
PROCEED_AT = 0.85
WARN_AT = 0.70
LOW_AT = 0.50
# below LOW_AT => REFUSE

# Cache parser reports by file content hash to avoid recomputation on
# pipeline restart. Bounded LRU.
_CACHE: dict[str, ParserConfidenceReport] = {}
_CACHE_MAX = 256


# ---------------------------------------------------------------------------
# The Assessor
# ---------------------------------------------------------------------------

def assess_input_quality(observations: ParserObservations,
                          file_hash: str) -> ParserConfidenceReport:
    """Compute the input quality report. Pure function of observations + hash."""
    if file_hash in _CACHE:
        cached = _CACHE[file_hash]
        return ParserConfidenceReport(
            file_hash=cached.file_hash, signals=cached.signals,
            pathology_penalty=cached.pathology_penalty,
            weighted_score=cached.weighted_score,
            final_score=cached.final_score, decision=cached.decision,
            decision_reason=cached.decision_reason,
            hard_refuse_triggers=cached.hard_refuse_triggers,
            elapsed_ms=cached.elapsed_ms, cached=True,
        )

    t0 = time.perf_counter()
    signals: list[SignalResult] = []
    hard_triggers: list[str] = []
    weighted = 0.0

    for name, weight in SIGNAL_WEIGHTS.items():
        value, raw = getattr(observations, name)
        # Clamp defensively
        value = max(0.0, min(1.0, float(value)))
        hard_fired = False
        hard_reason = None
        if name in HARD_REFUSE_THRESHOLDS and value < HARD_REFUSE_THRESHOLDS[name]:
            hard_fired = True
            hard_reason = (f"{name}={value:.2f} below hard-refuse threshold "
                           f"{HARD_REFUSE_THRESHOLDS[name]:.2f} — {raw}")
            hard_triggers.append(hard_reason)
        signals.append(SignalResult(
            name=name, weight=weight, value=value, raw_observation=raw,
            hard_refuse_fired=hard_fired, hard_refuse_reason=hard_reason,
        ))
        weighted += weight * value

    # Pathology penalty
    penalty = (
        observations.self_intersecting_polygons * PATHOLOGY_PENALTY_PER_ITEM["self_intersecting_polygons"]
        + observations.zero_area_polygons       * PATHOLOGY_PENALTY_PER_ITEM["zero_area_polygons"]
        + observations.unmatched_symbols        * PATHOLOGY_PENALTY_PER_ITEM["unmatched_symbols"]
    )
    penalty = min(penalty, PATHOLOGY_PENALTY_CAP)
    final = max(0.0, min(1.0, weighted - penalty))

    # Decide
    if hard_triggers:
        decision = GateDecision.REFUSE
        reason = (f"Hard-refuse trigger(s) fired: {len(hard_triggers)}. "
                  f"Final score {final:.2f} would have been "
                  f"{_label_for_score(final)} otherwise.")
    elif final >= PROCEED_AT:
        decision, reason = GateDecision.PROCEED, f"final score {final:.2f} ≥ {PROCEED_AT}"
    elif final >= WARN_AT:
        decision, reason = GateDecision.WARN, f"final score {final:.2f} in [{WARN_AT}, {PROCEED_AT})"
    elif final >= LOW_AT:
        decision, reason = GateDecision.LOW, (
            f"final score {final:.2f} in [{LOW_AT}, {WARN_AT}); "
            "explicit PE override required before any downstream computation."
        )
    else:
        decision, reason = GateDecision.REFUSE, (
            f"final score {final:.2f} < {LOW_AT}; refuse to compute on this input.")

    elapsed_ms = (time.perf_counter() - t0) * 1000.0
    report = ParserConfidenceReport(
        file_hash=file_hash, signals=signals,
        pathology_penalty=round(penalty, 4),
        weighted_score=round(weighted, 4),
        final_score=round(final, 4),
        decision=decision, decision_reason=reason,
        hard_refuse_triggers=hard_triggers,
        elapsed_ms=round(elapsed_ms, 3),
    )

    # Cache (simple FIFO bound)
    if len(_CACHE) >= _CACHE_MAX:
        _CACHE.pop(next(iter(_CACHE)))
    _CACHE[file_hash] = report
    return report


def _label_for_score(s: float) -> str:
    if s >= PROCEED_AT:  return "PROCEED"
    if s >= WARN_AT:     return "WARN"
    if s >= LOW_AT:      return "LOW"
    return "REFUSE"


# ---------------------------------------------------------------------------
# The Gate — called by the pipeline before any engineering module
# ---------------------------------------------------------------------------

def gate_input_or_refuse(report: ParserConfidenceReport,
                         drawing_hash: str,
                         pe_override_token: Optional[str] = None
                         ) -> Optional[DecisionProvenance]:
    """
    Returns:
        None  -> caller may proceed with downstream engineering modules.
        DecisionProvenance(value=None, ...)  -> caller MUST NOT proceed.
            This object is the audit-grade record of the refusal.

    The pe_override_token is consumed only for GateDecision.LOW. It must be
    a signed, time-bound token produced via the Human Authority layer.
    """
    if report.decision == GateDecision.PROCEED:
        return None

    if report.decision == GateDecision.WARN:
        # Proceed, but every downstream DecisionProvenance must inherit
        # the warning. The caller is responsible for propagating it.
        return None  # caller checks report.decision and adds the warning

    if report.decision == GateDecision.LOW and pe_override_token:
        # PE explicitly accepted lower-than-WARN quality.
        # NOTE: validation of the token is done by the human authority
        # layer (layer 4); here we trust that it was already validated.
        return None

    # Otherwise: REFUSE (or LOW without override)
    violations = [Violation(
        severity="ERROR",
        citation="V8.parser_confidence.gate",
        description=(f"Input quality gate refused to proceed. "
                     f"Decision={report.decision.value}. {report.decision_reason}"),
        location=None,
    )]
    if report.hard_refuse_triggers:
        for t in report.hard_refuse_triggers:
            violations.append(Violation(
                severity="ERROR",
                citation="V8.parser_confidence.hard_refuse",
                description=t,
                location=None,
            ))

    conf = ConfidenceScore(
        input_quality_score=report.final_score,
        rule_coverage=1.0,                 # gate logic is fully covered
        geometry_certainty=report.final_score,
        overall=ConfidenceLevel.REFUSE,
    )
    dp = DecisionProvenance.new(
        decision_type="input_quality_gate",
        value=None,
        inputs={"drawing_hash": drawing_hash, "jurisdiction": None,
                "code_versions": {}},
        rules_applied=[RuleApplied(
            citation="V8.parser_confidence",
            constant_id="V8.parser_confidence.gate.thresholds",
            value_used=report.final_score, unit="ratio")],
        algorithm={"name": "weighted_signal_gate",
                   "version": "v8.0.0",
                   "parameters": {"weights": SIGNAL_WEIGHTS,
                                  "proceed_at": PROCEED_AT,
                                  "warn_at": WARN_AT,
                                  "low_at": LOW_AT}},
        confidence=conf,
        selected_because=("Input quality is below the threshold required "
                          "for safe downstream computation. Manual review "
                          "or a higher-quality drawing is required."),
        violations=violations,
        warnings=[f"Signals: " + ", ".join(
            f"{s.name}={s.value:.2f}" for s in report.signals)],
    )
    dp.validate()
    dp.sign_engine()
    return dp


# ---------------------------------------------------------------------------
# Pipeline integration helper
# ---------------------------------------------------------------------------

def run_with_input_gate(
    drawing_hash: str,
    observations: ParserObservations,
    downstream_fn: Callable[[], DecisionProvenance],
    pe_override_token: Optional[str] = None,
) -> tuple[DecisionProvenance, ParserConfidenceReport]:
    """
    Convenience helper for pipeline code. Returns:
        (downstream_decision_or_refusal, gate_report)

    If the gate refuses, downstream_fn is NEVER called. The returned
    DecisionProvenance is the gate's refusal record.
    """
    report = assess_input_quality(observations, drawing_hash)
    refusal = gate_input_or_refuse(report, drawing_hash, pe_override_token)
    if refusal is not None:
        return refusal, report
    result = downstream_fn()
    # Propagate WARN/LOW into the downstream result as warnings.
    if report.decision in (GateDecision.WARN, GateDecision.LOW):
        result.warnings.append(
            f"Input quality {report.decision.value}: "
            f"final_score={report.final_score:.2f}. PE acknowledgement required."
        )
        # If downstream returned HIGH confidence on low-quality input, demote.
        if result.confidence.overall == ConfidenceLevel.HIGH:
            result.confidence = ConfidenceScore(
                input_quality_score=report.final_score,
                rule_coverage=result.confidence.rule_coverage,
                geometry_certainty=report.final_score,
                overall=ConfidenceLevel.MEDIUM,
            )
            result.sign_engine()  # re-sign after mutation
    return result, report


# ---------------------------------------------------------------------------
# Self-test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    # HIGH-quality input
    good = ParserObservations(
        legend_coverage=(0.97, "97% of symbols matched the legend"),
        scale_present=(1.00, "scale bar parsed: 1:100"),
        vector_purity=(0.95, "PDF is vector with minor raster annotations"),
        polygon_closure=(0.98, "98% of rooms are closed polygons"),
        layer_hygiene=(0.90, "DXF layers: FIRE, ELEC, ARCH all present"),
        title_block_completeness=(1.0, "title block fully parsed"),
        ocr_confidence=(0.95, "minor text recognition needed"),
        coordinate_sanity=(1.0, "building extents 80m x 60m — realistic"),
    )
    h = hashlib.sha256(b"good-input").hexdigest()
    r = assess_input_quality(good, h)
    assert r.decision == GateDecision.PROCEED, f"got {r.decision}"
    print(f"[parser_confidence] PROCEED at score {r.final_score:.3f} "
          f"in {r.elapsed_ms:.2f}ms")

    # WARN-quality input
    mixed = ParserObservations(
        legend_coverage=(0.80, "80% of symbols matched"),
        scale_present=(0.90, "scale bar parsed"),
        vector_purity=(0.55, "mixed vector/raster"),
        polygon_closure=(0.70, "some open polygons in corridors"),
        layer_hygiene=(0.60, "non-standard layer names"),
        title_block_completeness=(0.80, "missing revision number"),
        ocr_confidence=(0.75, "fair OCR"),
        coordinate_sanity=(1.0, "realistic"),
    )
    r2 = assess_input_quality(mixed, hashlib.sha256(b"warn-input").hexdigest())
    assert r2.decision in (GateDecision.WARN, GateDecision.LOW), f"got {r2.decision}"
    print(f"[parser_confidence] {r2.decision.value} at score {r2.final_score:.3f}")

    # REFUSE — no scale
    no_scale = ParserObservations(
        legend_coverage=(0.95, "ok"),
        scale_present=(0.0, "no scale bar found, no title-block scale"),
        vector_purity=(0.95, "ok"),
        polygon_closure=(0.95, "ok"),
        layer_hygiene=(0.9, "ok"),
        title_block_completeness=(0.9, "ok"),
        ocr_confidence=(0.9, "ok"),
        coordinate_sanity=(1.0, "ok"),
    )
    r3 = assess_input_quality(no_scale, hashlib.sha256(b"no-scale").hexdigest())
    assert r3.decision == GateDecision.REFUSE
    assert any("scale_present" in t for t in r3.hard_refuse_triggers)
    print(f"[parser_confidence] REFUSE (no scale) — hard triggers: "
          f"{len(r3.hard_refuse_triggers)}")

    # Gate integration test
    refusal = gate_input_or_refuse(r3, "sha256:demo")
    assert refusal is not None and refusal.value is None
    assert refusal.confidence.overall == ConfidenceLevel.REFUSE
    print(f"[parser_confidence] gate returned audit-grade refusal: "
          f"{refusal.decision_id[:8]}")

    # run_with_input_gate end-to-end
    def fake_downstream():
        rule = RuleApplied("NFPA72-2019 §17.6.3.1",
                           "NFPA72.17.6.3.1.smoke_max_spacing", 9.1, "m")
        conf = ConfidenceScore(1.0, 1.0, 1.0, ConfidenceLevel.HIGH)
        dp = DecisionProvenance.new(
            decision_type="panel_placement", value={"panels": [[0, 0]]},
            inputs={"drawing_hash": "x", "jurisdiction": "US.GENERIC",
                    "code_versions": {"NFPA72": "2019"}},
            rules_applied=[rule],
            algorithm={"name": "fake", "version": "1", "parameters": {}},
            confidence=conf, selected_because="test",
        )
        dp.validate(); dp.sign_engine()
        return dp

    result, gate_report = run_with_input_gate(
        "sha256:warn", mixed, fake_downstream,
    )
    assert result.value is not None
    # WARN/LOW path demoted HIGH -> MEDIUM
    if gate_report.decision in (GateDecision.WARN, GateDecision.LOW):
        assert result.confidence.overall == ConfidenceLevel.MEDIUM, \
            f"expected demotion to MEDIUM, got {result.confidence.overall}"
    print(f"[parser_confidence] pipeline integration PASS — "
          f"confidence demoted to {result.confidence.overall.value} on WARN input")
    print("[parser_confidence] all OK.")
