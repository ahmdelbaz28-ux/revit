"""
fireai/analytics/ml_pipeline.py — End-to-End ML Pipeline
============================================================
Feature engineering, model registry, training with cross-validation,
and evaluation framework for fire alarm design data.
"""

from __future__ import annotations

import copy
import json
import logging
import math
import os
import pickle
import random
import sqlite3
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# ── data classes ──────────────────────────────────────────────────────────────


@dataclass
class RoomDesignData:
    room_id: str
    area: float
    ceiling_height: float
    detector_count: int
    obstruction_count: int
    beam_depth_ratio: float
    wall_proximity_min: float
    hvac_proximity_min: float
    coverage_pct: float = 0.0


@dataclass
class DesignData:
    building_id: str
    rooms: List[RoomDesignData]


@dataclass
class FeatureSet:
    features: List[List[float]]
    feature_names: List[str]
    target: Optional[List[float]] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), default=str, indent=2)


@dataclass
class ModelMetadata:
    version_id: str
    created_at: str
    metrics: Dict[str, float]
    hyperparameters: Dict[str, Any]
    feature_names: List[str]
    target: str
    model_type: str
    artifact_path: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), default=str, indent=2)


@dataclass
class ModelArtifact:
    metadata: ModelMetadata
    model_data: bytes  # serialised model binary

    def to_dict(self) -> Dict[str, Any]:
        return {
            "metadata": asdict(self.metadata),
            "model_data_size": len(self.model_data),
        }


@dataclass
class EvaluationReport:
    accuracy: Optional[float] = None
    precision: Optional[float] = None
    recall: Optional[float] = None
    f1: Optional[float] = None
    mae: Optional[float] = None
    rmse: Optional[float] = None
    r2: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        return {k: v for k, v in asdict(self).items() if v is not None}

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), default=str, indent=2)


# ── Pure-Python ML implementations (fallback when sklearn unavailable) ──────


class _LinearRegression:
    def __init__(self):
        self.coef_: List[float] = []
        self.intercept_: float = 0.0

    def fit(self, X: List[List[float]], y: List[float]) -> None:
        n = len(X)
        m = len(X[0]) if X else 0
        if n == 0 or m == 0:
            self.coef_ = [0.0] * m
            self.intercept_ = 0.0
            return
        Xt = list(zip(*X))
        x_means = [sum(col) / n for col in Xt]
        y_mean = sum(y) / n
        coef: List[float] = []
        for j in range(m):
            num = sum((X[i][j] - x_means[j]) * (y[i] - y_mean) for i in range(n))
            den = sum((X[i][j] - x_means[j]) ** 2 for i in range(n))
            coef.append(num / den if den != 0 else 0.0)
        self.coef_ = coef
        self.intercept_ = y_mean - sum(c * xm for c, xm in zip(coef, x_means))

    def predict(self, X: List[List[float]]) -> List[float]:
        return [self.intercept_ + sum(c * x[j] for j, c in enumerate(self.coef_)) for x in X]


class _RandomForestClassifier:
    def __init__(self, n_estimators: int = 10, max_depth: int = 5, random_state: int = 42):
        self.n_estimators = n_estimators
        self.max_depth = max_depth
        self.random_state = random_state
        self.trees: List[dict] = []

    def fit(self, X: List[List[float]], y: List[float]) -> None:
        random.seed(self.random_state)
        self.trees = []
        n = len(X)
        m = len(X[0]) if X else 0
        for _ in range(self.n_estimators):
            indices = [random.randint(0, n - 1) for _ in range(n)]
            X_boot = [X[i] for i in indices]
            y_boot = [y[i] for i in indices]
            tree = self._build_tree(X_boot, y_boot, depth=0)
            self.trees.append(tree)

    def _build_tree(self, X: List[List[float]], y: List[float], depth: int) -> dict:
        if depth >= self.max_depth or len(set(y)) <= 1 or len(X) <= 2:
            return {"leaf": True, "value": sum(y) / max(len(y), 1) if y else 0.0}
        m = len(X[0]) if X else 0
        best_gini = float("inf")
        best_feat = 0
        best_thresh = 0.0
        for feat in range(m):
            values = sorted(set(X[i][feat] for i in range(len(X))))
            for val in values:
                left_y = [y[i] for i in range(len(X)) if X[i][feat] <= val]
                right_y = [y[i] for i in range(len(X)) if X[i][feat] > val]
                if not left_y or not right_y:
                    continue
                gini = self._gini(left_y) * len(left_y) / len(y) + self._gini(right_y) * len(right_y) / len(y)
                if gini < best_gini:
                    best_gini = gini
                    best_feat = feat
                    best_thresh = val
        if best_gini == float("inf"):
            return {"leaf": True, "value": sum(y) / max(len(y), 1)}
        left_X = [X[i] for i in range(len(X)) if X[i][best_feat] <= best_thresh]
        left_y = [y[i] for i in range(len(X)) if X[i][best_feat] <= best_thresh]
        right_X = [X[i] for i in range(len(X)) if X[i][best_feat] > best_thresh]
        right_y = [y[i] for i in range(len(X)) if X[i][best_feat] > best_thresh]
        return {
            "leaf": False,
            "feature": best_feat,
            "threshold": best_thresh,
            "left": self._build_tree(left_X, left_y, depth + 1),
            "right": self._build_tree(right_X, right_y, depth + 1),
        }

    def _gini(self, y: List[float]) -> float:
        if not y:
            return 0.0
        p = sum(y) / len(y)
        return 1.0 - p ** 2 - (1 - p) ** 2

    def predict(self, X: List[List[float]]) -> List[float]:
        results: List[float] = []
        for x in X:
            votes: List[float] = []
            for tree in self.trees:
                votes.append(self._predict_tree(tree, x))
            results.append(1.0 if sum(votes) / max(len(votes), 1) > 0.5 else 0.0)
        return results

    def _predict_tree(self, node: dict, x: List[float]) -> float:
        if node.get("leaf"):
            return node["value"]
        if x[node["feature"]] <= node["threshold"]:
            return self._predict_tree(node["left"], x)
        return self._predict_tree(node["right"], x)


class _RandomForestRegressor:
    def __init__(self, n_estimators: int = 10, max_depth: int = 5, random_state: int = 42):
        self.n_estimators = n_estimators
        self.max_depth = max_depth
        self.random_state = random_state
        self.trees: List[dict] = []

    def fit(self, X: List[List[float]], y: List[float]) -> None:
        random.seed(self.random_state)
        self.trees = []
        n = len(X)
        for _ in range(self.n_estimators):
            indices = [random.randint(0, n - 1) for _ in range(n)]
            X_boot = [X[i] for i in indices]
            y_boot = [y[i] for i in indices]
            tree = self._build_tree(X_boot, y_boot, depth=0)
            self.trees.append(tree)

    def _build_tree(self, X: List[List[float]], y: List[float], depth: int) -> dict:
        if depth >= self.max_depth or len(X) <= 2:
            return {"leaf": True, "value": sum(y) / max(len(y), 1) if y else 0.0}
        m = len(X[0]) if X else 0
        best_mse = float("inf")
        best_feat = 0
        best_thresh = 0.0
        for feat in range(m):
            values = sorted(set(X[i][feat] for i in range(len(X))))
            for val in values:
                left_y = [y[i] for i in range(len(X)) if X[i][feat] <= val]
                right_y = [y[i] for i in range(len(X)) if X[i][feat] > val]
                if not left_y or not right_y:
                    continue
                mse = self._mse(left_y) * len(left_y) / len(y) + self._mse(right_y) * len(right_y) / len(y)
                if mse < best_mse:
                    best_mse = mse
                    best_feat = feat
                    best_thresh = val
        if best_mse == float("inf"):
            return {"leaf": True, "value": sum(y) / max(len(y), 1)}
        left_X = [X[i] for i in range(len(X)) if X[i][best_feat] <= best_thresh]
        left_y = [y[i] for i in range(len(X)) if X[i][best_feat] <= best_thresh]
        right_X = [X[i] for i in range(len(X)) if X[i][best_feat] > best_thresh]
        right_y = [y[i] for i in range(len(X)) if X[i][best_feat] > best_thresh]
        return {
            "leaf": False,
            "feature": best_feat,
            "threshold": best_thresh,
            "left": self._build_tree(left_X, left_y, depth + 1),
            "right": self._build_tree(right_X, right_y, depth + 1),
        }

    def _mse(self, y: List[float]) -> float:
        if not y:
            return 0.0
        mean = sum(y) / len(y)
        return sum((v - mean) ** 2 for v in y) / len(y)

    def predict(self, X: List[List[float]]) -> List[float]:
        results: List[float] = []
        for x in X:
            preds = [self._predict_tree(tree, x) for tree in self.trees]
            results.append(sum(preds) / max(len(preds), 1))
        return results

    def _predict_tree(self, node: dict, x: List[float]) -> float:
        if node.get("leaf"):
            return node["value"]
        if x[node["feature"]] <= node["threshold"]:
            return self._predict_tree(node["left"], x)
        return self._predict_tree(node["right"], x)


# ── sklearn wrapper ─────────────────────────────────────────────────────────


def _get_sklearn_model(model_type: str, hyperparameters: Dict[str, Any]) -> Any:
    try:
        from sklearn.ensemble import RandomForestClassifier, RandomForestRegressor
        from sklearn.linear_model import LinearRegression

        if model_type == "linear_regression":
            return LinearRegression(**{k: v for k, v in hyperparameters.items() if k in ("fit_intercept", "normalize", "copy_X")})
        if model_type == "random_forest_classifier":
            params = {k: v for k, v in hyperparameters.items() if k in ("n_estimators", "max_depth", "random_state", "min_samples_split", "min_samples_leaf")}
            return RandomForestClassifier(**params, n_jobs=1)
        if model_type == "random_forest_regressor":
            params = {k: v for k, v in hyperparameters.items() if k in ("n_estimators", "max_depth", "random_state", "min_samples_split", "min_samples_leaf")}
            return RandomForestRegressor(**params, n_jobs=1)
    except ImportError:
        return None
    raise ValueError(f"Unknown model_type: {model_type}")


def _get_fallback_model(model_type: str, hyperparameters: Dict[str, Any]) -> Any:
    if model_type == "linear_regression":
        return _LinearRegression()
    if model_type == "random_forest_classifier":
        return _RandomForestClassifier(
            n_estimators=hyperparameters.get("n_estimators", 10),
            max_depth=hyperparameters.get("max_depth", 5),
            random_state=hyperparameters.get("random_state", 42),
        )
    if model_type == "random_forest_regressor":
        return _RandomForestRegressor(
            n_estimators=hyperparameters.get("n_estimators", 10),
            max_depth=hyperparameters.get("max_depth", 5),
            random_state=hyperparameters.get("random_state", 42),
        )
    raise ValueError(f"Unknown model_type: {model_type}")


# ── MLPipeline ───────────────────────────────────────────────────────────────


class MLPipeline:
    """
    End-to-end ML pipeline:
    - Feature engineering from fire alarm design data
    - Model registry (versioned, metadata-tagged)
    - Training pipeline with cross-validation
    - Evaluation framework with metrics
    """

    def __init__(self, registry_path: str = "fireai_ml_registry.sqlite3", artifacts_dir: str = "/tmp/fireai_models"):
        self.registry_path = registry_path
        self.artifacts_dir = artifacts_dir
        os.makedirs(artifacts_dir, exist_ok=True)
        self._conn = sqlite3.connect(registry_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._create_registry_tables()

    def _create_registry_tables(self) -> None:
        cursor = self._conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS model_registry (
                version_id TEXT PRIMARY KEY,
                created_at TEXT NOT NULL,
                metrics TEXT NOT NULL,
                hyperparameters TEXT NOT NULL,
                feature_names TEXT NOT NULL,
                target TEXT NOT NULL,
                model_type TEXT NOT NULL,
                artifact_path TEXT NOT NULL
            )
        """)
        self._conn.commit()

    def engineer_features(self, design: DesignData) -> FeatureSet:
        features: List[List[float]] = []
        feature_names = [
            "room_area",
            "ceiling_height",
            "detector_count",
            "coverage_pct",
            "obstruction_count",
            "beam_depth_ratio",
            "wall_proximity",
            "hvac_proximity",
        ]
        for room in design.rooms:
            row = [
                room.area,
                room.ceiling_height,
                float(room.detector_count),
                room.coverage_pct,
                float(room.obstruction_count),
                room.beam_depth_ratio,
                room.wall_proximity_min,
                room.hvac_proximity_min,
            ]
            features.append(row)
        return FeatureSet(features=features, feature_names=feature_names)

    def train(
        self,
        features: FeatureSet,
        target: str = "coverage_pct",
        model_type: str = "linear_regression",
        hyperparameters: Optional[Dict[str, Any]] = None,
        test_split: float = 0.2,
        cv_folds: int = 0,
    ) -> ModelArtifact:
        if hyperparameters is None:
            hyperparameters = {}
        if not features.features:
            raise ValueError("features must contain data and target")

        X = features.features
        y = features.target
        n = len(X)

        if n < 2:
            raise ValueError(f"Need at least 2 samples, got {n}")

        n_test = max(1, int(n * test_split))
        indices = list(range(n))
        random.shuffle(indices)
        train_idx = indices[:-n_test] if n_test < n else indices
        test_idx = indices[-n_test:] if n_test < n else indices[:max(1, n // 5)]

        X_train = [X[i] for i in train_idx]
        y_train = [y[i] for i in train_idx]
        X_test = [X[i] for i in test_idx]
        y_test = [y[i] for i in test_idx]

        model = _get_sklearn_model(model_type, hyperparameters)
        if model is None:
            model = _get_fallback_model(model_type, hyperparameters)

        model.fit(X_train, y_train)

        y_pred = model.predict(X_test) if hasattr(model, "predict") else []
        eval_report = self._evaluate_model(model, model_type, X_test, y_test)

        cv_scores: List[float] = []
        if cv_folds > 1 and n >= cv_folds * 2:
            fold_size = n // cv_folds
            for fold in range(cv_folds):
                val_start = fold * fold_size
                val_end = val_start + fold_size if fold < cv_folds - 1 else n
                val_idx = list(range(val_start, val_end))
                fold_train_idx = [i for i in range(n) if i not in val_idx]
                X_ft = [X[i] for i in fold_train_idx]
                y_ft = [y[i] for i in fold_train_idx]
                X_fv = [X[i] for i in val_idx]
                y_fv = [y[i] for i in val_idx]
                if not X_fv:
                    continue
                fold_model = copy.deepcopy(model)
                fold_model.fit(X_ft, y_ft)
                fold_pred = fold_model.predict(X_fv) if hasattr(fold_model, "predict") else []
                if fold_pred and target == "coverage_pct":
                    mae = sum(abs(a - b) for a, b in zip(y_fv, fold_pred)) / max(len(fold_pred), 1)
                    cv_scores.append(mae)
            if cv_scores:
                eval_report.mae = sum(cv_scores) / len(cv_scores)

        version_id = str(uuid.uuid4())
        created_at = datetime.now(timezone.utc).isoformat()
        artifact_path = os.path.join(self.artifacts_dir, f"{version_id}.pkl")
        model_data = pickle.dumps(model)

        with open(artifact_path, "wb") as f:
            f.write(model_data)

        metrics = eval_report.to_dict()
        metadata = ModelMetadata(
            version_id=version_id,
            created_at=created_at,
            metrics=metrics,
            hyperparameters=hyperparameters,
            feature_names=features.feature_names,
            target=target,
            model_type=model_type,
            artifact_path=artifact_path,
        )

        cursor = self._conn.cursor()
        cursor.execute(
            """
            INSERT INTO model_registry (version_id, created_at, metrics, hyperparameters,
                                        feature_names, target, model_type, artifact_path)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
            (
                version_id,
                created_at,
                json.dumps(metrics),
                json.dumps(hyperparameters),
                json.dumps(features.feature_names),
                target,
                model_type,
                artifact_path,
            ),
        )
        self._conn.commit()

        logger.info("Trained model %s (type=%s, target=%s)", version_id, model_type, target)
        return ModelArtifact(metadata=metadata, model_data=model_data)

    def _evaluate_model(self, model_obj: Any, model_type: str, X_test: List[List[float]], y_test: List[float]) -> EvaluationReport:
        y_pred = model_obj.predict(X_test) if hasattr(model_obj, "predict") else []
        if not y_pred:
            return EvaluationReport()
        report = EvaluationReport()
        errors = [abs(a - b) for a, b in zip(y_test, y_pred)] if len(y_test) == len(y_pred) else []
        if errors:
            report.mae = round(sum(errors) / max(len(errors), 1), 6)
            sq_errors = [(a - b) ** 2 for a, b in zip(y_test, y_pred)]
            report.rmse = round(math.sqrt(sum(sq_errors) / max(len(sq_errors), 1)), 6)
        if model_type in ("random_forest_classifier",):
            correct = sum(1 for a, b in zip(y_test, y_pred) if abs(a - b) < 0.5) if len(y_test) == len(y_pred) else 0
            report.accuracy = round(correct / max(len(y_test), 1), 6)
            tp = sum(1 for a, b in zip(y_test, y_pred) if a > 0.5 and b > 0.5) if len(y_test) == len(y_pred) else 0
            fp = sum(1 for a, b in zip(y_test, y_pred) if a < 0.5 < b) if len(y_test) == len(y_pred) else 0
            fn = sum(1 for a, b in zip(y_test, y_pred) if a > 0.5 > b) if len(y_test) == len(y_pred) else 0
            report.precision = round(tp / max(tp + fp, 1), 6)
            report.recall = round(tp / max(tp + fn, 1), 6)
            report.f1 = round(2 * report.precision * report.recall / max(report.precision + report.recall, 1e-9), 6)
        else:
            if y_test and y_pred:
                ss_res = sum((a - b) ** 2 for a, b in zip(y_test, y_pred))
                y_mean = sum(y_test) / len(y_test)
                ss_tot = sum((a - y_mean) ** 2 for a in y_test)
                report.r2 = round(1.0 - ss_res / max(ss_tot, 1e-9), 6)
        return report

    def evaluate(self, model: ModelArtifact, test_features: FeatureSet) -> EvaluationReport:
        if not model.model_data:
            return EvaluationReport()
        model_obj = pickle.loads(model.model_data)
        X_test = test_features.features
        y_test = test_features.target if test_features.target else []
        if not X_test or not y_test:
            return EvaluationReport()
        return self._evaluate_model(model_obj, model.metadata.model_type, X_test, y_test)

    def registry_list(self) -> List[ModelMetadata]:
        cursor = self._conn.cursor()
        cursor.execute("SELECT * FROM model_registry ORDER BY created_at DESC")
        rows = cursor.fetchall()
        result: List[ModelMetadata] = []
        for row in rows:
            result.append(
                ModelMetadata(
                    version_id=row["version_id"],
                    created_at=row["created_at"],
                    metrics=json.loads(row["metrics"]),
                    hyperparameters=json.loads(row["hyperparameters"]),
                    feature_names=json.loads(row["feature_names"]),
                    target=row["target"],
                    model_type=row["model_type"],
                    artifact_path=row["artifact_path"],
                )
            )
        return result

    def registry_get(self, model_id: str) -> Optional[ModelArtifact]:
        cursor = self._conn.cursor()
        cursor.execute("SELECT * FROM model_registry WHERE version_id = ?", (model_id,))
        row = cursor.fetchone()
        if row is None:
            return None
        metadata = ModelMetadata(
            version_id=row["version_id"],
            created_at=row["created_at"],
            metrics=json.loads(row["metrics"]),
            hyperparameters=json.loads(row["hyperparameters"]),
            feature_names=json.loads(row["feature_names"]),
            target=row["target"],
            model_type=row["model_type"],
            artifact_path=row["artifact_path"],
        )
        try:
            with open(metadata.artifact_path, "rb") as f:
                model_data = f.read()
        except FileNotFoundError:
            logger.warning("Artifact file not found for %s: %s", model_id, metadata.artifact_path)
            model_data = b""
        return ModelArtifact(metadata=metadata, model_data=model_data)

    def registry_delete(self, model_id: str) -> bool:
        cursor = self._conn.cursor()
        cursor.execute("DELETE FROM model_registry WHERE version_id = ?", (model_id,))
        self._conn.commit()
        return cursor.rowcount > 0
