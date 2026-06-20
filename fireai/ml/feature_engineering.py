"""fireai/ml/feature_engineering.py — Feature Engineering for ML Models.
=====================================================================

Converts raw asset data + maintenance history into the AssetFeatures
schema expected by ML models.

This module handles:
    - Computing age, age_ratio
    - Counting failures in time windows
    - Building weekly event sequences for LSTM
    - Computing mean time between failures
    - Looking up environment factors
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from fireai.ml.schemas import (
    AssetFeatures,
    AssetType,
    MaintenanceEventInput,
)

logger = logging.getLogger(__name__)


# Environment factor lookup (matches fireai/analytics/predictive_maintenance.py)
ENVIRONMENT_FACTORS = {
    "indoor": 1.0,
    "outdoor": 0.75,
    "hazardous": 0.55,
    "cleanroom": 0.95,
    "corrosive": 0.40,
    "coastal": 0.60,
    "desert": 0.50,
}

FAILURE_TYPES = {"FAILURE", "REPAIR", "REPLACEMENT"}
INSPECTION_TYPES = {"INSPECTION"}
MAINTENANCE_TYPES = {"INSPECTION", "TEST", "REPAIR", "REPLACEMENT", "CALIBRATION"}


class FeatureEngineer:
    """Build AssetFeatures from raw asset data + maintenance history."""

    @staticmethod
    def build_features(
        asset_id: str,
        asset_type: AssetType,
        installation_date: datetime,
        maintenance_history: list[MaintenanceEventInput],
        manufacturer: str = "",
        model: str = "",
        location: str = "",
        environment_rating: str = "indoor",
        design_life_years: float = 20.0,
    ) -> AssetFeatures:
        """Build complete AssetFeatures from raw inputs."""
        now = datetime.now(timezone.utc)

        # ── Age features ───────────────────────────────────────────
        age_days = max(0.0, (now - installation_date).total_seconds() / 86400.0)
        design_days = design_life_years * 365.25
        age_ratio = min(2.0, age_days / max(design_days, 1.0))

        # ── Failure counts ─────────────────────────────────────────
        recent_failures_90d = FeatureEngineer._count_failures(
            maintenance_history, now, days=90
        )
        recent_failures_365d = FeatureEngineer._count_failures(
            maintenance_history, now, days=365
        )
        total_failures = FeatureEngineer._count_failures(
            maintenance_history, now, days=None
        )

        # ── Maintenance counts ─────────────────────────────────────
        maintenance_count_365d = FeatureEngineer._count_by_type(
            maintenance_history, now, days=365, types=MAINTENANCE_TYPES
        )
        inspection_count_90d = FeatureEngineer._count_by_type(
            maintenance_history, now, days=90, types=INSPECTION_TYPES
        )

        # ── Repair ratio ───────────────────────────────────────────
        total_recent = FeatureEngineer._count_by_type(
            maintenance_history, now, days=365, types=MAINTENANCE_TYPES
        )
        repair_ratio_365d = (
            recent_failures_365d / total_recent if total_recent > 0 else 0.0
        )
        repair_ratio_365d = min(1.0, repair_ratio_365d)

        # ── MTBF (mean time between failures) ──────────────────────
        mtbf = FeatureEngineer._compute_mtbf(maintenance_history)

        # ── Environment ────────────────────────────────────────────
        env_factor = ENVIRONMENT_FACTORS.get(environment_rating, 0.7)

        # ── Weekly event sequence (for LSTM, last 52 weeks) ────────
        recent_event_counts = FeatureEngineer._build_weekly_sequence(
            maintenance_history, now, weeks=52
        )

        return AssetFeatures(
            asset_id=asset_id,
            asset_type=asset_type,
            installation_date=installation_date,
            manufacturer=manufacturer,
            model=model,
            location=location,
            environment_rating=environment_rating,
            design_life_years=design_life_years,
            age_days=round(age_days, 2),
            age_ratio=round(age_ratio, 4),
            recent_failures_90d=recent_failures_90d,
            recent_failures_365d=recent_failures_365d,
            total_failures=total_failures,
            maintenance_count_365d=maintenance_count_365d,
            inspection_count_90d=inspection_count_90d,
            repair_ratio_365d=round(repair_ratio_365d, 4),
            mean_time_between_failures_days=round(mtbf, 2) if mtbf else None,
            environment_factor=env_factor,
            is_battery=(asset_type == AssetType.BATTERY),
            is_outdoor=(environment_rating in ("outdoor", "coastal", "desert")),
            recent_event_counts=recent_event_counts,
            maintenance_history=maintenance_history,
        )

    @staticmethod
    def _count_failures(
        history: list[MaintenanceEventInput],
        now: datetime,
        days: int | None,
    ) -> int:
        """Count failure-type events within time window."""
        cutoff = now - timedelta(days=days) if days else datetime.min.replace(tzinfo=timezone.utc)
        return sum(
            1
            for e in history
            if e.maintenance_type.upper() in FAILURE_TYPES
            and e.timestamp >= cutoff
        )

    @staticmethod
    def _count_by_type(
        history: list[MaintenanceEventInput],
        now: datetime,
        days: int,
        types: set,
    ) -> int:
        cutoff = now - timedelta(days=days)
        return sum(
            1
            for e in history
            if e.maintenance_type.upper() in types and e.timestamp >= cutoff
        )

    @staticmethod
    def _compute_mtbf(
        history: list[MaintenanceEventInput],
    ) -> float | None:
        """Compute mean time between failures in days."""
        failures = sorted(
            [e for e in history if e.maintenance_type.upper() in FAILURE_TYPES],
            key=lambda e: e.timestamp,
        )
        if len(failures) < 2:
            return None
        deltas = []
        for i in range(1, len(failures)):
            delta = (failures[i].timestamp - failures[i - 1].timestamp).total_seconds() / 86400.0
            if delta > 0:
                deltas.append(delta)
        if not deltas:
            return None
        return sum(deltas) / len(deltas)

    @staticmethod
    def _build_weekly_sequence(
        history: list[MaintenanceEventInput],
        now: datetime,
        weeks: int,
    ) -> list[int]:
        """Build weekly event count sequence (oldest → newest)."""
        # Initialize all weeks to 0
        sequence = [0] * weeks

        # Bucket each event into its week index
        for event in history:
            days_ago = (now - event.timestamp).days
            if days_ago < 0:
                continue  # future event, skip
            week_idx = weeks - 1 - (days_ago // 7)
            if 0 <= week_idx < weeks:
                sequence[week_idx] += 1

        return sequence
