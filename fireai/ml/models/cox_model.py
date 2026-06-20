"""
fireai/ml/models/cox_model.py — Cox Proportional Hazards Survival Model
=========================================================================

Cox PH model for time-to-failure prediction using survival analysis.

Why lifelines (from awesome-machine-learning):
    - Python "Survival Analysis" section explicitly lists survival libraries
    - Cox PH is the gold standard for censored time-to-event data
    - Maintenance logs are inherently censored (asset hasn't failed yet)
    - Produces hazard ratios interpretable for regulatory audit

References:
    - Cox, D.R. (1972) "Regression models and life-tables"
    - NFPA 72-2022 §14.4 (inspection cycles ≈ right-censoring)
    - IEC 61649 (Weibull + Cox PH for reliability)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from fireai.ml.schemas import AssetFeatures, MLPrediction, ModelType, RiskLevel

logger = logging.getLogger(__name__)


@dataclass
class CoxTrainingResult:
    model_version: str
    samples_used: int
    metrics: Dict[str, float]
    trained_at: datetime
    hazard_ratios: Dict[str, float]


class CoxPHFailureModel:
    """Cox Proportional Hazards model using lifelines."""

    def __init__(self, model_path: Optional[Path] = None) -> None:
        self._model = None
        self._model_path = model_path
        self._model_version = "untrained"
        self._training_data_size = 0
        self._last_trained_at: Optional[datetime] = None
        self._hazard_ratios: Dict[str, float] = {}
        self._baseline_survival: Any = None
        self._feature_means: Any = None
        self._feature_stds: Any = None

        if model_path and model_path.exists():
            try:
                self.load(model_path)
            except Exception as exc:
                logger.warning("Failed to load Cox PH model: %s", exc)

    @staticmethod
    def is_available() -> bool:
        try:
            import lifelines  # noqa: F401
            return True
        except ImportError:
            return False

    def _features_to_cox_input(
        self, features: AssetFeatures
    ) -> Dict[str, float]:
        """Convert features to Cox PH input dictionary (standardized at train time)."""
        mtbf = features.mean_time_between_failures_days
        if mtbf is None or mtbf <= 0:
            mtbf = 3650.0
        # Log-transform MTBF for better conditioning
        return {
            "age_ratio": float(features.age_ratio),
            "recent_failures_365d": float(features.recent_failures_365d),
            "repair_ratio_365d": float(features.repair_ratio_365d),
            "environment_factor": float(features.environment_factor),
            "is_battery": 1.0 if features.is_battery else 0.0,
            "is_outdoor": 1.0 if features.is_outdoor else 0.0,
            "log_mtbf": float(np.log(max(1.0, mtbf))),
        }

    def train(
        self,
        X: List[Dict[str, float]],
        durations: List[float],
        events: List[int],
    ) -> CoxTrainingResult:
        """
        Train Cox PH model.

        Args:
            X: List of feature dicts (one per asset)
            durations: Time on observation (days)
            events: 1 if failure observed, 0 if censored
        """
        if not self.is_available():
            raise RuntimeError("lifelines not installed. Run: pip install lifelines")
        if len(X) != len(durations) or len(X) != len(events):
            raise ValueError("X/durations/events length mismatch")
        if len(X) < 30:
            raise ValueError(f"Need >= 30 samples for Cox PH, got {len(X)}")

        import numpy as np
        import pandas as pd
        from lifelines import CoxPHFitter

        df = pd.DataFrame(X)
        df["duration"] = durations
        df["event"] = events

        # FIX: Standardize numeric features to prevent numerical instability
        # Cox PH is sensitive to feature scale (age_ratio range 0-2 caused
        # HR=0.002 in earlier runs). We standardize then store means/stds
        # for inference-time alignment.
        numeric_cols = df.select_dtypes(include=[np.number]).columns.tolist()
        numeric_cols = [c for c in numeric_cols if c not in ("duration", "event")]
        self._feature_means = df[numeric_cols].mean()
        self._feature_stds = df[numeric_cols].std().replace(0, 1.0)
        df[numeric_cols] = (df[numeric_cols] - self._feature_means) / self._feature_stds

        # Use stronger penalizer (L2 ridge) for stability on small datasets
        self._model = CoxPHFitter(penalizer=0.3)
        self._model.fit(df, duration_col="duration", event_col="event")

        # Compute concordance index (C-statistic)
        c_index = self._model.concordance_index_

        # Extract hazard ratios (exp(coef))
        self._hazard_ratios = {
            name: float(val) for name, val in self._hazard_ratios_dict().items()
        }

        self._model_version = f"cox-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}"
        self._training_data_size = len(X)
        self._last_trained_at = datetime.now(timezone.utc)

        return CoxTrainingResult(
            model_version=self._model_version,
            samples_used=len(X),
            metrics={"concordance_index": float(c_index)},
            trained_at=self._last_trained_at,
            hazard_ratios=self._hazard_ratios,
        )

    def _hazard_ratios_dict(self) -> Dict[str, float]:
        if self._model is None:
            return {}
        return {
            name: float(np_exp)
            for name, np_exp in zip(
                self._model.params_.index,
                self._model.hazard_ratios_.values,
            )
        }

    def predict(self, features: AssetFeatures) -> Tuple[float, float, Dict[str, Any]]:
        """
        Predict failure probability and median survival time.

        Returns:
            (failure_probability_90d, median_survival_days, metadata)
        """
        if self._model is None:
            raise RuntimeError("Model not trained")
        if not self.is_available():
            raise RuntimeError("lifelines not available at inference")

        import pandas as pd

        feat = self._features_to_cox_input(features)
        df = pd.DataFrame([feat])

        # Apply same standardization as training
        if hasattr(self, "_feature_means") and self._feature_means is not None:
            for col in self._feature_means.index:
                if col in df.columns:
                    df[col] = (df[col] - self._feature_means[col]) / self._feature_stds[col]

        # Predict survival function at 90 days
        sf = self._model.predict_survival_function(df)
        survival_at_90 = float(sf.iloc[-1, 0]) if len(sf) > 0 else 1.0
        failure_prob_90d = 1.0 - survival_at_90

        # Predict median survival time
        try:
            median = self._model.predict_median(df)
            median_days = float(median.iloc[0]) if hasattr(median, "iloc") else float(median)
        except Exception:
            median_days = None

        return failure_prob_90d, median_days, {
            "model_version": self._model_version,
            "training_data_size": self._training_data_size,
            "last_trained_at": self._last_trained_at,
            "hazard_ratios": self._hazard_ratios,
        }

    def to_prediction(
        self,
        features: AssetFeatures,
        horizon_days: int = 90,
    ) -> MLPrediction:
        try:
            proba, median_ttf, meta = self.predict(features)
            risk = self._classify_risk(proba)
            return MLPrediction(
                model_type=ModelType.COX_PH,
                failure_probability=round(proba, 4),
                predicted_ttf_days=round(median_ttf, 1) if median_ttf else None,
                confidence_lower=max(0.0, proba - 0.1),
                confidence_upper=min(1.0, proba + 0.1),
                risk_level=risk,
                is_fallback=False,
                model_version=meta["model_version"],
                training_data_size=meta["training_data_size"],
                last_trained_at=meta["last_trained_at"],
            )
        except Exception as exc:
            logger.warning("Cox PH prediction failed: %s", exc)
            return MLPrediction(
                model_type=ModelType.COX_PH,
                failure_probability=0.5,
                risk_level=RiskLevel.MEDIUM,
                is_fallback=True,
                model_version="fallback-0.5",
            )

    def save(self, path: Path) -> None:
        if self._model is None:
            raise RuntimeError("Cannot save untrained model")
        import pickle
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "wb") as f:
            pickle.dump({
                "model": self._model,
                "model_version": self._model_version,
                "training_data_size": self._training_data_size,
                "last_trained_at": self._last_trained_at,
                "hazard_ratios": self._hazard_ratios,
                "feature_means": self._feature_means,
                "feature_stds": self._feature_stds,
            }, f)

    def load(self, path: Path) -> None:
        import pickle
        with open(path, "rb") as f:
            data = pickle.load(f)
        self._model = data["model"]
        self._model_version = data["model_version"]
        self._training_data_size = data["training_data_size"]
        self._last_trained_at = data["last_trained_at"]
        self._hazard_ratios = data.get("hazard_ratios", {})
        self._feature_means = data.get("feature_means")
        self._feature_stds = data.get("feature_stds")

    @staticmethod
    def _classify_risk(probability: float) -> RiskLevel:
        if probability > 0.5:
            return RiskLevel.CRITICAL
        if probability > 0.3:
            return RiskLevel.HIGH
        if probability > 0.15:
            return RiskLevel.MEDIUM
        return RiskLevel.LOW
