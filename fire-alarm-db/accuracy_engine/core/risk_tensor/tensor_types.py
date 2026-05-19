from dataclasses import dataclass, field
from typing import List, Dict, Tuple


@dataclass
class ImpactVector:
    coverage_loss: float
    detection_delay_seconds: float
    evacuation_risk_increase: float
    redundancy_loss: float


@dataclass
class SpatialPoint:
    x: float
    y: float
    risk_intensity: float
    zone_id: str


@dataclass
class RiskTensor:
    scenario_id: int
    failure_probability: float
    impact_vector: ImpactVector
    spatial_map: List[SpatialPoint]
    confidence: float
    affected_zones: List[str]
    contributing_rules: List[str]


@dataclass
class CompositeRiskIndex:
    scalar: float
    risk_level: str
    confidence_interval: Tuple[float, float]
    contributing_dimensions: Dict[str, float]
    spatial_heatmap: List[Dict]
    explainability: List[str]