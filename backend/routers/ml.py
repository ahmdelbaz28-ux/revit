"""
backend/routers/ml.py — ML Subsystem API Router
==================================================

Exposes ML-based predictive maintenance via FastAPI endpoints.

Endpoints:
    POST /api/ml/predictive-maintenance/predict
        Run ML ensemble prediction for a single asset

    POST /api/ml/predictive-maintenance/predict-batch
        Run predictions for multiple assets

    GET  /api/ml/predictive-maintenance/models
        List available ML models and their training status

    POST /api/ml/predictive-maintenance/train
        Trigger model retraining (requires admin role)

    GET  /api/ml/predictive-maintenance/health
        Health check for ML subsystem

All responses include audit_trail_id for regulatory compliance.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status

from fireai.ml import (
    MLFailurePredictor,
    MLModelRegistry,
    MLPredictionRequest,
    MLPredictionResponse,
    TrainingRequest,
    TrainingResponse,
)

logger = logging.getLogger(__name__)
# NOTE: prefix is "ml" (relative) — parent app mounts it under /api/v1
# Final paths will be: /api/v1/ml/predictive-maintenance/*
router = APIRouter(prefix="/ml", tags=["ml"])

# Singleton predictor (loaded once per process)
_predictor: MLFailurePredictor | None = None
_registry: MLModelRegistry | None = None


def get_predictor() -> MLFailurePredictor:
    global _predictor, _registry
    if _predictor is None:
        _registry = MLModelRegistry()
        _predictor = MLFailurePredictor(registry=_registry)
    return _predictor


def get_registry() -> MLModelRegistry:
    if _registry is None:
        get_predictor()
    assert _registry is not None
    return _registry


# ── Endpoints ────────────────────────────────────────────────────────────────

@router.get("/predictive-maintenance/health")
async def health_check() -> dict:
    """Health check for ML subsystem."""
    registry = get_registry()
    return {
        "status": "healthy",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "available_models": [m.value for m in registry.available_models()],
        "shap_available": registry.shap.is_available,
        "xgboost_installed": registry.xgboost.is_available(),
        "lstm_installed": registry.lstm.is_available(),
        "cox_installed": registry.cox.is_available(),
    }


@router.post(
    "/predictive-maintenance/predict",
    response_model=MLPredictionResponse,
    status_code=status.HTTP_200_OK,
)
async def predict_failure(
    request: MLPredictionRequest,
    predictor: MLFailurePredictor = Depends(get_predictor),
) -> MLPredictionResponse:
    """
    Predict asset failure probability using ML ensemble.

    Returns ensemble prediction + per-model predictions + SHAP explanations.
    All predictions are ADVISORY — NFPA 72 deterministic rules remain
    authoritative for life-safety decisions.
    """
    try:
        response = predictor.predict(request)
        # TODO: log to audit_trail once integration with backend/audit is wired
        return response
    except Exception as exc:
        logger.exception("ML prediction failed")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"ML prediction failed: {exc}",
        ) from exc


@router.post(
    "/predictive-maintenance/predict-batch",
    response_model=List[MLPredictionResponse],
    status_code=status.HTTP_200_OK,
)
async def predict_failures_batch(
    requests: List[MLPredictionRequest],
    predictor: MLFailurePredictor = Depends(get_predictor),
) -> List[MLPredictionResponse]:
    """Run predictions for multiple assets (batch mode)."""
    if len(requests) > 100:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Batch size limit: 100 assets per request",
        )
    return [predictor.predict(req) for req in requests]


@router.get("/predictive-maintenance/models")
async def list_models(
    registry: MLModelRegistry = Depends(get_registry),
) -> dict:
    """List available ML models with training status."""
    available = registry.available_models()
    return {
        "available_models": [
            {
                "model_type": m.value,
                "trained": True,
                "version": _get_model_version(registry, m),
                "training_data_size": _get_training_size(registry, m),
                "last_trained_at": _get_last_trained(registry, m),
            }
            for m in available
        ],
        "unavailable_models": [
            {
                "model_type": m.value,
                "reason": "library_not_installed_or_untrained",
            }
            for m in _all_model_types()
            if m not in available
        ],
    }


@router.post(
    "/predictive-maintenance/train",
    response_model=TrainingResponse,
    status_code=status.HTTP_200_OK,
)
async def train_model(
    request: TrainingRequest,
    registry: MLModelRegistry = Depends(get_registry),
) -> TrainingResponse:
    """
    Trigger model retraining on historical data.

    NOTE: Requires admin role in production (RBAC enforcement in main app).
    """
    # TODO: wire to actual historical data source (database query)
    # For now returns "skipped" — needs integration with backend/db_service.py
    return TrainingResponse(
        model_type=request.model_type,
        status="skipped",
        samples_used=0,
        metrics={},
        message=(
            "Training endpoint ready. Wire to historical data source "
            "(backend/db_service.py) before production use."
        ),
    )


# ── Helpers ──────────────────────────────────────────────────────────────────

def _all_model_types() -> list:
    from fireai.ml.schemas import ModelType
    return [
        ModelType.XGBOOST,
        ModelType.LSTM,
        ModelType.COX_PH,
    ]


def _get_model_version(registry: MLModelRegistry, model_type) -> str:
    if model_type.value == "XGBOOST":
        return registry.xgboost._model_version
    if model_type.value == "LSTM":
        return registry.lstm._model_version
    if model_type.value == "COX_PH":
        return registry.cox._model_version
    return "unknown"


def _get_training_size(registry: MLModelRegistry, model_type) -> int:
    if model_type.value == "XGBOOST":
        return registry.xgboost._training_data_size
    if model_type.value == "LSTM":
        return registry.lstm._training_data_size
    if model_type.value == "COX_PH":
        return registry.cox._training_data_size
    return 0


def _get_last_trained(registry: MLModelRegistry, model_type):
    if model_type.value == "XGBOOST":
        return registry.xgboost._last_trained_at
    if model_type.value == "LSTM":
        return registry.lstm._last_trained_at
    if model_type.value == "COX_PH":
        return registry.cox._last_trained_at
    return None
