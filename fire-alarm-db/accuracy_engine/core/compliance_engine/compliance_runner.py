from typing import List
from core.compliance_engine.base_rule import Violation
from core.compliance_engine.compliance_context import ComplianceContext
from core.compliance_engine.rule_registry import RuleRegistry


class ComplianceRunner:
    def __init__(self):
        RuleRegistry.initialize()
        self.rules = RuleRegistry.get_all_rules()
        self.all_violations: List[Violation] = []

    def run(self, room: dict, devices: list, validation: dict, constraints: dict = None) -> dict:
        if constraints is None:
            constraints = {
                "max_spacing": 15.0,
                "min_coverage": 0.90,
                "min_exits": 2
            }

        geometry = {
            "polygon": room.get("polygon", []),
            "area": room.get("area", 0),
            "width": room.get("width", 0)
        }

        context = ComplianceContext(
            room=room,
            devices=devices,
            geometry=geometry,
            validation=validation,
            constraints=constraints
        )

        room_violations = []
        for rule in self.rules:
            if rule.is_applicable(context.get_room_type()):
                violations = rule.evaluate(context)
                room_violations.extend(violations)

        self.all_violations.extend(room_violations)

        critical = [v for v in room_violations if v.severity == "CRITICAL"]
        high = [v for v in room_violations if v.severity == "HIGH"]
        medium = [v for v in room_violations if v.severity == "MEDIUM"]

        return {
            "room_id": room.get("id", "unknown"),
            "violations": [
                {
                    "rule_id": v.rule_id,
                    "severity": v.severity,
                    "room_id": v.room_id,
                    "message": v.message,
                    "recommendation": v.recommendation
                }
                for v in room_violations
            ],
            "total_violations": len(room_violations),
            "critical_count": len(critical),
            "high_count": len(high),
            "medium_count": len(medium),
            "passed": len(room_violations) == 0
        }

    def get_summary(self) -> dict:
        total = len(self.all_violations)
        critical = len([v for v in self.all_violations if v.severity == "CRITICAL"])
        high = len([v for v in self.all_violations if v.severity == "HIGH"])

        if critical > 0:
            overall = "REJECTED"
        elif high > 0:
            overall = "CONDITIONAL_APPROVAL"
        elif total > 0:
            overall = "APPROVED_WITH_WARNINGS"
        else:
            overall = "APPROVED"

        return {
            "overall": overall,
            "total_violations": total,
            "critical_violations": critical,
            "high_violations": high,
            "rules_executed": len(self.rules),
            "all_passed": total == 0
        }

    def generate_report(self) -> str:
        summary = self.get_summary()

        report = f"COMPLIANCE STATUS: {summary['overall']}\n"
        report += f"Rules Executed: {summary['rules_executed']}\n"
        report += f"Total Violations: {summary['total_violations']}\n"
        report += f"Critical: {summary['critical_violations']}\n"
        report += f"High: {summary['high_violations']}\n\n"

        if summary['total_violations'] > 0:
            report += "Violations:\n"
            for v in self.all_violations:
                report += f"  [{v.severity}] {v.rule_id}: {v.message}\n"
                report += f"    Recommendation: {v.recommendation}\n"

        return report