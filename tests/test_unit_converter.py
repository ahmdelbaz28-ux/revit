"""
tests/test_unit_converter.py
=============================
Comprehensive test suite for fireai/core/unit_converter.py

SAFETY CRITICAL: Incorrect unit conversions in BIM/Revit integration lead to
catastrophic engineering errors. A pipe sized in feet instead of metres, or a
pressure in psf instead of psi, can cause undersized fire suppression systems
that fail during a real fire, costing lives.

Standards:
  - NIST SP 811: Exact conversion factors
  - Revit API: Internal lengths are decimal feet (1 ft = 0.3048 m exactly)
  - NFPA 13-2022 Chapter 23: Hydraulic calculation units
"""

from __future__ import annotations

import math
import pytest

from fireai.core.unit_converter import (
    # Conversion factors
    FEET_TO_METRES,
    METRES_TO_FEET,
    INCHES_TO_MM,
    MM_TO_INCHES,
    FEET_TO_MM,
    MM_TO_FEET,
    METRES_TO_MM,
    MM_TO_METRES,
    SQFT_TO_SQM,
    SQM_TO_SQFT,
    SQIN_TO_SQMM,
    SQMM_TO_SQIN,
    CUBIC_FT_TO_CUBIC_M,
    CUBIC_M_TO_CUBIC_FT,
    GALLONS_US_TO_LITRES,
    LITRES_TO_GALLONS_US,
    PSI_TO_BAR,
    BAR_TO_PSI,
    PSI_TO_KPA,
    KPA_TO_PSI,
    PSF_TO_PSI,
    PSI_TO_PSF,
    PA_TO_PSI,
    GPM_TO_LPM,
    LPM_TO_GPM,
    FAHRENHEIT_OFFSET,
    FAHRENHEIT_SCALE,
    # Functions
    revit_internal_to_metres,
    metres_to_revit_internal,
    revit_internal_to_mm,
    mm_to_revit_internal,
    inches_to_mm,
    psi_to_bar,
    bar_to_psi,
    gpm_to_lpm,
    sqft_to_sqm,
    fahrenheit_to_celsius,
    celsius_to_fahrenheit,
    convert_polygon_revit_to_metres,
)


# ─────────────────────────────────────────────────────────────────────────────
# Exact Conversion Factors (NIST SP 811)
# ─────────────────────────────────────────────────────────────────────────────


class TestExactConversionFactors:
    """Verify all conversion factors match NIST definitions exactly."""

    def test_feet_to_metres_exact(self):
        """1 ft = 0.3048 m exactly (since 1959)."""
        assert FEET_TO_METRES == 0.3048

    def test_metres_to_feet_inverse(self):
        assert METRES_TO_FEET == pytest.approx(1.0 / 0.3048)

    def test_inches_to_mm_exact(self):
        """1 in = 25.4 mm exactly (since 1959)."""
        assert INCHES_TO_MM == 25.4

    def test_mm_to_inches_inverse(self):
        assert MM_TO_INCHES == pytest.approx(1.0 / 25.4)

    def test_feet_to_mm_composition(self):
        """FEET_TO_MM = FEET_TO_METRES × 1000."""
        assert FEET_TO_MM == FEET_TO_METRES * 1000.0

    def test_mm_to_feet_inverse(self):
        assert MM_TO_FEET == pytest.approx(1.0 / FEET_TO_MM)

    def test_sqft_to_sqm_exact(self):
        """1 ft² = 0.3048² = 0.09290304 m² exactly."""
        assert SQFT_TO_SQM == 0.09290304
        assert SQFT_TO_SQM == FEET_TO_METRES ** 2

    def test_sqm_to_sqft_inverse(self):
        assert SQM_TO_SQFT == pytest.approx(1.0 / 0.09290304)

    def test_sqin_to_sqmm_exact(self):
        """1 in² = 25.4² = 645.16 mm² exactly."""
        assert SQIN_TO_SQMM == 645.16
        assert SQIN_TO_SQMM == INCHES_TO_MM ** 2

    def test_cubic_ft_to_cubic_m_exact(self):
        """1 ft³ = 0.3048³ = 0.028316846592 m³ exactly."""
        assert CUBIC_FT_TO_CUBIC_M == pytest.approx(0.3048 ** 3)

    def test_gallons_to_litres_exact(self):
        """1 US gal = 3.785411784 L exactly."""
        assert GALLONS_US_TO_LITRES == 3.785411784

    def test_litres_to_gallons_inverse(self):
        assert LITRES_TO_GALLONS_US == pytest.approx(1.0 / 3.785411784)

    def test_psi_to_bar_approx(self):
        """1 psi ≈ 0.0689476 bar."""
        assert PSI_TO_BAR == pytest.approx(0.0689476, rel=1e-6)

    def test_bar_to_psi_inverse(self):
        assert BAR_TO_PSI == pytest.approx(1.0 / 0.0689476, rel=1e-6)

    def test_psi_to_kpa_approx(self):
        """1 psi ≈ 6.89476 kPa."""
        assert PSI_TO_KPA == pytest.approx(6.89476, rel=1e-6)

    def test_psf_to_psi_exact(self):
        """1 psi = 144 psf."""
        assert PSF_TO_PSI == 1.0 / 144.0
        assert PSI_TO_PSF == 144.0

    def test_gpm_to_lpm_same_as_gallons(self):
        """1 US gpm = 3.785411784 L/min (same factor as gallons→litres)."""
        assert GPM_TO_LPM == GALLONS_US_TO_LITRES

    def test_lpm_to_gpm_inverse(self):
        assert LPM_TO_GPM == pytest.approx(1.0 / 3.785411784)

    def test_fahrenheit_constants(self):
        assert FAHRENHEIT_OFFSET == 32.0
        assert FAHRENHEIT_SCALE == pytest.approx(5.0 / 9.0)


# ─────────────────────────────────────────────────────────────────────────────
# revit_internal_to_metres / metres_to_revit_internal
# ─────────────────────────────────────────────────────────────────────────────


class TestRevitInternalConversions:
    """CRITICAL: Revit stores ALL lengths as decimal feet internally."""

    def test_one_foot_to_metres(self):
        assert revit_internal_to_metres(1.0) == pytest.approx(0.3048)

    def test_zero_feet_to_metres(self):
        assert revit_internal_to_metres(0.0) == 0.0

    def test_negative_feet_to_metres(self):
        """Revit can have negative coordinates (e.g. below origin)."""
        assert revit_internal_to_metres(-1.0) == pytest.approx(-0.3048)

    def test_large_value(self):
        """1000 ft = 304.8 m."""
        assert revit_internal_to_metres(1000.0) == pytest.approx(304.8)

    def test_nan_rejected(self):
        with pytest.raises(ValueError, match="non-finite"):
            revit_internal_to_metres(float("nan"))

    def test_inf_rejected(self):
        with pytest.raises(ValueError, match="non-finite"):
            revit_internal_to_metres(float("inf"))

    def test_neg_inf_rejected(self):
        with pytest.raises(ValueError, match="non-finite"):
            revit_internal_to_metres(float("-inf"))

    def test_round_trip_feet_to_metres_to_feet(self):
        """Converting ft→m→ft must return original value."""
        original = 42.5
        result = metres_to_revit_internal(revit_internal_to_metres(original))
        assert result == pytest.approx(original, rel=1e-10)

    def test_metres_to_revit_internal(self):
        """1 m = 1/0.3048 ≈ 3.28084 ft."""
        assert metres_to_revit_internal(1.0) == pytest.approx(1.0 / 0.3048)

    def test_metres_negative_rejected(self):
        """Physical length cannot be negative when converting TO Revit."""
        with pytest.raises(ValueError, match="Negative"):
            metres_to_revit_internal(-1.0)

    def test_metres_nan_rejected(self):
        with pytest.raises(ValueError, match="non-finite"):
            metres_to_revit_internal(float("nan"))

    def test_metres_inf_rejected(self):
        with pytest.raises(ValueError, match="non-finite"):
            metres_to_revit_internal(float("inf"))

    def test_metres_zero_allowed(self):
        assert metres_to_revit_internal(0.0) == 0.0


# ─────────────────────────────────────────────────────────────────────────────
# revit_internal_to_mm / mm_to_revit_internal
# ─────────────────────────────────────────────────────────────────────────────


class TestRevitInternalMMConversions:
    def test_one_foot_to_mm(self):
        """1 ft = 304.8 mm."""
        assert revit_internal_to_mm(1.0) == pytest.approx(304.8)

    def test_zero_feet_to_mm(self):
        assert revit_internal_to_mm(0.0) == 0.0

    def test_nan_rejected(self):
        with pytest.raises(ValueError, match="non-finite"):
            revit_internal_to_mm(float("nan"))

    def test_inf_rejected(self):
        with pytest.raises(ValueError, match="non-finite"):
            revit_internal_to_mm(float("inf"))

    def test_mm_to_revit_internal(self):
        """304.8 mm = 1 ft."""
        assert mm_to_revit_internal(304.8) == pytest.approx(1.0, rel=1e-6)

    def test_mm_nan_rejected(self):
        with pytest.raises(ValueError, match="non-finite"):
            mm_to_revit_internal(float("nan"))

    def test_mm_inf_rejected(self):
        with pytest.raises(ValueError, match="non-finite"):
            mm_to_revit_internal(float("inf"))

    def test_round_trip_mm(self):
        """mm → ft → mm must return original."""
        original_mm = 1500.0  # 1.5 m
        result = revit_internal_to_mm(mm_to_revit_internal(original_mm))
        assert result == pytest.approx(original_mm, rel=1e-6)


# ─────────────────────────────────────────────────────────────────────────────
# inches_to_mm
# ─────────────────────────────────────────────────────────────────────────────


class TestInchesToMm:
    def test_one_inch(self):
        assert inches_to_mm(1.0) == pytest.approx(25.4)

    def test_two_inches(self):
        assert inches_to_mm(2.0) == pytest.approx(50.8)

    def test_pipe_diameter(self):
        """2" Schedule 40 internal diameter = 2.067" → 52.5 mm."""
        result = inches_to_mm(2.067)
        assert result == pytest.approx(52.5018, rel=1e-3)

    def test_zero_inches(self):
        assert inches_to_mm(0.0) == 0.0

    def test_negative_inches_rejected(self):
        with pytest.raises(ValueError, match="Negative"):
            inches_to_mm(-1.0)

    def test_nan_rejected(self):
        with pytest.raises(ValueError, match="non-finite"):
            inches_to_mm(float("nan"))

    def test_inf_rejected(self):
        with pytest.raises(ValueError, match="non-finite"):
            inches_to_mm(float("inf"))


# ─────────────────────────────────────────────────────────────────────────────
# Pressure Conversions
# ─────────────────────────────────────────────────────────────────────────────


class TestPressureConversions:
    def test_psi_to_bar_standard(self):
        """100 psi ≈ 6.89476 bar."""
        result = psi_to_bar(100.0)
        assert result == pytest.approx(100.0 * 0.0689476, rel=1e-6)

    def test_bar_to_psi_standard(self):
        """1 bar ≈ 14.5038 psi."""
        result = bar_to_psi(1.0)
        assert result == pytest.approx(1.0 / 0.0689476, rel=1e-4)

    def test_psi_bar_round_trip(self):
        original = 175.0
        result = bar_to_psi(psi_to_bar(original))
        assert result == pytest.approx(original, rel=1e-6)

    def test_zero_psi_to_bar(self):
        assert psi_to_bar(0.0) == 0.0

    def test_negative_psi_allowed(self):
        """Negative pressure (vacuum) is physically meaningful."""
        result = psi_to_bar(-14.7)
        assert result < 0

    def test_psi_nan_rejected(self):
        with pytest.raises(ValueError, match="non-finite"):
            psi_to_bar(float("nan"))

    def test_psi_inf_rejected(self):
        with pytest.raises(ValueError, match="non-finite"):
            psi_to_bar(float("inf"))

    def test_bar_nan_rejected(self):
        with pytest.raises(ValueError, match="non-finite"):
            bar_to_psi(float("nan"))

    def test_bar_inf_rejected(self):
        with pytest.raises(ValueError, match="non-finite"):
            bar_to_psi(float("inf"))


# ─────────────────────────────────────────────────────────────────────────────
# Flow Rate Conversions
# ─────────────────────────────────────────────────────────────────────────────


class TestFlowRateConversions:
    def test_gpm_to_lpm_standard(self):
        """100 gpm ≈ 378.5 L/min."""
        result = gpm_to_lpm(100.0)
        assert result == pytest.approx(100.0 * 3.785411784, rel=1e-6)

    def test_zero_gpm(self):
        assert gpm_to_lpm(0.0) == 0.0

    def test_negative_gpm_rejected(self):
        """Flow rate cannot be negative."""
        with pytest.raises(ValueError, match="Negative"):
            gpm_to_lpm(-10.0)

    def test_gpm_nan_rejected(self):
        with pytest.raises(ValueError, match="non-finite"):
            gpm_to_lpm(float("nan"))

    def test_gpm_inf_rejected(self):
        with pytest.raises(ValueError, match="non-finite"):
            gpm_to_lpm(float("inf"))


# ─────────────────────────────────────────────────────────────────────────────
# Area Conversions
# ─────────────────────────────────────────────────────────────────────────────


class TestAreaConversions:
    def test_sqft_to_sqm_standard(self):
        """100 ft² = 9.290304 m²."""
        result = sqft_to_sqm(100.0)
        assert result == pytest.approx(9.290304, rel=1e-6)

    def test_zero_sqft(self):
        assert sqft_to_sqm(0.0) == 0.0

    def test_negative_sqft_rejected(self):
        with pytest.raises(ValueError, match="Negative"):
            sqft_to_sqm(-10.0)

    def test_sqft_nan_rejected(self):
        with pytest.raises(ValueError, match="non-finite"):
            sqft_to_sqm(float("nan"))

    def test_sqft_inf_rejected(self):
        with pytest.raises(ValueError, match="non-finite"):
            sqft_to_sqm(float("inf"))


# ─────────────────────────────────────────────────────────────────────────────
# Temperature Conversions
# ─────────────────────────────────────────────────────────────────────────────


class TestTemperatureConversions:
    def test_freezing_point(self):
        """32°F = 0°C."""
        assert fahrenheit_to_celsius(32.0) == pytest.approx(0.0)

    def test_boiling_point(self):
        """212°F = 100°C."""
        assert fahrenheit_to_celsius(212.0) == pytest.approx(100.0)

    def test_body_temperature(self):
        """98.6°F = 37°C."""
        assert fahrenheit_to_celsius(98.6) == pytest.approx(37.0)

    def test_celsius_to_fahrenheit_freezing(self):
        """0°C = 32°F."""
        assert celsius_to_fahrenheit(0.0) == pytest.approx(32.0)

    def test_celsius_to_fahrenheit_boiling(self):
        """100°C = 212°F."""
        assert celsius_to_fahrenheit(100.0) == pytest.approx(212.0)

    def test_round_trip_f_to_c_to_f(self):
        original = 72.5
        result = celsius_to_fahrenheit(fahrenheit_to_celsius(original))
        assert result == pytest.approx(original, rel=1e-10)

    def test_round_trip_c_to_f_to_c(self):
        original = 25.3
        result = fahrenheit_to_celsius(celsius_to_fahrenheit(original))
        assert result == pytest.approx(original, rel=1e-10)

    def test_negative_fahrenheit(self):
        """-40°F = -40°C (the crossover point)."""
        assert fahrenheit_to_celsius(-40.0) == pytest.approx(-40.0)

    def test_fahrenheit_nan_rejected(self):
        with pytest.raises(ValueError, match="non-finite"):
            fahrenheit_to_celsius(float("nan"))

    def test_fahrenheit_inf_rejected(self):
        with pytest.raises(ValueError, match="non-finite"):
            fahrenheit_to_celsius(float("inf"))

    def test_celsius_nan_rejected(self):
        with pytest.raises(ValueError, match="non-finite"):
            celsius_to_fahrenheit(float("nan"))

    def test_celsius_inf_rejected(self):
        with pytest.raises(ValueError, match="non-finite"):
            celsius_to_fahrenheit(float("inf"))


# ─────────────────────────────────────────────────────────────────────────────
# Polygon Conversion
# ─────────────────────────────────────────────────────────────────────────────


class TestConvertPolygonRevitToMetres:
    def test_simple_square(self):
        """10ft × 10ft room → 3.048m × 3.048m."""
        poly_revit = [(0, 0), (10, 0), (10, 10), (0, 10)]
        result = convert_polygon_revit_to_metres(poly_revit)
        assert len(result) == 4
        assert result[0] == pytest.approx((0.0, 0.0))
        assert result[1] == pytest.approx((10 * 0.3048, 0.0))
        assert result[2] == pytest.approx((10 * 0.3048, 10 * 0.3048))

    def test_empty_polygon(self):
        result = convert_polygon_revit_to_metres([])
        assert result == []

    def test_single_point(self):
        result = convert_polygon_revit_to_metres([(1.0, 2.0)])
        assert result == pytest.approx([(1.0 * 0.3048, 2.0 * 0.3048)])

    def test_nan_coordinate_rejected(self):
        with pytest.raises(ValueError, match="Non-finite"):
            convert_polygon_revit_to_metres([(float("nan"), 0.0)])

    def test_inf_coordinate_rejected(self):
        with pytest.raises(ValueError, match="Non-finite"):
            convert_polygon_revit_to_metres([(0.0, float("inf"))])

    def test_negative_coordinates_allowed(self):
        """Negative coords are valid in Revit (e.g. below origin)."""
        result = convert_polygon_revit_to_metres([(-5.0, -10.0)])
        assert result[0][0] < 0
        assert result[0][1] < 0

    def test_l_shape_polygon(self):
        """L-shaped room from Revit."""
        poly_revit = [(0, 0), (20, 0), (20, 10), (10, 10), (10, 20), (0, 20)]
        result = convert_polygon_revit_to_metres(poly_revit)
        assert len(result) == 6
        for x, y in result:
            assert isinstance(x, float)
            assert isinstance(y, float)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
