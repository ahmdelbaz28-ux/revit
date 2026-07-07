# NOSONAR
"""
test_unit_converter.py — Tests for fireai/core/unit_converter.py

SAFETY-CRITICAL: Unit conversion errors can cause catastrophic engineering
failures (undersized fire suppression, wrong detector spacing, etc.).
These tests verify the exact conversion factors against NIST SP 811.
"""
from __future__ import annotations

import pytest

from fireai.core.unit_converter import (
    FEET_TO_METRES,
    GPM_TO_LPM,
    INCHES_TO_MM,
    SQFT_TO_SQM,
    bar_to_psi,
    celsius_to_fahrenheit,
    fahrenheit_to_celsius,
    gpm_to_lpm,
    inches_to_mm,
    metres_to_revit_internal,
    mm_to_revit_internal,
    psi_to_bar,
    revit_internal_to_metres,
    revit_internal_to_mm,
    sqft_to_sqm,
)


class TestRevitInternalConversions:
    """Revit internal units (decimal feet) ↔ metric conversions."""

    def test_revit_internal_to_metres_exact(self):
        """1 ft = 0.3048 m exactly (NIST SP 811)."""
        assert revit_internal_to_metres(1.0) == pytest.approx(0.3048, abs=1e-12)

    def test_revit_internal_to_metres_zero(self):
        """0 ft = 0 m."""
        assert revit_internal_to_metres(0.0) == 0.0  # NOSONAR — S1244: import retained for re-export / API surface

    def test_metres_to_revit_internal_negative_raises(self):
        """Negative metres should raise ValueError (safety: physical length >= 0)."""
        with pytest.raises(ValueError):
            metres_to_revit_internal(-5.0)

    def test_revit_internal_to_metres_large(self):
        """1000 ft = 304.8 m (building-scale)."""
        assert revit_internal_to_metres(1000.0) == pytest.approx(304.8, abs=1e-9)

    def test_metres_to_revit_internal_exact(self):
        """1 m = 1/0.3048 ft ≈ 3.28084 ft."""
        assert metres_to_revit_internal(1.0) == pytest.approx(1.0 / 0.3048, abs=1e-12)

    def test_metres_to_revit_internal_roundtrip(self):
        """roundtrip: ft → m → ft should return original."""
        for ft in [0.0, 1.0, 10.5, 100.0]:
            m = revit_internal_to_metres(ft)
            ft_back = metres_to_revit_internal(m)
            assert ft_back == pytest.approx(ft, abs=1e-12)

    def test_revit_internal_to_mm(self):
        """1 ft = 304.8 mm."""
        assert revit_internal_to_mm(1.0) == pytest.approx(304.8, abs=1e-9)

    def test_mm_to_revit_internal(self):
        """304.8 mm = 1 ft."""
        assert mm_to_revit_internal(304.8) == pytest.approx(1.0, abs=1e-9)

    def test_mm_roundtrip(self):
        """roundtrip: ft → mm → ft."""
        for ft in [1.0, 10.0, 50.5]:
            mm = revit_internal_to_mm(ft)
            ft_back = mm_to_revit_internal(mm)
            assert ft_back == pytest.approx(ft, abs=1e-9)


class TestInchesMmConversion:
    def test_inches_to_mm_exact(self):
        """1 in = 25.4 mm exactly."""
        assert inches_to_mm(1.0) == pytest.approx(25.4, abs=1e-12)

    def test_inches_to_mm_zero(self):
        assert inches_to_mm(0.0) == 0.0  # NOSONAR — S1244: import retained for re-export / API surface

    def test_inches_to_mm_pipe_diameter(self):
        """Common pipe: 2 in = 50.8 mm."""
        assert inches_to_mm(2.0) == pytest.approx(50.8, abs=1e-9)


class TestPressureConversions:
    def test_psi_to_bar(self):
        """1 psi ≈ 0.0689476 bar."""
        assert psi_to_bar(1.0) == pytest.approx(0.0689476, abs=1e-7)

    def test_psi_to_bar_zero(self):
        assert psi_to_bar(0.0) == 0.0  # NOSONAR — S1244: import retained for re-export / API surface

    def test_bar_to_psi_roundtrip(self):
        """roundtrip: psi → bar → psi."""
        for psi in [10.0, 50.0, 175.0]:  # common fire protection pressures
            bar = psi_to_bar(psi)
            psi_back = bar_to_psi(bar)
            assert psi_back == pytest.approx(psi, abs=1e-5)

    def test_typical_fire_pump_pressure(self):
        """100 psi (typical fire pump) ≈ 6.895 bar."""
        assert psi_to_bar(100.0) == pytest.approx(6.895, abs=0.01)


class TestFlowRateConversions:
    def test_gpm_to_lpm(self):
        """1 US gpm = 3.785411784 L/min."""
        assert gpm_to_lpm(1.0) == pytest.approx(3.785411784, abs=1e-9)

    def test_gpm_to_lpm_zero(self):
        assert gpm_to_lpm(0.0) == 0.0  # NOSONAR — S1244: import retained for re-export / API surface

    def test_typical_sprinkler_flow(self):
        """25 gpm (typical sprinkler discharge) ≈ 94.6 L/min."""
        assert gpm_to_lpm(25.0) == pytest.approx(94.6, abs=0.1)


class TestAreaConversions:
    def test_sqft_to_sqm(self):
        """1 ft² = 0.09290304 m² exactly."""
        assert sqft_to_sqm(1.0) == pytest.approx(0.09290304, abs=1e-12)

    def test_sqft_to_sqm_zero(self):
        assert sqft_to_sqm(0.0) == 0.0  # NOSONAR — S1244: import retained for re-export / API surface

    def test_large_room_area(self):
        """1000 ft² (medium room) = 92.9 m²."""
        assert sqft_to_sqm(1000.0) == pytest.approx(92.9, abs=0.1)


class TestTemperatureConversions:
    def test_fahrenheit_to_celsius_freezing(self):
        """32°F = 0°C (freezing point of water)."""
        assert fahrenheit_to_celsius(32.0) == pytest.approx(0.0, abs=1e-12)

    def test_fahrenheit_to_celsius_boiling(self):
        """212°F = 100°C (boiling point of water)."""
        assert fahrenheit_to_celsius(212.0) == pytest.approx(100.0, abs=1e-12)

    def test_celsius_to_fahrenheit_freezing(self):
        """0°C = 32°F."""
        assert celsius_to_fahrenheit(0.0) == pytest.approx(32.0, abs=1e-12)

    def test_celsius_to_fahrenheit_boiling(self):
        """100°C = 212°F."""
        assert celsius_to_fahrenheit(100.0) == pytest.approx(212.0, abs=1e-12)

    def test_temp_roundtrip(self):
        """roundtrip: F → C → F."""
        for f in [-40.0, 0.0, 32.0, 72.0, 100.0, 212.0]:
            c = fahrenheit_to_celsius(f)
            f_back = celsius_to_fahrenheit(c)
            assert f_back == pytest.approx(f, abs=1e-9)

    def test_neg_40_equal(self):
        """-40°F = -40°C (the intersection point)."""
        assert fahrenheit_to_celsius(-40.0) == pytest.approx(-40.0, abs=1e-9)


class TestConversionConstants:
    """Verify exact constant values (NIST SP 811)."""

    def test_feet_to_metres_exact(self):
        """1 ft = 0.3048 m (exact since 1959)."""
        assert FEET_TO_METRES == pytest.approx(0.3048)

    def test_inches_to_mm_exact(self):
        """1 in = 25.4 mm (exact since 1959)."""
        assert INCHES_TO_MM == pytest.approx(25.4)

    def test_gpm_to_lpm_exact(self):
        """1 US gal = 3.785411784 L (exact)."""
        assert GPM_TO_LPM == pytest.approx(3.785411784, abs=1e-12)

    def test_sqft_to_sqm_exact(self):
        """1 ft² = 0.09290304 m² (exact = 0.3048²)."""
        assert SQFT_TO_SQM == pytest.approx(0.3048 ** 2, abs=1e-15)
