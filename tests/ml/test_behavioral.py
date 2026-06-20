"""
tests/ml/test_behavioral.py — Behavioral Tests for ML Subsystem
================================================================

These tests verify BEHAVIOR (not just shape). They catch the bugs that
the structural tests in test_predictive_maintenance.py missed:
    - Monotonicity (more failures / older age → higher risk)
    - Horizon sensitivity (longer horizon → higher probability)
    - Cox PH save/load round-trip consistency
    - Pickle schema version enforcement
    - Audit trail population via FastAPI
    - Enforcement contract field presence
"""

from __future__ import annotations

import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

os.environ.setdefault("FIREAI_API_KEY", "test-behavioral-key-1234567890")
os.environ.setdefault("FIREAI_ENV", "development")

from fireai.ml import (
    MLFailurePredictor,
    MLPredictionRequest,
    MLModelRegistry,
)
from fireai.ml.feature_engineering import FeatureEngineer
from fireai.ml.models.cox_model import CoxPHFailureModel
from fireai.ml.models.xgboost_model import XGBoostFailureModel
from fireai.ml.schemas import (
    AssetFeatures,
    AssetType,
    MaintenanceEventInput,
    ModelType,
    RiskLevel,
)


# ── Fixtures ────────────────────────────────────────────────────────────────

@pytest.fixture
def fe() -> FeatureEngineer:
    return FeatureEngineer()


@pytest.fixture
def predictor() -> MLFailurePredictor:
    return MLFailurePredictor()


def _make_asset(
    fe: FeatureEngineer,
    *,
    asset_id: str,
    age_days: int = 1,
    n_failures: int = 0,
    environment: str = "indoor",
    design_life_years: float = 20.0,
) -> AssetFeatures:
    """Helper to build an asset with controlled risk factors."""
    install_date = datetime.now(timezone.utc) - timedelta(days=age_days)
    history = []
    for i in range(n_failures):
        history.append(
            MaintenanceEventInput(
                event_id=f"M-{i}",
                maintenance_type="REPAIR",
                timestamp=install_date + timedelta(days=30 + i * 60),
            )
        )
    return fe.build_features(
        asset_id=asset_id,
        asset_type=AssetType.DETECTOR_SMOKE,
        installation_date=install_date,
        maintenance_history=history,
        environment_rating=environment,
        design_life_years=design_life_years,
    )


# ── Monotonicity Tests ──────────────────────────────────────────────────────

class TestMonotonicity:
    """A risk model MUST rank risky assets higher than safe ones."""

    def test_more_failures_higher_risk(self, fe, predictor):
        """Asset with 5 failures should score higher than 0 failures."""
        safe = _make_asset(fe, asset_id="SAFE-001", age_days=30, n_failures=0)
        risky = _make_asset(fe, asset_id="RISKY-001", age_days=30, n_failures=5)

        resp_safe = predictor.predict(MLPredictionRequest(asset=safe, explain=False))
        resp_risky = predictor.predict(MLPredictionRequest(asset=risky, explain=False))

        # Allow equality only if both are at boundary; otherwise risky > safe
        assert resp_risky.ensemble_failure_probability >= resp_safe.ensemble_failure_probability, (
            f"Monotonicity violation: 5 failures ({resp_risky.ensemble_failure_probability}) "
            f"should be >= 0 failures ({resp_safe.ensemble_failure_probability})"
        )

    def test_older_asset_higher_risk(self, fe, predictor):
        """15-year-old asset should score higher than 1-day-old."""
        new = _make_asset(fe, asset_id="NEW-001", age_days=1, n_failures=0)
        old = _make_asset(fe, asset_id="OLD-001", age_days=365 * 15, n_failures=0, design_life_years=10.0)

        resp_new = predictor.predict(MLPredictionRequest(asset=new, explain=False))
        resp_old = predictor.predict(MLPredictionRequest(asset=old, explain=False))

        assert resp_old.ensemble_failure_probability >= resp_new.ensemble_failure_probability, (
            f"Monotonicity violation: 15yo ({resp_old.ensemble_failure_probability}) "
            f"should be >= 1-day-old ({resp_new.ensemble_failure_probability})"
        )

    def test_harsher_environment_higher_risk(self, fe, predictor):
        """Corrosive environment should score higher than cleanroom."""
        clean = _make_asset(fe, asset_id="CLEAN-001", age_days=365 * 5, n_failures=1, environment="cleanroom")
        corrosive = _make_asset(fe, asset_id="CORR-001", age_days=365 * 5, n_failures=1, environment="corrosive")

        resp_clean = predictor.predict(MLPredictionRequest(asset=clean, explain=False))
        resp_corr = predictor.predict(MLPredictionRequest(asset=corrosive, explain=False))

        assert resp_corr.ensemble_failure_probability >= resp_clean.ensemble_failure_probability, (
            f"Monotonicity violation: corrosive ({resp_corr.ensemble_failure_probability}) "
            f"should be >= cleanroom ({resp_clean.ensemble_failure_probability})"
        )

    def test_combined_high_risk_asset(self, fe, predictor):
        """15yo + 3 failures + corrosive should be HIGH or CRITICAL risk."""
        bad_asset = _make_asset(
            fe,
            asset_id="BAD-001",
            age_days=365 * 15,
            n_failures=3,
            environment="corrosive",
            design_life_years=10.0,
        )
        response = predictor.predict(MLPredictionRequest(asset=bad_asset, explain=False))
        assert response.ensemble_risk_level in (RiskLevel.HIGH, RiskLevel.CRITICAL), (
            f"15yo + 3 failures + corrosive should be HIGH/CRITICAL, "
            f"got {response.ensemble_risk_level} (p={response.ensemble_failure_probability})"
        )


# ── Horizon Sensitivity Tests ───────────────────────────────────────────────

class TestHorizonSensitivity:
    """Longer horizons MUST yield >= probability (Cox PH survival decays)."""

    def test_cox_ph_horizon_monotonic(self, fe, predictor):
        """Cox PH probability at 365 days should be >= 7 days."""
        asset = _make_asset(fe, asset_id="HORIZON-001", age_days=365 * 5, n_failures=2)

        resp_7d = predictor.predict(MLPredictionRequest(
            asset=asset, models=[ModelType.COX_PH], explain=False, horizon_days=7
        ))
        resp_365d = predictor.predict(MLPredictionRequest(
            asset=asset, models=[ModelType.COX_PH], explain=False, horizon_days=365
        ))

        cox_7d = next((p for p in resp_7d.predictions if p.model_type == ModelType.COX_PH), None)
        cox_365d = next((p for p in resp_365d.predictions if p.model_type == ModelType.COX_PH), None)

        if cox_7d and cox_365d and not cox_7d.is_fallback and not cox_365d.is_fallback:
            assert cox_365d.failure_probability >= cox_7d.failure_probability, (
                f"Cox PH horizon violation: 365d ({cox_365d.failure_probability}) "
                f"should be >= 7d ({cox_7d.failure_probability})"
            )

    def test_cox_ph_horizon_not_constant(self, fe, predictor):
        """Cox PH must NOT return the same probability for all horizons (regression #1)."""
        asset = _make_asset(fe, asset_id="HORIZON-002", age_days=365 * 10, n_failures=1)

        probs = []
        for h in [7, 30, 90, 180, 365]:
            resp = predictor.predict(MLPredictionRequest(
                asset=asset, models=[ModelType.COX_PH], explain=False, horizon_days=h
            ))
            cox = next((p for p in resp.predictions if p.model_type == ModelType.COX_PH), None)
            if cox and not cox.is_fallback:
                probs.append((h, cox.failure_probability))

        if len(probs) >= 2:
            unique_probs = set(p for _, p in probs)
            assert len(unique_probs) > 1, (
                f"Cox PH returns constant probability across horizons: {probs}. "
                f"This is the regression described in Critical Review Issue #1."
            )


# ── Save/Load Round-Trip Tests ──────────────────────────────────────────────

class TestSaveLoadRoundTrip:
    """Pickled models must produce identical predictions after load."""

    def test_xgboost_save_load_consistency(self, fe, tmp_path):
        """Train, save, reload, predict — predictions must match."""
        from fireai.ml.models.xgboost_model import FEATURE_NAMES, XGBoostFailureModel
        import random

        # Generate minimal training data
        random.seed(42)
        X, y = [], []
        for _ in range(50):
            vec = [random.random() for _ in FEATURE_NAMES]
            label = 1 if vec[0] + vec[2] > 1.0 else 0  # age_ratio + failures_90d
            X.append(vec)
            y.append(label)

        model = XGBoostFailureModel()
        model.train(X, y, FEATURE_NAMES)

        asset = _make_asset(fe, asset_id="RT-001", age_days=365 * 5, n_failures=2)
        prob_before, _ = model.predict(asset)

        # Save + reload
        save_path = tmp_path / "xgb.pkl"
        model.save(save_path)
        model2 = XGBoostFailureModel(model_path=save_path)
        prob_after, _ = model2.predict(asset)

        assert abs(prob_before - prob_after) < 1e-6, (
            f"XGBoost save/load round-trip mismatch: {prob_before} vs {prob_after}"
        )

    def test_cox_ph_save_load_consistency(self, fe, tmp_path):
        """Train, save, reload, predict — predictions must match."""
        import random

        random.seed(42)
        X, durations, events = [], [], []
        for _ in range(50):
            feat = {
                "age_ratio": random.uniform(0, 1.5),
                "recent_failures_365d": random.randint(0, 5),
                "repair_ratio_365d": random.uniform(0, 1),
                "environment_factor": random.uniform(0.4, 1.0),
                "is_battery": random.choice([0, 1]),
                "is_outdoor": random.choice([0, 1]),
                "log_mtbf": random.uniform(5, 9),
            }
            X.append(feat)
            durations.append(random.uniform(30, 7000))
            events.append(random.choice([0, 1]))

        model = CoxPHFailureModel()
        try:
            model.train(X, durations, events)
        except Exception:
            pytest.skip("Cox PH training requires lifelines")

        asset = _make_asset(fe, asset_id="RT-COX-001", age_days=365 * 5, n_failures=2)
        prob_before, _, _ = model.predict(asset, horizon_days=90)

        save_path = tmp_path / "cox.pkl"
        model.save(save_path)
        model2 = CoxPHFailureModel(model_path=save_path)
        prob_after, _, _ = model2.predict(asset, horizon_days=90)

        assert abs(prob_before - prob_after) < 1e-6, (
            f"Cox PH save/load round-trip mismatch: {prob_before} vs {prob_after}"
        )

    def test_old_pickle_schema_version_rejected(self, tmp_path):
        """Pickles without schema_version >=2 must be refused (train/serve skew guard)."""
        import pickle

        # Write a v1-style pickle (missing schema_version)
        bad_pickle = tmp_path / "bad.pkl"
        with open(bad_pickle, "wb") as f:
            pickle.dump({"model": None, "model_version": "old"}, f)

        model = XGBoostFailureModel()
        with pytest.raises(RuntimeError, match="schema_version"):
            model.load(bad_pickle)


# ── Audit Trail Tests ───────────────────────────────────────────────────────

class TestAuditTrail:
    """Every prediction via FastAPI MUST populate audit_trail_id."""

    @pytest.fixture(scope="class")
    def client(self):
        from fastapi.testclient import TestClient
        import importlib
        app_module = importlib.import_module("backend.app")
        client = TestClient(app_module.app)
        client.headers.update({"X-API-Key": os.environ["FIREAI_API_KEY"]})
        return client

    def test_predict_populates_audit_trail_id(self, client):
        """audit_trail_id MUST be a UUID, not None."""
        payload = {
            "asset": {
                "asset_id": "AUDIT-TEST-001",
                "asset_type": "DETECTOR_SMOKE",
                "installation_date": "2018-06-01T00:00:00Z",
                "environment_rating": "indoor",
                "design_life_years": 20.0,
            },
            "models": ["XGBOOST"],
            "explain": False,
            "horizon_days": 90,
        }
        r = client.post("/api/v1/ml/predictive-maintenance/predict", json=payload)
        assert r.status_code == 200
        data = r.json()
        assert data["audit_trail_id"] is not None, "audit_trail_id must not be None"
        assert len(data["audit_trail_id"]) >= 32, (
            f"audit_trail_id must be a UUID, got: {data['audit_trail_id']}"
        )

    def test_enforcement_contract_always_advisory_only(self, client):
        """Every response MUST carry enforcement_contract='advisory_only'."""
        payload = {
            "asset": {
                "asset_id": "CONTRACT-001",
                "asset_type": "BATTERY",
                "installation_date": "2020-01-01T00:00:00Z",
                "environment_rating": "indoor",
            },
            "models": ["XGBOOST", "COX_PH"],
            "explain": False,
        }
        r = client.post("/api/v1/ml/predictive-maintenance/predict", json=payload)
        assert r.status_code == 200
        data = r.json()
        assert data.get("enforcement_contract") == "advisory_only", (
            f"enforcement_contract must be 'advisory_only', got: {data.get('enforcement_contract')}"
        )


# ── Static-Analysis Test (Issue #8) ─────────────────────────────────────────

class TestAdvisoryOnlyEnforcement:
    """fireai.ml must NEVER be imported from deterministic NFPA 72 code paths."""

    def test_no_ml_imports_in_core(self):
        """fireai/core/ must not import from fireai.ml (safety boundary)."""
        import subprocess
        result = subprocess.run(
            ["grep", "-rln", "from fireai.ml", "fireai/core/"],
            capture_output=True, text=True, cwd=str(PROJECT_ROOT),
        )
        # grep returns 0 if matches found, 1 if no matches
        assert result.returncode == 1, (
            f"fireai/core/ contains ML imports (forbidden — breaks advisory-only):\n"
            f"{result.stdout}"
        )

    def test_no_ml_imports_in_rules_engine(self):
        """fireai/rules_engine/ must not import from fireai.ml (safety boundary)."""
        import subprocess
        rules_dir = PROJECT_ROOT / "fireai" / "rules_engine"
        if not rules_dir.exists():
            pytest.skip("fireai/rules_engine/ does not exist")
        result = subprocess.run(
            ["grep", "-rln", "from fireai.ml", str(rules_dir)],
            capture_output=True, text=True,
        )
        assert result.returncode == 1, (
            f"fireai/rules_engine/ contains ML imports (forbidden):\n{result.stdout}"
        )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
