"""Composite Engineering Risk Field (CERF) - 4D Risk Tensor System."""

from core.risk_tensor.tensor_types import RiskTensor, ImpactVector, SpatialPoint, CompositeRiskIndex
from core.risk_tensor.tensor_builder import build_risk_tensor
from core.risk_tensor.aggregator import aggregate_tensors
from core.risk_tensor.engine import run_composite_risk_analysis

__all__ = [
    "RiskTensor",
    "ImpactVector",
    "SpatialPoint",
    "CompositeRiskIndex",
    "build_risk_tensor",
    "aggregate_tensors",
    "run_composite_risk_analysis"
]