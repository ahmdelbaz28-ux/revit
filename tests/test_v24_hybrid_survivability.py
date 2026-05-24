"""
test_v24_hybrid_survivability.py — Layer 7 Hybrid Survivability Index Tests
============================================================================
Tests for the intersection of Layer 5 optical and V23 acoustic coverage.

Covers:
  - 4-state classification (REDUNDANT_HYBRID, OPTICAL_ONLY, ACOUSTIC_ONLY, BLIND_SPOT)
  - Acoustic grid analysis (UGLD per-grid-point)
  - Aggregate statistics (fractions, percentages)
  - Diagnostics and warnings
  - Edge cases (no sensors, no optical coverage, empty grid, mismatch)
  - Physical correctness (SNR-based classification)
  - Pydantic model validation
"""

import math
import pytest

from fireai.core.hybrid_survivability import (
    AcousticCoverageDetail,
    HybridPointResult,
    HybridSurvivabilityEngine,
    HybridSurvivabilityMap,
    SurvivabilityClass,
)
from fireai.core.flame_detector_aoc_raytrace import (
    CoverageResult,
    SingleDetectorResult,
)
from fireai.core.models_v21 import RayTracePoint
from fireai.core.ugld_acoustics import UltrasonicSensor
from fireai.core.ugld_raytrace import AcousticObstacle


# ── Fixtures ──────────────────────────────────────────────────────────────

@pytest.fixture
def simple_grid() -> list:
    """5x5 grid at z=0, 1m spacing."""
    pts = []
    for y in range(5):
        for x in range(5):
            pts.append(RayTracePoint(x=float(x), y=float(y), z=0.0))
    return pts


@pytest.fixture
def full_optical_result(simple_grid) -> CoverageResult:
    """All 25 points optically covered by 2 detectors (redundant)."""
    n = len(simple_grid)
    redundancy_map = {i: 2 for i in range(n)}
    per_det = {
        "FL-001": SingleDetectorResult(
            detector_id="FL-001",
            covered_pts=frozenset(range(n)),
            effective_range_m=15.0,
        ),
        "FL-002": SingleDetectorResult(
            detector_id="FL-002",
            covered_pts=frozenset(range(n)),
            effective_range_m=15.0,
        ),
    }
    return CoverageResult(
        total_points=n,
        covered_points=n,
        coverage_fraction=1.0,
        per_detector=per_det,
        warnings=[],
        redundancy_map=redundancy_map,
        min_redundancy=2,
        mean_redundancy=2.0,
        double_covered_pct=100.0,
    )


@pytest.fixture
def partial_optical_result(simple_grid) -> CoverageResult:
    """First 12 points covered, last 13 uncovered."""
    n = len(simple_grid)
    covered = set(range(12))
    redundancy_map = {i: 1 for i in range(12)}
    per_det = {
        "FL-001": SingleDetectorResult(
            detector_id="FL-001",
            covered_pts=frozenset(covered),
            effective_range_m=10.0,
        ),
    }
    return CoverageResult(
        total_points=n,
        covered_points=12,
        coverage_fraction=12.0 / n,
        per_detector=per_det,
        warnings=[],
        redundancy_map=redundancy_map,
        min_redundancy=0,
        mean_redundancy=0.48,
        double_covered_pct=0.0,
    )


@pytest.fixture
def no_optical_result(simple_grid) -> CoverageResult:
    """No optical coverage at all."""
    n = len(simple_grid)
    return CoverageResult(
        total_points=n,
        covered_points=0,
        coverage_fraction=0.0,
        per_detector={},
        warnings=[],
        redundancy_map={},
        min_redundancy=0,
        mean_redundancy=0.0,
        double_covered_pct=0.0,
    )


@pytest.fixture
def ugld_sensor() -> UltrasonicSensor:
    return UltrasonicSensor(
        sensor_id="UGLD-001",
        trigger_threshold_db=74.0,
        background_noise_db=60.0,
        center_frequency_hz=40_000.0,
    )


@pytest.fixture
def ugld_sensor_positions() -> dict:
    """Sensor at (2.0, 2.0, 3.0) — center of grid, elevated 3m."""
    return {"UGLD-001": (2.0, 2.0, 3.0)}


# ===========================================================================
# SurvivabilityClass tests
# ===========================================================================

class TestSurvivabilityClass:

    def test_four_states_exist(self):
        assert len(SurvivabilityClass) == 4

    def test_redundant_hybrid_is_covered(self):
        assert SurvivabilityClass.REDUNDANT_HYBRID.is_covered is True

    def test_redundant_hybrid_is_redundant(self):
        assert SurvivabilityClass.REDUNDANT_HYBRID.is_redundant is True

    def test_optical_only_is_covered_not_redundant(self):
        assert SurvivabilityClass.OPTICAL_ONLY.is_covered is True
        assert SurvivabilityClass.OPTICAL_ONLY.is_redundant is False

    def test_acoustic_only_is_covered_not_redundant(self):
        assert SurvivabilityClass.ACOUSTIC_ONLY.is_covered is True
        assert SurvivabilityClass.ACOUSTIC_ONLY.is_redundant is False

    def test_blind_spot_not_covered(self):
        assert SurvivabilityClass.BLIND_SPOT.is_covered is False
        assert SurvivabilityClass.BLIND_SPOT.is_redundant is False

    def test_severity_rank_ordering(self):
        assert SurvivabilityClass.REDUNDANT_HYBRID.severity_rank < \
               SurvivabilityClass.OPTICAL_ONLY.severity_rank < \
               SurvivabilityClass.ACOUSTIC_ONLY.severity_rank < \
               SurvivabilityClass.BLIND_SPOT.severity_rank

    def test_string_enum_values(self):
        assert SurvivabilityClass.REDUNDANT_HYBRID.value == "REDUNDANT_HYBRID"
        assert SurvivabilityClass.BLIND_SPOT.value == "BLIND_SPOT"


# ===========================================================================
# Pydantic model tests
# ===========================================================================

class TestAcousticCoverageDetail:

    def test_create_valid(self):
        d = AcousticCoverageDetail(
            sensor_id="UGLD-001",
            triggered=True,
            snr_db=15.0,
            margin_to_threshold_db=5.0,
            has_los=True,
            total_insertion_loss_db=0.0,
            distance_meters=8.5,
        )
        assert d.triggered is True
        assert d.snr_db == 15.0

    def test_frozen(self):
        d = AcousticCoverageDetail(
            sensor_id="UGLD-001", triggered=True, snr_db=15.0,
            margin_to_threshold_db=5.0, has_los=True,
            distance_meters=8.5,
        )
        with pytest.raises(Exception):
            d.snr_db = 20.0


class TestHybridPointResult:

    def test_create_with_acoustic(self):
        ac = AcousticCoverageDetail(
            sensor_id="UGLD-001", triggered=True, snr_db=12.0,
            margin_to_threshold_db=3.0, has_los=True,
            distance_meters=10.0,
        )
        r = HybridPointResult(
            point_index=0, x=1.0, y=2.0, z=0.0,
            survivability_class=SurvivabilityClass.REDUNDANT_HYBRID,
            optical_detector_count=2,
            best_acoustic_detail=ac,
        )
        assert r.best_acoustic_detail is not None
        assert r.best_acoustic_detail.snr_db == 12.0

    def test_create_without_acoustic(self):
        r = HybridPointResult(
            point_index=0, x=1.0, y=2.0, z=0.0,
            survivability_class=SurvivabilityClass.BLIND_SPOT,
        )
        assert r.best_acoustic_detail is None
        assert r.optical_detector_count == 0


class TestHybridSurvivabilityMap:

    def test_create_valid(self):
        m = HybridSurvivabilityMap(
            total_points=100,
            redundant_hybrid_count=60,
            optical_only_count=20,
            acoustic_only_count=10,
            blind_spot_count=10,
            hybrid_coverage_fraction=0.6,
            any_coverage_fraction=0.9,
            blind_spot_fraction=0.1,
        )
        assert m.is_fully_covered is False
        assert m.has_blind_spots is True
        assert m.blind_spot_pct == 10.0

    def test_fully_covered_no_blind_spots(self):
        m = HybridSurvivabilityMap(
            total_points=100,
            redundant_hybrid_count=80,
            optical_only_count=15,
            acoustic_only_count=5,
            blind_spot_count=0,
            hybrid_coverage_fraction=0.8,
            any_coverage_fraction=1.0,
            blind_spot_fraction=0.0,
        )
        assert m.is_fully_covered is True
        assert m.has_blind_spots is False

    def test_nfpa72_compliant(self):
        m = HybridSurvivabilityMap(
            total_points=50,
            redundant_hybrid_count=50,
            optical_only_count=0,
            acoustic_only_count=0,
            blind_spot_count=0,
            hybrid_coverage_fraction=1.0,
            any_coverage_fraction=1.0,
            blind_spot_fraction=0.0,
        )
        assert m.is_nfpa72_compliant is True

    def test_not_nfpa72_compliant(self):
        m = HybridSurvivabilityMap(
            total_points=50,
            redundant_hybrid_count=40,
            optical_only_count=10,
            acoustic_only_count=0,
            blind_spot_count=0,
            hybrid_coverage_fraction=0.8,
            any_coverage_fraction=1.0,
            blind_spot_fraction=0.0,
        )
        assert m.is_nfpa72_compliant is False

    def test_zero_total_not_nfpa72(self):
        m = HybridSurvivabilityMap(total_points=0)
        assert m.is_nfpa72_compliant is False

    def test_redundant_hybrid_pct(self):
        m = HybridSurvivabilityMap(
            total_points=200,
            hybrid_coverage_fraction=0.75,
        )
        assert m.redundant_hybrid_pct == 75.0


# ===========================================================================
# Engine integration tests
# ===========================================================================

class TestHybridSurvivabilityEngine:

    def test_full_hybrid_coverage(
        self, full_optical_result, simple_grid,
        ugld_sensor, ugld_sensor_positions,
    ):
        """With full optical + sensor near center: most points should be hybrid."""
        engine = HybridSurvivabilityEngine(
            leak_spl_at_1m=100.0,
        )
        result = engine.analyse(
            optical_result=full_optical_result,
            grid=simple_grid,
            ugld_sensors=[ugld_sensor],
            sensor_positions=ugld_sensor_positions,
        )
        assert result.total_points == 25
        # Sensor at (2,2,3) should cover most of a 4x4m grid
        assert result.redundant_hybrid_count > 0
        assert result.any_coverage_fraction > 0.5

    def test_optical_only_when_no_ugld(
        self, full_optical_result, simple_grid,
    ):
        """Without UGLD sensors, all covered points become OPTICAL_ONLY."""
        engine = HybridSurvivabilityEngine()
        result = engine.analyse(
            optical_result=full_optical_result,
            grid=simple_grid,
            ugld_sensors=[],
            sensor_positions={},
        )
        assert result.optical_only_count == 25
        assert result.redundant_hybrid_count == 0
        assert result.acoustic_only_count == 0
        assert "No UGLD sensors" in result.warnings[0]

    def test_acoustic_only_for_uncovered_optical(
        self, no_optical_result, simple_grid,
        ugld_sensor, ugld_sensor_positions,
    ):
        """With no optical coverage, covered acoustic points are ACOUSTIC_ONLY."""
        engine = HybridSurvivabilityEngine(leak_spl_at_1m=100.0)
        result = engine.analyse(
            optical_result=no_optical_result,
            grid=simple_grid,
            ugld_sensors=[ugld_sensor],
            sensor_positions=ugld_sensor_positions,
        )
        # Sensor at (2,2,3) covers nearby points acoustically
        assert result.acoustic_only_count > 0
        assert result.optical_only_count == 0

    def test_blind_spot_detection(
        self, no_optical_result, simple_grid,
    ):
        """Far away sensor + no optical = BLIND_SPOT for distant points."""
        far_sensor = UltrasonicSensor(
            sensor_id="UGLD-FAR",
            trigger_threshold_db=80.0,
            background_noise_db=65.0,
        )
        far_positions = {"UGLD-FAR": (100.0, 100.0, 3.0)}
        engine = HybridSurvivabilityEngine(leak_spl_at_1m=80.0)
        result = engine.analyse(
            optical_result=no_optical_result,
            grid=simple_grid,
            ugld_sensors=[far_sensor],
            sensor_positions=far_positions,
        )
        # All points too far for acoustic + no optical = all BLIND_SPOT
        assert result.blind_spot_count == 25
        assert result.has_blind_spots is True
        assert result.is_fully_covered is False
        assert any("BLIND_SPOT" in w for w in result.warnings)

    def test_mixed_classification(
        self, partial_optical_result, simple_grid,
        ugld_sensor, ugld_sensor_positions,
    ):
        """Partial optical + acoustic coverage → mix of all 4 states."""
        engine = HybridSurvivabilityEngine(leak_spl_at_1m=100.0)
        result = engine.analyse(
            optical_result=partial_optical_result,
            grid=simple_grid,
            ugld_sensors=[ugld_sensor],
            sensor_positions=ugld_sensor_positions,
        )
        # Should have a mix — at least 2 different states
        non_zero_states = sum(1 for c in [
            result.redundant_hybrid_count,
            result.optical_only_count,
            result.acoustic_only_count,
            result.blind_spot_count,
        ] if c > 0)
        assert non_zero_states >= 2

    def test_empty_grid_raises(self, full_optical_result):
        engine = HybridSurvivabilityEngine()
        with pytest.raises(ValueError, match="Grid must not be empty"):
            engine.analyse(
                optical_result=full_optical_result,
                grid=[],
                ugld_sensors=[],
                sensor_positions={},
            )

    def test_grid_length_mismatch_raises(self, simple_grid):
        wrong_result = CoverageResult(
            total_points=999,
            covered_points=999,
            coverage_fraction=1.0,
            per_detector={},
            warnings=[],
            redundancy_map={i: 1 for i in range(999)},
        )
        engine = HybridSurvivabilityEngine()
        with pytest.raises(ValueError, match="does not match"):
            engine.analyse(
                optical_result=wrong_result,
                grid=simple_grid,
                ugld_sensors=[],
                sensor_positions={},
            )

    def test_missing_sensor_position_raises(
        self, full_optical_result, simple_grid, ugld_sensor,
    ):
        engine = HybridSurvivabilityEngine()
        with pytest.raises(ValueError, match="has no position"):
            engine.analyse(
                optical_result=full_optical_result,
                grid=simple_grid,
                ugld_sensors=[ugld_sensor],
                sensor_positions={},  # Missing!
            )

    def test_obstacle_blocking_acoustic(
        self, full_optical_result, simple_grid,
        ugld_sensor, ugld_sensor_positions,
    ):
        """Obstacle between sensor and grid should reduce acoustic coverage."""
        # Steel plate obstacle between sensor (2,2,3) and far grid points
        obstacle = AcousticObstacle(
            obstacle_id="WALL-1",
            vertices=[[1.5, 1.5, 0.0], [1.5, 2.5, 3.0]],
            surface_type="concrete_block",
        )

        engine = HybridSurvivabilityEngine(leak_spl_at_1m=100.0)

        # Without obstacle
        result_clear = engine.analyse(
            optical_result=full_optical_result,
            grid=simple_grid,
            ugld_sensors=[ugld_sensor],
            sensor_positions=ugld_sensor_positions,
        )

        # With obstacle
        result_blocked = engine.analyse(
            optical_result=full_optical_result,
            grid=simple_grid,
            ugld_sensors=[ugld_sensor],
            sensor_positions=ugld_sensor_positions,
            acoustic_obstacles=[obstacle],
        )

        # Obstacle should reduce acoustic coverage (fewer hybrid points)
        assert result_blocked.redundant_hybrid_count <= result_clear.redundant_hybrid_count

    def test_multiple_sensors_best_snr(
        self, full_optical_result, simple_grid,
    ):
        """With multiple sensors, best SNR is selected per point."""
        sensor_close = UltrasonicSensor(
            sensor_id="CLOSE", trigger_threshold_db=74.0,
            background_noise_db=60.0,
        )
        sensor_far = UltrasonicSensor(
            sensor_id="FAR", trigger_threshold_db=74.0,
            background_noise_db=60.0,
        )
        positions = {
            "CLOSE": (2.0, 2.0, 3.0),
            "FAR": (50.0, 50.0, 3.0),
        }

        engine = HybridSurvivabilityEngine(leak_spl_at_1m=100.0)
        result = engine.analyse(
            optical_result=full_optical_result,
            grid=simple_grid,
            ugld_sensors=[sensor_close, sensor_far],
            sensor_positions=positions,
        )
        # Close sensor should dominate — best SNR selected
        # Most points should be covered by CLOSE sensor
        close_count = sum(
            1 for pr in result.point_results.values()
            if pr.best_acoustic_detail is not None
            and pr.best_acoustic_detail.sensor_id == "CLOSE"
        )
        assert close_count > 0

    def test_acoustic_detail_stored_for_hybrid(
        self, full_optical_result, simple_grid,
        ugld_sensor, ugld_sensor_positions,
    ):
        """Hybrid points should have acoustic detail stored."""
        engine = HybridSurvivabilityEngine(leak_spl_at_1m=100.0)
        result = engine.analyse(
            optical_result=full_optical_result,
            grid=simple_grid,
            ugld_sensors=[ugld_sensor],
            sensor_positions=ugld_sensor_positions,
        )
        hybrid_pts = [
            pr for pr in result.point_results.values()
            if pr.survivability_class == SurvivabilityClass.REDUNDANT_HYBRID
        ]
        for pt in hybrid_pts:
            assert pt.best_acoustic_detail is not None
            assert pt.best_acoustic_detail.triggered is True
            assert pt.best_acoustic_detail.snr_db >= 6.0  # SNR threshold

    def test_low_hybrid_redundancy_warning(
        self, partial_optical_result, simple_grid,
        ugld_sensor, ugld_sensor_positions,
    ):
        """If <50% hybrid, a warning should be emitted."""
        engine = HybridSurvivabilityEngine(leak_spl_at_1m=100.0)
        result = engine.analyse(
            optical_result=partial_optical_result,
            grid=simple_grid,
            ugld_sensors=[ugld_sensor],
            sensor_positions=ugld_sensor_positions,
        )
        if result.hybrid_coverage_fraction < 0.5:
            assert any("Low hybrid redundancy" in w for w in result.warnings)


# ===========================================================================
# Physical correctness tests
# ===========================================================================

class TestHybridPhysicalCorrectness:

    def test_snr_decreases_with_distance(
        self, no_optical_result, simple_grid,
    ):
        """Points farther from UGLD should have lower SNR."""
        sensor = UltrasonicSensor(
            sensor_id="UGLD-001",
            trigger_threshold_db=74.0,
            background_noise_db=60.0,
        )
        positions = {"UGLD-001": (0.0, 0.0, 3.0)}

        engine = HybridSurvivabilityEngine(leak_spl_at_1m=100.0)
        result = engine.analyse(
            optical_result=no_optical_result,
            grid=simple_grid,
            ugld_sensors=[sensor],
            sensor_positions=positions,
        )

        # Point (0,0,0) should have higher SNR than (4,4,0)
        pt_near = result.point_results.get(0)
        pt_far = result.point_results.get(24)  # (4,4,0)

        if pt_near.best_acoustic_detail and pt_far.best_acoustic_detail:
            assert pt_near.best_acoustic_detail.snr_db > pt_far.best_acoustic_detail.snr_db

    def test_coordinates_preserved(
        self, full_optical_result, simple_grid,
        ugld_sensor, ugld_sensor_positions,
    ):
        """Grid point coordinates must be preserved in hybrid results."""
        engine = HybridSurvivabilityEngine()
        result = engine.analyse(
            optical_result=full_optical_result,
            grid=simple_grid,
            ugld_sensors=[ugld_sensor],
            sensor_positions=ugld_sensor_positions,
        )
        # Check first point
        pr = result.point_results[0]
        assert pr.x == simple_grid[0].x
        assert pr.y == simple_grid[0].y
        assert pr.z == simple_grid[0].z

    def test_optical_detector_count_preserved(
        self, full_optical_result, simple_grid,
        ugld_sensor, ugld_sensor_positions,
    ):
        """Optical detector count from redundancy_map must be preserved."""
        engine = HybridSurvivabilityEngine()
        result = engine.analyse(
            optical_result=full_optical_result,
            grid=simple_grid,
            ugld_sensors=[ugld_sensor],
            sensor_positions=ugld_sensor_positions,
        )
        for pt_idx, pr in result.point_results.items():
            assert pr.optical_detector_count == full_optical_result.redundancy_map.get(pt_idx, 0)

    def test_counts_sum_to_total(
        self, partial_optical_result, simple_grid,
        ugld_sensor, ugld_sensor_positions,
    ):
        """All 4 classification counts must sum to total_points."""
        engine = HybridSurvivabilityEngine(leak_spl_at_1m=100.0)
        result = engine.analyse(
            optical_result=partial_optical_result,
            grid=simple_grid,
            ugld_sensors=[ugld_sensor],
            sensor_positions=ugld_sensor_positions,
        )
        total = (result.redundant_hybrid_count
                 + result.optical_only_count
                 + result.acoustic_only_count
                 + result.blind_spot_count)
        assert total == result.total_points

    def test_fractions_sum_correctly(
        self, full_optical_result, simple_grid,
        ugld_sensor, ugld_sensor_positions,
    ):
        """Coverage fractions must be consistent with counts."""
        engine = HybridSurvivabilityEngine(leak_spl_at_1m=100.0)
        result = engine.analyse(
            optical_result=full_optical_result,
            grid=simple_grid,
            ugld_sensors=[ugld_sensor],
            sensor_positions=ugld_sensor_positions,
        )
        n = result.total_points
        assert result.hybrid_coverage_fraction == round(result.redundant_hybrid_count / n, 4)
        assert result.blind_spot_fraction == round(result.blind_spot_count / n, 4)


# ===========================================================================
# Engine initialization tests
# ===========================================================================

class TestHybridEngineInit:

    def test_default_parameters(self):
        engine = HybridSurvivabilityEngine()
        assert engine._leak_spl == 100.0
        assert engine._freq_hz == 40_000.0
        assert engine._temp_c == 40.0
        assert engine._rh_pct == 50.0

    def test_custom_parameters(self):
        engine = HybridSurvivabilityEngine(
            leak_spl_at_1m=120.0,
            center_frequency_hz=25_000.0,
            temp_c=25.0,
            relative_humidity_pct=30.0,
        )
        assert engine._leak_spl == 120.0
        assert engine._freq_hz == 25_000.0
        assert engine._temp_c == 25.0
        assert engine._rh_pct == 30.0
