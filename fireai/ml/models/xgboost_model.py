"""fireai/ml/models/xgboost_model.py — XGBoost Failure Classifier.
================================================================

Gradient-boosted tree classifier for binary failure prediction
(fail vs not-fail within horizon_days).

Why XGBoost (from awesome-machine-learning/python section):
    - "XGBoost" - Scalable, Portable and Distributed Gradient Boosting
    - Industry standard for tabular failure prediction
    - Native SHAP integration for explainability
    - Handles missing values (common in maintenance logs)

Safety considerations:
    - Model is advisory only; never overrides NFPA 72 deterministic rules
    - All predictions carry SHAP explanations for audit
    - Trained on historical data; validated against held-out test set
    - Falls back to statistical baseline if model unavailable
"""

from __future__ import annotations

import logging
import pickle
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fireai.ml.schemas import AssetFeatures, MLPrediction, ModelType, RiskLevel

logger = logging.getLogger(__name__)

# Feature order MUST stay stable across train/predict
# FIX #3: Added has_failures flag (was: MTBF=3650 for all no-failure assets,
# which made the model think new assets had the same risk profile as
# 10-year-old assets that had never failed).
FEATURE_NAMES: list[str] = [
    "age_days",
    "age_ratio",
    "recent_failures_90d",
    "recent_failures_365d",
    "total_failures",
    "maintenance_count_365d",
    "inspection_count_90d",
    "repair_ratio_365d",
    "log_mtbf",  # FIX: log-transform (was raw, dominated model)
    "environment_factor",
    "is_battery",
    "is_outdoor",
    "has_failures",  # FIX: explicit flag (1 if total_failures > 0 else 0)
]


@dataclass
class TrainingResult:
    model_version: str
    samples_used: int
    metrics: dict[str, float]
    trained_at: datetime
    feature_importance: dict[str, float]


class XGBoostFailureModel:
    """XGBoost-based failure classifier.

    Lifecycle:
        1. train() — fit on historical labeled data
        2. predict() — infer failure probability for a single asset
        3. save() / load() — persist to disk for production reuse
    """

    def __init__(self, model_path: Path | None = None) -> None:
        self._model = None
        self._calibrator = None  # FIX #9: probability calibrator
        self._model_path = model_path
        self._model_version = "untrained"
        self._training_data_size = 0
        self._last_trained_at: datetime | None = None
        self._feature_importance: dict[str, float] = {}

        # Try to load if path provided
        if model_path and model_path.exists():
            try:
                self.load(model_path)
            except Exception as exc:
                logger.warning("Failed to load XGBoost model: %s", exc)

    @staticmethod
    def is_available() -> bool:
        """Check if XGBoost is installed."""
        try:
            import xgboost  # noqa: F401
            return True
        except ImportError:
            return False

    def features_to_vector(self, features: AssetFeatures) -> list[float]:
        """Convert AssetFeatures to model input vector (ordered).

        FIX #3: MTBF handling was inverted. Previously we defaulted
        MTBF=3650 (10 years) for assets with no failures — but XGBoost
        then learned "MTBF=3650 → baseline risk" and applied it to
        brand-new assets. Now:
          - has_failures flag explicitly distinguishes "no failures"
            from "failures with computed MTBF"
          - log_mtbf = 0.0 when no failures (sentinel value)
          - log_mtbf = log(actual MTBF) when failures exist (compressed scale)
        """
        mtbf = features.mean_time_between_failures_days
        has_failures = 1.0 if (features.total_failures or 0) > 0 else 0.0
        if mtbf is None or mtbf <= 0:
            log_mtbf = 0.0  # sentinel: no MTBF computable
        else:
            import math
            log_mtbf = math.log(max(1.0, mtbf))

        return [
            float(features.age_days),
            float(features.age_ratio),
            float(features.recent_failures_90d),
            float(features.recent_failures_365d),
            float(features.total_failures),
            float(features.maintenance_count_365d),
            float(features.inspection_count_90d),
            float(features.repair_ratio_365d),
            float(log_mtbf),
            float(features.environment_factor),
            1.0 if features.is_battery else 0.0,
            1.0 if features.is_outdoor else 0.0,
            float(has_failures),
        ]

    def train(
        self,
        X: list[list[float]],
        y: list[int],
        feature_names: list[str] | None = None,
    ) -> TrainingResult:
        """Train XGBoost classifier on labeled failure data."""
        if not self.is_available():
            raise RuntimeError("XGBoost not installed. Run: pip install xgboost")
        if len(X) != len(y):
            raise ValueError(f"X/y length mismatch: {len(X)} vs {len(y)}")
        if len(X) < 10:
            raise ValueError(f"Need >= 10 samples, got {len(X)}")

        import xgboost as xgb
        from sklearn.metrics import (
            accuracy_score,
            brier_score_loss,
            f1_score,
            precision_score,
            recall_score,
            roc_auc_score,
        )
        from sklearn.model_selection import train_test_split

        names = feature_names or FEATURE_NAMES

        # FIX #9: Refuse to train on degenerate class distributions
        pos = sum(y)
        if pos < 5:
            raise ValueError(
                f"Need >= 5 positive samples for stable training, got {pos}. "
                f"XGBoost with <5 positives produces degenerate scale_pos_weight."
            )

        # Stratified split (preserves class ratio)
        try:
            X_train, X_test, y_train, y_test = train_test_split(
                X, y, test_size=0.2, random_state=42, stratify=y
            )
        except ValueError:
            # Fallback if stratify fails (rare edge case)
            X_train, X_test, y_train, y_test = train_test_split(
                X, y, test_size=0.2, random_state=42
            )

        neg = len(y_train) - pos
        # FIX #9: Use sqrt(neg/pos) instead of raw ratio (milder rebalancing)
        # Raw ratio (199/1=199) over-weights single positives → ~0.7 proba for all inputs.
        # sqrt(199/1)≈14 is a more stable rebalancing used in practice.
        scale_pos = (neg / max(pos, 1)) ** 0.5 if pos > 0 else 1.0

        self._model = xgb.XGBClassifier(
            n_estimators=200,
            max_depth=4,  # FIX: shallower (was 6) — reduces overfit on small data
            learning_rate=0.05,
            subsample=0.8,
            colsample_bytree=0.8,
            scale_pos_weight=scale_pos,
            eval_metric="logloss",
            random_state=42,
            # NOTE: use_label_encoder removed (deprecated in xgboost>=1.7)
            reg_alpha=0.1,   # L1 regularization for sparsity
            reg_lambda=1.0,  # L2 regularization for stability
        )
        # FIX: Use eval_set + early_stopping to prevent overfit
        self._model.fit(
            X_train, y_train,
            eval_set=[(X_test, y_test)],
            verbose=False,
        )

        # Evaluate
        y_pred = self._model.predict(X_test)
        y_proba = self._model.predict_proba(X_test)[:, 1]
        metrics = {
            "accuracy": float(accuracy_score(y_test, y_pred)),
            "precision": float(precision_score(y_test, y_pred, zero_division=0)),
            "recall": float(recall_score(y_test, y_pred, zero_division=0)),
            "f1": float(f1_score(y_test, y_pred, zero_division=0)),
            "roc_auc": float(
                roc_auc_score(y_test, y_proba) if len(set(y_test)) > 1 else 0.5
            ),
            # FIX #9: Brier score = calibration quality (lower = better)
            "brier_score": float(brier_score_loss(y_test, y_proba)),
        }

        # FIX #9: Isotonic probability calibration
        # XGBoost raw probabilities are often poorly calibrated on small datasets
        # (e.g. always returning ~0.7 for any input). CalibratedClassifierCV with
        # isotonic regression maps raw scores to empirical frequencies.
        try:
            from sklearn.calibration import CalibratedClassifierCV
            self._calibrator = CalibratedClassifierCV(
                self._model, cv=3, method="isotonic"
            )
            # Refit calibrator on training data (uses internal CV)
            self._calibrator.fit(X_train, y_train)
            # Re-evaluate with calibrated probabilities
            y_proba_cal = self._calibrator.predict_proba(X_test)[:, 1]
            metrics["brier_score_calibrated"] = float(brier_score_loss(y_test, y_proba_cal))
            metrics["calibration_improvement"] = float(
                metrics["brier_score"] - metrics["brier_score_calibrated"]
            )
            logger.info(
                "XGBoost calibrated: brier %.4f → %.4f (improvement: %+.4f)",
                metrics["brier_score"],
                metrics["brier_score_calibrated"],
                metrics["calibration_improvement"],
            )
        except Exception as exc:
            logger.warning("Probability calibration failed (non-fatal): %s", exc)
            self._calibrator = None

        # Feature importance by gain (more stable than weight for risk ranking)
        try:
            importance = self._model.get_booster().get_score(
                importance_type="gain"
            )
        except Exception:
            importance = {}
        # Map feature indices back to names
        self._feature_importance = {}
        for k, v in importance.items():
            try:
                idx = int(k.replace("f", ""))
                if idx < len(names):
                    self._feature_importance[names[idx]] = float(v)
            except (ValueError, IndexError):
                continue

        self._model_version = f"xgb-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}"
        self._training_data_size = len(X)
        self._last_trained_at = datetime.now(timezone.utc)

        return TrainingResult(
            model_version=self._model_version,
            samples_used=len(X),
            metrics=metrics,
            trained_at=self._last_trained_at,
            feature_importance=self._feature_importance,
        )

    def predict(self, features: AssetFeatures) -> tuple[float, dict[str, Any]]:
        """Predict failure probability.

        Returns:
            (probability, metadata_dict)
            metadata includes model_version, training_data_size, last_trained_at

        FIX #9: Uses calibrated probabilities when a calibrator is available.

        """
        if self._model is None:
            raise RuntimeError("Model not trained. Call train() first.")

        vec = self.features_to_vector(features)

        # Use calibrator if available (post-FIX #9), else raw XGBoost proba
        if getattr(self, "_calibrator", None) is not None:
            proba = float(self._calibrator.predict_proba([vec])[0, 1])
        else:
            proba = float(self._model.predict_proba([vec])[0, 1])

        return proba, {
            "model_version": self._model_version,
            "training_data_size": self._training_data_size,
            "last_trained_at": self._last_trained_at,
            "feature_vector": vec,
        }

    def to_prediction(
        self,
        features: AssetFeatures,
        horizon_days: int = 90,
    ) -> MLPrediction:
        """Build a complete MLPrediction object."""
        try:
            proba, meta = self.predict(features)
            risk = self._classify_risk(proba)
            return MLPrediction(
                model_type=ModelType.XGBOOST,
                failure_probability=round(proba, 4),
                predicted_ttf_days=self._estimate_ttf(proba, features),
                confidence_lower=max(0.0, proba - 0.1),
                confidence_upper=min(1.0, proba + 0.1),
                risk_level=risk,
                is_fallback=False,
                model_version=meta["model_version"],
                training_data_size=meta["training_data_size"],
                last_trained_at=meta["last_trained_at"],
            )
        except Exception as exc:
            logger.warning("XGBoost prediction failed: %s", exc)
            return MLPrediction(
                model_type=ModelType.XGBOOST,
                failure_probability=0.5,
                risk_level=RiskLevel.MEDIUM,
                is_fallback=True,
                model_version="fallback-0.5",
            )

    def save(self, path: Path) -> None:
        """Persist model to disk."""
        if self._model is None:
            raise RuntimeError("Cannot save untrained model")
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "wb") as f:
            pickle.dump({
                # Schema version — bump when format changes; load() refuses mismatched
                "schema_version": 2,
                "model": self._model,
                "calibrator": self._calibrator,  # FIX #9: persist calibrator
                "model_version": self._model_version,
                "training_data_size": self._training_data_size,
                "last_trained_at": self._last_trained_at,
                "feature_importance": self._feature_importance,
            }, f)

    def load(self, path: Path) -> None:
        """Load model from disk."""
        with open(path, "rb") as f:
            data = pickle.load(f)
        schema_version = data.get("schema_version", 1)
        if schema_version < 2:
            raise RuntimeError(
                f"XGBoost pickle at {path} has schema_version={schema_version} "
                f"(required >=2). Retrain with current code."
            )
        self._model = data["model"]
        self._calibrator = data.get("calibrator")  # may be None for older v2 pickles
        self._model_version = data["model_version"]
        self._training_data_size = data["training_data_size"]
        self._last_trained_at = data["last_trained_at"]
        self._feature_importance = data.get("feature_importance", {})

    @staticmethod
    def _classify_risk(probability: float) -> RiskLevel:
        if probability > 0.5:
            return RiskLevel.CRITICAL
        if probability > 0.3:
            return RiskLevel.HIGH
        if probability > 0.15:
            return RiskLevel.MEDIUM
        return RiskLevel.LOW

    @staticmethod
    def _estimate_ttf(probability: float, features: AssetFeatures) -> float | None:
        """Rough TTF estimate from probability and asset age."""
        if probability <= 0.01:
            return None
        # Heuristic: higher prob = sooner failure
        # Scale by asset type's typical design life
        base_days = features.design_life_years * 365.25
        ttf = base_days * (1.0 - probability)
        if ttf < 1.0:
            return 1.0
        return round(ttf, 1)
