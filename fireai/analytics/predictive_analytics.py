"""fireai/analytics/predictive_analytics.py — Forecasting Engine
================================================================
Holt-Winters exponential smoothing for time-series forecasting with
moving-average fallback. Produces JSON-serialisable forecast reports
with confidence intervals.
"""

from __future__ import annotations

import json
import logging
import math
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


# ── data classes ──────────────────────────────────────────────────────────────


@dataclass
class DeviceEvent:
    device_id: str
    event_type: str  # "alarm", "trouble", "maintenance", "test", "failure"
    timestamp: datetime
    value: Optional[float] = None
    location: Optional[str] = None


@dataclass
class FailurePrediction:
    device_id: str
    predicted_ttf_hours: float
    confidence_lower: float
    confidence_upper: float
    probability: float
    failure_mode: str
    features_used: List[str]
    generated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), default=str, indent=2)


@dataclass
class CoverageForecast:
    room_id: str
    days: int
    daily_coverage_pct: List[float]
    trend: str  # "improving", "stable", "degrading"
    degradation_rate: float
    confidence_lower: List[float]
    confidence_upper: List[float]
    generated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), default=str, indent=2)


@dataclass
class LoadProfile:
    system_id: str
    timestamps: List[datetime]
    loads: List[float]


@dataclass
class CapacityPrediction:
    system_id: str
    current_load: float
    capacity: float
    predicted_peak: float
    headroom_pct: float
    risk: str  # "low", "medium", "high", "critical"
    confidence_lower: float
    confidence_upper: float
    generated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), default=str, indent=2)


@dataclass
class BuildingData:
    building_id: str
    rooms: List[str]
    age_years: float
    env_factor: float = 1.0  # 1.0 = nominal, >1.0 = harsh environment


@dataclass
class RiskScore:
    building_id: str
    composite_score: float
    failure_prob: float
    coverage_gap: float
    age_factor: float
    env_factor: float
    risk_level: str  # "low", "moderate", "high", "critical"
    recommendations: List[str]
    generated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), default=str, indent=2)


# ── Holt-Winters implementation ─────────────────────────────────────────────


def _holt_winters_forecast(
    series: List[float],
    horizon: int,
    alpha: float = 0.3,
    beta: float = 0.1,
    gamma: float = 0.1,
    season_period: int = 7,
) -> Dict[str, List[float]]:
    n = len(series)
    if n < 2:
        m = sum(series) / max(len(series), 1)
        return {
            "forecast": [m] * horizon,
            "lower": [m] * horizon,
            "upper": [m] * horizon,
        }
    if n < season_period * 2:
        return _moving_average_forecast(series, horizon)

    level = series[0]
    trend = 0.0
    if n > 1:
        trend = (series[-1] - series[0]) / max(n - 1, 1)

    seasonal = [0.0] * season_period
    if n >= season_period:
        seasonal_avg = sum(series[:season_period]) / season_period
        for i in range(season_period):
            seasonal[i] = series[i] / max(seasonal_avg, 1e-9)
    else:
        seasonal = [1.0] * season_period

    for i in range(n):
        obs = series[i]
        if i < season_period:
            continue
        prev_level = level
        season_idx = i % season_period
        level = alpha * (obs / max(seasonal[season_idx], 1e-9)) + (1 - alpha) * (level + trend)
        trend = beta * (level - prev_level) + (1 - beta) * trend
        seasonal[season_idx] = gamma * (obs / max(level, 1e-9)) + (1 - gamma) * seasonal[season_idx]

    forecast: List[float] = []
    lower: List[float] = []
    upper: List[float] = []
    residuals = _compute_residuals(series, level, trend, seasonal)
    std_err = max(_std_dev(residuals), 1e-9)

    for h in range(horizon):
        season_idx = (n + h) % season_period
        fc = (level + (h + 1) * trend) * seasonal[season_idx]
        forecast.append(fc)
        ci = 1.96 * std_err * math.sqrt(1 + (h + 1) / max(n, 1))
        lower.append(fc - ci)
        upper.append(fc + ci)

    return {"forecast": forecast, "lower": lower, "upper": upper}


def _moving_average_forecast(
    series: List[float], horizon: int, window: int = 5
) -> Dict[str, List[float]]:
    n = len(series)
    if n == 0:
        return {"forecast": [0.0] * horizon, "lower": [0.0] * horizon, "upper": [0.0] * horizon}
    w = min(window, n)
    ma = sum(series[-w:]) / w
    residuals = [abs(series[i] - sum(series[max(0, i - w):i]) / max(len(series[max(0, i - w):i]), 1)) for i in range(n)]
    std_err = max(_std_dev(residuals), 1e-9) if len(residuals) > 1 else 1.0
    forecast = [ma] * horizon
    lower = [ma - 1.96 * std_err] * horizon
    upper = [ma + 1.96 * std_err] * horizon
    return {"forecast": forecast, "lower": lower, "upper": upper}


def _compute_residuals(
    series: List[float], level: float, trend: float, seasonal: List[float]
) -> List[float]:
    residuals: List[float] = []
    for i in range(len(seasonal), len(series)):
        season_idx = i % len(seasonal)
        fitted = (level + (i - len(seasonal) + 1) * trend) * seasonal[season_idx]
        residuals.append(series[i] - fitted)
    return residuals if residuals else [0.0]


def _std_dev(values: List[float]) -> float:
    n = len(values)
    if n < 2:
        return 0.0
    mean = sum(values) / n
    var = sum((v - mean) ** 2 for v in values) / (n - 1)
    return math.sqrt(max(var, 0.0))


def _trend_from_forecast(forecast: List[float]) -> str:
    if len(forecast) < 2:
        return "stable"
    first = sum(forecast[:len(forecast) // 3]) / max(len(forecast[:len(forecast) // 3]), 1)
    last = sum(forecast[-len(forecast) // 3:]) / max(len(forecast[-len(forecast) // 3:]), 1)
    diff = last - first
    if diff > 0.01 * abs(first):
        return "improving"
    if diff < -0.01 * abs(first):
        return "degrading"
    return "stable"


# ── PredictiveAnalyticsEngine ────────────────────────────────────────────────


class PredictiveAnalyticsEngine:
    """Forecasting engine for:
    - Detector failure prediction (time-to-failure estimation)
    - Coverage degradation prediction
    - Capacity prediction (battery, circuit load)
    - Risk scoring per room/building
    """

    def __init__(
        self,
        alpha: float = 0.3,
        beta: float = 0.1,
        gamma: float = 0.1,
        season_period: int = 7,
    ):
        self.alpha = alpha
        self.beta = beta
        self.gamma = gamma
        self.season_period = season_period

    def predict_failure(self, device_history: List[DeviceEvent]) -> FailurePrediction:
        if not device_history:
            return FailurePrediction(
                device_id="unknown",
                predicted_ttf_hours=87600.0,
                confidence_lower=43800.0,
                confidence_upper=175200.0,
                probability=0.01,
                failure_mode="insufficient_data",
                features_used=[],
            )

        device_id = device_history[0].device_id
        events_sorted = sorted(device_history, key=lambda e: e.timestamp)
        now = datetime.now(timezone.utc)

        age_hours: List[float] = []
        for evt in events_sorted:
            delta = (now - evt.timestamp).total_seconds() / 3600.0
            age_hours.append(max(delta, 0.0))

        if len(age_hours) < 2:
            return FailurePrediction(
                device_id=device_id,
                predicted_ttf_hours=87600.0,
                confidence_lower=43800.0,
                confidence_upper=175200.0,
                probability=0.01,
                failure_mode="insufficient_data",
                features_used=["age_hours"],
            )

        failure_events = [e for e in events_sorted if e.event_type == "failure"]
        trouble_events = [e for e in events_sorted if e.event_type in ("trouble", "maintenance")]
        failure_rate = len(failure_events) / max(len(age_hours), 1)
        trouble_rate = len(trouble_events) / max(len(age_hours), 1)

        fc = _holt_winters_forecast(age_hours, horizon=30, alpha=self.alpha, beta=self.beta, gamma=self.gamma, season_period=self.season_period)
        fc["forecast"][-1] if fc["forecast"] else age_hours[-1]

        base_ttf = 87600.0
        if failure_rate > 0:
            base_ttf = (1.0 / max(failure_rate, 1e-9)) * 24.0
        elif trouble_rate > 0:
            base_ttf = (1.0 / max(trouble_rate, 1e-9)) * 48.0

        ttf = max(base_ttf, 24.0)
        probability = min(max(failure_rate * 10.0, 0.001), 0.99)

        ci_lower = max(ttf * 0.5, 12.0)
        ci_upper = ttf * 1.5

        mode = "wear_out"
        if failure_rate > 0.05:
            mode = "elevated_failure_rate"
        elif trouble_rate > 0.1:
            mode = "maintenance_deficit"

        features = ["age_hours", "failure_rate", "trouble_rate", "event_count"]

        return FailurePrediction(
            device_id=device_id,
            predicted_ttf_hours=round(ttf, 2),
            confidence_lower=round(ci_lower, 2),
            confidence_upper=round(ci_upper, 2),
            probability=round(probability, 4),
            failure_mode=mode,
            features_used=features,
        )

    def predict_coverage_degradation(self, room_id: str, days: int) -> CoverageForecast:
        datetime.now(timezone.utc)
        n = max(days, 1)
        coverage_series = self._simulate_recent_coverage(room_id)
        horizon = n

        fc = _holt_winters_forecast(coverage_series, horizon, alpha=self.alpha, beta=self.beta, gamma=self.gamma, season_period=min(self.season_period, max(len(coverage_series) // 2, 2)))

        forecast_values = fc["forecast"]
        lower_values = fc["lower"]
        upper_values = fc["upper"]

        trend = _trend_from_forecast(forecast_values)
        if coverage_series:
            degradation = (coverage_series[-1] - forecast_values[-1]) / max(coverage_series[-1], 1e-9)
        else:
            degradation = 0.0

        return CoverageForecast(
            room_id=room_id,
            days=n,
            daily_coverage_pct=[round(v, 4) for v in forecast_values],
            trend=trend,
            degradation_rate=round(degradation, 6),
            confidence_lower=[round(v, 4) for v in lower_values],
            confidence_upper=[round(v, 4) for v in upper_values],
        )

    def _simulate_recent_coverage(self, room_id: str) -> List[float]:
        return [0.95, 0.94, 0.93, 0.91, 0.90, 0.89, 0.88, 0.86, 0.85, 0.83]

    def predict_capacity(self, system_id: str, load_profile: LoadProfile) -> CapacityPrediction:
        loads = load_profile.loads
        if not loads:
            return CapacityPrediction(
                system_id=system_id,
                current_load=0.0,
                capacity=100.0,
                predicted_peak=0.0,
                headroom_pct=100.0,
                risk="low",
                confidence_lower=0.0,
                confidence_upper=0.0,
            )

        current_load = loads[-1]
        capacity = max(current_load * 1.5, 100.0)

        fc = _holt_winters_forecast(loads, horizon=30, alpha=0.5, beta=0.05, gamma=0.0, season_period=min(7, max(len(loads) // 2, 2)))
        predicted_peak = max(fc["forecast"]) if fc["forecast"] else current_load

        headroom = max(0.0, (capacity - predicted_peak) / max(capacity, 1e-9) * 100.0)
        if headroom > 40.0:
            risk = "low"
        elif headroom > 20.0:
            risk = "medium"
        elif headroom > 10.0:
            risk = "high"
        else:
            risk = "critical"

        ci_lower = max(predicted_peak * 0.85, 0.0)
        ci_upper = predicted_peak * 1.15

        return CapacityPrediction(
            system_id=system_id,
            current_load=round(current_load, 4),
            capacity=round(capacity, 4),
            predicted_peak=round(predicted_peak, 4),
            headroom_pct=round(headroom, 2),
            risk=risk,
            confidence_lower=round(ci_lower, 4),
            confidence_upper=round(ci_upper, 4),
        )

    def score_risk(self, building: BuildingData) -> RiskScore:
        failure_prob = 0.05 + building.age_years * 0.005
        coverage_gap = max(0.0, 1.0 - (0.92 - building.age_years * 0.002))
        age_factor = min(building.age_years / 30.0, 1.0)
        env_factor = building.env_factor

        weights = {"failure_prob": 0.3, "coverage_gap": 0.3, "age_factor": 0.2, "env_factor": 0.2}
        composite = (
            weights["failure_prob"] * min(failure_prob, 1.0)
            + weights["coverage_gap"] * min(coverage_gap, 1.0)
            + weights["age_factor"] * min(age_factor, 1.0)
            + weights["env_factor"] * min(env_factor, 1.0)
        )

        if composite < 0.2:
            risk_level = "low"
        elif composite < 0.4:
            risk_level = "moderate"
        elif composite < 0.7:
            risk_level = "high"
        else:
            risk_level = "critical"

        recommendations: List[str] = []
        if failure_prob > 0.1:
            recommendations.append("Schedule proactive maintenance for aging detectors")
        if coverage_gap > 0.05:
            recommendations.append("Review and remediate coverage gaps")
        if age_factor > 0.6:
            recommendations.append("Consider detector replacement program for aged devices")
        if env_factor > 1.2:
            recommendations.append("Upgrade environmental protection for harsh conditions")
        if not recommendations:
            recommendations.append("Routine monitoring sufficient")

        return RiskScore(
            building_id=building.building_id,
            composite_score=round(composite, 4),
            failure_prob=round(failure_prob, 4),
            coverage_gap=round(coverage_gap, 4),
            age_factor=round(age_factor, 4),
            env_factor=round(env_factor, 4),
            risk_level=risk_level,
            recommendations=recommendations,
        )

    def generate_report(self, prediction: Any) -> str:
        if hasattr(prediction, "to_json"):
            return prediction.to_json()
        return json.dumps(asdict(prediction), default=str, indent=2)
