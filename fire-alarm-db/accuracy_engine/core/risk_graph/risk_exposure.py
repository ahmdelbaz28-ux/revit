from typing import List
from core.risk_graph.risk_types import RiskContribution, RiskExposure


def calculate_risk_exposure(zone_id: str, zone_name: str, contributions: List[RiskContribution], failure_scenario: dict) -> RiskExposure:
    if not contributions:
        return RiskExposure(
            zone_id=zone_id,
            zone_name=zone_name,
            base_risk=0.0,
            conditional_risk=0.0,
            failure_scenario_impact=0.0,
            composite_index=0.0,
            risk_level="LOW",
            confidence=1.0,
            contributing_rules=[]
        )

    base_risk = sum(c.composite_risk for c in contributions) / len(contributions)

    failed_count = failure_scenario.get("failed_count", 0)
    total = failure_scenario.get("total_devices", 1)
    failure_impact = min(1.0, failed_count / max(total, 1))

    conditional_risk = base_risk * (1 + failure_impact)

    avg_confidence = sum(c.confidence for c in contributions) / len(contributions)
    composite_index = base_risk * 0.3 + conditional_risk * 0.4 + failure_impact * 0.2 + (1 - avg_confidence) * 0.1

    if composite_index >= 0.7:
        risk_level = "CRITICAL"
    elif composite_index >= 0.4:
        risk_level = "HIGH"
    elif composite_index >= 0.2:
        risk_level = "MEDIUM"
    else:
        risk_level = "LOW"

    return RiskExposure(
        zone_id=zone_id,
        zone_name=zone_name,
        base_risk=base_risk,
        conditional_risk=conditional_risk,
        failure_scenario_impact=failure_impact,
        composite_index=composite_index,
        risk_level=risk_level,
        confidence=avg_confidence,
        contributing_rules=[c.rule_id for c in contributions]
    )