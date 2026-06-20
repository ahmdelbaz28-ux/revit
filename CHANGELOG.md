# Changelog

All notable changes to FireAI will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added — Mermaid Diagram Renderer (adapted from Kittle)

Integrated the `MermaidRenderer` component from
[Kittle](https://github.com/TemRevil/Kittle) (open-source) into FireAI's
frontend. This adds Mermaid.js diagram rendering with zoom/pan/fullscreen
support — a feature previously missing from FireAI.

#### What was adapted
- `frontend/src/components/diagrams/MermaidRenderer.tsx` — adapted from
  Kittle's `components/MermaidRenderer.tsx`
- `frontend/src/pages/DiagramDemoPage.tsx` — new demo page with 6 diagram
  types (flowchart, sequence, ER, state, ML architecture)
- `frontend/src/components/diagrams/__tests__/MermaidRenderer.test.tsx` —
  34 tests covering rendering, props, interactions, accessibility, theme,
  edge cases, and debouncing

#### Adaptation choices (not copy-paste)
- Replaced `motion/react` (framer-motion) with CSS transitions — avoids
  adding a new heavy dependency
- Used shadcn/ui `cn()` utility for class merging
- Used FireAI's slate-950 dark theme palette (not Kittle's zinc palette)
- Added TypeScript strict-mode types via `import type { MermaidConfig }`
- Added accessibility: `role="img"`, `role="dialog"`, `aria-modal`,
  `aria-label` on all buttons
- Added `data-testid` attributes for testability
- Updated `vite.config.ts` to add `vendor-mermaid` chunk for code splitting

#### Why only this component (not the whole Kittle app)
Kittle is a client-side LLM chat tool. Dming it whole would violate
FireAI's safety-critical architecture (advisory-only ML contract, server-
side RBAC, deterministic NFPA 72 gates). Only the self-contained
MermaidRenderer was adapted — it has zero relative imports and only
depends on `mermaid` + `lucide-react` (already in FireAI).

#### Test results
- 34/34 unit tests passing (`MermaidRenderer.test.tsx`)
- TypeScript: no new errors introduced (pre-existing errors in
  ContextPanel.tsx and digitalTwinApi.ts are unchanged)
- Build: succeeds with mermaid isolated in `vendor-mermaid` chunk (2.8MB /
  758KB gzipped — large but loaded lazily)

#### Route
- `/diagram-demo` — visual QA page for engineers

### Fixed — ML Subsystem Critical Bug Fixes (Code Review Round 2)

After a senior-ML-engineer code review identified 10 critical issues in the
initial ML subsystem, all have been fixed and verified with behavioral tests:

#### Critical Fixes (CRITICAL severity)
- **#1 Cox PH prediction bug**: `predict()` was reading `iloc[-1]` of the
  survival function (survival at the maximum training duration, which is
  always ~0), yielding ~100% failure probability for every input. Now uses
  `times=[horizon_days]` to evaluate survival exactly at the requested horizon.
- **#2 Pickle schema versioning**: Added `schema_version=2` field to model
  pickles. `load()` refuses pickles with missing `feature_means`/`feature_stds`,
  eliminating silent train/serve skew.
- **#3 Monotonicity inversion**: A 1-day-old asset in a cleanroom was scoring
  HIGHER risk than a 15-year-old asset with 200 failures in a corrosive
  environment. Root cause: `MTBF` defaulted to 3650 for all no-failure assets,
  confusing the model. Fix: added explicit `has_failures` flag + `log_mtbf`
  sentinel; strengthened synthetic data generator signal.
- **#4 Audit trail integration wired**: `audit_trail_id` was always `None`
  (TODO in code). Now every `/predict` call writes an immutable JSON entry
  to `db/ml_audit/YYYY/MM/DD/<uuid>.json` with SHA-256 hash, and returns the
  UUID in the response for NFPA 72 §14.4 compliance.
- **#5 Frontend URL bug**: Frontend called `/api/ml/*` (404) instead of
  `/api/v1/ml/*`. Also missing `X-API-Key` header (401). Both fixed.
- **#6 Hardcoded path**: `MLModelRegistry` was hardcoded to
  `/home/z/my-project/data/ml_models` (dev machine only). Now uses
  `FIREAI_ML_MODELS_DIR` env var with CWD-relative fallback.
- **#7 RBAC on `/train`**: Was admin-only by docstring claim but no code
  enforcement. Now refuses non-admin roles with HTTP 403.
- **#8 `enforcement_contract` field**: "Advisory only" was comment-only.
  Now a required field on `MLPredictionResponse` (always `"advisory_only"`),
  with a static-analysis test that fails if `fireai.ml` is imported from
  `fireai/core/` or `fireai/rules_engine/` (safety boundary).

#### High-Severity Fixes
- **#9 XGBoost calibration**: `scale_pos_weight=neg/pos` produced degenerate
  weights (199 for 1 positive). Now uses `sqrt(neg/pos)`, adds L1/L2
  regularization, shallower trees (depth 4 vs 6), and isotonic probability
  calibration (Brier score improved from 0.27 to 0.25 on synthetic data).
- **#10 Behavioral tests added**: New `tests/ml/test_behavioral.py` with 12
  tests covering monotonicity (more failures/age → higher risk), horizon
  sensitivity, save/load round-trip, pickle schema enforcement, audit trail
  population, and static-analysis of safety boundaries.

#### Synthetic Data Generator Fixes
- Cox PH duration semantics corrected: `duration = (failure_date - install_date)`
  for failed assets, `(now - install_date)` for censored — not `age_days`
  for both (which conflated age-at-prediction with time-to-event).
- Stronger failure-probability signal: infant mortality (1%), steady-state,
  wear-out phases (sharp rise after design life) — model can now learn
  monotonic risk curves.

#### Test Results
- 36/36 tests passing (was 24/24 — added 12 behavioral tests)
- Concordance index: 0.96 → 0.80 (more honest; previous 0.96 was overfit)
- Brier score: 0.27 → 0.25 (after isotonic calibration)
- Monotonicity verified: 15yo+3failures+corrosive scores HIGH vs 1-day-old LOW

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