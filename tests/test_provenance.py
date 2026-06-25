"""
tests/test_provenance.py
============================
Comprehensive test suite for:
  - fireai/core/provenance.py

SAFETY CRITICAL: Provenance tracking provides audit trail for all
engineering decisions. Tampered or missing provenance could allow
unsafe designs to pass review. SHA-256 hash verification ensures
decision integrity.

Standards:
  NFPA 72 §1.3 — Documentation requirements
  ISO 13849 — Safety integrity verification
  IEC 61508 — Functional safety provenance
"""

from __future__ import annotations

import hashlib
import json
import time

import pytest

from fireai.core.provenance import (
    ConfidenceLevel,
    ConfidenceScore,
    DecisionProvenance,
    ProvenanceStore,
    RuleApplied,
    Violation,
    get_provenance_store,
    reset_provenance_store,
)

# ─────────────────────────────────────────────────────────────────────────────
# ConfidenceLevel Enum
# ─────────────────────────────────────────────────────────────────────────────


class TestConfidenceLevel:
    def test_all_levels(self):
        expected = {"DETERMINISTIC", "HIGH", "MEDIUM", "LOW", "UNCERTAIN"}
        actual = {l.value for l in ConfidenceLevel}
        assert actual == expected

    def test_hierarchy_ordering(self):
        """ISO 13849 PL hierarchy: DETERMINISTIC > HIGH > MEDIUM > LOW > UNCERTAIN."""
        levels = list(ConfidenceLevel)
        assert levels[0] == ConfidenceLevel.DETERMINISTIC
        assert levels[-1] == ConfidenceLevel.UNCERTAIN


# ─────────────────────────────────────────────────────────────────────────────
# ConfidenceScore
# ─────────────────────────────────────────────────────────────────────────────


class TestConfidenceScore:
    def test_default_values(self):
        cs = ConfidenceScore()
        assert cs.level == ConfidenceLevel.MEDIUM
        assert cs.value == 0.5
        assert cs.reason == ""
        assert cs.standard_reference == ""

    def test_custom_values(self):
        cs = ConfidenceScore(
            level=ConfidenceLevel.HIGH,
            value=0.9,
            reason="Validated by two independent methods",
            standard_reference="NFPA 72 §17.6.3.1.1",
        )
        assert cs.level == ConfidenceLevel.HIGH
        assert cs.value == 0.9
        assert "NFPA 72" in cs.standard_reference

    def test_value_range_valid(self):
        """Values 0.0 to 1.0 must be accepted."""
        ConfidenceScore(value=0.0)
        ConfidenceScore(value=1.0)
        ConfidenceScore(value=0.5)

    def test_value_above_1_raises(self):
        with pytest.raises(ValueError, match="0.0-1.0"):
            ConfidenceScore(value=1.1)

    def test_value_below_0_raises(self):
        with pytest.raises(ValueError, match="0.0-1.0"):
            ConfidenceScore(value=-0.1)

    def test_frozen(self):
        cs = ConfidenceScore()
        with pytest.raises(AttributeError):
            cs.value = 0.9


# ─────────────────────────────────────────────────────────────────────────────
# RuleApplied
# ─────────────────────────────────────────────────────────────────────────────


class TestRuleApplied:
    def test_default_values(self):
        r = RuleApplied()
        assert r.rule_id == ""
        assert r.result == ""

    def test_custom_values(self):
        r = RuleApplied(
            rule_id="NFPA72-17.6.3.1.1",
            description="Max detector spacing",
            standard="NFPA 72-2022",
            section="§17.6.3.1.1",
            result="PASS",
        )
        assert r.rule_id == "NFPA72-17.6.3.1.1"
        assert r.result == "PASS"

    def test_valid_results(self):
        for result in ("PASS", "FAIL", "WARNING", "N/A", ""):
            RuleApplied(result=result)

    def test_invalid_result_raises(self):
        with pytest.raises(ValueError, match="Invalid rule result"):
            RuleApplied(result="MAYBE")

    def test_frozen(self):
        r = RuleApplied(rule_id="R1", result="PASS")
        with pytest.raises(AttributeError):
            r.result = "FAIL"


# ─────────────────────────────────────────────────────────────────────────────
# Violation
# ─────────────────────────────────────────────────────────────────────────────


class TestViolation:
    def test_default_values(self):
        v = Violation()
        assert v.rule_id == ""
        assert v.severity == "HIGH"
        assert v.description == ""

    def test_custom_values(self):
        v = Violation(
            rule_id="NFPA72-17.6.3.1.1",
            severity="CRITICAL",
            description="Detector too far from wall",
            nfpa_section="§17.6.3.1.1",
            remediation="Move detector closer to wall",
        )
        assert v.severity == "CRITICAL"
        assert "CRITICAL" in v.severity

    def test_valid_severities(self):
        for sev in ("CRITICAL", "HIGH", "MEDIUM", "LOW"):
            Violation(severity=sev)

    def test_invalid_severity_raises(self):
        with pytest.raises(ValueError, match="Invalid severity"):
            Violation(severity="INFO")

    def test_frozen(self):
        v = Violation(severity="HIGH")
        with pytest.raises(AttributeError):
            v.severity = "LOW"


# ─────────────────────────────────────────────────────────────────────────────
# DecisionProvenance
# ─────────────────────────────────────────────────────────────────────────────


class TestDecisionProvenance:
    def test_default_values(self):
        dp = DecisionProvenance()
        assert dp.decision_id == ""
        assert dp.decision_type == ""
        assert dp.description == ""
        assert dp.parent_id is None
        assert dp.computation_hash == ""

    def test_auto_hash_when_id_present(self):
        """computation_hash auto-generated when decision_id is set."""
        dp = DecisionProvenance(decision_id="DEC-001", decision_type="PLACEMENT")
        assert dp.computation_hash != ""
        assert len(dp.computation_hash) == 32  # SHA-256 truncated to 32 chars

    def test_no_hash_when_no_id(self):
        """No hash generated when decision_id is empty."""
        dp = DecisionProvenance()
        assert dp.computation_hash == ""

    def test_compute_hash_deterministic(self):
        """Same input → same hash."""
        dp1 = DecisionProvenance(
            decision_id="DEC-001",
            decision_type="PLACEMENT",
            description="Place detector at (5,5)",
        )
        dp2 = DecisionProvenance(
            decision_id="DEC-001",
            decision_type="PLACEMENT",
            description="Place detector at (5,5)",
        )
        assert dp1.compute_hash() == dp2.compute_hash()

    def test_compute_hash_different_for_different_data(self):
        """Different input → different hash."""
        dp1 = DecisionProvenance(decision_id="DEC-001", decision_type="PLACEMENT")
        dp2 = DecisionProvenance(decision_id="DEC-002", decision_type="ROUTING")
        assert dp1.compute_hash() != dp2.compute_hash()

    def test_with_rules_applied(self):
        rule = RuleApplied(
            rule_id="R1",
            description="Test rule",
            standard="NFPA 72",
            section="§1",
            result="PASS",
        )
        dp = DecisionProvenance(
            decision_id="DEC-001",
            decision_type="PLACEMENT",
            rules_applied=(rule,),
        )
        assert len(dp.rules_applied) == 1
        assert dp.rules_applied[0].rule_id == "R1"

    def test_with_violations(self):
        viol = Violation(
            rule_id="R1",
            severity="CRITICAL",
            description="Major violation",
        )
        dp = DecisionProvenance(
            decision_id="DEC-001",
            decision_type="PLACEMENT",
            violations=(viol,),
        )
        assert len(dp.violations) == 1
        assert dp.violations[0].severity == "CRITICAL"

    def test_with_evidence(self):
        dp = DecisionProvenance(
            decision_id="DEC-001",
            decision_type="PLACEMENT",
            evidence={"area_m2": 100.0, "detector_count": 4},
        )
        assert dp.evidence["area_m2"] == 100.0
        assert dp.evidence["detector_count"] == 4

    def test_with_confidence(self):
        cs = ConfidenceScore(level=ConfidenceLevel.HIGH, value=0.9)
        dp = DecisionProvenance(
            decision_id="DEC-001",
            decision_type="PLACEMENT",
            confidence=cs,
        )
        assert dp.confidence.level == ConfidenceLevel.HIGH
        assert dp.confidence.value == 0.9

    def test_with_parent(self):
        dp = DecisionProvenance(
            decision_id="DEC-CHILD",
            decision_type="SUB_PLACEMENT",
            parent_id="DEC-PARENT",
        )
        assert dp.parent_id == "DEC-PARENT"

    def test_timestamp_auto_set(self):
        before = time.time()
        dp = DecisionProvenance(decision_id="DEC-001")
        after = time.time()
        assert before <= dp.timestamp <= after

    def test_not_frozen(self):
        """DecisionProvenance is NOT frozen — allows mutation for audit updates."""
        dp = DecisionProvenance(decision_id="DEC-001")
        # Should be mutable (not frozen) based on source code
        dp.description = "Updated description"
        assert dp.description == "Updated description"

    def test_hash_uses_sha256(self):
        """Verify hash is SHA-256 truncated to 32 hex chars."""
        dp = DecisionProvenance(
            decision_id="DEC-001",
            decision_type="TEST",
        )
        # Manually compute expected hash
        canonical = json.dumps(
            {
                "decision_id": "DEC-001",
                "decision_type": "TEST",
                "description": "",
                "confidence_value": 0.5,
                "rules": [],
                "violations": [],
                "evidence_keys": [],
            },
            sort_keys=True,
            default=str,
        )
        expected = hashlib.sha256(canonical.encode()).hexdigest()[:32]
        assert dp.computation_hash == expected


# ─────────────────────────────────────────────────────────────────────────────
# ProvenanceStore
# ─────────────────────────────────────────────────────────────────────────────


class TestProvenanceStore:
    @pytest.fixture
    def store(self):
        return ProvenanceStore()

    def test_add_and_get(self, store):
        dp = DecisionProvenance(decision_id="DEC-001", decision_type="PLACEMENT")
        store.add(dp)
        result = store.get("DEC-001")
        assert result is not None
        assert result.decision_id == "DEC-001"

    def test_get_nonexistent(self, store):
        result = store.get("NONEXISTENT")
        assert result is None

    def test_get_by_type(self, store):
        dp1 = DecisionProvenance(decision_id="DEC-001", decision_type="PLACEMENT")
        dp2 = DecisionProvenance(decision_id="DEC-002", decision_type="ROUTING")
        dp3 = DecisionProvenance(decision_id="DEC-003", decision_type="PLACEMENT")
        store.add(dp1)
        store.add(dp2)
        store.add(dp3)
        placements = store.get_by_type("PLACEMENT")
        assert len(placements) == 2
        routing = store.get_by_type("ROUTING")
        assert len(routing) == 1

    def test_get_by_type_empty(self, store):
        result = store.get_by_type("NONEXISTENT")
        assert result == []

    def test_get_children(self, store):
        parent = DecisionProvenance(decision_id="PARENT", decision_type="BUILDING")
        child1 = DecisionProvenance(decision_id="CHILD-1", decision_type="FLOOR", parent_id="PARENT")
        child2 = DecisionProvenance(decision_id="CHILD-2", decision_type="FLOOR", parent_id="PARENT")
        store.add(parent)
        store.add(child1)
        store.add(child2)
        children = store.get_children("PARENT")
        assert len(children) == 2

    def test_get_children_empty(self, store):
        children = store.get_children("NONEXISTENT")
        assert children == []

    def test_all_records(self, store):
        dp1 = DecisionProvenance(decision_id="DEC-001", decision_type="A")
        dp2 = DecisionProvenance(decision_id="DEC-002", decision_type="B")
        store.add(dp1)
        store.add(dp2)
        all_recs = store.all_records()
        assert len(all_recs) == 2

    def test_verify_integrity_valid(self, store):
        dp = DecisionProvenance(decision_id="DEC-001", decision_type="TEST")
        store.add(dp)
        valid, tampered = store.verify_integrity()
        assert valid == 1
        assert tampered == 0

    def test_verify_integrity_tampered(self, store):
        """Tampered record detected by hash mismatch."""
        dp = DecisionProvenance(decision_id="DEC-001", decision_type="TEST")
        store.add(dp)
        # Tamper with the record
        dp.description = "TAMPERED"
        valid, tampered = store.verify_integrity()
        assert tampered == 1
        assert valid == 0

    def test_verify_integrity_mixed(self, store):
        dp1 = DecisionProvenance(decision_id="DEC-001", decision_type="TEST")
        dp2 = DecisionProvenance(decision_id="DEC-002", decision_type="TEST")
        store.add(dp1)
        store.add(dp2)
        # Tamper only one
        dp1.description = "TAMPERED"
        valid, tampered = store.verify_integrity()
        assert valid == 1
        assert tampered == 1

    def test_summary(self, store):
        v1 = Violation(rule_id="R1", severity="CRITICAL", description="Bad")
        v2 = Violation(rule_id="R2", severity="MEDIUM", description="OK")
        dp = DecisionProvenance(
            decision_id="DEC-001",
            decision_type="PLACEMENT",
            violations=(v1, v2),
        )
        store.add(dp)
        s = store.summary()
        assert s["total_decisions"] == 1
        assert s["decision_types"]["PLACEMENT"] == 1
        assert s["total_violations"] == 2
        assert s["critical_violations"] == 1

    def test_summary_empty_store(self, store):
        s = store.summary()
        assert s["total_decisions"] == 0
        assert s["total_violations"] == 0
        assert s["critical_violations"] == 0

    def test_overwrite_by_id(self, store):
        """Adding record with same decision_id overwrites."""
        dp1 = DecisionProvenance(decision_id="DEC-001", decision_type="FIRST")
        dp2 = DecisionProvenance(decision_id="DEC-001", decision_type="SECOND")
        store.add(dp1)
        store.add(dp2)
        result = store.get("DEC-001")
        assert result.decision_type == "SECOND"


# ─────────────────────────────────────────────────────────────────────────────
# Global Store
# ─────────────────────────────────────────────────────────────────────────────


class TestGlobalStore:
    def test_get_provenance_store(self):
        store = get_provenance_store()
        assert isinstance(store, ProvenanceStore)

    def test_reset_provenance_store(self):
        # Add something to the store
        store = get_provenance_store()
        dp = DecisionProvenance(decision_id="TEMP", decision_type="TEST")
        store.add(dp)
        # Reset
        reset_provenance_store()
        # New store should be empty
        store = get_provenance_store()
        assert store.get("TEMP") is None

    def test_reset_creates_new_instance(self):
        store1 = get_provenance_store()
        reset_provenance_store()
        store2 = get_provenance_store()
        assert store1 is not store2


# ─────────────────────────────────────────────────────────────────────────────
# Edge Cases
# ─────────────────────────────────────────────────────────────────────────────


class TestEdgeCases:
    def test_confidence_score_boundary_0(self):
        cs = ConfidenceScore(value=0.0)
        assert cs.value == 0.0

    def test_confidence_score_boundary_1(self):
        cs = ConfidenceScore(value=1.0)
        assert cs.value == 1.0

    def test_empty_violations_and_rules(self):
        dp = DecisionProvenance(
            decision_id="DEC-001",
            rules_applied=(),
            violations=(),
        )
        assert len(dp.rules_applied) == 0
        assert len(dp.violations) == 0

    def test_large_evidence_dict(self):
        evidence = {f"key_{i}": i for i in range(100)}
        dp = DecisionProvenance(
            decision_id="DEC-001",
            evidence=evidence,
        )
        assert len(dp.evidence) == 100

    def test_many_rules_applied(self):
        rules = tuple(
            RuleApplied(rule_id=f"R{i}", result="PASS") for i in range(20)
        )
        dp = DecisionProvenance(
            decision_id="DEC-001",
            rules_applied=rules,
        )
        assert len(dp.rules_applied) == 20

    def test_store_with_many_records(self):
        store = ProvenanceStore()
        for i in range(50):
            dp = DecisionProvenance(
                decision_id=f"DEC-{i:04d}",
                decision_type="PLACEMENT" if i % 2 == 0 else "ROUTING",
            )
            store.add(dp)
        assert len(store.all_records()) == 50
        placements = store.get_by_type("PLACEMENT")
        assert len(placements) == 25


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
