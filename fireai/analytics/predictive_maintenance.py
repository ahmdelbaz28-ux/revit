"""fireai/analytics/predictive_maintenance.py
============================================
Predictive Maintenance — Asset health scoring and failure prediction
for fire alarm equipment using Weibull analysis and composite health models.

References:
  - NFPA 72-2022 §14.4 — Inspection, testing and maintenance
  - IEEE 762-2006 — Reliability data for power equipment
  - IEC 60300-3-11 — Reliability centered maintenance

"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


# ===========================================================================
# Supporting Data Types
# ===========================================================================


class AssetType(str, Enum):
    DETECTOR_SMOKE = "DETECTOR_SMOKE"
    DETECTOR_HEAT = "DETECTOR_HEAT"
    DETECTOR_FLAME = "DETECTOR_FLAME"
    DETECTOR_GAS = "DETECTOR_GAS"
    NAC = "NAC"
    FACP = "FACP"
    SLC_LOOP = "SLC_LOOP"
    BATTERY = "BATTERY"
    CABLE = "CABLE"


class RiskLevel(str, Enum):
    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


class MaintenanceType(str, Enum):
    INSPECTION = "INSPECTION"
    TEST = "TEST"
    REPAIR = "REPAIR"
    REPLACEMENT = "REPLACEMENT"
    CALIBRATION = "CALIBRATION"


@dataclass(frozen=True)
class AssetData:
    asset_id: str
    asset_type: AssetType
    installation_date: datetime
    manufacturer: str = ""
    model: str = ""
    location: str = ""
    environment_rating: str = ""  # indoor, outdoor, hazardous, cleanroom
    design_life_years: float = 20.0
    metadata: Dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class MaintenanceEvent:
    event_id: str
    asset_id: str
    maintenance_type: MaintenanceType
    timestamp: datetime
    description: str = ""
    findings: str = ""
    cost: float = 0.0
    technician: str = ""


@dataclass(frozen=True)
class FailurePrediction:
    asset_id: str
    weibull_shape: float
    weibull_scale: float
    mttf_days: float
    reliability_at_365d: float
    failure_probability_90d: float
    model_type: str  # "weibull" or "exponential"


@dataclass(frozen=True)
class MaintenanceRecommendation:
    asset_id: str
    risk_level: RiskLevel
    recommended_action: str
    urgency: str  # IMMEDIATE, WITHIN_7_DAYS, WITHIN_30_DAYS, WITHIN_90_DAYS, SCHEDULED
    description: str
    estimated_cost: float = 0.0


@dataclass(frozen=True)
class AssetHealth:
    asset_id: str
    health_score: float
    failure_probability: float
    estimated_ttf_days: Optional[float]
    risk_level: RiskLevel
    recommendations: List[str]

    def __post_init__(self) -> None:
        if not 0.0 <= self.health_score <= 1.0:
            raise ValueError(f"health_score must be in [0,1], got {self.health_score}")
        if not 0.0 <= self.failure_probability <= 1.0:
            raise ValueError(f"failure_probability must be in [0,1], got {self.failure_probability}")


# ===========================================================================
# Predictive Maintenance Engine
# ===========================================================================


class PredictiveMaintenance:
    """Asset health scoring and failure prediction for fire alarm equipment.

    Health score is a weighted composite of:
      - age_factor        (0.3) — degradation vs design life
      - maintenance_factor (0.3) — how well the asset is maintained
      - event_factor       (0.2) — recent failure or alarm events
      - env_factor         (0.2) — environmental stress factors

    Failure prediction uses a Weibull distribution model when sufficient
    maintenance history is available, falling back to an exponential model.
    """

    # Health score weights
    WEIGHT_AGE = 0.3
    WEIGHT_MAINTENANCE = 0.3
    WEIGHT_EVENT = 0.2
    WEIGHT_ENV = 0.2

    # Environment factor lookup
    ENVIRONMENT_FACTORS: Dict[str, float] = {
        "indoor": 1.0,
        "outdoor": 0.75,
        "hazardous": 0.55,
        "cleanroom": 0.95,
        "corrosive": 0.40,
        "coastal": 0.60,
        "desert": 0.50,
    }

    # Default Weibull parameters by asset type (shape, scale_days)
    DEFAULT_WEIBULL: Dict[AssetType, tuple[float, float]] = {
        AssetType.DETECTOR_SMOKE: (1.8, 3650.0),
        AssetType.DETECTOR_HEAT: (2.0, 4380.0),
        AssetType.DETECTOR_FLAME: (1.5, 2920.0),
        AssetType.DETECTOR_GAS: (1.6, 2555.0),
        AssetType.NAC: (2.2, 5110.0),
        AssetType.FACP: (2.5, 7300.0),
        AssetType.SLC_LOOP: (2.0, 5475.0),
        AssetType.BATTERY: (1.3, 1460.0),
        AssetType.CABLE: (3.0, 10950.0),
    }

    def __init__(self) -> None:
        self._history_cache: Dict[str, List[MaintenanceEvent]] = {}

    # ── Public API ────────────────────────────────────────────────────────

    def assess_health(self, asset: AssetData) -> AssetHealth:
        age_factor = self._compute_age_factor(asset)
        maintenance_factor = self._compute_maintenance_factor(asset)
        event_factor = self._compute_event_factor(asset)
        env_factor = self._compute_env_factor(asset)

        health_score = (
            age_factor * self.WEIGHT_AGE
            + maintenance_factor * self.WEIGHT_MAINTENANCE
            + event_factor * self.WEIGHT_EVENT
            + env_factor * self.WEIGHT_ENV
        )
        health_score = max(0.0, min(1.0, health_score))

        history = self._history_cache.get(asset.asset_id, [])
        prediction = self.predict_failure(history, asset)
        failure_prob = prediction.failure_probability_90d
        risk_level = self._classify_risk(health_score, failure_prob)

        recommendations = self._generate_recommendations(
            asset, health_score, risk_level
        )

        ttf = self._estimate_ttf(health_score, prediction)

        return AssetHealth(
            asset_id=asset.asset_id,
            health_score=round(health_score, 4),
            failure_probability=round(failure_prob, 4),
            estimated_ttf_days=ttf,
            risk_level=risk_level,
            recommendations=recommendations,
        )

    def predict_failure(
        self,
        maintenance_history: List[MaintenanceEvent],
        asset: Optional[AssetData] = None,
    ) -> FailurePrediction:
        asset_type = asset.asset_type if asset else AssetType.DETECTOR_SMOKE
        shape, scale = self.DEFAULT_WEIBULL.get(asset_type, (1.8, 3650.0))

        # If we have repair/replacement events, fit Weibull parameters
        if maintenance_history:
            try:
                fitted_shape, fitted_scale = self._fit_weibull(
                    maintenance_history
                )
                shape = fitted_shape
                scale = fitted_scale
            except Exception:
                logger.warning(
                    "Weibull fit failed for asset, using defaults"
                )

        model_type = "weibull"
        mttf = scale * math.gamma(1.0 + 1.0 / shape)
        reliability_365 = math.exp(-((365.0 / scale) ** shape))
        prob_90 = 1.0 - math.exp(-((90.0 / scale) ** shape))

        # Fallback: exponential if shape is degenerate
        if shape <= 0.1 or not math.isfinite(mttf):
            lambda_exp = 1.0 / scale
            mttf = scale
            reliability_365 = math.exp(-lambda_exp * 365.0)
            prob_90 = 1.0 - math.exp(-lambda_exp * 90.0)
            model_type = "exponential"

        asset_id = (
            maintenance_history[0].asset_id
            if maintenance_history
            else (asset.asset_id if asset else "unknown")
        )

        return FailurePrediction(
            asset_id=asset_id,
            weibull_shape=round(shape, 4),
            weibull_scale=round(scale, 2),
            mttf_days=round(mttf, 2),
            reliability_at_365d=round(reliability_365, 4),
            failure_probability_90d=round(prob_90, 4),
            model_type=model_type,
        )

    def recommend_maintenance(
        self, asset: AssetData
    ) -> MaintenanceRecommendation:
        health = self.assess_health(asset)
        risk = health.risk_level

        if risk == RiskLevel.CRITICAL:
            return MaintenanceRecommendation(
                asset_id=asset.asset_id,
                risk_level=risk,
                recommended_action="REPLACE",
                urgency="IMMEDIATE",
                description=(
                    f"Asset {asset.asset_id} is at CRITICAL risk "
                    f"(score={health.health_score:.2f}). "
                    f"Immediate replacement required to maintain "
                    f"life-safety compliance."
                ),
            )
        if risk == RiskLevel.HIGH:
            return MaintenanceRecommendation(
                asset_id=asset.asset_id,
                risk_level=risk,
                recommended_action="REPAIR_OR_REPLACE",
                urgency="WITHIN_7_DAYS",
                description=(
                    f"Asset {asset.asset_id} is at HIGH risk. "
                    f"Schedule detailed inspection and prepare "
                    f"for replacement within 7 days."
                ),
            )
        if risk == RiskLevel.MEDIUM:
            return MaintenanceRecommendation(
                asset_id=asset.asset_id,
                risk_level=risk,
                recommended_action="INSPECT",
                urgency="WITHIN_30_DAYS",
                description=(
                    f"Asset {asset.asset_id} is at MEDIUM risk. "
                    f"Schedule inspection within 30 days."
                ),
            )
        return MaintenanceRecommendation(
            asset_id=asset.asset_id,
            risk_level=risk,
            recommended_action="ROUTINE_MAINTENANCE",
            urgency="SCHEDULED",
            description=(
                f"Asset {asset.asset_id} is at LOW risk. "
                f"Continue routine maintenance per NFPA 72 §14.4."
            ),
        )

    # ── Internal: Health score components ────────────────────────────────

    def _compute_age_factor(self, asset: AssetData) -> float:
        age_days = (datetime.now(timezone.utc) - asset.installation_date).days
        design_days = asset.design_life_years * 365.25
        if design_days <= 0:
            return 1.0
        ratio = age_days / design_days
        if ratio >= 1.5:
            return 0.0
        if ratio >= 1.0:
            return 0.15
        if ratio >= 0.75:
            return 0.40
        if ratio >= 0.5:
            return 0.65
        if ratio >= 0.25:
            return 0.85
        return 1.0

    def _compute_maintenance_factor(
        self, asset: AssetData
    ) -> float:
        history = self._history_cache.get(asset.asset_id, [])
        if not history:
            return 0.5  # Neutral — no data

        now = datetime.now(timezone.utc)
        # Recent maintenance within 1 year is good
        recent = [
            e
            for e in history
            if (now - e.timestamp).days < 365
        ]
        if not recent:
            return 0.3  # No recent maintenance

        # Ratio of repairs to total events
        repairs = sum(
            1
            for e in recent
            if e.maintenance_type in (MaintenanceType.REPAIR, MaintenanceType.REPLACEMENT)
        )
        total = len(recent)
        if total == 0:
            return 0.5

        repair_ratio = repairs / total
        # Few repairs = well maintained
        base = 1.0 - (repair_ratio * 0.6)
        # Bonus for recent inspection
        has_recent_inspection = any(
            e.maintenance_type == MaintenanceType.INSPECTION
            and (now - e.timestamp).days < 90
            for e in recent
        )
        if has_recent_inspection:
            base = min(1.0, base + 0.15)
        return max(0.0, base)

    def _compute_event_factor(self, asset: AssetData) -> float:
        history = self._history_cache.get(asset.asset_id, [])
        if not history:
            return 1.0

        now = datetime.now(timezone.utc)
        # Look at last 2 years of events
        window = [
            e
            for e in history
            if (now - e.timestamp).days < 730
        ]
        if not window:
            return 1.0

        # Each repair event reduces factor
        repairs = sum(
            1
            for e in window
            if e.maintenance_type in (MaintenanceType.REPAIR, MaintenanceType.REPLACEMENT)
        )
        factor = 1.0 - (repairs * 0.15)
        return max(0.0, factor)

    def _compute_env_factor(self, asset: AssetData) -> float:
        return self.ENVIRONMENT_FACTORS.get(
            asset.environment_rating, 0.7
        )

    # ── Internal: Weibull fitting ────────────────────────────────────────

    def _fit_weibull(
        self, history: List[MaintenanceEvent]
    ) -> tuple[float, float]:
        """Fit Weibull parameters using method of moments on time-between-failures.

        Falls back to defaults if insufficient data points (< 3).
        """
        # Sort by timestamp and extract repair/replacement events
        repair_events = sorted(
            [
                e
                for e in history
                if e.maintenance_type
                in (MaintenanceType.REPAIR, MaintenanceType.REPLACEMENT)
            ],
            key=lambda e: e.timestamp,
        )

        if len(repair_events) < 3:
            return self.DEFAULT_WEIBULL.get(
                AssetType.DETECTOR_SMOKE, (1.8, 3650.0)
            )

        # Compute time-between-failures in days
        tbf: List[float] = []
        prev = repair_events[0].timestamp
        for event in repair_events[1:]:
            delta = (event.timestamp - prev).total_seconds() / 86400.0
            if delta > 0:
                tbf.append(delta)
            prev = event.timestamp

        if len(tbf) < 2:
            return self.DEFAULT_WEIBULL.get(
                AssetType.DETECTOR_SMOKE, (1.8, 3650.0)
            )

        # Method of moments
        mean_tbf = sum(tbf) / len(tbf)
        variance = sum((t - mean_tbf) ** 2 for t in tbf) / len(tbf)
        std_tbf = math.sqrt(variance)

        if mean_tbf <= 0 or std_tbf <= 0:
            return self.DEFAULT_WEIBULL.get(
                AssetType.DETECTOR_SMOKE, (1.8, 3650.0)
            )

        cv = std_tbf / mean_tbf
        shape_estimate = 1.2 / cv if cv > 0 else 2.0
        shape_estimate = max(0.5, min(5.0, shape_estimate))

        scale_estimate = mean_tbf / math.gamma(1.0 + 1.0 / shape_estimate)

        return (shape_estimate, scale_estimate)

    # ── Internal: Risk classification ────────────────────────────────────

    def _classify_risk(
        self, health_score: float, failure_prob: float
    ) -> RiskLevel:
        if health_score < 0.25 or failure_prob > 0.5:
            return RiskLevel.CRITICAL
        if health_score < 0.50 or failure_prob > 0.3:
            return RiskLevel.HIGH
        if health_score < 0.75 or failure_prob > 0.15:
            return RiskLevel.MEDIUM
        return RiskLevel.LOW

    def _estimate_ttf(
        self,
        health_score: float,
        prediction: FailurePrediction,
    ) -> Optional[float]:
        if health_score <= 0.05:
            return 0.0
        if health_score >= 0.95:
            return None
        # Exponential interpolation
        ttf = prediction.mttf_days * health_score
        if ttf > 36500:
            return None
        return round(ttf, 1)

    def _generate_recommendations(
        self,
        asset: AssetData,
        health_score: float,
        risk_level: RiskLevel,
    ) -> List[str]:
        recs: List[str] = []

        if risk_level == RiskLevel.CRITICAL:
            recs.append(
                f"URGENT: Replace {asset.asset_type.value} "
                f"{asset.asset_id} immediately"
            )
            recs.append(
                "Isolate asset from critical circuits until replacement"
            )
        elif risk_level == RiskLevel.HIGH:
            recs.append(
                f"Schedule replacement of {asset.asset_id} within 7 days"
            )
            recs.append("Perform detailed functional test before replacement")

        if health_score < 0.6:
            recs.append(
                f"Increase inspection frequency for {asset.asset_id}"
            )
        if (
            asset.asset_type
            in (AssetType.BATTERY, AssetType.DETECTOR_SMOKE)
            and health_score < 0.5
        ):
            recs.append("Consider proactive replacement strategy")
        if asset.environment_rating in ("corrosive", "coastal", "desert"):
            recs.append(
                "Apply corrosion protection per NFPA 72 §14.4.4"
            )

        if not recs:
            recs.append(
                f"No action required for {asset.asset_id} at this time"
            )
        return recs


# ===========================================================================
# Self-Test
# ===========================================================================

if __name__ == "__main__":
    pm = PredictiveMaintenance()

    asset = AssetData(
        asset_id="DET-001",
        asset_type=AssetType.DETECTOR_SMOKE,
        installation_date=datetime(2018, 6, 1, tzinfo=timezone.utc),
        manufacturer="SystemSensor",
        location="Building A - Floor 3",
        environment_rating="indoor",
        design_life_years=20.0,
    )

    history = [
        MaintenanceEvent(
            event_id="M-001",
            asset_id="DET-001",
            maintenance_type=MaintenanceType.INSPECTION,
            timestamp=datetime(2024, 1, 15, tzinfo=timezone.utc),
        ),
        MaintenanceEvent(
            event_id="M-002",
            asset_id="DET-001",
            maintenance_type=MaintenanceType.TEST,
            timestamp=datetime(2024, 6, 1, tzinfo=timezone.utc),
        ),
    ]

    pm._history_cache["DET-001"] = history

    health = pm.assess_health(asset)
    print(f"Health Score: {health.health_score}")
    print(f"Risk Level: {health.risk_level.value}")
    print(f"Failure Probability (90d): {health.failure_probability}")
    print(f"Estimated TTF (days): {health.estimated_ttf_days}")
    print(f"Recommendations: {health.recommendations}")

    prediction = pm.predict_failure(history, asset)
    print(f"\nWeibull shape={prediction.weibull_shape}, scale={prediction.weibull_scale}")
    print(f"MTTF={prediction.mttf_days:.0f} days")
    print(f"Reliability at 365d={prediction.reliability_at_365d:.2%}")

    rec = pm.recommend_maintenance(asset)
    print(f"\nRecommendation: {rec.recommended_action} ({rec.urgency})")
    print(f"  {rec.description}")
