# FireAI ML Subsystem — Documentation

## Overview

The `fireai/ml/` module is a **Machine Learning subsystem** for the FireAI
Digital Twin platform. It provides **ML-based predictive maintenance** that
**complements** (not replaces) the existing statistical engine in
`fireai/analytics/predictive_maintenance.py`.

This module implements the **Q4 2026 Roadmap** item: *"AI-Powered Features →
Predictive maintenance scheduling"*.

## Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                     fireai/ml/ Subsystem                            │
├─────────────────────────────────────────────────────────────────────┤
│  API Layer (FastAPI)                                                │
│  └─ backend/routers/ml.py → /api/ml/predictive-maintenance/*       │
├─────────────────────────────────────────────────────────────────────┤
│  Orchestrator                                                       │
│  └─ fireai/ml/predictive_maintenance.py → MLFailurePredictor       │
│     ├─ Runs requested models in ensemble                           │
│     ├─ Combines predictions (weighted average)                     │
│     └─ Cross-references statistical baseline                       │
├─────────────────────────────────────────────────────────────────────┤
│  Feature Engineering                                                │
│  └─ fireai/ml/feature_engineering.py → FeatureEngineer             │
│     ├─ Age, age_ratio, MTBF                                         │
│     ├─ Failure counts in time windows                              │
│     └─ Weekly event sequence (LSTM input)                          │
├─────────────────────────────────────────────────────────────────────┤
│  Models (Plug-in Architecture)                                      │
│  ├─ fireai/ml/models/xgboost_model.py → XGBoostFailureModel        │
│  ├─ fireai/ml/models/lstm_model.py     → LSTMFailureModel          │
│  └─ fireai/ml/models/cox_model.py      → CoxPHFailureModel         │
├─────────────────────────────────────────────────────────────────────┤
│  Explainability (Safety-Critical)                                   │
│  └─ fireai/ml/explainers/shap_explainer.py → SHAPExplainer          │
│     ├─ TreeExplainer for XGBoost                                   │
│     ├─ Cox PH hazard ratios                                        │
│     └─ Feature ablation for LSTM                                   │
├─────────────────────────────────────────────────────────────────────┤
│  Schemas (Pydantic + TypeScript)                                    │
│  └─ fireai/ml/schemas.py + frontend/src/services/mlApi.ts          │
└─────────────────────────────────────────────────────────────────────┘
```

## Library Selection (from awesome-machine-learning)

Each library was chosen from the curated list at
https://github.com/josephmisiti/awesome-machine-learning:

| Library | awesome-ML Section | Why Selected |
|---------|-------------------|--------------|
| **XGBoost** | Python → General-Purpose ML | Industry standard for tabular failure prediction; native SHAP support |
| **LightGBM** | Python → General-Purpose ML | Faster alternative for large datasets |
| **scikit-learn** | Python → General-Purpose ML | Train/test split, metrics, preprocessing primitives |
| **SHAP** | Python → General-Purpose ML | Mandatory for safety-critical ML (IEC 61508); game-theoretic explanations |
| **Prophet** | Python → General-Purpose ML | Facebook's seasonal time-series forecasting |
| **statsmodels** | Python → General-Purpose ML | ARIMA, Holt-Winters (complements existing analytics) |
| **lifelines** | Python → **Survival Analysis** | Gold standard for censored time-to-event data (Cox PH, Kaplan-Meier) |
| **PyTorch** | Python → General-Purpose ML | LSTM for sequential event pattern learning |

## Safety Architecture

### Advisory-Only Principle
ML predictions are **ADVISORY ONLY**. The deterministic NFPA 72 calculations
in `fireai/core/nfpa72_*.py` remain authoritative for all life-safety
decisions. ML outputs inform maintenance scheduling, not compliance
determinations.

### Audit Trail Integration
Every ML prediction MUST carry:
1. Per-model SHAP explanation (stored alongside prediction)
2. Statistical baseline cross-reference (from `fireai/analytics/`)
3. Advisory notice text
4. Audit trail ID (for NFPA 72 §14.4 compliance)

### Graceful Degradation
If any ML library is unavailable:
- Model returns fallback prediction (`is_fallback: true`)
- Predictor excludes fallback from ensemble weighting
- SHAP explainer returns raw feature values as proxy
- Statistical baseline still computed (uses pure-Python math)

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/ml/predictive-maintenance/health` | ML subsystem health check |
| POST | `/api/ml/predictive-maintenance/predict` | Single-asset prediction |
| POST | `/api/ml/predictive-maintenance/predict-batch` | Batch prediction (≤100 assets) |
| GET | `/api/ml/predictive-maintenance/models` | List available + unavailable models |
| POST | `/api/ml/predictive-maintenance/train` | Trigger model retraining (admin only) |

## Usage Example

### Python (programmatic)
```python
from datetime import datetime, timezone
from fireai.ml import MLFailurePredictor, MLPredictionRequest
from fireai.ml.schemas import AssetFeatures, AssetType, ModelType
from fireai.ml.feature_engineering import FeatureEngineer
from fireai.ml.schemas import MaintenanceEventInput

# Build features
fe = FeatureEngineer()
features = fe.build_features(
    asset_id="DET-001",
    asset_type=AssetType.DETECTOR_SMOKE,
    installation_date=datetime(2018, 6, 1, tzinfo=timezone.utc),
    maintenance_history=[
        MaintenanceEventInput(
            event_id="M1",
            maintenance_type="REPAIR",
            timestamp=datetime(2024, 1, 1, tzinfo=timezone.utc),
        ),
    ],
    environment_rating="corrosive",
)

# Predict
predictor = MLFailurePredictor()
response = predictor.predict(MLPredictionRequest(
    asset=features,
    models=[ModelType.XGBOOST, ModelType.COX_PH],
    explain=True,
    horizon_days=90,
))

print(f"Ensemble: {response.ensemble_failure_probability:.1%}")
print(f"Risk: {response.ensemble_risk_level}")
for pred in response.predictions:
    print(f"  {pred.model_type}: {pred.failure_probability:.1%} (fallback={pred.is_fallback})")
```

### Frontend (React)
See `frontend/src/pages/PredictiveMaintenancePage.tsx` for a complete dashboard
with risk gauge, model comparison chart, and SHAP visualisation.

## Installation

```bash
# P0.3: pyproject.toml is the single source of truth.
# Both requirements.txt and requirements-ml.txt have been removed.
# Install the base package + ML extras in one step:
pip install .[ml]

# Or for development + ML:
pip install .[ml,dev]
```

## Testing

```bash
cd /home/z/my-project
python -m pytest tests/ml/ -v
```

## File Inventory

```
fireai/ml/
├── __init__.py                       # Public API exports
├── schemas.py                        # Pydantic schemas
├── feature_engineering.py            # Raw data → AssetFeatures
├── predictive_maintenance.py         # MLFailurePredictor (orchestrator)
├── models/
│   ├── __init__.py
│   ├── xgboost_model.py              # XGBoost classifier
│   ├── lstm_model.py                 # LSTM time-series forecaster
│   └── cox_model.py                  # Cox PH survival model
└── explainers/
    ├── __init__.py
    └── shap_explainer.py             # SHAP explanations

backend/routers/
└── ml.py                             # FastAPI endpoints

frontend/src/
├── pages/PredictiveMaintenancePage.tsx    # Main dashboard
├── services/mlApi.ts                      # Typed API client
└── components/predictive/
    ├── RiskGauge.tsx                      # Circular probability gauge
    ├── ModelComparisonChart.tsx           # Horizontal bar chart
    └── SHAPExplanation.tsx                # SHAP force plot

tests/ml/
└── test_predictive_maintenance.py    # 14 tests covering all layers
```

## References

- **FireAI Roadmap** (`ROADMAP.md` Q4 2026): AI-Powered Features
- **NFPA 72-2022 §14.4**: Inspection, testing, and maintenance
- **IEC 61508**: Functional safety — ML explainability requirements
- **IEC 61649**: Weibull + Cox PH for reliability analysis
- **awesome-machine-learning**: https://github.com/josephmisiti/awesome-machine-learning
