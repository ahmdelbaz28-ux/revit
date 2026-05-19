from typing import List
from core.compliance_engine.base_rule import Rule, Violation
from core.compliance_engine.compliance_context import ComplianceContext


class CoverageRule(Rule):
    rule_id = "NFPA72-17.6.3.1-COVERAGE"
    source = "NFPA 72"
    version = "2022"
    severity = "CRITICAL"
    category = "coverage"
    description = "Detector coverage shall be at least 90% of room area"
    applicable_room_types = []

    def evaluate(self, context: ComplianceContext) -> List[Violation]:
        violations = []
        coverage = context.get_coverage()
        min_coverage = context.constraints.get("min_coverage", 0.90)

        if coverage < min_coverage:
            violations.append(Violation(
                rule_id=self.rule_id,
                severity=self.severity,
                room_id=context.room.get("id", "unknown"),
                message=f"Coverage {coverage:.1%} below required {min_coverage:.0%}",
                recommendation="Increase detector density or adjust placement to achieve 90% coverage"
            ))

        return violations