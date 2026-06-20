"""
scripts/test_ml_subsystem.py
==============================
Quick smoke test for the ML subsystem — verifies imports + basic flow.
"""

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Add project root to path
ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

print("=" * 70)
print("FireAI ML Subsystem — Smoke Test")
print("=" * 70)

# ── 1. Import test ──────────────────────────────────────────────────────────
print("\n[1/5] Testing imports...")
try:
    from fireai.ml import (
        MLFailurePredictor,
        MLPredictionRequest,
        MLModelRegistry,
        SHAPExplainer,
        AssetFeatures,
        MLPredictionResponse,
        ModelExplanation,
    )
    from fireai.ml.schemas import AssetType, ModelType, RiskLevel, MaintenanceEventInput
    from fireai.ml.feature_engineering import FeatureEngineer
    from fireai.ml.models.xgboost_model import XGBoostFailureModel
    from fireai.ml.models.lstm_model import LSTMFailureModel
    from fireai.ml.models.cox_model import CoxPHFailureModel
    print("  ✓ All imports successful")
except Exception as e:
    print(f"  ✗ Import failed: {e}")
    sys.exit(1)

# ── 2. Feature engineering test ─────────────────────────────────────────────
print("\n[2/5] Testing feature engineering...")
try:
    fe = FeatureEngineer()
    install_date = datetime(2018, 6, 1, tzinfo=timezone.utc)
    now = datetime.now(timezone.utc)
    history = [
        MaintenanceEventInput(
            event_id="M-001",
            maintenance_type="INSPECTION",
            timestamp=install_date + timedelta(days=30),
        ),
        MaintenanceEventInput(
            event_id="M-002",
            maintenance_type="REPAIR",
            timestamp=now - timedelta(days=180),
        ),
    ]
    features = fe.build_features(
        asset_id="DET-SMOKE-001",
        asset_type=AssetType.DETECTOR_SMOKE,
        installation_date=install_date,
        maintenance_history=history,
        environment_rating="corrosive",
        design_life_years=20.0,
    )
    print(f"  ✓ Asset: {features.asset_id}")
    print(f"  ✓ Age: {features.age_days:.0f} days ({features.age_ratio:.2f} ratio)")
    print(f"  ✓ Failures 90d: {features.recent_failures_90d}, 365d: {features.recent_failures_365d}")
    print(f"  ✓ Weekly sequence: {len(features.recent_event_counts)} weeks")
    print(f"  ✓ Environment factor: {features.environment_factor}")
    print(f"  ✓ is_battery: {features.is_battery}, is_outdoor: {features.is_outdoor}")
except Exception as e:
    print(f"  ✗ Feature engineering failed: {e}")
    sys.exit(1)

# ── 3. Model availability check ────────────────────────────────────────────
print("\n[3/5] Checking model availability...")
registry = MLModelRegistry()
print(f"  XGBoost installed: {registry.xgboost.is_available()}")
print(f"  LSTM (PyTorch) installed: {registry.lstm.is_available()}")
print(f"  Cox PH (lifelines) installed: {registry.cox.is_available()}")
print(f"  SHAP installed: {registry.shap.is_available}")
available = registry.available_models()
print(f"  Trained models: {len(available)}")
if available:
    for m in available:
        print(f"    - {m.value}")
else:
    print("    (none — all models in fallback mode)")

# ── 4. Prediction (with fallback) ──────────────────────────────────────────
print("\n[4/5] Testing prediction (fallback mode if no models trained)...")
try:
    predictor = MLFailurePredictor(registry=registry)
    request = MLPredictionRequest(
        asset=features,
        models=[ModelType.XGBOOST, ModelType.COX_PH, ModelType.LSTM],
        explain=True,
        horizon_days=90,
    )
    response = predictor.predict(request)

    print(f"  ✓ Asset ID: {response.asset_id}")
    print(f"  ✓ Ensemble probability: {response.ensemble_failure_probability:.4f}")
    print(f"  ✓ Ensemble risk: {response.ensemble_risk_level.value}")
    print(f"  ✓ Predictions count: {len(response.predictions)}")
    print(f"  ✓ Explanations count: {len(response.explanations)}")
    print(f"  ✓ Statistical baseline: {'present' if response.statistical_baseline else 'absent'}")
    print(f"  ✓ Advisory notice: {len(response.advisory_notice)} chars")

    for pred in response.predictions:
        flag = " (fallback)" if pred.is_fallback else ""
        print(f"    - {pred.model_type.value}: {pred.failure_probability:.2%}{flag}")
except Exception as e:
    print(f"  ✗ Prediction failed: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# ── 5. High-risk scenario test ─────────────────────────────────────────────
print("\n[5/5] Testing high-risk scenario (15-year-old battery in corrosive env)...")
try:
    old_battery = fe.build_features(
        asset_id="BAT-OLD-001",
        asset_type=AssetType.BATTERY,
        installation_date=datetime.now(timezone.utc) - timedelta(days=365 * 15),
        maintenance_history=[],
        environment_rating="corrosive",
        design_life_years=10.0,
    )
    response = predictor.predict(
        MLPredictionRequest(asset=old_battery, explain=False)
    )
    print(f"  ✓ Old battery ensemble probability: {response.ensemble_failure_probability:.4f}")
    print(f"  ✓ Old battery risk level: {response.ensemble_risk_level.value}")
except Exception as e:
    print(f"  ✗ High-risk test failed: {e}")
    sys.exit(1)

print("\n" + "=" * 70)
print("✓ All smoke tests passed!")
print("=" * 70)
print("\nNext steps:")
print("  1. Install ML libraries: pip install -r requirements-ml.txt")
print("  2. Train models on historical data (when DB integration ready)")
print("  3. Start FastAPI backend: uvicorn backend.app:app --reload")
print("  4. Open frontend dashboard at /predictive-maintenance")
