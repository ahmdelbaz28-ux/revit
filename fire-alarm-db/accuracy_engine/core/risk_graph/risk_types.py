from dataclasses import dataclass, field
from typing import List, Dict


@dataclass
class RiskDelta:
    rule_id: str
    delta_risk: float
    affected_zones: List[str]
    confidence: float
    spatial_impact: Dict[str, float] = field(default_factory=dict)


@dataclass
class RiskContribution:
    rule_id: str
    probability_violation: float
    severity_impact: float
    spatial_weight: float
    confidence: float
    composite_risk: float = 0.0

    def __post_init__(self):
        self.composite_risk = (
            self.probability_violation * 0.35 +
            self.severity_impact * 0.40 +
            self.spatial_weight * 0.15 +
            (1 - self.confidence) * 0.10
        )


@dataclass
class RiskExposure:
    zone_id: str
    zone_name: str
    base_risk: float
    conditional_risk: float
    failure_scenario_impact: float
    composite_index: float
    risk_level: str
    confidence: float
    contributing_rules: List[str]