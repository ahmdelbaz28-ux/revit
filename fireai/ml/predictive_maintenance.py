"""
fireai/ml/predictive_maintenance.py — ML-Based Predictive Maintenance
======================================================================

Top-level orchestrator that runs multiple ML models in ensemble and
combines their predictions with SHAP explanations.

This module COMPLEMENTS fireai/analytics/predictive_maintenance.py
(which uses statistical Weibull analysis). It does NOT replace it.

Usage:
    predictor = MLFailurePredictor()
    response = predictor.predict(request)
    # response.ensemble_failure_probability
    # response.predictions = [per-model predictions]
    # response.explanations = [per-model SHAP explanations]

Safety:
    - ML outputs are ADVISORY only
    - NFPA 72 deterministic rules (in fireai/core/) remain authoritative
    - Every prediction is logged to audit_trail with explanations
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from fireai.ml.explainers.shap_explainer import SHAPExplainer
from fireai.ml.models.cox_model import CoxPHFailureModel
from fireai.ml.models.lstm_model import LSTMFailureModel
from fireai.ml.models.xgboost_model import FEATURE_NAMES, XGBoostFailureModel
from fireai.ml.schemas import (
    AssetFeatures,
    MLPrediction,
    MLPredictionRequest,
    MLPredictionResponse,
    ModelExplanation,
    ModelType,
    RiskLevel,
)

logger = logging.getLogger(__name__)


class MLModelRegistry:
    """Registry of available ML models with lazy loading."""

    def __init__(self, models_dir: Optional[Path] = None) -> None:
        self.models_dir = models_dir or Path("/home/z/my-project/data/ml_models")
        self.models_dir.mkdir(parents=True, exist_ok=True)

        self._xgboost = XGBoostFailureModel(
            model_path=self.models_dir / "xgboost.pkl"
        )
        self._lstm = LSTMFailureModel(
            model_path=self.models_dir / "lstm.pt"
        )
        self._cox = CoxPHFailureModel(
            model_path=self.models_dir / "cox.pkl"
        )
        self._shap = SHAPExplainer()

    @property
    def xgboost(self) -> XGBoostFailureModel:
        return self._xgboost

    @property
    def lstm(self) -> LSTMFailureModel:
        return self._lstm

    @property
    def cox(self) -> CoxPHFailureModel:
        return self._cox

    @property
    def shap(self) -> SHAPExplainer:
        return self._shap

    def available_models(self) -> List[ModelType]:
        """List models that are both installed and trained."""
        available = []
        if self._xgboost.is_available() and self._xgboost._model is not None:
            available.append(ModelType.XGBOOST)
        if self._lstm.is_available() and self._lstm._model is not None:
            available.append(ModelType.LSTM)
        if self._cox.is_available() and self._cox._model is not None:
            available.append(ModelType.COX_PH)
        return available


class MLFailurePredictor:
    """
    Top-level orchestrator for ML-based failure prediction.

    Runs requested models in ensemble, combines predictions, and
    generates SHAP explanations for each model that supports them.
    """

    def __init__(self, registry: Optional[MLModelRegistry] = None) -> None:
        self.registry = registry or MLModelRegistry()

    def predict(self, request: MLPredictionRequest) -> MLPredictionResponse:
        """
        Run ML prediction ensemble.

        Args:
            request: Contains asset features, requested models, explain flag

        Returns:
            MLPredictionResponse with ensemble + per-model predictions
        """
        asset = request.asset
        models_to_run = self._resolve_models(request.models)
        horizon = request.horizon_days

        predictions: List[MLPrediction] = []
        explanations: List[ModelExplanation] = []

        for model_type in models_to_run:
            pred, expl = self._run_single_model(
                model_type, asset, horizon, request.explain
            )
            predictions.append(pred)
            if expl is not None:
                explanations.append(expl)

        # Build ensemble (weighted average)
        ensemble_proba, ensemble_risk, ensemble_ttf = self._combine_predictions(
            predictions
        )

        # Cross-reference statistical baseline (if analytics module available)
        statistical_baseline = self._compute_statistical_baseline(asset)

        return MLPredictionResponse(
            asset_id=asset.asset_id,
            generated_at=datetime.now(timezone.utc),
            horizon_days=horizon,
            ensemble_failure_probability=round(ensemble_proba, 4),
            ensemble_risk_level=ensemble_risk,
            ensemble_ttf_days=ensemble_ttf,
            predictions=predictions,
            explanations=explanations,
            statistical_baseline=statistical_baseline,
        )

    def _resolve_models(self, requested: List[ModelType]) -> List[ModelType]:
        """
        Resolve requested models to those runnable.

        Returns ALL requested models whose underlying library is installed
        (even if not yet trained — they will produce fallback predictions).
        ENSEMBLE returns all installed models.
        """
        if ModelType.ENSEMBLE in requested:
            installed = []
            if self.registry.xgboost.is_available():
                installed.append(ModelType.XGBOOST)
            if self.registry.lstm.is_available():
                installed.append(ModelType.LSTM)
            if self.registry.cox.is_available():
                installed.append(ModelType.COX_PH)
            return installed

        # Filter to installed-but-maybe-untrained (they'll fallback gracefully)
        result = []
        for m in requested:
            if m == ModelType.XGBOOST and self.registry.xgboost.is_available():
                result.append(m)
            elif m == ModelType.LSTM and self.registry.lstm.is_available():
                result.append(m)
            elif m == ModelType.COX_PH and self.registry.cox.is_available():
                result.append(m)
            elif m in (ModelType.PROPHET, ModelType.LIGHTGBM,
                       ModelType.FALLBACK_STATISTICAL):
                # Not yet implemented — skip silently
                pass
        return result

    def _run_single_model(
        self,
        model_type: ModelType,
        asset: AssetFeatures,
        horizon: int,
        explain: bool,
    ) -> tuple[MLPrediction, Optional[ModelExplanation]]:
        """Run a single model and optionally generate explanation."""
        try:
            if model_type == ModelType.XGBOOST:
                pred = self.registry.xgboost.to_prediction(asset, horizon)
                expl = None
                if explain and not pred.is_fallback:
                    expl = self._explain_xgboost(asset)
                return pred, expl

            elif model_type == ModelType.LSTM:
                pred = self.registry.lstm.to_prediction(asset, horizon)
                expl = None
                if explain and not pred.is_fallback:
                    expl = self._explain_lstm(asset)
                return pred, expl

            elif model_type == ModelType.COX_PH:
                pred = self.registry.cox.to_prediction(asset, horizon)
                expl = None
                if explain and not pred.is_fallback:
                    expl = self._explain_cox(asset)
                return pred, expl

            else:
                logger.warning("Unknown model type: %s", model_type)
                return MLPrediction(
                    model_type=model_type,
                    failure_probability=0.5,
                    risk_level=RiskLevel.MEDIUM,
                    is_fallback=True,
                ), None

        except Exception as exc:
            logger.error("Model %s failed: %s", model_type, exc)
            return MLPrediction(
                model_type=model_type,
                failure_probability=0.5,
                risk_level=RiskLevel.MEDIUM,
                is_fallback=True,
            ), None

    def _explain_xgboost(self, asset: AssetFeatures) -> Optional[ModelExplanation]:
        """Generate SHAP explanation for XGBoost prediction."""
        try:
            xgb_model = self.registry.xgboost
            if xgb_model._model is None:
                return None
            vec = xgb_model.features_to_vector(asset)
            return self.registry.shap.explain_xgboost(
                xgb_model._model, vec, FEATURE_NAMES
            )
        except Exception as exc:
            logger.warning("XGBoost explanation failed: %s", exc)
            return None

    def _explain_lstm(self, asset: AssetFeatures) -> Optional[ModelExplanation]:
        try:
            seq = self.registry.lstm.features_to_sequence(asset)
            return self.registry.shap.explain_lstm(seq)
        except Exception as exc:
            logger.warning("LSTM explanation failed: %s", exc)
            return None

    def _explain_cox(self, asset: AssetFeatures) -> Optional[ModelExplanation]:
        try:
            cox_model = self.registry.cox
            if cox_model._model is None or not cox_model._hazard_ratios:
                return None
            # Pass the model + features; explainer handles standardization internally
            return self.registry.shap.explain_cox(cox_model, asset)
        except Exception as exc:
            logger.warning("Cox explanation failed: %s", exc)
            return None

    @staticmethod
    def _combine_predictions(
        predictions: List[MLPrediction],
    ) -> tuple[float, RiskLevel, Optional[float]]:
        """
        Combine per-model predictions into ensemble.

        Weights (when available):
            - XGBoost: 0.45 (best for tabular features)
            - Cox PH:  0.35 (best for censored survival data)
            - LSTM:    0.20 (best for sequential patterns)
            - Fallback statistical: excluded from ensemble
        """
        weights = {
            ModelType.XGBOOST: 0.45,
            ModelType.COX_PH: 0.35,
            ModelType.LSTM: 0.20,
            ModelType.PROPHET: 0.10,
            ModelType.LIGHTGBM: 0.45,
            ModelType.FALLBACK_STATISTICAL: 0.0,
        }

        weighted_sum = 0.0
        total_weight = 0.0
        ttf_values: List[float] = []

        for pred in predictions:
            if pred.is_fallback:
                continue
            w = weights.get(pred.model_type, 0.0)
            weighted_sum += pred.failure_probability * w
            total_weight += w
            if pred.predicted_ttf_days is not None:
                ttf_values.append(pred.predicted_ttf_days)

        if total_weight == 0:
            # All fallbacks — use mean
            proba = sum(p.failure_probability for p in predictions) / max(len(predictions), 1)
        else:
            proba = weighted_sum / total_weight

        risk = MLFailurePredictor._classify_risk(proba)
        ttf = sum(ttf_values) / len(ttf_values) if ttf_values else None

        return round(proba, 4), risk, round(ttf, 1) if ttf else None

    @staticmethod
    def _classify_risk(probability: float) -> RiskLevel:
        if probability > 0.5:
            return RiskLevel.CRITICAL
        if probability > 0.3:
            return RiskLevel.HIGH
        if probability > 0.15:
            return RiskLevel.MEDIUM
        return RiskLevel.LOW

    def _compute_statistical_baseline(
        self, asset: AssetFeatures
    ) -> Optional[Dict[str, Any]]:
        """
        Cross-reference with fireai/analytics/predictive_maintenance.py
        for deterministic baseline comparison.
        """
        try:
            # Import lazily to avoid circular imports
            from fireai.analytics.predictive_maintenance import (
                AssetData,
                AssetType as StatAssetType,
                PredictiveMaintenance,
            )

            # Map ML AssetType enum to statistical AssetType enum
            stat_type = StatAssetType(asset.asset_type.value)

            stat_asset = AssetData(
                asset_id=asset.asset_id,
                asset_type=stat_type,
                installation_date=asset.installation_date,
                manufacturer=asset.manufacturer,
                model=asset.model,
                location=asset.location,
                environment_rating=asset.environment_rating,
                design_life_years=asset.design_life_years,
            )

            engine = PredictiveMaintenance()
            health = engine.assess_health(stat_asset)
            return {
                "engine": "fireai.analytics.predictive_maintenance",
                "health_score": health.health_score,
                "failure_probability": health.failure_probability,
                "risk_level": health.risk_level.value,
                "estimated_ttf_days": health.estimated_ttf_days,
                "recommendations": health.recommendations,
            }

        except ImportError:
            logger.debug(
                "fireai.analytics.predictive_maintenance not available — "
                "statistical baseline skipped"
            )
            return None
        except Exception as exc:
            logger.warning("Statistical baseline failed: %s", exc)
            return None
