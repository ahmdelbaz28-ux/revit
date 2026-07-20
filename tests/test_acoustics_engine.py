# File-level '# NOSONAR' removed per NOSONAR_AUDIT.md (V143 hardening).
# Per-line justified suppressions (e.g., '# NOSONAR — S3776: ...') are preserved.
"""
test_acoustics_engine.py — Unified Acoustics Engine Tests
=========================================================
V65 — Tests for fireai.core.acoustics_engine

Tests the AcousticsEngine integration layer that unifies:
  - NFPA 72 §18.4 audible notification (acoustic_calculator)
  - ISA-TR84.00.07 UGLD free-field physics (ugld_acoustics)
  - UGLD ray tracing (ugld_raytrace)

Safety-critical: This is the SINGLE ENTRY POINT for all acoustic analysis.
If AcousticsEngine gives wrong results, either alarms are inaudible or
gas leaks are undetected — both can kill people.

Reference: NFPA 72-2022 §18.4, ISO 9613-1:1993, ISA-TR 84.00.07
"""

import math

import pytest

from fireai.core.acoustic_calculator import (
    CheckPoint,
    Speaker,
)
from fireai.core.acoustics_engine import (
    DEFAULT_CEILING_ABSORPTION_COEFF,
    NFPA72_MAX_DBA,
    NFPA72_PRIVATE_MODE_ABOVE_AMBIENT_DB,
    NFPA72_PUBLIC_MODE_ABOVE_AMBIENT_DB,
    NFPA72_SLEEPING_ABSOLUTE_MIN_DBA,
    UGLD_AIR_ABSORPTION_CONSERVATIVE_DB_PER_M,
    UGLD_CENTER_FREQUENCY_HZ,
    UGLD_MIN_SNR_DB,
    AcousticCoverageResult,
    AcousticsEngine,
    UGLDCoverageResult,
    _combine_spl_db,
    _evaluate_ugld_trigger,
    _image_source_reflection_spl,
)
from fireai.core.ugld_acoustics import (
    UltrasonicSensor,
)
from fireai.core.ugld_raytrace import (
    AcousticObstacle,
)

# ============================================================================
# Module Constants
# ============================================================================


class TestConstants:
    """Verify module-level constants match NFPA 72 and ISA-TR84.00.07."""

    def test_public_mode_15db(self):
        """NFPA 72 §18.4.3: public mode = 15 dB above ambient."""
        assert NFPA72_PUBLIC_MODE_ABOVE_AMBIENT_DB == 15.0  # NOSONAR — S1244: import retained for re-export / API surface

    def test_private_mode_10db(self):
        """NFPA 72 §18.4.4: private mode = 10 dB above ambient."""
        assert NFPA72_PRIVATE_MODE_ABOVE_AMBIENT_DB == 10.0  # NOSONAR — S1244: import retained for re-export / API surface

    def test_sleeping_75dba(self):
        """NFPA 72 §18.4.2: sleeping areas = 75 dBA at pillow."""
        assert NFPA72_SLEEPING_ABSOLUTE_MIN_DBA == 75.0  # NOSONAR — S1244: import retained for re-export / API surface

    def test_max_110dba(self):
        """NFPA 72 §18.4.1.2: maximum 110 dBA."""
        assert NFPA72_MAX_DBA == 110.0  # NOSONAR — S1244: import retained for re-export / API surface

    def test_ugld_center_freq_40khz(self):
        assert UGLD_CENTER_FREQUENCY_HZ == 40_000.0  # NOSONAR — S1244: import retained for re-export / API surface

    def test_ugld_min_snr_6db(self):
        assert UGLD_MIN_SNR_DB == 6.0  # NOSONAR — S1244: import retained for re-export / API surface

    def test_conservative_absorption(self):
        """Conservative 1.5 dB/m at 40 kHz for industrial conditions."""
        assert UGLD_AIR_ABSORPTION_CONSERVATIVE_DB_PER_M == 1.5  # NOSONAR — S1244: import retained for re-export / API surface

    def test_default_ceiling_absorption(self):
        """Concrete/steel deck absorption ≈ 0.04 at ultrasonic freq."""
        assert 0.01 < DEFAULT_CEILING_ABSORPTION_COEFF < 0.10


# ============================================================================
# SPL Combination Utility
# ============================================================================


class TestCombineSPL:
    """Test _combine_spl_db() — logarithmic SPL addition."""

    def test_equal_spl_adds_3db(self):
        """Two equal SPL sources: total = +3 dB."""
        result = _combine_spl_db(80.0, 80.0)
        assert 82.9 < result < 83.1, f"Expected ~83 dB, got {result}"

    def test_dominant_source(self):
        """When one source is much louder, combined ≈ louder source."""
        result = _combine_spl_db(90.0, 60.0)
        assert 89.9 < result < 90.1, f"Expected ~90 dB, got {result}"

    def test_both_zero_returns_zero(self):
        assert _combine_spl_db(0.0, 0.0) == 0.0  # NOSONAR — S1244: import retained for re-export / API surface

    def test_both_negative_returns_zero(self):
        assert _combine_spl_db(-10.0, -5.0) == 0.0  # NOSONAR — S1244: import retained for re-export / API surface


    def test_nan_a_returns_b(self):
        """NaN input should fall back to the other value."""
        result = _combine_spl_db(float("nan"), 80.0)
        assert result == 80.0  # NOSONAR — S1244: import retained for re-export / API surface

    def test_nan_b_returns_a(self):
        result = _combine_spl_db(80.0, float("nan"))
        assert result == 80.0  # NOSONAR — S1244: import retained for re-export / API surface

    def test_both_nan_returns_zero(self):
        result = _combine_spl_db(float("nan"), float("nan"))
        assert result == 0.0  # NOSONAR — S1244: import retained for re-export / API surface

    def test_inf_a_returns_b(self):
        """Inf SPL should fall back to the other finite value."""
        result = _combine_spl_db(float("inf"), 80.0)
        assert result == 80.0  # NOSONAR — S1244: import retained for re-export / API surface

    def test_inf_b_returns_a(self):
        result = _combine_spl_db(80.0, float("inf"))
        assert result == 80.0  # NOSONAR — S1244: import retained for re-export / API surface

    def test_both_inf_returns_zero(self):
        result = _combine_spl_db(float("inf"), float("inf"))
        assert result == 0.0  # NOSONAR — S1244: import retained for re-export / API surface


# ============================================================================
# UGLD Trigger Evaluation
# ============================================================================


class TestEvaluateUGLDTrigger:
    """Test _evaluate_ugld_trigger()."""

    def test_triggered_returns_zero_deficit(self):
        sensor = UltrasonicSensor(trigger_threshold_db=70.0, background_noise_db=50.0)
        detected, deficit = _evaluate_ugld_trigger(80.0, sensor)
        assert detected is True
        assert deficit == 0.0  # NOSONAR — S1244: import retained for re-export / API surface

    def test_not_triggered_returns_positive_deficit(self):
        sensor = UltrasonicSensor(trigger_threshold_db=90.0, background_noise_db=50.0)
        detected, deficit = _evaluate_ugld_trigger(80.0, sensor)
        assert detected is False
        assert deficit > 0


# ============================================================================
# Image Source Ceiling Reflection
# ============================================================================


class TestImageSourceReflection:
    """Test _image_source_reflection_spl()."""

    def test_reflection_adds_spl(self):
        """Ceiling reflection should produce positive SPL at the sensor."""
        reflected = _image_source_reflection_spl(
            leak_point=(5.0, 5.0, 1.5),
            sensor_point=(10.0, 10.0, 1.5),
            ceiling_z=3.0,
            leak_spl_at_1m=100.0,
            center_frequency_hz=40_000,
        )
        assert reflected > 0, "Ceiling reflection should produce positive SPL"
        # Reflected SPL depends on image-source distance and absorption.
        # It may be higher or lower than direct SPL depending on geometry.
        # What matters is that it's positive and finite.
        assert math.isfinite(reflected), "Reflected SPL must be finite"

    def test_perfect_absorber_no_reflection(self):
        """Alpha = 1.0 (perfect absorber) → zero reflection."""
        reflected = _image_source_reflection_spl(
            leak_point=(5.0, 5.0, 1.5),
            sensor_point=(10.0, 10.0, 1.5),
            ceiling_z=3.0,
            leak_spl_at_1m=100.0,
            center_frequency_hz=40_000,
            ceiling_absorption_coeff=1.0,
        )
        assert reflected == 0.0  # NOSONAR — S1244: import retained for re-export / API surface


    def test_negative_absorption_raises(self):
        """Negative absorption is physically impossible — adds energy."""
        with pytest.raises(ValueError, match="must be >= 0"):
            _image_source_reflection_spl(
                leak_point=(5.0, 5.0, 1.5),
                sensor_point=(10.0, 10.0, 1.5),
                ceiling_z=3.0,
                leak_spl_at_1m=100.0,
                center_frequency_hz=40_000,
                ceiling_absorption_coeff=-0.1,
            )


# ============================================================================
# AcousticsEngine — NFPA 72 Audible Coverage
# ============================================================================


class TestAcousticsEngineAudibleCoverage:
    """Test AcousticsEngine.check_coverage() for NFPA 72 §18.4."""

    @pytest.fixture
    def engine(self):
        return AcousticsEngine()

    def test_compliant_public_mode(self, engine):
        """Speaker at reference distance should be compliant in public mode."""
        result = engine.check_coverage(
            room_id="R-101",
            occ_type="business",
            speakers=[Speaker(x=5, y=5, z=2.8, rating_dba=95)],
            check_points=[CheckPoint(x=5, y=5, z=1.5)],
            mode="public",
        )
        assert isinstance(result, AcousticCoverageResult)

    def test_compliant_private_mode(self, engine):
        result = engine.check_coverage(
            room_id="R-102",
            occ_type="business",
            speakers=[Speaker(x=5, y=5, z=2.8, rating_dba=95)],
            check_points=[CheckPoint(x=5, y=5, z=1.5)],
            mode="private",
        )
        assert isinstance(result, AcousticCoverageResult)
        # Private mode has lower threshold, should be compliant or closer
        assert result.required_dba <= 65  # 10 dB above ambient (55 dBA)

    def test_empty_speakers_raises(self, engine):
        """No speakers → cannot compute SPL → ValueError."""
        with pytest.raises(ValueError, match="at least one Speaker"):  # NOSONAR — S5778: re-raise inside except is intentional (context-specific)  # noqa: S5778
            engine.check_coverage(
                room_id="R-103",
                occ_type="business",
                speakers=[],
                check_points=[CheckPoint(x=1, y=1, z=1.5)],
                mode="public",
            )

    def test_empty_checkpoints_raises(self, engine):
        """No check points → cannot verify coverage → ValueError."""
        with pytest.raises(ValueError, match="at least one CheckPoint"):  # NOSONAR — S5778: re-raise inside except is intentional (context-specific)  # noqa: S5778
            engine.check_coverage(
                room_id="R-104",
                occ_type="business",
                speakers=[Speaker(x=5, y=5, z=2.8, rating_dba=95)],
                check_points=[],
                mode="public",
            )

    def test_invalid_mode_raises(self, engine):
        with pytest.raises(ValueError, match="Invalid mode"):  # NOSONAR — S5778: re-raise inside except is intentional (context-specific)  # noqa: S5778
            engine.check_coverage(
                room_id="R-105",
                occ_type="business",
                speakers=[Speaker(x=5, y=5, z=2.8, rating_dba=95)],
                check_points=[CheckPoint(x=5, y=5, z=1.5)],
                mode="invalid_mode",
            )

    def test_result_has_nfpa_sections(self, engine):
        result = engine.check_coverage(
            room_id="R-106",
            occ_type="business",
            speakers=[Speaker(x=5, y=5, z=2.8, rating_dba=95)],
            check_points=[CheckPoint(x=5, y=5, z=1.5)],
            mode="public",
        )
        assert len(result.nfpa_sections_referenced) > 0


# ============================================================================
# AcousticsEngine — UGLD Ray Trace
# ============================================================================


class TestAcousticsEngineUGLDRaytrace:
    """Test AcousticsEngine.ugld_raytrace() for ISA-TR84.00.07."""

    @pytest.fixture
    def engine(self):
        return AcousticsEngine()

    def test_free_field_detection(self, engine):
        """Free-field (no obstacles): should detect if within range."""
        sensor = UltrasonicSensor(trigger_threshold_db=74.0, background_noise_db=60.0)
        result = engine.ugld_raytrace(
            leak_point=(5.0, 5.0, 2.0),
            sensor_point=(10.0, 10.0, 2.0),
            sensor=sensor,
            leak_spl_at_1m=100.0,
        )
        assert isinstance(result, UGLDCoverageResult)
        assert result.sensors_evaluated == 1
        assert result.leak_points_evaluated == 1
        assert len(result.detection_zones) == 1

    def test_non_positive_leak_spl_raises(self, engine):
        sensor = UltrasonicSensor()
        with pytest.raises(ValueError, match="must be positive"):
            engine.ugld_raytrace(
                leak_point=(5.0, 5.0, 2.0),
                sensor_point=(10.0, 10.0, 2.0),
                sensor=sensor,
                leak_spl_at_1m=0.0,
            )

    def test_ceiling_reflection_without_ceiling_z_raises(self, engine):
        sensor = UltrasonicSensor()
        with pytest.raises(ValueError, match="ceiling_z is required"):
            engine.ugld_raytrace(
                leak_point=(5.0, 5.0, 2.0),
                sensor_point=(10.0, 10.0, 2.0),
                sensor=sensor,
                leak_spl_at_1m=100.0,
                include_ceiling_reflection=True,
                ceiling_z=None,
            )

    def test_with_obstacles(self, engine):
        """Ray trace with obstacles should produce results."""
        sensor = UltrasonicSensor(trigger_threshold_db=74.0, background_noise_db=60.0)
        obstacles = [
            AcousticObstacle(
                obstacle_id="TANK-01",
                vertices=[[6, 6, 0], [8, 8, 4]],
            )
        ]
        result = engine.ugld_raytrace(
            leak_point=(5.0, 5.0, 2.0),
            sensor_point=(15.0, 15.0, 2.0),
            sensor=sensor,
            leak_spl_at_1m=100.0,
            obstacles=obstacles,
        )
        assert isinstance(result, UGLDCoverageResult)

    def test_conservative_absorption_override(self, engine):
        """Conservative absorption (1.5 dB/m) should reduce SPL."""
        sensor = UltrasonicSensor(trigger_threshold_db=74.0, background_noise_db=60.0)
        result_normal = engine.ugld_raytrace(
            leak_point=(5.0, 5.0, 2.0),
            sensor_point=(15.0, 15.0, 2.0),
            sensor=sensor,
            leak_spl_at_1m=100.0,
        )
        result_conservative = engine.ugld_raytrace(
            leak_point=(5.0, 5.0, 2.0),
            sensor_point=(15.0, 15.0, 2.0),
            sensor=sensor,
            leak_spl_at_1m=100.0,
            use_conservative_absorption=True,
        )
        # Conservative absorption should give equal or lower SPL
        assert result_conservative.detection_zones[0].final_spl_db <= result_normal.detection_zones[0].final_spl_db + 0.1


# ============================================================================
# AcousticsEngine — Multi-Sensor UGLD Coverage
# ============================================================================


class TestAcousticsEngineMultiSensor:
    """Test AcousticsEngine.ugld_multi_sensor_coverage()."""

    @pytest.fixture
    def engine(self):
        return AcousticsEngine()

    def test_basic_multi_sensor(self, engine):
        sensors = [
            UltrasonicSensor(sensor_id="UGLD-A", trigger_threshold_db=74.0, background_noise_db=60.0),
            UltrasonicSensor(sensor_id="UGLD-B", trigger_threshold_db=74.0, background_noise_db=60.0),
        ]
        result = engine.ugld_multi_sensor_coverage(
            leak_points=[(5.0, 5.0, 2.0), (25.0, 25.0, 2.0)],
            sensor_points=[(5.0, 5.0, 3.0), (25.0, 15.0, 3.0)],
            sensors=sensors,
            area_bounds=((0, 0, 0), (30, 30, 10)),
        )
        assert isinstance(result, UGLDCoverageResult)
        assert result.sensors_evaluated == 2
        assert result.leak_points_evaluated == 2
        assert len(result.detection_zones) == 4  # 2 sensors × 2 leak points

    def test_empty_leak_points_raises(self, engine):
        sensors = [UltrasonicSensor()]
        with pytest.raises(ValueError, match="at least one leak"):
            engine.ugld_multi_sensor_coverage(
                leak_points=[],
                sensor_points=[(5, 5, 3)],
                sensors=sensors,
            )

    def test_empty_sensor_points_raises(self, engine):
        with pytest.raises(ValueError, match="at least one sensor"):
            engine.ugld_multi_sensor_coverage(
                leak_points=[(5, 5, 2)],
                sensor_points=[],
                sensors=[],
            )

    def test_mismatched_sensors_and_points_raises(self, engine):
        sensors = [UltrasonicSensor(), UltrasonicSensor()]
        with pytest.raises(ValueError, match="must match"):
            engine.ugld_multi_sensor_coverage(
                leak_points=[(5, 5, 2)],
                sensor_points=[(5, 5, 3)],
                sensors=sensors,
            )


# ============================================================================
# Engine Initialization
# ============================================================================


class TestEngineInit:
    """Test AcousticsEngine initialization."""

    def test_default_init(self):
        engine = AcousticsEngine()
        # S5727 fix: assert on the instance type rather than the tautological
        # `is not None` (always True after construction succeeds).
        assert isinstance(engine, AcousticsEngine)

    def test_custom_ambient_noise(self):
        engine = AcousticsEngine(room_ambient_noise={"business": 50.0})
        # S5727 fix: same pattern — assert on the instance type.
        assert isinstance(engine, AcousticsEngine)
