"""
FireAI Rules Engine — V95 Regression Tests
===========================================

Regression tests for two bugs fixed in engine.py commit c32f651:

  BUG-V95-ENGINE-02 (SAFETY-CRITICAL):
    _iteration was never reset between evaluate() calls. Repeated calls
    without reset() would silently exhaust max_iterations (e.g. 25 calls
    × 4 iters = 100 = default max → engine stops evaluating rules).
    In a continuously-running fire alarm system this causes silent failure
    to detect NFPA 72 violations — a life-safety defect.
    FIX: self._iteration = 0 at the start of every evaluate() call.

  BUG-V95-ENGINE-01 (TRACEABILITY):
    _evaluate_one_pass logged every not-fired rule on EVERY iteration,
    inflating audit logs (34 entries for 10 rules × 4 iterations).
    Inflated logs obscure genuine not-fired reasons in safety reports;
    NFPA 72 requires traceable, auditable design records.
    FIX: Log not-fired rules only in the first pass (iteration == 1).

SAFETY: These tests MUST NEVER be deleted or skipped. Failure means
the rules engine has regressed to a known unsafe or untraceable state.

Reference: NFPA 72-2022 §10.6.1 — system shall operate continuously
Reference: agent.md — Rule 17: document every bug with root cause
"""

from __future__ import annotations

import pytest
from collections import Counter

from fireai.core.rules_engine.engine import (
    RulesEngine, Fact, Rule, RulePriority, RuleResult,
)
from fireai.core.rules_engine.nfpa72_rules import NFPA72RuleSet


# ---------------------------------------------------------------------------
# BUG-V95-ENGINE-02 — Iteration reset between evaluate() calls
# ---------------------------------------------------------------------------

class TestBugV95Engine02IterationReset:
    """
    Regression suite for BUG-V95-ENGINE-02.

    SAFETY CRITICAL: Any failure here means the engine will silently stop
    evaluating NFPA 72 rules after ~25 consecutive evaluate() calls,
    allowing dangerous detector placements to go undetected.
    """

    def test_iteration_resets_per_evaluate_call(self):
        """_iteration must reset to 0 at the start of every evaluate() call."""
        engine = RulesEngine(max_iterations=10)
        engine.add_rules(NFPA72RuleSet.all_rules())

        convergence_points = []
        for i in range(8):
            engine.assert_fact(Fact(
                fact_type="room",
                properties={
                    "room_id": f"R{i}",
                    "ceiling_height_m": 3.0,
                    "detector_type": "smoke",
                },
            ))
            engine.evaluate()
            convergence_points.append(engine._iteration)

        # Every call must converge at the same iteration depth — never accumulate.
        assert all(it == convergence_points[0] for it in convergence_points), (
            f"BUG-V95-ENGINE-02 REGRESSION: _iteration accumulated across calls "
            f"instead of resetting: {convergence_points}. "
            f"All values must equal {convergence_points[0]}."
        )

    def test_engine_detects_violation_after_many_calls(self):
        """Engine must detect CRITICAL violations after 30+ consecutive evaluate() calls.

        Before the fix: 30 calls × ~4 iters = 120 > max_iterations=100 → silent stop.
        After the fix: each call resets _iteration → engine always evaluates fully.
        """
        engine = RulesEngine(max_iterations=100)
        engine.add_rules(NFPA72RuleSet.all_rules())

        for i in range(30):
            engine.assert_fact(Fact(
                fact_type="room",
                properties={
                    "room_id": f"NORMAL_{i}",
                    "ceiling_height_m": 3.0,
                    "detector_type": "smoke",
                },
            ))
            engine.evaluate()

        # After 30 calls, inject a ceiling height that MUST trigger NFPA72-003
        engine.assert_fact(Fact(
            fact_type="room",
            properties={
                "room_id": "CRITICAL_HIGH_CEILING",
                "ceiling_height_m": 15.0,   # exceeds NFPA 72 table → CRITICAL_SAFETY
                "detector_type": "smoke",
            },
        ))
        engine.evaluate()

        critical = engine.get_safety_violations()
        hits = [r for r in critical if r.rule_id == "NFPA72-003"]

        assert len(hits) >= 1, (
            "BUG-V95-ENGINE-02 REGRESSION (SAFETY): ceiling-height violation for "
            "CRITICAL_HIGH_CEILING room was NOT detected after 30 prior evaluate() "
            "calls. The engine silently stopped evaluating because _iteration "
            "accumulated beyond max_iterations. This is a life-safety defect — "
            "a detector at 15 m ceiling height violates NFPA 72 and must be caught."
        )

    def test_second_call_iteration_equals_first(self):
        """_iteration after call N+1 must equal _iteration after call N (same scenario)."""
        engine = RulesEngine(max_iterations=100)
        engine.add_rules(NFPA72RuleSet.all_rules())

        engine.assert_fact(Fact(
            fact_type="room",
            properties={"room_id": "R1", "ceiling_height_m": 3.0, "detector_type": "smoke"},
        ))
        engine.evaluate()
        first = engine._iteration

        engine.assert_fact(Fact(
            fact_type="room",
            properties={"room_id": "R2", "ceiling_height_m": 3.0, "detector_type": "smoke"},
        ))
        engine.evaluate()

        assert engine._iteration == first, (
            f"BUG-V95-ENGINE-02 REGRESSION: second call _iteration={engine._iteration} "
            f"differs from first call _iteration={first}. Must be equal after reset."
        )


# ---------------------------------------------------------------------------
# BUG-V95-ENGINE-01 — Audit log inflation
# ---------------------------------------------------------------------------

class TestBugV95Engine01AuditInflation:
    """
    Regression suite for BUG-V95-ENGINE-01.

    TRACEABILITY: Failure here means safety audit reports contain duplicate
    not-fired entries that obscure genuine compliance gaps. NFPA 72 requires
    traceable, auditable records for every design decision.
    """

    def test_not_fired_rules_appear_once_per_evaluate(self):
        """Each not-fired rule must appear at most once per evaluate() call."""
        engine = RulesEngine()
        engine.add_rules(NFPA72RuleSet.all_rules())
        engine.assert_fact(Fact(
            fact_type="room",
            properties={"room_id": "R1", "ceiling_height_m": 3.0, "detector_type": "smoke"},
        ))
        engine.evaluate()

        not_fired = [a for a in engine.get_audit_log() if not a.fired]
        counts = Counter(a.rule_id for a in not_fired)
        duplicates = {rid: cnt for rid, cnt in counts.items() if cnt > 1}

        assert not duplicates, (
            f"BUG-V95-ENGINE-01 REGRESSION: not-fired rules appear multiple times "
            f"per evaluate() call: {duplicates}. "
            f"Each not-fired rule must be logged exactly once."
        )

    def test_total_audit_entries_not_inflated(self):
        """Audit log must not contain more not-fired entries than total rules.

        Before fix: 34 entries for 10 rules (3.4× from per-iteration logging).
        After fix: not-fired entries ≤ number of rules.
        """
        engine = RulesEngine()
        engine.add_rules(NFPA72RuleSet.all_rules())
        engine.assert_fact(Fact(
            fact_type="room",
            properties={"room_id": "R1", "ceiling_height_m": 3.0, "detector_type": "smoke"},
        ))
        engine.evaluate()

        audit = engine.get_audit_log()
        n_rules = len(NFPA72RuleSet.all_rules())
        not_fired_count = sum(1 for a in audit if not a.fired)

        assert not_fired_count <= n_rules, (
            f"BUG-V95-ENGINE-01 REGRESSION: {not_fired_count} not-fired audit entries "
            f"for {n_rules} rules. Maximum allowed: {n_rules} (one per rule). "
            f"Audit log is inflated — not-fired rules logged per iteration."
        )

    def test_fired_rules_still_present_in_audit(self):
        """The audit inflation fix must NOT remove fired rule entries."""
        engine = RulesEngine()
        engine.add_rules(NFPA72RuleSet.all_rules())
        engine.assert_fact(Fact(
            fact_type="room",
            properties={"room_id": "R1", "ceiling_height_m": 3.0, "detector_type": "smoke"},
        ))
        engine.evaluate()

        fired_ids = {a.rule_id for a in engine.get_audit_log() if a.fired}
        assert "NFPA72-001" in fired_ids, (
            "Regression: NFPA72-001 (ceiling height → spacing) not in fired audit "
            "entries. The inflation fix must not remove legitimate fired entries."
        )

    def test_not_fired_rules_still_in_audit(self):
        """Not-fired rules must still appear exactly once — dedup, not delete."""
        engine = RulesEngine()
        engine.add_rules(NFPA72RuleSet.all_rules())
        engine.assert_fact(Fact(
            fact_type="room",
            properties={"room_id": "R1", "ceiling_height_m": 3.0, "detector_type": "smoke"},
        ))
        engine.evaluate()

        not_fired_ids = {a.rule_id for a in engine.get_audit_log() if not a.fired}

        # These rules require detector/hvac/elevator facts — must appear as not-fired
        for expected_id in ("NFPA72-004", "NFPA72-006", "NFPA72-007"):
            assert expected_id in not_fired_ids, (
                f"{expected_id} must appear as not-fired in audit when its required "
                f"fact type is absent. Audit completeness violated."
            )


# ---------------------------------------------------------------------------
# Combined regression — both fixes working together
# ---------------------------------------------------------------------------

class TestV95Combined:
    """Integration regression: both fixes must coexist correctly."""

    def test_not_fired_deduplicated_across_many_evaluate_calls(self):
        """Per-call not-fired dedup must hold across 10 consecutive evaluate() calls."""
        engine = RulesEngine(max_iterations=100)
        engine.add_rules(NFPA72RuleSet.all_rules())
        n_rules = len(NFPA72RuleSet.all_rules())

        for i in range(10):
            engine.assert_fact(Fact(
                fact_type="room",
                properties={
                    "room_id": f"R{i}",
                    "ceiling_height_m": 3.0,
                    "detector_type": "smoke",
                },
            ))
            prev = len(engine.get_audit_log())
            engine.evaluate()
            new_entries = engine.get_audit_log()[prev:]

            # Not-fired entries in THIS call must not repeat
            not_fired_here = [a for a in new_entries if not a.fired]
            counts = Counter(a.rule_id for a in not_fired_here)
            dups = {rid: cnt for rid, cnt in counts.items() if cnt > 1}

            assert not dups, (
                f"Call {i+1}: not-fired rules duplicated: {dups}. "
                f"BUG-V95-ENGINE-01 regression detected."
            )
            assert engine._iteration <= engine.max_iterations, (
                f"Call {i+1}: _iteration={engine._iteration} exceeded "
                f"max_iterations={engine.max_iterations}. "
                f"BUG-V95-ENGINE-02 regression detected."
            )

    def test_safety_violation_detected_in_running_system(self):
        """
        End-to-end safety test combining both fixes.

        Simulates a running fire alarm system that:
        1. Processes 20 normal rooms (no violations)
        2. Then receives a critical dead-air-space violation

        Before both fixes: engine would have stopped evaluating after ~25 calls
        AND the audit log would be inflated with duplicate not-fired entries.
        Both defects could allow safety violations to go undetected or unlogged.
        """
        engine = RulesEngine(max_iterations=50)
        engine.add_rules(NFPA72RuleSet.all_rules())

        for i in range(20):
            engine.assert_fact(Fact(
                fact_type="room",
                properties={
                    "room_id": f"NORMAL_{i}",
                    "ceiling_height_m": 3.0,
                    "detector_type": "smoke",
                },
            ))
            engine.evaluate()

        # Inject a dead-air-space violation (detector too close to wall)
        engine.assert_fact(Fact(
            fact_type="detector",
            properties={
                "detector_id": "WALL_VIOLATION_01",
                "distance_to_wall_m": 0.02,   # < 0.1 m → violates NFPA 72 §17.6.3.1.1
            },
        ))
        engine.evaluate()

        violations = engine.get_safety_violations()
        dead_air = [v for v in violations if v.rule_id == "NFPA72-004"]

        assert len(dead_air) >= 1, (
            "CRITICAL REGRESSION (BUG-V95-ENGINE-02 + BUG-V95-ENGINE-01): "
            "Dead-air-space violation for detector WALL_VIOLATION_01 was NOT "
            "detected after 20 prior evaluate() calls. "
            "This detector is placed 0.02 m from a wall, violating "
            "NFPA 72 §17.6.3.1.1 (minimum 0.1 m). "
            "In a real installation, this detector would be approved despite "
            "the code violation — a direct life-safety failure."
        )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
