"""
fireai/ml/__init__.py — FireAI Machine Learning Subsystem
============================================================

ML-based predictive maintenance that COMPLEMENTS (not replaces) the existing
statistical PredictiveMaintenance engine in fireai/analytics/.

Architecture:
    fireai/analytics/predictive_maintenance.py  ← Weibull + composite (deterministic)
    fireai/ml/predictive_maintenance.py         ← XGBoost + LSTM + SHAP (advisory)

Safety principle:
    ML outputs are ADVISORY only. NFPA 72 deterministic calculations remain
    authoritative. Every ML prediction is logged to audit_trail with SHAP
    explanations for regulatory review.

References:
    - FireAI Roadmap Q4 2026: AI-Powered Features (Predictive Maintenance)
    - NFPA 72-2022 §14.4 (Inspection, testing, maintenance)
    - IEC 61508 (Functional safety — ML explainability requirements)
    - Libraries curated from awesome-machine-learning (josephmisiti/awesome-machine-learning)
"""

from fireai.ml.predictive_maintenance import (
    MLFailurePredictor,
    MLPrediction,
    MLModelRegistry,
)
from fireai.ml.explainers.shap_explainer import SHAPExplainer
from fireai.ml.schemas import (
    AssetFeatures,
    MLPredictionRequest,
    MLPredictionResponse,
    ModelExplanation,
    ModelType,
    RiskLevel,
    TrainingRequest,
    TrainingResponse,
)

__version__ = "1.0.0"

__all__ = [
    "MLFailurePredictor",
    "MLPrediction",
    "MLModelRegistry",
    "SHAPExplainer",
    "AssetFeatures",
    "MLPredictionRequest",
    "MLPredictionResponse",
    "ModelExplanation",
    "ModelType",
    "RiskLevel",
    "TrainingRequest",
    "TrainingResponse",
    "__version__",
]
