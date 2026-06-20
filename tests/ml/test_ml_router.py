"""
tests/ml/test_ml_router.py — FastAPI Router Integration Tests
================================================================

Tests the actual /api/v1/ml/* endpoints via FastAPI TestClient.
Validates:
    1. API key authentication
    2. Health endpoint
    3. Models list endpoint
    4. Predict endpoint (single asset)
    5. Predict-batch endpoint
    6. Error handling (invalid input)
"""

from __future__ import annotations

import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# Set test API key BEFORE importing app
os.environ["FIREAI_API_KEY"] = "test-ml-router-key-1234567890abcdef"
os.environ["FIREAI_ENV"] = "development"


@pytest.fixture(scope="module")
def client():
    """FastAPI test client with valid API key configured."""
    from fastapi.testclient import TestClient
    import importlib
    app_module = importlib.import_module("backend.app")
    client = TestClient(app_module.app)
    client.headers.update({"X-API-Key": os.environ["FIREAI_API_KEY"]})
    return client


# ── Health endpoint ─────────────────────────────────────────────────────────

def test_health_returns_200(client):
    r = client.get("/api/v1/ml/predictive-maintenance/health")
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "healthy"
    assert "available_models" in data
    assert "shap_available" in data
    assert isinstance(data["available_models"], list)


def test_health_requires_api_key():
    """Without X-API-Key, should return 401."""
    from fastapi.testclient import TestClient
    import importlib
    app_module = importlib.import_module("backend.app")
    test_client = TestClient(app_module.app)
    r = test_client.get("/api/v1/ml/predictive-maintenance/health")
    assert r.status_code == 401


# ── Models endpoint ─────────────────────────────────────────────────────────

def test_list_models_returns_structure(client):
    r = client.get("/api/v1/ml/predictive-maintenance/models")
    assert r.status_code == 200
    data = r.json()
    assert "available_models" in data
    assert "unavailable_models" in data
    assert isinstance(data["available_models"], list)
    assert isinstance(data["unavailable_models"], list)


# ── Predict endpoint ────────────────────────────────────────────────────────

VALID_PAYLOAD = {
    "asset": {
        "asset_id": "TEST-DET-001",
        "asset_type": "DETECTOR_SMOKE",
        "installation_date": "2018-06-01T00:00:00Z",
        "manufacturer": "SystemSensor",
        "model": "i3",
        "location": "Building A",
        "environment_rating": "indoor",
        "design_life_years": 20.0,
        "recent_failures_90d": 0,
        "recent_failures_365d": 1,
        "total_failures": 2,
        "maintenance_count_365d": 4,
        "inspection_count_90d": 1,
        "repair_ratio_365d": 0.25,
    },
    "models": ["XGBOOST", "COX_PH"],
    "explain": True,
    "horizon_days": 90,
}


def test_predict_returns_full_response(client):
    r = client.post(
        "/api/v1/ml/predictive-maintenance/predict",
        json=VALID_PAYLOAD,
    )
    assert r.status_code == 200, f"Body: {r.text}"
    data = r.json()

    # Required fields
    assert data["asset_id"] == "TEST-DET-001"
    assert "generated_at" in data
    assert data["horizon_days"] == 90

    # Ensemble
    assert 0.0 <= data["ensemble_failure_probability"] <= 1.0
    assert data["ensemble_risk_level"] in ("LOW", "MEDIUM", "HIGH", "CRITICAL")

    # Per-model
    assert isinstance(data["predictions"], list)
    assert len(data["predictions"]) >= 1
    for pred in data["predictions"]:
        assert 0.0 <= pred["failure_probability"] <= 1.0
        assert pred["risk_level"] in ("LOW", "MEDIUM", "HIGH", "CRITICAL")
        assert pred["model_type"] in ("XGBOOST", "LIGHTGBM", "LSTM", "PROPHET", "COX_PH", "ENSEMBLE", "FALLBACK_STATISTICAL")

    # Explanations (may be empty if SHAP unavailable, but field must exist)
    assert "explanations" in data
    assert isinstance(data["explanations"], list)

    # Safety advisory MUST be present
    assert "advisory_notice" in data
    assert "ADVISORY" in data["advisory_notice"]
    assert "NFPA 72" in data["advisory_notice"]


def test_predict_with_explain_false(client):
    """When explain=False, explanations should be empty list."""
    payload = {**VALID_PAYLOAD, "explain": False}
    r = client.post(
        "/api/v1/ml/predictive-maintenance/predict",
        json=payload,
    )
    assert r.status_code == 200
    data = r.json()
    assert data["explanations"] == []


def test_predict_invalid_asset_type_returns_422(client):
    """Invalid asset_type should fail Pydantic validation."""
    payload = {
        "asset": {
            **VALID_PAYLOAD["asset"],
            "asset_type": "INVALID_TYPE",
        }
    }
    r = client.post(
        "/api/v1/ml/predictive-maintenance/predict",
        json=payload,
    )
    assert r.status_code == 422  # Pydantic validation error


def test_predict_missing_required_field_returns_422(client):
    """Missing asset_id should fail validation."""
    payload = {
        "asset": {
            **VALID_PAYLOAD["asset"],
            "asset_id": None,  # Required field
        }
    }
    r = client.post(
        "/api/v1/ml/predictive-maintenance/predict",
        json=payload,
    )
    assert r.status_code == 422


# ── Batch predict ───────────────────────────────────────────────────────────

def test_predict_batch_returns_list(client):
    payload = [
        {**VALID_PAYLOAD, "asset": {**VALID_PAYLOAD["asset"], "asset_id": "BATCH-1"}},
        {**VALID_PAYLOAD, "asset": {**VALID_PAYLOAD["asset"], "asset_id": "BATCH-2"}},
    ]
    r = client.post(
        "/api/v1/ml/predictive-maintenance/predict-batch",
        json=payload,
    )
    assert r.status_code == 200
    data = r.json()
    assert isinstance(data, list)
    assert len(data) == 2
    assert data[0]["asset_id"] == "BATCH-1"
    assert data[1]["asset_id"] == "BATCH-2"


def test_predict_batch_limit_enforced(client):
    """Batch > 100 should return 400."""
    payload = [
        {**VALID_PAYLOAD, "asset": {**VALID_PAYLOAD["asset"], "asset_id": f"BATCH-{i}"}}
        for i in range(101)
    ]
    r = client.post(
        "/api/v1/ml/predictive-maintenance/predict-batch",
        json=payload,
    )
    assert r.status_code == 400


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
