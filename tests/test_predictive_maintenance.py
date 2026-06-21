"""
tests/test_predictive_maintenance.py
=====================================
Comprehensive test suite for fireai/analytics/predictive_maintenance.py

Covers the ML predictive maintenance module identified in
TestSprite_Full_Report.md as missing test coverage (TC011-TC013).

NFPA 72 References:
  §14.4     — Inspection, testing and maintenance
  §10.6.7   — Battery standby (referenced via BATTERY asset type)
  IEEE 762  — Reliability data for power equipment
  IEC 60300-3-11 — Reliability-centered maintenance

Scope:
  - AssetType / RiskLevel / MaintenanceType enums
  - AssetData / MaintenanceEvent / FailurePrediction dataclasses
  - AssetHealth invariants (0 ≤ score ≤ 1, 0 ≤ failure_prob ≤ 1)
  - PredictiveMaintenance.assess_health() across age/maintenance/env branches
  - PredictiveMaintenance.predict_failure() with Weibull & exponential fallback
  - PredictiveMaintenance.recommend_maintenance() across all 4 risk levels
  - _fit_weibull() method-of-moments on time-between-failures
  - _classify_risk() boundary conditions
  - Edge cases: unknown environment, no history, very old asset
"""

from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone

import pytest

from fireai.analytics.predictive_maintenance import (
    AssetData,
    AssetHealth,
    AssetType,
    FailurePrediction,
    MaintenanceEvent,
    MaintenanceRecommendation,
    MaintenanceType,
    PredictiveMaintenance,
    RiskLevel,
)


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────


@pytest.fixture
def pm() -> PredictiveMaintenance:
    """Fresh PredictiveMaintenance instance (empty history cache)."""
    return PredictiveMaintenance()


@pytest.fixture
def fresh_asset() -> AssetData:
    """Recently installed indoor smoke detector in good environment."""
    return AssetData(
        asset_id="DET-FRESH-001",
        asset_type=AssetType.DETECTOR_SMOKE,
        installation_date=datetime.now(timezone.utc) - timedelta(days=180),
        manufacturer="SystemSensor",
        model="i3",
        location="Bldg A / Fl 3",
        environment_rating="indoor",
        design_life_years=20.0,
    )


@pytest.fixture
def old_battery() -> AssetData:
    """Old battery in a corrosive environment — should be HIGH/CRITICAL risk."""
    return AssetData(
        asset_id="BAT-OLD-007",
        asset_type=AssetType.BATTERY,
        installation_date=datetime.now(timezone.utc) - timedelta(days=365 * 8),
        manufacturer="Yuasa",
        location="FACP Room",
        environment_rating="corrosive",
        design_life_years=5.0,
    )


def _make_event(
    asset_id: str,
    event_type: MaintenanceType,
    days_ago: float,
    event_id: str | None = None,
) -> MaintenanceEvent:
    """Helper — build a MaintenanceEvent N days in the past."""
    return MaintenanceEvent(
        event_id=event_id or f"{asset_id}-{days_ago}",
        asset_id=asset_id,
        maintenance_type=event_type,
        timestamp=datetime.now(timezone.utc) - timedelta(days=days_ago),
    )


# ─────────────────────────────────────────────────────────────────────────────
# Enum & Dataclass Tests
# ─────────────────────────────────────────────────────────────────────────────


class TestEnums:
    """Enum coverage for AssetType, RiskLevel, MaintenanceType."""

    def test_asset_type_values_are_strings(self):
        """str-Enum pattern — values are stable string identifiers."""
        assert AssetType.DETECTOR_SMOKE.value == "DETECTOR_SMOKE"
        assert AssetType.FACP.value == "FACP"
        assert AssetType.BATTERY.value == "BATTERY"
        assert AssetType.CABLE.value == "CABLE"

    def test_asset_type_count(self):
        """Module exposes 9 asset types — guards against accidental removal."""
        assert len(list(AssetType)) == 9

    def test_risk_level_ordering(self):
        """Risk levels cover the full life-safety classification range."""
        values = {r.value for r in RiskLevel}
        assert values == {"CRITICAL", "HIGH", "MEDIUM", "LOW"}

    def test_maintenance_type_count(self):
        assert len(list(MaintenanceType)) == 5


class TestDataclasses:
    """Frozen dataclass construction & invariants."""

    def test_asset_data_defaults(self, fresh_asset: AssetData):
        assert fresh_asset.manufacturer == "SystemSensor"
        assert fresh_asset.design_life_years == 20.0
        assert fresh_asset.metadata == {}

    def test_asset_data_is_frozen(self, fresh_asset: AssetData):
        """Frozen dataclass must reject attribute mutation."""
        with pytest.raises((AttributeError, Exception)):
            fresh_asset.asset_id = "MUTATED"  # type: ignore[misc]

    def test_asset_health_rejects_out_of_range_score(self):
        """health_score MUST be in [0, 1] — out-of-range is a programming error."""
        with pytest.raises(ValueError):
            AssetHealth(
                asset_id="X",
                health_score=1.5,
                failure_probability=0.1,
                estimated_ttf_days=10,
                risk_level=RiskLevel.LOW,
                recommendations=[],
            )

    def test_asset_health_rejects_out_of_range_failure_prob(self):
        with pytest.raises(ValueError):
            AssetHealth(
                asset_id="X",
                health_score=0.5,
                failure_probability=-0.01,
                estimated_ttf_days=10,
                risk_level=RiskLevel.LOW,
                recommendations=[],
            )

    def test_asset_health_accepts_none_ttf(self):
        """None TTF is valid — represents 'no measurable degradation'."""
        h = AssetHealth(
            asset_id="X",
            health_score=0.99,
            failure_probability=0.001,
            estimated_ttf_days=None,
            risk_level=RiskLevel.LOW,
            recommendations=[],
        )
        assert h.estimated_ttf_days is None


# ─────────────────────────────────────────────────────────────────────────────
# assess_health()
# ─────────────────────────────────────────────────────────────────────────────


class TestAssessHealth:
    """PredictiveMaintenance.assess_health() — composite health scoring."""

    def test_fresh_indoor_asset_is_low_risk(self, pm: PredictiveMaintenance, fresh_asset: AssetData):
        """Recently installed, indoor, no events → score ≥ 0.75, LOW risk."""
        h = pm.assess_health(fresh_asset)
        assert 0.75 <= h.health_score <= 1.0
        assert h.risk_level == RiskLevel.LOW
        assert 0.0 <= h.failure_probability <= 1.0
        assert h.asset_id == "DET-FRESH-001"

    def test_old_corrosive_battery_is_high_or_critical(
        self, pm: PredictiveMaintenance, old_battery: AssetData
    ):
        """8-year-old battery in corrosive env, 5-year design life → HIGH/CRITICAL."""
        h = pm.assess_health(old_battery)
        assert h.risk_level in (RiskLevel.HIGH, RiskLevel.CRITICAL)
        assert h.health_score < 0.50

    def test_health_score_always_in_unit_interval(
        self, pm: PredictiveMaintenance, fresh_asset: AssetData, old_battery: AssetData
    ):
        """Invariant: 0 ≤ health_score ≤ 1 for any asset."""
        for asset in (fresh_asset, old_battery):
            h = pm.assess_health(asset)
            assert 0.0 <= h.health_score <= 1.0

    def test_failure_probability_always_in_unit_interval(
        self, pm: PredictiveMaintenance, fresh_asset: AssetData, old_battery: AssetData
    ):
        for asset in (fresh_asset, old_battery):
            h = pm.assess_health(asset)
            assert 0.0 <= h.failure_probability <= 1.0

    def test_recommendations_never_empty(self, pm: PredictiveMaintenance, fresh_asset: AssetData):
        """_generate_recommendations always returns at least one message."""
        h = pm.assess_health(fresh_asset)
        assert len(h.recommendations) >= 1
        assert all(isinstance(r, str) and r for r in h.recommendations)

    def test_unknown_environment_uses_default_factor(self, pm: PredictiveMaintenance):
        """Unknown env rating must fall back to 0.7 (not KeyError, not 1.0)."""
        asset = AssetData(
            asset_id="UNK-ENV",
            asset_type=AssetType.DETECTOR_SMOKE,
            installation_date=datetime.now(timezone.utc) - timedelta(days=180),
            environment_rating="UNKNOWN_ENV",
            design_life_years=20.0,
        )
        h = pm.assess_health(asset)
        # With unknown env (0.7) and fresh age (1.0) and no maintenance (0.5)
        # and no events (1.0): score = 1.0*0.3 + 0.5*0.3 + 1.0*0.2 + 0.7*0.2 = 0.79
        assert h.health_score == pytest.approx(0.79, abs=0.01)

    def test_with_recent_inspection_history_boosts_score(
        self, pm: PredictiveMaintenance, fresh_asset: AssetData
    ):
        """A recent inspection (<90d) should improve the maintenance factor."""
        # Without history: maintenance_factor = 0.5
        h_no_hist = pm.assess_health(fresh_asset)

        # With recent inspection
        pm._history_cache[fresh_asset.asset_id] = [
            _make_event(fresh_asset.asset_id, MaintenanceType.INSPECTION, 30),
            _make_event(fresh_asset.asset_id, MaintenanceType.TEST, 60),
        ]
        h_with_hist = pm.assess_health(fresh_asset)

        # Score should be at least as high with good maintenance history
        assert h_with_hist.health_score >= h_no_hist.health_score


# ─────────────────────────────────────────────────────────────────────────────
# predict_failure()
# ─────────────────────────────────────────────────────────────────────────────


class TestPredictFailure:
    """Weibull & exponential failure prediction."""

    def test_default_smoke_detector_prediction(self, pm: PredictiveMaintenance, fresh_asset: AssetData):
        """With no history, defaults to (shape=1.8, scale=3650d) for smoke detectors."""
        pred = pm.predict_failure([], fresh_asset)
        assert pred.asset_id == "DET-FRESH-001"
        assert pred.weibull_shape == pytest.approx(1.8, abs=1e-6)
        assert pred.weibull_scale == pytest.approx(3650.0, abs=1e-6)
        assert pred.model_type == "weibull"
        # 365-day reliability for shape=1.8, scale=3650 should be very high
        assert pred.reliability_at_365d > 0.95
        # 90-day failure probability should be small
        assert 0 < pred.failure_probability_90d < 0.05

    def test_mttf_matches_weibull_formula(self, pm: PredictiveMaintenance, fresh_asset: AssetData):
        """MTTF = scale × Γ(1 + 1/shape)."""
        pred = pm.predict_failure([], fresh_asset)
        expected_mttf = 3650.0 * math.gamma(1.0 + 1.0 / 1.8)
        assert pred.mttf_days == pytest.approx(expected_mttf, rel=1e-3)

    def test_reliability_formula(self, pm: PredictiveMaintenance, fresh_asset: AssetData):
        """R(365) = exp(-(365/scale)^shape)."""
        pred = pm.predict_failure([], fresh_asset)
        expected = math.exp(-((365.0 / 3650.0) ** 1.8))
        assert pred.reliability_at_365d == pytest.approx(expected, rel=1e-3)

    def test_failure_probability_formula(self, pm: PredictiveMaintenance, fresh_asset: AssetData):
        """F(90) = 1 - exp(-(90/scale)^shape). Source rounds to 4 decimals."""
        pred = pm.predict_failure([], fresh_asset)
        expected = round(1.0 - math.exp(-((90.0 / 3650.0) ** 1.8)), 4)
        assert pred.failure_probability_90d == pytest.approx(expected, abs=1e-4)

    def test_no_asset_no_history_returns_unknown_id(self, pm: PredictiveMaintenance):
        """Edge case — fallback asset_id is 'unknown'."""
        pred = pm.predict_failure([])
        assert pred.asset_id == "unknown"
        assert pred.model_type in ("weibull", "exponential")

    def test_battery_has_shorter_scale_than_facp(self, pm: PredictiveMaintenance):
        """Battery design life (~4yr) is much shorter than FACP (~20yr)."""
        battery = AssetData(
            asset_id="BAT-1",
            asset_type=AssetType.BATTERY,
            installation_date=datetime.now(timezone.utc),
        )
        facp = AssetData(
            asset_id="FACP-1",
            asset_type=AssetType.FACP,
            installation_date=datetime.now(timezone.utc),
        )
        bat_pred = pm.predict_failure([], battery)
        facp_pred = pm.predict_failure([], facp)
        # Battery scale (1460d) << FACP scale (7300d) — battery fails sooner
        assert bat_pred.weibull_scale < facp_pred.weibull_scale
        # And battery has higher 90d failure probability
        assert bat_pred.failure_probability_90d > facp_pred.failure_probability_90d

    def test_exponential_fallback_for_degenerate_shape(self, pm: PredictiveMaintenance):
        """If shape ≤ 0.1, exponential model is used."""
        # Patch the DEFAULT_WEIBULL to force a degenerate shape
        original = PredictiveMaintenance.DEFAULT_WEIBULL[AssetType.DETECTOR_SMOKE]
        try:
            PredictiveMaintenance.DEFAULT_WEIBULL[AssetType.DETECTOR_SMOKE] = (0.05, 1000.0)
            asset = AssetData(
                asset_id="DEGEN",
                asset_type=AssetType.DETECTOR_SMOKE,
                installation_date=datetime.now(timezone.utc),
            )
            pred = pm.predict_failure([], asset)
            assert pred.model_type == "exponential"
            assert pred.mttf_days == pytest.approx(1000.0)
            # Exponential: F(90) = 1 - exp(-90/scale) = 1 - exp(-0.09)
            expected = 1.0 - math.exp(-90.0 / 1000.0)
            assert pred.failure_probability_90d == pytest.approx(expected, rel=1e-3)
        finally:
            PredictiveMaintenance.DEFAULT_WEIBULL[AssetType.DETECTOR_SMOKE] = original


# ─────────────────────────────────────────────────────────────────────────────
# recommend_maintenance()
# ─────────────────────────────────────────────────────────────────────────────


class TestRecommendMaintenance:
    """recommend_maintenance() — risk-tiered action and urgency mapping."""

    def test_low_risk_returns_routine(self, pm: PredictiveMaintenance, fresh_asset: AssetData):
        rec = pm.recommend_maintenance(fresh_asset)
        assert rec.risk_level == RiskLevel.LOW
        assert rec.recommended_action == "ROUTINE_MAINTENANCE"
        assert rec.urgency == "SCHEDULED"
        assert "NFPA 72 §14.4" in rec.description

    def test_critical_risk_returns_immediate_replace(
        self, pm: PredictiveMaintenance, old_battery: AssetData
    ):
        """Old battery in corrosive env should be HIGH or CRITICAL."""
        rec = pm.recommend_maintenance(old_battery)
        assert rec.risk_level in (RiskLevel.HIGH, RiskLevel.CRITICAL)
        if rec.risk_level == RiskLevel.CRITICAL:
            assert rec.recommended_action == "REPLACE"
            assert rec.urgency == "IMMEDIATE"
        else:
            assert rec.recommended_action == "REPAIR_OR_REPLACE"
            assert rec.urgency == "WITHIN_7_DAYS"

    def test_urgency_ordering_matches_risk(self, pm: PredictiveMaintenance):
        """CRITICAL > HIGH > MEDIUM > LOW urgency."""
        urgency_rank = {
            "IMMEDIATE": 0,
            "WITHIN_7_DAYS": 1,
            "WITHIN_30_DAYS": 2,
            "SCHEDULED": 3,
        }
        # Build assets of each risk tier via different age/env combinations
        # CRITICAL: ancient battery in corrosive env
        ancient = AssetData(
            asset_id="ANCIENT",
            asset_type=AssetType.BATTERY,
            installation_date=datetime(1990, 1, 1, tzinfo=timezone.utc),
            environment_rating="corrosive",
            design_life_years=5.0,
        )
        rec_ancient = pm.recommend_maintenance(ancient)
        # MEDIUM: 12-year-old detector, indoor
        medium = AssetData(
            asset_id="MED",
            asset_type=AssetType.DETECTOR_SMOKE,
            installation_date=datetime.now(timezone.utc) - timedelta(days=365 * 12),
            environment_rating="indoor",
            design_life_years=20.0,
        )
        rec_medium = pm.recommend_maintenance(medium)
        # LOW: fresh detector
        fresh = AssetData(
            asset_id="LOW",
            asset_type=AssetType.DETECTOR_SMOKE,
            installation_date=datetime.now(timezone.utc) - timedelta(days=90),
            environment_rating="indoor",
            design_life_years=20.0,
        )
        rec_low = pm.recommend_maintenance(fresh)

        # Sanity: the rank must be monotonic with risk
        assert urgency_rank[rec_ancient.urgency] <= urgency_rank[rec_medium.urgency]
        assert urgency_rank[rec_medium.urgency] <= urgency_rank[rec_low.urgency]

    def test_recommendation_returns_correct_asset_id(
        self, pm: PredictiveMaintenance, fresh_asset: AssetData
    ):
        rec = pm.recommend_maintenance(fresh_asset)
        assert rec.asset_id == fresh_asset.asset_id


# ─────────────────────────────────────────────────────────────────────────────
# _fit_weibull() — Method of Moments
# ─────────────────────────────────────────────────────────────────────────────


class TestFitWeibull:
    """Weibull parameter fitting from maintenance history."""

    def test_insufficient_events_falls_back_to_defaults(self, pm: PredictiveMaintenance):
        """<3 repair events → return defaults."""
        history = [
            _make_event("A", MaintenanceType.REPAIR, 100),
            _make_event("A", MaintenanceType.REPAIR, 50),
        ]
        shape, scale = pm._fit_weibull(history)
        # Defaults for DETECTOR_SMOKE
        assert shape == pytest.approx(1.8, abs=1e-6)
        assert scale == pytest.approx(3650.0, abs=1e-6)

    def test_no_repair_events_falls_back_to_defaults(self, pm: PredictiveMaintenance):
        """Only inspections/tests — no repair data → defaults."""
        history = [
            _make_event("A", MaintenanceType.INSPECTION, 365),
            _make_event("A", MaintenanceType.INSPECTION, 180),
            _make_event("A", MaintenanceType.INSPECTION, 90),
        ]
        shape, scale = pm._fit_weibull(history)
        assert shape == pytest.approx(1.8, abs=1e-6)
        assert scale == pytest.approx(3650.0, abs=1e-6)

    def test_uniform_tbf_falls_back_to_defaults(self, pm: PredictiveMaintenance):
        """Zero-variance TBF (perfectly regular intervals) → std=0 → defaults.

        The source guard `if mean_tbf <= 0 or std_tbf <= 0: return defaults`
        fires for zero-variance input. We use FIXED timestamps (not
        datetime.now()) so the deltas are exactly identical — calling
        datetime.now() 5 times in a row introduces microsecond jitter that
        would make std_tbf a tiny non-zero float and bypass the guard.
        """
        base = datetime(2024, 1, 1, tzinfo=timezone.utc)
        history = [
            MaintenanceEvent(
                event_id=f"E{i}",
                asset_id="A",
                maintenance_type=MaintenanceType.REPAIR,
                timestamp=base + timedelta(days=i * 100),  # 0, 100, 200, 300, 400
            )
            for i in range(5)
        ]
        shape, scale = pm._fit_weibull(history)
        # All TBFs are exactly 100.0 days → variance = 0 → std_tbf = 0 → guard fires
        assert shape == pytest.approx(1.8, abs=1e-6)
        assert scale == pytest.approx(3650.0, abs=1e-6)

    def test_irregular_tbf_produces_finite_shape(self, pm: PredictiveMaintenance):
        """Varying TBF produces a non-default shape within [0.5, 5.0]."""
        # 5 repair events with varying intervals: 100, 200, 50, 300, 150 days
        history = [
            MaintenanceEvent(
                event_id=f"E{i}",
                asset_id="A",
                maintenance_type=MaintenanceType.REPAIR,
                timestamp=datetime.now(timezone.utc) - timedelta(days=days),
            )
            for i, days in enumerate([800, 700, 500, 450, 150])
        ]
        shape, scale = pm._fit_weibull(history)
        assert 0.5 <= shape <= 5.0
        assert scale > 0
        assert shape != pytest.approx(1.8, abs=1e-6)  # not default


# ─────────────────────────────────────────────────────────────────────────────
# _classify_risk() — Boundary Conditions
# ─────────────────────────────────────────────────────────────────────────────


class TestClassifyRisk:
    """Risk classification — boundary conditions at each tier transition."""

    @pytest.mark.parametrize(
        "score,prob,expected",
        [
            # CRITICAL — very low score OR very high prob
            (0.10, 0.05, RiskLevel.CRITICAL),  # score < 0.25
            (0.24, 0.05, RiskLevel.CRITICAL),  # score == 0.24 still critical
            (0.50, 0.55, RiskLevel.CRITICAL),  # prob > 0.5
            # HIGH — score < 0.50 OR prob > 0.30
            (0.49, 0.10, RiskLevel.HIGH),
            (0.50, 0.31, RiskLevel.HIGH),
            # MEDIUM — score < 0.75 OR prob > 0.15
            (0.74, 0.05, RiskLevel.MEDIUM),
            (0.80, 0.16, RiskLevel.MEDIUM),
            # LOW — healthy
            (0.80, 0.05, RiskLevel.LOW),
            (1.00, 0.00, RiskLevel.LOW),
        ],
    )
    def test_risk_boundaries(self, pm: PredictiveMaintenance, score, prob, expected):
        assert pm._classify_risk(score, prob) == expected

    def test_score_zero_probability_zero_is_critical(self, pm: PredictiveMaintenance):
        """Zero health score is always CRITICAL regardless of probability."""
        assert pm._classify_risk(0.0, 0.0) == RiskLevel.CRITICAL

    def test_perfect_health_low_prob_is_low(self, pm: PredictiveMaintenance):
        assert pm._classify_risk(1.0, 0.01) == RiskLevel.LOW


# ─────────────────────────────────────────────────────────────────────────────
# _compute_age_factor() — Design Life Tiers
# ─────────────────────────────────────────────────────────────────────────────


class TestAgeFactor:
    """Age factor — ratio of age to design life."""

    @pytest.mark.parametrize(
        "ratio,expected",
        [
            (0.10, 1.0),   # <25% — fresh
            (0.30, 0.85),  # 25-50%
            (0.60, 0.65),  # 50-75%
            (0.85, 0.40),  # 75-100%
            (1.20, 0.15),  # 100-150% — end of life
            (1.60, 0.0),   # >=150% — far beyond
            (2.00, 0.0),   # well beyond
        ],
    )
    def test_age_factor_tiers(self, pm: PredictiveMaintenance, ratio, expected):
        """Verify each age tier returns its expected factor.

        We pick ratio values that fall SAFELY INSIDE each tier (not on the
        boundary) because the source uses `(now - installation_date).days`
        which floors to integer days. A ratio of exactly 0.25 may floor to
        0.2499 and fall into the lower tier. Using ratio=0.30 (clearly
        inside the 0.25-0.50 tier) avoids this off-by-one.
        """
        design_years = 10.0
        age_days = ratio * design_years * 365.25
        # Add +1 day buffer so integer-day floor doesn't push us below threshold
        asset = AssetData(
            asset_id="AGE",
            asset_type=AssetType.DETECTOR_SMOKE,
            installation_date=datetime.now(timezone.utc) - timedelta(days=age_days + 1),
            design_life_years=design_years,
        )
        assert pm._compute_age_factor(asset) == pytest.approx(expected, abs=1e-6)

    def test_zero_design_life_returns_one(self, pm: PredictiveMaintenance):
        """Edge case — design_life_years=0 must not divide by zero."""
        asset = AssetData(
            asset_id="ZERO",
            asset_type=AssetType.DETECTOR_SMOKE,
            installation_date=datetime.now(timezone.utc) - timedelta(days=365),
            design_life_years=0.0,
        )
        assert pm._compute_age_factor(asset) == 1.0


# ─────────────────────────────────────────────────────────────────────────────
# _compute_env_factor() — Environment Lookup
# ─────────────────────────────────────────────────────────────────────────────


class TestEnvFactor:
    @pytest.mark.parametrize(
        "env,expected",
        [
            ("indoor", 1.0),
            ("cleanroom", 0.95),
            ("outdoor", 0.75),
            ("coastal", 0.60),
            ("desert", 0.50),
            ("hazardous", 0.55),
            ("corrosive", 0.40),
        ],
    )
    def test_known_environments(self, pm: PredictiveMaintenance, env, expected):
        asset = AssetData(
            asset_id=f"ENV-{env}",
            asset_type=AssetType.DETECTOR_SMOKE,
            installation_date=datetime.now(timezone.utc),
            environment_rating=env,
        )
        assert pm._compute_env_factor(asset) == pytest.approx(expected, abs=1e-6)

    def test_unknown_environment_uses_default(self, pm: PredictiveMaintenance):
        asset = AssetData(
            asset_id="UNK",
            asset_type=AssetType.DETECTOR_SMOKE,
            installation_date=datetime.now(timezone.utc),
            environment_rating="moonbase",
        )
        assert pm._compute_env_factor(asset) == pytest.approx(0.7, abs=1e-6)

    def test_corrosive_is_harshest_known_env(self, pm: PredictiveMaintenance):
        """Corrosive env (0.40) is the lowest (harshest) factor in the table."""
        asset = AssetData(
            asset_id="COR",
            asset_type=AssetType.DETECTOR_SMOKE,
            installation_date=datetime.now(timezone.utc),
            environment_rating="corrosive",
        )
        all_known = PredictiveMaintenance.ENVIRONMENT_FACTORS.values()
        assert pm._compute_env_factor(asset) == min(all_known)


# ─────────────────────────────────────────────────────────────────────────────
# Module Self-Test (the `if __name__ == "__main__"` block)
# ─────────────────────────────────────────────────────────────────────────────


class TestModuleSelfTest:
    """Verify the module's built-in self-test still works."""

    def test_self_test_runs_without_error(self):
        """The module's `if __name__ == "__main__"` block must not raise.

        We re-exec it as a subprocess to avoid polluting this process.
        """
        import subprocess
        import sys

        result = subprocess.run(
            [sys.executable, "-m", "fireai.analytics.predictive_maintenance"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert result.returncode == 0, (
            f"Self-test failed with code {result.returncode}.\n"
            f"STDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
        )
        # Self-test prints these key fields
        assert "Health Score:" in result.stdout
        assert "Risk Level:" in result.stdout
        assert "Recommendation:" in result.stdout
