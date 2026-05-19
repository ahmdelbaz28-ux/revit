from typing import List
from core.compliance_engine.base_rule import Rule, Violation
from core.compliance_engine.compliance_context import ComplianceContext


class RedundancyRule(Rule):
    rule_id = "NFPA72-17.7.1-REDUNDANCY"
    source = "NFPA 72"
    version = "2022"
    severity = "HIGH"
    category = "redundancy"
    description = "Critical areas require overlapping detector coverage"
    applicable_room_types = ["electrical", "server", "control", "mechanical", "storage"]

    def evaluate(self, context: ComplianceContext) -> List[Violation]:
        violations = []

        if not self.is_applicable(context.get_room_type()):
            return violations

        device_count = context.get_device_count()

        if device_count < 2:
            violations.append(Violation(
                rule_id=self.rule_id,
                severity=self.severity,
                room_id=context.room.get("id", "unknown"),
                message=f"Critical room has only {device_count} device(s), minimum 2 required for redundancy",
                recommendation="Add redundant detector to eliminate single point of failure"
            ))

        return violations