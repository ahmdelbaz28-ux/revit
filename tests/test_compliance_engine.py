"""
tests/test_compliance_engine.py — ComplianceEngine Unit Tests
=============================================================
PDF Audit Phase 3: Domain Verification

Tests the clause-mapped compliance engine from
fireai/validation/compliance_engine.py against the rules specified
in PDF Appendix B: NFPA 72 / NEC Clause-by-Clause Compliance Matrix.

Each rule must:
  1. Correctly flag NON-COMPLIANT designs
  2. Correctly PASS COMPLIANT designs
  3. Return the correct clause_id and remediation text

Standards Referenced:
  - NFPA 72-2022: National Fire Alarm and Signaling Code
  - NEC (NFPA 70-2023): National Electrical Code
"""

import pytest
from fireai.validation.compliance_engine import ComplianceEngine, ComplianceRule


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def engine():
    """Create a ComplianceEngine instance for testing."""
    return ComplianceEngine()


# ============================================================================
# Rule 1: NFPA 72 §17.6.3.1.2 — Detector Spacing vs. Ceiling Height
# ============================================================================

class TestDetectorSpacingRule:
    """Test spacing compliance per NFPA 72 §17.6.3.1.2."""

    def test_compliant_spacing_passes(self, engine):
        """Spacing within NFPA 72 limits should pass."""
        context = {
            'spacing_m': 9.1,
            'max_spacing_for_height': 9.1,
        }
        violations = engine.validate(context)
        spacing_violations = [v for v in violations
                              if '17.6.3.1.2' in v and 'sloped' not in v.lower()]
        assert len(spacing_violations) == 0, \
            f"Compliant spacing should pass, got: {spacing_violations}"

    def test_excessive_spacing_fails(self, engine):
        """Spacing exceeding max for ceiling height should fail."""
        context = {
            'spacing_m': 10.0,
            'max_spacing_for_height': 9.1,
        }
        violations = engine.validate(context)
        spacing_violations = [v for v in violations
                              if '17.6.3.1.2' in v and 'sloped' not in v.lower()]
        assert len(spacing_violations) > 0, \
            "Excessive spacing should be flagged as non-compliant"


# ============================================================================
# Rule 2: NFPA 72 §17.6.3.1.2(a) — Sloped Ceiling Spacing Reduction
# ============================================================================

class TestSlopedCeilingRule:
    """Test sloped ceiling spacing per NFPA 72 §17.6.3.1.2(a)."""

    def test_sloped_ceiling_within_limit(self, engine):
        """Sloped ceiling spacing <= 6.4m should pass."""
        context = {
            'ceiling_type': 'sloped',
            'spacing_m': 6.4,
        }
        violations = engine.validate(context)
        sloped_violations = [v for v in violations
                             if '17.6.3.1.2(a)' in v]
        assert len(sloped_violations) == 0, \
            f"Sloped ceiling at 6.4m should pass, got: {sloped_violations}"

    def test_sloped_ceiling_exceeds_limit(self, engine):
        """Sloped ceiling spacing > 6.4m should fail."""
        context = {
            'ceiling_type': 'sloped',
            'spacing_m': 9.1,
        }
        violations = engine.validate(context)
        sloped_violations = [v for v in violations
                             if '17.6.3.1.2(a)' in v]
        assert len(sloped_violations) > 0, \
            "Sloped ceiling at 9.1m spacing should be flagged"

    def test_flat_ceiling_not_affected_by_sloped_rule(self, engine):
        """Flat ceiling should never trigger sloped ceiling rule."""
        context = {
            'ceiling_type': 'flat',
            'spacing_m': 9.1,
        }
        violations = engine.validate(context)
        sloped_violations = [v for v in violations
                             if '17.6.3.1.2(a)' in v]
        assert len(sloped_violations) == 0, \
            "Flat ceiling should not trigger sloped rule"


# ============================================================================
# Rule 3: NFPA 72 §17.6.3.1.1 — Coverage >= 99.9%
# ============================================================================

class TestCoverageRule:
    """Test minimum coverage per NFPA 72 §17.6.3.1.1."""

    def test_sufficient_coverage_passes(self, engine):
        """Coverage >= 99.9% should pass."""
        context = {
            'coverage_pct': 99.9,
        }
        violations = engine.validate(context)
        coverage_violations = [v for v in violations if '17.6.3.1.1' in v]
        assert len(coverage_violations) == 0, \
            f"99.9% coverage should pass, got: {coverage_violations}"

    def test_insufficient_coverage_fails(self, engine):
        """Coverage < 99.9% should fail."""
        context = {
            'coverage_pct': 95.0,
        }
        violations = engine.validate(context)
        coverage_violations = [v for v in violations if '17.6.3.1.1' in v]
        assert len(coverage_violations) > 0, \
            "95% coverage should be flagged as non-compliant"


# ============================================================================
# Rule 4: NEC §210.19(A)(1) — Branch Circuit Voltage Drop <= 3%
# ============================================================================

class TestBranchVoltageDropRule:
    """Test branch circuit voltage drop per NEC §210.19(A)(1)."""

    def test_compliant_voltage_drop(self, engine):
        """Voltage drop <= 3% should pass."""
        context = {
            'v_drop_percent': 2.5,
        }
        violations = engine.validate(context)
        branch_violations = [v for v in violations if '210.19' in v]
        assert len(branch_violations) == 0, \
            f"2.5% drop should pass, got: {branch_violations}"

    def test_excessive_voltage_drop(self, engine):
        """Voltage drop > 3% should fail."""
        context = {
            'v_drop_percent': 4.0,
        }
        violations = engine.validate(context)
        branch_violations = [v for v in violations if '210.19' in v]
        assert len(branch_violations) > 0, \
            "4% drop should be flagged as non-compliant"


# ============================================================================
# Rule 5: NEC §215.2(A)(2) — Total Voltage Drop <= 5%
# ============================================================================

class TestTotalVoltageDropRule:
    """Test total voltage drop per NEC §215.2(A)(2).

    Note: The engine uses v_drop_total_percent if provided,
    otherwise falls back to v_drop_percent.
    """

    def test_compliant_total_drop(self, engine):
        """Total voltage drop <= 5% should pass."""
        context = {
            'v_drop_total_percent': 4.0,
        }
        violations = engine.validate(context)
        total_violations = [v for v in violations if '215.2' in v]
        assert len(total_violations) == 0, \
            f"4% total drop should pass, got: {total_violations}"

    def test_excessive_total_drop(self, engine):
        """Total voltage drop > 5% should fail."""
        context = {
            'v_drop_total_percent': 6.0,
        }
        violations = engine.validate(context)
        total_violations = [v for v in violations if '215.2' in v]
        assert len(total_violations) > 0, \
            "6% total drop should be flagged"


# ============================================================================
# Rule 6: NFPA 72 §10.14 — Terminal Voltage >= 16VDC
# ============================================================================

class TestTerminalVoltageRule:
    """Test minimum terminal voltage per NFPA 72 §10.14."""

    def test_sufficient_terminal_voltage(self, engine):
        """Terminal voltage >= 16V should pass."""
        context = {
            'terminal_voltage_v': 20.0,
        }
        violations = engine.validate(context)
        terminal_violations = [v for v in violations if '10.14' in v]
        assert len(terminal_violations) == 0, \
            f"20V terminal should pass, got: {terminal_violations}"

    def test_insufficient_terminal_voltage(self, engine):
        """Terminal voltage < 16V should fail."""
        context = {
            'terminal_voltage_v': 14.0,
        }
        violations = engine.validate(context)
        terminal_violations = [v for v in violations if '10.14' in v]
        assert len(terminal_violations) > 0, \
            "14V terminal should be flagged as non-compliant"


# ============================================================================
# Rule 7: NFPA 92 §6.4.2 — Stairwell Pressure <= 85 Pa
# ============================================================================

class TestStairwellMaxPressureRule:
    """Test maximum stairwell pressure per NFPA 92 §6.4.2.

    Note: The engine uses design_pressure_pa, NOT stairwell_pressure_pa.
    """

    def test_pressure_within_limit(self, engine):
        """Pressure <= 85 Pa should pass."""
        context = {
            'design_pressure_pa': 50.0,
        }
        violations = engine.validate(context)
        pressure_violations = [v for v in violations if '6.4.2' in v]
        assert len(pressure_violations) == 0, \
            f"50 Pa should pass, got: {pressure_violations}"

    def test_excessive_pressure(self, engine):
        """Pressure > 85 Pa should fail (door entrapment risk)."""
        context = {
            'design_pressure_pa': 100.0,
        }
        violations = engine.validate(context)
        pressure_violations = [v for v in violations if '6.4.2' in v]
        assert len(pressure_violations) > 0, \
            "100 Pa should be flagged (door entrapment risk)"


# ============================================================================
# Rule 8: NFPA 92 §6.4 — Stairwell Pressure >= 25 Pa
# ============================================================================

class TestStairwellMinPressureRule:
    """Test minimum stairwell pressure per NFPA 92 §6.4.

    Note: This rule only applies when pressurization_required=True.
    """

    def test_sufficient_min_pressure(self, engine):
        """Pressure >= 25 Pa with pressurization should pass."""
        context = {
            'design_pressure_pa': 30.0,
            'pressurization_required': True,
        }
        violations = engine.validate(context)
        # Find min pressure violations (not max pressure)
        min_violations = [v for v in violations
                          if 'NFPA92:6.4' in v and '6.4.2' not in v]
        assert len(min_violations) == 0, \
            f"30 Pa should pass, got: {min_violations}"

    def test_insufficient_min_pressure(self, engine):
        """Pressure < 25 Pa with pressurization should fail."""
        context = {
            'design_pressure_pa': 15.0,
            'pressurization_required': True,
        }
        violations = engine.validate(context)
        min_violations = [v for v in violations
                          if 'NFPA92:6.4' in v and '6.4.2' not in v]
        assert len(min_violations) > 0, \
            "15 Pa should be flagged (smoke infiltration risk)"

    def test_no_pressurization_not_flagged(self, engine):
        """Without pressurization, min pressure rule should not trigger."""
        context = {
            'design_pressure_pa': 0,
            'pressurization_required': False,
        }
        violations = engine.validate(context)
        min_violations = [v for v in violations
                          if 'NFPA92:6.4' in v and '6.4.2' not in v]
        assert len(min_violations) == 0, \
            "No pressurization should not trigger min pressure rule"


# ============================================================================
# validate_and_report method
# ============================================================================

class TestValidateAndReport:
    """Test the structured report method."""

    def test_report_contains_expected_keys(self, engine):
        """validate_and_report should return a structured dict."""
        context = {
            'spacing_m': 9.1,
            'max_spacing_for_height': 9.1,
            'coverage_pct': 99.9,
        }
        report = engine.validate_and_report(context)
        assert 'passed' in report
        assert 'violations' in report
        assert 'violation_count' in report
        assert 'rules_checked' in report
        assert 'compliance_percentage' in report
        assert isinstance(report['violations'], list)
        assert isinstance(report['violation_count'], int)
        assert report['rules_checked'] == len(engine.rules)

    def test_compliance_percentage_calculation(self, engine):
        """Compliance percentage should be correct."""
        context = {}
        report = engine.validate_and_report(context)
        expected_pct = round(
            (1 - report['violation_count'] / len(engine.rules)) * 100, 1
        )
        assert report['compliance_percentage'] == expected_pct


# ============================================================================
# Engine Construction
# ============================================================================

class TestEngineConstruction:
    """Test ComplianceEngine initialization."""

    def test_engine_has_rules(self, engine):
        """Engine must have at least 10 rules."""
        assert len(engine.rules) >= 10, \
            f"Engine should have >=10 rules, got {len(engine.rules)}"

    def test_all_rules_have_required_fields(self, engine):
        """Every rule must have clause_id, description, validator, remediation."""
        for rule in engine.rules:
            assert hasattr(rule, 'clause_id'), f"Rule missing clause_id: {rule}"
            assert hasattr(rule, 'description'), f"Rule missing description: {rule}"
            assert hasattr(rule, 'validator'), f"Rule missing validator: {rule}"
            assert hasattr(rule, 'remediation'), f"Rule missing remediation: {rule}"
            assert callable(rule.validator), f"Rule validator not callable: {rule}"

    def test_all_clause_ids_are_unique(self, engine):
        """Every rule must have a unique clause_id."""
        ids = [rule.clause_id for rule in engine.rules]
        assert len(ids) == len(set(ids)), \
            f"Duplicate clause_ids found: {[x for x in ids if ids.count(x) > 1]}"

    def test_severity_values(self, engine):
        """Every rule must have a valid severity."""
        valid_severities = {"CRITICAL", "HIGH", "MEDIUM", "LOW"}
        for rule in engine.rules:
            assert rule.severity in valid_severities, \
                f"Invalid severity '{rule.severity}' in rule {rule.clause_id}"
