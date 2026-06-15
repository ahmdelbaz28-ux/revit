"""
tests/test_qomn_kernel.py
Comprehensive test suite for:
  - fireai/core/qomn_kernel.py

SAFETY CRITICAL: This module is the QOMN-FIRE Deterministic Engineering
Kernel. Errors in physics guards, computation, or audit logging could
result in non-compliant fire alarm designs — a direct life-safety hazard.

NFPA 72 References:
  §10.6.7.2.1 — Battery sizing
  §17.6.3.1   — Heat detector spacing
  §17.7.3     — Smoke detector spacing
  §17.7.3.2.1 — Max spacing 9.144m (30ft)
  §17.7.3.2.4 — Ceiling height limit 18.288m (60ft)
NEC References:
  Chapter 9, Table 8 — Wire resistance
  §310.16             — Wire ampacity
"""

from __future__ import annotations

import math
import os

import pytest

from fireai.core.qomn_kernel import (
    ACCESS_CONTROL_READER_HEIGHT_M,
    CCTV_LENS_FOV_DEG,
    NEC_AMPACITY_60C,
    NEC_TABLE8_RESISTANCE_OHM_PER_KM,
    NFPA72_ALARM_MINUTES,
    NFPA72_BATTERY_DISCHARGE_EFFICIENCY,
    NFPA72_BATTERY_SAFETY_FACTOR,
    NFPA72_COVERAGE_RADIUS_FACTOR,
    NFPA72_HEAT_MAX_SPACING_M,
    NFPA72_PULL_STATION_FROM_EXIT_M,
    NFPA72_PULL_STATION_HEIGHT_M,
    NFPA72_SMOKE_MAX_SPACING_M,
    # Layer 1 — Constants
    NFPA72_SMOKE_SPACING_TABLE,
    NFPA72_STANDBY_HOURS,
    NFPA72_WALL_MIN_DISTANCE_M,
    TIA568_HORIZONTAL_MAX_M,
    TIA568_TOTAL_CHANNEL_MAX_M,
    # Layer 4 — Audit
    AuditEntry,
    ComputationError,
    # Layer 0 — Physics Guards
    PhysicsGuardError,
    QOMNAuditLog,
    # Kernel
    QOMNKernel,
    ValidationError,
    # Layer 2 — Computation
    _f64_hash,
    _guard_finite,
    compute_battery_capacity_ah,
    compute_heat_detector_spacing,
    compute_smoke_detector_spacing,
    compute_voltage_drop,
    guard_area_m2,
    guard_ceiling_height_m,
    guard_current_a,
    guard_efficiency,
    guard_temperature_c,
    guard_voltage_v,
    validate_battery_result,
    validate_heat_spacing_result,
    # Layer 3 — Validation
    validate_smoke_spacing_result,
    validate_voltage_drop_result,
)

# ═══════════════════════════════════════════════════════════════════════════════
# LAYER 0 — Physics Guard Tests
# ═══════════════════════════════════════════════════════════════════════════════


class TestGuardFinite:
    """IEEE-754 guard: reject NaN and Inf before any computation."""

    def test_valid_int(self):
        assert _guard_finite(42, "test") == 42.0

    def test_valid_float(self):
        assert _guard_finite(3.14, "test") == 3.14

    def test_zero(self):
        assert _guard_finite(0.0, "test") == 0.0

    def test_negative(self):
        assert _guard_finite(-10.0, "test") == -10.0

    def test_nan_rejected(self):
        with pytest.raises(PhysicsGuardError, match="NaN"):
            _guard_finite(float("nan"), "test_field")

    def test_inf_rejected(self):
        with pytest.raises(PhysicsGuardError, match="Infinity"):
            _guard_finite(float("inf"), "test_field")

    def test_negative_inf_rejected(self):
        with pytest.raises(PhysicsGuardError, match="Infinity"):
            _guard_finite(float("-inf"), "test_field")

    def test_string_rejected(self):
        with pytest.raises(PhysicsGuardError, match="numeric"):
            _guard_finite("3.14", "test_field")

    def test_none_rejected(self):
        with pytest.raises(PhysicsGuardError, match="numeric"):
            _guard_finite(None, "test_field")

    def test_list_rejected(self):
        with pytest.raises(PhysicsGuardError, match="numeric"):
            _guard_finite([1.0], "test_field")

    def test_error_has_field_and_reason(self):
        with pytest.raises(PhysicsGuardError) as exc_info:
            _guard_finite(float("nan"), "my_field")
        err = exc_info.value
        assert err.field == "my_field"
        assert "NaN" in err.reason


class TestGuardAreaM2:
    """NFPA 72 §17.7.3.2.1: max 232.26 m² (2500 ft²) per smoke detector."""

    def test_valid_area(self):
        assert guard_area_m2(100.0) == 100.0

    def test_max_allowed(self):
        assert guard_area_m2(232.26) == pytest.approx(232.26)

    def test_zero_rejected(self):
        with pytest.raises(PhysicsGuardError, match="> 0"):
            guard_area_m2(0.0)

    def test_negative_rejected(self):
        with pytest.raises(PhysicsGuardError, match="> 0"):
            guard_area_m2(-5.0)

    def test_exceeds_nfpa_max(self):
        with pytest.raises(PhysicsGuardError, match="232.26"):
            guard_area_m2(300.0)

    def test_nan_rejected(self):
        with pytest.raises(PhysicsGuardError):
            guard_area_m2(float("nan"))

    def test_inf_rejected(self):
        with pytest.raises(PhysicsGuardError):
            guard_area_m2(float("inf"))


class TestGuardCeilingHeightM:
    """NFPA 72 §17.7.3.2.4: ceiling height ≤ 18.288m (60ft)."""

    def test_valid_height(self):
        assert guard_ceiling_height_m(3.0) == 3.0

    def test_max_allowed(self):
        assert guard_ceiling_height_m(18.288) == pytest.approx(18.288)

    def test_zero_rejected(self):
        with pytest.raises(PhysicsGuardError, match="> 0"):
            guard_ceiling_height_m(0.0)

    def test_negative_rejected(self):
        with pytest.raises(PhysicsGuardError, match="> 0"):
            guard_ceiling_height_m(-1.0)

    def test_exceeds_max(self):
        with pytest.raises(PhysicsGuardError, match="18.288"):
            guard_ceiling_height_m(20.0)

    def test_nan_rejected(self):
        with pytest.raises(PhysicsGuardError):
            guard_ceiling_height_m(float("nan"))


class TestGuardCurrentA:
    """NEC §310.16: current must not exceed wire ampacity."""

    def test_valid_current(self):
        assert guard_current_a(5.0, 15.0, "14") == 5.0

    def test_zero_current(self):
        assert guard_current_a(0.0, 15.0, "14") == 0.0

    def test_negative_rejected(self):
        with pytest.raises(PhysicsGuardError, match="negative"):
            guard_current_a(-1.0, 15.0, "14")

    def test_exceeds_ampacity(self):
        with pytest.raises(PhysicsGuardError, match="ampacity"):
            guard_current_a(20.0, 15.0, "14")

    def test_exactly_at_ampacity(self):
        """Current exactly at ampacity is allowed (not exceeding)."""
        assert guard_current_a(15.0, 15.0, "14") == 15.0

    def test_nan_current_rejected(self):
        with pytest.raises(PhysicsGuardError):
            guard_current_a(float("nan"), 15.0, "14")

    def test_nan_ampacity_rejected(self):
        with pytest.raises(PhysicsGuardError):
            guard_current_a(5.0, float("nan"), "14")


class TestGuardVoltageV:
    """NEC §110.3(B): voltage must not exceed system rating."""

    def test_valid_voltage(self):
        assert guard_voltage_v(24.0, 48.0) == 24.0

    def test_zero_allowed(self):
        """Zero voltage is not negative — only negative is rejected."""
        assert guard_voltage_v(0.0, 48.0) == 0.0

    def test_negative_rejected(self):
        with pytest.raises(PhysicsGuardError, match="negative"):
            guard_voltage_v(-12.0, 48.0)

    def test_exceeds_rating(self):
        with pytest.raises(PhysicsGuardError, match="system rating"):
            guard_voltage_v(50.0, 48.0)

    def test_at_rating(self):
        """Voltage exactly at system rating is allowed."""
        assert guard_voltage_v(48.0, 48.0) == 48.0


class TestGuardTemperatureC:
    """NFPA 72 §17.6.2: ambient must be below detector rating."""

    def test_valid_temp(self):
        assert guard_temperature_c(25.0, 57.0) == 25.0

    def test_at_rating_rejected(self):
        """Ambient >= detector rating means detector can't reliably detect fire."""
        with pytest.raises(PhysicsGuardError, match="≥ detector rating"):
            guard_temperature_c(57.0, 57.0)

    def test_above_rating_rejected(self):
        with pytest.raises(PhysicsGuardError, match="≥ detector rating"):
            guard_temperature_c(60.0, 57.0)

    def test_nan_rejected(self):
        with pytest.raises(PhysicsGuardError):
            guard_temperature_c(float("nan"), 57.0)


class TestGuardEfficiency:
    """Physics: efficiency must be (0, 1.0]."""

    def test_valid_efficiency(self):
        assert guard_efficiency(0.8) == 0.8

    def test_one_hundred_percent(self):
        assert guard_efficiency(1.0) == 1.0

    def test_zero_rejected(self):
        with pytest.raises(PhysicsGuardError, match="> 0"):
            guard_efficiency(0.0)

    def test_negative_rejected(self):
        with pytest.raises(PhysicsGuardError, match="> 0"):
            guard_efficiency(-0.5)

    def test_above_one_rejected(self):
        with pytest.raises(PhysicsGuardError, match="conservation of energy"):
            guard_efficiency(1.1)

    def test_nan_rejected(self):
        with pytest.raises(PhysicsGuardError):
            guard_efficiency(float("nan"))


class TestPhysicsGuardError:
    """PhysicsGuardError carries structured metadata for AHJ review."""

    def test_attributes(self):
        err = PhysicsGuardError("field_x", 999, "too high", "NFPA 72-2022 §X")
        assert err.field == "field_x"
        assert err.value == 999
        assert err.reason == "too high"
        assert err.code_ref == "NFPA 72-2022 §X"

    def test_message_format(self):
        err = PhysicsGuardError("area", -1, "must be > 0", "Physics")
        assert "PHYSICS GUARD REJECTION" in str(err)
        assert "area" in str(err)
        assert "must be > 0" in str(err)


# ═══════════════════════════════════════════════════════════════════════════════
# LAYER 1 — Reference Constants Tests
# ═══════════════════════════════════════════════════════════════════════════════


class TestNFPA72Constants:
    """Verify NFPA 72 reference constants match published standard."""

    # V121 FIX: Smoke spacing table updated to canonical values from
    # fireai/constants/nfpa72.py. Old values applied heat detector
    # reduction (1%/ft) to smoke detectors — a known misapplication.
    # New table has 9 rows (conservative height-adjusted values).
    def test_smoke_spacing_table_entries(self):
        assert len(NFPA72_SMOKE_SPACING_TABLE) == 9

    def test_smoke_spacing_first_row(self):
        """≤3.0m → 9.1m (30ft listed spacing)."""
        assert NFPA72_SMOKE_SPACING_TABLE[0] == (3.0, 9.10)

    def test_smoke_spacing_last_row(self):
        """V130 FIX: ≤12.2m → FLAT 9.1m per §17.7.3.2.3 (no height reduction)."""
        assert NFPA72_SMOKE_SPACING_TABLE[-1] == (12.2, 9.10)

    def test_spacing_flat_at_all_heights(self):
        """V130 FIX: Smoke spacing is FLAT 9.1m at ALL heights per §17.7.3.2.3."""
        for _, spacing in NFPA72_SMOKE_SPACING_TABLE:
            assert spacing == 9.10, f"Expected 9.1m flat spacing, got {spacing}m"

    def test_coverage_radius_factor(self):
        """R = 0.7 × S per NFPA 72 §17.7.4.2.3.1."""
        assert NFPA72_COVERAGE_RADIUS_FACTOR == 0.7

    # V121 FIX: SMOKE_MAX_SPACING_M corrected from 9.144 to 9.1
    # (NFPA 72 states 9.1m, not 30ft×0.3048=9.144)
    def test_smoke_max_spacing(self):
        """NFPA 72 §17.7.3.2.3: max 9.1m (30ft)."""
        assert NFPA72_SMOKE_MAX_SPACING_M == pytest.approx(9.1)

    # V121 FIX: HEAT_MAX_SPACING_M corrected from 15.240 to 6.1
    # (6.1m = 20ft is the standard spacing at h≤3.0m per Table 17.6.3.5.1;
    # 15.24m = 50ft is the ABSOLUTE max listed spacing, now in
    # fireai/constants/nfpa72.py as HEAT_ABSOLUTE_MAX_SPACING_M)
    def test_heat_max_spacing(self):
        """NFPA 72 Table 17.6.2.1: max 6.1m (20ft) for fixed-temperature heat.
        CRITICAL FIX: Was 15.240m (50ft) which was the LINEAR detection spacing,
        not fixed-temperature. 15.24m would produce R=10.67m — 2.5× overestimate.
        """
        assert NFPA72_HEAT_MAX_SPACING_M == pytest.approx(6.1)

    # V121 FIX: WALL_MIN_DISTANCE corrected from 0.305 to 0.10
    # (NFPA 72 §17.6.3.1.1 specifies 0.1m dead air space minimum)
    def test_wall_min_distance(self):
        """NFPA 72 §17.6.3.1.1: 4 inches (0.1016m) dead air space minimum.
        CRITICAL FIX: Was 0.305m which conflated with wall MAX distance S/2.
        """
        assert NFPA72_WALL_MIN_DISTANCE_M == pytest.approx(0.1016)

    def test_pull_station_height(self):
        """NFPA 72 §17.15.7: 48 inches = 1.219m AFF."""
        assert NFPA72_PULL_STATION_HEIGHT_M == pytest.approx(1.219)

    def test_pull_station_from_exit(self):
        """NFPA 72 §17.15.3: 5 ft = 1.524m from exit."""
        assert NFPA72_PULL_STATION_FROM_EXIT_M == pytest.approx(1.524)

    def test_battery_standby_hours(self):
        """NFPA 72 §10.6.7.2.1: 24 hours standby."""
        assert NFPA72_STANDBY_HOURS == 24.0

    def test_battery_alarm_minutes(self):
        """NFPA 72 §10.6.7.2.1: 5 minutes alarm."""
        assert NFPA72_ALARM_MINUTES == 5.0

    def test_battery_safety_factor(self):
        """NFPA 72 §10.6.7.2.1: 25% additional capacity."""
        assert NFPA72_BATTERY_SAFETY_FACTOR == 1.25

    def test_battery_discharge_efficiency(self):
        assert NFPA72_BATTERY_DISCHARGE_EFFICIENCY == 0.80


class TestNECConstants:
    """Verify NEC Table 8 and ampacity constants."""

    def test_resistance_table_keys(self):
        # C-3 FIX: Table now uses 20°C stranded values from fireai/constants/nec.py
        # Includes AWG 3 which is in the stranded conductor table
        expected = {"18", "16", "14", "12", "10", "8", "6", "4", "3", "2", "1", "1/0", "2/0", "3/0", "4/0"}
        assert set(NEC_TABLE8_RESISTANCE_OHM_PER_KM.keys()) == expected

    def test_awg14_resistance(self):
        """AWG 14: 4.263 Ω/km at 20°C stranded (NEC Table 8).
        C-3 FIX: Value changed from 8.19 (incorrect 75°C claim) to 4.263 (correct 20°C stranded).
        Temperature correction to 75°C is applied in compute_voltage_drop()."""
        assert NEC_TABLE8_RESISTANCE_OHM_PER_KM["14"] == pytest.approx(4.263, abs=0.01)

    def test_resistance_increases_with_gauge(self):
        """Thinner wire (higher AWG) has more resistance."""
        assert NEC_TABLE8_RESISTANCE_OHM_PER_KM["18"] > NEC_TABLE8_RESISTANCE_OHM_PER_KM["14"]
        assert NEC_TABLE8_RESISTANCE_OHM_PER_KM["14"] > NEC_TABLE8_RESISTANCE_OHM_PER_KM["12"]

    def test_ampacity_table_keys(self):
        assert "14" in NEC_AMPACITY_60C
        assert "4/0" in NEC_AMPACITY_60C

    def test_awg14_ampacity(self):
        """NEC §310.16: AWG 14 copper 60°C = 15A."""
        assert NEC_AMPACITY_60C["14"] == 15.0

    def test_ampacity_increases_with_wire_size(self):
        """Larger wire carries more current."""
        assert NEC_AMPACITY_60C["12"] > NEC_AMPACITY_60C["14"]
        assert NEC_AMPACITY_60C["4/0"] > NEC_AMPACITY_60C["12"]


class TestTIA568Constants:
    def test_horizontal_max(self):
        assert TIA568_HORIZONTAL_MAX_M == 90.0

    def test_total_channel_max(self):
        assert TIA568_TOTAL_CHANNEL_MAX_M == 100.0


class TestCCTVLensConstants:
    def test_lens_fov_keys(self):
        assert "3.6mm" in CCTV_LENS_FOV_DEG
        assert "6mm" in CCTV_LENS_FOV_DEG

    def test_lens_fov_values(self):
        assert CCTV_LENS_FOV_DEG["3.6mm"] == 90.0
        assert CCTV_LENS_FOV_DEG["6mm"] == 60.0


class TestAccessControlConstants:
    def test_reader_height_range(self):
        lo, hi = ACCESS_CONTROL_READER_HEIGHT_M
        assert lo == pytest.approx(1.067)  # 42"
        assert hi == pytest.approx(1.219)  # 48"


# ═══════════════════════════════════════════════════════════════════════════════
# LAYER 2 — Computation Tests
# ═══════════════════════════════════════════════════════════════════════════════


class TestF64Hash:
    """IEEE-754 bit-exact hash: same input → same hash, always."""

    def test_deterministic(self):
        h1 = _f64_hash(3.14)
        h2 = _f64_hash(3.14)
        assert h1 == h2

    def test_different_values_different_hash(self):
        h1 = _f64_hash(1.0)
        h2 = _f64_hash(2.0)
        assert h1 != h2

    def test_length(self):
        h = _f64_hash(0.0)
        assert len(h) == 16  # SHA-256 truncated to 16 hex chars

    def test_zero_hash(self):
        h = _f64_hash(0.0)
        assert isinstance(h, str)
        assert len(h) == 16


class TestComputeSmokeDetectorSpacing:
    """NFPA 72 Table 17.6.3.1 + §17.7.3.2.3 height adjustment."""

    # V121 FIX: Spacing is now flat 9.1m per §17.7.3.2.3
    def test_low_ceiling(self):
        """h ≤ 3.0m → S = 9.1m, R = 0.7 × 9.1 = 6.37m."""
        result = compute_smoke_detector_spacing(3.0)
        assert result["listed_spacing_m"] == pytest.approx(9.1, rel=0.01)
        assert result["coverage_radius_m"] == pytest.approx(0.7 * 9.1, rel=0.01)

    # V127 PHASE C: Height-adjusted spacing per Table 17.6.3.1.1 restored.
    # The V121 flat-only override was removed in favor of the canonical
    # height-adjusted spacing table from fireai/constants/__init__.py.
    def test_medium_ceiling(self):
        """V130 FIX: h=4.0m → FLAT 9.1m spacing per §17.7.3.2.3."""
        result = compute_smoke_detector_spacing(4.0)
        assert result["listed_spacing_m"] == pytest.approx(9.10, abs=1e-3)

    def test_high_ceiling_flat_spacing(self):
        """V130 FIX: Spacing is FLAT 9.1m at ALL heights per §17.7.3.2.3."""
        r_low = compute_smoke_detector_spacing(3.0)
        r_high = compute_smoke_detector_spacing(6.0)
        assert r_high["listed_spacing_m"] == r_low["listed_spacing_m"]  # Both 9.1m

    def test_coverage_radius_is_07_times_spacing(self):
        """NFPA 72 §17.7.4.2.3.1: R = 0.7 × S."""
        result = compute_smoke_detector_spacing(3.0)
        assert result["coverage_radius_m"] == pytest.approx(
            0.7 * result["listed_spacing_m"], rel=1e-4
        )

    def test_nfpa_section_present(self):
        result = compute_smoke_detector_spacing(3.0)
        assert "NFPA 72" in result["nfpa_section"]

    def test_computation_hash_present(self):
        result = compute_smoke_detector_spacing(3.0)
        assert len(result["computation_hash"]) > 0

    def test_wall_distances(self):
        """Wall min = 0.1016m (4in dead air), Wall max = 0.5 × S per §17.6.3.1.1."""
        result = compute_smoke_detector_spacing(3.0)
        # wall_min_m: dead air space minimum (4 inches = 0.1016m)
        assert result["wall_min_m"] == pytest.approx(0.1016, rel=1e-3)
        # wall_max_m: maximum wall distance = S/2 per §17.6.3.1.1
        assert result["wall_max_m"] == pytest.approx(
            0.5 * result["listed_spacing_m"], rel=1e-4
        )

    def test_invalid_ceiling_height_raises(self):
        with pytest.raises(PhysicsGuardError):
            compute_smoke_detector_spacing(25.0)  # > 18.288m

    def test_zero_ceiling_height_raises(self):
        with pytest.raises(PhysicsGuardError):
            compute_smoke_detector_spacing(0.0)


class TestComputeHeatDetectorSpacing:
    """NFPA 72 §17.6.3.1: S = 0.7 × √A, max 15.24m (50ft absolute max)."""

    def test_small_area(self):
        """S = 0.7 × √A = 7.0m, within absolute max 15.24m (50ft)."""
        result = compute_heat_detector_spacing(3.0, 100.0)
        # 0.7 × √100 = 7.0m — within absolute max 15.24m
        assert result["spacing_m"] == pytest.approx(7.0, rel=0.01)

    def test_very_small_area_uncapped(self):
        """Small area where S = 0.7 × √A < 15.24m — no cap applied."""
        result = compute_heat_detector_spacing(3.0, 50.0)
        expected_s = 0.7 * math.sqrt(50.0)  # ≈4.95m — well below 15.24m cap
        assert result["spacing_m"] == pytest.approx(expected_s, rel=0.01)

    def test_large_area_capped(self):
        """Very large area (>232.26 m²) rejected by PhysicsGuard."""
        with pytest.raises(PhysicsGuardError, match="exceeds NFPA 72"):
            compute_heat_detector_spacing(3.0, 10000.0)

    def test_coverage_radius(self):
        result = compute_heat_detector_spacing(3.0, 100.0)
        assert result["coverage_radius_m"] == pytest.approx(
            0.7 * result["spacing_m"], rel=1e-4
        )

    def test_is_within_max(self):
        result = compute_heat_detector_spacing(3.0, 50.0)
        assert result["is_within_max"] is True

    def test_zero_area_rejected(self):
        with pytest.raises(PhysicsGuardError, match="> 0"):
            compute_heat_detector_spacing(3.0, 0.0)

    def test_negative_area_rejected(self):
        with pytest.raises(PhysicsGuardError, match="> 0"):
            compute_heat_detector_spacing(3.0, -10.0)

    def test_invalid_ceiling_rejected(self):
        with pytest.raises(PhysicsGuardError):
            compute_heat_detector_spacing(25.0, 100.0)


class TestComputeBatteryCapacityAh:
    """NFPA 72 §10.6.7.2.1: battery sizing formula."""

    def test_basic_calculation(self):
        """Ah = ((I_sb × 24h + I_al × 5/60h) / 0.80) × 1.25."""
        result = compute_battery_capacity_ah(1.0, 2.0)
        ah_standby = 1.0 * 24.0
        ah_alarm = 2.0 * (5.0 / 60.0)
        ah_raw = ah_standby + ah_alarm
        ah_required = (ah_raw / 0.80) * 1.25
        assert result["required_ah"] == pytest.approx(ah_required, rel=0.01)

    def test_standby_component(self):
        result = compute_battery_capacity_ah(1.0, 0.0)
        assert result["ah_standby"] == pytest.approx(24.0)

    def test_alarm_component(self):
        result = compute_battery_capacity_ah(0.0, 1.0)
        expected_alarm = 1.0 * (5.0 / 60.0)
        assert result["ah_alarm"] == pytest.approx(expected_alarm, rel=1e-4)

    def test_zero_currents(self):
        """Zero load → zero Ah (valid for pure standby-only check)."""
        result = compute_battery_capacity_ah(0.0, 0.0)
        assert result["required_ah"] == 0.0

    def test_negative_standby_rejected(self):
        with pytest.raises(PhysicsGuardError, match="negative"):
            compute_battery_capacity_ah(-1.0, 2.0)

    def test_negative_alarm_rejected(self):
        with pytest.raises(PhysicsGuardError, match="negative"):
            compute_battery_capacity_ah(1.0, -2.0)

    def test_safety_factor_below_one_rejected(self):
        with pytest.raises(PhysicsGuardError, match="≥ 1.0"):
            compute_battery_capacity_ah(1.0, 2.0, safety_factor=0.9)

    def test_discharge_efficiency_above_one_rejected(self):
        with pytest.raises(PhysicsGuardError, match="conservation"):
            compute_battery_capacity_ah(1.0, 2.0, discharge_efficiency=1.1)

    def test_nfpa_section_present(self):
        result = compute_battery_capacity_ah(1.0, 2.0)
        assert "NFPA 72" in result["nfpa_section"]

    def test_computation_hash_present(self):
        result = compute_battery_capacity_ah(1.0, 2.0)
        assert len(result["computation_hash"]) > 0


class TestComputeVoltageDrop:
    """NEC Chapter 9, Table 8: V_drop = 2 × I × L × R_per_m (at operating temp)."""

    def test_basic_calculation(self):
        """V_drop = 2 × I × L × R/km / 1000 × temp_correction.
        C-3 FIX: Now includes temperature correction from 20°C to 75°C operating temp.
        R_75 = R_20 × [1 + 0.00393 × (75-20)] = R_20 × 1.2163"""
        result = compute_voltage_drop(1.0, 100.0, "14")
        # Resistance at 20°C ref, corrected to 75°C operating temp
        r_20_per_m = NEC_TABLE8_RESISTANCE_OHM_PER_KM["14"] / 1000.0
        temp_correction = 1.0 + 0.00393 * (75.0 - 20.0)  # 1.2163
        r_per_m = r_20_per_m * temp_correction
        expected = 2.0 * 1.0 * 100.0 * r_per_m
        assert result["voltage_drop_v"] == pytest.approx(expected, rel=0.01)

    def test_return_factor_of_two(self):
        """SAFETY: Factor of 2 for DC round-trip (supply + return)."""
        result = compute_voltage_drop(1.0, 100.0, "14")
        r_20_per_m = NEC_TABLE8_RESISTANCE_OHM_PER_KM["14"] / 1000.0
        temp_correction = 1.0 + 0.00393 * (75.0 - 20.0)
        r_per_m = r_20_per_m * temp_correction
        # Without ×2 factor would be:
        single = 1.0 * 100.0 * r_per_m
        assert result["voltage_drop_v"] == pytest.approx(2.0 * single, rel=0.01)

    def test_compliant_short_circuit(self):
        result = compute_voltage_drop(0.1, 10.0, "14")
        assert result["is_compliant"] is True
        assert result["drop_pct"] <= 10.0

    def test_non_compliant_long_circuit(self):
        result = compute_voltage_drop(2.0, 500.0, "18")
        assert result["is_compliant"] is False

    def test_max_length_calculation(self):
        result = compute_voltage_drop(1.0, 100.0, "14")
        assert result["max_length_m"] > 0

    def test_zero_current_max_length(self):
        """Zero current → max_length is 0.0 (avoid div by zero)."""
        result = compute_voltage_drop(0.0, 100.0, "14")
        assert result["max_length_m"] == 0.0

    def test_negative_current_rejected(self):
        with pytest.raises(PhysicsGuardError, match="negative"):
            compute_voltage_drop(-1.0, 100.0, "14")

    def test_zero_length_rejected(self):
        with pytest.raises(PhysicsGuardError, match="> 0"):
            compute_voltage_drop(1.0, 0.0, "14")

    def test_zero_voltage_rejected(self):
        with pytest.raises(PhysicsGuardError, match="> 0"):
            compute_voltage_drop(1.0, 100.0, "14", supply_voltage_v=0.0)

    def test_unknown_gauge_rejected(self):
        with pytest.raises(ValueError, match="not in NEC Table 8"):
            compute_voltage_drop(1.0, 100.0, "999")

    def test_gauge_stripping(self):
        """'AWG14' or ' awg 14 ' should resolve to '14'."""
        result = compute_voltage_drop(1.0, 100.0, "AWG14")
        assert result["awg_gauge"] == "14"

    def test_nec_section_present(self):
        result = compute_voltage_drop(1.0, 100.0, "14")
        assert "NEC" in result["nec_section"]


# ═══════════════════════════════════════════════════════════════════════════════
# LAYER 3 — Validation Tests
# ═══════════════════════════════════════════════════════════════════════════════


class TestValidateSmokeSpacingResult:
    def test_valid_result_passes(self):
        result = compute_smoke_detector_spacing(3.0)
        validated = validate_smoke_spacing_result(result)
        assert validated["layer3_validated"] is True

    def test_non_finite_rejected(self):
        result = {"listed_spacing_m": float("nan"), "coverage_radius_m": 6.4}
        with pytest.raises(ComputationError, match="NaN"):
            validate_smoke_spacing_result(result)

    def test_zero_spacing_rejected(self):
        result = {"listed_spacing_m": 0.0, "coverage_radius_m": 0.0}
        with pytest.raises(ValidationError, match="≤ 0"):
            validate_smoke_spacing_result(result)

    def test_exceeds_max_rejected(self):
        result = {"listed_spacing_m": 15.0, "coverage_radius_m": 10.5}
        with pytest.raises(ValidationError, match="NFPA 72 max"):
            validate_smoke_spacing_result(result)

    def test_radius_mismatch_rejected(self):
        result = {"listed_spacing_m": 9.0, "coverage_radius_m": 5.0}
        with pytest.raises(ValidationError, match="0.7"):
            validate_smoke_spacing_result(result)


class TestValidateHeatSpacingResult:
    """V58 FIX (BUG #3): heat spacing L3 validation was missing."""

    def test_valid_result_passes(self):
        result = compute_heat_detector_spacing(3.0, 100.0)
        validated = validate_heat_spacing_result(result)
        assert validated["layer3_validated"] is True

    def test_nan_rejected(self):
        result = {"spacing_m": float("nan"), "coverage_radius_m": 5.0}
        with pytest.raises(ComputationError, match="NaN"):
            validate_heat_spacing_result(result)

    # V121 FIX: Error message updated to say "absolute max"
    def test_exceeds_max_rejected(self):
        result = {"spacing_m": 20.0, "coverage_radius_m": 14.0}
        with pytest.raises(ValidationError, match="absolute max"):
            validate_heat_spacing_result(result)


class TestValidateBatteryResult:
    def test_valid_result_passes(self):
        result = compute_battery_capacity_ah(1.0, 2.0)
        validated = validate_battery_result(result)
        assert validated["layer3_validated"] is True

    def test_zero_ah_rejected(self):
        result = {"required_ah": 0.0, "ah_raw": 0.0}
        with pytest.raises(ComputationError, match="non-physical"):
            validate_battery_result(result)

    def test_negative_ah_rejected(self):
        result = {"required_ah": -1.0, "ah_raw": 1.0}
        with pytest.raises(ComputationError, match="non-physical"):
            validate_battery_result(result)

    def test_ah_less_than_raw_rejected(self):
        result = {"required_ah": 0.1, "ah_raw": 100.0}
        with pytest.raises(ValidationError, match="computation error"):
            validate_battery_result(result)


class TestValidateVoltageDropResult:
    def test_valid_result_passes(self):
        result = compute_voltage_drop(1.0, 100.0, "14")
        validated = validate_voltage_drop_result(result)
        assert validated["layer3_validated"] is True

    def test_negative_drop_rejected(self):
        result = {"voltage_drop_v": -1.0, "supply_voltage_v": 24.0}
        with pytest.raises(ComputationError, match="non-physical"):
            validate_voltage_drop_result(result)

    def test_drop_exceeds_supply(self):
        result = {"voltage_drop_v": 25.0, "supply_voltage_v": 24.0}
        with pytest.raises(ValidationError, match="no current would flow"):
            validate_voltage_drop_result(result)


# ═══════════════════════════════════════════════════════════════════════════════
# LAYER 4 — Audit Log Tests
# ═══════════════════════════════════════════════════════════════════════════════


class TestAuditEntry:
    def test_creation(self):
        entry = AuditEntry(
            timestamp_utc="2025-01-01T00:00:00.000Z",
            computation_type="test",
            input_data={"x": 1},
            formula_ref="NFPA 72 §X",
            output_data={"y": 2},
            result_hash="abc123",
            layer3_passed=True,
        )
        assert entry.computation_type == "test"
        assert entry.layer3_passed is True


class TestQOMNAuditLog:
    """V114 FIX: HMAC-SHA256 chain integrity."""

    def test_record_returns_entry(self):
        log = QOMNAuditLog()
        entry = log.record("test", {"x": 1}, "NFPA 72", {"y": 2}, layer3_passed=True)
        assert isinstance(entry, AuditEntry)
        assert entry.computation_type == "test"
        assert entry.layer3_passed is True

    def test_append_only(self):
        log = QOMNAuditLog()
        log.record("test1", {}, "", {})
        log.record("test2", {}, "", {})
        exported = log.export_json()
        assert exported["total_entries"] == 2

    def test_chain_integrity(self):
        log = QOMNAuditLog()
        log.record("test1", {"x": 1}, "§1", {"y": 1})
        log.record("test2", {"x": 2}, "§2", {"y": 2})
        assert log.verify_chain_integrity() is True

    def test_empty_log_integrity(self):
        log = QOMNAuditLog()
        assert log.verify_chain_integrity() is True

    def test_layer3_default_false(self):
        """V112: FAIL-SAFE — layer3 not passed until verified."""
        log = QOMNAuditLog()
        entry = log.record("test", {}, "", {})
        assert entry.layer3_passed is False

    def test_export_json_structure(self):
        log = QOMNAuditLog()
        log.record("test", {"x": 1}, "§1", {"y": 1}, layer3_passed=True)
        exported = log.export_json()
        assert "qomn_version" in exported
        assert "chain_hash" in exported
        assert "entries" in exported
        assert len(exported["entries"]) == 1

    def test_hmac_key_used_when_set(self):
        """V114 FIX: When FIREAI_QOMN_HMAC_KEY is set, use HMAC-SHA256."""
        os.environ["FIREAI_QOMN_HMAC_KEY"] = "test-secret-key-12345"
        try:
            log = QOMNAuditLog()
            log.record("test", {"x": 1}, "§1", {"y": 1})
            assert log.verify_chain_integrity() is True
        finally:
            del os.environ["FIREAI_QOMN_HMAC_KEY"]

    def test_hmac_key_produces_different_hash_than_sha256(self):
        os.environ["FIREAI_QOMN_HMAC_KEY"] = "test-secret-key-12345"
        try:
            log_hmac = QOMNAuditLog()
            log_hmac.record("test", {"x": 1}, "§1", {"y": 1})
            hmac_hash = log_hmac._chain_hash
        finally:
            del os.environ["FIREAI_QOMN_HMAC_KEY"]

        log_plain = QOMNAuditLog()
        log_plain.record("test", {"x": 1}, "§1", {"y": 1})
        plain_hash = log_plain._chain_hash
        assert hmac_hash != plain_hash


# ═══════════════════════════════════════════════════════════════════════════════
# QOMN KERNEL — Unified Interface Tests
# ═══════════════════════════════════════════════════════════════════════════════


class TestQOMNKernel:
    """Full L0→L4 pipeline tests."""

    def test_smoke_detector_spacing(self):
        kernel = QOMNKernel()
        result = kernel.smoke_detector_spacing(3.0)
        assert result["listed_spacing_m"] > 0
        assert result["layer3_validated"] is True

    def test_heat_detector_spacing(self):
        kernel = QOMNKernel()
        result = kernel.heat_detector_spacing(3.0, 100.0)
        assert result["spacing_m"] > 0
        assert result["layer3_validated"] is True

    def test_battery_capacity(self):
        kernel = QOMNKernel()
        result = kernel.battery_capacity(1.0, 2.0)
        assert result["required_ah"] > 0
        assert result["layer3_validated"] is True

    def test_voltage_drop(self):
        kernel = QOMNKernel()
        result = kernel.voltage_drop(1.0, 100.0, "14")
        assert result["voltage_drop_v"] > 0
        assert result["layer3_validated"] is True

    def test_audit_log_recorded(self):
        """V58 FIX (BUG #5): audit should record layer3_passed=True."""
        kernel = QOMNKernel()
        kernel.smoke_detector_spacing(3.0)
        audit = kernel.get_audit_log()
        assert audit["total_entries"] == 1
        # V58 FIX: layer3_passed should be True (not default False)
        assert audit["entries"][0]["layer3_passed"] is True

    def test_audit_integrity(self):
        kernel = QOMNKernel()
        kernel.smoke_detector_spacing(3.0)
        kernel.battery_capacity(1.0, 2.0)
        assert kernel.verify_audit_integrity() is True

    def test_multiple_computations(self):
        kernel = QOMNKernel()
        kernel.smoke_detector_spacing(3.0)
        kernel.heat_detector_spacing(3.0, 100.0)
        kernel.battery_capacity(1.0, 2.0)
        kernel.voltage_drop(1.0, 100.0, "14")
        audit = kernel.get_audit_log()
        assert audit["total_entries"] == 4

    def test_invalid_input_propagates(self):
        """Invalid input raises PhysicsGuardError, not silent wrong answer."""
        kernel = QOMNKernel()
        with pytest.raises(PhysicsGuardError):
            kernel.smoke_detector_spacing(25.0)  # > 18.288m


# ═══════════════════════════════════════════════════════════════════════════════
# Integration Scenarios
# ═══════════════════════════════════════════════════════════════════════════════


class TestIntegrationScenarios:
    """End-to-end scenarios representing real fire alarm engineering."""

    def test_office_floor_smoke_detection(self):
        """Typical office: 3m ceiling, 100m² area."""
        kernel = QOMNKernel()
        smoke = kernel.smoke_detector_spacing(3.0)
        assert smoke["listed_spacing_m"] == pytest.approx(9.1, rel=0.01)
        # Verify spacing and radius are reasonable for office use
        assert smoke["coverage_radius_m"] > 5.0  # R ≈ 6.4m for 3m ceiling
        # Verify at least 1 detector needed for 100m²
        coverage_area = smoke["coverage_radius_m"] ** 2 * math.pi
        n_detectors = math.ceil(100.0 / coverage_area)
        assert n_detectors >= 1

    def test_warehouse_battery_sizing(self):
        """Warehouse: 2A standby, 4A alarm, 24h + 5min."""
        kernel = QOMNKernel()
        result = kernel.battery_capacity(2.0, 4.0)
        # Raw: 2×24 + 4×(5/60) = 48.333 Ah raw
        # Required: (48.333 / 0.80) × 1.25 = 75.52 Ah
        assert result["required_ah"] > 70.0

    def test_long_nac_voltage_drop(self):
        """Long NAC: 2A, 300m, AWG14 — likely non-compliant."""
        kernel = QOMNKernel()
        result = kernel.voltage_drop(2.0, 300.0, "14")
        # V_drop = 2 × 2 × 300 × 0.00819 = 9.828V → 40.95% → non-compliant
        assert result["drop_pct"] > 10.0
        assert result["is_compliant"] is False

    def test_full_office_project(self):
        """Complete project: smoke + battery + voltage drop + audit."""
        kernel = QOMNKernel()
        kernel.smoke_detector_spacing(3.0)
        kernel.battery_capacity(1.5, 3.0)
        kernel.voltage_drop(0.5, 50.0, "14")
        assert kernel.verify_audit_integrity() is True
        audit = kernel.get_audit_log()
        assert audit["total_entries"] == 3
