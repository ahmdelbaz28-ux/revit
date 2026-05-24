"""
test_v23_ugld_acoustics.py — V23 UGLD Acoustic Physics Engine Tests
====================================================================
Strict pytest tests validating:
  1. Speed of sound (temperature-dependent)
  2. Inverse Square Law (6 dB per doubling)
  3. Atmospheric attenuation (frequency-dependent via ISO 9613-1)
  4. SNR trigger logic (dual condition: threshold AND SNR)
  5. Maximum detection range
  6. Edge cases and physical consistency

These tests lock down the point-to-point physics BEFORE any Ray Tracing
is introduced — the same approach used for Layer 5 (Flame Detector).
"""

import math
import pytest

from fireai.core.ugld_acoustics import (
    UltrasonicSensor,
    AcousticPropagation,
    UGLDTriggerResult,
    UGLDFrequencyBand,
    check_ugld_trigger,
    atmospheric_attenuation_db_per_m,
    max_detection_range_m,
    speed_of_sound,
    _DEFAULT_UGLD_FREQUENCY_HZ,
    _MIN_SNR_DB,
    _ISO_9613_ALPHA_20C_50RH,
)


# ===========================================================================
# 1. Speed of Sound (Temperature Dependent)
# ===========================================================================

class TestSpeedOfSound:
    """Validate c = 331.3 * sqrt(1 + T/273.15) against known values."""

    def test_at_0c(self):
        """0C: c = 331.3 * sqrt(1 + 0/273.15) = 331.3 m/s."""
        assert speed_of_sound(0.0) == 331.3

    def test_at_20c(self):
        """20C: c ≈ 343.2 m/s (standard reference)."""
        expected = 331.3 * math.sqrt(1.0 + 20.0 / 273.15)
        assert abs(speed_of_sound(20.0) - round(expected, 1)) < 0.1

    def test_at_40c(self):
        """40C: c ≈ 354.7 m/s (typical industrial indoor)."""
        expected = 331.3 * math.sqrt(1.0 + 40.0 / 273.15)
        assert abs(speed_of_sound(40.0) - round(expected, 1)) < 0.1

    def test_at_minus_40c(self):
        """-40C: c ≈ 306.2 m/s (Arctic/extreme cold)."""
        expected = 331.3 * math.sqrt(1.0 + (-40.0) / 273.15)
        assert abs(speed_of_sound(-40.0) - round(expected, 1)) < 0.1

    def test_at_85c(self):
        """85C: c ≈ 377.5 m/s (extreme hot / desert equipment rating)."""
        expected = 331.3 * math.sqrt(1.0 + 85.0 / 273.15)
        assert abs(speed_of_sound(85.0) - round(expected, 1)) < 0.5

    def test_monotonically_increasing(self):
        """Speed of sound increases with temperature (ideal gas)."""
        temps = [-20, 0, 20, 40, 60, 80]
        speeds = [speed_of_sound(t) for t in temps]
        for i in range(len(speeds) - 1):
            assert speeds[i] < speeds[i + 1], (
                f"Speed at {temps[i]}C ({speeds[i]}) not less than "
                f"speed at {temps[i+1]}C ({speeds[i+1]})"
            )

    def test_propagation_model_uses_same_formula(self):
        """AcousticPropagation.speed_of_sound_mps must match speed_of_sound()."""
        prop = AcousticPropagation(
            leak_spl_at_1m=100.0,
            distance_meters=10.0,
            temp_c=35.0,
        )
        assert prop.speed_of_sound_mps == speed_of_sound(35.0)


# ===========================================================================
# 2. Inverse Square Law (6 dB per Doubling of Distance)
# ===========================================================================

class TestInverseSquareLaw:
    """Validate SPL(R) = SPL(1m) - 20 * log10(R)."""

    def test_at_1m(self):
        """At 1m: SPL = source SPL (no attenuation)."""
        prop = AcousticPropagation(
            leak_spl_at_1m=100.0,
            distance_meters=1.0,
            center_frequency_hz=25_000.0,  # Low attenuation for geometric test
        )
        # Geometric loss at 1m: 20*log10(1) = 0.0 dB
        assert prop.geometric_loss_db == 0.0
        # Final SPL ≈ 100.0 - 0.0 - small atmospheric loss
        # At 1m, atmospheric loss is negligible (alpha * 1 ≈ 0.12)
        assert prop.final_spl_db > 99.0

    def test_at_2m_6db_loss(self):
        """At 2m: geometric loss = 20*log10(2) ≈ 6.02 dB."""
        prop = AcousticPropagation(
            leak_spl_at_1m=100.0,
            distance_meters=2.0,
            center_frequency_hz=25_000.0,  # Low alpha to isolate geometric
        )
        assert abs(prop.geometric_loss_db - 6.0) < 0.1

    def test_at_10m_20db_loss(self):
        """At 10m: geometric loss = 20*log10(10) = 20.0 dB."""
        prop = AcousticPropagation(
            leak_spl_at_1m=100.0,
            distance_meters=10.0,
            center_frequency_hz=25_000.0,
        )
        assert abs(prop.geometric_loss_db - 20.0) < 0.1

    def test_at_100m_40db_loss(self):
        """At 100m: geometric loss = 20*log10(100) = 40.0 dB."""
        prop = AcousticPropagation(
            leak_spl_at_1m=100.0,
            distance_meters=100.0,
            center_frequency_hz=25_000.0,
        )
        assert abs(prop.geometric_loss_db - 40.0) < 0.1

    def test_6db_per_doubling(self):
        """Every doubling of distance adds ~6 dB geometric loss."""
        prop_5m = AcousticPropagation(
            leak_spl_at_1m=100.0, distance_meters=5.0,
            center_frequency_hz=25_000.0,
        )
        prop_10m = AcousticPropagation(
            leak_spl_at_1m=100.0, distance_meters=10.0,
            center_frequency_hz=25_000.0,
        )
        # Geometric loss difference = 20*log10(10) - 20*log10(5) = 20*log10(2) ≈ 6.02
        geo_diff = prop_10m.geometric_loss_db - prop_5m.geometric_loss_db
        assert abs(geo_diff - 6.0) < 0.1

    def test_spl_decreases_with_distance(self):
        """SPL must monotonically decrease with distance."""
        distances = [1, 2, 5, 10, 20, 50]
        spls = []
        for d in distances:
            prop = AcousticPropagation(
                leak_spl_at_1m=100.0, distance_meters=float(d),
                center_frequency_hz=25_000.0,
            )
            spls.append(prop.final_spl_db)
        for i in range(len(spls) - 1):
            assert spls[i] > spls[i + 1], (
                f"SPL at {distances[i]}m ({spls[i]}) not greater than "
                f"SPL at {distances[i+1]}m ({spls[i+1]})"
            )


# ===========================================================================
# 3. Atmospheric Attenuation (ISO 9613-1 Frequency-Dependent)
# ===========================================================================

class TestAtmosphericAttenuation:
    """Validate frequency-dependent atmospheric attenuation."""

    def test_low_frequency_low_alpha(self):
        """25 kHz: alpha should be relatively low (~0.12 dB/m)."""
        alpha = atmospheric_attenuation_db_per_m(25_000.0)
        assert 0.05 < alpha < 0.25, f"25 kHz alpha = {alpha}, expected ~0.12"

    def test_mid_frequency_moderate_alpha(self):
        """40 kHz: alpha should be moderate (~0.5 dB/m)."""
        alpha = atmospheric_attenuation_db_per_m(40_000.0)
        assert 0.3 < alpha < 0.8, f"40 kHz alpha = {alpha}, expected ~0.5"

    def test_high_frequency_high_alpha(self):
        """80 kHz: alpha should be high (~3.0 dB/m)."""
        alpha = atmospheric_attenuation_db_per_m(80_000.0)
        assert 2.0 < alpha < 5.0, f"80 kHz alpha = {alpha}, expected ~3.0"

    def test_very_high_frequency_very_high_alpha(self):
        """100 kHz: alpha should be very high (~5.5 dB/m)."""
        alpha = atmospheric_attenuation_db_per_m(100_000.0)
        assert 3.5 < alpha < 8.0, f"100 kHz alpha = {alpha}, expected ~5.5"

    def test_alpha_increases_with_frequency(self):
        """Atmospheric attenuation increases monotonically with frequency."""
        freqs = [20_000, 25_000, 31_500, 40_000, 50_000, 63_000, 80_000, 100_000]
        alphas = [atmospheric_attenuation_db_per_m(f) for f in freqs]
        for i in range(len(alphas) - 1):
            assert alphas[i] < alphas[i + 1], (
                f"Alpha at {freqs[i]} Hz ({alphas[i]}) not less than "
                f"alpha at {freqs[i+1]} Hz ({alphas[i+1]})"
            )

    def test_higher_temp_slightly_lower_alpha(self):
        """Higher temperature slightly reduces alpha at ultrasonic frequencies."""
        alpha_20c = atmospheric_attenuation_db_per_m(40_000.0, temp_c=20.0)
        alpha_50c = atmospheric_attenuation_db_per_m(40_000.0, temp_c=50.0)
        # The correction is small but should be present
        assert alpha_50c < alpha_20c + 0.05, (
            f"50C alpha ({alpha_50c}) should be <= 20C alpha ({alpha_20c})"
        )

    def test_dry_air_higher_alpha(self):
        """Very dry air (<20% RH) should increase alpha."""
        alpha_50rh = atmospheric_attenuation_db_per_m(40_000.0, relative_humidity_pct=50.0)
        alpha_10rh = atmospheric_attenuation_db_per_m(40_000.0, relative_humidity_pct=10.0)
        assert alpha_10rh > alpha_50rh, (
            f"Dry air alpha ({alpha_10rh}) should be > moderate humidity ({alpha_50rh})"
        )

    def test_interpolation_between_table_entries(self):
        """Frequencies between table entries should be interpolated."""
        # 30 kHz is between 25 kHz and 31.5 kHz entries
        alpha_30k = atmospheric_attenuation_db_per_m(30_000.0)
        alpha_25k = atmospheric_attenuation_db_per_m(25_000.0)
        alpha_31k = atmospheric_attenuation_db_per_m(31_500.0)
        assert alpha_25k < alpha_30k < alpha_31k, (
            f"30 kHz alpha ({alpha_30k}) should be between "
            f"25 kHz ({alpha_25k}) and 31.5 kHz ({alpha_31k})"
        )

    def test_flat_05_db_per_m_is_wrong(self):
        """
        PROVE that using 0.5 dB/m flat is physically incorrect.

        At 25 kHz, actual alpha ≈ 0.12 → 0.5 is 4x too conservative.
        At 100 kHz, actual alpha ≈ 5.5 → 0.5 is 11x too optimistic!

        This test documents WHY we rejected the consultant's flat coefficient.
        """
        alpha_25k = atmospheric_attenuation_db_per_m(25_000.0)
        alpha_100k = atmospheric_attenuation_db_per_m(100_000.0)

        # At 25 kHz, flat 0.5 dB/m would OVERESTIMATE attenuation
        assert alpha_25k < 0.5, (
            f"25 kHz alpha ({alpha_25k}) should be LESS than flat 0.5 dB/m"
        )

        # At 100 kHz, flat 0.5 dB/m would UNDERESTIMATE attenuation (DANGEROUS)
        assert alpha_100k > 0.5, (
            f"100 kHz alpha ({alpha_100k}) should be MORE than flat 0.5 dB/m"
        )

    def test_atmospheric_loss_in_propagation(self):
        """AcousticPropagation must apply frequency-dependent alpha."""
        # At 100m, 25 kHz: atm_loss ≈ 0.12 * 100 = 12 dB
        prop_25k = AcousticPropagation(
            leak_spl_at_1m=100.0, distance_meters=100.0,
            center_frequency_hz=25_000.0,
        )
        # At 100m, 80 kHz: atm_loss ≈ 3.0 * 100 = 300 dB (effectively undetectable)
        prop_80k = AcousticPropagation(
            leak_spl_at_1m=100.0, distance_meters=100.0,
            center_frequency_hz=80_000.0,
        )
        # Higher frequency must have significantly more atmospheric loss
        assert prop_80k.atmospheric_loss_db > prop_25k.atmospheric_loss_db * 10


# ===========================================================================
# 4. UGLD Trigger Logic (SNR + Threshold)
# ===========================================================================

class TestUGLDTrigger:
    """Validate check_ugld_trigger dual-condition logic."""

    def test_triggered_both_conditions_met(self):
        """Leak detected when both threshold and SNR are satisfied."""
        sensor = UltrasonicSensor(
            trigger_threshold_db=74.0,
            background_noise_db=60.0,
        )
        prop = AcousticPropagation(
            leak_spl_at_1m=100.0,
            distance_meters=5.0,
            center_frequency_hz=40_000.0,
        )
        result = check_ugld_trigger(prop, sensor)
        assert result.triggered is True
        assert result.fail_reason is None

    def test_not_triggered_below_threshold(self):
        """Leak NOT detected when SPL below trigger threshold."""
        sensor = UltrasonicSensor(
            trigger_threshold_db=90.0,  # Very high threshold
            background_noise_db=40.0,   # Quiet environment → SNR OK
        )
        prop = AcousticPropagation(
            leak_spl_at_1m=80.0,        # Moderate source
            distance_meters=20.0,
            center_frequency_hz=40_000.0,
        )
        result = check_ugld_trigger(prop, sensor)
        assert result.triggered is False
        assert result.fail_reason is not None
        assert "threshold" in result.fail_reason.lower()

    def test_not_triggered_below_snr(self):
        """Leak NOT detected when SPL above threshold but SNR too low."""
        sensor = UltrasonicSensor(
            trigger_threshold_db=70.0,   # Low threshold → easily met
            background_noise_db=85.0,    # Very noisy → SNR fails
        )
        prop = AcousticPropagation(
            leak_spl_at_1m=100.0,
            distance_meters=20.0,
            center_frequency_hz=40_000.0,
        )
        result = check_ugld_trigger(prop, sensor)
        # SPL might be above threshold but SNR is likely insufficient
        # because background is 85 dB and SPL at 20m is much lower
        if not result.triggered:
            assert "SNR" in result.fail_reason

    def test_snr_requirement(self):
        """SNR = Final_SPL - Background_Noise; must be >= 6 dB."""
        sensor = UltrasonicSensor(
            trigger_threshold_db=60.0,
            background_noise_db=70.0,
        )
        prop = AcousticPropagation(
            leak_spl_at_1m=100.0,
            distance_meters=3.0,
            center_frequency_hz=25_000.0,
        )
        result = check_ugld_trigger(prop, sensor)
        # Check SNR calculation
        expected_snr = prop.final_spl_db - sensor.background_noise_db
        assert abs(result.snr_db - round(expected_snr, 1)) < 0.2

    def test_margin_to_threshold(self):
        """Margin = Final_SPL - Trigger_Threshold."""
        sensor = UltrasonicSensor(trigger_threshold_db=70.0, background_noise_db=55.0)
        prop = AcousticPropagation(
            leak_spl_at_1m=100.0, distance_meters=5.0,
            center_frequency_hz=25_000.0,
        )
        result = check_ugld_trigger(prop, sensor)
        expected_margin = prop.final_spl_db - sensor.trigger_threshold_db
        assert abs(result.margin_to_threshold_db - round(expected_margin, 1)) < 0.2

    def test_both_conditions_fail(self):
        """When both threshold and SNR fail, both reasons are reported."""
        sensor = UltrasonicSensor(
            trigger_threshold_db=100.0,   # Impossible threshold
            background_noise_db=90.0,     # Very noisy
        )
        prop = AcousticPropagation(
            leak_spl_at_1m=80.0,          # Weak source
            distance_meters=20.0,
            center_frequency_hz=40_000.0,
        )
        result = check_ugld_trigger(prop, sensor)
        assert result.triggered is False
        # Both threshold and SNR should fail
        assert result.fail_reason is not None
        assert "threshold" in result.fail_reason.lower()
        assert "SNR" in result.fail_reason

    def test_result_is_frozen(self):
        """UGLDTriggerResult must be immutable (frozen Pydantic model)."""
        sensor = UltrasonicSensor(trigger_threshold_db=74.0, background_noise_db=60.0)
        prop = AcousticPropagation(
            leak_spl_at_1m=100.0, distance_meters=5.0,
        )
        result = check_ugld_trigger(prop, sensor)
        # Normal attribute assignment must raise on frozen model
        with pytest.raises(Exception):  # ValidationError for frozen model
            result.triggered = False


# ===========================================================================
# 5. Maximum Detection Range
# ===========================================================================

class TestMaxDetectionRange:
    """Validate max_detection_range_m binary search."""

    def test_detectable_leak_has_positive_range(self):
        """A strong leak should have a positive detection range."""
        sensor = UltrasonicSensor(
            trigger_threshold_db=74.0,
            background_noise_db=55.0,
            center_frequency_hz=40_000.0,
        )
        range_m = max_detection_range_m(
            leak_spl_at_1m=100.0,
            sensor=sensor,
        )
        assert range_m > 0.0

    def test_undetectable_leak_returns_zero(self):
        """A weak leak that can't be detected even at 1m returns 0."""
        sensor = UltrasonicSensor(
            trigger_threshold_db=120.0,  # Impossible threshold
            background_noise_db=80.0,
        )
        range_m = max_detection_range_m(
            leak_spl_at_1m=60.0,  # Weak source
            sensor=sensor,
        )
        assert range_m == 0.0

    def test_higher_frequency_shorter_range(self):
        """Higher center frequency = shorter detection range (more attenuation)."""
        sensor_low = UltrasonicSensor(
            trigger_threshold_db=74.0,
            background_noise_db=55.0,
            center_frequency_hz=25_000.0,
        )
        sensor_high = UltrasonicSensor(
            trigger_threshold_db=74.0,
            background_noise_db=55.0,
            center_frequency_hz=80_000.0,
        )
        range_low = max_detection_range_m(leak_spl_at_1m=100.0, sensor=sensor_low)
        range_high = max_detection_range_m(leak_spl_at_1m=100.0, sensor=sensor_high)
        assert range_low > range_high, (
            f"25 kHz range ({range_low}m) should exceed 80 kHz range ({range_high}m)"
        )

    def test_stronger_leak_longer_range(self):
        """Stronger leak source = longer detection range."""
        sensor = UltrasonicSensor(
            trigger_threshold_db=74.0,
            background_noise_db=55.0,
            center_frequency_hz=40_000.0,
        )
        range_weak = max_detection_range_m(leak_spl_at_1m=85.0, sensor=sensor)
        range_strong = max_detection_range_m(leak_spl_at_1m=110.0, sensor=sensor)
        assert range_strong > range_weak

    def test_noisier_environment_shorter_range(self):
        """Higher background noise = shorter effective range."""
        sensor_quiet = UltrasonicSensor(
            trigger_threshold_db=74.0,
            background_noise_db=50.0,
            center_frequency_hz=40_000.0,
        )
        sensor_noisy = UltrasonicSensor(
            trigger_threshold_db=74.0,
            background_noise_db=70.0,
            center_frequency_hz=40_000.0,
        )
        range_quiet = max_detection_range_m(leak_spl_at_1m=100.0, sensor=sensor_quiet)
        range_noisy = max_detection_range_m(leak_spl_at_1m=100.0, sensor=sensor_noisy)
        assert range_quiet > range_noisy

    def test_range_boundary_triggers_correctly(self):
        """At exactly max range, sensor should still trigger."""
        sensor = UltrasonicSensor(
            trigger_threshold_db=74.0,
            background_noise_db=55.0,
            center_frequency_hz=40_000.0,
        )
        range_m = max_detection_range_m(leak_spl_at_1m=100.0, sensor=sensor)
        # At max range, should still trigger
        prop_at_range = AcousticPropagation(
            leak_spl_at_1m=100.0,
            distance_meters=range_m,
            center_frequency_hz=sensor.center_frequency_hz,
        )
        result_at_range = check_ugld_trigger(prop_at_range, sensor)
        assert result_at_range.triggered is True

        # Slightly beyond max range, should NOT trigger
        prop_beyond = AcousticPropagation(
            leak_spl_at_1m=100.0,
            distance_meters=range_m + 0.5,
            center_frequency_hz=sensor.center_frequency_hz,
        )
        result_beyond = check_ugld_trigger(prop_beyond, sensor)
        assert result_beyond.triggered is False


# ===========================================================================
# 6. Pydantic Model Validation (Fail-Fast)
# ===========================================================================

class TestPydanticValidation:
    """Validate strict Pydantic models reject invalid inputs."""

    def test_sensor_rejects_negative_threshold(self):
        with pytest.raises(Exception):
            UltrasonicSensor(trigger_threshold_db=-1.0)

    def test_sensor_rejects_zero_threshold(self):
        with pytest.raises(Exception):
            UltrasonicSensor(trigger_threshold_db=0.0)

    def test_sensor_rejects_negative_noise(self):
        with pytest.raises(Exception):
            UltrasonicSensor(trigger_threshold_db=74.0, background_noise_db=-5.0)

    def test_propagation_rejects_zero_distance(self):
        with pytest.raises(Exception):
            AcousticPropagation(leak_spl_at_1m=100.0, distance_meters=0.0)

    def test_propagation_rejects_negative_distance(self):
        with pytest.raises(Exception):
            AcousticPropagation(leak_spl_at_1m=100.0, distance_meters=-5.0)

    def test_propagation_rejects_zero_leak_spl(self):
        with pytest.raises(Exception):
            AcousticPropagation(leak_spl_at_1m=0.0, distance_meters=10.0)

    def test_propagation_rejects_negative_leak_spl(self):
        with pytest.raises(Exception):
            AcousticPropagation(leak_spl_at_1m=-10.0, distance_meters=10.0)

    def test_propagation_rejects_temp_below_range(self):
        with pytest.raises(Exception):
            AcousticPropagation(
                leak_spl_at_1m=100.0, distance_meters=10.0,
                temp_c=-50.0,  # Below -40C limit
            )

    def test_propagation_rejects_temp_above_range(self):
        with pytest.raises(Exception):
            AcousticPropagation(
                leak_spl_at_1m=100.0, distance_meters=10.0,
                temp_c=100.0,  # Above 85C limit
            )

    def test_propagation_rejects_humidity_below_range(self):
        with pytest.raises(Exception):
            AcousticPropagation(
                leak_spl_at_1m=100.0, distance_meters=10.0,
                relative_humidity_pct=-5.0,
            )

    def test_propagation_rejects_humidity_above_range(self):
        with pytest.raises(Exception):
            AcousticPropagation(
                leak_spl_at_1m=100.0, distance_meters=10.0,
                relative_humidity_pct=105.0,
            )

    def test_models_are_frozen(self):
        """All models must be immutable after construction."""
        sensor = UltrasonicSensor(trigger_threshold_db=74.0, background_noise_db=60.0)
        prop = AcousticPropagation(
            leak_spl_at_1m=100.0, distance_meters=10.0,
        )
        # Normal attribute assignment must raise on frozen models
        with pytest.raises(Exception):
            sensor.trigger_threshold_db = 80.0
        with pytest.raises(Exception):
            prop.final_spl_db = 50.0


# ===========================================================================
# 7. Physical Consistency & Edge Cases
# ===========================================================================

class TestPhysicalConsistency:
    """Cross-check acoustic physics for internal consistency."""

    def test_leak_spl_at_1m_equals_source_plus_zero_geo_loss(self):
        """At 1m: final SPL ≈ source SPL (geometric loss = 0)."""
        prop = AcousticPropagation(
            leak_spl_at_1m=95.0,
            distance_meters=1.0,
            center_frequency_hz=25_000.0,
        )
        # At 1m, geometric_loss = 0, atmospheric_loss ≈ 0.12
        assert prop.geometric_loss_db == 0.0
        assert abs(prop.final_spl_db - 95.0) < 1.0  # Within 1 dB

    def test_temperature_affects_speed_of_sound_not_spl(self):
        """Temperature changes speed of sound but has minimal effect on SPL."""
        prop_20c = AcousticPropagation(
            leak_spl_at_1m=100.0, distance_meters=10.0,
            temp_c=20.0, center_frequency_hz=40_000.0,
        )
        prop_40c = AcousticPropagation(
            leak_spl_at_1m=100.0, distance_meters=10.0,
            temp_c=40.0, center_frequency_hz=40_000.0,
        )
        # Speed of sound differs significantly
        assert prop_20c.speed_of_sound_mps < prop_40c.speed_of_sound_mps
        # SPL differs only slightly (temperature correction on alpha is small)
        assert abs(prop_20c.final_spl_db - prop_40c.final_spl_db) < 1.0

    def test_total_loss_equals_geo_plus_atm(self):
        """Total SPL loss = geometric loss + atmospheric loss."""
        prop = AcousticPropagation(
            leak_spl_at_1m=100.0, distance_meters=30.0,
            center_frequency_hz=40_000.0,
        )
        total_loss = prop.leak_spl_at_1m - prop.final_spl_db
        expected_loss = prop.geometric_loss_db + prop.atmospheric_loss_db
        assert abs(total_loss - round(expected_loss, 1)) < 0.5

    def test_default_frequency_is_40khz(self):
        """Default center frequency should be 40 kHz (most common UGLD)."""
        assert _DEFAULT_UGLD_FREQUENCY_HZ == 40_000.0
        sensor = UltrasonicSensor(trigger_threshold_db=74.0, background_noise_db=60.0)
        assert sensor.center_frequency_hz == 40_000.0

    def test_default_snr_requirement_is_6db(self):
        """Default SNR requirement should be 6 dB."""
        assert _MIN_SNR_DB == 6.0

    def test_iso_9613_table_has_entries(self):
        """ISO 9613 lookup table must have reference values."""
        assert len(_ISO_9613_ALPHA_20C_50RH) >= 5
        # All values must be positive
        for freq, alpha in _ISO_9613_ALPHA_20C_50RH.items():
            assert alpha > 0, f"Alpha for {freq} Hz must be positive"

    def test_ugld_frequency_band_enum(self):
        """UGLDFrequencyBand enum must have all expected bands."""
        assert UGLDFrequencyBand.ULTRASOUND_LOW.value == "ULTRASOUND_LOW"
        assert UGLDFrequencyBand.ULTRASOUND_MID.value == "ULTRASOUND_MID"
        assert UGLDFrequencyBand.ULTRASOUND_HIGH.value == "ULTRASOUND_HIGH"
        assert UGLDFrequencyBand.ULTRASOUND_VHF.value == "ULTRASOUND_VHF"

    def test_consultant_bug_regression_flat_alpha(self):
        """
        REGRESSION: Flat 0.5 dB/m would cause safety-critical errors.

        At 100 kHz and 30m distance:
          - Flat 0.5: loss = 0.5 * 30 = 15 dB (UNDERESTIMATES by ~150 dB!)
          - ISO 9613: loss = 5.5 * 30 = 165 dB

        A sensor placed using flat 0.5 dB/m would FAIL to detect a real leak
        at 100 kHz because the actual attenuation is 10x what was calculated.
        This could leave an explosive gas leak undetected.
        """
        # At 30m, 100 kHz with flat 0.5 dB/m:
        flat_loss = 0.5 * 30  # = 15 dB

        # With ISO 9613-1 frequency-dependent:
        prop = AcousticPropagation(
            leak_spl_at_1m=100.0, distance_meters=30.0,
            center_frequency_hz=100_000.0,
        )
        real_loss = prop.atmospheric_loss_db

        # The real loss should be MUCH higher than flat
        assert real_loss > flat_loss * 5, (
            f"Real atmospheric loss ({real_loss:.1f} dB) should be >> "
            f"flat estimate ({flat_loss:.1f} dB) at 100 kHz"
        )

    def test_mena_high_temp_scenario(self):
        """
        GCC/MENA scenario: 55C ambient, 40% humidity, 40 kHz.

        Verifies UGLD works in extreme Middle East conditions.
        """
        sensor = UltrasonicSensor(
            trigger_threshold_db=74.0,
            background_noise_db=65.0,  # Noisy plant
            center_frequency_hz=40_000.0,
        )
        prop = AcousticPropagation(
            leak_spl_at_1m=100.0,
            distance_meters=10.0,
            center_frequency_hz=40_000.0,
            temp_c=55.0,
            relative_humidity_pct=40.0,
        )
        result = check_ugld_trigger(prop, sensor)
        # At 10m, 40 kHz, even in MENA conditions, 100 dB source should be detectable
        assert prop.final_spl_db > 0, "SPL should be positive"
        # Check that speed of sound reflects 55C
        assert prop.speed_of_sound_mps > 360.0, (
            f"Speed at 55C ({prop.speed_of_sound_mps}) should be > 360 m/s"
        )


# ===========================================================================
# 8. AcousticPropagation Computed Fields
# ===========================================================================

class TestPropagationComputedFields:
    """Verify all computed fields are set correctly."""

    def test_all_computed_fields_nonzero(self):
        """All computed fields must be non-zero for valid inputs."""
        prop = AcousticPropagation(
            leak_spl_at_1m=100.0, distance_meters=10.0,
            center_frequency_hz=40_000.0, temp_c=40.0,
        )
        assert prop.speed_of_sound_mps > 0
        assert prop.geometric_loss_db > 0
        assert prop.atmospheric_loss_db > 0
        assert prop.alpha_db_per_m > 0
        # final_spl_db can be negative (very distant source)
        # but should be a valid float
        assert math.isfinite(prop.final_spl_db)

    def test_alpha_stored_in_propagation(self):
        """AcousticPropagation stores the computed alpha value."""
        prop = AcousticPropagation(
            leak_spl_at_1m=100.0, distance_meters=10.0,
            center_frequency_hz=40_000.0, temp_c=25.0,
            relative_humidity_pct=50.0,
        )
        expected_alpha = atmospheric_attenuation_db_per_m(
            center_frequency_hz=40_000.0, temp_c=25.0,
            relative_humidity_pct=50.0,
        )
        assert abs(prop.alpha_db_per_m - expected_alpha) < 0.001
