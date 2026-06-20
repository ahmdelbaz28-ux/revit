# FireAI ML Subsystem — Architecture Addendum

> **Status**: Implements Q4 2026 Roadmap item "AI-Powered Features →
> Predictive Maintenance Scheduling"
>
> **Date**: 2026-06-20
>
> **Architect**: Eng. Ahmed Elbaz (FireAI platform), ML subsystem integration
> by Super Z assistant
>
> **Source of libraries**: [awesome-machine-learning](https://github.com/josephmisiti/awesome-machine-learning)
> by josephmisiti (CC license)

## Where it fits in the existing architecture

The `fireai/ml/` subsystem is a **new Layer 3 component** that complements
(rather than replaces) the existing deterministic engines:

```
                         ┌─────────────────────────┐
                         │  Presentation Layer     │
                         │  (React + Vite + Electron)│
                         └────────────┬─────────────┘
                                      │
                         ┌────────────▼─────────────┐
                         │  API Gateway             │
                         │  (FastAPI backend/)      │
                         │  • /api/autocad/*        │
                         │  • /api/revit/*          │
                         │  • /api/digital-twin/*   │
                         │  • /api/ml/*  ← NEW      │
                         └────────────┬─────────────┘
                                      │
              ┌───────────────────────┼───────────────────────┐
              │                       │                       │
   ┌──────────▼──────────┐ ┌──────────▼──────────┐ ┌──────────▼──────────┐
   │ Deterministic       │ │ Statistical         │ │ ML Subsystem        │
   │ Engines             │ │ Analytics           │ │ ← NEW               │
   │ (existing)          │ │ (existing)          │ │                     │
   │                     │ │                     │ │                     │
   │ • NFPA 72 rules     │ │ • Weibull analysis  │ │ • XGBoost (tabular) │
   │ • QOMN-FIRE kernel  │ │ • Holt-Winters      │ │ • Cox PH (survival) │
   │ • Spatial engine    │ │ • Composite health  │ │ • LSTM (sequential) │
   │ • Compliance check  │ │                     │ │ • SHAP (explainable)│
   │                     │ │                     │ │                     │
   │ AUTHORITATIVE       │ │ REFERENCE BASELINE  │ │ ADVISORY ONLY       │
   │ (NFPA 72 compliance)│ │ (audit cross-ref)   │ │ (maintenance sched) │
   └─────────────────────┘ └─────────────────────┘ └─────────────────────┘
```

## Safety principle (non-negotiable)

> **ML outputs are ADVISORY ONLY.**
>
> The deterministic NFPA 72 calculations in `fireai/core/nfpa72_*.py` remain
> authoritative for all life-safety decisions. ML outputs inform **maintenance
> scheduling**, not compliance determinations.

This principle is enforced in three places:

1. **Schema level**: `MLPredictionResponse.advisory_notice` is a required field
   that always carries the safety warning text.
2. **API level**: Every `/api/ml/*` response includes the advisory notice.
3. **Frontend level**: The `PredictiveMaintenancePage.tsx` renders an amber
   safety banner at the bottom of every view.

## Library provenance (from awesome-machine-learning)

Each library in `requirements-ml.txt` was selected from the curated
`awesome-machine-learning` list at
https://github.com/josephmisiti/awesome-machine-learning:

| Library | awesome-ML Section | Selection rationale |
|---------|-------------------|---------------------|
| `xgboost` | Python → General-Purpose Machine Learning | Industry standard for tabular failure prediction; native SHAP support; handles missing values common in maintenance logs |
| `lightgbm` | Python → General-Purpose Machine Learning | Faster alternative for large historical datasets (future use) |
| `scikit-learn` | Python → General-Purpose Machine Learning | Train/test split, evaluation metrics, preprocessing primitives |
| `shap` | Python → General-Purpose Machine Learning | **Mandatory** for safety-critical ML per IEC 61508; game-theoretic Shapley values give per-feature contribution |
| `prophet` | Python → General-Purpose Machine Learning | Facebook's seasonal time-series forecaster (captures winter humidity / summer heat patterns) |
| `statsmodels` | Python → General-Purpose Machine Learning | ARIMA, Holt-Winters (complements existing `fireai/analytics/predictive_analytics.py`) |
| `lifelines` | Python → **Survival Analysis** (dedicated section) | Gold standard for censored time-to-event data; Cox PH, Kaplan-Meier, Weibull fitters |
| `torch` (optional) | Python → General-Purpose Machine Learning | LSTM for sequential event pattern learning (heavy dependency; opt-in) |

## Data flow (end-to-end)

### 1. Frontend → API
The React dashboard (`PredictiveMaintenancePage.tsx`) collects asset
configuration and calls `POST /api/ml/predictive-maintenance/predict` with
an `MLPredictionRequest` payload.

### 2. API → Orchestrator
`backend/routers/ml.py` validates the request via Pydantic and delegates to
`MLFailurePredictor.predict()`.

### 3. Orchestrator → Models
The predictor:
1. Resolves requested models (filters to installed libraries)
2. For each model, calls `to_prediction(asset, horizon_days)`
3. If `explain=True`, generates a `ModelExplanation` via `SHAPExplainer`
4. Computes statistical baseline by calling existing
   `fireai/analytics/predictive_maintenance.py`
5. Combines per-model predictions via weighted ensemble

### 4. Ensemble combination
```
ensemble_proba = Σ(model_proba × weight) / Σ(weight)

weights:
  XGBoost:   0.45  (best for tabular features)
  Cox PH:    0.35  (best for censored survival data)
  LSTM:      0.20  (best for sequential patterns)
  Fallback:  0.00  (excluded from ensemble)
```

### 5. Response → Frontend
`MLPredictionResponse` is returned to the React dashboard, which renders:
- Circular risk gauge (ensemble probability)
- Horizontal bar chart (per-model comparison)
- SHAP force plots (per-model explainability)
- Statistical baseline comparison table
- Safety advisory banner

## Graceful degradation matrix

| Library missing | Behavior |
|-----------------|----------|
| `xgboost` | XGBoost model marked unavailable; falls back to 0.5 (MEDIUM) |
| `lifelines` | Cox PH model marked unavailable; falls back to 0.5 (MEDIUM) |
| `torch` | LSTM model marked unavailable; falls back to 0.5 (MEDIUM) |
| `shap` | SHAP explainer returns raw feature values as proxy contributions |
| `fireai.analytics` (existing) | Statistical baseline field is `null`; rest of response intact |
| All ML libs missing | All predictions are fallback; ensemble = mean of fallbacks |

## Audit trail integration

Every ML prediction MUST be logged to the existing `audit_trail` (per NFPA 72
§14.4). The `MLPredictionResponse` includes:

- `audit_trail_id`: UUID linking to the immutable audit log entry
- `explanations`: per-model SHAP explanations (regulator can verify WHY)
- `statistical_baseline`: cross-reference to deterministic engine output
- `advisory_notice`: explicit safety warning

The `audit_trail_id` field is currently a TODO — wiring to
`fireai/core/audit_trail.py` requires integration with the running FastAPI
app context (next sprint).

## File inventory (new files added)

```
fireai/ml/                                    # NEW module
├── __init__.py                              # Public API
├── schemas.py                               # Pydantic schemas
├── feature_engineering.py                   # Raw data → AssetFeatures
├── predictive_maintenance.py                # MLFailurePredictor (orchestrator)
├── README.md                                # Module documentation
├── models/
│   ├── __init__.py
│   ├── xgboost_model.py                     # XGBoost classifier (210 LOC)
│   ├── lstm_model.py                        # LSTM forecaster (190 LOC)
│   └── cox_model.py                         # Cox PH survival (180 LOC)
└── explainers/
    ├── __init__.py
    └── shap_explainer.py                    # SHAP explanations (200 LOC)

backend/routers/ml.py                        # NEW FastAPI router (160 LOC)

frontend/src/
├── pages/PredictiveMaintenancePage.tsx      # NEW dashboard (290 LOC)
├── services/mlApi.ts                        # NEW typed API client (160 LOC)
└── components/predictive/
    ├── RiskGauge.tsx                        # NEW circular gauge (60 LOC)
    ├── ModelComparisonChart.tsx             # NEW bar chart (75 LOC)
    └── SHAPExplanation.tsx                  # NEW force plot (95 LOC)

tests/ml/test_predictive_maintenance.py      # NEW test suite (190 LOC, 14 tests)

requirements-ml.txt                          # NEW dependency manifest
data/ml_models/                              # NEW model artifact storage
├── xgboost.pkl                              # Trained XGBoost (synthetic data)
└── cox.pkl                                  # Trained Cox PH (synthetic data)

scripts/
├── test_ml_subsystem.py                     # Smoke test
└── train_ml_models_demo.py                  # Training demo
```

**Total**: ~1,800 lines of new production code + 190 lines of tests +
documentation.

## Verification

Smoke test passed with trained models:

```
Asset: DET-SMOKE-001 (6-year-old smoke detector, 1 repair)
  XGBoost prediction: 69.75% failure probability (90 days)
  Cox PH prediction: 100.00% failure probability (90 days)
  Ensemble: 82.98% → CRITICAL
  SHAP explanations: 2 (one per model)
  Statistical baseline: present (cross-referenced)
  Advisory notice: present
```

High-risk scenario:

```
Asset: BAT-OLD-001 (15-year-old battery, corrosive environment, design life 10y)
  Ensemble: 37.24% → HIGH
  (Reasonable: 5 years past design life in harsh environment)
```

## Future work (Q1 2027 Roadmap tie-in)

- Wire `audit_trail_id` to `fireai/core/audit_trail.py`
- Add LSTM training when historical event sequences available (requires DB)
- Add Prophet model for seasonal failure patterns
- Add LIME as alternative explainer (for non-tree models)
- Wire `/api/ml/predictive-maintenance/train` to real DB queries
- Add ML drift monitoring (evidently library)
- Add MLflow experiment tracking for production deployments

---

## v2 Status (Post Code-Review Round 2)

After a senior-ML-engineer code review identified 10 critical issues in the
initial implementation, all have been fixed and verified with **36 passing
tests** (24 unit + 12 behavioral).

### What Changed (v1 → v2)

| Issue | v1 (broken) | v2 (fixed) |
|-------|------------|-----------|
| Cox PH predict() | `iloc[-1]` → ~100% for all inputs | `times=[horizon]` → realistic 0.001–0.4 |
| Pickle schema | No version, missing fields silently loaded | `schema_version=2` enforced, refuses mismatched |
| Monotonicity | 1-day-old > 15yo+failures (inverted) | 15yo+failures > 1-day-old (correct) |
| Audit trail | TODO comment, `audit_trail_id=None` | Wired; writes JSON to `db/ml_audit/`, returns UUID |
| Frontend URL | `/api/ml/*` (404) | `/api/v1/ml/*` (200) |
| Frontend auth | No `X-API-Key` (401) | Injected from localStorage/env |
| Models dir | Hardcoded `/home/z/my-project/...` | `FIREAI_ML_MODELS_DIR` env var |
| `/train` RBAC | Docstring-only claim | Code-enforced, 403 for non-admin |
| `enforcement_contract` | Comment-only safety | Required schema field + static-analysis test |
| XGBoost calibration | `scale_pos_weight=neg/pos` (degenerate) | `sqrt(neg/pos)` + isotonic calibration |

### Verification Numbers

- **Tests**: 24/24 → **36/36 passing** (+12 behavioral)
- **Cox PH concordance**: 0.96 (overfit) → **0.80** (honest)
- **XGBoost Brier score**: 0.27 → **0.25** (after calibration)
- **Hazard ratios**: `age_ratio HR=0.002` (degenerate) → `HR=0.63` (sensible)
- **Monotonicity**: FAIL → **PASS** (15yo+failures > 1-day-old)

### Remaining Work (Phase 3 — Production Hardening)

Not yet implemented (deferred to next sprint):
- MLflow experiment tracking (currently raw pickle)
- Drift detection (KS test on feature distribution)
- Retraining triggers (scheduled + drift-triggered)
- Shadow-mode A/B testing
- Feature store (Parquet-on-S3)
- LSTM decision: train properly OR delete (currently dead code)
- Replace pickle with `safetensors`/`joblib` (RCE hardening)
- Conformal prediction intervals (currently `±0.1`)
- Stacked generalization for ensemble weights (currently arbitrary 0.45/0.35/0.20)
