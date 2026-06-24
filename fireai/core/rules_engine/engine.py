"""FireAI Rules Engine — Core Engine
==================================

Pure-Python forward-chaining rules engine with:
- Alpha/Beta network evaluation (Rete-inspired)
- Priority-based conflict resolution (deterministic)
- Full audit trail for every rule evaluation
- Truth Maintenance System integration
- Thread-safe session isolation via session_id
- Structured NFPA section references on every rule

SAFETY CRITICAL: Every rule evaluation is logged. Every action is
traceable. No silent failures. No fabricated compliance.

Author: FireAI Engineering System
Reference: NFPA 72-2022, durable_rules Rete algorithm
"""

from __future__ import annotations

import logging
import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import IntEnum
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════════
# DATA STRUCTURES
# ═══════════════════════════════════════════════════════════════════════════════


class RulePriority(IntEnum):
    """Priority levels for conflict resolution.

    Lower value = higher priority = fires first.
    Safety-critical rules MUST have the highest priority (lowest number).

    Reference: This mirrors durable_rules' `pri` attribute but with
    explicit safety categories instead of arbitrary integers.
    """

    CRITICAL_SAFETY = 0  # Life-safety rules (e.g., coverage < 100%)
    SAFETY_VIOLATION = 10  # Code violations (e.g., spacing exceeded)
    COMPLIANCE_CHECK = 20  # Standard compliance checks
    DERIVED_FACT = 30  # Facts derived from other facts
    ADVISORY = 40  # Warnings and recommendations
    INFORMATIONAL = 50  # Information-only rules


@dataclass(frozen=True)
class Fact:
    """An immutable fact asserted into the rules engine.

    Facts are the data that rules match against. Each fact has:
    - A type (e.g., 'room', 'detector', 'ceiling')
    - Properties (e.g., {'ceiling_height_m': 3.0})
    - A unique ID for truth maintenance tracking
    - A source indicating where the fact came from (auditability)

    Immutable to prevent accidental mutation — a changed fact must
    be retracted and re-asserted, which triggers truth maintenance.
    """

    fact_type: str
    properties: Dict[str, Any] = field(default_factory=dict)
    fact_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    source: str = "user_input"  # or 'derived', 'sensor', 'import'
    nfpa_reference: Optional[str] = None  # e.g., "NFPA 72 §17.6.3.1"
    asserted_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def matches(self, fact_type: str, **conditions) -> bool:
        """Check if this fact matches a type and optional conditions.

        Conditions are key-value pairs checked against properties.
        A callable condition is treated as a predicate.
        """
        if self.fact_type != fact_type:
            return False
        for key, expected in conditions.items():
            if key not in self.properties:
                return False
            actual = self.properties[key]
            if callable(expected):
                if not expected(actual):
                    return False
            elif actual != expected:
                return False
        return True

    def __hash__(self) -> int:
        # FIX: hash must match eq scope — eq compares only fact_id,
        # so hash must use only fact_id to satisfy the Python invariant:
        # a == b → hash(a) == hash(b). Using (fact_type, fact_id)
        # violated this, corrupting set/dict lookups in _fired_combinations.
        return hash(self.fact_id)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Fact):
            return NotImplemented
        return self.fact_id == other.fact_id


@dataclass
class RuleResult:
    """The result of a rule firing.

    Contains the action taken, any new facts asserted, any facts
    retracted, and a severity level for audit purposes.
    """

    rule_id: str
    rule_name: str
    nfpa_reference: Optional[str]
    severity: RulePriority
    message: str
    asserted_facts: List[Fact] = field(default_factory=list)
    retracted_fact_ids: List[str] = field(default_factory=list)
    matched_facts: List[str] = field(default_factory=list)  # fact_ids
    session_id: str = ""
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    confidence: float = 1.0  # 0.0 to 1.0 — for uncertain inferences


@dataclass
class RuleAuditEntry:
    """Audit log entry for a rule evaluation.

    EVERY rule evaluation (whether it fires or not) is logged.
    This is a safety-critical requirement — you must be able to
    trace exactly why a rule did or did not fire.
    """

    rule_id: str
    rule_name: str
    nfpa_reference: Optional[str]
    evaluated_at: str
    fired: bool
    reason: str  # Why it fired or why it didn't
    session_id: str
    matched_fact_ids: List[str] = field(default_factory=list)
    result: Optional[RuleResult] = None


# Type aliases for rule conditions and actions
ConditionFn = Callable[[Fact], bool]
JoinConditionFn = Callable[[Fact, Fact], bool]
ActionFn = Callable[[List[Fact], "RulesEngine"], List[RuleResult]]


@dataclass
class Rule:
    """A declarative rule with structured metadata.

    Inspired by durable_rules' rule definition DSL but with:
    - Explicit NFPA section references (auditability)
    - Priority classification (safety-critical ordering)
    - Structured conditions instead of raw DSL
    - Truth maintenance integration

    Rules are defined declaratively and evaluated deterministically.
    """

    rule_id: str
    rule_name: str
    nfpa_reference: Optional[str]  # e.g., "NFPA 72 §17.6.3.1"
    priority: RulePriority = RulePriority.COMPLIANCE_CHECK
    description: str = ""

    # Condition: which fact types does this rule match?
    # Single-fact conditions (alpha network)
    fact_type: str = ""
    condition: Optional[ConditionFn] = None

    # Multi-fact join conditions (beta network)
    # List of (fact_type_1, fact_type_2, join_predicate)
    join_conditions: List[Tuple[str, str, JoinConditionFn]] = field(default_factory=list)

    # Action: what happens when the rule fires
    action: Optional[ActionFn] = None

    # Whether this rule derives new facts (for truth maintenance)
    derives_facts: bool = False

    def evaluate_condition(self, fact: Fact) -> bool:
        """Evaluate alpha condition on a single fact."""
        if not self.fact_type:
            return False
        if fact.fact_type != self.fact_type:
            return False
        if self.condition is None:
            return True  # No condition = match all facts of this type
        try:
            return self.condition(fact)
        except Exception as e:
            logger.error(
                f"Rule {self.rule_id} condition error on fact {fact.fact_id}: {e}",
                exc_info=True,
            )
            # SAFETY: On condition error, do NOT fire the rule.
            # Conservative = safer.
            return False


# ═══════════════════════════════════════════════════════════════════════════════
# RULES ENGINE
# ═══════════════════════════════════════════════════════════════════════════════


class RulesEngine:
    """Forward-chaining rules engine with audit trail and truth maintenance.

    Thread-safe via per-session locking. Each session represents one
    analysis context (e.g., one room or one building).

    Usage:
        engine = RulesEngine(session_id="room-001")
        engine.add_rule(my_rule)
        engine.assert_fact(Fact(fact_type="room", properties={...}))
        results = engine.evaluate()

    The engine logs EVERY rule evaluation — fired or not — for audit.
    No silent decisions. No hidden logic.

    Architecture (Rete-inspired):
        1. Alpha Network: Match individual facts against rule conditions
        2. Beta Network: Evaluate join conditions across fact pairs
        3. Conflict Resolution: Priority-based, deterministic ordering
        4. Action Execution: Fire actions in priority order
        5. TMS Update: Track dependencies for truth maintenance
        6. Audit Logging: Record every decision with evidence
    """

    def __init__(
        self,
        session_id: str = "",
        max_iterations: int = 100,
        audit_callback: Optional[Callable[[RuleAuditEntry], None]] = None,
    ) -> None:
        self.session_id = session_id or str(uuid.uuid4())
        self.max_iterations = max_iterations  # Prevent infinite loops
        self.audit_callback = audit_callback

        self._rules: Dict[str, Rule] = {}
        self._facts: Dict[str, Fact] = {}  # fact_id → Fact
        self._results: List[RuleResult] = []
        self._audit_log: List[RuleAuditEntry] = []

        # Alpha network: fact_type → list of rule_ids that match
        self._alpha_index: Dict[str, List[str]] = {}

        # TMS dependency tracking
        self._derived_from: Dict[str, List[str]] = {}  # derived_fact_id → [source_fact_ids]
        self._supports: Dict[str, List[str]] = {}  # source_fact_id → [derived_fact_ids]

        # Thread safety
        self._lock = threading.Lock()

        # Iteration counter for loop detection
        self._iteration = 0

        # Track which rule+fact combinations have already fired
        # in this evaluation cycle to prevent re-firing.
        # Key: (rule_id, frozenset of matched fact_ids)
        self._fired_combinations: set = set()

        # Validate max_iterations
        if max_iterations < 1:
            raise ValueError(f"max_iterations must be >= 1, got {max_iterations}")

    # ── Rule Management ──────────────────────────────────────────────────

    def add_rule(self, rule: Rule) -> None:
        """Add a rule to the engine.

        Validates that the rule has required fields and indexes it
        in the alpha network for efficient matching.
        """
        if not rule.rule_id:
            raise ValueError("Rule must have a rule_id")
        if not rule.rule_name:
            raise ValueError("Rule must have a rule_name")
        if rule.rule_id in self._rules:
            logger.warning(
                f"Rule {rule.rule_id} already exists — overwriting. "
                "In a safety-critical system, duplicate rule IDs may "
                "indicate a configuration error."
            )

        self._rules[rule.rule_id] = rule

        # Index in alpha network
        if rule.fact_type:
            if rule.fact_type not in self._alpha_index:
                self._alpha_index[rule.fact_type] = []
            if rule.rule_id not in self._alpha_index[rule.fact_type]:
                self._alpha_index[rule.fact_type].append(rule.rule_id)

        logger.debug(
            f"Rule added: {rule.rule_id} ({rule.rule_name}) priority={rule.priority.name} nfpa={rule.nfpa_reference}"
        )

    def add_rules(self, rules: Sequence[Rule]) -> None:
        """Add multiple rules at once."""
        for rule in rules:
            self.add_rule(rule)

    # ── Fact Management ──────────────────────────────────────────────────

    def assert_fact(self, fact: Fact) -> str:
        """Assert a fact into the engine.

        If a fact with the same ID already exists, it is replaced
        (retract + re-assert) to trigger truth maintenance.

        Returns the fact_id for tracking.
        """
        with self._lock:
            # If fact already exists, retract it first (TMS)
            if fact.fact_id in self._facts:
                self._retract_fact_internal(fact.fact_id, trigger_tms=True)

            self._facts[fact.fact_id] = fact
            logger.debug("Fact asserted: %s id=%s source=%s", fact.fact_type, fact.fact_id, fact.source)
            return fact.fact_id

    def retract_fact(self, fact_id: str) -> bool:
        """Retract a fact from the engine.

        Triggers truth maintenance: any derived facts that depended
        on this fact are also retracted (cascading).
        """
        with self._lock:
            return self._retract_fact_internal(fact_id, trigger_tms=True)

    def _retract_fact_internal(self, fact_id: str, trigger_tms: bool = True) -> bool:
        """Internal retract — called with lock already held."""
        if fact_id not in self._facts:
            return False

        fact = self._facts.pop(fact_id)

        # Truth maintenance: retract derived facts
        if trigger_tms and fact_id in self._supports:
            derived_ids = list(self._supports[fact_id])
            for derived_id in derived_ids:
                logger.info(
                    f"TMS: Retracting derived fact {derived_id} because supporting fact {fact_id} was retracted"
                )
                self._retract_fact_internal(derived_id, trigger_tms=True)

            # Clean up support index — guard against recursive deletion
            if fact_id in self._supports:
                del self._supports[fact_id]

        # Clean up derivation index
        if fact_id in self._derived_from:
            for source_id in self._derived_from[fact_id]:
                if source_id in self._supports:
                    if fact_id in self._supports[source_id]:
                        self._supports[source_id].remove(fact_id)
                    # FIX: Clean up empty support lists to prevent memory leak
                    if not self._supports[source_id]:
                        del self._supports[source_id]
            del self._derived_from[fact_id]

        logger.debug("Fact retracted: %s id=%s", fact.fact_type, fact_id)
        return True

    def get_facts(self, fact_type: Optional[str] = None) -> List[Fact]:
        """Get all facts, optionally filtered by type."""
        if fact_type is None:
            return list(self._facts.values())
        return [f for f in self._facts.values() if f.fact_type == fact_type]

    def get_fact(self, fact_id: str) -> Optional[Fact]:
        """Get a specific fact by ID."""
        return self._facts.get(fact_id)

    # ── Evaluation ───────────────────────────────────────────────────────

    def evaluate(self) -> List[RuleResult]:
        """Run the forward-chaining evaluation loop.

        This is the main entry point. It:
        1. Matches facts against rule conditions (alpha network)
        2. Evaluates join conditions (beta network)
        3. Resolves conflicts via priority
        4. Fires actions in order
        5. Processes derived facts (may trigger re-evaluation)
        6. Logs everything for audit

        The loop continues until no new facts are derived or
        max_iterations is reached (safety against infinite loops).

        Returns all RuleResults from this evaluation cycle.
        """
        all_results: List[RuleResult] = []
        previous_fact_count = -1

        # Reset per-cycle counters for this evaluation pass.
        # SAFETY: _iteration MUST be reset here, not only in reset().
        # Without this, repeated evaluate() calls silently exhaust
        # max_iterations across calls (e.g. 25 calls x 4 iters = 100 -> stops).
        # In a continuously-running fire alarm system, this causes the engine
        # to silently stop evaluating rules — a life-safety hazard.
        self._iteration = 0

        # Reset fired combinations for new evaluation cycle
        self._fired_combinations.clear()

        while self._iteration < self.max_iterations:
            self._iteration += 1
            new_results = self._evaluate_one_pass()
            all_results.extend(new_results)

            # Check for convergence: no new results AND no new facts
            current_fact_count = len(self._facts)
            if current_fact_count == previous_fact_count and len(new_results) == 0:
                break  # No new facts and no new results — converged
            previous_fact_count = current_fact_count

        if self._iteration >= self.max_iterations:
            logger.warning(
                f"Rules engine reached max_iterations={self.max_iterations} "
                f"in session {self.session_id}. This may indicate a rule "
                f"set that derives facts infinitely. Review rule set."
            )

        self._results.extend(all_results)
        return all_results

    def _evaluate_one_pass(self) -> List[RuleResult]:
        """One pass of the Rete-inspired evaluation cycle."""
        results: List[RuleResult] = []

        # Collect all rule candidates with their matching facts
        candidates: List[Tuple[Rule, List[Fact]]] = []

        # Phase 1: Alpha network — match individual facts
        # SAFETY: Rules with join_conditions are ONLY evaluated via
        # the beta network (Phase 2). Adding them as alpha-only
        # candidates would pass a single fact to an action that
        # expects a fact pair, causing IndexError.
        for fact in list(self._facts.values()):
            fact_type = fact.fact_type
            if fact_type not in self._alpha_index:
                continue

            for rule_id in self._alpha_index[fact_type]:
                rule = self._rules.get(rule_id)
                if rule is None:
                    continue

                # Skip join-only rules from alpha network — they need
                # pairs of facts, not a single fact
                if rule.join_conditions:
                    continue

                if rule.evaluate_condition(fact):
                    candidates.append((rule, [fact]))

        # Phase 2: Beta network — evaluate join conditions
        join_candidates = self._evaluate_joins(candidates)
        candidates.extend(join_candidates)

        # Phase 3: Conflict resolution — sort by priority
        candidates.sort(key=lambda x: x[0].priority)

        # Phase 4: Fire actions in priority order
        for rule, matched_facts in candidates:
            # Skip if this rule+fact combination already fired in this cycle
            combo_key = (rule.rule_id, frozenset(f.fact_id for f in matched_facts))
            if combo_key in self._fired_combinations:
                continue

            # Log the evaluation (even if it doesn't fire)
            audit = RuleAuditEntry(
                rule_id=rule.rule_id,
                rule_name=rule.rule_name,
                nfpa_reference=rule.nfpa_reference,
                evaluated_at=datetime.now(timezone.utc).isoformat(),
                fired=True,
                reason=f"Matched {len(matched_facts)} facts",
                session_id=self.session_id,
                matched_fact_ids=[f.fact_id for f in matched_facts],
            )

            if rule.action is not None:
                try:
                    rule_results = rule.action(matched_facts, self)
                    this_rule_results = []  # FIX: track only THIS rule's results

                    # Track derived facts for TMS
                    for result in rule_results:
                        result.session_id = self.session_id
                        for new_fact in result.asserted_facts:
                            # Record dependency: new_fact depends on matched_facts
                            self._derived_from[new_fact.fact_id] = [f.fact_id for f in matched_facts]
                            for source in matched_facts:
                                if source.fact_id not in self._supports:
                                    self._supports[source.fact_id] = []
                                self._supports[source.fact_id].append(new_fact.fact_id)
                            # Actually assert the derived fact
                            self.assert_fact(new_fact)

                        results.append(result)
                        this_rule_results.append(result)

                    audit.result = this_rule_results[-1] if this_rule_results else None

                    # FIX: Only add to fired_combinations on SUCCESS
                    self._fired_combinations.add(combo_key)

                except Exception as e:
                    logger.error(
                        f"Rule {rule.rule_id} action error: {e}",
                        exc_info=True,
                    )
                    audit.fired = False
                    audit.reason = f"Action error: {e}"
                    # FIX: Do NOT add to fired_combinations on error — allow retry

            else:
                # No action defined — still record as fired for dedup
                self._fired_combinations.add(combo_key)

            # Log audit entry
            self._audit_log.append(audit)
            if self.audit_callback:
                try:
                    self.audit_callback(audit)
                except Exception:
                    pass  # Audit callback must not crash the engine

        # Log rules that did NOT fire — only once per evaluate() call (iteration=1).
        # SAFETY: We still log every not-fired rule, but only in the first pass.
        # This prevents audit log inflation where the same rule is logged
        # N times (once per iteration) even though facts have not changed.
        # Inflated audit logs obscure genuine not-fired reasons in reports.
        fired_ids = {rule.rule_id for rule, _ in candidates}
        if self._iteration == 1:  # Only log not-fired in first pass
            for rule in self._rules.values():
                if rule.rule_id not in fired_ids:
                    audit = RuleAuditEntry(
                        rule_id=rule.rule_id,
                        rule_name=rule.rule_name,
                        nfpa_reference=rule.nfpa_reference,
                        evaluated_at=datetime.now(timezone.utc).isoformat(),
                        fired=False,
                        reason="No matching facts",
                        session_id=self.session_id,
                    )
                    self._audit_log.append(audit)
                    if self.audit_callback:
                        try:
                            self.audit_callback(audit)
                        except Exception:
                            pass

        return results

    def _evaluate_joins(self, alpha_candidates: List[Tuple[Rule, List[Fact]]]) -> List[Tuple[Rule, List[Fact]]]:
        """Evaluate beta network join conditions.

        For rules with join_conditions, find pairs of facts that
        satisfy the join predicate across fact types.
        """
        join_results: List[Tuple[Rule, List[Fact]]] = []

        for rule in self._rules.values():
            if not rule.join_conditions:
                continue  # No joins — handled by alpha network

            for fact_type_1, fact_type_2, join_pred in rule.join_conditions:
                facts_1 = self.get_facts(fact_type_1)
                facts_2 = self.get_facts(fact_type_2)

                for f1 in facts_1:
                    # FIX: Alpha condition filter only applies when
                    # rule.fact_type matches this join side's fact_type.
                    # The old code skipped ALL f1 facts when rule.fact_type
                    # != fact_type_1, which broke asymmetric joins.
                    if rule.fact_type and rule.fact_type == fact_type_1:
                        # This side matches the rule's primary fact_type,
                        # so apply the alpha condition
                        if rule.condition and not rule.condition(f1):
                            continue
                    # If rule.fact_type != fact_type_1, the alpha condition
                    # targets the other side — don't filter f1 here

                    for f2 in facts_2:
                        # SAFETY FIX (HIGH-14): Apply alpha condition to f2
                        # when rule.fact_type matches fact_type_2. Previously,
                        # f2 was never filtered, causing unfiltered facts to
                        # enter the join and be compared against the join
                        # predicate — inefficient and fragile.
                        if rule.fact_type and rule.fact_type == fact_type_2:
                            if rule.condition and not rule.condition(f2):
                                continue
                        try:
                            if join_pred(f1, f2):
                                join_results.append((rule, [f1, f2]))
                        except Exception as e:
                            logger.error(
                                f"Join condition error in rule {rule.rule_id}: {e}",
                                exc_info=True,
                            )

        return join_results

    # ── Query & Audit ────────────────────────────────────────────────────

    def get_results(
        self,
        severity: Optional[RulePriority] = None,
        rule_id: Optional[str] = None,
    ) -> List[RuleResult]:
        """Get evaluation results, optionally filtered."""
        results = self._results
        if severity is not None:
            results = [r for r in results if r.severity == severity]
        if rule_id is not None:
            results = [r for r in results if r.rule_id == rule_id]
        return results

    def get_audit_log(self) -> List[RuleAuditEntry]:
        """Get the complete audit log for this session."""
        return list(self._audit_log)

    def get_safety_violations(self) -> List[RuleResult]:
        """Get all CRITICAL_SAFETY and SAFETY_VIOLATION results."""
        return [r for r in self._results if r.severity <= RulePriority.SAFETY_VIOLATION]

    def get_compliance_summary(self) -> Dict[str, Any]:
        """Get a summary of compliance status from rule results.

        Returns a structured summary suitable for engineering reports.
        """
        critical = [r for r in self._results if r.severity == RulePriority.CRITICAL_SAFETY]
        violations = [r for r in self._results if r.severity == RulePriority.SAFETY_VIOLATION]
        compliant = [
            r
            for r in self._results
            if r.severity == RulePriority.COMPLIANCE_CHECK  # FIX: was >=, included advisory/info
        ]

        return {
            "session_id": self.session_id,
            "total_rules_evaluated": len(self._audit_log),
            "rules_fired": len([a for a in self._audit_log if a.fired]),
            "critical_safety_issues": len(critical),
            "safety_violations": len(violations),
            "compliant_checks": len(compliant),
            "total_facts": len(self._facts),
            "derived_facts": len(self._derived_from),
            "is_safe": len(critical) == 0 and len(violations) == 0,
            "nfpa_references": list({r.nfpa_reference for r in self._results if r.nfpa_reference}),
        }

    def reset(self) -> None:
        """Reset the engine state for a new evaluation cycle.

        Clears facts, results, and audit log. Keeps rules.
        """
        with self._lock:
            self._facts.clear()
            self._results.clear()
            self._audit_log.clear()
            self._derived_from.clear()
            self._supports.clear()
            self._fired_combinations.clear()  # FIX: was missing — stale combos blocked rules after reset
            self._iteration = 0

    def explain(self, fact_id: str, _visited: Optional[set] = None) -> Dict[str, Any]:
        """Explain why a fact exists — trace its derivation chain.

        Safety-critical feature: you must be able to explain every
        conclusion the system reaches.
        """
        # FIX: Cycle detection to prevent infinite recursion
        if _visited is None:
            _visited = set()
        if fact_id in _visited:
            return {"fact_id": fact_id, "status": "circular_reference"}
        _visited.add(fact_id)

        fact = self._facts.get(fact_id)
        if fact is None:
            return {"fact_id": fact_id, "status": "not_found"}

        derivation = self._derived_from.get(fact_id, [])
        supported_by = self._supports.get(fact_id, [])

        # Recursively explain source facts (pass visited set)
        source_explanations = []
        for source_id in derivation:
            source_explanations.append(self.explain(source_id, _visited))

        # Find which rule produced this fact
        producing_rule = None
        for audit in self._audit_log:
            if audit.fired and audit.result:
                if fact_id in [f.fact_id for f in audit.result.asserted_facts]:
                    producing_rule = {
                        "rule_id": audit.rule_id,
                        "rule_name": audit.rule_name,
                        "nfpa_reference": audit.nfpa_reference,
                    }
                    break

        return {
            "fact_id": fact_id,
            "fact_type": fact.fact_type,
            "source": fact.source,
            "nfpa_reference": fact.nfpa_reference,
            "is_derived": fact_id in self._derived_from,
            "derived_from": derivation,
            "source_explanations": source_explanations,
            "supports": supported_by,
            "producing_rule": producing_rule,
        }
