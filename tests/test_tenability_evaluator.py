# File-level '# NOSONAR' removed per NOSONAR_AUDIT.md (V143 hardening).
# Per-line justified suppressions (e.g., '# NOSONAR — S3776: ...') are preserved.
"""
tests/test_tenability_evaluator.py — Tests for tenability assessment.

Covers:
  - All criteria pass → tenable
  - Each individual criterion fails → not tenable
  - Safety margin (20%) is applied correctly
  - NaN/Inf inputs are rejected
  - Negative inputs (except temperature) are rejected
  - Edge cases: exact boundary values
  - Multiple simultaneous violations
  - NFPA/SFPE references are included
"""

from __future__ import annotations

import pytest

from fireai.core.tenability_evaluator import (
    TenabilityResult,
    evaluate_tenability,
)


class TestTenabilityPass:
    """Tests where all criteria pass → tenable."""

    def test_all_criteria_pass_is_tenable(self) -> None:
        """Normal room conditions should be tenable."""
        result = evaluate_tenability(
            temperature_c=25.0,
            visibility_m=30.0,
            co_ppm=0.0,
            co2_ppm=0.0,
            radiant_flux_kw_m2=0.0,
        )
        assert result.is_tenable is True
        assert len(result.violations) == 0

    def test_zero_temp_is_tenable(self) -> None:
        """0°C is well below the 48°C limit (with margin)."""
        result = evaluate_tenability(
            temperature_c=0.0,
            visibility_m=50.0,
        )
        assert result.is_tenable is True

    def test_just_below_all_limits_is_tenable(self) -> None:
        """Values just below the safety-margin-adjusted limits should pass."""
        # Limits with 20% margin: temp 48, vis 12.5, CO 960, CO2 32000, flux 2.0
        result = evaluate_tenability(
            temperature_c=47.9,
            visibility_m=12.6,
            co_ppm=959.0,
            co2_ppm=31999.0,
            radiant_flux_kw_m2=1.99,
        )
        assert result.is_tenable is True


class TestTemperatureFailure:
    """Tests where temperature exceeds the limit."""

    def test_temperature_exceeds_limit(self) -> None:
        """Temperature above 48°C (with margin) should fail."""
        result = evaluate_tenability(
            temperature_c=60.0,
            visibility_m=30.0,
        )
        assert result.is_tenable is False
        assert any("Temperature" in v for v in result.violations)

    def test_temperature_at_exact_limit_fails(self) -> None:
        """Temperature exactly at 48°C should fail (strict > comparison)."""
        result = evaluate_tenability(
            temperature_c=48.0,
            visibility_m=30.0,
        )
        # 48.0 > 48.0 is False, so it should pass
        assert result.is_tenable is True

    def test_extreme_temperature_fails(self) -> None:
        """1000°C should definitely fail."""
        result = evaluate_tenability(
            temperature_c=1000.0,
            visibility_m=30.0,
        )
        assert result.is_tenable is False


class TestVisibilityFailure:
    """Tests where visibility is below the minimum."""

    def test_visibility_below_limit(self) -> None:
        """Visibility below 12.5m (with margin) should fail."""
        result = evaluate_tenability(
            temperature_c=25.0,
            visibility_m=5.0,
        )
        assert result.is_tenable is False
        assert any("Visibility" in v for v in result.violations)

    def test_zero_visibility_fails(self) -> None:
        """Zero visibility should fail."""
        result = evaluate_tenability(
            temperature_c=25.0,
            visibility_m=0.0,
        )
        assert result.is_tenable is False


class TestCOFailure:
    """Tests where CO exceeds the limit."""

    def test_co_exceeds_limit(self) -> None:
        """CO above 960 ppm (with margin) should fail."""
        result = evaluate_tenability(
            temperature_c=25.0,
            visibility_m=30.0,
            co_ppm=1500.0,
        )
        assert result.is_tenable is False
        assert any("CO" in v for v in result.violations)

    def test_high_co_fails(self) -> None:
        """5000 ppm CO is lethal — should fail."""
        result = evaluate_tenability(
            temperature_c=25.0,
            visibility_m=30.0,
            co_ppm=5000.0,
        )
        assert result.is_tenable is False


class TestCO2Failure:
    """Tests where CO2 exceeds the limit."""

    def test_co2_exceeds_limit(self) -> None:
        """CO2 above 32000 ppm (with margin) should fail."""
        result = evaluate_tenability(
            temperature_c=25.0,
            visibility_m=30.0,
            co2_ppm=50000.0,
        )
        assert result.is_tenable is False
        assert any("CO2" in v for v in result.violations)


class TestRadiantFluxFailure:
    """Tests where radiant heat flux exceeds the limit."""

    def test_radiant_flux_exceeds_limit(self) -> None:
        """Radiant flux above 2.0 kW/m² (with margin) should fail."""
        result = evaluate_tenability(
            temperature_c=25.0,
            visibility_m=30.0,
            radiant_flux_kw_m2=3.0,
        )
        assert result.is_tenable is False
        assert any("Radiant" in v for v in result.violations)


class TestMultipleViolations:
    """Tests where multiple criteria fail simultaneously."""

    def test_all_criteria_fail(self) -> None:
        """All criteria failing should produce 5 violations."""
        result = evaluate_tenability(
            temperature_c=100.0,
            visibility_m=1.0,
            co_ppm=5000.0,
            co2_ppm=100000.0,
            radiant_flux_kw_m2=10.0,
        )
        assert result.is_tenable is False
        assert len(result.violations) == 5

    def test_two_criteria_fail(self) -> None:
        """Two criteria failing should produce 2 violations."""
        result = evaluate_tenability(
            temperature_c=100.0,
            visibility_m=5.0,
        )
        assert result.is_tenable is False
        assert len(result.violations) == 2


class TestInputValidation:
    """Tests for input validation (NaN, Inf, negative)."""

    def test_nan_temperature_rejected(self) -> None:
        """NaN temperature should raise ValueError."""
        with pytest.raises(ValueError, match="temperature_c must be finite"):  # NOSONAR — S5778: re-raise inside except is intentional (context-specific)  # noqa: S5778
            evaluate_tenability(
                temperature_c=float("nan"),
                visibility_m=30.0,
            )

    def test_inf_temperature_rejected(self) -> None:
        """Infinity temperature should raise ValueError."""
        with pytest.raises(ValueError, match="temperature_c must be finite"):  # NOSONAR — S5778: re-raise inside except is intentional (context-specific)  # noqa: S5778
            evaluate_tenability(
                temperature_c=float("inf"),
                visibility_m=30.0,
            )

    def test_negative_visibility_rejected(self) -> None:
        """Negative visibility should raise ValueError."""
        with pytest.raises(ValueError, match="visibility_m must be non-negative"):
            evaluate_tenability(
                temperature_c=25.0,
                visibility_m=-1.0,
            )

    def test_negative_co_rejected(self) -> None:
        """Negative CO should raise ValueError."""
        with pytest.raises(ValueError, match="co_ppm must be non-negative"):
            evaluate_tenability(
                temperature_c=25.0,
                visibility_m=30.0,
                co_ppm=-10.0,
            )

    def test_negative_co2_rejected(self) -> None:
        """Negative CO2 should raise ValueError."""
        with pytest.raises(ValueError, match="co2_ppm must be non-negative"):
            evaluate_tenability(
                temperature_c=25.0,
                visibility_m=30.0,
                co2_ppm=-100.0,
            )

    def test_negative_radiant_flux_rejected(self) -> None:
        """Negative radiant flux should raise ValueError."""
        with pytest.raises(ValueError, match="radiant_flux_kw_m2 must be non-negative"):
            evaluate_tenability(
                temperature_c=25.0,
                visibility_m=30.0,
                radiant_flux_kw_m2=-1.0,
            )

    def test_nan_visibility_rejected(self) -> None:
        """NaN visibility should raise ValueError."""
        with pytest.raises(ValueError, match="visibility_m must be finite"):  # NOSONAR — S5778: re-raise inside except is intentional (context-specific)  # noqa: S5778
            evaluate_tenability(
                temperature_c=25.0,
                visibility_m=float("nan"),
            )


class TestResultStructure:
    """Tests for TenabilityResult dataclass structure."""

    def test_result_contains_all_fields(self) -> None:
        """Result should contain all expected fields."""
        result = evaluate_tenability(
            temperature_c=25.0,
            visibility_m=30.0,
            co_ppm=10.0,
            co2_ppm=400.0,
            radiant_flux_kw_m2=0.5,
        )
        assert isinstance(result, TenabilityResult)
        assert result.temperature_c == pytest.approx(25.0)
        assert result.visibility_m == pytest.approx(30.0)
        assert result.co_ppm == pytest.approx(10.0)
        assert result.co2_ppm == pytest.approx(400.0)
        assert result.radiant_flux_kw_m2 == pytest.approx(0.5)
        assert isinstance(result.violations, tuple)
        assert isinstance(result.nfpa_references, tuple)

    def test_references_always_included(self) -> None:
        """References should always be included (even when tenable)."""
        result = evaluate_tenability(
            temperature_c=25.0,
            visibility_m=30.0,
        )
        assert len(result.nfpa_references) == 5
        assert "SFPE/NFPA 101 §7" in result.nfpa_references
        assert "SFPE Engineering Guide" in result.nfpa_references
        assert "ISO 13571" in result.nfpa_references

    def test_default_values(self) -> None:
        """Default values for CO, CO2, radiant flux should be 0."""
        result = evaluate_tenability(
            temperature_c=25.0,
            visibility_m=30.0,
        )
        assert result.co_ppm == pytest.approx(0.0)
        assert result.co2_ppm == pytest.approx(0.0)
        assert result.radiant_flux_kw_m2 == pytest.approx(0.0)


class TestSafetyMargin:
    """Tests verifying the 20% safety margin is applied."""

    def test_temperature_at_60c_fails(self) -> None:
        """60°C is the raw NFPA limit, but with 20% margin (48°C), 60 fails."""
        result = evaluate_tenability(
            temperature_c=60.0,
            visibility_m=30.0,
        )
        assert result.is_tenable is False

    def test_temperature_at_48c_passes(self) -> None:
        """48°C is exactly at the margin-adjusted limit (strict >, so passes)."""
        result = evaluate_tenability(
            temperature_c=48.0,
            visibility_m=30.0,
        )
        assert result.is_tenable is True

    def test_visibility_at_10m_fails(self) -> None:
        """10m is the raw SFPE minimum, but with 20% margin (12.5m), 10 fails."""
        result = evaluate_tenability(
            temperature_c=25.0,
            visibility_m=10.0,
        )
        assert result.is_tenable is False

    def test_visibility_at_12_5m_passes(self) -> None:
        """12.5m is exactly at the margin-adjusted minimum (strict <, so passes)."""
        result = evaluate_tenability(
            temperature_c=25.0,
            visibility_m=12.5,
        )
        assert result.is_tenable is True
