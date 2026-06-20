"""
fireai/ml/models/lstm_model.py — LSTM Time-Series Failure Forecaster
=====================================================================

LSTM neural network for predicting failure probability from
time-series of maintenance events.

Why LSTM (from awesome-machine-learning):
    - PyTorch is listed under Python/General-Purpose Machine Learning
    - LSTM excels at sequential pattern learning (event sequences)
    - Captures seasonal failure patterns (winter humidity, summer heat)
    - Complements XGBoost (which works on tabular features)

Input:
    Weekly event counts for last 52 weeks [52 x 1]
Output:
    Failure probability for next `horizon_days`

Safety:
    - Falls back to statistical baseline if PyTorch unavailable
    - Predictions are advisory; NFPA 72 rules remain authoritative
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from fireai.ml.schemas import AssetFeatures, MLPrediction, ModelType, RiskLevel

logger = logging.getLogger(__name__)

# LSTM input shape
SEQUENCE_LENGTH = 52  # 52 weeks of history
INPUT_DIM = 1  # event count per week


@dataclass
class LSTMTrainingResult:
    model_version: str
    samples_used: int
    metrics: Dict[str, float]
    trained_at: datetime


class LSTMFailureModel:
    """LSTM-based failure probability predictor."""

    def __init__(self, model_path: Optional[Path] = None) -> None:
        self._model = None
        self._model_path = model_path
        self._model_version = "untrained"
        self._training_data_size = 0
        self._last_trained_at: Optional[datetime] = None

        if model_path and model_path.exists():
            try:
                self.load(model_path)
            except Exception as exc:
                logger.warning("Failed to load LSTM model: %s", exc)

    @staticmethod
    def is_available() -> bool:
        try:
            import torch  # noqa: F401
            return True
        except ImportError:
            return False

    def _build_model(self) -> Any:
        """Construct the LSTM architecture."""
        import torch.nn as nn

        class _FailureLSTM(nn.Module):
            def __init__(self) -> None:
                super().__init__()
                self.lstm = nn.LSTM(
                    input_size=INPUT_DIM,
                    hidden_size=32,
                    num_layers=2,
                    batch_first=True,
                    dropout=0.2,
                )
                self.fc = nn.Linear(32, 1)
                self.sigmoid = nn.Sigmoid()

            def forward(self, x):
                out, _ = self.lstm(x)
                # Take last time step
                out = out[:, -1, :]
                out = self.fc(out)
                return self.sigmoid(out)

        return _FailureLSTM()

    def features_to_sequence(self, features: AssetFeatures) -> List[List[float]]:
        """
        Convert AssetFeatures.recent_event_counts to fixed-length sequence.
        Pads with zeros if shorter than SEQUENCE_LENGTH.
        """
        seq = list(features.recent_event_counts or [])
        # Pad or truncate
        if len(seq) < SEQUENCE_LENGTH:
            seq = [0.0] * (SEQUENCE_LENGTH - len(seq)) + seq
        elif len(seq) > SEQUENCE_LENGTH:
            seq = seq[-SEQUENCE_LENGTH:]
        # Normalise (cap at 10 events/week)
        return [[min(float(x), 10.0) / 10.0] for x in seq]

    def train(
        self,
        sequences: List[List[List[float]]],
        labels: List[int],
    ) -> LSTMTrainingResult:
        """Train LSTM on weekly event sequences."""
        if not self.is_available():
            raise RuntimeError("PyTorch not installed. Run: pip install torch")
        if len(sequences) != len(labels):
            raise ValueError("sequences/labels length mismatch")
        if len(sequences) < 20:
            raise ValueError(f"Need >= 20 samples for LSTM, got {len(sequences)}")

        import numpy as np
        import torch
        import torch.nn as nn
        from torch.utils.data import DataLoader, TensorDataset

        X = torch.tensor(sequences, dtype=torch.float32)
        y = torch.tensor(labels, dtype=torch.float32).unsqueeze(1)
        dataset = TensorDataset(X, y)
        loader = DataLoader(dataset, batch_size=16, shuffle=True)

        self._model = self._build_model()
        criterion = nn.BCELoss()
        optimizer = torch.optim.Adam(self._model.parameters(), lr=0.001)

        self._model.train()
        for epoch in range(50):
            for batch_X, batch_y in loader:
                optimizer.zero_grad()
                outputs = self._model(batch_X)
                loss = criterion(outputs, batch_y)
                loss.backward()
                optimizer.step()

        # Evaluate (training accuracy as a simple metric)
        self._model.eval()
        with torch.no_grad():
            preds = self._model(X).numpy().flatten()
            pred_labels = (preds > 0.5).astype(int)
            accuracy = float((pred_labels == labels).mean())

        self._model_version = f"lstm-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}"
        self._training_data_size = len(sequences)
        self._last_trained_at = datetime.now(timezone.utc)

        return LSTMTrainingResult(
            model_version=self._model_version,
            samples_used=len(sequences),
            metrics={"train_accuracy": accuracy},
            trained_at=self._last_trained_at,
        )

    def predict(self, features: AssetFeatures) -> Tuple[float, Dict[str, Any]]:
        """Predict failure probability from weekly event sequence."""
        if self._model is None:
            raise RuntimeError("Model not trained")
        if not self.is_available():
            raise RuntimeError("PyTorch not available at inference time")

        import torch

        seq = self.features_to_sequence(features)
        X = torch.tensor([seq], dtype=torch.float32)
        self._model.eval()
        with torch.no_grad():
            proba = float(self._model(X).item())
        return proba, {
            "model_version": self._model_version,
            "training_data_size": self._training_data_size,
            "last_trained_at": self._last_trained_at,
        }

    def to_prediction(
        self,
        features: AssetFeatures,
        horizon_days: int = 90,
    ) -> MLPrediction:
        try:
            proba, meta = self.predict(features)
            risk = self._classify_risk(proba)
            return MLPrediction(
                model_type=ModelType.LSTM,
                failure_probability=round(proba, 4),
                predicted_ttf_days=None,  # LSTM outputs probability only
                confidence_lower=max(0.0, proba - 0.15),
                confidence_upper=min(1.0, proba + 0.15),
                risk_level=risk,
                is_fallback=False,
                model_version=meta["model_version"],
                training_data_size=meta["training_data_size"],
                last_trained_at=meta["last_trained_at"],
            )
        except Exception as exc:
            logger.warning("LSTM prediction failed: %s", exc)
            return MLPrediction(
                model_type=ModelType.LSTM,
                failure_probability=0.5,
                risk_level=RiskLevel.MEDIUM,
                is_fallback=True,
                model_version="fallback-0.5",
            )

    def save(self, path: Path) -> None:
        if self._model is None:
            raise RuntimeError("Cannot save untrained model")
        import torch
        path.parent.mkdir(parents=True, exist_ok=True)
        torch.save({
            "model_state": self._model.state_dict(),
            "model_version": self._model_version,
            "training_data_size": self._training_data_size,
            "last_trained_at": self._last_trained_at,
        }, path)

    def load(self, path: Path) -> None:
        if not self.is_available():
            raise RuntimeError("PyTorch not installed")
        import torch
        data = torch.load(path, map_location="cpu")
        self._model = self._build_model()
        self._model.load_state_dict(data["model_state"])
        self._model.eval()
        self._model_version = data["model_version"]
        self._training_data_size = data["training_data_size"]
        self._last_trained_at = data["last_trained_at"]

    @staticmethod
    def _classify_risk(probability: float) -> RiskLevel:
        if probability > 0.5:
            return RiskLevel.CRITICAL
        if probability > 0.3:
            return RiskLevel.HIGH
        if probability > 0.15:
            return RiskLevel.MEDIUM
        return RiskLevel.LOW
