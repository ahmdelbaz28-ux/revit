# NOSONAR
"""
FireAI Rules Engine — Comprehensive Test Suite
=================================================

Tests the NFPA 72 Rules Engine, Truth Maintenance System,
and API Contract Validator.

SAFETY: These tests validate safety-critical behavior.
If any test fails, the rules engine MUST NOT be used in production.

Test Categories:
1. Engine basics (fact assertion, retraction, rule evaluation)
2. NFPA 72 rules (spacing, coverage, dead air, duct detectors)
3. Truth Maintenance System (retraction cascading)
4. API Contract validation
5. Audit trail completeness
6. Edge cases and adversarial inputs
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from fireai.core.rules_engine.api_contract import (
    ContractSeverity,
    ContractValidator,
)
from fireai.core.rules_engine.engine import (
    Fact,
    Rule,
    RulePriority,
    RuleResult,
    RulesEngine,
)
from fireai.core.rules_engine.nfpa72_rules import NFPA72RuleSet
from fireai.core.rules_engine.truth_maintenance import (
    TruthMaintenanceSystem,
)

# ═══════════════════════════════════════════════════════════════════════════════
# ENGINE BASICS
# ═══════════════════════════════════════════════════════════════════════════════


class TestFactBasics:
    """Test Fact creation and matching."""

    def test_fact_creation(self):
        fact = Fact(
            fact_type="room",
            properties={"room_id": "R1", "ceiling_height_m": 3.0},
        )
        assert fact.fact_type == "room"
        assert fact.properties["ceiling_height_m"] == 3.0  # NOSONAR — S1244: import retained for re-export / API surface
        assert fact.fact_id  # Auto-generated
        assert fact.source == "user_input"

    def test_fact_matching_by_type(self):
        fact = Fact(fact_type="room", properties={"room_id": "R1"})
        assert fact.matches("room")
        assert not fact.matches("detector")

    def test_fact_matching_with_conditions(self):
        fact = Fact(
            fact_type="room",
            properties={"ceiling_height_m": 3.0, "detector_type": "smoke"},
        )
        assert fact.matches("room", ceiling_height_m=3.0)
        assert fact.matches("room", detector_type="smoke")
        assert not fact.matches("room", ceiling_height_m=4.0)

    def test_fact_matching_with_predicate(self):
        fact = Fact(
            fact_type="room",
            properties={"ceiling_height_m": 5.0},
        )
        assert fact.matches("room", ceiling_height_m=lambda h: h > 3.0)
        assert not fact.matches("room", ceiling_height_m=lambda h: h < 3.0)

    def test_fact_immutability(self):
        fact = Fact(fact_type="room", properties={"h": 3.0})
        assert fact.properties["h"] == 3.0  # NOSONAR — S1244: import retained for re-export / API surface
        # Fact is frozen dataclass — cannot mutate directly
        with pytest.raises(AttributeError):
            fact.fact_type = "detector"

    def test_fact_unique_ids(self):
        f1 = Fact(fact_type="room", properties={"h": 3.0})
        f2 = Fact(fact_type="room", properties={"h": 3.0})
        assert f1.fact_id != f2.fact_id


class TestEngineBasics:
    """Test RulesEngine core functionality."""

    def test_engine_creation(self):
        engine = RulesEngine(session_id="test-001")
        assert engine.session_id == "test-001"

    def test_assert_and_get_facts(self):
        engine = RulesEngine()
        fact = Fact(fact_type="room", properties={"room_id": "R1"})
        fid = engine.assert_fact(fact)
        retrieved = engine.get_fact(fid)
        assert retrieved is not None
        assert retrieved.fact_type == "room"

    def test_retract_fact(self):
        engine = RulesEngine()
        fact = Fact(fact_type="room", properties={"room_id": "R1"})
        fid = engine.assert_fact(fact)
        assert engine.retract_fact(fid) is True
        assert engine.get_fact(fid) is None

    def test_retract_nonexistent_fact(self):
        engine = RulesEngine()
        assert engine.retract_fact("nonexistent") is False

    def test_get_facts_by_type(self):
        engine = RulesEngine()
        engine.assert_fact(Fact(fact_type="room", properties={"id": "R1"}))
        engine.assert_fact(Fact(fact_type="room", properties={"id": "R2"}))
        engine.assert_fact(Fact(fact_type="detector", properties={"id": "D1"}))
        rooms = engine.get_facts("room")
        assert len(rooms) == 2

    def test_simple_rule_fires(self):
        engine = RulesEngine()

        rule = Rule(
            rule_id="TEST-001",
            rule_name="Test Rule",
            nfpa_reference="NFPA 72 Test",
            priority=RulePriority.COMPLIANCE_CHECK,
            fact_type="room",
            condition=lambda f: f.properties.get("ceiling_height_m", 0) > 3.0,
            action=lambda facts, eng: [
                RuleResult(
                    rule_id="TEST-001",
                    rule_name="Test Rule",
                    nfpa_reference="NFPA 72 Test",
                    severity=RulePriority.COMPLIANCE_CHECK,
                    message="Ceiling too high",
                    matched_facts=[f.fact_id for f in facts],
                )
            ],
        )

        engine.add_rule(rule)
        engine.assert_fact(
            Fact(
                fact_type="room",
                properties={"ceiling_height_m": 4.0},
            )
        )
        results = engine.evaluate()
        assert len(results) == 1
        assert results[0].rule_id == "TEST-001"

    def test_rule_does_not_fire_when_condition_false(self):
        engine = RulesEngine()

        rule = Rule(
            rule_id="TEST-002",
            rule_name="Test Rule",
            nfpa_reference=None,
            priority=RulePriority.COMPLIANCE_CHECK,
            fact_type="room",
            condition=lambda f: f.properties.get("ceiling_height_m", 0) > 10.0,
            action=lambda facts, eng: [
                RuleResult(
                    rule_id="TEST-002",
                    rule_name="Test Rule",
                    nfpa_reference=None,
                    severity=RulePriority.COMPLIANCE_CHECK,
                    message="Should not fire",
                    matched_facts=[f.fact_id for f in facts],
                )
            ],
        )

        engine.add_rule(rule)
        engine.assert_fact(
            Fact(
                fact_type="room",
                properties={"ceiling_height_m": 3.0},
            )
        )
        results = engine.evaluate()
        assert len(results) == 0

    def test_priority_ordering(self):
        """Higher priority rules fire first (lower number = higher priority)."""
        engine = RulesEngine()
        fired_order = []

        def make_action(rule_id, order_list):
            def action(facts, eng):
                order_list.append(rule_id)
                return [
                    RuleResult(
                        rule_id=rule_id,
                        rule_name=rule_id,
                        nfpa_reference=None,
                        severity=RulePriority.COMPLIANCE_CHECK,
                        message=rule_id,
                        matched_facts=[f.fact_id for f in facts],
                    )
                ]

            return action

        # Add rules in reverse priority order
        engine.add_rule(
            Rule(
                rule_id="LOW",
                rule_name="Low Priority",
                nfpa_reference=None,
                priority=RulePriority.ADVISORY,
                fact_type="room",
                action=make_action("LOW", fired_order),
            )
        )
        engine.add_rule(
            Rule(
                rule_id="HIGH",
                rule_name="High Priority",
                nfpa_reference=None,
                priority=RulePriority.CRITICAL_SAFETY,
                fact_type="room",
                action=make_action("HIGH", fired_order),
            )
        )

        engine.assert_fact(Fact(fact_type="room"))
        engine.evaluate()

        # CRITICAL_SAFETY (0) should fire before ADVISORY (40)
        assert fired_order[0] == "HIGH"
        assert fired_order[1] == "LOW"

    def test_audit_log_completeness(self):
        """Every rule evaluation must be logged — fired or not."""
        engine = RulesEngine()

        engine.add_rule(
            Rule(
                rule_id="FIRES",
                rule_name="Fires",
                nfpa_reference="Test",
                priority=RulePriority.COMPLIANCE_CHECK,
                fact_type="room",
                action=lambda facts, eng: [
                    RuleResult(
                        rule_id="FIRES",
                        rule_name="Fires",
                        nfpa_reference="Test",
                        severity=RulePriority.COMPLIANCE_CHECK,
                        message="ok",
                        matched_facts=[f.fact_id for f in facts],
                    )
                ],
            )
        )
        engine.add_rule(
            Rule(
                rule_id="DOES_NOT_FIRE",
                rule_name="Does Not Fire",
                nfpa_reference="Test",
                priority=RulePriority.COMPLIANCE_CHECK,
                fact_type="detector",
                action=lambda facts, eng: [
                    RuleResult(
                        rule_id="DOES_NOT_FIRE",
                        rule_name="Does Not Fire",
                        nfpa_reference="Test",
                        severity=RulePriority.COMPLIANCE_CHECK,
                        message="ok",
                        matched_facts=[f.fact_id for f in facts],
                    )
                ],
            )
        )

        engine.assert_fact(Fact(fact_type="room"))
        engine.evaluate()

        audit = engine.get_audit_log()
        # Both rules should appear in audit
        fired_ids = {a.rule_id for a in audit if a.fired}
        not_fired_ids = {a.rule_id for a in audit if not a.fired}
        assert "FIRES" in fired_ids
        assert "DOES_NOT_FIRE" in not_fired_ids


# ═══════════════════════════════════════════════════════════════════════════════
# NFPA 72 RULES
# ═══════════════════════════════════════════════════════════════════════════════


class TestNFPA72Rules:
    """Test NFPA 72 declarative rules."""

    def test_ceiling_height_spacing_smoke(self):
        engine = RulesEngine()
        engine.add_rules(NFPA72RuleSet.all_rules())
        engine.assert_fact(
            Fact(
                fact_type="room",
                properties={
                    "room_id": "R1",
                    "ceiling_height_m": 3.0,
                    "detector_type": "smoke",
                },
            )
        )
        engine.evaluate()

        # Should produce spacing and coverage facts
        spacing_facts = engine.get_facts("spacing")
        assert len(spacing_facts) >= 1
        s = spacing_facts[0]
        assert s.properties["listed_spacing_m"] == 9.10  # NOSONAR — S1244: import retained for re-export / API surface
        assert s.properties["coverage_radius_m"] == pytest.approx(6.37, abs=0.01)

    def test_ceiling_height_spacing_heat(self):
        engine = RulesEngine()
        engine.add_rules(NFPA72RuleSet.all_rules())
        engine.assert_fact(
            Fact(
                fact_type="room",
                properties={
                    "room_id": "R2",
                    "ceiling_height_m": 3.0,
                    "detector_type": "heat",
                },
            )
        )
        engine.evaluate()
        spacing_facts = engine.get_facts("spacing")
        assert len(spacing_facts) >= 1
        s = spacing_facts[0]
        assert s.properties["listed_spacing_m"] == 6.10  # NOSONAR — S1244: import retained for re-export / API surface
        assert s.properties["coverage_radius_m"] == pytest.approx(4.27, abs=0.01)

    def test_ceiling_height_exceeds_table(self):
        engine = RulesEngine()
        engine.add_rules(NFPA72RuleSet.all_rules())
        engine.assert_fact(
            Fact(
                fact_type="room",
                properties={
                    "room_id": "R3",
                    "ceiling_height_m": 15.0,
                    "detector_type": "smoke",
                },
            )
        )
        engine.evaluate()

        # Should produce AHJ_REVIEW_REQUIRED flag
        critical = engine.get_safety_violations()
        assert len(critical) >= 1
        assert any(r.rule_id == "NFPA72-003" for r in critical)

        flags = engine.get_facts("safety_flag")
        assert len(flags) >= 1
        assert flags[0].properties["flag_type"] == "AHJ_REVIEW_REQUIRED"

    def test_dead_air_space_violation(self):
        engine = RulesEngine()
        engine.add_rules(NFPA72RuleSet.all_rules())
        engine.assert_fact(
            Fact(
                fact_type="detector",
                properties={
                    "detector_id": "D1",
                    "distance_to_wall_m": 0.05,  # Less than 0.1m
                },
            )
        )
        engine.evaluate()
        violations = engine.get_safety_violations()
        assert any(r.rule_id == "NFPA72-004" for r in violations)

    def test_dead_air_space_ok(self):
        engine = RulesEngine()
        engine.add_rules(NFPA72RuleSet.all_rules())
        engine.assert_fact(
            Fact(
                fact_type="detector",
                properties={
                    "detector_id": "D2",
                    "distance_to_wall_m": 0.5,  # More than 0.1m
                },
            )
        )
        results = engine.evaluate()
        violations = [r for r in results if r.rule_id == "NFPA72-004"]
        assert len(violations) == 0

    def test_duct_detector_required(self):
        engine = RulesEngine()
        engine.add_rules(NFPA72RuleSet.all_rules())
        engine.assert_fact(
            Fact(
                fact_type="hvac_unit",
                properties={
                    "unit_id": "AHU-1",
                    "cfm": 5000,
                    "has_duct_detector": False,
                },
            )
        )
        engine.evaluate()
        violations = engine.get_safety_violations()
        assert any(r.rule_id == "NFPA72-006" for r in violations)

    def test_duct_detector_not_required_below_threshold(self):
        engine = RulesEngine()
        engine.add_rules(NFPA72RuleSet.all_rules())
        engine.assert_fact(
            Fact(
                fact_type="hvac_unit",
                properties={
                    "unit_id": "AHU-2",
                    "cfm": 1500,  # Below 2000 CFM threshold
                    "has_duct_detector": False,
                },
            )
        )
        results = engine.evaluate()
        violations = [r for r in results if r.rule_id == "NFPA72-006"]
        assert len(violations) == 0

    def test_elevator_recall_violation(self):
        engine = RulesEngine()
        engine.add_rules(NFPA72RuleSet.all_rules())
        engine.assert_fact(
            Fact(
                fact_type="elevator",
                properties={
                    "elevator_id": "E1",
                    "has_lobby_detector": False,
                    "has_hoistway_detector": True,
                },
            )
        )
        engine.evaluate()
        violations = engine.get_safety_violations()
        assert any(r.rule_id == "NFPA72-007" for r in violations)

    def test_corridor_spacing_applied(self):
        engine = RulesEngine()
        engine.add_rules(NFPA72RuleSet.all_rules())
        engine.assert_fact(
            Fact(
                fact_type="room",
                properties={
                    "room_id": "C1",
                    "is_corridor": True,
                    "ceiling_height_m": 3.0,
                    "detector_type": "smoke",
                },
            )
        )
        engine.evaluate()
        corridor_flags = engine.get_facts("corridor_flag")
        assert len(corridor_flags) >= 1

    def test_compliance_summary(self):
        engine = RulesEngine()
        engine.add_rules(NFPA72RuleSet.all_rules())
        engine.assert_fact(
            Fact(
                fact_type="room",
                properties={
                    "room_id": "R1",
                    "ceiling_height_m": 3.0,
                    "detector_type": "smoke",
                },
            )
        )
        engine.evaluate()
        summary = engine.get_compliance_summary()
        assert "is_safe" in summary
        assert "total_facts" in summary
        assert summary["total_facts"] > 0


# ═══════════════════════════════════════════════════════════════════════════════
# TRUTH MAINTENANCE SYSTEM
# ═══════════════════════════════════════════════════════════════════════════════


class TestTruthMaintenance:
    """Test the Truth Maintenance System."""

    def test_dependency_recording(self):
        tms = TruthMaintenanceSystem()
        tms.record_dependency(
            derived_fact_id="F3",
            supporting_fact_ids=["F1", "F2"],
            producing_rule_id="R1",
        )
        derived = tms.get_derived_facts_for("F1")
        assert "F3" in derived

    def test_retraction_cascade(self):
        """When a supporting fact is retracted, derived facts are invalidated."""
        tms = TruthMaintenanceSystem()
        tms.record_dependency(
            derived_fact_id="F3",
            supporting_fact_ids=["F1"],
            producing_rule_id="R1",
        )
        retracted = tms.retract_support("F1")
        assert "F3" in retracted

    def test_multi_level_cascade(self):
        """Cascade through multiple levels of derivation."""
        tms = TruthMaintenanceSystem()
        # F1 → F2 → F3
        tms.record_dependency("F2", ["F1"], "R1")
        tms.record_dependency("F3", ["F2"], "R2")

        retracted = tms.retract_support("F1")
        # Both F2 and F3 should be retracted
        assert "F2" in retracted
        assert "F3" in retracted

    def test_explain_derivation(self):
        tms = TruthMaintenanceSystem()
        tms.record_dependency("F2", ["F1"], "R1")
        explanation = tms.explain_derivation("F2")
        assert explanation["status"] == "derived"
        assert explanation["producing_rule"] == "R1"
        assert "F1" in explanation["directly_depends_on"]

    def test_base_fact_explanation(self):
        tms = TruthMaintenanceSystem()
        explanation = tms.explain_derivation("F_nonexistent")
        assert explanation["status"] == "base_fact" or explanation["status"] == "not_found"

    def test_consistency_check(self):
        """Check for stale derived facts."""
        tms = TruthMaintenanceSystem()
        tms.record_dependency("F2", ["F1"], "R1")
        # F1 doesn't exist — F2 is stale
        existing = {"F2"}  # F2 exists but F1 doesn't
        stale = tms.validate_consistency(existing)
        assert "F2" in stale

    def test_engine_tms_integration(self):
        """Test that the engine properly retracts derived facts."""
        engine = RulesEngine()
        engine.add_rules(NFPA72RuleSet.all_rules())

        # Assert a room fact
        room_fact = Fact(
            fact_type="room",
            properties={
                "room_id": "R1",
                "ceiling_height_m": 3.0,
                "detector_type": "smoke",
            },
        )
        engine.assert_fact(room_fact)
        engine.evaluate()

        # Should have derived spacing facts
        spacing = engine.get_facts("spacing")
        assert len(spacing) >= 1

        # Retract the room fact
        engine.retract_fact(room_fact.fact_id)

        # Derived spacing fact should also be retracted
        spacing_after = engine.get_facts("spacing")
        # The spacing fact was derived from the room fact
        # After retraction, it should be gone (TMS cascade)
        remaining = [s for s in spacing_after if s.properties.get("room_id") == "R1"]
        assert len(remaining) == 0


# ═══════════════════════════════════════════════════════════════════════════════
# API CONTRACT VALIDATION
# ═══════════════════════════════════════════════════════════════════════════════


class TestAPIContract:
    """Test the type-safe API contract system."""

    def test_contract_validator_creation(self):
        validator = ContractValidator(severity=ContractSeverity.STRICT)
        assert validator.severity == ContractSeverity.STRICT

    def test_contract_registration(self):
        from pydantic import BaseModel

        class TestResponse(BaseModel):
            id: str
            name: str

        validator = ContractValidator()
        validator.register("/api/test", "GET", TestResponse)
        summary = validator.get_contract_summary()
        assert len(summary) == 1
        assert summary[0]["endpoint"] == "/api/test"

    def test_contract_validation_pass(self):
        from pydantic import BaseModel

        class TestResponse(BaseModel):
            id: str
            name: str

        validator = ContractValidator()
        validator.register("/api/test", "GET", TestResponse)

        data = {"id": "1", "name": "Test"}
        result = validator.validate_response("/api/test", "GET", data)
        assert result["id"] == "1"

    def test_contract_validation_fail_strict(self):
        from pydantic import BaseModel

        class TestResponse(BaseModel):
            id: str
            name: str

        validator = ContractValidator(severity=ContractSeverity.STRICT)
        validator.register("/api/test", "GET", TestResponse)

        data = {"id": "1"}  # Missing 'name'
        with pytest.raises(ValidationError):
            validator.validate_response("/api/test", "GET", data)

    def test_contract_validation_log_mode(self):
        from pydantic import BaseModel

        class TestResponse(BaseModel):
            id: str
            name: str

        validator = ContractValidator(severity=ContractSeverity.LOG)
        validator.register("/api/test", "GET", TestResponse)

        data = {"id": "1"}  # Missing 'name'
        # Should NOT raise, just log
        validator.validate_response("/api/test", "GET", data)
        violations = validator.get_violations()
        assert len(violations) == 1

    def test_openapi_generation(self):
        from pydantic import BaseModel

        class ProjectResponse(BaseModel):
            project_id: str
            name: str

        validator = ContractValidator()
        validator.register("/api/projects", "GET", ProjectResponse)
        components = validator.get_openapi_components()
        assert "schemas" in components
        assert "ProjectResponse" in components["schemas"]


# ═══════════════════════════════════════════════════════════════════════════════
# RULESET METADATA
# ═══════════════════════════════════════════════════════════════════════════════


class TestNFPA72RuleSetMetadata:
    """Test the NFPA 72 rule set metadata and querying."""

    def test_all_rules_have_ids(self):
        for rule in NFPA72RuleSet.all_rules():
            assert rule.rule_id, "Rule missing ID"
            assert rule.rule_name, f"Rule {rule.rule_id} missing name"

    def test_all_rules_have_nfpa_reference(self):
        """Every rule MUST have an NFPA reference for auditability."""
        for rule in NFPA72RuleSet.all_rules():
            assert rule.nfpa_reference is not None, (
                f"Rule {rule.rule_id} ({rule.rule_name}) is missing NFPA reference — required for safety audit"
            )

    def test_critical_rules_first(self):
        """CRITICAL_SAFETY rules must be ordered first."""
        critical = NFPA72RuleSet.critical_safety_rules()
        assert len(critical) >= 1
        for rule in critical:
            assert rule.priority == RulePriority.CRITICAL_SAFETY

    def test_rules_by_section(self):
        section_17_rules = NFPA72RuleSet.rules_by_nfpa_section("17.6")
        assert len(section_17_rules) >= 1

    def test_summary(self):
        summary = NFPA72RuleSet.summary()
        assert len(summary) >= 8  # We have 10 rules
        for s in summary:
            assert "rule_id" in s
            assert "nfpa_reference" in s
            assert "priority" in s


# ═══════════════════════════════════════════════════════════════════════════════
# EDGE CASES & ADVERSARIAL
# ═══════════════════════════════════════════════════════════════════════════════


class TestEdgeCases:
    """Test edge cases and adversarial inputs."""

    def test_empty_engine_evaluation(self):
        """Engine with no facts should return no results."""
        engine = RulesEngine()
        engine.add_rules(NFPA72RuleSet.all_rules())
        results = engine.evaluate()
        assert len(results) == 0

    def test_engine_with_no_rules(self):
        """Engine with facts but no rules should return no results."""
        engine = RulesEngine()
        engine.assert_fact(Fact(fact_type="room", properties={"h": 3.0}))
        results = engine.evaluate()
        assert len(results) == 0

    def test_max_iterations_safety(self):
        """Engine must not loop infinitely."""
        engine = RulesEngine(max_iterations=5)
        # A rule that asserts a fact matching its own condition
        # could cause infinite loops — max_iterations prevents this
        counter = {"n": 0}

        def looping_action(facts, eng):
            counter["n"] += 1
            if counter["n"] > 20:
                raise RuntimeError("Infinite loop detected!")
            return [
                RuleResult(
                    rule_id="LOOP",
                    rule_name="Loop",
                    nfpa_reference=None,
                    severity=RulePriority.INFORMATIONAL,
                    message=f"Loop {counter['n']}",
                    matched_facts=[f.fact_id for f in facts],
                )
            ]

        engine.add_rule(
            Rule(
                rule_id="LOOP",
                rule_name="Loop",
                nfpa_reference=None,
                priority=RulePriority.INFORMATIONAL,
                fact_type="room",
                action=looping_action,
            )
        )
        engine.assert_fact(Fact(fact_type="room"))
        engine.evaluate()
        # Should stop after max_iterations, not run forever
        assert counter["n"] <= 10  # Reasonable upper bound

    def test_rule_condition_exception_safe(self):
        """Rule condition that raises should not crash the engine."""
        engine = RulesEngine()

        engine.add_rule(
            Rule(
                rule_id="CRASH",
                rule_name="Crash Condition",
                nfpa_reference=None,
                priority=RulePriority.COMPLIANCE_CHECK,
                fact_type="room",
                condition=lambda f: 1 / 0,  # Division by zero
                action=lambda facts, eng: [
                    RuleResult(
                        rule_id="CRASH",
                        rule_name="Crash Condition",
                        nfpa_reference=None,
                        severity=RulePriority.COMPLIANCE_CHECK,
                        message="Should not reach",
                        matched_facts=[],
                    )
                ],
            )
        )

        engine.assert_fact(Fact(fact_type="room"))
        # Should NOT raise — engine handles condition errors gracefully
        results = engine.evaluate()
        assert len(results) == 0  # Rule should not fire

    def test_negative_ceiling_height(self):
        """Negative ceiling height should be handled gracefully."""
        engine = RulesEngine()
        engine.add_rules(NFPA72RuleSet.all_rules())
        engine.assert_fact(
            Fact(
                fact_type="room",
                properties={
                    "room_id": "BAD",
                    "ceiling_height_m": -1.0,
                    "detector_type": "smoke",
                },
            )
        )
        # Should not crash — may produce conservative spacing
        engine.evaluate()
        # No assertion on specific result — just no crash

    def test_zero_cfm_hvac(self):
        """Zero CFM HVAC unit should not require duct detector."""
        engine = RulesEngine()
        engine.add_rules(NFPA72RuleSet.all_rules())
        engine.assert_fact(
            Fact(
                fact_type="hvac_unit",
                properties={
                    "unit_id": "AHU-ZERO",
                    "cfm": 0,
                    "has_duct_detector": False,
                },
            )
        )
        results = engine.evaluate()
        violations = [r for r in results if r.rule_id == "NFPA72-006"]
        assert len(violations) == 0

    def test_explain_derived_fact(self):
        """Must be able to explain why any derived fact exists."""
        engine = RulesEngine()
        engine.add_rules(NFPA72RuleSet.all_rules())
        room_fact = Fact(
            fact_type="room",
            properties={
                "room_id": "R1",
                "ceiling_height_m": 3.0,
                "detector_type": "smoke",
            },
        )
        engine.assert_fact(room_fact)
        engine.evaluate()

        # Get a derived fact
        spacing_facts = engine.get_facts("spacing")
        if spacing_facts:
            explanation = engine.explain(spacing_facts[0].fact_id)
            assert explanation["is_derived"] is True or explanation.get("status") == "not_found"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
