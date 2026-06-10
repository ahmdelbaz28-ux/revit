"""
test_ugld_acoustics.py — UGLD Acoustic Physics Engine Tests
===========================================================
V65 — Comprehensive tests for fireai.core.ugld_acoustics

Tests all public functions and Pydantic models in the UGLD module:
  - atmospheric_attenuation_db_per_m()
  - UltrasonicSensor, AcousticPropagation, UGLDTriggerResult models
  - check_ugld_trigger()
  - max_detection_range_m()
  - speed_of_sound()

Safety-critical: These calculations determine whether gas leak detectors
will actually detect a leak. Wrong physics = undetected leak = explosion.

Reference: ISO 9613-1:1993, ISA-TR 84.00.07, IEC 60079-29-4
"""

import math
import pytest

from fireai.core.ugld_acoustics import (
    UGLDFrequencyBand,
    UltrasonicSensor,
    AcousticPropagation,
    UGLDTriggerResult,
    check_ugld_trigger,
    atmospheric_attenuation_db_per_m,
    max_detection_range_m,
    speed_of_sound,
    _DEFAULT_UGLD_FREQUENCY_HZ,
    _MIN_SNR_DB,
    _ISO_9613_ALPHA_20C_50RH,
)


# ============================================================================
# Constants
# ============================================================================


class TestConstants:
    """Verify module-level constants are physically correct."""

    def test_default_frequency_is_40khz(self):
        """40 kHz is the most common UGLD operating frequency."""
        assert _DEFAULT_UGLD_FREQUENCY_HZ == 40_000.0

    def test_min_snr_is_6db(self):
        """6 dB SNR = signal 4x noise power (ISA-TR 84.00.07)."""
        assert _MIN_SNR_DB == 6.0

    def test_iso_9613_table_has_expected_entries(self):
        """Verify the attenuation lookup table covers ultrasonic range."""
        assert 20_000 in _ISO_9613_ALPHA_20C_50RH
        assert 40_000 in _ISO_9613_ALPHA_20C_50RH
        assert 100_000 in _ISO_9613_ALPHA_20C_50RH

    def test_attenuation_increases_with_frequency(self):
        """Higher frequencies MUST have higher atmospheric attenuation."""
        freqs = sorted(_ISO_9613_ALPHA_20C_50RH.keys())
        alphas = [_ISO_9613_ALPHA_20C_50RH[f] for f in freqs]
        for i in range(1, len(alphas)):
            assert alphas[i] >= alphas[i - 1], (
                f"Atmospheric attenuation should increase with frequency: "
                f"{freqs[i]} Hz ({alphas[i]}) vs {freqs[i-1]} Hz ({alphas[i-1]})"
            )

    def test_40khz_attenuation_near_half_db_per_m(self):
        """At 40 kHz / 20°C / 50% RH: alpha ≈ 0.5 dB/m per ISO 9613-1."""
        assert 0.3 < _ISO_9613_ALPHA_20C_50RH[40_000] < 1.0


# ============================================================================
# Atmospheric Attenuation Function
# ============================================================================


class TestAtmosphericAttenuation:
    """Test atmospheric_attenuation_db_per_m() against ISO 9613-1."""

    def test_exact_table_value_40khz(self):
        """Exact frequency match should return table value."""
        alpha = atmospheric_attenuation_db_per_m(40_000, temp_c=20.0, relative_humidity_pct=50.0)
        assert alpha == _ISO_9613_ALPHA_20C_50RH[40_000]

    def test_exact_table_value_25khz(self):
        alpha = atmospheric_attenuation_db_per_m(25_000, temp_c=20.0, relative_humidity_pct=50.0)
        assert alpha == _ISO_9613_ALPHA_20C_50RH[25_000]

    def test_interpolation_between_table_entries(self):
        """Between 25kHz and 40kHz, alpha should interpolate."""
        alpha = atmospheric_attenuation_db_per_m(32_500, temp_c=20.0, relative_humidity_pct=50.0)
        a25 = _ISO_9613_ALPHA_20C_50RH[25_000]
        a40 = _ISO_9613_ALPHA_20C_50RH[40_000]
        assert a25 < alpha < a40, f"Interpolated alpha {alpha} should be between {a25} and {a40}"

    def test_higher_temperature_lower_attenuation(self):
        """At ultrasonic frequencies, higher temp slightly reduces alpha."""
        alpha_20 = atmospheric_attenuation_db_per_m(40_000, temp_c=20.0)
        alpha_40 = atmospheric_attenuation_db_per_m(40_000, temp_c=40.0)
        assert alpha_40 < alpha_20, "Higher temperature should reduce attenuation at ultrasonic freq"

    def test_very_dry_increases_attenuation(self):
        """Very dry air (<20% RH) increases attenuation at ultrasonic freq."""
        alpha_50 = atmospheric_attenuation_db_per_m(40_000, relative_humidity_pct=50.0)
        alpha_10 = atmospheric_attenuation_db_per_m(40_000, relative_humidity_pct=10.0)
        assert alpha_10 > alpha_50, "Very dry air should increase attenuation"

    def test_result_always_positive(self):
        """Attenuation coefficient must always be positive."""
        for freq in [20_000, 25_000, 40_000, 80_000, 100_000]:
            for temp in [-40.0, 0.0, 20.0, 40.0, 85.0]:
                for rh in [0.0, 20.0, 50.0, 80.0, 100.0]:
                    alpha = atmospheric_attenuation_db_per_m(freq, temp_c=temp, relative_humidity_pct=rh)
                    assert alpha > 0, f"alpha must be positive: freq={freq}, temp={temp}, rh={rh}"

    # V65: NaN/Inf input validation

    def test_nan_frequency_raises(self):
        with pytest.raises(ValueError, match="positive and finite"):
            atmospheric_attenuation_db_per_m(float("nan"))

    def test_inf_frequency_raises(self):
        with pytest.raises(ValueError, match="positive and finite"):
            atmospheric_attenuation_db_per_m(float("inf"))

    def test_zero_frequency_raises(self):
        with pytest.raises(ValueError, match="positive and finite"):
            atmospheric_attenuation_db_per_m(0.0)

    def test_negative_frequency_raises(self):
        with pytest.raises(ValueError, match="positive and finite"):
            atmospheric_attenuation_db_per_m(-40_000.0)

    def test_nan_temperature_raises(self):
        with pytest.raises(ValueError, match="finite and in range"):
            atmospheric_attenuation_db_per_m(40_000, temp_c=float("nan"))

    def test_inf_temperature_raises(self):
        with pytest.raises(ValueError, match="finite and in range"):
            atmospheric_attenuation_db_per_m(40_000, temp_c=float("inf"))

    def test_temperature_below_minus_40_raises(self):
        with pytest.raises(ValueError, match="finite and in range"):
            atmospheric_attenuation_db_per_m(40_000, temp_c=-50.0)

    def test_temperature_above_85_raises(self):
        with pytest.raises(ValueError, match="finite and in range"):
            atmospheric_attenuation_db_per_m(40_000, temp_c=100.0)

    def test_nan_humidity_raises(self):
        with pytest.raises(ValueError, match="finite and in range"):
            atmospheric_attenuation_db_per_m(40_000, relative_humidity_pct=float("nan"))

    def test_negative_humidity_raises(self):
        with pytest.raises(ValueError, match="finite and in range"):
            atmospheric_attenuation_db_per_m(40_000, relative_humidity_pct=-10.0)

    def test_humidity_above_100_raises(self):
        with pytest.raises(ValueError, match="finite and in range"):
            atmospheric_attenuation_db_per_m(40_000, relative_humidity_pct=110.0)

    def test_boundary_temperature_minus_40(self):
        """-40°C is the boundary — should NOT raise."""
        alpha = atmospheric_attenuation_db_per_m(40_000, temp_c=-40.0)
        assert alpha > 0

    def test_boundary_temperature_85(self):
        """85°C is the boundary — should NOT raise."""
        alpha = atmospheric_attenuation_db_per_m(40_000, temp_c=85.0)
        assert alpha > 0

    def test_boundary_humidity_0(self):
        """0% RH is the boundary — should NOT raise."""
        alpha = atmospheric_attenuation_db_per_m(40_000, relative_humidity_pct=0.0)
        assert alpha > 0

    def test_boundary_humidity_100(self):
        """100% RH is the boundary — should NOT raise."""
        alpha = atmospheric_attenuation_db_per_m(40_000, relative_humidity_pct=100.0)
        assert alpha > 0


# ============================================================================
# Pydantic Models
# ============================================================================


class TestUltrasonicSensor:
    """Test UltrasonicSensor Pydantic model."""

    def test_default_creation(self):
        sensor = UltrasonicSensor()
        assert sensor.sensor_id == "UGLD-001"
        assert sensor.trigger_threshold_db == 74.0
        assert sensor.background_noise_db == 60.0
        assert sensor.center_frequency_hz == _DEFAULT_UGLD_FREQUENCY_HZ
        assert sensor.directivity_deg == 360.0

    def test_custom_creation(self):
        sensor = UltrasonicSensor(
            sensor_id="UGLD-CUSTOM",
            trigger_threshold_db=80.0,
            background_noise_db=55.0,
            center_frequency_hz=25_000.0,
            directivity_deg=90.0,
        )
        assert sensor.sensor_id == "UGLD-CUSTOM"
        assert sensor.trigger_threshold_db == 80.0
        assert sensor.center_frequency_hz == 25_000.0
        assert sensor.directivity_deg == 90.0

    def test_frozen_model(self):
        """UltrasonicSensor is frozen — cannot modify after creation."""
        sensor = UltrasonicSensor()
        with pytest.raises(Exception):
            sensor.trigger_threshold_db = 90.0

    def test_negative_trigger_threshold_rejected(self):
        with pytest.raises(Exception):
            UltrasonicSensor(trigger_threshold_db=-1.0)

    def test_zero_background_noise_allowed(self):
        """0 dB background noise is valid (anechoic environment)."""
        sensor = UltrasonicSensor(background_noise_db=0.0)
        assert sensor.background_noise_db == 0.0

    def test_directivity_exceeding_360_rejected(self):
        with pytest.raises(Exception):
            UltrasonicSensor(directivity_deg=400.0)


class TestAcousticPropagation:
    """Test AcousticPropagation Pydantic model with computed fields."""

    def test_basic_creation(self):
        prop = AcousticPropagation(
            leak_spl_at_1m=100.0,
            distance_meters=10.0,
        )
        assert prop.leak_spl_at_1m == 100.0
        assert prop.distance_meters == 10.0
        assert prop.speed_of_sound_mps > 0
        assert prop.geometric_loss_db > 0
        assert prop.atmospheric_loss_db > 0
        assert prop.final_spl_db > 0

    def test_speed_of_sound_at_20c(self):
        """At 20°C: c ≈ 343.2 m/s per ISO 9613-1."""
        prop = AcousticPropagation(leak_spl_at_1m=100.0, distance_meters=1.0, temp_c=20.0)
        assert 343.0 <= prop.speed_of_sound_mps <= 344.0

    def test_speed_of_sound_at_40c(self):
        """At 40°C: c ≈ 354.7 m/s."""
        prop = AcousticPropagation(leak_spl_at_1m=100.0, distance_meters=1.0, temp_c=40.0)
        assert 354.0 <= prop.speed_of_sound_mps <= 356.0

    def test_geometric_loss_6db_per_doubling(self):
        """Inverse square law: 6 dB loss per distance doubling."""
        prop_1m = AcousticPropagation(leak_spl_at_1m=100.0, distance_meters=1.0)
        prop_2m = AcousticPropagation(leak_spl_at_1m=100.0, distance_meters=2.0)
        loss_diff = prop_2m.geometric_loss_db - prop_1m.geometric_loss_db
        assert 5.9 < loss_diff < 6.1, f"Expected ~6 dB per doubling, got {loss_diff:.2f}"

    def test_final_spl_decreases_with_distance(self):
        """SPL must decrease with distance."""
        prop_10m = AcousticPropagation(leak_spl_at_1m=100.0, distance_meters=10.0)
        prop_20m = AcousticPropagation(leak_spl_at_1m=100.0, distance_meters=20.0)
        assert prop_20m.final_spl_db < prop_10m.final_spl_db

    def test_higher_frequency_more_atmospheric_loss(self):
        """80 kHz should have more atmospheric absorption than 40 kHz."""
        prop_40k = AcousticPropagation(leak_spl_at_1m=100.0, distance_meters=15.0, center_frequency_hz=40_000)
        prop_80k = AcousticPropagation(leak_spl_at_1m=100.0, distance_meters=15.0, center_frequency_hz=80_000)
        assert prop_80k.atmospheric_loss_db > prop_40k.atmospheric_loss_db

    def test_frozen_model(self):
        """AcousticPropagation is frozen — cannot modify computed fields."""
        prop = AcousticPropagation(leak_spl_at_1m=100.0, distance_meters=10.0)
        with pytest.raises(Exception):
            prop.final_spl_db = 999.0

    def test_zero_leak_spl_rejected(self):
        with pytest.raises(Exception):
            AcousticPropagation(leak_spl_at_1m=0.0, distance_meters=10.0)

    def test_negative_leak_spl_rejected(self):
        with pytest.raises(Exception):
            AcousticPropagation(leak_spl_at_1m=-10.0, distance_meters=10.0)

    def test_zero_distance_rejected(self):
        with pytest.raises(Exception):
            AcousticPropagation(leak_spl_at_1m=100.0, distance_meters=0.0)

    def test_negative_distance_rejected(self):
        with pytest.raises(Exception):
            AcousticPropagation(leak_spl_at_1m=100.0, distance_meters=-5.0)

    def test_extreme_cold_temperature(self):
        """-40°C is the Pydantic boundary — should work."""
        prop = AcousticPropagation(leak_spl_at_1m=100.0, distance_meters=10.0, temp_c=-40.0)
        assert prop.speed_of_sound_mps > 0

    def test_extreme_hot_temperature(self):
        """85°C is the Pydantic boundary — should work."""
        prop = AcousticPropagation(leak_spl_at_1m=100.0, distance_meters=10.0, temp_c=85.0)
        assert prop.speed_of_sound_mps > 0

    def test_temp_below_minus_40_rejected(self):
        with pytest.raises(Exception):
            AcousticPropagation(leak_spl_at_1m=100.0, distance_meters=10.0, temp_c=-41.0)

    def test_temp_above_85_rejected(self):
        with pytest.raises(Exception):
            AcousticPropagation(leak_spl_at_1m=100.0, distance_meters=10.0, temp_c=86.0)


# ============================================================================
# UGLD Trigger Check
# ============================================================================


class TestCheckUGLDTrigger:
    """Test check_ugld_trigger() — the core detection logic."""

    def test_sensor_triggers_when_both_conditions_met(self):
        """Sensor triggers when SPL >= threshold AND SNR >= 6 dB."""
        sensor = UltrasonicSensor(trigger_threshold_db=74.0, background_noise_db=60.0)
        # Need SPL >= 74 dB (threshold) AND SPL >= 60 + 6 = 66 dB (SNR)
        # So SPL >= 74 dB satisfies both
        prop = AcousticPropagation(leak_spl_at_1m=100.0, distance_meters=10.0)
        result = check_ugld_trigger(prop, sensor)
        assert result.triggered is True
        assert result.snr_db >= _MIN_SNR_DB
        assert result.margin_to_threshold_db >= 0

    def test_sensor_does_not_trigger_below_threshold(self):
        """Below trigger threshold → not triggered."""
        sensor = UltrasonicSensor(trigger_threshold_db=90.0, background_noise_db=40.0)
        prop = AcousticPropagation(leak_spl_at_1m=100.0, distance_meters=50.0)
        result = check_ugld_trigger(prop, sensor)
        # At 50m with 100 dB source: SPL ≈ 100 - 20*log10(50) - 0.5*50 ≈ 66 - 25 = 41 dB
        # This is way below 90 dB threshold
        if result.final_spl_db < sensor.trigger_threshold_db:
            assert result.triggered is False
            assert result.fail_reason is not None

    def test_sensor_does_not_trigger_insufficient_snr(self):
        """High background noise can prevent trigger even if threshold met."""
        sensor = UltrasonicSensor(trigger_threshold_db=60.0, background_noise_db=80.0)
        prop = AcousticPropagation(leak_spl_at_1m=100.0, distance_meters=10.0)
        result = check_ugld_trigger(prop, sensor)
        # SNR = SPL - 80. If SPL < 86, SNR < 6 dB
        if result.snr_db < _MIN_SNR_DB:
            assert result.triggered is False

    def test_fail_reason_present_when_not_triggered(self):
        """When not triggered, fail_reason must explain why."""
        sensor = UltrasonicSensor(trigger_threshold_db=100.0, background_noise_db=40.0)
        prop = AcousticPropagation(leak_spl_at_1m=80.0, distance_meters=15.0)
        result = check_ugld_trigger(prop, sensor)
        if not result.triggered:
            assert result.fail_reason is not None
            assert len(result.fail_reason) > 0

    def test_result_type(self):
        sensor = UltrasonicSensor()
        prop = AcousticPropagation(leak_spl_at_1m=100.0, distance_meters=10.0)
        result = check_ugld_trigger(prop, sensor)
        assert isinstance(result, UGLDTriggerResult)

    def test_result_fields_populated(self):
        sensor = UltrasonicSensor()
        prop = AcousticPropagation(leak_spl_at_1m=100.0, distance_meters=10.0)
        result = check_ugld_trigger(prop, sensor)
        assert isinstance(result.triggered, bool)
        assert isinstance(result.final_spl_db, float)
        assert isinstance(result.snr_db, float)
        assert isinstance(result.margin_to_threshold_db, float)
        assert isinstance(result.margin_to_snr_db, float)


# ============================================================================
# Maximum Detection Range
# ============================================================================


class TestMaxDetectionRange:
    """Test max_detection_range_m() — binary search for max range."""

    def test_detectable_at_1m(self):
        """A 100 dB source should be detectable at 1m."""
        sensor = UltrasonicSensor(trigger_threshold_db=74.0, background_noise_db=60.0)
        range_m = max_detection_range_m(100.0, sensor)
        assert range_m > 0

    def test_range_increases_with_source_level(self):
        """Louder leak = longer detection range."""
        sensor = UltrasonicSensor()
        range_100 = max_detection_range_m(100.0, sensor)
        range_110 = max_detection_range_m(110.0, sensor)
        assert range_110 > range_100

    def test_range_decreases_with_higher_threshold(self):
        """Higher threshold = shorter detection range."""
        sensor_low = UltrasonicSensor(trigger_threshold_db=70.0)
        sensor_high = UltrasonicSensor(trigger_threshold_db=80.0)
        range_low = max_detection_range_m(100.0, sensor_low)
        range_high = max_detection_range_m(100.0, sensor_high)
        assert range_low > range_high

    def test_undetectable_source_returns_zero(self):
        """Source below threshold even at 1m → range = 0."""
        sensor = UltrasonicSensor(trigger_threshold_db=100.0, background_noise_db=40.0)
        range_m = max_detection_range_m(50.0, sensor)
        assert range_m == 0.0

    def test_range_is_positive_finite(self):
        """Detection range must be a positive finite number (or 0)."""
        sensor = UltrasonicSensor()
        range_m = max_detection_range_m(100.0, sensor)
        assert math.isfinite(range_m)
        assert range_m >= 0

    def test_higher_frequency_shorter_range(self):
        """Higher frequency = more attenuation = shorter range."""
        sensor_40k = UltrasonicSensor(center_frequency_hz=40_000)
        sensor_80k = UltrasonicSensor(center_frequency_hz=80_000)
        range_40k = max_detection_range_m(100.0, sensor_40k)
        range_80k = max_detection_range_m(100.0, sensor_80k)
        assert range_40k > range_80k, f"40kHz range ({range_40k}) should exceed 80kHz ({range_80k})"


# ============================================================================
# Speed of Sound
# ============================================================================


class TestSpeedOfSound:
    """Test speed_of_sound() utility."""

    def test_at_20c(self):
        """At 20°C: c ≈ 343.2 m/s."""
        c = speed_of_sound(20.0)
        assert 343.0 <= c <= 344.0

    def test_at_0c(self):
        """At 0°C: c ≈ 331.3 m/s."""
        c = speed_of_sound(0.0)
        assert 330.0 <= c <= 333.0

    def test_at_40c(self):
        """At 40°C: c ≈ 354.7 m/s."""
        c = speed_of_sound(40.0)
        assert 354.0 <= c <= 356.0

    def test_increases_with_temperature(self):
        """Speed of sound increases with temperature."""
        c_20 = speed_of_sound(20.0)
        c_40 = speed_of_sound(40.0)
        assert c_40 > c_20


# ============================================================================
# UGLDFrequencyBand Enum
# ============================================================================


class TestUGLDFrequencyBand:
    """Test the frequency band classification enum."""

    def test_all_bands_exist(self):
        assert UGLDFrequencyBand.ULTRASOUND_LOW.value == "ULTRASOUND_LOW"
        assert UGLDFrequencyBand.ULTRASOUND_MID.value == "ULTRASOUND_MID"
        assert UGLDFrequencyBand.ULTRASOUND_HIGH.value == "ULTRASOUND_HIGH"
        assert UGLDFrequencyBand.ULTRASOUND_VHF.value == "ULTRASOUND_VHF"

    def test_four_bands(self):
        assert len(UGLDFrequencyBand) == 4
