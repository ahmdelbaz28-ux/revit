# Changelog

All notable changes to FireAI will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added — ML Predictive Maintenance Subsystem (Roadmap Q4 2026)

Implements the Q4 2026 Roadmap item: *AI-Powered Features → Predictive
Maintenance Scheduling*. The new `fireai/ml/` module provides ML-based
failure prediction that **complements** (does not replace) the existing
statistical engine in `fireai/analytics/predictive_maintenance.py`.

#### New Modules
- `fireai/ml/` — Complete ML subsystem (predictor + models + explainers)
  - `schemas.py` — Pydantic schemas for API contracts
  - `feature_engineering.py` — Raw asset data → ML feature vectors
  - `predictive_maintenance.py` — MLFailurePredictor ensemble orchestrator
  - `models/xgboost_model.py` — XGBoost classifier (tabular features)
  - `models/lstm_model.py` — LSTM time-series forecaster (sequential events)
  - `models/cox_model.py` — Cox PH survival model (censored time-to-event)
  - `explainers/shap_explainer.py` — SHAP explanations (IEC 61508 compliance)
- `backend/routers/ml.py` — FastAPI endpoints under `/api/v1/ml/*`
- `frontend/src/pages/PredictiveMaintenancePage.tsx` — React dashboard
- `frontend/src/services/mlApi.ts` — Typed API client (Zod schemas)
- `frontend/src/components/predictive/` — Risk gauge, model comparison, SHAP
- `tests/ml/` — 24 tests (unit + integration with FastAPI TestClient)
- `requirements-ml.txt` — ML dependencies (XGBoost, lifelines, SHAP, etc.)
- `scripts/test_ml_subsystem.py` — Smoke test
- `scripts/train_ml_models_demo.py` — Training demo on synthetic data

#### Library Provenance
Libraries selected from the curated
[awesome-machine-learning](https://github.com/josephmisiti/awesome-machine-learning)
list (CC license). Selection rationale documented in
`ARCHITECTURE_ML_ADDENDUM.md`.

#### Safety Architecture
- **ML outputs are ADVISORY ONLY** — NFPA 72 deterministic rules remain
  authoritative for all life-safety decisions
- Every prediction carries SHAP explanation for regulatory audit
  (IEC 61508, NFPA 72 §14.4)
- Advisory notice mandatory in every API response
- Cross-references existing `fireai/analytics/predictive_maintenance.py`
  statistical baseline

#### API Endpoints
- `GET  /api/v1/ml/predictive-maintenance/health`
- `GET  /api/v1/ml/predictive-maintenance/models`
- `POST /api/v1/ml/predictive-maintenance/predict`
- `POST /api/v1/ml/predictive-maintenance/predict-batch` (≤100 assets)
- `POST /api/v1/ml/predictive-maintenance/train` (admin only)

#### Frontend
- New sidebar entry: "Predictive Maintenance" (Activity icon)
- Route: `/predictive-maintenance`
- Dark theme matching existing FireAI design language
- Risk gauge, model comparison bar chart, SHAP force plot
- Safety advisory banner on every view

#### Tests
- 24/24 tests passing (`tests/ml/test_predictive_maintenance.py` +
  `tests/ml/test_ml_router.py`)
- Unit tests: schema validation, feature engineering, predictor fallback
- Integration tests: FastAPI TestClient with API key authentication

### Added

- New NFPA 72-2022 compliance checks
- Enhanced acoustic modeling for notification appliances
- Real-time collaboration features for design teams
- Advanced 3D visualization engine

### Changed
- Improved performance for large building models
- Updated CAD parsing for newer file formats
- Enhanced error reporting and diagnostics

### Deprecated
- Legacy API endpoints (will be removed in v2.0)

### Removed
- Support for Python < 3.12

### Fixed
- Memory leak in geometry processing
- Race condition in concurrent analysis
- Incorrect coverage calculations for sloped ceilings

### Security
- Addressed potential injection in CAD file parsing
- Strengthened authentication for API endpoints

## [1.0.0] - 2026-06-11

### Added
- Initial release of FireAI Platform
- Core fire protection engineering engine
- NFPA 72 compliance checking
- AutoCAD and Revit integration
- Advanced detector placement algorithms
- Comprehensive audit trail system
- Multi-zone fire alarm system design
- Emergency voice communication planning
- Structural fire protection analysis
- Egress modeling and analysis

### Features
- **Automated Detector Placement**: Optimizes smoke and heat detector locations per NFPA 72
- **Compliance Verification**: Real-time checking against NFPA codes and local regulations
- **NAC Design**: Notification Appliance Circuit design with voltage drop calculations
- **Power Supply Allocation**: Automatic FACP and NAC power supply sizing
- **Integration Ready**: APIs for CAD software integration
- **Safety First**: Multiple validation layers and fail-safe mechanisms

### Safety Hardening
- V12 fixes for semantic substring collisions in detector identification
- V13 safety hardening for coverage verification
- V14 fixes for DC return path voltage drop calculations
- V19.1 RTI (Response Time Index) validation for shunt-trip systems
- V20.2 safety gate verification and proof validation

### Architecture
- Three-layer communication protocol (FACP)
- Distributed processing capability
- Pluggable compliance engine
- Extensible rule system
- Modular design for easy maintenance

### Performance
- Optimized spatial algorithms using Shapely/GEOS
- Parallel processing for large projects
- Efficient memory management
- Fast CAD file parsing

---

## Versioning

Major versions indicate significant architectural changes or safety hardening.
Minor versions add features and improvements.
Patch versions fix bugs and security issues.

## Safety Classification

- **Critical** - Safety-related fixes that prevent potential harm
- **High** - Important functionality improvements
- **Medium** - Feature enhancements
- **Low** - Minor improvements and documentation

---

**Note**: This changelog reflects the evolution of FireAI from its initial concept to a production-ready safety-critical system. All changes have undergone rigorous testing and safety validation.