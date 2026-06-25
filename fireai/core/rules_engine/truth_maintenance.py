"""FireAI Rules Engine — Truth Maintenance System (TMS)
=====================================================

Ensures that when a base fact is retracted, ALL conclusions derived
from it are also retracted. This is CRITICAL for safety-critical systems:

If a ceiling height changes from 3.0m to 4.0m, all spacing and coverage
conclusions derived from the 3.0m height must be invalidated and
re-derived with the new height.

Without TMS:
- Detector placed at 3.0m spacing (based on h=3.0m)
- Ceiling height changes to 4.0m (requires tighter spacing)
- Detector placement NOT updated → spacing violation → fire undetected

With TMS:
- Ceiling height change triggers retraction cascade
- All derived facts (spacing, coverage, compliance) are invalidated
- Rules re-evaluate with new height
- New detector placement is correct for h=4.0m

Reference: Doyle 1979, "A Truth Maintenance System", AI Journal
Reference: NFPA 72-2022 §17.6.3.1 (ceiling height determines spacing)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, List, Set

logger = logging.getLogger(__name__)


@dataclass
class DependencyRecord:
    """Records the dependency of a derived fact on its supporting facts.

    When any supporting fact is retracted, the derived fact must also
    be retracted and its producing rule must be re-evaluated.

    This is the core data structure of the TMS. It enables:
    1. Justification tracing (explain WHY a fact exists)
    2. Retraction cascading (remove invalid conclusions)
    3. Re-derivation (re-evaluate rules after retraction)
    """

    derived_fact_id: str
    supporting_fact_ids: List[str]
    producing_rule_id: str
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def is_still_valid(self, existing_fact_ids: Set[str]) -> bool:
        """Check if all supporting facts still exist."""
        return all(fid in existing_fact_ids for fid in self.supporting_fact_ids)


class TruthMaintenanceSystem:
    """Manages fact dependencies and ensures consistency.

    WARNING: This standalone TMS is NOT thread-safe. The RulesEngine
    maintains its own internal TMS (_derived_from/_supports) which IS
    protected by the engine's lock. The standalone TMS exists for audit
    purposes and must be synchronized manually if used from multiple threads.

    SAFETY CRITICAL: The TMS must NEVER silently fail to retract
    an invalid conclusion. A stale conclusion in a fire alarm system
    is a life safety hazard.
    """

    def __init__(self) -> None:
        # derived_fact_id → DependencyRecord
        self._dependencies: Dict[str, DependencyRecord] = {}

        # supporting_fact_id → Set[derived_fact_ids]
        self._support_index: Dict[str, Set[str]] = {}

        # Track retraction history for audit
        self._retraction_log: List[Dict] = []

        # FIX: Cascade-local visited set — replaces the historical-log
        # guard which incorrectly skipped re-derived facts.
        # Reset at the start of each top-level retract_support() call.
        self._cascade_visited: Set[str] = set()

    def record_dependency(
        self,
        derived_fact_id: str,
        supporting_fact_ids: List[str],
        producing_rule_id: str,
    ) -> None:
        """Record that a derived fact depends on supporting facts.

        This is called when a rule fires and asserts a new derived fact.
        """
        record = DependencyRecord(
            derived_fact_id=derived_fact_id,
            supporting_fact_ids=list(supporting_fact_ids),
            producing_rule_id=producing_rule_id,
        )
        self._dependencies[derived_fact_id] = record

        # Update support index
        for support_id in supporting_fact_ids:
            if support_id not in self._support_index:
                self._support_index[support_id] = set()
            self._support_index[support_id].add(derived_fact_id)

        logger.debug(
            f"TMS: Recorded dependency: {derived_fact_id} depends on {supporting_fact_ids} via rule {producing_rule_id}"
        )

    def retract_support(self, retracted_fact_id: str) -> List[str]:
        """Process the retraction of a supporting fact.

        Returns a list of derived fact IDs that must also be retracted
        because they depended on the retracted fact.

        This is a CASCADING operation: if a derived fact is retracted,
        any facts that depended on IT are also retracted.
        """
        # FIX: Initialize cascade-local visited set on top-level call.
        # This replaces the buggy historical-log guard that incorrectly
        # skipped re-derived facts (fact retracted then re-derived with
        # same ID would be permanently skipped on next cascade).
        is_top_level = not self._cascade_visited
        if is_top_level:
            self._cascade_visited = set()

        try:
            retracted_ids = self._retract_support_inner(retracted_fact_id)
        finally:
            # SAFETY FIX (MEDIUM-18): Always clear the cascade visited set
            # after a top-level call, even if an exception interrupted the
            # cascade. Without this, stale entries in _cascade_visited would
            # cause future retract_support calls to skip facts that were
            # visited in the interrupted cascade, leading to inconsistent
            # TMS state.
            if is_top_level:
                self._cascade_visited = set()

        return retracted_ids

    def _retract_support_inner(self, retracted_fact_id: str) -> List[str]:
        """Internal implementation of retract_support (without visited-set management)."""
        retracted_ids: List[str] = []

        if retracted_fact_id not in self._support_index:
            return retracted_ids

        # Get all facts directly supported by the retracted fact
        directly_affected = list(self._support_index[retracted_fact_id])

        for affected_id in directly_affected:
            # FIX: Use cascade-local visited set instead of historical log
            if affected_id in self._cascade_visited:
                continue  # Already retracted in THIS cascade
            self._cascade_visited.add(affected_id)

            # Log the retraction
            dep = self._dependencies.get(affected_id)
            reason = f"Supporting fact {retracted_fact_id} retracted" if dep else "Unknown dependency"
            self._retraction_log.append(
                {
                    "fact_id": affected_id,
                    "retracted_because": retracted_fact_id,
                    "producing_rule": dep.producing_rule_id if dep else "unknown",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "reason": reason,
                }
            )

            retracted_ids.append(affected_id)

            # Recursive: retract facts that depend on THIS derived fact
            cascade_ids = self._retract_support_inner(affected_id)
            retracted_ids.extend(cascade_ids)

        # Clean up support index for the retracted fact
        if retracted_fact_id in self._support_index:
            del self._support_index[retracted_fact_id]

        # Clean up dependency records
        for affected_id in retracted_ids:
            if affected_id in self._dependencies:
                dep = self._dependencies.pop(affected_id)
                # Remove from support index entries
                for support_id in dep.supporting_fact_ids:
                    if support_id in self._support_index:
                        self._support_index[support_id].discard(affected_id)
                        # FIX: Clean up empty sets to prevent memory leak
                        if not self._support_index[support_id]:
                            del self._support_index[support_id]

        if retracted_ids:
            logger.info(
                f"TMS: Retraction cascade from {retracted_fact_id}: {len(retracted_ids)} derived facts invalidated"
            )

        return retracted_ids

    def get_derived_facts_for(self, supporting_fact_id: str) -> List[str]:
        """Get all facts derived from a given supporting fact."""
        return list(self._support_index.get(supporting_fact_id, set()))

    def get_dependency_chain(self, fact_id: str) -> List[DependencyRecord]:
        """Get the full dependency chain for a fact.

        Returns the direct dependency record plus all transitive
        dependencies (dependencies of dependencies).
        """
        chain: List[DependencyRecord] = []
        visited: Set[str] = set()

        def _trace(fid: str) -> None:
            if fid in visited:
                return
            visited.add(fid)
            dep = self._dependencies.get(fid)
            if dep is not None:
                chain.append(dep)
                for support_id in dep.supporting_fact_ids:
                    _trace(support_id)

        _trace(fact_id)
        return chain

    def explain_derivation(self, fact_id: str) -> Dict:
        """Explain how a derived fact was produced.

        Returns a structured explanation suitable for engineering reports
        and safety audits.
        """
        dep = self._dependencies.get(fact_id)
        if dep is None:
            return {
                "fact_id": fact_id,
                "status": "base_fact",
                "message": "This fact was directly asserted, not derived.",
            }

        chain = self.get_dependency_chain(fact_id)

        return {
            "fact_id": fact_id,
            "status": "derived",
            "producing_rule": dep.producing_rule_id,
            "directly_depends_on": dep.supporting_fact_ids,
            "full_dependency_chain": [
                {
                    "derived_fact_id": r.derived_fact_id,
                    "supporting_facts": r.supporting_fact_ids,
                    "producing_rule": r.producing_rule_id,
                    "timestamp": r.timestamp,
                }
                for r in chain
            ],
            "retraction_history": [r for r in self._retraction_log if r["fact_id"] == fact_id],
        }

    def validate_consistency(self, existing_fact_ids: Set[str]) -> List[str]:
        """Check for stale dependencies — derived facts whose supports
        no longer exist but weren't properly retracted.

        Returns a list of stale derived fact IDs.

        SAFETY: This should return an empty list. If it doesn't,
        the TMS has a bug and stale conclusions may exist.
        """
        stale = []
        for fact_id, dep in self._dependencies.items():
            if not dep.is_still_valid(existing_fact_ids):
                stale.append(fact_id)
                logger.critical(
                    f"TMS CONSISTENCY ERROR: Derived fact {fact_id} has "
                    f"invalid supports {dep.supporting_fact_ids}. "
                    f"Missing: {set(dep.supporting_fact_ids) - existing_fact_ids}. "
                    f"This derived fact should have been retracted!"
                )

        if stale:
            logger.critical(
                f"TMS found {len(stale)} stale derived facts! "
                f"This is a CRITICAL safety error — conclusions may be "
                f"based on retracted facts. Stale IDs: {stale}"
            )

        return stale

    def get_retraction_log(self) -> List[Dict]:
        """Get the full retraction history for audit purposes."""
        return list(self._retraction_log)

    def reset(self) -> None:
        """Reset the TMS state."""
        self._dependencies.clear()
        self._support_index.clear()
        self._retraction_log.clear()
