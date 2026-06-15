"""
tests/test_hybrid_survivability.py
==================================
Comprehensive test suite for fireai/core/hybrid_survivability.py.

SAFETY CRITICAL: Hybrid survivability analysis intersects optical (Layer 5)
and acoustic (V23) coverage to classify each grid point. Misclassification
could leave blind spots undetected — a direct life-safety hazard.

NFPA 72 References:
  §17.8.3.4 — Detector redundancy for critical areas
  ISA-TR 84.00.07 — UGLD coverage
  IEC 60079-29-4 — Gas detection fundamentals

Key V-Fixes tested:
  V60 FIX (P3-1/P3-2/P3-3) — Rounding fixes for coverage percentages
"""

from __future__ import annotations

import json
import os
from unittest.mock import MagicMock, patch

import pytest

from fireai.core.hybrid_survivability import (
    AcousticCoverageDetail,
    HybridPointResult,
    HybridSurvivabilityEngine,
    HybridSurvivabilityMap,
    SurvivabilityClass,
)

# ─────────────────────────────────────────────────────────────────────────────
# SurvivabilityClass Tests
# ─────────────────────────────────────────────────────────────────────────────


class TestSurvivabilityClass:
    """4-state survivability classification per NFPA 72 / ISA-TR 84.00.07."""

    def test_four_states_exist(self):
        assert SurvivabilityClass.REDUNDANT_HYBRID.value == "REDUNDANT_HYBRID"
        assert SurvivabilityClass.OPTICAL_ONLY.value == "OPTICAL_ONLY"
        assert SurvivabilityClass.ACOUSTIC_ONLY.value == "ACOUSTIC_ONLY"
        assert SurvivabilityClass.BLIND_SPOT.value == "BLIND_SPOT"

    def test_is_covered(self):
        """True if at least one modality covers this point."""
        assert SurvivabilityClass.REDUNDANT_HYBRID.is_covered is True
        assert SurvivabilityClass.OPTICAL_ONLY.is_covered is True
        assert SurvivabilityClass.ACOUSTIC_ONLY.is_covered is True
        assert SurvivabilityClass.BLIND_SPOT.is_covered is False

    def test_is_redundant(self):
        """True only if BOTH modalities cover this point."""
        assert SurvivabilityClass.REDUNDANT_HYBRID.is_redundant is True
        assert SurvivabilityClass.OPTICAL_ONLY.is_redundant is False
        assert SurvivabilityClass.ACOUSTIC_ONLY.is_redundant is False
        assert SurvivabilityClass.BLIND_SPOT.is_redundant is False

    def test_severity_rank_ordering(self):
        """Lower rank = safer. Used for heatmap color mapping."""
        assert SurvivabilityClass.REDUNDANT_HYBRID.severity_rank == 0
        assert SurvivabilityClass.OPTICAL_ONLY.severity_rank == 1
        assert SurvivabilityClass.ACOUSTIC_ONLY.severity_rank == 2
        assert SurvivabilityClass.BLIND_SPOT.severity_rank == 3

    def test_severity_rank_monotonic(self):
        ranks = [cls.severity_rank for cls in SurvivabilityClass]
        assert ranks == sorted(ranks)

    def test_enum_string_inheritance(self):
        """SurvivabilityClass inherits from str for JSON serialization."""
        assert isinstance(SurvivabilityClass.REDUNDANT_HYBRID, str)
        assert SurvivabilityClass.REDUNDANT_HYBRID == "REDUNDANT_HYBRID"


# ─────────────────────────────────────────────────────────────────────────────
# AcousticCoverageDetail Tests
# ─────────────────────────────────────────────────────────────────────────────


class TestAcousticCoverageDetail:
    def test_create_valid(self):
        detail = AcousticCoverageDetail(
            sensor_id="UGLD-1",
            triggered=True,
            snr_db=25.0,
            margin_to_threshold_db=5.0,
            has_los=True,
            total_insertion_loss_db=0.0,
            distance_meters=15.0,
        )
        assert detail.sensor_id == "UGLD-1"
        assert detail.triggered is True
        assert detail.snr_db == 25.0
        assert detail.distance_meters == 15.0

    def test_frozen(self):
        detail = AcousticCoverageDetail(
            sensor_id="UGLD-1",
            triggered=True,
            snr_db=25.0,
            margin_to_threshold_db=5.0,
            has_los=True,
            distance_meters=15.0,
        )
        with pytest.raises(Exception):
            detail.sensor_id = "UGLD-2"

    def test_negative_snr(self):
        """SNR can be negative (below threshold)."""
        detail = AcousticCoverageDetail(
            sensor_id="UGLD-1",
            triggered=False,
            snr_db=-5.0,
            margin_to_threshold_db=-15.0,
            has_los=False,
            distance_meters=50.0,
        )
        assert detail.snr_db == -5.0
        assert detail.triggered is False

    def test_default_insertion_loss(self):
        detail = AcousticCoverageDetail(
            sensor_id="UGLD-1",
            triggered=True,
            snr_db=25.0,
            margin_to_threshold_db=5.0,
            has_los=True,
            distance_meters=15.0,
        )
        assert detail.total_insertion_loss_db == 0.0


# ─────────────────────────────────────────────────────────────────────────────
# HybridPointResult Tests
# ─────────────────────────────────────────────────────────────────────────────


class TestHybridPointResult:
    def test_create_valid(self):
        pr = HybridPointResult(
            point_index=0,
            x=1.0,
            y=2.0,
            z=3.0,
            survivability_class=SurvivabilityClass.REDUNDANT_HYBRID,
            optical_detector_count=2,
        )
        assert pr.point_index == 0
        assert pr.survivability_class == SurvivabilityClass.REDUNDANT_HYBRID

    def test_frozen(self):
        pr = HybridPointResult(
            point_index=0,
            x=1.0,
            y=2.0,
            z=3.0,
            survivability_class=SurvivabilityClass.OPTICAL_ONLY,
        )
        with pytest.raises(Exception):
            pr.x = 99.0

    def test_default_optical_count(self):
        pr = HybridPointResult(
            point_index=0,
            x=1.0,
            y=2.0,
            z=3.0,
            survivability_class=SurvivabilityClass.BLIND_SPOT,
        )
        assert pr.optical_detector_count == 0

    def test_default_acoustic_detail(self):
        pr = HybridPointResult(
            point_index=0,
            x=1.0,
            y=2.0,
            z=3.0,
            survivability_class=SurvivabilityClass.BLIND_SPOT,
        )
        assert pr.best_acoustic_detail is None

    def test_with_acoustic_detail(self):
        detail = AcousticCoverageDetail(
            sensor_id="UGLD-1",
            triggered=True,
            snr_db=25.0,
            margin_to_threshold_db=5.0,
            has_los=True,
            distance_meters=15.0,
        )
        pr = HybridPointResult(
            point_index=0,
            x=1.0,
            y=2.0,
            z=3.0,
            survivability_class=SurvivabilityClass.REDUNDANT_HYBRID,
            optical_detector_count=1,
            best_acoustic_detail=detail,
        )
        assert pr.best_acoustic_detail is not None
        assert pr.best_acoustic_detail.snr_db == 25.0


# ─────────────────────────────────────────────────────────────────────────────
# HybridSurvivabilityMap Tests
# ─────────────────────────────────────────────────────────────────────────────


class TestHybridSurvivabilityMap:
    def test_create_default(self):
        m = HybridSurvivabilityMap(total_points=100)
        assert m.total_points == 100
        assert m.redundant_hybrid_count == 0
        assert m.optical_only_count == 0
        assert m.acoustic_only_count == 0
        assert m.blind_spot_count == 0

    def test_redundant_hybrid_pct_full_coverage(self):
        """V60 FIX: 100% coverage returns exactly 100.00."""
        m = HybridSurvivabilityMap(
            total_points=100,
            redundant_hybrid_count=100,
            hybrid_coverage_fraction=1.0,
        )
        assert m.redundant_hybrid_pct == 100.00

    def test_redundant_hybrid_pct_partial(self):
        """V60 FIX: Partial coverage — no rounding to 100%."""
        m = HybridSurvivabilityMap(
            total_points=100,
            redundant_hybrid_count=99,
            hybrid_coverage_fraction=0.99,
        )
        assert m.redundant_hybrid_pct < 100.0

    def test_redundant_hybrid_pct_near_full(self):
        """V60 FIX (P3-1): 99.999% coverage must NOT round to 100.00."""
        m = HybridSurvivabilityMap(
            total_points=100000,
            redundant_hybrid_count=99999,
            hybrid_coverage_fraction=0.99999,
        )
        pct = m.redundant_hybrid_pct
        # Should NOT be 100.00
        assert pct < 100.0 or m.redundant_hybrid_count == m.total_points

    def test_any_coverage_pct_full(self):
        """V60 FIX (P3-2): No blind spots = 100.00."""
        m = HybridSurvivabilityMap(
            total_points=50,
            redundant_hybrid_count=30,
            optical_only_count=10,
            acoustic_only_count=10,
            blind_spot_count=0,
            any_coverage_fraction=1.0,
        )
        assert m.any_coverage_pct == 100.00

    def test_any_coverage_pct_partial(self):
        m = HybridSurvivabilityMap(
            total_points=100,
            blind_spot_count=5,
            any_coverage_fraction=0.95,
        )
        assert m.any_coverage_pct < 100.0

    def test_blind_spot_pct_zero(self):
        """V60 FIX (P3-3): True zero blind spots = 0.00."""
        m = HybridSurvivabilityMap(
            total_points=100,
            blind_spot_count=0,
            blind_spot_fraction=0.0,
        )
        assert m.blind_spot_pct == 0.00

    def test_blind_spot_pct_small(self):
        """V60 FIX (P3-3): Tiny blind spot must NOT round to 0.00."""
        m = HybridSurvivabilityMap(
            total_points=100000,
            blind_spot_count=5,
            blind_spot_fraction=5 / 100000,
        )
        pct = m.blind_spot_pct
        # Must NOT be 0.00 if blind_spot_count > 0
        if m.blind_spot_count > 0:
            assert pct > 0.0

    def test_is_fully_covered(self):
        m = HybridSurvivabilityMap(
            total_points=100,
            blind_spot_count=0,
            any_coverage_fraction=1.0,
        )
        assert m.is_fully_covered is True

    def test_is_not_fully_covered(self):
        m = HybridSurvivabilityMap(
            total_points=100,
            blind_spot_count=1,
        )
        assert m.is_fully_covered is False

    def test_is_fully_covered_zero_points(self):
        """Zero points with zero blind spots is NOT fully covered."""
        m = HybridSurvivabilityMap(
            total_points=0,
            blind_spot_count=0,
        )
        assert m.is_fully_covered is False

    def test_is_nfpa72_compliant(self):
        """NFPA 72 §17.8.3.4: All points REDUNDANT_HYBRID."""
        m = HybridSurvivabilityMap(
            total_points=50,
            redundant_hybrid_count=50,
            hybrid_coverage_fraction=1.0,
        )
        assert m.is_nfpa72_compliant is True

    def test_is_not_nfpa72_compliant(self):
        m = HybridSurvivabilityMap(
            total_points=50,
            redundant_hybrid_count=30,
            optical_only_count=20,
        )
        assert m.is_nfpa72_compliant is False

    def test_has_blind_spots(self):
        m = HybridSurvivabilityMap(total_points=100, blind_spot_count=5)
        assert m.has_blind_spots is True

    def test_no_blind_spots(self):
        m = HybridSurvivabilityMap(total_points=100, blind_spot_count=0)
        assert m.has_blind_spots is False

    def test_frozen(self):
        m = HybridSurvivabilityMap(total_points=100)
        with pytest.raises(Exception):
            m.total_points = 200

    def test_negative_total_points_rejected(self):
        with pytest.raises(Exception):
            HybridSurvivabilityMap(total_points=-1)

    def test_coverage_fraction_bounds(self):
        with pytest.raises(Exception):
            HybridSurvivabilityMap(
                total_points=100,
                hybrid_coverage_fraction=1.5,
            )

    def test_warnings_default_empty(self):
        m = HybridSurvivabilityMap(total_points=100)
        assert m.warnings == []


# ─────────────────────────────────────────────────────────────────────────────
# HybridSurvivabilityEngine — Initialization
# ─────────────────────────────────────────────────────────────────────────────


class TestHybridSurvivabilityEngineInit:
    def test_default_init(self):
        engine = HybridSurvivabilityEngine()
        assert engine._leak_spl == 100.0
        assert engine._freq_hz == 40_000.0
        assert engine._temp_c == 40.0
        assert engine._rh_pct == 50.0

    def test_custom_init(self):
        engine = HybridSurvivabilityEngine(
            leak_spl_at_1m=110.0,
            center_frequency_hz=25_000.0,
            temp_c=25.0,
            relative_humidity_pct=80.0,
        )
        assert engine._leak_spl == 110.0
        assert engine._freq_hz == 25_000.0
        assert engine._temp_c == 25.0
        assert engine._rh_pct == 80.0


# ─────────────────────────────────────────────────────────────────────────────
# HybridSurvivabilityEngine — analyse() Validation
# ─────────────────────────────────────────────────────────────────────────────


class TestHybridSurvivabilityEngineValidation:
    def _make_optical_result(self, total_points, redundancy_map=None):
        """Create a mock CoverageResult."""
        result = MagicMock()
        result.total_points = total_points
        result.redundancy_map = redundancy_map or {}
        return result

    def _make_grid(self, n_points):
        """Create a list of mock RayTracePoint."""
        points = []
        for i in range(n_points):
            pt = MagicMock()
            pt.x = float(i)
            pt.y = 0.0
            pt.z = 3.0
            points.append(pt)
        return points

    def test_empty_grid_raises(self):
        engine = HybridSurvivabilityEngine()
        optical = self._make_optical_result(0)
        with pytest.raises(ValueError, match="Grid must not be empty"):
            engine.analyse(optical, [], [], {})

    def test_length_mismatch_raises(self):
        engine = HybridSurvivabilityEngine()
        optical = self._make_optical_result(10)
        grid = self._make_grid(5)
        with pytest.raises(ValueError, match="Grid length"):
            engine.analyse(optical, grid, [], {})

    def test_missing_sensor_position_raises(self):
        engine = HybridSurvivabilityEngine()
        optical = self._make_optical_result(1)
        grid = self._make_grid(1)
        sensor = MagicMock()
        sensor.sensor_id = "UGLD-1"
        with pytest.raises(ValueError, match="has no position"):
            engine.analyse(optical, grid, [sensor], {})


# ─────────────────────────────────────────────────────────────────────────────
# HybridSurvivabilityEngine — analyse() Classification
# ─────────────────────────────────────────────────────────────────────────────


class TestHybridSurvivabilityEngineClassification:
    """Test the 4-state classification logic.

    Classification is the Cartesian product of {optical, no_optical}
    x {acoustic, no_acoustic}, yielding 4 exhaustive and mutually
    exclusive states.
    """

    def _make_optical_result(self, total_points, redundancy_map=None):
        result = MagicMock()
        result.total_points = total_points
        result.redundancy_map = redundancy_map or {}
        return result

    def _make_grid(self, n_points):
        points = []
        for i in range(n_points):
            pt = MagicMock()
            pt.x = float(i)
            pt.y = 0.0
            pt.z = 3.0
            points.append(pt)
        return points

    def _make_ray_result(self, triggered=True, snr_db=25.0, margin_db=5.0,
                         has_los=True, insertion_loss=0.0, distance=15.0):
        trigger = MagicMock()
        trigger.triggered = triggered
        trigger.snr_db = snr_db
        trigger.margin_to_threshold_db = margin_db
        result = MagicMock()
        result.trigger_result = trigger
        result.has_los = has_los
        result.total_insertion_loss_db = insertion_loss
        result.distance_meters = distance
        return result

    def test_all_redundant_hybrid(self):
        """All points have both optical and acoustic coverage."""
        engine = HybridSurvivabilityEngine()
        n = 5
        optical = self._make_optical_result(n, redundancy_map=dict.fromkeys(range(n), 1))
        grid = self._make_grid(n)
        sensor = MagicMock()
        sensor.sensor_id = "UGLD-1"
        sensor_positions = {"UGLD-1": (0.0, 0.0, 3.0)}

        with patch("fireai.core.hybrid_survivability.trace_acoustic_ray") as mock_trace:
            mock_trace.return_value = self._make_ray_result(triggered=True)
            result = engine.analyse(optical, grid, [sensor], sensor_positions)

        assert result.redundant_hybrid_count == n
        assert result.blind_spot_count == 0
        assert result.is_fully_covered is True

    def test_all_optical_only(self):
        """All points have optical but no acoustic coverage."""
        engine = HybridSurvivabilityEngine()
        n = 5
        optical = self._make_optical_result(n, redundancy_map=dict.fromkeys(range(n), 1))
        grid = self._make_grid(n)
        sensor = MagicMock()
        sensor.sensor_id = "UGLD-1"
        sensor_positions = {"UGLD-1": (0.0, 0.0, 3.0)}

        with patch("fireai.core.hybrid_survivability.trace_acoustic_ray") as mock_trace:
            mock_trace.return_value = self._make_ray_result(triggered=False, snr_db=-5.0, margin_db=-15.0)
            result = engine.analyse(optical, grid, [sensor], sensor_positions)

        assert result.optical_only_count == n
        assert result.redundant_hybrid_count == 0
        assert result.acoustic_only_count == 0
        assert result.blind_spot_count == 0

    def test_all_acoustic_only(self):
        """All points have acoustic but no optical coverage."""
        engine = HybridSurvivabilityEngine()
        n = 5
        optical = self._make_optical_result(n, redundancy_map={})  # No optical coverage
        grid = self._make_grid(n)
        sensor = MagicMock()
        sensor.sensor_id = "UGLD-1"
        sensor_positions = {"UGLD-1": (0.0, 0.0, 3.0)}

        with patch("fireai.core.hybrid_survivability.trace_acoustic_ray") as mock_trace:
            mock_trace.return_value = self._make_ray_result(triggered=True)
            result = engine.analyse(optical, grid, [sensor], sensor_positions)

        assert result.acoustic_only_count == n
        assert result.redundant_hybrid_count == 0

    def test_all_blind_spots(self):
        """No coverage at all — all BLIND_SPOT."""
        engine = HybridSurvivabilityEngine()
        n = 5
        optical = self._make_optical_result(n, redundancy_map={})
        grid = self._make_grid(n)
        sensor = MagicMock()
        sensor.sensor_id = "UGLD-1"
        sensor_positions = {"UGLD-1": (0.0, 0.0, 3.0)}

        with patch("fireai.core.hybrid_survivability.trace_acoustic_ray") as mock_trace:
            mock_trace.return_value = self._make_ray_result(triggered=False, snr_db=-10.0, margin_db=-20.0)
            result = engine.analyse(optical, grid, [sensor], sensor_positions)

        assert result.blind_spot_count == n
        assert result.has_blind_spots is True
        assert result.is_fully_covered is False

    def test_no_ugld_sensors_warning(self):
        """No UGLD sensors → warning about optical-only classification."""
        engine = HybridSurvivabilityEngine()
        n = 3
        optical = self._make_optical_result(n, redundancy_map=dict.fromkeys(range(n), 1))
        grid = self._make_grid(n)

        result = engine.analyse(optical, grid, [], {})
        assert len(result.warnings) > 0
        assert any("No UGLD sensors" in w for w in result.warnings)

    def test_mixed_classification(self):
        """Mix of all 4 states."""
        engine = HybridSurvivabilityEngine()
        n = 4
        # Point 0: optical only, Point 1: acoustic only, Point 2: both, Point 3: neither
        optical = self._make_optical_result(
            n,
            redundancy_map={0: 1, 2: 1}  # Points 0, 2 have optical
        )
        grid = self._make_grid(n)
        sensor = MagicMock()
        sensor.sensor_id = "UGLD-1"
        sensor_positions = {"UGLD-1": (0.0, 0.0, 3.0)}

        def mock_trace_side_effect(leak_point, sensor_point, obstacles, sensor, **kwargs):
            lp = leak_point
            if lp[0] == 0.0:  # Point 0: optical yes, acoustic no
                return self._make_ray_result(triggered=False, snr_db=-5.0)
            elif lp[0] == 1.0:  # Point 1: optical no, acoustic yes
                return self._make_ray_result(triggered=True)
            elif lp[0] == 2.0:  # Point 2: optical yes, acoustic yes
                return self._make_ray_result(triggered=True)
            else:  # Point 3: neither
                return self._make_ray_result(triggered=False, snr_db=-10.0)

        with patch("fireai.core.hybrid_survivability.trace_acoustic_ray") as mock_trace:
            mock_trace.side_effect = mock_trace_side_effect
            result = engine.analyse(optical, grid, [sensor], sensor_positions)

        assert result.optical_only_count == 1   # Point 0
        assert result.acoustic_only_count == 1   # Point 1
        assert result.redundant_hybrid_count == 1  # Point 2
        assert result.blind_spot_count == 1       # Point 3

    def test_blind_spot_warning_generated(self):
        """BLIND_SPOT points must generate a warning per NFPA 72 §17.8.3.4."""
        engine = HybridSurvivabilityEngine()
        n = 5
        optical = self._make_optical_result(n, redundancy_map={})
        grid = self._make_grid(n)
        sensor = MagicMock()
        sensor.sensor_id = "UGLD-1"
        sensor_positions = {"UGLD-1": (0.0, 0.0, 3.0)}

        with patch("fireai.core.hybrid_survivability.trace_acoustic_ray") as mock_trace:
            mock_trace.return_value = self._make_ray_result(triggered=False, snr_db=-10.0)
            result = engine.analyse(optical, grid, [sensor], sensor_positions)

        assert any("BLIND_SPOT" in w for w in result.warnings)
        assert any("§17.8.3.4" in w for w in result.warnings)

    def test_low_redundancy_warning(self):
        """Low hybrid redundancy (<50%) must generate a warning."""
        engine = HybridSurvivabilityEngine()
        n = 10
        # Only 2 out of 10 points have redundant hybrid
        optical = self._make_optical_result(
            n,
            redundancy_map=dict.fromkeys(range(n), 1)  # All have optical
        )
        grid = self._make_grid(n)
        sensor = MagicMock()
        sensor.sensor_id = "UGLD-1"
        sensor_positions = {"UGLD-1": (0.0, 0.0, 3.0)}

        call_count = [0]

        def mock_trace_side_effect(leak_point, sensor_point, obstacles, sensor, **kwargs):
            call_count[0] += 1
            # Only first 2 points trigger
            if call_count[0] <= 2:
                return self._make_ray_result(triggered=True)
            return self._make_ray_result(triggered=False, snr_db=-5.0)

        with patch("fireai.core.hybrid_survivability.trace_acoustic_ray") as mock_trace:
            mock_trace.side_effect = mock_trace_side_effect
            result = engine.analyse(optical, grid, [sensor], sensor_positions)

        assert any("Low hybrid redundancy" in w for w in result.warnings)

    def test_best_snr_selected(self):
        """When multiple sensors cover a point, the best SNR must be selected."""
        engine = HybridSurvivabilityEngine()
        n = 1
        optical = self._make_optical_result(n, redundancy_map={0: 1})
        grid = self._make_grid(n)
        sensor1 = MagicMock()
        sensor1.sensor_id = "UGLD-1"
        sensor2 = MagicMock()
        sensor2.sensor_id = "UGLD-2"
        sensor_positions = {
            "UGLD-1": (0.0, 0.0, 3.0),
            "UGLD-2": (10.0, 0.0, 3.0),
        }

        call_count = [0]

        def mock_trace_side_effect(leak_point, sensor_point, obstacles, sensor, **kwargs):
            call_count[0] += 1
            if sensor.sensor_id == "UGLD-1":
                return self._make_ray_result(triggered=True, snr_db=20.0)
            else:
                return self._make_ray_result(triggered=True, snr_db=30.0)

        with patch("fireai.core.hybrid_survivability.trace_acoustic_ray") as mock_trace:
            mock_trace.side_effect = mock_trace_side_effect
            result = engine.analyse(optical, grid, [sensor1, sensor2], sensor_positions)

        # Point should have acoustic detail from the BEST sensor (UGLD-2, snr=30)
        pr = result.point_results[0]
        assert pr.best_acoustic_detail is not None
        assert pr.best_acoustic_detail.snr_db == 30.0

    def test_acoustic_detail_stored_only_if_triggered(self):
        """Acoustic detail is stored only if the sensor triggered."""
        engine = HybridSurvivabilityEngine()
        n = 1
        optical = self._make_optical_result(n, redundancy_map={0: 0})  # No optical
        grid = self._make_grid(n)
        sensor = MagicMock()
        sensor.sensor_id = "UGLD-1"
        sensor_positions = {"UGLD-1": (0.0, 0.0, 3.0)}

        with patch("fireai.core.hybrid_survivability.trace_acoustic_ray") as mock_trace:
            mock_trace.return_value = self._make_ray_result(triggered=False, snr_db=-5.0)
            result = engine.analyse(optical, grid, [sensor], sensor_positions)

        # Acoustic NOT triggered → best_acoustic_detail should be None
        pr = result.point_results[0]
        assert pr.best_acoustic_detail is None


# ─────────────────────────────────────────────────────────────────────────────
# HybridSurvivabilityEngine — export_heatmap_json()
# ─────────────────────────────────────────────────────────────────────────────


class TestExportHeatmapJson:
    def test_export_creates_file(self, tmp_path):
        engine = HybridSurvivabilityEngine()
        hmap = HybridSurvivabilityMap(total_points=2, point_results={
            0: HybridPointResult(
                point_index=0, x=1.0, y=2.0, z=3.0,
                survivability_class=SurvivabilityClass.REDUNDANT_HYBRID,
                optical_detector_count=1,
            ),
            1: HybridPointResult(
                point_index=1, x=4.0, y=5.0, z=3.0,
                survivability_class=SurvivabilityClass.BLIND_SPOT,
                optical_detector_count=0,
            ),
        })
        output_path = str(tmp_path / "heatmap.json")
        result = engine.export_heatmap_json(hmap, output_path)
        assert result == output_path
        assert os.path.exists(output_path)

    def test_export_valid_json(self, tmp_path):
        engine = HybridSurvivabilityEngine()
        hmap = HybridSurvivabilityMap(total_points=1, point_results={
            0: HybridPointResult(
                point_index=0, x=1.0, y=2.0, z=3.0,
                survivability_class=SurvivabilityClass.OPTICAL_ONLY,
                optical_detector_count=2,
            ),
        })
        output_path = str(tmp_path / "heatmap.json")
        engine.export_heatmap_json(hmap, output_path)
        with open(output_path) as f:
            data = json.load(f)
        assert "meta" in data
        assert "statistics" in data
        assert "points" in data
        assert data["meta"]["total_points"] == 1

    def test_export_color_map(self, tmp_path):
        """Each survivability class must have a specific color."""
        engine = HybridSurvivabilityEngine()
        hmap = HybridSurvivabilityMap(total_points=4, point_results={
            0: HybridPointResult(
                point_index=0, x=1.0, y=2.0, z=3.0,
                survivability_class=SurvivabilityClass.REDUNDANT_HYBRID,
            ),
            1: HybridPointResult(
                point_index=1, x=4.0, y=5.0, z=3.0,
                survivability_class=SurvivabilityClass.OPTICAL_ONLY,
            ),
            2: HybridPointResult(
                point_index=2, x=7.0, y=8.0, z=3.0,
                survivability_class=SurvivabilityClass.ACOUSTIC_ONLY,
            ),
            3: HybridPointResult(
                point_index=3, x=10.0, y=11.0, z=3.0,
                survivability_class=SurvivabilityClass.BLIND_SPOT,
            ),
        })
        output_path = str(tmp_path / "heatmap.json")
        engine.export_heatmap_json(hmap, output_path)
        with open(output_path) as f:
            data = json.load(f)

        colors = {p["class"]: p["color"] for p in data["points"]}
        assert colors["REDUNDANT_HYBRID"] == "#00AA44"
        assert colors["OPTICAL_ONLY"] == "#FFD700"
        assert colors["ACOUSTIC_ONLY"] == "#FF8C00"
        assert colors["BLIND_SPOT"] == "#CC0000"

    def test_export_standards_references(self, tmp_path):
        """Export must include NFPA 72 and ISA-TR references."""
        engine = HybridSurvivabilityEngine()
        hmap = HybridSurvivabilityMap(total_points=1, point_results={
            0: HybridPointResult(
                point_index=0, x=1.0, y=2.0, z=3.0,
                survivability_class=SurvivabilityClass.REDUNDANT_HYBRID,
            ),
        })
        output_path = str(tmp_path / "heatmap.json")
        engine.export_heatmap_json(hmap, output_path)
        with open(output_path) as f:
            data = json.load(f)

        standards = data["meta"]["standards"]
        assert any("NFPA 72" in s for s in standards)
        assert any("ISA-TR 84" in s for s in standards)

    def test_export_acoustic_snr(self, tmp_path):
        """Export must include acoustic SNR when available."""
        engine = HybridSurvivabilityEngine()
        detail = AcousticCoverageDetail(
            sensor_id="UGLD-1",
            triggered=True,
            snr_db=28.5,
            margin_to_threshold_db=8.5,
            has_los=True,
            distance_meters=12.0,
        )
        hmap = HybridSurvivabilityMap(total_points=1, point_results={
            0: HybridPointResult(
                point_index=0, x=1.0, y=2.0, z=3.0,
                survivability_class=SurvivabilityClass.REDUNDANT_HYBRID,
                best_acoustic_detail=detail,
            ),
        })
        output_path = str(tmp_path / "heatmap.json")
        engine.export_heatmap_json(hmap, output_path)
        with open(output_path) as f:
            data = json.load(f)

        assert data["points"][0]["acoustic_snr_db"] == 28.5

    def test_export_no_acoustic_snr(self, tmp_path):
        """Points without acoustic detail must have null SNR."""
        engine = HybridSurvivabilityEngine()
        hmap = HybridSurvivabilityMap(total_points=1, point_results={
            0: HybridPointResult(
                point_index=0, x=1.0, y=2.0, z=3.0,
                survivability_class=SurvivabilityClass.OPTICAL_ONLY,
            ),
        })
        output_path = str(tmp_path / "heatmap.json")
        engine.export_heatmap_json(hmap, output_path)
        with open(output_path) as f:
            data = json.load(f)

        assert data["points"][0]["acoustic_snr_db"] is None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
