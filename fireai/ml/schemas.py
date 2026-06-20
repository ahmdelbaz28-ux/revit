"""
fireai/ml/schemas.py — Pydantic schemas for ML subsystem
==========================================================

All ML inputs/outputs are typed for FastAPI integration.
Designed to be JSON-serialisable for audit_trail storage.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, confloat, conint


# ── Enums (mirror fireai/analytics/predictive_maintenance.py for compat) ─────

class AssetType(str, Enum):
    DETECTOR_SMOKE = "DETECTOR_SMOKE"
    DETECTOR_HEAT = "DETECTOR_HEAT"
    DETECTOR_FLAME = "DETECTOR_FLAME"
    DETECTOR_GAS = "DETECTOR_GAS"
    NAC = "NAC"
    FACP = "FACP"
    SLC_LOOP = "SLC_LOOP"
    BATTERY = "BATTERY"
    CABLE = "CABLE"


class RiskLevel(str, Enum):
    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


class ModelType(str, Enum):
    """Which ML model produced the prediction."""
    XGBOOST = "XGBOOST"
    LIGHTGBM = "LIGHTGBM"
    LSTM = "LSTM"
    PROPHET = "PROPHET"
    COX_PH = "COX_PH"
    ENSEMBLE = "ENSEMBLE"
    FALLBACK_STATISTICAL = "FALLBACK_STATISTICAL"


# ── Input schemas ────────────────────────────────────────────────────────────

class MaintenanceEventInput(BaseModel):
    """A single maintenance/test/failure event for an asset."""
    event_id: str
    maintenance_type: str = Field(
        ..., description="INSPECTION | TEST | REPAIR | REPLACEMENT | CALIBRATION | FAILURE"
    )
    timestamp: datetime
    description: str = ""
    cost: float = 0.0


class AssetFeatures(BaseModel):
    """
    Feature vector for ML-based failure prediction.

    All features are normalised to be model-agnostic so the same vector
    can be fed to XGBoost, LSTM, Prophet, or Cox PH.
    """
    asset_id: str
    asset_type: AssetType
    installation_date: datetime
    manufacturer: str = ""
    model: str = ""
    location: str = ""
    environment_rating: str = "indoor"  # indoor|outdoor|hazardous|cleanroom|corrosive|coastal|desert
    design_life_years: float = 20.0

    # Derived features (computed by feature engineering)
    age_days: float = 0.0
    age_ratio: confloat(ge=0.0, le=2.0) = 0.0  # age / design_life
    recent_failures_90d: conint(ge=0) = 0
    recent_failures_365d: conint(ge=0) = 0
    total_failures: conint(ge=0) = 0
    maintenance_count_365d: conint(ge=0) = 0
    inspection_count_90d: conint(ge=0) = 0
    repair_ratio_365d: confloat(ge=0.0, le=1.0) = 0.0
    mean_time_between_failures_days: Optional[float] = None
    environment_factor: confloat(ge=0.0, le=1.0) = 1.0
    is_battery: bool = False
    is_outdoor: bool = False

    # Time-series features (for LSTM/Prophet)
    recent_event_counts: List[conint(ge=0)] = Field(
        default_factory=list,
        description="Weekly event counts for last 52 weeks (LSTM/Prophet input)"
    )

    # Raw history (for survival analysis)
    maintenance_history: List[MaintenanceEventInput] = Field(default_factory=list)


class MLPredictionRequest(BaseModel):
    """Request body for /api/ml/predictive-maintenance/predict."""
    asset: AssetFeatures
    models: List[ModelType] = Field(
        default=[ModelType.XGBOOST, ModelType.COX_PH],
        description="Which models to run. ENSEMBLE combines all available."
    )
    explain: bool = Field(
        default=True,
        description="Generate SHAP explanations (recommended for audit trail)"
    )
    horizon_days: conint(ge=1, le=365) = Field(
        default=90,
        description="Prediction horizon in days"
    )


# ── Output schemas ───────────────────────────────────────────────────────────

class ModelExplanation(BaseModel):
    """
    SHAP-based explanation for a single model's prediction.

    Critical for safety-critical systems: every ML prediction MUST
    carry an explanation traceable to NFPA 72 audit requirements.
    """
    model_type: ModelType
    base_value: float = Field(..., description="Expected prediction (mean)")
    prediction_value: float = Field(..., description="Actual prediction")
    feature_contributions: Dict[str, float] = Field(
        default_factory=dict,
        description="SHAP value per feature (positive = increases failure risk)"
    )
    top_features: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="Top 5 features by |SHAP|, sorted descending"
    )
    explanation_text: str = Field(
        ..., description="Human-readable explanation in English"
    )


class MLPrediction(BaseModel):
    """A single model's prediction."""
    model_type: ModelType
    failure_probability: confloat(ge=0.0, le=1.0)
    predicted_ttf_days: Optional[float] = None
    confidence_lower: Optional[float] = None
    confidence_upper: Optional[float] = None
    risk_level: RiskLevel
    is_fallback: bool = Field(
        default=False,
        description="True if model was unavailable and statistical fallback used"
    )
    model_version: str = ""
    training_data_size: int = 0
    last_trained_at: Optional[datetime] = None


class MLPredictionResponse(BaseModel):
    """Full response: ensemble prediction + per-model breakdown + explanations."""
    asset_id: str
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    horizon_days: int = 90

    # Ensemble (combined) prediction
    ensemble_failure_probability: confloat(ge=0.0, le=1.0)
    ensemble_risk_level: RiskLevel
    ensemble_ttf_days: Optional[float] = None

    # Per-model predictions
    predictions: List[MLPrediction] = Field(default_factory=list)

    # Explanations (one per model that produced one)
    explanations: List[ModelExplanation] = Field(default_factory=list)

    # Cross-reference to existing statistical engine
    statistical_baseline: Optional[Dict[str, Any]] = Field(
        None,
        description="Output of fireai/analytics/predictive_maintenance.py for comparison"
    )

    # Advisory notice (safety-critical)
    advisory_notice: str = Field(
        default=(
            "ML predictions are ADVISORY ONLY. NFPA 72 deterministic "
            "calculations remain authoritative for life-safety decisions."
        )
    )

    # Audit trail reference
    audit_trail_id: Optional[str] = None


# ── Training schemas ─────────────────────────────────────────────────────────

class TrainingRequest(BaseModel):
    """Trigger model retraining on historical data."""
    model_type: ModelType
    force: bool = False
    min_samples: conint(ge=10) = 50


class TrainingResponse(BaseModel):
    model_type: ModelType
    status: str  # "success" | "skipped" | "failed"
    samples_used: int = 0
    metrics: Dict[str, float] = Field(default_factory=dict)
    trained_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    model_version: str = ""
    message: str = ""
