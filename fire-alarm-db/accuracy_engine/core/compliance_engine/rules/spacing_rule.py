from math import sqrt
from typing import List
from core.compliance_engine.base_rule import Rule, Violation
from core.compliance_engine.compliance_context import ComplianceContext


class DetectorSpacingRule(Rule):
    rule_id = "NFPA72-17.6.3-SPACING"
    source = "NFPA 72"
    version = "2022"
    severity = "HIGH"
    category = "detector_spacing"
    description = "Maximum detector spacing shall not exceed 15 meters"
    applicable_room_types = ["office", "corridor", "meeting", "lobby", "hall", "storage"]

    def evaluate(self, context: ComplianceContext) -> List[Violation]:
        violations = []
        devices = [d for d in context.devices if d.get("room_id") == context.room.get("id")]
        max_spacing = context.constraints.get("max_spacing", 15.0)

        for i, d1 in enumerate(devices):
            for j, d2 in enumerate(devices):
                if j <= i:
                    continue
                dist = sqrt((d1.get("x", 0) - d2.get("x", 0))**2 + (d1.get("y", 0) - d2.get("y", 0))**2)
                if dist > max_spacing:
                    violations.append(Violation(
                        rule_id=self.rule_id,
                        severity=self.severity,
                        room_id=context.room.get("id", "unknown"),
                        message=f"Detector spacing {dist:.1f}m exceeds maximum {max_spacing}m",
                        recommendation="Add additional detector between these two devices"
                    ))

        return violations