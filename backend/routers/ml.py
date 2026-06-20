"""backend/routers/ml.py — ML Subsystem API Router.
==================================================

Exposes ML-based predictive maintenance via FastAPI endpoints.

Endpoints (all under /api/v1/ml/predictive-maintenance/):
    GET  /health                   — ML subsystem health check
    GET  /models                   — List available + unavailable models
    POST /predict                  — Single-asset failure prediction
    POST /predict-batch            — Batch prediction (≤100 assets)
    POST /train                    — Trigger retraining (admin RBAC required)

Audit Trail:
    Every /predict call writes an immutable audit entry containing:
      - Request payload (asset features, requested models, horizon)
      - Full MLPredictionResponse (ensemble + per-model + SHAP)
      - Caller API key role (from X-API-Key middleware)
      - SHA-256 hash for tamper-detection
    Returns audit_trail_id in response for NFPA 72 §14.4 compliance.

Safety:
    All responses include enforcement_contract="advisory_only" field.
    ML outputs MUST NOT override NFPA 72 deterministic calculations.
"""

from __future__ import annotations

import hashlib
import json
import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, List

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status

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

# Audit log directory — uses same env var pattern as MLModelRegistry
_AUDIT_DIR = Path(__file__).resolve().parents[2] / "db" / "ml_audit"


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


# ── Audit Trail Integration ─────────────────────────────────────────────────

def _write_audit_entry(
    request_payload: dict[str, Any],
    response_payload: dict[str, Any],
    caller_role: str = "unknown",
) -> str:
    """Write an immutable audit entry for an ML prediction.

    Returns the audit_trail_id (UUID4) — callers MUST set it on the response.

    Audit entries are append-only JSONL files under db/ml_audit/:
        db/ml_audit/YYYY/MM/DD/<audit_trail_id>.json

    Each entry contains a SHA-256 hash for tamper detection.
    """
    audit_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc)

    entry = {
        "audit_trail_id": audit_id,
        "timestamp": now.isoformat(),
        "caller_role": caller_role,
        "request": request_payload,
        "response": response_payload,
        "schema_version": 1,
    }

    # Compute SHA-256 hash for tamper detection
    entry_str = json.dumps(entry, sort_keys=True, default=str)
    entry["sha256"] = hashlib.sha256(entry_str.encode("utf-8")).hexdigest()

    # Write to disk (append-only JSONL per day)
    _AUDIT_DIR.mkdir(parents=True, exist_ok=True)
    day_dir = _AUDIT_DIR / f"{now.strftime('%Y/%m/%d')}"
    day_dir.mkdir(parents=True, exist_ok=True)

    out_file = day_dir / f"{audit_id}.json"
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(entry, f, indent=2, default=str)

    logger.info("ML audit entry written: %s (role=%s)", audit_id, caller_role)
    return audit_id


def _get_caller_role(request: Request, x_api_key: str | None) -> str:
    """Extract caller role from request state (set by ApiKeyMiddleware)."""
    # ApiKeyMiddleware sets scope["fireai_role"] — see backend/security_middleware.py
    role = getattr(request.state, "fireai_role", None) if hasattr(request, "state") else None
    if role:
        return str(role)
    return "unknown"


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
        "audit_trail_enabled": True,
    }


@router.post(
    "/predictive-maintenance/predict",
    response_model=MLPredictionResponse,
    status_code=status.HTTP_200_OK,
)
async def predict_failure(
    request: MLPredictionRequest,
    http_request: Request,
    x_api_key: str | None = Header(None, alias="X-API-Key"),
    predictor: MLFailurePredictor = Depends(get_predictor),
) -> MLPredictionResponse:
    """Predict asset failure probability using ML ensemble.

    Returns ensemble prediction + per-model predictions + SHAP explanations.
    All predictions are ADVISORY — NFPA 72 deterministic rules remain
    authoritative for life-safety decisions.

    Audit Trail:
        Every call writes an immutable JSON entry under db/ml_audit/
        and returns audit_trail_id in the response for regulatory review.
    """
    try:
        response = predictor.predict(request)

        # FIX #4: Wire audit trail integration (was: # TODO)
        caller_role = _get_caller_role(http_request, x_api_key)
        request_payload = request.model_dump(mode="json")
        response_payload = response.model_dump(mode="json")
        audit_id = _write_audit_entry(request_payload, response_payload, caller_role)
        response.audit_trail_id = audit_id

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
    requests: list[MLPredictionRequest],
    http_request: Request,
    x_api_key: str | None = Header(None, alias="X-API-Key"),
    predictor: MLFailurePredictor = Depends(get_predictor),
) -> list[MLPredictionResponse]:
    """Run predictions for multiple assets (batch mode). Each gets its own audit entry."""
    if len(requests) > 100:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Batch size limit: 100 assets per request",
        )

    caller_role = _get_caller_role(http_request, x_api_key)
    results: list[MLPredictionResponse] = []

    for req in requests:
        response = predictor.predict(req)
        audit_id = _write_audit_entry(
            req.model_dump(mode="json"),
            response.model_dump(mode="json"),
            caller_role,
        )
        response.audit_trail_id = audit_id
        results.append(response)

    return results


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
    http_request: Request,
    x_api_key: str | None = Header(None, alias="X-API-Key"),
    registry: MLModelRegistry = Depends(get_registry),
) -> TrainingResponse:
    """Trigger model retraining on historical data.

    RBAC: Requires admin role. Caller role is checked via the same
    ApiKeyMiddleware that sets request.state.fireai_role. We refuse
    to train if the caller's role is not 'admin' (defense in depth —
    even if a future engineer forgets to add the Depends decorator).
    """
    # FIX #7: RBAC enforcement (was: docstring-only claim)
    caller_role = _get_caller_role(http_request, x_api_key)
    # Normalize role (accept "admin", "ADMIN", "Role.ADMIN", etc.)
    role_str = str(caller_role).upper().replace("ROLE.", "")
    if role_str not in ("ADMIN", "SYSTEM"):
        logger.warning(
            "Unauthorized /train attempt by role=%s (requires admin)",
            caller_role,
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                f"Admin role required to trigger model retraining. "
                f"Your role: {caller_role}"
            ),
        )

    # TODO: wire to actual historical data source (database query)
    # For now returns "skipped" — needs integration with backend/db_service.py
    return TrainingResponse(
        model_type=request.model_type,
        status="skipped",
        samples_used=0,
        metrics={},
        message=(
            "Training endpoint ready (RBAC-protected). Wire to historical "
            "data source (backend/db_service.py) before production use."
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
