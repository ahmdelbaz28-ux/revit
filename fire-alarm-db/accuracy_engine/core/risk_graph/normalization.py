from typing import List
from core.risk_graph.risk_types import RiskContribution


def normalize_risks(contributions: List[RiskContribution]) -> List[RiskContribution]:
    if not contributions:
        return contributions

    correlations = {
        ("NFPA72-17.6.3.1-COVERAGE", "NFPA72-17.6.3-SPACING"): 0.4,
        ("NFPA72-17.6.3.1-COVERAGE", "NFPA72-17.7.1-REDUNDANCY"): 0.6,
        ("NFPA72-17.6.3-SPACING", "NFPA72-17.7.1-REDUNDANCY"): 0.2,
    }

    normalized = []
    for c in contributions:
        adjusted = RiskContribution(
            rule_id=c.rule_id,
            probability_violation=c.probability_violation,
            severity_impact=c.severity_impact,
            spatial_weight=c.spatial_weight,
            confidence=c.confidence
        )

        for other in contributions:
            if other.rule_id != c.rule_id:
                corr_key = (c.rule_id, other.rule_id)
                corr_key_rev = (other.rule_id, c.rule_id)
                correlation = correlations.get(corr_key, correlations.get(corr_key_rev, 0.0))

                if correlation > 0:
                    adjusted.probability_violation = min(1.0, adjusted.probability_violation * (1 + correlation * 0.3))
                    adjusted.severity_impact = min(1.0, adjusted.severity_impact * (1 + correlation * 0.2))

        normalized.append(adjusted)

    return normalized