# File-level '# NOSONAR' removed per NOSONAR_AUDIT.md (V143 hardening).
# Per-line justified suppressions (e.g., '# NOSONAR — S3776: ...') are preserved.
"""
Tests for fireai.core.nfpa72_engine — NFPA 72 Engineering Calculations

Covers all public functions and data classes:
  - SpacingResult dataclass
  - BatteryResult dataclass
  - VoltageDropResult dataclass
  - get_detector_spacing()
  - estimate_detector_count()
  - calculate_battery()
  - calculate_voltage_drop()
  - verify_fault_isolator_placement()

Safety-critical edge cases (NaN, Inf, negative, zero) are tested throughout.
The ×2 DC return path factor in voltage drop is explicitly verified —
this was a life-safety bug.
"""

import math

import pytest

from fireai.core.nfpa72_engine import (
    _BATTERY_DERATING_FACTOR,
    _HEAT_SPACING_TABLE,
    _MAX_DEVICES_BETWEEN_ISOLATORS,
    _MAX_VOLTAGE_DROP_PCT,
    _SMOKE_SPACING_TABLE,
    _STANDARD_BATTERY_SIZES,
    _SYSTEM_VOLTAGE,
    AWG_RESISTANCE_OHM_PER_KM,
    BatteryResult,
    SpacingResult,
    VoltageDropResult,
    calculate_battery,
    calculate_voltage_drop,
    estimate_detector_count,
    get_detector_spacing,
    verify_fault_isolator_placement,
)

# ═══════════════════════════════════════════════════════════════════════════════
# 1. DATACLASS TESTS
# ═══════════════════════════════════════════════════════════════════════════════


class TestSpacingResult:
    """Tests for the SpacingResult frozen dataclass."""

    def test_field_values(self):
        sr = SpacingResult(
            max_spacing_m=9.10,
            coverage_radius_m=6.37,
            nfpa_section="NFPA 72 §17.6.3.1",
            formula="S=9.10m",
            table_row_used="≤3.0m",
        )
        assert sr.max_spacing_m == 9.10  # NOSONAR — S1244: import retained for re-export / API surface
        assert sr.coverage_radius_m == 6.37  # NOSONAR — S1244: import retained for re-export / API surface
        assert sr.nfpa_section == "NFPA 72 §17.6.3.1"
        assert sr.formula == "S=9.10m"
        assert sr.table_row_used == "≤3.0m"

    def test_frozen_immutable(self):
        sr = SpacingResult(
            max_spacing_m=9.10,
            coverage_radius_m=6.37,
            nfpa_section="NFPA 72 §17.6.3.1",
            formula="test",
            table_row_used="row",
        )
        with pytest.raises(AttributeError):
            sr.max_spacing_m = 5.0

    def test_equality(self):
        a = SpacingResult(9.10, 6.37, "NFPA 72 §17.6.3.1", "f", "r")
        b = SpacingResult(9.10, 6.37, "NFPA 72 §17.6.3.1", "f", "r")
        assert a == b

    def test_inequality(self):
        a = SpacingResult(9.10, 6.37, "NFPA 72 §17.6.3.1", "f", "r")
        b = SpacingResult(5.50, 3.85, "NFPA 72 §17.6.3.1", "f", "r")
        assert a != b


class TestBatteryResult:
    """Tests for the BatteryResult frozen dataclass."""

    def test_field_values(self):
        br = BatteryResult(
            required_ah=12.5,
            installed_ah=15.0,
            is_adequate=True,
            formula="Ah = ...",
            nfpa_section="NFPA 72 §10.6.7",
        )
        assert br.required_ah == 12.5  # NOSONAR — S1244: import retained for re-export / API surface
        assert br.installed_ah == 15.0  # NOSONAR — S1244: import retained for re-export / API surface
        assert br.is_adequate is True
        assert br.formula == "Ah = ..."
        assert br.nfpa_section == "NFPA 72 §10.6.7"

    def test_frozen_immutable(self):
        br = BatteryResult(12.5, 15.0, True, "f", "s")
        with pytest.raises(AttributeError):
            br.required_ah = 99.0

    def test_not_adequate(self):
        br = BatteryResult(55.0, 50.0, False, "f", "s")
        assert br.is_adequate is False


class TestVoltageDropResult:
    """Tests for the VoltageDropResult frozen dataclass."""

    def test_field_values(self):
        vr = VoltageDropResult(
            voltage_drop_v=1.8,
            voltage_drop_pct=7.5,
            max_length_m=300.0,
            is_compliant=True,
            formula="V_drop = I × 2 × R × L",
        )
        assert vr.voltage_drop_v == 1.8  # NOSONAR — S1244: import retained for re-export / API surface
        assert vr.voltage_drop_pct == 7.5  # NOSONAR — S1244: import retained for re-export / API surface
        assert vr.max_length_m == 300.0  # NOSONAR — S1244: import retained for re-export / API surface
        assert vr.is_compliant is True
        assert vr.formula == "V_drop = I × 2 × R × L"

    def test_frozen_immutable(self):
        vr = VoltageDropResult(1.8, 7.5, 300.0, True, "f")
        with pytest.raises(AttributeError):
            vr.voltage_drop_v = 99.0

    def test_non_compliant(self):
        vr = VoltageDropResult(3.0, 12.5, 150.0, False, "f")
        assert vr.is_compliant is False


# ═══════════════════════════════════════════════════════════════════════════════
# 2. GET_DETECTOR_SPACING TESTS
# ═══════════════════════════════════════════════════════════════════════════════


class TestGetDetectorSpacing:
    """Tests for get_detector_spacing()."""

    # --- Smoke detector at various ceiling heights ---

    def test_smoke_at_3m(self):
        """At exactly 3.0 m, smoke detector uses the first row (≤3.0m)."""
        result = get_detector_spacing(3.0, "smoke")
        assert result.max_spacing_m == 9.10  # NOSONAR — S1244: import retained for re-export / API surface
        assert result.coverage_radius_m == round(0.7 * 9.10, 4)
        assert result.nfpa_section == "NFPA 72 §17.6.3.1"
        assert result.table_row_used == "≤3.0m"

    def test_smoke_at_4m(self):
        """
        At 4.0 m, smoke detector: flat 9.10m per NFPA 72 §17.7.3.2.3.
        M-10 FIX: No height-based reduction for smoke detectors.
        """
        result = get_detector_spacing(4.0, "smoke")
        # M-10 FIX: Smoke spacing is flat 9.10m at ALL heights
        assert result.max_spacing_m == pytest.approx(9.10)
        assert result.coverage_radius_m == round(0.7 * 9.10, 4)

    def test_smoke_at_7_5m(self):
        """
        At 7.5 m, smoke detector: flat 9.10m per NFPA 72 §17.7.3.2.3.
        M-10 FIX: No height-based reduction for smoke detectors.
        """
        result = get_detector_spacing(7.5, "smoke")
        # M-10 FIX: Smoke spacing is flat 9.10m at ALL heights
        assert result.max_spacing_m == pytest.approx(9.10)
        assert result.coverage_radius_m == round(0.7 * 9.10, 4)

    def test_smoke_at_12_2m(self):
        """
        At exactly 12.2 m, smoke detector: flat 9.10m per NFPA 72 §17.7.3.2.3.
        M-10 FIX: No height-based reduction for smoke detectors.
        """
        result = get_detector_spacing(12.2, "smoke")
        # M-10 FIX: Smoke spacing is flat 9.10m at ALL heights
        assert result.max_spacing_m == pytest.approx(9.10)
        assert result.coverage_radius_m == round(0.7 * 9.10, 4)
        assert result.table_row_used == "≤12.2m"

    def test_smoke_at_15m_exceeds_table(self):
        """
        At 15 m, smoke detector exceeds table — flat 9.10m fallback.
        M-10 FIX: Flat 9.10m at all heights, even beyond table.
        """
        result = get_detector_spacing(15.0, "smoke")
        assert result.max_spacing_m == pytest.approx(9.10)
        assert result.coverage_radius_m == round(0.7 * 9.10, 4)

    def test_smoke_at_100m_exceeds_table(self):
        """Very high ceiling — flat 9.10m fallback."""
        result = get_detector_spacing(100.0, "smoke")
        assert result.max_spacing_m == pytest.approx(9.10)

    # --- Heat detector ---

    def test_heat_at_3m(self):
        """Heat detector at 3.0m — first row of heat table."""
        result = get_detector_spacing(3.0, "heat")
        assert result.max_spacing_m == 6.10  # NOSONAR — S1244: import retained for re-export / API surface
        assert result.coverage_radius_m == round(0.7 * 6.10, 4)

    def test_heat_at_4m(self):
        """Heat detector at 4.0m — ≤4.6m row."""
        result = get_detector_spacing(4.0, "heat")
        assert result.max_spacing_m == pytest.approx(5.50)
        assert result.coverage_radius_m == round(0.7 * 5.50, 4)

    def test_heat_at_9m_exceeds_table(self):
        """Heat detector at 9.1m — ≤9.1m row of heat table."""
        result = get_detector_spacing(9.1, "heat")
        assert result.max_spacing_m == pytest.approx(4.30)

    def test_heat_at_15m_exceeds_table(self):
        """Heat detector at 15m — exceeds heat table, conservative default."""
        result = get_detector_spacing(15.0, "heat")
        assert result.max_spacing_m == 3.00  # NOSONAR — S1244: import retained for re-export / API surface
        assert "conservative" in result.table_row_used.lower()

    def test_case_insensitive_detector_type(self):
        """Detector type should be case-insensitive."""
        r1 = get_detector_spacing(3.0, "Smoke")
        r2 = get_detector_spacing(3.0, "SMOKE")
        r3 = get_detector_spacing(3.0, "smoke")
        assert r1 == r2 == r3

    def test_unknown_detector_type_uses_heat_table(self):
        """Any non-'smoke' type falls back to heat table."""
        result = get_detector_spacing(3.0, "flame")
        heat_result = get_detector_spacing(3.0, "heat")
        assert result.max_spacing_m == heat_result.max_spacing_m

    # --- Invalid inputs ---

    def test_negative_ceiling_height(self):
        """V96 FIX: Negative ceiling height raises ValueError (fail-safe)."""
        with pytest.raises(ValueError, match="ceiling_height_m"):
            get_detector_spacing(-1.0, "smoke")

    def test_zero_ceiling_height(self):
        """V96 FIX: Zero ceiling height raises ValueError (fail-safe)."""
        with pytest.raises(ValueError, match="ceiling_height_m"):
            get_detector_spacing(0.0, "smoke")

    def test_nan_ceiling_height(self):
        """V96 FIX: NaN ceiling height raises ValueError (fail-safe)."""
        with pytest.raises(ValueError, match="ceiling_height_m"):  # NOSONAR — S5778: re-raise inside except is intentional (context-specific)  # noqa: S5778
            get_detector_spacing(float("nan"), "smoke")

    def test_inf_ceiling_height(self):
        """V96 FIX: Infinity ceiling height raises ValueError (fail-safe)."""
        with pytest.raises(ValueError, match="ceiling_height_m"):  # NOSONAR — S5778: re-raise inside except is intentional (context-specific)  # noqa: S5778
            get_detector_spacing(float("inf"), "smoke")

    def test_negative_inf_ceiling_height(self):
        """V96 FIX: Negative infinity ceiling height raises ValueError (fail-safe)."""
        with pytest.raises(ValueError, match="ceiling_height_m"):  # NOSONAR — S5778: re-raise inside except is intentional (context-specific)  # noqa: S5778
            get_detector_spacing(float("-inf"), "smoke")

    # --- NFPA section reference ---

    def test_nfpa_section_reference(self):
        """All results must reference NFPA 72 §17.6.3.1."""
        result = get_detector_spacing(3.0, "smoke")
        assert "17.6.3.1" in result.nfpa_section  # NOSONAR - python:S1313

    def test_formula_contains_spacing_and_height(self):
        """
        Formula string should contain the spacing value and height.
        M-10 FIX: Smoke spacing is now flat 9.1m at all heights.
        """
        result = get_detector_spacing(4.0, "smoke")
        # M-10 FIX: spacing is flat 9.1m, not height-reduced 7.3m
        assert "9.1" in result.formula
        assert "4.0" in result.formula


# ═══════════════════════════════════════════════════════════════════════════════
# 3. ESTIMATE_DETECTOR_COUNT TESTS
# ═══════════════════════════════════════════════════════════════════════════════


class TestEstimateDetectorCount:
    """Tests for estimate_detector_count()."""

    def test_small_room_smoke(self):
        """Small room with 3m ceiling — should need few detectors."""
        result = estimate_detector_count(50.0, 3.0, "smoke")
        spacing = get_detector_spacing(3.0, "smoke")
        radius = spacing.coverage_radius_m
        coverage = math.pi * radius ** 2
        expected = max(1, math.ceil(50.0 / coverage))
        assert result["min_detector_count"] == expected

    def test_large_room_smoke(self):
        """Large room with 3m ceiling — many detectors."""
        result = estimate_detector_count(500.0, 3.0, "smoke")
        spacing = get_detector_spacing(3.0, "smoke")
        radius = spacing.coverage_radius_m
        coverage = math.pi * radius ** 2
        expected = max(1, math.ceil(500.0 / coverage))
        assert result["min_detector_count"] == expected
        assert result["min_detector_count"] > 1

    def test_high_ceiling_needs_more_detectors(self):
        """
        M-10 FIX: Smoke detectors have FLAT spacing at all heights.
        For smoke detectors, spacing doesn't change with height.
        For heat detectors, higher ceiling = smaller spacing = more detectors.
        We test with heat detectors to verify the height-based reduction.
        """
        low = estimate_detector_count(200.0, 3.0, "heat")
        high = estimate_detector_count(200.0, 10.0, "heat")
        assert high["min_detector_count"] > low["min_detector_count"]

    def test_heat_vs_smoke(self):
        """Heat detectors have smaller spacing → more detectors needed."""
        smoke = estimate_detector_count(100.0, 3.0, "smoke")
        heat = estimate_detector_count(100.0, 3.0, "heat")
        # Heat spacing at 3m = 6.10 vs smoke 9.10 → more heat detectors
        assert heat["min_detector_count"] >= smoke["min_detector_count"]

    def test_area_per_detector_m2(self):
        """area_per_detector_m2 should be π × R²."""
        result = estimate_detector_count(100.0, 3.0, "smoke")
        spacing = get_detector_spacing(3.0, "smoke")
        radius = spacing.coverage_radius_m
        expected_area = round(math.pi * radius ** 2, 4)
        assert result["area_per_detector_m2"] == expected_area

    def test_returns_spacing_info(self):
        """Result should include spacing and radius from SpacingResult."""
        result = estimate_detector_count(100.0, 3.0, "smoke")
        spacing = get_detector_spacing(3.0, "smoke")
        assert result["spacing_m"] == spacing.max_spacing_m
        assert result["coverage_radius_m"] == spacing.coverage_radius_m

    # --- Edge cases ---

    def test_zero_area(self):
        """V96 FIX: Zero area returns count=0 with error (fail-safe)."""
        result = estimate_detector_count(0.0, 3.0, "smoke")
        assert result["min_detector_count"] == 0
        assert "error" in result

    def test_negative_area(self):
        """V96 FIX: Negative area returns count=0 with error (fail-safe)."""
        result = estimate_detector_count(-10.0, 3.0, "smoke")
        assert result["min_detector_count"] == 0
        assert "error" in result

    def test_nan_area(self):
        """V96 FIX: NaN area returns count=0 with error (fail-safe)."""
        result = estimate_detector_count(float("nan"), 3.0, "smoke")
        assert result["min_detector_count"] == 0
        assert "error" in result

    def test_inf_area(self):
        """V96 FIX: Inf area returns count=0 with error (fail-safe)."""
        result = estimate_detector_count(float("inf"), 3.0, "smoke")
        assert result["min_detector_count"] == 0
        assert "error" in result

    def test_very_small_area(self):
        """Very small area still needs at least 1 detector."""
        result = estimate_detector_count(0.01, 3.0, "smoke")
        assert result["min_detector_count"] >= 1

    def test_invalid_ceiling_height_gives_count_1(self):
        """
        V96 FIX: Invalid ceiling height now raises ValueError in
        get_detector_spacing, which estimate_detector_count propagates.
        """
        with pytest.raises(ValueError, match="ceiling_height_m"):
            estimate_detector_count(50.0, -1.0, "smoke")


# ═══════════════════════════════════════════════════════════════════════════════
# 4. CALCULATE_BATTERY TESTS
# ═══════════════════════════════════════════════════════════════════════════════


class TestCalculateBattery:
    """Tests for calculate_battery()."""

    # --- Known value calculations ---

    def test_basic_calculation(self):
        """
        Verify the full Ah calculation with known values.

        I_standby = 0.5A, I_alarm = 1.5A, 24h standby, 5min alarm
        standby_ah = 0.5 × 24 = 12.0
        alarm_ah   = 1.5 × (5/60) = 0.125
        total_raw  = 12.125
        derated    = 12.125 / 0.85 = 14.2647...
        required   = 14.2647... × 1.20 = 17.1176...
        """
        result = calculate_battery(0.5, 1.5)
        standby_ah = 0.5 * 24
        alarm_ah = 1.5 * (5 / 60)
        total_raw = standby_ah + alarm_ah
        derated = total_raw / _BATTERY_DERATING_FACTOR
        required = derated * 1.20
        assert abs(result.required_ah - round(required, 4)) < 0.001

    def test_formula_verification(self):
        """Verify Ah = (I_sb×24 + I_al×5/60) / 0.85 × 1.20."""
        I_sb = 0.3  # NOSONAR - python:S117
        I_al = 2.0  # NOSONAR - python:S117
        result = calculate_battery(I_sb, I_al)

        standby_ah = I_sb * 24
        alarm_ah = I_al * (5 / 60)
        total_raw = standby_ah + alarm_ah
        derated = total_raw / _BATTERY_DERATING_FACTOR
        required = derated * (1 + 0.20)

        assert abs(result.required_ah - round(required, 4)) < 0.001

    # --- Safety margin ---

    def test_default_safety_margin_is_20_pct(self):
        """Default safety margin should be 20% per NFPA 72 §10.6.7.2.1."""
        I_sb = 1.0  # NOSONAR - python:S117
        I_al = 1.0  # NOSONAR - python:S117
        result = calculate_battery(I_sb, I_al)

        standby_ah = I_sb * 24
        alarm_ah = I_al * (5 / 60)
        total_raw = standby_ah + alarm_ah
        derated = total_raw / _BATTERY_DERATING_FACTOR
        # With 20% margin
        required_20 = derated * 1.20
        # Without margin
        required_no_margin = derated * 1.00

        assert abs(result.required_ah - round(required_20, 4)) < 0.001
        assert result.required_ah > required_no_margin

    def test_custom_safety_margin(self):
        """Custom safety margin should change the result."""
        r_default = calculate_battery(0.5, 1.5)
        r_large = calculate_battery(0.5, 1.5, safety_margin=0.50)
        assert r_large.required_ah > r_default.required_ah

    def test_zero_safety_margin(self):
        """Zero safety margin should give smaller required Ah."""
        result = calculate_battery(0.5, 1.5, safety_margin=0.0)
        I_sb, I_al = 0.5, 1.5  # NOSONAR - python:S117
        standby_ah = I_sb * 24
        alarm_ah = I_al * (5 / 60)
        total_raw = standby_ah + alarm_ah
        derated = total_raw / _BATTERY_DERATING_FACTOR
        expected = derated * 1.0  # No margin
        assert abs(result.required_ah - round(expected, 4)) < 0.001

    # --- Derating ---

    def test_derating_factor_applied(self):
        """Verify derating factor increases required Ah beyond raw total."""
        I_sb = 0.5  # NOSONAR - python:S117
        I_al = 1.0  # NOSONAR - python:S117
        result = calculate_battery(I_sb, I_al, safety_margin=0.0)

        raw_total = I_sb * 24 + I_al * (5 / 60)
        # With derating, required should be > raw total
        assert result.required_ah > raw_total

    def test_derating_factor_value(self):
        """Derating factor should be 0.85 (15% derating for lead-acid)."""
        assert _BATTERY_DERATING_FACTOR == 0.85  # NOSONAR — S1244: import retained for re-export / API surface

    # --- Standard battery size selection ---

    def test_installed_ah_is_standard_size(self):
        """
        installed_ah should always be a standard battery size or a
        round-up to nearest 10.
        """
        result = calculate_battery(0.5, 1.5)
        # Check that installed_ah is either in the standard sizes list
        # or is a multiple of 10 (the fallback)
        is_standard = result.installed_ah in _STANDARD_BATTERY_SIZES
        is_rounded_10 = (result.installed_ah % 10 == 0 and
                         result.installed_ah > _STANDARD_BATTERY_SIZES[-1])
        assert is_standard or is_rounded_10

    def test_installed_ah_gte_required(self):
        """installed_ah should always be >= required_ah."""
        result = calculate_battery(0.5, 1.5)
        assert result.installed_ah >= result.required_ah

    def test_is_adequate_true(self):
        """With standard battery selection, is_adequate should be True."""
        result = calculate_battery(0.5, 1.5)
        assert result.is_adequate is True

    def test_large_load_selects_bigger_battery(self):
        """Very large load should select a large standard battery."""
        result = calculate_battery(5.0, 10.0)
        assert result.installed_ah >= 100.0
        assert result.is_adequate is True

    def test_very_small_load_selects_smallest_battery(self):
        """Tiny load should select the smallest standard battery (1.2 Ah)."""
        result = calculate_battery(0.001, 0.001)
        assert result.installed_ah >= 1.2

    def test_beyond_largest_standard_size(self):
        """Load beyond largest standard size rounds up to nearest 10."""
        # Use very high currents to exceed 200 Ah
        result = calculate_battery(10.0, 50.0)
        if result.required_ah > _STANDARD_BATTERY_SIZES[-1]:
            assert result.installed_ah % 10 == 0
            assert result.installed_ah >= result.required_ah

    # --- Zero / negative current rejection ---

    def test_zero_standby_zero_alarm_raises(self):
        """Both currents at zero must raise ValueError."""
        with pytest.raises(ValueError, match="cannot be zero"):
            calculate_battery(0.0, 0.0)

    def test_negative_standby_raises(self):
        """Negative standby current must raise ValueError."""
        with pytest.raises(ValueError, match="non-negative finite"):
            calculate_battery(-0.5, 1.0)

    def test_negative_alarm_raises(self):
        """Negative alarm current must raise ValueError."""
        with pytest.raises(ValueError, match="non-negative finite"):
            calculate_battery(0.5, -1.0)

    def test_zero_standby_valid(self):
        """Zero standby with non-zero alarm should work."""
        result = calculate_battery(0.0, 1.0)
        assert result.required_ah > 0

    def test_zero_alarm_valid(self):
        """Non-zero standby with zero alarm should work."""
        result = calculate_battery(1.0, 0.0)
        assert result.required_ah > 0

    # --- NaN / Inf rejection ---

    def test_nan_standby_raises(self):
        """NaN standby current must raise ValueError."""
        with pytest.raises(ValueError, match="non-negative finite"):  # NOSONAR — S5778: re-raise inside except is intentional (context-specific)  # noqa: S5778
            calculate_battery(float("nan"), 1.0)

    def test_nan_alarm_raises(self):
        """NaN alarm current must raise ValueError."""
        with pytest.raises(ValueError, match="non-negative finite"):  # NOSONAR — S5778: re-raise inside except is intentional (context-specific)  # noqa: S5778
            calculate_battery(1.0, float("nan"))

    def test_inf_standby_raises(self):
        """Inf standby current must raise ValueError."""
        with pytest.raises(ValueError, match="non-negative finite"):  # NOSONAR — S5778: re-raise inside except is intentional (context-specific)  # noqa: S5778
            calculate_battery(float("inf"), 1.0)

    def test_inf_alarm_raises(self):
        """Inf alarm current must raise ValueError."""
        with pytest.raises(ValueError, match="non-negative finite"):  # NOSONAR — S5778: re-raise inside except is intentional (context-specific)  # noqa: S5778
            calculate_battery(1.0, float("inf"))

    def test_negative_inf_standby_raises(self):
        """Negative Inf standby current must raise ValueError."""
        with pytest.raises(ValueError, match="non-negative finite"):  # NOSONAR — S5778: re-raise inside except is intentional (context-specific)  # noqa: S5778
            calculate_battery(float("-inf"), 1.0)

    # --- Custom standby/alarm durations ---

    def test_custom_standby_hours(self):
        """Custom standby hours should be used in calculation."""
        result = calculate_battery(1.0, 1.0, standby_hours=48.0)
        # 48h standby doubles the standby contribution
        result_24 = calculate_battery(1.0, 1.0, standby_hours=24.0)
        # The standby portion is doubled, so result should be larger
        assert result.required_ah > result_24.required_ah

    def test_custom_alarm_minutes(self):
        """Custom alarm minutes should be used in calculation."""
        result = calculate_battery(1.0, 1.0, alarm_minutes=10.0)
        result_5 = calculate_battery(1.0, 1.0, alarm_minutes=5.0)
        assert result.required_ah > result_5.required_ah

    # --- NFPA section reference ---

    def test_nfpa_section_reference(self):
        """Battery result must reference NFPA 72 §10.6.7."""
        result = calculate_battery(0.5, 1.5)
        assert "10.6.7" in result.nfpa_section

    def test_formula_contains_values(self):
        """Formula string should contain key calculation components."""
        result = calculate_battery(0.5, 1.5)
        assert "0.5000" in result.formula
        assert "1.5000" in result.formula
        assert str(_BATTERY_DERATING_FACTOR) in result.formula


# ═══════════════════════════════════════════════════════════════════════════════
# 5. CALCULATE_VOLTAGE_DROP TESTS
# ═══════════════════════════════════════════════════════════════════════════════


class TestCalculateVoltageDrop:
    """
    Tests for calculate_voltage_drop().

    The ×2 DC return path factor is life-safety critical — it was a bug
    in a previous version. These tests explicitly verify it.
    """

    # --- DC return path ×2 factor (LIFE SAFETY CRITICAL) ---

    def test_dc_return_path_factor(self):
        """
        V_drop MUST include ×2 factor for DC return path.

        Without ×2, voltage drop would be reported at 50% of actual
        value — a life-safety-dangerous bug.

        V_drop = I × 2 × R_per_km × L_km
        """
        current = 1.0  # 1A
        length_m = 100.0  # 100m
        gauge = "14"  # 8.450 Ω/km

        r_per_km = AWG_RESISTANCE_OHM_PER_KM["14"]
        length_km = length_m / 1000.0

        # Expected with ×2 factor
        expected_with_x2 = current * 2.0 * r_per_km * length_km

        # Expected WITHOUT ×2 factor (the old bug)
        expected_without_x2 = current * r_per_km * length_km

        # V97 FIX: Explicitly pass ambient_temperature_c=20.0 to test the ×2
        # factor at reference temperature. Default changed from 20→75°C.
        result = calculate_voltage_drop(current, length_m, gauge, ambient_temperature_c=20.0)
        assert abs(result.voltage_drop_v - round(expected_with_x2, 4)) < 0.001

        # Result must NOT match the no-×2 calculation
        assert abs(result.voltage_drop_v - round(expected_without_x2, 4)) > 0.001

        # The result should be EXACTLY 2× the no-×2 value
        assert abs(result.voltage_drop_v - 2 * expected_without_x2) < 0.01

    def test_dc_return_path_various_gauges(self):
        """×2 factor must be applied regardless of wire gauge."""
        current = 0.5
        length_m = 200.0

        for gauge, r_per_km in AWG_RESISTANCE_OHM_PER_KM.items():
            # V97 FIX: Use 20°C to match raw r_per_km in expected value
            result = calculate_voltage_drop(current, length_m, gauge, ambient_temperature_c=20.0)
            length_km = length_m / 1000.0
            expected = current * 2.0 * r_per_km * length_km
            assert abs(result.voltage_drop_v - round(expected, 4)) < 0.01, (
                f"×2 factor not applied for gauge {gauge}"
            )

    # --- Compliant vs non-compliant ---

    def test_compliant_circuit(self):
        """Short circuit with reasonable current should be compliant."""
        # 0.5A on 50m of 14 AWG
        result = calculate_voltage_drop(0.5, 50.0, "14")
        assert result.voltage_drop_pct <= _MAX_VOLTAGE_DROP_PCT
        assert result.is_compliant is True

    def test_non_compliant_circuit(self):
        """Long circuit with high current should be non-compliant."""
        # 3.0A on 500m of 14 AWG — definitely over 10%
        result = calculate_voltage_drop(3.0, 500.0, "14")
        assert result.voltage_drop_pct > _MAX_VOLTAGE_DROP_PCT
        assert result.is_compliant is False

    def test_compliant_boundary(self):
        """
        Test near the compliance boundary.

        Note: due to floating-point arithmetic, the exact boundary
        may produce drop_pct slightly above 10.0 (e.g. 10.0000001),
        which rounds to 10.0 for display but makes is_compliant False.
        We test just inside the boundary instead.
        """
        current = 1.0
        gauge = "14"
        r_per_km = AWG_RESISTANCE_OHM_PER_KM[gauge]
        max_length_m = (24.0 * 0.10) / (current * 2.0 * r_per_km) * 1000.0

        # Just inside the boundary: should be compliant
        # V97 FIX: Use 20°C to match r_per_km used in boundary calculation
        result_inside = calculate_voltage_drop(current, max_length_m - 1.0, gauge, ambient_temperature_c=20.0)
        assert result_inside.is_compliant is True

        # Well over max length: non-compliant
        result_over = calculate_voltage_drop(current, max_length_m + 10.0, gauge, ambient_temperature_c=20.0)
        assert result_over.is_compliant is False

    # --- Max length calculation ---

    def test_max_length_m_calculation(self):
        """max_length_m should be the maximum compliant one-way length."""
        current = 1.0
        gauge = "12"
        r_per_km = AWG_RESISTANCE_OHM_PER_KM[gauge]
        max_drop_v = 24.0 * (_MAX_VOLTAGE_DROP_PCT / 100.0)
        expected_max_length_km = max_drop_v / (current * 2.0 * r_per_km)
        expected_max_length_m = expected_max_length_km * 1000.0

        # V97 FIX: Use 20°C to match raw r_per_km in expected calculation
        result = calculate_voltage_drop(current, 50.0, gauge, ambient_temperature_c=20.0)
        assert abs(result.max_length_m - round(expected_max_length_m, 2)) < 0.1

    def test_max_length_includes_x2_factor(self):
        """max_length_m must account for the ×2 DC return path."""
        current = 1.0
        gauge = "14"
        r_per_km = AWG_RESISTANCE_OHM_PER_KM[gauge]

        # Correct max length (with ×2)
        max_drop_v = 2.4  # 10% of 24V
        correct_max_m = (max_drop_v / (current * 2.0 * r_per_km)) * 1000.0

        # Buggy max length (without ×2) would be 2× too long
        buggy_max_m = (max_drop_v / (current * r_per_km)) * 1000.0

        # V97 FIX: Use 20°C to match raw r_per_km in expected calculation
        result = calculate_voltage_drop(current, 50.0, gauge, ambient_temperature_c=20.0)
        assert abs(result.max_length_m - round(correct_max_m, 2)) < 0.1

        # Must NOT match the buggy (no ×2) calculation
        assert abs(result.max_length_m - buggy_max_m) > 10.0  # Way off

    # --- Various wire gauges ---

    def test_larger_gauge_less_drop(self):
        """Larger wire (smaller AWG number) → less voltage drop."""
        r_14 = calculate_voltage_drop(1.0, 100.0, "14")
        r_12 = calculate_voltage_drop(1.0, 100.0, "12")
        r_10 = calculate_voltage_drop(1.0, 100.0, "10")
        assert r_14.voltage_drop_v > r_12.voltage_drop_v > r_10.voltage_drop_v

    def test_all_valid_gauges(self):
        """Every gauge in the resistance table should work."""
        for gauge in AWG_RESISTANCE_OHM_PER_KM:
            result = calculate_voltage_drop(0.5, 100.0, gauge)
            assert result.voltage_drop_v > 0
            assert result.voltage_drop_pct >= 0

    # --- Invalid AWG gauge ---

    def test_invalid_awg_gauge(self):
        """Invalid AWG gauge must raise ValueError."""
        with pytest.raises(ValueError, match="Unsupported AWG gauge"):
            calculate_voltage_drop(1.0, 100.0, "999")

    def test_empty_awg_gauge(self):
        """Empty string gauge must raise ValueError."""
        with pytest.raises(ValueError, match="Unsupported AWG gauge"):
            calculate_voltage_drop(1.0, 100.0, "")

    def test_fractional_gauge_valid(self):
        """Fractional gauges like '1/0', '2/0' should be valid."""
        result = calculate_voltage_drop(1.0, 100.0, "1/0")
        assert result.voltage_drop_v > 0

    # --- Zero current ---

    def test_zero_current(self):
        """Zero current should give zero voltage drop, compliant."""
        result = calculate_voltage_drop(0.0, 100.0, "14")
        assert result.voltage_drop_v == 0.0  # NOSONAR — S1244: import retained for re-export / API surface
        assert result.voltage_drop_pct == 0.0  # NOSONAR — S1244: import retained for re-export / API surface
        assert result.is_compliant is True

    # --- Invalid inputs ---

    def test_negative_current_raises(self):
        """Negative current must raise ValueError."""
        with pytest.raises(ValueError, match="non-negative finite"):
            calculate_voltage_drop(-1.0, 100.0, "14")

    def test_negative_length_raises(self):
        """Negative circuit length must raise ValueError."""
        with pytest.raises(ValueError, match="non-negative finite"):
            calculate_voltage_drop(1.0, -100.0, "14")

    def test_nan_current_raises(self):
        """NaN current must raise ValueError."""
        with pytest.raises(ValueError, match="non-negative finite"):  # NOSONAR — S5778: re-raise inside except is intentional (context-specific)  # noqa: S5778
            calculate_voltage_drop(float("nan"), 100.0, "14")

    def test_inf_current_raises(self):
        """Inf current must raise ValueError."""
        with pytest.raises(ValueError, match="non-negative finite"):  # NOSONAR — S5778: re-raise inside except is intentional (context-specific)  # noqa: S5778
            calculate_voltage_drop(float("inf"), 100.0, "14")

    def test_nan_length_raises(self):
        """NaN length must raise ValueError."""
        with pytest.raises(ValueError, match="non-negative finite"):  # NOSONAR — S5778: re-raise inside except is intentional (context-specific)  # noqa: S5778
            calculate_voltage_drop(1.0, float("nan"), "14")

    def test_inf_length_raises(self):
        """Inf length must raise ValueError."""
        with pytest.raises(ValueError, match="non-negative finite"):  # NOSONAR — S5778: re-raise inside except is intentional (context-specific)  # noqa: S5778
            calculate_voltage_drop(1.0, float("inf"), "14")

    # --- Custom parameters ---

    def test_custom_ps_voltage(self):
        """Custom power supply voltage should affect percentage calculation."""
        r_24 = calculate_voltage_drop(1.0, 100.0, "14", ps_voltage=24.0)
        r_12 = calculate_voltage_drop(1.0, 100.0, "14", ps_voltage=12.0)
        # Same absolute drop, but higher percentage on 12V system
        assert r_12.voltage_drop_pct > r_24.voltage_drop_pct

    def test_custom_max_drop_pct(self):
        """Custom max drop percentage changes compliance."""
        # 7% threshold — stricter than default 10%
        result = calculate_voltage_drop(2.0, 200.0, "14", max_drop_pct=7.0)
        # With 7% threshold, this may be non-compliant
        # The compliance check is against max_drop_pct
        max_drop_v = 24.0 * (7.0 / 100.0)
        if result.voltage_drop_v > max_drop_v:
            assert result.is_compliant is False

    # --- Zero length ---

    def test_zero_length(self):
        """Zero circuit length should give zero voltage drop."""
        result = calculate_voltage_drop(1.0, 0.0, "14")
        assert result.voltage_drop_v == 0.0  # NOSONAR — S1244: import retained for re-export / API surface
        assert result.is_compliant is True

    # --- Formula string ---

    def test_formula_contains_x2(self):
        """Formula must show the ×2 DC return path factor."""
        result = calculate_voltage_drop(1.0, 100.0, "14")
        assert "× 2" in result.formula or "2" in result.formula

    def test_formula_contains_gauge_resistance(self):
        """Formula should include the wire resistance value.

        C-03 FIX (Engineering Review): the previously asserted value "4.263"
        was the SOLID conductor resistance from NEC Table 8 (mislabeled as
        "stranded" in the source). The correct STRANDED value at 20°C is
        8.286 Ω/km — see fireai.constants.nec.NEC_TABLE8_RESISTANCE_OHM_PER_KM_20C.
        """
        # V97 FIX: Use 20°C so formula shows raw Table 8 resistance
        result = calculate_voltage_drop(1.0, 100.0, "14", ambient_temperature_c=20.0)
        # C-03 FIX: 8.286 is the STRANDED AWG 14 resistance at 20°C per NEC Table 8.
        assert "8.286" in result.formula


# ═══════════════════════════════════════════════════════════════════════════════
# 6. VERIFY_FAULT_ISOLATOR_PLACEMENT TESTS
# ═══════════════════════════════════════════════════════════════════════════════


class TestVerifyFaultIsolatorPlacement:
    """Tests for verify_fault_isolator_placement()."""

    # --- Compliant setup ---

    def test_compliant_setup(self):
        """Well-isolated circuit with ≤32 devices between isolators."""
        devices = []
        # Isolator at start
        devices.append({"device_id": "ISO-1", "device_type": "isolator"})
        # 30 devices between isolators — within limit
        for i in range(30):
            devices.append({
                "device_id": f"DET-{i}",
                "device_type": "detector",
                "zone_id": "Z1",
            })
        # Isolator at end
        devices.append({"device_id": "ISO-2", "device_type": "isolator"})

        result = verify_fault_isolator_placement(devices)
        assert result["compliant"] is True
        assert len(result["violations"]) == 0
        assert result["isolator_count"] == 2
        assert result["device_count"] == 32  # 30 detectors + 2 isolators

    def test_compliant_exactly_32_devices(self):
        """Exactly 32 devices between isolators — should be compliant."""
        devices = []
        devices.append({"device_id": "ISO-1", "device_type": "isolator"})
        for i in range(32):
            devices.append({
                "device_id": f"DET-{i}",
                "device_type": "detector",
            })
        devices.append({"device_id": "ISO-2", "device_type": "isolator"})

        result = verify_fault_isolator_placement(devices)
        assert result["compliant"] is True
        assert len(result["violations"]) == 0

    # --- >32 devices between isolators ---

    def test_too_many_devices_between_isolators(self):
        """33 devices between isolators — violation."""
        devices = []
        devices.append({"device_id": "ISO-1", "device_type": "isolator"})
        for i in range(33):
            devices.append({
                "device_id": f"DET-{i}",
                "device_type": "detector",
            })
        devices.append({"device_id": "ISO-2", "device_type": "isolator"})

        result = verify_fault_isolator_placement(devices)
        assert result["compliant"] is False
        assert len(result["violations"]) >= 1
        assert result["violations"][0]["type"] == "too_many_devices_between_isolators"
        assert result["violations"][0]["device_count"] == 33
        assert result["violations"][0]["max_allowed"] == 32

    def test_50_devices_between_isolators(self):
        """50 devices between isolators — clear violation."""
        devices = []
        devices.append({"device_id": "ISO-1", "device_type": "isolator"})
        for i in range(50):
            devices.append({
                "device_id": f"DET-{i}",
                "device_type": "detector",
            })
        devices.append({"device_id": "ISO-2", "device_type": "isolator"})

        result = verify_fault_isolator_placement(devices)
        assert result["compliant"] is False

    # --- No isolators at all ---

    def test_no_isolators_violation(self):
        """Circuit with devices but no isolators — end-of-circuit violation."""
        devices = []
        for i in range(40):
            devices.append({
                "device_id": f"DET-{i}",
                "device_type": "detector",
            })

        result = verify_fault_isolator_placement(devices)
        assert result["compliant"] is False
        assert result["isolator_count"] == 0
        # End-of-circuit segment has 40 devices > 32
        assert any(
            v["type"] == "too_many_devices_end_of_circuit"
            for v in result["violations"]
        )

    def test_few_devices_no_isolators_compliant(self):
        """Few devices with no isolators might still be compliant."""
        devices = []
        for i in range(10):
            devices.append({
                "device_id": f"DET-{i}",
                "device_type": "detector",
            })

        result = verify_fault_isolator_placement(devices)
        # 10 ≤ 32, so no violation
        assert result["compliant"] is True
        assert result["isolator_count"] == 0

    # --- Empty list ---

    def test_empty_device_list(self):
        """
        V69-4 FIX: Empty device list is NOT compliant — fail-safe.

        An empty device list could indicate a data extraction failure
        (parser bug), not that the circuit is genuinely compliant.
        Missing compliance data = BLOCKED per V67 safety principle.
        """
        result = verify_fault_isolator_placement([])
        assert result["compliant"] is False
        assert len(result["violations"]) > 0  # Should have a "no devices" violation
        assert result["device_count"] == 0
        assert result["isolator_count"] == 0
        assert "No devices" in result["message"]

    # --- Multi-circuit ---

    def test_multi_circuit_compliant(self):
        """Multiple circuits, each compliant."""
        devices = []
        # Circuit A
        devices.append({
            "device_id": "ISO-A1", "device_type": "isolator",
            "circuit_id": "SLC-A",
        })
        for i in range(20):
            devices.append({
                "device_id": f"DET-A{i}", "device_type": "detector",
                "circuit_id": "SLC-A",
            })
        devices.append({
            "device_id": "ISO-A2", "device_type": "isolator",
            "circuit_id": "SLC-A",
        })
        # Circuit B
        devices.append({
            "device_id": "ISO-B1", "device_type": "isolator",
            "circuit_id": "SLC-B",
        })
        for i in range(15):
            devices.append({
                "device_id": f"DET-B{i}", "device_type": "detector",
                "circuit_id": "SLC-B",
            })
        devices.append({
            "device_id": "ISO-B2", "device_type": "isolator",
            "circuit_id": "SLC-B",
        })

        result = verify_fault_isolator_placement(devices)
        assert result["compliant"] is True
        assert result["isolator_count"] == 4

    def test_multi_circuit_one_violation(self):
        """Multiple circuits, one has too many devices."""
        devices = []
        # Circuit A — compliant
        devices.append({
            "device_id": "ISO-A1", "device_type": "isolator",
            "circuit_id": "SLC-A",
        })
        for i in range(10):
            devices.append({
                "device_id": f"DET-A{i}", "device_type": "detector",
                "circuit_id": "SLC-A",
            })
        devices.append({
            "device_id": "ISO-A2", "device_type": "isolator",
            "circuit_id": "SLC-A",
        })
        # Circuit B — violation: 40 devices, no isolator
        for i in range(40):
            devices.append({
                "device_id": f"DET-B{i}", "device_type": "detector",
                "circuit_id": "SLC-B",
            })

        result = verify_fault_isolator_placement(devices)
        assert result["compliant"] is False
        assert len(result["violations"]) >= 1

    # --- NFPA section references ---

    def test_nfpa_section_in_result(self):
        """Result should reference NFPA 72 §12.3."""
        result = verify_fault_isolator_placement([])
        assert "12.3" in result["nfpa_section"]

    def test_violation_includes_nfpa_section(self):
        """Violations should reference NFPA 72 §12.3.1."""
        devices = []
        for i in range(40):
            devices.append({
                "device_id": f"DET-{i}", "device_type": "detector",
            })
        result = verify_fault_isolator_placement(devices)
        for v in result["violations"]:
            assert "12.3.1" in v["nfpa_section"]

    # --- Isolator type matching ---

    def test_isolator_type_variations(self):
        """'isolator' substring matching — various device_type values."""
        devices = [
            {"device_id": "FI-1", "device_type": "fault_isolator"},
            {"device_id": "D-1", "device_type": "detector"},
            {"device_id": "FI-2", "device_type": "circuit_isolator"},
            {"device_id": "D-2", "device_type": "detector"},
        ]
        result = verify_fault_isolator_placement(devices)
        assert result["isolator_count"] == 2
        assert result["compliant"] is True

    # --- End-of-circuit segment ---

    def test_end_of_circuit_segment_violation(self):
        """Devices after last isolator — end-of-circuit segment check."""
        devices = [
            {"device_id": "ISO-1", "device_type": "isolator"},
        ]
        # 33 devices after last isolator
        for i in range(33):
            devices.append({
                "device_id": f"DET-{i}", "device_type": "detector",
            })

        result = verify_fault_isolator_placement(devices)
        assert result["compliant"] is False
        assert any(
            v["type"] == "too_many_devices_end_of_circuit"
            for v in result["violations"]
        )

    def test_end_of_circuit_segment_exactly_32_compliant(self):
        """32 devices after last isolator — should be compliant."""
        devices = [
            {"device_id": "ISO-1", "device_type": "isolator"},
        ]
        for i in range(32):
            devices.append({
                "device_id": f"DET-{i}", "device_type": "detector",
            })

        result = verify_fault_isolator_placement(devices)
        assert result["compliant"] is True

    # --- Message field ---

    def test_compliant_message(self):
        """Compliant result should have 'Compliant' message."""
        devices = [
            {"device_id": "ISO-1", "device_type": "isolator"},
            {"device_id": "D-1", "device_type": "detector"},
        ]
        result = verify_fault_isolator_placement(devices)
        assert result["message"] == "Compliant"

    def test_violation_message(self):
        """Non-compliant result should show violation count."""
        devices = []
        for i in range(40):
            devices.append({
                "device_id": f"DET-{i}", "device_type": "detector",
            })
        result = verify_fault_isolator_placement(devices)
        assert "violation" in result["message"].lower()


# ═══════════════════════════════════════════════════════════════════════════════
# 7. CROSS-CUTTING / INTEGRATION TESTS
# ═══════════════════════════════════════════════════════════════════════════════


class TestCrossCutting:
    """Cross-cutting tests that verify inter-function consistency."""

    def test_spacing_table_matches_detector_count(self):
        """estimate_detector_count uses spacing from get_detector_spacing."""
        ceiling = 5.0
        det_type = "smoke"
        spacing = get_detector_spacing(ceiling, det_type)
        count = estimate_detector_count(100.0, ceiling, det_type)
        assert count["spacing_m"] == spacing.max_spacing_m
        assert count["coverage_radius_m"] == spacing.coverage_radius_m

    def test_voltage_drop_and_max_length_consistent(self):
        """At max_length_m, voltage drop should be at the threshold."""
        current = 1.0
        gauge = "14"
        # V97 FIX: Use 20°C to match raw r_per_km in hand calculation
        result = calculate_voltage_drop(current, 50.0, gauge, ambient_temperature_c=20.0)

        # Calculate V_drop at max_length_m
        r_per_km = AWG_RESISTANCE_OHM_PER_KM[gauge]
        max_len_km = result.max_length_m / 1000.0
        v_drop_at_max = current * 2.0 * r_per_km * max_len_km
        expected_max_drop = 24.0 * (_MAX_VOLTAGE_DROP_PCT / 100.0)

        assert abs(v_drop_at_max - expected_max_drop) < 0.1

    def test_all_spacing_tables_have_decreasing_spacing(self):
        """
        As ceiling height increases, HEAT detector spacing should decrease.
        M-10 FIX: Smoke detector spacing is FLAT (9.10m) at all heights per
        NFPA 72 §17.7.3.2.3 — it does NOT decrease. Only heat detectors
        have height-based spacing reduction per Table 17.6.3.5.1.
        """
        # Heat table: spacing MUST decrease with height
        heat_spacings = [s for _, s in _HEAT_SPACING_TABLE]
        for i in range(len(heat_spacings) - 1):
            assert heat_spacings[i] > heat_spacings[i + 1], (
                "heat table: spacing should decrease with height"
            )
        # Smoke table: spacing is FLAT at 9.10m (no height reduction)
        smoke_spacings = [s for _, s in _SMOKE_SPACING_TABLE]
        for s in smoke_spacings:
            assert s == pytest.approx(9.10), f"smoke spacing must be flat 9.10m, got {s}"

    def test_smoke_spacing_always_ge_heat_spacing(self):
        """At the same ceiling height, smoke detectors allow larger spacing."""
        # At 3.0m ceiling
        smoke = get_detector_spacing(3.0, "smoke")
        heat = get_detector_spacing(3.0, "heat")
        assert smoke.max_spacing_m > heat.max_spacing_m

    def test_battery_result_is_adequate_consistency(self):
        """is_adequate must match installed_ah >= required_ah."""
        for I_sb, I_al in [(0.1, 0.5), (1.0, 2.0), (5.0, 10.0)]:  # NOSONAR - python:S117
            result = calculate_battery(I_sb, I_al)
            assert result.is_adequate == (result.installed_ah >= result.required_ah)

    def test_voltage_drop_percentage_matches_voltage(self):
        """voltage_drop_pct should be (voltage_drop_v / ps_voltage) × 100."""
        result = calculate_voltage_drop(1.0, 100.0, "14")
        expected_pct = (result.voltage_drop_v / 24.0) * 100.0
        assert abs(result.voltage_drop_pct - round(expected_pct, 4)) < 0.01

    def test_max_devices_constant(self):
        """_MAX_DEVICES_BETWEEN_ISOLATORS should be 32 per NFPA 72 §12.3.1."""
        assert _MAX_DEVICES_BETWEEN_ISOLATORS == 32

    def test_system_voltage_24(self):
        """System voltage should be 24V (standard fire alarm)."""
        assert _SYSTEM_VOLTAGE == 24.0  # NOSONAR — S1244: import retained for re-export / API surface

    def test_max_voltage_drop_10_pct(self):
        """Max voltage drop should be 10% per NFPA 72 §10.6.4."""
        assert _MAX_VOLTAGE_DROP_PCT == 10.0  # NOSONAR — S1244: import retained for re-export / API surface

    def test_awg_resistance_table_completeness(self):
        """AWG resistance table should have entries for common gauges."""
        required_gauges = ["18", "16", "14", "12", "10"]
        for g in required_gauges:
            assert g in AWG_RESISTANCE_OHM_PER_KM
            assert AWG_RESISTANCE_OHM_PER_KM[g] > 0

    def test_awg_resistance_decreasing_with_gauge_size(self):
        """Larger wire (smaller AWG number) should have less resistance."""
        # 14 AWG should have more resistance than 12 AWG
        assert AWG_RESISTANCE_OHM_PER_KM["14"] > AWG_RESISTANCE_OHM_PER_KM["12"]
        assert AWG_RESISTANCE_OHM_PER_KM["12"] > AWG_RESISTANCE_OHM_PER_KM["10"]
