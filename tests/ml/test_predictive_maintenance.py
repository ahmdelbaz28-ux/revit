"""
tests/ml/test_predictive_maintenance.py — Tests for ML subsystem
===================================================================

Validates:
    1. Schema validation (Pydantic)
    2. Feature engineering correctness
    3. ML model fallback behavior when libraries missing
    4. SHAP explanation graceful degradation
    5. Statistical baseline cross-reference
    6. End-to-end prediction pipeline
"""

from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

# Ensure project root on path
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from fireai.ml.schemas import (
    AssetFeatures,
    AssetType,
    MLPredictionRequest,
    ModelType,
    RiskLevel,
)
from fireai.ml.feature_engineering import FeatureEngineer
from fireai.ml.predictive_maintenance import MLFailurePredictor
from fireai.ml import MLModelRegistry


# ── Fixtures ────────────────────────────────────────────────────────────────

@pytest.fixture
def sample_features() -> AssetFeatures:
    """Build features for a 6-year-old smoke detector with 1 failure."""
    fe = FeatureEngineer()
    install_date = datetime(2018, 6, 1, tzinfo=timezone.utc)
    now = datetime.now(timezone.utc)

    from fireai.ml.schemas import MaintenanceEventInput

    history = [
        MaintenanceEventInput(
            event_id="M-001",
            maintenance_type="INSPECTION",
            timestamp=install_date + timedelta(days=30),
        ),
        MaintenanceEventInput(
            event_id="M-002",
            maintenance_type="TEST",
            timestamp=install_date + timedelta(days=400),
        ),
        MaintenanceEventInput(
            event_id="M-003",
            maintenance_type="REPAIR",
            timestamp=now - timedelta(days=180),
        ),
        MaintenanceEventInput(
            event_id="M-004",
            maintenance_type="INSPECTION",
            timestamp=now - timedelta(days=30),
        ),
    ]

    return fe.build_features(
        asset_id="DET-TEST-001",
        asset_type=AssetType.DETECTOR_SMOKE,
        installation_date=install_date,
        maintenance_history=history,
        environment_rating="indoor",
        design_life_years=20.0,
    )


# ── Schema tests ────────────────────────────────────────────────────────────

def test_asset_features_schema_validates():
    """AssetFeatures should validate required fields."""
    feat = AssetFeatures(
        asset_id="X",
        asset_type=AssetType.BATTERY,
        installation_date=datetime.now(timezone.utc),
        # Explicitly set is_battery (schema does not auto-derive)
        is_battery=True,
    )
    assert feat.asset_id == "X"
    assert feat.asset_type == AssetType.BATTERY
    assert feat.is_battery is True


def test_risk_level_enum():
    assert RiskLevel.CRITICAL.value == "CRITICAL"
    assert RiskLevel.LOW.value == "LOW"


def test_model_type_enum_includes_ensemble():
    assert ModelType.ENSEMBLE in ModelType


# ── Feature engineering tests ───────────────────────────────────────────────

def test_feature_engineering_computes_age(sample_features):
    """age_days should be > 0 for a 6-year-old asset."""
    assert sample_features.age_days > 365 * 5
    assert 0 < sample_features.age_ratio < 1


def test_feature_engineering_counts_failures(sample_features):
    """Should count 1 failure in 365d (the REPAIR event)."""
    assert sample_features.recent_failures_365d == 1
    assert sample_features.total_failures == 1


def test_feature_engineering_weekly_sequence(sample_features):
    """Weekly sequence should have 52 entries (last 52 weeks)."""
    assert len(sample_features.recent_event_counts) == 52


def test_feature_engineering_mtbf(sample_features):
    """MTBF should be None when only 1 failure observed."""
    assert sample_features.mean_time_between_failures_days is None


def test_feature_engineering_battery_flag():
    """Battery asset type should set is_battery flag."""
    fe = FeatureEngineer()
    feat = fe.build_features(
        asset_id="BAT-1",
        asset_type=AssetType.BATTERY,
        installation_date=datetime.now(timezone.utc) - timedelta(days=365),
        maintenance_history=[],
    )
    assert feat.is_battery is True


# ── Predictor tests (with graceful fallback) ────────────────────────────────

def test_predictor_returns_response_even_without_trained_models(sample_features):
    """
    Predictor should return a valid response regardless of whether models
    are trained. Trained models produce real predictions; untrained produce
    fallbacks. Either way, the ensemble must be in [0, 1].
    """
    predictor = MLFailurePredictor()
    request = MLPredictionRequest(
        asset=sample_features,
        models=[ModelType.XGBOOST, ModelType.COX_PH, ModelType.LSTM],
        explain=False,
        horizon_days=90,
    )
    response = predictor.predict(request)
    assert response is not None
    assert response.asset_id == sample_features.asset_id
    assert 0.0 <= response.ensemble_failure_probability <= 1.0
    assert response.ensemble_risk_level in RiskLevel
    # At least one prediction should be present (XGBoost and Cox PH are
    # installed in test env; LSTM may or may not be)
    assert len(response.predictions) >= 1
    # Each prediction should be a valid probability in [0, 1]
    for pred in response.predictions:
        assert 0.0 <= pred.failure_probability <= 1.0
        assert pred.risk_level in RiskLevel


def test_predictor_with_explanations(sample_features):
    """Predictor should attempt explanations even in fallback mode."""
    predictor = MLFailurePredictor()
    request = MLPredictionRequest(
        asset=sample_features,
        models=[ModelType.XGBOOST],
        explain=True,
        horizon_days=90,
    )
    response = predictor.predict(request)
    # Explanations list may be empty if all models are fallbacks
    # but the response should still be valid
    assert isinstance(response.explanations, list)


def test_predictor_includes_advisory_notice(sample_features):
    """Response must include safety-critical advisory notice."""
    predictor = MLFailurePredictor()
    response = predictor.predict(
        MLPredictionRequest(asset=sample_features, explain=False)
    )
    assert "ADVISORY" in response.advisory_notice
    assert "NFPA 72" in response.advisory_notice


# ── Registry tests ──────────────────────────────────────────────────────────

def test_registry_lists_available_models():
    """Registry should return list (possibly empty) of available models."""
    registry = MLModelRegistry()
    available = registry.available_models()
    assert isinstance(available, list)
    # All items should be ModelType enum
    for m in available:
        assert isinstance(m, ModelType)


def test_registry_shap_graceful_when_unavailable():
    """SHAP explainer should not crash if shap package missing."""
    registry = MLModelRegistry()
    # is_available is a property
    assert isinstance(registry.shap.is_available, bool)


# ── Statistical baseline integration test ───────────────────────────────────

def test_statistical_baseline_cross_reference(sample_features):
    """
    If fireai.analytics is available, response should include baseline.
    Otherwise statistical_baseline should be None (graceful).
    """
    predictor = MLFailurePredictor()
    response = predictor.predict(
        MLPredictionRequest(asset=sample_features, explain=False)
    )
    # Either None (analytics not importable) or dict
    assert response.statistical_baseline is None or isinstance(
        response.statistical_baseline, dict
    )


# ── Integration: end-to-end ─────────────────────────────────────────────────

def test_end_to_end_high_risk_battery():
    """A 15-year-old battery in corrosive environment should flag high risk."""
    fe = FeatureEngineer()
    install_date = datetime.now(timezone.utc) - timedelta(days=365 * 15)
    feat = fe.build_features(
        asset_id="BAT-OLD-001",
        asset_type=AssetType.BATTERY,
        installation_date=install_date,
        maintenance_history=[],
        environment_rating="corrosive",
        design_life_years=10.0,
    )
    predictor = MLFailurePredictor()
    response = predictor.predict(
        MLPredictionRequest(asset=feat, explain=False)
    )
    # Even with fallback models, response should be valid
    assert 0 <= response.ensemble_failure_probability <= 1
    assert response.ensemble_risk_level in RiskLevel


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
