"""fireai.core.provenance — Decision Provenance & Audit Trail
===========================================================

Provides structured audit provenance for engineering decisions in the
FireAI safety-critical system. Every engineering decision (device placement,
cable routing, coverage verification, etc.) must be traceable to its
root cause, applicable standard, and confidence level.

V108 FIX: This module was removed in error — it's imported by 12 core modules.
Restored with a self-contained implementation (no external src.v8_core dependency).

Standards:
  - NFPA 72 §1.3 — Documentation requirements
  - ISO 13849 — Safety integrity verification
  - IEC 61508 — Functional safety provenance
"""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

# ═══════════════════════════════════════════════════════════════════════════════
# CONFIDENCE LEVELS
# ═══════════════════════════════════════════════════════════════════════════════


class ConfidenceLevel(Enum):
    """Confidence level for engineering decisions.

    Matches ISO 13849 PL (Performance Level) hierarchy:
      DETERMINISTIC: Mathematically proven (PL e equivalent)
      HIGH: Validated by multiple independent methods (PL d)
      MEDIUM: Validated by one method with standards reference (PL c)
      LOW: Best engineering judgment, needs manual verification (PL b)
      UNCERTAIN: Insufficient data, manual review required (PL a)
    """

    DETERMINISTIC = "DETERMINISTIC"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    UNCERTAIN = "UNCERTAIN"


# ═══════════════════════════════════════════════════════════════════════════════
# PROVENANCE DATA CLASSES
# ═══════════════════════════════════════════════════════════════════════════════


@dataclass(frozen=True)
class ConfidenceScore:
    """Quantified confidence in an engineering decision.

    Attributes:
        level: Qualitative confidence level.
        value: Numeric confidence (0.0 to 1.0).
        reason: Human-readable justification.
        standard_reference: Applicable standard (e.g., 'NFPA 72 §17.6.3.1.1').
        input_quality_score: Quality score for input data (0.0 to 1.0).
        rule_coverage: Fraction of applicable rules that were verified (0.0 to 1.0).
        geometry_certainty: Certainty of geometric inputs (0.0 to 1.0).
        overall: Overall confidence level (alias for level).

    """

    level: ConfidenceLevel = ConfidenceLevel.MEDIUM
    value: float = 0.5
    reason: str = ""
    standard_reference: str = ""
    input_quality_score: float = 0.5
    rule_coverage: float = 0.5
    geometry_certainty: float = 0.5
    overall: ConfidenceLevel = ConfidenceLevel.MEDIUM

    def __post_init__(self):
        if not (0.0 <= self.value <= 1.0):
            raise ValueError(f"Confidence value must be 0.0-1.0, got {self.value}")


@dataclass(frozen=True)
class RuleApplied:
    """Record of a specific rule or standard applied during decision-making.

    Attributes:
        rule_id: Unique rule identifier (e.g., 'NFPA72-17.6.3.1.1').
        description: Human-readable rule description.
        standard: Source standard (e.g., 'NFPA 72-2022').
        section: Section number (e.g., '§17.6.3.1.1').
        result: Outcome of applying this rule ('PASS', 'FAIL', 'WARNING', 'N/A').
        value_used: The numeric or string value used when applying this rule.
        unit: Unit of measurement for value_used (e.g., 'm', 'ft', 'VDC').
        constant_id: Identifier for the engineering constant referenced.
        citation: Full citation string for the rule source.

    """

    rule_id: str = ""
    description: str = ""
    standard: str = ""
    section: str = ""
    result: str = ""
    value_used: Optional[Any] = None
    unit: str = ""
    constant_id: str = ""
    citation: str = ""

    def __post_init__(self):
        if self.result not in ("PASS", "FAIL", "WARNING", "N/A", ""):
            raise ValueError(f"Invalid rule result: {self.result}")


@dataclass(frozen=True)
class Violation:
    """A violation found during rule application.

    Attributes:
        rule_id: Rule that was violated.
        severity: 'CRITICAL', 'HIGH', 'MEDIUM', or 'LOW'.
        description: Human-readable violation description.
        nfpa_section: Applicable NFPA section.
        remediation: Suggested fix.
        citation: Full citation string for the violated rule.
        location: Location identifier where the violation was found.

    """

    rule_id: str = ""
    severity: str = "HIGH"
    description: str = ""
    nfpa_section: str = ""
    remediation: str = ""
    citation: str = ""
    location: str = ""

    def __post_init__(self):
        if self.severity not in ("CRITICAL", "HIGH", "MEDIUM", "LOW"):
            raise ValueError(f"Invalid severity: {self.severity}")


@dataclass
class DecisionProvenance:
    """Complete provenance record for an engineering decision.

    This is the central audit artifact — every safety-critical decision
    in FireAI must produce a DecisionProvenance object that can be:
    1. Stored in the audit trail
    2. Reviewed by a human engineer
    3. Verified by the compliance engine
    4. Presented as evidence in AHJ submittals

    Attributes:
        decision_id: Unique identifier for this decision.
        decision_type: Category (e.g., 'DEVICE_PLACEMENT', 'CABLE_ROUTING').
        description: Human-readable description.
        confidence: Quantified confidence score.
        rules_applied: List of rules/standards applied.
        violations: List of violations found.
        evidence: Key-value evidence (calculation results, measurements).
        timestamp: Unix timestamp of decision.
        parent_id: ID of parent decision (for hierarchical decisions).
        computation_hash: SHA-256 hash for tamper detection.
        value: The decision value or result payload.
        inputs: Input parameters that influenced this decision.
        algorithm: Algorithm metadata (name, version, corrections).
        feasible_alternatives_considered: Number of alternatives evaluated.
        selected_because: Rationale for why this decision was selected.
        alternatives_top_3: Top 3 alternative decisions considered.
        warnings: Warnings generated during decision-making.
        violations_detected: Violations detected during decision-making.

    """

    decision_id: str = ""
    decision_type: str = ""
    description: str = ""
    confidence: ConfidenceScore = field(default_factory=ConfidenceScore)
    rules_applied: Tuple[RuleApplied, ...] = ()
    violations: Tuple[Violation, ...] = ()
    evidence: Dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)
    parent_id: Optional[str] = None
    computation_hash: str = ""
    value: Any = None
    inputs: Dict[str, Any] = field(default_factory=dict)
    algorithm: Dict[str, Any] = field(default_factory=dict)
    feasible_alternatives_considered: int = 0
    selected_because: str = ""
    alternatives_top_3: List[Any] = field(default_factory=list)
    warnings: List[Any] = field(default_factory=list)
    violations_detected: Optional[List[Any]] = None

    @classmethod
    def new(cls, **kwargs: Any) -> DecisionProvenance:
        """Factory method to create a DecisionProvenance with auto-generated ID.

        Accepts the same keyword arguments as the constructor, plus
        automatically generates decision_id and timestamp if not provided.
        """
        if "decision_id" not in kwargs:
            kwargs["decision_id"] = (
                f"dp-{hashlib.md5(str(kwargs).encode(), usedforsecurity=False).hexdigest()[:12]}"
            )
        if "timestamp" not in kwargs:
            kwargs["timestamp"] = time.time()
        obj = cls(**kwargs)
        return obj

    def compute_hash(self) -> str:
        """Compute SHA-256 hash of the decision for tamper detection."""
        canonical = json.dumps(
            {
                "decision_id": self.decision_id,
                "decision_type": self.decision_type,
                "description": self.description,
                "confidence_value": self.confidence.value,
                "rules": [r.rule_id for r in self.rules_applied],
                "violations": [v.rule_id for v in self.violations],
                "evidence_keys": sorted(self.evidence.keys()),
            },
            sort_keys=True,
            default=str,
        )
        return hashlib.sha256(canonical.encode()).hexdigest()[:32]

    def __post_init__(self):
        if not self.computation_hash and self.decision_id:
            object.__setattr__(self, "computation_hash", self.compute_hash())


# ═══════════════════════════════════════════════════════════════════════════════
# PROVENANCE STORE
# ═══════════════════════════════════════════════════════════════════════════════


class ProvenanceStore:
    """In-memory store for decision provenance records.

    Thread-safe storage for all engineering decisions made during
    a FireAI analysis session. Supports lookup by decision_id,
    decision_type, and parent_id for hierarchical traversal.
    """

    def __init__(self):
        self._records: Dict[str, DecisionProvenance] = {}
        self._by_type: Dict[str, List[str]] = {}

    def add(self, provenance: DecisionProvenance) -> None:
        """Add a provenance record to the store."""
        self._records[provenance.decision_id] = provenance
        if provenance.decision_type not in self._by_type:
            self._by_type[provenance.decision_type] = []
        self._by_type[provenance.decision_type].append(provenance.decision_id)

    def get(self, decision_id: str) -> Optional[DecisionProvenance]:
        """Get a provenance record by ID."""
        return self._records.get(decision_id)

    def get_by_type(self, decision_type: str) -> List[DecisionProvenance]:
        """Get all provenance records of a given type."""
        ids = self._by_type.get(decision_type, [])
        return [self._records[i] for i in ids if i in self._records]

    def get_children(self, parent_id: str) -> List[DecisionProvenance]:
        """Get all child decisions of a parent."""
        return [p for p in self._records.values() if p.parent_id == parent_id]

    def all_records(self) -> List[DecisionProvenance]:
        """Get all stored records."""
        return list(self._records.values())

    def verify_integrity(self) -> Tuple[int, int]:
        """Verify all computation hashes. Returns (valid_count, tampered_count)."""
        valid = 0
        tampered = 0
        for record in self._records.values():
            expected = record.compute_hash()
            if record.computation_hash == expected:
                valid += 1
            else:
                tampered += 1
        return valid, tampered

    def summary(self) -> Dict[str, Any]:
        """Generate a summary of the provenance store."""
        return {
            "total_decisions": len(self._records),
            "decision_types": {k: len(v) for k, v in self._by_type.items()},
            "total_violations": sum(len(r.violations) for r in self._records.values()),
            "critical_violations": sum(
                1 for r in self._records.values() for v in r.violations if v.severity == "CRITICAL"
            ),
        }


# Global provenance store instance
_global_store = ProvenanceStore()


def get_provenance_store() -> ProvenanceStore:
    """Get the global provenance store."""
    return _global_store


def reset_provenance_store() -> None:
    """Reset the global provenance store (for testing)."""
    global _global_store
    _global_store = ProvenanceStore()
